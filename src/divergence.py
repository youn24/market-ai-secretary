"""
src/divergence.py — ヒドゥンダイバージェンス検出（マルチタイムフレーム確認つき）

ヒドゥンダイバージェンス = 「トレンド継続」のサイン
  🟢 強気ヒドゥン: 価格は安値を切り上げ / RSIは安値を切り下げ
                   → 上昇トレンド中の押し目（買い場）
  🔴 弱気ヒドゥン: 価格は高値を切り下げ / RSIは高値を切り上げ
                   → 下降トレンド中の戻り（売り場）

※通常のダイバージェンス（トレンド転換）とは逆の意味を持つ。

マルチタイムフレーム確認:
  ヒドゥンダイバージェンスは「トレンドが続く」サインなので、
  そもそもトレンドが出ていないと意味がない。そこで
    日足でトレンドを確認 → 1時間足でダイバージェンスを探す
  とし、向きが一致したときだけシグナルとして採用する。
  （上昇トレンド中の強気ヒドゥン／下降トレンド中の弱気ヒドゥンのみ）

検出時は monitor_run.py（15分ごと）から即アラートを送る。
連発防止のため、同一銘柄＋同一種別は1セッション（JST6時始まり）に1回だけ。
"""

import json
import traceback
from datetime import timedelta

import pandas as pd

from src.utils import setup_logger, get_jst_now, BASE_DIR

logger = setup_logger("divergence")

# 監視対象（シンボル, 表示名, 単位）
TARGETS = [
    ("USDJPY=X", "ドル円",     "円"),
    ("^N225",    "日経225",    "円"),
    ("NIY=F",    "日経先物",   "円"),
    ("^GSPC",    "S&P500",     ""),
]

# ── 検出パラメータ ──
_PIVOT_LR      = 3      # 前後3本より高い/安い点をスイングとみなす
_MIN_BAR_GAP   = 5      # 2つのスイングは最低5本離れていること
_MAX_BAR_GAP   = 80     # 離れすぎ（80本超）は無関係とみなす
_MAX_AGE       = 12     # 直近スイングが12本以内＝出来たてのシグナルのみ
_MIN_RSI_DIFF  = 2.0    # RSIの差がこれ未満はノイズ
_MIN_PX_DIFF   = 0.05   # 価格差(%)がこれ未満はノイズ

_STATE_FILE = BASE_DIR / "data" / "divergence_state.json"


# ── テクニカル ───────────────────────────────────────────────────
def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain  = delta.clip(lower=0).ewm(com=n - 1, min_periods=n).mean()
    loss  = (-delta.clip(upper=0)).ewm(com=n - 1, min_periods=n).mean()
    rs    = gain / loss.replace(0, 1e-10)
    return 100 - 100 / (1 + rs)


def _fetch(sym: str, period: str, interval: str) -> pd.DataFrame | None:
    try:
        import yfinance as yf
        df = yf.Ticker(sym).history(period=period, interval=interval, auto_adjust=True)
        if df is None or df.empty or "Close" not in df.columns:
            return None
        return df.dropna(subset=["Close"])
    except Exception:
        logger.debug(traceback.format_exc())
        return None


def _daily_trend(sym: str) -> str:
    """日足のトレンド（大きな流れ）: up / down / range / unknown"""
    df = _fetch(sym, "6mo", "1d")
    if df is None or len(df) < 80:
        return "unknown"
    c = df["Close"]
    ma25 = c.rolling(25).mean().iloc[-1]
    ma75 = c.rolling(75).mean().iloc[-1]
    last = float(c.iloc[-1])
    if pd.isna(ma25) or pd.isna(ma75):
        return "unknown"
    if last > ma25 > ma75:
        return "up"
    if last < ma25 < ma75:
        return "down"
    return "range"


# ── スイング（山・谷）検出 ──────────────────────────────────────
def _pivots(vals: list, kind: str, lr: int = _PIVOT_LR) -> list:
    """
    前後 lr 本と比べて極値になっている位置を返す。
    確定させるため、右側に lr 本そろっている点のみ対象。
    """
    out = []
    for i in range(lr, len(vals) - lr):
        window = vals[i - lr: i + lr + 1]
        v = vals[i]
        if kind == "low" and v == min(window):
            out.append(i)
        elif kind == "high" and v == max(window):
            out.append(i)
    return out


