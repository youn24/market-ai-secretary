"""
Telegram通知モジュール（初心者でも一目でわかるデザイン）
"""
import os
import traceback
import requests
from dotenv import load_dotenv
from src.utils import setup_logger, get_today_str, get_jst_now

logger = setup_logger("notify_telegram")
load_dotenv()

# ────────────────────────────────────────────────────────────────
# 通知ヘッダー（通し番号＋タイトル＋時刻）と「配信もくじ」
# ────────────────────────────────────────────────────────────────

_WEEKDAYS_JA = ["月", "火", "水", "木", "金", "土", "日"]
_seq = 0          # 当日配信の通し番号
_toc: list = []   # もくじ用 (番号, タイトル)


def _now_label() -> str:
    n = get_jst_now()
    return f"{n.month}/{n.day}({_WEEKDAYS_JA[n.weekday()]}) {n.strftime('%H:%M')}"


def _stamp(title: str) -> str:
    """各通知の先頭に付ける統一ヘッダーを返し、もくじに登録する。
    例:
      ┌ No.04 ┃ 🎭 3シナリオ分析
      └ 🕒 6/12(金) 07:32
    """
    global _seq
    _seq += 1
    _toc.append(f"{_seq:02d}. {title}")
    return (
        f"┌ *No.{_seq:02d}* ┃ *{title}*\n"
        f"└ 🕒 {_now_label()}\n"
        f"━━━━━━━━━━━━━━━\n"
    )


def _reset_stamp() -> None:
    global _seq
    _seq = 0
    _toc.clear()


def _send_toc() -> None:
    """その日に送った全通知の「もくじ」を最後に1通送る"""
    if not _toc:
        return
    msg = (
        f"📑 *本日の配信もくじ*（全{len(_toc)}通）\n"
        f"🕒 {_now_label()}\n"
        f"━━━━━━━━━━━━━━━\n"
        + "\n".join(_toc)
        + "\n\n💡 No.番号を目印に上へスクロールすると、目的の通知がすぐ見つかります"
    )
    send_message(msg)
    logger.info("✅ 配信もくじ送信")


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


