"""
AI予測トラッカー（自己学習モジュール）
毎日の予測を記録 → 翌日の実際の結果と照合 → 正解率を計算
→ 正解率・パターンをGeminiにフィードバックして分析精度を向上させる
"""
import os
import json
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from src.utils import setup_logger, get_jst_now, get_today_str, get_dirs

logger = setup_logger("prediction_tracker")

PRED_FILE = Path("data/predictions.json")


# ──────────────────────────────────────────────────────────────
# データ読み書き
# ──────────────────────────────────────────────────────────────

def _load() -> dict:
    try:
        if PRED_FILE.exists():
            with open(PRED_FILE, encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"予測データ読込エラー: {e}")
    return {"predictions": [], "accuracy": {}}


def _save(data: dict):
    try:
        PRED_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(PRED_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"予測データ保存エラー: {e}")


# ──────────────────────────────────────────────────────────────
# 予測を保存
# ──────────────────────────────────────────────────────────────

def save_prediction(prices: dict, risk: dict, ai_summary: dict, scenario: dict):
    """
    今日の「予測」を記録する。
    - AIが「強気」「弱気」「中立」どれを言ったか
    - 現在の市場データ（検証用）
    """
    today = get_today_str()
    data  = _load()

    # AIの予測方向を判定
    direction = _extract_direction(ai_summary, scenario, risk)

    # 現在価格を記録
    def p(sym): return prices.get(sym, {}).get("latest")

    record = {
        "date":         today,
        "direction":    direction,      # "bull" / "bear" / "neutral"
        "score":        risk.get("score", 0),
        "fg":           None,           # fear_greedは外から渡せないので省略
        "nikkei":       p("^N225"),
        "sp500":        p("^GSPC"),
        "usdjpy":       p("USDJPY=X"),
        "vix":          p("^VIX"),
        "verified":     False,          # 翌日に検証済みになる
        "correct":      None,           # True/False/None
        "actual_move":  None,           # 翌日の実際の騰落率
    }

    # 既存の同日レコードを更新
    data["predictions"] = [p for p in data["predictions"] if p["date"] != today]
    data["predictions"].append(record)

    # 最新90日分のみ保持
    data["predictions"] = sorted(
        data["predictions"], key=lambda x: x["date"]
    )[-90:]

    _save(data)
    logger.info(f"予測記録: {today} → {direction} (スコア:{risk.get('score',0):+.2f})")
    return record


def _extract_direction(ai_summary: dict, scenario: dict, risk: dict) -> str:
    """AIの総合的な方向性を文字列で返す"""
    score = risk.get("score", 0)

    # スコアベースの判定
    if score >= 1.5:   base = "bull"
    elif score <= -1.5: base = "bear"
    else:               base = "neutral"

    # シナリオ確率で補正
    if scenario and scenario.get("available"):
        bull_p = scenario.get("bull", {}).get("prob", 0) or 0
        bear_p = scenario.get("bear", {}).get("prob", 0) or 0
        base_p = scenario.get("base", {}).get("prob", 0) or 0
        try:
            bull_p = int(bull_p); bear_p = int(bear_p)
        except Exception:
            pass
        if bull_p >= 45:   base = "bull"
        elif bear_p >= 45: base = "bear"
        else:               base = "neutral"

    return base


# ──────────────────────────────────────────────────────────────
# 昨日の予測を検証
# ──────────────────────────────────────────────────────────────

def verify_yesterday(prices: dict):
    """
    昨日の予測が当たったか検証する。
    日経平均の実際の値動きと予測方向を比較。
    """
    data     = _load()
    yesterday = (get_jst_now() - timedelta(days=1)).strftime("%Y-%m-%d")
    nk_now   = prices.get("^N225", {}).get("latest")
    if not nk_now:
        logger.warning("日経平均データなし → 検証スキップ")
        return

    updated = False
    for pred in data["predictions"]:
        if pred["date"] == yesterday and not pred["verified"]:
            nk_then = pred.get("nikkei")
            if not nk_then:
                continue

            actual_move = (nk_now - nk_then) / nk_then * 100
            direction   = pred["direction"]

            # 正解判定（±0.3%以内は中立とみなす）
            if actual_move > 0.3:    actual_dir = "bull"
            elif actual_move < -0.3: actual_dir = "bear"
            else:                    actual_dir = "neutral"

            correct = (direction == actual_dir)

            pred["verified"]    = True
            pred["correct"]     = correct
            pred["actual_move"] = round(actual_move, 2)
            pred["actual_dir"]  = actual_dir
            updated = True

            result_emoji = "✅" if correct else "❌"
            logger.info(
                f"{result_emoji} 検証: {yesterday} 予測={direction} "
                f"実際={actual_dir}({actual_move:+.2f}%) → {'正解' if correct else '不正解'}"
            )

    if updated:
        _save(data)

    return data


