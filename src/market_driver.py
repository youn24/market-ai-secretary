"""
「昨日マーケットを動かしたのは何か」の要因分析（Step MD）

大きく動いた日だけ、その原因をAIに要約させる。
毎日出すと「特に材料なし」の日も無理やり理由をこじつけてしまうため、
主要指数が一定以上動いた日に限定する（後付け解釈のノイズを避ける）。

あわせて、直近に発表された経済指標のうち「市場が最も重視するもの」を
予想比で評価する。指標は結果そのものより“予想とのズレ”が相場を動かすため。

run(prices, news, econ, macro_watch) → {"available", "summary", "drivers":[...], "telegram_block"}
"""
import os
import traceback
from src.utils import setup_logger, get_jst_now

logger = setup_logger("market_driver")

# この変動幅を超えた指数があった日だけ要因を分析する（％）
_TRIGGER = {
    "^N225": 1.2, "^GSPC": 1.0, "^IXIC": 1.5,
    "USDJPY=X": 0.8, "^VIX": 12.0, "GC=F": 1.5, "CL=F": 3.0,
}

_JA = {
    "^N225": "日経平均", "^GSPC": "S&P500", "^IXIC": "NASDAQ",
    "USDJPY=X": "ドル円", "^VIX": "VIX", "GC=F": "金", "CL=F": "原油",
}

# 市場が最も重視する経済指標（この順で重要度が高い）
_KEY_INDICATORS = [
    "雇用統計", "CPI", "消費者物価", "FOMC", "PCE", "GDP",
    "小売売上", "ISM", "PPI", "失業保険", "日銀", "決算",
]


def _movers(prices: dict) -> list:
    """トリガーを超えて動いた指数を、動きの大きい順に返す。"""
    out = []
    for sym, th in _TRIGGER.items():
        d = (prices or {}).get(sym) or {}
        chg = d.get("change_pct")
        if chg is None or abs(chg) < th:
            continue
        out.append({"symbol": sym, "name": _JA.get(sym, sym),
                    "chg": chg, "value": d.get("latest")})
    out.sort(key=lambda x: abs(x["chg"]), reverse=True)
    return out


def _relevant_news(news: list, limit: int = 12) -> list:
    """重要度の高いニュースを優先して抽出（AIに渡す材料）。"""
    if not news:
        return []
    ranked = sorted(news, key=lambda n: {"A": 0, "B": 1, "C": 2}.get(n.get("importance", "C"), 2))
    return [n.get("title", "")[:70] for n in ranked[:limit] if n.get("title")]


def _key_events(news: list) -> list:
    """市場が重視する経済指標に関するニュースを拾う。"""
    hits = []
    for n in (news or []):
        t = n.get("title", "")
        for kw in _KEY_INDICATORS:
            if kw in t:
                hits.append({"keyword": kw, "title": t[:70]})
                break
    return hits[:5]


def _policy_impact(policy: dict, movers: list) -> dict | None:
    """
    中央銀行が金利を動かした日に、相場が実際どう反応したかを結びつける。
    「利上げした」だけでなく「その結果マーケットがどう動いたか」まで示す。
    """
    events = (policy or {}).get("events") or []
    if not events or not movers:
        return None
    e = events[0]
    top = movers[0]
    react = "大きく反応しました" if abs(top["chg"]) >= 1.5 else "反応しました"
    updown = "上昇" if top["chg"] > 0 else "下落"
    if e["direction"] == "利上げ":
        read = ("利上げは通常は株の重荷ですが、想定内なら安心感から買われることもあります。"
                if top["chg"] > 0 else "利上げを嫌気した売りが出たとみられます。")
    else:
        read = ("利下げは株の追い風。素直に好感されたとみられます。"
                if top["chg"] > 0 else
                "利下げにもかかわらず下落。景気悪化への懸念が勝った可能性があります。")
    return {
        "name": e["name"], "direction": e["direction"],
        "prev_rate": e.get("prev_rate"), "rate": e.get("rate"),
        "text": (f"{e['name']}が{e['direction']}"
                 f"（{e.get('prev_rate'):.2f}%→{e.get('rate'):.2f}%）。"
                 f"{top['name']}は{top['chg']:+.2f}%と{updown}して{react}。{read}"),
    }


