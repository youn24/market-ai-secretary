"""
アノマリーカレンダー（相場の経験則）
その日・その週・その時期に該当する市場アノマリーを自動判定して表示する。

アノマリーは「過去こういう傾向があった」という経験則であり、
必ず当たるものではない。投資家心理として意識されるため参考情報として出す。
天体イベント（astro_calendar）も統合して「今日意識すべきこと」を一覧化する。

外部ライブラリ・APIキー不要（日付計算のみ）。
"""
import calendar as _cal
from datetime import datetime, timedelta, timezone

from src.utils import setup_logger, get_jst_now

logger = setup_logger("anomaly_calendar")

JST = timezone(timedelta(hours=9))

# sentiment 絵文字
SENT = {"bull": "📈", "bear": "📉", "warn": "⚠️", "neutral": "➡️"}


# ── 日付ユーティリティ ───────────────────────────────────────
def _last_day(y: int, m: int) -> int:
    return _cal.monthrange(y, m)[1]


def _is_second_friday(dt: datetime) -> bool:
    """その月の第2金曜日か（SQ日）"""
    return dt.weekday() == 4 and 8 <= dt.day <= 14


def _is_goto_day(dt: datetime) -> bool:
    """ゴトー日（5・10のつく日＝5,10,15,20,25,月末）。
    土日の場合は直前の営業日（金曜）に前倒しされる慣習を反映。"""
    last = _last_day(dt.year, dt.month)
    goto = {5, 10, 15, 20, 25, last}
    # その日がゴトー日
    if dt.day in goto and dt.weekday() < 5:
        return True
    # 金曜で、翌日(土)or翌々日(日)がゴトー日なら前倒し対象
    if dt.weekday() == 4:
        for add in (1, 2):
            nxt = dt + timedelta(days=add)
            if nxt.month == dt.month and nxt.day in goto:
                return True
            # 月末がゴトーで土日の場合
            if nxt.day in {5, 10, 15, 20, 25, _last_day(nxt.year, nxt.month)}:
                return True
    return False


# ── アノマリー判定（各 judge は dt を受けて bool） ─────────────
# (id, 絵文字, 名前, sentiment, 説明, judge関数)
_ANOMALIES = [
    # ─ 時期・季節 ─
    ("january",     "🎍", "1月効果",        "bull",
     "年初の資金流入で小型株が上がりやすい時期",
     lambda d: d.month == 1),
    ("setsubun",    "🌸", "節分天井",        "warn",
     "2月初旬に高値をつけやすい（節分天井・彼岸底の格言）",
     lambda d: d.month == 2 and d.day <= 10),
    ("higan",       "🌅", "彼岸底",          "bull",
     "3月下旬（彼岸）に安値をつけ反転しやすいとされる",
     lambda d: d.month == 3 and 18 <= d.day <= 25),
    ("new_fy",      "🌱", "新年度入り",      "bull",
     "4月は新規資金流入で上がりやすい（新年度相場）",
     lambda d: d.month == 4 and d.day <= 10),
    ("sell_in_may", "🚪", "Sell in May",     "bear",
     "「5月に売れ」。5〜10月は軟調になりやすい季節局面入り",
     lambda d: d.month == 5),
    ("summer",      "🏖", "夏枯れ相場",      "warn",
     "7〜8月は商いが薄く方向感が出にくい（夏休み・お盆）",
     lambda d: d.month in (7, 8)),
    ("halloween",   "🎃", "ハロウィン効果",  "bull",
     "10月末に買って翌4月まで保有すると良いという経験則",
     lambda d: d.month == 10 and d.day >= 25),
    ("santa",       "🎅", "サンタクロース・ラリー", "bull",
     "12月下旬〜年始は株高になりやすい（年末ラリー）",
     lambda d: d.month == 12 and d.day >= 20),

    # ─ 大局（半年サイクル） ─
    ("weak_half",   "🍂", "半年の軟調期（5〜10月）", "bear",
     "5〜10月は歴史的にリターンが低い「Sell in May〜ハロウィン」局面",
     lambda d: 5 <= d.month <= 10),
    ("strong_half", "🌟", "半年の好調期（11〜4月）", "bull",
     "11〜4月は歴史的にリターンが高い「ハロウィン〜5月」局面",
     lambda d: d.month >= 11 or d.month <= 4),

    # ─ 日付・需給 ─
    ("month_start", "📈", "月初効果",        "bull",
     "月初は年金など機関の資金流入で上がりやすい",
     lambda d: d.day <= 3 and d.weekday() < 5),
    ("goto",        "💴", "ゴトー日",        "neutral",
     "5・10のつく日。ドル買い需要でドル円が上がりやすい（円安方向）",
     _is_goto_day),
    ("sq",          "🔔", "SQ（第2金曜）",   "warn",
     "オプション清算日。需給で乱高下しやすい",
     lambda d: _is_second_friday(d) and d.month not in (3, 6, 9, 12)),
    ("major_sq",    "🔔", "メジャーSQ",      "warn",
     "先物＋オプション同時清算（3・6・9・12月の第2金曜）。最も荒れやすい",
     lambda d: _is_second_friday(d) and d.month in (3, 6, 9, 12)),
    ("sq_week",     "🌀", "SQ週",            "warn",
     "今週末がSQ。週を通して値動きが荒くなりやすい",
     lambda d: any(_is_second_friday(d + timedelta(days=k)) for k in range(0, 5 - d.weekday()) if d.weekday() < 5)),
    ("rule45",      "📆", "45日ルール",      "warn",
     "四半期末45日前。ヘッジファンド解約通知が集中し需給が崩れやすい",
     lambda d: d.month in (2, 5, 8, 11) and 13 <= d.day <= 17),

    # ─ 配当・期末 ─
    ("ken_ochi",    "✂️", "配当権利落ち期",  "warn",
     "3月末・9月末の権利確定後は配当分だけ株価が下がりやすい",
     lambda d: d.month in (3, 9) and d.day >= 25),

    # ─ 曜日 ─
    ("monday",      "😴", "週明け（月曜）",  "bear",
     "月曜は下がりやすいという「週末効果」",
     lambda d: d.weekday() == 0),
    ("friday",      "😀", "週末（金曜）",    "bull",
     "金曜は上がりやすい一方、リスク回避で手仕舞いも出やすい",
     lambda d: d.weekday() == 4),
]


