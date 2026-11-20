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
_BG2 = "#0a0d13"      # 記事の紙面。カードより少しだけ暗く、枠は外側だけ
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


def _pill(text: str) -> str:
    """文末に付ける小さな出典バッジ。見本の「みんかぶ +1」の形。

    ⚠️ 出典を段落の下に別行で置くと読み飛ばされる。見本どおり
       **文の終わりに続けて**置くと、どの記述の出どころかが一目で分かる。
    """
    if not text:
        return ""
    return (f'<span style="display:inline-block;vertical-align:middle;'
            f'font-size:9px;color:{_DIM};background:rgba(255,255,255,.07);'
            f'border:1px solid {_LINE};border-radius:20px;'
            f'padding:1.5px 7px;margin-left:5px;white-space:nowrap">{text}</span>')


_TOC = []          # 目次の材料。build() の最初で空にする


class _SkipVideoEmbed(Exception):
    """画像版で動画をサムネイルにしたあと、埋め込み用の処理を飛ばすための合図。"""


def _slug(title: str) -> str:
    """見出しから飛び先のidを作る。絵文字や記号は落とす。"""
    import hashlib
    return "s" + hashlib.md5(str(title).encode("utf-8")).hexdigest()[:8]


def _sec(title, body, note="", src="", toc=True) -> str:
    """見出し＋中身＋（注記）＋（出典）の1区画。

    ⚠️ **カードで囲まない。** 見本は雑誌記事の体裁で、区画ごとに枠を付けると
       画面が升目に割れて「ダッシュボード」になってしまう（一度そうして
       「理想とかけ離れている」と指摘を受けた）。区切りは余白と細い線で作る。
    """
    sid = _slug(title) if title else ""
    if title and toc:
        _TOC.append((sid, title))
    t = (f'<h2 id="{sid}" style="font-size:17px;font-weight:800;color:{_TEXT};'
         f'margin:0 0 10px;letter-spacing:.01em;scroll-margin-top:12px">'
         f'{title}</h2>') if title else ""
    n = (f'<div style="font-size:12.5px;color:{_DIM};margin-top:8px;'
         f'line-height:1.9">{_b(note)}</div>') if note else ""
    sc = (f'<div style="margin-top:5px">{_pill(src)}</div>') if src else ""
    return (f'<section style="margin:24px 0 0;padding-top:20px;'
            f'border-top:1px solid {_LINE}">{t}{body}{n}{sc}</section>')


def _p(text: str, size=14) -> str:
    """記事の本文1段落。読み物として読める大きさと行間にする。

    ⚠️ 既定を 12.5px から 14px に上げた。Telegramの画像でも公開ページでも
       「小さすぎる」と指摘を受けたため。迷ったら大きいほうに倒す。
    """
    return (f'<p style="font-size:{size}px;line-height:1.95;color:{_TEXT};'
            f'margin:0 0 10px">{_b(text)}</p>')


def _box(inner, pad="12px 14px") -> str:
    """数値をまとめる枠。見本でもここだけは枠で囲っている。"""
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


def _news_title(x, limit=52) -> str:
    """ニュースの見出しを表示用に整える。

    ⚠️ 以前は `split(" - ")[0]` で切っていたため、題名の途中に " - " がある
       記事（Reutersの「Breakingviews - コラム：…」など）が
       **先頭の1語だけ**になっていた。見出しが消えるので何の話か分からない。
       Google News RSS が付けるのは**末尾の " - 配信元"** だけなので、
       後ろから1回だけ切り、配信元と一致したときに限って落とす。
    """
    t = str(x.get("title") or "").strip()
    src = str(x.get("source") or "").strip()
    if src and " - " in t:
        head, tail = t.rsplit(" - ", 1)
        if tail.strip() == src and len(head) >= 8:
            t = head.strip()
    return t[:limit] + ("…" if len(t) > limit else "")


def _links(items, icon="📰", n=3) -> str:
    return "".join(
        f'<div style="padding:5px 0;border-bottom:1px solid {_LINE}">'
        f'<a href="{x["url"]}" target="_blank" rel="noopener" '
        f'style="font-size:10.5px;color:{_ACC};text-decoration:none">'
        f'{x.get("label", icon)} {_news_title(x)}</a>'
        f'<span style="font-size:9px;color:{_DIM}"> ／ {x.get("source", "")}</span>'
        f'</div>' for x in items[:n])


# ── ニュースの束ね方 ────────────────────────────────────
# ⚠️ 見出しから「なぜ動いたか」を**こちらで推測して書かない**。
#    見出しはそのまま載せ、出どころを添える。相場の原因を断定するのは
#    誤情報のいちばん出やすい形で、しかも外から検証できない。
#    「どこに効くか」の説明は、見出しごとではなく**話題ごとの固定文**に
#    してある（下の表）。固定文なら人が確認でき、日によってぶれない。
#
# 束ね方は `label`（config/news_sources.yaml の表示名）で引く。
# 見出しの文字で引くと、同じ語を含む無関係な記事を拾う。

#   束の名前 → (まとめ見出し, [label...], どこに効くかの固定文)
_THEME_GROUPS = (
    ("ai", "💻 AI・半導体", ["💻 AI・半導体", "📈 テック株"],
     "日経平均は今、半導体関連の比重が大きいので、"
     "**この話題が指数をいちばん大きく動かします。**"
     "米国のテック株が動いた翌朝は、東京の半導体株がほぼ同じ方向に動きます。"),
    ("gafa", "🏢 米巨大テックの決算", ["🏢 GAFA決算"],
     "決算はその会社の成績表です。見るところは売上より"
     "**AI向けの設備投資をいくらに増やしたか**で、"
     "そこが日本の半導体製造装置メーカーへの注文につながります。"),
    ("jp", "🇯🇵 日本の大企業", ["🏢 日本大企業", "🏢 企業決算"],
     "日経平均は**株価の平均**なので、株価の高い銘柄"
     "（ソフトバンクG・ファストリなど）の値動きが指数を強く動かします。"
     "同じ1%でも指数への効き方が違います。"),
)