def _check(df: pd.DataFrame, trend: str) -> dict | None:
    """1時間足でヒドゥンダイバージェンスを判定（トレンドと一致する側のみ）"""
    close = df["Close"]
    if len(close) < 60:
        return None
    rsi = _rsi(close)
    if rsi.isna().all():
        return None

    px  = close.tolist()
    rs  = rsi.tolist()
    n   = len(px)

    def _valid(i, j):
        """2つのスイングが有効な間隔か（j が直近側）"""
        gap = j - i
        return _MIN_BAR_GAP <= gap <= _MAX_BAR_GAP and (n - 1 - j) <= _MAX_AGE

    # 🟢 強気ヒドゥン（上昇トレンド中の押し目）
    if trend == "up":
        lows = [i for i in _pivots(px, "low") if not pd.isna(rs[i])]
        if len(lows) >= 2:
            i, j = lows[-2], lows[-1]
            px_up  = (px[j] - px[i]) / abs(px[i]) * 100 if px[i] else 0
            rsi_dn = rs[i] - rs[j]
            if (_valid(i, j) and px_up >= _MIN_PX_DIFF and rsi_dn >= _MIN_RSI_DIFF):
                return {
                    "kind": "bullish_hidden",
                    "label": "🟢 強気ヒドゥンダイバージェンス",
                    "direction": "buy",
                    "desc": (f"安値を {px[i]:,.2f} → {px[j]:,.2f} と切り上げる一方、"
                             f"RSIは {rs[i]:.0f} → {rs[j]:.0f} と切り下げ。"),
                    "meaning": "上昇トレンド中の押し目。トレンド継続の可能性。",
                    "tip": "順張りの買い場になりやすい場面。直近安値の下抜けは想定と逆。",
                    "price": px[j], "rsi": rs[j],
                }

    # 🔴 弱気ヒドゥン（下降トレンド中の戻り）
    if trend == "down":
        highs = [i for i in _pivots(px, "high") if not pd.isna(rs[i])]
        if len(highs) >= 2:
            i, j = highs[-2], highs[-1]
            px_dn  = (px[i] - px[j]) / abs(px[i]) * 100 if px[i] else 0
            rsi_up = rs[j] - rs[i]
            if (_valid(i, j) and px_dn >= _MIN_PX_DIFF and rsi_up >= _MIN_RSI_DIFF):
                return {
                    "kind": "bearish_hidden",
                    "label": "🔴 弱気ヒドゥンダイバージェンス",
                    "direction": "sell",
                    "desc": (f"高値を {px[i]:,.2f} → {px[j]:,.2f} と切り下げる一方、"
                             f"RSIは {rs[i]:.0f} → {rs[j]:.0f} と切り上げ。"),
                    "meaning": "下降トレンド中の戻り。下落継続の可能性。",
                    "tip": "順張りの売り場になりやすい場面。安易な逆張り買いは禁物。",
                    "price": px[j], "rsi": rs[j],
                }

    return None


# ── 連発防止（1セッション1回） ──────────────────────────────────
def _session_key(now=None) -> str:
    now = now or get_jst_now()
    return (now - timedelta(hours=6)).strftime("%Y-%m-%d")


def _apply_cooldown(hits: list) -> list:
    now  = get_jst_now()
    skey = _session_key(now)
    try:
        st = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        st = {}

    kept = []
    for h in hits:
        key = f"{h['symbol']}:{h['kind']}"
        rec = st.get(key)
        if isinstance(rec, dict) and rec.get("session") == skey:
            logger.info(f"通知済みのためスキップ: {h['name']} {h['label']}")
            continue
        kept.append(h)

    if kept:
        for h in kept:
            st[f"{h['symbol']}:{h['kind']}"] = {
                "session": skey, "ts": now.isoformat(), "price": h.get("price"),
            }
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
    """全対象を検査し、トレンドと一致したヒドゥンダイバージェンスを返す"""
    hits = []
    for sym, name, unit in TARGETS:
        try:
            trend = _daily_trend(sym)
            if trend not in ("up", "down"):
                continue    # トレンドが無いならヒドゥンは意味を持たない
            df = _fetch(sym, "60d", "1h")
            if df is None:
                continue
            r = _check(df, trend)
            if r:
                r.update({"symbol": sym, "name": name, "unit": unit,
                          "daily_trend": trend})
                hits.append(r)
        except Exception:
            logger.debug(traceback.format_exc())
    return hits


def build_message(hits: list) -> str:
    trend_ja = {"up": "📈 日足は上昇トレンド", "down": "📉 日足は下降トレンド"}
    lines = ["📐 *ヒドゥンダイバージェンス検出*",
             "（日足トレンド × 1時間足のRSI）",
             "━━━━━━━━━━━━━━"]
    for h in hits:
        lines += [
            "",
            f"*{h['name']}*　{h['label']}",
            f"　{trend_ja.get(h['daily_trend'], '')}",
            h["desc"],
            f"→ {h['meaning']}",
            f"💡 {h['tip']}",
        ]
    lines.append("\n※トレンド継続を示す教科書的なシグナルを機械判定したものです。")
    return "\n".join(lines)


def run_divergence_alert() -> bool:
    """
    monitor_run.py から呼ぶ。検出したら即Telegramへ送る。
    返り値: 送信したか
    """
    try:
        hits = detect()
        if not hits:
            logger.info("ヒドゥンダイバージェンス: 検出なし")
            return False

        hits = _apply_cooldown(hits)
        if not hits:
            return False

        from src.notify_telegram import send_message
        ok = send_message(build_message(hits))
        if ok:
            names = " / ".join(f"{h['name']}{h['label']}" for h in hits)
            logger.info(f"✅ ヒドゥンダイバージェンス通知: {names}")
        return bool(ok)
    except Exception:
        logger.error("ヒドゥンダイバージェンス検出エラー")
        logger.debug(traceback.format_exc())
        return False
