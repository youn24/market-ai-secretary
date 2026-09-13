"""
日本株ADR（米国預託証券）データ取得モジュール
日本企業の株が「ニューヨーク市場で夜間どう取引されたか」を取得する。

ADRは日本の主要企業が米国市場に上場している株。日本時間の夜にNYで売買され、
その「ADR換算株価（円）」が翌日の東京市場の寄り付きの先行ヒントになる。
  ・ADR換算 > 東京終値 → NYで買われた → 今日の東京は買い先行になりやすい
  ・ADR換算 < 東京終値 → NYで売られた → 今日の東京は売り先行になりやすい

データは nikkei225jp.com が公開する _adr_all.js から直接取得（ブラウザ不要）：
  https://nikkei225jp.com/_data/_nfsDATA/adr/_adr_all.js
形式: A0[q]="東証コード_ティッカー_社名_..._ADR換算株価[8]_..._東京終値[20]_..."

⚠️ APIキー不要。サイト構造変更で取れなくなる可能性あり。
   ADRの乖離はあくまで寄り付きの目安で、その後の値動きを保証しない。
"""
import re

import requests

from src.utils import setup_logger

logger = setup_logger("adr_data")

_URL = "https://nikkei225jp.com/_data/_nfsDATA/adr/_adr_all.js"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://nikkei225jp.com/adr/",
}

# フィールド位置（_adr_all.js のJS構造を解析して確定）
F_CODE, F_TICKER, F_NAME_EN = 0, 1, 4
F_ADR_YEN, F_ADR_CHG_PCT = 8, 10     # ADR換算株価(円)・前日比%
F_ADR_USD, F_USD_CHG_PCT = 13, 15    # ADR価格(USD)・USD前日比%
F_VOLUME, F_USDJPY = 16, 18
F_TOKYO_CLOSE = 20                   # 東京終値(円)

# 主要銘柄（日経225の代表格・_adr_all.js 冒頭の Shu リスト相当）
_MAJORS = {
    "7203": "トヨタ", "6758": "ソニーG", "9984": "ソフトバンクG",
    "8306": "三菱UFJ", "6861": "キーエンス", "9983": "ファストリ",
    "6098": "リクルート", "8035": "東京エレク", "4063": "信越化学",
    "6594": "ニデック", "7974": "任天堂", "9433": "KDDI",
    "6857": "アドテスト", "6501": "日立", "7267": "ホンダ",
    "8316": "三井住友FG", "8411": "みずほFG", "4502": "武田",
    "6902": "デンソー", "7741": "HOYA",
}


def fetch_adr_raw() -> list:
    r = requests.get(_URL, headers=_HEADERS, timeout=15)
    r.raise_for_status()
    text = r.content.decode("utf-8", errors="replace")
    return re.findall(r'A0\[q\]="([^"]+)";', text)


def _f(v):
    try:
        return float(str(v).replace(",", ""))
    except (ValueError, TypeError):
        return None


def run(prices: dict = None, risk: dict = None, fear_greed: dict = None) -> dict:
    """ADRデータを取得し、東京終値との乖離率（夜間の値動き）でランキング化"""
    try:
        entries = fetch_adr_raw()
    except Exception as e:
        logger.warning(f"ADR取得失敗: {e}")
        return {"available": False, "reason": str(e)}

    items = []
    for e in entries:
        f = e.split("_")
        if len(f) <= F_TOKYO_CLOSE:
            continue
        code    = f[F_CODE]
        adr_yen = _f(f[F_ADR_YEN])
        tokyo   = _f(f[F_TOKYO_CLOSE])
        if not adr_yen or not tokyo or tokyo <= 0:
            continue
        div = round((adr_yen - tokyo) / tokyo * 100, 2)   # 乖離率（夜間の値動き）
        items.append({
            "code": code,
            "ticker": f[F_TICKER],
            "name": _MAJORS.get(code) or f[F_NAME_EN][:18],
            "is_major": code in _MAJORS,
            "adr_yen": round(adr_yen),
            "tokyo_close": round(tokyo),
            "divergence": div,
            "adr_usd": _f(f[F_ADR_USD]),
            "usd_chg": _f(f[F_USD_CHG_PCT]),
        })

    if len(items) < 10:
        return {"available": False, "reason": "データ不足"}

    items.sort(key=lambda x: x["divergence"], reverse=True)
    majors = [x for x in items if x["is_major"]]

    # 全体の平均乖離（地合いの先行指標）
    avg_div = round(sum(x["divergence"] for x in items) / len(items), 2)
    major_avg = round(sum(x["divergence"] for x in majors) / len(majors), 2) if majors else avg_div

    result = {
        "available": True,
        "count": len(items),
        "all": items,
        "majors": majors,
        "top": items[:6],          # 買い先行期待
        "bottom": items[-6:][::-1],  # 売り先行懸念
        "avg_divergence": avg_div,
        "major_avg_divergence": major_avg,
    }
    result["telegram_message"] = build_telegram_message(result)
    result["html"] = get_html(result)
    logger.info(f"✅ ADR: {len(items)}銘柄 / 主要平均乖離={major_avg:+.2f}%")
    return result


