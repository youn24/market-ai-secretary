"""
src/setup_scanner.py — 売買手法シグナル・スキャナー（マルチタイムフレーム対応）
熟練トレーダーが使う代表的なセットアップを毎日自動判定する。

判定する手法:
  - 押し目買いゾーン   : 上昇トレンド中の一時的な下げ（順張りの買い場）
  - 戻り売りゾーン     : 下降トレンド中の一時的な上げ（順張りの売り場）
  - 上抜けブレイクアウト: 直近高値を上抜け（勢いに乗る）
  - 下抜けブレイク     : 直近安値を下抜け（下落加速の警戒）
  - 売られすぎ反発期待  : RSIが低すぎる（逆張りの反発狙い）
  - 買われすぎ警戒     : RSIが高すぎる（利益確定・深追い注意）

マルチタイムフレーム分析:
  週足で「そもそも上か下か」の大きな流れを確認し、日足のシグナルが
  その流れに沿っているか（順張り＝信頼度高）を判定して表示する。
  週足と逆行するシグナルは「慎重に」の注記を付ける。

※投資助言ではなく「教科書的なシグナルの有無」を機械的に示すもの。
"""

import traceback
import pandas as pd
import numpy as np

from src.utils import setup_logger

logger = setup_logger("setup_scanner")

# 色（design_ai と合わせる）
GREEN  = "#00ff87"
RED    = "#ff3d5a"
YELLOW = "#ffc837"

# 監視対象（シンボル, 表示名, 単位）
TARGETS = [
    ("USDJPY=X", "ドル円",   "円"),
    ("^N225",    "日経225",  "円"),
    ("^GSPC",    "S&P500",   ""),
]


# ── テクニカル計算（軽量・pandasのみ） ────────────────────────────
def _rsi(close: pd.Series, n: int = 14) -> float | None:
    if len(close) < n + 1:
        return None
    delta = close.diff()
    gain  = delta.clip(lower=0).ewm(com=n - 1, min_periods=n).mean()
    loss  = (-delta.clip(upper=0)).ewm(com=n - 1, min_periods=n).mean()
    rs    = gain / loss.replace(0, 1e-10)
    rsi   = 100 - 100 / (1 + rs)
    v = rsi.iloc[-1]
    return float(v) if pd.notna(v) else None


def _fetch(sym: str, interval: str = "1d", periods: list[str] | None = None) -> pd.DataFrame | None:
    """yfinanceでOHLCVを取得。失敗時None。"""
    periods = periods or (["2y", "5y", "1y"] if interval == "1wk" else ["6mo", "1y", "3mo"])
    min_len = 20 if interval == "1wk" else 30
    try:
        import yfinance as yf
        for p in periods:
            df = yf.Ticker(sym).history(period=p, interval=interval, auto_adjust=True)
            if df is not None and not df.empty and len(df) >= min_len:
                return df
        return None
    except Exception:
        logger.debug(traceback.format_exc())
        return None


