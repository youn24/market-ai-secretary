"""
Google Gemini AI 分析モジュール
APIキー不要の無料枠で動作
"""
import os
import traceback
from src.utils import setup_logger

logger = setup_logger("ai_gemini")


def run_gemini_analysis(prices: dict, news: list, risk: dict, fear_greed: dict) -> dict:
    """Gemini APIで市場分析を実行"""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        logger.info("GEMINI_API_KEY未設定。スキップします。")
        return {"available": False}

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))

        sentiment = risk.get("sentiment", "不明")
        score     = risk.get("score", 0)
        fg_score  = fear_greed.get("score")
        fg_rating = fear_greed.get("rating_ja", "不明")

        def fmt(sym, unit=""):
            d   = prices.get(sym, {})
            v   = d.get("latest")
            chg = d.get("change_pct")
            if v is None: return "取得失敗"
            s = f"+{chg:.2f}%" if (chg or 0) >= 0 else f"{chg:.2f}%"
            return f"{v:,.2f}{unit}({s})"

        # ニュース上位10件
        sorted_news = sorted(news, key=lambda x: {"A":0,"B":1,"C":2}.get(x.get("importance","C"),2))
        news_text = "\n".join(f"・{item.get('title','')}" for item in sorted_news[:10])

        prompt = f"""あなたはプロの金融アナリストです。以下の市場データを分析してください。

【本日の市場データ】
市場地合い: {sentiment}（スコア: {score:+.2f}）
Fear & Greed: {fg_score}（{fg_rating}）

【主要指数】
日経平均: {fmt('^N225','円')}
S&P500: {fmt('^GSPC')}
NASDAQ: {fmt('^IXIC')}
ダウ: {fmt('^DJI')}
VIX: {fmt('^VIX')}
ドル円: {fmt('USDJPY=X','円')}
米10年金利: {fmt('^TNX','%')}
金: {fmt('GC=F','$')}
原油: {fmt('CL=F','$')}
Bitcoin: {fmt('BTC-USD','$')}

【本日の注目ニュース】
{news_text}

以下の形式で分析してください（各200文字以内）：

【総合判断】
市場全体の状況を簡潔に。

【注目ポイント】
今日最も重要な点を3つ。

【リスク要因】
投資家が注意すべきリスクを2つ。

【今後の見通し】
短期的な市場の方向性（推測として）。

※事実と推測を明確に分け、断定表現は使わないでください。"""

        response = model.generate_content(prompt)
        result_text = response.text

        # セクション分割
        sections = {}
        current = "overall"
        current_lines = []
        for line in result_text.split("\n"):
            if "総合判断" in line:
                if current_lines: sections[current] = "\n".join(current_lines).strip()
                current = "overall"; current_lines = []
            elif "注目ポイント" in line:
                if current_lines: sections[current] = "\n".join(current_lines).strip()
                current = "points"; current_lines = []
            elif "リスク要因" in line:
                if current_lines: sections[current] = "\n".join(current_lines).strip()
                current = "risks"; current_lines = []
            elif "今後の見通し" in line:
                if current_lines: sections[current] = "\n".join(current_lines).strip()
                current = "outlook"; current_lines = []
            else:
                if line.strip():
                    current_lines.append(line)
        if current_lines:
            sections[current] = "\n".join(current_lines).strip()

        logger.info("Gemini AI分析完了")
        return {
            "available": True,
            "model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            "overall_summary": sections.get("overall", result_text[:300]),
            "points": sections.get("points", ""),
            "risks": sections.get("risks", ""),
            "outlook": sections.get("outlook", ""),
            "full_text": result_text,
        }

    except Exception as e:
        logger.error(f"Gemini AI分析エラー: {e}")
        logger.debug(traceback.format_exc())
        return {"available": False, "error": str(e)}
