"""
フィード用の図版（Step FEED-V）— すべて自前で描くインラインSVG

なぜ外部サイトの画像を貼らないか:
  見本では「世界の株価」などのチャート画像を引用する案だったが、採らなかった。

  1. **他所の画像サーバーを直リンクすると、相手に通信費を負わせる**。
     毎朝ぶんが積み上がるうえ、先方がURLを変えた瞬間に全部壊れる。
     実際この案件では nikkei225jp.com がフォルダ名を1語変えただけで
     日経内部データが1ヶ月止まった。画像でも同じことが起きる。
  2. **自分で描けば数字と必ず一致する。** 他所のチャートは締め時刻も
     対象指数も違うことがあり、本文の数字と食い違っても気づけない。
  3. 著作権の問題が起きない。

  SVGにしているのは、画像ファイルを作らずHTMLに直接埋められるため。
  保存・配信の手間がなく、拡大してもぼやけず、ダークでも見える。

⚠️ ここで描く図は**実データそのもの**。見栄えのために値を丸めたり
   省いたりしない（グラフは数字より嘘をつきやすい）。
"""
import urllib.request
import json
from src.utils import setup_logger

logger = setup_logger("feed_visuals")

UP, DOWN, DIM, TEXT = "#2fd98a", "#ff4d63", "#8a99ae", "#eaf0fa"
ACC, WARN, LINE = "#6aa9ff", "#ffc24d", "rgba(255,255,255,0.10)"

_HEAD = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}


