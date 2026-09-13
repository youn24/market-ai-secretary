"""
Redditソーシャル感情分析（L5f）
r/wallstreetbets・r/investing・r/stocks のホット投稿から
個人投資家の熱量・楽観/悲観ムードを数値化する。
APIキー不要・公開JSONエンドポイントを使用。
"""
import ssl
import json
import logging
import urllib.request
import re
from collections import Counter
from src.utils import get_jst_now

logger = logging.getLogger(__name__)

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE

SUBREDDITS = [
    ("wallstreetbets", "投機色が強い個人投資家コミュニティ"),
    ("investing", "一般投資家コミュニティ"),
    ("stocks", "株式投資全般"),
]

# 楽観/悲観キーワード（タイトルを解析）
BULL_WORDS = {
    "bull": 2, "bullish": 2, "moon": 3, "ath": 2, "all time high": 2,
    "buy": 1, "long": 1, "calls": 2, "yolo": 2, "pump": 1, "rocket": 2,
    "breakout": 2, "surge": 1, "rally": 1, "green": 1, "up": 1,
    "beat": 1, "record": 1, "boom": 2, "squeeze": 2, "gains": 1,
}
BEAR_WORDS = {
    "bear": 2, "bearish": 2, "crash": 3, "dump": 2, "short": 1,
    "puts": 2, "recession": 2, "sell": 1, "bottom": 1, "red": 1,
    "down": 1, "miss": 1, "fear": 1, "fud": 2, "bubble": 2,
    "collapse": 3, "drop": 1, "risk": 1, "correction": 1, "panic": 2,
}

# 注目ティッカーを検出するパターン（$NVDA, $AAPL, NVDA, etc.）
TICKER_RE = re.compile(r'\$([A-Z]{2,5})\b|(?<!\w)([A-Z]{2,5})(?!\w)')
COMMON_WORDS = {
    "AI", "IS", "US", "OR", "BE", "DO", "AT", "BY", "ON", "IF", "NO", "SO",
    "WE", "ME", "GO", "IT", "AN", "AM", "TO", "UP", "IN", "OF", "MY",
    "THE", "AND", "FOR", "NOT", "BUT", "ALL", "CAN", "GET", "HAS",
    "DID", "USE", "NEW", "NOW", "OUT", "WHO", "HOW", "ONE", "TWO", "SEC",
    "FED", "IMF", "GDP", "CPI", "IPO", "ETF", "WSB", "YOLO", "ATH",
}


def _get_reddit(subreddit: str, sort: str = "hot", limit: int = 25) -> list:
    """Reddit公開JSONエンドポイントから投稿を取得"""
    url = f"https://www.reddit.com/r/{subreddit}/{sort}.json?limit={limit}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "MarketAI/1.0 (investment analysis bot)"}
    )
    try:
        resp = urllib.request.urlopen(req, context=_ctx, timeout=15)
        data = json.loads(resp.read())
        posts = data.get("data", {}).get("children", [])
        return [p["data"] for p in posts if p.get("data")]
    except Exception as e:
        logger.warning(f"  r/{subreddit} 取得失敗: {e}")
        return []


def _analyze_posts(posts: list) -> dict:
    """投稿リストのセンチメントを分析"""
    bull_score = 0
    bear_score = 0
    tickers = []
    post_summaries = []

    for post in posts:
        title = (post.get("title", "") + " " + post.get("selftext", "")[:100]).lower()
        score = post.get("score", 0)  # アップボート数
        weight = max(1, min(score, 10000)) / 1000  # 重み（最大10倍）

        # 楽観・悲観キーワードスコア計算
        for word, w in BULL_WORDS.items():
            if word in title:
                bull_score += w * (1 + weight * 0.1)
        for word, w in BEAR_WORDS.items():
            if word in title:
                bear_score += w * (1 + weight * 0.1)

        # ティッカー検出
        for m in TICKER_RE.finditer(post.get("title", "")):
            ticker = (m.group(1) or m.group(2) or "").upper()
            if ticker and ticker not in COMMON_WORDS and len(ticker) >= 2:
                tickers.append(ticker)

        # 高スコア投稿のサマリー（スコア100以上のみ）
        if score >= 100:
            post_summaries.append({
                "title": post.get("title", "")[:80],
                "score": score,
                "comments": post.get("num_comments", 0),
            })

    # センチメントスコア -100〜+100
    total = bull_score + bear_score
    if total > 0:
        sentiment_score = round((bull_score - bear_score) / total * 100)
    else:
        sentiment_score = 0

    return {
        "bull_score": round(bull_score, 1),
        "bear_score": round(bear_score, 1),
        "sentiment_score": sentiment_score,
        "tickers": tickers,
        "top_posts": sorted(post_summaries, key=lambda x: x["score"], reverse=True)[:3],
        "post_count": len(posts),
    }


