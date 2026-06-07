"""
週次レポート（毎週日曜日に自動実行）
1週間の振り返り・AI分析・来週の見通し
"""
import os
import sys
import json
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from src.utils import ensure_dirs, setup_logger, get_jst_now, get_today_str, get_dirs

logger = setup_logger("weekly_run")


def run():
    ensure_dirs()
    now = get_jst_now()
    logger.info(f"====== 週次レポート開始 {now.strftime('%Y-%m-%d')} ======")

    prices     = {}
    fear_greed = {"score": None, "rating_ja": "---"}
    news       = []
    risk       = {"score": 0, "sentiment": "不明", "signals": []}

    # データ取得
    try:
        from src.fetch_prices import run as fp
        prices, fear_greed = fp()
    except Exception:
        logger.error("価格取得エラー")

    try:
        from src.fetch_news import run as fn
        news = fn()
    except Exception:
        logger.error("ニュース取得エラー")

    try:
        from src.indicators import calc_risk_score
        risk = calc_risk_score(prices)
    except Exception:
        logger.error("リスク計算エラー")

    # 週次AI分析
    weekly_analysis = _generate_weekly_analysis(prices, news, risk, fear_greed)

    # YouTube要約
    youtube = {}
    try:
        from src.youtube_summary import run as yt_run
        youtube = yt_run(news)
    except Exception:
        logger.error("YouTube分析エラー")

    # 記憶更新
    try:
        from src.ai_memory import update_memory, analyze_with_memory
        memory = update_memory(prices, risk, fear_greed, {})
        memory_analysis = analyze_with_memory(prices, risk, fear_greed)
    except Exception:
        memory_analysis = ""

    # 来週のカレンダー生成
    calendar_data = {}
    try:
        from src.economic_calendar import run as run_cal
        calendar_data = run_cal()
    except Exception:
        logger.error("カレンダー生成エラー")

    # Telegram送信
    _send_weekly_report(weekly_analysis, youtube, memory_analysis, prices, fear_greed, risk, calendar_data)

    logger.info("====== 週次レポート完了 ======")


def _generate_weekly_analysis(prices, news, risk, fear_greed) -> dict:
    """Geminiで週次分析を生成"""
    import os
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return {"available": False}

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")

        # 過去1週間のニュース
        news_text = "\n".join(f"・{n.get('title','')}" for n in
                              sorted(news, key=lambda x: {"A":0,"B":1,"C":2}.get(x.get("importance","C"),2))[:15])

        def fmt(sym, unit=""):
            d = prices.get(sym, {})
            v = d.get("latest")
            chg = d.get("change_pct")
            if v is None: return "---"
            s = f"+{chg:.2f}%" if (chg or 0) >= 0 else f"{chg:.2f}%"
            return f"{v:,.2f}{unit}({s})"

        prompt = f"""あなたはプロの金融アナリストです。
今週の市場を振り返り、来週の見通しを分析してください。

【今週末の市場データ】
日経平均: {fmt('^N225','円')}
S&P500: {fmt('^GSPC')}
ドル円: {fmt('USDJPY=X','円')}
VIX: {fmt('^VIX')}
金: {fmt('GC=F','$')}
Bitcoin: {fmt('BTC-USD','$')}
地合い: {risk.get('sentiment','---')} (スコア:{risk.get('score',0):+.2f})
Fear&Greed: {fear_greed.get('score','---')} ({fear_greed.get('rating_ja','---')})

【今週の主要ニュース】
{news_text}

以下を分析してください：

【今週の総括】（200文字以内）
今週の市場を一言で表すと。

【来週の注目イベント】（150文字以内）
来週注目すべき経済指標・イベント（推測として）。

【来週の見通し】（200文字以内）
来週の市場方向性（推測として、断定禁止）。

【投資家へのメッセージ】（150文字以内）
来週に向けて投資家が意識すべき点。"""

        response = model.generate_content(prompt)
        result = response.text

        sections = {}
        current = "all"
        lines = []
        for line in result.split("\n"):
            if "今週の総括" in line:
                if lines: sections[current] = "\n".join(lines).strip()
                current = "summary"; lines = []
            elif "来週の注目" in line:
                if lines: sections[current] = "\n".join(lines).strip()
                current = "events"; lines = []
            elif "来週の見通し" in line:
                if lines: sections[current] = "\n".join(lines).strip()
                current = "outlook"; lines = []
            elif "投資家へのメッセージ" in line:
                if lines: sections[current] = "\n".join(lines).strip()
                current = "message"; lines = []
            else:
                if line.strip(): lines.append(line)
        if lines: sections[current] = "\n".join(lines).strip()

        return {
            "available": True,
            "summary": sections.get("summary", ""),
            "events":  sections.get("events", ""),
            "outlook": sections.get("outlook", ""),
            "message": sections.get("message", ""),
        }

    except Exception as e:
        logger.error(f"週次分析エラー: {e}")
        return {"available": False}


