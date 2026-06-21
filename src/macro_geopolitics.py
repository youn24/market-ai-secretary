"""
src/macro_geopolitics.py
マクロ経済 + 地政学リスク分析モジュール（FX専用トークルーム向け）
─────────────────────────────────────────────
■ マクロ経済
  - FRED 実データ（FFR・CPI・失業率・HYスプレッド・日米金利）
  - 米財務省イールドカーブ・逆イールド判定
  - 日米金利差（円安/円高の主因）

■ 地政学リスク
  - 安全資産フロー（金・原油・VIX・CHF・米国債）から
    地政学リスク温度を 0-100 で定量化
  - Google News RSS から地政学ニュース抽出
  - （任意）Gemini で為替目線の要約

すべて無料データ・APIキー不要（Gemini はあれば使用）
"""

import os
import warnings
from datetime import datetime, timezone, timedelta

import requests

warnings.filterwarnings("ignore")

JST = timezone(timedelta(hours=9))


def _fmt_date_ja(date_str: str) -> str:
    """FRED日付文字列 (YYYY-MM-DD or YYYY-MM) を日本語形式 YYYY年M月 に変換"""
    try:
        s = str(date_str or "").strip()[:7]   # "YYYY-MM"
        y, m = s.split("-")
        return f"{y}年{int(m)}月"
    except Exception:
        return str(date_str)


# ─────────────────────────────────────────────────────────────────────────────
# 1. マクロ経済サマリー
# ─────────────────────────────────────────────────────────────────────────────

def build_macro_summary(premium: dict | None = None, data: dict | None = None) -> str:
    """
    マクロ経済サマリーの Telegram テキストを組み立てる
    premium: src.fx_data_premium.fetch_all_premium() の戻り値
    data:    src.fx_visual_report.fetch_all_data() の戻り値（米10年金利等）
    """
    premium = premium or {}
    data    = data or {}
    fred    = premium.get("fred", {})
    tc      = premium.get("treasury", {})
    fw      = premium.get("fedwatch", {})

    lines = ["🌐〰〰〰 *マクロ経済* 〰〰〰🌐", ""]

    # ── 米金融政策 ──
    ffr = fred.get("FEDFUNDS", {}).get("value")
    if ffr is None and fw:
        ffr = fw.get("current_ffr")
    if ffr is not None:
        lines.append(f"🏦 *米政策金利（FFR）*: `{ffr:.2f}%`")
        lines.append("　└ 米連邦準備制度（FRB）が設定する短期金利の誘導目標")

    # FedWatch 直近会合の利下げ確率
    if fw and fw.get("meetings"):
        m0   = fw["meetings"][0]
        cut0 = fw["cut_prob"][0]
        lines.append(f"　└ 次回FOMC会合（{m0}） 利下げ確率 *{cut0:.0f}%*")
        lines.append("　　└ FOMCは年8回開催される「米国の金利を決める会議」")

    # ── 物価・雇用 ──
    cpi    = fred.get("CPIAUCSL", {})
    unrate = fred.get("UNRATE", {})
    if unrate:
        lines.append(f"👷 *失業率*: `{unrate['value']:.1f}%`  （{_fmt_date_ja(unrate['date'])}時点）")
    if cpi:
        lines.append(f"📈 *消費者物価指数（CPI）*: `{cpi['value']:.1f}`  （{_fmt_date_ja(cpi['date'])}時点）")

    # ── 金利・日米金利差 ──
    us10y = data.get("^TNX", {}).get("latest")
    if us10y is None and tc:
        us10y = tc.get("10Y")
    jp10y = fred.get("IRLTLT01JPM156N", {}).get("value")

    if us10y is not None:
        lines.append("")
        lines.append(f"🇺🇸 *米国10年国債金利*: `{us10y:.3f}%`")
        lines.append("　└ 世界の「お金の流れ」の基準となる金利")
    if jp10y is not None and us10y is not None:
        lines.append(f"🇯🇵 *日本10年国債金利*: `{jp10y:.3f}%`")
        diff = us10y - jp10y
        direction = "円安方向" if diff >= 3.0 else "円安圧力やや低下" if diff >= 2.0 else "円高圧力"
        lines.append(f"📐 *日米金利差*: `{diff:.2f}%`  ← {direction}の主因")

    # ── 逆イールド判定 ──
    if tc and "3M" in tc and "10Y" in tc:
        spread = tc["10Y"] - tc["3M"]
        if spread < 0:
            lines.append(f"⚠️ *逆イールド発生中* （10年債ー3ヶ月 差={spread:+.2f}%） — 景気後退シグナル")
        else:
            lines.append(f"✅ イールドカーブ正常 （10年債ー3ヶ月 差={spread:+.2f}%）")

    # ── HYスプレッド（信用リスク）──
    hy = fred.get("BAMLH0A0HYM2", {})
    if hy:
        v = hy["value"]
        judge = "🟢 落ち着き" if v < 3.5 else "🟡 やや警戒" if v < 5 else "🔴 信用不安"
        lines.append(f"💳 *高利回り社債スプレッド*: `{v:.2f}%` {judge}")
        lines.append("　└ スプレッドが広がると「企業の信用不安」のサイン")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# 2. 地政学リスク温度（安全資産フローから定量化）