# ── 週足：大きな流れ（トレンド）を判定 ────────────────────────────
def _weekly_trend(sym: str) -> dict:
    """
    週足の位置関係から「そもそもの大きな流れ」を判定する。
    - 週足終値 > 週足MA10 > 週足MA40 → 上昇トレンド
    - 週足終値 < 週足MA10 < 週足MA40 → 下降トレンド
    - それ以外 → 方向感なし（レンジ）
    """
    df = _fetch(sym, interval="1wk")
    if df is None or "Close" not in df.columns or len(df) < 15:
        return {"available": False, "trend": "unknown", "label": "週足データ不足"}

    close = df["Close"].dropna()
    ma10  = close.rolling(10).mean()
    ma40  = close.rolling(40).mean() if len(close) >= 40 else None

    last = float(close.iloc[-1])
    m10  = float(ma10.iloc[-1]) if pd.notna(ma10.iloc[-1]) else None
    m40  = float(ma40.iloc[-1]) if (ma40 is not None and pd.notna(ma40.iloc[-1])) else None

    if m10 is None:
        return {"available": False, "trend": "unknown", "label": "週足データ不足"}

    if m40 is not None:
        if last > m10 > m40:
            return {"available": True, "trend": "up", "label": "📈 週足は上昇トレンド"}
        if last < m10 < m40:
            return {"available": True, "trend": "down", "label": "📉 週足は下降トレンド"}
        return {"available": True, "trend": "range", "label": "➡️ 週足は方向感なし（レンジ）"}

    # 40週MAが計算できない（データ不足）場合はMA10のみで簡易判定
    if last > m10:
        return {"available": True, "trend": "up", "label": "📈 週足は上昇基調（簡易判定）"}
    if last < m10:
        return {"available": True, "trend": "down", "label": "📉 週足は下降基調（簡易判定）"}
    return {"available": True, "trend": "range", "label": "➡️ 週足は方向感なし（簡易判定）"}


def _mtf_note(weekly_trend: str, direction: str) -> tuple[str, str]:
    """週足トレンドと日足シグナルの方向を突き合わせ、一致度と注記を返す"""
    if weekly_trend == "unknown" or direction not in ("buy", "sell"):
        return "", ""

    bullish_signal = direction == "buy"
    bearish_signal = direction == "sell"

    if (weekly_trend == "up" and bullish_signal) or (weekly_trend == "down" and bearish_signal):
        return "◎ 週足と一致（信頼度高）", GREEN
    if (weekly_trend == "up" and bearish_signal) or (weekly_trend == "down" and bullish_signal):
        return "△ 週足の流れに逆行（慎重に）", YELLOW
    return "○ 週足はレンジ（参考程度）", YELLOW


