"""
材料分析AI（デイトレーダーの「材料評価の頭の中」を再現）

プロのトレーダーが材料（適時開示・決算・業績修正）を見たときに頭の中で走る
評価プロセスを、Geminiで自動化する。単なる要約ではなく「今日のデイトレで
資金が入るか」まで踏み込んで、反証可能な仮説を立てる。

評価の5軸：
  ① 何の材料か        ② 業績に効くか        ③ 一時的か継続的か
  ④ すでに織り込み済みか ⑤ 今日資金が入るか

材料の質の見極め：
  売上増？利益率改善？一時益？来期も強い？市場予想より上？すでに上昇済み？

出力（材料ごと）：
  仮説（例: 上方修正＋増配で短期資金が入りやすく、寄り後も買い継続のはず）
  注意（例: 寄り前気配が高すぎると寄り天）
  失敗ライン（例: VWAPを明確に割ったら仮説アウト）

対象：注目銘柄（watchlist）の開示 ＋ 市場全体の主要材料（上方修正・増配/自社株買い/M&A）。
タイミング：朝7:30（寄り付き前）。ライブのVWAP監視はせず、「見るべきライン」を提示する。

⚠️ AIの仮説であり、株価を保証するものではない。最終判断はご自身で。
"""
import os
import json
import re
import time

import requests

from src.utils import setup_logger

logger = setup_logger("catalyst_analyzer")

_MAX_CATALYSTS = 7          # 1回で分析する最大材料数（Gemini無料枠に優しく）
_MAX_PDF_READS = 3          # PDF直読みの上限（トークン節約）
_MAX_PDF_BYTES = 18 * 1024 * 1024

# デイトレ妙味のランク表示
_APPEAL_RANK = {"高": 0, "中": 1, "低": 2, "": 3}
_APPEAL_COLOR = {"高": "#3fb950", "中": "#d29922", "低": "#7a8fa8"}


# ────────────────────────────────────────────────────────────────
# 株価の「織り込み」を判定するための直近の値動き（yfinance）
# ────────────────────────────────────────────────────────────────
def _price_context(code: str) -> dict:
    """銘柄コードの直近1ヶ月の値動きを取得（織り込み判定の材料）。失敗時 空dict。"""
    try:
        import yfinance as yf
        sym = f"{str(code).split('.')[0]}.T"
        h = yf.Ticker(sym).history(period="1mo")
        if len(h) < 5:
            return {}
        last = float(h["Close"].iloc[-1])
        m1   = float(h["Close"].iloc[0])
        hi   = float(h["High"].max())
        chg_1m = round((last / m1 - 1) * 100, 1)
        from_high = round((last / hi - 1) * 100, 1)   # 直近高値からの距離（0に近い=高値圏）
        return {"close": round(last), "chg_1m": chg_1m, "from_high": from_high}
    except Exception:
        return {}


def _price_phrase(ctx: dict) -> str:
    """価格コンテキストを日本語の一文に（プロンプト用）"""
    if not ctx:
        return "直近の株価データは取得できず（織り込み度は開示内容から推定）"
    parts = [f"現在値 約{ctx['close']:,}円"]
    if ctx.get("chg_1m") is not None:
        trend = "上昇" if ctx["chg_1m"] > 0 else "下落"
        parts.append(f"直近1ヶ月は{ctx['chg_1m']:+.1f}%（{trend}）")
    if ctx.get("from_high") is not None:
        if ctx["from_high"] >= -3:
            parts.append("直近高値圏（すでに買われている可能性）")
        elif ctx["from_high"] <= -15:
            parts.append("直近高値から大きく下落（出遅れ・押し目の可能性）")
        else:
            parts.append(f"直近高値から{ctx['from_high']:.0f}%")
    return "、".join(parts)


