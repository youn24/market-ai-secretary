"""
Telegram通知モジュール（初心者でも一目でわかるデザイン）
"""
import os
import re
import json
import traceback
import requests
from dotenv import load_dotenv
from src.utils import setup_logger, get_today_str

logger = setup_logger("notify_telegram")
load_dotenv()


def _is_configured() -> bool:
    token   = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    skip    = {"ここにBotFatherのトークン", "ここにあなたのChat ID", ""}
    return token not in skip and chat_id not in skip


def _fmt(prices: dict, sym: str, unit: str = "") -> str:
    d   = prices.get(sym, {})
    v   = d.get("latest")
    chg = d.get("change_pct")
    if v is None:
        return "---"
    arrow = "▲" if (chg or 0) >= 0 else "▼"
    chg_s = f"{abs(chg):.2f}%" if chg is not None else ""
    return f"{v:,.2f}{unit} {arrow}{chg_s}"


def _mood(score: float) -> tuple:
    """地合いスコア → (信号灯, 一言)"""
    if   score >= 2:   return "🟢", "強気！上昇ムード"
    elif score >= 0.5: return "🟢", "やや強気"
    elif score >= -0.5:return "🟡", "中立・様子見"
    elif score >= -2:  return "🟠", "やや弱気・注意"
    else:               return "🔴", "弱気！慎重に"


def _fg_bar(score) -> str:
    """Fear&Greed をテキストバーで表現"""
    n = int(score or 50)
    filled = round(n / 10)
    bar = "█" * filled + "░" * (10 - filled)
    if n >= 75: emoji, label = "😱", "超強欲"
    elif n >= 55: emoji, label = "😤", "強欲"
    elif n >= 45: emoji, label = "😐", "中立"
    elif n >= 25: emoji, label = "😰", "恐怖"
    else:         emoji, label = "😭", "超恐怖"
    return f"{emoji} {bar} {n} ({label})"


def _fmtv(prices: dict, sym: str, unit: str = "") -> str:
    """値をinline code・変化率を矢印付きで返す（プロ仕様フォーマット）"""
    d   = prices.get(sym, {})
    v   = d.get("latest")
    chg = d.get("change_pct")
    if v is None:
        return "`---`"
    arrow = "▲" if (chg or 0) >= 0 else "▼"
    chg_s = f" {arrow}`{abs(chg):.2f}%`" if chg is not None else ""
    return f"`{v:,.2f}{unit}`{chg_s}"


def build_three_messages(risk, analysis, mode,
                         prices=None, news=None,
                         fear_greed=None, ai_summary=None,
                         report_paths=None,
                         note_article_url: str = "",
                         note_magazine_url: str = "") -> list:
    from datetime import date as _date
    today      = get_today_str()
    prices     = prices or {}
    news       = news or []
    fear_greed = fear_greed or {}
    ai_summary = ai_summary or {}
    report_paths = report_paths or {}

    score    = risk.get("score", 0)
    tl, mood = _mood(score)
    fg_score = fear_greed.get("score") or 50
    fg_bar   = _fg_bar(fg_score)
    score_s  = f"+{score:.1f}" if score >= 0 else f"{score:.1f}"
    weekday  = ["月", "火", "水", "木", "金", "土", "日"][_date.today().weekday()]

    # VIX判定
    vix_val = prices.get("^VIX", {}).get("latest") or 0
    if   vix_val < 15: vix_icon, vix_txt = "🟢", "安定"
    elif vix_val < 20: vix_icon, vix_txt = "🟡", "やや不安"
    elif vix_val < 30: vix_icon, vix_txt = "🟠", "警戒"
    else:              vix_icon, vix_txt = "🔴", "危険！"

    # ニュース整理（重要度順・カテゴリ偏り防止）
    sorted_news = sorted(news, key=lambda x: {"A":0,"B":1,"C":2}.get(x.get("importance","C"),2))
    imp_icon    = {"A": "🔴", "B": "🟡", "C": "⚪"}
    cat_counts: dict[str, int] = {}
    news_lines  = []
    for item in sorted_news:
        if len(news_lines) >= 6:
            break
        cat = item.get("category", "その他")
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
        if cat_counts[cat] <= 2:
            icon  = imp_icon.get(item.get("importance", "C"), "⚪")
            title = item.get("title", "")[:42]
            news_lines.append(f"{icon} {title}")

    # ━━━━━ 通知① 相場まとめ（プロ仕様） ━━━━━
    msg1 = (
        f"🤖 *市場AI秘書* | {today}（{weekday}）\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"\n"
        f"┌─────────────────────┐\n"
        f"│  {tl} *今日の判断: {mood}*\n"
        f"│  AIスコア `{score_s}` / ±3\n"
        f"└─────────────────────┘\n"
        f"\n"
        f"*📈 株価*\n"
        f"🇯🇵 日経  {_fmtv(prices,'^N225','円')}\n"
        f"🇺🇸 S&P  {_fmtv(prices,'^GSPC')}\n"
        f"🇺🇸 NAS  {_fmtv(prices,'^IXIC')}\n"
        f"\n"
        f"*💱 為替・商品*\n"
        f"💵 ドル円 {_fmtv(prices,'USDJPY=X','円')}\n"
        f"🥇 金    {_fmtv(prices,'GC=F','$')}\n"
        f"🛢 原油  {_fmtv(prices,'CL=F','$')}\n"
        f"₿ BTC   {_fmtv(prices,'BTC-USD','$')}\n"
        f"\n"
        f"⚡ *VIX* {_fmtv(prices,'^VIX')}  {vix_icon} {vix_txt}\n"
        f"😱 *恐怖指数* `{fg_bar}`\n"
        f"\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"*📰 注目ニュース*\n"
        + "\n".join(news_lines)
    )

    # ━━━━━ 通知② AI 3視点分析 ━━━━━
    ai_lines = []
    if ai_summary.get("available"):
        bull = (ai_summary.get("bull_view") or "")[:120]
        bear = (ai_summary.get("bear_view") or "")[:120]
        neut = (ai_summary.get("neutral_view") or "")[:180]
        if bull: ai_lines.append(f"📈 *強気派の見方*\n{bull}")
        if bear: ai_lines.append(f"📉 *弱気派の見方*\n{bear}")
        if neut: ai_lines.append(f"⚖️ *AIの総合判断*\n{neut}")
    else:
        ai_lines.append("🤖 AI分析を実行中...")

    msg2_caption = (
        f"🤖 *AI 3視点分析*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        + "\n\n".join(ai_lines)
    )

    # ━━━━━ 通知③ 詳細レポート + note誘導 ━━━━━
    report_url   = report_paths.get("url", "")
    mag_url      = note_magazine_url or os.getenv("NOTE_MAGAZINE_URL", "").strip()
    article_url  = note_article_url  or ""

    # note誘導ブロック（マガジンURLがある場合のみ表示）
    note_block = ""
    if mag_url:
        note_block = (
            f"\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📝 *今日のnote記事（AI深掘り分析）*\n"
        )
        if article_url:
            note_block += f"🔗 {article_url}\n"
        note_block += (
            f"✅ 無料：相場まとめ・価格表\n"
            f"🔐 有料：AI3視点・シナリオ・テクニカル\n"
            f"\n"
            f"📰 *月額マガジン登録*（毎朝届く深掘り分析）\n"
            f"💳 {mag_url}\n"
        )

    # FXアフィリエイトブロック（FX_AFFILIATE_URL設定時のみ表示）
    aff_url = os.getenv("FX_AFFILIATE_URL", "").strip()
    aff_block = ""
    if aff_url:
        aff_block = (
            f"\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💹 *FX口座をお持ちでない方へ*\n"
            f"スプレッド最狭水準・ツール充実のFX口座\n"
            f"👇 無料開設はこちら\n"
            f"{aff_url}\n"
        )

    msg3 = (
        f"📱 *詳細レポート*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"チャート・AI分析・ニュースを一画面で確認：\n\n"
        f"{report_url if report_url else '（準備中）'}\n"
        f"\n"
        f"📊チャート  🤖AI議論  📰ニュース\n"
        f"📐テクニカル  🎭シナリオ  📅カレンダー"
        + note_block
        + aff_block
    )

    return [msg1, msg2_caption, msg3]


