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

    # Step 1.5: データ健全性チェック（誤データの汚染を防ぐ）
    data_integrity = {"available": False}
    try:
        logger.info("--- Step 1.5: データ健全性チェック ---")
        from src.data_integrity import check as check_integrity
        data_integrity = check_integrity(prices)
        if data_integrity.get("max_severity") == "high":
            logger.warning(f"⚠️ データ異常: {data_integrity.get('summary')}")
        else:
            logger.info(f"✅ {data_integrity.get('summary')}")
    except Exception:
        logger.error("データ健全性チェックエラー"); logger.debug(traceback.format_exc())

    # Step 1.6: 多重ソース照合（Yahoo ＋ Stooq で主要8シンボルをクロスチェック）
    source_verify_summary = {"verified": 0, "single_source": 0, "disagreement": 0}
    try:
        logger.info("--- Step 1.6: 多重ソース照合 ---")
        from src.source_verify import run as run_sv
        prices, source_verify_summary = run_sv(prices)
        disc = source_verify_summary.get("disagreement", 0)
        if disc:
            logger.warning(f"⚠️ ソース乖離: {disc}件 → 中央値で補正済み")
        else:
            logger.info(f"✅ 多重照合OK: 一致={source_verify_summary.get('verified')}件")
    except Exception:
        logger.error("多重ソース照合エラー（スキップ）"); logger.debug(traceback.format_exc())

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

    # Step 4.5: 爆速通知 ─ AI解析前に価格＋リスクを即テキスト送信（開始60秒以内）
    try:
        logger.info("--- Step 4.5: 爆速通知（価格・リスク速報） ---")
        from src.notify_telegram import send_message

        def _fv(sym, dp=0, unit=""):
            d = prices.get(sym, {})
            v = d.get("latest")
            c = d.get("change_pct")
            if v is None:
                return "---"
            arrow = "▲" if (c or 0) >= 0 else "▼"
            return f"{v:,.{dp}f}{unit} ({arrow}{abs(c or 0):.2f}%)"

        _fg     = fear_greed.get("score")
        _fg_s   = f"{int(_fg)}" if _fg is not None else "---"
        _fg_r   = fear_greed.get("rating_ja", "---")
        _rscore = risk.get("score", 0)
        _rsent  = risk.get("sentiment", "不明")
        _r_sign = "+" if _rscore >= 0 else ""
        _now_s  = get_jst_now().strftime("%m/%d %H:%M")

        _early_msg = "\n".join([
            f"⚡ *朝の速報* — {_now_s} JST",
            "━━━━━━━━━━━━━━━",
            f"🇯🇵 日経225: *{_fv('^N225', 0)}*",
            f"🇺🇸 S&P500: *{_fv('^GSPC', 0)}*",
            f"🇺🇸 NASDAQ: *{_fv('^IXIC', 0)}*",
            f"💴 USD/JPY: *{_fv('USDJPY=X', 2, '円')}*",
            f"😱 VIX: *{_fv('^VIX', 2)}*",
            "━━━━━━━━━━━━━━━",
            f"🌡 地合い: *{_rsent}* ({_r_sign}{_rscore:.1f}pt)",
            f"😰 Fear&Greed: *{_fg_s}* ({_fg_r})",
            "━━━━━━━━━━━━━━━",
            "📊 *AI詳細分析は10〜20分後に届きます*",
        ])
        send_message(_early_msg)
        logger.info("✅ 爆速通知送信完了")
    except Exception:
        logger.error("爆速通知エラー（メインパイプラインは継続）")
        logger.debug(traceback.format_exc())

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

    # Step 5b.5: 校閲ループ（断定軟化・空セクション除去・捏造数字検出）
    try:
        logger.info("--- Step 5b.5: 校閲ループ ---")
        from src.editorial_qa import qa_ai_summary
        ai_summary = qa_ai_summary(ai_summary, prices)
        if ai_summary.get("qa_applied"):
            logger.info(f"✅ 校閲完了: {ai_summary.get('qa_fixes',0)}件修正")
        else:
            logger.info("校閲: 修正なし")
    except Exception:
        logger.error("校閲エラー（スキップ）"); logger.debug(traceback.format_exc())

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

    # Step L3b2: 手法シグナル・スキャナー（押し目買い/ブレイク/売られすぎ等）
    setups = {"available": False}
    try:
        logger.info("--- Step L3b2: 手法シグナル・スキャナー ---")
        from src.setup_scanner import run as run_setups
        setups = run_setups(prices=prices, technical=technical)
        if setups.get("available"):
            logger.info(f"✅ 手法スキャナー完了（{len(setups.get('setups',[]))}銘柄）")
    except Exception:
        logger.error("手法スキャナーエラー"); logger.debug(traceback.format_exc())

    # Step L3b3: 銘柄カルテ（合わせ技スコア × TradingViewリンク × リスクファースト）
    stock_dossier = {"available": False, "dossiers": []}
    try:
        logger.info("--- Step L3b3: 銘柄カルテ ---")
        from src.stock_dossier import run as run_dossier
        stock_dossier = run_dossier(prices=prices, risk=risk, fear_greed=fear_greed)
        if stock_dossier.get("available"):
            cnt = len(stock_dossier.get("dossiers", []))
            top = stock_dossier["dossiers"][0] if cnt else {}
            logger.info(f"✅ 銘柄カルテ完了 {cnt}銘柄 最高スコア={top.get('confluence',0)}")
    except Exception:
        logger.error("銘柄カルテエラー"); logger.debug(traceback.format_exc())

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

    # Step L4a2: 日本 業種別ランキング（TOPIX-17 ETF・自動更新JSON）
    sector_ranking = {"available": False}
    try:
        logger.info("--- Step L4a2: 日本業種別ランキング ---")
        from src.sector_ranking_jp import run as run_srk
        sector_ranking = run_srk()
    except Exception:
        logger.error("業種別ランキングエラー"); logger.debug(traceback.format_exc())

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
            logger.info(f"✅ 合議: {v.get('direction','---')} {v.get('consensus_level','')} 確信度{v.get('consensus_confidence','?')}")
    except Exception:
        logger.error("マルチエージェント合議エラー"); logger.debug(traceback.format_exc())

    # Step L5a.5: 合議の確信度を予測レコードへ書き戻す（Brierスコア計算のため）
    try:
        conf = multi_consensus.get("verdict", {}).get("consensus_confidence")
        if conf is not None and prediction_tracker.get("available"):
            from src.prediction_tracker import update_confidence
            update_confidence(get_today_str(), conf)
            logger.info(f"確信度記録: {conf:.3f}")
    except Exception:
        logger.debug(traceback.format_exc())

    # Step L5a.6: 情報源クロスチェック（複数手法の方向一致度＝信頼度）
    cross_check = {"available": False}
    try:
        logger.info("--- Step L5a.6: 情報源クロスチェック ---")
        from src.cross_check import run as run_cross
        cross_check = run_cross(risk, multi_consensus=multi_consensus,
                                scenario=scenario, technical=technical)
        if cross_check.get("available"):
            logger.info(f"✅ {cross_check.get('summary')}")
    except Exception:
        logger.error("クロスチェックエラー"); logger.debug(traceback.format_exc())

    # Step L5a.7: 較正アンサンブル（複数手法の重み付き多数決予測）
    ensemble = {"available": False}
    try:
        logger.info("--- Step L5a.7: 較正アンサンブル ---")
        from src.ensemble import run as run_ensemble
        ensemble = run_ensemble(
            risk=risk, ai_summary=ai_summary, scenario=scenario,
            technical=technical, multi_consensus=multi_consensus,
        )
        if ensemble.get("available"):
            logger.info(
                f"✅ アンサンブル: {ensemble['direction']} "
                f"一致率={ensemble['agreement_pct']:.0f}% "
                f"信頼度={ensemble['confidence']}"
            )
    except Exception:
        logger.error("アンサンブルエラー（スキップ）"); logger.debug(traceback.format_exc())

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

    # Step 6: チャート生成（matplotlibが使える場合）
    try:
        logger.info("--- Step 6: チャート生成 ---")
        from src.visualize import run as vis
        chart_paths = vis(prices, news, risk, fear_greed)
        logger.info(f"チャート生成: {len(chart_paths)}件")
    except Exception:
        logger.error("チャート生成エラー（続行）"); logger.debug(traceback.format_exc())

    # Step CHR は後方（決算・材料・動いた銘柄など全素材が揃った後）へ移動。
    # ここでは器だけ用意しておく（以降の各ステップは character_comments を参照しない）。
    character_comments = {"available": False, "ganesha": "", "otter": ""}

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

    # ══════════ 追加分析モジュール群（再統合） ══════════
    _wd = get_jst_now().weekday()          # 0=月曜
    _is_monday = (_wd == 0 or mode == "test")

    # Step MA: マクロ要約（ファンダ＋金融政策・毎日）
    macro = {"available": False}
    try:
        logger.info("--- Step MA: マクロ要約（ファンダ＋金融政策） ---")
        from src.macro_summary import run as run_ma
        macro = run_ma(prices=prices, news=news, fear_greed=fear_greed, risk=risk,
                       fred_data=fred_data, fomc_sentiment=fomc_sentiment,
                       econ_analysis=econ_analysis, sector_analysis=sector_analysis,
                       congress_trades=congress_trades)
        if macro.get("available"):
            logger.info(f"✅ マクロ要約: {'AI生成' if macro.get('ai_generated') else '簡易'}")
    except Exception:
        logger.error("マクロ要約エラー"); logger.debug(traceback.format_exc())

    # Step TD: TDnet適時開示ウォッチャー（毎日・ウォッチリスト銘柄のみ）
    tdnet = {"available": False}
    try:
        logger.info("--- Step TD: TDnet適時開示ウォッチャー ---")
        from src.tdnet_watcher import run as run_td
        tdnet = run_td(prices, risk, fear_greed)
        if tdnet.get("available"):
            logger.info(f"✅ 適時開示: {tdnet.get('count',0)}件")
    except Exception:
        logger.error("TDnetウォッチャーエラー"); logger.debug(traceback.format_exc())

    # Step EB: 決算ブリーフ（決算PDFのAI要約・毎日・tdnet依存）
    earnings_brief = {"available": False}
    try:
        if tdnet.get("available"):
            logger.info("--- Step EB: 決算ブリーフ ---")
            from src.earnings_brief import run as run_eb
            earnings_brief = run_eb(tdnet)
            if earnings_brief.get("available"):
                logger.info(f"✅ 決算ブリーフ: {earnings_brief.get('count',0)}件")
    except Exception:
        logger.error("決算ブリーフエラー"); logger.debug(traceback.format_exc())

    # Step CA: 材料分析AI（5軸評価＋デイトレ仮説・毎日・tdnet/earnings_brief依存）
    catalyst = {"available": False}
    try:
        logger.info("--- Step CA: 材料分析AI ---")
        from src.catalyst_analyzer import run as run_ca
        catalyst = run_ca(prices, risk, fear_greed, tdnet=tdnet, earnings_brief=earnings_brief)
        if catalyst.get("available"):
            logger.info(f"✅ 材料分析: {catalyst.get('count',0)}件（妙味高 {catalyst.get('high_count',0)}件）")
    except Exception:
        logger.error("材料分析エラー"); logger.debug(traceback.format_exc())

    # Step AN: アノマリーカレンダー（毎日・該当する経験則）
    anomaly = {"available": False}
    try:
        logger.info("--- Step AN: アノマリーカレンダー ---")
        from src.anomaly_calendar import run as run_an
        anomaly = run_an(prices, risk, fear_greed)
        if anomaly.get("available"):
            logger.info(f"✅ アノマリー: {anomaly.get('count',0)}件")
    except Exception:
        logger.error("アノマリーカレンダーエラー"); logger.debug(traceback.format_exc())

    # Step TR: テーマ株人気ランキング（毎日）
    theme_ranking = {"available": False}
    try:
        logger.info("--- Step TR: テーマ株人気ランキング ---")
        from src.theme_ranker import run as run_tr
        theme_ranking = run_tr(prices=prices, risk=risk, fear_greed=fear_greed, news=news)
        if theme_ranking.get("available"):
            logger.info("✅ テーマランキング完了")
    except Exception:
        logger.error("テーマランキングエラー"); logger.debug(traceback.format_exc())

    # Step FA: 財務・決算書分析（月曜のみ）
    financial_analysis = {"available": False}
    try:
        if _is_monday:
            logger.info("--- Step FA: 財務・決算書分析 ---")
            from src.financial_analyzer import run as run_fa
            financial_analysis = run_fa(prices, risk, fear_greed)
            if financial_analysis.get("available"):
                logger.info(f"✅ 財務分析: {financial_analysis.get('count',0)}社")
    except Exception:
        logger.error("財務分析エラー"); logger.debug(traceback.format_exc())

    # Step SD: 需給分析ランキング（月曜のみ・出来高/資金フロー/空売り残高）
    supply_demand = {"available": False}
    try:
        if _is_monday:
            logger.info("--- Step SD: 需給分析ランキング ---")
            from src.supply_demand import run as run_sd
            supply_demand = run_sd(prices, risk, fear_greed)
            if supply_demand.get("available"):
                logger.info(f"✅ 需給分析: {supply_demand.get('count',0)}銘柄")
    except Exception:
        logger.error("需給分析エラー"); logger.debug(traceback.format_exc())

    # Step KY: 株予報（アナリスト目標株価・月曜のみ）
    kabuyoho = {"available": False}
    try:
        if _is_monday:
            logger.info("--- Step KY: 株予報（アナリスト目標株価） ---")
            from src.kabuyoho import run as run_ky
            kabuyoho = run_ky(prices, risk, fear_greed)
            if kabuyoho.get("available"):
                logger.info(f"✅ 株予報: {kabuyoho.get('count',0)}銘柄")
    except Exception:
        logger.error("株予報エラー"); logger.debug(traceback.format_exc())

    # Step SH: 業種ヒートマップ（毎日）
    sector_heatmap = {"available": False}
    try:
        logger.info("--- Step SH: 業種ヒートマップ ---")
        from src.sector_heatmap import run as run_sh
        sector_heatmap = run_sh(prices, risk, fear_greed)
        if sector_heatmap.get("available"):
            logger.info(f"✅ 業種ヒートマップ: {sector_heatmap.get('count',0)}業種")
    except Exception:
        logger.error("業種ヒートマップエラー"); logger.debug(traceback.format_exc())

    # Step ND: 日経225 内部データ（騰落レシオ・空売り比率・新高安・PER/PBR・毎日）
    nikkei_internals = {"available": False}
    try:
        logger.info("--- Step ND: 日経225 内部データ ---")
        from src.nikkei_market_data import run as run_nd
        nikkei_internals = run_nd(prices, risk, fear_greed)
        if nikkei_internals.get("available"):
            logger.info(f"✅ 日経内部データ: 騰落レシオ25日={nikkei_internals.get('trk25')} 空売り{nikkei_internals.get('short_ratio')}%")
    except Exception:
        logger.error("日経内部データエラー"); logger.debug(traceback.format_exc())

    # Step VW: バリュエーション節目ウォッチ（PER/PBR/配当利回り/イールドスプレッド）
    valuation = {"available": False}
    try:
        logger.info("--- Step VW: バリュエーション節目 ---")
        from src.valuation_watch import run as run_vw
        valuation = run_vw(nikkei_internals)
        if valuation.get("available"):
            logger.info(f"✅ バリュエーション節目通過: {len(valuation.get('events', []))}件")
    except Exception:
        logger.error("バリュエーション監視エラー"); logger.debug(traceback.format_exc())

    # Step MW: 景気・信用の先行シグナル（HYスプレッド/逆イールド/サーム/実質金利/バフェット指数）
    macro_watch = {"available": False}
    try:
        logger.info("--- Step MW: 景気・信用シグナル ---")
        from src.macro_watch import run as run_mw
        macro_watch = run_mw(nikkei_internals)
        if macro_watch.get("available"):
            logger.info(f"✅ マクロ節目通過: {len(macro_watch.get('events', []))}件")
    except Exception:
        logger.error("マクロ監視エラー"); logger.debug(traceback.format_exc())

    # 通知台帳: 同じ話題を1日に二度送らないための記録。セッション(JST6時始まり)が
    # 変われば自動で空になるため、ここでは読み込むだけで初期化は不要。
    # Step RS: リスクオン/オフの複合判定（株・為替・金・債券・VIXの一致度）
    risk_sentiment = {"available": False}
    try:
        logger.info("--- Step RS: リスクオン/オフ判定 ---")
        from src.risk_sentiment import run as run_rs
        risk_sentiment = run_rs(prices)
        if risk_sentiment.get("available"):
            logger.info(f"🚨 極端な{risk_sentiment['direction']}: スコア{risk_sentiment['score']}")
    except Exception:
        logger.error("リスク選好判定エラー"); logger.debug(traceback.format_exc())

    # Step SE: 市場心理の極値と反転（恐怖・強欲の底/天井で市場が反応した瞬間）
    sentiment = {"available": False}
    try:
        logger.info("--- Step SE: 市場心理の極値・反転 ---")
        from src.sentiment_extreme import run as run_se
        sentiment = run_se(prices, fear_greed)
        if sentiment.get("available"):
            logger.info(f"🎭 市場心理シグナル: {len(sentiment.get('events', []))}件")
    except Exception:
        logger.error("市場心理シグナルエラー"); logger.debug(traceback.format_exc())

    # Step PW: 中央銀行の政策金利（前回の利上げ/利下げからの動き）
    policy = {"available": False}
    try:
        logger.info("--- Step PW: 政策金利ウォッチ ---")
        from src.policy_watch import run as run_pw
        policy = run_pw()
        if policy.get("available") and policy.get("events"):
            logger.info(f"🚨 政策金利に変更: {len(policy['events'])}件")
    except Exception:
        logger.error("政策金利ウォッチエラー"); logger.debug(traceback.format_exc())

    # Step MD: 相場を動かした要因分析（大きく動いた日のみAIが要約）
    market_driver = {"available": False}
    try:
        logger.info("--- Step MD: 相場変動の要因分析 ---")
        from src.market_driver import run as run_md
        market_driver = run_md(prices, news, econ_analysis, macro_watch, policy)
        if market_driver.get("available"):
            logger.info(f"✅ 要因分析: {len(market_driver.get('movers', []))}指標が大きく変動")
    except Exception:
        logger.error("要因分析エラー"); logger.debug(traceback.format_exc())

    # Step MS: 市場内部シグナル（SOX/SKEW/VVIX/ドル指数/NT倍率・取得済み価格から判定）
    market_signals = {"available": False}
    try:
        logger.info("--- Step MS: 市場内部シグナル ---")
        from src.market_signals import run as run_ms
        market_signals = run_ms(prices)
        if market_signals.get("available"):
            logger.info(f"✅ 市場内部シグナル: {len(market_signals.get('events', []))}件")
    except Exception:
        logger.error("市場内部シグナルエラー"); logger.debug(traceback.format_exc())

    # Step ADR: 日本株ADR（夜間NYの値動き・寄り付き先行ヒント・毎日）
    adr = {"available": False}
    try:
        logger.info("--- Step ADR: 日本株ADR（夜間NY） ---")
        from src.adr_data import run as run_adr
        adr = run_adr(prices, risk, fear_greed)
        if adr.get("available"):
            logger.info(f"✅ ADR: {adr.get('count',0)}銘柄 主要平均乖離={adr.get('major_avg_divergence')}%")
    except Exception:
        logger.error("ADRエラー"); logger.debug(traceback.format_exc())

    # Step KD: 株ドラゴン デイトレランキング（値上がり/S高/出来高急増/値下がり・毎日）
    kabudragon = {"available": False}
    try:
        logger.info("--- Step KD: 株ドラゴン ランキング ---")
        from src.kabudragon import run as run_kd
        kabudragon = run_kd()
        if kabudragon.get("available"):
            _n_kd = sum(1 for v in kabudragon.get("rankings", {}).values() if v.get("items"))
            logger.info(f"✅ 株ドラゴン: {_n_kd}ランキング取得")
    except Exception:
        logger.error("株ドラゴンエラー"); logger.debug(traceback.format_exc())

    # Step PTS: PTS夜間取引の急騰・急落銘柄（株探・寄り付き先行ヒント・毎日）
    pts = {"available": False}
    try:
        logger.info("--- Step PTS: PTS夜間 急騰急落 ---")
        from src.pts_data import run as run_pts
        pts = run_pts()
        if pts.get("available"):
            logger.info(f"✅ PTS: 急騰{len(pts.get('up',[]))}件 急落{len(pts.get('down',[]))}件")
    except Exception:
        logger.error("PTSエラー"); logger.debug(traceback.format_exc())

    # Step US: 米国主要株の時間外ムーバー（アフターアワーズ・ザラ場先行シグナル・毎日）
    us_ah = {"available": False}
    try:
        logger.info("--- Step US: 米国時間外ムーバー ---")
        from src.us_afterhours import run as run_us_ah
        us_ah = run_us_ah()
        if us_ah.get("available"):
            logger.info(f"✅ 米国時間外: {len(us_ah.get('movers',[]))}銘柄が大きく変動")
    except Exception:
        logger.error("米国時間外エラー"); logger.debug(traceback.format_exc())

    # Step MACRO: マクロ（ファンダメンタル）レジーム判定
    #   逆イールド・サームルール・信用スプレッド・実質金利（歴史的に実績のある指標）
    macro_regime = {"available": False}
    try:
        logger.info("--- Step MACRO: マクロレジーム判定 ---")
        from src.fundamental_signals import run as run_macro_regime
        macro_regime = run_macro_regime()
        if macro_regime.get("available"):
            logger.info(f"✅ マクロレジーム: {len(macro_regime.get('signals', []))}件")
    except Exception:
        logger.error("マクロレジームエラー"); logger.debug(traceback.format_exc())

    # Step CFD: CFD/24時間先物＋SQ情報（CME日経ギャップ・SQ日程・毎日）
    cfd_sq = {"available": False}
    try:
        logger.info("--- Step CFD: CFD/24時間先物・SQ ---")
        from src.cfd_sq import run as run_cfd
        cfd_sq = run_cfd(prices)
        if cfd_sq.get("available"):
            logger.info(f"✅ CFD/SQ: CMEギャップ={cfd_sq.get('cme_gap_pct')}% SQ={cfd_sq.get('sq',{}).get('date')}")
    except Exception:
        logger.error("CFD/SQエラー"); logger.debug(traceback.format_exc())

    # Step EV: 今後のイベント予定（SQ/雇用統計/FOMC確定計算＋週次カレンダー永続分・毎日）
    upcoming = {"available": False}
    try:
        logger.info("--- Step EV: 今後のイベント予定 ---")
        from src.upcoming_events import run as run_ev
        upcoming = run_ev()
        if upcoming.get("available"):
            logger.info(f"✅ 今後のイベント: {len(upcoming.get('events', []))}件")
    except Exception:
        logger.error("イベント予定エラー"); logger.debug(traceback.format_exc())

    # Step CHR: AIキャラクターコメント生成（全素材が揃ったこの位置で実行）
    try:
        logger.info("--- Step CHR: AIキャラクターコメント生成（詳細材料つき） ---")
        from src.character_commentary import generate_comments
        _extras = {
            "経済指標":            econ_analysis,
            "マクロ要約":          macro,
            "決算プレビュー":       earnings_preview,
            "決算ブリーフ":         earnings_brief,
            "財務・決算分析":       financial_analysis,
            "材料分析":            catalyst,
            "TDnet適時開示":       tdnet,
            "手法シグナル(押し目/ブレイク)": setups,
            "注目銘柄ドシエ":       stock_dossier,
            "日本株スクリーナー":    jquants,
            "テーマ株ランキング":    theme_ranking,
            "需給ランキング":       supply_demand,
            "日経内部指標":         nikkei_internals,
            "日本株ADR(夜間)":     adr,
            "株ドラゴン":          kabudragon,
            "PTS夜間":            pts,
            "米国時間外ムーバー":    us_ah,
            "CFD/SQ":            cfd_sq,
            "今後のイベント":       upcoming,
        }
        character_comments = generate_comments(prices, risk, fear_greed,
                                               ai_summary=ai_summary, news=news,
                                               sector=sector_analysis,
                                               sector_ranking=sector_ranking,
                                               extras=_extras)
        if character_comments.get("available"):
            logger.info("✅ ガネーシャ＆カワウソ コメント生成完了（詳細材料反映）")
    except Exception:
        logger.error("キャラクターコメントエラー"); logger.debug(traceback.format_exc())

    # Step 7: HTMLレポート生成
    report_paths = {}
    try:
        logger.info("--- Step 7: HTMLレポート生成 ---")
        _save_html_report(mode, prices, news, risk, analysis, fear_greed, chart_paths,
                          ai_summary, econ_analysis, youtube_summary, memory_analysis,
                          agent_report, technical, portfolio, scenario, prediction_tracker,
                          character_comments=character_comments,
                          macro=macro, tdnet=tdnet, earnings_brief=earnings_brief,
                          catalyst=catalyst,
                          anomaly=anomaly, theme_ranking=theme_ranking,
                          financial_analysis=financial_analysis,
                          supply_demand=supply_demand, kabuyoho=kabuyoho,
                          sector_heatmap=sector_heatmap,
                          nikkei_internals=nikkei_internals, adr=adr,
                          weekly_calendar=weekly_calendar)
        today = get_today_str()
        report_paths = {
            "html": str(get_dirs()["reports"] / f"{today}_{mode}.html"),
            "md":   str(get_dirs()["reports"] / f"{today}_{mode}.md"),
            # GitHub Pages は main/docs を公開する。日付つきHTMLは reports/ にしか
            # 無く Pages では 404 になるため、必ず公開済みの daily_report.html を案内する
            "url":  f"{PAGES_URL}/daily_report.html",
        }
    except Exception:
        logger.error("レポート生成エラー"); logger.debug(traceback.format_exc())

    # Step 7a2: デザインAIレポート（docs/daily_report.html・公開メインのリッチ版）
    try:
        logger.info("--- Step 7a2: デザインAIレポート（リッチ公開版） ---")
        from src.design_ai import run as run_design
        _design_res = run_design(
            prices=prices, news=news, risk=risk, fear_greed=fear_greed,
            ai_summary=ai_summary, scenario=scenario, technical=technical,
            sector_analysis=sector_analysis, prediction_tracker=prediction_tracker,
            weekly_calendar=weekly_calendar,
            youtube_summary=youtube_summary,
            data_integrity=data_integrity,
            character_comments=character_comments,
            cross_check=cross_check,
            sector_ranking=sector_ranking,
            setups=setups,
            ensemble=ensemble,
            stock_dossier=stock_dossier,
            kabudragon=kabudragon,
            pts=pts,
            us_afterhours=us_ah,
            adr=adr,
            macro_regime=macro_regime,
            cfd_sq=cfd_sq,
            upcoming=upcoming,
            valuation=valuation,
            macro_watch=macro_watch,
            market_signals=market_signals,
            policy=policy,
            market_driver=market_driver,
            sentiment=sentiment,
            risk_sentiment=risk_sentiment,
            mode=mode,
        )
        # 公開ページが更新されたことを必ず確認する。
        # ここを検証していなかったため、生成失敗に長期間気づけず
        # 公開レポートが古いまま固定される事故が起きた。
        _p = Path(__file__).parent / "docs" / "daily_report.html"
        if not (_design_res or {}).get("available"):
            logger.error(f"❌ 公開レポートを更新できませんでした: "
                         f"{(_design_res or {}).get('error', '原因不明')}")
        elif not _p.exists():
            logger.error(f"❌ 公開レポートのファイルが見つかりません: {_p}")
        else:
            _txt = _p.read_text(encoding="utf-8", errors="ignore")[:4000]
            if get_today_str() in _txt:
                logger.info(f"✅ 公開レポート更新済み（{_p.stat().st_size:,}バイト・本日の日付を確認）")
            else:
                logger.error("❌ 公開レポートに本日の日付がありません（古い内容のままの可能性）")
    except Exception:
        logger.error("デザインAIレポートエラー"); logger.error(traceback.format_exc())

    # Step 7b: note記事生成
    note_article = {"available": False}
    try:
        logger.info("--- Step 7b: note記事生成 ---")
        from src.note_article import run as run_note
        note_article = run_note(
            prices=prices, news=news, risk=risk, fear_greed=fear_greed,
            ai_summary=ai_summary, scenario=scenario, technical=technical,
            prediction_tracker=prediction_tracker, report_paths=report_paths,
        )
        if note_article.get("available"):
            logger.info(f"✅ note記事生成完了: {note_article.get('path','')}")
    except Exception:
        logger.error("note記事生成エラー"); logger.debug(traceback.format_exc())

    # Step 7c: note カバー画像生成
    note_cover = {"available": False}
    try:
        logger.info("--- Step 7c: note カバー画像生成 ---")
        from src.note_cover import run as run_cover
        note_cover = run_cover(prices=prices, risk=risk, fear_greed=fear_greed)
        if note_cover.get("available"):
            logger.info(f"✅ note カバー画像: {note_cover.get('path','')}")
    except Exception:
        logger.error("note カバー画像エラー"); logger.debug(traceback.format_exc())

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

        # Step VID: 要約ナレーション動画（通知③・失敗しても通知①②は継続）
        video_path = None
        try:
            logger.info("--- Step VID: 要約ナレーション動画 ---")
            from src.video_summary import run as run_video
            _vid = run_video(prices=prices, fear_greed=fear_greed, risk=risk,
                             ai_summary=ai_summary, news=news,
                             character_comments=character_comments,
                             chart_paths=chart_paths, mode=mode)
            if _vid.get("available"):
                video_path = _vid.get("path")
                logger.info("✅ 要約動画 準備完了")
        except Exception:
            logger.debug(traceback.format_exc())

        notify_tg(risk, analysis, report_paths, mode,
                  video_path=video_path,
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
                  character_comments=character_comments,
                  macro=macro, tdnet=tdnet, earnings_brief=earnings_brief,
                  catalyst=catalyst,
                  anomaly=anomaly, theme_ranking=theme_ranking,
                  financial_analysis=financial_analysis,
                  supply_demand=supply_demand, kabuyoho=kabuyoho,
                  sector_heatmap=sector_heatmap,
                  nikkei_internals=nikkei_internals, adr=adr,
                  setups=setups,
                  stock_dossier=stock_dossier,
                  ensemble=ensemble,
                  kabudragon=kabudragon,
                  pts=pts,
                  us_afterhours=us_ah,
                  macro_regime=macro_regime,
                  cfd_sq=cfd_sq,
                  upcoming=upcoming,
                  valuation=valuation,
                  macro_watch=macro_watch,
                  market_signals=market_signals,
                  policy=policy,
                  market_driver=market_driver,
                  sentiment=sentiment,
                  risk_sentiment=risk_sentiment)
    except Exception:
        logger.error("Telegram通知エラー"); logger.debug(traceback.format_exc())

    # Step 8b: note記事テキスト自動生成
    note_article = {"available": False}
    try:
        logger.info("--- Step 8b: note記事生成 ---")
        from src.note_article_generator import run as gen_note
        note_article = gen_note(prices, risk, fear_greed,
                                ai_summary=ai_summary,
                                scenario=scenario,
                                news=news,
                                note_magazine_url=os.getenv("NOTE_MAGAZINE_URL", ""))
        if note_article.get("available"):
            logger.info(f"✅ note記事生成完了: {note_article.get('path')}")
    except Exception:
        logger.error("note記事生成エラー"); logger.debug(traceback.format_exc())

    # Step 8d: X（Twitter）自動投稿
    try:
        logger.info("--- Step 8d: X自動投稿 ---")
        from src.notify_x import run as notify_x
        x_result = notify_x(risk, prices, fear_greed,
                            ai_summary=ai_summary,
                            news=news,
                            report_paths=report_paths,
                            note_magazine_url=os.getenv("NOTE_MAGAZINE_URL", ""))
        if x_result.get("posted"):
            logger.info("✅ X投稿完了")
        elif x_result.get("available"):
            logger.warning("X投稿失敗（API設定確認）")
        else:
            logger.info("X API未設定のためスキップ")
    except Exception:
        logger.error("X投稿エラー"); logger.debug(traceback.format_exc())

    # ── 稼働状況の一覧（どの機能が動き、どれが取得できなかったかを毎回残す）──
    # 個々のStepは try/except で継続するため、失敗しても実行は最後まで進む。
    # そのぶん「静かに動かなくなった機能」を見逃しやすいので、ここで棚卸しする。
    try:
        _modules = [
            ("価格取得", bool(prices)), ("ニュース", bool(news)),
            ("AI3視点", (ai_summary or {}).get("available")),
            ("3シナリオ", (scenario or {}).get("available")),
            ("テクニカル", (technical or {}).get("available")),
            ("日経内部データ", (nikkei_internals or {}).get("available")),
            ("ADR", (adr or {}).get("available")),
            ("PTS夜間", (pts or {}).get("available")),
            ("米時間外", (us_ah or {}).get("available")),
            ("株ドラゴン", (kabudragon or {}).get("available")),
            ("CFD/SQ", (cfd_sq or {}).get("available")),
            ("今後のイベント", (upcoming or {}).get("available")),
            ("バリュエーション", bool((valuation or {}).get("current"))),
            ("マクロ・信用", bool((macro_watch or {}).get("current"))),
            ("市場内部シグナル", bool((market_signals or {}).get("current"))),
            ("政策金利", (policy or {}).get("available")),
            ("要因分析", (market_driver or {}).get("available")),
            ("市場心理", bool((sentiment or {}).get("current"))),
            ("リスク選好", (risk_sentiment or {}).get("direction") is not None),
        ]
        ok = [n for n, v in _modules if v]
        ng = [n for n, v in _modules if not v]
        logger.info(f"📊 稼働: {len(ok)}/{len(_modules)} 機能")
        if ng:
            logger.warning(f"⚠️ データ取得できず: {', '.join(ng)}")
    except Exception:
        logger.debug(traceback.format_exc())

    logger.info(f"====== クラウド実行完了 ======")
    print(f"\n✅ 完了 | 地合い: {risk.get('sentiment')} | "
          f"F&G: {fear_greed.get('score')} ({fear_greed.get('rating_ja')}) | "
          f"ニュース: {len(news)}件 | チャート: {len(chart_paths)}件")


