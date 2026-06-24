"""
日経225 内部データ（騰落・空売り・新高安・PER/PBR/配当）取得モジュール
nikkei225jp.com が公開している daily2year.json から、ブラウザを介さず直接取得する。

このサイトは Highcharts で描画しており画面上は JS 依存だが、元データは
  https://nikkei225jp.com/_data/_nfsDATA/DAY/daily2year.json
に「var DAILY = [[...],[...]]」形式で全公開されている（2年分・日次）。
JSコードを解析して列の意味を確定済み：

  [0]  日時(ms, JST)        [1]  日経225 終値      [2]  出来高
  [5]  値上がり銘柄数        [6]  値下がり銘柄数
  [8]  新高値銘柄数          [9]  新安値銘柄数
  [12] PER                   [13] PBR              [14] 配当利回り(%)
  [17] ドル円                [18] ユーロ円
  [20] 実売買代金 比率(%)    [22] 空売り(規制あり)% [24] 空売り(規制なし)%

  ・騰落レシオ(N日) = N日間の値上がり合計 ÷ 値下がり合計 × 100   ← サイトのJSと同一ロジック
  ・空売り比率       = [22] + [24]                                ← サイトのJSと同一ロジック

⚠️ APIキー不要。サイト構造変更で取れなくなる可能性あり（その場合は欠損扱い）。
   投資判断はご自身で。これらは市場全体の過熱・悲観の目安。
"""
import json
import re
from datetime import datetime, timezone, timedelta

import requests

from src.utils import setup_logger

logger = setup_logger("nikkei_market_data")

_URL = "https://nikkei225jp.com/_data/_nfsDATA/DAY/daily2year.json"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://nikkei225jp.com/data/touraku.php",
}
_JST = timezone(timedelta(hours=9))

# 列インデックス（nikkei225jp.com の生データを 2026-06-23 のスクショと1列ずつ照合して確定）
#   [1]日経225 [2]プライム出来高(百万株) [5]値上り [6]値下り [7]騰落レシオ25日(計算済)
#   [8]新高値 [9]新安値 [11]日経VI [12]PER [13]PBR [14]日本10年金利 [16]配当利回り
#   [17]ドル円 [18]ユーロ円 [22]空売り規制あり% [24]空売り規制なし%
#   ※益回り=100/PER, EPS=日経/PER, BPS=日経/PBR, イールドスプレッド=益回り-10年金利
C_DATE, C_CLOSE, C_VOL = 0, 1, 2
C_UP, C_DOWN = 5, 6
C_TRK25_STORED = 7        # サイトが計算済みの25日騰落レシオ
C_NEWHIGH, C_NEWLOW = 8, 9
C_NVI = 11                # 日経VI（日本版恐怖指数）
C_PER, C_PBR = 12, 13
C_JGB10 = 14              # 日本10年国債金利(%)
C_YIELD = 16             # 配当利回り(%)  ← 以前[14]と誤っていたのを修正
C_USDJPY, C_EURJPY = 17, 18
C_SHORT_REG, C_SHORT_NOREG = 22, 24


def _sanitize_js_array(text: str) -> list:
    """var DAILY = [...]; を Python リストへ。空フィールドの ,, を ,"" に補正してパース"""
    body = text[text.find("["):text.rfind("]") + 1]
    # 連続カンマ（空フィールド）を空文字に補正： ,, → ,"",  / [, → ["",  / ,] → ,""]
    prev = None
    while prev != body:
        prev = body
        body = re.sub(r',(\s*[,\]])', r',""\1', body)
        body = re.sub(r'(\[\s*),', r'\1"",', body)
    return json.loads(body)


def _f(v):
    """数値化（空文字・None は None）"""
    if v in ("", None):
        return None
    try:
        f = float(v)
        return f
    except (ValueError, TypeError):
        return None


