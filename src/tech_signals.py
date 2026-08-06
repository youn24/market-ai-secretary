"""
src/tech_signals.py — 明確なテクニカルシグナルの検出＋即時アラート

「誰が見ても同じ判定になる」教科書的なシグナルだけを機械的に検出し、
発生したタイミングでTelegramへ通知する。

検出するシグナル（優先度順）:
  1. ゴールデンクロス / デッドクロス   … MA25 が MA75 を上抜け/下抜け（中期の節目）
  2. 200日移動平均線の上抜け / 下抜け  … 長期トレンドの分岐点
  3. 通常ダイバージェンス（強気/弱気） … トレンド「転換」の予兆
  4. ヒドゥンダイバージェンス          … トレンド「継続」のサイン（divergence.py）
  5. MACD クロス                       … 勢いの転換
  6. ボリンジャーバンド ±2σ 突破       … 過熱・加速
  7. RSI 30/70 からの反転              … 売られすぎ/買われすぎの解消

通知は「1回の実行につき1通」にまとめる（複数出ても通知は増やさない）。
同一銘柄＋同一シグナルは1セッション（JST6時始まり）に1回だけ。
"""

import json
import traceback
from datetime import timedelta

import pandas as pd

from src.utils import setup_logger, get_jst_now, BASE_DIR
from src.divergence import (
    TARGETS, _rsi, _fetch, _pivots,
    _MIN_RSI_DIFF, _MIN_PX_DIFF,
)

logger = setup_logger("tech_signals")

_STATE_FILE = BASE_DIR / "data" / "tech_signal_state.json"

# 通常ダイバージェンス（日足）の判定パラメータ
_D_MIN_GAP = 5      # スイング間隔の下限（本）
_D_MAX_GAP = 60     # スイング間隔の上限（本）
_D_MAX_AGE = 5      # 直近スイングが5本以内＝出来たてのみ


def _last_two(vals: list, idxs: list):
    """直近2つのスイング位置を返す（無ければNone）"""
    return (idxs[-2], idxs[-1]) if len(idxs) >= 2 else (None, None)


# ── 各シグナルの検出 ────────────────────────────────────────────
def _sig_ma_cross(c: pd.Series) -> dict | None:
    """ゴールデンクロス / デッドクロス（MA25 × MA75）"""
    if len(c) < 80:
        return None
    ma25, ma75 = c.rolling(25).mean(), c.rolling(75).mean()
    if pd.isna(ma25.iloc[-2]) or pd.isna(ma75.iloc[-2]):
        return None
    prev = ma25.iloc[-2] - ma75.iloc[-2]
    now  = ma25.iloc[-1] - ma75.iloc[-1]
    if prev <= 0 < now:
        return {"type": "golden_cross", "emoji": "✨", "direction": "buy",
                "label": "ゴールデンクロス発生",
                "desc": f"25日線が75日線を上抜け（{ma25.iloc[-1]:,.2f} > {ma75.iloc[-1]:,.2f}）。",
                "meaning": "中期トレンドが上向きに転換しやすい節目。",
                "tip": "王道の買いサイン。ただし直後は急がず、押し目を待つのが堅実。",
                "priority": 1}
    if prev >= 0 > now:
        return {"type": "dead_cross", "emoji": "⚠️", "direction": "sell",
                "label": "デッドクロス発生",
                "desc": f"25日線が75日線を下抜け（{ma25.iloc[-1]:,.2f} < {ma75.iloc[-1]:,.2f}）。",
                "meaning": "中期トレンドが下向きに転換しやすい節目。",
                "tip": "王道の売りサイン。安易な逆張り買いは禁物。",
                "priority": 1}
    return None


def _sig_ma200(c: pd.Series) -> dict | None:
    """200日移動平均線の上抜け / 下抜け（長期の分岐点）"""
    if len(c) < 210:
        return None
    ma = c.rolling(200).mean()
    if pd.isna(ma.iloc[-2]):
        return None
    prev = c.iloc[-2] - ma.iloc[-2]
    now  = c.iloc[-1] - ma.iloc[-1]
    if prev <= 0 < now:
        return {"type": "ma200_up", "emoji": "🚀", "direction": "buy",
                "label": "200日線を上抜け",
                "desc": f"終値 {c.iloc[-1]:,.2f} が200日線 {ma.iloc[-1]:,.2f} を上回った。",
                "meaning": "長期トレンドが強気側へ切り替わる重要な分岐点。",
                "tip": "機関投資家も意識する節目。定着すれば上昇継続の期待。",
                "priority": 2}
    if prev >= 0 > now:
        return {"type": "ma200_down", "emoji": "🛑", "direction": "sell",
                "label": "200日線を下抜け",
                "desc": f"終値 {c.iloc[-1]:,.2f} が200日線 {ma.iloc[-1]:,.2f} を下回った。",
                "meaning": "長期トレンドが弱気側へ切り替わる重要な分岐点。",
                "tip": "下落が長引きやすい局面。まずは様子見が安全。",
                "priority": 2}
    return None


