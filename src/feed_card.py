"""
GANESHA MARKET FEED（Step FEED）— レポートの一番上に置くニュース面

構成（オーナー提示の見本に合わせた）:
  ヘッダー（日付・曜日・時間帯・重要度★）
  → 大きなチャート＋出典
  → 📌 3秒で結論
  → 主要指標3つ（日経・TOPIX・ドル円。それぞれ小チャート＋値＋%）
  → 市場全体の数字（売買代金・値上がり・値下がり）
  → 📋 なぜ動いたのか ①②③（図＋小見出し＋要約＋出典）
  → 💱 為替・金利・資金の流れ
  → 🏦 日銀・政府・政策
  → 🐊 違う角度から分析すると？
  → 🎯 これからの3つの筋書き
  → 🐘 最後のおさらい
  → 📚 出典 ／ 🔍 この記事の作られ方

■ 画像について（見本から変えた点）
  見本は「世界の株価」等のチャート画像を引用する案だったが、**自分で描く**。
  理由は `src/feed_visuals.py` の冒頭に書いた3点:
  相手のサーバーに負担をかける／先方のURL変更で壊れる／本文の数字と食い違っても
  気づけない。自前のSVGなら実データと必ず一致し、壊れない。
  写真は使わない（当日の現場写真を用意する手段が無く、関係のない写真を
  その日の写真のように並べるのは数字の捏造と同じ種類の嘘になる）。

■ 文字の大きさ・色は内容で変える
  重要度が高い日は見出しを大きく・強い色に、静かな日は小さく落ち着いた色にする。
  毎日同じ見た目だと「今日は普通の日か」が一目で分からないため。

■ 同じ図を二度出さない
  図は「その場所でしか言えないこと」を示すものだけを置く。
  飾りのために同じ絵を繰り返すと、読む人は図を見なくなる。

Gemini は使わない（渡された解釈を並べるだけ）。
"""
from src.utils import setup_logger, get_jst_now
from src import feed_visuals as V

logger = setup_logger("feed_card")

_CARD = "rgba(255,255,255,0.045)"
_LINE = "rgba(255,255,255,0.10)"
_TEXT, _DIM = "#eaf0fa", "#8a99ae"
_UP, _DOWN = "#2fd98a", "#ff4d63"
_ACC, _WARN = "#6aa9ff", "#ffc24d"

_WD = "月火水木金土日"


# ── 小物 ────────────────────────────────────────────────
def _b(t) -> str:
    """文中の **強調** を太字タグに直す（HTMLでは星印がそのまま出るため）。"""
    out, bold = [], False
    for part in str(t or "").split("**"):
        out.append(part if not bold else "<b>" + part + "</b>")
        bold = not bold
    return "".join(out)


def _n(v, dp=2, default=None):
    """数値のときだけ書式を当てる。None を 0 と書かない。"""
    if isinstance(v, (int, float)) and v == v:
        return f"{v:,.{dp}f}"
    return default


def _q(prices, sym):
    d = (prices or {}).get(sym) or {}
    c = d.get("change_pct")
    if not isinstance(c, (int, float)) or c != c:
        return None
    return {"v": d.get("latest"), "c": c, "src": d.get("source", "")}


def _breadth(internals):
    """値下がり銘柄の割合（0〜1）。数えられなければ None。"""
    a, d = (internals or {}).get("advancing"), (internals or {}).get("declining")
    if not (isinstance(a, (int, float)) and isinstance(d, (int, float))):
        return None
    return (d / (a + d)) if (a + d) > 0 else None


def _importance(nk_chg, score, nvi_pct, dec_ratio=None) -> int:
    """重要度1〜5。読む前に「今日は普通の日か」が分かるようにする。

    勘で決めず、実際に効くものだけで決める:
      値動きの大きさ／売り買いの広がり／地合いスコア／恐怖指数の位置
    """
    pts = 0
    a = abs(nk_chg or 0)
    pts += 3 if a >= 3.0 else 2 if a >= 1.5 else 1 if a >= 0.8 else 0
    if isinstance(dec_ratio, (int, float)):
        one = max(dec_ratio, 1 - dec_ratio)
        pts += 2 if one >= 0.85 else 1 if one >= 0.70 else 0
    s = abs(score or 0)
    pts += 2 if s >= 12 else 1 if s >= 6 else 0
    if isinstance(nvi_pct, (int, float)):
        pts += 2 if nvi_pct >= 95 else 1 if nvi_pct >= 90 else 0
    return max(1, min(5, pts))


def _tone(imp, nk_chg):
    """重要度と向きで、見出しの大きさ・色・背景の強さを決める。

    ⚠️ 毎日同じ見た目にしない。見た瞬間に「今日は普通の日か」が
       分かることが、文章を読むより先に効く。
    """
    col = _DOWN if (nk_chg or 0) < 0 else _UP
    table = {
        5: (22, 900, col, .22, "大きく動いた日", _DOWN),
        4: (20, 900, col, .16, "動きの大きい日", _DOWN),
        3: (18, 800, col, .11, "やや動いた日", _WARN),
        2: (16.5, 800, _TEXT, .07, "落ち着いた日", _ACC),
        1: (15.5, 700, _TEXT, .05, "静かな日", _DIM),
    }
    sz, wt, c, g, lb, bd = table.get(imp, table[1])
    return {"size": sz, "weight": wt, "col": c, "glow": g, "label": lb, "badge": bd}


def _sec(title, body, note="", src="") -> str:
    """見出し＋中身＋（注記）＋（出典）の1区画。"""
    t = (f'<div style="font-size:13px;font-weight:800;color:{_TEXT};'
         f'margin-bottom:8px">{title}</div>') if title else ""
    n = (f'<div style="font-size:10px;color:{_DIM};margin-top:6px;line-height:1.75">'
         f'{_b(note)}</div>') if note else ""
    sc = (f'<div style="font-size:9px;color:{_DIM};opacity:.75;margin-top:4px">'
          f'出典: {src}</div>') if src else ""
    return f'<div style="margin:18px 0 0">{t}{body}{n}{sc}</div>'