def fetch_daily() -> list:
    """daily2year.json を取得してパース。新しい順ではなく古い→新しい順のまま返す"""
    r = requests.get(_URL, headers=_HEADERS, timeout=15)
    r.raise_for_status()
    rows = _sanitize_js_array(r.content.decode("utf-8", errors="replace"))
    # 日経終値が入っている有効行だけ残す（休場・データ無し行を除外）
    valid = [row for row in rows if _f(row[C_CLOSE]) is not None and _f(row[C_UP]) is not None]
    return valid


def _date_str(ms) -> str:
    return datetime.fromtimestamp(float(ms) / 1000, _JST).strftime("%Y-%m-%d")


def _trk(rows: list, n: int):
    """騰落レシオ（N日）= N日間の値上がり合計 ÷ 値下がり合計 × 100"""
    seg = rows[-n:]
    ups = sum(_f(r[C_UP]) or 0 for r in seg)
    dws = sum(_f(r[C_DOWN]) or 0 for r in seg)
    if dws <= 0:
        return None
    return round(ups / dws * 100, 1)


def _trk_comment(trk25) -> str:
    """騰落レシオの目安コメント（25日）"""
    if trk25 is None:
        return ""
    if trk25 >= 120:
        return "過熱圏（短期は反落に注意）"
    if trk25 >= 100:
        return "やや強い（買い優勢）"
    if trk25 >= 80:
        return "中立〜やや弱い"
    if trk25 >= 70:
        return "売られすぎ気味（反発の芽）"
    return "底値圏のサイン（売られすぎ）"


def _short_comment(short) -> str:
    if short is None:
        return ""
    if short >= 45:
        return "売り方が積極的（高水準）"
    if short >= 40:
        return "やや売り圧力強め"
    if short >= 35:
        return "おおむね平常"
    return "売り圧力は限定的"


def _per_comment(per) -> str:
    """日経PERの割安・割高の目安（日経平均は概ね13〜16倍が標準レンジ）"""
    if per is None:
        return ""
    if per >= 18:
        return "やや割高（利益の伸び以上に買われ気味）"
    if per >= 16:
        return "標準やや上"
    if per >= 13:
        return "標準的なレンジ"
    if per >= 11:
        return "やや割安（押し目妙味）"
    return "割安圏（売られすぎの可能性）"


def _spread_comment(spread) -> str:
    """イールドスプレッド（株式益回り − 10年金利）。大きいほど株が債券より割安"""
    if spread is None:
        return ""
    if spread >= 5:
        return "株は債券よりかなり割安"
    if spread >= 3.5:
        return "株はやや割安"
    if spread >= 2:
        return "ほぼ中立"
    return "株の割安感は乏しい"


def _nvi_comment(nvi) -> str:
    """日経VI（日本版恐怖指数）。20以下=平穏、30超=警戒、40超=パニック"""
    if nvi is None:
        return ""
    if nvi >= 40:
        return "パニック的な警戒（底値圏のことも）"
    if nvi >= 30:
        return "警戒感が強い"
    if nvi >= 22:
        return "やや神経質"
    return "落ち着いている"


