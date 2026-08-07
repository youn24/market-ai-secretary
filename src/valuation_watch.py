"""
バリュエーション節目ウォッチ（Step VW）

PER・PBR・配当利回り・益回り（対金利スプレッド）が、投資判断の分かれ目となる
「歴史的な節目」を跨いだときだけ知らせる。日々の小さな上下は無視する。

なぜ節目だけか:
  PERが14.2→14.3のような動きは判断を変えない。一方「PBR 1.0倍割れ」は
  “日経平均が解散価値を下回った”という別次元の話で、過去の大底圏でしか
  起きていない。動いた量ではなく「どのゾーンに入ったか」が意味を持つ。

判定は前日のゾーンと比較し、ゾーンが変わった瞬間だけ発火。
同じゾーンに留まる限り二度と鳴らない（data/valuation_state.json で管理）。

run(nikkei_internals) → {"available", "events":[...], "telegram_block"}
"""
import json
import traceback
from src.utils import setup_logger, get_jst_now, BASE_DIR

logger = setup_logger("valuation_watch")

_STATE_FILE = BASE_DIR / "data" / "valuation_state.json"

# 指標ごとの「ゾーン」定義。(上限, ゾーン名, 絵文字, 意味, 行動のヒント)
# 上限は「この値未満ならこのゾーン」。最後の要素は上限なし。
_ZONES = {
    "per": {
        "label": "日経平均PER（株価が利益の何倍か）",
        "unit": "倍",
        "bands": [
            (11.0, "歴史的割安", "🟢🟢", "利益に対して株価が非常に安い水準。過去の大底圏と同じゾーン。",
             "長期の買い場になりやすい局面。ただし業績悪化が理由のこともあるので確認を。"),
            (13.0, "割安", "🟢", "標準レンジ（13〜16倍）を下回る。買い手に分がある水準。",
             "押し目買いを検討しやすいゾーン。"),
            (16.0, "標準", "🟡", "日経平均の平常レンジ内。割高でも割安でもない。",
             "バリュエーションは判断材料にならない。テクニカルや業績で判断を。"),
            (18.0, "やや割高", "🟠", "標準レンジを上抜け。利益の伸びが追いつくか要確認。",
             "高値づかみに注意。新規買いは慎重に。"),
            (None, "割高", "🔴", "利益に対し株価が高い水準。調整が入りやすいゾーン。",
             "利益確定を検討する場面。押し目を待つ判断も。"),
        ],
    },
    "pbr": {
        "label": "日経平均PBR（株価が純資産の何倍か）",
        "unit": "倍",
        "bands": [
            (1.0, "解散価値割れ", "🟢🟢", "会社を今すぐ畳んで資産を配った方が高いという異常な安さ。",
             "歴史的にはリーマン級の暴落時にしか起きない水準。長期の仕込み場。"),
            (1.2, "割安", "🟢", "純資産に対して株価が安い。東証が是正を求めてきた水準。",
             "自社株買い・増配などの株主還元が出やすいゾーン。"),
            (1.5, "標準", "🟡", "近年の日経平均の平常レンジ。",
             "PBR単独では判断できない。ROEや成長性と合わせて。"),
            (None, "高評価", "🔴", "純資産の1.5倍超。成長期待が株価に織り込まれた状態。",
             "期待が剥落すると下げも速い。業績の裏付けを確認。"),
        ],
    },
    "dividend_yield": {
        "label": "日経平均の配当利回り",
        "unit": "%",
        # 日経平均の実績: 平常1.7〜2.2%、コロナ暴落(2020/3)で2.7%台まで上昇
        "bands": [
            (1.6, "低い", "🔴", "配当の魅力が乏しい水準。株価が高いことの裏返し。",
             "インカム狙いには不向きなゾーン。"),
            (2.2, "標準", "🟡", "日経平均の平常的な配当利回り（1.7〜2.2%）。",
             "特段の妙味も割高感もない。"),
            (2.8, "妙味あり", "🟢", "配当の魅力が増す水準。株価下落で利回りが上昇している。",
             "長期保有でインカムを狙いやすいゾーン。"),
            (None, "高利回り", "🟢🟢", "歴史的に高い配当利回り。暴落局面でしか出ない水準。",
             "減配リスクの確認は必要だが、長期の買い場になりやすい。"),
        ],
    },
    "spread": {
        "label": "イールドスプレッド（株の利回り−国債金利）",
        "unit": "%",
        "bands": [
            (1.0, "株が割高", "🔴", "国債と比べた株式の魅力が乏しい。資金が債券に向かいやすい。",
             "株から債券へ資金が流れやすい局面。"),
            (3.0, "標準", "🟡", "株と債券のバランスが取れた状態。",
             "どちらかに大きく傾いてはいない。"),
            (5.0, "株が割安", "🟢", "国債より株式の期待利回りが大きく上回る。",
             "株式に資金が向かいやすいゾーン。"),
            (None, "株が極めて割安", "🟢🟢", "債券に対して株の魅力が歴史的に高い水準。",
             "長期の株式投資に有利な環境。"),
        ],
    },
}