def _sig_regular_divergence(c: pd.Series) -> dict | None:
    """通常ダイバージェンス（トレンド転換の予兆）"""
    if len(c) < 60:
        return None
    r = _rsi(c)
    if r.isna().all():
        return None
    px, rs, n = c.tolist(), r.tolist(), len(c)

    def _ok(i, j):
        gap = j - i
        return _D_MIN_GAP <= gap <= _D_MAX_GAP and (n - 1 - j) <= _D_MAX_AGE

    # 弱気ダイバージェンス: 高値切り上げ / RSI切り下げ → 上昇の勢い減衰
    highs = [i for i in _pivots(px, "high") if not pd.isna(rs[i])]
    i, j = _last_two(px, highs)
    if i is not None and _ok(i, j):
        px_up  = (px[j] - px[i]) / abs(px[i]) * 100 if px[i] else 0
        rsi_dn = rs[i] - rs[j]
        if px_up >= _MIN_PX_DIFF and rsi_dn >= _MIN_RSI_DIFF:
            return {"type": "bearish_divergence", "emoji": "🔻", "direction": "sell",
                    "label": "弱気ダイバージェンス",
                    "desc": (f"高値を {px[i]:,.2f} → {px[j]:,.2f} と切り上げる一方、"
                             f"RSIは {rs[i]:.0f} → {rs[j]:.0f} と切り下げ。"),
                    "meaning": "上昇の勢いが衰えている。下落へ転換する可能性。",
                    "tip": "高値づかみに注意。利益確定を検討する場面。",
                    "priority": 3}

    # 強気ダイバージェンス: 安値切り下げ / RSI切り上げ → 下落の勢い減衰
    lows = [i for i in _pivots(px, "low") if not pd.isna(rs[i])]
    i, j = _last_two(px, lows)
    if i is not None and _ok(i, j):
        px_dn  = (px[i] - px[j]) / abs(px[i]) * 100 if px[i] else 0
        rsi_up = rs[j] - rs[i]
        if px_dn >= _MIN_PX_DIFF and rsi_up >= _MIN_RSI_DIFF:
            return {"type": "bullish_divergence", "emoji": "🔺", "direction": "buy",
                    "label": "強気ダイバージェンス",
                    "desc": (f"安値を {px[i]:,.2f} → {px[j]:,.2f} と切り下げる一方、"
                             f"RSIは {rs[i]:.0f} → {rs[j]:.0f} と切り上げ。"),
                    "meaning": "下落の勢いが衰えている。上昇へ転換する可能性。",
                    "tip": "反発狙いの目安。下げ止まりを確認してから少しずつ。",
                    "priority": 3}
    return None


def _sig_macd(c: pd.Series) -> dict | None:
    """MACD がシグナル線を上抜け / 下抜け（勢いの転換）"""
    if len(c) < 40:
        return None
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    macd  = ema12 - ema26
    sig   = macd.ewm(span=9, adjust=False).mean()
    hist  = macd - sig
    if len(hist) < 2 or pd.isna(hist.iloc[-2]):
        return None
    prev, now = hist.iloc[-2], hist.iloc[-1]
    if prev <= 0 < now:
        return {"type": "macd_gc", "emoji": "📈", "direction": "buy",
                "label": "MACDが上抜け（買いシグナル）",
                "desc": "MACDがシグナル線を上抜けた。",
                "meaning": "下落の勢いが弱まり、上昇に転じやすいタイミング。",
                "tip": "短期の買いシグナル。トレンドの向きと合っていれば信頼度が上がる。",
                "priority": 4}
    if prev >= 0 > now:
        return {"type": "macd_dc", "emoji": "📉", "direction": "sell",
                "label": "MACDが下抜け（売りシグナル）",
                "desc": "MACDがシグナル線を下抜けた。",
                "meaning": "上昇の勢いが弱まり、下落に転じやすいタイミング。",
                "tip": "短期の売りシグナル。持ち高の見直しを検討する場面。",
                "priority": 4}
    return None