def _plain_summary(d: dict) -> dict:
    """専門用語ゼロで「今日の東証はこういう状態」を中学生にもわかる言葉でまとめる"""
    per = d.get("per"); spread = d.get("spread"); trk = d.get("trk25")
    nvi = d.get("nvi"); short = d.get("short_ratio"); breadth = d.get("breadth_pct")

    lines = []
    if per is not None:
        if per >= 18:
            lines.append(f"📐 今の株価は会社の利益に対して<b>やや高め（割高ぎみ）</b>。PERは{per}倍で、ふだんの13〜16倍より上です。")
        elif per <= 13:
            lines.append(f"📐 今の株価は<b>お買い得ゾーン（割安）</b>。PERは{per}倍と低めです。")
        else:
            lines.append(f"📐 今の株価は<b>ふつうの範囲</b>。PERは{per}倍で行き過ぎ感はありません。")
    if spread is not None:
        if spread >= 3.5:
            lines.append("⚖️ ただし<b>銀行預金や国債より株のほうがお得</b>な水準。長い目で見れば株に分があります。")
        elif spread >= 2:
            lines.append("⚖️ 株と債券（国債）の魅力は<b>ほぼ互角</b>。どちらが得とも言いにくい状態です。")
        else:
            lines.append("⚖️ 国債の利回りが上がり、<b>株のお得感はやや薄れ気味</b>です。")
    if trk is not None:
        if trk >= 120:
            lines.append("🌡 短期的には<b>買われすぎ（過熱ぎみ）</b>。一服・反落に注意したい場面です。")
        elif trk <= 70:
            lines.append("🌡 短期的には<b>売られすぎ</b>。そろそろ反発（リバウンド）が出やすい水準です。")
        else:
            lines.append("🌡 短期の過熱感は<b>なくほどほど</b>。行き過ぎたサインは出ていません。")
    if nvi is not None:
        if nvi >= 30:
            lines.append("😨 投資家の不安は<b>やや高め（警戒モード）</b>。値動きが荒くなりやすいので慎重に。")
        elif nvi >= 22:
            lines.append("😨 投資家の心理は<b>やや神経質</b>。大きなニュースに振られやすい状態です。")
        else:
            lines.append("😌 投資家の心理は<b>落ち着いて</b>います。")
    extra = []
    if breadth is not None:
        if breadth >= 55:
            extra.append("この日は値上がりした銘柄のほうが多め")
        elif breadth <= 45:
            extra.append("この日は値下がりした銘柄のほうが多め")
    if short is not None and short >= 40:
        extra.append("売り方（空売り）もそこそこ活発")
    if extra:
        lines.append("📊 " + "、".join(extra) + "でした。")

    warn = 0
    if per is not None and per >= 18: warn += 1
    if nvi is not None and nvi >= 30: warn += 1
    if trk is not None and (trk >= 120 or trk <= 70): warn += 1
    if breadth is not None and breadth <= 45: warn += 1
    if warn >= 3:
        head, emo, hc = "様子見・守りも意識したい一日", "🟡", "#d29922"
    elif warn <= 1 and (spread is None or spread >= 3.5):
        head, emo, hc = "落ち着いて買い場を探せる地合い", "🟢", "#3fb950"
    else:
        head, emo, hc = "良い点・注意点が混在。欲張らず慎重に", "🟡", "#d29922"

    return {"head": head, "emoji": emo, "color": hc, "lines": lines}