_GEO_GROUPS = (
    ("macro", "📊 物価・雇用・景気（経済指標）",
     ["📊 米CPI", "📊 雇用統計", "📊 GDP", "📊 PMI"],
     "ここが**金利を決めます**。物価が高いと利上げ、雇用が弱いと利下げ。"
     "利上げなら株に逆風、利下げなら追い風という順で回ってきます。"),
    ("uscn", "🇺🇸🇨🇳 米中と台湾", ["⚠️ 米中・台湾"],
     "米中が対立すると、半導体の輸出制限や関税が増えます。"
     "日本は半導体の製造装置を中国に売っているので、"
     "**東京エレクトロン・アドバンテストなどに直接ひびきます。**"),
    ("tariff", "🧾 関税・通商政策", ["🇺🇸 米経済政策"],
     "関税は輸入品に上乗せされる税です。米国に車を売るトヨタなどの"
     "利益を削り、同時に**米国の物価を押し上げて利上げの理由になります。**"),
    ("fiscal", "💸 米国の財政と国債", ["🇺🇸 米財政"],
     "国の借金が増えると、国債を買ってもらうために利回り（金利）を"
     "上げる必要が出ます。**金利が上がると株は割高に見えて売られやすい**"
     "ので、ここは株価に回ってきます。"),
    ("me", "🛢 中東情勢", ["⚠️ 中東情勢"],
     "原油の産地と輸送路です。紛争が広がると原油が上がり、"
     "日本は輸入に頼っているので**物価と企業のコストが上がります。**"),
    ("ru", "🌍 ロシア・ウクライナ", ["⚠️ ロシア・ウクライナ"],
     "エネルギーと穀物の供給に影響します。"
     "欧州の景気と資源価格を通して、日本株にも回ってきます。"),
    ("cn", "🇨🇳 中国の景気", ["🇨🇳 中国経済", "🇪🇺 欧州経済"],
     "中国は日本の最大の輸出先です。中国の景気が悪いと"
     "**機械・化学・自動車の注文が減ります。**"),
    ("jppol", "🇯🇵 日本の政策", ["🇯🇵 日本経済"],
     "補正予算や減税は、**どの業種にお金が流れるか**を変えます。"),
)

# 「報道が挙げている理由」に載せる話題。相場を動かした話に絞る
_WHY_LABELS = ["📈 米国株", "📈 テック株", "📈 日本株", "💻 AI・半導体",
               "📊 米金利", "💱 為替", "🥇 金", "🛢 原油"]


def _news_by_label(news, labels, used=None) -> list:
    """label が一致するニュースを、重要度の高い順に拾う。

    ⚠️ 同じ記事を2か所に出さないため `used`（出したURLの集合）を見る。
       欄が増えるほど重複は必ず起きるので、気をつけて書くのではなく
       機械的に避ける（写真の `used_photos` と同じ考え）。
    """
    used = used if used is not None else set()
    out = []
    for n in (news or []):
        if not isinstance(n, dict):
            continue
        u, t = n.get("url"), str(n.get("title") or "").strip()
        if not u or not t or u in used:
            continue
        if str(n.get("label") or "") in labels:
            out.append(n)
    out.sort(key=lambda x: {"S": 0, "A": 1, "B": 2}.get(x.get("importance"), 3))
    return out


def _topic_block(title, body_html, hint="") -> str:
    """話題ひとかたまり。小見出し＋見出し一覧＋効くところ。"""
    h = (f'<div style="font-size:12.5px;font-weight:800;color:{_TEXT};'
         f'margin:0 0 5px">{title}</div>')
    k = (f'<div style="font-size:11px;color:{_DIM};line-height:1.85;'
         f'margin-top:6px">{_b(hint)}</div>') if hint else ""
    return (f'<div style="padding:11px 0;border-bottom:1px solid {_LINE}">'
            f'{h}{body_html}{k}</div>')


def _groups_section(news, groups, title, note, used, per=2, cap=4) -> str:
    """束ごとに「小見出し＋見出し＋効くところ」を並べた区画を作る。

    ⚠️ 取れなかった束は**その束ごと出さない**。空の小見出しが並ぶと
       読む気が失せるし、何も起きていないのか取れなかったのか
       区別できなくなる。
    """
    blocks = []
    for _k, label, labels, hint in groups:
        got = _news_by_label(news, labels, used)[:per]
        if not got:
            continue
        for g in got:
            used.add(g.get("url"))
        blocks.append(_topic_block(label, _links(got, "📰", per), hint))
        if len(blocks) >= cap:
            break
    if not blocks:
        return ""
    return _sec(title, _box("".join(blocks), "4px 14px 6px"),
                note=note, src="Google News RSS（見出しと配信元はそのまま）")


