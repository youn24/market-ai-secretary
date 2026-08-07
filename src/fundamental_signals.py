"""
src/fundamental_signals.py — ファンダメンタル（マクロ）レジーム・シグナル

「歴史的に実績のある」マクロ指標だけを厳選し、状態が変わった瞬間を捉える。
テクニカルと違い月次・週次データなので、1日1回だけ判定する。

判定するシグナル:
  1. 逆イールド（米10年-2年）      … 景気後退の代表的な先行指標
     ・逆転入り  … 警戒の始まり
     ・逆転解消  … 歴史的には「景気後退の直前」に起きることが多い（重要）
  2. サームルール（米失業率）       … 景気後退のリアルタイム判定
     失業率の3ヶ月平均が、直近12ヶ月の最低値から +0.50pt 以上上昇したら発動
  3. HY社債スプレッド              … 株より先に動くリスクオフの先行指標
  4. 米実質金利（TIPS 10年）        … 金・グロース株の最重要ドライバー

⚠️ 正直な注記:
  これらは「よく当たってきた」指標であって、絶対ではない。
  逆イールドは2022〜24年の逆転で景気後退が来ず、サームルールも2024年に
  発動したが景気後退にならなかった。過信せず「警戒度を上げる材料」として扱う。
"""

import io
import json
import traceback
from datetime import timedelta

import pandas as pd
import requests

from src.utils import setup_logger, get_jst_now, BASE_DIR

logger = setup_logger("fundamental_signals")

_HEADERS    = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
_STATE_FILE = BASE_DIR / "data" / "fundamental_state.json"

# FRED系列（履歴が必要なのでCSVを直接読む）
_SERIES = {
    "T10Y2Y":       "米10年-2年スプレッド",
    "UNRATE":       "米失業率",
    "BAMLH0A0HYM2": "HY社債スプレッド",
    "DFII10":       "米実質10年金利",
}


def _fetch_series(sid: str) -> pd.Series | None:
    """FREDのCSVを取得して日付インデックスのSeriesで返す"""
    try:
        r = requests.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}",
                         timeout=20, headers=_HEADERS)
        if r.status_code != 200:
            return None
        df = pd.read_csv(io.StringIO(r.text), na_values=".")
        df.columns = ["date", "value"]
        df = df.dropna()
        if df.empty:
            return None
        s = pd.Series(df["value"].astype(float).values,
                      index=pd.to_datetime(df["date"]))
        return s
    except Exception:
        logger.debug(traceback.format_exc())
        return None


# ── ① 逆イールド ────────────────────────────────────────────────
def _sig_yield_curve(s: pd.Series) -> dict | None:
    if s is None or len(s) < 40:
        return None
    now = float(s.iloc[-1])
    # 直近20営業日の平均で「均された」状態を見る（1日だけの上下でブレないように）
    recent = float(s.iloc[-20:].mean())
    prev   = float(s.iloc[-60:-20].mean()) if len(s) >= 60 else recent

    if now < 0:
        return {"key": "yield_curve_inverted", "emoji": "⚠️", "level": "警戒",
                "title": "逆イールド発生中（米10年 < 米2年）",
                "value": f"{now:+.2f}%",
                "meaning": "長期金利が短期金利を下回る異常な状態。"
                           "過去の景気後退の多くに先行して現れてきた。",
                "note": "ただし逆転してから景気後退まで1〜2年かかることが多く、"
                        "すぐ株が下がるわけではない。",
                "weight": 3}
    if prev < 0 <= recent:
        return {"key": "yield_curve_normalized", "emoji": "🚨", "level": "重要",
                "title": "逆イールドが解消（順イールドに復帰）",
                "value": f"{now:+.2f}%",
                "meaning": "歴史的には、逆転そのものより"
                           "「解消した直後」に景気後退入りした例が多い重要な転換点。",
                "note": "リスク資産の持ち高を点検したい局面。ただし例外もある。",
                "weight": 4}
    return None