def run(prices: dict = None, risk: dict = None, fear_greed: dict = None) -> dict:
    """日経225の内部データを取得して指標化する"""
    try:
        rows = fetch_daily()
    except Exception as e:
        logger.warning(f"daily2year取得失敗: {e}")
        return {"available": False, "reason": str(e)}

    if len(rows) < 25:
        return {"available": False, "reason": "データ不足"}

    last = rows[-1]
    prev = rows[-2]

    date    = _date_str(last[C_DATE])
    close   = _f(last[C_CLOSE])
    up      = int(_f(last[C_UP]) or 0)
    down    = int(_f(last[C_DOWN]) or 0)
    newhigh = int(_f(last[C_NEWHIGH]) or 0)
    newlow  = int(_f(last[C_NEWLOW]) or 0)
    per     = _f(last[C_PER])
    pbr     = _f(last[C_PBR])
    yield_  = _f(last[C_YIELD])
    jgb10   = _f(last[C_JGB10])
    nvi     = _f(last[C_NVI])
    usdjpy  = _f(last[C_USDJPY])

    # バリュエーション派生値
    earnings_yield = round(100 / per, 2) if per else None          # 株式益回り
    eps = round(close / per, 1) if (close and per) else None        # 1株利益
    bps = round(close / pbr, 0) if (close and pbr) else None        # 1株純資産
    spread = round(earnings_yield - jgb10, 2) if (earnings_yield is not None and jgb10 is not None) else None

    short_reg   = _f(last[C_SHORT_REG]) or 0
    short_noreg = _f(last[C_SHORT_NOREG]) or 0
    short_total = round(short_reg + short_noreg, 1) if (short_reg or short_noreg) else None

    # 騰落レシオ：サイト計算済みの[7]を優先、無ければ自前計算
    trk25 = _f(last[C_TRK25_STORED]) or _trk(rows, 25)
    trk6  = _trk(rows, 6)

    breadth = round(up / (up + down) * 100, 0) if (up + down) > 0 else None

    # ── チャート用の推移（直近120営業日）──
    seg = rows[-120:]

    def _short_of(r):
        a = _f(r[C_SHORT_REG]); b = _f(r[C_SHORT_NOREG])
        return round((a or 0) + (b or 0), 1) if (a or b) else None

    def _breadth_of(r):
        u = _f(r[C_UP]); dn = _f(r[C_DOWN])
        return round(u / (u + dn) * 100, 0) if (u and dn and (u + dn) > 0) else None

    series = {
        "dates":  [_date_str(r[C_DATE])[5:] for r in seg],             # MM-DD
        "close":  [_f(r[C_CLOSE]) for r in seg],
        "per":    [_f(r[C_PER]) for r in seg],
        "pbr":    [_f(r[C_PBR]) for r in seg],
        "eyield": [round(100 / _f(r[C_PER]), 2) if _f(r[C_PER]) else None for r in seg],
        "dyield": [_f(r[C_YIELD]) for r in seg],
        "jgb10":  [_f(r[C_JGB10]) for r in seg],
        "trk25":  [_f(r[C_TRK25_STORED]) for r in seg],
        "nvi":    [_f(r[C_NVI]) for r in seg],
        "short":  [_short_of(r) for r in seg],
        "breadth":[_breadth_of(r) for r in seg],
        "newhigh":[_f(r[C_NEWHIGH]) for r in seg],
        "newlow": [_f(r[C_NEWLOW]) for r in seg],
    }

    result = {
        "available": True,
        "date": date,
        "close": close,
        "advancing": up,
        "declining": down,
        "breadth_pct": breadth,
        "new_high": newhigh,
        "new_low": newlow,
        "trk25": trk25,
        "trk6": trk6,
        "trk25_comment": _trk_comment(trk25),
        "short_ratio": short_total,
        "short_reg": round(short_reg, 1) if short_reg else None,
        "short_noreg": round(short_noreg, 1) if short_noreg else None,
        "short_comment": _short_comment(short_total),
        "per": per,
        "pbr": pbr,
        "yield": yield_,
        "jgb10": jgb10,
        "nvi": nvi,
        "earnings_yield": earnings_yield,
        "eps": eps,
        "bps": bps,
        "spread": spread,
        "per_comment": _per_comment(per),
        "spread_comment": _spread_comment(spread),
        "nvi_comment": _nvi_comment(nvi),
        "usdjpy": usdjpy,
        "series": series,
        "trk25_series": [_trk(rows[: i + 1], 25) for i in range(max(25, len(rows) - 60), len(rows))],
    }
    result["telegram_message"] = build_telegram_message(result)
    result["html"] = get_html(result)
    logger.info(f"✅ 日経内部データ: PER{per} 配当{yield_}% 益回り{earnings_yield} 騰落レシオ{trk25} 空売り{short_total}% 日経VI{nvi}")
    return result