# ── 見出し ──────────────────────────────────────────────
def _photo(key: str, w: int = 330) -> str:
    """固定リストの写真を、作者・ライセンス・撮影時期つきで1枚出す。

    ⚠️ **説明を必ず付ける。** Commonsにあるのは建物の一般写真であって
       その日の相場の写真ではない。今日の数字の隣に裸で置くと
       今日の光景と誤読される。何の写真でいつ撮られたかまで書く。
    ⚠️ 取れなければ**何も出さない**。代わりの写真を探しに行かない
       （探すと全文検索に戻り、無関係な画像を載せる事故になる）。
    """
    try:
        from src.media_credits import photo, photo_credit
        pm = photo(key)
        if not pm:
            return ""
        # ⚠️ f文字列の中に f文字列を入れ子にしない。同じ引用符を内側で使うと
        #    **Python 3.11 では SyntaxError**（緩和されたのは3.12から）。
        #    手元は3.14で通るのに CI(3.11) だけ落ち、しかもモジュールごと
        #    import できなくなるので朝のレポートが丸ごと消える。
        page = pm.get("page") or ""
        link = ""
        if page:
            link = ('　・<a href="' + page + '" target="_blank" '
                    'rel="noopener noreferrer" style="color:' + _DIM + '">'
                    '出典ページ</a>')
        return (
            f'<figure style="margin:8px 0 0">'
            f'<img src="{pm["url"]}" alt="{pm["caption"]}" loading="lazy" '
            f'style="width:100%;max-width:{w}px;height:132px;object-fit:cover;'
            f'border-radius:10px;display:block;border:1px solid {_LINE}">'
            f'<figcaption style="font-size:9px;color:{_DIM};margin-top:3px;'
            f'line-height:1.6">{photo_credit(pm)}{link}'
            f'</figcaption></figure>')
    except Exception:
        logger.error(f"写真を出せませんでした [{key}]", exc_info=True)
        return ""


def _scenarios(scenario):
    """3シナリオを [(鍵, 名前, 確率, 本文)] の形に揃える。

    ⚠️ `scenario.run()` が返すのは {"bull":…, "base":…, "bear":…} であって
       `"scenarios"` という一覧ではない。以前そこを読んでいたため、
       **レポートでも通知でも3シナリオが丸ごと空だった**
       （例外にならず静かに消えるので、ログでは気づけない）。
       取り違えを2か所で繰り返さないよう、ここに一本化する。
    """
    out = []
    for key, nm in (("bull", "強気"), ("base", "中立"), ("bear", "弱気")):
        e = (scenario or {}).get(key)
        if not isinstance(e, dict):
            continue
        txt = str(e.get("text") or "").replace("\n", " ").strip()
        if not txt:
            continue
        pr = e.get("prob")
        out.append((key, nm, pr if isinstance(pr, (int, float)) else None, txt))
    return out