def _box(inner, pad="10px 14px") -> str:
    return (f'<div style="background:{_CARD};border:1px solid {_LINE};'
            f'border-radius:12px;padding:{pad}">{inner}</div>')


def _row(label, value, col=None, sub="") -> str:
    col = col or _TEXT
    s = (f'<div style="font-size:9.5px;color:{_DIM};padding:0 0 3px">{sub}</div>'
         ) if sub else ""
    return (f'<div style="padding:7px 0;border-bottom:1px solid {_LINE}">'
            f'<div style="display:flex;align-items:baseline;gap:8px">'
            f'<span style="font-size:11.5px;font-weight:700;color:{_TEXT};flex:1">{label}</span>'
            f'<span class="num" style="font-size:13px;font-weight:800;color:{col}">{value}</span>'
            f'</div>{s}</div>')


def _links(items, icon="📰", n=3) -> str:
    return "".join(
        f'<div style="padding:5px 0;border-bottom:1px solid {_LINE}">'
        f'<a href="{x["url"]}" target="_blank" rel="noopener" '
        f'style="font-size:10.5px;color:{_ACC};text-decoration:none">'
        f'{x.get("label", icon)} {str(x.get("title", "")).split(" - ")[0][:52]}</a>'
        f'<span style="font-size:9px;color:{_DIM}"> ／ {x.get("source", "")}</span>'
        f'</div>' for x in items[:n])


# ── 見出し ──────────────────────────────────────────────
def _mo_tag(vals) -> str:
    """小チャートの下に「1ヶ月で何%」を書く。

    ⚠️ 小チャートは1ヶ月の形なので色も1ヶ月の向きで決まる。
       ところが数字は当日の前日比なので、**緑のグラフの上に赤い-0.19%**
       という見た目が起きる（実際に起きた）。
       どちらの期間の話か分かるよう、1ヶ月の変化率を必ず添える。
    """
    vals = [v for v in (vals or []) if isinstance(v, (int, float))]
    if len(vals) < 3 or not vals[0]:
        return ""
    c = (vals[-1] / vals[0] - 1) * 100
    col = _UP if c >= 0 else _DOWN
    return (f'<div style="font-size:9px;color:{col};text-align:right;margin-top:1px">'
            f'1ヶ月 {c:+.1f}%</div>')


def _headline(nk, internals):
    if not nk:
        return "📊 今日の市場まとめ"
    c, r = nk["c"], _breadth(internals)
    wide_dn = isinstance(r, (int, float)) and r >= 0.70
    wide_up = isinstance(r, (int, float)) and r <= 0.30
    if c <= -3.0:
        return f"📉 日経平均 {abs(c):.2f}% の大幅安！一体何が起こった？"
    if c <= -1.5:
        return f"📉 日経平均が大きく下げました（{c:+.2f}%）"
    if c >= 3.0:
        return f"📈 日経平均 {c:.2f}% の大幅高！一体何が起こった？"
    if c >= 1.5:
        return f"📈 日経平均が大きく上げました（{c:+.2f}%）"
    if c <= -0.5 and wide_dn:
        return f"📉 日経は{c:+.2f}%でも、{r*100:.0f}%の銘柄が下げた1日"
    if wide_dn:
        return f"📊 指数は小動きでも、{r*100:.0f}%の銘柄が下げた1日（{c:+.2f}%）"
    if wide_up:
        return f"📊 指数は小動きでも、{(1-r)*100:.0f}%の銘柄が上げた1日（{c:+.2f}%）"
    return f"📊 今日の市場まとめ（日経 {c:+.2f}%）"


# ── ①②③ なぜ動いたか ──────────────────────────────────
def _chain(prices, internals, sector_ranking, hist):
    """その日の実際の値動きから連鎖を組み立てる。推測は書かない。"""
    out = []

    us = [(s, nm) for s, nm in (("^GSPC", "S&P500"), ("^IXIC", "NASDAQ"),
                                ("^SOX", "半導体SOX")) if _q(prices, s)]
    if us:
        cs = [_q(prices, s)["c"] for s, _ in us]
        txt = "　".join(f"{nm} {_q(prices, s)['c']:+.2f}%" for s, nm in us)
        if min(cs) <= -1.0:
            note = ("米国株が下げており、日本株にも売りが波及しやすい地合いでした。"
                    "特に半導体は日本の同業にその日のうちに伝わります。")
        elif max(cs) >= 1.0:
            note = "米国株が上げており、日本株にも買いが入りやすい地合いでした。"
        else:
            note = ("米国株に大きな方向感は無く、**日本側の材料が効きやすい**"
                    "状態でした。")
        out.append({"title": "前の晩の米国市場", "val": txt, "note": note,
                    "src": "Yahoo Finance",
                    "vis": V.sparkline(hist.get("^GSPC") or [], w=96, h=42)})

    rk = (sector_ranking or {}).get("ranking") or []
    if len(rk) >= 4:
        up = "／".join(f"{x.get('name','')[:5]}{x.get('pct',0):+.1f}%" for x in rk[:2])
        dn = "／".join(f"{x.get('name','')[:5]}{x.get('pct',0):+.1f}%" for x in rk[-2:])
        spread = (rk[0].get("pct") or 0) - (rk[-1].get("pct") or 0)
        note = (f"強い業種と弱い業種の差は{spread:.1f}ポイント。"
                + ("差が大きく、相場全体というより**業種ごとの事情**で動いています。"
                   if spread >= 2.5 else
                   "差は小さく、業種を問わず同じ方向に動いています。"))
        out.append({"title": "日本株のどこが動いたか", "val": f"強い {up}／弱い {dn}",
                    "note": note, "src": "TOPIX-17 業種別ETF",
                    "vis": V.sector_bars(rk, w=160, top=3)})

    adv, dec = (internals or {}).get("advancing"), (internals or {}).get("declining")
    r = _breadth(internals)
    if r is not None:
        if r >= 0.80:
            note = (f"**{r*100:.0f}%の銘柄が下げました。**売りが市場全体に広がった形で、"
                    "一部の銘柄だけの話ではありません。")
        elif r >= 0.65:
            note = f"{r*100:.0f}%の銘柄が下げており、売りが広い範囲に及んでいます。"
        elif r <= 0.20:
            note = f"**{(1-r)*100:.0f}%の銘柄が上げました。**買いが市場全体に広がった形です。"
        elif r <= 0.35:
            note = f"{(1-r)*100:.0f}%の銘柄が上げており、買いが広い範囲に及んでいます。"
        else:
            note = "値上がりと値下がりが拮抗し、全体が一方向に動いたわけではありません。"
        trk = (internals or {}).get("trk25")
        if isinstance(trk, (int, float)):
            note += (f"　騰落レシオ25日は{trk:.0f}で、"
                     + ("**売られすぎの目安（70以下）に近づいています**。" if trk <= 80 else
                        "買われすぎの目安（120以上）に近づいています。" if trk >= 110 else
                        "普通の範囲です。"))
        out.append({"title": "売り買いの広がり",
                    "val": f"値上がり {adv:,.0f} ／ 値下がり {dec:,.0f}",
                    "note": note, "src": "nikkei225jp.com",
                    "vis": V.breadth_bar(adv, dec, w=160, h=36)})

    for i, c in enumerate(out, 1):
        c["no"] = i
    return out


