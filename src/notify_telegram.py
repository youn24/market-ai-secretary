"""
Telegram通知モジュール（初心者でも一目でわかるデザイン）
"""
import os
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


def build_three_messages(risk, analysis, mode,
                         prices=None, news=None,
                         fear_greed=None, ai_summary=None,
                         report_paths=None) -> list:
    today      = get_today_str()
    prices     = prices or {}
    news       = news or []
    fear_greed = fear_greed or {}
    ai_summary = ai_summary or {}
    report_paths = report_paths or {}

    score    = risk.get("score", 0)
    signals  = risk.get("signals", [])
    tl, mood = _mood(score)
    fg_score = fear_greed.get("score") or 50
    fg_bar   = _fg_bar(fg_score)

    # VIX判定
    vix_val = prices.get("^VIX", {}).get("latest") or 0
    vix_comment = "低い=安定🟢" if vix_val < 15 else "注意が必要🟡" if vix_val < 20 else "高い=危険🔴"

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 通知①：市場速報（数字一覧）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    sorted_news = sorted(news, key=lambda x: {"A":0,"B":1,"C":2}.get(x.get("importance","C"),2))
    news_lines  = []
    imp_icon = {"A":"🔴","B":"🟡","C":"⚪"}
    for item in sorted_news[:6]:
        icon  = imp_icon.get(item.get("importance","C"), "⚪")
        title = item.get("title","")[:45]
        news_lines.append(f"{icon} {title}")

    msg1 = (
        f"📊 *市場AI秘書 [{today}]*\n"
        f"━━━━━━━━━━━━━━━\n"
        f"\n"
        f"🌡 *今日の相場*\n"
        f"{tl} *{mood}*  （スコア: {score:+.2f}）\n"
        f"\n"
        f"😱 恐怖＆強欲\n"
        f"`{fg_bar}`\n"
        f"\n"
        f"📈 *株価指数*\n"
        f"🇯🇵 日経平均:  {_fmt(prices,'^N225','円')}\n"
        f"🇺🇸 S\\&P 500: {_fmt(prices,'^GSPC')}\n"
        f"🇺🇸 NASDAQ:   {_fmt(prices,'^IXIC')}\n"
        f"\n"
        f"💱 *為替・コモディティ*\n"
        f"💵 ドル円:  {_fmt(prices,'USDJPY=X','円')}\n"
        f"🥇 金:      {_fmt(prices,'GC=F','$')}\n"
        f"🛢 原油:    {_fmt(prices,'CL=F','$')}\n"
        f"₿ BTC:     {_fmt(prices,'BTC-USD','$')}\n"
        f"\n"
        f"⚡ VIX: {_fmt(prices,'^VIX')}  → {vix_comment}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📰 *本日の重要ニュース*\n"
        + "\n".join(news_lines)
    )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 通知②：AI分析（画像キャプション用）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    ai_lines = []
    if ai_summary.get("available"):
        bull = (ai_summary.get("bull_view") or "")[:120]
        bear = (ai_summary.get("bear_view") or "")[:120]
        neut = (ai_summary.get("neutral_view") or "")[:160]
        if bull: ai_lines.append(f"📈 *強気AI*: {bull}")
        if bear: ai_lines.append(f"📉 *弱気AI*: {bear}")
        if neut: ai_lines.append(f"⚖️ *中立AI*: {neut}")
    else:
        ai_lines.append("🤖 AI分析準備中...")

    # シグナル
    sig_lines = []
    for s in signals[:3]:
        d     = s.get("direction","")
        arrow = "🔺" if any(k in d for k in ["上昇","強"]) else "🔻" if any(k in d for k in ["下落","弱"]) else "➡️"
        sig_lines.append(f"{arrow} {s.get('indicator','')}: {d}")

    msg2_caption = (
        f"🤖 *AI マルチ視点分析*\n"
        f"━━━━━━━━━━━━━━━\n"
        + "\n\n".join(ai_lines) + "\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🔍 *市場シグナル*\n"
        + ("\n".join(sig_lines) if sig_lines else "シグナルなし")
    )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 通知③：レポートリンク（Safari/Chrome で開く）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    report_url = report_paths.get("url","")
    msg3 = (
        f"📄 *本日の詳細レポート*\n"
        f"━━━━━━━━━━━━━━━\n"
        f"グラフ・チャート・AI分析をすべて見れます！\n\n"
        f"📱 iPhoneのSafariやChromeで開いてください👇\n"
        f"{report_url if report_url else '（レポート生成中）'}\n"
        f"\n"
        f"✅ チャート  ✅ AI議論  ✅ ニュース  ✅ 経済指標"
    )

    return [msg1, msg2_caption, msg3]


# ────────────────────────────────────────────────────────────────
# 低レベル送信関数
# ────────────────────────────────────────────────────────────────

