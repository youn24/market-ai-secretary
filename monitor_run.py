"""
15分ごと監視スクリプト（GitHub Actions用）
急変検知・AIアラート
"""
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from src.utils import ensure_dirs, setup_logger, get_jst_now

logger = setup_logger("monitor_run")


def run():
    ensure_dirs()
    now = get_jst_now()
    logger.info(f"====== 監視実行開始 {now.strftime('%H:%M JST')} ======")

    prices     = {}
    fear_greed = {"score": None, "rating_ja": "---"}
    risk       = {"score": 0, "sentiment": "不明", "signals": []}

    # 価格取得
    try:
        from src.fetch_prices import run as fp
        prices, fear_greed = fp()
        logger.info(f"価格取得: {sum(1 for v in prices.values() if v.get('latest'))}件")
    except Exception:
        logger.error("価格取得エラー"); logger.debug(traceback.format_exc())

    # リスク計算
    try:
        from src.indicators import calc_risk_score
        risk = calc_risk_score(prices)
    except Exception:
        logger.error("リスク計算エラー")

    # 暴落級アラートチェック（安全網）
    # ※通常の細かい急変通知は廃止。本当に大きな暴落のときだけ通知する。
    try:
        from src.alert_monitor import run_alert_check
        alerted = run_alert_check(prices, fear_greed, risk)
        if alerted:
            logger.info("✅ 暴落級アラート送信完了")
        else:
            logger.info("暴落級の急変なし")
    except Exception:
        logger.error("アラートエラー"); logger.debug(traceback.format_exc())

    # 米国時間外の個別株 大変動アラート（±5%級＝決算反応など）
    try:
        from src.alert_monitor import run_afterhours_alert
        if run_afterhours_alert():
            logger.info("✅ 時間外ムーバーアラート送信完了")
    except Exception:
        logger.error("時間外アラートエラー"); logger.debug(traceback.format_exc())

    # CFD/24時間マーケット（指数先物・欧州指数・コモディティ）の急変アラート
    try:
        from src.alert_monitor import run_cfd_alert
        if run_cfd_alert():
            logger.info("✅ CFD/24時間アラート送信完了")
    except Exception:
        logger.error("CFD/24時間アラートエラー"); logger.debug(traceback.format_exc())

    # テクニカルシグナル検出アラート（tech_signals.py に一本化）
    #   52週線(年線)・52週高値安値・GC/DC・200日線・一目の雲・出来高の裏付け・
    #   通常/ヒドゥンダイバージェンス・MACDクロス・ボリンジャー±2σ・RSI30/70反転
    #   週足＋日足の重なりを信頼度として評価し、複数出ても「1通にまとめて」送る。
    #   同一銘柄＋同一種別は1セッション（JST6時始まり）に1回だけ。
    # 日足・週足の確定が要るため、東京の引け後〜夜間のみ判定（未確定足での誤発火防止）
    if now.hour >= 15 or now.hour < 6:
        try:
            from src.tech_signals import run_tech_alert
            if run_tech_alert():
                logger.info("✅ テクニカルシグナル通知送信完了")
        except Exception:
            logger.error("テクニカルシグナル検出エラー"); logger.debug(traceback.format_exc())

    # マクロ（ファンダメンタル）レジーム変化アラート
    #   逆イールド・サームルール・信用スプレッド・実質金利。
    #   月次/週次データなので判定は1日1回だけ（内部でセッションガード）。
    #   重要な状態変化が起きたときのみ通知するので通常は無風。
    try:
        from src.fundamental_signals import run_macro_alert
        if run_macro_alert():
            logger.info("✅ マクロレジーム変化アラート送信完了")
    except Exception:
        logger.error("マクロシグナル検出エラー"); logger.debug(traceback.format_exc())

    logger.info("====== 監視完了 ======")


if __name__ == "__main__":
    run()
