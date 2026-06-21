"""
経済指標取得・予測・分析モジュール
主要な経済指標を取得してGeminiで分析
"""
import os
import requests
import traceback
from src.utils import setup_logger, get_jst_now

logger = setup_logger("economic_indicators")

# 主要経済指標リスト
INDICATORS = [
    {"name": "米国GDP成長率",      "keyword": "US GDP growth rate"},
    {"name": "米国CPI（インフレ）", "keyword": "US CPI inflation"},
    {"name": "米国雇用統計",        "keyword": "US non-farm payroll"},
    {"name": "FRB政策金利",        "keyword": "Federal Reserve interest rate"},
    {"name": "日銀政策金利",        "keyword": "Bank of Japan interest rate"},
    {"name": "日本CPI",            "keyword": "Japan CPI"},
    {"name": "中国GDP",            "keyword": "China GDP"},
    {"name": "米国ISM製造業",       "keyword": "US ISM manufacturing"},
]


def fetch_economic_news() -> list:
    """経済指標関連ニュースをRSSで取得"""
    import feedparser
    results = []
    keywords = [
        "GDP 経済指標", "CPI インフレ", "雇用統計", "FRB 利上げ",
        "日銀 金融政策", "政策金利", "PMI 景気", "貿易収支"
    ]
    for kw in keywords:
        try:
            url = f"https://news.google.com/rss/search?q={requests.utils.quote(kw)}&hl=ja&gl=JP&ceid=JP:ja"
            feed = feedparser.parse(url)
            for entry in feed.entries[:2]:
                results.append({
                    "title": entry.get("title",""),
                    "source": "Google News",
                    "category": "経済指標",
                    "importance": "A",
                    "keyword": kw,
                })
        except Exception:
            pass
    logger.info(f"経済指標ニュース取得: {len(results)}件")
    return results


def analyze_indicators_with_gemini(prices: dict, econ_news: list) -> dict:
    """Geminiで経済指標を分析・予測"""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return {"available": False}

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))

        news_text = "\n".join(f"・{n['title']}" for n in econ_news[:10])

        def fmt(sym, unit=""):
            d = prices.get(sym, {})
            v = d.get("latest")
            chg = d.get("change_pct")
            if v is None: return "---"
            s = f"+{chg:.2f}%" if (chg or 0) >= 0 else f"{chg:.2f}%"
            return f"{v:,.2f}{unit}({s})"

        prompt = f"""あなたはマクロ経済の専門家です。
以下の市場データと経済指標ニュースを分析してください。

【市場データ】
米10年金利: {fmt('^TNX','%')}
ドル円: {fmt('USDJPY=X','円')}
S&P500: {fmt('^GSPC')}
VIX: {fmt('^VIX')}
金: {fmt('GC=F','$')}

【経済指標ニュース】
{news_text}

以下を簡潔に分析してください：

【現状分析】（100文字以内）
現在の経済状況を一言で。

【注目指標】（100文字以内）
今週・今月注目すべき経済指標は何か。

【市場への影響予測】（150文字以内）
経済指標が株・為替・金利に与える影響の見通し（推測として）。

【投資家へのヒント】（100文字以内）
経済指標を踏まえた注意点（断定表現禁止）。"""

        response = model.generate_content(prompt)
        result = response.text

        # セクション分割
        sections = {}
        current = "all"
        current_lines = []
        for line in result.split("\n"):
            if "現状分析" in line:
                if current_lines: sections[current] = "\n".join(current_lines).strip()
                current = "status"; current_lines = []
            elif "注目指標" in line:
                if current_lines: sections[current] = "\n".join(current_lines).strip()
                current = "focus"; current_lines = []
            elif "市場への影響" in line:
                if current_lines: sections[current] = "\n".join(current_lines).strip()
                current = "impact"; current_lines = []
            elif "投資家へのヒント" in line:
                if current_lines: sections[current] = "\n".join(current_lines).strip()
                current = "hint"; current_lines = []
            else:
                if line.strip():
                    current_lines.append(line)
        if current_lines:
            sections[current] = "\n".join(current_lines).strip()

        logger.info("✅ 経済指標Gemini分析完了")
        return {
            "available": True,
            "status":    sections.get("status", ""),
            "focus":     sections.get("focus", ""),
            "impact":    sections.get("impact", ""),
            "hint":      sections.get("hint", ""),
            "full_text": result,
            "news_count": len(econ_news),
        }

    except Exception as e:
        logger.error(f"経済指標分析エラー: {e}")
        logger.debug(traceback.format_exc())
        return {"available": False}


def run(prices: dict) -> dict:
    """経済指標モジュール実行"""
    logger.info("=== 経済指標分析開始 ===")
    econ_news = fetch_economic_news()
    result = analyze_indicators_with_gemini(prices, econ_news)
    result["news"] = econ_news
    return result
