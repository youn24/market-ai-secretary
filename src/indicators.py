"""
市場指標の計算：リスクオン/オフ判定、地合い評価

リスクスコアの重みは config/signal_weights.json（calibrate_weights.py が生成）を
読み込んで使う。これは「各指標の前営業日リターンが、実際に翌日の日経をどれだけ
当てたか（相関）」で決めた“実績ベース”の重み。較正ファイルが無ければ従来の既定値で動く。
"""
import json
from pathlib import Path
from src.utils import setup_logger

logger = setup_logger("indicators")

_WEIGHTS_PATH = Path(__file__).parent.parent / "config" / "signal_weights.json"

# 既定重み（較正ファイルが無い場合のフォールバック＝従来の手打ち値）
_DEFAULT_WEIGHTS = {
    "^GSPC": 1.0, "^IXIC": 1.0, "^N225": 1.0,
    "^VIX": -0.5, "GC=F": -0.3, "USDJPY=X": 0.5,
}
_NAMES = {
    "^GSPC": "S&P500", "^IXIC": "NASDAQ", "^N225": "日経平均", "^SOX": "半導体SOX",
    "^VIX": "VIX", "GC=F": "金", "USDJPY=X": "ドル円",
}

# 後方互換のため従来の定数も残す
RISK_ON_SIGNALS = {"^GSPC": "S&P500", "^IXIC": "NASDAQ", "^N225": "日経平均"}
RISK_OFF_SIGNALS = {"^VIX": "VIX", "GC=F": "金"}
USDJPY_SYMBOL = "USDJPY=X"


def _load_weights() -> tuple:
    """(weights dict, meta or None) を返す。較正ファイルがあればそれを使う。"""
    try:
        data = json.loads(_WEIGHTS_PATH.read_text(encoding="utf-8"))
        w = {s: v.get("weight") for s, v in data.get("weights", {}).items()
             if v.get("weight") is not None}
        if w:
            return w, data
    except Exception:
        pass
    return dict(_DEFAULT_WEIGHTS), None


def calc_risk_score(prices: dict) -> dict:
    """
    リスクオン/オフスコアを計算する。
    スコア > 0: 翌日の日経に上昇圧力 / スコア < 0: 下落圧力
    重みは実績較正（config/signal_weights.json）を優先使用。
    """
    weights, meta = _load_weights()
    calibrated = meta is not None

    score = 0.0
    signals = []
    for sym, w in weights.items():
        if w is None:
            continue
        chg = (prices.get(sym) or {}).get("change_pct")
        if chg is None:
            continue
        contrib = chg * w
        score += contrib
        name = _NAMES.get(sym, sym)
        if abs(contrib) < 0.02:
            direction = "中立"
        elif contrib > 0:
            direction = "上昇圧力"
        else:
            direction = "下落圧力"
        signals.append({
            "indicator": name,
            "change": round(chg, 2),
            "weight": round(w, 2),
            "contribution": round(contrib, 2),
            "direction": direction,
            "type": "risk_on" if w >= 0 else "risk_off",
        })

    # 影響の大きい順（寄与の絶対値）に並べる
    signals.sort(key=lambda s: abs(s["contribution"]), reverse=True)

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
        "calibrated": calibrated,
    }
    if calibrated:
        # 最も効いている指標トップ3（相関）を添える
        ws = meta.get("weights", {})
        top = sorted(ws.items(), key=lambda kv: abs(kv[1].get("corr", 0)), reverse=True)
        result["top_predictors"] = [
            {"name": v.get("name"), "corr": v.get("corr")} for _, v in top[:3]
        ]
        result["calibrated_at"] = (meta.get("generated_at") or "")[:10]
    tag = "実績較正" if calibrated else "既定重み"
    logger.info(f"リスク判定: {sentiment} (スコア={score:.2f}) [{tag}]")
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
