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
                  chart_paths=chart_paths)
    except Exception:
        logger.error("Telegram通知エラー"); logger.debug(traceback.format_exc())

    logger.info(f"====== クラウド実行完了 ======")
    print(f"\n✅ 完了 | 地合い: {risk.get('sentiment')} | "
          f"F&G: {fear_greed.get('score')} ({fear_greed.get('rating_ja')}) | "
          f"ニュース: {len(news)}件 | チャート: {len(chart_paths)}件")


def _save_html_report(mode, prices, news, risk, analysis, fear_greed, chart_paths, ai_summary=None, econ_analysis=None, youtube_summary=None, memory_analysis=""):
    """プロ仕様の金融ダッシュボードHTMLを保存"""
    import base64
    today = get_today_str()
    dirs  = get_dirs()
    now   = get_jst_now().strftime("%Y-%m-%d %H:%M JST")

    sentiment = risk.get("sentiment","不明")
    score     = risk.get("score", 0)
    fg_score  = fear_greed.get("score")
    fg_rating = fear_greed.get("rating_ja","---")
    signals   = risk.get("signals", [])
    facts     = analysis.get("facts", [])
    hypotheses= analysis.get("hypotheses", [])
    ai_summary = ai_summary or {}
    ai_available = ai_summary.get("available", False)
    ai_overall = ai_summary.get("overall_summary", "")
    ai_points  = ai_summary.get("points", "")
    ai_risks   = ai_summary.get("risks", "")
    ai_outlook = ai_summary.get("outlook", "")

    def p_val(sym):
        d = prices.get(sym, {})
        v = d.get("latest")
        return f"{v:,.2f}" if v else "---"

    def p_chg(sym):
        chg = prices.get(sym, {}).get("change_pct")
        if chg is None: return "---", "neutral"
        arrow = "▲" if chg >= 0 else "▼"
        cls = "up" if chg >= 0 else "down"
        return f"{arrow}{abs(chg):.2f}%", cls

    def img_tag(key):
        path = chart_paths.get(key, "")
        if not path or not Path(path).exists(): return ""
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        return f'<img src="data:image/png;base64,{b64}" class="chart-img">'

    score_color = "#3fb950" if score >= 2 else "#f85149" if score <= -2 else "#8b949e"
    fg_color    = "#3fb950" if (fg_score or 0) >= 55 else "#f85149" if (fg_score or 0) <= 30 else "#e3b341"

    # 指数カード生成
    def price_card(emoji, label, sym, unit=""):
        val = p_val(sym)
        chg_str, cls = p_chg(sym)
        return f'''<div class="price-card">
            <div class="pc-label">{emoji} {label}</div>
            <div class="pc-value">{val}{unit}</div>
            <div class="pc-chg {cls}">{chg_str}</div>
        </div>'''

    # ニュース生成
    sorted_news = sorted(news, key=lambda x: {{"A":0,"B":1,"C":2}}.get(x.get("importance","C"),2))
    news_html = ""
    for item in sorted_news[:20]:
        imp   = item.get("importance","C")
        title = item.get("title","")
        src   = item.get("source_name") or item.get("source","")
        url   = item.get("url","")
        cat   = item.get("category","")
        imp_cls = {{"A":"ni-a","B":"ni-b","C":"ni-c"}}.get(imp,"ni-c")
        link = f'<a href="{url}" target="_blank">{title}</a>' if url else title
        news_html += f'<div class="news-item"><span class="ni-badge {imp_cls}">{imp}</span><span class="ni-cat">{cat}</span><span class="ni-title">{link}</span><span class="ni-src">{src}</span></div>'

    # シグナル
    signal_html = ""
    for s in signals[:6]:
        d = s.get("direction","")
        arrow = "🔺" if "上昇" in d or "強" in d else "🔻" if "下落" in d or "弱" in d else "➡️"
        signal_html += f'<div class="signal-item">{arrow} <strong>{s.get("indicator","")}</strong>: {d}</div>'

    # 分析テキスト
    facts_html = "".join(f'<div class="analysis-item">✅ {f}</div>' for f in facts[:3])
    hypo_html  = "".join(f'<div class="analysis-item">🔮 {h}</div>' for h in hypotheses[:2])

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>市場AI秘書 {today}</title>
<style>
:root {{
  --bg: #0a0e17;
  --bg2: #0f1623;
  --card: #141d2b;
  --border: #1e2d42;
  --accent: #00d4ff;
  --accent2: #7b61ff;
  --up: #00e676;
  --down: #ff4444;
  --neutral: #607d8b;
  --text: #e8f0fe;
  --text2: #8899aa;
  --gold: #ffd700;
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:var(--bg); color:var(--text); font-family:'Hiragino Sans','Meiryo',system-ui,sans-serif; min-height:100vh; }}

