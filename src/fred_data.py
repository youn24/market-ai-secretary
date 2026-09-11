"""
L4c: FRB経済指標（FRED）取得モジュール
APIキー不要でGDP・CPI・失業率・FF金利・イールドカーブを取得
"""
import urllib.request
import ssl
import time
import io
import json
import csv
import logging
from datetime import datetime, timedelta

from src.utils import BASE_DIR

logger = logging.getLogger(__name__)

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE

FRED_SERIES = {
    "cpi":       {"id": "CPIAUCSL",  "name": "米CPI（消費者物価）", "unit": "前年比%", "type": "yoy"},
    "core_cpi":  {"id": "CPILFESL",  "name": "米コアCPI",          "unit": "前年比%", "type": "yoy"},
    "unemployment": {"id": "UNRATE", "name": "米失業率",            "unit": "%",      "type": "level"},
    "fed_funds": {"id": "FEDFUNDS",  "name": "FF金利",             "unit": "%",      "type": "level"},
    "yield_curve":{"id": "T10Y2Y",   "name": "イールドカーブ(10y-2y)","unit": "bp",  "type": "level"},
    "gdp_growth": {"id": "A191RL1Q225SBEA", "name": "米GDP成長率(QoQ)", "unit": "%", "type": "level"},
    "pce":        {"id": "PCE",      "name": "米PCE物価指数",       "unit": "前年比%", "type": "yoy"},
}


# FREDから取れた系列をそのまま置いておく場所。
# ⚠️ FREDのCSV口は日によって全系列が落ちる（2026-09-10に実測。
#    40分前まで取れていた T10Y2Y も含めて全滅した）。
#    ここで扱うのはCPI・失業率・政策金利といった**月次で動く指標**なので、
#    数日前の値でも判断の役に立つ。取れない日に何も出さないほうが損失が大きい。
_CACHE_FILE = BASE_DIR / "data" / "fred_cache.json"
_CACHE_MAX_DAYS = 21          # 月次指標なので3週間までは使う


def _cache_load() -> dict:
    try:
        return json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _cache_get(series_id: str):
    """(行データ, 何日前か)。使えなければ (None, -1)。"""
    c = _cache_load().get(series_id)
    if not c:
        return None, -1
    try:
        d0 = datetime.strptime(c["date"], "%Y-%m-%d").date()
        age = (datetime.now().date() - d0).days
        if age < 0 or age > _CACHE_MAX_DAYS or not c.get("rows"):
            return None, -1
        return c["rows"], age
    except Exception:
        return None, -1


def _cache_put(series_id: str, rows: list) -> None:
    try:
        c = _cache_load()
        c[series_id] = {"date": datetime.now().strftime("%Y-%m-%d"), "rows": rows}
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


# ── FRED全体の遮断器（サーキットブレーカー）──────────────────
# ⚠️ 2026-09-11、朝のレポートが**タイムアウトで丸ごと落ちた**。原因は前日に
#    入れた「3回リトライ・30秒待ち」。FREDが落ちている日は1系列あたり
#    最大97秒かかり、fred_data 7系列で11分・fundamental_signals 4系列で5分・
#    政策金利2系列で3分、**合計約20分**が普段の20分に上乗せされて
#    30分の制限を超えた。
#
#    しかも「FREDは落ちるときは全系列が同時に落ちる」ことは前日に
#    自分で実測していた（40分前まで取れていた系列も含めて全滅した）。
#    それなのに系列ごとに律儀に3回ずつ待つ作りにしていた。
#
#    そこで、**1系列でも全試行が失敗したら、その実行の間はFREDを
#    落ちているとみなし、以降は通信せずキャッシュへ直行する**。
#    最悪でも最初の1系列ぶん（約26秒）しか待たない。
_FRED_DOWN = False


def fred_is_down() -> bool:
    """この実行の中でFREDが全滅と判定済みか（他モジュールからも見る）。"""
    return _FRED_DOWN


