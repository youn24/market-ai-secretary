"""
fx_noon_run.py
FX午後レポート実行スクリプト — 毎日 14:00 JST 配信
GitHub Actions: .github/workflows/fx_noon.yml から呼ばれる

通知構成（2メッセージに圧縮）:
  ① テキスト: FX主要レート + マクロ + 地政学 + URL を1通にまとめ
  ② 画像: matplotlib 16パネルダッシュボード
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

# .env を最初に読み込む（FX_BOT_TOKEN などをモジュール変数に反映するため）
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from src.utils import setup_logger, get_jst_now

logger = setup_logger("fx_noon")

PAGES_URL = os.getenv(
    "GITHUB_PAGES_URL",
    "https://youn24.github.io/market-ai-secretary"
)

FX_CHAT_ID  = os.getenv("TELEGRAM_FX_CHAT_ID",  "").strip() or None
FX_BOT_TOKEN = os.getenv("TELEGRAM_FX_BOT_TOKEN", "").strip() or None


# ─────────────────────────────────────────────────────────────────────────────
# コンパクトサマリー生成（FX + マクロ + 地政学 + URL を1通に集約）
# ─────────────────────────────────────────────────────────────────────────────

def _build_compact_msg(fx_result: dict, mood_emoji: str, char_info: dict) -> str:
    data    = fx_result.get("data",    {}) or {}
    premium = fx_result.get("premium", {}) or {}

    # ── ヘッダー ──
    jst = get_jst_now()
    wd  = ["月", "火", "水", "木", "金", "土", "日"][jst.weekday()]
    lines = [
        "💱〰〰〰〰〰〰〰〰〰〰〰💱",
        "　　〽️ *ミセスワタナベ FX* 〽️",
        "　 ＼ 為替マーケット速報 ／",
        "💱〰〰〰〰〰〰〰〰〰〰〰💱",
        f"🗓 *{jst.year}年{jst.month}月{jst.day}日（{wd}）*",
        f"🕑 *{jst.strftime('%H:%M')} JST* ─ 東京市場",
    ]

    # キャラクター一言（あれば）
    if char_info.get("desc"):
        lines += ["", f"{mood_emoji} _{char_info['desc']}_"]

    # ── 主要FXレート ──
    def _rate(sym, label):
        d   = data.get(sym, {})
        v   = d.get("latest")
        chg = d.get("chg") or 0
        if v is None:
            return f"{label}: `---`"
        arr = "▲" if chg >= 0 else "▼"
        return f"{label}: `{v:,.2f}円` {arr}{abs(chg):.2f}%"

    lines += [
        "",
        "*📌 主要レート（東京14時）*",
        _rate("USDJPY=X", "💵 ドル円  "),
        _rate("EURJPY=X", "🇪🇺 ユーロ円"),
        _rate("GBPJPY=X", "🇬🇧 ポンド円"),
        _rate("AUDJPY=X", "🇦🇺 豪ドル円"),
        "━━━━━━━━━━━━━━",
    ]

    # ── マクロ環境 ──
    fred = premium.get("fred",     {})
    fw   = premium.get("fedwatch", {})
    tc   = premium.get("treasury", {})

    ffr   = fred.get("FEDFUNDS", {}).get("value") or (fw.get("current_ffr") if fw else None)
    cut_p = fw.get("cut_prob",  [None])[0] if fw else None
    jp10y = fred.get("IRLTLT01JPM156N", {}).get("value")
    us10y = data.get("^TNX", {}).get("latest") or (tc.get("10Y") if tc else None)
    vix   = data.get("^VIX", {}).get("latest")
    hy    = fred.get("BAMLH0A0HYM2", {}).get("value")

    macro_lines = ["*📊 マクロ & 市場環境*"]
    if ffr is not None:
        cut_str = f"  （次回利下げ {cut_p:.0f}%）" if cut_p is not None else ""
        macro_lines.append(f"🏦 政策金利: `{ffr:.2f}%`{cut_str}")
    if us10y is not None and jp10y is not None:
        diff = us10y - jp10y
        dir_str = "円安圧力" if diff >= 3.0 else "やや円安" if diff >= 2.0 else "円高圧力"
        macro_lines.append(f"📐 日米金利差: `{diff:.2f}%`（{dir_str}）")
    if vix is not None:
        vix_icon = "🟢" if vix < 20 else "🟡" if vix < 25 else "🔴"
        vix_str  = "安定" if vix < 20 else "警戒" if vix < 25 else "危険"
        macro_lines.append(f"⚡ 恐怖指数VIX: `{vix:.1f}` {vix_icon} {vix_str}")
    if hy is not None:
        hy_icon = "🟢" if hy < 3.5 else "🟡" if hy < 5 else "🔴"
        macro_lines.append(f"💳 信用スプレッド: `{hy:.2f}%` {hy_icon}")

    if len(macro_lines) > 1:
        lines += macro_lines + ["━━━━━━━━━━━━━━"]

    # ── 地政学リスク ──
    try:
        from src.macro_geopolitics import calc_geopolitical_risk
        risk = calc_geopolitical_risk(data)
        lines.append(f"*🌍 地政学リスク*: {risk['level']} `{risk['score']}/100`")
        for f in risk["factors"][:2]:          # 上位2件のみ
            lines.append(f"  • {f}")
        lines.append("━━━━━━━━━━━━━━")
    except Exception:
        pass

    # ── URL ──
    lines += [
        "*🔗 詳細チャート・全分析はこちら*",
        PAGES_URL,
        "📱 iPhoneのSafariで開けます",
    ]

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# メイン
# ─────────────────────────────────────────────────────────────────────────────

def main():
    logger.info("=" * 55)
    logger.info("  FX午後レポート開始 [14:00 JST]")
    logger.info(f"  実行時刻: {get_jst_now().strftime('%Y-%m-%d %H:%M:%S JST')}")
    logger.info("=" * 55)

    char_info  = {"mood": "analyzing", "desc": "", "path": None, "available": False}
    mood_emoji = "📊"

    # ── Step 1: FX ビジュアル分析 + チャート生成 ──────────────────
    fx_result = {"available": False, "text_msg": "", "url_msg": "", "chart_path": None}
    try:
        logger.info("--- Step 1: FX ビジュアル分析 ---")
        from src.fx_visual_report import run as fx_run
        fx_result = fx_run()
        if fx_result.get("available"):
            logger.info("✅ FX分析 + チャート生成完了")
            try:
                from src.character_selector import get_character_for_market, get_mood_emoji
                data       = fx_result.get("data", {})
                usdjpy_chg = data.get("USDJPY=X", {}).get("chg", 0) or 0
                vix        = data.get("^VIX",     {}).get("latest", 20) or 20
                rsi_val    = None
                if "USDJPY=X" in data:
                    from src.fx_visual_report import calc_rsi
                    close   = data["USDJPY=X"]["df"]["Close"].tail(30)
                    rsi_s   = calc_rsi(close)
                    rsi_val = float(rsi_s.iloc[-1]) if len(rsi_s) > 0 else None
                char_info  = get_character_for_market(usdjpy_chg, vix, rsi_val)
                mood_emoji = get_mood_emoji(char_info["mood"])
            except Exception:
                logger.debug(traceback.format_exc())
        else:
            logger.warning(f"⚠️  FX分析 一部失敗: {fx_result.get('error', '不明')}")
    except Exception:
        logger.error("FX分析 エラー")
        logger.debug(traceback.format_exc())

    # ── Step 2: Telegram 送信（2メッセージに圧縮） ────────────────
    try:
        logger.info("--- Step 2: Telegram 送信（2メッセージ）---")
        from src.notify_telegram import send_message, send_photo, _is_configured

        if not _is_configured():
            logger.info("Telegram 未設定 → スキップ")
            print("\n" + "─" * 60)
            print(_build_compact_msg(fx_result, mood_emoji, char_info))
            print("─" * 60)
            return

        # ① コンパクトサマリー（FX + マクロ + 地政学 + URL を1通）
        compact = _build_compact_msg(fx_result, mood_emoji, char_info)
        ok1 = send_message(compact, chat_id=FX_CHAT_ID, bot_token=FX_BOT_TOKEN)
        logger.info(f"{'✅' if ok1 else '❌'} ① コンパクトサマリー送信")

        # ② ダッシュボード画像
        chart_path = fx_result.get("chart_path", "")
        if chart_path and os.path.exists(chart_path):
            caption = (
                "💱 *為替FX 16パネルダッシュボード*\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "📈 ドル円チャート ／ テクニカル指標\n"
                "💵 ドル指数 ／ 日米金利差 ／ 通貨強弱\n"
                "🏦 利下げ確率 ／ 投機ポジション ／ VIX\n"
                "🌐 米国債イールドカーブ ／ マクロ指標"
            )
            ok2 = send_photo(chart_path, caption=caption,
                             chat_id=FX_CHAT_ID, bot_token=FX_BOT_TOKEN)
            logger.info(f"{'✅' if ok2 else '❌'} ② ダッシュボード画像送信")
        else:
            logger.warning("チャートファイルなし（深夜テスト時は正常）")

    except Exception:
        logger.error("Telegram 送信エラー")
        logger.debug(traceback.format_exc())

    logger.info("=" * 55)
    logger.info("  FX午後レポート完了")
    logger.info("=" * 55)


if __name__ == "__main__":
    main()
