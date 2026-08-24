"""
src/usdjpy_alert.py — ドル円 専用 緊急シグナルアラート

ドル円に限り、複数の時間軸で信頼度の高いシグナルが重なった瞬間に
「緊急アラート」を必ず送る。

【なぜドル円だけ専用にするか】
tech_signals は複数銘柄をまとめて1通にするため、ドル円の重要シグナルが
他の銘柄に埋もれる。また日足確定を待つ時間ガードがかかっており、
24時間動くドル円には遅すぎる。そこでドル円だけ独立して監視する。

【時間軸と重み】長い足ほど重い
    週足   ×2.0   … 大局。ここが効くと数週間〜数ヶ月の流れ
    日足   ×1.5   … 中期
    4時間足 ×1.0   … 短期の節目（1時間足から合成）
    1時間足 ×0.5   … 目先

【緊急と判定する条件】
  同じ方向のシグナルが 2つ以上 重なり、かつ
    net スコア（逆方向を差し引いた値）が
      6.0以上 → 🚨 最重要（★★★）
      4.0以上 → ⚠️ 重要（★★）
  ※単発シグナルでは鳴らさない（＝「重なった時」だけ）

【連発防止】
  同じ方向のアラートは4時間クールダウン。
  ただしスコアが 2.0 以上悪化（強化）した場合は再通知する（エスカレーション）。
  方向が反転した場合は即座に通知する。
"""

import json
import traceback
from datetime import timedelta

import pandas as pd

from src.utils import setup_logger, get_jst_now, BASE_DIR
from src.tech_signals import (
    _sig_ma_cross, _sig_ma200, _sig_regular_divergence,
    _sig_macd, _sig_bollinger, _sig_rsi_reversal,
    _TYPE_SCORE, _relabel,
)

logger = setup_logger("usdjpy_alert")

SYMBOL = "USDJPY=X"
NAME   = "ドル円"
TICKER = "USD/JPY"

_STATE_FILE = BASE_DIR / "data" / "usdjpy_alert_state.json"

# (yfinance interval, 表示名, 取得期間, 重み)
_TF_SPECS = [
    ("1wk", "週足",    "10y", 2.0),
    ("1d",  "日足",    "2y",  1.5),
    ("4h",  "4時間足", "60d", 1.0),   # 1時間足から合成
    ("1h",  "1時間足", "60d", 0.5),
]

_EMERGENCY_HIGH = 6.0    # 🚨 最重要
_EMERGENCY_MID  = 4.0    # ⚠️ 重要
_MIN_SIGNALS    = 2      # 「重なった時」＝2つ以上

_COOLDOWN_HOURS = 4
_ESCALATE_DIFF  = 2.0    # これ以上スコアが伸びたら再通知

_DETECTORS = (_sig_ma_cross, _sig_ma200, _sig_regular_divergence,
              _sig_macd, _sig_bollinger, _sig_rsi_reversal)

_DIR_JA = {"buy": "円安（ドル高）", "sell": "円高（ドル安）"}


def _fetch(interval: str, period: str) -> pd.DataFrame | None:
    """ドル円の足を取得。4時間足は1時間足から合成する。"""
    try:
        import yfinance as yf
        if interval == "4h":
            df = yf.Ticker(SYMBOL).history(period=period, interval="1h",
                                           auto_adjust=True)
            if df is None or df.empty:
                return None
            df = df.resample("4h").agg({
                "Open": "first", "High": "max",
                "Low": "min", "Close": "last",
            }).dropna()
            return df
        df = yf.Ticker(SYMBOL).history(period=period, interval=interval,
                                       auto_adjust=True)
        if df is None or df.empty or "Close" not in df.columns:
            return None
        return df.dropna(subset=["Close"])
    except Exception:
        logger.debug(traceback.format_exc())
        return None