def mark_fred_down(reason: str = "") -> None:
    """FREDを落ちているとみなす。以降のFRED呼び出しは通信しない。"""
    global _FRED_DOWN
    if not _FRED_DOWN:
        logger.warning(f"⚡ FREDに接続できないため、この実行の間は通信を止めて"
                       f"キャッシュを使います（{reason}）")
    _FRED_DOWN = True


def _fetch_series(series_id: str, limit: int = 24, tries: int = 2) -> list:
    """FREDからCSVデータを取得（API不要）

    ⚠️ FREDのこのCSV口は、混んでいる時間帯に**接続そのものを切ってくる**
       （2026-09-10に WinError 10054 と read timeout を実測）。
       1回で諦めていたため、政策金利ウォッチが 08-26 以降ずっと
       「データなし」で落ちていた。少し待って試し直す。
       同じ対策を src/fundamental_signals.py にも入れてある。
    """
    # 既に全滅と分かっているなら待たない。キャッシュがあれば使う。
    if _FRED_DOWN:
        cached, age = _cache_get(series_id)
        return cached[-limit:] if cached else []

    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    for i in range(tries):
        try:
            # 30秒→12秒。応答するときは数秒で返る。長く待っても取れない。
            resp = urllib.request.urlopen(req, context=_ctx, timeout=12)
            content = resp.read().decode("utf-8")
            reader = csv.reader(io.StringIO(content))
            rows = [r for r in reader if len(r) == 2 and r[1] not in (".", "")]
            rows = rows[1:]
            if rows:
                _cache_put(series_id, rows[-60:])   # 少し多めに残しておく
            return rows[-limit:]
        except Exception as e:
            if i == tries - 1:
                mark_fred_down(f"{series_id}: {type(e).__name__}")
                cached, age = _cache_get(series_id)
                if cached:
                    logger.warning(f"FRED取得失敗 {series_id}（{tries}回試行）。"
                                   f"{age}日前の値を使います: {e}")
                    return cached[-limit:]
                logger.warning(f"FRED取得失敗 {series_id}（{tries}回試行・"
                               f"キャッシュも無し）: {e}")
                return []
            time.sleep(2 * (i + 1))
    return []


def _fetch_yahoo_macro() -> dict:
    """Yahoo FinanceからマクロデータをFREDのフォールバックとして取得"""
    import json
    result = {}
    yahoo_symbols = {
        "fed_funds":   ("^IRX", "FF金利(TB3M代理)", "%", "level"),
        "yield_10y":   ("^TNX", "米10年国債利回り", "%", "level"),
        "yield_30y":   ("^TYX", "米30年国債利回り", "%", "level"),
    }
    for key, (sym, name, unit, typ) in yahoo_symbols.items():
        url = f"https://query2.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=1mo"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            resp = urllib.request.urlopen(req, context=_ctx, timeout=10)
            data = json.loads(resp.read())
            r = data["chart"]["result"][0]
            closes = [c for c in r["indicators"]["quote"][0]["close"] if c]
            if closes:
                latest = closes[-1]
                prev = closes[-2] if len(closes) > 1 else latest
                result[key] = {
                    "name": name, "unit": unit,
                    "value": round(latest, 3),
                    "change": round(latest - prev, 3),
                    "date": datetime.now().strftime("%Y-%m"),
                    "history": [],
                }
        except Exception:
            pass
    # yield curve = 10y - 3m
    if "yield_10y" in result and "fed_funds" in result:
        yc = result["yield_10y"]["value"] - result["fed_funds"]["value"]
        result["yield_curve"] = {
            "name": "イールドカーブ(10y-3m)",
            "unit": "%",
            "value": round(yc, 3),
            "change": 0,
            "date": datetime.now().strftime("%Y-%m"),
            "history": [],
        }
    return result


