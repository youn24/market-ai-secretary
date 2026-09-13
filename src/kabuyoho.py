"""
株予報（kabuyoho.jp）データ取得モジュール
アナリストの目標株価・レーティング・指標を無料の公開ページから取得する。

株予報の銘柄ページには指標がJSONで埋め込まれており、
  - TARGET_PRICE   : アナリストのコンセンサス目標株価
  - PER / PBR      : 予想PER・PBR
  - DPS_YEALD_EST  : 予想配当利回り
  - 52週高値・安値、1日/1週/1月/3月騰落率
が取れる。さらにページ本文から最新レーティングのテキストも拾う。

⚠️ APIキー不要。サイト構造変更で取れなくなる可能性あり（その場合は欠損扱い）。
   目標株価はアナリスト予想であり、株価を保証するものではない。
"""
import re
import time

import requests

from src.utils import setup_logger, BASE_DIR

logger = setup_logger("kabuyoho")

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ja",
}


def _load_watchlist():
    import json
    path = BASE_DIR / "data" / "watchlist.json"
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for s in data.get("stocks", []):
            if s.get("symbol"):
                out.append((s["symbol"].split(".")[0], s.get("name", "")))
    except Exception as e:
        logger.warning(f"watchlist読み込み失敗: {e}")
    return out


def _num(txt: str, key: str):
    """埋め込みJSONから数値を1つ取り出す"""
    m = re.search(rf'"{key}"\s*:\s*(-?[0-9.]+)', txt)
    if not m:
        return None
    try:
        v = float(m.group(1))
        return int(v) if v == int(v) else round(v, 2)
    except Exception:
        return None


def _extract_rating(txt: str) -> str:
    """ページ本文から最新レーティングのテキストを拾う"""
    # 例: 「レーティング中立を据置き、目標株価4,700円（米系大手証券）」
    m = re.search(r"(レーティング[^<]{0,60}?（[^<）]{0,20}）)", txt)
    if m:
        s = re.sub(r"\s+", " ", m.group(1)).strip()
        return s[:80]
    return ""


def fetch_kabuyoho(code: str) -> dict:
    """1銘柄の株予報データを取得"""
    code = str(code).split(".")[0]
    url = f"https://kabuyoho.jp/reportTarget?bcode={code}"
    try:
        r = requests.get(url, headers=_HEADERS, timeout=12)
        if r.status_code != 200:
            return {"available": False}
        txt = r.content.decode("utf-8", errors="replace")
    except Exception as e:
        logger.debug(f"株予報取得失敗[{code}]: {e}")
        return {"available": False}

    close   = _num(txt, "CLOSE_PRICE")
    target  = _num(txt, "TARGET_PRICE")
    per     = _num(txt, "PER")
    pbr     = _num(txt, "PBR")
    yield_  = _num(txt, "DPS_YEALD_EST")
    w52_hi  = _num(txt, "STOCK_PRICE_52W_HIGH")
    w52_lo  = _num(txt, "STOCK_PRICE_52W_LOW")
    chg_1w  = _num(txt, "DIFF_PRICE_1W")
    chg_1m  = _num(txt, "DIFF_PRICE_1M")
    chg_3m  = _num(txt, "DIFF_PRICE_3M")
    rating  = _extract_rating(txt)

    if close is None and target is None:
        return {"available": False}

    # 目標株価までの上値余地（%）
    upside = None
    if close and target:
        upside = round((target / close - 1) * 100, 1)
    # 52週レンジ内の位置（%）
    pos_52w = None
    if close and w52_hi and w52_lo and w52_hi > w52_lo:
        pos_52w = round((close - w52_lo) / (w52_hi - w52_lo) * 100, 0)

    return {
        "available": True,
        "code": code,
        "close": close,
        "target": target,
        "upside": upside,
        "per": per,
        "pbr": pbr,
        "yield": yield_,
        "w52_high": w52_hi,
        "w52_low": w52_lo,
        "pos_52w": pos_52w,
        "chg_1w": chg_1w,
        "chg_1m": chg_1m,
        "chg_3m": chg_3m,
        "rating": rating,
    }


