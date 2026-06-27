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
# Gemini AI 為替コメント生成
# ─────────────────────────────────────────────────────────────────────────────

def _gemini_fx_comment(data: dict, premium: dict) -> str:
    """Gemini-1.5-flash で FX市場の2〜3文AI解説を生成（日本語）"""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return ""
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))

        usdjpy  = data.get("USDJPY=X", {})
        vix     = data.get("^VIX",     {}).get("latest", "N/A")
        gold_chg= data.get("GC=F",     {}).get("chg",    "N/A")
        dxy     = data.get("DX-Y.NYB", {}).get("latest", "N/A")
        fred    = premium.get("fred",  {})
        fw      = premium.get("fedwatch", {})
        ffr     = fred.get("FEDFUNDS", {}).get("value") or (fw.get("current_ffr") if fw else None)
        cut_p   = (fw.get("cut_prob", [None])[0] if fw else None)

        facts = [
            f"ドル円: {usdjpy.get('latest','N/A'):.3f}円（前日比 {usdjpy.get('chg',0):+.2f}%）" if usdjpy.get("latest") else "ドル円: N/A",
            f"VIX恐怖指数: {vix:.1f}" if isinstance(vix, float) else f"VIX: {vix}",
            f"ドル指数(DXY): {dxy:.2f}" if isinstance(dxy, float) else f"DXY: {dxy}",
            f"金の前日比: {gold_chg:+.2f}%" if isinstance(gold_chg, float) else "",
            f"米政策金利(FFR): {ffr:.2f}%" if ffr else "",
            f"次回FOMC利下げ確率: {cut_p:.0f}%" if cut_p is not None else "",
        ]
        facts_str = "\n".join(f for f in facts if f)

        prompt = (
            "あなたはFX・マクロ専門アナリストです。以下の本日の市場データをもとに、"
            "ドル円相場の動向と今後の注目点を投資初心者にもわかるよう"
            "2〜3文の日本語で簡潔かつ丁寧に解説してください。"
            "断定は避け、「〜が注目されます」「〜に注意が必要です」などの表現を使ってください。\n\n"
            f"【本日の市場データ】\n{facts_str}"
        )
        resp = model.generate_content(prompt)
        return (resp.text or "").strip()[:350]
    except Exception:
        return ""


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

    # ── Gemini AI 解説 ──
    try:
        ai_comment = _gemini_fx_comment(data, premium)
        if ai_comment:
            lines += [
                "*🤖 AI市場解説（Gemini）*",
                ai_comment,
                "━━━━━━━━━━━━━━",
            ]
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
# IMM 投機筋ポジション + 中央銀行・介入監視 メッセージ生成
# ─────────────────────────────────────────────────────────────────────────────

def _build_imm_cb_msg(fx_result: dict) -> str:
    """
    ② IMM 投機筋ポジション + 中央銀行・介入監視 の1通
    FX速報テキスト（①）とは別メッセージで送信する
    """
    data    = fx_result.get("data",    {}) or {}
    premium = fx_result.get("premium", {}) or {}

    jst = get_jst_now()
    wd  = ["月", "火", "水", "木", "金", "土", "日"][jst.weekday()]

    lines = [
        "📡〰〰〰〰〰〰〰〰〰〰〰📡",
        "　 *投機筋ポジション & 介入監視*",
        "📡〰〰〰〰〰〰〰〰〰〰〰📡",
        f"🗓 {jst.year}年{jst.month}月{jst.day}日（{wd}） {jst.strftime('%H:%M')} JST",
        "",
    ]

    # ── IMM 投機筋ポジション ──
    try:
        from src.cb_monitor import build_imm_summary_text
        imm = build_imm_summary_text(premium)
        if imm:
            lines += [imm, "━━━━━━━━━━━━━━", ""]
    except Exception:
        pass

    # ── 中央銀行・為替介入監視 ──
    try:
        from src.cb_monitor import build_cb_monitor_text
        cb = build_cb_monitor_text(data)
        if cb:
            lines += [cb, "━━━━━━━━━━━━━━", ""]
    except Exception:
        pass

    lines.append("📱 詳細は下の画像ダッシュボードをご確認ください")
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

    # ── Step 2: Telegram 送信（3メッセージ構成） ────────────────────
    try:
        logger.info("--- Step 2: Telegram 送信（3メッセージ）---")
        from src.notify_telegram import send_message, send_photo, _is_configured

        if not _is_configured():
            logger.info("Telegram 未設定 → スキップ")
            print("\n" + "─" * 60)
            print(_build_compact_msg(fx_result, mood_emoji, char_info))
            print("─" * 60)
            print(_build_imm_cb_msg(fx_result))
            print("─" * 60)
            return

        # ⓪ FXサマリーカード（HTML→PNG・Canva級の一目でわかる1枚）
        try:
            from src.fx_summary_card import make_fx_card
            _data    = fx_result.get("data", {}) or {}
            _premium = fx_result.get("premium", {}) or {}
            _ai      = _gemini_fx_comment(_data, _premium)
            card_path = make_fx_card(_data, _premium, ai_comment=_ai)
            if card_path and os.path.exists(card_path):
                send_photo(card_path, caption="〽️ ミセスワタナベ FX ─ 本日の為替サマリー",
                           chat_id=FX_CHAT_ID, bot_token=FX_BOT_TOKEN)
                logger.info("✅ ⓪ FXサマリーカード送信")
        except Exception:
            logger.debug(traceback.format_exc())

        # ① コンパクトサマリー（FX + マクロ + 地政学 + AI解説 + URL）
        compact = _build_compact_msg(fx_result, mood_emoji, char_info)
        ok1 = send_message(compact, chat_id=FX_CHAT_ID, bot_token=FX_BOT_TOKEN)
        logger.info(f"{'✅' if ok1 else '❌'} ① FXサマリー送信")

        # ② IMM 投機筋ポジション + 中央銀行・介入監視
        imm_cb = _build_imm_cb_msg(fx_result)
        ok2 = send_message(imm_cb, chat_id=FX_CHAT_ID, bot_token=FX_BOT_TOKEN)
        logger.info(f"{'✅' if ok2 else '❌'} ② 投機筋ポジション・介入監視送信")

        # ③ ダッシュボード画像
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
            ok3 = send_photo(chart_path, caption=caption,
                             chat_id=FX_CHAT_ID, bot_token=FX_BOT_TOKEN)
            logger.info(f"{'✅' if ok3 else '❌'} ③ ダッシュボード画像送信")
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
