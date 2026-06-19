"""
note.com 有料記事 自動生成モジュール
市場AI秘書のデータから publication-ready な Markdown 記事を毎朝自動生成する
"""
import os
from datetime import date as _date
from src.utils import setup_logger, get_today_str, get_dirs

logger = setup_logger("note_article")


# ── ヘルパー ────────────────────────────────────────────────────

def _fmt(prices: dict, sym: str, unit: str = "") -> tuple[str, str]:
    """(値文字列, 変化率文字列) のタプルを返す"""
    d   = prices.get(sym, {})
    v   = d.get("latest")
    chg = d.get("change_pct")
    if v is None:
        return "―", "―"
    val_s = f"{v:,.2f}{unit}"
    if chg is None:
        return val_s, "―"
    arrow = "▲" if chg >= 0 else "▼"
    return val_s, f"{arrow} {abs(chg):.2f}%"


def _mood(score: float) -> tuple[str, str]:
    if   score >= 2:    return "🟢", "強気！上昇ムード"
    elif score >= 0.5:  return "🟢", "やや強気"
    elif score >= -0.5: return "🟡", "中立・様子見"
    elif score >= -2:   return "🔴", "やや弱気・注意"
    else:               return "🔴", "弱気！慎重に"


# ── Gemini でエグゼクティブサマリーを生成 ────────────────────────

def _generate_summary(prices, risk, fear_greed, ai_summary) -> str:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return _fallback_summary(risk, fear_greed)
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")

        score     = risk.get("score", 0)
        sentiment = risk.get("sentiment", "不明")
        fg        = fear_greed.get("score", 50)
        bull      = (ai_summary.get("bull_view") or "")[:200]
        bear      = (ai_summary.get("bear_view") or "")[:200]

        nk_v, nk_c = _fmt(prices, "^N225", "円")
        sp_v, sp_c = _fmt(prices, "^GSPC")
        fx_v, fx_c = _fmt(prices, "USDJPY=X", "円")
        vix_v, _   = _fmt(prices, "^VIX")

        prompt = f"""以下の市場データをもとに、今日の相場の「エグゼクティブサマリー」を日本語で3〜4文書いてください。
投資初心者にもわかりやすく、でも中級者も納得できる内容にしてください。
断定表現（「必ず上がる」など）は使わず、推測は「〜の可能性」「〜が予想される」と表現してください。

【市場データ】
地合い: {sentiment}（スコア: {score:+.2f}）
日経平均: {nk_v} ({nk_c})
S&P500: {sp_v} ({sp_c})
ドル円: {fx_v} ({fx_c})
VIX: {vix_v}
Fear&Greed: {fg}

【AI議論より】
強気派: {bull}
弱気派: {bear}

サマリー（3〜4文・200字以内・日本語）:"""

        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        logger.warning(f"Gemini サマリー生成失敗: {e}")
        return _fallback_summary(risk, fear_greed)


def _fallback_summary(risk, fear_greed) -> str:
    score     = risk.get("score", 0)
    sentiment = risk.get("sentiment", "不明")
    fg        = fear_greed.get("score", 50)
    fg_label  = fear_greed.get("rating_ja", "中立")
    if score >= 1:
        tone = "上昇優位の地合い"
    elif score >= -1:
        tone = "方向感のない横ばい展開"
    else:
        tone = "下落圧力が優勢"
    return (
        f"本日の市場は**{sentiment}**（リスクスコア: {score:+.1f}）で、{tone}と判断されます。"
        f"投資家心理を示すFear＆Greed指数は**{fg:.0f}（{fg_label}）**で推移しており、"
        f"市場参加者のセンチメントは引き続き注目が必要な状況です。"
        f"以下のAI分析と市場データを参考に、今日の相場展望をご確認ください。"
    )


# ── セクション生成ヘルパー ─────────────────────────────────────

def _price_table(prices) -> str:
    rows = [
        ("^N225",    "🇯🇵 日経平均", "円"),
        ("^GSPC",    "🇺🇸 S&P500",   ""),
        ("^IXIC",    "🇺🇸 NASDAQ",   ""),
        ("^DJI",     "🇺🇸 ダウ",     ""),
        ("USDJPY=X", "💵 ドル円",     "円"),
        ("^TNX",     "📊 米10年金利", "%"),
        ("GC=F",     "🥇 金",        "$"),
        ("CL=F",     "🛢 WTI原油",   "$"),
        ("BTC-USD",  "₿ Bitcoin",    "$"),
        ("^VIX",     "⚡ VIX",       ""),
    ]
    lines = ["| 指標 | 値 | 前日比 |", "|------|-----|--------|"]
    for sym, name, unit in rows:
        val, chg = _fmt(prices, sym, unit)
        lines.append(f"| {name} | {val} | {chg} |")
    return "\n".join(lines)


