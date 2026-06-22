"""
src/notify_x.py
X（Twitter）への毎朝相場サマリー自動投稿（スレッド形式・高品質版）

必要なGitHub Secrets:
  X_API_KEY            → X Developer Portal の API Key
  X_API_SECRET         → X Developer Portal の API Key Secret
  X_ACCESS_TOKEN       → Access Token
  X_ACCESS_TOKEN_SECRET → Access Token Secret
"""
import os
import traceback
from datetime import date as _date

from src.utils import setup_logger, get_today_str

logger = setup_logger("notify_x")

WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]


def _is_configured() -> bool:
    keys = ["X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET"]
    return all(os.getenv(k, "").strip() for k in keys)


def _mood(score: float) -> tuple[str, str]:
    if   score >= 2:    return "🟢", "強気！上昇ムード"
    elif score >= 0.5:  return "🟢", "やや強気"
    elif score >= -0.5: return "🟡", "中立・様子見"
    elif score >= -2:   return "🟠", "やや弱気・注意"
    else:               return "🔴", "弱気！慎重に"


def _pf(prices: dict, sym: str, unit: str = "", decimals: int = 2) -> str:
    d   = prices.get(sym, {})
    v   = d.get("latest")
    chg = d.get("change_pct")
    if v is None:
        return "---"
    fmt  = f"{{:,.{decimals}f}}"
    vs   = fmt.format(v) + unit
    if chg is None:
        return vs
    arrow = "▲" if chg >= 0 else "▼"
    sign  = "+" if chg >= 0 else ""
    return f"{vs} {arrow}{sign}{chg:.2f}%"


def _fg_label(score) -> str:
    n = int(score or 50)
    if n >= 75: return f"😱 超強欲 ({n})"
    if n >= 55: return f"😤 強欲 ({n})"
    if n >= 45: return f"😐 中立 ({n})"
    if n >= 25: return f"😰 恐怖 ({n})"
    return f"😭 超恐怖 ({n})"


def _vix_label(vix: float) -> str:
    if vix < 15: return "😊 安定"
    if vix < 20: return "😑 やや不安"
    if vix < 30: return "😟 警戒"
    return "😱 危険"


def build_thread(risk: dict, prices: dict, fear_greed: dict,
                 ai_summary: dict = None, news: list = None,
                 report_url: str = "", note_url: str = "") -> list[str]:
    """2ツイートのスレッドを生成して返す"""
    ai_summary = ai_summary or {}
    news       = news or []
    today      = get_today_str()
    weekday    = WEEKDAYS[_date.today().weekday()]
    score      = risk.get("score", 0)
    tl, mood   = _mood(score)
    score_s    = f"+{score:.1f}" if score >= 0 else f"{score:.1f}"
    fg_score   = fear_greed.get("score") or 50
    vix_val    = prices.get("^VIX", {}).get("latest") or 0

    # ━━━━━ ツイート① メイン相場まとめ ━━━━━
    tweet1_lines = [
        f"📊 市場AI秘書｜{today}（{weekday}）",
        f"",
        f"{'━'*18}",
        f"{tl} {mood}",
        f"AIスコア {score_s} ／ VIX {vix_val:.1f} {_vix_label(vix_val)}",
        f"{'━'*18}",
        f"",
        f"🇯🇵 日経   {_pf(prices, '^N225',   '円', 0)}",
        f"🇺🇸 S&P500 {_pf(prices, '^GSPC',   '',  2)}",
        f"🇺🇸 NASDAQ {_pf(prices, '^IXIC',   '',  2)}",
        f"",
        f"💵 ドル円  {_pf(prices, 'USDJPY=X','円', 2)}",
        f"🥇 金      {_pf(prices, 'GC=F',    '$',  0)}",
        f"₿  BTC    {_pf(prices, 'BTC-USD', '$',  0)}",
        f"",
        f"😱 恐怖指数 {_fg_label(fg_score)}",
        f"",
        f"🧵 AI分析・注目ニュースは続きへ↓",
    ]
    tweet1 = "\n".join(tweet1_lines)
    if len(tweet1) > 270:
        tweet1 = tweet1[:267] + "..."

    # ━━━━━ ツイート② AI分析 + ニュース + リンク ━━━━━
    tweet2_lines = ["🤖 AI 3視点分析", ""]

    if ai_summary.get("available"):
        bull = (ai_summary.get("bull_view") or "")[:60].strip()
        bear = (ai_summary.get("bear_view") or "")[:60].strip()
        neut = (ai_summary.get("neutral_view") or "")[:80].strip()
        if bull: tweet2_lines += [f"📈 強気派：{bull}"]
        if bear: tweet2_lines += [f"📉 弱気派：{bear}"]
        if neut: tweet2_lines += [f"⚖️ AI総合：{neut}"]
    else:
        tweet2_lines += ["📊 AI分析データ取得中..."]

    # 重要ニュース最大2件
    top_news = [n for n in news if n.get("importance") == "A"][:2]
    if top_news:
        tweet2_lines += ["", "📰 本日の注目"]
        for n in top_news:
            tweet2_lines.append(f"🔴 {n.get('title','')[:40]}")

    tweet2_lines += [""]
    if report_url:
        tweet2_lines += [f"📊 詳細レポート", report_url]
    if note_url:
        tweet2_lines += [f"📝 AI深掘り（note）", note_url]

    tweet2_lines += ["", "#市場AI秘書 #相場分析 #日経平均 #FX #BTC"]

    tweet2 = "\n".join(tweet2_lines)
    if len(tweet2) > 270:
        tweet2 = tweet2[:267] + "..."

    return [tweet1, tweet2]


def post_thread(tweets: list[str]) -> bool:
    try:
        import tweepy
        client = tweepy.Client(
            consumer_key=os.getenv("X_API_KEY"),
            consumer_secret=os.getenv("X_API_SECRET"),
            access_token=os.getenv("X_ACCESS_TOKEN"),
            access_token_secret=os.getenv("X_ACCESS_TOKEN_SECRET"),
        )
        prev_id = None
        for i, text in enumerate(tweets):
            kwargs = {"text": text}
            if prev_id:
                kwargs["in_reply_to_tweet_id"] = prev_id
            resp    = client.create_tweet(**kwargs)
            prev_id = resp.data["id"]
            logger.info(f"✅ X投稿({i+1}/{len(tweets)}) tweet_id={prev_id}")
        return True
    except Exception:
        logger.error("X投稿エラー")
        logger.debug(traceback.format_exc())
        return False


def run(risk: dict, prices: dict, fear_greed: dict,
        ai_summary: dict = None, news: list = None,
        report_paths: dict = None, note_magazine_url: str = "") -> dict:
    result = {"available": False, "tweets": [], "posted": False}

    if not _is_configured():
        logger.info("X API未設定のためスキップ")
        return result

    report_paths = report_paths or {}
    report_url   = report_paths.get("url", "")
    note_url     = note_magazine_url or os.getenv("NOTE_MAGAZINE_URL", "").strip()

    tweets = build_thread(risk, prices, fear_greed,
                          ai_summary=ai_summary or {},
                          news=news or [],
                          report_url=report_url,
                          note_url=note_url)

    result["available"] = True
    result["tweets"]    = tweets
    result["posted"]    = post_thread(tweets)
    return result