def _send_weekly_report(weekly, youtube, memory_analysis, prices, fear_greed, risk, calendar_data=None):
    """週次レポートをTelegramに送信"""
    try:
        from src.notify_telegram import send_message, send_photo
        from src.utils import get_today_str

        today = get_today_str()

        def fmt(sym, unit=""):
            d = prices.get(sym, {})
            v = d.get("latest")
            chg = d.get("change_pct")
            if v is None: return "---"
            s = f"{'▲' if (chg or 0)>=0 else '▼'}{abs(chg):.2f}%" if chg else ""
            return f"{v:,.2f}{unit} {s}"

        # メッセージ①：週次サマリー
        msg1 = "\n".join([
            f"📅 *週次マーケットレポート*",
            f"━━━━━━━━━━━━━━━",
            f"📊 今週末の主要指標",
            f"🇯🇵 日経: {fmt('^N225','円')}",
            f"🇺🇸 S&P: {fmt('^GSPC')}",
            f"💵 ドル円: {fmt('USDJPY=X','円')}",
            f"😰 VIX: {fmt('^VIX')}",
            f"₿ BTC: {fmt('BTC-USD','$')}",
            f"━━━━━━━━━━━━━━━",
            f"🌡 地合い: {risk.get('sentiment','---')}",
            f"😱 Fear&Greed: {fear_greed.get('score','---')} ({fear_greed.get('rating_ja','---')})",
        ])
        send_message(msg1)

        # メッセージ②：AI週次分析
        if weekly.get("available"):
            msg2_lines = ["🤖 *Gemini AI 週次分析*", "━━━━━━━━━━━━━━━"]
            if weekly.get("summary"):
                msg2_lines += ["📝 今週の総括", weekly["summary"], ""]
            if weekly.get("events"):
                msg2_lines += ["🎯 来週の注目イベント", weekly["events"], ""]
            if weekly.get("outlook"):
                msg2_lines += ["🔮 来週の見通し", weekly["outlook"], ""]
            if weekly.get("message"):
                msg2_lines += ["💌 投資家へのメッセージ", weekly["message"]]
            send_message("\n".join(msg2_lines))

        # メッセージ③：記憶分析＋YouTube
        msg3_lines = []
        if memory_analysis:
            msg3_lines += ["🧠 *AI記憶分析*", "━━━━━━━━━━━━━━━", memory_analysis, ""]
        if youtube.get("available"):
            msg3_lines += ["📺 *今週の注目動画まとめ*", "━━━━━━━━━━━━━━━"]
            if youtube.get("points"):
                msg3_lines += ["💡 動画のポイント", youtube["points"], ""]
            if youtube.get("impact"):
                msg3_lines += ["📊 市場への示唆", youtube["impact"]]
            for v in youtube.get("videos", [])[:3]:
                msg3_lines.append(f"🎬 {v['title']}")
        if msg3_lines:
            send_message("\n".join(msg3_lines))

        # 来週のカレンダー画像
        if calendar_data and calendar_data.get("available"):
            cal_path = calendar_data.get("image_path","")
            if cal_path and os.path.exists(str(cal_path)):
                n = len(calendar_data.get("events",[]))
                send_photo(str(cal_path), caption=(
                    f"📅 *来週のイベントスケジュール*\n"
                    f"━━━━━━━━━━━━━━━\n"
                    f"📋 全{n}件掲載\n"
                    f"🔴 赤=重要  🟠 橙=注目  🟣 紫=決算\n"
                    f"⏰ 時刻は日本時間・目安です"
                ))

        logger.info("✅ 週次レポートTelegram送信完了")

    except Exception as e:
        logger.error(f"週次送信エラー: {e}")


if __name__ == "__main__":
    run()