def run(prices: dict = None, news: list = None,
        econ: dict = None, macro_watch: dict = None,
        policy: dict = None) -> dict:
    movers = _movers(prices)
    if not movers:
        logger.info("市場要因分析: 大きな変動なし（分析はスキップ）")
        return {"available": False, "drivers": []}

    key_events = _key_events(news)
    headlines = _relevant_news(news)
    pol_impact = _policy_impact(policy, movers)

    # ── AIに「なぜ動いたか」を要約させる ──
    summary = ""
    try:
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if api_key and headlines:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))

            move_txt = "\n".join(
                f"・{m['name']}: {m['chg']:+.2f}%" for m in movers)
            news_txt = "\n".join(f"・{h}" for h in headlines)
            ev_txt = "\n".join(f"・{e['title']}" for e in key_events) or "（該当なし）"

            prompt = f"""あなたは市場アナリストです。以下の値動きとニュースから、
「相場を動かした主な要因」を投資初心者にもわかるよう説明してください。

【大きく動いた指標】
{move_txt}

【注目された経済指標・イベント】
{ev_txt}

【当日のニュース見出し】
{news_txt}

次の形式で、全体250文字以内で簡潔に書いてください:
1行目「要因: （最も効いた要因を20字以内で）」
2行目以降: なぜその要因でこの値動きになったのかを2〜3文。
最後に「今日への影響: （1文）」

【厳守事項】
- 上に挙げたニュースと数値だけを根拠にすること。挙げていない事実や数値を創作しない
- ニュースから要因が読み取れない場合は正直に「明確な材料は見当たらず、需給要因の可能性」と書く
- 断定を避け「〜とみられる」「〜が意識された」等の表現を使う"""

            resp = model.generate_content(prompt)
            summary = (resp.text or "").strip()[:400]
            # 数値の捏造チェック（既存のガードを再利用）
            try:
                from src.ai_guard import verify_against, build_allowed
                allowed = build_allowed(prices or {})
                summary, suspects = verify_against(summary, allowed)
                if suspects:
                    logger.warning(f"要因分析に照合できない数値: {suspects[:3]}")
            except Exception:
                pass
    except Exception:
        logger.error("要因分析AIエラー")
        logger.debug(traceback.format_exc())

    now = get_jst_now().strftime("%m/%d")
    lines = [f"🔍 *相場を動かした要因* （{now}）", "━━━━━━━━━━━━━━━"]
    for m in movers[:4]:
        arrow = "🔺" if m["chg"] > 0 else "🔻"
        val = f"{m['value']:,.2f}" if m.get("value") else "—"
        lines.append(f"{arrow} *{m['name']}* {val}（{m['chg']:+.2f}%）")
    if pol_impact:
        lines += ["", f"🏛 *中央銀行の動き*", f"　{pol_impact['text']}"]
    if key_events:
        lines.append("")
        lines.append("📅 *注目された指標・イベント*")
        for e in key_events[:3]:
            lines.append(f"　・{e['title']}")
    if summary:
        lines += ["", summary]
    lines += ["━━━━━━━━━━━━━━━",
              "大きく動いた日だけ、その要因を分析しています。"]

    logger.info(f"✅ 要因分析: {len(movers)}指標が大きく変動")
    return {"available": True, "movers": movers, "key_events": key_events,
            "policy_impact": pol_impact,
            "summary": summary, "drivers": movers,
            "telegram_block": "\n".join(lines)}


if __name__ == "__main__":
    p = {"^N225": {"latest": 39000, "change_pct": -2.1},
         "^VIX": {"latest": 24.0, "change_pct": 18.0}}
    n = [{"title": "米CPI予想上振れ 利下げ観測後退", "importance": "A"},
         {"title": "半導体株が軟調", "importance": "B"}]
    r = run(p, n)
    print(r.get("telegram_block", "変動なし"))