def _make_gauge_svg(value, lo, hi, gid, grad):
    """半円SVGニードルゲージを返す。grad は [("0%","#color"), ...] のリスト。"""
    import math
    v     = max(lo, min(hi, float(value if value is not None else lo)))
    ratio = (v - lo) / (hi - lo) if hi != lo else 0
    angle = math.radians(-180 + ratio * 180)
    nx    = 70 + 50 * math.cos(angle)
    ny    = 68 + 50 * math.sin(angle)
    stops = "".join(f'<stop offset="{p}" stop-color="{c}"/>' for p, c in grad)
    return (
        f'<svg viewBox="0 0 140 78" xmlns="http://www.w3.org/2000/svg"'
        f' width="130" height="72" style="display:block;margin:0 auto;">'
        f'<defs><linearGradient id="gg{gid}" x1="0%" y1="0%" x2="100%" y2="0%">'
        f'{stops}</linearGradient></defs>'
        f'<path d="M12,68 A58,58 0 0,1 128,68" fill="none" stroke="#1e2d42"'
        f' stroke-width="14" stroke-linecap="round"/>'
        f'<path d="M12,68 A58,58 0 0,1 128,68" fill="none" stroke="url(#gg{gid})"'
        f' stroke-width="14" stroke-linecap="round" opacity="0.88"/>'
        f'<line x1="70" y1="68" x2="{nx:.1f}" y2="{ny:.1f}"'
        f' stroke="#ffffff" stroke-width="3.5" stroke-linecap="round"/>'
        f'<circle cx="70" cy="68" r="5.5" fill="#ffffff"/>'
        f'<text x="70" y="54" text-anchor="middle" font-size="17" font-weight="900"'
        f' fill="#ffffff" font-family="sans-serif">{v:.0f}</text>'
        f'</svg>'
    )