# ────────────────────────────────────────────────────────────────
# Gemini で材料を5軸評価＋仮説生成（JSON出力）
# ────────────────────────────────────────────────────────────────
_PROMPT = """あなたは日本株の短期売買に長けたプロのトレーダーです。
以下の「材料（適時開示）」を、デイトレ目線で評価してください。要約ではなく、今日の寄り付き後に
資金が入って買いが続くかどうかを、根拠とともに見極めるのが仕事です。

# 銘柄
コード: {code}
銘柄名: {name}
材料カテゴリ: {category}
開示タイトル: {title}

# 株価の状況（織り込み判定の参考）
{price_phrase}

# 開示の中身（わかっている場合）
{body}

# あなたのタスク
次の5つの軸で評価し、最後にデイトレの仮説を立ててください。専門用語は噛み砕き、
わからない点は正直に「要確認」と書く（憶測で埋めない）。必ず下記のJSONだけを出力すること。

{{
  "catalyst_type": "何の材料か（例: 上方修正＋増配 / 自社株買い / 大型受注）。20字以内",
  "earnings_impact": "業績に効くか。売上増か利益率改善か、規模感を一言（30字以内）",
  "temp_or_cont": "一時的か継続的か（例: 一時益で単発 / 本業の伸びで継続）。25字以内",
  "priced_in": "すでに株価に織り込まれていないか。直近の値動きを踏まえて（30字以内）",
  "money_in_today": "高 / 中 / 低 のいずれか1つだけ（今日デイトレ資金が入りそうか）",
  "hypothesis": "仮説を1文で（例: 上方修正＋増配で短期資金が入りやすく、寄り後も買い継続のはず）。50字以内",
  "watch_point": "注意点を1文で（例: 寄り前気配が高すぎると寄り天）。40字以内",
  "fail_line": "仮説が崩れる失敗ライン（例: VWAPを明確に割ったら撤退 / 寄り高値を超えられず失速なら見送り）。40字以内"
}}"""


def _extract_json(text: str) -> dict:
    """Geminiの返答からJSONオブジェクトを取り出す"""
    if not text:
        return {}
    # ```json ... ``` を除去
    text = re.sub(r"```(?:json)?|```", "", text).strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:
        # 末尾カンマなどを軽く補正
        s = re.sub(r",(\s*[}\]])", r"\1", m.group(0))
        try:
            return json.loads(s)
        except Exception:
            return {}