def _breadth_phrase(r) -> str:
    """売り買いの広がりを「3秒で結論」向けに一言で。

    ⚠️ 判定の帯は「売り買いの広がり」の説明文と必ず揃える。
       以前は r>=.5 で機械的に側を選んでいたため、60%の日に
       結論は「60%の銘柄が下げました」、広がりの欄は「拮抗」と
       **同じ通知の中で正反対のことを言っていた**。
       同じ判定を2か所に書くと必ず片方だけずれるので、ここに一本化する。
    """
    if not isinstance(r, (int, float)):
        return ""
    if 0.35 < r < 0.65:
        return "値上がりと値下がりはほぼ拮抗しました"
    side = "下げ" if r >= .5 else "上げ"
    return f"{(r if r >= .5 else 1 - r) * 100:.0f}%の銘柄が{side}ました"


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
          sector_ranking=None, fear=None, policy=None, mode="morning",
          for_image=False) -> str:
    # ⚠️ 目次の台帳は実行ごとに空にする。モジュールの変数なので、
    #    空にし忘れると2回目の実行で前回の項目が二重に並ぶ。
    _TOC.clear()
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

        # ── ヘッダー（見本の体裁: ブランド名＋重要度バッジ）──
        # ⚠️ 重要度は★の並びではなく **「5/5」の数字**にする。
        #    見本がそうなっているのに加え、★5個は小さい画面で潰れて
        #    何個あるか数えられない。数字なら一瞬で分かる。
        head = (
            f'<div style="display:flex;align-items:center;gap:9px">'
            f'<span style="font-size:19px">🐘</span>'
            f'<span style="font-size:14px;font-weight:900;letter-spacing:.06em;'
            f'color:{_TEXT}">GANESHA MARKET FEED</span>'
            f'<span style="margin-left:auto;font-size:10px;font-weight:800;'
            f'color:{tone["badge"]};background:{tone["badge"]}1f;'
            f'border-radius:6px;padding:3px 8px;white-space:nowrap">'
            f'重要度 {imp}/5</span></div>'
            f'<div style="font-size:10.5px;color:{_DIM};margin-top:10px">'
            f'{now.month}月{now.day}日（{_WD[now.weekday()]}）'
            f'{"　" + when if when else ""} ｜ 日本株・米国株</div>'
            f'<h1 style="font-size:{tone["size"] + 2}px;font-weight:{tone["weight"]};'
            f'color:{_TEXT};line-height:1.5;margin:11px 0 0;'
            f'letter-spacing:-.01em">{_b(_headline(nk, internals))}</h1>')

        # 1本の記事の中で**同じ写真を二度出さない**（オーナーの明示指示）。
        # 気をつけて書くだけでは、欄が増えたときに必ず重複する。
        # 使った鍵をここで覚えて、以降は自動で避ける。
        used_photos = set()

        def _pick(*keys):
            """まだ使っていない写真の鍵を1つ返す。無ければ None。"""
            for k in keys:
                if k not in used_photos:
                    used_photos.add(k)
                    return k
            return None

        # ── 記事の顔になる写真（見本の大きな報道写真の位置）──
        # ⚠️ 見本は当日の報道写真だが、こちらは用意できない。
        #    代わりに取引所の写真を**「いつ撮られた何か」を明記して**置く。
        #    その日の光景のように見せないことが条件。
        lead_photo = ""
        try:
            from src.media_credits import photo, photo_credit
            # ⚠️ 外観(tse2)を先に。tse は入口の**天井**の写真で、
            #    記事の顔には「ここは取引所だ」と分かる絵が要る。
            _pm = photo(_pick("tse2", "tse") or "tse2")
            if _pm:
                lead_photo = (
                    f'<figure style="margin:14px 0 0">'
                    f'<img src="{_pm["url"]}" alt="{_pm["caption"]}" loading="lazy" '
                    f'style="width:100%;height:172px;object-fit:cover;'
                    f'border-radius:12px;display:block;border:1px solid {_LINE}">'
                    f'<figcaption style="font-size:9px;color:{_DIM};margin-top:5px;'
                    f'line-height:1.6">{photo_credit(_pm)}'
                    f'　※当日の写真ではありません</figcaption></figure>')
        except Exception:
            logger.error("見出し写真を出せませんでした", exc_info=True)
        head += lead_photo

        # ── 大きなチャート（ローソク足）──
        # 折れ線は終値しか見せない。ローソクなら「その日どこまで行って
        # 戻されたか」まで見える。上ヒゲが長い日＝高いところで売られた、
        # という形は終値だけ追っていると気づけない。
        hero = ""
        try:
            _rows = V.ohlc("^N225", "6mo")
            _svg = V.candles(_rows, w=330, h=176, label="日経平均", days=30)
            if _svg:
                hero = _sec("", _box(_svg, pad="10px 10px 4px"),
                            note="緑はその日上げた日、赤は下げた日。"
                                 "上下に伸びる細い線は**その日の高値と安値**です。",
                            src="Yahoo Finance の4本値から自前で作図")
        except Exception:
            logger.error("ローソク足を描けませんでした", exc_info=True)
        if not hero and hist.get("^N225"):
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
            if _breadth_phrase(r):
                bits.append(_breadth_phrase(r))
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

        # ── 📋 なぜ動いたのか（見本の①②③ の形）──
        # 左に小さな図、右に小見出し＋本文＋出典。枠で囲わず記事として流す。
        chain_html = ""
        ch = _chain(prices, internals, sector_ranking, hist)
        if ch:
            # 連鎖ごとに違う写真を当てる。
            # ⚠️ **同じ写真を2枚出さない**（オーナーの明示指示）。
            #    使える写真が足りない日は、足りない分は写真なしで出す。
            # ⚠️ 写真は**中身に合うものだけ**を付ける。順番で機械的に割ると、
            #    「売り買いの広がり」の横に日銀の写真、のような
            #    意味のない組み合わせになる（オーナー指示は
            #    「できるだけ意味のある内容の画像」）。
            #    合う写真が無い項目は、写真なしで文字だけ出す。
            def _match(title: str):
                t = str(title or "")
                if any(k in t for k in ("米国", "NY", "ナスダック", "S&P")):
                    return _pick("nyse2", "nyse")
                if any(k in t for k in ("日銀", "金利", "政策")):
                    return _pick("boj",)
                if any(k in t for k in ("為替", "ドル円", "円安", "円高")):
                    return _pick("mof",)
                if any(k in t for k in ("FRB", "FOMC", "米金融")):
                    return _pick("fed",)
                return None

            pkeys = [_match(c.get("title")) for c in ch]
            rows = ""
            for i, c in enumerate(ch):
                vis = (f'<div style="flex:0 0 104px">{c["vis"]}</div>'
                       ) if c.get("vis") else ""
                thumb = vis
                if not thumb and i < len(pkeys) and pkeys[i]:
                    try:
                        from src.media_credits import photo as _ph
                        _p2 = _ph(pkeys[i])
                        if _p2:
                            thumb = (f'<img src="{_p2["url"]}" alt="" loading="lazy" '
                                     f'style="width:104px;height:72px;object-fit:cover;'
                                     f'border-radius:8px;flex:0 0 auto;'
                                     f'border:1px solid {_LINE}">')
                    except Exception:
                        logger.debug("連鎖の写真を出せませんでした")
                rows += (
                    f'<div style="display:flex;gap:12px;align-items:flex-start;'
                    f'margin:0 0 17px">{thumb}'
                    f'<div style="flex:1;min-width:0">'
                    f'<div style="font-size:12.5px;font-weight:800;color:{_TEXT};'
                    f'margin-bottom:4px">{c["no"]}. {c["title"]}</div>'
                    f'<div style="font-size:11.5px;line-height:1.9;color:{_DIM}">'
                    f'<span class="num" style="color:{_ACC};font-weight:700">'
                    f'{c["val"]}</span>　{_b(c["note"])}{_pill(c["src"])}'
                    f'</div></div></div>')
            chain_html = _sec(f"📋 なぜ動いたのか？ {len(ch)}つの連鎖", rows,
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
        if pol_rows:
            _pk = _pick("boj", "mof", "fed")
            if _pk:
                pol_rows += _photo(_pk)
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
        scs = _scenarios(scenario)
        if scs:
            icon = {"強気": ("🟢", _UP), "中立": ("🟡", _WARN), "弱気": ("🔴", _DOWN)}
            rows = ""
            for _k, nm, pr, _txt in scs[:3]:
                ic, cl = icon.get(nm, ("⚪", _DIM))
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
        if _breadth_phrase(r):
            # ⚠️ ここも _breadth_phrase に揃える。以前は広がりの欄が「拮抗」と
            #    書いている日に、おさらいだけ「60%の銘柄が下げた」と言っていた。
            recap.append(_breadth_phrase(r)
                         .replace("拮抗しました", "拮抗")
                         .replace("ました", ""))
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

        # ── 📺 公式チャンネルの最新動画 ──
        # ⚠️ **要約しない。** 動画を見ていないのに中身を書くのがハルシネーション。
        #    出すのは YouTube が返した題名・チャンネル名・公開日だけ。
        vid_html = ""
        try:
            from src.media_credits import videos
            vids = videos(limit=3, max_age_days=2)
            if vids:
                # ⚠️ 画像(PNG)にするときは iframe が意味を持たないので
                #    サムネイルに落とす。ページでは再生できる形のまま。
                if for_image:
                    cells = "".join(
                        f'<div style="display:flex;gap:10px;margin:0 0 12px;'
                        f'align-items:flex-start">'
                        f'<img src="{v["thumb"]}" alt="" '
                        f'style="width:124px;height:70px;object-fit:cover;'
                        f'border-radius:8px;flex:0 0 auto;border:1px solid {_LINE}">'
                        f'<div style="flex:1;min-width:0">'
                        f'<div style="font-size:12px;color:{_TEXT};line-height:1.6">'
                        f'{v["title"]}</div>'
                        f'<div style="font-size:10.5px;color:{_DIM};margin-top:3px">'
                        f'{v["channel"]}　{v["published"][:10]}</div></div></div>'
                        for v in vids)
                    vid_html = _sec(
                        "📺 公式チャンネルの最新動画",
                        f'<div>{cells}</div>',
                        note="題名とチャンネル名は**YouTubeが返したそのまま**です。"
                             "再生は記事ページから。",
                        src="YouTube 公式チャンネルのRSS")
                    raise _SkipVideoEmbed

                # ⚠️ 画像ではなく**その場で再生できる形**にする。
                #    `youtube-nocookie.com` を使うのは、再生するまで
                #    閲覧履歴を残さないため（prefer privacy）。
                #    `loading="lazy"` で、下まで来るまで読み込まない。
                cells = "".join(
                    f'<div style="margin:0 0 14px">'
                    f'<div style="position:relative;width:100%;padding-top:56.25%;'
                    f'border-radius:10px;overflow:hidden;border:1px solid {_LINE}">'
                    f'<iframe src="https://www.youtube-nocookie.com/embed/{v["id"]}" '
                    f'title="{v["title"]}" loading="lazy" allowfullscreen '
                    f'referrerpolicy="no-referrer" frameborder="0" '
                    f'style="position:absolute;inset:0;width:100%;height:100%">'
                    f'</iframe></div>'
                    f'<div style="font-size:12px;color:{_TEXT};line-height:1.6;'
                    f'margin-top:6px">{v["title"]}</div>'
                    f'<div style="font-size:10.5px;color:{_DIM};margin-top:3px">'
                    f'{v["channel"]}　{v["published"][:10]}</div></div>'
                    for v in vids)
                vid_html = _sec(
                    "📺 公式チャンネルの最新動画",
                    f'<div>{cells}</div>',
                    note="題名とチャンネル名は**YouTubeが返したそのまま**です。"
                         "中身は見ていないので要約は付けていません。",
                    src="YouTube 公式チャンネルのRSS")
        except _SkipVideoEmbed:
            pass                      # サムネイル版を作り終えただけ。異常ではない
        except Exception:
            logger.error("動画の欄を作れませんでした", exc_info=True)

        # ── 📰 報道が挙げている理由 ──
        # ⚠️ 上の「なぜ動いたのか」は**値動きから出した事実**で、ここは
        #    **報道がそう言っている**という別の種類の情報。混ぜると
        #    「相場が動いた原因はこれだ」と断定したことになる。分けて置く。
        why_used = set()
        why_html = ""
        try:
            why = _news_by_label(news, _WHY_LABELS, why_used)[:4]
            if why:
                for w in why:
                    why_used.add(w.get("url"))
                why_html = _sec(
                    "📰 報道が挙げている理由",
                    _box(_links(why, "📰", 4), "4px 14px 8px"),
                    note="**見出しはそのまま載せています。**こちらで要約も解釈も"
                         "していません。報道が挙げている理由であって、"
                         "相場が動いた原因を断定するものではありません。",
                    src="Google News RSS")
        except Exception:
            logger.error("報道の欄を作れませんでした", exc_info=True)

        # ── 💻 注目の企業とテーマ ──
        theme_html = ""
        try:
            theme_html = _groups_section(
                news, _THEME_GROUPS, "💻 注目の企業とテーマ",
                "**どの会社の話が日経平均に効くか**は、株価の高さと"
                "業種の比重で決まります。話題ごとに、どこに効くのかを添えました。",
                why_used, per=2, cap=3)
        except Exception:
            logger.error("テーマの欄を作れませんでした", exc_info=True)

        # ── 🏛 世界の政治とお金 ──
        # オーナー要望「政治はどうなのか？」。地政学と通商・財政は
        # 毎朝取っていたのに、レポートにも通知にも一度も出していなかった。
        geo_html = ""
        try:
            geo_html = _groups_section(
                news, _GEO_GROUPS, "🏛 世界の政治とお金",
                "政治の話が株価に届くまでには**必ず途中の道筋があります**"
                "（関税→企業の利益、財政→金利、紛争→原油）。"
                "その道筋を話題ごとに書いてあります。",
                why_used, per=2, cap=5)
        except Exception:
            logger.error("政治の欄を作れませんでした", exc_info=True)

        # ── 📚 出典 ──
        picked = [n for n in (news or [])
                  if isinstance(n, dict) and n.get("url") and n.get("title")]
        picked.sort(key=lambda x: {"S": 0, "A": 1, "B": 2}.get(x.get("importance"), 3))
        # 政策・報道・テーマ・政治の欄で既に出したものは繰り返さない
        # ⚠️ 欄が増えたので、ここを足し忘れると同じ記事が二度並ぶ。
        shown = set(why_used)
        if pol_news:
            shown |= {n.get("url") for n in pol_news[:3]}
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
              f'<br><b style="color:{_WARN}">写真はWikimedia Commonsから引用しています。</b>'
              '作者とライセンスを写真ごとに明記しています。ただし'
              '<b>その日の相場の写真ではありません</b>（建物などの一般写真です）。'
              'いつ撮られた何の写真かを必ず添えているのはそのためです。'
              f'<br><b style="color:{_WARN}">動画は題名をそのまま載せています。</b>'
              '中身は見ていないので要約は付けません。'
              '<br>数字は自動取得したもので、取引所の一次データとの'
              '全項目照合はしていません。</div>')

        # ── 🧭 今日の目次（タップでその項目へ飛ぶ）──
        # ⚠️ **ここは全セクションを作り終えた後でないと作れない。**
        #    _TOC は _sec() が呼ばれるたびに積まれるので、
        #    上で作っておくと空の目次になる。
        toc_html = ""
        if len(_TOC) >= 3:
            items = "".join(
                f'<a href="#{sid}" style="display:block;text-decoration:none;'
                f'color:{_TEXT};font-size:13.5px;line-height:1.5;'
                f'padding:9px 10px;border-radius:9px;background:{_CARD};'
                f'border:1px solid {_LINE}">{t}'
                f'<span style="float:right;color:{_DIM}">›</span></a>'
                for sid, t in _TOC)
            toc_html = (
                f'<nav style="margin:18px 0 0">'
                f'<div style="font-size:15px;font-weight:800;color:{_TEXT};'
                f'margin-bottom:9px">🧭 今日の目次</div>'
                f'<div style="display:grid;gap:7px">{items}</div>'
                f'<div style="font-size:11.5px;color:{_DIM};margin-top:8px">'
                f'項目をタップすると、その場所へ飛びます。</div></nav>')

        # ⚠️ 外枠は**記事の紙面**であって、カードを並べる台ではない。
        #    以前は枠＋角丸＋薄い発光を付けていたが、中の区画にも枠があるため
        #    画面が升目に割れて「ダッシュボード」に見えていた。
        #    枠は外側の1本だけにして、中は余白と区切り線で読ませる。
        return (
            f'<article style="margin-bottom:18px;background:{_BG2};'
            f'border:1px solid {_LINE};border-radius:16px;padding:20px 18px 22px">'
            f'{head}{toc_html}{hero}{concl_html}{idx_html}{mkt}{chain_html}'
            f'{why_html}{theme_html}{fx_html}{pol_html}{geo_html}'
            f'{alt_html}{sc_html}{recap_html}{vid_html}{src_html}{verify}'
            f'</article>')
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
# ⚠️ ここを広げると実機での文字が小さくなる（build_compact の説明を参照）。
#    スマホのチャット幅に合わせた 420 が、読める上限いっぱいの幅。
TG_W = 420                 # CSSの幅。device_scale_factor=2 で実寸840px
_FONT = ("-apple-system,'Hiragino Kaku Gothic ProN','Noto Sans CJK JP',"
         "'Noto Sans JP','Yu Gothic UI',Meiryo,sans-serif")