# ─────────────────────────────────────────────────────────────────────────────

def calc_geopolitical_risk(data: dict | None = None) -> dict:
    """
    安全資産フローから地政学リスク温度を 0-100 で算出
    要素: 金の上昇 / 原油の急変動 / VIX / 安全通貨CHF / 米国債への逃避
    Returns:
        {"score": int, "level": str, "emoji": str, "factors": [str, ...]}
    """
    data    = data or {}
    factors = []
    score   = 0.0

    # 金: 当日上昇でリスク回避
    gold_chg = data.get("GC=F", {}).get("chg")
    if gold_chg is not None:
        if gold_chg >= 1.5:
            score += 25; factors.append(f"🥇 金が急騰 {gold_chg:+.1f}%（質への逃避）")
        elif gold_chg >= 0.5:
            score += 12; factors.append(f"🥇 金が上昇 {gold_chg:+.1f}%")
        elif gold_chg <= -1.5:
            factors.append(f"🥇 金が急落 {gold_chg:+.1f}%（リスク選好）")

    # 原油: 急変動で供給不安（地政学の主因）
    oil_chg = data.get("CL=F", {}).get("chg")
    if oil_chg is not None:
        if abs(oil_chg) >= 3.0:
            score += 25; factors.append(f"🛢 原油が急変動 {oil_chg:+.1f}%（供給不安/中東リスク）")
        elif abs(oil_chg) >= 1.5:
            score += 12; factors.append(f"🛢 原油が変動 {oil_chg:+.1f}%")

    # VIX: 市場の恐怖
    vix     = data.get("^VIX", {}).get("latest")
    vix_chg = data.get("^VIX", {}).get("chg")
    if vix is not None:
        if vix >= 30:
            score += 30; factors.append(f"⚡ VIX={vix:.0f} 極度の警戒")
        elif vix >= 25:
            score += 20; factors.append(f"⚡ VIX={vix:.0f} 警戒水準")
        elif vix >= 20:
            score += 10; factors.append(f"⚡ VIX={vix:.0f} やや不安")
        if vix_chg is not None and vix_chg >= 8:
            score += 10; factors.append(f"⚡ VIX急騰 {vix_chg:+.0f}%")

    # 安全通貨 CHF の強さ（USDCHF下落 = CHF高 = リスクオフ）
    chf_chg = data.get("USDCHF=X", {}).get("chg")
    if chf_chg is not None and chf_chg <= -0.7:
        score += 10; factors.append("🇨🇭 スイスフラン買い（安全通貨需要）")

    # 米国債利回り低下 = 質への逃避
    us10y_chg = data.get("^TNX", {}).get("chg")
    if us10y_chg is not None and us10y_chg <= -2.0:
        score += 8; factors.append("🇺🇸 米国債買い（利回り低下=質への逃避）")

    score = int(min(100, max(0, score)))

    if score >= 70:
        level, emoji = "🔴 非常に高い", "🚨"
    elif score >= 45:
        level, emoji = "🟠 高い", "⚠️"
    elif score >= 25:
        level, emoji = "🟡 やや高い", "🔸"
    else:
        level, emoji = "🟢 落ち着き", "✅"

    if not factors:
        factors.append("特段の地政学的ストレスは検出されず")

    return {"score": score, "level": level, "emoji": emoji, "factors": factors}


