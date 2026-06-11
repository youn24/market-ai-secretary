"""
テーマ株人気ランキングモジュール
株探・minkabu スクレイピング + ニュース言及数 + ETF騰落率を統合して
「今週どのテーマが熱いか」をランキング化する
"""
import os
import re
import json
import time
import traceback
from pathlib import Path
from datetime import datetime, timedelta

from src.utils import setup_logger, get_jst_now

logger = setup_logger("theme_ranker")

# ── テーマ定義（キーワード + 代表銘柄コード） ──────────────────────────
THEMES = {
    "AI・生成AI":      {"keywords": ["AI", "人工知能", "生成AI", "ChatGPT", "LLM", "GPU", "エヌビディア"], "symbols": ["3778.T", "9984.T", "8035.T"]},
    "半導体":          {"keywords": ["半導体", "チップ", "ウェーハ", "ラピダス", "TSMC", "EUV"], "symbols": ["8035.T", "6857.T", "3436.T", "4063.T"]},
    "防衛・安全保障":   {"keywords": ["防衛", "安全保障", "防衛費", "ミサイル", "NATO", "自衛隊"], "symbols": ["7011.T", "7013.T", "7012.T"]},
    "インバウンド":     {"keywords": ["インバウンド", "訪日", "観光", "外国人旅行", "円安恩恵"], "symbols": ["9202.T", "4661.T", "9201.T"]},
    "EV・脱炭素":      {"keywords": ["EV", "電気自動車", "脱炭素", "再生可能エネルギー", "太陽光", "洋上風力"], "symbols": ["7203.T", "6752.T", "6971.T"]},
    "金利上昇・銀行":   {"keywords": ["利上げ", "金利上昇", "日銀", "政策金利", "メガバンク"], "symbols": ["8306.T", "8316.T", "8411.T"]},
    "商社・資源":       {"keywords": ["商社", "資源", "原油", "鉄鉱石", "バフェット", "LNG"], "symbols": ["8058.T", "8001.T", "8002.T"]},
    "海運・物流":       {"keywords": ["海運", "コンテナ", "フレート", "物流", "運賃"], "symbols": ["9104.T", "9101.T", "9107.T"]},
    "医療・ヘルスケア": {"keywords": ["医薬品", "バイオ", "医療機器", "創薬", "治験"], "symbols": ["4519.T", "4543.T", "4568.T"]},
    "ロボット・FA":    {"keywords": ["ロボット", "FA", "自動化", "工場自動化", "産業用ロボット"], "symbols": ["6954.T", "6506.T", "7013.T"]},
    "データセンター":   {"keywords": ["データセンター", "クラウド", "サーバー", "DC", "電力需要"], "symbols": ["3778.T", "9613.T", "9432.T"]},
    "円安メリット":     {"keywords": ["円安", "輸出株", "円安恩恵", "為替メリット"], "symbols": ["7203.T", "6981.T", "6762.T"]},
}

# テーマETF（騰落率参考用）
THEME_ETFS = {
    "半導体": "2244.T",          # グローバルX 半導体ETF
    "AI・生成AI": "2244.T",
    "銀行・金融": "1615.T",      # NEXT FUNDS 銀行(TOPIX-17)
    "EV・脱炭素": "2637.T",      # iShares 世界クリーンエネルギー
}


def _count_news_mentions(news: list) -> dict:
    """ニュース一覧からテーマ別言及数を集計"""
    counts = {theme: 0 for theme in THEMES}
    for item in news:
        text = (item.get("title", "") + " " + item.get("summary", "")).upper()
        for theme, meta in THEMES.items():
            for kw in meta["keywords"]:
                if kw.upper() in text:
                    counts[theme] += 1
                    break  # 1記事1カウント
    return counts