/* ヘッダー */
.header {{ background:linear-gradient(135deg,#0f1623,#1a1f3a); border-bottom:1px solid var(--border); padding:16px 20px; display:flex; align-items:center; justify-content:space-between; }}
.header-title {{ font-size:1.3em; font-weight:700; background:linear-gradient(90deg,var(--accent),var(--accent2)); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }}
.header-meta {{ color:var(--text2); font-size:0.8em; }}

/* メインコンテンツ */
.container {{ max-width:1200px; margin:0 auto; padding:16px; }}

/* ステータスバー */
.status-bar {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:16px; }}
.status-card {{ background:var(--card); border:1px solid var(--border); border-radius:12px; padding:16px; text-align:center; position:relative; overflow:hidden; }}
.status-card::before {{ content:''; position:absolute; top:0; left:0; right:0; height:3px; }}
.status-card.market::before {{ background:linear-gradient(90deg,{score_color},{score_color}88); }}
.status-card.fg::before {{ background:linear-gradient(90deg,{fg_color},{fg_color}88); }}
.sc-label {{ color:var(--text2); font-size:0.75em; margin-bottom:8px; letter-spacing:1px; text-transform:uppercase; }}
.sc-value {{ font-size:1.8em; font-weight:800; color:{score_color}; }}
.sc-value2 {{ font-size:1.8em; font-weight:800; color:{fg_color}; }}
.sc-sub {{ color:var(--text2); font-size:0.8em; margin-top:4px; }}

/* 価格グリッド */
.section-title {{ color:var(--accent); font-size:0.85em; font-weight:600; letter-spacing:2px; text-transform:uppercase; margin:16px 0 8px; padding-left:8px; border-left:3px solid var(--accent); }}
.price-grid {{ display:grid; grid-template-columns:repeat(2,1fr); gap:8px; margin-bottom:16px; }}
.price-card {{ background:var(--card); border:1px solid var(--border); border-radius:10px; padding:12px; transition:border-color 0.2s; }}
.price-card:hover {{ border-color:var(--accent); }}
.pc-label {{ color:var(--text2); font-size:0.75em; margin-bottom:4px; }}
.pc-value {{ font-size:1.2em; font-weight:700; color:var(--text); margin-bottom:2px; }}
.pc-chg {{ font-size:0.85em; font-weight:600; }}
.up {{ color:var(--up); }} .down {{ color:var(--down); }} .neutral {{ color:var(--neutral); }}

/* チャート */
.chart-img {{ width:100%; border-radius:10px; margin:8px 0; border:1px solid var(--border); }}

/* シグナル */
.signals {{ background:var(--card); border:1px solid var(--border); border-radius:12px; padding:14px; margin-bottom:16px; }}
.signal-item {{ padding:6px 0; border-bottom:1px solid var(--border); font-size:0.9em; }}
.signal-item:last-child {{ border-bottom:none; }}

/* 分析 */
.analysis {{ background:var(--card); border:1px solid var(--border); border-radius:12px; padding:14px; margin-bottom:16px; }}
.analysis-item {{ padding:5px 0; font-size:0.88em; color:var(--text2); border-bottom:1px solid var(--border); }}
.analysis-item:last-child {{ border-bottom:none; }}

/* ニュース */
.news-list {{ background:var(--card); border:1px solid var(--border); border-radius:12px; padding:14px; margin-bottom:16px; }}
.news-item {{ display:flex; align-items:flex-start; gap:8px; padding:8px 0; border-bottom:1px solid var(--border); flex-wrap:wrap; }}
.news-item:last-child {{ border-bottom:none; }}
.ni-badge {{ padding:2px 6px; border-radius:4px; font-size:0.7em; font-weight:700; flex-shrink:0; }}
.ni-a {{ background:#f85149; color:#fff; }}
.ni-b {{ background:#e3b341; color:#000; }}
.ni-c {{ background:#21262d; color:#8b949e; }}
.ni-cat {{ color:var(--accent2); font-size:0.72em; flex-shrink:0; padding-top:2px; }}
.ni-title {{ flex:1; font-size:0.85em; min-width:0; }}
.ni-title a {{ color:var(--text); text-decoration:none; }}
.ni-title a:hover {{ color:var(--accent); }}
.ni-src {{ color:var(--text2); font-size:0.72em; flex-shrink:0; padding-top:2px; }}

/* TradingView */
.tv-section {{ background:var(--card); border:1px solid var(--border); border-radius:12px; padding:14px; margin-bottom:16px; overflow:hidden; }}

/* AI分析 */
.ai-box {{ background:linear-gradient(135deg,#0f1a2e,#1a1040); border:1px solid #7b61ff44; border-radius:12px; padding:16px; margin-bottom:16px; }}
.ai-section {{ margin-bottom:12px; padding-bottom:12px; border-bottom:1px solid #7b61ff22; }}
.ai-section:last-child {{ margin-bottom:0; padding-bottom:0; border-bottom:none; }}
.ai-label {{ color:#a78bfa; font-size:0.8em; font-weight:700; letter-spacing:1px; margin-bottom:6px; }}
.ai-text {{ color:var(--text); font-size:0.9em; line-height:1.7; white-space:pre-wrap; }}

/* フッター */
.footer {{ text-align:center; color:var(--text2); font-size:0.75em; padding:20px; border-top:1px solid var(--border); }}

@media(min-width:600px) {{
  .price-grid {{ grid-template-columns:repeat(3,1fr); }}
  .status-bar {{ grid-template-columns:repeat(4,1fr); }}
}}
</style>
</head>
<body>

<div class="header">
  <div class="header-title">🦣 市場AI秘書</div>
  <div class="header-meta">📅 {today} {now}</div>
</div>

<div class="container">

  <!-- ステータス -->
  <div class="status-bar">
    <div class="status-card market">
      <div class="sc-label">🌡 市場地合い</div>
      <div class="sc-value">{sentiment}</div>
      <div class="sc-sub">スコア: {score:+.2f}</div>
    </div>
    <div class="status-card fg">
      <div class="sc-label">😱 Fear &amp; Greed</div>
      <div class="sc-value2">{f"{fg_score:.0f}" if fg_score else "---"}</div>
      <div class="sc-sub">{fg_rating}</div>
    </div>
  </div>

  <!-- 主要指数 -->
  <div class="section-title">📈 主要指数</div>
  <div class="price-grid">
    {price_card("🇯🇵","日経平均","^N225","円")}
    {price_card("🇺🇸","S&P 500","^GSPC","")}
    {price_card("🇺🇸","NASDAQ","^IXIC","")}
    {price_card("🇺🇸","ダウ平均","^DJI","")}
    {price_card("😰","VIX恐怖指数","^VIX","")}
    {price_card("📊","米10年金利","^TNX","%")}
  </div>

  <!-- 為替・コモディティ -->
  <div class="section-title">💱 為替・コモディティ</div>
  <div class="price-grid">
    {price_card("💵","ドル円","USDJPY=X","円")}
    {price_card("💶","EUR/USD","EURUSD=X","")}
    {price_card("🥇","金 (GOLD)","GC=F","$")}
    {price_card("🛢","WTI原油","CL=F","$")}
    {price_card("₿","Bitcoin","BTC-USD","$")}
  </div>

  <!-- TradingViewチャート -->
  <div class="section-title">📊 リアルタイムチャート</div>
  <div class="tv-section">
    <div class="tradingview-widget-container">
      <div class="tradingview-widget-container__widget"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-market-overview.js" async>
      {{
        "colorTheme": "dark",
        "dateRange": "1D",
        "showChart": true,
        "locale": "ja",
        "largeChartUrl": "",
        "isTransparent": true,
        "showSymbolLogo": true,
        "showFloatingTooltip": false,
        "width": "100%",
        "height": "400",
        "tabs": [
          {{"title":"指数","symbols":[
            {{"s":"INDEX:NKY","d":"日経平均"}},
            {{"s":"SP:SPX","d":"S&P500"}},
            {{"s":"NASDAQ:NDX","d":"NASDAQ"}},
            {{"s":"INDEX:DJI","d":"ダウ"}}
          ]}},
          {{"title":"為替","symbols":[
            {{"s":"FX:USDJPY","d":"ドル円"}},
            {{"s":"FX:EURUSD","d":"EUR/USD"}}
          ]}},
          {{"title":"コモディティ","symbols":[
            {{"s":"COMEX:GC1!","d":"金"}},
            {{"s":"NYMEX:CL1!","d":"原油"}},
            {{"s":"BITSTAMP:BTCUSD","d":"Bitcoin"}}
          ]}}
        ]
      }}
      </script>
    </div>
  </div>

  <!-- チャート画像 -->
  {f'<div class="section-title">🎨 市場ビジュアル</div><div>{img_tag("overview")}{img_tag("fear_greed")}{img_tag("risk_meter")}</div>' if chart_paths else ""}

  <!-- シグナル -->
  <div class="section-title">🔍 市場シグナル</div>
  <div class="signals">{signal_html or "<div class='signal-item'>シグナルなし</div>"}</div>

  <!-- AI議論分析 -->
  <div class="section-title">🤖 AIマルチ視点分析</div>
  {f'''<div class="ai-box">
    <div class="ai-section">
      <div class="ai-label">📈 強気派AI の意見</div>
      <div class="ai-text">{ai_summary.get("bull_view","---")}</div>
    </div>
    <div class="ai-section">
      <div class="ai-label">📉 弱気派AI の意見</div>
      <div class="ai-text">{ai_summary.get("bear_view","---")}</div>
    </div>
    <div class="ai-section">
      <div class="ai-label">⚖️ 中立AI の総合判断</div>
      <div class="ai-text">{ai_summary.get("neutral_view","---")}</div>
    </div>
    {f'<div class="ai-section"><div class="ai-label">📊 過去データ比較</div><div class="ai-text">{ai_summary.get("history_comment","")}</div></div>' if ai_summary.get("history_comment") else ""}
  </div>''' if ai_available else '<div class="ai-box"><div class="ai-text">AI分析準備中...</div></div>'}

  <!-- 経済指標分析 -->
  <div class="section-title">📊 経済指標分析</div>
  {f'''<div class="ai-box">
    {f'<div class="ai-section"><div class="ai-label">🌍 現状分析</div><div class="ai-text">{econ_analysis.get("status","")}</div></div>' if econ_analysis and econ_analysis.get("status") else ""}
    {f'<div class="ai-section"><div class="ai-label">🎯 注目指標</div><div class="ai-text">{econ_analysis.get("focus","")}</div></div>' if econ_analysis and econ_analysis.get("focus") else ""}
    {f'<div class="ai-section"><div class="ai-label">💹 市場への影響予測</div><div class="ai-text">{econ_analysis.get("impact","")}</div></div>' if econ_analysis and econ_analysis.get("impact") else ""}
    {f'<div class="ai-section"><div class="ai-label">💡 投資家へのヒント</div><div class="ai-text">{econ_analysis.get("hint","")}</div></div>' if econ_analysis and econ_analysis.get("hint") else ""}
  </div>''' if econ_analysis and econ_analysis.get("available") else '<div class="ai-box"><div class="ai-text">経済指標分析準備中...</div></div>'}

  <!-- 分析 -->
  {f'<div class="section-title">📝 マクロ分析</div><div class="analysis">{facts_html}{hypo_html}</div>' if facts_html or hypo_html else ""}

  <!-- AI記憶分析 -->
  {f'''<div class="section-title">🧠 AI記憶・パターン分析</div>
  <div class="ai-box"><div class="ai-text">{memory_analysis}</div></div>''' if memory_analysis else ""}

  <!-- YouTube動画要約 -->
  {f'''<div class="section-title">📺 YouTube注目動画</div>
  <div class="ai-box">
    {f'<div class="ai-section"><div class="ai-label">💡 動画のポイント</div><div class="ai-text">{youtube_summary.get("points","")}</div></div>' if youtube_summary and youtube_summary.get("points") else ""}
    {f'<div class="ai-section"><div class="ai-label">📊 市場への示唆</div><div class="ai-text">{youtube_summary.get("impact","")}</div></div>' if youtube_summary and youtube_summary.get("impact") else ""}
    {"".join(f'<div class="ai-section"><div class="ai-text">🎬 <a href=\\"{v.get("url","")}\\" target=\\"_blank\\" style=\\"color:var(--accent)\\">{v.get("title","")}</a></div></div>' for v in (youtube_summary or {{}}).get("videos",[])[:4]) if youtube_summary and youtube_summary.get("videos") else ""}
  </div>''' if youtube_summary and youtube_summary.get("available") else ""}

  <!-- ニュース -->
  <div class="section-title">📰 注目ニュース</div>
  <div class="news-list">{news_html or "<div class='news-item'>ニュースなし</div>"}</div>

</div>

<div class="footer">市場AI秘書 | GitHub Actions 自動生成 | {now}</div>

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