def run() -> dict:
    """Reddit全サブレディットのセンチメントを集計"""
    logger.info("--- Redditソーシャル感情分析 ---")
    result = {"available": False}

    all_posts = []
    sub_results = []

    for sub, desc in SUBREDDITS:
        posts = _get_reddit(sub, sort="hot", limit=25)
        if not posts:
            logger.warning(f"  r/{sub}: 取得失敗")
            continue
        analysis = _analyze_posts(posts)
        analysis["subreddit"] = sub
        analysis["description"] = desc
        sub_results.append(analysis)
        all_posts.extend(posts)
        logger.info(
            f"  r/{sub}: {len(posts)}件 "
            f"強気{analysis['bull_score']:.0f}/弱気{analysis['bear_score']:.0f}"
        )

    if not sub_results:
        logger.warning("  全サブレディット取得失敗")
        return result

    # 総合センチメント
    combined = _analyze_posts(all_posts)
    total_sentiment = combined["sentiment_score"]

    if total_sentiment >= 30:
        signal = "🐂 強気ムード（個人投資家は楽観）"
        signal_id = "bull"
    elif total_sentiment >= 10:
        signal = "😊 やや楽観"
        signal_id = "slightly_bull"
    elif total_sentiment >= -10:
        signal = "😐 中立・様子見"
        signal_id = "neutral"
    elif total_sentiment >= -30:
        signal = "😰 やや悲観"
        signal_id = "slightly_bear"
    else:
        signal = "🐻 弱気ムード（個人投資家は悲観）"
        signal_id = "bear"

    # 注目ティッカーランキング
    all_tickers = combined["tickers"]
    ticker_ranking = Counter(all_tickers).most_common(5)

    result = {
        "available": True,
        "sentiment_score": total_sentiment,
        "signal": signal,
        "signal_id": signal_id,
        "subreddit_results": sub_results,
        "top_tickers": ticker_ranking,
        "top_posts": combined["top_posts"],
        "total_posts_analyzed": len(all_posts),
        "fetched_at": get_jst_now().strftime("%Y-%m-%d %H:%M"),
    }

    logger.info(f"✅ Reddit分析: {signal} (スコア:{total_sentiment})")
    return result


def format_telegram(data: dict) -> str:
    if not data.get("available"):
        return ""
    score = data.get("sentiment_score", 0)
    signal = data.get("signal", "")
    bar_val = (score + 100) // 20  # 0〜10
    bar = "█" * bar_val + "░" * (10 - bar_val)

    lines = [
        "🤖 *Reddit個人投資家センチメント*",
        "━━━━━━━━━━━━━━━",
        f"{signal}",
        f"`{bar}` {score:+d}",
        f"  -100=超悲観 ← 0=中立 → +100=超楽観",
        "",
    ]

    top_tickers = data.get("top_tickers", [])
    if top_tickers:
        lines.append("💬 最も話題の銘柄:")
        for ticker, count in top_tickers[:5]:
            lines.append(f"  {ticker}: {count}件")
        lines.append("")

    top_posts = data.get("top_posts", [])
    if top_posts:
        lines.append("🔥 バズり投稿:")
        for p in top_posts[:2]:
            lines.append(f"  ({p['score']:,}↑) {p['title'][:50]}")

    lines.append(f"\n  📊 {data.get('total_posts_analyzed',0)}件を分析")
    return "\n".join(lines)