def _fetch_kabutan_themes() -> list:
    """株探テーマ人気ランキングをスクレイピング"""
    try:
        import requests
        from html.parser import HTMLParser

        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        url = "https://kabutan.jp/themes/"
        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = "utf-8"

        # テーマ名を抽出（シンプルな正規表現）
        themes_found = re.findall(r'<a[^>]*href="/themes/\?theme=\d+"[^>]*>([^<]+)</a>', resp.text)
        return [t.strip() for t in themes_found[:20] if t.strip()]
    except Exception as e:
        logger.warning(f"株探スクレイピング失敗: {e}")
        return []


def _fetch_minkabu_themes() -> list:
    """minkabu テーマランキングをスクレイピング"""
    try:
        import requests
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        url = "https://minkabu.jp/themes"
        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = "utf-8"

        themes_found = re.findall(r'class="[^"]*theme[^"]*"[^>]*>([ぁ-ん一-龯ァ-ヴA-Za-z0-9・\s]+)</[^>]+>', resp.text)
        cleaned = [t.strip() for t in themes_found if 2 <= len(t.strip()) <= 20]
        return list(dict.fromkeys(cleaned))[:20]  # 重複除去
    except Exception as e:
        logger.warning(f"minkabuスクレイピング失敗: {e}")
        return []


def _get_theme_performance(symbols: list, prices: dict = None) -> dict:
    """テーマ代表銘柄の騰落率を取得。prices辞書があれば優先使用（yfinance呼び出しを削減）"""
    perfs = []

    # prices辞書から取得を試みる
    if prices:
        for sym in symbols[:3]:
            entry = prices.get(sym)
            if entry and entry.get("change_pct") is not None:
                perfs.append(entry["change_pct"])
        if perfs:
            return {"avg_5d": sum(perfs) / len(perfs), "count": len(perfs)}

    # fallback: yfinance
    try:
        import yfinance as yf
        for sym in symbols[:3]:
            try:
                ticker = yf.Ticker(sym)
                hist = ticker.history(period="5d")
                if len(hist) >= 2:
                    chg = (hist["Close"].iloc[-1] / hist["Close"].iloc[0] - 1) * 100
                    perfs.append(chg)
            except Exception:
                pass
        if perfs:
            return {"avg_5d": sum(perfs) / len(perfs), "count": len(perfs)}
    except Exception:
        pass
    return {"avg_5d": 0, "count": 0}


def _gemini_theme_analysis(rankings: list, news: list) -> str:
    """Gemini でテーマ総評を生成"""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return ""
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")

        top5 = rankings[:5]
        ranking_text = "\n".join(
            f"{i+1}位 {r['theme']}（ニュース{r['news_count']}件, 5日騰落{r['perf_5d']:+.1f}%）"
            for i, r in enumerate(top5)
        )
        recent_news = "\n".join(f"・{n.get('title','')}" for n in news[:8])

        prompt = f"""以下はテーマ株人気ランキングと最近のニュースです。
投資初心者向けに今週のテーマ株市場を150字以内でわかりやすく解説してください。

【今週のテーマランキング（上位5位）】
{ranking_text}

【最近の注目ニュース】
{recent_news}

解説（150字以内）:"""

        resp = model.generate_content(prompt)
        return resp.text.strip()
    except Exception as e:
        logger.warning(f"Geminiテーマ分析失敗: {e}")
        return ""


