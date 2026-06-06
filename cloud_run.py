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
        _save_html_report(mode, prices, news, risk, analysis, fear_greed, chart_paths)
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
                  fear_greed=fear_greed, ai_summary={"available": False},
                  chart_paths=chart_paths)
    except Exception:
        logger.error("Telegram通知エラー"); logger.debug(traceback.format_exc())

    logger.info(f"====== クラウド実行完了 ======")
    print(f"\n✅ 完了 | 地合い: {risk.get('sentiment')} | "
          f"F&G: {fear_greed.get('score')} ({fear_greed.get('rating_ja')}) | "
          f"ニュース: {len(news)}件 | チャート: {len(chart_paths)}件")


def _save_html_report(mode, prices, news, risk, analysis, fear_greed, chart_paths):
    """見やすいHTMLレポートを保存"""
    today = get_today_str()
    dirs  = get_dirs()
    now   = get_jst_now().strftime("%Y-%m-%d %H:%M JST")

    sentiment = risk.get("sentiment","不明")
    score     = risk.get("score", 0)
    fg_score  = fear_greed.get("score")
    fg_rating = fear_greed.get("rating_ja","---")
    signals   = risk.get("signals", [])

    def p(sym, unit=""):
        d   = prices.get(sym, {})
        v   = d.get("latest")
        chg = d.get("change_pct")
        if v is None: return "<span class='na'>---</span>"
        arrow = "▲" if (chg or 0) >= 0 else "▼"
        cls   = "up" if (chg or 0) >= 0 else "down"
        chg_s = f"<span class='{cls}'>{arrow}{abs(chg):.2f}%</span>" if chg else ""
        return f"<strong>{v:,.2f}{unit}</strong> {chg_s}"

    # チャート画像をbase64で埋め込み
    import base64
    def img_tag(key):
        path = chart_paths.get(key, "")
        if not path or not Path(path).exists():
            return ""
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        return f'<img src="data:image/png;base64,{b64}" style="width:100%;border-radius:8px;margin:8px 0">'

    sorted_news = sorted(news, key=lambda x: {"A":0,"B":1,"C":2}.get(x.get("importance","C"),2))
    news_rows = ""
    for item in sorted_news[:15]:
        imp  = item.get("importance","C")
        cls  = {"A":"imp-a","B":"imp-b","C":"imp-c"}.get(imp,"imp-c")
        title = item.get("title","")
        src   = item.get("source_name") or item.get("source","")
        cat   = item.get("category","")
        url   = item.get("url","")
        title_link = f'<a href="{url}" target="_blank">{title}</a>' if url else title
        news_rows += f'<tr><td><span class="badge {cls}">{imp}</span></td><td>{title_link}</td><td>{cat}</td><td>{src}</td></tr>'

    signal_items = ""
    for s in signals[:6]:
        d = s.get("direction","")
        arrow = "🔺" if "上昇" in d or "強" in d else "🔻" if "下落" in d or "弱" in d else "➡️"
        signal_items += f'<li>{arrow} <strong>{s.get("indicator","")}</strong>: {d}</li>'

    score_color = "#3fb950" if score >= 2 else "#f85149" if score <= -2 else "#8b949e"
    fg_color = "#3fb950" if (fg_score or 0) >= 55 else "#f85149" if (fg_score or 0) <= 30 else "#e3b341"

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>市場AI秘書 {today}</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:#0d1117; color:#e6edf3; font-family:'Hiragino Sans','Meiryo',sans-serif; padding:16px; }}
  h1 {{ font-size:1.4em; color:#58a6ff; margin-bottom:4px; }}
  h2 {{ font-size:1.1em; color:#58a6ff; margin:16px 0 8px; border-left:3px solid #58a6ff; padding-left:8px; }}
  .meta {{ color:#8b949e; font-size:0.85em; margin-bottom:16px; }}
  .cards {{ display:grid; grid-template-columns:repeat(2,1fr); gap:10px; margin-bottom:16px; }}
  .card {{ background:#161b22; border:1px solid #30363d; border-radius:8px; padding:12px; text-align:center; }}
  .card .label {{ color:#8b949e; font-size:0.8em; margin-bottom:4px; }}
  .card .value {{ font-size:1.3em; font-weight:bold; }}
  .up {{ color:#3fb950; }} .down {{ color:#f85149; }} .na {{ color:#8b949e; }}
  .grid2 {{ display:grid; grid-template-columns:repeat(2,1fr); gap:10px; }}
  .section {{ background:#161b22; border:1px solid #30363d; border-radius:8px; padding:12px; margin-bottom:12px; }}
  table {{ width:100%; border-collapse:collapse; font-size:0.85em; }}
  th {{ background:#21262d; color:#8b949e; padding:6px; text-align:left; }}
  td {{ padding:6px; border-bottom:1px solid #21262d; }}
  a {{ color:#58a6ff; text-decoration:none; }}
  .badge {{ padding:2px 6px; border-radius:4px; font-size:0.75em; font-weight:bold; }}
  .imp-a {{ background:#f85149; color:#fff; }}
  .imp-b {{ background:#e3b341; color:#000; }}
  .imp-c {{ background:#30363d; color:#8b949e; }}
  ul {{ padding-left:20px; }} li {{ margin:4px 0; }}
  .score-big {{ font-size:2em; font-weight:bold; color:{score_color}; }}
  .fg-big {{ font-size:2em; font-weight:bold; color:{fg_color}; }}
</style>
</head>
<body>
<h1>📊 市場AI秘書レポート</h1>
<div class="meta">📅 {today} {now} | GitHub Actions 自動生成</div>

<div class="cards">
  <div class="card">
    <div class="label">🌡 市場地合い</div>
    <div class="score-big">{sentiment}</div>
    <div style="color:#8b949e;font-size:0.85em">スコア: {score:+.2f}</div>
  </div>
  <div class="card">
    <div class="label">😱 Fear & Greed</div>
    <div class="fg-big">{fg_score:.0f if fg_score else '---'}</div>
    <div style="color:#8b949e;font-size:0.85em">{fg_rating}</div>
  </div>
</div>

<h2>📈 主要指数</h2>
<div class="section">
<div class="grid2">
  <div>🇯🇵 日経平均: {p('^N225','円')}</div>
  <div>🇺🇸 S&P500: {p('^GSPC')}</div>
  <div>🇺🇸 NASDAQ: {p('^IXIC')}</div>
  <div>🇺🇸 ダウ: {p('^DJI')}</div>
  <div>😰 VIX: {p('^VIX')}</div>
  <div>📊 米10Y: {p('^TNX','%')}</div>
</div>
</div>

<h2>💱 為替・コモディティ</h2>
<div class="section">
<div class="grid2">
  <div>💵 ドル円: {p('USDJPY=X','円')}</div>
  <div>💶 EUR/USD: {p('EURUSD=X')}</div>
  <div>🥇 金: {p('GC=F','$')}</div>
  <div>🛢 原油: {p('CL=F','$')}</div>
  <div>₿ Bitcoin: {p('BTC-USD','$')}</div>
</div>
</div>

<h2>🔍 市場シグナル</h2>
<div class="section"><ul>{signal_items}</ul></div>

{f'<h2>📊 チャート</h2><div class="section">{img_tag("overview")}{img_tag("fear_greed")}{img_tag("risk_meter")}</div>' if chart_paths else ''}

<h2>📰 注目ニュース</h2>
<div class="section">
<table>
<tr><th>重要度</th><th>タイトル</th><th>カテゴリ</th><th>情報源</th></tr>
{news_rows}
</table>
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
