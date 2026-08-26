"""
統合AI解釈（Step AIB）— 6回に分けていたGemini呼び出しを1回にまとめる

なぜ必要か:
  Geminiの無料枠は**1日20回**しかない（2026-08-25にログで判明）。
  一方、朝の中核だけで7回を使っていた。

  中身を見ると、そのうち5回はすべて
  **「今日の値動きとニュースを見て解釈を書く」**という同じ仕事だった。
    ・ai_debate  … 強気の見方 / 弱気の見方 / 中立の総合判断（3回）
    ・scenario   … 今後1〜4週間の3シナリオ（1回）
    ・market_driver … なぜ動いたか（1回）

  同じ材料を5回送り直して、5回別々に読ませていた。
  1回で全部書かせれば、内容を落とさずに4回ぶん空く。

  実測（scripts/measure_prompts.py）では入力は全部で2,798トークンしかなく、
  **入力の長さは問題ではなかった**。効くのは回数だけである。

なぜ「まとめても質が落ちない」と言えるか:
  3つの視点は互いに独立ではない。むしろ中立の判断は
  強気と弱気を読んでから書くものなので、**同じ応答の中で書く方が自然**。
  実際、元の実装でも中立役には強弱2つの意見を渡していた
  （＝3回目は1・2回目の結果を待つ直列処理で、時間もかかっていた）。

⚠️ 1回で全部取るということは、失敗すると全部失うということでもある。
   そこで JSON で受け取り、**部分的に壊れていても取れた分だけ使う**。
   完全に失敗したら呼び出し側は従来どおり available:False で静かに畳む。
"""
import json
import os
import re
import traceback

from src.utils import setup_logger

logger = setup_logger("ai_brief")

# 応答の形。response_schema で縛ると、余計な前置きや
# ```json ``` の囲みが混ざらず、解析の失敗が減る。
_SCHEMA = {
    "type": "object",
    "properties": {
        "bull_view":    {"type": "string"},
        "bear_view":    {"type": "string"},
        "neutral_view": {"type": "string"},
        "driver":       {"type": "string"},
        "scenarios": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name":        {"type": "string"},
                    "probability": {"type": "integer"},
                    "detail":      {"type": "string"},
                },
                "required": ["name", "probability", "detail"],
            },
        },
    },
    "required": ["bull_view", "bear_view", "neutral_view", "driver", "scenarios"],
}


def _fmt(prices: dict, sym: str, label: str, unit: str = "") -> str:
    d = (prices or {}).get(sym) or {}
    v, c = d.get("latest"), d.get("change_pct")
    if v is None:
        return ""
    return f"{label} {v:,.2f}{unit}（{c:+.2f}%）" if c is not None \
        else f"{label} {v:,.2f}{unit}"


def _market_text(prices: dict, risk: dict, fear_greed: dict) -> str:
    rows = [
        _fmt(prices, "^N225", "日経平均", "円"),
        _fmt(prices, "^GSPC", "S&P500"),
        _fmt(prices, "^IXIC", "NASDAQ"),
        _fmt(prices, "^SOX", "SOX半導体"),
        _fmt(prices, "USDJPY=X", "ドル円", "円"),
        _fmt(prices, "^VIX", "VIX"),
        _fmt(prices, "GC=F", "金", "$"),
        _fmt(prices, "CL=F", "原油", "$"),
    ]
    out = "\n".join(f"・{r}" for r in rows if r)
    s = (risk or {}).get("score")
    if s is not None:
        out += f"\n・地合いスコア {s:+.1f}（±3が上限）"
    fg = (fear_greed or {}).get("score")
    if fg is not None:
        out += f"\n・Fear&Greed {fg}"
    return out