def build_compact(prices=None, risk=None, internals=None, ai_summary=None,
                  market_driver=None, fear=None, mode="morning",
                  scenario=None, news=None, sector_ranking=None,
                  policy=None) -> str:
    """Telegramに画像で送る記事。**公開ページと同じ中身をまるごと**入れる。

    ⚠️ **縦に長くしても、実機での文字は小さくならない。**
       効くのは幅だけ。Telegramは画像をチャット幅（実機390pt前後）に
       縮めるので、文字の大きさを決めるのは「CSS幅 ÷ 390」であって、
       縦の長さは一切関係しない。

         CSS幅 760 → 0.51倍 → 13pxが6.6pt（読めない）
         CSS幅 420 → 0.93倍 → 13pxが12.1pt（読める）

       一度ここを取り違えて「長いと字が小さくなる」と考え、中身を削って
       表紙だけにしたが、**それは間違い**で、ただ内容が減っただけだった。
       幅さえ420に保てば、いくら長くしても字の大きさは変わらない。

    ⚠️ **縦の上限は Telegram の仕様から来る。**
       sendPhoto は「幅＋高さ > 10000px」の写真を受け取らない。
       実寸(×2)で 840 + 2×高さ ≤ 10000 → **CSS高さ 4580pxまで**。
       `make_feed_image` が出来た画像を測って、超えたら従来カードへ落とす。
    """
    body = build(prices=prices, risk=risk, internals=internals,
                 ai_summary=ai_summary, scenario=scenario,
                 market_driver=market_driver, news=news,
                 sector_ranking=sector_ranking, fear=fear, policy=policy,
                 mode=mode, for_image=True)
    if not body:
        return ""
    return (f'<div id="feed" style="width:{TG_W}px;background:{_BG2};'
            f'color:{_TEXT};font-family:{_FONT};padding:16px 14px 18px;'
            f'box-sizing:border-box">{body}'
            f'<div style="font-size:12px;color:{_DIM};margin-top:18px;'
            f'text-align:center;line-height:1.85">'
            f'👇 目次をタップして飛べる記事・動画の再生は下のボタンから'
            f'</div></div>')