def _save_html_report(mode, prices, news, risk, analysis, fear_greed, chart_paths,
                      ai_summary=None, econ_analysis=None, youtube_summary=None,
                      memory_analysis="", agent_report=None, technical=None,
                      portfolio=None, scenario=None, prediction_tracker=None,
                      character_comments=None,
                      macro=None, tdnet=None, earnings_brief=None, anomaly=None,
                      catalyst=None,
                      theme_ranking=None, financial_analysis=None,
                      supply_demand=None, kabuyoho=None, sector_heatmap=None,
                      nikkei_internals=None, adr=None, weekly_calendar=None):
    """初心者でもわかる見やすいダッシュボードHTMLを保存"""
    import base64
    today  = get_today_str()
    dirs   = get_dirs()
    _now_dt = get_jst_now()
    now    = _now_dt.strftime("%Y-%m-%d %H:%M JST")
    wd_jp  = ["月", "火", "水", "木", "金", "土", "日"][_now_dt.weekday()]
    wd_en  = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"][_now_dt.weekday()]
    date_dot = _now_dt.strftime("%Y.%m.%d")

    # ── 追加モジュールのHTML生成（再統合） ──
    macro = macro or {};              macro_html = macro.get("html", "") if macro.get("available") else ""
    tdnet = tdnet or {};              tdnet_html = tdnet.get("html", "") if tdnet.get("available") else ""
    earnings_brief = earnings_brief or {}; eb_html = earnings_brief.get("html", "") if earnings_brief.get("available") else ""
    catalyst = catalyst or {};        catalyst_html = catalyst.get("html", "") if catalyst.get("available") else ""
    anomaly = anomaly or {};          anomaly_html = anomaly.get("html", "") if anomaly.get("available") else ""
    theme_ranking = theme_ranking or {}; theme_html = theme_ranking.get("html", "") if theme_ranking.get("available") else ""
    supply_demand = supply_demand or {}; sd_html = supply_demand.get("html", "") if supply_demand.get("available") else ""
    kabuyoho = kabuyoho or {};        ky_html = kabuyoho.get("html", "") if kabuyoho.get("available") else ""
    sector_heatmap = sector_heatmap or {}; sh_html = sector_heatmap.get("html", "") if sector_heatmap.get("available") else ""
    nikkei_internals = nikkei_internals or {}; nd_html = nikkei_internals.get("html", "") if nikkei_internals.get("available") else ""
    adr = adr or {}; adr_html = adr.get("html", "") if adr.get("available") else ""
    financial_analysis = financial_analysis or {}
    fa_html = ""
    if financial_analysis.get("available"):
        try:
            from src.financial_analyzer import get_html as _fa_html
            fa_html = _fa_html(financial_analysis)
        except Exception:
            fa_html = ""

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

    # SVG ニードルゲージ（Fear&Greed と VIX）
    _vix_now   = prices.get("^VIX", {}).get("latest") or 15
    _fg_svg    = _make_gauge_svg(fg_int, 0, 100, "FG",
                   [("0%","#7c3aed"),("25%","#ef4444"),("50%","#f59e0b"),("100%","#22c55e")])
    _vix_svg   = _make_gauge_svg(_vix_now, 0, 50, "VX",
                   [("0%","#22c55e"),("50%","#f59e0b"),("80%","#ef4444"),("100%","#7c3aed")])
    _vix_lbl   = "⚠ 危険！" if _vix_now > 30 else "高め" if _vix_now > 20 else "普通" if _vix_now > 15 else "✓ 安定"
    _vix_color = "#ff4444" if _vix_now > 30 else "#ffd740" if _vix_now > 20 else "#69f0ae" if _vix_now > 15 else "#00e676"

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
  background:rgba(9,13,20,.82);
  border-bottom:1px solid var(--border);
  padding:13px 18px;
  display:flex;align-items:center;justify-content:space-between;
  position:sticky;top:0;z-index:100;backdrop-filter:blur(14px);
}}
.header::before{{
  content:'';position:absolute;top:0;left:0;right:0;height:3px;
  background:linear-gradient(90deg,var(--accent),var(--accent2) 70%,transparent);
}}
.header-brand{{display:flex;align-items:center;gap:9px;}}
.header-mark{{
  width:28px;height:28px;border-radius:8px;display:grid;place-items:center;
  font-size:15px;font-weight:900;color:#070a10;
  background:linear-gradient(135deg,var(--accent),var(--accent2));
}}
.header-logo{{font-size:1.05em;font-weight:800;color:var(--text);letter-spacing:.02em;}}
.header-tag{{
  font-size:0.62em;font-weight:700;color:var(--accent);letter-spacing:.2em;
  border-left:1px solid var(--border);padding-left:9px;margin-left:2px;
}}
.header-date{{color:var(--text2);font-size:0.78em;letter-spacing:.04em;font-weight:600;}}
.header-date b{{color:var(--text);font-weight:700;}}

