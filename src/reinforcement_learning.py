"""
強化学習ループ（L5c）
蓄積した予測データから「自分がいつ間違えるか」のパターンを学習する。
データが30件以上あればRandomForestで機械学習予測も実行。
Gemini予測 × ML予測のアンサンブル（加重平均）で精度向上を目指す。
"""
import json
import logging
import os
from pathlib import Path
from src.utils import get_jst_now

logger = logging.getLogger(__name__)

DATA_PATH = Path("data/predictions.json")
MIN_SAMPLES_FOR_ML = 20  # ML学習に必要な最低データ数


def _load_predictions() -> list:
    """predictions.jsonを読み込む"""
    if not DATA_PATH.exists():
        return []
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _extract_features(pred: dict) -> dict | None:
    """1件の予測データから特徴量を抽出"""
    # prediction_trackerが保存するデータ構造に対応
    try:
        vix = float(pred.get("vix", 20) or 20)
        fg = float(pred.get("fear_greed", 50) or 50)
        risk_score = float(pred.get("risk_score", 0) or 0)
        direction = pred.get("direction", "neutral")  # bull/bear/neutral
        correct = pred.get("correct")  # True/False/None

        # 検証済みデータのみ使用
        if correct is None:
            return None

        return {
            "vix": vix,
            "fg": fg,
            "risk_score": risk_score,
            "direction_num": {"bull": 1, "neutral": 0, "bear": -1}.get(direction, 0),
            "correct": int(correct),
        }
    except Exception:
        return None


def _analyze_failure_patterns(verified: list) -> dict:
    """どういう条件で間違えるかのパターン分析"""
    if not verified:
        return {}

    patterns = {
        "total": len(verified),
        "correct_count": sum(1 for v in verified if v.get("correct")),
        "vix_high_accuracy": None,   # VIX>25のときの正解率
        "vix_low_accuracy": None,    # VIX<15のときの正解率
        "fg_high_accuracy": None,    # FG>70のときの正解率
        "fg_low_accuracy": None,     # FG<30のときの正解率
        "bull_accuracy": None,       # 強気予測の正解率
        "bear_accuracy": None,       # 弱気予測の正解率
        "worst_condition": "",
        "best_condition": "",
    }

    overall_rate = patterns["correct_count"] / patterns["total"] * 100

    # VIX別
    vix_high = [v for v in verified if v.get("vix", 0) > 25]
    vix_low = [v for v in verified if v.get("vix", 0) < 15]
    fg_high = [v for v in verified if v.get("fg", 50) > 70]
    fg_low = [v for v in verified if v.get("fg", 50) < 30]
    bull_preds = [v for v in verified if v.get("direction_num", 0) > 0]
    bear_preds = [v for v in verified if v.get("direction_num", 0) < 0]

    def accuracy(lst):
        if not lst:
            return None
        return round(sum(v["correct"] for v in lst) / len(lst) * 100, 1)

    patterns["vix_high_accuracy"] = accuracy(vix_high)
    patterns["vix_low_accuracy"] = accuracy(vix_low)
    patterns["fg_high_accuracy"] = accuracy(fg_high)
    patterns["fg_low_accuracy"] = accuracy(fg_low)
    patterns["bull_accuracy"] = accuracy(bull_preds)
    patterns["bear_accuracy"] = accuracy(bear_preds)

    # 最悪・最良条件を特定
    condition_rates = []
    if patterns["vix_high_accuracy"] is not None:
        condition_rates.append(("VIX>25（恐怖）", patterns["vix_high_accuracy"]))
    if patterns["vix_low_accuracy"] is not None:
        condition_rates.append(("VIX<15（安定）", patterns["vix_low_accuracy"]))
    if patterns["fg_high_accuracy"] is not None:
        condition_rates.append(("F&G>70（強欲）", patterns["fg_high_accuracy"]))
    if patterns["fg_low_accuracy"] is not None:
        condition_rates.append(("F&G<30（恐怖）", patterns["fg_low_accuracy"]))

    if condition_rates:
        condition_rates.sort(key=lambda x: x[1])
        patterns["worst_condition"] = f"{condition_rates[0][0]}で正解率{condition_rates[0][1]:.0f}%と低い"
        patterns["best_condition"] = f"{condition_rates[-1][0]}で正解率{condition_rates[-1][1]:.0f}%と高い"

    patterns["overall_rate"] = round(overall_rate, 1)
    return patterns


def _train_ml_model(verified: list):
    """scikit-learnでRandomForestを訓練して返す"""
    try:
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.preprocessing import StandardScaler
        import numpy as np

        X = []
        y = []
        for v in verified:
            X.append([v["vix"], v["fg"], v["risk_score"]])
            y.append(v["direction_num"])  # -1, 0, 1

        X = np.array(X)
        y = np.array(y)

        if len(set(y)) < 2:
            return None, None  # クラスが1種類しかない場合はスキップ

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        clf = RandomForestClassifier(n_estimators=50, max_depth=4, random_state=42)
        clf.fit(X_scaled, y)

        logger.info(f"  RandomForest訓練完了 ({len(X)}サンプル)")
        return clf, scaler
    except ImportError:
        logger.info("  scikit-learnが見つかりません。パターン分析のみ実施します。")
        return None, None
    except Exception as e:
        logger.warning(f"  ML訓練エラー: {e}")
        return None, None


