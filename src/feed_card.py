"""
GANESHA MARKET FEED（Step FEED）— レポートの一番上に置く「結論カード」

なぜ必要か:
  公開レポートは区画が40以上あり、全部見るのは現実的でない。
  いちばん知りたい「今日は何が起きて、それはなぜで、どうすればいいか」が
  下の方まで探さないと分からなかった。

  そこで**最初の一枚**に、ニュースアプリのような形でまとめる:
    結論 → 数字 → なぜ（3つの連鎖）→ 為替金利 → 3シナリオ → 判断 → 出典

設計の決まりごと:
  1. **写真は使わない。** 見本には現場写真が入っていたが、当日の実際の写真を
     用意する手段が無い。関係のない画像を「その日の相場の写真」のように
     並べるのは、数字を捏造するのと同じ種類の嘘になる。
     代わりに数字そのものを大きく見せる。
  2. **「なぜ」は作り話にしない。** 連鎖はその日の実際の値動き
     （米国→日本→広がり）から組み立て、関連ニュースを出典として添える。
     AIの推測を混ぜるときは「AIの見立て」と明記して分ける。
  3. **出典を必ず付ける。** どの数字がどこから来たかを書く。
  4. 取れなかった項目は**その行ごと出さない**（「---」を並べない）。

Gemini は使わない（渡された ai_summary / scenario をそのまま並べるだけ）。
"""
from src.utils import setup_logger, get_jst_now

logger = setup_logger("feed_card")

# 配色（design_ai と揃える）
_BG, _CARD = "#0b0e14", "rgba(255,255,255,0.045)"
_LINE = "rgba(255,255,255,0.10)"
_TEXT, _DIM = "#eaf0fa", "#8a99ae"
_UP, _DOWN = "#2fd98a", "#ff4d63"
_ACC, _WARN = "#6aa9ff", "#ffc24d"


def _b(t) -> str:
    """文中の **強調** を太字タグに直す。

    ⚠️ 説明文は Telegram と同じ気持ちで `**…**` と書きがちだが、
       HTMLではそのまま星印が表示される（実際に一度出してしまった）。
       文を書く側が気にせず済むよう、出口で一括変換する。
    """
    t = str(t or "")
    out, bold = [], False
    for part in t.split("**"):
        out.append(part if not bold else "<b>" + part + "</b>")
        bold = not bold
    return "".join(out)


def _n(v, dp=2, default=None):
    """数値のときだけ書式を当てる。None を '0' と書かない。"""
    if isinstance(v, (int, float)) and v == v:
        return f"{v:,.{dp}f}"
    return default


def _chg(prices, sym):
    d = (prices or {}).get(sym) or {}
    v, c = d.get("latest"), d.get("change_pct")
    if not isinstance(c, (int, float)):
        return None
    return {"v": v, "c": c}


def _breadth(internals):
    """値下がり銘柄の割合（0〜1）。数えられなければ None。

    ⚠️ 「値上がり何銘柄・値下がり何銘柄」は数が大きくて比べにくい。
       割合に直すと「7割が下げた日」と一目で分かる。
    """
    adv = (internals or {}).get("advancing")
    dec = (internals or {}).get("declining")
    if not (isinstance(adv, (int, float)) and isinstance(dec, (int, float))):
        return None
    tot = adv + dec
    return (dec / tot) if tot > 0 else None


def _importance(nk_chg, score, nvi_pct, dec_ratio=None) -> int:
    """重要度1〜5。読む前に「今日は普通の日か」が分かるようにする。

    ⚠️ 勘で決めない。実際に効くものだけで決める:
       ・日経の値動きの大きさ（1.5%超は年に数えるほど）
       ・**売り買いの広がり**（指数が小さくても8割が下げた日は普通ではない）
       ・地合いスコアの強さ
       ・恐怖指数が過去の中でどこにいるか
    """
    pts = 0
    a = abs(nk_chg or 0)
    pts += 3 if a >= 3.0 else 2 if a >= 1.5 else 1 if a >= 0.8 else 0
    if isinstance(dec_ratio, (int, float)):
        one_side = max(dec_ratio, 1 - dec_ratio)
        pts += 2 if one_side >= 0.85 else 1 if one_side >= 0.70 else 0
    s = abs(score or 0)
    pts += 2 if s >= 12 else 1 if s >= 6 else 0
    if isinstance(nvi_pct, (int, float)):
        pts += 2 if nvi_pct >= 95 else 1 if nvi_pct >= 90 else 0
    return max(1, min(5, pts))


