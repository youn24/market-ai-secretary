"""
Level 3: シナリオ分析
楽観・基本・悲観の3シナリオをGeminiが確率付きで生成
"""
import os
import traceback
from src.utils import setup_logger

logger = setup_logger("scenario")


def run(prices: dict, risk: dict, fear_greed: dict, news: list) -> dict:
    """3シナリオ分析を実行"""
    api_key = os.getenv("GEMINI_API_KEY","").strip()
    if not api_key:
        return {"available": False}

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")

        score    = risk.get("score", 0)
        fg       = fear_greed.get("score") or 50
        fg_label = fear_greed.get("rating_ja","---")

        def fmt(sym, unit=""):
            d = prices.get(sym, {})
            v = d.get("latest"); chg = d.get("change_pct")
            if v is None: return "---"
            s = f"+{chg:.2f}%" if (chg or 0)>=0 else f"{chg:.2f}%"
            return f"{v:,.2f}{unit}({s})"

        news_text = "\n".join(
            f"・{n.get('title','')}" for n in
            sorted(news, key=lambda x: {"A":0,"B":1,"C":2}.get(x.get("importance","C"),2))[:8]
        )

        prompt = f"""あなたはトップ金融アナリストです。
現在の市場データをもとに、今後1〜4週間の3シナリオを分析してください。

【現在の市場データ】
日経平均: {fmt('^N225','円')}
S&P500:  {fmt('^GSPC')}
ドル円:  {fmt('USDJPY=X','円')}
VIX:     {fmt('^VIX')}
金:      {fmt('GC=F','$')}
Bitcoin: {fmt('BTC-USD','$')}
リスクスコア: {score:+.2f}
Fear&Greed: {fg:.0f} ({fg_label})

【最近の主要ニュース】
{news_text}

以下の形式で3シナリオを分析してください。
確率の合計が100%になるようにしてください。

【🟢 楽観シナリオ（強気）】確率: XX%
このシナリオが起きる条件（1文）:
日経平均の予想レンジ:
S&P500の予想レンジ:
キーポイント（100文字）:

【🟡 基本シナリオ（中立）】確率: XX%
このシナリオが起きる条件（1文）:
日経平均の予想レンジ:
S&P500の予想レンジ:
キーポイント（100文字）:

【🔴 悲観シナリオ（弱気）】確率: XX%
このシナリオが起きる条件（1文）:
日経平均の予想レンジ:
S&P500の予想レンジ:
キーポイント（100文字）:

【⚡ 最注目リスク】（100文字）:
今最も注意すべきリスクは何か。

すべて推測として述べ、断定表現は禁止。"""

        resp = model.generate_content(prompt)
        raw  = resp.text

        # セクション分割
        sections = _parse_scenarios(raw)

        logger.info("✅ シナリオ分析完了")
        return {
            "available": True,
            "full_text": raw,
            "bull":      sections.get("bull",{}),
            "base":      sections.get("base",{}),
            "bear":      sections.get("bear",{}),
            "top_risk":  sections.get("top_risk",""),
        }

    except Exception as e:
        logger.error(f"シナリオ分析エラー: {e}")
        logger.debug(traceback.format_exc())
        return {"available": False}


def _parse_scenarios(text: str) -> dict:
    """テキストから3シナリオを抽出"""
    result = {"bull":{}, "base":{}, "bear":{}, "top_risk":""}
    current = None
    buf = []

    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if "楽観シナリオ" in line or "強気" in line and "確率" in line:
            if current and buf: result[current]["text"] = "\n".join(buf)
            current = "bull"; buf = [line]
        elif "基本シナリオ" in line or ("中立" in line and "確率" in line):
            if current and buf: result[current]["text"] = "\n".join(buf)
            current = "base"; buf = [line]
        elif "悲観シナリオ" in line or ("弱気" in line and "確率" in line):
            if current and buf: result[current]["text"] = "\n".join(buf)
            current = "bear"; buf = [line]
        elif "最注目リスク" in line or "注目リスク" in line:
            if current and buf: result[current]["text"] = "\n".join(buf)
            current = "top_risk"; buf = []
        else:
            if current == "top_risk":
                if line: result["top_risk"] += line + " "
            else:
                buf.append(line)
                # 確率を抽出
                if "確率" in line and "%" in line:
                    import re
                    m = re.search(r"(\d+)%", line)
                    if m and current in result:
                        result[current]["prob"] = int(m.group(1))

    if current and buf and current != "top_risk":
        result[current]["text"] = "\n".join(buf)

    # テキストが取れていない場合は全文を入れる
    for key in ["bull","base","bear"]:
        if not result[key].get("text"):
            result[key]["text"] = ""

    return result