def build_telegram_message(d: dict) -> str:
    if not d.get("available"):
        return ""
    up, down = d["advancing"], d["declining"]
    breadth = d.get("breadth_pct")
    trk25 = d.get("trk25")
    short = d.get("short_ratio")

    # 1行目＝通知バーに出る要点
    if trk25 is not None and trk25 >= 120:
        head = f"🌡 騰落レシオ{trk25}・過熱圏（東証の中身）"
    elif trk25 is not None and trk25 <= 70:
        head = f"🌡 騰落レシオ{trk25}・売られすぎ（東証の中身）"
    else:
        head = f"🌡 東証の中身：値上り{up}／値下り{down}"

    lines = [head, ""]
    # やさしい総括を先頭に
    ps = _plain_summary(d)
    lines.append(f"🔰 *ひとことで言うと*：{ps['emoji']} {ps['head']}")
    for ln in ps["lines"]:
        lines.append("　" + ln.replace("<b>", "").replace("</b>", ""))
    lines.append("")
    lines.append("―― くわしい数字 ――")
    if breadth is not None:
        mood = "買い優勢" if breadth >= 55 else ("売り優勢" if breadth <= 45 else "拮抗")
        lines.append(f"📈 値上がり比率：{breadth:.0f}%（{mood}）")
    lines.append(f"　 値上がり {up} 銘柄 / 値下がり {down} 銘柄")
    if trk25 is not None:
        lines.append(f"🌡 騰落レシオ(25日)：{trk25}　{d.get('trk25_comment','')}")
    if d.get("new_high") is not None:
        lines.append(f"🆕 新高値 {d['new_high']} / 新安値 {d['new_low']}")
    if short is not None:
        lines.append(f"🩳 空売り比率：{short}%　{d.get('short_comment','')}")
    lines.append("")
    # バリュエーション（割安・割高）
    if d.get("per") is not None:
        lines.append(f"📐 日経PER {d['per']}（{d.get('per_comment','')}）")
        lines.append(f"　 PBR {d['pbr']} ・ EPS {d.get('eps','—')}円 ・ 配当利回り {d['yield']}%")
    if d.get("spread") is not None:
        lines.append(f"⚖️ イールドスプレッド {d['spread']}％pt（{d.get('spread_comment','')}）")
        lines.append(f"　 株式益回り {d.get('earnings_yield')}% − 10年金利 {d.get('jgb10')}%")
    if d.get("nvi") is not None:
        lines.append(f"😨 日経VI（恐怖指数）{d['nvi']}（{d.get('nvi_comment','')}）")
    lines.append("")
    lines.append("※市場全体の過熱・悲観・割安割高の目安です（東証プライム）")
    return "\n".join(lines)


