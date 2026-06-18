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
    report_paths = {}  # Step L5i(LINE)より前に初期化（NameError防止）

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

    # Step NEW-A: 煽りニュース検出
    news_bias = {"available": False}
    try:
        logger.info("--- Step NEW-A: 煽りニュース検出 ---")
        from src.news_bias_detector import analyze_news_bias
        news_bias = analyze_news_bias(news)
        if news_bias.get("available"):
            logger.info(f"✅ 煽りニュース検出: 平均スコア{news_bias.get('avg_score',0):.1f}")
    except Exception:
        logger.error("煽りニュース検出エラー"); logger.debug(traceback.format_exc())

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

    # ── Level 3 ─────────────────────────────────────────────

    # Step L3a: 自律AIエージェント
    agent_report = {"available": False}
    try:
        logger.info("--- Step L3a: 自律AIエージェント ---")
        from src.ai_agent import run_agent
        agent_report = run_agent(prices, news, risk, fear_greed)
        if agent_report.get("available"):
            logger.info(f"✅ エージェント完了 (ツール{agent_report.get('tool_count',0)}回呼び出し)")
    except Exception:
        logger.error("エージェントエラー"); logger.debug(traceback.format_exc())

    # Step L3b: テクニカル分析
    technical = {"available": False}
    try:
        logger.info("--- Step L3b: テクニカル分析 ---")
        from src.technical_ai import run as run_tech
        technical = run_tech()
        if technical.get("available"):
            logger.info("✅ テクニカル分析完了")
    except Exception:
        logger.error("テクニカル分析エラー"); logger.debug(traceback.format_exc())

    # Step L3c: ポートフォリオ管理
    portfolio = {"available": False}
    try:
        logger.info("--- Step L3c: ポートフォリオ管理 ---")
        from src.portfolio import run as run_pf
        portfolio = run_pf()
        if portfolio.get("available"):
            logger.info(f"✅ ポートフォリオ完了 {len(portfolio.get('holdings',[]))}銘柄")
    except Exception:
        logger.error("ポートフォリオエラー"); logger.debug(traceback.format_exc())

    # Step NEW-F: 保有銘柄アラート
    portfolio_alerts = {"available": False}
    try:
        logger.info("--- Step NEW-F: 保有銘柄アラート ---")
        from src.portfolio_alert import check_portfolio_alerts
        portfolio_alerts = check_portfolio_alerts(prices)
        if portfolio_alerts.get("available"):
            logger.info(f"✅ 保有銘柄アラート: {len(portfolio_alerts.get('alerts',[]))}件")
    except Exception:
        logger.error("保有銘柄アラートエラー"); logger.debug(traceback.format_exc())

    # Step L3d: シナリオ分析
    scenario = {"available": False}
    try:
        logger.info("--- Step L3d: シナリオ分析 ---")
        from src.scenario import run as run_scen
        scenario = run_scen(prices, risk, fear_greed, news)
        if scenario.get("available"):
            logger.info("✅ シナリオ分析完了")
    except Exception:
        logger.error("シナリオ分析エラー"); logger.debug(traceback.format_exc())

    # Step L3e: 予測トラッカー（自己学習・正解率記録）
    prediction_tracker = {"available": False}
    try:
        logger.info("--- Step L3e: 予測トラッカー（自己学習） ---")
        from src.prediction_tracker import run as run_pt
        prediction_tracker = run_pt(prices, risk, fear_greed, news, ai_summary, scenario)
        if prediction_tracker.get("available"):
            stats = prediction_tracker.get("stats", {})
            r10 = stats.get("10d", {}).get("rate")
            logger.info(f"✅ 予測トラッカー完了 (直近10日正解率:{r10}%)")
    except Exception:
        logger.error("予測トラッカーエラー"); logger.debug(traceback.format_exc())

    # Step L4a: セクター分析・ローテーション
    sector_analysis = {"available": False}
    try:
        logger.info("--- Step L4a: セクター分析・ローテーション ---")
        from src.sector_analysis import run as run_sector
        sector_analysis = run_sector()
        if sector_analysis.get("available"):
            rot = sector_analysis.get("rotation", {})
            logger.info(f"✅ セクター分析完了: {rot.get('phase','---')}")
    except Exception:
        logger.error("セクター分析エラー"); logger.debug(traceback.format_exc())

    # セクターチャート生成
    sector_chart_path = None
    try:
        if sector_analysis.get("available"):
            from src.sector_chart import make_sector_chart
            sector_chart_path = make_sector_chart(sector_analysis)
            if sector_chart_path:
                logger.info(f"✅ セクターチャート生成: {sector_chart_path}")
    except Exception:
        logger.error("セクターチャート生成エラー"); logger.debug(traceback.format_exc())

    # Step L4b: 長期歴史データ分析
    historical_analysis = {"available": False}
    try:
        logger.info("--- Step L4b: 長期歴史データ分析 ---")
        from src.historical_analysis import run as run_hist
        historical_analysis = run_hist()
        if historical_analysis.get("available"):
            reg = historical_analysis.get("regime", {})
            logger.info(f"✅ 歴史分析完了: {reg.get('regime','---')}")
    except Exception:
        logger.error("歴史分析エラー"); logger.debug(traceback.format_exc())

    # Step TR: テーマ株人気ランキング
    theme_ranking = {"available": False}
    try:
        logger.info("--- Step TR: テーマ株人気ランキング ---")
        from src.theme_ranker import run as run_tr
        theme_ranking = run_tr(prices=prices, risk=risk, fear_greed=fear_greed, news=news)
        if theme_ranking.get("available"):
            top = theme_ranking.get("top5", [])
            top_name = top[0]["theme"] if top else "---"
            logger.info(f"✅ テーマランキング完了: 1位={top_name}")
    except Exception:
        logger.error("テーマランキングエラー"); logger.debug(traceback.format_exc())

    # Step TD: TDnet適時開示ウォッチャー（毎日・ウォッチリスト銘柄のみ）
    tdnet = {"available": False}
    try:
        logger.info("--- Step TD: TDnet適時開示ウォッチャー ---")
        from src.tdnet_watcher import run as run_td
        tdnet = run_td(prices, risk, fear_greed)
        if tdnet.get("available"):
            logger.info(f"✅ 適時開示: {tdnet.get('count',0)}件（重要{tdnet.get('high_count',0)}件）")
        else:
            logger.info("適時開示: ウォッチリスト銘柄の開示なし")
    except Exception:
        logger.error("TDnetウォッチャーエラー"); logger.debug(traceback.format_exc())

    # Step EB: 決算ブリーフ（決算系PDFの中身をAI要約）
    earnings_brief = {"available": False}
    try:
        if tdnet.get("available"):
            logger.info("--- Step EB: 決算ブリーフ（PDF要約） ---")
            from src.earnings_brief import run as run_eb
            earnings_brief = run_eb(tdnet)
            if earnings_brief.get("available"):
                logger.info(f"✅ 決算ブリーフ: {earnings_brief.get('count',0)}件要約")
    except Exception:
        logger.error("決算ブリーフエラー"); logger.debug(traceback.format_exc())

    # Step AN: アノマリーカレンダー（毎日・該当する経験則を全部表示）
    anomaly = {"available": False}
    try:
        logger.info("--- Step AN: アノマリーカレンダー ---")
        from src.anomaly_calendar import run as run_an
        anomaly = run_an(prices, risk, fear_greed)
        if anomaly.get("available"):
            logger.info(f"✅ アノマリー: {anomaly.get('count',0)}件該当")
    except Exception:
        logger.error("アノマリーカレンダーエラー"); logger.debug(traceback.format_exc())

    # Step MA（マクロ要約）はFRED/FOMC/議員取引の計算後に実行する（後段に配置）
    macro = {"available": False}

    # Step FA: 財務・決算書分析（月曜のみ）
    financial_analysis = {"available": False}
    try:
        if get_jst_now().weekday() == 0 or mode == "test":
            logger.info("--- Step FA: 財務・決算書分析 ---")
            from src.financial_analyzer import run as run_fa
            financial_analysis = run_fa(prices, risk, fear_greed)
            if financial_analysis.get("available"):
                logger.info(f"✅ 財務分析: {financial_analysis.get('count',0)}社完了")
        else:
            logger.info("財務分析: 月曜以外のためスキップ")
    except Exception:
        logger.error("財務分析エラー"); logger.debug(traceback.format_exc())

    # Step SD: 需給分析ランキング（月曜のみ・26銘柄で重いため）
    supply_demand = {"available": False}
    try:
        if get_jst_now().weekday() == 0 or mode == "test":
            logger.info("--- Step SD: 需給分析ランキング ---")
            from src.supply_demand import run as run_sd
            supply_demand = run_sd(prices, risk, fear_greed)
            if supply_demand.get("available"):
                top = supply_demand.get("top", [])
                top_name = top[0]["name"] if top else "---"
                logger.info(f"✅ 需給分析: {supply_demand.get('count',0)}銘柄 / 1位={top_name}")
        else:
            logger.info("需給分析: 月曜以外のためスキップ")
    except Exception:
        logger.error("需給分析エラー"); logger.debug(traceback.format_exc())

    # Step NEW-B: 割安株スキャン（月曜のみ）
    bargain = {"available": False}
    try:
        if get_jst_now().weekday() == 0 or mode == "test":
            logger.info("--- Step NEW-B: 割安株スキャン ---")
            from src.bargain_scanner import scan_bargain_stocks
            bargain = scan_bargain_stocks()
            if bargain.get("available"):
                logger.info(f"✅ 割安株スキャン: TOP{len(bargain.get('top_stocks',[]))}銘柄")
        else:
            logger.info("割安株スキャン: 月曜以外のためスキップ")
    except Exception:
        logger.error("割安株スキャンエラー"); logger.debug(traceback.format_exc())

    # Step NEW-D: 積立タイミング分析（月曜のみ）
    dca = {"available": False}
    try:
        if get_jst_now().weekday() == 0 or mode == "test":
            logger.info("--- Step NEW-D: 積立タイミング分析 ---")
            from src.dca_optimizer import analyze_dca_timing
            dca = analyze_dca_timing()
            if dca.get("available"):
                logger.info(f"✅ 積立最適日: {dca.get('best_day','---')}日 節約率{dca.get('saving_pct',0):.1f}%")
        else:
            logger.info("積立タイミング: 月曜以外のためスキップ")
    except Exception:
        logger.error("積立タイミング分析エラー"); logger.debug(traceback.format_exc())

    # Step L4c: FRED経済指標
    fred_data = {"available": False}
    try:
        logger.info("--- Step L4c: FRED経済指標 ---")
        from src.fred_data import run as run_fred
        fred_data = run_fred()
        if fred_data.get("available"):
            logger.info(f"✅ FRED取得完了: {fred_data.get('summary','')}")
    except Exception:
        logger.error("FRED取得エラー"); logger.debug(traceback.format_exc())

    # Step L4d: 資産間相関分析
    correlation = {"available": False}
    try:
        logger.info("--- Step L4d: 相関分析 ---")
        from src.correlation_analysis import run as run_corr
        correlation = run_corr()
        if correlation.get("available"):
            k = correlation.get("key", {})
            logger.info(f"✅ 相関分析完了: 日経-ドル円r={k.get('nikkei_usdjpy','---')}")
    except Exception:
        logger.error("相関分析エラー"); logger.debug(traceback.format_exc())

    # Step L4e: バックテスト（週1回：月曜のみ）
    backtest = {"available": False}
    try:
        weekday_now = get_jst_now().weekday()
        if weekday_now == 0 or mode == "test":
            logger.info("--- Step L4e: バックテスト ---")
            from src.backtest import run as run_bt
            backtest = run_bt()
            if backtest.get("available"):
                logger.info(f"✅ バックテスト完了: 最良={backtest.get('best_strategy','---')}")
        else:
            logger.info("バックテスト: 月曜以外のためスキップ")
    except Exception:
        logger.error("バックテストエラー"); logger.debug(traceback.format_exc())

    # Step L4f: センチメントデータ（P/C比率・AAII・COT）
    sentiment_data = {"available": False}
    try:
        logger.info("--- Step L4f: センチメントデータ ---")
        from src.sentiment_data import run as run_sent
        sentiment_data = run_sent()
        if sentiment_data.get("available"):
            logger.info(f"✅ センチメント: {sentiment_data.get('overall_signal','---')}")
    except Exception:
        logger.error("センチメントエラー"); logger.debug(traceback.format_exc())

    if correlation.get("chart_path"):
        chart_paths["correlation"] = correlation["chart_path"]
    if backtest.get("chart_path"):
        chart_paths["backtest"] = backtest["chart_path"]

    # Step L4h: モンテカルロ + マーコウィッツ（月曜のみ）
    monte_carlo = {"available": False}
    try:
        if get_jst_now().weekday() == 0 or mode == "test":
            logger.info("--- Step L4h: モンテカルロ + マーコウィッツ ---")
            from src.monte_carlo import run as run_mc
            monte_carlo = run_mc()
            if monte_carlo.get("available"):
                mc = monte_carlo.get("monte_carlo", {})
                logger.info(f"✅ MC完了: 利益確率={mc.get('prob_profit','---')}%")
            if monte_carlo.get("chart_path"):
                chart_paths["monte_carlo"] = monte_carlo["chart_path"]
    except Exception:
        logger.error("モンテカルロエラー"); logger.debug(traceback.format_exc())

    # Step L4i: FOMC議事録NLP分析（月曜のみ）
    fomc_sentiment = {"available": False}
    try:
        if get_jst_now().weekday() == 0 or mode == "test":
            logger.info("--- Step L4i: FOMC分析 ---")
            from src.fomc_sentiment import run as run_fomc
            fomc_sentiment = run_fomc()
            if fomc_sentiment.get("available"):
                logger.info(f"✅ FOMC: {fomc_sentiment.get('sentiment',{}).get('label','---')}")
    except Exception:
        logger.error("FOMC分析エラー"); logger.debug(traceback.format_exc())

    # Step L4j: 米議員株取引（月曜のみ）
    congress_trades = {"available": False}
    try:
        if get_jst_now().weekday() == 0 or mode == "test":
            logger.info("--- Step L4j: 米議員株取引 ---")
            from src.congress_trading import run as run_congress
            congress_trades = run_congress(days=14)
            if congress_trades.get("available"):
                logger.info(f"✅ 議員取引: {congress_trades.get('total_trades','---')}件")
    except Exception:
        logger.error("議員取引エラー"); logger.debug(traceback.format_exc())

    # Step MA: マクロ要約（毎日・FRED/FOMC/議員取引など全マクロデータを統合してAI要約）
    try:
        logger.info("--- Step MA: マクロ要約（ファンダ＋金融政策） ---")
        from src.macro_summary import run as run_ma
        macro = run_ma(prices=prices, news=news, fear_greed=fear_greed, risk=risk,
                       fred_data=fred_data, fomc_sentiment=fomc_sentiment,
                       econ_analysis=econ_analysis, sector_analysis=sector_analysis,
                       congress_trades=congress_trades)
        if macro.get("available"):
            logger.info(f"✅ マクロ要約: {'AI生成' if macro.get('ai_generated') else '簡易要約'} / 専門データ{len(macro.get('extra_sources',[]))}件統合")
    except Exception:
        logger.error("マクロ要約エラー"); logger.debug(traceback.format_exc())

    # ── Level 5 ─────────────────────────────────────────────

    # Step L5e: 自己批判エンジン（過去予測の反省学習）
    self_critique = {"available": False}
    try:
        logger.info("--- Step L5e: 自己批判エンジン ---")
        from src.self_critique import run as run_sc
        self_critique = run_sc(prices=prices, risk=risk)
        if self_critique.get("available"):
            logger.info(f"✅ 自己批判: 正解率{self_critique.get('accuracy','---')}% 教訓{len(self_critique.get('lessons',[]))}件")
        else:
            logger.info(f"自己批判: {self_critique.get('reason','データ不足')}")
    except Exception:
        logger.error("自己批判エンジンエラー"); logger.debug(traceback.format_exc())

    # Step L5f: Redditソーシャル感情分析（APIキー不要）
    reddit_sentiment = {"available": False}
    try:
        logger.info("--- Step L5f: Reddit感情分析 ---")
        from src.reddit_sentiment import run as run_reddit
        reddit_sentiment = run_reddit()
        if reddit_sentiment.get("available"):
            logger.info(f"✅ Reddit: {reddit_sentiment.get('signal','---')} (スコア:{reddit_sentiment.get('sentiment_score',0)})")
    except Exception:
        logger.error("Reddit感情分析エラー"); logger.debug(traceback.format_exc())

    # Step L5g: 決算前AI事前分析
    earnings_preview = {"available": False}
    try:
        logger.info("--- Step L5g: 決算前AI分析 ---")
        from src.earnings_preview import run as run_ep
        earnings_preview = run_ep()
        if earnings_preview.get("available"):
            n = earnings_preview.get("count", 0)
            msg = f"{n}件の決算" if n > 0 else "今週の主要決算なし"
            logger.info(f"✅ 決算前分析: {msg}")
    except Exception:
        logger.error("決算前分析エラー"); logger.debug(traceback.format_exc())

    # Step L5h: グローバル市場連鎖分析（日経→欧州→米国の連鎖）
    market_chain = {"available": False}
    try:
        logger.info("--- Step L5h: グローバル市場連鎖 ---")
        from src.market_chain import run as run_mc2
        market_chain = run_mc2(prices=prices)
        if market_chain.get("available"):
            sp_pred = market_chain.get("sp500_prediction", {})
            logger.info(f"✅ 市場連鎖: S&P500翌日予測={sp_pred.get('direction','---')} ({sp_pred.get('predicted_ret',0):+.2f}%)")
    except Exception:
        logger.error("市場連鎖分析エラー"); logger.debug(traceback.format_exc())

    # Step L5j: J-Quants 日本株スクリーナー（月曜のみ）
    jquants = {"available": False}
    try:
        if get_jst_now().weekday() == 0 or mode == "test":
            logger.info("--- Step L5j: J-Quants日本株スクリーナー ---")
            from src.jquants_screener import run as run_jq
            jquants = run_jq()
            if jquants.get("available"):
                logger.info(f"✅ J-Quants: {jquants.get('total_stocks',0)}銘柄分析完了")
        else:
            logger.info("J-Quants: 月曜以外のためスキップ")
    except Exception:
        logger.error("J-Quantsエラー"); logger.debug(traceback.format_exc())

    # Step L5a: マルチエージェント合議（4AI多数決）
    multi_consensus = {"available": False}
    try:
        logger.info("--- Step L5a: マルチエージェント合議 ---")
        from src.multi_agent_consensus import run as run_mac
        multi_consensus = run_mac(prices, risk, fear_greed, news,
                                  technical=technical, fred_data=fred_data)
        if multi_consensus.get("available"):
            v = multi_consensus.get("verdict", {})
            logger.info(f"✅ 合議: {v.get('direction','---')} {v.get('consensus_level','')}")
    except Exception:
        logger.error("マルチエージェント合議エラー"); logger.debug(traceback.format_exc())

    # Step L5b: 完全自律エージェント（今日のミッション決定）
    autonomous_plan = {"available": False}
    try:
        logger.info("--- Step L5b: 完全自律エージェント ---")
        from src.autonomous_orchestrator import run as run_auto
        autonomous_plan = run_auto(
            prices, risk, fear_greed, news,
            technical=technical,
            historical_analysis=historical_analysis,
            fred_data=fred_data,
            fomc_sentiment=fomc_sentiment,
            multi_consensus=multi_consensus,
        )
        if autonomous_plan.get("available"):
            logger.info(f"✅ 自律エージェント: {autonomous_plan.get('todays_mission','')[:50]}")
    except Exception:
        logger.error("自律エージェントエラー"); logger.debug(traceback.format_exc())

    # ★★★ Step L5: 完全自律チームディベート（NEW）★★★
    team_debate = {"available": False}
    try:
        logger.info("--- Step L5: 完全自律チームディベート ---")
        from src.ai_debate import run_team_debate
        
        # 市場データ文字列を構築
        market_data_str = f"""
        【市場データ】
        日経平均: {prices.get('^N225', {}).get('latest', '---')}円 ({prices.get('^N225', {}).get('change_pct', 0):+.2f}%)
        S&P500: {prices.get('^GSPC', {}).get('latest', '---')} ({prices.get('^GSPC', {}).get('change_pct', 0):+.2f}%)
        VIX: {prices.get('^VIX', {}).get('latest', '---')}
        ドル円: {prices.get('USDJPY=X', {}).get('latest', '---')} ({prices.get('USDJPY=X', {}).get('change_pct', 0):+.2f}%)
        リスクスコア: {risk.get('score', 0):.1f}
        Fear&Greed: {fear_greed.get('score', 'N/A')} ({fear_greed.get('rating_ja', 'N/A')})
        """
        
        news_text = "\n".join([f"・{n.get('title', '')}" for n in news[:5]])
        
        # チームディベート実行
        team_debate = run_team_debate(market_data_str, news_text)
        if team_debate.get("status") == "success":
            logger.info(f"✅ チームディベート完了: 最終判断 = 「{team_debate.get('final_decision', '---')}」 (信頼度: {team_debate.get('confidence', 0):.1%})")
            logger.info(f"   マーケット太郎: {team_debate.get('members', {}).get('マーケット太郎', {}).get('vote', '---')}")
            logger.info(f"   ニュース花子:   {team_debate.get('members', {}).get('ニュース花子', {}).get('vote', '---')}")
            logger.info(f"   リスク次郎:     {team_debate.get('members', {}).get('リスク次郎', {}).get('vote', '---')}")
        else:
            logger.info(f"チームディベート: {team_debate.get('status', '実行中')}")
    except Exception:
        logger.error("チームディベートエラー"); logger.debug(traceback.format_exc())

    # Step L5c: 強化学習ループ（予測パターン学習・ML予測）
    rl_result = {"available": False}
    try:
        logger.info("--- Step L5c: 強化学習ループ ---")
        from src.reinforcement_learning import run as run_rl
        rl_result = run_rl(prices, risk, fear_greed, technical=technical)
        if rl_result.get("available"):
            logger.info(f"✅ 強化学習: {rl_result.get('learning_summary','')[:60]}")
        else:
            logger.info(f"強化学習: {rl_result.get('reason','データ蓄積中')}")
    except Exception:
        logger.error("強化学習エラー"); logger.debug(traceback.format_exc())

    # Step 5f: 週次カレンダー（月曜朝のみ）
    weekly_calendar = {"available": False}
    try:
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

    # Step NEW-C: 今日の投資レッスン
    tutor = {"available": False}
    try:
        logger.info("--- Step NEW-C: 今日の投資レッスン ---")
        from src.investment_tutor import generate_daily_lesson
        tutor = generate_daily_lesson(prices, risk, fear_greed)
        if tutor.get("available"):
            logger.info(f"✅ 投資レッスン: {tutor.get('topic','')}")
    except Exception:
        logger.error("投資レッスンエラー"); logger.debug(traceback.format_exc())

    # Step NEW-E: FIREシミュレーター
    fire_result = {"available": False}
    try:
        logger.info("--- Step NEW-E: FIREシミュレーター ---")
        from src.fire_simulator import calc_fire_years
        fire_result = calc_fire_years()
        if fire_result.get("available"):
            logger.info(f"✅ FIRE: {fire_result.get('fire_age','---')}歳達成（あと{fire_result.get('fire_years','---')}年）")
    except Exception:
        logger.error("FIREシミュレーターエラー"); logger.debug(traceback.format_exc())

    # Step 6: チャート生成（matplotlibが使える場合）
    try:
        logger.info("--- Step 6: チャート生成 ---")
        from src.visualize import run as vis
        chart_paths = vis(prices, news, risk, fear_greed)
        logger.info(f"チャート生成: {len(chart_paths)}件")
    except Exception:
        logger.error("チャート生成エラー（続行）"); logger.debug(traceback.format_exc())

    # Step CHR: AIキャラクターコメント生成（ガネーシャ＆カワウソ）
    character_comments = {"available": False, "ganesha": "", "otter": ""}
    try:
        logger.info("--- Step CHR: AIキャラクターコメント生成 ---")
        from src.character_commentary import generate_comments
        character_comments = generate_comments(prices, risk, fear_greed, ai_summary=ai_summary)
        if character_comments.get("available"):
            logger.info("✅ ガネーシャ＆カワウソ コメント生成完了")
    except Exception:
        logger.error("キャラクターコメントエラー"); logger.debug(traceback.format_exc())

    # Step L5d: マルチモーダル分析（チャート画像をVisionで解析・Step6後に実行）
    multimodal = {"available": False}
    try:
        if chart_paths:
            logger.info("--- Step L5d: マルチモーダル Vision分析 ---")
            from src.multimodal_analysis import run as run_mm
            multimodal = run_mm(chart_paths, prices, technical=technical)
            if multimodal.get("available"):
                logger.info(f"✅ Vision分析: direction={multimodal.get('direction','---')}")
    except Exception:
        logger.error("マルチモーダル分析エラー"); logger.debug(traceback.format_exc())

    # Step L5i: LINE通知（Telegramと並行送信）
    try:
        logger.info("--- Step L5i: LINE通知 ---")
        from src.notify_line import run as run_line
        run_line(
            risk, fear_greed, prices, report_paths,
            ai_summary=ai_summary,
            chart_paths=chart_paths,
            multi_consensus=multi_consensus,
            autonomous_plan=autonomous_plan,
        )
    except Exception:
        logger.error("LINE通知エラー"); logger.debug(traceback.format_exc())

    # Step L5k: デザインAIレポート（docs/daily_report.html）
    design_report = {"available": False}
    try:
        logger.info("--- Step L5k: デザインAIレポート ---")
        from src.design_ai import run as run_design
        design_report = run_design(
            prices=prices, news=news, risk=risk, fear_greed=fear_greed,
            ai_summary=ai_summary, scenario=scenario, technical=technical,
            sector_analysis=sector_analysis, prediction_tracker=prediction_tracker,
            weekly_calendar=weekly_calendar, team_debate=team_debate,
            youtube_summary=youtube_summary,
            mode=mode,
        )
        if design_report.get("available"):
            logger.info(f"✅ デザインAIレポート: {design_report.get('path','')}")
    except Exception:
        logger.error("デザインAIエラー"); logger.debug(traceback.format_exc())

    # Step 7: HTMLレポート生成
    report_paths = {}
    try:
        logger.info("--- Step 7: HTMLレポート生成 ---")
        _save_html_report(mode, prices, news, risk, analysis, fear_greed, chart_paths,
                          ai_summary, econ_analysis, youtube_summary, memory_analysis,
                          agent_report, technical, portfolio, scenario, prediction_tracker,
                          character_comments=character_comments,
                          news_bias=news_bias, fire_result=fire_result, bargain=bargain,
                          tutor=tutor, dca=dca, notif_filter=notif_filter,
                          portfolio_alerts=portfolio_alerts,
                          financial_analysis=financial_analysis,
                          theme_ranking=theme_ranking,
                          tdnet=tdnet,
                          weekly_calendar=weekly_calendar,
                          anomaly=anomaly,
                          supply_demand=supply_demand,
                          macro=macro,
                          earnings_brief=earnings_brief)
        today = get_today_str()
        report_paths = {
            "html": str(get_dirs()["reports"] / f"{today}_{mode}.html"),
            "md":   str(get_dirs()["reports"] / f"{today}_{mode}.md"),
            # GitHub Pages は main/docs を公開する。docs/daily_report.html が
            # デザインAIレポートの公開先なので、必ずこのURLを案内する
            # （日付つき {today}_{mode}.html は reports/ にしか無く Pages では 404）
            "url":  f"{PAGES_URL}/daily_report.html",
        }
    except Exception:
        logger.error("レポート生成エラー"); logger.debug(traceback.format_exc())

    # Step NEW-G: 通知重要度フィルター
    notif_filter = {"importance_score": 5, "level": "MEDIUM", "send_full_report": True}
    try:
        logger.info("--- Step NEW-G: 通知重要度フィルター ---")
        from src.notification_filter import score_notification_importance
        notif_filter = score_notification_importance(prices, risk, fear_greed)
        logger.info(f"✅ 通知重要度: {notif_filter.get('importance_score',0):.1f} [{notif_filter.get('level','---')}]")
    except Exception:
        logger.error("通知フィルターエラー"); logger.debug(traceback.format_exc())

    # Step 8: Telegram通知
    try:
        logger.info("--- Step 8: Telegram通知 ---")
        from src.notify_telegram import run as notify_tg
        # テクニカル・ポートフォリオチャートを追加
        if technical.get("chart_path"):
            chart_paths["technical"] = technical["chart_path"]
        if portfolio.get("chart_path"):
            chart_paths["portfolio"] = portfolio["chart_path"]

        if sector_chart_path:
            chart_paths["sector"] = sector_chart_path

        notify_tg(risk, analysis, report_paths, mode,
                  prices=prices, news=news,
                  fear_greed=fear_greed, ai_summary=ai_summary,
                  chart_paths=chart_paths,
                  weekly_calendar=weekly_calendar,
                  agent_report=agent_report,
                  technical=technical,
                  portfolio=portfolio,
                  scenario=scenario,
                  prediction_tracker=prediction_tracker,
                  sector_analysis=sector_analysis,
                  historical_analysis=historical_analysis,
                  fred_data=fred_data,
                  correlation=correlation,
                  backtest=backtest,
                  sentiment_data=sentiment_data,
                  monte_carlo=monte_carlo,
                  fomc_sentiment=fomc_sentiment,
                  congress_trades=congress_trades,
                  multi_consensus=multi_consensus,
                  autonomous_plan=autonomous_plan,
                  rl_result=rl_result,
                  multimodal=multimodal,
                  self_critique=self_critique,
                  reddit_sentiment=reddit_sentiment,
                  earnings_preview=earnings_preview,
                  market_chain=market_chain,
                  jquants=jquants,
                  tdnet=tdnet,
                  anomaly=anomaly,
                  supply_demand=supply_demand,
                  macro=macro,
                  earnings_brief=earnings_brief,
                  character_comments=character_comments)
    except Exception:
        logger.error("Telegram通知エラー"); logger.debug(traceback.format_exc())

    logger.info(f"====== クラウド実行完了 ======")
    print(f"\n✅ 完了 | 地合い: {risk.get('sentiment')} | "
          f"F&G: {fear_greed.get('score')} ({fear_greed.get('rating_ja')}) | "
          f"ニュース: {len(news)}件 | チャート: {len(chart_paths)}件")


