"""
夜の相場振り返り + 感情売買ガード
毎晩23時 JST に Telegram へ送信。

【機能】
1. 今日の相場を3行でまとめる（Gemini生成）
2. 明日の注意点を1行で提示
3. VIX水準に応じて「感情的判断の危険度」アラート
4. 恐怖・強欲指数の今日の終値チェック
"""
import os
import traceback
import logging
from src.utils import get_jst_now

logger = logging.getLogger(__name__)


def _vix_emotion_alert(vix: float) -> tuple[str, str]:
    """VIX → (感情警告レベル, メッセージ)"""
    if vix >= 35:
        return "🚨 超危険", (
            "━━━━━━━━━━━━━━━\n"
            "🚨 *感情売買ガード: 最高警戒*\n"
            f"VIX {vix:.1f} → 市場は極度の恐怖状態です。\n"
            "❌ 今この瞬間の売却は統計的に最悪タイミングです。\n"
            "✅ 過去の暴落から1年以内に全回復した例が大多数。\n"
            "📌 *今夜は何もしないことが最善策です。*\n"
            "━━━━━━━━━━━━━━━"
        )
    elif vix >= 25:
        return "⚠️ 警戒", (
            "⚠️ *感情売買ガード: 警戒モード*\n"
            f"VIX {vix:.1f} → 不安が高まっています。\n"
            "冷静に。このレベルで売った人の多くが後悔しています。"
        )
    elif vix >= 20:
        return "🟡 注意", (
            f"🟡 VIX {vix:.1f} — やや不安定。慌てず様子見を。"
        )
    else:
        return "✅ 平穏", ""


def _fg_emoji(score: float) -> str:
    if score >= 75: return f"😱 超強欲 ({score:.0f})"
    elif score >= 55: return f"😤 強欲 ({score:.0f})"
    elif score >= 45: return f"😐 中立 ({score:.0f})"
    elif score >= 25: return f"😰 恐怖 ({score:.0f})"
    else: return f"😭 超恐怖 ({score:.0f})"


def _change_arrow(chg: float | None) -> str:
    if chg is None: return "---"
    arrow = "▲" if chg >= 0 else "▼"
    return f"{arrow}{abs(chg):.2f}%"