def _overnight_text(us_ah: dict, adr: dict, us_movers: dict) -> str:
    """
    夜のうちの動き。**朝7:30の判断ではここが中心になる。**

    東京はまだ開いていないので、前日の東京終値より
    「夜に何が起きたか」の方が寄り付きを決める。
    2026-08-25まで、この情報はAIに渡っていなかった
    （3つのStepが統合AI解釈より後に置かれていたため）。

    3つは見ているものが違うので、まとめずに分けて渡す:
      ・米国の通常取引 … 何が崩れたか/伸びたか（業界単位）
      ・米国の時間外   … 引け後に出た材料への反応
      ・ADR           … 日本株そのものが夜間にどう値付けされたか
    """
    parts = []

    um = us_movers or {}
    if um.get("available"):
        secs = [s.get("sector", "") for s in (um.get("sectors") or [])[:2]]
        if secs:
            parts.append(f"・米国通常取引で動いた業界: {'、'.join(secs)}")
        mv = [f"{m.get('name','')} {m.get('chg_pct',0):+.1f}%"
              for m in (um.get("movers") or [])[:4]]
        if mv:
            parts.append(f"・米国の主な値動き: {' / '.join(mv)}")
        if um.get("emergency"):
            parts.append("・米国市場は全面的に動いています（広がりのある動き）")

    # ⚠️ キー名は実データで確認すること。us_afterhours は change_pct ではなく
    #    **chg_pct**。間違えても例外にならず「全部 +0.0%」という
    #    もっともらしい嘘が並ぶだけで気づけない（実際に一度やらかした）。
    ah = us_ah or {}
    if ah.get("available"):
        mv = [f"{m.get('name') or m.get('symbol','')} {m['chg_pct']:+.1f}%"
              for m in (ah.get("movers") or [])[:4]
              if m.get("chg_pct") is not None]
        if mv:
            parts.append(f"・米国時間外（引け後）: {' / '.join(mv)}")

    # ADR は stocks ではなく **top / majors**、値は divergence（東京終値との差）
    ad = adr or {}
    if ad.get("available"):
        d = ad.get("major_avg_divergence")
        if d is not None:
            parts.append(f"・日本株ADR（夜間NYでの日本株）: 東京終値との差 平均{d:+.2f}%")
        rows = (ad.get("top") or []) + (ad.get("bottom") or [])
        top = [f"{a.get('name','')} {a['divergence']:+.1f}%"
               for a in rows[:4] if a.get("divergence") is not None]
        if top:
            parts.append(f"　うち目立つもの: {' / '.join(top)}")

    return "\n".join(parts) if parts else "（夜間に目立った動きなし）"


def _news_text(news: list, limit: int = 6) -> str:
    if not news:
        return "（主要ニュースなし）"
    ranked = sorted(news or [],
                    key=lambda x: {"A": 0, "B": 1, "C": 2}.get(
                        x.get("importance", "C"), 2))
    return "\n".join(f"・{n.get('title','')[:60]}" for n in ranked[:limit])


def _parse(text: str) -> dict:
    """
    JSONを取り出す。response_schema を指定していても、
    モデルが前後に文章を付けることがあるので括弧の範囲を探す。
    壊れていたら空を返し、呼び出し側で静かに畳ませる。
    """
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            logger.error("JSONの解析に失敗しました（応答の先頭200字: "
                         f"{text[:200]}）")
    return {}


