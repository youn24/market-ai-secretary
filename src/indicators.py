"""
市場指標の計算：リスクオン/オフ判定、地合い評価
"""
from src.utils import setup_logger

logger = setup_logger("indicators")

# リスクオン/オフ判定に使う指標
RISK_ON_SIGNALS = {
    "^GSPC": "S&P500",
    "^IXIC": "NASDAQ",
    "^N225": "日経平均",
}
RISK_OFF_SIGNALS = {
    "^VIX": "VIX",
    "GC=F": "金",
}
USDJPY_SYMBOL = "USDJPY=X"


def calc_risk_score(prices: dict) -> dict:
    """
    リスクオン/オフスコアを計算する。
    スコア > 0: リスクオン傾向
    スコア < 0: リスクオフ傾向
    """
    score = 0.0
    signals = []

    # リスクオン指標：上昇→プラス
    for sym, name in RISK_ON_SIGNALS.items():
        p = prices.get(sym, {})
        chg = p.get("change_pct")
        if chg is not None:
            weight = 1.0
            score += chg * weight
            direction = "上昇" if chg > 0 else "下落"
            signals.append({"indicator": name, "change": chg, "direction": direction, "type": "risk_on"})

    # VIX：上昇→リスクオフ（マイナス）
    vix = prices.get("^VIX", {})
    vix_chg = vix.get("change_pct")
    if vix_chg is not None:
        score -= vix_chg * 0.5
        direction = "上昇(不安増大)" if vix_chg > 0 else "低下(不安後退)"
        signals.append({"indicator": "VIX", "change": vix_chg, "direction": direction, "type": "risk_off"})

    # 金：上昇→リスクオフ（マイナス）
    gold = prices.get("GC=F", {})
    gold_chg = gold.get("change_pct")
    if gold_chg is not None:
        score -= gold_chg * 0.3
        direction = "上昇(安全資産買い)" if gold_chg > 0 else "低下"
        signals.append({"indicator": "金", "change": gold_chg, "direction": direction, "type": "risk_off"})

    # ドル円：上昇→リスクオン
    usdjpy = prices.get(USDJPY_SYMBOL, {})
    usdjpy_chg = usdjpy.get("change_pct")
    if usdjpy_chg is not None:
        score += usdjpy_chg * 0.5
        direction = "円安(リスクオン方向)" if usdjpy_chg > 0 else "円高(リスクオフ方向)"
        signals.append({"indicator": "ドル円", "change": usdjpy_chg, "direction": direction, "type": "forex"})

    # 判定
    if score >= 1.5:
        sentiment = "強気 (リスクオン)"
        meter = "RISK_ON"
    elif score <= -1.5:
        sentiment = "弱気 (リスクオフ)"
        meter = "RISK_OFF"
    else:
        sentiment = "中立"
        meter = "NEUTRAL"

    result = {
        "score": round(score, 2),
        "sentiment": sentiment,
        "meter": meter,
        "signals": signals,
    }
    logger.info(f"リスク判定: {sentiment} (スコア={score:.2f})")
    return result


def summarize_market(prices: dict, risk: dict) -> dict:
    """市場全体のサマリーを作成する。"""
    summary = {
        "sentiment": risk.get("sentiment", "不明"),
        "meter": risk.get("meter", "NEUTRAL"),
        "score": risk.get("score", 0),
        "key_moves": [],
    }

    key_symbols = [
        ("^N225", "日経平均"),
        ("^GSPC", "S&P500"),
        ("USDJPY=X", "ドル円"),
        ("^TNX", "米10年金利"),
        ("^VIX", "VIX"),
        ("GC=F", "金"),
        ("CL=F", "原油"),
        ("BTC-USD", "Bitcoin"),
    ]

    for sym, name in key_symbols:
        p = prices.get(sym, {})
        latest = p.get("latest")
        chg = p.get("change_pct")
        if latest is not None:
            summary["key_moves"].append({
                "name": name,
                "latest": latest,
                "change_pct": chg,
                "error": p.get("error"),
            })

    return summary
