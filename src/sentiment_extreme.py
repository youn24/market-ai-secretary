"""
市場心理の極値と「反転」の検知（Step SE）

恐怖指数（VIX）とFear&Greed Indexは、平常時の細かい上下に意味は薄い。
価値があるのは次の2つの瞬間だけ:

  1. 極値に到達した … 「他人が恐怖している時に買え」の水準に来た
  2. 極値から戻り始めた … 恐怖のピークが過ぎた＝市場が実際に反応した

特に重要なのは 2 の「反転」。極端な恐怖に入っただけでは、そこからさらに
下がることもある。しかし極値から戻り始めた時は、売り方の力が尽きた
サインとして機能しやすく、歴史的な底・天井はこの形で作られてきた。

そのため本モジュールは「今どのゾーンか」に加えて
「極値に何日いたか」「そこから抜けたか」を状態として持ち、
抜けた瞬間＝反転を最重要シグナルとして通知する。

run(prices, fear_greed) → {"available", "events":[...], "current":{...}, "telegram_block"}
"""
import json
import traceback
from src.utils import setup_logger, get_jst_now, BASE_DIR

logger = setup_logger("sentiment_extreme")

_STATE_FILE = BASE_DIR / "data" / "sentiment_state.json"

# Fear&Greed Index のゾーン（0-100）
# 数値が小さいほど恐怖＝逆張りの買い場になりやすい
_FG_ZONES = [
    (25, "極端な恐怖", "😱", 0),
    (45, "恐怖", "😰", 1),
    (55, "中立", "😐", 2),
    (75, "強欲", "😤", 3),
    (101, "極端な強欲", "🤑", 4),
]
_FG_EXTREME_LOW = 0     # 極端な恐怖のゾーン番号
_FG_EXTREME_HIGH = 4    # 極端な強欲のゾーン番号

# VIX の水準
_VIX_ZONES = [
    (15, "平穏", "🟢", 0),
    (20, "標準", "🟡", 1),
    (30, "警戒", "🟠", 2),
    (40, "パニック", "🔴", 3),
    (999, "暴落級", "🆘", 4),
]
# VIX30超（パニック以上）を「極値」とみなす。20〜30の警戒は年に何度もあり、
# ここを極値にすると通知が増えすぎるため、30超に限定する。
_VIX_PANIC = 3

# VIXがこの割合で急騰したら、水準に関係なく知らせる（%）
_VIX_SPIKE = 20.0


def _zone(value, table):
    if value is None:
        return None
    for upper, name, emoji, idx in table:
        if value < upper:
            return {"idx": idx, "name": name, "emoji": emoji}
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


