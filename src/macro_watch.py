"""
マクロ・信用の警戒シグナル監視（Step MW）

「今が高いか安いか」を見るバリュエーション（valuation_watch.py）に対して、
こちらは「この先どうなりそうか」を見る先行指標をまとめて監視する。

監視する5つ:
  1. ハイイールド債スプレッド … 信用不安の温度計。株の暴落に先行しやすい
  2. 逆イールド（10年−2年）   … 景気後退の先行指標として最も実績がある
  3. サーム・ルール            … 失業率から景気後退の開始を判定する経験則
  4. 実質金利（10年）          … 金とハイテク株の評価を左右する“本当の金利”
  5. バフェット指数            … 市場全体が経済規模に対して割高かの長期物差し
  ＋ 日経EPSトレンド           … 株価上昇に企業の利益が伴っているかの裏取り

いずれも日々の細かな上下は無視し、「意味の変わるゾーンを跨いだとき」だけ通知する。
初心者にも伝わるよう、各指標に［これは何か／今どういう状態か／だからどうするか］
の3点セットを必ず添える。

run(nikkei_internals) → {"available", "events":[...], "current":{...}, "telegram_block"}
"""
import json
import traceback
from src.utils import setup_logger, get_jst_now, BASE_DIR

logger = setup_logger("macro_watch")

_STATE_FILE = BASE_DIR / "data" / "macro_state.json"

# FREDの系列ID（APIキー不要のCSVエンドポイントで取得）
_FRED = {
    "hy_spread":  "BAMLH0A0HYM2",   # ハイイールド債スプレッド（%）日次
    "yield_curve": "T10Y2Y",        # 10年−2年（%）日次
    "sahm":       "SAHMREALTIME",   # サーム・ルール指数（%pt）月次
    "real_rate":  "DFII10",         # 10年物価連動債利回り＝実質金利（%）日次
}

# 流動性（カネ余り度）。水準ではなく「増えているか減っているか」が効くため、
# 前年比の変化率で判定する。
_FRED_FLOW = {
    "cb_assets": "WALCL",           # FRB総資産（週次・百万ドル）
    "m2":        "M2SL",            # M2マネーサプライ（月次・十億ドル）
}

