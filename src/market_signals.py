"""
市場内部・リスク指標の監視（Step MS）

すでに毎朝取得しているのに、シグナルとして活かせていなかった指標を判定する。
価格データ（prices）から計算するだけなので、取得コストはゼロ。

  1. SOX指数（米半導体）… 日本のハイテク株の先行指標。夜の動きが翌朝そのまま出る
  2. SKEW指数          … 暴落（ブラックスワン）への備えの厚さ。VIXより先に動くことがある
  3. VVIX              … VIXそのものの荒れ具合。恐怖が「加速するか」を示す
  4. ドル指数(DXY)     … ドル自身の強さ。ドル円だけでは見えない世界の資金の向き
  5. NT倍率(日経÷TOPIX)… 上昇が値がさ株偏重か、全体的か＝相場の“質”

SOXだけは「ゾーン」ではなく前日比の大きさで判定する。
半導体は日本株への波及が速く、水準よりも「昨夜どれだけ動いたか」が効くため。

run(prices) → {"available", "events":[...], "current":{...}, "telegram_block"}
"""
import json
import traceback
from src.utils import setup_logger, get_jst_now, BASE_DIR

logger = setup_logger("market_signals")

_STATE_FILE = BASE_DIR / "data" / "market_signal_state.json"

# SOXは翌朝の日本の半導体株に直結するため、この変動幅を超えたら知らせる
_SOX_ALERT = 2.5

_ZONES = {
    "skew": {
        "label": "SKEW指数（暴落への備え）",
        "what": "急落に備える保険（プットオプション）がどれだけ買われているか。VIXが「今の不安」なら、SKEWは「まさかの急落への警戒」",
        "unit": "",
        "bands": [
            (120.0, "警戒感なし", "🟢", "急落を警戒する動きはほぼ無い。市場は落ち着いている。",
             "この指標からは警戒サインなし。"),
            (135.0, "標準", "🟡", "平常レンジ。特別な警戒は出ていない。",
             "他の指標で判断する局面。"),
            (145.0, "警戒", "🟠", "急落に備える動きが増えている。大口が保険を買い始めた状態。",
             "上昇していても足元を確認したい場面。"),
            (None, "強い警戒", "🔴", "暴落への備えが歴史的に厚い。過去の急落前に出たゾーン。",
             "必ず下がるわけではないが、リスクの取りすぎは避けたい。"),
        ],
    },
    "vvix": {
        "label": "VVIX（恐怖指数の荒れ具合）",
        "what": "VIX自体がどれだけ激しく動くか。VIXが上がる前に先に動くことがあり、より早い警報になる",
        "unit": "",
        "bands": [
            (85.0, "安定", "🟢", "市場心理は落ち着いている。恐怖が急に高まる気配は薄い。",
             "この指標からは問題なし。"),
            (105.0, "標準", "🟡", "平常レンジ。",
             "特段の警戒は不要。"),
            (130.0, "不安定", "🟠", "投資家心理が揺れやすくなっている。VIX急騰の前触れになることがある。",
             "急変に備えて、持ち高を確認しておきたい。"),
            (None, "極めて不安定", "🔴", "恐怖指数そのものが荒れている。相場が大きく振れやすい状態。",
             "無理な取引は避けたい局面。"),
        ],
    },
    "dxy": {
        "label": "ドル指数（ドル自身の強さ）",
        "what": "主要通貨に対するドルの総合的な強さ。ドルが強すぎると新興国や金・原油に逆風が吹く",
        "unit": "",
        "bands": [
            (95.0, "ドル安", "🟢", "ドルが弱い。新興国・コモディティ・金に追い風。",
             "資源国やゴールドに有利な環境。"),
            (105.0, "標準", "🟡", "平常レンジ。",
             "特段の偏りはない。"),
            (110.0, "ドル高", "🟠", "ドルが強い。世界の資金が米国に集まり、他が売られやすい。",
             "新興国株・金には逆風。日本株は円安が支えになる面も。"),
            (None, "極端なドル高", "🔴", "歴史的なドル高水準。世界の金融市場に負荷がかかりやすい。",
             "各国の通貨防衛や政策変更のリスクを意識したい。"),
        ],
    },
    "nt": {
        "label": "NT倍率（日経平均 ÷ TOPIX）",
        "what": "上昇が一部の値がさ株（ファストリ・ソフトバンクG等）に偏っているか、市場全体で上げているかを示す“相場の質”",
        "unit": "倍",
        "bands": [
            (13.0, "全体的な相場", "🟢", "日経とTOPIXが揃って動いている。幅広い銘柄が買われる健全な形。",
             "個別株でも利益を出しやすい地合い。"),
            (14.0, "標準", "🟡", "平常レンジ。",
             "特段の偏りはない。"),
            (14.8, "値がさ株偏重", "🟠", "一部の大型株だけが指数を押し上げている。指数ほど個別株は上がっていない。",
             "「日経は上がったのに自分の株は上がらない」が起きやすい局面。"),
            (None, "極端な偏り", "🔴", "ごく一部の銘柄が指数を吊り上げている状態。相場の足腰は弱い。",
             "指数の強さを鵜呑みにしない。反動が出やすい。"),
        ],
    },
}