def _news_section(news, max_per_imp=4) -> str:
    if not news:
        return "*ニュースデータなし*"
    sorted_news = sorted(
        news, key=lambda x: {"A": 0, "B": 1, "C": 2}.get(x.get("importance", "C"), 2)
    )
    imp_label = {
        "A": "### 🔴 重要度A — 要注目",
        "B": "### 🟡 重要度B — 注目",
        "C": "### ⚪ 重要度C — 参考",
    }
    grouped: dict[str, list] = {}
    for item in sorted_news:
        imp = item.get("importance", "C")
        grouped.setdefault(imp, [])
        if len(grouped[imp]) < max_per_imp:
            grouped[imp].append(item)

    out = []
    for imp in ["A", "B", "C"]:
        items = grouped.get(imp, [])
        if not items:
            continue
        out.append(imp_label[imp])
        for item in items:
            title  = item.get("title", "")
            source = item.get("source", "")
            pub    = (item.get("published_jst") or "")[:10]
            out.append(f"- **{title}**  \n  *{source}・{pub}*")
    return "\n\n".join(out)


def _scenario_section(scenario) -> str:
    if not scenario or not scenario.get("available"):
        return "*シナリオデータなし（Gemini API設定後に有効化されます）*"
    bull     = scenario.get("bull", {})
    base     = scenario.get("base", {})
    bear     = scenario.get("bear", {})
    top_risk = scenario.get("top_risk", "")
    lines = []
    if bull.get("text"):
        lines.append(f"### 🟢 楽観シナリオ（確率 {bull.get('prob','?')}%）\n\n{bull['text']}")
    if base.get("text"):
        lines.append(f"### 🟡 基本シナリオ（確率 {base.get('prob','?')}%）\n\n{base['text']}")
    if bear.get("text"):
        lines.append(f"### 🔴 悲観シナリオ（確率 {bear.get('prob','?')}%）\n\n{bear['text']}")
    if top_risk:
        lines.append(f"### ⚡ 最注目リスク\n\n{top_risk}")
    return "\n\n".join(lines) if lines else "*シナリオデータなし*"


def _technical_section(technical) -> str:
    if not technical or not technical.get("available"):
        return "*テクニカルデータなし*"
    comment = technical.get("ai_comment", "")
    rsi     = technical.get("rsi")
    lines   = []
    if comment:
        lines.append(comment)
    if rsi is not None:
        rsi_label = "買われ過ぎ圏（70超）" if rsi > 70 else "売られ過ぎ圏（30未満）" if rsi < 30 else "中立圏"
        lines.append(f"\n**RSI: {rsi:.1f}**（{rsi_label}）")
    return "\n".join(lines) if lines else "*テクニカルデータなし*"


def _prediction_section(prediction_tracker) -> str:
    if not prediction_tracker or not prediction_tracker.get("available"):
        return "*予測データ蓄積中（3件以上で表示開始）*"
    today_pred = prediction_tracker.get("today_prediction", {})
    stats      = prediction_tracker.get("stats", {})
    r10        = stats.get("10d", {})
    rate       = r10.get("rate")
    lines      = []

    if today_pred:
        direction = today_pred.get("direction", "neutral")
        dir_label = {
            "bull":    "📈 強気（上昇期待）",
            "bear":    "📉 弱気（下落警戒）",
            "neutral": "➡️ 中立（横ばい予想）",
        }.get(direction, "")
        lines.append(f"**今日のAI予測: {dir_label}**")
        lines.append("*翌日の実際の値動きと照合して精度を自動記録しています*")

    if rate is not None:
        correct = r10.get("correct", 0)
        total   = r10.get("total", 0)
        filled  = round(rate / 10)
        bar     = "█" * filled + "░" * (10 - filled)
        grade   = "🎯 優秀" if rate >= 65 else "🔶 普通" if rate >= 50 else "⚠️ 改善中"
        lines.append(f"\n**直近10日の予測正解率: {rate:.0f}%** {grade}  \n`{bar}` （{correct}/{total}日正解）")

    return "\n\n".join(lines) if lines else "*予測データなし*"