# ゾーン定義: (上限, 名前, 絵文字, これは何か+今の状態, だからどうするか)
# 上限は「この値未満ならこのゾーン」。末尾は上限なし。
_ZONES = {
    "hy_spread": {
        "label": "ハイイールド債スプレッド",
        "what": "信用力の低い企業の借入コスト。企業の資金繰り不安が高まると急拡大する",
        "unit": "%",
        "bands": [
            (3.5, "極めて安定", "🟢🟢", "企業の資金繰り不安がほぼ無い状態。投資家がリスクを取れている。",
             "株式に追い風。急拡大に転じないか見ておけば十分。"),
            (5.0, "安定", "🟢", "平常レンジ。信用不安は見られない。",
             "特に警戒は不要なゾーン。"),
            (7.0, "警戒", "🟠", "企業の資金繰りに不安が出始めた。株価の下落に先行することが多い。",
             "リスクを取りすぎていないか点検する場面。"),
            (None, "危険", "🔴", "信用不安が本格化。過去の急落局面（リーマン・コロナ）と同じゾーン。",
             "守りを固める局面。ただし底では急速に縮小するため、反転のサインにもなる。"),
        ],
    },
    "yield_curve": {
        "label": "逆イールド（10年金利 − 2年金利）",
        "what": "長期金利から短期金利を引いた差。マイナス＝逆イールドで、過去の景気後退の大半を先行して当ててきた",
        "unit": "%",
        "bands": [
            (0.0, "逆イールド（警戒）", "🔴", "短期金利が長期を上回る異常な状態。過去は1〜2年後に景気後退が来ることが多かった。",
             "すぐ暴落するわけではない。ただし長期の資産配分を見直す材料にはなる。"),
            (0.5, "ほぼ平坦", "🟠", "金利差がほとんど無い。景気の勢いが鈍っているサイン。",
             "逆イールドに入るか、戻るかの分かれ道。注視したい。"),
            (1.5, "正常", "🟡", "長短金利差が健全な範囲。景気は普通に回っている。",
             "この指標からは警戒シグナルは出ていない。"),
            (None, "急峻化", "🟢", "長短金利差が大きい。景気回復の初期や利下げ局面で出やすい。",
             "銀行株などに追い風が吹きやすいゾーン。"),
        ],
    },
    "sahm": {
        "label": "サーム・ルール（失業率の悪化速度）",
        "what": "失業率の3か月平均が直近1年の最低から何%上がったか。0.5以上で景気後退入りとされる経験則",
        "unit": "%pt",
        "bands": [
            (0.3, "健全", "🟢", "雇用は悪化していない。景気後退の兆候は出ていない。",
             "この指標からは問題なし。"),
            (0.5, "悪化の兆し", "🟠", "失業率がじわり上昇。景気後退ラインに近づいている。",
             "雇用統計の発表に注目したい局面。"),
            (None, "景気後退サイン", "🔴", "0.5を突破。過去はほぼ例外なく景気後退が始まっていた水準。",
             "景気敏感株の比率を見直す材料。ただし株価は先に織り込むことも多い。"),
        ],
    },
    "real_rate": {
        "label": "実質金利（10年・インフレを差し引いた本当の金利）",
        "what": "名目金利から予想インフレを引いた金利。上がると金や高PER株に逆風、下がると追い風",
        "unit": "%",
        "bands": [
            (0.0, "マイナス金利", "🟢🟢", "お金を持っているだけで価値が目減りする状態。株や金に資金が向かいやすい。",
             "金・ハイテク株に追い風のゾーン。"),
            (1.0, "低い", "🟢", "実質金利が低め。リスク資産に有利な環境。",
             "株式にとって居心地の良いゾーン。"),
            (2.0, "標準", "🟡", "平常レンジ。特に有利でも不利でもない。",
             "他の材料で判断する局面。"),
            (None, "高い", "🔴", "実質金利が高く、株より債券が魅力的に見える水準。高PER株には重荷。",
             "グロース株・金には逆風。バリュー株が相対的に有利になりやすい。"),
        ],
    },
    "cb_assets": {
        "label": "FRBの総資産（市場に出回るお金の量）",
        "what": "中央銀行が抱える資産の増減。増える＝市場にお金を流している（緩和）、減る＝回収している（引き締め）。株価の最大の追い風・向かい風になる",
        "unit": "%",
        "bands": [
            (-5.0, "強い引き締め", "🔴", "中央銀行が急ピッチでお金を回収している。株には強い逆風。",
             "上値が重くなりやすい環境。守りを意識したい。"),
            (0.0, "引き締め", "🟠", "お金の量が緩やかに減っている。",
             "相場全体の上昇力は鈍りやすい。"),
            (5.0, "中立", "🟡", "お金の量はほぼ横ばい。",
             "流動性は判断材料にならない局面。"),
            (None, "緩和的", "🟢", "中央銀行がお金を増やしている。株には追い風。",
             "リスク資産に資金が向かいやすい環境。"),
        ],
    },
    "m2": {
        "label": "M2マネーサプライ（世の中のお金の総量）",
        "what": "現金・預金など、実際に使えるお金の総量の前年比。増えれば株や不動産に流れ込みやすい",
        "unit": "%",
        "bands": [
            (0.0, "減少（異例）", "🔴", "お金の総量が前年より減っている。歴史的にも稀で、景気に強い逆風。",
             "リスクを取りにくい環境。現金の価値が相対的に高まる。"),
            (3.0, "低い伸び", "🟠", "お金の増え方が鈍い。",
             "相場の勢いは出にくい。"),
            (8.0, "標準", "🟡", "平常的な増加ペース。",
             "特段の追い風も向かい風もない。"),
            (None, "カネ余り", "🟢", "お金が大きく増えている。株・不動産などに資金が向かいやすい。",
             "資産価格が上がりやすい環境。ただしインフレにも注意。"),
        ],
    },
    "buffett": {
        "label": "バフェット指数（米国株の時価総額 ÷ GDP）",
        "what": "国全体の株価が経済規模の何倍かを見る長期の物差し。バフェット氏が重視すると語ったことで有名",
        "unit": "%",
        "bands": [
            (75.0, "割安", "🟢🟢", "経済規模に対して株価が安い。歴史的には買い場になってきた水準。",
             "長期の積み立てを増やす判断材料になるゾーン。"),
            (100.0, "適正", "🟢", "経済規模と株価がおおむね釣り合っている。",
             "特に警戒も強気も不要。"),
            (140.0, "やや割高", "🟠", "経済規模を大きく上回る株価。過去の平均より高い。",
             "新規の大きな買いは慎重に。"),
            (None, "かなり割高", "🔴", "経済規模の1.4倍超。ITバブル・2021年末と同じゾーン。",
             "長期リターンが低くなりやすい水準。守りも意識したい。"),
        ],
    },
}


def _fetch(series_id: str, limit: int = 400) -> list:
    """FREDのCSVから (日付, 値) を取得する。fred_data.py の実装を再利用。"""
    try:
        from src.fred_data import _fetch_series
        return _fetch_series(series_id, limit=limit)
    except Exception:
        logger.debug(traceback.format_exc())
        return []


def _latest(series_id: str):
    rows = _fetch(series_id, limit=8)
    if not rows:
        return None
    try:
        return float(rows[-1][1])
    except Exception:
        return None


