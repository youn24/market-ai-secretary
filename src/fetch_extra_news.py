"""
追加ニュース取得モジュール
取得元：NHK / Yahoo Finance JP / 東洋経済 / MarketWatch / FXStreet /
        Investing.com / Yahoo Finance EN
APIキー不要
"""
import json
import time
from datetime import datetime, timedelta, timezone

import feedparser
import requests

from src.utils import get_jst_now, get_today_str, get_dirs, setup_logger

logger = setup_logger("fetch_extra_news")
JST = timezone(timedelta(hours=9))

RSS_SOURCES = [
    # ─ 日本語：公共・政府機関 ─────────────────────────────
    {
        "id":       "nhk_economy",
        "name":     "NHK 経済",
        "url":      "https://www3.nhk.or.jp/rss/news/cat6.xml",
        "lang":     "ja",
        "importance": "A",
        "max":      6,
    },
    {
        "id":       "nhk_top",
        "name":     "NHK トップ",
        "url":      "https://www3.nhk.or.jp/rss/news/cat0.xml",
        "lang":     "ja",
        "importance": "A",
        "max":      5,
    },
    # ─ 日本語：金融・投資専門 ────────────────────────────
    {
        "id":       "yahoo_finance_jp",
        "name":     "Yahoo! ファイナンス",
        "url":      "https://news.yahoo.co.jp/rss/categories/business.xml",
        "lang":     "ja",
        "importance": "B",
        "max":      6,
    },
    {
        "id":       "toyokeizai",
        "name":     "東洋経済",
        "url":      "https://toyokeizai.net/list/feed/rss",
        "lang":     "ja",
        "importance": "B",
        "max":      5,
    },
    # ─ 英語：金融専門 ────────────────────────────────────
    {
        "id":       "marketwatch",
        "name":     "MarketWatch",
        "url":      "https://feeds.marketwatch.com/marketwatch/topstories/",
        "lang":     "en",
        "importance": "A",
        "max":      5,
    },
    {
        "id":       "fxstreet",
        "name":     "FXStreet（FX専門）",
        "url":      "https://www.fxstreet.com/rss",
        "lang":     "en",
        "importance": "A",
        "max":      5,
    },
    {
        "id":       "investing_com",
        "name":     "Investing.com",
        "url":      "https://www.investing.com/rss/news.rss",
        "lang":     "en",
        "importance": "B",
        "max":      5,
    },
    {
        "id":       "yahoo_finance_en",
        "name":     "Yahoo Finance",
        "url":      "https://finance.yahoo.com/rss/",
        "lang":     "en",
        "importance": "B",
        "max":      5,
    },
]

# Google News RSS経由で取得する専門情報源
# （直接RSSが公開されていないサイトはGoogle News経由）
GOOGLE_NEWS_SITE_SOURCES = [
    # ─ 日銀・政府 ──────────────────────────────────────
    {
        "id":       "boj",
        "name":     "日銀公式",
        "keyword":  "site:boj.or.jp",
        "label":    "日銀動向",
        "importance": "A",
        "max":      5,
    },
    {
        "id":       "kantei",
        "name":     "首相官邸",
        "keyword":  "site:kantei.go.jp 経済 OR 財政",
        "label":    "政府動向",
        "importance": "A",
        "max":      4,
    },
    {
        "id":       "mof",
        "name":     "財務省",
        "keyword":  "site:mof.go.jp",
        "label":    "財務省動向",
        "importance": "A",
        "max":      4,
    },
    # ─ 投資・FX専門サイト ───────────────────────────────
    {
        "id":       "traders_web",
        "name":     "トレーダーズウェブ",
        "keyword":  "site:traders.co.jp",
        "label":    "トレーダーズウェブ",
        "importance": "B",
        "max":      5,
    },
    {
        "id":       "traders_fx",
        "name":     "トレーダーズウェブFX",
        "keyword":  "site:traders.co.jp FX 為替",
        "label":    "トレーダーズウェブFX",
        "importance": "B",
        "max":      4,
    },
    {
        "id":       "minkabu",
        "name":     "みんかぶ",
        "keyword":  "site:minkabu.jp 株",
        "label":    "みんかぶ株",
        "importance": "B",
        "max":      5,
    },
    {
        "id":       "minkabu_fx",
        "name":     "みんかぶFX",
        "keyword":  "site:fx.minkabu.jp",
        "label":    "みんかぶFX",
        "importance": "B",
        "max":      4,
    },
    {
        "id":       "nikkei225jp",
        "name":     "日経225専門",
        "keyword":  "site:nikkei225jp.com",
        "label":    "日経225分析",
        "importance": "B",
        "max":      4,
    },
    {
        "id":       "oanda",
        "name":     "OANDA為替",
        "keyword":  "OANDA 為替 レート",
        "label":    "OANDA為替情報",
        "importance": "B",
        "max":      4,
    },
    # ─ 企業信用・倒産 ────────────────────────────────────
    {
        "id":       "tdb",
        "name":     "帝国データバンク",
        "keyword":  "帝国データバンク 倒産 OR 業績",
        "label":    "帝国DB企業信用",
        "importance": "B",
        "max":      4,
    },
    # ─ FedWatch（米利上げ確率） ──────────────────────────
    {
        "id":       "fedwatch",
        "name":     "FedWatch利上げ確率",
        "keyword":  "FedWatch 利上げ 確率 FOMC",
        "label":    "FedWatch",
        "importance": "A",
        "max":      4,
    },
    # ─ PayPay証券・ペイペイ証券 ──────────────────────────
    {
        "id":       "paypay_sec",
        "name":     "PayPay証券",
        "keyword":  "PayPay証券 株 投資",
        "label":    "PayPay証券情報",
        "importance": "C",
        "max":      3,
    },
]


