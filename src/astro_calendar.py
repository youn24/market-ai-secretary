"""
天体イベントカレンダー（投資アノマリー用）
新月・満月・水星逆行を計算し、経済カレンダーに重ねて表示する。

投資界のアノマリー（経験則）：
  - 満月・新月：相場の転換点になりやすいという経験則（科学的根拠は薄いが意識される）
  - 水星逆行：通信・契約・取引のトラブルが起きやすいとされ、慎重になる投資家がいる

新月・満月は朔望月（約29.53日）から計算（±数時間精度・アノマリー用途には十分）。
水星逆行は天文計算が複雑なため、公開データの概算期間テーブルを使用。
外部ライブラリ不要・APIキー不要。
"""
from datetime import datetime, timedelta, timezone

from src.utils import setup_logger

logger = setup_logger("astro_calendar")

JST = timezone(timedelta(hours=9))

# 満月の通称（ネイティブアメリカン由来・日本でも話題になる）
_FULL_MOON_NAMES = {
    1:  "ウルフムーン",       2:  "スノームーン",
    3:  "ワームムーン",       4:  "ピンクムーン",
    5:  "フラワームーン",     6:  "ストロベリームーン",
    7:  "バックムーン",       8:  "スタージョンムーン",
    9:  "ハーベストムーン",   10: "ハンターズムーン",
    11: "ビーバームーン",     12: "コールドムーン",
}

# 水星逆行の概算期間（UTC基準・目安）。天文暦に基づく一般的な公開値。
# 日付は年により数日ずれることがあるため「目安」として扱う。
_MERCURY_RETROGRADE = [
    ("2025-03-15", "2025-04-07"),
    ("2025-07-18", "2025-08-11"),
    ("2025-11-09", "2025-11-29"),
    ("2026-02-25", "2026-03-20"),
    ("2026-06-29", "2026-07-23"),
    ("2026-10-24", "2026-11-13"),
    ("2027-02-09", "2027-03-03"),
    ("2027-06-10", "2027-07-04"),
    ("2027-10-07", "2027-10-28"),
]

_SYNODIC = 29.530588853  # 朔望月（新月→新月の平均日数）


def _to_jd(dt: datetime) -> float:
    """datetime(UTC) → ユリウス通日"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    ts = dt.timestamp()
    return 2440587.5 + ts / 86400.0


def _from_jd(jd: float) -> datetime:
    """ユリウス通日 → datetime(UTC)"""
    ts = (jd - 2440587.5) * 86400.0
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def _moon_events(start: datetime, end: datetime) -> list[dict]:
    """期間内の新月・満月を計算して返す"""
    # 基準新月：2000-01-06 18:14 UTC ≒ JD 2451550.26
    base_jd = 2451550.26
    start_jd = _to_jd(start)
    end_jd   = _to_jd(end)

    events = []
    # 開始日より前の最も近い新月インデックスから探索
    k = int((start_jd - base_jd) / _SYNODIC) - 1
    while True:
        new_jd  = base_jd + k * _SYNODIC
        full_jd = new_jd + _SYNODIC / 2  # 満月は新月のほぼ中間
        if new_jd > end_jd + _SYNODIC:
            break
        for jd, kind in ((new_jd, "new"), (full_jd, "full")):
            if start_jd <= jd <= end_jd:
                dt_jst = _from_jd(jd).astimezone(JST)
                if kind == "new":
                    events.append({
                        "dt": dt_jst, "emoji": "🌑", "kind": "新月",
                        "label": "新月", "importance": "low",
                    })
                else:
                    name = _FULL_MOON_NAMES.get(dt_jst.month, "")
                    events.append({
                        "dt": dt_jst, "emoji": "🌕", "kind": "満月",
                        "label": f"満月（{name}）" if name else "満月",
                        "importance": "low",
                    })
        k += 1
    return events


def _mercury_events(start: datetime, end: datetime) -> list[dict]:
    """期間内に開始/終了/継続する水星逆行を返す"""
    events = []
    s = start.date()
    e = end.date()
    for begin_s, end_s in _MERCURY_RETROGRADE:
        b = datetime.strptime(begin_s, "%Y-%m-%d").date()
        f = datetime.strptime(end_s, "%Y-%m-%d").date()
        # 逆行開始がこの期間に入る
        if s <= b <= e:
            events.append({
                "dt": datetime(b.year, b.month, b.day, tzinfo=JST),
                "emoji": "☿", "kind": "水星逆行入り",
                "label": "水星逆行入り（取引ミス注意の経験則）",
                "importance": "medium",
            })
        # 逆行終了（順行へ）がこの期間に入る
        if s <= f <= e:
            events.append({
                "dt": datetime(f.year, f.month, f.day, tzinfo=JST),
                "emoji": "☿", "kind": "水星順行戻り",
                "label": "水星逆行明け（順行に戻る）",
                "importance": "low",
            })
    return events


def is_mercury_retrograde(dt: datetime = None) -> tuple[bool, str]:
    """指定日（未指定なら今日）が水星逆行中か。 (True/False, 期間文字列)"""
    d = (dt or datetime.now(JST)).date()
    for begin_s, end_s in _MERCURY_RETROGRADE:
        b = datetime.strptime(begin_s, "%Y-%m-%d").date()
        f = datetime.strptime(end_s, "%Y-%m-%d").date()
        if b <= d <= f:
            return True, f"{begin_s} 〜 {end_s}"
    return False, ""


def get_astro_events(start: datetime, end: datetime) -> list[dict]:
    """
    指定期間の天体イベントを economic_calendar 形式で返す。
    返り値: [{date, time, country, category, importance, event}, ...]
    """
    raw = _moon_events(start, end) + _mercury_events(start, end)
    raw.sort(key=lambda x: x["dt"])

    out = []
    for ev in raw:
        out.append({
            "date":       ev["dt"].strftime("%Y-%m-%d"),
            "time":       ev["dt"].strftime("%H:%M"),
            "country":    "world",
            "category":   "天体",
            "importance": ev["importance"],
            "event":      f'{ev["emoji"]} {ev["label"]}',
        })
    return out


def get_upcoming_summary(days: int = 30) -> dict:
    """今後N日間の天体イベント要約（HTML/Telegram用）"""
    now = datetime.now(JST)
    events = get_astro_events(now, now + timedelta(days=days))
    retro_now, retro_period = is_mercury_retrograde(now)
    return {
        "available":     len(events) > 0,
        "events":        events,
        "mercury_now":   retro_now,
        "mercury_period": retro_period,
    }


if __name__ == "__main__":
    now = datetime.now(JST)
    evs = get_astro_events(now, now + timedelta(days=45))
    retro, period = is_mercury_retrograde(now)
    lines = [f"=== 今後45日の天体イベント（{len(evs)}件）==="]
    lines.append(f"水星逆行中: {'はい（'+period+'）' if retro else 'いいえ'}\n")
    for e in evs:
        lines.append(f"{e['date']} {e['time']}  {e['event']}")
    text = "\n".join(lines)
    try:
        print(text)
    except UnicodeEncodeError:
        with open("astro_output.txt", "w", encoding="utf-8") as f:
            f.write(text)
        print("astro_output.txt に保存しました")