def history(symbol: str, rng: str = "1mo") -> list:
    """日次終値の並びを返す。取れなければ空。

    ⚠️ 前日終値の計算には使わない（`quote_util` の担当）。
       ここは「形を描く」ためだけに使う。
    """
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
           f"?interval=1d&range={rng}")
    try:
        req = urllib.request.Request(url, headers=_HEAD)
        res = json.load(urllib.request.urlopen(req, timeout=15))
        q = res["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        return [float(x) for x in q if isinstance(x, (int, float))]
    except Exception as e:
        logger.debug(f"履歴を取れませんでした [{symbol}]: {e}")
        return []


def sparkline(vals, w=108, h=34, strong=False) -> str:
    """小さな折れ線。上げ下げで色が変わる。"""
    vals = [v for v in (vals or []) if isinstance(v, (int, float))]
    if len(vals) < 3:
        return ""
    lo, hi = min(vals), max(vals)
    if hi == lo:
        hi = lo + 1
    col = UP if vals[-1] >= vals[0] else DOWN
    n = len(vals)
    pts = [(2 + (w - 4) * i / (n - 1), h - 3 - (h - 7) * (v - lo) / (hi - lo))
           for i, v in enumerate(vals)]
    d = " ".join(("M" if i == 0 else "L") + f"{x:.1f},{y:.1f}"
                 for i, (x, y) in enumerate(pts))
    area = d + f" L{pts[-1][0]:.1f},{h} L{pts[0][0]:.1f},{h} Z"
    gid = f"g{abs(hash((w, h, col, round(vals[-1], 3)))) % 99999}"
    return (f'<svg viewBox="0 0 {w} {h}" style="width:100%;height:auto;display:block" '
            f'preserveAspectRatio="none">'
            f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="{col}" stop-opacity=".28"/>'
            f'<stop offset="1" stop-color="{col}" stop-opacity="0"/></linearGradient></defs>'
            f'<path d="{area}" fill="url(#{gid})"/>'
            f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{2.2 if strong else 1.6}" '
            f'stroke-linejoin="round" stroke-linecap="round"/></svg>')


def big_chart(vals, title="", sub="", w=330, h=128) -> str:
    """見出しの下に置く大きめのチャート。高安と最新値を数字で添える。

    ⚠️ 軸の数字を省かない。形だけ見せると、2%の下げも20%の下げも
       同じ絵に見えてしまう。
    """
    vals = [v for v in (vals or []) if isinstance(v, (int, float))]
    if len(vals) < 5:
        return ""
    lo, hi = min(vals), max(vals)
    if hi == lo:
        hi = lo + 1
    col = UP if vals[-1] >= vals[0] else DOWN
    chg = (vals[-1] / vals[0] - 1) * 100
    x0, x1, y0, y1 = 42, w - 8, 12, h - 20
    n = len(vals)
    pt = [(x0 + (x1 - x0) * i / (n - 1), y1 - (y1 - y0) * (v - lo) / (hi - lo))
          for i, v in enumerate(vals)]
    d = " ".join(("M" if i == 0 else "L") + f"{x:.1f},{y:.1f}"
                 for i, (x, y) in enumerate(pt))
    gid = f"b{abs(hash((title, round(vals[-1], 3)))) % 99999}"
    grid = "".join(
        f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" stroke="{LINE}" stroke-width=".6"/>'
        f'<text x="{x0 - 5}" y="{y + 3:.1f}" fill="{DIM}" font-size="7.5" '
        f'text-anchor="end">{v:,.0f}</text>'
        for v, y in ((hi, y0), ((hi + lo) / 2, (y0 + y1) / 2), (lo, y1)))
    return (f'<svg viewBox="0 0 {w} {h}" style="width:100%;height:auto;display:block">'
            f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="{col}" stop-opacity=".30"/>'
            f'<stop offset="1" stop-color="{col}" stop-opacity="0"/></linearGradient></defs>'
            f'{grid}'
            f'<path d="{d} L{pt[-1][0]:.1f},{y1} L{pt[0][0]:.1f},{y1} Z" fill="url(#{gid})"/>'
            f'<path d="{d}" fill="none" stroke="{col}" stroke-width="2" '
            f'stroke-linejoin="round"/>'
            f'<circle cx="{pt[-1][0]:.1f}" cy="{pt[-1][1]:.1f}" r="3" fill="{col}"/>'
            f'<text x="{x0}" y="{h - 6}" fill="{DIM}" font-size="8">{title}</text>'
            f'<text x="{x1}" y="{h - 6}" fill="{col}" font-size="8.5" font-weight="700" '
            f'text-anchor="end">{chg:+.2f}%（{sub}）</text></svg>')


def breadth_bar(adv, dec, w=330, h=30) -> str:
    """値上がり／値下がりの帯。割合がそのまま幅になる。"""
    if not (isinstance(adv, (int, float)) and isinstance(dec, (int, float))):
        return ""
    tot = adv + dec
    if tot <= 0:
        return ""
    wa = (w - 2) * adv / tot
    return (f'<svg viewBox="0 0 {w} {h}" style="width:100%;height:auto;display:block">'
            f'<rect x="1" y="7" width="{wa:.1f}" height="15" rx="3" fill="{UP}" opacity=".85"/>'
            f'<rect x="{wa + 1:.1f}" y="7" width="{w - 2 - wa:.1f}" height="15" rx="3" '
            f'fill="{DOWN}" opacity=".85"/>'
            f'<text x="5" y="18.5" fill="#06121f" font-size="9.5" font-weight="800">'
            f'↑{adv:,.0f}</text>'
            f'<text x="{w - 5}" y="18.5" fill="#1a0309" font-size="9.5" font-weight="800" '
            f'text-anchor="end">↓{dec:,.0f}</text></svg>')


def gauge(pct, label="", w=330, h=46) -> str:
    """0〜100の中での位置を示す帯（恐怖指数の水準など）。"""
    if not isinstance(pct, (int, float)):
        return ""
    p = max(0.0, min(100.0, float(pct)))
    x = 6 + (w - 12) * p / 100
    gid = f"gg{abs(hash(label)) % 9999}"
    return (f'<svg viewBox="0 0 {w} {h}" style="width:100%;height:auto;display:block">'
            f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="1" y2="0">'
            f'<stop offset="0" stop-color="{ACC}"/><stop offset=".45" stop-color="{UP}"/>'
            f'<stop offset=".75" stop-color="{WARN}"/><stop offset="1" stop-color="{DOWN}"/>'
            f'</linearGradient></defs>'
            f'<rect x="6" y="14" width="{w - 12}" height="9" rx="4.5" fill="url(#{gid})" opacity=".85"/>'
            f'<rect x="{x - 1.6:.1f}" y="10" width="3.2" height="17" rx="1.6" fill="{TEXT}"/>'
            f'<text x="6" y="38" fill="{DIM}" font-size="8">低い</text>'
            f'<text x="{w / 2}" y="38" fill="{DIM}" font-size="8" text-anchor="middle">{label}</text>'
            f'<text x="{w - 6}" y="38" fill="{DIM}" font-size="8" text-anchor="end">高い</text></svg>')


def sector_bars(ranking, w=330, top=4) -> str:
    """業種別の強弱を横棒で。上位と下位を同じ目盛りで比べる。

    ⚠️ 最初の版では2つやらかした（実際に描いて気づいた）:
       1. 業種名を中央線のすぐ左に置いたため、**下げた業種は棒が名前に重なり**
          名前が読めなかった。名前は必ず左端の列に固定する。
       2. `rk[:4] + rk[-4:]` は一覧が8件未満だと**同じ業種を二度並べる**。
          件数で重なりを判定して取り直す。
    """
    rk = [r for r in (ranking or []) if isinstance(r, dict)
          and isinstance(r.get("pct"), (int, float))]
    if len(rk) < 4:
        return ""
    k = min(top, len(rk) // 2)          # 上位と下位が重ならない数にする
    picks = rk[:k] + rk[len(rk) - k:]
    m = max(abs(r["pct"]) for r in picks) or 1
    rowh, pad = 18, 5
    h = rowh * len(picks) + pad * 2
    name_w = 58                          # 名前の列（棒はここより右にしか出ない）
    mid = name_w + (w - name_w - 46) / 2
    out = []
    for i, r in enumerate(picks):
        y = pad + i * rowh
        v = r["pct"]
        bw = (w - name_w - 46) / 2 * abs(v) / m
        col = UP if v >= 0 else DOWN
        x = mid if v >= 0 else mid - bw
        nm = str(r.get("name", ""))[:5]
        out.append(
            f'<text x="{name_w - 6}" y="{y + 12}" fill="{TEXT}" font-size="9" '
            f'text-anchor="end">{nm}</text>'
            f'<rect x="{x:.1f}" y="{y + 4}" width="{max(bw, 1.5):.1f}" height="10" rx="2" '
            f'fill="{col}" opacity=".88"/>'
            f'<text x="{w - 4}" y="{y + 12}" fill="{col}" font-size="8.5" '
            f'font-weight="700" text-anchor="end">{v:+.1f}%</text>')
    return (f'<svg viewBox="0 0 {w} {h}" style="width:100%;height:auto;display:block">'
            f'<line x1="{mid:.1f}" y1="{pad}" x2="{mid:.1f}" y2="{h - pad}" '
            f'stroke="{LINE}" stroke-width="1"/>{"".join(out)}</svg>')


def donut(parts, w=104) -> str:
    """内訳の円グラフ（売買代金の中身など）。parts=[(名前,値,色), ...]"""
    parts = [(n, v, c) for n, v, c in (parts or [])
             if isinstance(v, (int, float)) and v > 0]
    if not parts:
        return ""
    import math
    tot = sum(v for _, v, _ in parts)
    cx = cy = w / 2
    r, th = w / 2 - 6, 13
    ang = -math.pi / 2
    segs = []
    for _, v, c in parts:
        a2 = ang + 2 * math.pi * v / tot
        large = 1 if (a2 - ang) > math.pi else 0
        x1, y1 = cx + r * math.cos(ang), cy + r * math.sin(ang)
        x2, y2 = cx + r * math.cos(a2), cy + r * math.sin(a2)
        segs.append(f'<path d="M{x1:.1f},{y1:.1f} A{r:.1f},{r:.1f} 0 {large} 1 '
                    f'{x2:.1f},{y2:.1f}" fill="none" stroke="{c}" stroke-width="{th}" '
                    f'opacity=".9"/>')
        ang = a2
    return (f'<svg viewBox="0 0 {w} {w}" style="width:100%;height:auto;display:block">'
            f'{"".join(segs)}</svg>')


if __name__ == "__main__":
    import io
    import sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    nk = history("^N225")
    print(f"日経 {len(nk)}日分")
    html = (big_chart(nk, "日経平均 1ヶ月", "1ヶ月")
            + sparkline(nk)
            + breadth_bar(401, 1110)
            + gauge(88, "過去3年の中での位置")
            + sector_bars([{"name": "電機", "pct": 1.3}, {"name": "機械", "pct": .5},
                           {"name": "商社", "pct": -1.3}, {"name": "銀行", "pct": -1.4},
                           {"name": "小売", "pct": -1.5}])
            + donut([("実売買", 4925148, ACC), ("空売り規制有", 3012856, WARN),
                     ("空売り規制無", 809020, DOWN)]))
    io.open("visual_preview.html", "w", encoding="utf-8").write(
        '<meta charset="utf-8"><body style="background:#0b0e14;max-width:380px;'
        'margin:auto;padding:14px">' + html + "</body>")
    print(f"{len(html):,}字 → visual_preview.html")
