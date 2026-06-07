"""
fx_noon_run.py
FX午後レポート実行スクリプト — 毎日 14:00 JST 配信
GitHub Actions: .github/workflows/fx_noon.yml から呼ばれる

構成:
  ① Telegram テキスト（FX サマリー + 主要レート）
  ② Telegram 画像（matplotlib ダッシュボード PNG）
  ③ Telegram URL（GitHub Pages レポートリンク）
"""

import os
import sys
import traceback
from pathlib import Path

# Windows ローカル実行時の文字化け対策
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# プロジェクトルートを PYTHONPATH に追加
sys.path.insert(0, str(Path(__file__).parent))

from src.utils import setup_logger, get_jst_now

logger = setup_logger("fx_noon")

PAGES_URL = os.getenv(
    "GITHUB_PAGES_URL",
    "https://youn24.github.io/market-ai-secretary"
)


def main():
    logger.info("=" * 55)
    logger.info("  FX午後レポート開始 [14:00 JST]")
    logger.info(f"  実行時刻: {get_jst_now().strftime('%Y-%m-%d %H:%M:%S JST')}")
    logger.info("=" * 55)

    # ── 環境変数読み込み（ローカル実行時） ─────────────────────────
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # GitHub Actions では不要

    # ── Step 1: FX ビジュアル分析 + チャート生成 ──────────────────
    fx_result = {"available": False, "text_msg": "", "url_msg": "", "chart_path": None}
    try:
        logger.info("--- Step 1: FX ビジュアル分析 ---")
        from src.fx_visual_report import run as fx_run
        fx_result = fx_run()
        if fx_result.get("available"):
            logger.info("✅ FX分析 + チャート生成完了")
        else:
            err = fx_result.get("error", "不明なエラー")
            logger.warning(f"⚠️  FX分析 一部失敗: {err}")
    except Exception:
        logger.error("FX分析 エラー")
        logger.debug(traceback.format_exc())

    # ── Step 2: Telegram 送信（3メッセージ構成） ──────────────────
    try:
        logger.info("--- Step 2: Telegram 送信 ---")
        from src.notify_telegram import send_message, send_photo, _is_configured

        if not _is_configured():
            logger.info("Telegram 未設定 → スキップ（テストモード）")
            # テスト時はテキストだけ表示
            print("\n" + "─" * 60)
            print(fx_result.get("text_msg", "（メッセージなし）"))
            print("─" * 60)
            return

        # ①  テキストサマリー
        text = fx_result.get("text_msg") or _fallback_text()
        ok1  = send_message(text)
        logger.info(f"{'✅' if ok1 else '❌'} ① テキスト送信")

        # ②  チャート画像
        chart_path = fx_result.get("chart_path", "")
        if chart_path and os.path.exists(chart_path):
            caption = (
                "📊 *FX ダッシュボード*\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "📈 USD/JPY + BB + MA\n"
                "📐 RSI / MACD / Stochastic\n"
                "💵 DXY / クロスアセット / 金利差\n"
                "💪 通貨強弱 / IMM / 相関マトリクス\n"
                "🏦 FedWatch / ⚡ VIX ゲージ / 💹 価格ボード"
            )
            ok2 = send_photo(chart_path, caption=caption)
            logger.info(f"{'✅' if ok2 else '❌'} ② チャート画像送信")
        else:
            logger.warning("チャートファイルなし → テキスト代替")
            send_message("📊 チャート生成に問題が発生しました。次回をお待ちください。")

        # ③  URL
        url_msg = fx_result.get("url_msg") or (
            f"🔗 *詳細レポート*\n{PAGES_URL}\n📱 iPhone Safari で開けます"
        )
        ok3 = send_message(url_msg)
        logger.info(f"{'✅' if ok3 else '❌'} ③ URL 送信")

    except Exception:
        logger.error("Telegram 送信エラー")
        logger.debug(traceback.format_exc())

    # ── 完了 ─────────────────────────────────────────────────────
    logger.info("=" * 55)
    logger.info("  FX午後レポート完了")
    logger.info("=" * 55)


def _fallback_text() -> str:
    """データ取得失敗時のフォールバックメッセージ"""
    from src.utils import get_jst_now
    now = get_jst_now()
    return (
        f"💹 *FX 午後マーケットレポート*\n"
        f"📅 {now.strftime('%Y/%m/%d')}  14:00 JST\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ データ取得中に問題が発生しました。\n"
        f"しばらくしてから再度ご確認ください。\n"
        f"🔗 {PAGES_URL}"
    )


if __name__ == "__main__":
    main()
