"""
iPhone通知モジュール（ntfy.sh使用）
ntfy.sh は無料・APIキー不要・iPhoneアプリあり

設定方法：
1. iPhoneのApp Storeで「ntfy」を検索してインストール
2. アプリを開いて「+」→ Subscribe to topic
3. トピック名を入力（例: market-ai-secretary-あなたの名前）
4. .env に NTFY_TOPIC=market-ai-secretary-あなたの名前 を追加

※ トピック名は世界中でユニークにすること（名前や日付を混ぜると安全）
"""
import os
import requests
from dotenv import load_dotenv
from src.utils import setup_logger, get_today_str, get_jst_now

load_dotenv()
logger = setup_logger("notify_iphone")

NTFY_BASE_URL = "https://ntfy.sh"


def _is_configured() -> bool:
    topic = os.getenv("NTFY_TOPIC", "").strip()
    return bool(topic) and topic not in {"ここにトピック名", ""}


def _get_sentiment_emoji(meter: str) -> str:
    return {"RISK_ON": "📈🔥", "RISK_OFF": "📉🛡️", "NEUTRAL": "➡️⚖️"}.get(meter, "➡️")


def _get_fg_emoji(score) -> str:
    if score is None: return "❓"
    if score >= 75:   return "😄"
    elif score >= 56: return "🙂"
    elif score >= 45: return "😐"
    elif score >= 25: return "😟"
    else:             return "😱"


def build_iphone_message(risk: dict, fear_greed: dict,
                          prices: dict, ai_summary: dict,
                          mode: str) -> dict:
    """iPhone通知用のタイトルと本文を生成"""
    today     = get_today_str()
    now       = get_jst_now().strftime("%H:%M JST")
    sentiment = risk.get("sentiment", "不明")
    score     = risk.get("score", 0)
    meter     = risk.get("meter", "NEUTRAL")
    emoji     = _get_sentiment_emoji(meter)

    fg_score  = fear_greed.get("score")
    fg_rating = fear_greed.get("rating_ja", "不明")
    fg_emoji  = _get_fg_emoji(fg_score)

    # 主要指数
    def p(sym):
        d   = prices.get(sym, {})
        v   = d.get("latest")
        chg = d.get("change_pct")
        if v is None: return "N/A"
        sign = "▲" if (chg or 0) >= 0 else "▼"
        return f"{v:,.1f} {sign}{abs(chg):.2f}%" if chg else f"{v:,.1f}"

    # タイトル（通知バナーに表示）
    title = f"{emoji} {today} 市場レポート [{mode.upper()}]"

    # 本文（通知を開いた時に表示）
    lines = [
        f"🎯 地合い: {sentiment}（{score:+.2f}）",
        f"😨 Fear&Greed: {fg_emoji} {fg_score:.0f if fg_score else '?'} {fg_rating}",
        "",
        "📊 主要指数",
        f"  🗾 日経平均: {p('^N225')}",
        f"  🗽 S&P500: {p('^GSPC')}",
        f"  💱 ドル円: {p('USDJPY=X')}",
        f"  📈 米10年金利: {p('^TNX')}",
        f"  😱 VIX: {p('^VIX')}",
        "",
        "⛽ コモディティ",
        f"  🥇 金: {p('GC=F')}",
        f"  🛢️ 原油: {p('CL=F')}",
        f"  ₿ Bitcoin: {p('BTC-USD')}",
    ]

    # AI要約があれば追加
    if ai_summary.get("available") and ai_summary.get("market_comment"):
        comment = ai_summary["market_comment"][:150].replace("\n", " ")
        lines += ["", "🤖 AI市場コメント", f"  {comment}..."]

    lines += [
        "",
        "⚠️ 投資助言ではありません",
        f"🕐 {now}",
    ]

    body = "\n".join(lines)

    # 優先度設定（地合いに応じて）
    if meter == "RISK_OFF" or (fg_score and fg_score < 25):
        priority = "high"
        tags     = "warning,chart_with_downwards_trend"
    elif meter == "RISK_ON":
        priority = "default"
        tags     = "chart_with_upwards_trend"
    else:
        priority = "default"
        tags     = "bar_chart"

    return {
        "title":    title,
        "body":     body,
        "priority": priority,
        "tags":     tags,
    }


def send_iphone_notification(risk: dict, fear_greed: dict,
                              prices: dict, ai_summary: dict,
                              mode: str) -> bool:
    """iPhoneにntfy.sh経由で通知を送信する"""
    if not _is_configured():
        logger.info("ntfy.sh未設定のためスキップ（.envにNTFY_TOPICを追加してください）")
        return False

    topic = os.getenv("NTFY_TOPIC").strip()
    msg   = build_iphone_message(risk, fear_greed, prices, ai_summary, mode)

    try:
        resp = requests.post(
            f"{NTFY_BASE_URL}/{topic}",
            data=msg["body"].encode("utf-8"),
            headers={
                "Title":    msg["title"].encode("utf-8"),
                "Priority": msg["priority"],
                "Tags":     msg["tags"],
            },
            timeout=15,
        )
        resp.raise_for_status()
        logger.info(f"✅ iPhone通知送信成功（ntfy.sh/{topic}）")
        return True
    except Exception as e:
        logger.error(f"iPhone通知送信失敗: {e}")
        return False


def run(risk: dict, fear_greed: dict, prices: dict,
        ai_summary: dict, mode: str) -> bool:
    if not _is_configured():
        logger.info("ntfy.sh未設定。スキップします。")
        return False
    return send_iphone_notification(risk, fear_greed, prices, ai_summary, mode)
