"""
自己改善AI エンジン
予測ミスのパターンを自動分析し、予測ロジックのパラメータを自動最適化する。
毎週日曜夜に実行し、精度が向上していればコードを書き換えてgit pushする。

これが本当の「自律AI」 ― 人間が寝ている間に自分で賢くなる。
"""
import json
import os
import re
import traceback
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from itertools import product
import logging

logger = logging.getLogger(__name__)


def _load_predictions() -> list:
    path = Path("data/predictions.json")
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("predictions", [])
    except Exception:
        return []


def _accuracy_for_params(predictions: list, bull_th: float, bear_th: float,
                          vix_weight: float) -> float:
    """
    仮のパラメータで全予測を再評価し、正解率を返す。
    これが「バックテスト」の核心部分。
    """
    correct = 0
    total = 0
    for p in predictions:
        if not p.get("verified"):
            continue
        # 元のスコアから新パラメータで方向を再計算
        bull_p = p.get("bull_probability", 0) or 0
        bear_p = p.get("bear_probability", 0) or 0
        vix = p.get("vix") or 20
        risk = p.get("risk_score") or 0

        # VIXによる補正
        vix_adj = min((vix - 20) * vix_weight, 10) if vix > 20 else 0
        bear_p_adj = bear_p + vix_adj
        bull_p_adj = bull_p - vix_adj

        if bull_p_adj >= bull_th:
            simulated_dir = "bull"
        elif bear_p_adj >= bear_th:
            simulated_dir = "bear"
        else:
            simulated_dir = "neutral"

        actual_chg = p.get("actual_change_pct") or 0
        if simulated_dir == "bull":
            predicted_correct = actual_chg > 0.3
        elif simulated_dir == "bear":
            predicted_correct = actual_chg < -0.3
        else:
            predicted_correct = abs(actual_chg) <= 1.0

        if predicted_correct:
            correct += 1
        total += 1

    return correct / total * 100 if total > 0 else 0


def grid_search_params(predictions: list) -> dict:
    """
    グリッドサーチで最適パラメータを探す。
    bull_threshold: 45〜60 / bear_threshold: 40〜55 / vix_weight: 0〜0.5
    """
    verified = [p for p in predictions if p.get("verified")]
    if len(verified) < 5:
        return {"enough_data": False}

    best_acc = 0
    best_params = {"bull_th": 45, "bear_th": 40, "vix_weight": 0.2}

    bull_range = [40, 42, 45, 48, 50, 52, 55]
    bear_range = [35, 38, 40, 42, 45, 48]
    vix_range  = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]

    for bull_th, bear_th, vix_w in product(bull_range, bear_range, vix_range):
        acc = _accuracy_for_params(verified, bull_th, bear_th, vix_w)
        if acc > best_acc:
            best_acc = acc
            best_params = {"bull_th": bull_th, "bear_th": bear_th, "vix_weight": vix_w}

    current_acc = _accuracy_for_params(verified, 45, 40, 0.2)

    return {
        "enough_data": True,
        "current_accuracy": round(current_acc, 1),
        "best_accuracy": round(best_acc, 1),
        "best_params": best_params,
        "improvement": round(best_acc - current_acc, 1),
        "n_verified": len(verified),
    }


def analyze_failure_patterns(predictions: list) -> dict:
    """失敗パターンを分析して苦手な市場環境を特定"""
    failures = [p for p in predictions if p.get("verified") and not p.get("correct")]
    successes = [p for p in predictions if p.get("verified") and p.get("correct")]

    if not failures:
        return {"patterns": []}

    patterns = []

    # VIX別成績
    for vix_min, vix_max, label in [(0, 15, "低VIX(<15)"), (15, 25, "中VIX(15-25)"), (25, 100, "高VIX(>25)")]:
        f_count = sum(1 for p in failures if vix_min <= (p.get("vix") or 20) < vix_max)
        s_count = sum(1 for p in successes if vix_min <= (p.get("vix") or 20) < vix_max)
        total = f_count + s_count
        if total > 0:
            acc = s_count / total * 100
            patterns.append({
                "condition": label,
                "accuracy": round(acc, 1),
                "n": total,
                "weak": acc < 50,
            })

    # 方向別成績
    for direction in ["bull", "bear", "neutral"]:
        f_count = sum(1 for p in failures if p.get("direction") == direction)
        s_count = sum(1 for p in successes if p.get("direction") == direction)
        total = f_count + s_count
        if total > 0:
            acc = s_count / total * 100
            patterns.append({
                "condition": f"{direction}予測",
                "accuracy": round(acc, 1),
                "n": total,
                "weak": acc < 50,
            })

    return {"patterns": patterns}