def run(prices: dict = None, fear_greed: dict = None) -> dict:
    prices = prices or {}
    fg_val = (fear_greed or {}).get("score")
    vix = (prices.get("^VIX") or {}).get("latest")
    vix_chg = (prices.get("^VIX") or {}).get("change_pct")
    n225_chg = (prices.get("^N225") or {}).get("change_pct")
    spx_chg = (prices.get("^GSPC") or {}).get("change_pct")

    fg_z = _zone(fg_val, _FG_ZONES)
    vix_z = _zone(vix, _VIX_ZONES)

    st = _load_state()
    events = []
    new_state = {}

    # ── Fear & Greed ─────────────────────────────────────────
    if fg_z:
        prev = st.get("fg") or {}
        streak = int(prev.get("streak", 0))
        in_extreme = fg_z["idx"] in (_FG_EXTREME_LOW, _FG_EXTREME_HIGH)
        was_extreme = prev.get("idx") in (_FG_EXTREME_LOW, _FG_EXTREME_HIGH)
        streak = streak + 1 if (in_extreme and prev.get("idx") == fg_z["idx"]) else (1 if in_extreme else 0)
        new_state["fg"] = {"idx": fg_z["idx"], "name": fg_z["name"],
                           "value": fg_val, "streak": streak}

        if prev.get("idx") is not None and prev["idx"] != fg_z["idx"]:
            # ① 極値から抜けた＝反転（最重要）
            if was_extreme and not in_extreme:
                bottom = prev["idx"] == _FG_EXTREME_LOW
                days = prev.get("streak", 1)
                events.append({
                    "key": "fg_reversal", "priority": 0,
                    "emoji": "🔄🟢" if bottom else "🔄🔴",
                    "title": ("恐怖のピークアウト（底打ちの兆候）" if bottom
                              else "過熱の解消（天井警戒）"),
                    "detail": (f"Fear&Greedが{prev.get('value')}→{fg_val}。"
                               f"「{prev['name']}」ゾーンに{days}日いた後、"
                               f"「{fg_z['name']}」へ戻りました。"),
                    "meaning": ("投資家の恐怖が和らぎ始めた瞬間。売りの力が尽きたサインとして"
                                "働きやすく、歴史的な底はこの形で作られてきました。" if bottom else
                                "行き過ぎた楽観が冷え始めた瞬間。高値圏での過熱解消は"
                                "調整の入り口になることがあります。"),
                    "tip": ("一気に全額を投じるのではなく、数回に分けて拾うのが定石。"
                            "反転が続くかを数日確認したい。" if bottom else
                            "利益確定を検討する場面。追いかけ買いは避けたい。"),
                })
            # ② 極値に入った
            elif in_extreme:
                low = fg_z["idx"] == _FG_EXTREME_LOW
                events.append({
                    "key": "fg_extreme", "priority": 1,
                    "emoji": fg_z["emoji"],
                    "title": ("市場が『極端な恐怖』に到達" if low
                              else "市場が『極端な強欲』に到達"),
                    "detail": f"Fear&Greedが{prev.get('value')}→{fg_val}（{fg_z['name']}）。",
                    "meaning": ("投資家心理が極度に冷え込んだ状態。過去はこの水準から"
                                "反発することが多い一方、さらに下がることもあります。" if low else
                                "投資家が強気に傾きすぎた状態。過去はこの水準から"
                                "調整が入ることが多くなっています。"),
                    "tip": ("まだ底とは限らない。反転（このゾーンから戻る動き）を"
                            "確認してからでも遅くない。" if low else
                            "新規の追随買いは慎重に。持ち高の点検を。"),
                })

    # ── VIX ──────────────────────────────────────────────────
    if vix_z:
        prev = st.get("vix") or {}
        streak = int(prev.get("streak", 0))
        in_ext = vix_z["idx"] >= _VIX_PANIC
        was_ext = (prev.get("idx") or 0) >= _VIX_PANIC
        streak = streak + 1 if (in_ext and was_ext) else (1 if in_ext else 0)
        new_state["vix"] = {"idx": vix_z["idx"], "name": vix_z["name"],
                            "value": vix, "streak": streak}

        if prev.get("idx") is not None and prev["idx"] != vix_z["idx"]:
            if was_ext and not in_ext:
                # 恐怖のピークアウト＝リスクオン再開のサイン
                events.append({
                    "key": "vix_calm", "priority": 0, "emoji": "🕊",
                    "title": "VIXが警戒水準から低下（市場が落ち着きを取り戻す）",
                    "detail": (f"VIXが{prev.get('value')}→{vix:.1f}。"
                               f"「{prev['name']}」から「{vix_z['name']}」へ。"),
                    "meaning": "恐怖のピークが過ぎたサイン。VIXの低下局面では株価が戻りやすい傾向があります。",
                    "tip": "急落後の反発局面になりやすい。ただし戻りが一時的なこともあるため段階的に。",
                })
            elif in_ext:
                events.append({
                    "key": "vix_panic", "priority": 1, "emoji": vix_z["emoji"],
                    "title": f"VIXが{vix_z['name']}水準に上昇",
                    "detail": f"VIXが{prev.get('value')}→{vix:.1f}（{vix_z['name']}）。",
                    "meaning": "投資家の不安が高まり、株価が大きく振れやすい状態です。",
                    "tip": "無理な取引は避け、下げ止まりを確認したい局面。",
                })

    # ── VIXの急騰（水準に関係なく即座に知らせる）──
    if vix_chg is not None and vix_chg >= _VIX_SPIKE and vix:
        events.append({
            "key": "vix_spike", "priority": 0, "emoji": "⚡",
            "title": f"VIXが急騰（前日比 {vix_chg:+.1f}%）",
            "detail": f"VIXが{vix:.1f}へ急上昇。",
            "meaning": "何らかの悪材料に市場が急反応した可能性。株価は下落しやすい局面です。",
            "tip": "急変時は値動きが荒くなります。落ち着くまで様子を見るのが安全。",
        })

    # ── 極値の最中に相場が実際に反応したか（＝底や天井で市場が動いた瞬間）──
    fg_now = new_state.get("fg") or {}
    if fg_now.get("idx") == _FG_EXTREME_LOW and fg_now.get("streak", 0) >= 2:
        move = n225_chg if n225_chg is not None else spx_chg
        if move is not None and move >= 1.5:
            events.append({
                "key": "bottom_bounce", "priority": 0, "emoji": "🚀",
                "title": "極端な恐怖の中での大幅反発",
                "detail": (f"Fear&Greedが{fg_val}（極端な恐怖）と冷え切る中、"
                           f"株価が{move:+.2f}%と大きく反発しました。"),
                "meaning": "悲観が極まった状態での反発は、売り一巡＝底打ちの初動になることがあります。",
                "tip": "反発が続くか数日確認したい。戻り売りに押される場合は深追いしない。",
            })
    if fg_now.get("idx") == _FG_EXTREME_HIGH and fg_now.get("streak", 0) >= 2:
        move = n225_chg if n225_chg is not None else spx_chg
        if move is not None and move <= -1.5:
            events.append({
                "key": "top_reversal", "priority": 0, "emoji": "⚠️",
                "title": "極端な強欲の中での大幅下落",
                "detail": (f"Fear&Greedが{fg_val}（極端な強欲）と過熱する中、"
                           f"株価が{move:+.2f}%と大きく下落しました。"),
                "meaning": "楽観が極まった状態での急落は、天井形成の初動になることがあります。",
                "tip": "利益確定を検討する場面。下げが続くようなら深追いは避けたい。",
            })

    _save_state(new_state)

    if not events:
        logger.info(f"市場心理: 極値・反転なし（F&G={fg_val} VIX={vix}）")
        return {"available": False, "events": [], "current": new_state}

    events.sort(key=lambda e: e.get("priority", 9))
    now = get_jst_now().strftime("%m/%d")
    lines = [f"🎭 *市場心理が節目に到達* （{now}）", "━━━━━━━━━━━━━━━"]
    for e in events[:3]:
        lines += [f"{e['emoji']} *{e['title']}*", f"　{e['detail']}",
                  f"　{e['meaning']}", f"　💡 {e['tip']}"]
    lines += ["━━━━━━━━━━━━━━━",
              "恐怖・強欲が極端に振れた時と、そこから戻り始めた時だけ通知しています。"]

    logger.info(f"✅ 市場心理シグナル: {len(events)}件 ({[e['key'] for e in events]})")
    return {"available": True, "events": events, "current": new_state,
            "telegram_block": "\n".join(lines)}


if __name__ == "__main__":
    print(_zone(18, _FG_ZONES), _zone(85, _FG_ZONES), _zone(35, _VIX_ZONES))
