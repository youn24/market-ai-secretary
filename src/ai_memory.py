"""
AI記憶機能モジュール
過去の分析・判断を記憶して学習する
"""
import os
import json
import traceback
from pathlib import Path
from src.utils import setup_logger, get_jst_now, get_today_str, get_dirs

logger = setup_logger("ai_memory")

MEMORY_FILE = Path("data/ai_memory.json")


def load_memory() -> dict:
    """記憶を読み込む"""
    try:
        if MEMORY_FILE.exists():
            with open(MEMORY_FILE, encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"記憶読み込みエラー: {e}")
    return {"history": [], "patterns": {}, "lessons": []}


def save_memory(memory: dict):
    """記憶を保存する"""
    try:
        MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(memory, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"記憶保存エラー: {e}")


def update_memory(prices: dict, risk: dict, fear_greed: dict, ai_analysis: dict):
    """本日のデータを記憶に追加"""
    memory = load_memory()
    today = get_today_str()

    entry = {
        "date": today,
        "sentiment": risk.get("sentiment", "不明"),
        "score": risk.get("score", 0),
        "fg_score": fear_greed.get("score"),
        "fg_rating": fear_greed.get("rating_ja", "---"),
        "nikkei": prices.get("^N225", {}).get("latest"),
        "sp500": prices.get("^GSPC", {}).get("latest"),
        "usdjpy": prices.get("USDJPY=X", {}).get("latest"),
        "vix": prices.get("^VIX", {}).get("latest"),
        "ai_judgment": ai_analysis.get("neutral_view", "") if ai_analysis.get("available") else "",
    }

    # 重複防止
    memory["history"] = [h for h in memory["history"] if h.get("date") != today]
    memory["history"].append(entry)

    # 最新90日分だけ保持
    memory["history"] = sorted(memory["history"], key=lambda x: x.get("date",""))[-90:]

    save_memory(memory)
    logger.info(f"記憶更新: {today} (合計{len(memory['history'])}日分)")
    return memory


def analyze_with_memory(prices: dict, risk: dict, fear_greed: dict) -> str:
    """記憶を使ってAIが過去パターンを分析"""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return ""

    memory = load_memory()
    if len(memory["history"]) < 5:
        return "記憶データ蓄積中..."

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))

        # 過去データをテキスト化
        recent = memory["history"][-14:]  # 直近2週間
        history_text = "\n".join(
            f"{h['date']}: 地合い={h['sentiment']}(スコア:{h['score']:+.1f}) "
            # 書式指定(:,.0f)の中に条件式は書けない。値の有無は外側で分ける。
            f"日経={format(h['nikkei'], ',.0f') if h['nikkei'] else '---'} "
            f"F&G={h['fg_score'] or '---'}"
            for h in recent
        )

        current_sentiment = risk.get("sentiment", "不明")
        current_score = risk.get("score", 0)

        prompt = f"""あなたはAI市場アナリストです。過去のデータを記憶しています。

【過去2週間の記録】
{history_text}

【本日】
地合い: {current_sentiment} (スコア: {current_score:+.2f})
日経平均: {prices.get('^N225', {}).get('latest', '---')}
Fear&Greed: {fear_greed.get('score', '---')}

過去のパターンと比較して、以下を150文字以内で分析してください：
・過去と比べて今日の相場はどうか
・繰り返しているパターンはあるか
・注目すべき変化はあるか

推測として述べ、断定表現は使わないでください。"""

        response = model.generate_content(prompt)
        result = response.text[:400]
        logger.info("✅ 記憶ベース分析完了")
        return result

    except Exception as e:
        logger.error(f"記憶分析エラー: {e}")
        return ""