def _save_html_report(mode, prices, news, risk, analysis, fear_greed, chart_paths,
                      ai_summary=None, econ_analysis=None, youtube_summary=None,
                      memory_analysis="", agent_report=None, technical=None,
                      portfolio=None, scenario=None, prediction_tracker=None,
                      character_comments=None,
                      news_bias=None, fire_result=None, bargain=None,
                      tutor=None, dca=None, notif_filter=None, portfolio_alerts=None,
                      financial_analysis=None, theme_ranking=None, tdnet=None,
                      weekly_calendar=None, anomaly=None, supply_demand=None,
                      macro=None, earnings_brief=None):
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
    character_comments = character_comments or {}

    # キャラクターHTMLセクション生成
    char_html_section = ""
    try:
        from src.character_commentary import get_character_html, CHARACTER_CSS
        if character_comments.get("available"):
            char_html_section = get_character_html(
                character_comments.get("ganesha", ""),
                character_comments.get("otter", ""),
                mood=character_comments.get("mood", "neutral"),
            )
    except Exception:
        CHARACTER_CSS = ""
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

    # ── Level 3: 自律AIエージェントHTML ──────────────────────
    agent_report = agent_report or {}
    agent_html = ""
    if agent_report.get("available"):
        secs = agent_report.get("sections", {})
        full = agent_report.get("full_report","")
        tc   = agent_report.get("tool_count", 0)
        agent_html += f'<div class="debate-intro">🤖 AIエージェントが<strong>{tc}回</strong>ツールを自律呼び出しして分析しました</div>'
        if secs.get("summary"):
            agent_html += f'<div class="bubble" style="border-left:4px solid #00d4ff;background:linear-gradient(135deg,#071520,#0a1f2e);"><div class="bubble-head" style="color:#00d4ff;">📋 エージェント総評</div><div class="bubble-text">{secs["summary"]}</div></div>'
        if secs.get("technical"):
            agent_html += f'<div class="bubble" style="border-left:4px solid #f0c060;background:linear-gradient(135deg,#1a1500,#231c00);"><div class="bubble-head" style="color:#f0c060;">📐 テクニカル分析</div><div class="bubble-text">{secs["technical"]}</div></div>'
        if secs.get("scenario"):
            agent_html += f'<div class="bubble" style="border-left:4px solid #bc8cff;background:linear-gradient(135deg,#100a20,#18102e);"><div class="bubble-head" style="color:#bc8cff;">🎭 シナリオ考察</div><div class="bubble-text">{secs["scenario"]}</div></div>'
        if secs.get("judgment"):
            agent_html += f'<div class="bubble" style="border-left:4px solid #3fb950;background:linear-gradient(135deg,#0a1f10,#0d2b18);"><div class="bubble-head" style="color:#3fb950;">⚡ 最終判断</div><div class="bubble-text">{secs["judgment"]}</div></div>'

    # ── Level 3: テクニカル分析HTML ────────────────────────
    technical = technical or {}
    tech_html = ""
    if technical.get("available"):
        ai_comment = technical.get("ai_comment","")
        if ai_comment:
            tech_html += f'<div class="debate-intro">{ai_comment}</div>'
        for r in technical.get("results",[]):
            if "error" in r: continue
            label   = r.get("label", r.get("symbol",""))
            rsi     = r.get("rsi", 50)
            rsi_sig = r.get("rsi_signal","")
            bb_pct  = r.get("bb_pct", 50)
            bb_sig  = r.get("bb_signal","")
            macd_h  = r.get("macd_hist",0)
            trend   = r.get("trend","")
            rsi_c   = "#f44336" if rsi>70 else "#3fb950" if rsi<30 else "#ffd740"
            bb_c    = "#f44336" if bb_pct>80 else "#3fb950" if bb_pct<20 else "#ffd740"
            macd_c  = "#3fb950" if macd_h>=0 else "#f44336"
            tech_html += f'''<div class="econ-row">
              <div class="econ-icon">📐</div>
              <div style="flex:1">
                <div class="econ-lbl">{label}</div>
                <div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:4px;">
                  <span style="color:{rsi_c};font-size:0.85em;">RSI:{rsi:.0f} {rsi_sig}</span>
                  <span style="color:{bb_c};font-size:0.85em;">BB:{bb_pct:.0f}% {bb_sig}</span>
                  <span style="color:{macd_c};font-size:0.85em;">MACD:{macd_h:+.3f}</span>
                  <span style="color:#8899aa;font-size:0.85em;">{trend}</span>
                </div>
              </div>
            </div>'''

    # ── Level 3: ポートフォリオHTML ────────────────────────
    portfolio = portfolio or {}
    pf_html = ""
    if portfolio.get("available"):
        total_pct = portfolio.get("total_pnl_pct",0)
        total_pnl = portfolio.get("total_pnl",0)
        tc = "#3fb950" if total_pct>=0 else "#f44336"
        pf_html += f'<div style="text-align:center;font-size:1.3em;font-weight:800;color:{tc};margin-bottom:12px;">{"▲" if total_pct>=0 else "▼"}{abs(total_pct):.2f}%  ({total_pnl:+,.0f}円)</div>'
        for h in portfolio.get("holdings",[]):
            pct = h.get("pnl_pct") or 0
            pc  = "#3fb950" if pct>=0 else "#f44336"
            pf_html += f'<div class="econ-row"><div class="econ-icon">{"📈" if pct>=0 else "📉"}</div><div><div class="econ-lbl">{h.get("name",h.get("symbol",""))}</div><div style="color:{pc};font-weight:700;">{pct:+.2f}% ({h.get("pnl",0):+,.0f}円)</div><div style="color:#8899aa;font-size:0.75em;">取得:{h.get("buy_price",0):,.2f} → 現在:{h.get("current",0):,.2f}</div></div></div>'
        for alert in portfolio.get("alerts",[]):
            pf_html += f'<div style="background:#2a0a0a;border:1px solid #f44336;border-radius:8px;padding:10px;margin-top:8px;color:#f44336;">{alert.get("msg","")}</div>'

    # ── Level 3: シナリオHTML ──────────────────────────────
    scenario = scenario or {}
    scen_html = ""
    if scenario.get("available"):
        def scen_card(data, icon, color, bg):
            if not data: return ""
            prob = data.get("prob","?")
            text = data.get("text","")[:300]
            return f'<div class="bubble" style="border-left:4px solid {color};background:{bg};"><div class="bubble-head" style="color:{color};">{icon} 確率 {prob}%</div><div class="bubble-text">{text}</div></div>'
        scen_html += scen_card(scenario.get("bull",{}), "🟢 楽観シナリオ（強気）", "#3fb950", "linear-gradient(135deg,#0a1f10,#0d2b18)")
        scen_html += scen_card(scenario.get("base",{}), "🟡 基本シナリオ（中立）", "#ffd740", "linear-gradient(135deg,#1f1a00,#2b2400)")
        scen_html += scen_card(scenario.get("bear",{}), "🔴 悲観シナリオ（弱気）", "#f44336", "linear-gradient(135deg,#200a0a,#2b0d0d)")
        if scenario.get("top_risk"):
            scen_html += f'<div style="background:#1a0f00;border:1px solid #ff9800;border-radius:12px;padding:14px;margin-top:8px;"><div style="color:#ff9800;font-weight:700;margin-bottom:6px;">⚡ 最注目リスク</div><div>{scenario["top_risk"]}</div></div>'

    # ── Level 3: 予測学習・精度HTML ────────────────────────
    prediction_tracker = prediction_tracker or {}
    pred_html = ""
    if prediction_tracker.get("available"):
        stats  = prediction_tracker.get("stats", {})
        r10    = stats.get("10d", {})
        r30    = stats.get("30d", {})
        recent = stats.get("recent5", [])
        la     = prediction_tracker.get("learning_analysis", "")

        # 正解率バー
        rate10 = r10.get("rate")
        if rate10 is not None:
            bar_color = "#3fb950" if rate10 >= 65 else "#ffd740" if rate10 >= 50 else "#f44336"
            bar_emoji = "🎯" if rate10 >= 65 else "🔶" if rate10 >= 50 else "⚠️"
            pred_html += f'''
            <div style="margin-bottom:16px;">
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                <span style="font-weight:700;font-size:0.9em;">{bar_emoji} 直近10日の正解率</span>
                <span style="font-size:1.5em;font-weight:900;color:{bar_color};">{rate10}%</span>
              </div>
              <div style="background:#1e2d42;border-radius:8px;height:16px;overflow:hidden;">
                <div style="height:100%;background:{bar_color};border-radius:8px;width:{rate10}%;transition:width 0.8s;"></div>
              </div>
              <div style="display:flex;justify-content:space-between;font-size:0.68em;color:#7a8fa8;margin-top:4px;">
                <span>正解: {r10.get("correct",0)}/{r10.get("total",0)}日</span>
                <span>{'精度良好 ✅' if rate10>=65 else '普通 🔶' if rate10>=50 else '要改善 ⚠️'}</span>
              </div>
            </div>'''

        # 直近5日カード
        if recent:
            pred_html += '<div style="margin-bottom:12px;"><div style="font-size:0.75em;color:#7a8fa8;font-weight:700;margin-bottom:8px;letter-spacing:1px;">📅 直近の予測と結果</div>'
            pred_html += '<div style="display:grid;grid-template-columns:repeat(5,1fr);gap:6px;">'
            icons = {"bull": "📈", "bear": "📉", "neutral": "➡️"}
            for r in recent:
                mark  = "✅" if r.get("correct") else "❌" if r.get("correct") is False else "⏳"
                icon  = icons.get(r.get("direction",""), "")
                move  = f"{r['move']:+.1f}%" if r.get("move") is not None else "---"
                color = "#3fb950" if r.get("correct") else "#f44336" if r.get("correct") is False else "#8899aa"
                pred_html += f'<div style="background:#0f1623;border:1px solid {color}44;border-radius:10px;padding:8px;text-align:center;"><div style="font-size:1.1em;">{mark}</div><div style="font-size:0.6em;color:#7a8fa8;">{r.get("date","")[-5:]}</div><div style="font-size:0.7em;">{icon}</div><div style="font-size:0.7em;color:{color};font-weight:700;">{move}</div></div>'
            pred_html += '</div></div>'

        # 学習フィードバック分析
        if la:
            pred_html += f'<div style="background:linear-gradient(135deg,#070f1f,#0a1428);border:1px solid #00d4ff33;border-radius:12px;padding:14px;margin-top:8px;"><div style="color:#00d4ff;font-weight:700;font-size:0.8em;margin-bottom:8px;">🧠 AIの自己分析（過去の結果を踏まえて）</div><div style="font-size:0.85em;line-height:1.75;white-space:pre-wrap;">{la}</div></div>'

    # ── YouTube HTML ──────────────────────────────────────
    yt_html = ""
    if youtube_summary.get("available"):
        if youtube_summary.get("points"):
            yt_html += f'<div class="yt-section"><div class="yt-head">💡 動画のポイント</div><div class="yt-text">{youtube_summary["points"]}</div></div>'
        if youtube_summary.get("impact"):
            yt_html += f'<div class="yt-section"><div class="yt-head">📊 市場への示唆</div><div class="yt-text">{youtube_summary["impact"]}</div></div>'
        for v in youtube_summary.get("videos",[])[:4]:
            yt_html += f'<div class="yt-video"><span>🎬</span><a href="{v.get("url","")}" target="_blank" rel="noopener">{v.get("title","")}</a></div>'

    # ── テーマ株ランキングHTML ────────────────────────────────
    theme_ranking = theme_ranking or {}
    theme_html = theme_ranking.get("html", "") if theme_ranking.get("available") else ""

    # ── TDnet適時開示HTML ─────────────────────────────────────
    tdnet = tdnet or {}
    tdnet_html = tdnet.get("html", "") if tdnet.get("available") else ""

    # ── 今後の決算予定 + 天体イベントHTML ─────────────────────
    weekly_calendar = weekly_calendar or {}
    calendar_extra_html = ""
    if weekly_calendar.get("upcoming_earnings") or weekly_calendar.get("astro"):
        try:
            from src.economic_calendar import get_html as cal_get_html
            calendar_extra_html = cal_get_html(weekly_calendar)
        except Exception:
            calendar_extra_html = ""

    # ── アノマリーカレンダーHTML ───────────────────────────────
    anomaly = anomaly or {}
    anomaly_html = anomaly.get("html", "") if anomaly.get("available") else ""

    # ── 需給分析ランキングHTML ─────────────────────────────────
    supply_demand = supply_demand or {}
    sd_html = supply_demand.get("html", "") if supply_demand.get("available") else ""

    # ── マクロ要約HTML（ファンダ＋金融政策） ───────────────────
    macro = macro or {}
    macro_html = macro.get("html", "") if macro.get("available") else ""

    # ── 決算ブリーフHTML（決算PDFのAI要約） ───────────────────
    earnings_brief = earnings_brief or {}
    eb_html = earnings_brief.get("html", "") if earnings_brief.get("available") else ""

    # ── 財務・決算書分析HTML ──────────────────────────────────
    financial_analysis = financial_analysis or {}
    fa_html = ""
    if financial_analysis.get("available"):
        try:
            from src.financial_analyzer import get_html as fa_get_html
            fa_html = fa_get_html(financial_analysis)
        except Exception:
            fa_html = ""

    # ── 煽りニュース検出HTML ─────────────────────────────────
    news_bias = news_bias or {}
    bias_html = ""
    if news_bias.get("available"):
        avg = news_bias.get("avg_score", 0)
        top = news_bias.get("top_biased", [])
        bias_color = "#ff1744" if avg >= 6 else "#ff9800" if avg >= 4 else "#00e676"
        bias_html += f'<div style="text-align:center;margin-bottom:14px;"><span style="font-size:1.8em;font-weight:900;color:{bias_color};">{avg:.1f}<span style="font-size:0.5em;color:#8899aa;"> / 10</span></span><div style="color:#8899aa;font-size:0.75em;margin-top:2px;">平均煽りスコア</div></div>'
        for item in top[:3]:
            sc = item.get("bias_score", 0)
            lbl = item.get("bias_label", "")
            sc_c = "#ff1744" if sc >= 6 else "#ff9800" if sc >= 4 else "#8899aa"
            bias_html += f'<div class="econ-row"><div class="econ-icon">📰</div><div><div class="econ-lbl" style="color:{sc_c};">{lbl} (スコア:{sc:.1f})</div><div style="font-size:0.82em;">{item.get("title","")[:80]}</div></div></div>'

    # ── FIREシミュレーターHTML ─────────────────────────────
    fire_result = fire_result or {}
    fire_html = ""
    if fire_result.get("available"):
        fy = fire_result.get("fire_years", "?")
        fa = fire_result.get("fire_age", "?")
        fpct = fire_result.get("progress_pct", 0)
        ftgt = fire_result.get("fire_target", 0)
        bar_c = "#3fb950" if fpct >= 50 else "#ffd740" if fpct >= 25 else "#ff6d00"
        fire_html += f'<div style="text-align:center;margin-bottom:16px;"><div style="font-size:2em;font-weight:900;color:#ffd740;">{fa}歳</div><div style="color:#8899aa;font-size:0.8em;">FIRE達成目標（あと{fy}年）</div><div style="color:#8899aa;font-size:0.72em;margin-top:4px;">目標額: {int(ftgt)//10000}万円</div></div>'
        fire_html += f'<div style="background:#1e2d42;border-radius:8px;height:16px;margin-bottom:4px;overflow:hidden;"><div style="height:100%;background:{bar_c};width:{min(fpct,100):.1f}%;border-radius:8px;"></div></div>'
        fire_html += f'<div style="display:flex;justify-content:space-between;font-size:0.68em;color:#7a8fa8;margin-bottom:12px;"><span>現在達成率</span><span style="color:{bar_c};font-weight:700;">{fpct:.1f}%</span></div>'
        for ms in fire_result.get("milestones", [])[:4]:
            done = ms.get("reached", False)
            ic = "✅" if done else "⏳"
            fire_html += f'<div class="econ-row"><div class="econ-icon">{ic}</div><div><div class="econ-lbl">{ms.get("label","")}</div><div style="font-size:0.8em;color:#8899aa;">{ms.get("years",0):.1f}年後達成</div></div></div>'

    # ── 割安株スキャンHTML ─────────────────────────────────
    bargain = bargain or {}
    bargain_html = ""
    if bargain.get("available"):
        for s in bargain.get("top_stocks", [])[:5]:
            score_v = s.get("total_score", 0)
            sc_c = "#ffd740" if score_v >= 60 else "#8899aa"
            per_v = s.get("per") or 0
            pbr_v = s.get("pbr") or 0
            div_v = s.get("dividend") or 0
            bargain_html += f'<div class="econ-row"><div class="econ-icon">🏆</div><div><div class="econ-lbl" style="color:{sc_c};">{s.get("name", s.get("symbol",""))} (スコア:{score_v:.0f})</div><div style="font-size:0.8em;color:#8899aa;">PER:{per_v:.1f} PBR:{pbr_v:.2f} 配当:{div_v:.1f}%</div></div></div>'

    # ── 投資レッスンHTML ──────────────────────────────────
    tutor = tutor or {}
    tutor_html = ""
    if tutor.get("available"):
        topic = tutor.get("topic", "")
        lesson = tutor.get("lesson", "")
        takeaway = tutor.get("key_takeaway", "")
        tutor_html += f'<div style="background:linear-gradient(135deg,#0a1428,#0f1a33);border:1px solid #7b61ff44;border-radius:12px;padding:14px;margin-bottom:10px;"><div style="color:#7b61ff;font-weight:700;font-size:0.85em;margin-bottom:8px;">📚 今日のテーマ: {topic}</div><div style="font-size:0.88em;line-height:1.75;white-space:pre-wrap;">{lesson}</div></div>'
        if takeaway:
            tutor_html += f'<div style="background:#0d1f10;border:1px solid #3fb95044;border-radius:10px;padding:12px;"><div style="color:#3fb950;font-weight:700;font-size:0.8em;margin-bottom:6px;">💡 今日のポイント</div><div style="font-size:0.88em;">{takeaway}</div></div>'

    # ── 積立タイミングHTML ────────────────────────────────
    dca = dca or {}
    dca_html = ""
    if dca.get("available"):
        best = dca.get("best_day", "?")
        worst = dca.get("worst_day", "?")
        saving = dca.get("saving_pct", 0)
        insight = dca.get("insight", "")
        dca_html += f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:12px;"><div style="background:#0a1f10;border:1px solid #3fb95044;border-radius:10px;padding:12px;text-align:center;"><div style="font-size:1.5em;font-weight:900;color:#3fb950;">{best}日</div><div style="color:#8899aa;font-size:0.72em;">最適な積立日</div></div><div style="background:#1f0a0a;border:1px solid #f4433644;border-radius:10px;padding:12px;text-align:center;"><div style="font-size:1.5em;font-weight:900;color:#f44336;">{worst}日</div><div style="color:#8899aa;font-size:0.72em;">コスト高になる日</div></div></div>'
        if saving > 0:
            dca_html += f'<div style="text-align:center;color:#ffd740;font-size:0.85em;margin-bottom:8px;">💰 最適日と最悪日の差: {saving:.2f}%節約</div>'
        if insight:
            dca_html += f'<div style="background:#0f1623;border-radius:8px;padding:10px;font-size:0.85em;color:#8899aa;">{insight}</div>'

    # ── 保有銘柄アラートHTML ──────────────────────────────
    portfolio_alerts = portfolio_alerts or {}
    palert_html = ""
    if portfolio_alerts.get("available"):
        alerts = portfolio_alerts.get("alerts", [])
        for a in alerts:
            alv = a.get("level", "info")
            alc = "#ff1744" if alv == "critical" else "#ff9800" if alv == "warning" else "#3fb950"
            chg = a.get("change_pct") or 0
            unr = a.get("unrealized_pnl_pct") or 0
            chg_c = "#3fb950" if chg >= 0 else "#f44336"
            unr_c = "#3fb950" if unr >= 0 else "#f44336"
            palert_html += f'<div style="background:#1a0d00;border:1px solid {alc}55;border-radius:10px;padding:12px;margin-bottom:8px;"><div style="color:{alc};font-weight:700;font-size:0.85em;">{a.get("name","")}</div><div style="font-size:0.8em;color:#8899aa;margin-top:4px;">当日変動: <span style="color:{chg_c};">{chg:+.1f}%</span>　含み損益: <span style="color:{unr_c};">{unr:+.1f}%</span></div><div style="font-size:0.78em;color:{alc};margin-top:4px;">{a.get("message","")}</div></div>'
        if not alerts:
            palert_html += '<div style="text-align:center;color:#3fb950;padding:12px;">✅ 異常なし — 保有銘柄は正常範囲内です</div>'

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

