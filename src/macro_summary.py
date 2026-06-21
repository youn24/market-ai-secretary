"""
マクロ要約エンジン（ファンダメンタル＋金融政策）
毎朝、金融政策（日銀・FRB）と景気・バリュエーションの観点で
「いま相場の土台で何が起きているか」を初心者向けに要約する。

入力はすべて既存データ（追加API不要）：
  - news        : fetch_news が集めた日銀・FRB・CPI・雇用統計などのニュース
  - prices      : 金利(^TNX)・ドル円・VIX・日経などの価格
  - fear_greed  : 投資家心理（恐怖＆強欲指数）

要約は Gemini が生成。APIキーが無い場合はデータから機械的に組み立てる。
"""
import os

from src.utils import setup_logger, get_jst_now

logger = setup_logger("macro_summary")

# ニュースを分類するためのラベル/キーワード
_POLICY_LABELS = ["日銀", "FRB", "FOMC", "日銀会合", "政策金利"]
_ECON_LABELS   = ["経済指標", "CPI", "雇用統計", "GDP", "PMI", "景況感"]
_POLICY_KW = ["日銀", "FRB", "FOMC", "利上げ", "利下げ", "政策金利", "金融政策",
              "植田", "パウエル", "金利"]
_ECON_KW   = ["CPI", "消費者物価", "雇用統計", "GDP", "PMI", "インフレ",
              "景況感", "失業率", "物価"]


def _classify_news(news: list) -> dict:
    """ニュースを金融政策・経済指標に仕分け"""
    policy, econ = [], []
    seen = set()
    for n in news or []:
        title = n.get("title", "")
        if not title or title in seen:
            continue
        label = n.get("label", "")
        text = title + " " + label
        if any(k in text for k in _POLICY_KW) or any(l in label for l in _POLICY_LABELS):
            policy.append(n); seen.add(title)
        elif any(k in text for k in _ECON_KW) or any(l in label for l in _ECON_LABELS):
            econ.append(n); seen.add(title)
    return {"policy": policy[:10], "econ": econ[:8]}


def _summarize_module(data, label: str) -> str:
    """各分析モジュールの結果から人間可読な要約行を防御的に抽出する。
    モジュールごとに構造が違うため、よくあるキーを順に探す。"""
    if not isinstance(data, dict) or not data.get("available"):
        return ""
    # 既に人が読める要約テキストがあれば最優先
    for k in ["summary", "ai_comment", "comment", "analysis", "analysis_text",
              "stance_ja", "stance", "verdict", "verdict_text", "headline", "note"]:
        v = data.get(k)
        if isinstance(v, str) and v.strip():
            return f"{label}：{v.strip()[:220]}"
    # Telegram用テキストがあればマークダウンを除いて使う
    tg = data.get("telegram_message")
    if isinstance(tg, str) and tg.strip():
        clean = tg.replace("*", "").replace("#", "").replace("━", "").strip()
        clean = " ".join(clean.split())
        return f"{label}：{clean[:220]}"
    return ""


def _build_extra_context(fred_data=None, fomc_sentiment=None, econ_analysis=None,
                         sector_analysis=None, congress_trades=None) -> str:
    """既存の専門分析モジュールの結果を要約文字列に束ねる"""
    parts = []
    for data, label in [
        (econ_analysis,   "経済指標分析"),
        (fred_data,       "FRED米経済指標(GDP/CPI/失業率/金利)"),
        (fomc_sentiment,  "FOMC議事録のタカ派/ハト派判定"),
        (sector_analysis, "セクターローテーション"),
        (congress_trades, "米議員の株取引動向"),
    ]:
        line = _summarize_module(data, label)
        if line:
            parts.append("・" + line)
    return "\n".join(parts)


def _market_context(prices: dict, fear_greed: dict) -> dict:
    """価格データから金利・為替・恐怖指数などの現状を抜き出す"""
    prices = prices or {}
    def g(sym, key="latest"):
        v = prices.get(sym, {})
        return v.get(key) if isinstance(v, dict) else None
    ctx = {
        "nikkei":     g("^N225"),
        "nikkei_chg": g("^N225", "change_pct"),
        "us10y":      g("^TNX"),
        "us10y_chg":  g("^TNX", "change_pct"),
        "usdjpy":     g("USDJPY=X"),
        "vix":        g("^VIX"),
        "nikkei_vi":  g("NIKKEI_VI"),
        "fg_score":   (fear_greed or {}).get("score"),
        "fg_rating":  (fear_greed or {}).get("rating_ja", ""),
        "fg_1w":      (fear_greed or {}).get("prev_1_week"),
        "fg_1m":      (fear_greed or {}).get("prev_1_month"),
    }
    return ctx


