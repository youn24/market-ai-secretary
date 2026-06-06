"""
Telegram通知モジュール
.envに TELEGRAM_BOT_TOKEN と TELEGRAM_CHAT_ID がない場合はスキップ
"""
import os
import traceback

import requests
from dotenv import load_dotenv

from src.utils import setup_logger, get_today_str

logger = setup_logger("notify_telegram")

load_dotenv()


def _is_configured() -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    placeholders = {"ここにBotFatherのトークン", "ここにあなたのChat ID", ""}
    if token in placeholders or chat_id in placeholders:
        return False
    return True


def _fmt_price(prices: dict, sym: str, unit: str = "") -> str:
    d = prices.get(sym, {})
    v = d.get("latest")
    chg = d.get("change_pct")
    if v is None:
        return "取得中..."
    arrow = "🔺" if (chg or 0) >= 0 else "🔻"
    chg_str = f"{chg:+.2f}%" if chg is not None else ""
    return f"{arrow} {v:,.2f}{unit} ({chg_str})"


def build_three_messages(risk: dict, analysis: dict, mode: str,
                         prices: dict = None, news: list = None,
                         fear_greed: dict = None, ai_summary: dict = None) -> list:
    """Telegramに送る3通のメッセージを生成"""
    today = get_today_str()
    prices = prices or {}
    news = news or []
    fear_greed = fear_greed or {}
    ai_summary = ai_summary or {}

    sentiment = risk.get("sentiment", "不明")
    score = risk.get("score", 0)
    signals = risk.get("signals", [])
    facts = analysis.get("facts", [])
    hypotheses = analysis.get("hypotheses", [])

    # 地合いアイコン
    if score >= 5:
        mood = "🟢 強気"
    elif score >= 2:
        mood = "🟡 やや強気"
    elif score >= -2:
        mood = "⚪ 中立"
    elif score >= -5:
        mood = "🟠 やや弱気"
    else:
        mood = "🔴 弱気"

    fg_score = fear_greed.get("score")
    fg_rating = fear_greed.get("rating_ja", "不明")
    if fg_score:
        if fg_score >= 75:   fg_icon = "😱 極度の強欲"
        elif fg_score >= 55: fg_icon = "😄 強欲"
        elif fg_score >= 45: fg_icon = "😐 中立"
        elif fg_score >= 25: fg_icon = "😟 恐怖"
        else:                fg_icon = "😨 極度の恐怖"
        fg_str = f"{fg_icon} ({fg_score:.0f}点)"
    else:
        fg_str = "取得中..."

    # ===== 通知①: ニュース＆市場概況 =====
    sorted_news = sorted(news, key=lambda x: {"A": 0, "B": 1, "C": 2}.get(x.get("importance", "C"), 2))
    imp_icons = {"A": "🔴", "B": "🟡", "C": "⚪"}

    news_lines = []
    for item in sorted_news[:8]:
        title = item.get("title", "")[:40]
        imp = item.get("importance", "C")
        icon = imp_icons.get(imp, "⚪")
        news_lines.append(f"{icon} {title}")

    msg1 = "\n".join([
        f"📰 *本日の注目ニュース* [{today}]",
        "━━━━━━━━━━━━━━━",
        *news_lines,
        "",
        f"📈 日経: {_fmt_price(prices,'^N225','円')}",
        f"📈 S&P: {_fmt_price(prices,'^GSPC')}  NYダウ: {_fmt_price(prices,'^DJI')}",
        f"💵 ドル円: {_fmt_price(prices,'USDJPY=X','円')}  VIX: {_fmt_price(prices,'^VIX')}",
        f"🥇 金: {_fmt_price(prices,'GC=F','$')}  ₿: {_fmt_price(prices,'BTC-USD','$')}",
        "",
        "📱 市場AI秘書",
    ])

    # ===== 通知②: イラスト付きAI分析（画像のキャプションとして使用）=====
    signal_lines = []
    for s in signals[:4]:
        d = s.get("direction", "")
        arrow = "🔺" if "上昇" in d or "強" in d else "🔻" if "下落" in d or "弱" in d else "➡️"
        signal_lines.append(f"{arrow} {s.get('indicator','')}: {d}")

    ai_text = ""
    if ai_summary and ai_summary.get("available"):
        overall = ai_summary.get("overall_summary", "")
        if overall:
            ai_text = f"\n🤖 *AI分析:*\n{overall[:300]}{'...' if len(overall)>300 else ''}"

    facts_text = ""
    if facts:
        facts_text = "\n✅ " + "\n✅ ".join(facts[:2])
    hypo_text = ""
    if hypotheses:
        hypo_text = "\n🔮 " + "\n🔮 ".join(hypotheses[:1])

    msg2_caption = "\n".join([
        f"🦣 *ガネーシャの市場分析* [{mode.upper()}]",
        f"━━━━━━━━━━━━━━━",
        f"地合い: {mood}  スコア: {score:+.2f}",
        f"Fear&Greed: {fg_str}",
        "",
        *signal_lines,
        facts_text,
        hypo_text,
        ai_text,
        "",
        "📱 市場AI秘書",
    ])

    # レポートURL
    report_url = ""
    if report_paths and report_paths.get("url"):
        report_url = f"\n\n🌐 [レポートを見る]({report_paths.get('url')})"

    return [msg1, msg2_caption + report_url]


