"""
煽りニュース検出AI
市場ニュースの見出しの誇張度・煽り度を0-10でスコアリングする
"""
import os
import json
import logging
import re

logger = logging.getLogger(__name__)

# ルールベース判定用ワード
PANIC_WORDS = ["ショック", "暴落", "暴騰", "緊急", "今すぐ", "崩壊", "危機", "激震", "壊滅", "大暴落", "大暴騰"]
HYPE_WORDS  = ["必見", "絶対", "注目", "衝撃", "驚愕", "異常", "歴史的", "前代未聞"]


def _get_bias_label(score: float) -> str:
    if score >= 9:
        return "🚨 超煽り"
    elif score >= 6:
        return "🔥 煽り"
    elif score >= 4:
        return "⚠️ やや誇張"
    else:
        return "📰 平静"


def _rule_based_score(title: str) -> float:
    score = 0.0
    for word in PANIC_WORDS:
        if word in title:
            score += 2.0
    for word in HYPE_WORDS:
        if word in title:
            score += 1.5
    # 「！！」「？？」連続
    if re.search(r'[！!]{2,}', title) or re.search(r'[？?]{2,}', title):
        score += 1.0
    return min(score, 10.0)


def _rule_based_reason(title: str) -> str:
    hits = []
    for word in PANIC_WORDS:
        if word in title:
            hits.append(word)
    for word in HYPE_WORDS:
        if word in title:
            hits.append(word)
    if re.search(r'[！!]{2,}', title) or re.search(r'[？?]{2,}', title):
        hits.append("連続感嘆符")
    if hits:
        return f"煽りワード: {', '.join(hits[:3])}"
    return "客観的な表現"


