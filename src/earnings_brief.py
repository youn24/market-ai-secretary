"""
決算ブリーフ（決算・IR開示PDFのAI要約）
TDnetウォッチャーが検知したウォッチリスト銘柄の決算・決算説明会・業績修正PDFを
ダウンロードし、Gemini が「中身」を初心者向けに3行要約する。

ポイント：
  - Gemini はPDFを直接読める（画像スライドの説明会資料もOK）→ 追加ライブラリ不要
  - 要約対象は投資家が中身を知りたい開示のみ（決算/説明会/業績・配当修正）に限定
  - 1日の要約件数を絞り、無料枠（1500回/日）に優しく

⚠️ AI要約は誤読の可能性あり。正確な数字は必ず原本PDFで確認すること。
"""
import os

import requests

from src.utils import setup_logger

logger = setup_logger("earnings_brief")

# 中身を要約する価値が高いカテゴリ（tdnet_watcher の category 名に対応）
_TARGET_CATEGORIES = {
    "決算", "決算説明会", "上方修正・増配", "下方修正・減配", "予想修正（要確認）",
}
_MAX_BRIEFS = 5          # 1回で要約する最大件数（トークン節約）
_MAX_PDF_BYTES = 18 * 1024 * 1024  # Gemini inlineの上限目安


def _summarize_pdf(pdf_url: str, name: str, title: str) -> str:
    """決算PDFをGeminiで3行要約。失敗時は空文字。"""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or not pdf_url:
        return ""
    try:
        r = requests.get(pdf_url, timeout=25,
                         headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200 or len(r.content) < 1000:
            return ""
        pdf_bytes = r.content
        if len(pdf_bytes) > _MAX_PDF_BYTES:
            logger.info(f"PDF大きすぎスキップ [{name}]: {len(pdf_bytes)//1024}KB")
            return ""

        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")

        prompt = f"""これは「{name}」の開示資料「{title}」のPDFです。
投資初心者にもわかるように、次の3点を各1行・合計3行で日本語要約してください。
専門用語は噛み砕き、PDFに書かれた具体的な数字（売上・利益・増減率など）を必ず引用してください。

1) 何の開示か（ひとことで）
2) 業績・数字のポイント（前年比や進捗率など具体的数値で）
3) 株価へのプラス材料／マイナス材料（どちらかを明示）

※PDFから読み取れない項目は「記載読み取れず」と正直に書く。誇張や憶測はしない。"""

        resp = model.generate_content([
            {"mime_type": "application/pdf", "data": pdf_bytes},
            prompt,
        ])
        return resp.text.strip()
    except Exception as e:
        logger.warning(f"PDF要約失敗 [{name}]: {e}")
        return ""


def run(tdnet_result: dict = None) -> dict:
    """TDnetの開示結果から決算系PDFを要約する"""
    if not tdnet_result or not tdnet_result.get("available"):
        return {"available": False, "reason": "対象開示なし"}

    # 要約対象を抽出（決算系 × PDFあり）
    targets = [
        d for d in tdnet_result.get("disclosures", [])
        if d.get("category") in _TARGET_CATEGORIES and d.get("pdf")
    ]
    # 重要度highを優先し、件数を絞る
    targets.sort(key=lambda d: 0 if d.get("importance") == "high" else 1)
    targets = targets[:_MAX_BRIEFS]

    if not targets:
        return {"available": False, "reason": "決算系PDFなし"}

    briefs = []
    for d in targets:
        summary = _summarize_pdf(d["pdf"], d.get("watch_name", d.get("name", "")), d["title"])
        if summary:
            briefs.append({
                "code": d["code"][:4],
                "name": d.get("watch_name", d.get("name", "")),
                "title": d["title"],
                "category": d.get("category", ""),
                "emoji": d.get("emoji", "📄"),
                "summary": summary,
                "pdf": d["pdf"],
            })

    if not briefs:
        return {"available": False, "reason": "要約生成できず"}

    result = {"available": True, "briefs": briefs, "count": len(briefs)}
    result["html"] = get_html(result)
    result["telegram_message"] = build_telegram_message(result)
    logger.info(f"✅ 決算ブリーフ: {len(briefs)}件要約")
    return result


def build_telegram_message(result: dict) -> str:
    if not result.get("available"):
        return ""
    lines = ["📑 *決算ブリーフ（AIが中身を要約）*", ""]
    for b in result["briefs"]:
        lines.append(f"{b['emoji']} *[{b['code']}] {b['name']}*")
        lines.append(f"_{b['title'][:50]}_")
        lines.append(b["summary"])
        lines.append("")
    lines.append("※AI要約です。正確な数字は原本でご確認を")
    return "\n".join(lines).strip()


def get_html(result: dict) -> str:
    if not result or not result.get("available"):
        return ""
    cards = ""
    for b in result["briefs"]:
        summary_html = b["summary"].replace("\n", "<br>")
        cards += f'''
<div style="background:#0f1623;border:1px solid #1e2d42;border-radius:12px;padding:14px;margin-bottom:10px;">
  <div style="font-size:0.78em;color:#7a8fa8;margin-bottom:2px;">{b['emoji']} {b['category']}</div>
  <div style="font-weight:700;font-size:0.92em;">[{b['code']}] {b['name']}</div>
  <div style="font-size:0.76em;color:#7a8fa8;margin:3px 0 8px;">
    <a href="{b['pdf']}" target="_blank" style="color:#7ec8ff;text-decoration:none;">{b['title']} 📄</a>
  </div>
  <div style="font-size:0.86em;line-height:1.8;color:#dde8ff;">{summary_html}</div>
</div>'''
    return f'''
<div>
  <div style="font-size:0.75em;color:#7a8fa8;margin-bottom:10px;">
    AIが決算・説明会PDFの中身を要約しました（{result['count']}件）。正確な数字は原本でご確認ください
  </div>
  {cards}
</div>'''


if __name__ == "__main__":
    # 直近のTDnet開示で単体テスト
    from src.tdnet_watcher import fetch_watchlist_disclosures, build_telegram_message as _t
    import sys
    date = sys.argv[1] if len(sys.argv) > 1 else None
    td = fetch_watchlist_disclosures(date_str=date)
    r = run(td)
    out = []
    if r.get("available"):
        for b in r["briefs"]:
            out.append(f"{b['emoji']} [{b['code']}] {b['name']} | {b['category']}")
            out.append(f"  {b['title']}")
            out.append(f"  {b['summary']}")
            out.append("")
    else:
        out.append(f"要約対象なし: {r.get('reason','')}")
    text = "\n".join(out)
    try:
        print(text)
    except UnicodeEncodeError:
        with open("eb_output.txt", "w", encoding="utf-8") as f:
            f.write(text)
        print("eb_output.txt に保存しました")