# ── 本体 ────────────────────────────────────────────────
def build(prices=None, risk=None, internals=None, ai_summary=None,
          scenario=None, market_driver=None, news=None,
          sector_ranking=None, fear=None, policy=None, mode="morning") -> str:
    try:
        prices, internals = prices or {}, internals or {}
        nk = _q(prices, "^N225")
        if not nk and not internals.get("available"):
            return ""

        score = (risk or {}).get("score")
        nvi_pct = (fear or {}).get("nvi_pctile")
        nvi = internals.get("nvi")
        r = _breadth(internals)
        imp = _importance(nk["c"] if nk else None, score, nvi_pct, r)
        tone = _tone(imp, nk["c"] if nk else 0)
        now = get_jst_now()
        when = {"morning": "寄り付き前", "noon": "前場終了後",
                "evening": "大引け後", "test": "検証"}.get(mode, "")

        # 図に使う履歴。**1銘柄につき1回しか取らない**
        hist = {s: V.history(s) for s in ("^N225", "^TOPX", "USDJPY=X", "^GSPC")}
        if not hist.get("^TOPX"):
            hist["^TOPX"] = V.history("1306.T")      # TOPIX連動ETFで代替

        # ── ヘッダー ──
        stars = "★" * imp + "☆" * (5 - imp)
        head = (
            f'<div style="display:flex;align-items:center;gap:8px;'
            f'border-bottom:1px solid {_LINE};padding-bottom:10px">'
            f'<span style="font-size:16px">🐘</span>'
            f'<span style="font-size:12.5px;font-weight:900;letter-spacing:.07em;'
            f'color:{_TEXT}">MARKET FEED</span>'
            f'<span style="margin-left:auto;font-size:10px;font-weight:800;'
            f'color:{tone["badge"]};border:1px solid {tone["badge"]};'
            f'border-radius:20px;padding:2px 9px">{stars}</span></div>'
            f'<div style="font-size:10px;color:{_DIM};margin-top:7px">'
            f'{now.year}年{now.month}月{now.day}日（{_WD[now.weekday()]}）'
            f'{"　" + when if when else ""} ｜ 日本株・米国株'
            f'<span style="color:{tone["badge"]}">　{tone["label"]}</span></div>'
            f'<div style="font-size:{tone["size"]}px;font-weight:{tone["weight"]};'
            f'color:{tone["col"]};line-height:1.45;margin-top:9px;'
            f'letter-spacing:-.01em">{_b(_headline(nk, internals))}</div>')

        # ── 大きなチャート ──
        hero = ""
        if hist.get("^N225"):
            hero = _sec("", _box(V.big_chart(hist["^N225"], "日経平均 この1ヶ月", "1ヶ月"),
                                 pad="10px 10px 4px"),
                        src="Yahoo Finance（終値から自前で作図）")

        # ── 📌 3秒で結論 ──
        concl = ""
        for cand in ((ai_summary or {}).get("neutral_view"),
                     (market_driver or {}).get("summary")):
            if isinstance(cand, str) and cand.strip():
                concl = cand.strip()[:230]
                break
        ai_made = bool(concl)
        if len(concl) < 24 and nk:
            bits = [f"日経平均は{nk['c']:+.2f}%"]
            if isinstance(r, (int, float)):
                side = "下げ" if r >= .5 else "上げ"
                bits.append(f"{(r if r >= .5 else 1 - r)*100:.0f}%の銘柄が{side}ました")
            if isinstance(nvi, (int, float)) and isinstance(nvi_pct, (int, float)):
                if nvi_pct >= 90:
                    bits.append(f"恐怖指数は{nvi:.1f}と高く、値動きが荒くなりやすい状態です")
                elif nvi_pct <= 25:
                    bits.append(f"恐怖指数は{nvi:.1f}と低く、市場は落ち着いています")
            concl, ai_made = "。".join(bits) + "。", False
        concl_html = _sec(
            "📌 3秒で結論",
            _box(f'<div style="font-size:13.5px;line-height:1.9;color:{_TEXT}">'
                 f'{_b(concl)}</div>'),
            src="AIの要約（Gemini）" if ai_made else "当日の数値から自動生成") if concl else ""

        # ── 主要指標3つ ──
        cols = ""
        for sym, nm, dp, unit in (("^N225", "日経平均", 2, "円"),
                                  ("^TOPX", "TOPIX", 2, ""),
                                  ("USDJPY=X", "ドル円", 2, "円")):
            d = _q(prices, sym)
            if not d:
                continue
            col = _UP if d["c"] >= 0 else _DOWN
            cols += (
                f'<div style="flex:1;min-width:0;background:{_CARD};'
                f'border:1px solid {_LINE};border-radius:11px;padding:8px 9px">'
                f'<div style="font-size:9.5px;color:{_DIM}">{nm}</div>'
                f'<div class="num" style="font-size:13.5px;font-weight:900;color:{_TEXT};'
                f'margin-top:1px">{_n(d["v"], dp) or "—"}{unit}</div>'
                f'<div class="num" style="font-size:11px;font-weight:800;color:{col}">'
                f'{d["c"]:+.2f}%</div>'
                f'<div style="margin-top:5px">{V.sparkline(hist.get(sym) or [], w=96)}</div>'
                f'{_mo_tag(hist.get(sym))}</div>')
        idx_html = _sec("📈 主要指標（この1ヶ月の形）",
                        f'<div style="display:flex;gap:7px">{cols}</div>',
                        note="小さなグラフは**1ヶ月の値動きの形**です。"
                             "数字は最新値と前日比を表しています。",
                        src="日経平均・ドル円: Yahoo Finance ／ TOPIX: 株探") if cols else ""

        # ── 市場全体の数字 ──
        mkt = ""
        turn = internals.get("turnover_total")
        bits = []
        if isinstance(turn, (int, float)):
            bits.append(_row("東証の売買代金", f"{turn / 1e6:.2f}兆円", _ACC,
                             "東証全体（プライム＋スタンダード＋グロース）の合計"))
        adv, dec = internals.get("advancing"), internals.get("declining")
        if isinstance(adv, (int, float)) and isinstance(dec, (int, float)):
            bits.append(_row("値上がり銘柄", f"{adv:,.0f}銘柄", _UP))
            bits.append(_row("値下がり銘柄", f"{dec:,.0f}銘柄", _DOWN))
        if bits:
            mkt = _sec("🧮 市場全体の数字",
                       _box("".join(bits)
                            + f'<div style="margin-top:8px">{V.breadth_bar(adv, dec)}</div>'),
                       note="帯の幅がそのまま**値上がり・値下がりの割合**です。"
                            "売買代金が大きい日は、それだけ多くのお金が動いたということです。",
                       src="nikkei225jp.com（東証の公表値をまとめたもの）")

        # ── 📋 なぜ動いたのか ──
        chain_html = ""
        ch = _chain(prices, internals, sector_ranking, hist)
        if ch:
            rows = ""
            for c in ch:
                vis = (f'<div style="flex:0 0 104px">{c["vis"]}</div>'
                       ) if c.get("vis") else ""
                rows += (
                    f'<div style="display:flex;gap:11px;align-items:flex-start;'
                    f'padding:11px 0;border-bottom:1px solid {_LINE}">{vis}'
                    f'<div style="flex:1;min-width:0">'
                    f'<div style="display:flex;align-items:center;gap:6px">'
                    f'<span style="width:17px;height:17px;border-radius:6px;'
                    f'background:{_ACC};color:#06121f;font-size:10px;font-weight:900;'
                    f'display:inline-flex;align-items:center;justify-content:center">'
                    f'{c["no"]}</span>'
                    f'<span style="font-size:11.5px;font-weight:800;color:{_TEXT}">'
                    f'{c["title"]}</span></div>'
                    f'<div class="num" style="font-size:10.5px;color:{_ACC};'
                    f'margin-top:3px">{c["val"]}</div>'
                    f'<div style="font-size:10.5px;color:{_DIM};margin-top:3px;'
                    f'line-height:1.8">{_b(c["note"])}</div>'
                    f'<div style="font-size:9px;color:{_DIM};opacity:.7;margin-top:2px">'
                    f'出典: {c["src"]}</div></div></div>')
            chain_html = _sec(f"📋 なぜ動いたのか — {len(ch)}つの連鎖",
                              _box(rows, "4px 14px 8px"),
                              note="ここに並ぶのは**その日に実際に起きた値動き**だけです。"
                                   "解釈は下の「違う角度から」に分けてあります。")

        # ── 💱 為替・金利・資金の流れ ──
        fx_rows = ""
        for sym, nm, dp, unit, note in (
                ("USDJPY=X", "ドル円", 2, "円",
                 "円高は輸出企業の利益を押し下げ、円安は押し上げます"),
                ("^TNX", "米10年金利", 3, "%",
                 "金利が上がるほど、株より債券の魅力が増します")):
            d = _q(prices, sym)
            if d:
                fx_rows += _row(nm, f"{_n(d['v'], dp) or '—'}{unit}",
                                _UP if d["c"] >= 0 else _DOWN,
                                f"{d['c']:+.2f}%　{note}")
        jgb = internals.get("jgb10")
        if isinstance(jgb, (int, float)):
            fx_rows += _row("日本10年国債利回り", f"{jgb:.3f}%", _TEXT,
                            "日本の金利が上がると、銀行株には追い風・不動産には逆風")
        fx_html = ""
        if fx_rows:
            uj = hist.get("USDJPY=X") or []
            chart = (f'<div style="margin-top:9px">'
                     f'{V.sparkline(uj, w=300, h=46, strong=True)}</div>'
                     f'<div style="font-size:9px;color:{_DIM};text-align:center;'
                     f'margin-top:2px">ドル円 この1ヶ月</div>') if uj else ""
            fx_html = _sec("💱 為替・金利・資金の流れ", _box(fx_rows + chart),
                           src="Yahoo Finance")

        # ── 🏦 日銀・政府・政策 ──
        # ⚠️ policy_watch の返り値は {"fed": {...}, "boj": {...}} であって
        #    "current" というキーは無い。最初 current を読んでいたため
        #    **政策金利の数値が1つも出ていなかった**（ニュースだけが並んでいた）。
        #    こういう取り違えは例外にならず静かに空欄になるので、
        #    新しいデータを繋いだら必ず実データで表示を確認すること。
        # ⚠️ 1つの区画のデータが壊れていても**カード全体を落とさない**。
        #    渡されるのは外部データなので、形が変わることがある。
        pol_rows = ""
        _pol = policy if isinstance(policy, dict) else {}
        for key, icon in (("fed", "🇺🇸"), ("boj", "🇯🇵")):
            e = _pol.get(key)
            e = e if isinstance(e, dict) else {}
            rate = e.get("rate")
            if not isinstance(rate, (int, float)):
                continue
            d = e.get("direction") or ""
            since = e.get("days_since")
            sub = (f"前回の変更は{d}（{e.get('changed_on')}）。それから{since}日間そのまま"
                   if d and d != "据え置き" and since else
                   "この期間に変更はありません")
            col = _WARN if d == "利上げ" else _ACC if d == "利下げ" else _TEXT
            pol_rows += _row(f"{icon} {e.get('name', key)}", f"{rate:.2f}%", col, sub)
        pol_news = [n for n in (news or []) if isinstance(n, dict) and n.get("url")
                    and any(k in str(n.get("title", "")) + str(n.get("keyword", ""))
                            for k in ("日銀", "政府", "財務省", "政策金利", "利上げ",
                                      "利下げ", "FRB", "FOMC"))]
        if pol_news:
            pol_rows += f'<div style="margin-top:6px">{_links(pol_news, "🏦")}</div>'
        pol_html = _sec("🏦 日銀・政府・政策", _box(pol_rows),
                        note="金利を決めるのは日銀とFRBで、**株より先に為替が反応**します。"
                             "利上げは企業の借入コストを上げるので、株には逆風に"
                             "なりやすい話です。",
                        src="FRED（政策金利）／ Google News RSS") if pol_rows else ""

        # ── 🐊 違う角度から分析すると？ ──
        alt = []
        if nk and nk["c"] < 0 and (ai_summary or {}).get("bull_view"):
            alt.append(("🟢 下げた日でも、強気側はこう見る",
                        str(ai_summary["bull_view"])[:200], "AIの見立て（Gemini）"))
        elif nk and (ai_summary or {}).get("bear_view"):
            alt.append(("🔴 上げた日でも、弱気側はこう見る",
                        str(ai_summary["bear_view"])[:200], "AIの見立て（Gemini）"))
        trk = internals.get("trk25")
        if isinstance(trk, (int, float)):
            if trk <= 80:
                alt.append(("📉 売られすぎの目安に近い",
                            f"騰落レシオ25日は{trk:.0f}。70以下は「売られすぎ」と"
                            "言われる水準で、反発が起きやすい場面とされます。"
                            "ただし下げが続く相場では、70を割ったまま進むこともあります。",
                            "nikkei225jp.com"))
            elif trk >= 115:
                alt.append(("📈 買われすぎの目安に近い",
                            f"騰落レシオ25日は{trk:.0f}。120以上は「買われすぎ」と"
                            "言われ、高値づかみになりやすい場面とされます。",
                            "nikkei225jp.com"))
        if isinstance(nvi, (int, float)) and isinstance(nvi_pct, (int, float)) and nvi_pct >= 85:
            alt.append(("😱 恐怖指数が高いのは、悪い話だけではない",
                        f"日経VIは{nvi:.1f}（過去3年で上から{100 - nvi_pct:.0f}%）。"
                        "高いほど値動きは荒れますが、**恐怖が極まった後に底を打つ**"
                        "ことも多く、売り一辺倒とは限りません。"
                        "ただし「いつ」は誰にも分かりません。", "日経公式CSV"))
        alt_html = ""
        if alt:
            blocks = "".join(
                f'<div style="padding:9px 0;border-bottom:1px solid {_LINE}">'
                f'<div style="font-size:11.5px;font-weight:800;color:{_TEXT}">{t}</div>'
                f'<div style="font-size:11px;color:{_DIM};line-height:1.85;margin-top:3px">'
                f'{_b(x)}</div>'
                f'<div style="font-size:9px;color:{_DIM};opacity:.7;margin-top:2px">'
                f'出典: {sr}</div></div>' for t, x, sr in alt)
            gg = (f'<div style="margin-top:9px">'
                  f'{V.gauge(nvi_pct, "恐怖指数が過去3年のどこにいるか")}</div>'
                  if isinstance(nvi_pct, (int, float)) else "")
            alt_html = _sec("🐊 違う角度から分析すると？", _box(blocks + gg, "4px 14px 10px"),
                            note="**反対の見方をわざと並べています。**"
                                 "片方だけ読むと、見たい材料だけを信じてしまいます。")

        # ── 🎯 3シナリオ ──
        sc_html = ""
        scs = (scenario or {}).get("scenarios") or []
        if scs:
            icon = {"楽観": ("🟢", _UP), "基本": ("🟡", _WARN), "悲観": ("🔴", _DOWN)}
            rows = ""
            for s in scs[:3]:
                nm = str(s.get("name", ""))[:6]
                ic, cl = icon.get(nm, ("⚪", _DIM))
                pr = s.get("probability")
                bar = (f'<div style="height:4px;border-radius:3px;background:{cl};'
                       f'opacity:.75;width:{max(4, min(100, pr))}%;margin-top:3px"></div>'
                       if isinstance(pr, (int, float)) else "")
                rows += (
                    f'<div style="display:flex;gap:9px;padding:9px 0;'
                    f'border-bottom:1px solid {_LINE}">'
                    f'<div style="flex:0 0 64px"><span style="font-size:11.5px;'
                    f'font-weight:800;color:{cl}">{ic} {nm}</span>'
                    f'<div class="num" style="font-size:10px;color:{_DIM}">'
                    f'{f"{pr}%" if isinstance(pr, (int, float)) else ""}</div>{bar}</div>'
                    f'<div style="flex:1;font-size:11px;color:{_TEXT};line-height:1.8">'
                    f'{str(s.get("detail", ""))[:150]}</div></div>')
            sc_html = _sec("🎯 これからの3つの筋書き", _box(rows, "4px 14px 8px"),
                           note="確率はAIの見立てで、当たることが保証された数字では"
                                "ありません。「どれか1つが来る」ではなく"
                                "「この幅の中で動きやすい」と読んでください。",
                           src="AIの見立て（Gemini）")

        # ── 🐘 最後のおさらい ──
        recap = []
        if nk:
            recap.append(f"日経平均は **{_n(nk['v'], 2)}円（{nk['c']:+.2f}%）**")
        if isinstance(r, (int, float)):
            side = "下げ" if r >= .5 else "上げ"
            recap.append(f"{(r if r >= .5 else 1 - r)*100:.0f}%の銘柄が{side}た")
        if isinstance(turn, (int, float)):
            recap.append(f"東証の売買代金は **{turn / 1e6:.2f}兆円**")
        if isinstance(nvi, (int, float)):
            pos = (f"（過去3年で上から{100 - nvi_pct:.0f}%）"
                   if isinstance(nvi_pct, (int, float)) else "")
            recap.append(f"恐怖指数 日経VIは **{nvi:.1f}**{pos}")
        act = ("恐怖指数が高い日は、**同じ株数でも損得の振れ幅が大きくなります。**"
               "株数を減らす・損切りの逆指値を広めに置く・落ち着くまで待つ、"
               "のどれかを選ぶ場面です。"
               if isinstance(nvi_pct, (int, float)) and nvi_pct >= 85 else
               "大きく荒れてはいません。いつもどおりの株数で構いませんが、"
               "**決めた損切りの線は動かさない**ことだけ守ってください。")
        recap_html = _sec(
            "🐘 最後のおさらい",
            _box(f'<div style="font-size:12px;color:{_TEXT};line-height:2">'
                 + "<br>".join("・" + _b(x) for x in recap) + "</div>"
                 + f'<div style="font-size:11px;color:{_WARN};line-height:1.9;'
                   f'margin-top:9px;padding-top:9px;border-top:1px solid {_LINE}">'
                   f'{_b(act)}</div>')) if recap else ""

        # ── 📚 出典 ──
        picked = [n for n in (news or [])
                  if isinstance(n, dict) and n.get("url") and n.get("title")]
        picked.sort(key=lambda x: {"S": 0, "A": 1, "B": 2}.get(x.get("importance"), 3))
        # 政策の欄で既に出したものは繰り返さない
        shown = {n.get("url") for n in pol_news[:3]} if pol_news else set()
        rest = [n for n in picked if n.get("url") not in shown]
        src_html = _sec("📚 参考にしたニュース", _box(_links(rest, "📰", 5), "4px 14px 8px")
                        ) if rest else ""

        used = ["株価・為替: Yahoo Finance", "TOPIX: 株探"]
        if internals.get("available"):
            used.append("騰落・売買代金・PER・日経VI: nikkei225jp.com")
        if scs or (ai_summary or {}).get("bull_view"):
            used.append("見立て・筋書き: Gemini（AIの生成）")
        if picked:
            used.append("ニュース: Google News RSS")
        verify = _sec(
            "🔍 この記事の作られ方",
            f'<div style="font-size:10px;color:{_DIM};line-height:1.9">'
            + "／".join(used)
            + f'<br><b style="color:{_WARN}">グラフはすべて自前で描いています。</b>'
              'よそのチャート画像を借りると、相手のサーバーに負担をかけるうえ、'
              '先方のURLが変わった日に壊れ、本文の数字と食い違っても気づけません。'
              f'<br><b style="color:{_WARN}">写真は使っていません。</b>'
              '当日の現場写真を用意できないため、関係のない写真を'
              'その日の写真のように見せない方針です。'
              '<br>数字は自動取得したもので、取引所の一次データとの'
              '全項目照合はしていません。</div>')

        return (
            f'<div style="margin-bottom:18px;background:linear-gradient(180deg,'
            f'rgba(106,169,255,{tone["glow"]}),rgba(106,169,255,0) 170px);'
            f'border:1px solid {_LINE};border-radius:16px;padding:16px 16px 20px">'
            f'{head}{hero}{concl_html}{idx_html}{mkt}{chain_html}'
            f'{fx_html}{pol_html}{alt_html}{sc_html}{recap_html}{src_html}{verify}'
            f'</div>')
    except Exception:
        logger.error("フィードカードを作れませんでした", exc_info=True)
        return ""


