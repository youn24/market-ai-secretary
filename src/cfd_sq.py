"""
CFD/24時間先物 ＋ SQ情報（Step CFD・寄り付き先行ヒント）

- CME日経225先物（円建て NIY=F）: ほぼ24時間取引されるCFD価格の実体。
  前日の日経225終値との乖離＝寄り付きギャップの最有力先行指標。
- 米株指数先物（S&P/NASDAQ/ダウ）: 朝7:30時点の時間外リスクセンチメント。
- SQ: 毎月第2金曜のSQ日程を純計算（メジャー=3/6/9/12月）。
  SQ週は先物・オプション清算に向けたポジション調整で荒れやすい。

run(prices) → {"available", "futures":[...], "cme_gap_pct", "sq":{...}, "telegram_block"}
"""
import json
import traceback
from datetime import date, timedelta
from src.utils import setup_logger, get_jst_now

logger = setup_logger("cfd_sq")

# 24時間取引の先物（CFD業者の配信価格はこれらのCME/Globex価格がベース）
_FUTURES = [
    ("NIY=F", "CME日経225先物(円建)"),
    ("ES=F",  "S&P500先物"),
    ("NQ=F",  "NASDAQ100先物"),
    ("YM=F",  "NYダウ先物"),
]

# CFDで24時間取引されるコモディティ・欧州指数（朝のレポート表示用）
_COMMODITIES = [
    ("GC=F",   "金",        "🥇"),
    ("SI=F",   "銀",        "🥈"),
    ("CL=F",   "WTI原油",   "🛢"),
    ("NG=F",   "天然ガス",   "🔥"),
    ("HG=F",   "銅",        "🔶"),
    ("^GDAXI", "独DAX",     "🇩🇪"),
    ("^FTSE",  "英FTSE",    "🇬🇧"),
]


def _fetch_one(sym: str):
    """最新値と前日清算値比%を返す。失敗は None。"""
    try:
        import yfinance as yf
        t = yf.Ticker(sym)
        last = prev = None
        try:
            fi = t.fast_info
            last = fi.last_price
            prev = fi.previous_close
        except Exception:
            pass
        if not last or not prev:
            h = t.history(period="5d", interval="1d")
            if h is None or h.empty:
                return None
            closes = h["Close"].dropna()
            if len(closes) < 2:
                return None
            last, prev = float(closes.iloc[-1]), float(closes.iloc[-2])
        chg = (last - prev) / prev * 100
        return {"latest": round(float(last), 2), "change_pct": round(chg, 2)}
    except Exception:
        return None


def next_sq(today: date) -> dict:
    """次のSQ日（第2金曜）を純計算で返す。"""
    for off in (0, 1, 2):
        y = today.year + (today.month - 1 + off) // 12
        m = (today.month - 1 + off) % 12 + 1
        w = date(y, m, 1).weekday()          # Mon=0..Fri=4
        day = 1 + (4 - w) % 7 + 7            # 第2金曜の日付
        sq = date(y, m, day)
        if sq >= today:
            days = (sq - today).days
            major = m in (3, 6, 9, 12)
            return {
                "date": sq.strftime("%m/%d(金)"),
                "days_to": days,
                "is_major": major,
                "type": "メジャーSQ" if major else "オプションSQ",
                "is_sq_week": days <= 4,
                "is_today": days == 0,
            }
    return {}


# SQ値（特別清算指数）の履歴。メジャーSQのSQ値はその後の相場の節目として意識される。
_SQ_HISTORY_URL = "https://nikkei225jp.com/_data/_nfsDATA/HS_DATA_DAY/SQ_HISTORY.json"


def fetch_sq_value(prices: dict = None):
    """
    直近のSQ値と、現在の日経平均がその上か下かを返す。

    「SQ値を上回って推移していれば強い」というのは市場で広く意識される見方で、
    特にメジャーSQのSQ値はその後1〜3か月の節目として機能することが多い。
    """
    try:
        import re
        import requests
        from datetime import datetime, timezone, timedelta
        r = requests.get(_SQ_HISTORY_URL, timeout=15, headers={
            "User-Agent": "Mozilla/5.0", "Referer": "https://nikkei225jp.com/data/sq.php"})
        r.raise_for_status()
        m = re.search(r"var\s+SQ_HISTORY\s*=\s*(\[.*?\])\s*;", r.text, re.S)
        if not m:
            return None
        rows = json.loads(m.group(1))
        if not rows:
            return None
        JST = timezone(timedelta(hours=9))

        def _d(ts):
            return datetime.fromtimestamp(ts / 1000, JST).date()

        # メジャーSQ＝3/6/9/12月の第2金曜。日付から自前で判定する（フラグに依存しない）
        def _is_major(d):
            return d.month in (3, 6, 9, 12) and d.weekday() == 4 and 8 <= d.day <= 14

        last = rows[-1]
        last_d, last_v = _d(last[0]), float(last[1])
        majors = [(_d(x[0]), float(x[1])) for x in rows[-40:] if _is_major(_d(x[0]))]
        major_d, major_v = majors[-1] if majors else (None, None)

        # 値の妥当性（日経平均のレンジを大きく外れたら破棄）
        if not (5000 <= last_v <= 200000):
            return None

        n225 = (prices or {}).get("^N225", {}).get("latest")
        res = {"date": last_d.strftime("%m/%d"), "value": last_v,
               "major_date": major_d.strftime("%m/%d") if major_d else None,
               "major_value": major_v}
        if n225 and major_v:
            diff = (n225 - major_v) / major_v * 100
            res["vs_major_pct"] = round(diff, 2)
            res["above_major"] = diff > 0
        return res
    except Exception:
        logger.debug(traceback.format_exc())
        return None