# ────────────────────────────────────────────────────────────────
# 低レベル送信関数
# ────────────────────────────────────────────────────────────────

def verify_bot() -> bool:
    """
    起動時にボットトークンの有効性を確認し、結果をログに明示する。
    → トークンが失効/不一致のとき、Actionsログに「❌」が必ず残るので
       「成功表示なのに通知が来ない」事故が一目で分かる。
    """
    if not _is_configured():
        logger.error("❌ Telegram未設定（TOKEN/CHAT_IDが空）。通知は送れません。"
                     "GitHub Secrets を確認してください。")
        return False
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    try:
        r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
        if r.status_code == 200 and r.json().get("ok"):
            uname = r.json().get("result", {}).get("username", "?")
            logger.info(f"✅ Telegramボット有効: @{uname}")
            return True
        logger.error(f"❌ TELEGRAM_BOT_TOKEN が無効（getMe status={r.status_code}）。"
                     "BotFatherでトークンを再生成した場合は GitHub Secrets の "
                     "TELEGRAM_BOT_TOKEN を新トークンに更新してください。")
        return False
    except Exception as e:
        logger.error(f"❌ Telegram getMe 失敗: {e}")
        return False


def send_message(text: str, chat_id: str = None, bot_token: str = None) -> bool:
    _tok = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    _cid = str(chat_id) if chat_id is not None else os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not _tok or not _cid or _tok in {"ここにBotFatherのトークン", ""} or _cid in {"ここにあなたのChat ID", ""}:
        logger.info("Telegram 未設定スキップ")
        return False
    url = f"https://api.telegram.org/bot{_tok}/sendMessage"

    # ① まず Markdown で送信
    try:
        r = requests.post(
            url,
            json={"chat_id": _cid, "text": text, "parse_mode": "Markdown"},
            timeout=15,
        )
        if r.status_code == 200:
            logger.info("Telegram テキスト送信 ✅")
            return True
        # Markdown構文エラー(400)等 → プレーンで再送して"1通消える"のを防ぐ
        logger.warning(f"Markdown送信失敗(status={r.status_code}): "
                       f"{r.text[:160]} → プレーンで再送")
    except Exception as e:
        logger.warning(f"Telegram送信例外: {e} → プレーンで再送")

    # ② プレーンテキストで再送（parse_mode なし）
    try:
        r = requests.post(url, json={"chat_id": _cid, "text": text}, timeout=15)
        r.raise_for_status()
        logger.info("Telegram テキスト送信 ✅（プレーン）")
        return True
    except Exception as e:
        logger.error(f"Telegram 送信失敗（プレーンも不可）: {e}")
        return False