# ══════════════════════════════════════════════════════════
# Telegram に「画像」として送る版
# ══════════════════════════════════════════════════════════
#
# Telegram は HTML も SVG も表示できない。文字だけの通知になる。
# ところが朝の通知は元から「画像＋キャプション＋ボタン」の形で送っているので、
# **その画像を MARKET FEED の見た目にすれば**、見本どおりのものが届く。
# HTML→PNG は note のカバー画像で既に使っている Playwright で行う。
#
# ⚠️ 全部を1枚に詰めない。Telegram は縦長の画像をチャット幅（実質400px程度）に
#    縮めて表示するため、縦に長いほど**文字が潰れて読めなくなる**。
#    横760・縦1400くらいに収まる分量だけ載せ、残りはレポートへ送る。
TG_W = 760                 # CSSの幅。device_scale_factor=2 で実寸1520px
_FONT = ("-apple-system,'Hiragino Kaku Gothic ProN','Noto Sans CJK JP',"
         "'Noto Sans JP','Yu Gothic UI',Meiryo,sans-serif")


def build_compact(prices=None, risk=None, internals=None, ai_summary=None,
                  market_driver=None, fear=None, mode="morning") -> str:
    """Telegram画像用の短い版。読めることを最優先にする。"""
    prices, internals = prices or {}, internals or {}
    nk = _q(prices, "^N225")
    if not nk and not internals.get("available"):
        return ""

    score = (risk or {}).get("score")
    nvi_pct = (fear or {}).get("nvi_pctile")
    nvi = internals.get("nvi")
    r = _breadth(internals)
    imp = _importance(nk["c"] if nk else None, score, nvi_pct, r)
    tone = _tone(imp, nk["c"] if nk else 0)
    now = get_jst_now()
    when = {"morning": "寄り付き前", "noon": "前場終了後",
            "evening": "大引け後", "test": "検証"}.get(mode, "")
    stars = "★" * imp + "☆" * (5 - imp)

    hist = {s: V.history(s) for s in ("^N225", "^TOPX", "USDJPY=X")}
    if not hist.get("^TOPX"):
        hist["^TOPX"] = V.history("1306.T")

    # 指標3つ
    cards = ""
    for sym, nm, dp, unit in (("^N225", "日経平均", 2, "円"),
                              ("^TOPX", "TOPIX", 2, ""),
                              ("USDJPY=X", "ドル円", 2, "円")):
        d = _q(prices, sym)
        if not d:
            continue
        col = _UP if d["c"] >= 0 else _DOWN
        cards += (
            f'<div style="flex:1;min-width:0;background:{_CARD};border:1px solid {_LINE};'
            f'border-radius:14px;padding:13px 14px">'
            f'<div style="font-size:15px;color:{_DIM}">{nm}</div>'
            f'<div class="num" style="font-size:25px;font-weight:900;color:{_TEXT};'
            f'margin-top:2px;letter-spacing:-.01em">{_n(d["v"], dp) or "—"}'
            f'<span style="font-size:15px">{unit}</span></div>'
            f'<div class="num" style="font-size:18px;font-weight:800;color:{col}">'
            f'{d["c"]:+.2f}%</div>'
            f'<div style="margin-top:7px">{V.sparkline(hist.get(sym) or [], w=150, h=46)}'
            # ⚠️ 小チャートは1ヶ月の形、上の%は当日の前日比。期間が違うので
            #    「緑の数字の下に赤いグラフ」が普通に起きる（実際に起きた）。
            #    レポート版では直してあったが、こちらに入れ忘れていた。
            f'</div>{_mo_tag(hist.get(sym))}</div>')

    # ── ローソク足（日経平均） ──
    # 折れ線は終値しか見せない。ローソクなら「その日どこまで行って戻されたか」
    # まで分かる。上ヒゲが長い日は高いところで売られたということで、
    # 終値だけ見ていると気づけない情報。
    candle_html = ""
    try:
        rows = V.ohlc("^N225")
        svg = V.candles(rows, w=700, h=196, label="日経平均", days=30)
        if svg:
            candle_html = (
                f'<div style="background:{_CARD};border:1px solid {_LINE};'
                f'border-radius:14px;padding:10px 12px 8px;margin-top:12px">'
                f'{svg}'
                f'<div style="font-size:11px;color:{_DIM};margin-top:2px">'
                f'緑＝その日上げた　赤＝下げた　／　細い線はその日の高値と安値'
                f'<span style="float:right">数値: Yahoo Finance ／ 作図: 市場AI秘書</span>'
                f'</div></div>')
    except Exception:
        logger.error("ローソク足を描けませんでした", exc_info=True)

    # 市場全体
    mkt = ""
    adv, dec = internals.get("advancing"), internals.get("declining")
    turn = internals.get("turnover_total")
    chips = []
    if isinstance(turn, (int, float)):
        chips.append(("東証の売買代金", f"{turn / 1e6:.2f}兆円", _ACC))
    if isinstance(adv, (int, float)):
        chips.append(("値上がり", f"{adv:,.0f}銘柄", _UP))
    if isinstance(dec, (int, float)):
        chips.append(("値下がり", f"{dec:,.0f}銘柄", _DOWN))
    if isinstance(nvi, (int, float)):
        pos = (f"上から{100 - nvi_pct:.0f}%"
               if isinstance(nvi_pct, (int, float)) else "")
        chips.append(("恐怖指数 日経VI", f"{nvi:.1f}" + (f"（{pos}）" if pos else ""), _WARN))
    if chips:
        inner = "".join(
            f'<div style="min-width:46%;flex:1;padding:7px 0">'
            f'<div style="font-size:14px;color:{_DIM}">{a}</div>'
            f'<div class="num" style="font-size:20px;font-weight:800;color:{c}">{b}</div>'
            f'</div>' for a, b, c in chips)
        bar = (f'<div style="margin-top:6px">{V.breadth_bar(adv, dec, w=700, h=34)}</div>'
               if isinstance(adv, (int, float)) and isinstance(dec, (int, float)) else "")
        mkt = (f'<div style="background:{_CARD};border:1px solid {_LINE};'
               f'border-radius:14px;padding:10px 16px 14px;margin-top:12px">'
               f'<div style="display:flex;flex-wrap:wrap;gap:0 20px">{inner}</div>'
               f'{bar}</div>')

    # 結論
    concl = ""
    for cand in ((ai_summary or {}).get("neutral_view"),
                 (market_driver or {}).get("summary")):
        if isinstance(cand, str) and cand.strip():
            concl = cand.strip()[:170]
            break
    if len(concl) < 24 and nk:
        bits = [f"日経平均は{nk['c']:+.2f}%"]
        if isinstance(r, (int, float)):
            side = "下げ" if r >= .5 else "上げ"
            bits.append(f"{(r if r >= .5 else 1 - r)*100:.0f}%の銘柄が{side}ました")
        concl = "。".join(bits) + "。"
    concl_html = (
        f'<div style="background:{_CARD};border:1px solid {_LINE};border-radius:14px;'
        f'padding:14px 16px;margin-top:12px">'
        f'<div style="font-size:15px;font-weight:800;color:{_TEXT};margin-bottom:6px">'
        f'📌 3秒で結論</div>'
        f'<div style="font-size:18px;line-height:1.8;color:{_TEXT}">{_b(concl)}</div>'
        f'</div>') if concl else ""

    # 今日の構え
    act = ("恐怖指数が高い日です。**同じ株数でも損得の振れ幅が大きくなります。**"
           "株数を減らす・損切りを広めに置く・待つ、のどれかを選ぶ場面。"
           if isinstance(nvi_pct, (int, float)) and nvi_pct >= 85 else
           "大きく荒れてはいません。いつもどおりで構いませんが、"
           "**決めた損切りの線は動かさない**ことだけ守ってください。")
    act_html = (
        f'<div style="border:1px solid {_WARN}55;background:{_WARN}12;border-radius:14px;'
        f'padding:13px 16px;margin-top:12px">'
        f'<div style="font-size:15px;font-weight:800;color:{_WARN};margin-bottom:5px">'
        f'🐘 今日の構え</div>'
        f'<div style="font-size:16px;line-height:1.8;color:{_TEXT}">{_b(act)}</div></div>')

    return (
        f'<div id="feed" style="width:{TG_W}px;background:#0b0e14;color:{_TEXT};'
        f'font-family:{_FONT};padding:22px 22px 20px;box-sizing:border-box">'
        f'<div style="background:linear-gradient(180deg,rgba(106,169,255,'
        f'{tone["glow"] + 0.05}),rgba(106,169,255,0) 200px);'
        f'border:1px solid {_LINE};border-radius:20px;padding:20px 20px 22px">'
        # ヘッダー
        f'<div style="display:flex;align-items:center;gap:10px;'
        f'border-bottom:1px solid {_LINE};padding-bottom:13px">'
        f'<span style="font-size:24px">🐘</span>'
        f'<span style="font-size:19px;font-weight:900;letter-spacing:.08em">MARKET FEED</span>'
        f'<span style="margin-left:auto;font-size:15px;font-weight:800;'
        f'color:{tone["badge"]};border:1.5px solid {tone["badge"]};border-radius:30px;'
        f'padding:3px 14px">{stars}</span></div>'
        f'<div style="font-size:14.5px;color:{_DIM};margin-top:11px">'
        f'{now.year}年{now.month}月{now.day}日（{_WD[now.weekday()]}）'
        f'{"　" + when if when else ""} ｜ 日本株・米国株'
        f'<span style="color:{tone["badge"]}">　{tone["label"]}</span></div>'
        # 見出し
        f'<div style="font-size:{tone["size"] + 10}px;font-weight:{tone["weight"]};'
        f'color:{tone["col"]};line-height:1.4;margin-top:11px;letter-spacing:-.015em">'
        f'{_b(_headline(nk, internals))}</div>'
        # 指標
        f'<div style="display:flex;gap:11px;margin-top:15px">{cards}</div>'
        f'{candle_html}'
        f'{mkt}{concl_html}{act_html}'
        f'<div style="font-size:13.5px;color:{_DIM};margin-top:14px;text-align:center">'
        f'👇 なぜ動いたかの連鎖・3シナリオ・チャートは下のボタンから'
        f'<br><span style="opacity:.7">グラフは自前作図／数値: Yahoo Finance・'
        f'nikkei225jp.com・株探</span></div>'
        f'</div></div>')