def _mood(avg: float) -> str:
    if avg >= 0.4:
        return "夜間のNYで買われた → 東京は買い先行になりやすい"
    if avg >= 0.1:
        return "夜間はやや買い優勢"
    if avg > -0.1:
        return "夜間はほぼ横ばい"
    if avg > -0.4:
        return "夜間はやや売り優勢"
    return "夜間のNYで売られた → 東京は売り先行に警戒"


def build_telegram_message(d: dict) -> str:
    if not d.get("available"):
        return ""
    avg = d.get("major_avg_divergence", 0)
    head = f"🌃 ADR夜間：主要株 平均{avg:+.2f}%（{'買い先行' if avg >= 0.1 else '売り先行' if avg <= -0.1 else '横ばい'}）"

    lines = [head, "", f"📊 {_mood(avg)}", ""]
    lines.append("🟢 NYで買われた（寄り高期待）：")
    for x in d["top"][:4]:
        lines.append(f"・{x['name']}（{x['code']}）{x['divergence']:+.2f}%")
    lines.append("")
    lines.append("🔴 NYで売られた（寄り安懸念）：")
    for x in d["bottom"][:4]:
        lines.append(f"・{x['name']}（{x['code']}）{x['divergence']:+.2f}%")
    lines.append("")
    lines.append("※ADR換算株価と東京終値の差。寄り付きの目安です")
    return "\n".join(lines)


def get_html(d: dict) -> str:
    if not d.get("available"):
        return ""
    avg = d.get("major_avg_divergence", 0)
    avg_c = "#3fb950" if avg >= 0.1 else ("#f85149" if avg <= -0.1 else "#8aa0c0")

    def row(x):
        c = "#3fb950" if x["divergence"] > 0 else ("#f85149" if x["divergence"] < 0 else "#8aa0c0")
        star = "⭐ " if x["is_major"] else ""
        return f'''
<div style="display:flex;align-items:center;gap:8px;padding:7px 0;border-bottom:1px solid #1e2d42;">
  <div style="flex:1;font-size:0.85em;">{star}<b>{x["name"]}</b> <span style="color:#7a8fa8;font-size:0.85em;">[{x["code"]}/{x["ticker"]}]</span></div>
  <div style="font-size:0.72em;color:#7a8fa8;text-align:right;">ADR {x["adr_yen"]:,}円<br>東京 {x["tokyo_close"]:,}円</div>
  <div style="width:62px;text-align:right;color:{c};font-weight:800;">{x["divergence"]:+.2f}%</div>
</div>'''

    top_rows = "".join(row(x) for x in d["top"])
    bot_rows = "".join(row(x) for x in d["bottom"])

    return f'''
<div style="background:#0d1117;border:1px solid #1e2d42;border-radius:14px;padding:16px;">
  <div style="font-size:0.75em;color:#7a8fa8;margin-bottom:10px;">
    日本株が夜間のNY市場でどう取引されたか（ADR換算株価 − 東京終値）。今日の東京の寄り付きの先行ヒント。
  </div>
  <div style="background:#0f1623;border:1px solid #1e2d42;border-radius:10px;padding:11px 13px;margin-bottom:12px;">
    <div style="font-size:0.7em;color:#7a8fa8;">主要株の夜間 平均乖離</div>
    <div style="font-size:1.4em;font-weight:800;color:{avg_c};margin-top:2px;">{avg:+.2f}%</div>
    <div style="font-size:0.72em;color:#7a8fa8;margin-top:2px;">{_mood(avg)}</div>
  </div>
  <div style="font-size:0.8em;color:#3fb950;font-weight:700;margin-bottom:2px;">🟢 NYで買われた（寄り高期待）</div>
  {top_rows}
  <div style="font-size:0.8em;color:#f85149;font-weight:700;margin:12px 0 2px;">🔴 NYで売られた（寄り安懸念）</div>
  {bot_rows}
  <div style="font-size:0.68em;color:#5a6b82;margin-top:10px;">⭐＝日経225の主要銘柄</div>
</div>'''


if __name__ == "__main__":
    r = run()
    out = []
    if r.get("available"):
        out.append(f"=== 日本株ADR（夜間NY・{r['count']}銘柄）===")
        out.append(f"主要株 平均乖離: {r['major_avg_divergence']:+.2f}%  {_mood(r['major_avg_divergence'])}")
        out.append("--- NYで買われた（寄り高期待）---")
        for x in r["top"]:
            out.append(f"  {x['name']}({x['code']}/{x['ticker']}): ADR換算{x['adr_yen']:,}円 vs 東京{x['tokyo_close']:,}円 = {x['divergence']:+.2f}%")
        out.append("--- NYで売られた（寄り安懸念）---")
        for x in r["bottom"]:
            out.append(f"  {x['name']}({x['code']}/{x['ticker']}): ADR換算{x['adr_yen']:,}円 vs 東京{x['tokyo_close']:,}円 = {x['divergence']:+.2f}%")
    else:
        out.append(f"取得失敗: {r.get('reason','')}")
    text = "\n".join(out)
    try:
        print(text)
    except UnicodeEncodeError:
        with open("adr_output.txt", "w", encoding="utf-8") as f:
            f.write(text)
        print("adr_output.txt に保存しました")