def send_photo(image_path: str, caption: str = "",
               chat_id: str = None, bot_token: str = None) -> bool:
    _tok = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    _cid = str(chat_id) if chat_id is not None else os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not _tok or not _cid:
        return False
    url = f"https://api.telegram.org/bot{_tok}/sendPhoto"
    cap = caption[:1024]

    # ① Markdown キャプションで送信
    try:
        with open(image_path, "rb") as f:
            r = requests.post(
                url,
                data={"chat_id": _cid, "caption": cap, "parse_mode": "Markdown"},
                files={"photo": f},
                timeout=30,
            )
        if r.status_code == 200:
            logger.info(f"Telegram 画像送信 ✅: {image_path}")
            return True
        logger.warning(f"画像Markdown送信失敗(status={r.status_code}): "
                       f"{r.text[:160]} → プレーンで再送")
    except Exception as e:
        logger.warning(f"Telegram 画像送信例外: {e} → プレーンで再送")

    # ② プレーンキャプションで再送
    try:
        with open(image_path, "rb") as f:
            r = requests.post(
                url,
                data={"chat_id": _cid, "caption": cap},
                files={"photo": f},
                timeout=30,
            )
        r.raise_for_status()
        logger.info(f"Telegram 画像送信 ✅（プレーン）: {image_path}")
        return True
    except Exception as e:
        logger.error(f"Telegram 画像送信失敗（プレーンも不可）: {e}")
        return False


def send_video(video_path: str, caption: str = "",
               chat_id: str = None, bot_token: str = None) -> bool:
    """MP4動画を送信（通知③・要約ナレーション動画）"""
    _tok = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    _cid = str(chat_id) if chat_id is not None else os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not _tok or not _cid or not video_path or not os.path.exists(video_path):
        return False
    url = f"https://api.telegram.org/bot{_tok}/sendVideo"
    try:
        with open(video_path, "rb") as f:
            r = requests.post(
                url,
                data={"chat_id": _cid, "caption": caption[:1024],
                      "parse_mode": "HTML", "supports_streaming": True},
                files={"video": f},
                timeout=120,
            )
        r.raise_for_status()
        logger.info(f"Telegram 動画送信 ✅: {video_path}")
        return True
    except Exception as e:
        logger.error(f"Telegram 動画送信失敗: {e}")
        return False


# ── 通知②の読みやすさ強化: Markdown風テキスト → Telegram HTML（カテゴリ折りたたみ） ──
_CAT = "\x00CAT\x00"   # カテゴリ区切りセンチネル（_to_html_message が blockquote に変換）