def _analyze_with_gemini(titles: list) -> list:
    """Gemini APIで全見出しを1回のAPIコールでスコアリング"""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return []

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))

        numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles))
        prompt = f"""以下のニュース見出しそれぞれの「煽り・誇張度」を0〜10でスコアリングしてください。
10=最大の煽り、0=客観的事実のみ。
JSON配列で [{{"title": "...", "score": 数値, "reason": "30字以内の理由"}}] の形式で返してください。
他のテキストは一切含めず、JSON配列のみを返してください。

見出し一覧:
{numbered}"""

        response = model.generate_content(prompt)
        raw = response.text.strip()

        # ```json ... ``` などのコードブロックを除去
        raw = re.sub(r'^```[a-z]*\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        raw = raw.strip()

        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
        return []

    except Exception as e:
        logger.warning(f"Gemini煽り検出失敗: {e}")
        return []


def _build_html(items: list, top_biased: list, avg_score: float) -> str:
    """ダークテーマのHTMLセクションを生成"""

    # プログレスバー色
    pct = min(avg_score / 10.0 * 100, 100)
    if avg_score >= 6:
        bar_color = "#ff4444"
    elif avg_score >= 4:
        bar_color = "#ff8c00"
    else:
        bar_color = "#44bb44"

    # 上位3件カード
    top_html = ""
    for item in top_biased:
        score = item.get("bias_score", 0)
        label = item.get("bias_label", "")
        title = item.get("title", "")
        reason = item.get("reason", "")
        if score >= 9:
            card_color = "#cc0000"
            border_color = "#ff2222"
        elif score >= 6:
            card_color = "#8b3a00"
            border_color = "#ff6600"
        else:
            card_color = "#2a4a2a"
            border_color = "#44bb44"
        top_html += f"""
        <div style="background:{card_color};border-left:4px solid {border_color};padding:10px 14px;margin:8px 0;border-radius:4px;">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <span style="font-size:1.1em;font-weight:bold;color:#fff;">{label}</span>
            <span style="background:#333;padding:2px 8px;border-radius:12px;font-size:0.9em;color:#ffcc00;">スコア {score:.1f}</span>
          </div>
          <div style="margin-top:6px;color:#fff;font-size:0.95em;">{title}</div>
          <div style="margin-top:4px;color:#ccc;font-size:0.82em;">{reason}</div>
        </div>"""

    # 全件テーブル行
    rows_html = ""
    for item in items:
        score = item.get("bias_score", 0)
        label = item.get("bias_label", "")
        title = item.get("title", "")
        reason = item.get("reason", "")
        if score >= 6:
            row_style = "background:#3a1a00;"
            score_color = "#ff6600"
        elif score >= 4:
            row_style = "background:#2a2a00;"
            score_color = "#ffcc00"
        else:
            row_style = ""
            score_color = "#88cc88"
        rows_html += f"""
        <tr style="{row_style}">
          <td style="padding:6px 10px;color:{score_color};font-weight:bold;white-space:nowrap;">{score:.1f}</td>
          <td style="padding:6px 10px;white-space:nowrap;">{label}</td>
          <td style="padding:6px 10px;">{title}</td>
          <td style="padding:6px 10px;color:#aaa;font-size:0.85em;">{reason}</td>
        </tr>"""

    html = f"""
<div style="background:#1a1a2e;color:#e0e0e0;padding:20px;border-radius:10px;margin:20px 0;border:1px solid #333;">
  <h2 style="color:#fff;margin-top:0;border-bottom:2px solid #444;padding-bottom:10px;">
    🔍 ニュース客観度チェック
  </h2>

  <div style="margin-bottom:18px;">
    <div style="display:flex;justify-content:space-between;margin-bottom:6px;">
      <span style="color:#ccc;font-size:0.95em;">平均煽りスコア</span>
      <span style="color:#ffcc00;font-weight:bold;font-size:1.1em;">{avg_score:.1f} / 10</span>
    </div>
    <div style="background:#333;border-radius:6px;height:12px;overflow:hidden;">
      <div style="background:{bar_color};width:{pct:.1f}%;height:100%;border-radius:6px;transition:width 0.3s;"></div>
    </div>
  </div>

  {f'<h3 style="color:#ffcc00;margin-top:0;">🏆 煽り度トップ3</h3>{top_html}' if top_biased else ''}

  <h3 style="color:#ccc;margin-top:16px;">全件一覧</h3>
  <div style="overflow-x:auto;">
    <table style="width:100%;border-collapse:collapse;font-size:0.88em;">
      <thead>
        <tr style="background:#2a2a3e;color:#aaa;">
          <th style="padding:6px 10px;text-align:left;">スコア</th>
          <th style="padding:6px 10px;text-align:left;">判定</th>
          <th style="padding:6px 10px;text-align:left;">見出し</th>
          <th style="padding:6px 10px;text-align:left;">理由</th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>
  </div>
</div>"""
    return html


def analyze_news_bias(news: list) -> dict:
    """
    ニュース見出しの煽り度を分析する。

    Args:
        news: [{"title": str, "url": str, ...}, ...]

    Returns:
        {
          "available": bool,
          "items": [{"title", "bias_score", "bias_label", "reason"}],
          "top_biased": list,   # スコア上位3件
          "avg_score": float,
          "html": str,
        }
    """
    if not news:
        logger.info("ニュースリストが空のため煽り検出をスキップ")
        return {"available": False, "items": [], "top_biased": [], "avg_score": 0.0, "html": ""}

    try:
        titles = [item.get("title", "") for item in news if item.get("title")]

        if not titles:
            return {"available": False, "items": [], "top_biased": [], "avg_score": 0.0, "html": ""}

        # Gemini で一括スコアリング試行
        gemini_results = _analyze_with_gemini(titles)

        # Gemini結果をタイトルでマッピング
        gemini_map = {}
        if gemini_results:
            for g in gemini_results:
                t = g.get("title", "")
                if t:
                    gemini_map[t] = g

        items = []
        for title in titles:
            if title in gemini_map:
                g = gemini_map[title]
                score = float(g.get("score", 0))
                score = max(0.0, min(10.0, score))
                reason = str(g.get("reason", ""))[:50]
                source = "gemini"
            else:
                # ルールベースにフォールバック
                score = _rule_based_score(title)
                reason = _rule_based_reason(title)
                source = "rule"

            label = _get_bias_label(score)
            items.append({
                "title": title,
                "bias_score": round(score, 1),
                "bias_label": label,
                "reason": reason,
                "_source": source,
            })

        # スコア降順ソート
        sorted_items = sorted(items, key=lambda x: x["bias_score"], reverse=True)
        top_biased = sorted_items[:3]

        # 平均スコア
        avg_score = sum(i["bias_score"] for i in items) / len(items) if items else 0.0
        avg_score = round(avg_score, 2)

        html = _build_html(items, top_biased, avg_score)

        logger.info(f"煽り検出完了: {len(items)}件, 平均スコア={avg_score:.1f}")

        return {
            "available": True,
            "items": items,
            "top_biased": top_biased,
            "avg_score": avg_score,
            "html": html,
        }

    except Exception as e:
        logger.error(f"煽りニュース検出エラー: {e}", exc_info=True)
        return {"available": False, "items": [], "top_biased": [], "avg_score": 0.0, "html": ""}