{CHARACTER_CSS}

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

  <!-- キャラクターコメント（ガネーシャ & カワウソ） -->
  {char_html_section}

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

  <!-- Level 3: 自律AIエージェント -->
  {f'<div class="sec-head">🤖 Level 3 自律AIエージェント分析</div><div class="debate-wrap">{agent_html}</div>' if agent_html else ""}

  <!-- Level 3: シナリオ分析 -->
  {f'<div class="sec-head">🎭 3シナリオ分析（楽観・基本・悲観）</div><div class="debate-wrap">{scen_html}</div>' if scen_html else ""}

  <!-- Level 3: テクニカル分析 -->
  {f'<div class="sec-head">📐 テクニカル分析（RSI・MACD・ボリンジャー）</div><div class="econ-wrap">{tech_html}</div>' if tech_html else ""}
  {(f'<img src="data:image/png;base64,{__import__("base64").b64encode(open(technical["chart_path"],"rb").read()).decode()}" class="chart-img">') if technical and technical.get("chart_path") and Path(technical["chart_path"]).exists() else ""}

  <!-- Level 3: ポートフォリオ -->
  {f'<div class="sec-head">💼 ポートフォリオ損益管理</div><div class="econ-wrap">{pf_html}</div>' if pf_html else ""}
  {(f'<img src="data:image/png;base64,{__import__("base64").b64encode(open(portfolio["chart_path"],"rb").read()).decode()}" class="chart-img">') if portfolio and portfolio.get("chart_path") and Path(portfolio["chart_path"]).exists() else ""}

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

  <!-- 予測学習・精度トラッカー -->
  {f'<div class="sec-head">🧠 AI予測学習レポート（正解率・精度向上）</div><div class="econ-wrap">{pred_html}</div>' if pred_html else ""}

  <!-- YouTube -->
  {f'<div class="sec-head">📺 YouTube注目動画まとめ</div><div class="yt-wrap">{yt_html}</div>' if yt_html else ""}

  <!-- ファンダメンタル＋金融政策の要約（毎日） -->
  {f'<div class="sec-head">🌐 ファンダ＆金融政策の要約</div>{macro_html}' if macro_html else ""}

  <!-- TDnet適時開示アラート（ウォッチリスト銘柄のみ） -->
  {f'<div class="sec-head">📋 適時開示アラート（あなたの注目銘柄）</div>{tdnet_html}' if tdnet_html else ""}

  <!-- 決算ブリーフ（決算PDFのAI要約） -->
  {f'<div class="sec-head">📑 決算ブリーフ（AIが中身を要約）</div>{eb_html}' if eb_html else ""}

  <!-- 今後の決算予定 + 天体イベント（月曜のみ） -->
  {f'<div class="sec-head">🗓️ 決算予定＆イベントカレンダー</div>{calendar_extra_html}' if calendar_extra_html else ""}

  <!-- 今日のアノマリー（相場の経験則・毎日） -->
  {f'<div class="sec-head">📜 今日のアノマリー</div>{anomaly_html}' if anomaly_html else ""}

  <!-- 需給分析ランキング（月曜のみ） -->
  {f'<div class="sec-head">📊 需給分析ランキング（買いの勢いが強い順）</div>{sd_html}' if sd_html else ""}

  <!-- テーマ株人気ランキング -->
  {f'<div class="sec-head">🔥 テーマ株人気ランキング（今週どのテーマが熱い？）</div>{theme_html}' if theme_html else ""}

  <!-- 財務・決算書分析（月曜のみ） -->
  {f'<div class="sec-head">📊 財務・決算書分析（フジクラ・ソフトバンクG・村田製作所 他）</div>{fa_html}' if fa_html else ""}

  <!-- 煽りニュース検出 -->
  {f'<div class="sec-head">🔍 ニュース煽り度チェック</div><div class="econ-wrap">{bias_html}</div>' if bias_html else ""}

  <!-- 今日の投資レッスン -->
  {f'<div class="sec-head">📚 今日の投資レッスン</div><div class="econ-wrap">{tutor_html}</div>' if tutor_html else ""}

  <!-- 割安株スキャン（月曜のみ） -->
  {f'<div class="sec-head">🏆 割安株スキャン（バリュー投資候補）</div><div class="econ-wrap">{bargain_html}</div>' if bargain_html else ""}

  <!-- 積立タイミング分析（月曜のみ） -->
  {f'<div class="sec-head">📅 積立最適タイミング分析（過去10年データ）</div><div class="econ-wrap">{dca_html}</div>' if dca_html else ""}

  <!-- FIREシミュレーター -->
  {f'<div class="sec-head">🔥 FIREシミュレーター（経済的自由への道）</div><div class="econ-wrap">{fire_html}</div>' if fire_html else ""}

  <!-- 保有銘柄アラート -->
  {f'<div class="sec-head">🔔 保有銘柄アラート</div><div class="econ-wrap">{palert_html}</div>' if palert_html else ""}

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

    # モバイル最適化レポートも同時生成
    try:
        from src.mobile_html import generate as gen_mobile
        gen_mobile(
            mode=mode, prices=prices, news=news, risk=risk,
            fear_greed=fear_greed, chart_paths=chart_paths,
            ai_summary=ai_summary, scenario=scenario,
            prediction_tracker=prediction_tracker, technical=technical,
        )
    except Exception:
        logger.debug("モバイルHTML生成スキップ")

    logger.info(f"HTMLレポート保存: {html_path}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["morning","noon","evening","test"], default="morning")
    run(p.parse_args().mode)


if __name__ == "__main__":
    main()