def _gemini_summary(ctx: dict, cls: dict, extra_context: str = "") -> dict:
    """Gemini でファンダ＆金融政策の要約を生成"""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return {}
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))

        policy_titles = "\n".join(f"・{n.get('title','')}" for n in cls["policy"][:8])
        econ_titles   = "\n".join(f"・{n.get('title','')}" for n in cls["econ"][:6])

        ctx_txt = (
            f"日経平均 {ctx.get('nikkei')}（前日比{ctx.get('nikkei_chg')}%）, "
            f"米10年金利 {ctx.get('us10y')}%（前日比{ctx.get('us10y_chg')}%）, "
            f"ドル円 {ctx.get('usdjpy')}, "
            f"VIX {ctx.get('vix')}, 日経VI {ctx.get('nikkei_vi')}, "
            f"恐怖＆強欲指数 {ctx.get('fg_score')}（{ctx.get('fg_rating')}／1週前{ctx.get('fg_1w')}・1ヶ月前{ctx.get('fg_1m')}）"
        )

        extra_block = f"\n\n【システムの専門分析データ（最重要・優先的に根拠として使う）】\n{extra_context}" if extra_context else ""

        prompt = f"""あなたは個人投資家にやさしく教える一流のマーケットエコノミストです。
以下のデータだけを根拠に、いまの相場を「金融政策」と「ファンダメンタル（景気・企業価値）」の
観点から要約してください。

【守るべきこと】
- 中学生でもわかる言葉で、専門用語は必ず一言で噛み砕く（例：「タカ派＝利上げに前向き」）
- 必ず具体的な数値・固有名詞（日銀/FRB/CPI%/金利/銘柄名など）を引用して根拠を示す
- 4つの観点を互いに関連づける（例：金利↑→為替→株、のように因果でつなぐ）
- 断定や「儲かる/必ず上がる」等の投資助言・予言はしない
- データにない事柄を創作しない。情報が乏しい項目は「現時点で材料は限定的」と正直に書く

【市場の現状】
{ctx_txt}

【金融政策ニュース】
{policy_titles or '（なし）'}

【経済指標ニュース】
{econ_titles or '（なし）'}{extra_block}

次の4項目を、それぞれ100〜140字で出力してください。各項目は必ず「###」見出しで始めてください：
### 金融政策
（日銀とFRBの方向性と、それが金利・為替・株にどう波及するか。具体的な金利水準や会合日程に触れる）
### ファンダメンタル
（景気指標の強弱・企業業績やバリュエーション。割安/割高の判断材料を数値で）
### 注目のねじれ・リスク
（株価と投資家心理の矛盾、需給、タカ/ハトのズレなど、見落としがちな注意点を具体的に）
### 今後の注目
（次に控える重要イベントと、それぞれで何を確認すべきか）"""

        raw = model.generate_content(prompt).text.strip()
        # ### で分割
        sections = {}
        cur = None
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith("###"):
                cur = line.replace("#", "").strip()
                sections[cur] = ""
            elif cur and line:
                sections[cur] += line + " "
        sections = {k: v.strip() for k, v in sections.items() if v.strip()}
        return sections
    except Exception as e:
        logger.warning(f"Geminiマクロ要約失敗: {e}")
        return {}


def _fallback_summary(ctx: dict, cls: dict, extra: str = "") -> dict:
    """Geminiが使えないときの機械的要約"""
    s = {}
    # 金融政策（抽出ニュースの見出しから）
    pol = [n.get("title", "") for n in cls["policy"][:3]]
    s["金融政策"] = "／".join(pol) if pol else "主要な金融政策ニュースは検出されませんでした。"
    # ファンダ（経済指標ニュース＋専門分析データ）
    econ = [n.get("title", "") for n in cls["econ"][:2]]
    fund = "／".join(econ) if econ else "主要な経済指標ニュースは検出されませんでした。"
    if extra:
        fund += "　【専門分析】" + extra.replace("\n", " ")[:300]
    s["ファンダメンタル"] = fund
    # ねじれ
    fg = ctx.get("fg_score")
    nz = ""
    if fg is not None and ctx.get("nikkei_chg") is not None:
        if fg <= 45 and ctx["nikkei_chg"] > 0:
            nz = f"株価は上昇（日経{ctx['nikkei_chg']:+.1f}%）なのに投資家心理は恐怖（{fg}）。気分と値動きにねじれがあります。"
        elif fg >= 60:
            nz = f"投資家心理は強欲寄り（{fg}）。過熱に注意。"
        else:
            nz = f"投資家心理は中立圏（{fg}）。"
    s["注目のねじれ・リスク"] = nz or "特筆すべきねじれは検出されませんでした。"
    s["今後の注目"] = "日銀・FRBの会合、CPI・雇用統計などの重要指標に注目。"
    return s


def run(prices: dict = None, news: list = None, fear_greed: dict = None,
        risk: dict = None, fred_data: dict = None, fomc_sentiment: dict = None,
        econ_analysis: dict = None, sector_analysis: dict = None,
        congress_trades: dict = None) -> dict:
    try:
        cls = _classify_news(news)
        ctx = _market_context(prices, fear_greed)
        extra = _build_extra_context(fred_data, fomc_sentiment, econ_analysis,
                                     sector_analysis, congress_trades)
        sections = _gemini_summary(ctx, cls, extra)
        used_ai = bool(sections)
        if not sections:
            sections = _fallback_summary(ctx, cls, extra)

        result = {
            "available": True,
            "sections": sections,
            "context": ctx,
            "policy_news": cls["policy"][:5],
            "econ_news": cls["econ"][:4],
            "ai_generated": used_ai,
            "extra_sources": [l for l in extra.split("\n") if l.strip()],
        }
        result["html"] = get_html(result)
        result["telegram_message"] = build_telegram_message(result)
        return result
    except Exception as e:
        logger.error(f"マクロ要約エラー: {e}")
        return {"available": False}