def get_html(d: dict) -> str:
    if not d.get("available"):
        return ""
    up, down = d["advancing"], d["declining"]
    total = max(up + down, 1)
    up_w = up / total * 100
    breadth = d.get("breadth_pct")
    trk25 = d.get("trk25")
    short = d.get("short_ratio")

    def chip(label, value, sub="", color="#58a6ff"):
        sub_html = f'<div style="font-size:0.68em;color:#7a8fa8;margin-top:2px;">{sub}</div>' if sub else ""
        return f'''
<div style="flex:1;min-width:128px;background:#0f1623;border:1px solid #1e2d42;border-radius:10px;padding:11px 13px;">
  <div style="font-size:0.7em;color:#7a8fa8;">{label}</div>
  <div style="font-size:1.25em;font-weight:800;color:{color};margin-top:2px;">{value}</div>
  {sub_html}
</div>'''

    trk_color = "#f85149" if (trk25 and trk25 >= 120) else ("#3fb950" if (trk25 and trk25 >= 100) else ("#d29922" if (trk25 and trk25 < 80) else "#58a6ff"))
    short_color = "#f85149" if (short and short >= 42) else "#58a6ff"

    # ── 需給チップ ──
    chips = ""
    if breadth is not None:
        mood = "買い優勢" if breadth >= 55 else ("売り優勢" if breadth <= 45 else "拮抗")
        chips += chip("値上がり比率", f"{breadth:.0f}%", mood, "#3fb950" if breadth >= 50 else "#f85149")
    if trk25 is not None:
        chips += chip("騰落レシオ(25日)", trk25, d.get("trk25_comment", ""), trk_color)
    if short is not None:
        chips += chip("空売り比率", f"{short}%", d.get("short_comment", ""), short_color)
    if d.get("new_high") is not None:
        chips += chip("新高値 / 新安値", f"{d['new_high']} / {d['new_low']}",
                      "52週ベース", "#3fb950" if d['new_high'] >= d['new_low'] else "#f85149")
    if d.get("nvi") is not None:
        nvi_c = "#f85149" if d["nvi"] >= 30 else ("#d29922" if d["nvi"] >= 22 else "#3fb950")
        chips += chip("日経VI（恐怖指数）", d["nvi"], d.get("nvi_comment", ""), nvi_c)

    # ── バリュエーション・チップ ──
    vchips = ""
    if d.get("per") is not None:
        per_c = "#f85149" if d["per"] >= 18 else ("#3fb950" if d["per"] <= 13 else "#8aa0c0")
        vchips += chip("日経PER", f"{d['per']}倍", d.get("per_comment", ""), per_c)
    if d.get("pbr") is not None:
        vchips += chip("日経PBR", f"{d['pbr']}倍", f"1株純資産 {d.get('bps','—')}円", "#8aa0c0")
    if d.get("earnings_yield") is not None:
        vchips += chip("株式益回り", f"{d['earnings_yield']}%", f"EPS {d.get('eps','—')}円", "#58a6ff")
    if d.get("yield") is not None:
        vchips += chip("配当利回り", f"{d['yield']}%", "配当でもらえる率", "#3fb950")
    if d.get("spread") is not None:
        sp_c = "#3fb950" if d["spread"] >= 3.5 else ("#d29922" if d["spread"] >= 2 else "#f85149")
        vchips += chip("イールドスプレッド", f"{d['spread']}pt", d.get("spread_comment", ""), sp_c)
    if d.get("jgb10") is not None:
        vchips += chip("日本10年金利", f"{d['jgb10']}%", "債券の利回り（比較用）", "#8aa0c0")

    # ── 値上がり/値下がり バー ──
    bar = f'''
<div style="margin:6px 0 14px;">
  <div style="display:flex;height:26px;border-radius:8px;overflow:hidden;font-size:0.72em;font-weight:700;">
    <div style="width:{up_w:.0f}%;background:#238636;color:#fff;display:flex;align-items:center;justify-content:center;">値上り {up}</div>
    <div style="width:{100-up_w:.0f}%;background:#b62324;color:#fff;display:flex;align-items:center;justify-content:center;">値下り {down}</div>
  </div>
</div>'''

    # ── Chart.js 個別推移チャート（指標ごとに1枚ずつ）──
    import json as _json
    s = d.get("series", {})
    cid = f"nmd{abs(hash(d.get('date',''))) % 100000}"
    chart_html = ""
    if s.get("dates"):
        labels = _json.dumps(s["dates"], ensure_ascii=False)

        def _arr(key, dp=2):
            return _json.dumps([round(x, dp) if isinstance(x, (int, float)) else None for x in s.get(key, [])])

        # 各チャートの定義（canvasサフィックス, 見出し, JS datasets, y軸オプション）
        # 単線チャートのカードを作るヘルパ（参照ラインband付き）
        def _card(suffix, title, sub):
            return (f'<div style="background:#0f1623;border:1px solid #1e2d42;border-radius:10px;padding:11px 12px;">'
                    f'<div style="font-size:0.8em;color:#cdd9ec;font-weight:700;">{title}</div>'
                    f'<div style="font-size:0.66em;color:#7a8fa8;margin-bottom:5px;">{sub}</div>'
                    f'<div style="position:relative;height:150px;"><canvas id="{cid}_{suffix}"></canvas></div></div>')

        cards = "".join([
            _card("close", "📈 日経225 株価", "市場全体の方向"),
            _card("per",   "📐 PER（株価収益率）", "標準13〜16倍／高いほど割高"),
            _card("pbr",   "📕 PBR（株価純資産倍率）", "1倍が解散価値の目安"),
            _card("yield", "⚖️ 益回り・配当利回り・10年金利", "益回り＞金利なら株は割安"),
            _card("trk",   "🌡 騰落レシオ(25日)", "70=売られすぎ／120=過熱"),
            _card("nvi",   "😨 日経VI（恐怖指数）", "20=平穏／30超=警戒"),
            _card("short", "🩳 空売り比率", "40%超＝売り圧力強め"),
            _card("nh",    "🆕 新高値・新安値 銘柄数", "高値超え＝強い相場"),
        ])

        chart_html = f'''
<div style="font-size:0.78em;color:#9fb4d4;font-weight:700;margin:2px 0 8px;">📊 各指標の推移（直近120営業日）</div>
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:10px;margin-bottom:14px;">{cards}</div>
<script>
(function(){{
  function line(id,sets,pct,refs){{
    var el=document.getElementById(id); if(!el||el._d)return; el._d=1;
    var ann=(refs||[]).map(function(r){{return r;}});
    new Chart(el,{{type:'line',data:{{labels:{labels},datasets:sets}},options:{{
      responsive:true,maintainAspectRatio:false,interaction:{{mode:'index',intersect:false}},
      plugins:{{legend:{{display:sets.length>1,labels:{{color:'#cdd9ec',font:{{size:9}},boxWidth:10}}}}}},
      scales:{{x:{{ticks:{{color:'#7a8fa8',maxTicksLimit:6,font:{{size:8}}}},grid:{{color:'rgba(255,255,255,.04)'}}}},
        y:{{ticks:{{color:'#7a8fa8',font:{{size:9}},callback:function(v){{return pct?v+'%':v;}}}},grid:{{color:'rgba(255,255,255,.05)'}}}}}}}}}});
  }}
  function draw(){{
    if(typeof Chart==='undefined')return setTimeout(draw,200);
    line("{cid}_close",[{{label:'日経225',data:{_arr('close',0)},borderColor:'#e6b800',backgroundColor:'rgba(230,184,0,.08)',fill:true,tension:.25,pointRadius:0,borderWidth:2}}]);
    line("{cid}_per",[{{label:'PER',data:{_arr('per')},borderColor:'#58a6ff',backgroundColor:'rgba(88,166,255,.08)',fill:true,tension:.25,pointRadius:0,borderWidth:2}}]);
    line("{cid}_pbr",[{{label:'PBR',data:{_arr('pbr')},borderColor:'#d29922',backgroundColor:'rgba(210,153,34,.08)',fill:true,tension:.25,pointRadius:0,borderWidth:2}}]);
    line("{cid}_yield",[
      {{label:'益回り',data:{_arr('eyield')},borderColor:'#3fb950',tension:.25,pointRadius:0,borderWidth:2}},
      {{label:'配当',data:{_arr('dyield')},borderColor:'#e8a0c0',tension:.25,pointRadius:0,borderWidth:2}},
      {{label:'10年金利',data:{_arr('jgb10')},borderColor:'#8aa0c0',borderDash:[4,3],tension:.25,pointRadius:0,borderWidth:2}}
    ],true);
    line("{cid}_trk",[{{label:'騰落レシオ',data:{_arr('trk25',1)},borderColor:'#7ee787',backgroundColor:'rgba(126,231,135,.07)',fill:true,tension:.25,pointRadius:0,borderWidth:2}}]);
    line("{cid}_nvi",[{{label:'日経VI',data:{_arr('nvi',1)},borderColor:'#f85149',backgroundColor:'rgba(248,81,73,.08)',fill:true,tension:.25,pointRadius:0,borderWidth:2}}]);
    line("{cid}_short",[{{label:'空売り比率',data:{_arr('short',1)},borderColor:'#a371f7',backgroundColor:'rgba(163,113,247,.08)',fill:true,tension:.25,pointRadius:0,borderWidth:2}}],true);
    line("{cid}_nh",[
      {{label:'新高値',data:{_arr('newhigh',0)},borderColor:'#3fb950',tension:.25,pointRadius:0,borderWidth:2}},
      {{label:'新安値',data:{_arr('newlow',0)},borderColor:'#f85149',tension:.25,pointRadius:0,borderWidth:2}}
    ]);
  }}
  if(!window.Chart){{var sc=document.createElement('script');sc.src='https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js';sc.onload=draw;document.head.appendChild(sc);}}else{{draw();}}
}})();
</script>'''

    # ── やさしい総括（専門用語ゼロの解説）──
    ps = _plain_summary(d)
    ps_lines = "".join(f'<div style="font-size:0.82em;color:#dde8ff;line-height:1.7;margin-top:3px;">{ln}</div>' for ln in ps["lines"])
    plain_box = f'''
<div style="background:#11203a;border:1px solid {ps['color']}66;border-left:4px solid {ps['color']};border-radius:0 12px 12px 0;padding:13px 15px;margin-bottom:14px;">
  <div style="font-size:0.72em;color:#9fb4d4;font-weight:700;">🔰 ひとことで言うと（やさしい解説）</div>
  <div style="font-size:1.05em;font-weight:800;color:{ps['color']};margin:3px 0 6px;">{ps['emoji']} {ps['head']}</div>
  {ps_lines}
</div>'''

    return f'''
<div style="background:#0d1117;border:1px solid #1e2d42;border-radius:14px;padding:16px;">
  <div style="font-size:0.75em;color:#7a8fa8;margin-bottom:10px;">
    東証プライムの「中身」。値上がり銘柄数・騰落レシオ・空売り・PER/PBR・益回りで市場全体の過熱／悲観・割安／割高を見る（{d.get("date","")} 時点）
  </div>
  {plain_box}
  {bar}
  <div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px;">{chips}</div>
  {chart_html}
  <div style="font-size:0.78em;color:#9fb4d4;font-weight:700;margin-bottom:6px;">💴 バリュエーション（割安・割高の目安）</div>
  <div style="display:flex;flex-wrap:wrap;gap:8px;">{vchips}</div>
</div>'''