def detect() -> list:
    """全時間軸でシグナルを検出する"""
    hits = []
    for interval, tf_name, period, weight in _TF_SPECS:
        df = _fetch(interval, period)
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
            r.update({"tf": tf_name, "tf_weight": weight,
                      "base_type": r["type"],
                      "type": f"{r['type']}@{interval}"})
            hits.append(r)

    # ヒドゥンダイバージェンス（日足トレンド × 1時間足）も加える
    try:
        from src.divergence import _daily_trend, _check, _fetch as _dfetch
        trend = _daily_trend(SYMBOL)
        if trend in ("up", "down"):
            d1h = _dfetch(SYMBOL, "60d", "1h")
            if d1h is not None:
                r = _check(d1h, trend)
                if r:
                    r["base_type"] = r.get("kind", "hidden")
                    r["type"] = f"{r['base_type']}@1h"
                    r["emoji"] = "🟢" if r.get("direction") == "buy" else "🔴"
                    r["label"] = r["label"].replace("🟢 ", "").replace("🔴 ", "")
                    r["tf"] = "1時間足"
                    r["tf_weight"] = 0.5
                    r.setdefault("priority", 3)
                    hits.append(r)
    except Exception:
        logger.debug(traceback.format_exc())

    hits.sort(key=lambda x: (-x.get("tf_weight", 1.0), x.get("priority", 9)))
    return hits


def score(hits: list) -> dict:
    """方向別にスコアを集計し、緊急に該当するか判定する"""
    buy = sell = 0.0
    for h in hits:
        d = h.get("direction")
        if d not in ("buy", "sell"):
            continue
        s = _TYPE_SCORE.get(h.get("base_type"), 1.0) * h.get("tf_weight", 1.0)
        if d == "buy":
            buy += s
        else:
            sell += s

    direction = "buy" if buy >= sell else "sell"
    gross     = max(buy, sell)
    net       = gross - min(buy, sell)
    same      = [h for h in hits if h.get("direction") == direction]

    if net >= _EMERGENCY_HIGH and len(same) >= _MIN_SIGNALS:
        rank, stars, mark = "最重要", "★★★", "🚨"
    elif net >= _EMERGENCY_MID and len(same) >= _MIN_SIGNALS:
        rank, stars, mark = "重要", "★★", "⚠️"
    else:
        rank, stars, mark = None, "★", ""

    return {"direction": direction, "buy": buy, "sell": sell,
            "net": net, "same": same, "rank": rank, "stars": stars,
            "mark": mark, "conflict": min(buy, sell) > 0,
            "is_emergency": rank is not None}


def _load_state() -> dict:
    try:
        return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _should_send(sc: dict) -> bool:
    """クールダウン判定。方向反転・スコア急伸は即通知する。"""
    st  = _load_state()
    now = get_jst_now()
    prev_dir  = st.get("direction")
    prev_net  = float(st.get("net", 0) or 0)
    prev_ts   = st.get("ts")

    if prev_dir != sc["direction"]:
        return True                       # 方向が変わった＝必ず通知
    if sc["net"] >= prev_net + _ESCALATE_DIFF:
        return True                       # さらに強まった＝再通知
    if not prev_ts:
        return True
    try:
        elapsed = (now - pd.Timestamp(prev_ts).to_pydatetime()).total_seconds() / 3600
    except Exception:
        return True
    return elapsed >= _COOLDOWN_HOURS


