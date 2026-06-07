"""
YouTube動画要約モジュール
日銀・FRB・経済ニュース動画をGeminiで要約
"""
import os
import requests
import traceback
import feedparser
from src.utils import setup_logger

logger = setup_logger("youtube_summary")

# 注目チャンネル・キーワード
YOUTUBE_KEYWORDS = [
    "日銀 総裁 会見",
    "FRB 議長 会見 Federal Reserve",
    "日経平均 相場解説",
    "米国株 市場解説",
    "為替 ドル円 解説",
    "トランプ 経済政策",
    "経済指標 解説",
]


def fetch_youtube_videos() -> list:
    """YouTubeの動画情報をRSSで取得"""
    videos = []
    for keyword in YOUTUBE_KEYWORDS:
        try:
            url = f"https://www.youtube.com/results?search_query={requests.utils.quote(keyword)}&sp=EgIIAQ%3D%3D"
            # YouTube RSS（直近動画）
            rss_url = f"https://news.google.com/rss/search?q={requests.utils.quote(keyword + ' site:youtube.com')}&hl=ja"
            feed = feedparser.parse(rss_url)
            for entry in feed.entries[:2]:
                title = entry.get("title", "")
                link  = entry.get("link", "")
                if "youtube" in link.lower() or "youtu.be" in link.lower():
                    videos.append({
                        "title": title,
                        "url": link,
                        "keyword": keyword,
                    })
        except Exception:
            pass

    logger.info(f"YouTube動画取得: {len(videos)}件")
    return videos


def summarize_videos_with_gemini(videos: list, news: list) -> dict:
    """Geminiで動画タイトルから内容を推測・要約"""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or not videos:
        return {"available": False}

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")

        video_list = "\n".join(f"・{v['title']} ({v['keyword']})" for v in videos[:10])

        # 関連ニュースも追加
        related_news = [n for n in news if any(
            kw in n.get("title","") for kw in ["日銀","FRB","金融政策","利上げ","利下げ"]
        )]
        news_text = "\n".join(f"・{n['title']}" for n in related_news[:5])

        prompt = f"""あなたは金融メディアのアナリストです。
以下の動画タイトルと関連ニュースから、重要な情報を分析してください。

【本日の注目動画】
{video_list}

【関連ニュース】
{news_text if news_text else "なし"}

以下を分析してください（各100文字以内）：

【動画のポイント】
今日の動画で最も重要なテーマは何か。

【市場への示唆】
これらの情報が相場に与える影響（推測として）。

断定表現は使わず、推測として述べてください。"""

        response = model.generate_content(prompt)
        result = response.text

        # 分割
        sections = {}
        current = "all"
        lines = []
        for line in result.split("\n"):
            if "動画のポイント" in line:
                if lines: sections[current] = "\n".join(lines).strip()
                current = "points"; lines = []
            elif "市場への示唆" in line:
                if lines: sections[current] = "\n".join(lines).strip()
                current = "impact"; lines = []
            else:
                if line.strip(): lines.append(line)
        if lines: sections[current] = "\n".join(lines).strip()

        logger.info("✅ YouTube動画分析完了")
        return {
            "available": True,
            "videos": videos[:5],
            "points": sections.get("points", ""),
            "impact": sections.get("impact", ""),
            "full_text": result,
        }

    except Exception as e:
        logger.error(f"YouTube分析エラー: {e}")
        return {"available": False}


def run(news: list = None) -> dict:
    """YouTube要約モジュール実行"""
    logger.info("=== YouTube動画分析開始 ===")
    videos = fetch_youtube_videos()
    result = summarize_videos_with_gemini(videos, news or [])
    return result
