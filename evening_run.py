"""
夜の相場振り返りスクリプト（GitHub Actions用）
毎晩23:00 JST に自動実行

送信内容:
  ① 今日の相場3行サマリー（Gemini生成）
  ② 明日への1行アドバイス
  ③ 感情売買ガード（VIX高騰時に自動発動）
"""
import sys
import traceback
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))
from src.utils import ensure_dirs, setup_logger, get_jst_now

logger = setup_logger("evening_run")


def run():
    ensure_dirs()
    logger.info(f"====== 夜の振り返り開始 [{get_jst_now().strftime('%Y-%m-%d %H:%M')}] ======")

    prices     = {}
    fear_greed = {"score": 50, "rating_ja": "中立"}
    risk       = {"score": 0, "sentiment": "中立"}

    # 価格取得
    try:
        logger.info("価格データ取得中...")
        from src.fetch_prices import run as fp
        prices, fear_greed = fp()
        logger.info(f"取得完了: {sum(1 for v in prices.values() if v.get('latest'))}銘柄")
    except Exception:
        logger.error("価格取得エラー"); logger.debug(traceback.format_exc())

    # リスクスコア計算
    try:
        from src.indicators import calc_risk_score
        risk = calc_risk_score(prices)
    except Exception:
        logger.debug(traceback.format_exc())

    # 夜の振り返り送信
    # ⚠️ 2026-09-11まで、ここは何が起きても正常終了していた。
    #    ・通知モジュールが壊れても → 詳細は debug（本番ログに出ない）
    #    ・送信に失敗しても → warning だけ
    #    どちらも GitHub Actions は緑のまま。夜の通知が止まっても
    #    誰も気づけない作りだった（点検中に構文エラーを入れたとき、
    #    実際に「✅ 完走・送信0件」で終わるのを見て発覚した）。
    #    「公開レポートが1.5ヶ月更新されなかった」事故と同じ形。
    #    届かなかったときは、Actionsを赤にしてメールで気づけるようにする。
    delivered = False
    try:
        logger.info("夜の振り返り生成 + 送信...")
        from src.evening_summary import run as run_evening
        result = run_evening(prices, fear_greed, risk)
        if result.get("available"):
            logger.info("✅ 夜の振り返り完了")
            delivered = True
        else:
            logger.error("❌ 夜の振り返りを送信できませんでした"
                         "（TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID を確認）")
    except Exception:
        logger.error("❌ 夜の振り返りでエラー", exc_info=True)

    logger.info("====== 夜の振り返り終了 ======")
    return delivered


if __name__ == "__main__":
    # 届かなかった日はActionsを赤にする（緑のまま黙って止まらないように）
    sys.exit(0 if run() else 1)
