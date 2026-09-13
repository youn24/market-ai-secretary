"""
中央銀行の政策金利ウォッチ（Step PW）

FRB（米）と日銀の政策金利について「今いくらか」だけでなく
「前回いつ・どちら向きに・何%動かしたか」「そこから何日据え置いているか」を示す。

金利は株価を動かす最大の要因のひとつだが、水準そのものより
“方向が変わった瞬間”（利上げ局面→利下げ局面への転換）が相場の転換点になる。
そのため、変更があった日と、その意味を必ず添えて伝える。

run() → {"available", "fed": {...}, "boj": {...}, "events": [...], "telegram_block"}
"""
import json
import traceback
from datetime import datetime
from src.utils import setup_logger, get_jst_now, BASE_DIR

logger = setup_logger("policy_watch")

_STATE_FILE = BASE_DIR / "data" / "policy_state.json"

# FRED系列（APIキー不要）
_FED_SERIES = "DFEDTARU"      # FF金利の誘導目標レンジ上限（日次）
_BOJ_SERIES = "IRSTCB01JPM156N"  # 日本の中央銀行政策金利（月次）


def _fetch(series_id: str, limit: int = 1500):
    try:
        from src.fred_data import _fetch_series
        return _fetch_series(series_id, limit=limit)
    except Exception:
        logger.debug(traceback.format_exc())
        return []


def _analyze(series_id: str, name: str, limit: int = 1500) -> dict | None:
    """
    金利系列から「現在値・前回変更日・変更幅・据え置き日数」を割り出す。
    """
    rows = _fetch(series_id, limit=limit)
    if len(rows) < 2:
        return None
    try:
        pts = [(r[0], float(r[1])) for r in rows if r[1] not in ("", ".")]
    except Exception:
        return None
    if len(pts) < 2:
        return None

    cur_date, cur = pts[-1]
    # 直近で値が変わった地点をさかのぼって探す
    prev_val, change_date = None, None
    for d, v in reversed(pts[:-1]):
        if abs(v - cur) > 1e-9:
            prev_val, change_date = v, d
            break
    if prev_val is None:
        return {"name": name, "rate": cur, "direction": "据え置き",
                "change": None, "changed_on": None, "days_since": None,
                "note": "この期間内に変更なし"}

    # change_date は「変わる前の最後の日」なので、その翌営業日が変更日
    idx = [i for i, (d, _) in enumerate(pts) if d == change_date]
    changed_on = pts[idx[0] + 1][0] if idx and idx[0] + 1 < len(pts) else change_date

    diff = round(cur - prev_val, 2)
    if diff > 0:
        direction, emoji = "利上げ", "🔺"
    elif diff < 0:
        direction, emoji = "利下げ", "🔻"
    else:
        direction, emoji = "据え置き", "➡️"

    try:
        days = (datetime.strptime(get_jst_now().strftime("%Y-%m-%d"), "%Y-%m-%d")
                - datetime.strptime(changed_on, "%Y-%m-%d")).days
    except Exception:
        days = None

    return {"name": name, "rate": cur, "prev_rate": prev_val,
            "change": diff, "direction": direction, "emoji": emoji,
            "changed_on": changed_on, "days_since": days}


def _phase_note(info: dict) -> tuple:
    """局面（利上げ/利下げ）の意味と、投資家目線での見方を返す。"""
    if not info or info.get("change") is None:
        return ("金利の変更は確認できていません。",
                "政策の方向が変わるまでは、金利以外の材料で相場が動きやすい。")
    d, chg, days = info["direction"], info["change"], info.get("days_since")
    stay = f"（それから{days}日間据え置き）" if days else ""
    if d == "利上げ":
        return (f"前回の変更は *利上げ* {chg:+.2f}%{stay}。",
                "金利上昇は企業の借入コスト増＝株には逆風。特に高PERのハイテク株が売られやすい。")
    if d == "利下げ":
        return (f"前回の変更は *利下げ* {chg:+.2f}%{stay}。",
                "金利低下は株に追い風。ただし「景気が悪いから下げる」場合は株安と重なることもある。")
    return ("金利は据え置きが続いています。",
            "方向が変わるまでは様子見。次の会合の発言に注目。")


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


def run() -> dict:
    try:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as ex:
            f_fed = ex.submit(_analyze, _FED_SERIES, "FRB（米国）", 1500)
            f_boj = ex.submit(_analyze, _BOJ_SERIES, "日銀（日本）", 120)
            fed = f_fed.result(timeout=40)
            boj = f_boj.result(timeout=40)
    except Exception:
        logger.debug(traceback.format_exc())
        fed = boj = None

    if not fed and not boj:
        return {"available": False, "events": []}

    st = _load_state()
    events = []
    new_state = {}
    for key, info in (("fed", fed), ("boj", boj)):
        if not info:
            continue
        new_state[key] = {"rate": info["rate"], "changed_on": info.get("changed_on")}
        prev = st.get(key)
        # 金利が動いた「その日」だけをイベントとして扱う
        if isinstance(prev, dict) and prev.get("rate") is not None \
                and abs(prev["rate"] - info["rate"]) > 1e-9:
            events.append({**info, "key": key})
    _save_state(new_state)

    lines = ["🏛 *中央銀行の政策金利*", "━━━━━━━━━━━━━━━"]
    for info in (fed, boj):
        if not info:
            continue
        what, tip = _phase_note(info)
        chg_s = ""
        if info.get("changed_on"):
            chg_s = f"　{info['emoji']} {info['changed_on']} に {info['prev_rate']:.2f}% → {info['rate']:.2f}%"
        lines += [f"*{info['name']}*　現在 *{info['rate']:.2f}%*", chg_s,
                  f"　{what}", f"　💡 {tip}"]
    lines = [l for l in lines if l]
    lines.append("━━━━━━━━━━━━━━━")

    result = {"available": True, "fed": fed, "boj": boj, "events": events,
              "telegram_block": "\n".join(lines)}
    if events:
        logger.info(f"🚨 政策金利に変更: {[e['name'] for e in events]}")
    else:
        logger.info(f"政策金利: 変更なし（FRB={fed and fed['rate']} 日銀={boj and boj['rate']}）")
    return result


if __name__ == "__main__":
    r = run()
    print(r.get("telegram_block", "取得できず"))