def _headline(nk, internals) -> tuple:
    """見出しと、その日の性格を表す絵文字。"""
    if not nk:
        return "📊 今日の市場まとめ", "📊"
    c = nk["c"]
    v = _n(nk["v"], 0) or "—"
    r = _breadth(internals)
    wide_dn = isinstance(r, (int, float)) and r >= 0.70
    wide_up = isinstance(r, (int, float)) and r <= 0.30
    if c <= -3.0:
        return f"📉 日経平均 {abs(c):.2f}% の大幅安！何が起きた？", "📉"
    if c <= -1.5:
        return f"📉 日経平均が大きく下げました（{c:+.2f}%）", "📉"
    if c <= -0.5 and wide_dn:
        return (f"📉 日経は{c:+.2f}%でも、{r*100:.0f}%の銘柄が下げた1日", "📉")
    if c >= 3.0:
        return f"📈 日経平均 {c:.2f}% の大幅高！何が起きた？", "📈"
    if c >= 1.5:
        return f"📈 日経平均が大きく上げました（{c:+.2f}%）", "📈"
    if wide_dn:
        return (f"📊 指数は小動きでも、{r*100:.0f}%の銘柄が下げた1日（{c:+.2f}%）", "📊")
    if wide_up:
        return (f"📊 指数は小動きでも、{(1-r)*100:.0f}%の銘柄が上げた1日（{c:+.2f}%）", "📊")
    return f"📊 今日の市場まとめ（日経 {c:+.2f}%）", "📊"


def _chain(prices, internals, sector_ranking) -> list:
    """「なぜ動いたか」を**その日の実際の値動き**から3つの連鎖に組み立てる。

    ⚠️ ここに推測を書かない。書くのは起きた事実だけ。
       解釈は下の「AIの見立て」に分けてある。
    """
    out = []

    # ① 海外（前の晩）で何が起きたか
    us = [(s, nm) for s, nm in (("^GSPC", "S&P500"), ("^IXIC", "NASDAQ"),
                                ("^SOX", "半導体SOX")) if _chg(prices, s)]
    if us:
        parts = []
        for s, nm in us:
            d = _chg(prices, s)
            parts.append(f"{nm} {d['c']:+.2f}%")
        worst = min((_chg(prices, s)["c"] for s, _ in us))
        best = max((_chg(prices, s)["c"] for s, _ in us))
        if worst <= -1.0:
            note = "米国株が下げており、日本株にも売りが波及しやすい地合いでした。"
        elif best >= 1.0:
            note = "米国株が上げており、日本株にも買いが入りやすい地合いでした。"
        else:
            note = "米国株は大きな方向感が無く、日本固有の材料が効きやすい状態でした。"
        out.append({"title": "前の晩の米国市場",
                    "val": "　".join(parts), "note": note, "src": "Yahoo Finance"})

    # ② 日本への波及（業種のばらつき）
    rk = (sector_ranking or {}).get("ranking") or []
    if len(rk) >= 6:
        up = "／".join(f"{x.get('name','')[:6]} {x.get('pct',0):+.1f}%" for x in rk[:2])
        dn = "／".join(f"{x.get('name','')[:6]} {x.get('pct',0):+.1f}%" for x in rk[-2:])
        out.append({"title": "日本株のどこが動いたか",
                    "val": f"強い: {up}　弱い: {dn}",
                    "note": "業種ごとの差が大きいほど、相場全体ではなく"
                            "特定の業種の事情で動いた可能性が高くなります。",
                    "src": "TOPIX-17 業種別ETF"})

    # ③ 広がり（売りが全体に及んだか）
    adv, dec = (internals or {}).get("advancing"), (internals or {}).get("declining")
    r = _breadth(internals)
    if isinstance(adv, (int, float)) and isinstance(dec, (int, float)) and r is not None:
        tot = adv + dec
        # ⚠️ 「値下がりが値上がりの3倍」を基準にすると、401対1,110（=73%が下げ）
        #    という明らかに一方的な日まで「拮抗」と書いてしまっていた。
        #    数ではなく**割合**で判定する。
        if r >= 0.80:
            note = (f"**{r*100:.0f}%の銘柄が下げました。**売りが市場全体に広がった形で、"
                    "一部の銘柄だけの話ではありません。")
        elif r >= 0.65:
            note = (f"{r*100:.0f}%の銘柄が下げており、売りが広い範囲に及んでいます。")
        elif r <= 0.20:
            note = f"**{(1-r)*100:.0f}%の銘柄が上げました。**買いが市場全体に広がった形です。"
        elif r <= 0.35:
            note = f"{(1-r)*100:.0f}%の銘柄が上げており、買いが広い範囲に及んでいます。"
        else:
            note = ("値上がりと値下がりが拮抗しており、全体が一方向に"
                    "動いたわけではありません。")
        trk = (internals or {}).get("trk25")
        extra = f"　騰落レシオ25日 {trk:.0f}" if isinstance(trk, (int, float)) else ""
        out.append({"title": "売り買いの広がり",
                    "val": f"値上がり {adv:,.0f}銘柄 ／ 値下がり {dec:,.0f}銘柄"
                           f"（全{tot:,.0f}）{extra}",
                    "note": note, "src": "nikkei225jp.com"})
    # ⚠️ 番号を固定で持たせると、取れなかった項目があるときに
    #    「1・3」と飛んで、読む人に「2はどこ？」と思わせる。通し番号にする。
    for i, c in enumerate(out, 1):
        c["no"] = i
    return out