def _read_pdf_bytes(pdf_url: str):
    try:
        r = requests.get(pdf_url, timeout=25, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200 and 1000 < len(r.content) <= _MAX_PDF_BYTES:
            return r.content
    except Exception:
        pass
    return None


def _analyze_one(model, cat: dict, price_phrase: str, pdf_budget: list) -> dict:
    """1材料をGeminiで5軸評価。pdf_budget は残りPDF読み込み回数を入れた可変リスト[int]。"""
    body = cat.get("brief_summary", "")
    parts = [_PROMPT.format(
        code=cat["code"], name=cat["name"], category=cat["category"],
        title=cat["title"], price_phrase=price_phrase,
        body=body or "（タイトルとカテゴリから判断してください）",
    )]

    # 中身の要約がなく、PDFがあり、予算が残っていればPDFを直読みさせる
    if not body and cat.get("pdf") and pdf_budget[0] > 0:
        pdf_bytes = _read_pdf_bytes(cat["pdf"])
        if pdf_bytes:
            pdf_budget[0] -= 1
            parts = [{"mime_type": "application/pdf", "data": pdf_bytes}, parts[0]]

    try:
        resp = model.generate_content(parts)
        data = _extract_json(resp.text)
    except Exception as e:
        logger.warning(f"材料分析失敗 [{cat['name']}]: {e}")
        return {}
    return data


def run(prices: dict = None, risk: dict = None, fear_greed: dict = None,
        tdnet: dict = None, earnings_brief: dict = None) -> dict:
    """注目銘柄＋市場の主要材料を集めて、5軸評価＋デイトレ仮説を生成する"""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return {"available": False, "reason": "GEMINI_API_KEY未設定"}

    # ── 1. 分析対象の材料を集める ──────────────────────────────
    catalysts = []
    seen = set()

    # (a) 注目銘柄（watchlist）の開示 ＝ 最優先
    for d in (tdnet or {}).get("disclosures", []):
        if d.get("importance") == "low":
            continue
        code4 = d["code"][:4]
        key = (code4, d.get("category"))
        if key in seen:
            continue
        seen.add(key)
        catalysts.append({
            "code": code4,
            "name": d.get("watch_name") or d.get("name", ""),
            "category": d.get("category", "開示"),
            "title": d.get("title", ""),
            "emoji": d.get("emoji", "📄"),
            "pdf": d.get("pdf", ""),
            "is_watch": True,
        })

    # 決算ブリーフの要約を材料に紐付け（PDF再読み込みを避ける）
    brief_map = {}
    for b in (earnings_brief or {}).get("briefs", []):
        brief_map[(b.get("code"), b.get("category"))] = b.get("summary", "")
    for c in catalysts:
        c["brief_summary"] = brief_map.get((c["code"], c["category"]), "")

    # (b) 市場全体の主要材料（watchlist以外の上方修正・増配/自社株買い/M&A）
    try:
        from src.tdnet_watcher import fetch_market_catalysts
        for m in fetch_market_catalysts(limit=6):
            code4 = m["code"][:4]
            key = (code4, m.get("category"))
            if key in seen:
                continue
            seen.add(key)
            catalysts.append({
                "code": code4,
                "name": m.get("name", ""),
                "category": m.get("category", "材料"),
                "title": m.get("title", ""),
                "emoji": m.get("emoji", "🔥"),
                "pdf": m.get("pdf", ""),
                "is_watch": False,
                "brief_summary": "",
            })
    except Exception as e:
        logger.debug(f"市場材料の取得スキップ: {e}")

    if not catalysts:
        return {"available": False, "reason": "分析対象の材料なし"}

    # watchlist優先で件数を絞る
    catalysts.sort(key=lambda c: 0 if c["is_watch"] else 1)
    catalysts = catalysts[:_MAX_CATALYSTS]

    # ── 2. Gemini で1件ずつ評価 ────────────────────────────────
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))

    pdf_budget = [_MAX_PDF_READS]
    analyzed = []
    for cat in catalysts:
        ctx = _price_context(cat["code"])
        data = _analyze_one(model, cat, _price_phrase(ctx), pdf_budget)
        if not data or not data.get("hypothesis"):
            continue
        appeal = (data.get("money_in_today") or "").strip()[:1]
        if appeal not in ("高", "中", "低"):
            appeal = "中"
        analyzed.append({
            **cat,
            "price_ctx": ctx,
            "catalyst_type": data.get("catalyst_type", cat["category"]),
            "earnings_impact": data.get("earnings_impact", ""),
            "temp_or_cont": data.get("temp_or_cont", ""),
            "priced_in": data.get("priced_in", ""),
            "appeal": appeal,
            "hypothesis": data.get("hypothesis", ""),
            "watch_point": data.get("watch_point", ""),
            "fail_line": data.get("fail_line", ""),
        })
        time.sleep(0.3)

    if not analyzed:
        return {"available": False, "reason": "仮説生成できず"}

    # デイトレ妙味の高い順
    analyzed.sort(key=lambda x: _APPEAL_RANK.get(x["appeal"], 3))

    result = {
        "available": True,
        "count": len(analyzed),
        "catalysts": analyzed,
        "high_count": sum(1 for x in analyzed if x["appeal"] == "高"),
    }
    result["telegram_message"] = build_telegram_message(result)
    result["html"] = get_html(result)
    logger.info(f"✅ 材料分析: {len(analyzed)}件（妙味高 {result['high_count']}件）")
    return result


def build_telegram_message(result: dict) -> str:
    if not result.get("available"):
        return ""
    cats = result["catalysts"]
    high = result.get("high_count", 0)

    # 1行目＝通知バー。妙味「高」の筆頭材料を出す
    top = cats[0]
    head = f"🎯 材料分析：{top['name']}〔{top['catalyst_type']}〕資金妙味{top['appeal']}"

    lines = [head, "",
             f"プロ目線で {result['count']} 材料を評価（資金が入りそう＝妙味）", ""]
    for c in cats:
        mark = {"高": "🟢", "中": "🟡", "低": "⚪"}.get(c["appeal"], "⚪")
        tag = "" if c["is_watch"] else "（市場全体）"
        lines.append(f"{mark} *[{c['code']}] {c['name']}* {tag}")
        lines.append(f"　{c['emoji']} {c['catalyst_type']}")
        lines.append(f"　💡 仮説：{c['hypothesis']}")
        if c.get("watch_point"):
            lines.append(f"　⚠️ 注意：{c['watch_point']}")
        if c.get("fail_line"):
            lines.append(f"　🛑 失敗ライン：{c['fail_line']}")
        lines.append("")
    lines.append("※AIの仮説です。寄り付き後の値動きで必ず検証を")
    return "\n".join(lines).strip()