# ──────────────────────────────────────────────────────────────
# 正解率を計算
# ──────────────────────────────────────────────────────────────

def calc_accuracy() -> dict:
    """過去10日・30日・90日の正解率を計算"""
    data = _load()
    verified = [p for p in data["predictions"] if p.get("verified")]

    def acc(days: int) -> dict:
        cutoff   = (get_jst_now() - timedelta(days=days)).strftime("%Y-%m-%d")
        recent   = [p for p in verified if p["date"] >= cutoff]
        total    = len(recent)
        correct  = sum(1 for p in recent if p.get("correct"))
        rate     = correct / total * 100 if total > 0 else None

        # 方向別の正解率
        bull_total   = sum(1 for p in recent if p["direction"] == "bull")
        bull_correct = sum(1 for p in recent if p["direction"] == "bull" and p.get("correct"))
        bear_total   = sum(1 for p in recent if p["direction"] == "bear")
        bear_correct = sum(1 for p in recent if p["direction"] == "bear" and p.get("correct"))

        return {
            "total":        total,
            "correct":      correct,
            "rate":         round(rate, 1) if rate is not None else None,
            "bull_acc":     round(bull_correct/bull_total*100, 1) if bull_total > 0 else None,
            "bear_acc":     round(bear_correct/bear_total*100, 1) if bear_total > 0 else None,
        }

    result = {
        "10d":  acc(10),
        "30d":  acc(30),
        "90d":  acc(90),
        "total_verified": len(verified),
    }

    # 最近のパターン（直近5日）
    recent5 = sorted(verified, key=lambda x: x["date"])[-5:]
    result["recent5"] = [
        {
            "date":      p["date"],
            "direction": p["direction"],
            "correct":   p.get("correct"),
            "move":      p.get("actual_move"),
        }
        for p in recent5
    ]

    logger.info(
        f"正解率: 10日={result['10d']['rate']}% / "
        f"30日={result['30d']['rate']}% / "
        f"検証済={result['total_verified']}件"
    )
    return result


# ──────────────────────────────────────────────────────────────
# 学習フィードバックをGeminiに渡すテキスト生成
# ──────────────────────────────────────────────────────────────

def generate_learning_feedback() -> str:
    """
    Geminiに渡す「過去の予測実績」テキストを生成。
    これをプロンプトに含めることで分析精度が向上する。
    """
    stats = calc_accuracy()
    data  = _load()
    verified = [p for p in data["predictions"] if p.get("verified")]

    if not verified:
        return "（予測データ蓄積中）"

    lines = []

    # 正解率サマリー
    r10 = stats["10d"]["rate"]
    r30 = stats["30d"]["rate"]
    lines.append(f"【あなたの最近の予測実績】")
    if r10 is not None:
        emoji = "🎯" if r10 >= 60 else "⚠️" if r10 < 50 else "🔶"
        lines.append(f"{emoji} 直近10日の正解率: {r10}% ({stats['10d']['correct']}/{stats['10d']['total']})")
    if r30 is not None:
        lines.append(f"   直近30日の正解率: {r30}%")

    # 方向別の得意・不得意
    b_acc = stats["10d"].get("bull_acc")
    br_acc = stats["10d"].get("bear_acc")
    if b_acc is not None: lines.append(f"   強気予測の正解率: {b_acc}%")
    if br_acc is not None: lines.append(f"   弱気予測の正解率: {br_acc}%")

    # 直近5日の結果
    if stats.get("recent5"):
        lines.append("\n【直近の予測と結果】")
        icons = {"bull": "📈", "bear": "📉", "neutral": "➡️"}
        for r in stats["recent5"]:
            mark  = "✅" if r.get("correct") else "❌" if r.get("correct") is False else "⏳"
            icon  = icons.get(r["direction"], "")
            move  = f"{r['move']:+.1f}%" if r.get("move") is not None else ""
            lines.append(f"  {mark} {r['date']} {icon}{r['direction']} → 実際{move}")

    # 精度に応じた自己調整指示
    lines.append("\n【精度に基づく分析指針】")
    if r10 is not None:
        if r10 >= 65:
            lines.append("✅ 予測精度が高い状態です。自信を持って分析してください。")
        elif r10 >= 50:
            lines.append("🔶 予測精度は普通。バランスよく両サイドを考慮してください。")
        else:
            lines.append("⚠️ 最近予測が外れ気味です。より慎重に、断定を避けて分析してください。")
    else:
        lines.append("📊 データ蓄積中。標準的な分析を行ってください。")

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
# Geminiによる予測分析強化
# ──────────────────────────────────────────────────────────────