def _sec(title, body, note="") -> str:
    n = (f'<div style="font-size:10px;color:{_DIM};margin-top:6px;'
         f'line-height:1.7">{_b(note)}</div>') if note else ""
    return (f'<div style="margin:16px 0 0">'
            f'<div style="font-size:12.5px;font-weight:800;color:{_TEXT};'
            f'margin-bottom:8px">{title}</div>{body}{n}</div>')


def build(prices=None, risk=None, internals=None, ai_summary=None,
          scenario=None, market_driver=None, news=None,
          sector_ranking=None, fear=None, mode="morning") -> str:
    """フィードカードのHTMLを返す。出せる材料が無ければ空文字。"""
    try:
        prices = prices or {}
        nk = _chg(prices, "^N225")
        internals = internals or {}
        score = (risk or {}).get("score")
        nvi_pct = (fear or {}).get("nvi_pctile")

        if not nk and not internals.get("available"):
            return ""

        imp = _importance(nk["c"] if nk else None, score, nvi_pct,
                          _breadth(internals))
        head, emo = _headline(nk, internals)
        now = get_jst_now()
        when = {"morning": "寄り付き前", "noon": "前場終了後",
                "evening": "大引け後"}.get(mode, "")
        imp_col = _DOWN if imp >= 4 else _WARN if imp == 3 else _DIM

        # ── 📌 3秒で結論 ──
        concl = ""
        for cand in ((ai_summary or {}).get("neutral_view"),
                     (market_driver or {}).get("summary"),
                     (internals or {}).get("trk25_comment")):
            if isinstance(cand, str) and cand.strip():
                concl = cand.strip()[:220]
                break
        # ⚠️ AIが使えない日は trk25_comment（「中立〜やや弱い」等）しか無く、
        #    一言すぎて結論の役目を果たさない。その日は数字から文を組み立てる。
        if len(concl) < 24 and nk:
            r = _breadth(internals)
            bits = [f"日経平均は{nk['c']:+.2f}%"]
            if isinstance(r, (int, float)):
                side = "下げ" if r >= 0.5 else "上げ"
                pct = r * 100 if r >= 0.5 else (1 - r) * 100
                bits.append(f"{pct:.0f}%の銘柄が{side}ました")
            nvi = internals.get("nvi")
            if isinstance(nvi, (int, float)) and isinstance(nvi_pct, (int, float)):
                if nvi_pct >= 90:
                    bits.append(f"恐怖指数は{nvi:.1f}と高く、値動きが荒くなりやすい状態です")
                elif nvi_pct <= 25:
                    bits.append(f"恐怖指数は{nvi:.1f}と低く、市場は落ち着いています")
            concl = "。".join(bits) + "。" + (("（" + concl + "）") if concl else "")

        concl_html = ""
        if concl:
            concl_html = _sec("📌 3秒で結論",
                              f'<div style="font-size:13px;line-height:1.85;'
                              f'color:{_TEXT}">{_b(concl)}</div>')

        # ── 数字のカード ──
        num = ""
        if nk:
            col = _UP if nk["c"] >= 0 else _DOWN
            arrow = "▲" if nk["c"] >= 0 else "▼"
            diff = None
            pv = (prices.get("^N225") or {}).get("prev_close")
            if isinstance(pv, (int, float)) and isinstance(nk["v"], (int, float)):
                diff = nk["v"] - pv
            sub = []
            adv, dec = internals.get("advancing"), internals.get("declining")
            if isinstance(dec, (int, float)):
                sub.append(("値下がり銘柄", f"{dec:,.0f}銘柄", _DOWN))
            if isinstance(adv, (int, float)):
                sub.append(("値上がり銘柄", f"{adv:,.0f}銘柄", _UP))
            nvi = internals.get("nvi")
            if isinstance(nvi, (int, float)):
                pos = (f"（過去3年で上から{100 - nvi_pct:.0f}%）"
                       if isinstance(nvi_pct, (int, float)) else "")
                sub.append(("恐怖指数 日経VI", f"{nvi:.1f}{pos}", _WARN))
            subs = "".join(
                f'<div style="min-width:46%;flex:1;padding:6px 0">'
                f'<div style="font-size:9.5px;color:{_DIM}">{a}</div>'
                f'<div style="font-size:13px;font-weight:800;color:{c}">{b}</div></div>'
                for a, b, c in sub)
            num = (f'<div style="background:{_CARD};border:1px solid {_LINE};'
                   f'border-radius:12px;padding:14px 16px;margin-top:12px">'
                   f'<div style="font-size:10px;color:{_DIM};margin-bottom:4px">'
                   f'🇯🇵 日経平均 ｜ {now.year}年{now.month}月{now.day}日 {when}</div>'
                   f'<div style="font-size:26px;font-weight:900;color:{col};'
                   f'letter-spacing:-.01em">{_n(nk["v"], 2)}円</div>'
                   f'<div style="font-size:14px;font-weight:800;color:{col};'
                   f'margin-top:2px">{arrow} '
                   f'{(_n(abs(diff), 2) + "円 ") if diff is not None else ""}'
                   f'（{nk["c"]:+.2f}%）</div>'
                   f'<div style="display:flex;flex-wrap:wrap;gap:0 14px;'
                   f'margin-top:10px;border-top:1px solid {_LINE};padding-top:4px">'
                   f'{subs}</div></div>')

        # ── 📋 なぜ動いたか（3つの連鎖）──
        chain_html = ""
        ch = _chain(prices, internals, sector_ranking)
        if ch:
            rows = ""
            for c in ch:
                rows += (
                    f'<div style="display:flex;gap:10px;padding:9px 0;'
                    f'border-bottom:1px solid {_LINE}">'
                    f'<div style="flex:0 0 22px;height:22px;border-radius:7px;'
                    f'background:{_ACC};color:#06121f;font-weight:900;font-size:11px;'
                    f'display:flex;align-items:center;justify-content:center">{c["no"]}</div>'
                    f'<div style="flex:1;min-width:0">'
                    f'<div style="font-size:11.5px;font-weight:800;color:{_TEXT}">{c["title"]}</div>'
                    f'<div class="num" style="font-size:11px;color:{_ACC};margin-top:2px">{c["val"]}</div>'
                    f'<div style="font-size:10.5px;color:{_DIM};margin-top:3px;'
                    f'line-height:1.7">{_b(c["note"])}</div>'
                    f'<div style="font-size:9px;color:{_DIM};opacity:.7;margin-top:2px">'
                    f'出典: {c["src"]}</div></div></div>')
            chain_html = _sec(f"📋 なぜ動いたのか — {len(ch)}つの連鎖",
                              f'<div style="background:{_CARD};border:1px solid {_LINE};'
                              f'border-radius:12px;padding:4px 14px 8px">{rows}</div>',
                              "ここに書いてあるのは**その日に実際に起きた値動き**だけです。"
                              "解釈は下の「AIの見立て」に分けてあります。")

        # ── 💱 為替・金利 ──
        fx_rows = ""
        for sym, nm, dp, unit, note in (
                ("USDJPY=X", "ドル円", 2, "円",
                 "円高は輸出企業の利益を押し下げ、円安は押し上げます"),
                ("^TNX", "米10年金利", 3, "%",
                 "金利が上がるほど、株より債券の魅力が増します")):
            d = _chg(prices, sym)
            if not d:
                continue
            col = _UP if d["c"] >= 0 else _DOWN
            fx_rows += (
                f'<div style="display:flex;align-items:baseline;gap:8px;padding:7px 0;'
                f'border-bottom:1px solid {_LINE}">'
                f'<span style="font-size:11.5px;font-weight:700;color:{_TEXT};flex:1">{nm}</span>'
                f'<span class="num" style="font-size:13px;font-weight:800;color:{_TEXT}">'
                f'{_n(d["v"], dp)}{unit}</span>'
                f'<span class="num" style="font-size:11px;font-weight:800;color:{col};'
                f'min-width:52px;text-align:right">{d["c"]:+.2f}%</span></div>'
                f'<div style="font-size:9.5px;color:{_DIM};padding:0 0 4px">{note}</div>')
        jgb = internals.get("jgb10")
        if isinstance(jgb, (int, float)):
            fx_rows += (
                f'<div style="display:flex;align-items:baseline;gap:8px;padding:7px 0">'
                f'<span style="font-size:11.5px;font-weight:700;color:{_TEXT};flex:1">'
                f'日本10年国債利回り</span>'
                f'<span class="num" style="font-size:13px;font-weight:800;color:{_TEXT}">'
                f'{jgb:.3f}%</span></div>')
        fx_html = _sec("💱 為替・金利",
                       f'<div style="background:{_CARD};border:1px solid {_LINE};'
                       f'border-radius:12px;padding:4px 14px 8px">{fx_rows}</div>'
                       ) if fx_rows else ""

        # ── 🎯 3シナリオ ──
        sc_html = ""
        scs = (scenario or {}).get("scenarios") or []
        if scs:
            rows = ""
            icon = {"楽観": ("🟢", _UP), "基本": ("🟡", _WARN), "悲観": ("🔴", _DOWN)}
            for s in scs[:3]:
                nm = str(s.get("name", ""))[:6]
                ic, cl = icon.get(nm, ("⚪", _DIM))
                pr = s.get("probability")
                pr_s = f"{pr}%" if isinstance(pr, (int, float)) else ""
                rows += (
                    f'<div style="display:flex;gap:9px;padding:8px 0;'
                    f'border-bottom:1px solid {_LINE}">'
                    f'<div style="flex:0 0 62px"><span style="font-size:11.5px;'
                    f'font-weight:800;color:{cl}">{ic} {nm}</span>'
                    f'<div class="num" style="font-size:10px;color:{_DIM}">{pr_s}</div></div>'
                    f'<div style="flex:1;font-size:11px;color:{_TEXT};line-height:1.75">'
                    f'{str(s.get("detail", ""))[:140]}</div></div>')
            sc_html = _sec("🎯 これからの3つの筋書き",
                           f'<div style="background:{_CARD};border:1px solid {_LINE};'
                           f'border-radius:12px;padding:4px 14px 8px">{rows}</div>',
                           "確率はAIの見立てで、当たることが保証された数字ではありません。"
                           "「どれか1つが来る」ではなく「この幅の中で動きやすい」と読んでください。")

        # ── 🐘 AIの見立て（強気・弱気の両論）──
        ai_html = ""
        bull = (ai_summary or {}).get("bull_view")
        bear = (ai_summary or {}).get("bear_view")
        if bull or bear:
            blocks = ""
            for ttl, txt, cl in (("🟢 強気の見方", bull, _UP), ("🔴 弱気の見方", bear, _DOWN)):
                if not txt:
                    continue
                blocks += (
                    f'<div style="padding:8px 0;border-bottom:1px solid {_LINE}">'
                    f'<div style="font-size:11px;font-weight:800;color:{cl}">{ttl}</div>'
                    f'<div style="font-size:11px;color:{_TEXT};line-height:1.8;'
                    f'margin-top:3px">{_b(str(txt)[:200])}</div></div>')
            ai_html = _sec("🐘 AIの見立て（反対の見方も並べます）",
                           f'<div style="background:{_CARD};border:1px solid {_LINE};'
                           f'border-radius:12px;padding:4px 14px 8px">{blocks}</div>',
                           "**上がる理由と下がる理由を両方**出しています。"
                           "片方だけ読むと、見たい材料だけを信じてしまいます。")

        # ── 📚 参考にしたニュース ──
        src_html = ""
        picked = [n for n in (news or [])
                  if isinstance(n, dict) and n.get("url") and n.get("title")]
        picked.sort(key=lambda x: {"S": 0, "A": 1, "B": 2}.get(x.get("importance"), 3))
        if picked:
            items = ""
            for n in picked[:4]:
                t = str(n.get("title", "")).split(" - ")[0][:58]
                items += (
                    f'<div style="padding:5px 0;border-bottom:1px solid {_LINE}">'
                    f'<a href="{n["url"]}" target="_blank" rel="noopener" '
                    f'style="font-size:10.5px;color:{_ACC};text-decoration:none">'
                    f'{n.get("label", "📰")} {t}</a>'
                    f'<span style="font-size:9px;color:{_DIM}"> ／ {n.get("source", "")}</span>'
                    f'</div>')
            src_html = _sec("📚 参考にしたニュース",
                            f'<div style="background:{_CARD};border:1px solid {_LINE};'
                            f'border-radius:12px;padding:4px 14px 8px">{items}</div>')

        # ── 🔍 検証状態（何をどこから取ったか）──
        used = ["株価・為替: Yahoo Finance"]
        if internals.get("available"):
            used.append("騰落・PER・日経VI: nikkei225jp.com")
        if scs or bull:
            used.append("見立て・筋書き: Gemini（AIの生成）")
        if picked:
            used.append("ニュース: Google News RSS")
        verify = _sec(
            "🔍 この記事の作られ方",
            f'<div style="font-size:10px;color:{_DIM};line-height:1.85">'
            + "／".join(used) +
            '<br>数字は自動取得したもので、取引所の一次データとの全項目照合はしていません。'
            '<b style="color:' + _WARN + '">写真は使っていません</b>'
            '（当日の現場写真を用意できないため、関係のない画像を'
            'その日の写真のように見せないという方針です）。</div>')

        return (
            f'<div style="margin-bottom:16px;background:linear-gradient(180deg,'
            f'rgba(106,169,255,.09),rgba(106,169,255,0) 120px);'
            f'border:1px solid {_LINE};border-radius:16px;padding:16px 16px 18px">'
            # ヘッダー
            f'<div style="display:flex;align-items:center;gap:8px;'
            f'border-bottom:1px solid {_LINE};padding-bottom:10px">'
            f'<span style="font-size:15px">🐘</span>'
            f'<span style="font-size:12.5px;font-weight:900;letter-spacing:.06em;'
            f'color:{_TEXT}">GANESHA MARKET FEED</span>'
            f'<span style="margin-left:auto;font-size:9.5px;font-weight:800;'
            f'color:{imp_col};border:1px solid {imp_col};border-radius:20px;'
            f'padding:2px 9px">重要度 {imp}/5</span></div>'
            f'<div style="font-size:9.5px;color:{_DIM};margin-top:7px">'
            f'{now.month}月{now.day}日（{"月火水木金土日"[now.weekday()]}）{when} ｜ 日本株・米国株</div>'
            # 見出し
            f'<div style="font-size:17px;font-weight:900;color:{_TEXT};'
            f'line-height:1.5;margin-top:8px">{_b(head)}</div>'
            f'{num}{concl_html}{chain_html}{fx_html}{sc_html}{ai_html}'
            f'{src_html}{verify}'
            f'</div>')
    except Exception:
        logger.error("フィードカードを作れませんでした", exc_info=True)
        return ""


if __name__ == "__main__":
    import io
    import sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    from src.fetch_prices import run as fp
    from src.indicators import calc_risk_score
    from src.nikkei_market_data import run as nd
    from src.fetch_news import run as fn
    from src.fear_watch import run as fw
    pr, fg = fp()
    html = build(prices=pr, risk=calc_risk_score(pr), internals=nd(),
                 news=fn(), fear=fw(), mode="evening")
    out = "feed_preview.html"
    io.open(out, "w", encoding="utf-8").write(
        f'<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<body style="background:{_BG};color:{_TEXT};font-family:-apple-system,'
        f'\'Hiragino Kaku Gothic ProN\',Meiryo,sans-serif;max-width:460px;margin:auto;'
        f'padding:12px"><style>.num{{font-variant-numeric:tabular-nums}}</style>{html}</body>')
    print(f"{len(html):,}字 → {out}")