def _notable_stocks(prices: dict) -> str:
    """注目銘柄トップ3騰落・ワースト3騰落を返す"""
    watch = [
        ("^N225", "日経"), ("^GSPC", "S&P"), ("^IXIC", "NAS"),
        ("USDJPY=X", "ドル円"), ("GC=F", "金"), ("CL=F", "原油"),
        ("BTC-USD", "BTC"), ("^VIX", "VIX"),
    ]
    movers = []
    for sym, name in watch:
        chg = prices.get(sym, {}).get("change_pct")
        if chg is not None:
            movers.append((name, chg))
    if not movers:
        return ""
    movers.sort(key=lambda x: x[1], reverse=True)
    top3  = movers[:3]
    bot3  = movers[-3:]
    lines = []
    for name, chg in top3:
        lines.append(f"🟢 {name} {chg:+.2f}%")
    for name, chg in bot3:
        lines.append(f"🔴 {name} {chg:+.2f}%")
    return "\n".join(lines)


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
    tl, mood = _mood(score)
    fg_score = fear_greed.get("score") or 50
    fg_bar   = _fg_bar(fg_score)

    # VIX判定
    vix_val = prices.get("^VIX", {}).get("latest") or 0
    if   vix_val < 15: vix_icon, vix_txt = "🟢", "安定"
    elif vix_val < 20: vix_icon, vix_txt = "🟡", "やや不安"
    elif vix_val < 30: vix_icon, vix_txt = "🟠", "警戒"
    else:              vix_icon, vix_txt = "🔴", "危険！"

    # 信号機（大きく目立つように）
    if   score >= 2:    sig_line = "🟢🟢🟢 *強気シグナル！積極的に注目*"
    elif score >= 0.5:  sig_line = "🟢 *やや強気・通常ポジションOK*"
    elif score >= -0.5: sig_line = "🟡 *中立・様子見で問題なし*"
    elif score >= -2:   sig_line = "🟠 *要注意・リスク管理強化*"
    else:               sig_line = "🔴🔴🔴 *危険信号！守りのポジション*"

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 通知①：今日の相場まとめ（シンプル・わかりやすく）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    # ニュースをカテゴリ別に整理
    sorted_news = sorted(news, key=lambda x: {"A":0,"B":1,"C":2}.get(x.get("importance","C"),2))
    news_lines = []
    imp_icon   = {"A": "🔴", "B": "🟡", "C": "⚪"}
    for item in sorted_news:
        if len(news_lines) >= 8:
            break
        cat_count = sum(1 for l in news_lines if item.get("category","") in l)
        if cat_count < 2:
            icon  = imp_icon.get(item.get("importance","C"), "⚪")
            title = item.get("title", "")[:42]
            news_lines.append(f"{icon} {title}")

    # 注目銘柄
    notable = _notable_stocks(prices)

    msg1 = (
        f"*🚦 今日のシグナル*\n"
        f"{sig_line}\n"
        f"\n"
        f"*みんなの心理* 😱\n"
        f"`{fg_bar}`\n"
        f"  0=超怖い ← 50=普通 → 100=強気すぎ\n"
        f"\n"
        f"*📈 株価*\n"
        f"🇯🇵 日経:   {_fmt(prices,'^N225','円')}\n"
        f"🇺🇸 S&P:   {_fmt(prices,'^GSPC')}\n"
        f"🇺🇸 NAS:   {_fmt(prices,'^IXIC')}\n"
        f"\n"
        f"*💱 為替・商品*\n"
        f"💵 ドル円: {_fmt(prices,'USDJPY=X','円')}\n"
        f"🥇 金:     {_fmt(prices,'GC=F','$')}\n"
        f"🛢 原油:   {_fmt(prices,'CL=F','$')}\n"
        f"₿ BTC:    {_fmt(prices,'BTC-USD','$')}\n"
        f"\n"
        f"*⚡ 市場の怖さ（VIX）*\n"
        f"{vix_icon} {_fmt(prices,'^VIX')} → {vix_txt}\n"
    )
    if notable:
        msg1 += (
            f"━━━━━━━━━━━━━━━━━━\n"
            f"*📊 本日の注目騰落*\n"
            f"{notable}\n"
        )
    msg1 += (
        f"━━━━━━━━━━━━━━━━━━\n"
        f"*📰 今日のニュース（カテゴリ別）*\n"
        + "\n".join(news_lines)
    )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 通知②：AI分析（チャート画像キャプション）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    ai_lines = []
    if ai_summary.get("available"):
        bull = (ai_summary.get("bull_view") or "")[:100]
        bear = (ai_summary.get("bear_view") or "")[:100]
        neut = (ai_summary.get("neutral_view") or "")[:150]
        if bull: ai_lines.append(f"📈 *上がると思う理由*\n{bull}")
        if bear: ai_lines.append(f"📉 *下がると思う理由*\n{bear}")
        if neut: ai_lines.append(f"⚖️ *AIのまとめ*\n{neut}")
    else:
        ai_lines.append("🤖 AI分析を実行中...")

    msg2_caption = (
        f"（同じデータを3つのAIが議論）\n"
        + "\n\n".join(ai_lines)
    )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 通知③：レポートURL
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    report_url = report_paths.get("url", "")
    msg3 = (
        f"グラフ・チャート・AI分析を全部まとめて見れます\n\n"
        f"👇 iPhoneのSafariやChromeで開いてください\n"
        f"{report_url if report_url else '（準備中）'}\n"
        f"\n"
        f"📊 チャート  🤖 AI議論  📰 ニュース\n"
        f"📐 テクニカル  🎭 シナリオ  📅 カレンダー"
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

def _send_character_messages(character_comments: dict) -> None:
    """ガネーシャとカワウソのコメントをTelegramに送信"""
    if not character_comments or not character_comments.get("available"):
        return
    ganesha = character_comments.get("ganesha", "")
    otter = character_comments.get("otter", "")
    if ganesha or otter:
        msg = _stamp("🐘🦦 ガネ先生＆カワウソくん")
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
        tdnet=None,
        anomaly=None,
        supply_demand=None,
        character_comments=None) -> bool:
    if not _is_configured():
        logger.info("Telegram 設定なし。スキップします。")
        return False

    try:
        _reset_stamp()
        msgs = build_three_messages(
            risk, analysis, mode,
            prices=prices, news=news,
            fear_greed=fear_greed, ai_summary=ai_summary,
            report_paths=report_paths,
        )

        # ① 市場まとめ画像（新：サマリーカード → リスクゲージ → テキストの順でフォールバック）
        msg1_stamped = _stamp("📊 今日の市場まとめ") + msgs[0]
        msg1_sent = False
        # (1) サマリーカード（A案・一目でわかるカード型ビジュアル）
        try:
            from src.summary_card import make_summary_card
            card_path = make_summary_card(prices or {}, fear_greed or {}, risk or {})
            if card_path and os.path.exists(card_path):
                send_photo(card_path, caption=msg1_stamped)
                msg1_sent = True
                logger.info("✅ サマリーカード画像送信")
        except Exception as _e:
            logger.warning(f"サマリーカードスキップ: {_e}")
        # (2) フォールバック：従来のリスクゲージ画像
        if not msg1_sent:
            try:
                from src.risk_gauge import make_gauge_image
                gauge_path = make_gauge_image(risk, fear_greed or {}, prices or {})
                if gauge_path and os.path.exists(gauge_path):
                    send_photo(gauge_path, caption=msg1_stamped)
                    msg1_sent = True
                    logger.info("✅ リスクゲージ画像送信")
            except Exception as _e:
                logger.warning(f"ゲージ画像スキップ: {_e}")
        # (3) 最終フォールバック：テキストのみ
        if not msg1_sent:
            send_message(msg1_stamped)

        # ①.5 キャラクターコメント（ガネーシャ＆カワウソ）
        _send_character_messages(character_comments)

        # ② AI分析チャート画像 + キャプション
        msg2_stamped = _stamp("🤖 AI 3視点分析") + msgs[1]
        chart_sent = False
        if chart_paths:
            for key in ["overview", "prices", "indices"]:
                path = chart_paths.get(key, "")
                if path and os.path.exists(str(path)):
                    send_photo(str(path), caption=msg2_stamped)
                    chart_sent = True
                    break
        if not chart_sent:
            send_message(msg2_stamped)

        # ③ レポートURL
        send_message(_stamp("📱 詳細レポートURL") + msgs[2])

        # ③.5 TDnet適時開示アラート（ウォッチリスト銘柄の決算・自社株買い等）
        if tdnet and tdnet.get("available") and tdnet.get("telegram_message"):
            send_message(_stamp("📋 適時開示アラート") + tdnet["telegram_message"])

        # ③.6 今日のアノマリー（相場の経験則）
        if anomaly and anomaly.get("available") and anomaly.get("telegram_message"):
            send_message(_stamp("📜 今日のアノマリー") + anomaly["telegram_message"])

        # ③.7 需給分析ランキング（月曜のみ）
        if supply_demand and supply_demand.get("available") and supply_demand.get("telegram_message"):
            send_message(_stamp("📊 需給分析ランキング") + supply_demand["telegram_message"])

        # ④ Level 3: シナリオ分析テキスト
        if scenario and scenario.get("available"):
            bull = scenario.get("bull",{}); base = scenario.get("base",{}); bear = scenario.get("bear",{})
            sc_msg = (
                _stamp("🎭 3シナリオ分析")
                + f"🟢 楽観 {bull.get('prob','?')}% — {(bull.get('text','')[:80] or '---')}\n\n"
                f"🟡 基本 {base.get('prob','?')}% — {(base.get('text','')[:80] or '---')}\n\n"
                f"🔴 悲観 {bear.get('prob','?')}% — {(bear.get('text','')[:80] or '---')}"
            )
            if scenario.get("top_risk"):
                sc_msg += f"\n\n⚡ *最注目リスク*\n{scenario['top_risk'][:100]}"
            send_message(sc_msg)

        # ⑤ Level 3: テクニカル分析チャート
        if technical and technical.get("chart_path") and os.path.exists(str(technical["chart_path"])):
            ai_c = technical.get("ai_comment","")[:300]
            send_photo(str(technical["chart_path"]), caption=_stamp("📐 テクニカル分析") + ai_c)

        # ⑥ Level 3: ポートフォリオ
        if portfolio and portfolio.get("available") and portfolio.get("chart_path"):
            if os.path.exists(str(portfolio["chart_path"])):
                total_pct = portfolio.get("total_pnl_pct",0)
                arrow = "▲" if total_pct>=0 else "▼"
                pf_cap = _stamp("💼 ポートフォリオ損益") + f"総損益: {arrow}{abs(total_pct):.2f}%"
                for a in portfolio.get("alerts",[]):
                    pf_cap += f"\n{a.get('msg','')}"
                send_photo(str(portfolio["chart_path"]), caption=pf_cap)

        # ⑦ 予測学習レポート（蓄積3件以上の場合のみ）
        if prediction_tracker and prediction_tracker.get("available"):
            stats = prediction_tracker.get("stats", {})
            r10   = stats.get("10d", {})
            rate  = r10.get("rate")
            total = stats.get("total_verified", 0)
            if total >= 3 and rate is not None:
                # 正解率バー（テキスト）
                filled = round(rate / 10)
                bar    = "█" * filled + "░" * (10 - filled)
                bar_emoji = "🎯" if rate >= 65 else "🔶" if rate >= 50 else "⚠️"
                # 直近5日
                recent_lines = []
                icons_d = {"bull":"📈","bear":"📉","neutral":"➡️"}
                for r in stats.get("recent5", []):
                    mark = "✅" if r.get("correct") else "❌" if r.get("correct") is False else "⏳"
                    icon = icons_d.get(r.get("direction",""),"")
                    move = f"{r['move']:+.1f}%" if r.get("move") is not None else ""
                    recent_lines.append(f"  {mark} {r.get('date','')[-5:]} {icon} → {move}")

                pt_msg = (
                    _stamp("🧠 AI予測学習レポート")
                    + f"{bar_emoji} 直近10日の正解率\n"
                    f"`{bar}` {rate}%\n"
                    f"({r10.get('correct',0)}/{r10.get('total',0)}日正解)\n"
                )
                if stats.get("10d",{}).get("bull_acc") is not None:
                    pt_msg += f"  📈 強気予測: {stats['10d']['bull_acc']}%  "
                if stats.get("10d",{}).get("bear_acc") is not None:
                    pt_msg += f"📉 弱気予測: {stats['10d']['bear_acc']}%\n"
                if recent_lines:
                    pt_msg += "\n*直近の結果*\n" + "\n".join(recent_lines)
                # 今日の予測
                today_pred = prediction_tracker.get("today_prediction", {})
                if today_pred:
                    dir_icon = {"bull":"📈 強気（上昇)","bear":"📉 弱気（下落）","neutral":"➡️ 中立（横ばい）"}.get(today_pred.get("direction","neutral"),"")
                    pt_msg += f"\n\n*今日のAI予測:* {dir_icon}\n（明日の結果で検証します）"
                send_message(pt_msg)
                logger.info("✅ 予測学習レポート送信")

        # ⑧ セクター分析チャート
        if sector_analysis and sector_analysis.get("available"):
            rot = sector_analysis.get("rotation", {})
            top3 = sector_analysis.get("top3", [])
            bot3 = sector_analysis.get("bottom3", [])
            ai_c = sector_analysis.get("ai_comment", "")[:200]

            top_str = "  ".join(f"{s['name']} {s['chg_1d']:+.1f}%" for s in top3)
            bot_str = "  ".join(f"{s['name']} {s['chg_1d']:+.1f}%" for s in bot3)

            sec_caption = (
                _stamp("🌐 米国セクター分析")
                + f"📊 フェーズ: {rot.get('phase','---')}\n"
                f"{rot.get('label','')}\n\n"
                f"🟢 強いセクター\n  {top_str}\n"
                f"🔴 弱いセクター\n  {bot_str}\n"
            )
            if ai_c:
                sec_caption += f"\n🤖 AI分析\n{ai_c}"

            sec_path = chart_paths.get("sector", "") if chart_paths else ""
            if sec_path and os.path.exists(str(sec_path)):
                send_photo(str(sec_path), caption=sec_caption)
            else:
                send_message(sec_caption)
            logger.info("✅ セクター分析送信")

        # ⑨ 長期歴史データ分析
        if historical_analysis and historical_analysis.get("available"):
            reg = historical_analysis.get("regime", {})
            stats = historical_analysis.get("stats", {})
            similar = historical_analysis.get("similar_periods", [])

            sp_st = stats.get("sp500", {})
            vix_st = stats.get("vix", {})
            nk_st = stats.get("nikkei", {})

            hist_lines = [
                _stamp("📚 長期歴史分析（過去20年）").rstrip("\n"),
                f"🌡️ 市場レジーム: *{reg.get('regime','---')}*",
                f"{reg.get('description','')}",
                "",
            ]
            if sp_st:
                hist_lines.append(f"📊 S\\&P500: {sp_st.get('percentile',0):.0f}%ile（過去20年中の位置）")
                hist_lines.append(f"   ATHから{sp_st.get('from_ath_pct',0):.1f}%")
            if nk_st:
                hist_lines.append(f"🗾 日経225: {nk_st.get('percentile',0):.0f}%ile  ATHから{nk_st.get('from_ath_pct',0):.1f}%")
            if vix_st:
                hist_lines.append(f"😱 VIX: {vix_st.get('percentile',0):.0f}%ile（{vix_st.get('current',0):.1f}）")

            if similar:
                hist_lines.append("")
                hist_lines.append("🔍 類似した過去の時期")
                for p in similar[:2]:
                    hist_lines.append(f"  • {p['year']}年頃: VIX={p['vix']}  下落率={p['drawdown']}%")

            send_message("\n".join(hist_lines))
            logger.info("✅ 歴史分析送信")

        # ⑩ FRED経済指標
        if fred_data and fred_data.get("available"):
            from src.fred_data import format_telegram as fmt_fred
            msg = fmt_fred(fred_data)
            if msg:
                send_message(_stamp("🏦 FRED経済指標") + msg)
                logger.info("✅ FRED指標送信")

        # ⑪ センチメント複合データ（P/C比率・AAII）
        if sentiment_data and sentiment_data.get("available"):
            pc = sentiment_data.get("put_call", {})
            overall = sentiment_data.get("overall_signal", "")
            lines = [
                _stamp("📊 市場センチメント").rstrip("\n"),
                f"総合: {overall}",
            ]
            if pc.get("available") and pc.get("value"):
                lines.append(f"📉 P/C比率: {pc['value']:.2f} {pc.get('signal','')}")
            aaii = sentiment_data.get("aaii", {})
            if aaii.get("available"):
                lines.append(
                    f"👥 AAII個人投資家: 強気{aaii.get('bullish',0):.0f}%"
                    f" / 弱気{aaii.get('bearish',0):.0f}%"
                )
                if aaii.get("note"):
                    lines.append(f"   {aaii['note']}")
            send_message("\n".join(lines))
            logger.info("✅ センチメント送信")

        # ⑫ 相関分析チャート
        if correlation and correlation.get("available"):
            key = correlation.get("key", {})
            insights = correlation.get("insights", [])
            cap_lines = [
                _stamp("🔗 資産間 相関分析（2年）").rstrip("\n"),
            ]
            if key.get("nikkei_usdjpy") is not None:
                r = key["nikkei_usdjpy"]
                cap_lines.append(f"日経↔ドル円: r={r:.2f} {'（強い連動）' if abs(r)>0.6 else '（中程度）'}")
            if key.get("nikkei_sp500") is not None:
                r = key["nikkei_sp500"]
                cap_lines.append(f"日経↔S&P500: r={r:.2f} {'（強い連動）' if abs(r)>0.6 else '（中程度）'}")
            top_insight = next((i for i in insights if i.get("comment")), None)
            if top_insight:
                cap_lines.append(f"\n💡 {top_insight['comment']}")
            corr_path = chart_paths.get("correlation", "") if chart_paths else ""
            if corr_path and os.path.exists(str(corr_path)):
                send_photo(str(corr_path), caption="\n".join(cap_lines))
            else:
                send_message("\n".join(cap_lines))
            logger.info("✅ 相関分析送信")

        # ⑬ バックテスト（月曜のみ）
        if backtest and backtest.get("available"):
            strategies = backtest.get("strategies", [])
            bt_lines = [
                _stamp("📐 バックテスト（S&P500 20年）").rstrip("\n"),
                f"🏆 最良戦略: {backtest.get('best_strategy','')}",
                "",
            ]
            for s in strategies:
                icon = "🥇" if s["name"] == backtest.get("best_strategy") else "•"
                bt_lines.append(
                    f"{icon} {s['name']}: CAGR {s['cagr']:.1f}%"
                    f" (BH:{s['bnh_cagr']:.1f}%) MaxDD{s['max_drawdown']:.1f}%"
                )
            bt_path = chart_paths.get("backtest", "") if chart_paths else ""
            if bt_path and os.path.exists(str(bt_path)):
                send_photo(str(bt_path), caption="\n".join(bt_lines))
            else:
                send_message("\n".join(bt_lines))
            logger.info("✅ バックテスト送信")

        # ⑭ モンテカルロ + マーコウィッツ（月曜のみ）
        if monte_carlo and monte_carlo.get("available"):
            mc = monte_carlo.get("monte_carlo", {})
            mz = monte_carlo.get("markowitz")
            p = mc.get("percentiles", {})
            mc_lines = [
                _stamp("🎲 モンテカルロ×効率的フロンティア").rstrip("\n"),
                f"📊 日経225 1年後シミュレーション（5,000回）",
                f"  🟢 楽観(95%ile): {p.get('p95', '---'):.1f}",
                f"  🟡 中央値(50%ile): {p.get('p50', '---'):.1f}",
                f"  🔴 悲観(5%ile):  {p.get('p5', '---'):.1f}",
                f"",
                f"  利益確率: *{mc.get('prob_profit','---')}%*",
                f"  10%超損失確率: {mc.get('prob_loss10','---')}%",
                f"  年率リターン(期待値): {mc.get('mu_annual','---')}%",
            ]
            if mz:
                ms = mz.get("max_sharpe", {})
                w = ms.get("weights", {})
                w_str = " / ".join(f"{k}:{v:.0f}%" for k, v in w.items() if v > 5)
                mc_lines += [
                    f"",
                    f"📐 最適配分（シャープ比最大）",
                    f"  {w_str}",
                    f"  期待リターン: {ms.get('return','---')}%  リスク: {ms.get('risk','---')}%",
                ]
            mc_path = chart_paths.get("monte_carlo", "") if chart_paths else ""
            if mc_path and os.path.exists(str(mc_path)):
                send_photo(str(mc_path), caption="\n".join(mc_lines))
            else:
                send_message("\n".join(mc_lines))
            logger.info("✅ モンテカルロ送信")

        # ⑮ FOMC議事録分析（月曜のみ）
        if fomc_sentiment and fomc_sentiment.get("available"):
            sent = fomc_sentiment.get("sentiment", {})
            fomc_lines = [
                _stamp("🏦 FOMC声明文 NLP分析").rstrip("\n"),
                f"📊 スタンス: *{sent.get('label','---')}*",
                f"  タカ派ワード: {sent.get('hawk_count',0)}個",
                f"  ハト派ワード: {sent.get('dove_count',0)}個",
                f"",
                f"🇯🇵 日本への影響: {fomc_sentiment.get('japan_impact','')}",
            ]
            ai = fomc_sentiment.get("ai_analysis", "")
            if ai:
                fomc_lines += ["", f"🤖 AI分析", ai]
            send_message("\n".join(fomc_lines))
            logger.info("✅ FOMC分析送信")

        # ⑯ 米議員株取引（月曜のみ）
        if congress_trades and congress_trades.get("available"):
            from src.congress_trading import format_telegram as fmt_ct
            msg = fmt_ct(congress_trades)
            if msg:
                send_message(_stamp("🏛 米議員の株取引") + msg)
                logger.info("✅ 議員取引送信")

        # ㉒ 自己批判エンジン（L5e）
        if self_critique and self_critique.get("available"):
            from src.self_critique import format_telegram as fmt_sc
            msg = fmt_sc(self_critique)
            if msg:
                send_message(_stamp("🔍 AI自己批判レポート") + msg)
                logger.info("✅ 自己批判送信")

        # ㉓ Reddit感情分析（L5f）
        if reddit_sentiment and reddit_sentiment.get("available"):
            from src.reddit_sentiment import format_telegram as fmt_reddit
            msg = fmt_reddit(reddit_sentiment)
            if msg:
                send_message(_stamp("📡 Reddit個人投資家の空気") + msg)
                logger.info("✅ Reddit感情送信")

        # ㉔ 決算前分析（L5g）
        if earnings_preview and earnings_preview.get("available"):
            from src.earnings_preview import format_telegram as fmt_ep
            msg = fmt_ep(earnings_preview)
            if msg:
                send_message(_stamp("📅 決算前チェック") + msg)
                logger.info("✅ 決算前分析送信")

        # ㉕ グローバル市場連鎖（L5h）
        if market_chain and market_chain.get("available"):
            from src.market_chain import format_telegram as fmt_chain
            msg = fmt_chain(market_chain)
            if msg:
                send_message(_stamp("🌏 世界市場の連鎖分析") + msg)
                logger.info("✅ 市場連鎖送信")

        # ㉖ J-Quants日本株スクリーナー（L5j・月曜のみ）
        if jquants and jquants.get("available"):
            from src.jquants_screener import format_telegram as fmt_jq
            msg = fmt_jq(jquants)
            if msg:
                send_message(_stamp("🗾 日本株スクリーナー") + msg)
                logger.info("✅ J-Quants送信")

        # ⑱ マルチエージェント合議（L5a）
        if multi_consensus and multi_consensus.get("available"):
            from src.multi_agent_consensus import format_telegram as fmt_mac
            msg = fmt_mac(multi_consensus)
            if msg:
                send_message(_stamp("🗳 4AI多数決の結論") + msg)
                logger.info("✅ マルチエージェント合議送信")

        # ⑲ 完全自律エージェント（L5b）
        if autonomous_plan and autonomous_plan.get("available"):
            from src.autonomous_orchestrator import format_telegram as fmt_auto
            msg = fmt_auto(autonomous_plan)
            if msg:
                send_message(_stamp("🎯 今日のAIミッション") + msg)
                logger.info("✅ 自律エージェント送信")

        # ⑳ 強化学習ループ（L5c）
        if rl_result and (rl_result.get("available") or rl_result.get("total_verified", 0) > 0):
            from src.reinforcement_learning import format_telegram as fmt_rl
            msg = fmt_rl(rl_result)
            if msg:
                send_message(_stamp("♻️ 強化学習レポート") + msg)
                logger.info("✅ 強化学習送信")

        # ㉑ マルチモーダルVision分析（L5d）
        if multimodal and multimodal.get("available"):
            from src.multimodal_analysis import format_telegram as fmt_mm
            msg = fmt_mm(multimodal)
            if msg:
                send_message(_stamp("👁 チャートVision分析") + msg)
                logger.info("✅ Vision分析送信")

        # ⑰ 週次カレンダー（月曜朝のみ・画像送信）
        if weekly_calendar and weekly_calendar.get("available"):
            cal_path = weekly_calendar.get("image_path","")
            if cal_path and os.path.exists(str(cal_path)):
                n_events = len(weekly_calendar.get("events",[]))
                w_start  = weekly_calendar.get("week_start","")
                w_end    = weekly_calendar.get("week_end","")
                caption  = (
                    _stamp("📅 今週の注目イベント")
                    + f"📆 {w_start} 〜 {w_end}\n"
                    f"📋 全{n_events}件のイベントを掲載\n\n"
                    f"🔴 赤＝超重要  🟠 橙＝注目  🟣 紫＝決算\n"
                    f"⏰ 時刻はすべて日本時間の目安です"
                )
                send_photo(str(cal_path), caption=caption)
                logger.info("✅ 週次カレンダー画像送信完了")

            # 今後の決算予定（ウォッチリスト）+ 天体イベント
            upcoming = weekly_calendar.get("upcoming_earnings", []) or []
            astro    = weekly_calendar.get("astro", {}) or {}
            if upcoming or astro.get("mercury_now"):
                lines = [_stamp("🗓️ 決算予定＆イベント")]
                if upcoming:
                    lines.append("📊 *今後の決算予定（注目銘柄）*")
                    for u in upcoming[:8]:
                        d = u.get("date","")
                        md = f"{int(d[5:7])}/{int(d[8:10])}" if len(d) >= 10 else d
                        lines.append(f"  {md}  [{u.get('code','')}] {u.get('name','')}")
                    lines.append("")
                if astro.get("mercury_now"):
                    lines.append(f"☿ *水星逆行中*（{astro.get('mercury_period','')}）")
                    lines.append("　取引ミス・通信トラブルに注意の経験則")
                aev = astro.get("events", []) or []
                next_moon = next((e for e in aev if "月" in e.get("event","")), None)
                if next_moon:
                    nd = next_moon.get("date","")
                    nmd = f"{int(nd[5:7])}/{int(nd[8:10])}" if len(nd) >= 10 else nd
                    lines.append(f"{next_moon.get('event','')}　{nmd}")
                send_message("\n".join(lines))

        # 最後に「配信もくじ」を送信（全通知のタイトル一覧）
        _send_toc()

        logger.info("✅ Telegram 送信完了")
        return True

    except Exception as e:
        logger.error(f"Telegram通知エラー: {e}")
        logger.debug(traceback.format_exc())
        return False