def send_message(text: str) -> bool:
    if not _is_configured():
        logger.info("Telegram 未設定スキップ")
        return False
    token   = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=15,
        )
        r.raise_for_status()
        logger.info("Telegram テキスト送信 ✅")
        return True
    except Exception as e:
        logger.error(f"Telegram 送信失敗: {e}")
        return False


def send_photo(image_path: str, caption: str = "") -> bool:
    if not _is_configured():
        return False
    token   = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    try:
        with open(image_path, "rb") as f:
            r = requests.post(
                f"https://api.telegram.org/bot{token}/sendPhoto",
                data={"chat_id": chat_id, "caption": caption[:1024], "parse_mode": "Markdown"},
                files={"photo": f},
                timeout=30,
            )
        r.raise_for_status()
        logger.info(f"Telegram 画像送信 ✅: {image_path}")
        return True
    except Exception as e:
        logger.error(f"Telegram 画像送信失敗: {e}")
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

def run(risk, analysis, report_paths, mode,
        prices=None, news=None,
        fear_greed=None, ai_summary=None,
        chart_paths=None,
        weekly_calendar=None,
        agent_report=None,
        technical=None,
        portfolio=None,
        scenario=None) -> bool:
    if not _is_configured():
        logger.info("Telegram 設定なし。スキップします。")
        return False

    try:
        msgs = build_three_messages(
            risk, analysis, mode,
            prices=prices, news=news,
            fear_greed=fear_greed, ai_summary=ai_summary,
            report_paths=report_paths,
        )

        # ① 数字・ニュース速報
        send_message(msgs[0])

        # ② AI分析チャート画像 + キャプション
        chart_sent = False
        if chart_paths:
            for key in ["overview", "prices", "indices"]:
                path = chart_paths.get(key, "")
                if path and os.path.exists(str(path)):
                    send_photo(str(path), caption=msgs[1])
                    chart_sent = True
                    break
        if not chart_sent:
            send_message(msgs[1])

        # ③ レポートURL
        send_message(msgs[2])

        # ④ Level 3: シナリオ分析テキスト
        if scenario and scenario.get("available"):
            bull = scenario.get("bull",{}); base = scenario.get("base",{}); bear = scenario.get("bear",{})
            sc_msg = (
                "🎭 *3シナリオ分析*\n"
                "━━━━━━━━━━━━━━━\n"
                f"🟢 楽観 {bull.get('prob','?')}% — {(bull.get('text','')[:80] or '---')}\n\n"
                f"🟡 基本 {base.get('prob','?')}% — {(base.get('text','')[:80] or '---')}\n\n"
                f"🔴 悲観 {bear.get('prob','?')}% — {(bear.get('text','')[:80] or '---')}"
            )
            if scenario.get("top_risk"):
                sc_msg += f"\n\n⚡ *最注目リスク*\n{scenario['top_risk'][:100]}"
            send_message(sc_msg)

        # ⑤ Level 3: テクニカル分析チャート
        if technical and technical.get("chart_path") and os.path.exists(str(technical["chart_path"])):
            ai_c = technical.get("ai_comment","")[:300]
            send_photo(str(technical["chart_path"]), caption=f"📐 *テクニカル分析*\n{ai_c}")

        # ⑥ Level 3: ポートフォリオ
        if portfolio and portfolio.get("available") and portfolio.get("chart_path"):
            if os.path.exists(str(portfolio["chart_path"])):
                total_pct = portfolio.get("total_pnl_pct",0)
                arrow = "▲" if total_pct>=0 else "▼"
                pf_cap = f"💼 *ポートフォリオ損益*\n総損益: {arrow}{abs(total_pct):.2f}%"
                for a in portfolio.get("alerts",[]):
                    pf_cap += f"\n{a.get('msg','')}"
                send_photo(str(portfolio["chart_path"]), caption=pf_cap)

        # ⑧ 週次カレンダー（月曜朝のみ・画像送信）
        if weekly_calendar and weekly_calendar.get("available"):
            cal_path = weekly_calendar.get("image_path","")
            if cal_path and os.path.exists(str(cal_path)):
                n_events = len(weekly_calendar.get("events",[]))
                w_start  = weekly_calendar.get("week_start","")
                w_end    = weekly_calendar.get("week_end","")
                caption  = (
                    f"📅 *今週の注目イベントスケジュール*\n"
                    f"━━━━━━━━━━━━━━━\n"
                    f"📆 {w_start} 〜 {w_end}\n"
                    f"📋 全{n_events}件のイベントを掲載\n\n"
                    f"🔴 赤＝超重要  🟠 橙＝注目  🟣 紫＝決算\n"
                    f"⏰ 時刻はすべて日本時間の目安です"
                )
                send_photo(str(cal_path), caption=caption)
                logger.info("✅ 週次カレンダー画像送信完了")

        logger.info("✅ Telegram 送信完了")
        return True

    except Exception as e:
        logger.error(f"Telegram通知エラー: {e}")
        logger.debug(traceback.format_exc())
        return False