_ZONES["margin_pl"] = {
    "label": "信用評価損益率（個人投資家の含み損益）",
    "what": "信用取引をしている個人が平均でどれだけ儲かっているか。常にマイナス圏で推移し、-20%前後まで沈むと追証（追加保証金）による投げ売りが起きて、そこが底になることが多い",
    "unit": "%",
    # 値が小さい（マイナスが深い）ほど売られ過ぎ＝底値圏。並び順に合わせて下から定義
    "bands": [
        (-20.0, "追証ゾーン（底値圏）", "🟢🟢",
         "個人の含み損が極限。追証の強制売りが出やすく、過去はここが大底になってきた。",
         "投げ売りが一巡すれば反発しやすい。長期の買い場になりやすいゾーン。"),
        (-15.0, "悲観", "🟢",
         "個人投資家の含み損がかなり大きい。売られ過ぎの領域。",
         "反発を狙いやすいが、追証売りがもう一段出る可能性も。"),
        (-8.0, "標準", "🟡",
         "平常レンジ。信用取引の需給は特に偏っていない。",
         "この指標からは判断材料にならない。"),
        (-3.0, "楽観", "🟠",
         "含み損が小さい＝個人が儲かっている状態。高値圏で出やすい。",
         "利益確定売りが出やすく、上値が重くなりやすい。"),
        (None, "過熱", "🔴",
         "個人が大きく儲かっている異例の状態。相場の過熱を示す。",
         "反落に注意。新規の追随買いは慎重に。"),
    ],
}

# 週次データ（毎週金曜更新）の取得元。日足と同じ nikkei225jp.com の生JSON。
_WEEKLY_URL = "https://nikkei225jp.com/_data/_nfsDATA/DAY/dailyweek2.json"
_W_MARGIN_PL = 7        # 信用評価損益率(%)
_W_MARGIN_RATIO = 8     # 信用倍率(倍)


def _fetch_weekly():
    """週次の信用データを取得。取れなければ None（他の指標は通常どおり動く）。"""
    try:
        import re
        import requests
        r = requests.get(_WEEKLY_URL, timeout=15, headers={
            "User-Agent": "Mozilla/5.0", "Referer": "https://nikkei225jp.com/data/sinyou.php"})
        r.raise_for_status()
        m = re.search(r"=\s*(\[.*\])\s*;?\s*$", r.text, re.S)
        if not m:
            return None
        rows = json.loads(m.group(1))
        for row in reversed(rows):          # 直近で値が入っている週を探す
            pl = row[_W_MARGIN_PL] if len(row) > _W_MARGIN_PL else ""
            if pl in ("", None):
                continue
            pl = float(pl)
            # 信用評価損益率は歴史的に -40〜+10% の範囲。外れたら列ズレとみなし破棄
            if not (-40.0 <= pl <= 10.0):
                logger.warning(f"信用評価損益率が想定外の値: {pl} → 破棄")
                return None
            ratio = row[_W_MARGIN_RATIO] if len(row) > _W_MARGIN_RATIO else ""
            ratio = float(ratio) if ratio not in ("", None) and 0.3 <= float(ratio) <= 40 else None
            return {"margin_pl": round(pl, 2), "margin_ratio": ratio}
        return None
    except Exception:
        logger.debug(traceback.format_exc())
        return None


def _zone_of(key: str, value):
    if value is None:
        return None
    for i, band in enumerate(_ZONES[key]["bands"]):
        upper = band[0]
        if upper is None or value < upper:
            return (i, band[1], band[2], band[3], band[4])
    return None


def _load_state() -> dict:
    try:
        return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(st: dict) -> None:
    try:
        _STATE_FILE.parent.mkdir(exist_ok=True)
        _STATE_FILE.write_text(json.dumps(st, ensure_ascii=False, indent=1),
                               encoding="utf-8")
    except Exception:
        logger.debug(traceback.format_exc())


