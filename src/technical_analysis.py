"""
テクニカル分析モジュール
yfinanceの履歴データからMA・RSI・MACD・BB・ストキャスを計算
"""
import pandas as pd
import numpy as np
import yfinance as yf
import time
from src.utils import setup_logger

logger = setup_logger("technical")

SYMBOLS = {
    "^N225":    "日経平均",
    "^GSPC":    "S&P500",
    "^IXIC":    "NASDAQ",
    "USDJPY=X": "ドル円",
    "GC=F":     "金",
    "CL=F":     "原油",
    "BTC-USD":  "Bitcoin",
}


def _calc_rsi(close: pd.Series, period: int = 14) -> float | None:
    try:
        delta = close.diff()
        gain  = delta.clip(lower=0).rolling(period).mean()
        loss  = (-delta.clip(upper=0)).rolling(period).mean()
        rs    = gain / loss
        rsi   = 100 - (100 / (1 + rs))
        val   = rsi.dropna()
        return round(float(val.iloc[-1]), 1) if len(val) > 0 else None
    except Exception:
        return None


def _calc_macd(close: pd.Series) -> dict:
    try:
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd  = ema12 - ema26
        signal= macd.ewm(span=9, adjust=False).mean()
        hist  = macd - signal
        return {
            "macd":   round(float(macd.iloc[-1]), 2),
            "signal": round(float(signal.iloc[-1]), 2),
            "hist":   round(float(hist.iloc[-1]), 2),
            "cross":  "ゴールデンクロス" if (macd.iloc[-1] > signal.iloc[-1] and
                                              macd.iloc[-2] <= signal.iloc[-2]) else
                      "デッドクロス"     if (macd.iloc[-1] < signal.iloc[-1] and
                                              macd.iloc[-2] >= signal.iloc[-2]) else "なし",
        }
    except Exception:
        return {}


def _calc_bb(close: pd.Series, period: int = 20) -> dict:
    try:
        ma    = close.rolling(period).mean()
        std   = close.rolling(period).std()
        upper = ma + 2 * std
        lower = ma - 2 * std
        cur   = close.iloc[-1]
        pos   = (cur - lower.iloc[-1]) / (upper.iloc[-1] - lower.iloc[-1]) * 100
        return {
            "upper":    round(float(upper.iloc[-1]), 2),
            "middle":   round(float(ma.iloc[-1]), 2),
            "lower":    round(float(lower.iloc[-1]), 2),
            "position": round(float(pos), 1),
            "signal":   "上限接近(過熱)" if pos > 80 else
                        "下限接近(売られすぎ)" if pos < 20 else "中間",
        }
    except Exception:
        return {}


def _calc_stochastic(high, low, close, k=14, d=3) -> dict:
    try:
        lowest  = low.rolling(k).min()
        highest = high.rolling(k).max()
        k_val   = (close - lowest) / (highest - lowest) * 100
        d_val   = k_val.rolling(d).mean()
        return {
            "k": round(float(k_val.iloc[-1]), 1),
            "d": round(float(d_val.iloc[-1]), 1),
            "signal": "買われすぎ" if k_val.iloc[-1] > 80 else
                      "売られすぎ" if k_val.iloc[-1] < 20 else "中間",
        }
    except Exception:
        return {}


def _trend_signal(close: pd.Series, ma5, ma25, ma75) -> str:
    """トレンド判定"""
    try:
        cur = close.iloc[-1]
        signals = []
        if cur > ma5 and ma5 > ma25:
            signals.append("短期上昇トレンド")
        elif cur < ma5 and ma5 < ma25:
            signals.append("短期下落トレンド")
        if ma25 > ma75:
            signals.append("中期上昇")
        elif ma25 < ma75:
            signals.append("中期下落")
        return " / ".join(signals) if signals else "方向感なし"
    except Exception:
        return "判定不可"


def analyze_symbol(symbol: str, name: str) -> dict:
    try:
        tk   = yf.Ticker(symbol)
        hist = tk.history(period="90d")
        if hist.empty or len(hist) < 26:
            return {"symbol": symbol, "name": name, "error": "データ不足"}

        close = hist["Close"]
        high  = hist["High"]
        low   = hist["Low"]
        cur   = float(close.iloc[-1])

        # 移動平均
        ma5  = float(close.rolling(5).mean().dropna().iloc[-1])  if len(close)>=5  else None
        ma25 = float(close.rolling(25).mean().dropna().iloc[-1]) if len(close)>=25 else None
        ma75 = float(close.rolling(75).mean().dropna().iloc[-1]) if len(close)>=75 else None

        # 乖離率
        def dev(ma): return round((cur - ma) / ma * 100, 2) if ma else None

        result = {
            "symbol":  symbol,
            "name":    name,
            "current": round(cur, 2),
            "ma": {
                "ma5":   round(ma5,  2) if ma5  else None,
                "ma25":  round(ma25, 2) if ma25 else None,
                "ma75":  round(ma75, 2) if ma75 else None,
                "dev_ma5":  dev(ma5),
                "dev_ma25": dev(ma25),
                "dev_ma75": dev(ma75),
            },
            "rsi":        _calc_rsi(close),
            "macd":       _calc_macd(close),
            "bb":         _calc_bb(close),
            "stochastic": _calc_stochastic(high, low, close),
            "trend":      _trend_signal(close, ma5, ma25, ma75),
        }

        # RSIシグナル
        rsi = result["rsi"]
        if rsi:
            result["rsi_signal"] = "買われすぎ注意" if rsi > 70 else \
                                   "売られすぎ注意" if rsi < 30 else "中立"

        logger.info(f"[OK] テクニカル: {name} RSI={rsi} トレンド={result['trend']}")
        return result

    except Exception as e:
        logger.error(f"[FAIL] テクニカル {name}: {e}")
        return {"symbol": symbol, "name": name, "error": str(e)}


def run_technical() -> dict:
    import json
    from src.utils import get_today_str, get_dirs
    logger.info("=== テクニカル分析開始 ===")
    results = {}
    for sym, name in SYMBOLS.items():
        results[sym] = analyze_symbol(sym, name)
        time.sleep(0.5)
    # 保存
    dirs = get_dirs()
    path = dirs["data_processed"] / f"{get_today_str()}_technical.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    logger.info(f"=== テクニカル分析完了: {len(results)}件 → {path} ===")
    return results