# ── メイン記事生成 ─────────────────────────────────────────────

def build_article(
    prices=None, news=None, risk=None, fear_greed=None,
    ai_summary=None, scenario=None, technical=None,
    prediction_tracker=None, report_paths=None,
) -> str:
    """note.com向け有料記事 Markdown を組み立てる"""
    prices             = prices or {}
    news               = news or []
    risk               = risk or {"score": 0, "sentiment": "不明"}
    fear_greed         = fear_greed or {}
    ai_summary         = ai_summary or {}
    scenario           = scenario or {}
    technical          = technical or {}
    prediction_tracker = prediction_tracker or {}
    report_paths       = report_paths or {}

    today      = get_today_str()
    weekday    = ["月", "火", "水", "木", "金", "土", "日"][_date.today().weekday()]
    score      = risk.get("score", 0)
    tl, mood   = _mood(score)
    score_s    = f"+{score:.1f}" if score >= 0 else f"{score:.1f}"
    fg_score   = fear_greed.get("score") or 50
    fg_label   = fear_greed.get("rating_ja", "中立")
    fg_filled  = round(fg_score / 10)
    fg_bar     = "█" * fg_filled + "░" * (10 - fg_filled)
    report_url = report_paths.get("url", "")

    # Gemini でサマリー生成
    logger.info("note記事: エグゼクティブサマリー生成中...")
    exec_summary = _generate_summary(prices, risk, fear_greed, ai_summary)

    # AI 3視点
    bull_text = ai_summary.get("bull_view") or "*データなし（AI議論モジュールが必要です）*"
    bear_text = ai_summary.get("bear_view") or "*データなし*"
    neut_text = ai_summary.get("neutral_view") or "*データなし*"

    article = f"""# 📊【市場AI秘書】{today}（{weekday}）｜今日の相場レポート

> {tl} **今日の判定：{mood}** ［スコア: {score_s}］

---

## ⚡ 今日のサマリー（1分で読める）

{exec_summary}

---

## 📈 主要市場データ

{_price_table(prices)}

---

## 😱 市場センチメント

| 指標 | 値 | バー |
|------|-----|------|
| Fear & Greed | {fg_score:.0f}（{fg_label}） | `{fg_bar}` |
| リスクスコア | {score_s} | {tl} {mood} |

> Fear & Greed指数は0〜100で投資家心理を示します。
> 0＝極度の恐怖 ／ 50＝中立 ／ 100＝極度の強欲

---

## 🤖 AI 3視点分析

3つのAI視点から今日の相場を多角的に分析しています。

### 📈 強気派の見方

{bull_text}

### 📉 弱気派の見方

{bear_text}

### ⚖️ AIの総合判断

{neut_text}

---

## 📰 今日の注目ニュース

{_news_section(news)}

---

## 🎭 3シナリオ分析

{_scenario_section(scenario)}

---

## 📐 テクニカル分析のポイント

{_technical_section(technical)}

---

## 🔮 今日のAI予測

{_prediction_section(prediction_tracker)}

---

## 📱 詳細レポート（インタラクティブチャート版）

チャート・相関分析・セクター分析など、より詳しいビジュアルレポートはこちら：

{report_url if report_url else "（URLは別途お知らせします）"}

---

*※本記事はAIが自動生成した市場分析レポートです。投資判断は必ずご自身でお願いします。*
"""
    return article.strip()


# ── エントリーポイント ────────────────────────────────────────

def run(
    prices=None, news=None, risk=None, fear_greed=None,
    ai_summary=None, scenario=None, technical=None,
    prediction_tracker=None, report_paths=None,
) -> dict:
    """note記事を生成してファイルに保存する"""
    result = {"available": False, "content": "", "path": ""}
    try:
        today    = get_today_str()
        dirs     = get_dirs()
        article  = build_article(
            prices=prices, news=news, risk=risk, fear_greed=fear_greed,
            ai_summary=ai_summary, scenario=scenario, technical=technical,
            prediction_tracker=prediction_tracker, report_paths=report_paths,
        )
        out_path = dirs["reports"] / f"{today}_note_article.md"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(article)
        logger.info(f"✅ note記事生成完了: {out_path}")
        result["available"] = True
        result["content"]   = article
        result["path"]      = str(out_path)
    except Exception as e:
        logger.error(f"note記事生成エラー: {e}")
    return result
