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

    # 急変アラートチェック
    try:
        from src.alert_monitor import run_alert_check
        alerted = run_alert_check(prices, fear_greed, risk)
        if alerted:
            logger.info("✅ 急変アラート送信完了")
        else:
            logger.info("急変なし")
    except Exception:
        logger.error("アラートエラー"); logger.debug(traceback.format_exc())

    logger.info("====== 監視完了 ======")


if __name__ == "__main__":
    run()
