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

    # ── 緊急アラート ────────────────────────────────────────
    # 他の何より先に実行する。後ろに置くと、途中の処理が失敗したときに
    # 緊急の連絡だけ届かないという最悪の事態になりうる。
    #
    # 判定基準は過去2年の実測で年5〜15回に収まる水準に設定してある。
    # 「1銘柄が急落した」は緊急にしない。73銘柄も見ていればどれかは毎日動く。
    # 市場全体が壊れているかどうかだけを見る。
    try:
        from src.us_movers import run_emergency_alert as us_em
        if us_em():
            logger.warning("🚨 米国市場の緊急アラートを送信しました")
    except Exception:
        logger.error("米国緊急アラートエラー", exc_info=True)

    # 日経側は「偏った急変」を緊急とする。指数の値幅そのものは
    # 下の暴落級アラートが見ているので、ここでは中身の偏りだけを扱う。
    if 15 <= now.hour < 20:
        try:
            from src.nikkei_impact import run_emergency_alert as nk_em
            if nk_em():
                logger.warning("🚨 日経の偏った急変を通知しました")
        except Exception:
            logger.error("日経緊急アラートエラー", exc_info=True)

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

    # 米国ザラ場ムーバー（us_movers.py）
    #   これまで米国株は時間外しか見ていなかったが、2026-08-18の半導体安のように
    #   通常取引の最中に崩れる日がある。日本時間の深夜に進むため、
    #   朝には終わっていて備える時間が無かった。
    #   しきい値は銘柄ごとに過去1年から自動計算（テスラの4%と別銘柄の4%は別物）。
    #   セクター単位の動きも見る（同業が揃えば翌日の日本株にほぼ波及する）。
    #   通常取引の時間帯かどうかはモジュール側で判定するので時間指定は不要。
    try:
        from src.us_movers import run_movers_alert
        if run_movers_alert():
            logger.info("✅ 米国ザラ場ムーバー通知送信完了")
    except Exception:
        logger.error("米国ザラ場ムーバーエラー", exc_info=True)

    # 日経平均への寄与度（nikkei_impact.py）
    #   日経は株価の平均なので、値がさ株ほど指数を動かす力が強い。
    #   「日経が下げた」が1銘柄のせいか全体かで意味が変わるため、
    #   寄与度と偏りを数字で出す。東京の引け後に1日1回。
    if 15 <= now.hour < 20:
        try:
            from src.nikkei_impact import run_impact_alert
            if run_impact_alert():
                logger.info("✅ 日経寄与度の通知送信完了")
        except Exception:
            logger.error("日経寄与度エラー", exc_info=True)

    # CFD/24時間マーケット（指数先物・欧州指数・コモディティ）の急変アラート
    try:
        from src.alert_monitor import run_cfd_alert
        if run_cfd_alert():
            logger.info("✅ CFD/24時間アラート送信完了")
    except Exception:
        logger.error("CFD/24時間アラートエラー"); logger.debug(traceback.format_exc())

    # ── ドル円 緊急シグナルアラート（最優先・時間ガードなし）──
    #   ドル円で信頼度の高いシグナルが「複数の時間軸で重なった」瞬間だけ鳴らす。
    #   ドル円は24時間動くため、日足確定を待つ時間ガードはかけない。
    #   他銘柄とまとめると埋もれるので tech_signals とは独立して送る。
    #   連発防止: 同方向は4hクールダウン。方向反転・スコア急伸なら即再通知。
    try:
        from src.usdjpy_alert import run_usdjpy_emergency
        if run_usdjpy_emergency():
            logger.info("🚨 ドル円 緊急アラート送信完了")
    except Exception:
        logger.error("ドル円緊急アラートエラー"); logger.debug(traceback.format_exc())

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

    # チャートの形（candlestick.py）
    #   ローソク足7種＋プライスアクション3種を検出し、同じ方向の「出来事」が
    #   2つ以上重なった銘柄（年2回ほどの稀な場面）か、
    #   出来事1つ＋トレンド構造が一致した銘柄（月1回ほど）だけを通知する。
    #   高値安値の切り上げ等は数週間続く「状態」なので出来事として数えない
    #   （数えると毎週鳴って重なりの意味が失われる）。
    #   日足の確定が要るため、東京の引け後〜夜間のみ判定する。
    if now.hour >= 15 or now.hour < 6:
        try:
            from src.candlestick import run_pattern_alert
            if run_pattern_alert():
                logger.info("✅ チャートの形の通知送信完了")
        except Exception:
            logger.error("チャートの形の検出エラー", exc_info=True)

    # 為替シグナル（fx_signals.py）
    #   クロス円5組＋ドルストレート3組を週足・日足・4時間足で検査し、
    #   信頼度の高いサインが同方向に3つ以上そろった通貨ペアだけ通知する。
    #   為替は24時間動くため時間帯で絞らない（株と違い引け後の確定を待つ必要がない）。
    #   条件を緩めると毎日鳴って読み飛ばされるので、3つ以上は動かさないこと。
    #   配信先はFX専用グループ（TELEGRAM_FX_CHAT_ID）。
    try:
        from src.fx_signals import run_fx_alert
        if run_fx_alert():
            logger.info("✅ 為替シグナル通知送信完了")
    except Exception:
        logger.error("為替シグナル検出エラー", exc_info=True)

    # 窓開け（gap_scanner.py）
    #   前日終値と当日始値の差＝夜のうちに前提が変わった証拠。
    #   寄り付き後でないと始値が確定しないため 9:15〜11:30 の間だけ動かす。
    #   （9:00ちょうどだと気配値を拾うことがあるので少し待つ）
    #   埋め具合まで見るので、前場のうちに一度流せば十分。1日1回。
    if 9 <= now.hour < 12 and not (now.hour == 9 and now.minute < 15):
        try:
            from src.gap_scanner import run_gap_alert
            if run_gap_alert():
                logger.info("✅ 窓開け通知送信完了")
        except Exception:
            logger.error("窓開けスキャンエラー", exc_info=True)

    # リスク計器盤（risk_gauges.py）
    #   恐怖指数10種・債券/商品ボラ3種・日米金利・ドル指数・暗号資産F&Gを一覧し、
    #   「その指標にとって普段より大きい」動きが出たものだけ通知する。
    #   しきい値は各指標の過去1年から自動計算（固定%だと指標ごとの性格差を吸収できない）。
    try:
        from src.risk_gauges import run_gauge_alert
        if run_gauge_alert():
            logger.info("✅ 大きく動いた指標の通知送信完了")
    except Exception:
        logger.error("リスク計器盤エラー", exc_info=True)

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