def _us_election_cycle(dt: datetime) -> dict | None:
    """大統領選サイクル（2024年=選挙年を基準）"""
    phase = (dt.year - 2024) % 4
    table = {
        0: ("warn",    "🗳", "大統領選イヤー", "選挙year。政策不透明感で乱高下しやすい"),
        1: ("neutral", "1️⃣", "政権1年目",     "就任1年目。歴史的にやや軟調"),
        2: ("bear",    "2️⃣", "政権2年目（中間選挙年）", "中間選挙year。4年で最も軟調になりやすい"),
        3: ("bull",    "3️⃣", "政権3年目",     "歴史的に4年で最も株高になりやすい年（最強アノマリー）"),
    }
    sent, emoji, name, desc = table[phase]
    return {"id": "election", "emoji": emoji, "name": name,
            "sentiment": sent, "desc": desc}


def get_active_anomalies(dt: datetime = None) -> list[dict]:
    """指定日（未指定なら今日）に該当するアノマリーを全部返す"""
    d = dt or get_jst_now()
    active = []
    for aid, emoji, name, sent, desc, judge in _ANOMALIES:
        try:
            if judge(d):
                active.append({"id": aid, "emoji": emoji, "name": name,
                               "sentiment": sent, "desc": desc})
        except Exception:
            pass
    # 大統領選サイクルは常に1つ該当
    ec = _us_election_cycle(d)
    if ec:
        active.append(ec)
    return active


# ── 出力生成 ─────────────────────────────────────────────────
def _sentiment_counts(anomalies: list) -> dict:
    c = {"bull": 0, "bear": 0, "warn": 0, "neutral": 0}
    for a in anomalies:
        c[a["sentiment"]] = c.get(a["sentiment"], 0) + 1
    return c


def build_telegram_message(anomalies: list, astro: dict) -> str:
    if not anomalies and not (astro and astro.get("mercury_now")):
        return ""
    lines = ["📜 *今日のアノマリー（相場の経験則）*", ""]
    for a in anomalies:
        lines.append(f"{a['emoji']} {SENT[a['sentiment']]} *{a['name']}*")
        lines.append(f"　{a['desc']}")
    # 天体
    if astro:
        if astro.get("mercury_now"):
            lines.append("")
            lines.append(f"☿ *水星逆行中*（{astro.get('mercury_period','')}）")
            lines.append("　取引ミス・通信トラブルに注意の経験則")
        aev = astro.get("events", []) or []
        soon = [e for e in aev if "月" in e.get("event", "")][:1]
        for e in soon:
            d = e.get("date", "")
            md = f"{int(d[5:7])}/{int(d[8:10])}" if len(d) >= 10 else d
            lines.append(f"{e.get('event','')}　{md}")
    lines.append("")
    lines.append("※あくまで経験則。必ず当たるものではありません")
    return "\n".join(lines)