def _save_state(sc: dict) -> None:
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(json.dumps({
            "direction": sc["direction"], "net": sc["net"],
            "ts": get_jst_now().isoformat(),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        logger.debug(traceback.format_exc())


def _context() -> list:
    """介入警戒度・投機筋など、判断に効く周辺情報を1〜2行で添える"""
    out = []
    try:
        from src.intervention_stats import analyze
        iv = analyze()
        if iv.get("available") and iv.get("score", 0) >= 30:
            c = iv["current"]
            out.append(f"🚨 介入警戒度 {iv['score']}/100（{iv['level_label']}）"
                       f"・前回介入から{c['days_since']}日")
    except Exception:
        logger.debug(traceback.format_exc())
    try:
        from src.cot_weekly import run as cot
        r = cot()
        if r.get("available"):
            yen = next((i for i in r["items"] if i["name"] == "円"), None)
            if yen:
                side = "買い越し" if yen["net_k"] >= 0 else "売り越し"
                out.append(f"📡 投機筋の円: ネット{side} {abs(yen['net_k']):,.1f}千枚"
                           f"（傾き{yen['pct']:.0f}%）")
    except Exception:
        logger.debug(traceback.format_exc())
    return out


def build_message(hits: list, sc: dict, price: float | None) -> str:
    """1行目＝スマホの通知バー。銘柄・方向・信頼度を必ず入れる。"""
    n = len(sc["same"])
    px = f"{price:,.2f}円" if price is not None else ""
    title = (f"{sc['mark']} *【緊急】{NAME}（{TICKER}）* "
             f"{_DIR_JA[sc['direction']]}シグナル{n}つ重複【{sc['stars']}】")

    lines = [title, f"現在値 `{px}` ／ 信頼度 {sc['rank']}（スコア {sc['net']:.1f}）",
             "━━━━━━━━━━━━━━", ""]

    for h in hits:
        mark = "・" if h.get("direction") == sc["direction"] else "※逆"
        lines.append(f"{mark}【{h.get('tf','')}】{h.get('emoji','')} {h['label']}")

    tfs = list(dict.fromkeys(h.get("tf", "") for h in sc["same"]))
    lines.append("")
    if len(tfs) >= 2:
        lines.append(f"→ *{'・'.join(tfs)}* の複数の時間軸で"
                     f"{_DIR_JA[sc['direction']]}方向が一致。信頼度の高い場面。")
    else:
        lines.append(f"→ {tfs[0]}で{_DIR_JA[sc['direction']]}方向のサインが{n}つ重なっている。")

    if sc["conflict"]:
        lines.append("⚠️ 逆方向のシグナルも出ており、勢いはやや不透明。")

    ctx = _context()
    if ctx:
        lines += [""] + ctx

    lead = sc["same"][0] if sc["same"] else (hits[0] if hits else None)
    if lead:
        if lead.get("desc"):
            lines += ["", lead["desc"]]
        if lead.get("tip"):
            lines.append(f"💡 {lead['tip']}")

    lines.append("\n※教科書的なシグナルの重なりを機械判定したものです。"
                 "売買の指示ではありません。")
    return "\n".join(l for l in lines if l is not None)[:4000]


def run_usdjpy_emergency() -> bool:
    """
    monitor_run.py から毎回呼ぶ。
    ドル円で信頼度の高いシグナルが複数重なったら緊急通知を送る。
    """
    try:
        hits = detect()
        if not hits:
            logger.info("ドル円: シグナルなし")
            return False

        sc = score(hits)
        if not sc["is_emergency"]:
            logger.info(f"ドル円: 緊急水準に未達（{sc['direction']} net={sc['net']:.1f} "
                        f"重なり{len(sc['same'])}件）")
            return False

        if not _should_send(sc):
            logger.info(f"ドル円: クールダウン中のためスキップ（net={sc['net']:.1f}）")
            return False

        price = None
        try:
            df = _fetch("1h", "5d")
            if df is not None and len(df):
                price = float(df["Close"].iloc[-1])
        except Exception:
            pass

        from src.notify_telegram import send_message
        ok = send_message(build_message(hits, sc, price))
        if ok:
            _save_state(sc)
            logger.info(f"🚨 ドル円 緊急アラート送信: {sc['rank']} "
                        f"{sc['direction']} net={sc['net']:.1f} "
                        f"重なり{len(sc['same'])}件")
        else:
            logger.error("❌ ドル円 緊急アラートの送信に失敗")
        return bool(ok)
    except Exception:
        logger.error("ドル円 緊急アラートエラー")
        logger.debug(traceback.format_exc())
        return False


if __name__ == "__main__":
    run_usdjpy_emergency()
