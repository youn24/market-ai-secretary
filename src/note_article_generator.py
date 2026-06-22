"""
src/note_article_generator.py
実際の市場データからnote記事テキストを自動生成して data/ に保存する
"""
import os
from pathlib import Path
from src.utils import setup_logger, get_today_str

logger = setup_logger("note_article_generator")


def _p(prices: dict, sym: str, unit: str = "", decimals: int = 2) -> str:
    d   = prices.get(sym, {})
    v   = d.get("latest")
    chg = d.get("change_pct")
    if v is None:
        return "---"
    fmt   = f"{{:,.{decimals}f}}"
    vs    = fmt.format(v) + unit
    if chg is None:
        return vs
    arrow = "▲" if chg >= 0 else "▼"
    sign  = "+" if chg >= 0 else ""
    return f"{vs}（{arrow}{sign}{chg:.2f}%）"


def _mood(score: float) -> str:
    if   score >= 2:    return "🟢 強気！上昇ムード"
    elif score >= 0.5:  return "🟢 やや強気"
    elif score >= -0.5: return "🟡 中立・様子見"
    elif score >= -2:   return "🟠 やや弱気・注意"
    else:               return "🔴 弱気！慎重に"


def _fg_label(score) -> str:
    n = int(score or 50)
    if n >= 75: return f"超強欲😱（{n}）"
    if n >= 55: return f"強欲😤（{n}）"
    if n >= 45: return f"中立😐（{n}）"
    if n >= 25: return f"恐怖😰（{n}）"
    return f"超恐怖😭（{n}）"


def _vix_comment(vix: float) -> str:
    if vix < 15: return "安定圏。リスクオン継続しやすい環境。"
    if vix < 20: return "やや不安定。急変に備えた分散が有効。"
    if vix < 30: return "警戒水準。ポジション管理に注意。"
    return "危険水準！急落リスクが高い状態。"


