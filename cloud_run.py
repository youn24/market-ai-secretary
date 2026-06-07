"""
クラウド実行スクリプト（GitHub Actions用）
PC電源OFFでもGitHub上で毎日自動実行される
"""
import argparse
import os
import sys
import traceback
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))
from src.utils import ensure_dirs, setup_logger, get_jst_now, get_dirs, get_today_str

logger = setup_logger("cloud_run")

PAGES_URL = os.getenv("GITHUB_PAGES_URL", "https://youn24.github.io/market-ai-secretary")


def run(mode: str):
    ensure_dirs()
    logger.info(f"====== クラウド実行開始 [mode={mode}] ======")
    logger.info(f"実行時刻(JST): {get_jst_now().strftime('%Y-%m-%d %H:%M:%S')}")

    prices      = {}
    fear_greed  = {"score": None, "rating_ja": "取得失敗"}
    news        = []
    risk        = {"score":0,"sentiment":"不明","meter":"NEUTRAL","signals":[]}
    analysis    = {}
    chart_paths = {}

    # Step 1: 価格取得
    try:
        logger.info("--- Step 1: 価格データ取得 ---")
        from src.fetch_prices import run as fp
        prices, fear_greed = fp()
        logger.info(f"価格取得: {sum(1 for v in prices.values() if v.get('latest'))}件")
    except Exception:
        logger.error("価格取得エラー"); logger.debug(traceback.format_exc())

    # Step 2: ニュース取得
    try:
        logger.info("--- Step 2: ニュース取得 ---")
        from src.fetch_news import run as fn
        news = fn()
    except Exception:
        logger.error("ニュース取得エラー"); logger.debug(traceback.format_exc())

    # Step 3: 追加ニュース
    try:
        logger.info("--- Step 3: 追加ニュース取得 ---")
        from src.fetch_extra_news import run as fen
        extra_news, _ = fen()
        news = news + extra_news
        logger.info(f"ニュース合計: {len(news)}件")
    except Exception:
        logger.error("追加ニュース取得エラー"); logger.debug(traceback.format_exc())

    # Step 4: 指標計算
    try:
        logger.info("--- Step 4: 指標計算 ---")
        from src.indicators import calc_risk_score
        risk = calc_risk_score(prices)
    except Exception:
        logger.error("指標計算エラー"); logger.debug(traceback.format_exc())

    # Step 5: 分析
    try:
        logger.info("--- Step 5: 分析 ---")
        from src.analyze import build_analysis
        analysis = build_analysis(prices, risk)
    except Exception:
        logger.error("分析エラー"); logger.debug(traceback.format_exc())

    # Step 5b: AI議論分析（強気・弱気・中立）
    ai_summary = {"available": False}
    try:
        logger.info("--- Step 5b: AI議論分析 ---")
        from src.ai_debate import run_ai_debate
        ai_summary = run_ai_debate(prices, news, risk, fear_greed)
        if ai_summary.get("available"):
            logger.info("✅ AI議論分析完了")
        else:
            logger.info("AI議論スキップ")
    except Exception:
        logger.error("AI議論エラー"); logger.debug(traceback.format_exc())

    # Step 5c: 経済指標分析
    econ_analysis = {"available": False}
    try:
        logger.info("--- Step 5c: 経済指標分析 ---")
        from src.economic_indicators import run as run_econ
        econ_analysis = run_econ(prices)
        if econ_analysis.get("available"):
            logger.info("✅ 経済指標分析完了")
    except Exception:
        logger.error("経済指標分析エラー"); logger.debug(traceback.format_exc())

    # Step 5d: YouTube動画要約
    youtube_summary = {"available": False}
    try:
        logger.info("--- Step 5d: YouTube動画要約 ---")
        from src.youtube_summary import run as run_yt
        youtube_summary = run_yt(news)
        if youtube_summary.get("available"):
            logger.info(f"✅ YouTube分析完了 ({len(youtube_summary.get('videos',[]))}件)")
    except Exception:
        logger.error("YouTube要約エラー"); logger.debug(traceback.format_exc())

    # Step 5f: 週次カレンダー（月曜朝のみ）
    weekly_calendar = {"available": False}
    try:
        from src.utils import get_jst_now
        weekday = get_jst_now().weekday()   # 0=月曜
        if weekday == 0 or mode == "test":
            logger.info("--- Step 5f: 週次カレンダー生成 ---")
            from src.economic_calendar import run as run_cal
            weekly_calendar = run_cal()
            if weekly_calendar.get("available"):
                logger.info("✅ 週次カレンダー生成完了")
        else:
            logger.info("週次カレンダー: 月曜以外のためスキップ")
    except Exception:
        logger.error("週次カレンダーエラー"); logger.debug(traceback.format_exc())

    # Step 5e: AI記憶更新・分析
    memory_analysis = ""
    try:
        logger.info("--- Step 5e: AI記憶更新 ---")
        from src.ai_memory import update_memory, analyze_with_memory
        update_memory(prices, risk, fear_greed, ai_summary)
        memory_analysis = analyze_with_memory(prices, risk, fear_greed)
        if memory_analysis:
            logger.info("✅ AI記憶分析完了")
    except Exception:
        logger.error("AI記憶エラー"); logger.debug(traceback.format_exc())

    # Step 6: チャート生成（matplotlibが使える場合）
    try:
        logger.info("--- Step 6: チャート生成 ---")
        from src.visualize import run as vis
        chart_paths = vis(prices, news, risk, fear_greed)
        logger.info(f"チャート生成: {len(chart_paths)}件")
    except Exception:
        logger.error("チャート生成エラー（続行）"); logger.debug(traceback.format_exc())

    # Step 7: HTMLレポート生成
    report_paths = {}
    try:
        logger.info("--- Step 7: HTMLレポート生成 ---")
        _save_html_report(mode, prices, news, risk, analysis, fear_greed, chart_paths, ai_summary, econ_analysis, youtube_summary, memory_analysis)
        today = get_today_str()
        report_paths = {
            "html": str(get_dirs()["reports"] / f"{today}_{mode}.html"),
            "md":   str(get_dirs()["reports"] / f"{today}_{mode}.md"),
            "url":  f"{PAGES_URL}/{today}_{mode}.html",
        }
    except Exception:
        logger.error("レポート生成エラー"); logger.debug(traceback.format_exc())

    # Step 8: Telegram通知
    try:
        logger.info("--- Step 8: Telegram通知 ---")
        from src.notify_telegram import run as notify_tg
        notify_tg(risk, analysis, report_paths, mode,
                  prices=prices, news=news,
                  fear_greed=fear_greed, ai_summary=ai_summary,
                  chart_paths=chart_paths,
                  weekly_calendar=weekly_calendar)
    except Exception:
        logger.error("Telegram通知エラー"); logger.debug(traceback.format_exc())

    logger.info(f"====== クラウド実行完了 ======")
    print(f"\n✅ 完了 | 地合い: {risk.get('sentiment')} | "
          f"F&G: {fear_greed.get('score')} ({fear_greed.get('rating_ja')}) | "
          f"ニュース: {len(news)}件 | チャート: {len(chart_paths)}件")


