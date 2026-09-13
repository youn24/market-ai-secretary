"""
日本株 業種ヒートマップ（どの業種に買いが集まっているか）
東証17業種ETF（NEXT FUNDS TOPIX-17シリーズ）の騰落率を色分けして可視化する。

株マップのような「業種マップ」を、確実に取れるETFデータで再現。
緑＝買われている業種、赤＝売られている業種。濃いほど勢いが強い。
yfinance のみ・APIキー不要。

⚠️ 業種の強弱はその時点の傾向であり、将来を保証しない。
"""
import time

from src.utils import setup_logger

logger = setup_logger("sector_heatmap")

# 東証17業種ETF（TOPIX-17シリーズ）
TOPIX17 = [
    ("1617.T", "食品"),          ("1618.T", "エネルギー資源"),
    ("1619.T", "建設・資材"),     ("1620.T", "素材・化学"),
    ("1621.T", "医薬品"),         ("1622.T", "自動車・輸送機"),
    ("1623.T", "鉄鋼・非鉄"),     ("1624.T", "機械"),
    ("1625.T", "電機・精密"),     ("1626.T", "情報通信・サービス"),
    ("1627.T", "電力・ガス"),     ("1628.T", "運輸・物流"),
    ("1629.T", "商社・卸売"),     ("1630.T", "小売"),
    ("1631.T", "銀行"),          ("1632.T", "金融(除く銀行)"),
    ("1633.T", "不動産"),
]


def _color(chg: float) -> str:
    """騰落率→背景色（緑=上昇・赤=下落・濃淡で強弱）"""
    if chg is None:
        return "#3a4a5e"
    if chg >= 2.0:   return "#1b7e3c"
    if chg >= 1.0:   return "#2ea043"
    if chg >= 0.3:   return "#2ea04399"
    if chg > -0.3:   return "#3a4a5e"
    if chg > -1.0:   return "#c6313199"
    if chg > -2.0:   return "#e23b3b"
    return "#b71c1c"


def run(prices: dict = None, risk: dict = None, fear_greed: dict = None) -> dict:
    try:
        import yfinance as yf
    except Exception:
        return {"available": False, "reason": "yfinance不在"}

    results = []
    for sym, name in TOPIX17:
        try:
            h = yf.Ticker(sym).history(period="5d")
            if len(h) >= 2:
                chg1 = (h["Close"].iloc[-1] / h["Close"].iloc[-2] - 1) * 100
                chg5 = (h["Close"].iloc[-1] / h["Close"].iloc[0] - 1) * 100
                results.append({
                    "name": name, "code": sym.split(".")[0],
                    "chg": round(chg1, 2), "chg5": round(chg5, 2),
                })
            time.sleep(0.15)
        except Exception:
            pass

    if len(results) < 5:
        return {"available": False, "reason": "データ不足"}

    results.sort(key=lambda x: x["chg"], reverse=True)
    result = {
        "available": True,
        "sectors": results,
        "strong": results[:3],
        "weak": results[-3:][::-1],
        "count": len(results),
    }
    result["html"] = get_html(result)
    result["telegram_message"] = build_telegram_message(result)
    logger.info(f"✅ 業種ヒートマップ: {len(results)}業種 / 最強={results[0]['name']}")
    return result


def build_telegram_message(result: dict) -> str:
    if not result.get("available"):
        return ""
    lines = ["🗺 *業種ヒートマップ（日本株）*", "", "🟢 買われている業種："]
    for s in result["strong"]:
        lines.append(f"・{s['name']}　{s['chg']:+.1f}%")
    lines.append("")
    lines.append("🔴 売られている業種：")
    for s in result["weak"]:
        lines.append(f"・{s['name']}　{s['chg']:+.1f}%")
    lines.append("")
    lines.append("※その日の傾向です（前日比）")
    return "\n".join(lines)


def get_html(result: dict) -> str:
    if not result or not result.get("available"):
        return ""
    cells = ""
    for s in result["sectors"]:
        bg = _color(s["chg"])
        chg = s["chg"]
        tc = "#ffffff" if abs(chg) >= 0.3 else "#aebed4"
        cells += f'''
<div style="background:{bg};border-radius:8px;padding:10px 8px;text-align:center;min-height:54px;display:flex;flex-direction:column;justify-content:center;">
  <div style="font-size:0.74em;color:{tc};font-weight:700;line-height:1.2;">{s["name"]}</div>
  <div style="font-size:0.92em;color:{tc};font-weight:900;margin-top:2px;">{chg:+.1f}%</div>
</div>'''
    return f'''
<div style="background:#0f1623;border:1px solid #1e2d42;border-radius:14px;padding:16px;">
  <div style="font-size:0.75em;color:#7a8fa8;margin-bottom:10px;">
    東証17業種ETFの前日比。🟢緑＝買われている業種・🔴赤＝売られている業種（濃いほど勢いが強い）
  </div>
  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:6px;">
    {cells}
  </div>
</div>'''


if __name__ == "__main__":
    r = run()
    out = []
    if r.get("available"):
        out.append(f"=== 業種ヒートマップ（{r['count']}業種）===")
        for s in r["sectors"]:
            bar = "🟢" if s["chg"] > 0.3 else "🔴" if s["chg"] < -0.3 else "⚪"
            out.append(f"{bar} {s['name']}: {s['chg']:+.2f}% (5日{s['chg5']:+.1f}%)")
    else:
        out.append(f"取得失敗: {r.get('reason','')}")
    text = "\n".join(out)
    try:
        print(text)
    except UnicodeEncodeError:
        with open("sh_output.txt", "w", encoding="utf-8") as f:
            f.write(text)
        print("sh_output.txt に保存しました")