def _yoy(series_id: str, per_year: int):
    """
    前年比の変化率(%)を返す。per_year は年あたりのデータ本数
    （週次=52・月次=12）。流動性は水準でなく増減が効くため。
    """
    rows = _fetch(series_id, limit=per_year + 8)
    if len(rows) < per_year + 1:
        return None
    try:
        now = float(rows[-1][1])
        ago = float(rows[-1 - per_year][1])
        return round((now - ago) / ago * 100, 2) if ago else None
    except Exception:
        return None


def _buffett_index():
    """米国株時価総額(Wilshire5000) ÷ 名目GDP × 100。GDPは四半期なので最新値を使う。"""
    try:
        mcap = _fetch("WILL5000PRFC", limit=8)     # 10億ドル単位
        gdp = _fetch("GDP", limit=4)               # 10億ドル・年率
        if not mcap or not gdp:
            return None
        m, g = float(mcap[-1][1]), float(gdp[-1][1])
        return round(m / g * 100, 1) if g else None
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


def _eps_trend(nd: dict):
    """
    日経のEPS（1株利益）が伸びているか縮んでいるか。
    株価上昇に利益が伴っているかの裏取りに使う（利益減＋株高＝危うい上昇）。
    """
    series = (nd or {}).get("series") or {}
    closes, pers = series.get("close") or [], series.get("per") or []
    eps = [c / p for c, p in zip(closes, pers) if c and p]
    if len(eps) < 60:
        return None
    now, ago = eps[-1], eps[-60:][0]
    if not ago:
        return None
    chg = (now - ago) / ago * 100
    px_chg = None
    if closes and closes[-60] and closes[-1]:
        px_chg = (closes[-1] - closes[-60]) / closes[-60] * 100
    if chg >= 3:
        state, emoji = "増益トレンド", "🟢"
        meaning = f"企業の利益が3か月で{chg:+.1f}%増えている。株価上昇に中身が伴う状態。"
        tip = "業績相場。上昇が続きやすい地合い。"
    elif chg <= -3:
        state, emoji = "減益トレンド", "🔴"
        meaning = f"企業の利益が3か月で{chg:+.1f}%減っている。"
        tip = "株価が上がっていても中身が伴わない。割高化に注意。"
        if px_chg is not None and px_chg > 0:
            meaning += f" その間に株価は{px_chg:+.1f}%。利益が減る中での上昇は危うい。"
    else:
        state, emoji = "横ばい", "🟡"
        meaning = f"企業の利益はほぼ横ばい（3か月で{chg:+.1f}%）。"
        tip = "業績以外の材料（金利・需給）で動きやすい局面。"
    return {"value": round(now, 1), "chg_pct": round(chg, 1),
            "state": state, "emoji": emoji, "meaning": meaning, "tip": tip}


# 前回からの変化がこれを超えたら「急変」として、ゾーンが同じでも通知する。
# 単位は指標により % か pt（絶対差）。信用スプレッドの急拡大は最も早い警報になる。
_SPIKE_ABS = {
    "hy_spread":   0.4,    # +0.4%の急拡大＝信用不安が一気に高まった
    "yield_curve": 0.25,   # 長短金利差が1日で0.25%動くのは大きい
    "sahm":        0.15,   # 雇用の悪化速度が跳ねた
    "real_rate":   0.2,    # 実質金利の急変は株の評価を直撃する
}
_SPIKE_PCT_KEYS = {"buffett": 5.0, "cb_assets": 3.0, "m2": 2.0}


def _spike_event(key: str, val, prev_val):
    """ゾーン内でも大きく動いた場合のイベントを作る。"""
    if val is None or prev_val is None:
        return None
    z = _ZONES.get(key)
    if not z:
        return None
    diff = val - prev_val
    if key in _SPIKE_ABS:
        if abs(diff) < _SPIKE_ABS[key]:
            return None
        move = f"{diff:+.2f}{z['unit']}"
    elif key in _SPIKE_PCT_KEYS:
        if not prev_val:
            return None
        pct = diff / abs(prev_val) * 100
        if abs(pct) < _SPIKE_PCT_KEYS[key]:
            return None
        move = f"{pct:+.1f}%"
    else:
        return None

    worse_up = key in ("hy_spread", "real_rate", "buffett")   # 上昇が悪材料の指標
    bad = (diff > 0) == worse_up
    if key == "yield_curve":
        bad = diff < 0        # 金利差の縮小＝景気減速方向
    if key in ("cb_assets", "m2"):
        bad = diff < 0        # 流動性の減少＝株に逆風

    return {
        "key": key, "label": z["label"], "what": z["what"], "unit": z["unit"],
        "value": val, "prev_value": prev_val,
        "zone": f"急変 {move}", "prev_zone": "同ゾーン内",
        "emoji": "⚡🔴" if bad else "⚡🟢", "spike": True,
        "meaning": (f"ゾーンは変わらないものの、前回から {move} と急に動きました。"
                    + ("悪化方向への急変で、変化が続くと警戒ゾーンに入ります。" if bad
                       else "改善方向への急変です。")),
        "tip": ("ゾーンを跨ぐ前の“予兆”です。この方向が続くか次回の値で確認したい。"),
        "worse": bad,
    }


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