def render_png(html: str, out_path: str) -> bool:
    """HTMLを1枚のPNGにする。Playwrightが無ければ False（呼び出し側で代替へ）。

    ⚠️ `wait_until="networkidle"` は外部を読み込まないページでは待ち続けることがある。
       この図は外部URLを1つも使わないので `load` で十分。
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.info("playwright が無いため、従来のカード画像を使います")
        return False
    try:
        with sync_playwright() as pw:
            br = pw.chromium.launch(args=["--no-sandbox"])
            page = br.new_page(viewport={"width": TG_W, "height": 1200},
                               device_scale_factor=2)
            page.set_content(html, wait_until="load")
            page.locator("#feed").screenshot(path=out_path)
            br.close()
        return True
    except Exception as e:
        logger.warning(f"フィード画像の描画に失敗（従来のカードへ）: {e}")
        return False


def make_feed_image(out_path: str, **kw) -> str | None:
    """Telegram用のフィード画像を作ってパスを返す。作れなければ None。"""
    try:
        html = build_compact(**kw)
        if not html:
            return None
        return out_path if render_png(html, out_path) else None
    except Exception:
        logger.error("フィード画像を作れませんでした", exc_info=True)
        return None


if __name__ == "__main__":
    import io
    import sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    from dotenv import load_dotenv
    load_dotenv(".env")
    from src.fetch_prices import run as fp
    from src.indicators import calc_risk_score
    from src.nikkei_market_data import run as nd
    from src.fetch_news import run as fn
    from src.fear_watch import run as fw
    from src.sector_ranking_jp import run as srj
    from src.policy_watch import run as pw
    pr, fg = fp()
    html = build(prices=pr, risk=calc_risk_score(pr), internals=nd(), news=fn(),
                 fear=fw(), sector_ranking=srj(), policy=pw(), mode="evening")
    io.open("feed_preview.html", "w", encoding="utf-8").write(
        '<meta charset="utf-8"><meta name="viewport" content="width=device-width,'
        'initial-scale=1"><body style="background:#0b0e14;color:#eaf0fa;'
        'font-family:-apple-system,\'Hiragino Kaku Gothic ProN\',Meiryo,sans-serif;'
        'max-width:460px;margin:auto;padding:14px">'
        '<style>.num{font-variant-numeric:tabular-nums}a{color:#6aa9ff}</style>'
        + html + "</body>")
    print(f"{len(html):,}字 → feed_preview.html")
