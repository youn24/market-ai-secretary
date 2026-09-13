"""
今後のイベント予定（Step EV・毎日表示）

「これからあるイベントごとを必ず教えて」に応えるモジュール。
1. 確定計算イベント（ネット不要・絶対に正確）:
   - SQ: 毎月第2金曜（3/6/9/12月=メジャーSQ）
   - 米雇用統計: 原則第1金曜（日本時間 夏21:30/冬22:30）
   - FOMC結果発表: FRB公表済み2026年日程（日本時間は翌朝未明）
2. 週次カレンダー（月曜にGemini取得→data/weekly_calendar.jsonに永続化）から
   今日以降のイベントを毎日読み出して表示。

run() → {"available", "events":[{date,label,icon,days_to,importance}], "telegram_block"}
"""
import json
from datetime import date, timedelta
from pathlib import Path
from src.utils import setup_logger, get_jst_now
from src.cfd_sq import next_sq

logger = setup_logger("upcoming_events")

_CAL_FILE = Path(__file__).parent.parent / "data" / "weekly_calendar.json"

# FRB公表済みの2026年FOMC日程（結果発表日=2日目。日本時間は翌朝未明）
_FOMC_2026 = [
    date(2026, 1, 28), date(2026, 3, 18), date(2026, 4, 29), date(2026, 6, 17),
    date(2026, 7, 29), date(2026, 9, 16), date(2026, 10, 28), date(2026, 12, 9),
]

_WD = ["月", "火", "水", "木", "金", "土", "日"]


def _fmt(d: date) -> str:
    return f"{d.month}/{d.day}({_WD[d.weekday()]})"


def _first_friday(y: int, m: int) -> date:
    w = date(y, m, 1).weekday()
    return date(y, m, 1 + (4 - w) % 7)


def _builtin_events(today: date, horizon: int) -> list[dict]:
    """確定計算イベント（SQ・米雇用統計・FOMC）"""
    ev = []
    # SQ
    sq = next_sq(today)
    if sq and sq.get("days_to", 99) <= horizon:
        ev.append({"date": today + timedelta(days=sq["days_to"]), "icon": "🇯🇵",
                   "label": sq["type"] + ("〈本日〉" if sq["is_today"] else ""),
                   "importance": "high" if sq["is_major"] else "medium"})
    # 米雇用統計（原則第1金曜）
    for off in (0, 1):
        y = today.year + (today.month - 1 + off) // 12
        m = (today.month - 1 + off) % 12 + 1
        d = _first_friday(y, m)
        if 0 <= (d - today).days <= horizon:
            ev.append({"date": d, "icon": "🇺🇸", "label": "米雇用統計（夜・原則第1金曜）",
                       "importance": "high"})
            break
    # FOMC（超大型イベントは30日先まで常時表示）
    for d in _FOMC_2026:
        if 0 <= (d - today).days <= max(horizon, 30):
            ev.append({"date": d, "icon": "🏛", "label": "FOMC結果発表（日本時間は翌朝未明）",
                       "importance": "high"})
            break
    return ev


def _calendar_events(today: date, horizon: int) -> list[dict]:
    """月曜保存の週次カレンダーから今日以降のイベントを読む。"""
    try:
        data = json.loads(_CAL_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []
    out = []
    for e in data.get("events", []):
        try:
            d = date.fromisoformat(str(e.get("date", ""))[:10])
        except Exception:
            continue
        if 0 <= (d - today).days <= horizon:
            flag = {"JP": "🇯🇵", "US": "🇺🇸", "EU": "🇪🇺", "UK": "🇬🇧",
                    "CN": "🇨🇳", "CA": "🇨🇦", "AU": "🇦🇺"}.get(e.get("country", ""), "🌐")
            t = e.get("time", "-")
            label = e.get("event", "")
            if t and t != "-":
                label += f"（{t}）"
            out.append({"date": d, "icon": flag, "label": label,
                        "importance": e.get("importance", "medium")})
    return out


def run(horizon: int = 10, max_events: int = 8) -> dict:
    today = get_jst_now().date()
    events = _builtin_events(today, horizon) + _calendar_events(today, horizon)

    # 重複除去（同日・類似ラベル）＋ high優先・日付順
    seen, uniq = set(), []
    for e in sorted(events, key=lambda x: (x["date"], x["importance"] != "high")):
        key = (e["date"], e["label"][:8])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(e)
    highs = [e for e in uniq if e["importance"] == "high"]
    rest  = [e for e in uniq if e["importance"] != "high"]
    picked = sorted((highs + rest)[:max_events], key=lambda x: x["date"])

    if not picked:
        return {"available": False, "events": []}

    lines = ["📅 *今後の注目イベント*"]
    for e in picked:
        days = (e["date"] - today).days
        when = "★今日" if days == 0 else "明日" if days == 1 else f"あと{days}日"
        imp  = "🔴" if e["importance"] == "high" else "・"
        lines.append(f"{imp} {_fmt(e['date'])} {e['icon']} {e['label']}〔{when}〕")

    for e in picked:
        e["date"] = e["date"].isoformat()
        e["days_to"] = (date.fromisoformat(e["date"]) - today).days

    result = {"available": True, "events": picked,
              "telegram_block": "\n".join(lines)}
    logger.info(f"✅ 今後のイベント: {len(picked)}件（{horizon}日先まで）")
    return result


if __name__ == "__main__":
    r = run()
    for e in r.get("events", []):
        print(e["date"], e["label"], e["days_to"])