# ─────────────────────────────────────────────────────────────────────────────
# 3. 地政学ニュース（Google News RSS）
# ─────────────────────────────────────────────────────────────────────────────

def fetch_geopolitical_news(max_items: int = 6) -> list:
    """
    Google News RSS から地政学関連ニュースの見出しを取得
    Returns: [{"title": str, "source": str}, ...]
    """
    try:
        import feedparser
    except ImportError:
        return []

    seen    = set()
    result  = []
    queries = [
        "地政学 OR 中東 OR イラン OR イスラエル OR ウクライナ",
        "台湾 OR 北朝鮮 OR 制裁 OR 為替介入 OR 原油 供給",
    ]
    for q in queries:
        try:
            url = (
                "https://news.google.com/rss/search?q="
                + requests.utils.quote(q)
                + "&hl=ja&gl=JP&ceid=JP:ja"
            )
            feed = feedparser.parse(url)
            for entry in feed.entries[:8]:
                title = entry.get("title", "").strip()
                if not title or title in seen:
                    continue
                seen.add(title)
                source = ""
                if " - " in title:
                    parts  = title.rsplit(" - ", 1)
                    title  = parts[0].strip()
                    source = parts[1].strip()
                result.append({"title": title[:60], "source": source[:20]})
                if len(result) >= max_items:
                    return result
        except Exception:
            pass
    return result


def build_geopolitics_summary(data: dict | None = None,
                              use_gemini: bool = True) -> str:
    """地政学リスクサマリーの Telegram テキストを組み立てる"""
    risk = calc_geopolitical_risk(data)
    news = fetch_geopolitical_news()

    bar_n = round(risk["score"] / 10)
    bar   = "█" * bar_n + "░" * (10 - bar_n)

    lines = [
        "🌍〰〰〰 *地政学リスク* 〰〰〰🌍",
        "",
        f"{risk['emoji']} *リスク温度*: {risk['level']}",
        f"`{bar}` {risk['score']}/100",
        "",
        "*📊 検出シグナル（安全資産フロー）*",
    ]
    for f in risk["factors"]:
        lines.append(f"  • {f}")

    if news:
        lines.append("")
        lines.append("*📰 注目の地政学ニュース*")
        for n in news:
            src = f" ({n['source']})" if n["source"] else ""
            lines.append(f"  🔹 {n['title']}{src}")

    if use_gemini and news:
        ai = _gemini_geopolitics_comment(risk, news)
        if ai:
            lines.append("")
            lines.append("*🤖 AI地政学コメント*")
            lines.append(ai)

    return "\n".join(lines)


def _gemini_geopolitics_comment(risk: dict, news: list) -> str:
    """Gemini で地政学ニュースを為替目線で要約（APIキーがあれば）"""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return ""
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
        headlines = "\n".join(f"- {n['title']}" for n in news)
        prompt = (
            "あなたはFX・マクロ専門アナリストです。以下の地政学ニュースの見出しと"
            f"現在の地政学リスク温度({risk['score']}/100)を踏まえ、"
            "為替（特にドル円・円）への影響を投資初心者にもわかるよう"
            "2〜3文の日本語で簡潔に解説してください。断定を避け、注意喚起の形で。\n\n"
            f"【ニュース見出し】\n{headlines}"
        )
        resp = model.generate_content(prompt)
        return (resp.text or "").strip()[:400]
    except Exception:
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# 4. 統合: マクロ + 地政学の2メッセージを返す
# ─────────────────────────────────────────────────────────────────────────────

def build_macro_geo_messages(data: dict | None = None,
                             premium: dict | None = None,
                             use_gemini: bool = True) -> list:
    """FX専用トークルームに追加送信する [マクロ, 地政学] の2メッセージを返す"""
    macro = build_macro_summary(premium, data)
    geo   = build_geopolitics_summary(data, use_gemini=use_gemini)
    return [macro, geo]