# ── ② サームルール ──────────────────────────────────────────────
def _sig_sahm(s: pd.Series) -> dict | None:
    """失業率3ヶ月平均が直近12ヶ月の最低値から+0.50pt以上 → 景気後退シグナル"""
    if s is None or len(s) < 15:
        return None
    ma3 = s.rolling(3).mean().dropna()
    if len(ma3) < 13:
        return None
    now = float(ma3.iloc[-1])
    low = float(ma3.iloc[-13:].min())      # 直近12ヶ月＋当月の最低値
    gap = now - low
    if gap >= 0.50:
        return {"key": "sahm_triggered", "emoji": "🚨", "level": "重要",
                "title": "サームルール発動（米雇用の悪化）",
                "value": f"失業率3ヶ月平均 {now:.2f}%（直近安値 {low:.2f}% から +{gap:.2f}pt）",
                "meaning": "1970年以降のすべての景気後退を捉えてきたリアルタイム指標。"
                           "雇用の悪化が本格化しているサイン。",
                "note": "2024年の発動時は景気後退に至らなかった例もあり、過信は禁物。",
                "weight": 4}
    if gap >= 0.35:
        return {"key": "sahm_warning", "emoji": "⚠️", "level": "注意",
                "title": "サームルールが発動水準に接近",
                "value": f"+{gap:.2f}pt（発動は +0.50pt）",
                "meaning": "雇用の悪化が進みつつある。景気減速に注意したい段階。",
                "note": "まだ発動前。今後の失業率の発表に注目。",
                "weight": 2}
    return None


# ── ③ HY社債スプレッド ──────────────────────────────────────────
def _sig_credit(s: pd.Series) -> dict | None:
    if s is None or len(s) < 30:
        return None
    now  = float(s.iloc[-1])
    ago  = float(s.iloc[-21])              # 約1ヶ月前
    diff = now - ago
    if now >= 5.0 or diff >= 0.80:
        return {"key": "credit_stress", "emoji": "🔴", "level": "警戒",
                "title": "信用スプレッドが急拡大（リスクオフ）",
                "value": f"{now:.2f}%（1ヶ月で {diff:+.2f}pt）",
                "meaning": "低格付け企業の資金調達が厳しくなっているサイン。"
                           "株式より先に動くことが多い先行指標。",
                "note": "3.5%未満＝平穏 / 5%超＝ストレス、が目安。",
                "weight": 3}
    if now < 3.0:
        return {"key": "credit_calm", "emoji": "🟢", "level": "良好",
                "title": "信用スプレッドは低位（リスクオン環境）",
                "value": f"{now:.2f}%",
                "meaning": "企業の資金調達環境は良好。株式に追い風の地合い。",
                "note": "低すぎる状態が続くと、逆に楽観の行き過ぎとも読める。",
                "weight": 1}
    return None


# ── ④ 実質金利 ──────────────────────────────────────────────────
def _sig_real_rate(s: pd.Series) -> dict | None:
    if s is None or len(s) < 30:
        return None
    now  = float(s.iloc[-1])
    ago  = float(s.iloc[-21])
    diff = now - ago
    if now >= 2.0:
        return {"key": "real_rate_high", "emoji": "🟠", "level": "注意",
                "title": "米実質金利が高水準",
                "value": f"{now:.2f}%（1ヶ月 {diff:+.2f}pt）",
                "meaning": "現金・債券の魅力が増す水準。金やグロース株には逆風。",
                "note": "1%未満＝緩和的 / 2%超＝引き締め的、が目安。",
                "weight": 2}
    if now < 0.5:
        return {"key": "real_rate_low", "emoji": "🟢", "level": "良好",
                "title": "米実質金利が低水準",
                "value": f"{now:.2f}%（1ヶ月 {diff:+.2f}pt）",
                "meaning": "金・グロース株に追い風の金融環境。",
                "note": "実質金利＝名目金利－期待インフレ率。",
                "weight": 2}
    return None