def _sig_bollinger(c: pd.Series) -> dict | None:
    """ボリンジャーバンド ±2σ の突破（過熱・加速）"""
    if len(c) < 25:
        return None
    mid = c.rolling(20).mean()
    sd  = c.rolling(20).std()
    up, lo = mid + 2 * sd, mid - 2 * sd
    if pd.isna(up.iloc[-2]) or pd.isna(lo.iloc[-2]):
        return None
    if c.iloc[-2] <= up.iloc[-2] and c.iloc[-1] > up.iloc[-1]:
        return {"type": "bb_upper", "emoji": "🔥", "direction": "caution",
                "label": "ボリンジャーバンド +2σ を突破",
                "desc": f"終値 {c.iloc[-1]:,.2f} が +2σ（{up.iloc[-1]:,.2f}）を上抜け。",
                "meaning": "通常より強い上昇。過熱と加速の両面がある。",
                "tip": "勢いは強いが高値づかみに注意。飛びつきは避けたい。",
                "priority": 5}
    if c.iloc[-2] >= lo.iloc[-2] and c.iloc[-1] < lo.iloc[-1]:
        return {"type": "bb_lower", "emoji": "🧊", "direction": "caution",
                "label": "ボリンジャーバンド -2σ を突破",
                "desc": f"終値 {c.iloc[-1]:,.2f} が -2σ（{lo.iloc[-1]:,.2f}）を下抜け。",
                "meaning": "通常より強い下落。売られすぎと下落加速の両面がある。",
                "tip": "急いで拾わず、下げ止まりの確認を待ちたい場面。",
                "priority": 5}
    return None


def _sig_rsi_reversal(c: pd.Series) -> dict | None:
    """RSI 30/70 からの反転（売られすぎ・買われすぎの解消）"""
    r = _rsi(c)
    if len(r) < 3 or pd.isna(r.iloc[-2]):
        return None
    prev, now = r.iloc[-2], r.iloc[-1]
    if prev <= 30 < now:
        return {"type": "rsi_recover", "emoji": "🟢", "direction": "buy",
                "label": "RSIが売られすぎ圏から回復",
                "desc": f"RSIが {prev:.0f} → {now:.0f} と30を上抜け。",
                "meaning": "売られすぎの解消。反発が始まりやすい局面。",
                "tip": "逆張りの反発狙い。戻り切らずに再下落することもある。",
                "priority": 6}
    if prev >= 70 > now:
        return {"type": "rsi_cooldown", "emoji": "🔴", "direction": "sell",
                "label": "RSIが買われすぎ圏から反落",
                "desc": f"RSIが {prev:.0f} → {now:.0f} と70を下抜け。",
                "meaning": "買われすぎの解消。上昇一服・調整が入りやすい局面。",
                "tip": "利益確定を検討する場面。深追いは禁物。",
                "priority": 6}
    return None


_DETECTORS = (
    _sig_ma_cross,
    _sig_ma200,
    _sig_regular_divergence,
    _sig_macd,
    _sig_bollinger,
    _sig_rsi_reversal,
)

# ── 時間軸（長い足ほど重い）────────────────────────────────────
# (yfinance interval, 表示名, 取得期間, 重み)
_TF_SPECS = [
    ("1wk", "週足", "10y", 2.0),   # 長期＝最も重い
    ("1d",  "日足", "2y",  1.0),
]
_TF_HIDDEN_WEIGHT = 0.5            # ヒドゥン（1時間足）は軽め

# シグナル種別ごとの基礎スコア（重要度）
_TYPE_SCORE = {
    "golden_cross": 3.0, "dead_cross": 3.0,
    "ma200_up":     3.0, "ma200_down": 3.0,
    "bullish_divergence": 2.0, "bearish_divergence": 2.0,
    "bullish_hidden":     2.0, "bearish_hidden":     2.0,
    "macd_gc": 1.5, "macd_dc": 1.5,
    "bb_upper": 1.0, "bb_lower": 1.0,
    "rsi_recover": 1.0, "rsi_cooldown": 1.0,
}

# 信頼度のしきい値（合計スコア）
_CONF_HIGH = 6.0
_CONF_MID  = 3.5

# 週足のときにラベルの「日」表記を「週」に直す
_RELABEL = (("25日線", "25週線"), ("75日線", "75週線"),
            ("200日移動平均線", "200週移動平均線"), ("200日線", "200週線"))


def _relabel(text: str, tf_name: str) -> str:
    if tf_name != "週足" or not text:
        return text
    for a, b in _RELABEL:
        text = text.replace(a, b)
    return text