def run(prices: dict = None, risk: dict = None, fear_greed: dict = None,
        news: list = None) -> dict:
    """テーマランキングをスコアリングして返す"""
    news = news or []

    # 1. ニュース言及数カウント
    mention_counts = _count_news_mentions(news)

    # 2. 株探・minkabuからテーマ名を取得（スクレイピング）
    kabutan_themes = _fetch_kabutan_themes()
    minkabu_themes = _fetch_minkabu_themes()
    external_themes = set(kabutan_themes + minkabu_themes)

    # 3. テーマ別スコアリング
    rankings = []
    for theme, meta in THEMES.items():
        news_cnt = mention_counts.get(theme, 0)

        # 外部ランキングに出ているか
        external_bonus = 0
        for ext in external_themes:
            if any(kw in ext for kw in meta["keywords"][:2]):
                external_bonus = 3
                break

        # 代表銘柄の5日騰落率（pricesがあればyfinance呼び出し不要）
        perf = _get_theme_performance(meta["symbols"], prices)
        perf_5d = perf.get("avg_5d", 0)

        # 総合スコア（ニュース×2 + 外部ボーナス + 騰落率×0.5）
        score = news_cnt * 2 + external_bonus + max(perf_5d * 0.5, 0)

        rankings.append({
            "theme":       theme,
            "score":       round(score, 1),
            "news_count":  news_cnt,
            "perf_5d":     round(perf_5d, 2),
            "symbols":     meta["symbols"][:3],
            "external_hit": external_bonus > 0,
        })
        time.sleep(0.1)  # yfinance レート制限

    # 4. スコア降順でソート
    rankings.sort(key=lambda x: x["score"], reverse=True)

    # 5. Gemini 総評
    ai_comment = _gemini_theme_analysis(rankings, news)

    # 6. HTML生成
    html = _build_html(rankings[:10], kabutan_themes[:5], ai_comment)

    # 7. Telegram メッセージ
    tg = f"🔥 テーマ株ランキング（{get_jst_now().strftime('%m/%d')}）\n\n"
    for i, r in enumerate(rankings[:5]):
        medal = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][i]
        arrow = "▲" if r["perf_5d"] > 0 else "▼" if r["perf_5d"] < 0 else "➡"
        tg += f"{medal} {r['theme']}  {arrow}{abs(r['perf_5d']):.1f}%  ニュース{r['news_count']}件\n"
    if ai_comment:
        tg += f"\n💡 {ai_comment}"

    return {
        "available":        True,
        "rankings":         rankings,
        "top5":             rankings[:5],
        "kabutan_trending": kabutan_themes[:10],
        "ai_comment":       ai_comment,
        "html":             html,
        "telegram_message": tg,
    }


def _build_html(rankings: list, trending: list, ai_comment: str) -> str:
    rows = ""
    medals = ["🥇", "🥈", "🥉"] + [""] * 10
    for i, r in enumerate(rankings):
        perf = r["perf_5d"]
        pc = "#3fb950" if perf > 0 else "#f44336" if perf < 0 else "#8899aa"
        arrow = "▲" if perf > 0 else "▼" if perf < 0 else "➡"
        ext = "🔥" if r.get("external_hit") else ""
        rows += f'''
<div style="display:flex;align-items:center;gap:10px;padding:10px 0;
            border-bottom:1px solid #1e2d42;">
  <div style="width:28px;text-align:center;font-size:1.1em;">{medals[i] or str(i+1)}</div>
  <div style="flex:1;">
    <div style="font-weight:700;font-size:0.9em;">{r["theme"]} {ext}</div>
    <div style="font-size:0.72em;color:#7a8fa8;">ニュース{r["news_count"]}件</div>
  </div>
  <div style="text-align:right;">
    <div style="color:{pc};font-weight:700;font-size:0.9em;">{arrow}{abs(perf):.1f}%</div>
    <div style="font-size:0.68em;color:#7a8fa8;">5日騰落</div>
  </div>
</div>'''

    ai_block = f'<div style="background:#070f1f;border:1px solid #00d4ff33;border-radius:10px;padding:12px;margin-top:12px;font-size:0.85em;line-height:1.7;color:#dde8ff;">💡 {ai_comment}</div>' if ai_comment else ""

    trending_block = ""
    if trending:
        tags = "".join(f'<span style="background:#1e2d42;border-radius:20px;padding:3px 10px;font-size:0.72em;margin:3px 2px;display:inline-block;">{t}</span>' for t in trending[:8])
        trending_block = f'<div style="margin-top:10px;"><div style="color:#7a8fa8;font-size:0.72em;margin-bottom:6px;">📌 株探 トレンドテーマ</div>{tags}</div>'

    return f'<div style="background:#0f1623;border:1px solid #1e2d42;border-radius:14px;padding:16px;">{rows}{trending_block}{ai_block}</div>'
