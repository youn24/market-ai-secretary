"""
軽量・寄り前/引け後チェック（GitHub Actions用）
- 平日 9:00 JST（東証スタート＝寄り） と 15:30 JST（東証クローズ＝引け後）に実行
- フルレポート（約15通）ではなく「サマリーカード画像1枚＋一言」だけを送る
- 7:30 のフル朝レポートと役割を分け、通知の数を抑えるのが目的
"""
import sys
import traceback
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))
from src.utils import ensure_dirs, setup_logger, get_jst_now

logger = setup_logger("intraday_run")

_WEEKDAYS_JA = ["月", "火", "水", "木", "金", "土", "日"]


def _session_label() -> tuple:
    """現在時刻から (見出し, 補足) を決める。"""
    h = get_jst_now().hour
    if h < 12:
        return "🌅 寄りチェック", "東証スタート時点のスナップショット"
    elif h < 14:
        return "🍱 前場まとめ", "午前の取引（前場）を終えた時点の分析要約"
    elif h < 18:
        return "🔔 引け後チェック", "東証クローズ時点のスナップショット"
    else:
        return "🌙 ナイトチェック", "夜間市場のスナップショット"


def _fmt(prices: dict, sym: str, unit: str = "") -> str:
    d = prices.get(sym, {})
    v, chg = d.get("latest"), d.get("change_pct")
    if v is None:
        return f"{sym}: ---"
    arrow = "▲" if (chg or 0) >= 0 else "▼"
    chg_s = f"{arrow}{abs(chg):.2f}%" if chg is not None else ""
    return f"{v:,.2f}{unit} {chg_s}"


def _one_line(prices: dict) -> str:
    """主要指標から一言コメントを組み立てる（ルールベース・API不要）。"""
    parts = []
    n225 = prices.get("^N225", {}).get("change_pct")
    if n225 is not None:
        mood = "堅調" if n225 >= 0.5 else "軟調" if n225 <= -0.5 else "もみ合い"
        parts.append(f"日経は{mood}（{n225:+.2f}%）")
    usdjpy = prices.get("USDJPY=X", {})
    if usdjpy.get("latest") is not None:
        parts.append(f"ドル円 {usdjpy['latest']:,.2f}")
    vix = prices.get("^VIX", {}).get("latest")
    if vix is not None:
        vmood = "警戒" if vix >= 25 else "やや不安" if vix >= 20 else "落ち着き"
        parts.append(f"VIX {vix:.1f}（{vmood}）")
    return " / ".join(parts) if parts else "主要指標の取得に失敗しました"


def _zenba_summary(prices: dict) -> str:
    """前場（午前の取引）の分析要約を数行で組み立てる（ルールベース・API不要）。"""
    lines = []
    n225 = prices.get("^N225", {})
    nchg = n225.get("change_pct")
    nval = n225.get("latest")
    if nchg is not None and nval is not None:
        if   nchg >= 1.0:  read = "買い優勢で堅調"
        elif nchg >= 0.2:  read = "小幅高でしっかり"
        elif nchg > -0.2:  read = "方向感に乏しくもみ合い"
        elif nchg > -1.0:  read = "上値の重い展開"
        else:              read = "売り優勢で軟調"
        lines.append(f"📊 日経 {nval:,.0f}（{nchg:+.2f}%）— 前場は{read}")

    usdjpy = prices.get("USDJPY=X", {})
    uchg, uval = usdjpy.get("change_pct"), usdjpy.get("latest")
    if uval is not None:
        if   uchg is not None and uchg >= 0.2:  fx = "円安が追い風"
        elif uchg is not None and uchg <= -0.2: fx = "円高が重し"
        else:                                   fx = "為替は横ばい"
        lines.append(f"💱 ドル円 {uval:,.2f} — {fx}")

    g = prices.get("GROWTH250", {}).get("change_pct")
    if g is not None and nchg is not None:
        rel = g - nchg
        if   rel >= 0.5:  risk = "新興・グロースに資金（リスクオン気味）"
        elif rel <= -0.5: risk = "大型・バリュー優位（守りの色）"
        else:             risk = "大型と新興はほぼ拮抗"
        lines.append(f"🚀 グロース250 {g:+.2f}% — {risk}")

    vix = prices.get("^VIX", {}).get("latest")
    if vix is not None:
        vmood = "警戒水準" if vix >= 25 else "やや不安" if vix >= 20 else "落ち着き"
        lines.append(f"😱 VIX {vix:.1f} — 市場心理は{vmood}")

    return "\n".join(lines) if lines else "主要指標の取得に失敗しました"


def run():
    ensure_dirs()
    now = get_jst_now()
    logger.info(f"====== 軽量チェック開始 [{now.strftime('%Y-%m-%d %H:%M')}] ======")

    title, sub = _session_label()
    time_label = f"{now.month}/{now.day}({_WEEKDAYS_JA[now.weekday()]}) {now.strftime('%H:%M')}"

    prices     = {}
    fear_greed = {"score": 50, "rating_ja": "中立"}
    risk       = {"score": 0, "sentiment": "中立"}

    try:
        from src.fetch_prices import run as fp
        prices, fear_greed = fp()
        logger.info(f"取得完了: {sum(1 for v in prices.values() if v.get('latest'))}銘柄")
    except Exception:
        logger.error("価格取得エラー"); logger.debug(traceback.format_exc())

    try:
        from src.indicators import calc_risk_score
        risk = calc_risk_score(prices)
    except Exception:
        logger.debug(traceback.format_exc())

    # キャプション（前場まとめは複数行の分析要約、それ以外は一言）
    pages_url = "https://youn24.github.io/market-ai-secretary"
    body = _zenba_summary(prices) if "前場" in title else _one_line(prices)
    caption = (
        f"┌ *{title}* ┃ {time_label}\n"
        f"└ {sub}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"{body}\n\n"
        f"💡 詳しくは朝7:30のフルレポート、または\n{pages_url}"
    )

    # サマリーカード画像を1枚だけ送る
    try:
        from src.summary_card import make_summary_card
        from src.notify_telegram import send_photo, send_message
        card = make_summary_card(prices, fear_greed, risk)
        if card and Path(card).exists():
            ok = send_photo(card, caption=caption)
            logger.info("✅ サマリーカード送信" if ok else "送信失敗（設定確認）")
        else:
            send_message(caption)
            logger.info("✅ テキストのみ送信（カード生成失敗）")
    except Exception:
        logger.error("送信エラー"); logger.debug(traceback.format_exc())

    logger.info("====== 軽量チェック終了 ======")


if __name__ == "__main__":
    run()
