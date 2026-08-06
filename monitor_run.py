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

    # ヒドゥンダイバージェンス（日足トレンド × 1時間足RSI）検出アラート
    # トレンド継続のサイン。検出時のみ・同一銘柄は1セッション1回だけ通知
    try:
        from src.divergence import run_divergence_alert
        if run_divergence_alert():
            logger.info("✅ ヒドゥンダイバージェンス通知送信完了")
    except Exception:
        logger.error("ダイバージェンス検出エラー"); logger.debug(traceback.format_exc())

    logger.info("====== 監視完了 ======")


if __name__ == "__main__":
    run()