def _confluence(hits: list) -> list:
    """
    銘柄ごとにシグナルを束ね、方向別に信頼度スコアを合計する。
    長い足ほど重く、重要なシグナルほど重く効く。
    返り値: [{symbol,name,ticker,direction,score,stars,signals:[...]}, ...]
    """
    by_sym = {}
    for h in hits:
        g = by_sym.setdefault(h["symbol"], {
            "symbol": h["symbol"], "name": h["name"], "ticker": h["ticker"],
            "buy": 0.0, "sell": 0.0, "signals": [],
        })
        g["signals"].append(h)
        d = h.get("direction")
        if d in ("buy", "sell"):
            base = h.get("base_type") or h.get("type", "")
            g[d] += _TYPE_SCORE.get(base, 1.0) * h.get("tf_weight", 1.0)

    groups = []
    for g in by_sym.values():
        # 買い・売りの強い方を採用（拮抗しているときは差分で評価）
        if g["buy"] >= g["sell"]:
            direction, score, opposite = "buy", g["buy"], g["sell"]
        else:
            direction, score, opposite = "sell", g["sell"], g["buy"]
        net = score - opposite          # 逆方向のシグナルがあるほど信頼度は下がる

        if net >= _CONF_HIGH:   stars, rank = "★★★", "高"
        elif net >= _CONF_MID:  stars, rank = "★★",  "中"
        else:                   stars, rank = "★",   "参考"

        # 長い足のシグナルを先に見せる
        g["signals"].sort(key=lambda x: (-x.get("tf_weight", 1.0),
                                         x.get("priority", 9)))
        groups.append({**g, "direction": direction, "score": score,
                       "net": net, "stars": stars, "rank": rank,
                       "conflict": opposite > 0})
    groups.sort(key=lambda x: -x["net"])
    return groups


# ── 連発防止（1セッション1回） ──────────────────────────────────
def _session_key(now=None) -> str:
    now = now or get_jst_now()
    return (now - timedelta(hours=6)).strftime("%Y-%m-%d")


