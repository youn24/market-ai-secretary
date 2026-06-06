"""
メインエントリーポイント
python run_daily.py --mode morning / noon / evening / test
"""
import argparse, sys, traceback
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))
from src.utils import ensure_dirs, setup_logger, get_jst_now, get_dirs, get_today_str

logger = setup_logger("run_daily")


def run(mode: str):
    ensure_dirs()
    logger.info(f"====== Market AI Secretary 開始 [mode={mode}] ======")
    logger.info(f"実行時刻(JST): {get_jst_now().strftime('%Y-%m-%d %H:%M:%S')}")

    prices        = {}
    fear_greed    = {"score": None, "rating_ja": "取得失敗"}
    news          = []
    extra_news    = []
    polymarket    = []
    risk          = {"score":0,"sentiment":"不明","meter":"NEUTRAL","signals":[]}
    analysis      = {}
    technical     = {}
    fundamental   = {}
    chart_paths   = {}
    plotly_charts = {}
    ai_summary    = {"available": False}
    report_paths  = {}

    # Step 1: 価格 + Fear & Greed
    try:
        logger.info("--- Step 1: 価格データ取得 ---")
        from src.fetch_prices import run as fp
        prices, fear_greed = fp()
    except Exception:
        logger.error("価格取得エラー（続行）"); logger.debug(traceback.format_exc())

    # Step 2: ニュース
    try:
        logger.info("--- Step 2: ニュース取得 ---")
        from src.fetch_news import run as fn
        news = fn()
    except Exception:
        logger.error("ニュース取得エラー（続行）"); logger.debug(traceback.format_exc())

    # Step 3: 指標
    try:
        logger.info("--- Step 3: 指標計算 ---")
        from src.indicators import calc_risk_score
        risk = calc_risk_score(prices)
    except Exception:
        logger.error("指標計算エラー（続行）"); logger.debug(traceback.format_exc())

    # Step 4: 分析
    try:
        logger.info("--- Step 4: 分析 ---")
        from src.analyze import build_analysis
        analysis = build_analysis(prices, risk)
    except Exception:
        logger.error("分析エラー（続行）"); logger.debug(traceback.format_exc())

    # Step 5: matplotlib チャート（PNG保存）
    try:
        logger.info("--- Step 5: matplotlibチャート生成 ---")
        from src.visualize import run as vis
        chart_paths = vis(prices, news, risk, fear_greed)
    except Exception:
        logger.error("チャート生成エラー（続行）"); logger.debug(traceback.format_exc())

    # Step 6: Plotly インタラクティブチャート
    try:
        logger.info("--- Step 6: Plotlyチャート生成 ---")
        from src.visualize_plotly import run_plotly
        plotly_charts = run_plotly(prices, news, risk, fear_greed)
    except Exception:
        logger.error("Plotlyチャートエラー（続行）"); logger.debug(traceback.format_exc())

    # Step 5b: テクニカル分析
    try:
        logger.info("--- Step 5b: テクニカル分析 ---")
        from src.technical_analysis import run_technical
        technical = run_technical()
    except Exception:
        logger.error("テクニカル分析エラー（続行）"); logger.debug(traceback.format_exc())

    # Step 5c: ファンダメンタル分析
    try:
        logger.info("--- Step 5c: ファンダメンタル分析 ---")
        from src.fundamental_analysis import run_fundamental
        fundamental = run_fundamental(prices)
    except Exception:
        logger.error("ファンダメンタル分析エラー（続行）"); logger.debug(traceback.format_exc())

    # Step 6b: 追加ニュース（NHK・Yahoo・MarketWatch等）+ Polymarket
    try:
        logger.info("--- Step 6b: 追加ニュース・Polymarket取得 ---")
        from src.fetch_extra_news import run as fen
        extra_news, polymarket = fen()
        news = news + extra_news  # メインニュースと統合
    except Exception:
        logger.error("追加ニュース取得エラー（続行）"); logger.debug(traceback.format_exc())

    # Step 7: Ollama AI 要約（カテゴリ別）
    try:
        logger.info("--- Step 7: Ollama AI要約（カテゴリ別） ---")
        from src.ai_summary import run_ai_summary
        ai_summary = run_ai_summary(prices, news, risk, fear_greed)
        # ダッシュボード用に保存
        if ai_summary.get("available"):
            import json as _json
            ai_path = get_dirs()["data_raw"] / f"{get_today_str()}_ai_{mode}.json"
            with open(ai_path, "w", encoding="utf-8") as f:
                _json.dump(ai_summary, f, ensure_ascii=False, indent=2)
            logger.info(f"AI要約保存: {ai_path}")
    except Exception:
        logger.error("AI要約エラー（続行）"); logger.debug(traceback.format_exc())

    # Step 8: レポート生成
    try:
        logger.info("--- Step 8: レポート生成 ---")
        from src.report_writer import save_report
        report_paths = save_report(
            mode, prices, news, risk, analysis,
            chart_paths, fear_greed, ai_summary, plotly_charts
        )
        logger.info(f"HTML: {report_paths.get('html')}")
    except Exception:
        logger.error("レポート生成エラー（続行）"); logger.debug(traceback.format_exc())

    # Step 9: Telegram通知
    try:
        logger.info("--- Step 9: Telegram通知 ---")
        from src.notify_telegram import run as notify
        notify(risk, analysis, report_paths, mode,
               prices=prices, news=news,
               fear_greed=fear_greed, ai_summary=ai_summary,
               chart_paths=chart_paths)
    except Exception:
        logger.error("Telegram通知エラー（続行）"); logger.debug(traceback.format_exc())

    # Step 10: iPhone通知（ntfy.sh）
    try:
        logger.info("--- Step 10: iPhone通知（ntfy.sh） ---")
        from src.notify_iphone import run as notify_iphone
        notify_iphone(risk, fear_greed, prices, ai_summary, mode)
    except Exception:
        logger.error("iPhone通知エラー（続行）"); logger.debug(traceback.format_exc())

    logger.info(f"====== 完了 [mode={mode}] ======")

    if mode == "test":
        ai_stat = f"✅ {ai_summary.get('model')}" if ai_summary.get("available") else "❌ 未起動"
        print(f"""
{'='*52}
テスト実行完了
  地合い:         {risk.get('sentiment','不明')}
  Fear & Greed:   {fear_greed.get('score')} ({fear_greed.get('rating_ja')})
  価格取得:       {sum(1 for v in prices.values() if v.get('latest'))}件
  ニュース:       {len(news)}件
  チャートPNG:    {len(chart_paths)}枚
  Plotlyチャート: {len(plotly_charts)}個
  Ollama AI:      {ai_stat}
  TradingView:    ✅ HTMLに埋め込み済み
  レポートHTML:   {report_paths.get('html','')}
{'='*52}""")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["morning","noon","evening","test"],
                   default="morning")
    run(p.parse_args().mode)

if __name__ == "__main__":
    main()