def run(prices: dict, news: list, risk: dict, fear_greed: dict,
        us_ah: dict = None, adr: dict = None, us_movers: dict = None) -> dict:
    """
    1回の呼び出しで、強気/弱気/中立の見方・変動要因・3シナリオを得る。

    us_ah / adr / us_movers は夜のうちの動き。
    朝7:30は東京が開く前なので、**判断材料の中心はここ**になる。
    渡されなければ従来どおり前日終値だけで書くが、精度は落ちる。

    戻り値は既存のモジュールと同じ形に整えて返すので、
    受け取り側（design_ai・notify_telegram）は変更しなくてよい。
    """
    out = {"available": False}
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        logger.info("GEMINI_API_KEY 未設定のためスキップ")
        return out

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))

        prompt = f"""あなたは日本の個人投資家向けの市場アナリストです。
読者は投資初心者なので、中学生にも分かる言葉で書いてください。
今は日本時間の早朝で、東京市場はまだ開いていません。

【前日までの終値】
{_market_text(prices, risk, fear_greed)}

【夜のうちの動き（東京の寄り付きに直接効く）】
{_overnight_text(us_ah, adr, us_movers)}

【主なニュース】
{_news_text(news)}

次の5つを一度に、JSONで答えてください。
判断は「夜のうちの動き」を主に、終値は背景として使ってください。

1. bull_view … 強気派ならこの相場をどう見るか（120字以内）
2. bear_view … 弱気派ならどこを警戒するか（120字以内）
3. neutral_view … 1と2を踏まえた総合判断（150字以内）
4. driver … 今この相場を動かしている一番の要因（60字以内）
5. scenarios … 今後1〜4週間の3つの筋書き。
   name は「楽観」「基本」「悲観」、probability は3つ合計が100になる整数、
   detail は各100字以内。

守ってほしいこと:
・上のデータに無い数字を作らないでください
・「必ず」「確実に」などの断定は避けてください
・専門用語を使うときは短く言い換えを添えてください"""

        resp = model.generate_content(
            prompt,
            generation_config={
                "max_output_tokens": 2048,
                "temperature": 0.7,
                "response_mime_type": "application/json",
                "response_schema": _SCHEMA,
            },
        )
        data = _parse(getattr(resp, "text", "") or "")
        if not data:
            logger.error("統合AI解釈: 応答を解析できませんでした")
            return out

        scen = []
        for s in (data.get("scenarios") or [])[:3]:
            try:
                scen.append({"name": str(s.get("name", ""))[:8],
                             "probability": int(s.get("probability", 0)),
                             "detail": str(s.get("detail", ""))[:200]})
            except Exception:
                continue

        # 一部でも取れていれば使う。全部そろわないと捨てる作りにすると、
        # ちょっとした欠けで朝の中身が丸ごと消える。
        got = {k: str(data.get(k, ""))[:300]
               for k in ("bull_view", "bear_view", "neutral_view", "driver")}
        if not any(got.values()) and not scen:
            return out

        logger.info(f"✅ 統合AI解釈（1回の呼び出しで {sum(1 for v in got.values() if v)}項目"
                    f"＋シナリオ{len(scen)}件）")
        return {"available": True, **got, "scenarios": scen,
                "ai_generated": True}
    except Exception as e:
        # 予算超過は障害ではないので静かに畳む
        if type(e).__name__ == "BudgetExceeded":
            logger.info(f"統合AI解釈: {e}")
        else:
            logger.error("統合AI解釈に失敗", exc_info=True)
        return out


def to_ai_summary(b: dict) -> dict:
    """既存の ai_debate 互換の形（notify_telegram / design_ai が読む）。"""
    if not b.get("available"):
        return {"available": False}
    return {"available": True, "bull_view": b.get("bull_view", ""),
            "bear_view": b.get("bear_view", ""),
            "neutral_view": b.get("neutral_view", ""),
            "ai_generated": True}


def to_scenario(b: dict) -> dict:
    """既存の scenario 互換の形。"""
    if not b.get("available") or not b.get("scenarios"):
        return {"available": False}
    return {"available": True, "scenarios": b["scenarios"],
            "ai_generated": True}


def to_market_driver(b: dict) -> dict:
    """既存の market_driver 互換の形。"""
    if not b.get("available") or not b.get("driver"):
        return {"available": False}
    return {"available": True, "summary": b["driver"], "drivers": [],
            "ai_generated": True}


if __name__ == "__main__":
    import io
    import sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace")
    from src.fetch_prices import run as fp
    from src.fetch_news import run as fn
    from src.indicators import calc_risk_score
    p, fg = fp()
    n = fn()
    r = run(p, n, calc_risk_score(p), fg)
    print(json.dumps(r, ensure_ascii=False, indent=2))