def generate_evening_message(prices: dict, fear_greed: dict, risk: dict) -> str:
    """夜の振り返りTelegramメッセージ全文を生成"""
    now = get_jst_now()
    date_str = now.strftime("%Y年%m月%d日")

    vix     = prices.get("^VIX", {}).get("latest") or 20
    sp_chg  = prices.get("^GSPC", {}).get("change_pct") or 0
    nk_chg  = prices.get("^N225", {}).get("change_pct") or 0
    dxy_chg = prices.get("DX-Y.NYB", {}).get("change_pct") or 0
    usdjpy  = prices.get("USDJPY=X", {}).get("latest") or 150
    fg_score= fear_greed.get("score") or 50
    rs      = risk.get("score", 0)

    # ── 感情ガード ──
    emotion_level, emotion_msg = _vix_emotion_alert(vix)

    # ── Gemini で今日のまとめを生成 ──
    recap_text = ""
    tomorrow_tip = ""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if api_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))

            prompt = f"""今日({date_str})の市場を振り返り、投資初心者に向けて超わかりやすくまとめてください。

データ:
- S&P500: {_change_arrow(sp_chg)}
- 日経225: {_change_arrow(nk_chg)}
- ドル円: {usdjpy:.1f}円
- VIX(恐怖指数): {vix:.1f}
- Fear&Greed: {fg_score:.0f}
- 地合いスコア: {rs:+.2f}

以下の形式で出力してください（各行30字以内・絵文字1個含む）:
1行目: 今日一番大事だったこと（結論）
2行目: その理由（なぜそうなった？）
3行目: 明日への一言アドバイス

専門用語は使わず中学生でもわかる言葉で。"""

            resp = model.generate_content(prompt)
            # ⚠️ resp.text は本文が空だと例外を投げる（思考モデルで出力が
            #    打ち切られたとき等）。朝の統合AI解釈はこれで2週間落ちていた。
            try:
                raw = resp.text or ""
            except Exception:
                raw = ""
                try:
                    fr = resp.candidates[0].finish_reason
                    logger.error(f"夜の振り返り: Geminiの本文が空でした"
                                 f"（finish_reason={getattr(fr, 'name', fr)}）")
                except Exception:
                    logger.error("夜の振り返り: Geminiの本文が空でした")
            lines = [l.strip() for l in raw.strip().splitlines() if l.strip()]
            if len(lines) >= 3:
                recap_text  = "\n".join(lines[:2])
                tomorrow_tip = lines[2]
            elif lines:
                recap_text = "\n".join(lines)
        except Exception:
            # warning＋debug では本番ログに原因が残らない。error で型ごと残す。
            logger.error("夜の振り返り: Gemini生成に失敗", exc_info=True)

    # ── フォールバック（Geminiが使えなかった日）──
    # ⚠️ 以前は**米国株(S&P500)だけ**で判定していた。そのため
    #    2026-09-11、日経が-2.47%下げた日に（S&Pは-0.58%）
    #    「📊 今日は方向感のない横ばい相場でした／大きな動きなく静かな1日でした」
    #    と、真上に並ぶ数字と正反対のことを送っていた。
    #    読んでいるのは日本株の投資家なので、**日経を先に見る**。
    #    どちらかが大きく動いた日に「静か」とは絶対に書かない。
    # 価格が取れなかった日を「静か」と呼ばない。取れていないだけである。
    _have_nk = isinstance((prices.get("^N225") or {}).get("change_pct"), (int, float))
    _have_sp = isinstance((prices.get("^GSPC") or {}).get("change_pct"), (int, float))
    if not recap_text and not (_have_nk or _have_sp):
        recap_text = ("⚠️ 今日は株価データを取得できませんでした\n"
                      "明朝のレポートで改めてお伝えします。")
    if not recap_text:
        big_nk = abs(nk_chg) >= 1.0
        big_sp = abs(sp_chg) >= 1.0
        if big_nk and nk_chg < 0:
            recap_text = (f"📉 今日は日本株が大きく下げました（日経 {_change_arrow(nk_chg)}）\n"
                          + ("米国株も下げており、世界的に売りが優勢でした。" if sp_chg <= -0.5
                             else "米国株は小動きで、日本側の材料による下げでした。"))
        elif big_nk and nk_chg > 0:
            recap_text = (f"📈 今日は日本株が大きく上げました（日経 {_change_arrow(nk_chg)}）\n"
                          + ("米国株も上げており、世界的に買いが優勢でした。" if sp_chg >= 0.5
                             else "米国株は小動きで、日本側の材料による上げでした。"))
        elif big_sp:
            recap_text = (f"{'📈' if sp_chg > 0 else '📉'} 米国株が大きく"
                          f"{'上げ' if sp_chg > 0 else '下げ'}ました（{_change_arrow(sp_chg)}）\n"
                          "日本株は小動きでしたが、明日の寄り付きに響く可能性があります。")
        elif abs(nk_chg) >= 0.5 or abs(sp_chg) >= 0.5:
            recap_text = (f"📊 今日は小幅な動きでした（日経 {_change_arrow(nk_chg)}／"
                          f"S&P {_change_arrow(sp_chg)}）\n大きな方向感は出ていません。")
        else:
            recap_text = "📊 今日は方向感のない横ばい相場でした\n大きな動きなく静かな1日でした。"
    if not tomorrow_tip:
        tomorrow_tip = "明日も無理せず、長期目線で✨"

    # ── メッセージ組み立て ──
    lines = [
        f"🌙 *今日の相場振り返り — {date_str}*",
        "",
        "━━ 📊 今日の数字 ━━",
        f"🇺🇸 S\\&P500   {_change_arrow(sp_chg)}",
        f"🇯🇵 日経225  {_change_arrow(nk_chg)}",
        f"💴 ドル円   {usdjpy:.1f}円",
        f"😱 恐怖指数 VIX {vix:.1f}",
        f"💭 Fear\\&Greed  {_fg_emoji(fg_score)}",
        "",
        "━━ 🤖 AIの振り返り ━━",
        recap_text,
        "",
        f"📌 *明日のポイント*: {tomorrow_tip}",
    ]

    if emotion_msg:
        lines += ["", emotion_msg]

    lines += [
        "",
        "━━━━━━━━━━━━━━━",
        "💤 ゆっくり休んでください。明日の朝7:30にまた分析をお届けします🤖",
    ]

    return "\n".join(lines)


def send_evening_telegram(message: str) -> bool:
    """Telegramに夜の振り返りを送信

    ⚠️ 2026-09-11まで、ここだけ api.telegram.org へ直接 requests.post していた。
       そのため:
       ・notify_meter（通知の実績記録）を通らず、夜の分が記録に残らなかった
       ・Markdownの書式エラー（Geminiの文に * や _ が1つ余る等）で
         Telegramが400を返すと、**そのまま届かなかった**
       send_message は書式エラー時に書式なしで送り直すので、そちらに揃える。
    """
    token   = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    skip    = {"ここにBotFatherのトークン", "ここにあなたのChat ID", ""}
    if token in skip or chat_id in skip:
        logger.warning("Telegram未設定 — 送信スキップ")
        return False
    try:
        from src.notify_telegram import send_message
        ok = bool(send_message(message))
        if ok:
            logger.info("✅ 夜の振り返り送信完了")
        else:
            logger.error("❌ 夜の振り返りの送信に失敗しました")
        return ok
    except Exception:
        logger.error("❌ 夜の振り返りの送信でエラー", exc_info=True)
        return False


def run(prices: dict, fear_greed: dict, risk: dict) -> dict:
    """エントリーポイント"""
    try:
        msg = generate_evening_message(prices, fear_greed, risk)
        ok  = send_evening_telegram(msg)
        return {"available": ok, "message": msg}
    except Exception:
        logger.error("夜の振り返りエラー"); logger.debug(traceback.format_exc())
        return {"available": False, "message": ""}