def _zone_of(key: str, value) -> tuple | None:
    """値がどのゾーンに属するかを返す。(index, name, emoji, meaning, tip)"""
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


def run(nikkei_internals: dict = None) -> dict:
    """
    日経のバリュエーション指標がゾーンを跨いだかを判定する。
    nikkei_internals は Step ND の結果（per/pbr/dividend_yield/spread を含む）。
    """
    nd = nikkei_internals or {}
    if not nd.get("available"):
        return {"available": False, "events": []}

    values = {
        "per": nd.get("per"),
        "pbr": nd.get("pbr"),
        "dividend_yield": nd.get("dividend_yield") or nd.get("yield"),
        "spread": nd.get("spread"),
    }

    st = _load_state()
    events, new_state = [], {}

    for key, val in values.items():
        z = _zone_of(key, val)
        if not z:
            continue
        idx, name, emoji, meaning, tip = z
        new_state[key] = {"zone": idx, "name": name, "value": val}
        prev = st.get(key)
        # 初回はゾーンを記録するだけ（過去との比較ができないため通知しない）
        if not isinstance(prev, dict) or "zone" not in prev:
            continue
        if prev["zone"] == idx:
            continue
        direction = "改善（割安方向）" if idx < prev["zone"] else "悪化（割高方向）"
        # PERとPBRは数値が小さいほど割安。配当利回り・スプレッドは逆。
        if key in ("dividend_yield", "spread"):
            direction = "上昇（妙味増）" if idx > prev["zone"] else "低下（妙味減）"
        events.append({
            "key": key,
            "label": _ZONES[key]["label"],
            "unit": _ZONES[key]["unit"],
            "value": val,
            "prev_value": prev.get("value"),
            "zone": name,
            "prev_zone": prev.get("name"),
            "emoji": emoji,
            "meaning": meaning,
            "tip": tip,
            "direction": direction,
        })

    _save_state(new_state)

    if not events:
        logger.info(f"バリュエーション: ゾーン変化なし（{len(new_state)}指標を監視）")
        return {"available": False, "events": [], "current": new_state}

    now = get_jst_now().strftime("%m/%d")
    lines = [f"📐 *バリュエーションが節目を通過* （{now}）", "━━━━━━━━━━━━━━━"]
    for e in events:
        pv = f"{e['prev_value']:.2f}" if e.get("prev_value") is not None else "—"
        lines.append(f"{e['emoji']} *{e['label']}*")
        lines.append(f"　{pv} → *{e['value']:.2f}{e['unit']}*　"
                     f"「{e['prev_zone']}」→「*{e['zone']}*」")
        lines.append(f"　{e['meaning']}")
        lines.append(f"　💡 {e['tip']}")
    lines += ["━━━━━━━━━━━━━━━",
              "日々の小さな上下は無視し、投資判断が変わる節目を跨いだときだけ通知しています。"]

    logger.info(f"✅ バリュエーション節目通過: {len(events)}件")
    return {"available": True, "events": events, "current": new_state,
            "telegram_block": "\n".join(lines)}


if __name__ == "__main__":
    # 自己テスト（ゾーン判定）
    for k, v in (("per", 10.5), ("per", 14.0), ("pbr", 0.95), ("pbr", 1.3),
                 ("dividend_yield", 2.7), ("spread", 5.5)):
        z = _zone_of(k, v)
        print(f"{k}={v} -> {z[1]} {z[2]}")