def send_message(text: str) -> bool:
    """Telegram にメッセージを送信する。失敗時は False を返す。"""
    if not _is_configured():
        logger.info("Telegram 未設定のためスキップ（.envを確認してください）")
        return False

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    try:
        resp = requests.post(url, json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
        }, timeout=15)
        resp.raise_for_status()
        logger.info("Telegram 送信成功")
        return True
    except Exception as e:
        logger.error(f"Telegram 送信失敗: {e}")
        return False


def send_photo(image_path: str, caption: str = "") -> bool:
    """Telegram にチャート画像を送信する。"""
    if not _is_configured():
        return False

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{token}/sendPhoto"

    try:
        with open(image_path, "rb") as f:
            resp = requests.post(url, data={
                "chat_id": chat_id,
                "caption": caption[:1024],
            }, files={"photo": f}, timeout=30)
        resp.raise_for_status()
        logger.info(f"Telegram 画像送信成功: {image_path}")
        return True
    except Exception as e:
        logger.error(f"Telegram 画像送信失敗: {e}")
        return False


def send_document(file_path: str, caption: str = "") -> bool:
    """Telegram にHTMLレポートなどのファイルを送信する。"""
    if not _is_configured():
        return False

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{token}/sendDocument"

    try:
        with open(file_path, "rb") as f:
            resp = requests.post(url, data={
                "chat_id": chat_id,
                "caption": caption[:1024],
            }, files={"document": f}, timeout=30)
        resp.raise_for_status()
        logger.info(f"Telegram ファイル送信成功: {file_path}")
        return True
    except Exception as e:
        logger.error(f"Telegram ファイル送信失敗: {e}")
        return False


def send_charts(chart_paths: dict, ai_summary: dict = None) -> bool:
    """チャートPNG画像をまとめて送信する。"""
    if not _is_configured() or not chart_paths:
        return False

    # AI要約があればキャプションに使う
    overall = ""
    if ai_summary and ai_summary.get("available"):
        overall = ai_summary.get("overall_summary", "")
        if len(overall) > 300:
            overall = overall[:300] + "..."

    sent = 0
    # メインチャート（overview）を最初に送る
    priority_keys = ["overview", "fear_greed", "prices", "indices"]
    ordered = []
    for k in priority_keys:
        if k in chart_paths:
            ordered.append((k, chart_paths[k]))
    for k, v in chart_paths.items():
        if k not in priority_keys:
            ordered.append((k, v))

    for i, (key, path) in enumerate(ordered[:4]):  # 最大4枚
        import os as _os
        if not path or not _os.path.exists(str(path)):
            continue
        caption = ""
        if i == 0 and overall:
            caption = f"🤖 AI分析:\n{overall}\n\n⚠️投資助言ではありません"
        elif i == 0:
            caption = "📊 市場概況チャート | ⚠️投資助言ではありません"
        send_photo(str(path), caption)
        sent += 1

    logger.info(f"チャート画像 {sent}枚 送信")
    return sent > 0


def run(risk: dict, analysis: dict, report_paths: dict, mode: str,
        prices: dict = None, news: list = None,
        fear_greed: dict = None, ai_summary: dict = None,
        chart_paths: dict = None) -> bool:
    if not _is_configured():
        logger.info("Telegram 設定なし。通知をスキップします。")
        return False

    try:
        msgs = build_three_messages(
            risk, analysis, mode,
            prices=prices, news=news,
            fear_greed=fear_greed, ai_summary=ai_summary
        )

        # 通知①: ニュース＆市場概況（テキスト）
        send_message(msgs[0])

        # 通知②: イラスト（チャート画像）＋AI分析キャプション
        chart_sent = False
        if chart_paths:
            import os as _os
            for key in ["overview", "prices", "indices"]:
                path = chart_paths.get(key, "")
                if path and _os.path.exists(str(path)):
                    send_photo(str(path), caption=msgs[1])
                    chart_sent = True
                    break
        if not chart_sent:
            # チャートがなければテキストで送る
            send_message(msgs[1])

        # 通知③: HTMLレポートファイル（Safari・Chromeで開ける）
        html_path = report_paths.get("html", "")
        if html_path:
            import os as _os
            if _os.path.exists(str(html_path)):
                send_document(
                    str(html_path),
                    caption="📄 本日の詳細レポート\nSafari・Chrome・Edgeで開いてください\n\n⚠️投資助言ではありません"
                )

        logger.info("Telegram 3通送信完了")
        return True
    except Exception as e:
        logger.error(f"Telegram通知エラー: {e}")
        logger.debug(traceback.format_exc())
        return False