# ── 1日1回だけ判定するためのガード ──────────────────────────────
def _session_key(now=None) -> str:
    now = now or get_jst_now()
    return (now - timedelta(hours=6)).strftime("%Y-%m-%d")


def _load_state() -> dict:
    try:
        return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(st: dict) -> None:
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(json.dumps(st, ensure_ascii=False, indent=2),
                               encoding="utf-8")
    except Exception:
        logger.debug(traceback.format_exc())


# ── 実行 ─────────────────────────────────────────────────────────
def run(*_args, **_kwargs) -> dict:
    """
    マクロレジームを判定する。
    返り値: {available, signals: [...], changed: [...], telegram_block}
      changed = 前回判定から状態が変わったシグナル（＝アラート対象）
    """
    result = {"available": False, "signals": [], "changed": []}
    try:
        data = {sid: _fetch_series(sid) for sid in _SERIES}

        signals = []
        for fn, sid in ((_sig_yield_curve, "T10Y2Y"),
                        (_sig_sahm,        "UNRATE"),
                        (_sig_credit,      "BAMLH0A0HYM2"),
                        (_sig_real_rate,   "DFII10")):
            try:
                r = fn(data.get(sid))
            except Exception:
                logger.debug(traceback.format_exc())
                continue
            if r:
                r["series"] = sid
                signals.append(r)

        if not signals:
            logger.info("マクロシグナル: 該当なし")
            return result

        signals.sort(key=lambda x: -x.get("weight", 0))

        # 前回から状態が変わったものだけを「変化」として拾う
        st   = _load_state()
        prev = set(st.get("keys", []))
        now_keys = [s["key"] for s in signals]
        changed  = [s for s in signals if s["key"] not in prev]

        _save_state({"keys": now_keys, "session": _session_key(),
                     "ts": get_jst_now().isoformat()})

        result["signals"]        = signals
        result["changed"]        = changed
        result["available"]      = True
        result["telegram_block"] = build_block(signals)
        logger.info(f"✅ マクロシグナル {len(signals)}件（うち変化 {len(changed)}件）")
        return result
    except Exception:
        logger.error("マクロシグナル判定エラー")
        logger.debug(traceback.format_exc())
        return result


def build_block(signals: list) -> str:
    """朝レポート用のコンパクトなブロック"""
    if not signals:
        return ""
    lines = ["🌐 *マクロ環境（ファンダメンタル）*"]
    for s in signals[:3]:
        lines.append(f"{s['emoji']} {s['title']}　`{s['value']}`")
    return "\n".join(lines)


def build_alert(changed: list) -> str:
    """状態が変わったときの単独アラート本文"""
    top = changed[0]
    title = f"{top['emoji']} *マクロ警戒: {top['title']}*"
    lines = [title, "━━━━━━━━━━━━━━"]
    for s in changed:
        lines += [
            "",
            f"{s['emoji']} *{s['title']}*（{s['level']}）",
            f"現在値: `{s['value']}`",
            f"→ {s['meaning']}",
            f"💡 {s['note']}",
        ]
    lines.append("\n※歴史的に実績のあるマクロ指標の状態変化を機械判定したものです。"
                 "絶対的な予測ではありません。")
    return "\n".join(lines)


def run_macro_alert() -> bool:
    """
    monitor_run.py から呼ぶ。1日1回だけ判定し、
    レジームが変わったときだけ通知する（月次データなので通常は無風）。
    """
    try:
        st = _load_state()
        if st.get("session") == _session_key():
            return False          # 本日ぶんは判定済み

        res = run()
        changed = res.get("changed", [])
        # 重要度の高い変化（weight>=3）だけ単独アラートにする
        important = [c for c in changed if c.get("weight", 0) >= 3]
        if not important:
            return False

        from src.notify_telegram import send_message
        ok = send_message(build_alert(important))
        if ok:
            logger.info(f"✅ マクロレジーム変化アラート送信（{len(important)}件）")
        return bool(ok)
    except Exception:
        logger.error("マクロアラートエラー")
        logger.debug(traceback.format_exc())
        return False
