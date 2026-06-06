"""
ニュース取得モジュール
Google News RSS を feedparser で取得（APIキー不要）
"""
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import feedparser
import yaml

from src.utils import BASE_DIR, JST, get_jst_now, get_today_str, get_dirs, setup_logger

logger = setup_logger("fetch_news")


def load_news_config() -> dict:
    with open(BASE_DIR / "config" / "news_sources.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _parse_entry(entry: dict, keyword: str, label: str, importance: str) -> dict:
    """feedparser のエントリを統一フォーマットに変換する。"""
    title = entry.get("title", "タイトル不明")
    link = entry.get("link", "")
    source = ""
    if hasattr(entry, "source") and entry.source:
        source = entry.source.get("title", "")
    published = entry.get("published", "")
    published_jst = ""
    try:
        t = entry.get("published_parsed")
        if t:
            dt_utc = datetime(*t[:6], tzinfo=datetime.now(JST).tzinfo.__class__(timedelta(0)))
            dt_jst = dt_utc.astimezone(JST)
            published_jst = dt_jst.strftime("%Y-%m-%d %H:%M JST")
    except Exception:
        published_jst = published

    return {
        "keyword": keyword,
        "label": label,
        "importance": importance,
        "title": title,
        "url": link,
        "source": source,
        "published_jst": published_jst,
        "fetch_time": get_jst_now().isoformat(),
    }


def fetch_google_news(keyword: str, label: str, importance: str,
                      max_items: int = 5) -> list[dict]:
    """Google News RSS から指定キーワードのニュースを取得する。"""
    encoded = quote(keyword)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=ja&gl=JP&ceid=JP:ja"
    try:
        feed = feedparser.parse(url)
        if not feed.entries:
            logger.warning(f"ニュースなし [{keyword}]: エントリ0件")
            return []
        items = []
        for entry in feed.entries[:max_items]:
            items.append(_parse_entry(entry, keyword, label, importance))
        logger.info(f"[OK] ニュース取得 [{keyword}]: {len(items)}件")
        return items
    except Exception as e:
        logger.error(f"[FAIL] ニュース取得 [{keyword}]: {e}")
        return []


def fetch_all_news() -> list[dict]:
    cfg = load_news_config()
    keywords = cfg.get("google_news_keywords", [])
    max_items = cfg.get("max_items_per_keyword", 5)

    all_news = []
    for kw_cfg in keywords:
        items = fetch_google_news(
            keyword=kw_cfg["keyword"],
            label=kw_cfg["label"],
            importance=kw_cfg["importance"],
            max_items=max_items,
        )
        all_news.extend(items)
        time.sleep(1.0)  # Google RSS への過負荷防止

    return all_news


def save_news(news: list[dict]) -> Path:
    dirs = get_dirs()
    today = get_today_str()
    path = dirs["data_news"] / f"{today}_news.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(news, f, ensure_ascii=False, indent=2)
    logger.info(f"ニュース保存: {path} ({len(news)}件)")
    return path


def run() -> list[dict]:
    logger.info("=== ニュース取得開始 ===")
    news = fetch_all_news()
    save_news(news)
    logger.info(f"=== ニュース取得完了: {len(news)}件 ===")
    return news


if __name__ == "__main__":
    run()