def run(nikkei_internals: dict = None) -> dict:
    # FREDへの問い合わせは6系列あるため並列で取る（朝の実行時間を伸ばさないため）。
    # 取得できなかった系列は None のまま＝その指標だけ黙って除外される。
    values = {}
    try:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=6) as ex:
            futs = {k: ex.submit(_latest, sid) for k, sid in _FRED.items()}
            futs["buffett"] = ex.submit(_buffett_index)
            # 流動性は前年比（週次52本 / 月次12本さかのぼる）
            futs["cb_assets"] = ex.submit(_yoy, _FRED_FLOW["cb_assets"], 52)
            futs["m2"] = ex.submit(_yoy, _FRED_FLOW["m2"], 12)
            for k, f in futs.items():
                try:
                    values[k] = f.result(timeout=40)
                except Exception:
                    values[k] = None
    except Exception:
        logger.debug(traceback.format_exc())
        return {"available": False, "events": [], "current": {}}

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
            continue          # 初回は記録のみ（比較対象がないため通知しない）
        if prev["zone"] == idx:
            # ゾーンが同じでも急激に動いた場合は知らせる。
            # 特に信用スプレッドの急拡大は、ゾーンを跨ぐ前が最も早い警報になる。
            spike = _spike_event(key, val, prev.get("value"))
            if spike:
                events.append(spike)
            continue
        events.append({
            "key": key, "label": _ZONES[key]["label"], "what": _ZONES[key]["what"],
            "unit": _ZONES[key]["unit"], "value": val, "prev_value": prev.get("value"),
            "zone": name, "prev_zone": prev.get("name"),
            "emoji": emoji, "meaning": meaning, "tip": tip,
            "worse": idx > prev["zone"] if key != "yield_curve" else idx < prev["zone"],
        })

    # EPSトレンドは「状態」が変わったときだけ通知（数値は常時レポートに出す）
    eps = _eps_trend(nikkei_internals)
    if eps:
        new_state["eps"] = {"zone": eps["state"], "value": eps["value"]}
        prev_eps = st.get("eps")
        if isinstance(prev_eps, dict) and prev_eps.get("zone") not in (None, eps["state"]):
            events.append({
                "key": "eps", "label": "日経平均のEPS（1株あたり利益）",
                "what": "企業が1株でいくら稼いだか。株価の土台になる数字",
                "unit": "円", "value": eps["value"], "prev_value": prev_eps.get("value"),
                "zone": eps["state"], "prev_zone": prev_eps.get("zone"),
                "emoji": eps["emoji"], "meaning": eps["meaning"], "tip": eps["tip"],
                "worse": eps["state"] == "減益トレンド",
            })

    _save_state(new_state)

    # 同じ話題を他モジュールが既に通知していれば重ねて出さない
    try:
        from src.notify_ledger import filter_new
        events = filter_new(events, source="macro")
    except Exception:
        logger.debug(traceback.format_exc())

    if not events:
        logger.info(f"マクロ: ゾーン変化なし（{len(new_state)}指標を監視）")
        return {"available": False, "events": [], "current": new_state, "eps": eps}

    now = get_jst_now().strftime("%m/%d")
    lines = [f"🌡 *景気・信用シグナルが変化* （{now}）", "━━━━━━━━━━━━━━━"]
    for e in events:
        pv = f"{e['prev_value']:.2f}" if e.get("prev_value") is not None else "—"
        lines += [
            f"{e['emoji']} *{e['label']}*",
            f"　{pv} → *{e['value']:.2f}{e['unit']}*　"
            f"「{e['prev_zone']}」→「*{e['zone']}*」",
            f"　📖 {e['what']}",
            f"　{e['meaning']}",
            f"　💡 {e['tip']}",
        ]
    lines += ["━━━━━━━━━━━━━━━",
              "景気や信用の「先行き」を示す指標です。節目を跨いだとき／急に動いたときだけ通知しています。"]

    logger.info(f"✅ マクロ節目通過: {len(events)}件")
    return {"available": True, "events": events, "current": new_state,
            "eps": eps, "telegram_block": "\n".join(lines)}


if __name__ == "__main__":
    for k, v in (("hy_spread", 8.2), ("yield_curve", -0.3), ("sahm", 0.6),
                 ("real_rate", 2.3), ("buffett", 195.0)):
        z = _zone_of(k, v)
        print(f"{k}={v} -> {z[1]} {z[2]}")
