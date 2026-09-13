"""
情報源クロスチェック（精度向上）
複数の独立した分析手法（リスクスコア / 4AI合議 / シナリオ確率 / テクニカル）の
方向性が一致しているかを突き合わせ、一致度=信頼度として可視化する。
全手法が同じ結論なら信頼でき、バラバラなら「情報が割れている」と警告して過信を防ぐ。
外部API不要・既存の分析結果を突き合わせるだけの軽量モジュール。
"""
from collections import Counter
from src.utils import setup_logger

logger = setup_logger("cross_check")

_DIR_JA = {"bull": "上昇", "bear": "下落", "neutral": "中立"}


def _risk_dir(risk: dict):
    """リスクスコアから方向を判定（prediction_trackerと同じ閾値）"""
    s = (risk or {}).get("score", 0) or 0
    if s >= 3.0:  return "bull"
    if s <= -3.0: return "bear"
    return "neutral"


def _consensus_dir(mc: dict):
    """4AI合議の最終方向"""
    if not mc or not mc.get("available"):
        return None
    return mc.get("verdict", {}).get("direction")


def _scenario_dir(scenario: dict):
    """3シナリオのうち最も確率の高いものの方向"""
    if not scenario or not scenario.get("available"):
        return None
    probs = {
        "bull":    scenario.get("bull", {}).get("prob", 0) or 0,
        "neutral": scenario.get("base", {}).get("prob", 0) or 0,
        "bear":    scenario.get("bear", {}).get("prob", 0) or 0,
    }
    if max(probs.values()) == 0:
        return None
    return max(probs, key=probs.get)


def _technical_dir(technical: dict):
    """テクニカル（S&P500のMACD/RSI）から方向を判定"""
    if not technical or not technical.get("available"):
        return None
    for r in technical.get("results", []):
        label = r.get("label", "")
        if "S&P" in label or "SP500" in label:
            macd = r.get("macd_hist", 0) or 0
            rsi  = r.get("rsi")
            if macd > 0 and (rsi is None or rsi < 70): return "bull"
            if macd < 0 and (rsi is None or rsi > 30): return "bear"
            return "neutral"
    return None


def run(risk: dict, multi_consensus: dict = None,
        scenario: dict = None, technical: dict = None) -> dict:
    """4つの独立シグナルの方向一致度を計算する"""
    sources = []

    def add(name, d):
        if d:
            sources.append({"name": name, "dir": d, "dir_ja": _DIR_JA.get(d, d)})

    add("リスクスコア", _risk_dir(risk))
    add("4AI合議",     _consensus_dir(multi_consensus))
    add("シナリオ確率", _scenario_dir(scenario))
    add("テクニカル",   _technical_dir(technical))

    # 2つ以上の独立シグナルが揃わなければ比較できない
    if len(sources) < 2:
        return {"available": False}

    counts = Counter(s["dir"] for s in sources)
    verdict, top = counts.most_common(1)[0]
    agreement = round(top / len(sources), 2)
    conflict  = agreement < 0.6

    if agreement >= 1.0:
        level, emoji = "完全一致", "🔥"
    elif agreement >= 0.66:
        level, emoji = "おおむね一致", "✅"
    elif agreement >= 0.5:
        level, emoji = "やや割れ", "🟡"
    else:
        level, emoji = "意見が割れている", "⚠️"

    summary = (f"{len(sources)}つの分析手法のうち{top}つが"
               f"「{_DIR_JA.get(verdict, verdict)}」で一致（{level}）")
    logger.info(f"クロスチェック: {summary}")

    return {
        "available":  True,
        "sources":    sources,
        "verdict":    verdict,
        "verdict_ja": _DIR_JA.get(verdict, verdict),
        "agreement":  agreement,
        "conflict":   conflict,
        "level":      level,
        "emoji":      emoji,
        "summary":    summary,
    }
