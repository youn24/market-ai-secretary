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

# 列インデックス（JS解析で確定）
C_DATE, C_CLOSE, C_VOL = 0, 1, 2
C_UP, C_DOWN = 5, 6
C_NEWHIGH, C_NEWLOW = 8, 9
C_PER, C_PBR, C_YIELD = 12, 13, 14
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
    usdjpy  = _f(last[C_USDJPY])

    short_reg   = _f(last[C_SHORT_REG]) or 0
    short_noreg = _f(last[C_SHORT_NOREG]) or 0
    short_total = round(short_reg + short_noreg, 1) if (short_reg or short_noreg) else None

    trk25 = _trk(rows, 25)
    trk6  = _trk(rows, 6)

    # 値上がり比率
    breadth = round(up / (up + down) * 100, 0) if (up + down) > 0 else None

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
        "usdjpy": usdjpy,
        # チャート用の推移（直近60営業日）
        "trk25_series": [_trk(rows[: i + 1], 25) for i in range(max(25, len(rows) - 60), len(rows))],
    }
    result["telegram_message"] = build_telegram_message(result)
    result["html"] = get_html(result)
    logger.info(f"✅ 日経内部データ: 騰落レシオ25日={trk25} 空売り{short_total}% 新高値{newhigh}/新安値{newlow}")
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
    if d.get("per") is not None:
        lines.append(f"📐 日経PER {d['per']} ・ PBR {d['pbr']} ・ 配当利回り {d['yield']}%")
    lines.append("")
    lines.append("※市場全体の過熱・悲観の目安です（東証プライム）")
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
    if d.get("per") is not None:
        chips += chip("日経PER / PBR", f"{d['per']} / {d['pbr']}", f"配当利回り {d['yield']}%", "#8aa0c0")

    # 値上がり/値下がり バー
    bar = f'''
<div style="margin:6px 0 14px;">
  <div style="display:flex;height:26px;border-radius:8px;overflow:hidden;font-size:0.72em;font-weight:700;">
    <div style="width:{up_w:.0f}%;background:#238636;color:#fff;display:flex;align-items:center;justify-content:center;">値上り {up}</div>
    <div style="width:{100-up_w:.0f}%;background:#b62324;color:#fff;display:flex;align-items:center;justify-content:center;">値下り {down}</div>
  </div>
</div>'''

    return f'''
<div style="background:#0d1117;border:1px solid #1e2d42;border-radius:14px;padding:16px;">
  <div style="font-size:0.75em;color:#7a8fa8;margin-bottom:10px;">
    東証プライムの「中身」。値上がり銘柄数・騰落レシオ・空売り比率などで市場全体の過熱／悲観を見る（{d.get("date","")} 時点）
  </div>
  {bar}
  <div style="display:flex;flex-wrap:wrap;gap:8px;">{chips}</div>
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
        out.append(f"日経PER: {r['per']} / PBR: {r['pbr']} / 配当利回り: {r['yield']}%")
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