def build_text(prices=None, risk=None, internals=None, ai_summary=None,
               market_driver=None, fear=None, scenario=None, policy=None,
               mode="morning", limit=3900) -> str:
    """Telegramに**文字のまま**送る記事。画像にしない版。

    ⚠️ **なぜ画像をやめたか（2026-11-19・オーナー指摘）**
       「かなり見にくい」「アップするとぼやける」「クリックせずとも見たい」。
       原因は画像という入れ物そのものにあった。

       1. Telegramは写真を**圧縮して保存し直す**ので、文字が滲む。
          縦に長い画像ほど縮小率が大きく、拡大すると崩れる。
       2. チャットの中では縮めて表示されるので、**タップしないと読めない**。
       3. 画像の文字は選択もコピーも検索もできない。

       文字で送れば、どれも起きない。**端末の文字で描かれるので、
       拡大しても絶対に滲まない**し、チャットを開いた時点で読める。

    ⚠️ **字数の上限が写真とは違う。**
       写真のキャプション = 1024字／**テキストの本文 = 4096字**。
       画像をやめると、載せられる中身はむしろ4倍に増える。
       それでも上限はあるので、入り切らない分は下から落とす
       （大事なものを上に置いてあるので、落ちるのは参考情報から）。
    """
    prices, internals = prices or {}, internals or {}
    nk = _q(prices, "^N225")
    if not nk and not internals.get("available"):
        return ""

    now = get_jst_now()
    score = (risk or {}).get("score")
    nvi_pct = (fear or {}).get("nvi_pctile")
    nvi = internals.get("nvi")
    r = _breadth(internals)
    imp = _importance(nk["c"] if nk else None, score, nvi_pct, r)
    when = {"morning": "寄り付き前", "noon": "前場終了後",
            "evening": "大引け後", "test": "検証"}.get(mode, "")

    def _t(x):
        """Telegramの書式を壊さないように整える。

        ⚠️ `*` や `_` が奇数個あると Markdown の解析が失敗し、
           send_message が書式なしで送り直す（＝太字が全部消える）。
           **強調** はこちらの書き方なので *強調* に直し、
           残った裸の記号は落とす。
        """
        x = str(x or "").replace("**", "\x00")
        x = x.replace("*", "").replace("_", "").replace("`", "")
        return x.replace("\x00", "*")

    head = []
    # 1行目＝見出し。iPhoneのロック画面にはここだけが出る
    head.append(f"*{_t(_headline(nk, internals))}*")
    head.append(f"🐘 市場AI秘書 ｜ {now.month}/{now.day}"
                f"（{_WD[now.weekday()]}）"
                f"{'　' + when if when else ''}　重要度 {imp}/5")
    head.append("━━━━━━━━━━━━━━")

    blocks = []

    # 📌 3秒で結論
    concl = ""
    for cand in ((ai_summary or {}).get("neutral_view"),
                 (market_driver or {}).get("summary")):
        if isinstance(cand, str) and cand.strip():
            concl = cand.strip()[:220]
            break
    if len(concl) < 24 and nk:
        bits = [f"日経平均は{nk['c']:+.2f}%"]
        if _breadth_phrase(r):
            bits.append(_breadth_phrase(r))
        concl = "。".join(bits) + "。"
    if concl:
        blocks.append(("concl", f"📌 *3秒で結論*\n{_t(concl)}"))

    # 📊 本日の数字
    lines = []
    for sym, nm, unit in (("^N225", "日経平均", "円"), ("^TOPX", "TOPIX", ""),
                          ("USDJPY=X", "ドル円", "円")):
        d = _q(prices, sym)
        if d:
            mark = "📈" if d["c"] >= 0 else "📉"
            lines.append(f"{mark} {nm} {_n(d['v'], 2)}{unit}（{d['c']:+.2f}%）")
    adv, dec = internals.get("advancing"), internals.get("declining")
    turn = internals.get("turnover_total")
    if isinstance(turn, (int, float)):
        lines.append(f"💰 東証の売買代金 {turn / 1e6:.2f}兆円")
    if isinstance(adv, (int, float)) and isinstance(dec, (int, float)):
        pct = dec / max(1, adv + dec) * 100
        lines.append(f"🔻 値上がり {adv:,.0f} ／ 値下がり {dec:,.0f}"
                     f"（{pct:.0f}%が下げ）")
    if isinstance(nvi, (int, float)):
        pos = (f"・上から{100 - nvi_pct:.0f}%"
               if isinstance(nvi_pct, (int, float)) else "")
        lines.append(f"😨 恐怖指数 日経VI {nvi:.1f}{pos}")
    if lines:
        blocks.append(("num", "📊 *本日の数字*\n" + "\n".join(lines)))

    # 📋 なぜ動いたのか
    try:
        ch = _chain(prices, internals, None, {})
        if ch:
            rows = []
            for c in ch[:3]:
                rows.append(f"*{c['no']}. {_t(c['title'])}*\n"
                            f"{_t(c['val'])}　{_t(c['note'])}")
            blocks.append(("chain", "📋 *なぜ動いたのか*\n" + "\n\n".join(rows)))
    except Exception:
        logger.error("連鎖を作れませんでした", exc_info=True)

    # 💱 為替・金利
    fx = []
    for sym, nm, unit in (("USDJPY=X", "ドル円", "円"), ("^TNX", "米10年金利", "%"),
                          ("JP10Y", "日本10年国債", "%")):
        d = _q(prices, sym)
        if d:
            fx.append(f"・{nm} {_n(d['v'], 2)}{unit}（{d['c']:+.2f}%）")
    if fx:
        blocks.append(("fx", "💱 *為替・金利*\n" + "\n".join(fx)))

    # 🏦 日銀・政府・政策
    pol = []
    for key, icon, nm in (("fed", "🇺🇸", "FRB（米国）"), ("boj", "🇯🇵", "日銀（日本）")):
        e = (policy or {}).get(key) or {}
        if isinstance(e.get("rate"), (int, float)):
            pol.append(f"{icon} {nm} {e['rate']:.2f}%")
    if pol:
        blocks.append(("pol", "🏦 *政策金利*\n" + "\n".join(pol)))

    # 🎯 3シナリオ
    try:
        rows = []
        for _k, nm, pr, txt in _scenarios(scenario):
            ic = {"強気": "🟢", "中立": "🟡", "弱気": "🔴"}.get(nm, "⚪")
            pr_s = f"（{pr}%）" if pr is not None else ""
            rows.append(f"{ic} *{nm}*{pr_s} {_t(txt)[:110]}")
        if rows:
            blocks.append(("scn", "🎯 *3つの筋書き*\n" + "\n".join(rows)))
        risk_txt = _t((scenario or {}).get("top_risk") or "")[:130]
        if risk_txt:
            blocks.append(("risk", f"⚠️ *いちばんの気がかり*\n{risk_txt}"))
    except Exception:
        logger.error("シナリオを作れませんでした", exc_info=True)

    # 🐘 今日の構え
    act = ("恐怖指数が高い日です。*同じ株数でも損得の振れ幅が大きくなります。*"
           "株数を減らす・損切りを広めに置く・待つ、のどれかを選ぶ場面。"
           if isinstance(nvi_pct, (int, float)) and nvi_pct >= 85 else
           "大きく荒れてはいません。いつもどおりで構いませんが、"
           "*決めた損切りの線は動かさない*ことだけ守ってください。")
    blocks.append(("act", f"🐘 *今日の構え*\n{act}"))

    tail = ("📚 出典: 日本経済新聞社・Yahoo Finance・nikkei225jp.com・株探\n"
            "📖 グラフ・写真・動画つきの記事は下のボタンから")

    # ⚠️ 上から詰めて上限に収める。途中で切らず**ブロックごと落とす**
    #    （文の途中で切れると意味が変わる。priority.py と同じ考え方）。
    out = "\n".join(head)
    for _, b in blocks:
        if len(out) + len(b) + len(tail) + 6 > limit:
            logger.info(f"字数のため以降のブロックを省きました（{len(out)}字）")
            break
        out += "\n\n" + b
    return out + "\n\n" + tail