def generate(prices: dict, risk: dict, fear_greed: dict,
             ai_summary: dict = None, scenario: dict = None,
             news: list = None, note_magazine_url: str = "") -> dict:
    """
    note記事テキストを生成して data/note_article_YYYY-MM-DD.md に保存する

    Returns:
        dict: available, path, title, free_text, paid_text
    """
    result = {"available": False, "path": "", "title": "", "free_text": "", "paid_text": ""}

    try:
        today      = get_today_str()
        score      = risk.get("score", 0)
        score_s    = f"+{score:.1f}" if score >= 0 else f"{score:.1f}"
        mood       = _mood(score)
        fg_score   = fear_greed.get("score") or 50
        vix_val    = prices.get("^VIX", {}).get("latest") or 0
        mag_url    = note_magazine_url or os.getenv("NOTE_MAGAZINE_URL", "").strip()

        # ── 無料パート ──────────────────────────────────────
        free_lines = [
            f"こんにちは、市場AI秘書です。",
            f"毎朝7時30分に株・為替・コモディティをAIが自動分析しています。",
            f"",
            f"━━━━━━━━━━━━━━━━━",
            f"📊 {today} 主要マーケット",
            f"━━━━━━━━━━━━━━━━━",
            f"",
            f"🇯🇵 日経平均  {_p(prices, '^N225',   '円', 0)}",
            f"🇺🇸 S&P500   {_p(prices, '^GSPC',   '',  2)}",
            f"🇺🇸 NASDAQ   {_p(prices, '^IXIC',   '',  2)}",
            f"",
            f"💵 ドル円    {_p(prices, 'USDJPY=X','円', 2)}",
            f"🥇 金        {_p(prices, 'GC=F',    '$',  0)}",
            f"🛢 原油      {_p(prices, 'CL=F',    '$',  2)}",
            f"₿  BTC      {_p(prices, 'BTC-USD', '$',  0)}",
            f"",
            f"⚡ VIX恐怖指数  {vix_val:.1f}",
            f"😱 Fear&Greed  {_fg_label(fg_score)}",
            f"",
            f"━━━━━━━━━━━━━━━━━",
            f"🤖 今日のAI判断",
            f"━━━━━━━━━━━━━━━━━",
            f"",
            f"{mood}",
            f"AIスコア：{score_s}（-3〜+3）",
            f"",
        ]

        # 重要ニュース（無料）
        top_news = [n for n in (news or []) if n.get("importance") == "A"][:3]
        if top_news:
            free_lines += ["━━━━━━━━━━━━━━━━━", "📰 本日の注目ニュース", "━━━━━━━━━━━━━━━━━", ""]
            for n in top_news:
                free_lines.append(f"🔴 {n.get('title', '')}")
            free_lines.append("")

        if mag_url:
            free_lines += [
                f"📰 毎朝マガジンで深掘り分析をお届けしています",
                f"👇 マガジン登録はこちら",
                mag_url,
            ]

        # ── 有料パート ──────────────────────────────────────
        paid_lines = [
            f"━━━━━━━━━━━━━━━━━",
            f"🤖 AI 3視点分析（有料）",
            f"━━━━━━━━━━━━━━━━━",
            f"",
        ]

        ai_summary = ai_summary or {}
        if ai_summary.get("available"):
            bull = (ai_summary.get("bull_view") or "").strip()
            bear = (ai_summary.get("bear_view") or "").strip()
            neut = (ai_summary.get("neutral_view") or "").strip()
            if bull:
                paid_lines += [f"📈 強気派の見方", bull, ""]
            if bear:
                paid_lines += [f"📉 弱気派の見方", bear, ""]
            if neut:
                paid_lines += [f"⚖️ AIの総合判断", neut, ""]
        else:
            paid_lines += ["📊 AI分析データ準備中", ""]

        # VIXコメント
        paid_lines += [
            f"━━━━━━━━━━━━━━━━━",
            f"⚡ VIX分析",
            f"━━━━━━━━━━━━━━━━━",
            f"",
            f"VIX {vix_val:.1f} → {_vix_comment(vix_val)}",
            f"",
        ]

        # シナリオ
        scenario = scenario or {}
        if scenario.get("available"):
            paid_lines += ["━━━━━━━━━━━━━━━━━", "🎯 3つのシナリオ", "━━━━━━━━━━━━━━━━━", ""]
            for sc in scenario.get("scenarios", []):
                name  = sc.get("name", "")
                prob  = sc.get("probability", 0)
                desc  = sc.get("description", "")
                paid_lines += [f"【{name} {prob}%】", desc, ""]
        else:
            paid_lines += [
                "━━━━━━━━━━━━━━━━━",
                "🎯 3つのシナリオ",
                "━━━━━━━━━━━━━━━━━",
                "",
                f"【楽観シナリオ】VIX低下・ドル円上昇継続で株高",
                f"【基本シナリオ】現在の水準でレンジ推移",
                f"【悲観シナリオ】VIX上昇・リスクオフで下落",
                "",
            ]

        if mag_url:
            paid_lines += [
                "━━━━━━━━━━━━━━━━━",
                "📰 毎朝このような分析をマガジンでお届けしています",
                f"👇 マガジン登録（毎朝届く）",
                mag_url,
            ]

        # ── ファイル保存 ──────────────────────────────────────
        title     = f"【{today}】市場AI秘書の朝レポート｜今日の相場判断と3つのシナリオ"
        free_text = "\n".join(free_lines)
        paid_text = "\n".join(paid_lines)

        full_md = (
            f"# {title}\n\n"
            f"{free_text}\n\n"
            f"---ここから有料---\n\n"
            f"{paid_text}\n"
        )

        out_dir  = Path("data")
        out_dir.mkdir(exist_ok=True)
        out_path = out_dir / f"note_article_{today}.md"
        out_path.write_text(full_md, encoding="utf-8")

        logger.info(f"✅ note記事生成完了: {out_path}")
        result.update({
            "available":  True,
            "path":       str(out_path),
            "title":      title,
            "free_text":  free_text,
            "paid_text":  paid_text,
        })

    except Exception as e:
        logger.error(f"note記事生成エラー: {e}")

    return result


def run(prices: dict, risk: dict, fear_greed: dict,
        ai_summary: dict = None, scenario: dict = None,
        news: list = None, note_magazine_url: str = "") -> dict:
    return generate(prices, risk, fear_greed,
                    ai_summary=ai_summary,
                    scenario=scenario,
                    news=news,
                    note_magazine_url=note_magazine_url)