def run(prices: dict = None) -> dict:
    prices = prices or {}
    futures = []
    for sym, name in _FUTURES:
        d = _fetch_one(sym)
        if d:
            futures.append({"symbol": sym, "name": name, **d})

    # コモディティ・欧州指数（24時間CFD銘柄）を並列取得
    commodities = []
    try:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=5) as ex:
            fs = {ex.submit(_fetch_one, s): (s, n, ic) for s, n, ic in _COMMODITIES}
            for f in as_completed(fs):
                s, n, ic = fs[f]
                d = f.result()
                if d:
                    commodities.append({"symbol": s, "name": n, "icon": ic, **d})
        order = {s: i for i, (s, _, _) in enumerate(_COMMODITIES)}
        commodities.sort(key=lambda x: order.get(x["symbol"], 99))
    except Exception:
        logger.debug("コモディティ取得スキップ")

    # CME日経 vs 前日の日経225終値 → 寄り付きギャップ予想
    cme_gap = None
    n225 = (prices.get("^N225") or {}).get("latest")
    cme = next((f for f in futures if f["symbol"] == "NIY=F"), None)
    if cme and n225:
        g = (cme["latest"] - n225) / n225 * 100
        # 通常±3%以内。5%超はデータ不整合（限月替わり・stale値）とみなし非表示
        cme_gap = round(g, 2) if abs(g) <= 5 else None

    sq = next_sq(get_jst_now().date())
    sq_value = fetch_sq_value(prices)

    if not futures and not sq:
        return {"available": False}

    # Telegram用ブロック
    lines = ["🌐 *CFD/24時間先物・SQ*"]
    if cme and cme_gap is not None:
        g_e = "🟢上" if cme_gap > 0.3 else "🔴下" if cme_gap < -0.3 else "🟡横"
        lines.append(f"CME日経: {cme['latest']:,.0f}円 (大阪比 {cme_gap:+.2f}% {g_e}ギャップ示唆)")
    elif cme:
        lines.append(f"CME日経: {cme['latest']:,.0f}円 ({cme['change_pct']:+.2f}%)")
    us_parts = [f"{f['name'].replace('先物','')} {f['change_pct']:+.2f}%"
                for f in futures if f["symbol"] != "NIY=F"]
    if us_parts:
        lines.append("米先物: " + " / ".join(us_parts))
    if commodities:
        cm_parts = [f"{c['icon']}{c['name']} {c['change_pct']:+.1f}%" for c in commodities]
        lines.append("商品・欧州: " + " / ".join(cm_parts))
    if sq_value and sq_value.get("major_value"):
        if sq_value.get("vs_major_pct") is not None:
            mark = "上" if sq_value["above_major"] else "下"
            lines.append(f"🎯 メジャーSQ値 {sq_value['major_value']:,.0f}（{sq_value['major_date']}）"
                         f" — 現在は{mark}回り {sq_value['vs_major_pct']:+.2f}%")
        else:
            lines.append(f"🎯 メジャーSQ値 {sq_value['major_value']:,.0f}（{sq_value['major_date']}）")
    if sq:
        sq_s = f"📅 {sq['type']}: {sq['date']}"
        sq_s += " ★本日SQ" if sq["is_today"] else f" (あと{sq['days_to']}日)"
        if sq["is_sq_week"] and not sq["is_today"]:
            sq_s += " ⚠️SQ週=荒れやすい"
        lines.append(sq_s)

    result = {
        "available": True,
        "futures": futures,
        "sq_value": sq_value,
        "commodities": commodities,
        "cme_gap_pct": cme_gap,
        "sq": sq,
        "telegram_block": "\n".join(lines),
    }
    logger.info(f"✅ CFD/SQ: 先物{len(futures)}本 商品{len(commodities)}本 "
                f"CMEギャップ={cme_gap}% SQまで{sq.get('days_to')}日")
    return result


if __name__ == "__main__":
    r = run({"^N225": {"latest": 39000.0}})
    print(r.get("telegram_block", "unavailable"))
    print("SQ:", r.get("sq"))