def render_png(html: str, out_path: str) -> bool:
    """HTMLを1枚のPNGにする。Playwrightが無ければ False（呼び出し側で代替へ）。

    ⚠️ `wait_until="networkidle"` にしない。写真や動画のサムネイルを
       外から読むようになったので、1枚でも遅い画像があると待ち続ける。
       `load` で待ち、そのあと少しだけ時間を置いて画像の到着を待つ。
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.info("playwright が無いため、従来のカード画像を使います")
        return False
    try:
        with sync_playwright() as pw:
            br = pw.chromium.launch(args=["--no-sandbox"])

            # ⚠️ **中身を削って縮めない。** Telegram の「幅＋高さ ≤ 10000」は
            #    実寸の話なので、倍率(device_scale_factor)を下げれば収まる。
            #    倍率は**粗さ**だけを変え、実機での文字の大きさは変えない
            #    （文字の大きさを決めるのは CSS幅 ÷ チャット幅 だけ）。
            #    なので「長い記事＝字が小さい」ではない。削るのは最後の手段。
            probe = br.new_page(viewport={"width": TG_W, "height": 1000},
                                device_scale_factor=1)
            probe.set_content(html, wait_until="load")
            try:
                probe.wait_for_load_state("networkidle", timeout=12000)
            except Exception:
                pass
            probe.wait_for_timeout(800)
            h_css = probe.evaluate(
                "() => Math.ceil(document.querySelector('#feed')"
                ".getBoundingClientRect().height)") or 1200
            probe.close()

            dsf = min(2.0, (TG_MAX_SUM - 200) / max(1, TG_W + h_css))
            dsf = max(1.0, round(dsf, 2))
            logger.info(f"記事の高さ {h_css}px → 倍率 {dsf}（実寸 "
                        f"{int(TG_W * dsf)}x{int(h_css * dsf)}）")

            page = br.new_page(viewport={"width": TG_W, "height": 1200},
                               device_scale_factor=dsf)
            page.set_content(html, wait_until="load")
            # 外から読む写真が入るので、少し待ってから撮る。
            # 待たないと**写真の枠だけが空で写る**（実際に一度やった）。
            try:
                page.wait_for_load_state("networkidle", timeout=12000)
            except Exception:
                logger.debug("画像の読み込み待ちが時間切れ。そのまま撮ります")
            page.wait_for_timeout(1200)
            page.locator("#feed").screenshot(path=out_path)
            br.close()
        return True
    except Exception as e:
        logger.warning(f"フィード画像の描画に失敗（従来のカードへ）: {e}")
        return False


TG_MAX_SUM = 10000      # Telegram の sendPhoto は 幅+高さ がこれを超えると拒否する


def make_feed_image(out_path: str, **kw) -> str | None:
    """Telegram用のフィード画像を作ってパスを返す。作れなければ None。"""
    try:
        html = build_compact(**kw)
        if not html:
            return None
        if not render_png(html, out_path):
            return None

        # ⚠️ 出来た画像の寸法を**必ず確かめる。**
        #    Telegram は 幅+高さ > 10000 の写真を受け取らない。
        #    文章が長い日に静かに超えて、その朝だけ通知が画像なしになる
        #    （しかもログには出ない）のがいちばん困る。ここで気づく。
        try:
            from PIL import Image
            with Image.open(out_path) as im:
                w, h = im.size
            if w + h > TG_MAX_SUM:
                logger.error(
                    f"フィード画像が大きすぎます {w}x{h}（幅+高さ={w + h} > "
                    f"{TG_MAX_SUM}）。Telegramが拒否するため従来のカードに落とします。"
                    f"載せる項目を減らすか build_compact の分量を見直してください")
                return None
            logger.info(f"フィード画像 {w}x{h}px（幅+高さ={w + h}／上限{TG_MAX_SUM}）")
        except ImportError:
            logger.debug("Pillow が無いため画像の寸法確認は省略します")
        return out_path
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