def _analyze_symbol(sym: str, name: str, unit: str) -> dict | None:
    df = _fetch(sym, interval="1d")
    if df is None or "Close" not in df.columns:
        return None
    close = df["Close"].dropna()
    high  = df["High"].dropna() if "High" in df.columns else close
    low   = df["Low"].dropna()  if "Low"  in df.columns else close
    if len(close) < 30:
        return None

    last  = float(close.iloc[-1])
    ma25  = float(close.rolling(25).mean().iloc[-1]) if len(close) >= 25 else None
    ma75  = float(close.rolling(75).mean().iloc[-1]) if len(close) >= 75 else None
    rsi   = _rsi(close)

    # 直近20日の高値・安値（当日を除く）
    hi20  = float(high.iloc[-21:-1].max()) if len(high) >= 21 else float(high.max())
    lo20  = float(low.iloc[-21:-1].min())  if len(low)  >= 21 else float(low.min())

    # トレンド判定（日足）
    uptrend   = ma25 is not None and ma75 is not None and last > ma25 > ma75
    downtrend = ma25 is not None and ma75 is not None and last < ma25 < ma75

    # ── シグナル判定（優先度順に1つ） ──
    signal = None
    if last > hi20:
        signal = ("breakout_up", "🚀 上抜けブレイクアウト", "buy", GREEN,
                  f"直近20日の高値 {hi20:,.2f}{unit} を上抜け。上昇の勢いが強い。",
                  "勢いに乗る場面。ただし急騰直後は飛びつかず押し目も待つ。")
    elif last < lo20:
        signal = ("breakout_down", "⚠️ 下抜けブレイク", "sell", RED,
                  f"直近20日の安値 {lo20:,.2f}{unit} を下抜け。下落が加速しやすい。",
                  "下落警戒。安易な逆張りは禁物、まず様子見が安全。")
    elif rsi is not None and rsi <= 30:
        signal = ("oversold", "🟢 売られすぎ反発期待", "buy", GREEN,
                  f"RSI {rsi:.0f} と売られすぎ水準。反発（リバウンド）が出やすい。",
                  "逆張りの反発狙い。下げ止まりを確認してから少しずつ。")
    elif rsi is not None and rsi >= 70:
        signal = ("overbought", "🔴 買われすぎ警戒", "caution", RED,
                  f"RSI {rsi:.0f} と買われすぎ水準。高値づかみ・反落に注意。",
                  "深追い禁物。利益確定や一部利食いも検討する場面。")
    elif uptrend and rsi is not None and 40 <= rsi <= 58:
        signal = ("pullback_buy", "📗 押し目買いゾーン", "buy", GREEN,
                  f"上昇トレンド中（MA25>MA75）でRSI {rsi:.0f} まで一服。押し目の好機。",
                  "トレンドに沿った買い場。MA25付近の反発を確認すると堅い。")
    elif downtrend and rsi is not None and 42 <= rsi <= 60:
        signal = ("rally_sell", "📕 戻り売りゾーン", "sell", RED,
                  f"下降トレンド中（MA25<MA75）でRSI {rsi:.0f} まで戻し。戻り売りの目安。",
                  "トレンドに沿った売り場。戻り高値での失速を確認したい。")
    else:
        trend_txt = "上昇基調" if uptrend else "下降基調" if downtrend else "方向感が乏しい"
        rsi_txt   = f"{rsi:.0f}" if rsi is not None else "—"
        signal = ("neutral", "😐 様子見", "neutral", YELLOW,
                  f"いまは明確なシグナルなし（{trend_txt}・RSI {rsi_txt}）。",
                  "無理に動かず、次の節目（高値・安値）まで待つのが得策。")

    key, label, direction, color, desc, tip = signal

    # ── マルチタイムフレーム：週足の大きな流れを突き合わせる ──
    wk = _weekly_trend(sym)
    mtf_note, mtf_color = _mtf_note(wk.get("trend", "unknown"), direction)

    return {
        "symbol": sym, "name": name, "unit": unit,
        "key": key, "label": label, "direction": direction, "color": color,
        "desc": desc, "tip": tip,
        "last": last, "ma25": ma25, "ma75": ma75, "rsi": rsi,
        "hi20": hi20, "lo20": lo20,
        "weekly_trend": wk.get("trend", "unknown"),
        "weekly_label": wk.get("label", ""),
        "mtf_note": mtf_note, "mtf_color": mtf_color,
    }


def run(prices: dict = None, technical: dict = None, **_kwargs) -> dict:
    """
    手法スキャナーを実行（マルチタイムフレーム＝週足×日足）。
    返り値: {available, setups: [...], telegram_message, generated}
    """
    result = {"available": False, "setups": []}
    try:
        setups = []
        for sym, name, unit in TARGETS:
            info = _analyze_symbol(sym, name, unit)
            if info:
                setups.append(info)

        if not setups:
            logger.warning("手法スキャナー: データ取得できず")
            return result

        result["setups"] = setups
        result["available"] = True
        result["telegram_message"] = _build_telegram(setups)
        logger.info(f"✅ 手法スキャナー完了（{len(setups)}銘柄・マルチタイムフレーム対応）")
        return result
    except Exception:
        logger.error("手法スキャナーエラー")
        logger.debug(traceback.format_exc())
        return result


def _build_telegram(setups: list) -> str:
    lines = ["📐 *手法シグナル・スキャナー*", "（週足×日足 マルチタイムフレーム）", "━━━━━━━━━━━━━━━"]
    for s in setups:
        lines.append(f"\n*{s['name']}*  {s['label']}")
        if s.get("weekly_label"):
            lines.append(f"　{s['weekly_label']}")
        lines.append(f"{s['desc']}")
        if s.get("mtf_note"):
            lines.append(f"　{s['mtf_note']}")
        lines.append(f"💡 {s['tip']}")
    lines.append("\n※教科書的なシグナルの有無を機械判定したものです。")
    return "\n".join(lines)