def apply_parameter_update(best_params: dict) -> bool:
    """
    prediction_tracker.py のパラメータを最適値に書き換える。
    コメントで「自己改善エンジンが最適化」と明記する。
    """
    tracker_path = Path("src/prediction_tracker.py")
    if not tracker_path.exists():
        return False

    try:
        code = tracker_path.read_text(encoding="utf-8")
        now = datetime.now().strftime("%Y-%m-%d")
        bull_th = best_params["bull_th"]
        bear_th = best_params["bear_th"]

        # bull threshold を置き換え
        code = re.sub(
            r'(bull_threshold\s*=\s*)\d+',
            f'\\g<1>{bull_th}  # 自己改善エンジンが最適化 ({now})',
            code
        )
        # bear threshold を置き換え
        code = re.sub(
            r'(bear_threshold\s*=\s*)\d+',
            f'\\g<1>{bear_th}  # 自己改善エンジンが最適化 ({now})',
            code
        )

        tracker_path.write_text(code, encoding="utf-8")
        logger.info(f"パラメータ更新完了: bull={bull_th}, bear={bear_th}")
        return True
    except Exception as e:
        logger.error(f"パラメータ更新失敗: {e}")
        return False


def gemini_insight(patterns: dict, grid_result: dict) -> str:
    """Geminiに失敗パターンを解析させてコメントを生成"""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return ""
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")

        weak_patterns = [p for p in patterns.get("patterns", []) if p.get("weak")]
        pattern_text = "\n".join(
            f"・{p['condition']}: 正解率{p['accuracy']}%（{p['n']}件）"
            for p in weak_patterns
        ) or "特定の弱点なし"

        prompt = f"""AI市場予測システムの自己分析レポートです。

弱点パターン:
{pattern_text}

現在の正解率: {grid_result.get('current_accuracy', '---')}%
最適化後の予測正解率: {grid_result.get('best_accuracy', '---')}%
改善幅: +{grid_result.get('improvement', '---')}%

このパターンから、市場予測AIが苦手とする市場環境と改善の方向性を
100文字以内で端的に説明してください。"""

        resp = model.generate_content(prompt)
        return resp.text[:200]
    except Exception:
        return ""


def run_and_auto_improve() -> dict:
    """
    自己改善サイクルのメイン関数。
    1. 予測データを読み込む
    2. グリッドサーチで最適パラメータを探す
    3. 精度が5%以上改善するならパラメータを自動更新
    4. Geminiがコメントを生成
    5. 結果を返す
    """
    logger.info("=== 自己改善AI エンジン 起動 ===")
    result = {"available": False}

    try:
        predictions = _load_predictions()
        if not predictions:
            logger.warning("予測データなし")
            return result

        logger.info(f"  予測データ: {len(predictions)}件")

        # グリッドサーチ
        logger.info("  グリッドサーチ実行中...")
        grid_result = grid_search_params(predictions)
        if not grid_result.get("enough_data"):
            logger.info("  データ不足 → スキップ")
            return {"available": True, "enough_data": False,
                    "message": f"データ蓄積中（{len(predictions)}件）"}

        logger.info(
            f"  現在: {grid_result['current_accuracy']}% → "
            f"最適: {grid_result['best_accuracy']}% "
            f"(+{grid_result['improvement']}%)"
        )

        # 失敗パターン分析
        patterns = analyze_failure_patterns(predictions)

        # 自動改善実行（5%以上改善の場合）
        auto_updated = False
        if grid_result["improvement"] >= 5.0:
            logger.info(f"  🚀 5%以上改善 → 自動パラメータ更新実行")
            auto_updated = apply_parameter_update(grid_result["best_params"])
            if auto_updated:
                logger.info("  ✅ パラメータ自動更新完了")
        else:
            logger.info(f"  改善幅{grid_result['improvement']}% < 5% → 更新保留")

        # Gemini分析コメント
        ai_comment = gemini_insight(patterns, grid_result)

        result = {
            "available": True,
            "enough_data": True,
            "current_accuracy": grid_result["current_accuracy"],
            "best_accuracy": grid_result["best_accuracy"],
            "improvement": grid_result["improvement"],
            "best_params": grid_result["best_params"],
            "patterns": patterns.get("patterns", []),
            "auto_updated": auto_updated,
            "ai_comment": ai_comment,
            "n_verified": grid_result["n_verified"],
            "run_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

        logger.info(f"✅ 自己改善AI完了: 自動更新={'あり' if auto_updated else 'なし'}")

    except Exception as e:
        logger.error(f"自己改善AIエラー: {e}")
        logger.debug(traceback.format_exc())

    return result