def _save_html_report(mode, prices, news, risk, analysis, fear_greed, chart_paths, ai_summary=None, econ_analysis=None, youtube_summary=None, memory_analysis=""):
    """初心者でもわかる見やすいダッシュボードHTMLを保存"""
    import base64
    today = get_today_str()
    dirs  = get_dirs()
    now   = get_jst_now().strftime("%Y-%m-%d %H:%M JST")

    sentiment  = risk.get("sentiment", "不明")
    score      = risk.get("score", 0)
    fg_score   = fear_greed.get("score") or 50
    fg_rating  = fear_greed.get("rating_ja", "---")
    signals    = risk.get("signals", [])
    ai_summary = ai_summary or {}
    ai_available = ai_summary.get("available", False)
    econ_analysis   = econ_analysis or {}
    youtube_summary = youtube_summary or {}

    # ── ヒーローの色・絵文字・メッセージを決定 ──────────────────
    if score >= 2:
        hero_color = "#00e676"; hero_bg = "linear-gradient(135deg,#0d2b1a,#0a1f14)"
        hero_emoji = "🚀"; hero_label = "強気相場"; hero_msg = "市場は元気！上昇ムードです"
        tl = "🟢"
    elif score >= 0.5:
        hero_color = "#69f0ae"; hero_bg = "linear-gradient(135deg,#0d2b1a,#112916)"
        hero_emoji = "😊"; hero_label = "やや強気"; hero_msg = "落ち着いた上昇傾向です"
        tl = "🟢"
    elif score >= -0.5:
        hero_color = "#ffd740"; hero_bg = "linear-gradient(135deg,#2b2200,#1a1600)"
        hero_emoji = "😐"; hero_label = "中立"; hero_msg = "どちらでもない様子見状態"
        tl = "🟡"
    elif score >= -2:
        hero_color = "#ff6e40"; hero_bg = "linear-gradient(135deg,#2b0d00,#1a0900)"
        hero_emoji = "😟"; hero_label = "やや弱気"; hero_msg = "少し不安定。注意しましょう"
        tl = "🟠"
    else:
        hero_color = "#ff1744"; hero_bg = "linear-gradient(135deg,#2b0000,#1a0000)"
        hero_emoji = "😱"; hero_label = "弱気相場"; hero_msg = "荒れた相場！慎重に！"
        tl = "🔴"

    # Fear&Greed バー色
    fg_int = int(fg_score)
    if fg_int >= 75:   fg_color = "#ff1744"; fg_emoji = "😱"; fg_desc = "超強欲（バブルに注意！）"
    elif fg_int >= 55: fg_color = "#ff6d00"; fg_emoji = "😤"; fg_desc = "強欲（強気が多い）"
    elif fg_int >= 45: fg_color = "#ffd740"; fg_emoji = "😐"; fg_desc = "中立（拮抗状態）"
    elif fg_int >= 25: fg_color = "#40c4ff"; fg_emoji = "😰"; fg_desc = "恐怖（弱気が多い）"
    else:              fg_color = "#7c4dff"; fg_emoji = "😭"; fg_desc = "超恐怖（チャンスかも）"

    def p_val(sym):
        v = prices.get(sym, {}).get("latest")
        return f"{v:,.2f}" if v else "---"

    def p_chg(sym):
        chg = prices.get(sym, {}).get("change_pct")
        if chg is None: return "---", "neutral", "➡️"
        if chg >= 0:  return f"+{chg:.2f}%", "up",   "▲"
        else:         return f"{chg:.2f}%",  "down", "▼"

    def img_b64(key):
        path = chart_paths.get(key, "")
        if not path or not Path(path).exists(): return ""
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        return f'<img src="data:image/png;base64,{b64}" class="chart-img" loading="lazy">'

    # ── 価格カード (大きめ・説明付き) ─────────────────────────
    def big_card(emoji, label, sym, unit="", hint=""):
        val = p_val(sym)
        chg_str, cls, arrow = p_chg(sym)
        chg_color = "#00e676" if cls=="up" else "#ff4444" if cls=="down" else "#8899aa"
        bg_shine  = "rgba(0,230,118,0.06)" if cls=="up" else "rgba(255,68,68,0.06)" if cls=="down" else "transparent"
        return f'''<div class="bcard" style="background:{bg_shine};">
          <div class="bcard-top"><span class="bcard-emoji">{emoji}</span><span class="bcard-label">{label}</span></div>
          <div class="bcard-val">{val}<span class="bcard-unit">{unit}</span></div>
          <div class="bcard-chg" style="color:{chg_color};">{arrow} {chg_str}</div>
          {f'<div class="bcard-hint">{hint}</div>' if hint else ""}
        </div>'''

    # ── ニュースHTML ───────────────────────────────────────
    sorted_news = sorted(news, key=lambda x: {"A":0,"B":1,"C":2}.get(x.get("importance","C"),2))
    news_html = ""
    imp_label = {"A":"🔴 重要","B":"🟡 注目","C":"⚪ 情報"}
    for item in sorted_news[:18]:
        imp   = item.get("importance","C")
        title = item.get("title","")
        src   = item.get("source_name") or item.get("source","")
        url   = item.get("url","")
        cat   = item.get("category","")
        badge_color = "#ff4444" if imp=="A" else "#ffd740" if imp=="B" else "#444"
        badge_text  = imp_label.get(imp, "")
        link  = f'<a href="{url}" target="_blank" rel="noopener">{title}</a>' if url else title
        news_html += f'''<div class="news-row">
          <span class="nbadge" style="background:{badge_color};">{badge_text}</span>
          <span class="ncat">{cat}</span>
          <span class="ntitle">{link}</span>
          <span class="nsrc">{src}</span>
        </div>'''

    # ── AIディベート (吹き出しスタイル) ───────────────────────
    def bubble(icon, title, color, text, bg):
        return f'''<div class="bubble" style="border-left:4px solid {color};background:{bg};">
          <div class="bubble-head" style="color:{color};">{icon} {title}</div>
          <div class="bubble-text">{text}</div>
        </div>'''

    ai_html = ""
    if ai_available:
        ai_html += bubble("📈","強気派AI（上がると思う理由）","#00e676","linear-gradient(135deg,#0a1f10,#0d2b18)",
                          ai_summary.get("bull_view","---"))
        ai_html += bubble("📉","弱気派AI（下がると思う理由）","#ff4444","linear-gradient(135deg,#1f0a0a,#2b0d0d)",
                          ai_summary.get("bear_view","---"))
        ai_html += bubble("⚖️","中立AI（総合まとめ）","#ffd740","linear-gradient(135deg,#1f1a00,#2b2400)",
                          ai_summary.get("neutral_view","---"))
        if ai_summary.get("history_comment"):
            ai_html += bubble("📊","過去データと比べると…","#40c4ff","linear-gradient(135deg,#001a2b,#00111f)",
                              ai_summary.get("history_comment",""))
    else:
        ai_html = '<div class="bubble" style="border-left:4px solid #555;">AI分析準備中...</div>'

    # ── 経済指標HTML ──────────────────────────────────────
    econ_html = ""
    if econ_analysis.get("available"):
        rows = [
            ("🌍","今の経済状況は？",      econ_analysis.get("status","")),
            ("🎯","今週の注目ポイント",      econ_analysis.get("focus","")),
            ("💹","株・為替への影響は？",    econ_analysis.get("impact","")),
            ("💡","気をつけること",          econ_analysis.get("hint","")),
        ]
        for icon, lbl, txt in rows:
            if txt:
                econ_html += f'<div class="econ-row"><span class="econ-icon">{icon}</span><div><div class="econ-lbl">{lbl}</div><div class="econ-txt">{txt}</div></div></div>'

    # ── YouTube HTML ──────────────────────────────────────
    yt_html = ""
    if youtube_summary.get("available"):
        if youtube_summary.get("points"):
            yt_html += f'<div class="yt-section"><div class="yt-head">💡 動画のポイント</div><div class="yt-text">{youtube_summary["points"]}</div></div>'
        if youtube_summary.get("impact"):
            yt_html += f'<div class="yt-section"><div class="yt-head">📊 市場への示唆</div><div class="yt-text">{youtube_summary["impact"]}</div></div>'
        for v in youtube_summary.get("videos",[])[:4]:
            yt_html += f'<div class="yt-video"><span>🎬</span><a href="{v.get("url","")}" target="_blank" rel="noopener">{v.get("title","")}</a></div>'

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1">
<title>市場AI秘書 📊 {today}</title>
<style>
/* ══════════════════════════════════════
   リセット＆ベース
══════════════════════════════════════ */
*,*::before,*::after{{margin:0;padding:0;box-sizing:border-box;}}
:root{{
  --bg:#090d14; --card:#0f1623; --card2:#141d2b;
  --border:#1e2d42; --accent:#00d4ff; --accent2:#7b61ff;
  --up:#00e676; --down:#ff4444; --text:#dde8ff; --text2:#7a8fa8;
  --gold:#ffd740; --radius:16px;
}}
html{{scroll-behavior:smooth;}}
body{{background:var(--bg);color:var(--text);
  font-family:'Hiragino Sans','Noto Sans JP','Meiryo',system-ui,sans-serif;
  min-height:100vh;font-size:15px;line-height:1.6;}}