def _parse_time(entry) -> str:
    try:
        t = entry.get("published_parsed")
        if t:
            dt = datetime(*t[:6], tzinfo=timezone.utc).astimezone(JST)
            return dt.strftime("%Y-%m-%d %H:%M JST")
    except Exception:
        pass
    return entry.get("published", "")


def fetch_rss_source(src: dict) -> list[dict]:
    try:
        feed = feedparser.parse(src["url"])
        items = []
        for entry in feed.entries[:src["max"]]:
            items.append({
                "source_id":   src["id"],
                "source_name": src["name"],
                "lang":        src["lang"],
                "importance":  src["importance"],
                "title":       entry.get("title", ""),
                "url":         entry.get("link", ""),
                "summary":     entry.get("summary", "")[:200],
                "published_jst": _parse_time(entry),
                "fetch_time":  get_jst_now().isoformat(),
            })
        logger.info(f"[OK] {src['name']}: {len(items)}件")
        return items
    except Exception as e:
        logger.error(f"[FAIL] {src['name']}: {e}")
        return []


def fetch_google_news_site(src: dict) -> list[dict]:
    """Google News RSS 経由でサイト指定・キーワード検索取得"""
    from urllib.parse import quote
    keyword = src["keyword"]
    url = f"https://news.google.com/rss/search?q={quote(keyword)}&hl=ja&gl=JP&ceid=JP:ja"
    try:
        feed  = feedparser.parse(url)
        items = []
        for entry in feed.entries[:src["max"]]:
            items.append({
                "source_id":     src["id"],
                "source_name":   src["name"],
                "label":         src["label"],
                "lang":          "ja",
                "importance":    src["importance"],
                "title":         entry.get("title", ""),
                "url":           entry.get("link", ""),
                "summary":       entry.get("summary", "")[:200],
                "published_jst": _parse_time(entry),
                "fetch_time":    get_jst_now().isoformat(),
            })
        logger.info(f"[OK] {src['name']}: {len(items)}件")
        return items
    except Exception as e:
        logger.error(f"[FAIL] {src['name']}: {e}")
        return []


def fetch_all_extra_news() -> list[dict]:
    all_news = []
    # 通常RSS
    for src in RSS_SOURCES:
        all_news.extend(fetch_rss_source(src))
        time.sleep(0.8)
    # Google News経由（サイト指定・キーワード）
    for src in GOOGLE_NEWS_SITE_SOURCES:
        all_news.extend(fetch_google_news_site(src))
        time.sleep(1.0)
    return all_news


# ─── Polymarket ───────────────────────────────────────────────

POLY_KEYWORDS = [
    "fed", "rate", "recession", "inflation", "interest",
    "japan", "dollar", "yen", "bitcoin", "btc", "crypto",
    "stock", "market", "oil", "gold", "gdp", "economy",
    "tariff", "trade", "election", "bank", "nasdaq", "s&p",
]


def fetch_polymarket(limit: int = 100) -> list[dict]:
    """Polymarket の金融・経済関連マーケットを取得する（APIキー不要）"""
    url = "https://gamma-api.polymarket.com/markets"
    try:
        resp = requests.get(url,
                            params={"limit": limit, "active": "true"},
                            timeout=15)
        resp.raise_for_status()
        data = resp.json()

        finance = []
        for m in data:
            q = m.get("question", "").lower()
            if not any(k in q for k in POLY_KEYWORDS):
                continue

            # 確率を取得
            prices = m.get("outcomePrices", "")
            try:
                import json as _json
                p = _json.loads(prices) if isinstance(prices, str) else prices
                yes_prob = round(float(p[0]) * 100, 1) if p else None
            except Exception:
                yes_prob = None

            finance.append({
                "question":    m.get("question", ""),
                "yes_prob":    yes_prob,
                "no_prob":     round(100 - yes_prob, 1) if yes_prob else None,
                "volume":      m.get("volume"),
                "end_date":    m.get("endDate", ""),
                "url":         f"https://polymarket.com/event/{m.get('slug','')}",
                "fetch_time":  get_jst_now().isoformat(),
            })

        logger.info(f"[OK] Polymarket: {len(finance)}件（金融・経済関連）")
        return finance

    except Exception as e:
        logger.error(f"[FAIL] Polymarket: {e}")
        return []


def save_extra_news(news: list[dict], polymarket: list[dict]):
    dirs  = get_dirs()
    today = get_today_str()

    path_news = dirs["data_news"] / f"{today}_extra_news.json"
    with open(path_news, "w", encoding="utf-8") as f:
        json.dump(news, f, ensure_ascii=False, indent=2)

    path_poly = dirs["data_news"] / f"{today}_polymarket.json"
    with open(path_poly, "w", encoding="utf-8") as f:
        json.dump(polymarket, f, ensure_ascii=False, indent=2)

    logger.info(f"追加ニュース保存: {len(news)}件 / Polymarket: {len(polymarket)}件")


def run() -> tuple[list[dict], list[dict]]:
    logger.info("=== 追加ニュース・Polymarket 取得開始 ===")
    extra_news  = fetch_all_extra_news()
    polymarket  = fetch_polymarket()
    save_extra_news(extra_news, polymarket)
    logger.info(f"=== 完了: ニュース{len(extra_news)}件 / Polymarket{len(polymarket)}件 ===")
    return extra_news, polymarket


if __name__ == "__main__":
    run()
