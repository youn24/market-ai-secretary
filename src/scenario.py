"""
Level 3: シナリオ分析
楽観・基本・悲観の3シナリオをGeminiが確率付きで生成
"""
import math
import os
import traceback
from src.utils import setup_logger

logger = setup_logger("scenario")


def run(prices: dict, risk: dict, fear_greed: dict, news: list) -> dict:
    """3シナリオ分析を実行"""
    api_key = os.getenv("GEMINI_API_KEY","").strip()
    if not api_key:
        logger.warning("GEMINI_API_KEY が無いので、計算で3シナリオを出します")
        return _rule_based(prices, risk)

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))

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

【ルール】
・各キーポイントには必ず上記の具体的な数値（現在の日経・VIX・ドル円など）を最低1つ引用すること。
・投資初心者にも分かるよう、専門用語には短い言い換えを添えること（例：VIX＝恐怖指数）。
・すべて推測として述べ、断定表現は禁止。"""

        resp = model.generate_content(prompt)
        raw  = resp.text

        # セクション分割
        sections = _parse_scenarios(raw)

        # ⚠️ Geminiが返事をしても、形が崩れていれば3つとも空文字になる。
        #    そのまま返すと**レポートの区画が丸ごと消える**（例外も出ない）。
        if not any((sections.get(k) or {}).get("text")
                   for k in ("bull", "base", "bear")):
            logger.warning("Geminiの返事を3つに分けられませんでした → 計算で出します")
            return _rule_based(prices, risk)

        logger.info("✅ シナリオ分析完了")
        return {
            "available": True,
            "source":    "gemini",
            "full_text": raw,
            "bull":      sections.get("bull",{}),
            "base":      sections.get("base",{}),
            "bear":      sections.get("bear",{}),
            "top_risk":  sections.get("top_risk",""),
        }

    except Exception as e:
        logger.error(f"シナリオ分析エラー: {e}")
        logger.debug(traceback.format_exc())
        return _rule_based(prices, risk)


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


# ──────────────────────────────────────────────────────────────
#  Gemini が使えない日の3シナリオ（計算だけで出す）
# ──────────────────────────────────────────────────────────────
#
# ⚠️ なぜ要るか。
#    `GEMINI_API_KEY` が無い／上限に当たった／返事の形が崩れた、の
#    どれでも従来は {"available": False} を返していた。
#    読み手から見ると**区画が丸ごと消えるだけ**で、例外もログも出ない。
#    実際に9月は2週間ほど3シナリオが消えたまま配信していた。
#
# ⚠️ ここで出すのは**予想ではない**。
#    ・幅   … 恐怖指数（日経VI）が示す1ヶ月の振れ幅を機械的に当てた数字
#    ・確率 … リスクスコアの符号で60%を振り分けただけ
#    だから出典も「AIの見立て」ではなく「計算」と名乗る（`source` を見る）。
#    ここを混ぜると、計算値をAIの判断だと誤解させることになる。

_SIGMA_FALLBACK = 5.0   # 恐怖指数が取れない日に使う1ヶ月の振れ幅(%)


def _month_sigma(prices: dict):
    """1ヶ月でどれくらい振れやすいかを % で返す。→ (幅, 根拠の一言)

    恐怖指数は**1年あたり**の振れ幅なので、1ヶ月なら √12 で割る。
    """
    for sym, nm in (("NIKKEI_VI", "日経VI"), ("^VIX", "VIX")):
        v = (prices.get(sym) or {}).get("latest")
        if isinstance(v, (int, float)) and 5 <= v <= 150:
            return v / math.sqrt(12), f"{nm} {v:.1f}"
    return _SIGMA_FALLBACK, ""


def _probs(score):
    """中立に40%を置き、残り60%をリスクスコアの向きで振り分ける。

    リスクスコアは ±1.5 で強気／弱気の判定が変わる（indicators.py）ので、
    そこを振り切った状態に合わせる。合計はいつもちょうど100%。
    """
    t = max(-1.0, min(1.0, float(score or 0) / 1.5))
    bull = int(round(30 + 15 * t))
    return bull, 40, 100 - 40 - bull


def _top_down_factor(risk: dict) -> str:
    """いちばん下げに効いている指標を1つだけ返す（寄与の大きい順に並んでいる）。"""
    for sg in (risk or {}).get("signals") or []:
        if sg.get("direction") != "下落圧力":
            continue
        nm = str(sg.get("indicator") or "").strip()
        ch = sg.get("change")
        if not nm:
            continue
        return f"{nm}（{ch:+.2f}%）" if isinstance(ch, (int, float)) else nm
    return ""


def _rule_based(prices: dict, risk: dict) -> dict:
    """恐怖指数とリスクスコアだけで3つの幅を出す。"""
    try:
        sigma, basis = _month_sigma(prices or {})
        nk = ((prices or {}).get("^N225") or {}).get("latest")
        bull_p, base_p, bear_p = _probs((risk or {}).get("score"))

        def band(lo_sd, hi_sd):
            if not isinstance(nk, (int, float)) or nk <= 0:
                return ""   # 日経の値が取れない日は幅を書かない（数字を作らない）
            lo = nk * (1 + lo_sd * sigma / 100)
            hi = nk * (1 + hi_sd * sigma / 100)
            return f"日経平均は {lo:,.0f}〜{hi:,.0f}円あたり。"

        out = {
            "available": True,
            "source": "rule",
            "basis": basis,
            "bull": {"prob": bull_p,
                     "text": band(0.5, 1.5) + "上にぶれた場合の幅です。"},
            "base": {"prob": base_p,
                     "text": band(-0.5, 0.5)
                             + "大きな材料が出ず、いまの振れ幅のまま進んだ場合です。"},
            "bear": {"prob": bear_p,
                     "text": band(-1.5, -0.5) + "下にぶれた場合の幅です。"},
        }
        f = _top_down_factor(risk)
        out["top_risk"] = (
            f"いま一番強く下げに効いている指標は {f} です。"
            "これが続くかどうかが分かれ目になります。"
            if f else "下げ方向に目立って効いている指標は、いまのところありません。")
        logger.info(f"3シナリオ: 計算で作成（強気{bull_p}/中立{base_p}/弱気{bear_p}%、"
                    f"振れ幅{sigma:.1f}% 根拠={basis or 'なし'}）")
        return out
    except Exception:
        logger.error("3シナリオを計算できませんでした", exc_info=True)
        return {"available": False}