if __name__ == "__main__":
    r = run()
    out = []
    if r.get("available"):
        out.append(f"=== 日経225 内部データ（{r['date']}）===")
        out.append(f"日経終値: {r['close']:.0f}")
        out.append(f"値上がり: {r['advancing']} / 値下がり: {r['declining']}（値上がり比率 {r['breadth_pct']:.0f}%）")
        out.append(f"騰落レシオ 25日: {r['trk25']}（{r['trk25_comment']}） / 6日: {r['trk6']}")
        out.append(f"新高値: {r['new_high']} / 新安値: {r['new_low']}")
        out.append(f"空売り比率: {r['short_ratio']}%（規制あり{r['short_reg']}% + 規制なし{r['short_noreg']}%）{r['short_comment']}")
        out.append(f"日経VI（恐怖指数）: {r['nvi']}（{r['nvi_comment']}）")
        out.append(f"日経PER: {r['per']}倍（{r['per_comment']}） / PBR: {r['pbr']}倍")
        out.append(f"EPS: {r['eps']}円 / BPS: {r['bps']}円")
        out.append(f"株式益回り: {r['earnings_yield']}% / 配当利回り: {r['yield']}%")
        out.append(f"イールドスプレッド: {r['spread']}pt（益回り{r['earnings_yield']}% − 10年金利{r['jgb10']}%）{r['spread_comment']}")
        out.append(f"ドル円: {r['usdjpy']}")
    else:
        out.append(f"取得失敗: {r.get('reason','')}")
    text = "\n".join(out)
    try:
        print(text)
    except UnicodeEncodeError:
        with open("nmd_output.txt", "w", encoding="utf-8") as f:
            f.write(text)
        print("nmd_output.txt に保存しました")
