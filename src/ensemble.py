"""
較正アンサンブル予測（フェーズ4・L4 精度土台）
複数の独立した予測手法を統合し、過去の Brier スコアで重み付けした
集合的な方向予測と確率を返す。

run(risk, ai_summary, scenario, technical, multi_consensus, prediction_tracker)
  → {"available": True, "direction": "bull"|"bear"|"neutral",
      "agreement_pct": 0-100, "brier_score": float,
      "confidence": "high"|"mid"|"low", "members": [...]}

各 member:
  name     : 手法名
  direction: bull / bear / neutral
  weight   : 重み（0-1）
  note     : 理由
"""
import json
import math
from pathlib import Path
from src.utils import BASE_DIR, setup_logger

logger = setup_logger("ensemble")

_PRED_FILE = BASE_DIR / "data" / "predictions.json"


def _load_brier() -> float | None:
    """predictions.json から全体 Brier スコアを読む。なければ None。"""
    try:
        data = json.loads(_PRED_FILE.read_text(encoding="utf-8"))
        acc  = data.get("accuracy", {})
        # Brier スコアは prediction_tracker が計算済みの場合のみ使用
        return acc.get("brier_score")
    except Exception:
        return None


def _risk_to_dir(risk: dict) -> tuple[str, str]:
    """indicators.py のリスクスコアを方向に変換する。"""
    score = risk.get("score", 0)
    if score >= 3:
        return "bull", f"リスクスコア {score:+.1f}（強気ゾーン≥+3）"
    if score <= -3:
        return "bear", f"リスクスコア {score:+.1f}（弱気ゾーン≤-3）"
    return "neutral", f"リスクスコア {score:+.1f}（中立ゾーン）"


def _ai_debate_dir(ai_summary: dict) -> tuple[str, str]:
    """AI 3視点議論の dominant 方向を返す。"""
    if not ai_summary or not ai_summary.get("available"):
        return "neutral", "AI議論未取得"
    # consensus_direction があれば優先
    cd = ai_summary.get("consensus_direction") or ai_summary.get("direction")
    if cd in ("bull", "bear", "neutral"):
        return cd, f"AI議論合意: {cd}"
    # フォールバック: 3テキストの長さでプロキシ
    bull_len = len(ai_summary.get("bull_view") or "")
    bear_len = len(ai_summary.get("bear_view") or "")
    if bull_len > bear_len * 1.3:
        return "bull", "強気テキストが優勢"
    if bear_len > bull_len * 1.3:
        return "bear", "弱気テキストが優勢"
    return "neutral", "強気・弱気が拮抗"


def _scenario_dir(scenario: dict) -> tuple[str, str]:
    """3シナリオの最高確率方向を返す。"""
    if not scenario or not scenario.get("available"):
        return "neutral", "シナリオ未取得"
    bull_p = scenario.get("bull", {}).get("prob", 0) or 0
    base_p = scenario.get("base", {}).get("prob", 0) or 0
    bear_p = scenario.get("bear", {}).get("prob", 0) or 0
    total  = bull_p + base_p + bear_p
    if total == 0:
        return "neutral", "シナリオ確率なし"
    if bull_p >= bear_p and bull_p >= base_p:
        return "bull", f"楽観シナリオ {bull_p}%が最高"
    if bear_p >= bull_p and bear_p >= base_p:
        return "bear", f"悲観シナリオ {bear_p}%が最高"
    return "neutral", f"基本シナリオ {base_p}%が最高（中立扱い）"


def _technical_dir(technical: dict) -> tuple[str, str]:
    """テクニカル分析の方向を返す。"""
    if not technical or not technical.get("available"):
        return "neutral", "テクニカル未取得"
    # setup_scanner 経由の setups がある場合はそれを使う
    signal = technical.get("overall_signal") or technical.get("signal")
    if isinstance(signal, str):
        s = signal.lower()
        if "buy" in s or "bull" in s or "買い" in s or "上昇" in s:
            return "bull", f"テクニカルシグナル: {signal}"
        if "sell" in s or "bear" in s or "売り" in s or "下落" in s:
            return "bear", f"テクニカルシグナル: {signal}"
    # RSI で判断（50以上=強気、50未満=弱気）
    rsi = technical.get("rsi")
    if rsi is not None:
        if rsi >= 55:
            return "bull", f"RSI={rsi:.1f}（強気圏）"
        if rsi <= 45:
            return "bear", f"RSI={rsi:.1f}（弱気圏）"
    return "neutral", "テクニカル中立"