/* ══════════════════════════════════════
   ヒーローカード（今日の相場）
══════════════════════════════════════ */
.hero{{
  {hero_bg};
  border:1px solid {hero_color}44;
  border-radius:var(--radius);
  padding:30px 26px;
  margin:18px 0;
  position:relative;overflow:hidden;
}}
.hero::before{{
  content:'';position:absolute;inset:0;opacity:.5;pointer-events:none;
  background-image:linear-gradient(rgba(255,255,255,.025) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.025) 1px,transparent 1px);
  background-size:38px 38px;
}}
.hero::after{{
  content:'';position:absolute;top:-60px;right:-50px;
  width:220px;height:220px;border-radius:50%;
  background:radial-gradient({hero_color}33,transparent 70%);
}}
.hero-eyebrow{{
  position:relative;font-size:0.72em;font-weight:700;color:{hero_color};
  letter-spacing:.22em;margin-bottom:12px;
}}
.hero-headline{{position:relative;display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;}}
.hero-emoji{{font-size:2.6em;line-height:1;}}
.hero-label{{font-size:2.5em;font-weight:900;color:{hero_color};letter-spacing:-.01em;line-height:1;}}
.hero-msg{{position:relative;color:var(--text);opacity:.82;font-size:1.05em;margin-top:16px;line-height:1.6;}}
.hero-score{{
  position:relative;display:inline-flex;align-items:center;gap:10px;margin-top:20px;
  background:{hero_color}1f;border:1px solid {hero_color}5e;border-radius:999px;
  padding:8px 20px;
}}
.hero-score .lbl{{color:var(--text2);font-size:0.78em;font-weight:600;letter-spacing:.04em;}}
.hero-score .num{{color:{hero_color};font-size:1.3em;font-weight:900;}}

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
  <div class="header-brand">
    <span class="header-mark">M</span>
    <span class="header-logo">市場AI秘書</span>
    <span class="header-tag">DAILY REPORT</span>
  </div>
  <div class="header-date">{date_dot} <b>{wd_en}</b> ・ {now}</div>
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
    <div class="hero-eyebrow">本日の判定 ／ {wd_jp}曜日</div>
    <div class="hero-headline">
      <span class="hero-label">{hero_label}</span>
      <span class="hero-emoji">{hero_emoji}</span>
    </div>
    <div class="hero-msg">{hero_msg}</div>
    <div class="hero-score"><span class="lbl">リスクスコア</span><span class="num">{score:+.1f}</span></div>
  </div>

  <!-- キャラクターコメント（ガネーシャ & カワウソ） -->
  {char_html_section}

  <!-- SVGゲージ: Fear&Greed / VIX / ドル円 -->
  <div class="quick-row">
    <div class="qcard" style="padding:12px 6px;text-align:center;">
      {_fg_svg}
      <div style="font-weight:700;color:{fg_color};font-size:0.82em;margin-top:3px;">{fg_emoji} {fg_desc}</div>
      <div style="color:var(--text2);font-size:0.68em;margin-top:1px;">Fear &amp; Greed Index（0〜100）</div>
    </div>
    <div class="qcard" style="padding:12px 6px;text-align:center;">
      {_vix_svg}
      <div style="font-weight:700;color:{_vix_color};font-size:0.82em;margin-top:3px;">{_vix_lbl}</div>
      <div style="color:var(--text2);font-size:0.68em;margin-top:1px;">VIX 恐怖指数（0〜50）</div>
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

  <!-- ══ 再統合モジュール群 ══ -->
  {f'<div class="sec-head">🌐 ファンダ＆金融政策の要約</div>{macro_html}' if macro_html else ""}
  {f'<div class="sec-head">📋 適時開示アラート（あなたの注目銘柄）</div>{tdnet_html}' if tdnet_html else ""}
  {f'<div class="sec-head">📑 決算ブリーフ（AIが中身を要約）</div>{eb_html}' if eb_html else ""}
  {f'<div class="sec-head">🎯 材料分析AI（プロ目線の5軸評価＋デイトレ仮説）</div>{catalyst_html}' if catalyst_html else ""}
  {f'<div class="sec-head">🎯 アナリスト目標株価（株予報）</div>{ky_html}' if ky_html else ""}
  {f'<div class="sec-head">📊 需給分析ランキング（買いの勢いが強い順）</div>{sd_html}' if sd_html else ""}
  {f'<div class="sec-head">🌡 東証プライムの中身（騰落レシオ・空売り比率・新高安）</div>{nd_html}' if nd_html else ""}
  {f'<div class="sec-head">🌃 ADR夜間（NYの値動き・今日の寄り付き先行ヒント）</div>{adr_html}' if adr_html else ""}
  {f'<div class="sec-head">🗺 業種ヒートマップ（東証17業種・どこに買いが集まるか）</div>{sh_html}' if sh_html else ""}
  {f'<div class="sec-head">📊 財務・決算書分析</div>{fa_html}' if fa_html else ""}
  {f'<div class="sec-head">🔥 テーマ株人気ランキング</div>{theme_html}' if theme_html else ""}
  {f'<div class="sec-head">📜 今日のアノマリー</div>{anomaly_html}' if anomaly_html else ""}

  <!-- AI記憶分析 -->
  {f'<div class="sec-head">🧠 AI記憶：過去との比較</div><div class="memory-box"><div class="memory-text">{memory_analysis}</div></div>' if memory_analysis else ""}

  <!-- 予測学習・精度トラッカー -->
  {f'<div class="sec-head">🧠 AI予測学習レポート（正解率・精度向上）</div><div class="econ-wrap">{pred_html}</div>' if pred_html else ""}

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
    mode = p.parse_args().mode
    try:
        run(mode)
    except Exception:
        # ステップ間のつなぎコードで想定外の例外が起きても、
        # ①最低限の失敗通知をTelegramへ送り、②非ゼロ終了でワークフローを赤くする。
        # （「成功表示なのに通知が来ない」事故を二度と起こさないための安全網）
        logger.error("致命的エラーでレポート生成が中断しました")
        logger.debug(traceback.format_exc())
        try:
            from src.notify_telegram import send_message
            last = (traceback.format_exc().strip().splitlines() or ["不明なエラー"])[-1][:200]
            send_message(
                "⚠️ *市場AI秘書*\n"
                "本日のレポート生成が途中で失敗しました。\n"
                f"エラー: `{last}`\n"
                "（GitHub Actions のログを確認してください）"
            )
        except Exception:
            logger.debug("失敗通知の送信にも失敗", exc_info=True)
        raise  # 終了コード非ゼロ → ワークフローを失敗（赤）にする


if __name__ == "__main__":
    main()