def get_html(result: dict) -> str:
    if not result or not result.get("available"):
        return ""
    anomalies = result.get("anomalies", [])
    astro     = result.get("astro", {}) or {}

    sent_color = {"bull": "#3fb950", "bear": "#f44336",
                  "warn": "#ffa726", "neutral": "#7a8fa8"}
    rows = ""
    for a in anomalies:
        c = sent_color.get(a["sentiment"], "#7a8fa8")
        rows += f'''
<div style="display:flex;gap:10px;padding:9px 0;border-bottom:1px solid #1e2d42;">
  <div style="font-size:1.2em;">{a["emoji"]}</div>
  <div style="flex:1;">
    <div style="font-weight:700;font-size:0.9em;color:{c};">{SENT[a['sentiment']]} {a["name"]}</div>
    <div style="font-size:0.8em;color:#aebed4;line-height:1.5;">{a["desc"]}</div>
  </div>
</div>'''

    merc = ""
    if astro.get("mercury_now"):
        merc = f'<div style="background:#2a1a3a;border:1px solid #7e57c2;border-radius:8px;padding:8px 12px;margin:8px 0;font-size:0.85em;">☿ <b>水星逆行中</b>（{astro.get("mercury_period","")}）— 取引ミス・通信障害に注意の経験則</div>'

    cnt = _sentiment_counts(anomalies)
    summary = (f'<div style="font-size:0.78em;color:#7a8fa8;margin-bottom:10px;">'
               f'今日該当：📈強気{cnt["bull"]} / 📉弱気{cnt["bear"]} / ⚠️注意{cnt["warn"]} / ➡️中立{cnt["neutral"]}　'
               f'（経験則であり保証ではありません）</div>')

    return f'''
<div style="background:#0f1623;border:1px solid #1e2d42;border-radius:14px;padding:16px;margin-bottom:16px;">
  <div style="font-weight:700;margin-bottom:4px;">📜 今日のアノマリー（相場の経験則）</div>
  {summary}{merc}{rows}
</div>'''


# ── cloud_run.py 標準インターフェース ───────────────────────────
def run(prices: dict = None, risk: dict = None, fear_greed: dict = None) -> dict:
    try:
        anomalies = get_active_anomalies()
        # 天体サマリーを統合
        astro = {"available": False}
        try:
            from src.astro_calendar import get_upcoming_summary
            astro = get_upcoming_summary(days=30)
        except Exception:
            pass
        result = {
            "available": len(anomalies) > 0,
            "anomalies": anomalies,
            "astro":     astro,
            "count":     len(anomalies),
        }
        result["html"] = get_html(result)
        result["telegram_message"] = build_telegram_message(anomalies, astro)
        return result
    except Exception as e:
        logger.error(f"アノマリーカレンダーエラー: {e}")
        return {"available": False}


if __name__ == "__main__":
    import sys
    # 引数で日付指定可能（YYYYMMDD）
    if len(sys.argv) > 1 and len(sys.argv[1]) == 8:
        s = sys.argv[1]
        dt = datetime(int(s[:4]), int(s[4:6]), int(s[6:8]), tzinfo=JST)
        anomalies = get_active_anomalies(dt)
        d_label = s
    else:
        anomalies = get_active_anomalies()
        d_label = get_jst_now().strftime("%Y-%m-%d (%a)")

    lines = [f"=== {d_label} に該当するアノマリー（{len(anomalies)}件）==="]
    for a in anomalies:
        lines.append(f"{a['emoji']} {SENT[a['sentiment']]} {a['name']}")
        lines.append(f"   {a['desc']}")
    text = "\n".join(lines)
    try:
        print(text)
    except UnicodeEncodeError:
        with open("anomaly_output.txt", "w", encoding="utf-8") as f:
            f.write(text)
        print("anomaly_output.txt に保存しました")