def _consensus_dir(multi_consensus: dict) -> tuple[str, str]:
    """4AI合議の verdict 方向を返す。"""
    if not multi_consensus or not multi_consensus.get("available"):
        return "neutral", "4AI合議未取得"
    v   = multi_consensus.get("verdict", {})
    dir_ = v.get("direction", "neutral")
    lvl  = v.get("consensus_level", "")
    conf = v.get("consensus_confidence", 0.5)
    return dir_, f"4AI合議: {dir_} ({lvl} conf={conf:.2f})"


def _vote(members: list[dict]) -> tuple[str, float]:
    """重み付き多数決で方向と一致率(%)を返す。"""
    tally = {"bull": 0.0, "bear": 0.0, "neutral": 0.0}
    total = 0.0
    for m in members:
        w = m.get("weight", 1.0)
        d = m.get("direction", "neutral")
        tally[d] = tally.get(d, 0) + w
        total    += w
    if total == 0:
        return "neutral", 0.0
    winner    = max(tally, key=lambda k: tally[k])
    agree_pct = tally[winner] / total * 100
    return winner, round(agree_pct, 1)


def run(risk: dict = None,
        ai_summary: dict = None,
        scenario: dict = None,
        technical: dict = None,
        multi_consensus: dict = None,
        prediction_tracker: dict = None) -> dict:
    """
    アンサンブル予測を実行して返す。
    """
    risk            = risk            or {}
    ai_summary      = ai_summary      or {}
    scenario        = scenario        or {}
    technical       = technical       or {}
    multi_consensus = multi_consensus or {}

    # Brier スコアから基準重みを設定（スコアが低いほど精度高い = 重みを増やす）
    brier = _load_brier()
    if brier is not None and brier < 0.25:
        # 0.25 以下（ランダムより良い）→ 実績メンバーを 1.5 倍
        perf_boost = 1.5
    else:
        perf_boost = 1.0

    # 各メンバーの予測を集める
    members = []

    # 1. リスクスコア（指標較正済み重み）
    d, note = _risk_to_dir(risk)
    members.append({"name": "リスクスコア", "direction": d,
                    "weight": 2.0 * perf_boost, "note": note})

    # 2. AI3視点議論
    d, note = _ai_debate_dir(ai_summary)
    members.append({"name": "AI3視点議論", "direction": d,
                    "weight": 1.5, "note": note})

    # 3. 3シナリオ分析
    d, note = _scenario_dir(scenario)
    members.append({"name": "3シナリオ", "direction": d,
                    "weight": 1.5, "note": note})

    # 4. テクニカル分析
    d, note = _technical_dir(technical)
    members.append({"name": "テクニカル", "direction": d,
                    "weight": 1.0, "note": note})

    # 5. 4AI合議（最高重み: 合議体なのでシグナルが強い）
    d, note = _consensus_dir(multi_consensus)
    conf_boost = multi_consensus.get("verdict", {}).get("consensus_confidence", 0.5)
    members.append({"name": "4AI合議", "direction": d,
                    "weight": 2.0 * conf_boost, "note": note})

    # 重み付き多数決
    direction, agreement_pct = _vote(members)

    # 信頼度
    if agreement_pct >= 80:
        confidence = "high"
    elif agreement_pct >= 55:
        confidence = "mid"
    else:
        confidence = "low"

    result = {
        "available":     True,
        "direction":     direction,
        "agreement_pct": agreement_pct,
        "brier_score":   brier,
        "confidence":    confidence,
        "members":       members,
    }

    logger.info(
        f"アンサンブル完了: {direction} 一致率={agreement_pct:.0f}% "
        f"信頼度={confidence} Brier={brier}"
    )
    return result


if __name__ == "__main__":
    # 自己テスト（ダミーデータ）
    test_risk  = {"score": 5.2, "sentiment": "強気"}
    test_ai    = {"available": True, "consensus_direction": "bull"}
    test_scen  = {"available": True,
                  "bull": {"prob": 50}, "base": {"prob": 30}, "bear": {"prob": 20}}
    test_tech  = {"available": True, "rsi": 58.0}
    test_mc    = {"available": True, "verdict": {"direction": "bull",
                  "consensus_level": "strong", "consensus_confidence": 0.8}}

    result = run(test_risk, test_ai, test_scen, test_tech, test_mc)
    print(f"方向: {result['direction']}  一致率: {result['agreement_pct']}%  信頼度: {result['confidence']}")
    for m in result["members"]:
        print(f"  {m['name']:12s} → {m['direction']:8s} (w={m['weight']:.1f})  {m['note']}")