def _ml_predict(clf, scaler, current_features: dict) -> dict:
    """訓練済みモデルで今日を予測"""
    try:
        import numpy as np
        X = np.array([[
            current_features["vix"],
            current_features["fg"],
            current_features["risk_score"],
        ]])
        X_scaled = scaler.transform(X)
        pred = clf.predict(X_scaled)[0]
        proba = clf.predict_proba(X_scaled)[0]
        max_proba = round(float(max(proba)) * 100, 1)

        direction = {1: "bull", 0: "neutral", -1: "bear"}.get(int(pred), "neutral")

        # 特徴量重要度
        importance = dict(zip(
            ["VIX", "Fear&Greed", "リスクスコア"],
            [round(float(v) * 100, 1) for v in clf.feature_importances_]
        ))

        return {
            "direction": direction,
            "confidence": max_proba,
            "feature_importance": importance,
        }
    except Exception as e:
        logger.warning(f"  ML予測エラー: {e}")
        return {"direction": "neutral", "confidence": 33.0, "feature_importance": {}}


def run(prices, risk, fear_greed, technical=None) -> dict:
    """強化学習ループを実行"""
    logger.info("--- 強化学習ループ ---")
    result = {"available": False}

    # 現在の特徴量
    current_features = {
        "vix": prices.get("^VIX", {}).get("latest", 20) or 20,
        "fg": fear_greed.get("score", 50) or 50,
        "risk_score": risk.get("score", 0),
    }

    # 予測データを読み込み
    all_preds = _load_predictions()
    logger.info(f"  読み込み: {len(all_preds)}件の予測")

    # 特徴量抽出
    verified = []
    for pred in all_preds:
        feat = _extract_features(pred)
        if feat is not None:
            verified.append(feat)

    total_verified = len(verified)
    logger.info(f"  検証済み: {total_verified}件")

    if total_verified == 0:
        logger.info("  検証済みデータなし — パターン分析スキップ")
        result = {
            "available": False,
            "reason": "データ蓄積中（まだ予測データがありません）",
            "total_verified": 0,
            "current_features": current_features,
        }
        return result

    # パターン分析（件数問わず実施）
    patterns = _analyze_failure_patterns(verified)

    # ML予測（30件以上の場合）
    ml_result = None
    model_used = "パターン分析"

    if total_verified >= MIN_SAMPLES_FOR_ML:
        clf, scaler = _train_ml_model(verified)
        if clf is not None:
            ml_result = _ml_predict(clf, scaler, current_features)
            model_used = "RandomForest"
            logger.info(f"  ML予測: {ml_result.get('direction')} (確信度{ml_result.get('confidence')}%)")

    # 学習レポート生成
    overall = patterns.get("overall_rate", 0)
    worst = patterns.get("worst_condition", "")
    best = patterns.get("best_condition", "")

    learning_summary = f"検証{total_verified}件 / 総合正解率{overall:.0f}%"
    if worst:
        learning_summary += f" / 弱点: {worst}"
    if best:
        learning_summary += f" / 強み: {best}"

    result = {
        "available": True,
        "total_verified": total_verified,
        "patterns": patterns,
        "ml_result": ml_result,
        "model_used": model_used,
        "current_features": current_features,
        "learning_summary": learning_summary,
        "needs_more_data": total_verified < MIN_SAMPLES_FOR_ML,
        "data_needed": max(0, MIN_SAMPLES_FOR_ML - total_verified),
    }

    logger.info(f"✅ 強化学習: {learning_summary}")
    return result


def format_telegram(data: dict) -> str:
    if not data.get("available"):
        reason = data.get("reason", "データ不足")
        return f"🤖 *強化学習ループ*\n  {reason}"

    patterns = data.get("patterns", {})
    ml = data.get("ml_result")
    total = data.get("total_verified", 0)
    overall = patterns.get("overall_rate", 0)

    lines = [
        "🤖 *強化学習ループ — 自己学習レポート*",
        "━━━━━━━━━━━━━━━",
        f"📊 学習データ: {total}件検証済み",
        f"🎯 総合正解率: {overall:.0f}%",
        "",
        "📈 発見したパターン:",
    ]

    bull_acc = patterns.get("bull_accuracy")
    bear_acc = patterns.get("bear_accuracy")
    if bull_acc is not None:
        lines.append(f"  📈 強気予測の正解率: {bull_acc:.0f}%")
    if bear_acc is not None:
        lines.append(f"  📉 弱気予測の正解率: {bear_acc:.0f}%")
    if patterns.get("worst_condition"):
        lines.append(f"  ⚠️ 弱点: {patterns['worst_condition']}")
    if patterns.get("best_condition"):
        lines.append(f"  ✅ 強み: {patterns['best_condition']}")

    if ml:
        dir_ja = {"bull": "📈 上昇", "bear": "📉 下落", "neutral": "➡️ 中立"}
        lines += [
            "",
            "🧠 *RandomForest予測*",
            f"  方向: {dir_ja.get(ml.get('direction','neutral'), '---')}",
            f"  確信度: {ml.get('confidence', 0):.0f}%",
        ]
        imp = ml.get("feature_importance", {})
        if imp:
            top_feat = max(imp, key=imp.get)
            lines.append(f"  最重要因子: {top_feat} ({imp[top_feat]:.0f}%)")
    elif data.get("needs_more_data"):
        lines.append(f"\n  💡 ML有効化まであと{data.get('data_needed',0)}件")

    return "\n".join(lines)