# ── 出力 ─────────────────────────────────────────────────────
_SEC_EMOJI = {
    "金融政策": "🏦", "ファンダメンタル": "📈",
    "注目のねじれ・リスク": "⚡", "今後の注目": "📅",
}


def build_telegram_message(result: dict) -> str:
    if not result.get("available"):
        return ""
    sec = result.get("sections", {})
    lines = ["🌐 *ファンダ＆金融政策 要約*", ""]
    for name in ["金融政策", "ファンダメンタル", "注目のねじれ・リスク", "今後の注目"]:
        if sec.get(name):
            emo = _SEC_EMOJI.get(name, "・")
            lines.append(f"{emo} *{name}*")
            lines.append(f"{sec[name]}")
            lines.append("")
    return "\n".join(lines).strip()


def get_html(result: dict) -> str:
    if not result or not result.get("available"):
        return ""
    sec = result.get("sections", {})
    ctx = result.get("context", {})

    # 市場サマリーバー
    chips = ""
    def chip(label, val, suffix=""):
        if val is None:
            return ""
        return (f'<span style="display:inline-block;background:#1e2d42;border-radius:20px;'
                f'padding:4px 11px;font-size:0.75em;margin:3px;">{label} '
                f'<b style="color:#7ec8ff;">{val}{suffix}</b></span>')
    chips += chip("日経", f'{ctx.get("nikkei_chg"):+.1f}' if ctx.get("nikkei_chg") is not None else None, "%")
    chips += chip("米10年金利", ctx.get("us10y"), "%")
    chips += chip("ドル円", ctx.get("usdjpy"))
    chips += chip("VIX", ctx.get("vix"))
    chips += chip("恐怖&強欲", f'{ctx.get("fg_score")}（{ctx.get("fg_rating")}）' if ctx.get("fg_score") is not None else None)

    blocks = ""
    sec_color = {"金融政策": "#ef5350", "ファンダメンタル": "#3fb950",
                 "注目のねじれ・リスク": "#ffa726", "今後の注目": "#7e9bff"}
    for name in ["金融政策", "ファンダメンタル", "注目のねじれ・リスク", "今後の注目"]:
        if sec.get(name):
            c = sec_color.get(name, "#7a8fa8")
            emo = _SEC_EMOJI.get(name, "")
            blocks += f'''
<div style="margin-bottom:12px;">
  <div style="font-weight:700;color:{c};font-size:0.9em;margin-bottom:3px;">{emo} {name}</div>
  <div style="font-size:0.86em;line-height:1.7;color:#dde8ff;">{sec[name]}</div>
</div>'''

    n_src = len(result.get("extra_sources", []))
    src_note = ""
    if n_src:
        src_note = (f'<div style="font-size:0.7em;color:#7a8fa8;margin-top:8px;">'
                    f'📚 この要約はニュース＋価格に加え、システムの専門分析 {n_src} 件'
                    f'（FRED経済指標・FOMC・経済指標・セクター・議員取引）を根拠にしています</div>')
    ai_note = "" if result.get("ai_generated") else (
        '<div style="font-size:0.7em;color:#7a8fa8;margin-top:6px;">'
        '※AI未使用時の簡易要約（GEMINI_API_KEY設定でAI要約に切替）</div>')
    ai_note = src_note + ai_note

    return f'''
<div style="background:#0f1623;border:1px solid #1e2d42;border-radius:14px;padding:16px;">
  <div style="margin-bottom:12px;">{chips}</div>
  {blocks}{ai_note}
</div>'''


if __name__ == "__main__":
    import json, glob
    from pathlib import Path
    # 最新の蓄積データで単体テスト
    base = Path(__file__).resolve().parent.parent
    price_files = sorted(glob.glob(str(base / "data" / "raw" / "*_prices.json")))
    news_files  = sorted(glob.glob(str(base / "data" / "news" / "*_news.json")))
    prices, fg, news = {}, {}, []
    if price_files:
        d = json.load(open(price_files[-1], encoding="utf-8"))
        prices = d.get("prices", {}); fg = d.get("fear_and_greed", {})
    if news_files:
        news = json.load(open(news_files[-1], encoding="utf-8"))

    r = run(prices=prices, news=news, fear_greed=fg)
    out = ["=== ファンダ＆金融政策 要約 ==="]
    out.append(f"AI生成: {r.get('ai_generated')}")
    for k, v in r.get("sections", {}).items():
        out.append(f"\n### {k}\n{v}")
    text = "\n".join(out)
    try:
        print(text)
    except UnicodeEncodeError:
        with open("macro_output.txt", "w", encoding="utf-8") as f:
            f.write(text)
        print("macro_output.txt に保存しました")