def analyze_with_learning(prices: dict, risk: dict, fear_greed: dict,
                           news: list, base_analysis: dict) -> str:
    """
    過去の予測実績を踏まえてGeminiが高精度な分析を行う
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return ""

    feedback = generate_learning_feedback()
    stats    = calc_accuracy()
    r10      = stats["10d"]["rate"]

    # データが少ない場合はスキップ
    if stats["total_verified"] < 3:
        logger.info("検証データ3件未満 → 学習フィードバックスキップ")
        return ""

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")

        def fmt(sym, unit=""):
            d = prices.get(sym, {})
            v = d.get("latest"); c = d.get("change_pct")
            if v is None: return "---"
            s = f"+{c:.2f}%" if (c or 0)>=0 else f"{c:.2f}%"
            return f"{v:,.2f}{unit}({s})"

        prompt = f"""あなたは自己学習する市場分析AIです。
過去の予測実績から自分の得意・不得意を把握し、より精度の高い分析を行います。

{feedback}

【現在の市場データ】
日経平均: {fmt('^N225','円')} / S&P500: {fmt('^GSPC')} / ドル円: {fmt('USDJPY=X','円')}
VIX: {fmt('^VIX')} / リスクスコア: {risk.get('score',0):+.2f}
Fear&Greed: {fear_greed.get('score', 50):.0f} ({fear_greed.get('rating_ja','---')})

【前回までのAI分析サマリー】
{base_analysis.get('neutral_view','なし')[:200] if base_analysis.get('available') else 'なし'}

上記の予測実績と現在データをもとに、以下を分析してください：

【🎯 精度向上ポイント】（100文字以内）
過去の予測パターンから、今日特に注意すべきことは何か。

【📊 今日の確信度】（高/中/低 + 理由を50文字）
現在の相場について、どの程度確信を持って予測できるか。

【🔮 今日の方向性予測】（bull/neutral/bear + 根拠100文字）
今日から明日にかけての方向性。過去の実績を踏まえた推測として。

断定表現は避け、すべて推測として述べてください。"""

        response = model.generate_content(prompt)
        result   = response.text
        logger.info("✅ 学習フィードバック分析完了")
        return result

    except Exception as e:
        logger.error(f"学習分析エラー: {e}")
        return ""


# ──────────────────────────────────────────────────────────────
# メイン実行
# ──────────────────────────────────────────────────────────────

def run(prices: dict, risk: dict, fear_greed: dict, news: list,
        ai_summary: dict, scenario: dict) -> dict:
    """予測トラッカーのメイン処理"""
    logger.info("=== 予測トラッカー開始 ===")

    # Step 1: 昨日の予測を検証
    verify_yesterday(prices)

    # Step 2: 正解率を計算
    stats = calc_accuracy()

    # Step 3: 今日の予測を記録
    pred = save_prediction(prices, risk, ai_summary, scenario)

    # Step 4: 学習フィードバック付き分析
    learning_analysis = analyze_with_learning(
        prices, risk, fear_greed, news, ai_summary
    )

    # Step 5: フィードバックテキスト（通知・HTMLに使う）
    feedback_text = generate_learning_feedback()

    logger.info(f"✅ 予測トラッカー完了 (検証済:{stats['total_verified']}件)")
    return {
        "available":        True,
        "stats":            stats,
        "today_prediction": pred,
        "learning_analysis": learning_analysis,
        "feedback_text":    feedback_text,
    }