def get_html(result: dict) -> str:
    if not result or not result.get("available"):
        return ""
    cards = ""
    for c in result["catalysts"]:
        col = _APPEAL_COLOR.get(c["appeal"], "#7a8fa8")
        tag = '<span style="font-size:0.7em;color:#7a8fa8;">注目銘柄</span>' if c["is_watch"] \
              else '<span style="font-size:0.7em;color:#d29922;">市場全体</span>'
        ctx = c.get("price_ctx") or {}
        ctx_html = ""
        if ctx.get("chg_1m") is not None:
            cc = "#3fb950" if ctx["chg_1m"] >= 0 else "#f85149"
            ctx_html = f'<span style="color:{cc};">直近1ヶ月 {ctx["chg_1m"]:+.1f}%</span>'

        def cell(label, val):
            if not val:
                return ""
            return f'''<div style="flex:1;min-width:130px;">
  <div style="font-size:0.66em;color:#7a8fa8;">{label}</div>
  <div style="font-size:0.8em;color:#dde8ff;margin-top:1px;">{val}</div>
</div>'''

        cards += f'''
<div style="background:#0f1623;border:1px solid #1e2d42;border-left:3px solid {col};border-radius:12px;padding:14px;margin-bottom:12px;">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
    <div style="flex:1;font-weight:800;font-size:0.96em;">{c['emoji']} [{c['code']}] {c['name']} {tag}</div>
    <div style="text-align:right;">
      <div style="font-size:0.66em;color:#7a8fa8;">資金妙味</div>
      <div style="font-weight:900;color:{col};">{c['appeal']}</div>
    </div>
  </div>
  <div style="font-size:0.82em;font-weight:700;color:{col};margin-bottom:6px;">{c['catalyst_type']}　<span style="color:#7a8fa8;font-weight:400;">{ctx_html}</span></div>
  <div style="display:flex;flex-wrap:wrap;gap:8px 12px;margin-bottom:8px;">
    {cell("業績インパクト", c.get("earnings_impact"))}
    {cell("一時的か継続か", c.get("temp_or_cont"))}
    {cell("織り込み度", c.get("priced_in"))}
  </div>
  <div style="background:#0d1117;border-radius:8px;padding:9px 11px;">
    <div style="font-size:0.84em;line-height:1.5;color:#eaf2ff;">💡 <b>仮説</b>：{c['hypothesis']}</div>
    {f'<div style="font-size:0.78em;line-height:1.5;color:#d29922;margin-top:4px;">⚠️ 注意：{c["watch_point"]}</div>' if c.get("watch_point") else ""}
    {f'<div style="font-size:0.78em;line-height:1.5;color:#f85149;margin-top:4px;">🛑 失敗ライン：{c["fail_line"]}</div>' if c.get("fail_line") else ""}
  </div>
</div>'''

    return f'''
<div style="background:#0d1117;border:1px solid #1e2d42;border-radius:14px;padding:16px;">
  <div style="font-size:0.75em;color:#7a8fa8;margin-bottom:12px;">
    プロのトレーダー目線で、今日の材料を「何の材料か→業績に効くか→一時的か継続か→織り込み済みか→今日資金が入るか」の5軸で評価し、
    寄り付き後の仮説と失敗ラインまで立てます（{result['count']}材料・資金妙味の高い順）
  </div>
  {cards}
  <div style="font-size:0.68em;color:#5a6b82;margin-top:4px;">🟢資金妙味 高 ／ 🟡中 ／ ⚪低　※AIの仮説で、株価を保証しません</div>
</div>'''


if __name__ == "__main__":
    from src.tdnet_watcher import fetch_watchlist_disclosures
    import sys
    date = sys.argv[1] if len(sys.argv) > 1 else None
    td = fetch_watchlist_disclosures(date_str=date)
    r = run(tdnet=td)
    out = []
    if r.get("available"):
        out.append(f"=== 材料分析 {r['count']}件（妙味高 {r['high_count']}件）===\n")
        for c in r["catalysts"]:
            out.append(f"[{c['appeal']}] [{c['code']}] {c['name']} — {c['catalyst_type']}")
            out.append(f"   業績: {c['earnings_impact']}")
            out.append(f"   一時/継続: {c['temp_or_cont']}")
            out.append(f"   織り込み: {c['priced_in']}")
            out.append(f"   💡 仮説: {c['hypothesis']}")
            out.append(f"   ⚠️ 注意: {c['watch_point']}")
            out.append(f"   🛑 失敗ライン: {c['fail_line']}")
            out.append("")
    else:
        out.append(f"分析対象なし: {r.get('reason','')}")
    text = "\n".join(out)
    try:
        print(text)
    except UnicodeEncodeError:
        with open("ca_output.txt", "w", encoding="utf-8") as f:
            f.write(text)
        print("ca_output.txt に保存しました")