def _apply_cooldown(hits: list) -> list:
    now, skey = get_jst_now(), _session_key()
    try:
        st = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        st = {}

    kept = []
    for h in hits:
        key = f"{h['symbol']}:{h['type']}"
        rec = st.get(key)
        if isinstance(rec, dict) and rec.get("session") == skey:
            logger.info(f"通知済みのためスキップ: {h['name']} {h['label']}")
            continue
        kept.append(h)

    if kept:
        for h in kept:
            st[f"{h['symbol']}:{h['type']}"] = {"session": skey, "ts": now.isoformat()}
        st = {k: v for k, v in st.items()
              if isinstance(v, dict) and v.get("session") == skey}
        try:
            _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            _STATE_FILE.write_text(json.dumps(st, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
        except Exception:
            logger.debug(traceback.format_exc())
    return kept


# ── 実行 ─────────────────────────────────────────────────────────
def detect() -> list:
    """
    全対象を「週足 → 日足」の順で検査する。
    長い足のシグナルほど重み（tf_weight）が大きい。
    ヒドゥンダイバージェンス（1時間足）は divergence.py から合流。
    """
    hits = []
    for sym, name, unit, ticker in TARGETS:
        for interval, tf_name, period, weight in _TF_SPECS:
            try:
                df = _fetch(sym, period, interval)
                if df is None or len(df) < 30:
                    continue
                c = df["Close"]
                for fn in _DETECTORS:
                    try:
                        r = fn(c)
                    except Exception:
                        logger.debug(traceback.format_exc())
                        continue
                    if not r:
                        continue
                    r["label"] = _relabel(r.get("label", ""), tf_name)
                    r["desc"]  = _relabel(r.get("desc", ""), tf_name)
                    r.update({
                        "symbol": sym, "name": name, "unit": unit, "ticker": ticker,
                        "tf": tf_name, "tf_weight": weight,
                        "base_type": r["type"],          # スコア算出用
                        # 時間軸ごとに別シグナル扱い（週足と日足は別々に通知したい）
                        "type": f"{r['type']}@{interval}",
                    })
                    hits.append(r)
            except Exception:
                logger.debug(traceback.format_exc())

    # ヒドゥンダイバージェンス（1時間足・日足トレンドと一致したものだけ）
    try:
        from src.divergence import detect as detect_hidden
        for h in detect_hidden():
            h["base_type"] = h.get("kind", "hidden")
            h["type"] = f"{h['base_type']}@1h"
            h.setdefault("emoji", "🟢" if h.get("direction") == "buy" else "🔴")
            h.setdefault("priority", 3)
            h["label"] = h["label"].replace("🟢 ", "").replace("🔴 ", "")
            h["tf"] = "1時間足"
            h["tf_weight"] = _TF_HIDDEN_WEIGHT
            hits.append(h)
    except Exception:
        logger.debug(traceback.format_exc())

    # 長い足・重要なものを先頭へ
    hits.sort(key=lambda x: (-x.get("tf_weight", 1.0), x.get("priority", 9)))
    return hits


_DIR_JA = {"buy": "買い", "sell": "売り"}


def build_message(hits: list) -> str:
    """
    通知メッセージ。Telegramの通知バーには1行目しか出ないため、
    銘柄名・ティッカー・信頼度を必ず1行目に入れる。
    シグナルは銘柄ごとにまとめ、重なった数と信頼度★で示す。
    """
    groups = _confluence(hits)

    # ── タイトル行（＝スマホの通知バーに出る文言）──
    top = groups[0]
    n_top = len([s for s in top["signals"] if s.get("direction") == top["direction"]])
    if len(groups) == 1:
        if n_top >= 2:
            title = (f"🔥 *{top['name']}（{top['ticker']}）* "
                     f"{_DIR_JA[top['direction']]}シグナル{n_top}つ重複"
                     f"【信頼度{top['stars']}】")
        else:
            s0 = top["signals"][0]
            title = (f"{s0['emoji']} *{top['name']}（{top['ticker']}）* "
                     f"【{s0.get('tf','')}】{s0['label']}【{top['stars']}】")
    else:
        names = "・".join(f"{g['name']}({g['ticker']})" for g in groups)
        title = (f"📊 *{names}* テクニカルシグナル"
                 f"（最高信頼度 {top['stars']}）")

    lines = [title, "━━━━━━━━━━━━━━"]

    for g in groups:
        same = [s for s in g["signals"] if s.get("direction") == g["direction"]]
        head = (f"{'🔥' if len(same) >= 2 else same[0]['emoji'] if same else '📊'} "
                f"*{g['name']}（{g['ticker']}）*　"
                f"{_DIR_JA[g['direction']]}方向 {g['stars']}"
                f"（信頼度{g['rank']}・スコア {g['net']:.1f}）")
        lines += ["", head]

        for s in g["signals"]:
            mark = "・" if s.get("direction") == g["direction"] else "※逆"
            lines.append(f"{mark}【{s.get('tf','')}】{s['emoji']} {s['label']}")

        # 重なりの意味づけ
        if len(same) >= 2:
            tfs = list(dict.fromkeys(s.get("tf", "") for s in same))
            if len(tfs) >= 2:
                lines.append(f"→ {'・'.join(tfs)}の複数の時間軸で"
                             f"{_DIR_JA[g['direction']]}サインが重なっている。信頼度の高い場面。")
            else:
                lines.append(f"→ {tfs[0]}で{_DIR_JA[g['direction']]}サインが"
                             f"{len(same)}つ重なっている。")
        if g["conflict"]:
            lines.append("⚠️ 逆方向のシグナルも出ているため、勢いはやや不透明。")

        # 代表シグナル（最も重い1つ）の詳細だけ載せる
        lead = g["signals"][0]
        if lead.get("desc"):
            lines.append(lead["desc"])
        if lead.get("tip"):
            lines.append(f"💡 {lead['tip']}")

    lines.append("\n★★★=長い足を含む複数一致 ／ ★=単発。"
                 "教科書的なシグナルの発生を機械判定したものです。")
    text = "\n".join(l for l in lines if l)
    return text[:4000]


def run_tech_alert() -> bool:
    """
    monitor_run.py から呼ぶ。検出したシグナルを「1通にまとめて」送る。
    返り値: 送信したか
    """
    try:
        hits = detect()
        if not hits:
            logger.info("テクニカルシグナル: 検出なし")
            return False

        hits = _apply_cooldown(hits)
        if not hits:
            return False

        from src.notify_telegram import send_message
        ok = send_message(build_message(hits))
        if ok:
            names = " / ".join(f"{h['name']}{h['label']}" for h in hits)
            logger.info(f"✅ テクニカルシグナル通知（{len(hits)}件）: {names}")
        return bool(ok)
    except Exception:
        logger.error("テクニカルシグナル検出エラー")
        logger.debug(traceback.format_exc())
        return False
