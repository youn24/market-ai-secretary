"""
src/notify_x.py
X（Twitter）への毎朝相場サマリー自動投稿モジュール

必要なGitHub Secrets:
  X_API_KEY            → X Developer Portal の API Key
  X_API_SECRET         → X Developer Portal の API Key Secret
  X_ACCESS_TOKEN       → Access Token
  X_ACCESS_TOKEN_SECRET → Access Token Secret
"""
import os
import traceback

from src.utils import setup_logger, get_today_str

logger = setup_logger("notify_x")


def _is_configured() -> bool:
    keys = ["X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET"]
    return all(os.getenv(k, "").strip() for k in keys)


def _mood_label(score: float) -> str:
    if   score >= 2:    return "🟢強気"
    elif score >= 0.5:  return "🟢やや強気"
    elif score >= -0.5: return "🟡中立"
    elif score >= -2:   return "🟠やや弱気"
    else:               return "🔴弱気"


def build_tweet(risk: dict, prices: dict, fear_greed: dict,
                report_url: str = "", note_url: str = "") -> str:
    today    = get_today_str()
    score    = risk.get("score", 0)
    mood     = _mood_label(score)
    score_s  = f"+{score:.1f}" if score >= 0 else f"{score:.1f}"

    def _p(sym, unit=""):
        d   = prices.get(sym, {})
        v   = d.get("latest")
        chg = d.get("change_pct")
        if v is None:
            return "---"
        arrow = "▲" if (chg or 0) >= 0 else "▼"
        chg_s = f"{abs(chg):.2f}%" if chg is not None else ""
        return f"{v:,.0f}{unit} {arrow}{chg_s}"

    fg = fear_greed.get("score") or 50
    fg_label = (
        "超強欲😱" if fg >= 75 else
        "強欲😤"   if fg >= 55 else
        "中立😐"   if fg >= 45 else
        "恐怖😰"   if fg >= 25 else
        "超恐怖😭"
    )

    nikkei  = _p("^N225", "円")
    usdjpy  = _p("USDJPY=X", "円")
    sp500   = _p("^GSPC")
    vix_val = prices.get("^VIX", {}).get("latest") or 0

    lines = [
        f"📊 {today} 朝の相場まとめ",
        f"",
        f"{mood}（AIスコア {score_s}）",
        f"",
        f"🇯🇵日経 {nikkei}",
        f"🇺🇸S&P {sp500}",
        f"💵ドル円 {usdjpy}",
        f"⚡VIX {vix_val:.1f}",
        f"😱恐怖指数 {fg}（{fg_label}）",
    ]

    if report_url:
        lines += ["", f"📈詳細レポート", report_url]

    if note_url:
        lines += ["", f"📝AI深掘り分析（note）", note_url]

    lines += ["", "#市場AI秘書 #相場 #FX #日経平均"]

    tweet = "\n".join(lines)
    # X の文字数制限 280字（URLは23字換算）に収まるよう末尾トリム
    if len(tweet) > 270:
        tweet = tweet[:267] + "..."
    return tweet


def post_tweet(text: str) -> bool:
    try:
        import tweepy
        client = tweepy.Client(
            consumer_key=os.getenv("X_API_KEY"),
            consumer_secret=os.getenv("X_API_SECRET"),
            access_token=os.getenv("X_ACCESS_TOKEN"),
            access_token_secret=os.getenv("X_ACCESS_TOKEN_SECRET"),
        )
        resp = client.create_tweet(text=text)
        tweet_id = resp.data["id"]
        logger.info(f"✅ X投稿成功: tweet_id={tweet_id}")
        return True
    except Exception:
        logger.error("X投稿エラー")
        logger.debug(traceback.format_exc())
        return False


def run(risk: dict, prices: dict, fear_greed: dict,
        report_paths: dict = None, note_magazine_url: str = "") -> dict:
    result = {"available": False, "tweet": "", "posted": False}

    if not _is_configured():
        logger.info("X API未設定のためスキップ")
        return result

    report_paths = report_paths or {}
    report_url   = report_paths.get("url", "")
    note_url     = note_magazine_url or os.getenv("NOTE_MAGAZINE_URL", "").strip()

    tweet = build_tweet(risk, prices, fear_greed, report_url, note_url)
    result["available"] = True
    result["tweet"]     = tweet

    result["posted"] = post_tweet(tweet)
    return result
