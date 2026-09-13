"""
LINE通知モジュール（L5i）
LINE Notify API を使ってTelegramと同じ内容を送信する。
日本での普及率95%のLINEに対応することで、家族・友人との共有が簡単になる。

セットアップ:
1. https://notify-bot.line.me/my/ にアクセス
2. 「トークンを発行する」→ トークン名を入力 → 「1対1でLINE Notifyから通知を受け取る」
3. 発行されたトークンを GitHub Secrets の LINE_NOTIFY_TOKEN に設定
"""
import os
import logging
import requests
from src.utils import setup_logger, get_today_str

logger = setup_logger("notify_line")

LINE_NOTIFY_URL = "https://notify-api.line.me/api/notify"


def _is_configured() -> bool:
    token = os.getenv("LINE_NOTIFY_TOKEN", "").strip()
    return bool(token) and token not in {"ここにLINEトークン", ""}


def _get_token() -> str:
    return os.getenv("LINE_NOTIFY_TOKEN", "").strip()


def send_message(text: str) -> bool:
    """LINEにテキストメッセージを送信"""
    if not _is_configured():
        logger.debug("LINE Notify 未設定スキップ")
        return False
    try:
        headers = {"Authorization": f"Bearer {_get_token()}"}
        data = {"message": f"\n{text}"}
        r = requests.post(LINE_NOTIFY_URL, headers=headers, data=data, timeout=15)
        r.raise_for_status()
        logger.info("LINE テキスト送信 ✅")
        return True
    except Exception as e:
        logger.error(f"LINE 送信失敗: {e}")
        return False


def send_image(image_path: str, caption: str = "") -> bool:
    """LINEに画像を送信（キャプション付き）"""
    if not _is_configured():
        return False
    try:
        headers = {"Authorization": f"Bearer {_get_token()}"}
        data = {"message": f"\n{caption}" if caption else "\n画像"}
        with open(image_path, "rb") as f:
            files = {"imageFile": f}
            r = requests.post(LINE_NOTIFY_URL, headers=headers, data=data, files=files, timeout=30)
        r.raise_for_status()
        logger.info(f"LINE 画像送信 ✅: {image_path}")
        return True
    except Exception as e:
        logger.error(f"LINE 画像送信失敗: {e}")
        return False


def run(risk, fear_greed, prices, report_paths,
        ai_summary=None, chart_paths=None,
        multi_consensus=None, autonomous_plan=None) -> bool:
    """LINE通知メイン（Telegramの主要メッセージを転送）"""
    if not _is_configured():
        logger.info("LINE Notify 未設定 — スキップ")
        return False

    logger.info("--- LINE通知送信 ---")
    today = get_today_str()

    # ① メインサマリー（コンパクト版）
    score = risk.get("score", 0)
    fg = fear_greed.get("score", 50) or 50
    fg_label = fear_greed.get("rating_ja", "---")

    if score >= 2:    mood = "🚀 強気！"
    elif score >= 0.5: mood = "😊 やや強気"
    elif score >= -0.5:mood = "😐 中立"
    elif score >= -2:  mood = "😟 やや弱気"
    else:              mood = "😱 弱気！"

    def fmt(sym, unit=""):
        d = prices.get(sym, {})
        v = d.get("latest")
        chg = d.get("change_pct")
        if not v:
            return "---"
        arrow = "▲" if (chg or 0) >= 0 else "▼"
        return f"{v:,.1f}{unit} {arrow}{abs(chg or 0):.1f}%"

    main_msg = (
        f"📊 市場AI秘書 [{today}]\n"
        f"{'━'*20}\n"
        f"{mood}\n"
        f"Fear&Greed: {fg} ({fg_label})\n\n"
        f"🇯🇵 日経: {fmt('^N225','円')}\n"
        f"🇺🇸 S&P: {fmt('^GSPC')}\n"
        f"💵 ドル円: {fmt('USDJPY=X','円')}\n"
        f"😱 VIX: {fmt('^VIX')}\n"
        f"🥇 金: {fmt('GC=F','$')}"
    )

    # マルチエージェント結果があれば追加
    if multi_consensus and multi_consensus.get("available"):
        v = multi_consensus.get("verdict", {})
        dir_ja = {"bull": "📈上昇", "bear": "📉下落", "neutral": "➡️中立"}
        main_msg += (
            f"\n\n🗳️ 4AI合議: {dir_ja.get(v.get('direction','neutral'),'---')}"
            f" ({v.get('consensus_level','')})"
        )

    send_message(main_msg)

    # ② チャート画像（最初に見つかったもの）
    if chart_paths:
        for key in ["overview", "technical", "prices"]:
            path = chart_paths.get(key, "")
            if path and os.path.exists(str(path)):
                ai_caption = ""
                if ai_summary and ai_summary.get("available"):
                    neut = (ai_summary.get("neutral_view") or "")[:100]
                    ai_caption = f"AI総評: {neut}"
                send_image(str(path), caption=ai_caption)
                break

    # ③ レポートURL
    report_url = report_paths.get("url", "")
    if report_url:
        url_msg = (
            f"📱 詳細レポート\n"
            f"{report_url}\n"
            f"（iPhoneのSafariで開いてください）"
        )
        send_message(url_msg)

    # ④ 今日のミッション（自律エージェントがあれば）
    if autonomous_plan and autonomous_plan.get("available"):
        mission = autonomous_plan.get("todays_mission", "")
        regime = autonomous_plan.get("regime", {}).get("label", "")
        if mission:
            send_message(f"🧠 今日のミッション\n{regime}\n{mission}")

    logger.info("✅ LINE通知完了")
    return True