def _calc_yoy(rows: list) -> float | None:
    """前年比を計算（月次データ用）"""
    if len(rows) < 13:
        return None
    try:
        current = float(rows[-1][1])
        year_ago = float(rows[-13][1])
        if year_ago == 0:
            return None
        return round((current - year_ago) / year_ago * 100, 2)
    except Exception:
        return None


def run() -> dict:
    """FRED経済指標を取得して返す"""
    logger.info("--- Step L4c: FRED経済指標取得 ---")
    result = {"available": False, "indicators": {}, "summary": "", "fetched_at": ""}

    try:
        indicators = {}
        for key, meta in FRED_SERIES.items():
            rows = _fetch_series(meta["id"], limit=24)
            if not rows:
                continue

            latest_date = rows[-1][0]
            latest_val = float(rows[-1][1])

            if meta["type"] == "yoy":
                display_val = _calc_yoy(rows)
                if display_val is None:
                    display_val = latest_val
            else:
                display_val = latest_val

            prev_val = float(rows[-2][1]) if len(rows) >= 2 else None
            change = round(display_val - (
                _calc_yoy(rows[:-1]) if meta["type"] == "yoy" and prev_val else prev_val or display_val
            ), 2) if prev_val else 0

            indicators[key] = {
                "name": meta["name"],
                "unit": meta["unit"],
                "value": round(display_val, 2),
                "raw_latest": round(latest_val, 2),
                "date": latest_date,
                "change": change,
                "history": [(r[0], float(r[1])) for r in rows[-6:]],
            }
            logger.info(f"  ✅ {meta['name']}: {display_val:.2f}{meta['unit']} ({latest_date})")

        if not indicators:
            logger.warning("FRED直接取得失敗 → Yahoo Financeフォールバック")
            indicators = _fetch_yahoo_macro()
            if not indicators:
                return result
            logger.info(f"  Yahoo Financeフォールバック: {len(indicators)}件取得")

        # サマリー生成
        parts = []
        if "fed_funds" in indicators:
            ff = indicators["fed_funds"]["value"]
            parts.append(f"FF金利{ff:.2f}%")
        if "unemployment" in indicators:
            ur = indicators["unemployment"]["value"]
            parts.append(f"失業率{ur:.1f}%")
        if "cpi" in indicators:
            cp = indicators["cpi"]["value"]
            parts.append(f"CPI前年比{cp:.1f}%")
        if "yield_curve" in indicators:
            yc = indicators["yield_curve"]["value"]
            sign = "正常" if yc > 0 else "逆転"
            parts.append(f"イールドカーブ{yc:.2f}bp({sign})")

        result = {
            "available": True,
            "indicators": indicators,
            "summary": " / ".join(parts),
            "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        logger.info(f"✅ FRED指標取得完了: {len(indicators)}件")

    except Exception as e:
        logger.error(f"FRED取得エラー: {e}")
        import traceback
        logger.debug(traceback.format_exc())

    return result


def format_telegram(fred: dict) -> str:
    """Telegram用フォーマット"""
    if not fred.get("available"):
        return ""
    ind = fred["indicators"]
    lines = [
        "🏦 *米国マクロ指標（FRED）*",
        "━━━━━━━━━━━━━━━",
    ]
    order = ["fed_funds", "unemployment", "cpi", "core_cpi", "yield_curve", "gdp_growth"]
    icons = {"fed_funds": "💰", "unemployment": "👷", "cpi": "🛒",
             "core_cpi": "📊", "yield_curve": "📈", "gdp_growth": "🏭", "pce": "💳"}
    for key in order:
        if key not in ind:
            continue
        d = ind[key]
        icon = icons.get(key, "•")
        chg_str = ""
        if d.get("change") and abs(d["change"]) > 0.01:
            chg_str = f" ({'+' if d['change']>0 else ''}{d['change']:.2f})"
        lines.append(f"{icon} {d['name']}: *{d['value']:.2f}{d['unit']}*{chg_str}")
        lines.append(f"   更新: {d['date']}")
    return "\n".join(lines)