def _esc_html(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _md_to_tg_html(t: str) -> str:
    """*bold* と [text](url) を Telegram HTML に変換（stray * はそのまま安全）"""
    t = _esc_html(t)
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', t)
    t = re.sub(r"\*([^*\n]+)\*", r"<b>\1</b>", t)
    t = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", t)
    return t


def _to_html_message(raw: str) -> str:
    """
    センチネル区切りを「┏━ 太字下線タイトル ＋ 枠ブロック」へ変換する。
    Telegramの<blockquote>は色付き背景＋左バーで描画される＝カテゴリの枠。
    センチネル直後の1文字: "0"=常時表示の枠 / "1"=タップで展開する枠（長い データ用）
    """
    parts = raw.split(_CAT)
    out = [_md_to_tg_html(parts[0].strip())]
    for p in parts[1:]:
        head, _, body = p.partition("\n")
        body = body.strip()
        if not body:
            continue   # 中身のないカテゴリは枠ごと表示しない
        flag  = head[:1]
        title = head[1:].strip() if flag in "01" else head.strip()
        tag   = "<blockquote expandable>" if flag == "1" else "<blockquote>"
        out.append(f"\n┏━ <b><u>{_esc_html(title)}</u></b>")
        out.append(f"{tag}{_md_to_tg_html(body)}</blockquote>")
    msg = "\n".join(out)
    if len(msg) > 4000:   # タグ途中で切れるとHTML全体が壊れるため枠の境界で切る
        cut = msg.rfind("</blockquote>", 0, 4000)
        msg = msg[:cut + 13] if cut != -1 else msg[:4000]
    return msg + "\n\n📌 チャート・全データは下のボタンからフルレポートへ"


def send_message_with_button(text: str, button_text: str, button_url: str,
                             chat_id: str = None, bot_token: str = None,
                             parse_modes=("Markdown", None)) -> bool:
    """インラインキーボードボタン付きのメッセージを送信"""
    _tok = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    _cid = str(chat_id) if chat_id is not None else os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not _tok or not _cid:
        return False
    url = f"https://api.telegram.org/bot{_tok}/sendMessage"
    markup = {"inline_keyboard": [[{"text": button_text, "url": button_url}]]}

    for parse_mode in parse_modes:
        body = text
        if parse_mode is None and "<" in text:
            # HTML失敗時のプレーン再送: タグを剥がして可読性を保つ
            body = re.sub(r"<[^>]+>", "", text)
            body = body.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        payload = {"chat_id": _cid, "text": body[:4096], "reply_markup": markup}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        try:
            r = requests.post(url, json=payload, timeout=15)
            if r.status_code == 200:
                logger.info("Telegram ボタン付きメッセージ送信 ✅")
                return True
            if parse_mode:
                logger.warning(f"Markdown失敗({r.status_code}) → プレーンで再送")
        except Exception as e:
            logger.warning(f"Telegram送信例外: {e}")
    logger.error("Telegram ボタン付きメッセージ 送信失敗")
    return False


def send_photo_with_button(image_path: str, caption: str,
                           button_text: str, button_url: str,
                           chat_id: str = None, bot_token: str = None) -> bool:
    """
    画像＋キャプション＋インラインボタンを「1通」で送る。
    通知を1本にまとめたいときに使う（FX午後レポート等）。
    Markdown失敗時はプレーンで自動再送する。
    """
    _tok = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    _cid = str(chat_id) if chat_id is not None else os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not _tok or not _cid:
        return False
    url    = f"https://api.telegram.org/bot{_tok}/sendPhoto"
    cap    = (caption or "")[:1024]
    markup = json.dumps({"inline_keyboard": [[{"text": button_text, "url": button_url}]]})

    for parse_mode in ("Markdown", None):
        data = {"chat_id": _cid, "caption": cap, "reply_markup": markup}
        if parse_mode:
            data["parse_mode"] = parse_mode
        try:
            with open(image_path, "rb") as f:
                r = requests.post(url, data=data, files={"photo": f}, timeout=40)
            if r.status_code == 200:
                logger.info(f"Telegram 画像+ボタン送信 ✅: {image_path}")
                return True
            logger.warning(f"画像+ボタン送信失敗(status={r.status_code}): "
                           f"{r.text[:160]}" + ("→ プレーンで再送" if parse_mode else ""))
        except Exception as e:
            logger.warning(f"Telegram 画像+ボタン送信例外: {e}")
    logger.error("Telegram 画像+ボタン 送信失敗")
    return False


def send_document(file_path: str, caption: str = "") -> bool:
    if not _is_configured():
        return False
    token   = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    try:
        with open(file_path, "rb") as f:
            r = requests.post(
                f"https://api.telegram.org/bot{token}/sendDocument",
                data={"chat_id": chat_id, "caption": caption[:1024]},
                files={"document": f},
                timeout=30,
            )
        r.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Telegram ファイル送信失敗: {e}")
        return False


# ────────────────────────────────────────────────────────────────
# メイン実行
# ────────────────────────────────────────────────────────────────

def _p(prices, sym, unit="", digits=2):
    """price + arrow + pct を1行テキストで返す（キャプション用）"""
    d   = prices.get(sym, {})
    v   = d.get("latest")
    chg = d.get("change_pct")
    if v is None:
        return "---"
    arrow = "▲" if (chg or 0) >= 0 else "▼"
    chg_s = f"{abs(chg):.2f}%" if chg is not None else ""
    return f"{v:,.{digits}f}{unit} {arrow}{chg_s}"


def _build_overview_caption(risk, prices, fear_greed, news, ai_summary) -> str:
    """
    通知①のキャプション（1024文字以内の全体俯瞰）
    写真送信時のキャプションとして使う
    """
    from datetime import date as _date
    today   = get_today_str()
    weekday = ["月", "火", "水", "木", "金", "土", "日"][_date.today().weekday()]

    score    = risk.get("score", 0)
    tl, mood = _mood(score)
    score_s  = f"+{score:.1f}" if score >= 0 else f"{score:.1f}"

    vix_val = prices.get("^VIX", {}).get("latest") or 0
    vix_icon = "🟢" if vix_val < 15 else "🟡" if vix_val < 20 else "🟠" if vix_val < 30 else "🔴"
    vix_txt  = "安定" if vix_val < 15 else "やや不安" if vix_val < 20 else "警戒" if vix_val < 30 else "危険！"

    fg  = fear_greed.get("score") or 50
    fg_n = int(fg)
    bar = "█" * round(fg_n / 10) + "░" * (10 - round(fg_n / 10))
    if fg_n >= 75:   fg_lbl = "超強欲"
    elif fg_n >= 55: fg_lbl = "強欲"
    elif fg_n >= 45: fg_lbl = "中立"
    elif fg_n >= 25: fg_lbl = "恐怖"
    else:            fg_lbl = "超恐怖"

    # ニュース上位3件
    sorted_news = sorted(news or [], key=lambda x: {"A":0,"B":1,"C":2}.get(x.get("importance","C"),2))
    imp_icon = {"A": "🔴", "B": "🟡", "C": "⚪"}
    news_lines = []
    for item in sorted_news[:3]:
        icon  = imp_icon.get(item.get("importance","C"), "⚪")
        title = item.get("title","")[:38]
        news_lines.append(f"{icon} {title}")

    # AIの一言（中立見解の先頭100字）
    ai_one = ""
    if (ai_summary or {}).get("available"):
        ai_one = ((ai_summary.get("neutral_view") or "")[:100]).strip()

    lines = [
        f"🤖 *市場AI秘書* | {today}（{weekday}）",
        "━━━━━━━━━━━━━━━━━━━━",
        f"{tl} *{mood}*  スコア `{score_s}`",
        "",
        "📈 *株価*",
        f"🇯🇵 日経  {_p(prices,'^N225','円',0)}",
        f"🇺🇸 S&P  {_p(prices,'^GSPC','',2)}",
        f"🇺🇸 NAS  {_p(prices,'^IXIC','',2)}",
        "",
        "💱 *為替・商品*",
        f"💵 ドル円 {_p(prices,'USDJPY=X','円',2)}",
        f"🥇 金    {_p(prices,'GC=F','$',0)}",
        f"🛢 原油  {_p(prices,'CL=F','$',2)}",
        f"₿ BTC   {_p(prices,'BTC-USD','$',0)}",
        "",
        f"⚡ VIX `{vix_val:.1f}` {vix_icon} {vix_txt}",
        f"😱 F&G `{bar}` {fg_n} ({fg_lbl})",
    ]
    if news_lines:
        lines += ["", "📰 *注目ニュース*"] + news_lines
    if ai_one:
        lines += ["", f"⚖️ *AIの一言*", ai_one]

    return "\n".join(lines)


def _build_unified_caption(risk, prices, fear_greed, ai_summary,
                           setups=None, prediction_tracker=None,
                           us_afterhours=None, pts=None, adr=None,
                           kabudragon=None, valuation=None, macro_watch=None,
                           market_signals=None, macro_regime=None) -> str:
    """
    朝レポートを1通に集約したときのキャプション（Telegram上限1024字）。

    価格・F&G・VIX・ニュース・AI3視点・キャラクターは
    サマリーカード画像に載っているため重複させない。
    ここでは「カードに写らない・かつ寄り付き前に効く」情報を優先する。
    優先度の低いブロックから順に落として1024字に収める。
    """
    from datetime import date as _date
    today   = get_today_str()
    weekday = ["月", "火", "水", "木", "金", "土", "日"][_date.today().weekday()]

    score    = (risk or {}).get("score", 0)
    tl, mood = _mood(score)
    score_s  = f"+{score:.1f}" if score >= 0 else f"{score:.1f}"

    head = [
        f"🤖 *市場AI秘書* | {today}（{weekday}）",
        "━━━━━━━━━━━━━━",
        f"{tl} *{mood}*　スコア `{score_s}`",
    ]

    # ── バリュエーション節目（滅多に出ないが出たら最重要なので先頭付近に置く）──
    vw = valuation or {}
    if vw.get("available"):
        head.append("")
        for e in vw.get("events", [])[:2]:
            short = e["label"].split("（")[0]
            head.append(f"{e['emoji']} *{short} {e['value']:.2f}{e['unit']}*"
                        f"「{e['prev_zone']}」→「{e['zone']}」")

    # ── 景気・信用の先行シグナル（滅多に変わらないが変われば最重要）──
    mw = macro_watch or {}
    if mw.get("available"):
        head.append("")
        for e in mw.get("events", [])[:2]:
            short = e["label"].split("（")[0]
            head.append(f"{e['emoji']} *{short} {e['value']:.2f}{e['unit']}*"
                        f"「{e['prev_zone']}」→「{e['zone']}」")

    # ── 市場内部シグナル（SOXは寄り付きに直結するので上に出す）──
    ms = market_signals or {}
    if ms.get("available"):
        head.append("")
        for e in ms.get("events", [])[:2]:
            short = e["label"].split("（")[0]
            head.append(f"{e['emoji']} *{short}* {e['zone']}")

    # ── 寄り付き前チェック（最優先：時間が経つと価値が消える情報） ──
    pre = []
    ua = us_afterhours or {}
    if ua.get("available"):
        movers = ua.get("movers", [])
        if movers:
            top = movers[0]
            e = "⬆️" if top["chg_pct"] >= 0 else "⬇️"
            pre.append(f"🇺🇸 米時間外: {e}{top['name']} {top['chg_pct']:+.1f}%")
            semis = [m for m in movers if m.get("sector") == "半導体"
                     and abs(m.get("chg_pct") or 0) >= 2.0]
            if semis:
                big = max(semis, key=lambda x: abs(x["chg_pct"]))
                pre.append(f"　→ 日本の半導体株に{'追い風' if big['chg_pct']>0 else '逆風'}")
        else:
            pre.append("🇺🇸 米時間外: 大きな変動なし")

    pt = pts or {}
    if pt.get("available"):
        u = (pt.get("up") or [])[:1]
        d = (pt.get("down") or [])[:1]
        seg = []
        if u: seg.append(f"⬆️{u[0]['name']} {u[0]['chg_pct']:+.1f}%")
        if d: seg.append(f"⬇️{d[0]['name']} {d[0]['chg_pct']:+.1f}%")
        if seg:
            pre.append("🌙 PTS夜間: " + " / ".join(seg))

    ad = adr or {}
    if ad.get("available") and ad.get("major_avg_divergence") is not None:
        div = ad["major_avg_divergence"]
        pre.append(f"🌏 ADR乖離 {div:+.2f}%（寄り付き示唆）")

    kd = kabudragon or {}
    if kd.get("available"):
        ups = ((kd.get("rankings") or {}).get("age") or {}).get("items", [])[:1]
        if ups and ups[0].get("chg_pct") is not None:
            pre.append(f"🐉 前日値上がり1位: {ups[0]['name']} {ups[0]['chg_pct']:+.1f}%")

    # ── シグナル ──
    sig = []
    st = setups or {}
    if st.get("available") and st.get("setups"):
        s0 = st["setups"][0]
        line = f"🎯 {s0.get('name','')}: {s0.get('label','')}"
        if s0.get("mtf_note"):
            line += f"（{s0['mtf_note']}）"
        sig.append(line)

    # ── 予測精度 ──
    acc = []
    ptk = prediction_tracker or {}
    if ptk.get("available"):
        r10 = (ptk.get("stats") or {}).get("10d", {})
        rate = r10.get("rate")
        if rate is not None:
            mark = "🎯" if rate >= 65 else "🔶" if rate >= 50 else "⚠️"
            acc.append(f"🧠 AI直近10日の的中率 {mark} {rate}%")

    # ── マクロ環境（歴史的に実績のあるファンダ指標） ──
    mac = []
    mr = macro_regime or {}
    if mr.get("available"):
        for s in (mr.get("signals") or [])[:2]:
            mac.append(f"{s.get('emoji','')} {s.get('title','')}　{s.get('value','')}")

    # ── AIの一言 ──
    ai_one = ""
    if (ai_summary or {}).get("available"):
        ai_one = ((ai_summary.get("neutral_view") or "")[:110]).strip()
    ai_blk = [f"⚖️ {ai_one}"] if ai_one else []

    foot = ["👇 3シナリオ・チャート・全データはレポートへ"]

    # 優先度の低い順に落として1024字に収める
    blocks = [pre, sig, acc, mac, ai_blk]
    while True:
        parts = [head]
        parts += [b for b in blocks if b]
        parts.append(foot)
        text = "\n\n".join("\n".join(p) for p in parts)
        if len(text) <= 1024:
            return text
        # 後ろのブロックから削る（AI一言 → 精度 → シグナル の順）
        for i in range(len(blocks) - 1, -1, -1):
            if blocks[i]:
                blocks[i] = []
                break
        else:
            return text[:1024]


def _build_detail_message(risk, prices, fear_greed, news,
                          ai_summary, scenario, technical,
                          sector_analysis, prediction_tracker,
                          autonomous_plan, multi_consensus,
                          character_comments, macro,
                          nikkei_internals, adr, setups,
                          stock_dossier=None, ensemble=None,
                          kabudragon=None, pts=None,
                          us_afterhours=None, cfd_sq=None,
                          upcoming=None, theme_ranking=None,
                          valuation=None) -> str:
    """
    通知②の詳細テキスト（4096文字以内・ボタン付きで送る）
    AIの3視点・シナリオ・テクニカル・セクター・予測精度・自律AIミッション
    """
    lines = [
        "📊 *本日の詳細AI分析*",
        "━━━━━━━━━━━━━━━━━━━━",
    ]

    # ── カテゴリA: AI分析（3視点・キャラ・シナリオ） ──
    lines += [_CAT + "0🤖 AI分析（3視点・シナリオ）"]

    # ── AI 3視点 ──
    ai = ai_summary or {}
    if ai.get("available"):
        bull = (ai.get("bull_view") or "")[:160].strip()
        bear = (ai.get("bear_view") or "")[:160].strip()
        neut = (ai.get("neutral_view") or "")[:200].strip()
        _blk = [
            "🤖 *AI 3視点分析*",
            f"📈 *強気派:* {bull}" if bull else "",
            f"📉 *弱気派:* {bear}" if bear else "",
            f"⚖️ *総合判断:* {neut}" if neut else "",
        ]
        lines += [""] + [l for l in _blk if l]

    # ── キャラクターコメント ──
    cc = character_comments or {}
    if cc.get("available"):
        if cc.get("ganesha"):
            lines += ["", f"🐘 *ガネーシャ:* {cc['ganesha'][:120]}"]
        if cc.get("otter"):
            lines += [f"🦦 *カワウソ:* {cc['otter'][:120]}"]

    # ── 3シナリオ ──
    sc = scenario or {}
    if sc.get("available"):
        bull_sc = sc.get("bull", {}); base_sc = sc.get("base", {}); bear_sc = sc.get("bear", {})
        lines += [
            "",
            "🎭 *3シナリオ分析*",
            f"🟢 楽観 {bull_sc.get('prob','?')}% — {(bull_sc.get('text','')[:70] or '---')}",
            f"🟡 基本 {base_sc.get('prob','?')}% — {(base_sc.get('text','')[:70] or '---')}",
            f"🔴 悲観 {bear_sc.get('prob','?')}% — {(bear_sc.get('text','')[:70] or '---')}",
        ]
        if sc.get("top_risk"):
            lines.append(f"⚡ 最大リスク: {sc['top_risk'][:80]}")

    # ── カテゴリB: シグナル・テクニカル・AI精度 ──
    lines += [_CAT + "0📊 シグナル・テクニカル・AI精度"]

    # ── マルチエージェント合議 ──
    mc = multi_consensus or {}
    if mc.get("available"):
        v   = mc.get("verdict", {})
        dir_icon = {"bull": "📈", "bear": "📉", "neutral": "➡️"}.get(v.get("direction",""), "")
        lines += [
            "",
            f"🤝 *4AI合議:* {dir_icon} {v.get('direction','---')} | {v.get('consensus_level','')} | 確信度 {v.get('consensus_confidence', '?')}",
        ]

    # ── アンサンブル予測 ──
    ens = ensemble or {}
    if ens.get("available"):
        dir_icon = {"bull": "📈", "bear": "📉", "neutral": "➡️"}.get(ens.get("direction",""), "")
        conf_icon = {"high": "🟢", "mid": "🟡", "low": "🔴"}.get(ens.get("confidence",""), "")
        brier = ens.get("brier_score")
        brier_s = f" | Brier={brier:.3f}" if brier is not None else ""
        lines += [
            "",
            f"🎯 *アンサンブル予測:* {dir_icon} *{ens.get('direction','---')}*"
            f" 一致率={ens.get('agreement_pct',0):.0f}% {conf_icon}{brier_s}",
        ]

    # ── テクニカル（日経225のみ） ──
    tech = technical or {}
    if tech.get("available"):
        results = tech.get("results", [])
        nk_res  = next((r for r in results if "225" in r.get("label","") or "N225" in r.get("symbol","")), None)
        if not nk_res and results:
            nk_res = results[0]
        if nk_res and "error" not in nk_res:
            rsi    = nk_res.get("rsi", 50)
            bb_pct = nk_res.get("bb_pct", 50)
            macd_h = nk_res.get("macd_hist", 0)
            rsi_s  = nk_res.get("rsi_signal", "")
            bb_s   = nk_res.get("bb_signal", "")
            rsi_e  = "🔴" if rsi > 70 else "🟢" if rsi < 30 else "🟡"
            lines += [
                "",
                "📐 *テクニカル（日経225）*",
                f"RSI: {rsi:.0f} {rsi_e} {rsi_s}　BB: {bb_pct:.0f}%　MACD: {macd_h:+.3f}",
            ]
        if tech.get("ai_comment"):
            lines.append(f"💬 {tech['ai_comment'][:100]}")

    # ── セクターローテーション ──
    sec = sector_analysis or {}
    if sec.get("available"):
        rot  = sec.get("rotation", {})
        top3 = sec.get("top3", [])
        top_str = "  ".join(f"{s['name']} {s['chg_1d']:+.1f}%" for s in top3[:2])
        _blk = [
            f"🌐 *セクター:* {rot.get('phase','---')}",
            f"🟢 強いセクター: {top_str}" if top_str else "",
        ]
        lines += [""] + [l for l in _blk if l]

    # ── テーマ株ランキング（上位3＋前回からの変動） ──
    th = theme_ranking or {}
    if th.get("available") and th.get("top5"):
        medals = ["🥇", "🥈", "🥉"]
        _blk = ["🔥 *人気テーマ*"]
        for i, r in enumerate(th["top5"][:3]):
            arrow = "▲" if r.get("perf_5d", 0) > 0 else "▼" if r.get("perf_5d", 0) < 0 else "➡"
            _blk.append(f"{medals[i]} {r['theme']} {arrow}{abs(r.get('perf_5d', 0)):.1f}% (ニュース{r.get('news_count', 0)}件)")
        for m in (th.get("movers") or [])[:3]:
            if m.get("kind") == "new":
                _blk.append(f"🆕 急浮上: *{m['theme']}*（圏外 → {m['rank']}位）")
            else:
                _blk.append(f"⬆️ 上昇中: *{m['theme']}*（{m['prev']}位 → {m['rank']}位）")
        lines += [""] + _blk
        if sec.get("ai_comment"):
            lines.append(f"💬 {sec['ai_comment'][:100]}")

    # ── 手法シグナル（押し目等） ──
    st = setups or {}
    if st.get("available") and st.get("setups"):
        top_setup = st["setups"][0] if st["setups"] else None
        if top_setup:
            lines += [
                "",
                f"🎯 *シグナル:* {top_setup.get('name','---')} / {top_setup.get('symbol','')} {top_setup.get('reason','')[:60]}",
            ]

    # ── AI予測精度 ──
    pt = prediction_tracker or {}
    if pt.get("available"):
        stats = pt.get("stats", {})
        r10   = stats.get("10d", {})
        rate  = r10.get("rate")
        if rate is not None:
            bar_e = "🎯" if rate >= 65 else "🔶" if rate >= 50 else "⚠️"
            bar_t = "█" * round(rate/10) + "░" * (10 - round(rate/10))
            today_pred = pt.get("today_prediction", {})
            dir_icon_map = {"bull":"📈 強気（上昇）","bear":"📉 弱気（下落）","neutral":"➡️ 中立（横ばい）"}
            dir_str = dir_icon_map.get(today_pred.get("direction",""), "")
            _blk = [
                f"🧠 *AI予測精度* (直近10日)",
                f"{bar_e} `{bar_t}` {rate}%  ({r10.get('correct',0)}/{r10.get('total',0)}日正解)",
                f"🎯 今日の予測: {dir_str}" if dir_str else "",
            ]
            lines += [""] + [l for l in _blk if l]

    # ── カテゴリC: マクロ・市場内部データ ──
    lines += [_CAT + "1🏛 マクロ・市場内部データ"]

    # ── 自律AIの今日のミッション ──
    ap = autonomous_plan or {}
    if ap.get("available") and ap.get("todays_mission"):
        lines += [
            "",
            f"🤖 *自律AIのミッション*",
            f"{ap['todays_mission'][:150]}",
        ]

    # ── マクロ一言 ──
    ma = macro or {}
    if ma.get("available") and ma.get("summary"):
        lines += [
            "",
            f"🌍 *マクロ:* {ma['summary'][:120]}",
        ]

    # ── 日経内部データ（騰落レシオ） ──
    nd = nikkei_internals or {}
    if nd.get("available") and nd.get("trk25"):
        trk = nd.get("trk25"); short = nd.get("short_ratio")
        trk_e = "🔴" if trk and trk > 120 else "🟢" if trk and trk < 80 else "🟡"
        lines += [
            "",
            f"📊 *東証内部:* 騰落レシオ25日={trk} {trk_e}" +
            (f"  空売り比率={short}%" if short else ""),
        ]

    # ── カテゴリD: 予定・イベント ──
    lines += [_CAT + "0📅 予定・イベント・先物"]

    up = upcoming or {}
    if up.get("available") and up.get("telegram_block"):
        lines += ["", up["telegram_block"]]

    # ── CFD/24時間先物・SQ（CME日経ギャップ・SQ日程） ──
    cf = cfd_sq or {}
    if cf.get("available") and cf.get("telegram_block"):
        lines += ["", cf["telegram_block"]]

    # ── カテゴリE: 夜間市場チェック ──
    lines += [_CAT + "1🌙 夜間市場チェック（寄り付き先行）"]

    # ── ADR（寄り付き先行ヒント） ──
    ad = adr or {}
    if ad.get("available") and ad.get("major_avg_divergence") is not None:
        div = ad["major_avg_divergence"]
        div_e = "🟢" if div > 0.5 else "🔴" if div < -0.5 else "🟡"
        lines += [
            "",
            f"🌙 *ADR寄り付き先行:* 主要平均乖離 {div:+.2f}% {div_e}",
        ]

    # ── 米国時間外ムーバー（ザラ場先行シグナル） ──
    us_ah = us_afterhours or {}
    if us_ah.get("available") and us_ah.get("telegram_block"):
        lines += ["", us_ah["telegram_block"]]

    # ── PTS夜間の急騰・急落（寄り付き先行ヒント） ──
    pt_data = pts or {}
    if pt_data.get("available") and pt_data.get("telegram_block"):
        lines += ["", pt_data["telegram_block"]]

    # ── 株ドラゴン デイトレランキング ──
    kd = kabudragon or {}
    if kd.get("available") and kd.get("telegram_block"):
        lines += ["", kd["telegram_block"]]

    # ── カテゴリF: 注目銘柄カルテ TOP3（合わせ技スコア順） ──
    lines += [_CAT + "0🎯 今日の注目銘柄カルテ"]
    sd = stock_dossier or {}
    top_dossiers = [d for d in sd.get("dossiers", []) if d.get("confluence", 0) >= 5][:3]
    if top_dossiers:
        for d in top_dossiers:
            chg = d.get("change_pct")
            chg_s = f"{chg:+.2f}%" if chg is not None else "---"
            close = d.get("close")
            close_s = f"{close:,.0f}円" if close else "---"
            conf = d.get("confluence", 0)
            tv = d.get("tv_link", "")
            _blk = [
                f"📌 *{d.get('name','?')}* ({d.get('code','')}) {close_s} {chg_s}",
                f"合わせ技スコア: *{conf}/10* | "
                f"目標: {d['target']:,.0f}円(+{d['upside']:.0f}%)" if d.get('target') else f"合わせ技スコア: *{conf}/10*",
                f"エントリー: {d.get('entry_zone','')}",
                f"損切り: {d.get('stop_loss','')}",
                f"[📈 TradingViewで確認]({tv})" if tv else "",
            ]
            lines += [""] + [l for l in _blk if l]

    return "\n".join(lines)


def _send_character_messages(character_comments: dict) -> None:
    """ガネーシャとカワウソのコメントをTelegramに送信"""
    if not character_comments or not character_comments.get("available"):
        return
    ganesha = character_comments.get("ganesha", "")
    otter = character_comments.get("otter", "")
    if ganesha or otter:
        msg = "🐘 *AIガネーシャ＆🦦 AIカワウソ*\n━━━━━━━━━━━━━━━\n"
        if ganesha:
            msg += f"🐘 *ガネーシャ*\n{ganesha}\n\n"
        if otter:
            msg += f"🦦 *カワウソ*\n{otter}"
        send_message(msg)
        logger.info("✅ キャラクターコメント送信")


def run(risk, analysis, report_paths, mode,
        prices=None, news=None,
        fear_greed=None, ai_summary=None,
        historical_analysis=None,
        chart_paths=None,
        weekly_calendar=None,
        agent_report=None,
        technical=None,
        portfolio=None,
        scenario=None,
        prediction_tracker=None,
        sector_analysis=None,
        fred_data=None,
        correlation=None,
        backtest=None,
        sentiment_data=None,
        monte_carlo=None,
        fomc_sentiment=None,
        congress_trades=None,
        multi_consensus=None,
        autonomous_plan=None,
        rl_result=None,
        multimodal=None,
        self_critique=None,
        reddit_sentiment=None,
        earnings_preview=None,
        market_chain=None,
        jquants=None,
        character_comments=None,
        macro=None, tdnet=None, earnings_brief=None, anomaly=None,
        catalyst=None,
        theme_ranking=None, financial_analysis=None,
        supply_demand=None, kabuyoho=None, sector_heatmap=None,
        nikkei_internals=None, adr=None, setups=None,
        stock_dossier=None, ensemble=None, kabudragon=None,
        pts=None, us_afterhours=None, cfd_sq=None, upcoming=None,
        valuation=None, macro_watch=None, market_signals=None,
        macro_regime=None, video_path=None) -> bool:

    if not _is_configured():
        logger.info("Telegram 設定なし。スキップします。")
        return False

    verify_bot()

    prices       = prices       or {}
    news         = news         or []
    fear_greed   = fear_greed   or {}
    ai_summary   = ai_summary   or {}
    chart_paths  = chart_paths  or {}
    report_paths = report_paths or {}

    try:
        # ════════════════════════════════════════════════════════
        # 朝レポート ─ 1通に集約
        #   サマリーカード画像 ＋ 寄り付き前チェックのキャプション
        #   ＋「フルレポートを開く」インラインボタン
        #   ※詳細（3シナリオ/合議/セクター/株ドラゴン等）はレポート側に集約
        # ════════════════════════════════════════════════════════
        caption = _build_unified_caption(
            risk, prices, fear_greed, ai_summary,
            setups=setups, prediction_tracker=prediction_tracker,
            us_afterhours=us_afterhours, pts=pts, adr=adr,
            kabudragon=kabudragon, valuation=valuation, macro_watch=macro_watch,
            market_signals=market_signals, macro_regime=macro_regime,
        )

        report_url = report_paths.get("url", "").strip()
        if not report_url:
            report_url = os.getenv("GITHUB_PAGES_URL",
                                   "https://youn24.github.io/market-ai-secretary") + "/daily_report.html"

        card_path = None
        try:
            from src.summary_card import make_summary_card
            card_path = make_summary_card(
                prices=prices, fear_greed=fear_greed, risk=risk,
                ai_summary=ai_summary, news=list(news),
                character_comments=character_comments,
            )
        except Exception:
            logger.error("サマリーカード生成エラー")
            logger.debug(traceback.format_exc())

        # 画像が作れなければ既存チャートで代替
        if not (card_path and os.path.exists(str(card_path))):
            for key in ("overview", "prices", "indices"):
                p = chart_paths.get(key, "")
                if p and os.path.exists(str(p)):
                    card_path = str(p)
                    break

        sent = False
        if card_path and os.path.exists(str(card_path)):
            sent = send_photo_with_button(
                str(card_path), caption=caption,
                button_text="📊 フルレポートを開く →",
                button_url=report_url,
            )
        if not sent:
            # 画像がまったく無い場合もテキスト1通で必ず届ける（無音を回避）
            sent = send_message_with_button(
                text=caption,
                button_text="📊 フルレポートを開く →",
                button_url=report_url,
            )

        logger.info(f"{'✅' if sent else '❌'} 朝レポート送信（1通）")
        return True

    except Exception as e:
        logger.error(f"Telegram通知エラー: {e}")
        logger.debug(traceback.format_exc())
        return False