def run(prices: dict = None, risk: dict = None, fear_greed: dict = None) -> dict:
    """ウォッチリスト全銘柄の株予報データを取得しランキング化"""
    results = []
    for code, name in _load_watchlist():
        d = fetch_kabuyoho(code)
        if d.get("available"):
            d["name"] = name
            results.append(d)
        time.sleep(0.3)

    if not results:
        return {"available": False, "reason": "取得失敗"}

    # 上値余地（目標株価まで）の大きい順
    with_upside = [r for r in results if r.get("upside") is not None]
    with_upside.sort(key=lambda x: x["upside"], reverse=True)

    result = {
        "available": True,
        "results": results,
        "ranked_upside": with_upside,
        "count": len(results),
    }
    result["html"] = get_html(result)
    result["telegram_message"] = build_telegram_message(result)
    logger.info(f"✅ 株予報: {len(results)}銘柄取得")
    return result


def build_telegram_message(result: dict) -> str:
    if not result.get("available"):
        return ""
    top = result.get("ranked_upside", [])[:6]
    lines = ["🎯 *アナリスト目標株価（株予報）*", "", "上値余地が大きい順："]
    for r in top:
        up = r.get("upside")
        up_s = f"+{up}%" if up and up > 0 else f"{up}%"
        tgt = f"{r['target']:,}円" if r.get("target") else "—"
        lines.append(f"・{r['name']}：目標{tgt}（余地{up_s}）")
    lines.append("")
    lines.append("※目標株価はアナリスト予想で、株価を保証しません")
    return "\n".join(lines)


def get_html(result: dict) -> str:
    if not result or not result.get("available"):
        return ""
    rows = ""
    for r in result.get("ranked_upside", [])[:20]:
        up = r.get("upside")
        up_c = "#3fb950" if (up or 0) > 0 else "#f44336"
        up_s = f"+{up}%" if up and up > 0 else (f"{up}%" if up is not None else "—")
        tgt = f"{r['target']:,}円" if r.get("target") else "—"
        cur = f"{r['close']:,}円" if r.get("close") else "—"
        yld = f"{r['yield']}%" if r.get("yield") else "—"
        per = r.get("per") or "—"
        pos = f"{r['pos_52w']:.0f}%" if r.get("pos_52w") is not None else "—"
        rating = f'<div style="font-size:0.72em;color:#7a8fa8;margin-top:2px;">📣 {r["rating"]}</div>' if r.get("rating") else ""
        rows += f'''
<div style="padding:10px 0;border-bottom:1px solid #1e2d42;">
  <div style="display:flex;align-items:center;gap:8px;">
    <div style="flex:1;font-weight:700;font-size:0.9em;">[{r["code"]}] {r["name"]}</div>
    <div style="text-align:right;">
      <div style="color:{up_c};font-weight:800;">{up_s}</div>
      <div style="font-size:0.66em;color:#7a8fa8;">上値余地</div>
    </div>
  </div>
  <div style="font-size:0.72em;color:#7a8fa8;margin-top:3px;">
    現在{cur} → 目標{tgt} ・ PER{per} ・ 配当{yld} ・ 52週内位置{pos}
  </div>
  {rating}
</div>'''
    return f'''
<div style="background:#0f1623;border:1px solid #1e2d42;border-radius:14px;padding:16px;">
  <div style="font-size:0.75em;color:#7a8fa8;margin-bottom:10px;">
    株予報（kabuyoho.jp）のアナリスト目標株価・指標。上値余地（目標株価までの差）が大きい順。予想であり保証ではありません
  </div>
  {rows}
</div>'''


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        d = fetch_kabuyoho(sys.argv[1])
        out = [f"=== 株予報 {sys.argv[1]} ==="]
        for k, v in d.items():
            out.append(f"  {k}: {v}")
        text = "\n".join(out)
    else:
        r = run()
        out = [f"=== 株予報ランキング（上値余地順・{r.get('count',0)}銘柄）==="]
        for x in r.get("ranked_upside", []):
            up = x.get("upside")
            out.append(f"{x['name']}({x['code']}): 現在{x.get('close')} 目標{x.get('target')} 余地{up}% PER{x.get('per')} 配当{x.get('yield')}%")
            if x.get("rating"):
                out.append(f"   {x['rating']}")
        text = "\n".join(out)
    try:
        print(text)
    except UnicodeEncodeError:
        with open("ky_output.txt", "w", encoding="utf-8") as f:
            f.write(text)
        print("ky_output.txt に保存しました")