a{{color:var(--accent);text-decoration:none;}}
a:hover{{text-decoration:underline;}}

/* ══════════════════════════════════════
   ヘッダー
══════════════════════════════════════ */
.header{{
  background:linear-gradient(90deg,#0a0f1c,#111830);
  border-bottom:1px solid var(--border);
  padding:14px 20px;
  display:flex;align-items:center;justify-content:space-between;
  position:sticky;top:0;z-index:100;backdrop-filter:blur(10px);
}}
.header-logo{{font-size:1.2em;font-weight:800;
  background:linear-gradient(90deg,var(--accent),var(--accent2));
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;}}
.header-date{{color:var(--text2);font-size:0.8em;}}

/* ══════════════════════════════════════
   ヒーローカード（今日の相場）
══════════════════════════════════════ */
.hero{{
  {hero_bg};
  border:1px solid {hero_color}44;
  border-radius:var(--radius);
  padding:28px 20px;
  text-align:center;
  margin:16px 0;
  position:relative;overflow:hidden;
}}
.hero::after{{
  content:'';position:absolute;top:-40px;right:-40px;
  width:160px;height:160px;border-radius:50%;
  background:{hero_color}15;
}}
.hero-emoji{{font-size:3.5em;display:block;margin-bottom:8px;}}
.hero-label{{font-size:1.9em;font-weight:900;color:{hero_color};margin-bottom:6px;}}
.hero-msg{{color:#aac;font-size:1em;margin-bottom:12px;}}
.hero-score{{
  display:inline-block;background:{hero_color}22;
  border:1px solid {hero_color}55;border-radius:30px;
  padding:4px 18px;color:{hero_color};font-size:0.9em;font-weight:700;
}}

/* ══════════════════════════════════════
   クイック3ステータス
══════════════════════════════════════ */
.quick-row{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:16px;}}
.qcard{{
  background:var(--card);border:1px solid var(--border);
  border-radius:var(--radius);padding:14px 10px;text-align:center;
}}
.qcard-icon{{font-size:1.8em;margin-bottom:4px;}}
.qcard-label{{color:var(--text2);font-size:0.7em;margin-bottom:6px;letter-spacing:0.5px;}}
.qcard-val{{font-size:1.3em;font-weight:800;}}
.qcard-sub{{font-size:0.72em;color:var(--text2);margin-top:3px;}}

/* Fear & Greed メーター */
.fg-bar-wrap{{
  background:var(--card);border:1px solid var(--border);
  border-radius:var(--radius);padding:18px;margin-bottom:16px;
}}
.fg-bar-title{{font-size:0.95em;font-weight:700;margin-bottom:4px;}}
.fg-bar-desc{{color:var(--text2);font-size:0.8em;margin-bottom:12px;}}
.fg-rail{{background:#1e2d42;border-radius:8px;height:20px;position:relative;overflow:hidden;}}
.fg-fill{{height:100%;border-radius:8px;
  background:linear-gradient(90deg,#7c4dff,#40c4ff,#ffd740,#ff6d00,#ff1744);
  transition:width 0.8s ease;}}
.fg-needle{{
  position:absolute;top:-4px;width:4px;height:28px;
  background:#fff;border-radius:2px;transform:translateX(-2px);
  box-shadow:0 0 8px #fff8;
}}
.fg-labels{{display:flex;justify-content:space-between;margin-top:6px;font-size:0.68em;color:var(--text2);}}
.fg-cur{{text-align:center;margin-top:10px;font-size:1.5em;font-weight:900;color:{fg_color};}}
.fg-cur-label{{text-align:center;color:{fg_color};font-size:0.85em;margin-top:2px;}}

/* ══════════════════════════════════════
   価格カードグリッド
══════════════════════════════════════ */
.sec-head{{
  display:flex;align-items:center;gap:8px;
  color:var(--accent);font-size:0.8em;font-weight:700;
  letter-spacing:1.5px;text-transform:uppercase;
  margin:20px 0 10px;padding-left:10px;
  border-left:3px solid var(--accent);
}}
.bcard-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-bottom:16px;}}
.bcard{{
  background:var(--card);border:1px solid var(--border);
  border-radius:var(--radius);padding:14px;
  transition:transform 0.15s,box-shadow 0.15s;cursor:default;
}}
.bcard:hover{{transform:translateY(-2px);box-shadow:0 6px 20px rgba(0,212,255,0.12);}}
.bcard-top{{display:flex;align-items:center;gap:6px;margin-bottom:6px;}}
.bcard-emoji{{font-size:1.4em;}}
.bcard-label{{color:var(--text2);font-size:0.75em;}}
.bcard-val{{font-size:1.35em;font-weight:800;margin-bottom:3px;}}
.bcard-unit{{font-size:0.65em;font-weight:400;color:var(--text2);margin-left:2px;}}
.bcard-chg{{font-size:0.85em;font-weight:700;}}
.bcard-hint{{color:var(--text2);font-size:0.7em;margin-top:5px;border-top:1px solid var(--border);padding-top:4px;}}

/* ══════════════════════════════════════
   チャート
══════════════════════════════════════ */
.chart-img{{width:100%;border-radius:12px;margin:8px 0;border:1px solid var(--border);display:block;}}
.tv-wrap{{
  background:var(--card);border:1px solid var(--border);
  border-radius:var(--radius);padding:12px;margin-bottom:16px;overflow:hidden;
}}

/* ══════════════════════════════════════
   AIディベート 吹き出し
══════════════════════════════════════ */
.debate-wrap{{margin-bottom:16px;}}
.debate-intro{{
  background:linear-gradient(135deg,#0a0f20,#0f1430);
  border:1px solid #7b61ff44;border-radius:var(--radius);
  padding:14px 16px;margin-bottom:12px;
  color:var(--text2);font-size:0.85em;line-height:1.7;
}}
.bubble{{
  border-radius:var(--radius);padding:16px;margin-bottom:10px;
  transition:transform 0.15s;
}}
.bubble:hover{{transform:translateX(4px);}}
.bubble-head{{font-size:0.9em;font-weight:800;margin-bottom:8px;}}
.bubble-text{{font-size:0.88em;line-height:1.75;white-space:pre-wrap;}}

/* ══════════════════════════════════════
   経済指標
══════════════════════════════════════ */
.econ-wrap{{
  background:var(--card);border:1px solid var(--border);
  border-radius:var(--radius);padding:16px;margin-bottom:16px;
}}
.econ-row{{
  display:flex;align-items:flex-start;gap:12px;
  padding:10px 0;border-bottom:1px solid var(--border);
}}
.econ-row:last-child{{border-bottom:none;}}
.econ-icon{{font-size:1.6em;flex-shrink:0;margin-top:2px;}}
.econ-lbl{{color:var(--accent2);font-size:0.75em;font-weight:700;margin-bottom:4px;}}
.econ-txt{{font-size:0.88em;line-height:1.7;}}

/* ══════════════════════════════════════
   AI記憶
══════════════════════════════════════ */
.memory-box{{
  background:linear-gradient(135deg,#080f20,#0a1428);
  border:1px solid #00d4ff33;border-radius:var(--radius);
  padding:16px;margin-bottom:16px;
}}
.memory-text{{font-size:0.88em;line-height:1.75;white-space:pre-wrap;}}

/* ══════════════════════════════════════
   YouTube
══════════════════════════════════════ */
.yt-wrap{{
  background:var(--card);border:1px solid var(--border);
  border-radius:var(--radius);padding:16px;margin-bottom:16px;
}}
.yt-section{{margin-bottom:12px;padding-bottom:12px;border-bottom:1px solid var(--border);}}
.yt-section:last-child{{border-bottom:none;}}
.yt-head{{color:#ff6d6d;font-size:0.8em;font-weight:700;margin-bottom:6px;}}
.yt-text{{font-size:0.88em;line-height:1.7;}}
.yt-video{{
  display:flex;align-items:flex-start;gap:8px;
  padding:8px 0;border-top:1px solid var(--border);
  font-size:0.85em;
}}

/* ══════════════════════════════════════
   ニュース
══════════════════════════════════════ */
.news-wrap{{
  background:var(--card);border:1px solid var(--border);
  border-radius:var(--radius);padding:8px 14px;margin-bottom:16px;
}}
.news-row{{
  display:flex;align-items:flex-start;gap:8px;
  padding:10px 0;border-bottom:1px solid var(--border);flex-wrap:wrap;
}}
.news-row:last-child{{border-bottom:none;}}
.nbadge{{
  padding:2px 7px;border-radius:20px;font-size:0.68em;
  font-weight:700;color:#fff;flex-shrink:0;white-space:nowrap;
}}
.ncat{{color:var(--accent2);font-size:0.7em;flex-shrink:0;padding-top:3px;}}
.ntitle{{flex:1;font-size:0.85em;min-width:0;}}
.ntitle a{{color:var(--text);}}
.ntitle a:hover{{color:var(--accent);}}
.nsrc{{color:var(--text2);font-size:0.68em;flex-shrink:0;padding-top:3px;}}

/* ══════════════════════════════════════
   TradingViewミニティッカー
══════════════════════════════════════ */
.ticker-wrap{{margin-bottom:16px;overflow:hidden;border-radius:var(--radius);}}

/* ══════════════════════════════════════
   フッター
══════════════════════════════════════ */
.footer{{
  text-align:center;color:var(--text2);font-size:0.75em;
  padding:24px 16px;border-top:1px solid var(--border);
  margin-top:8px;
}}
.footer-badge{{
  display:inline-block;background:var(--card);border:1px solid var(--border);
  border-radius:20px;padding:4px 12px;margin-top:8px;font-size:0.85em;
}}

/* ══════════════════════════════════════
   レスポンシブ
══════════════════════════════════════ */
@media(min-width:540px){{
  .bcard-grid{{grid-template-columns:repeat(3,1fr);}}
  .quick-row{{grid-template-columns:repeat(3,1fr);}}
}}
@media(min-width:800px){{
  .bcard-grid{{grid-template-columns:repeat(4,1fr);}}
  .container{{max-width:900px;margin:0 auto;}}
}}

/* ══════════════════════════════════════
   アニメーション
══════════════════════════════════════ */
@keyframes fadeIn{{from{{opacity:0;transform:translateY(12px);}}to{{opacity:1;transform:none;}}}}
.hero,.bcard,.qcard,.bubble,.econ-row{{animation:fadeIn 0.4s ease both;}}
.bcard:nth-child(2){{animation-delay:0.05s;}}
.bcard:nth-child(3){{animation-delay:0.1s;}}
.bcard:nth-child(4){{animation-delay:0.15s;}}
</style>
</head>
<body>

<!-- ヘッダー -->
<div class="header">
  <div class="header-logo">📊 市場AI秘書</div>
  <div class="header-date">📅 {today} {now}</div>
</div>

<!-- ティッカー（リアルタイム） -->
<div class="ticker-wrap">
  <div class="tradingview-widget-container">
    <div class="tradingview-widget-container__widget"></div>
    <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-ticker-tape.js" async>
    {{
      "symbols":[
        {{"proName":"INDEX:NKY","title":"日経225"}},
        {{"proName":"SP:SPX","title":"S&P500"}},
        {{"proName":"NASDAQ:NDX","title":"NASDAQ"}},
        {{"proName":"FX:USDJPY","title":"ドル円"}},
        {{"proName":"COMEX:GC1!","title":"金"}},
        {{"proName":"BITSTAMP:BTCUSD","title":"BTC"}},
        {{"proName":"CBOE:VIX","title":"VIX"}}
      ],
      "showSymbolLogo":true,"isTransparent":true,
      "displayMode":"adaptive","colorTheme":"dark","locale":"ja"
    }}
    </script>
  </div>
</div>

<div class="container" style="padding:0 14px;">

  <!-- ヒーロー：今日の相場一言 -->
  <div class="hero">
    <span class="hero-emoji">{hero_emoji}</span>
    <div class="hero-label">{tl} 今日の相場：{hero_label}</div>
    <div class="hero-msg">{hero_msg}</div>
    <div class="hero-score">リスクスコア {score:+.2f}</div>
  </div>

  <!-- クイックステータス3つ -->
  <div class="quick-row">
    <div class="qcard">
      <div class="qcard-icon">😱</div>
      <div class="qcard-label">恐怖＆強欲</div>
      <div class="qcard-val" style="color:{fg_color};">{fg_int}</div>
      <div class="qcard-sub">{fg_emoji} {fg_rating}</div>
    </div>
    <div class="qcard">
      <div class="qcard-icon">🌡</div>
      <div class="qcard-label">VIX 恐怖指数</div>
      <div class="qcard-val" style="color:{'#ff4444' if (prices.get('^VIX',{{}}).get('latest') or 0)>20 else '#ffd740' if (prices.get('^VIX',{{}}).get('latest') or 0)>15 else '#00e676'};">{p_val('^VIX')}</div>
      <div class="qcard-sub">{'高い=危険' if (prices.get('^VIX',{{}}).get('latest') or 0)>20 else '普通' if (prices.get('^VIX',{{}}).get('latest') or 0)>15 else '低い=安定'}</div>
    </div>
    <div class="qcard">
      <div class="qcard-icon">💵</div>
      <div class="qcard-label">ドル円</div>
      <div class="qcard-val">{p_val('USDJPY=X')}</div>
      <div class="qcard-sub">円</div>
    </div>
  </div>

  <!-- Fear & Greed バーメーター -->
  <div class="fg-bar-wrap">
    <div class="fg-bar-title">{fg_emoji} 恐怖＆強欲指数（Fear &amp; Greed Index）とは？</div>
    <div class="fg-bar-desc">0=超恐怖（売りが多い） ／ 100=超強欲（買いが多い）。50前後が中立です。</div>
    <div class="fg-rail">
      <div class="fg-fill" style="width:100%;"></div>
      <div class="fg-needle" style="left:{fg_int}%;"></div>
    </div>
    <div class="fg-labels"><span>😭 超恐怖</span><span>😰 恐怖</span><span>😐 中立</span><span>😤 強欲</span><span>😱 超強欲</span></div>
    <div class="fg-cur">{fg_int}</div>
    <div class="fg-cur-label">{fg_emoji} {fg_desc}</div>
  </div>

  <!-- リアルタイムチャート（TradingView） -->
  <div class="sec-head">📈 リアルタイムチャート（クリックで拡大）</div>
  <div class="tv-wrap">
    <div class="tradingview-widget-container">
      <div class="tradingview-widget-container__widget"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-market-overview.js" async>
      {{
        "colorTheme":"dark","dateRange":"1D","showChart":true,"locale":"ja",
        "isTransparent":true,"showSymbolLogo":true,"width":"100%","height":"420",
        "tabs":[
          {{"title":"株式指数","symbols":[
            {{"s":"INDEX:NKY","d":"🇯🇵 日経平均"}},
            {{"s":"SP:SPX","d":"🇺🇸 S&P500"}},
            {{"s":"NASDAQ:NDX","d":"🇺🇸 NASDAQ"}},
            {{"s":"INDEX:DJI","d":"🇺🇸 ダウ"}}
          ]}},
          {{"title":"為替","symbols":[
            {{"s":"FX:USDJPY","d":"💵 ドル円"}},
            {{"s":"FX:EURUSD","d":"💶 ユーロドル"}}
          ]}},
          {{"title":"コモディティ","symbols":[
            {{"s":"COMEX:GC1!","d":"🥇 金"}},
            {{"s":"NYMEX:CL1!","d":"🛢 原油"}},
            {{"s":"BITSTAMP:BTCUSD","d":"₿ Bitcoin"}}
          ]}}
        ]
      }}
      </script>
    </div>
  </div>

  <!-- チャート画像 -->
  {(f'<div class="sec-head">🎨 AI生成チャート</div>' + img_b64("overview") + img_b64("fear_greed") + img_b64("risk_meter")) if chart_paths else ""}

  <!-- 主要指数 -->
  <div class="sec-head">🇯🇵 🇺🇸 主要株価指数</div>
  <div class="bcard-grid">
    {big_card("🇯🇵","日経平均","^N225","円","日本の株市場の代表")}
    {big_card("🇺🇸","S&P500","^GSPC","","米500社の平均")}
    {big_card("🇺🇸","NASDAQ","^IXIC","","米テック株中心")}
    {big_card("🇺🇸","ダウ平均","^DJI","","米30社の老舗指数")}
    {big_card("😰","VIX","^VIX","","高いほど市場が不安")}
    {big_card("📊","米10年金利","^TNX","%","上がると株に逆風")}
  </div>

  <!-- 為替・コモディティ -->
  <div class="sec-head">💱 為替・商品・仮想通貨</div>
  <div class="bcard-grid">
    {big_card("💵","ドル円","USDJPY=X","円","円安なら輸出株に有利")}
    {big_card("💶","ユーロドル","EURUSD=X","","欧米の力関係")}
    {big_card("🥇","金（ゴールド）","GC=F","$","安全資産。不安時に上がる")}
    {big_card("🛢","原油 WTI","CL=F","$","エネルギーコストに直結")}
    {big_card("₿","ビットコイン","BTC-USD","$","仮想通貨の代表格")}
    {big_card("🪙","イーサリアム","ETH-USD","$","仮想通貨2位")}
  </div>

  <!-- AI議論分析 -->
  <div class="sec-head">🤖 AIが多角的に分析（強気・弱気・中立の3視点）</div>
  <div class="debate-wrap">
    <div class="debate-intro">
      💡 <strong>3つのAIが議論しています</strong><br>
      同じデータを見ても「上がる」「下がる」の意見が分かれます。
      どちらの意見が参考になるか、自分で考えてみましょう！
    </div>
    {ai_html}
  </div>

  <!-- 経済指標分析 -->
  {f'<div class="sec-head">📊 経済指標の分析</div><div class="econ-wrap">{econ_html}</div>' if econ_html else ""}

  <!-- AI記憶分析 -->
  {f'<div class="sec-head">🧠 AI記憶：過去との比較</div><div class="memory-box"><div class="memory-text">{memory_analysis}</div></div>' if memory_analysis else ""}

  <!-- YouTube -->
  {f'<div class="sec-head">📺 YouTube注目動画まとめ</div><div class="yt-wrap">{yt_html}</div>' if yt_html else ""}

  <!-- ニュース -->
  <div class="sec-head">📰 注目ニュース一覧</div>
  <div class="news-wrap">{news_html or "<div class='news-row'>ニュースなし</div>"}</div>

</div><!-- /container -->

<div class="footer">
  市場AI秘書 — GitHub Actions で自動生成<br>
  <span class="footer-badge">🤖 Gemini AI 分析 ｜ 📅 {now}</span>
</div>

</body>
</html>"""

    today_str = get_today_str()
    html_path = dirs["reports"] / f"{today_str}_{mode}.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    md_path = dirs["reports"] / f"{today_str}_{mode}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# 市場レポート {today_str} [{mode.upper()}]\n生成: {now}\n\n地合い: {sentiment} ({score:+.2f})\nFear&Greed: {fg_score} ({fg_rating})\n")

    logger.info(f"HTMLレポート保存: {html_path}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["morning","noon","evening","test"], default="morning")
    run(p.parse_args().mode)


if __name__ == "__main__":
    main()