def _sox_event(prices: dict):
    """
    SOX（米半導体指数）の前日比。日本の半導体株は翌朝ほぼ同じ方向に動くため、
    水準ではなく「昨夜どれだけ動いたか」を見る。
    """
    d = (prices or {}).get("^SOX") or {}
    chg, val = d.get("change_pct"), d.get("latest")
    if chg is None or abs(chg) < _SOX_ALERT:
        return None
    up = chg > 0
    return {
        "key": "sox",
        "label": "SOX指数（米半導体）",
        "what": "米国の半導体株の指数。東京エレクトロン・アドバンテスト・レーザーテックなど日本のハイテク株は、この動きを翌朝そのまま引き継ぐことが多い",
        "unit": "",
        "value": val, "prev_value": None,
        "zone": f"前日比 {chg:+.2f}%",
        "prev_zone": "—",
        "emoji": "🚀" if up else "📉",
        "meaning": (f"米半導体が{'大きく上昇' if up else '大きく下落'}（{chg:+.2f}%）。"
                    f"日本の半導体関連株に{'追い風' if up else '逆風'}が吹きやすい。"),
        "tip": ("寄り付きで既に織り込まれることが多い。飛びつかず、寄り後の値動きを確認したい。"
                if up else
                "半導体関連は寄り付きから売られやすい。慌てて拾わず落ち着きを待ちたい。"),
        "worse": not up,
    }


def run(prices: dict = None) -> dict:
    prices = prices or {}

    def _v(sym):
        return (prices.get(sym) or {}).get("latest")

    nikkei, topix = _v("^N225"), _v("^TOPX")
    values = {
        "skew": _v("^SKEW"),
        "vvix": _v("^VVIX"),
        "dxy":  _v("DX-Y.NYB"),
        "nt":   round(nikkei / topix, 2) if (nikkei and topix) else None,
    }

    # 信用評価損益率（週次・毎週金曜更新）
    weekly = _fetch_weekly()
    if weekly:
        values["margin_pl"] = weekly["margin_pl"]

    st = _load_state()
    events, new_state = [], {}

    for key, val in values.items():
        z = _zone_of(key, val)
        if not z:
            continue
        idx, name, emoji, meaning, tip = z
        new_state[key] = {"zone": idx, "name": name, "value": val}
        prev = st.get(key)
        if not isinstance(prev, dict) or "zone" not in prev:
            continue          # 初回は記録のみ
        if prev["zone"] == idx:
            continue
        events.append({
            "key": key, "label": _ZONES[key]["label"], "what": _ZONES[key]["what"],
            "unit": _ZONES[key]["unit"], "value": val, "prev_value": prev.get("value"),
            "zone": name, "prev_zone": prev.get("name"),
            "emoji": emoji, "meaning": meaning, "tip": tip,
            "worse": idx > prev["zone"],
        })

    # SOXは毎回「昨夜の変動」で判定する（ゾーンではないので状態保存もしない）
    sox = _sox_event(prices)
    if sox:
        events.insert(0, sox)      # 寄り付きに直結するため先頭に置く
    if (prices.get("^SOX") or {}).get("latest"):
        new_state["sox"] = {"value": prices["^SOX"]["latest"],
                            "chg": prices["^SOX"].get("change_pct")}

    _save_state(new_state)

    if not events:
        logger.info(f"市場内部シグナル: 変化なし（{len(new_state)}指標を監視）")
        return {"available": False, "events": [], "current": new_state}

    now = get_jst_now().strftime("%m/%d")
    lines = [f"🧭 *市場内部シグナルが変化* （{now}）", "━━━━━━━━━━━━━━━"]
    for e in events:
        if e.get("prev_value") is not None:
            head = (f"　{e['prev_value']:.2f} → *{e['value']:.2f}{e['unit']}*　"
                    f"「{e['prev_zone']}」→「*{e['zone']}*」")
        else:
            head = f"　*{e['value']:,.2f}{e['unit']}*　{e['zone']}"
        lines += [f"{e['emoji']} *{e['label']}*", head,
                  f"　📖 {e['what']}", f"　{e['meaning']}", f"　💡 {e['tip']}"]
    lines += ["━━━━━━━━━━━━━━━",
              "相場の「中身」を示す指標です。意味が変わったときだけ通知しています。"]

    logger.info(f"✅ 市場内部シグナル: {len(events)}件")
    return {"available": True, "events": events, "current": new_state,
            "telegram_block": "\n".join(lines)}


if __name__ == "__main__":
    for k, v in (("skew", 150.0), ("vvix", 135.0), ("dxy", 112.0), ("nt", 15.0)):
        z = _zone_of(k, v)
        print(f"{k}={v} -> {z[1]} {z[2]}")
