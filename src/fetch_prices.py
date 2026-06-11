"""
価格データ取得モジュール
すべて無料・APIキー不要のソースのみ使用

取得ソース（優先順位順）:
  1. Yahoo Finance 直接API (query1.finance.yahoo.com/v8/finance/chart)
  2. CoinGecko API (仮想通貨のみ)
  3. open.er-api.com (為替のみ)
  4. Stooq CSV (補完)
"""
import json
import time
from pathlib import Path

import pandas as pd
import requests
import yaml

from src.utils import BASE_DIR, get_jst_now, get_today_str, get_dirs, setup_logger

logger = setup_logger("fetch_prices")

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "ja,en;q=0.9",
}


def load_symbols() -> dict:
    with open(BASE_DIR / "config" / "symbols.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ─── ① Yahoo Finance 直接API ────────────────────────────────────────────────

def _fetch_yahoo_direct(symbol: str) -> dict | None:
    """Yahoo Finance chart API に直接リクエスト。latestとchange_pctを返す。"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d"
    try:
        r = requests.get(url, headers=_HEADERS, timeout=15)
        r.raise_for_status()
        result = r.json()["chart"]["result"][0]
        closes = [c for c in result["indicators"]["quote"][0]["close"] if c is not None]
        if not closes:
            return None
        latest = round(closes[-1], 4)
        prev   = round(closes[-2], 4) if len(closes) >= 2 else None
        change = round((latest - prev) / abs(prev) * 100, 2) if prev else None
        return {"latest": latest, "prev_close": prev, "change_pct": change, "source": "Yahoo直接API"}
    except Exception as e:
        logger.warning(f"Yahoo直接API 失敗 [{symbol}]: {e}")
    return None


# ─── ② CoinGecko（仮想通貨） ─────────────────────────────────────────────────

_COINGECKO_IDS = {
    "BTC-USD": "bitcoin",
    "ETH-USD": "ethereum",
    "SOL-USD": "solana",
}

def _fetch_coingecko(symbol: str) -> dict | None:
    cg_id = _COINGECKO_IDS.get(symbol)
    if not cg_id:
        return None
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={cg_id}&vs_currencies=usd&include_24hr_change=true"
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        data = r.json().get(cg_id, {})
        price = data.get("usd")
        change = data.get("usd_24h_change")
        if price is None:
            return None
        return {
            "latest": round(price, 2),
            "prev_close": None,
            "change_pct": round(change, 2) if change else None,
            "source": "CoinGecko",
        }
    except Exception as e:
        logger.warning(f"CoinGecko 失敗 [{symbol}]: {e}")
    return None


# ─── ③ open.er-api.com（為替） ──────────────────────────────────────────────

_ER_BASE_PAIRS = {
    "USDJPY=X": ("USD", "JPY"),
    "EURUSD=X": ("EUR", "USD"),
    "GBPUSD=X": ("GBP", "USD"),
    "EURJPY=X": ("EUR", "JPY"),
}

_er_cache: dict = {}

def _fetch_exchangerate(symbol: str) -> dict | None:
    pair = _ER_BASE_PAIRS.get(symbol)
    if not pair:
        return None
    base, quote = pair
    # 同じbaseは1回だけ取得してキャッシュ
    if base not in _er_cache:
        try:
            r = requests.get(f"https://open.er-api.com/v6/latest/{base}", timeout=15)
            r.raise_for_status()
            _er_cache[base] = r.json().get("rates", {})
        except Exception as e:
            logger.warning(f"ExchangeRate-API 失敗 [{base}]: {e}")
            return None
    rate = _er_cache.get(base, {}).get(quote)
    if rate is None:
        return None
    return {"latest": round(rate, 4), "prev_close": None, "change_pct": None, "source": "ExchangeRate-API"}


# ─── ④ 日本市場プロ指標（株探 / Yahoo!ファイナンス日本版 / 日経公式CSV） ──────

def _fetch_kabutan(code: str) -> dict | None:
    """株探（kabutan.jp）から指数値をスクレイピング。
    TOPIX=0010, 日経平均=0000, グロース250=0012, ドル円=0950
    """
    import re
    url = f"https://kabutan.jp/stock/?code={code}"
    try:
        r = requests.get(url, headers=_HEADERS, timeout=15)
        r.raise_for_status()
        m = re.search(r'<span class="kabuka">([\d,\.]+)', r.text)
        if not m:
            return None
        latest = float(m.group(1).replace(",", ""))
        # 前日比: <dt>前日比</dt><dd><span class="down">-17.25</span></dd><dd><span class="down">-0.45</span>%</dd>
        change = None
        prev = None
        m2 = re.search(
            r'<dt>前日比</dt>\s*'
            r'<dd><span(?: class="[^"]*")?>([+\-]?[\d,\.]+)</span></dd>\s*'
            r'<dd><span(?: class="[^"]*")?>([+\-]?[\d,\.]+)</span>%',
            r.text)
        if m2:
            diff   = float(m2.group(1).replace(",", ""))
            change = float(m2.group(2))
            prev   = round(latest - diff, 2)
        return {"latest": round(latest, 2), "prev_close": prev,
                "change_pct": change, "source": f"株探({code})"}
    except Exception as e:
        logger.warning(f"株探 失敗 [{code}]: {e}")
    return None


def _fetch_yahoo_japan(code: str) -> dict | None:
    """Yahoo!ファイナンス日本版のページからJSON埋め込み値を抽出。TOPIX=998405.T"""
    import re
    url = f"https://finance.yahoo.co.jp/quote/{code}"
    try:
        r = requests.get(url, headers=_HEADERS, timeout=15)
        r.raise_for_status()
        m = re.search(r'"price"\s*:\s*"([\d,\.]+)"', r.text)
        if not m:
            return None
        latest = float(m.group(1).replace(",", ""))
        change = None
        prev = None
        m2 = re.search(r'"changePriceRate"\s*:\s*"(-?[\d,\.]+)"', r.text)
        if m2:
            change = float(m2.group(1).replace(",", ""))
        m3 = re.search(r'"previousPrice"\s*:\s*"([\d,\.]+)"', r.text)
        if m3:
            prev = float(m3.group(1).replace(",", ""))
        return {"latest": round(latest, 2), "prev_close": prev,
                "change_pct": change, "source": f"Yahoo!Japan({code})"}
    except Exception as e:
        logger.warning(f"Yahoo!Japan 失敗 [{code}]: {e}")
    return None


def _fetch_nikkei_official_csv(csv_name: str) -> dict | None:
    """日経公式CSV（indexes.nikkei.co.jp）。日経VI・日経平均の公式日次データ。
    形式: "日付","終値","始値","高値","安値"
    """
    url = f"https://indexes.nikkei.co.jp/nkave/historical/{csv_name}"
    try:
        r = requests.get(url, headers=_HEADERS, timeout=15)
        r.raise_for_status()
        lines = r.content.decode("shift_jis", errors="replace").strip().splitlines()
        # データ行のみ（日付で始まる行）を抽出
        rows = []
        for ln in lines:
            parts = [p.strip().strip('"') for p in ln.split(",")]
            if len(parts) >= 2 and "/" in parts[0]:
                try:
                    rows.append((parts[0], float(parts[1])))
                except ValueError:
                    continue
        if not rows:
            return None
        latest = rows[-1][1]
        prev   = rows[-2][1] if len(rows) >= 2 else None
        change = round((latest - prev) / abs(prev) * 100, 2) if prev else None
        return {"latest": round(latest, 2), "prev_close": round(prev, 2) if prev else None,
                "change_pct": change, "source": "日経公式CSV"}
    except Exception as e:
        logger.warning(f"日経公式CSV 失敗 [{csv_name}]: {e}")
    return None


def _fetch_topix() -> dict | None:
    """TOPIX指数（本物）: 株探 → Yahoo!Japan の2段フォールバック"""
    return _fetch_kabutan("0010") or _fetch_yahoo_japan("998405.T")


def _fetch_nikkei_vi() -> dict | None:
    """日経VI（日経平均ボラティリティー・インデックス）: 日経公式CSV"""
    return _fetch_nikkei_official_csv("nikkei_stock_average_vi_daily_jp.csv")


def _fetch_growth250() -> dict | None:
    """東証グロース市場250指数（本物）: 株探(0012) → ETF(2516.T)代替の順"""
    data = _fetch_kabutan("0012")
    if data:
        return data
    etf = _fetch_yahoo_direct("2516.T")
    if etf:
        etf["source"] = "グロース250ETF(2516.T)代替"
    return etf


# 特殊シンボル → 専用フェッチャーのディスパッチ
_SPECIAL_FETCHERS = {
    "^TOPX":     _fetch_topix,
    "NIKKEI_VI": _fetch_nikkei_vi,
    "GROWTH250": _fetch_growth250,
}


# ─── ⑤ Stooq CSV（補完） ────────────────────────────────────────────────────

def _fetch_stooq(stooq_symbol: str) -> dict | None:
    url = f"https://stooq.com/q/d/l/?s={stooq_symbol}&i=d"
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        from io import StringIO
        df = pd.read_csv(StringIO(resp.text))
        if df.empty or "Close" not in df.columns:
            return None
        closes = df.sort_values("Date")["Close"].dropna()
        if closes.empty:
            return None
        latest = round(float(closes.iloc[-1]), 4)
        prev   = round(float(closes.iloc[-2]), 4) if len(closes) >= 2 else None
        change = round((latest - prev) / abs(prev) * 100, 2) if prev else None
        return {"latest": latest, "prev_close": prev, "change_pct": change, "source": f"Stooq({stooq_symbol})"}
    except Exception as e:
        logger.warning(f"Stooq 失敗 [{stooq_symbol}]: {e}")
    return None


# ─── メイン取得ロジック ───────────────────────────────────────────────────────

def _fetch_single(sym: str, name: str, category: str, fallback_map: dict) -> dict:
    fetch_time = get_jst_now().isoformat()
    base = {"symbol": sym, "name": name, "category": category, "fetch_time": fetch_time}

    # ⓪ 特殊シンボル（TOPIX・日経VI・グロース250）は専用ルート
    special = _SPECIAL_FETCHERS.get(sym)
    data = special() if special else None

    # ① Yahoo Finance直接API（全シンボル共通）
    if data is None:
        data = _fetch_yahoo_direct(sym)

    # ② 仮想通貨はCoinGeckoも試す
    if data is None and sym in _COINGECKO_IDS:
        data = _fetch_coingecko(sym)

    # ③ 為替はExchangeRate-APIも試す
    if data is None and sym in _ER_BASE_PAIRS:
        data = _fetch_exchangerate(sym)

    # ④ Stooqフォールバック
    if data is None:
        stooq_sym = fallback_map.get(sym)
        if stooq_sym:
            data = _fetch_stooq(stooq_sym)

    if data:
        logger.info(f"[OK] {name}({sym}) = {data['latest']} [{data['source']}]")
        return {**base, **data, "error": None}

    logger.error(f"[FAIL] {name}({sym}): 全ソースで取得失敗")
    return {**base, "latest": None, "prev_close": None, "change_pct": None,
            "source": None, "error": "全ソースで取得失敗"}


def fetch_all_prices() -> dict:
    cfg = load_symbols()
    fallback_map = cfg.get("stooq_fallback", {})
    all_categories = ["indices", "fear_indices", "forex", "rates",
                      "commodities", "crypto", "us_stocks", "jp_stocks",
                      "shipping_proxy"]
    results = {}
    for cat in all_categories:
        for item in cfg.get(cat, []):
            results[item["symbol"]] = _fetch_single(
                item["symbol"], item["name"],
                item.get("category", cat), fallback_map
            )
            time.sleep(0.3)

    # ─── NT倍率（日経平均 ÷ TOPIX）を自動計算 ───
    n225  = results.get("^N225", {}).get("latest")
    topix = results.get("^TOPX", {}).get("latest")
    nt = {"symbol": "NT_RATIO", "name": "NT倍率", "category": "japan",
          "fetch_time": get_jst_now().isoformat(),
          "latest": None, "prev_close": None, "change_pct": None,
          "source": "計算値(日経平均÷TOPIX)", "error": None}
    if n225 and topix:
        nt["latest"] = round(n225 / topix, 2)
        # 前日NT倍率も計算できれば変化率を出す
        n225_prev  = results.get("^N225", {}).get("prev_close")
        topix_prev = results.get("^TOPX", {}).get("prev_close")
        if n225_prev and topix_prev:
            prev_nt = n225_prev / topix_prev
            nt["prev_close"] = round(prev_nt, 2)
            nt["change_pct"] = round((nt["latest"] - prev_nt) / prev_nt * 100, 2)
        logger.info(f"[OK] NT倍率 = {nt['latest']} [計算値]")
    else:
        nt["error"] = "日経平均またはTOPIX欠損のため計算不可"
        logger.warning("[--] NT倍率: 計算に必要なデータが不足")
    results["NT_RATIO"] = nt

    return results


# ─── Fear & Greed Index ───────────────────────────────────────────────────────

def fetch_fear_and_greed() -> dict:
    """CNN Fear & Greed Index（無料・APIキー不要）"""
    from datetime import datetime, timedelta
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    url = f"https://production.dataviz.cnn.io/index/fearandgreed/graphdata/{week_ago}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer":    "https://edition.cnn.com/markets/fear-and-greed",
        "Accept":     "application/json",
    }

    def _rating(score: float) -> tuple[str, str]:
        if score <= 24:   return "Extreme Fear", "極度の恐怖 😱"
        elif score <= 44: return "Fear",          "恐怖 😟"
        elif score <= 55: return "Neutral",       "中立 😐"
        elif score <= 74: return "Greed",         "強欲 🙂"
        else:             return "Extreme Greed", "極度の強欲 😄"

    try:
        resp = requests.get(url, headers=headers, timeout=12)
        resp.raise_for_status()
        fg    = resp.json().get("fear_and_greed", {})
        score = float(fg.get("score", 50))
        rating_en, rating_ja = _rating(score)
        result = {
            "score":        round(score, 1),
            "rating":       rating_en,
            "rating_ja":    rating_ja,
            "prev_close":   round(float(fg["previous_close"]), 1)  if fg.get("previous_close") else None,
            "prev_1_week":  round(float(fg["previous_1_week"]), 1) if fg.get("previous_1_week") else None,
            "prev_1_month": round(float(fg["previous_1_month"]), 1) if fg.get("previous_1_month") else None,
            "fetch_time":   get_jst_now().isoformat(),
            "source":       "CNN Fear & Greed Index",
        }
        logger.info(f"[OK] CNN Fear & Greed: {score:.1f} ({rating_ja})")
        return result
    except Exception as e:
        logger.error(f"[FAIL] CNN Fear & Greed 取得失敗: {e}")
        return {"score": None, "rating": "", "rating_ja": "取得失敗",
                "prev_close": None, "prev_1_week": None, "prev_1_month": None,
                "fetch_time": get_jst_now().isoformat(), "source": "CNN Fear & Greed Index"}


# ─── 保存・実行 ───────────────────────────────────────────────────────────────

def save_prices(prices: dict, fear_greed: dict) -> Path:
    dirs = get_dirs()
    today = get_today_str()
    payload = {"prices": prices, "fear_and_greed": fear_greed}
    json_path = dirs["data_raw"] / f"{today}_prices.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    df = pd.DataFrame(list(prices.values()))
    csv_path = dirs["data_processed"] / f"{today}_prices.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    logger.info(f"価格データ保存: {json_path}")
    return json_path


def run() -> tuple[dict, dict]:
    logger.info("=== 価格データ取得開始 ===")
    prices     = fetch_all_prices()
    fear_greed = fetch_fear_and_greed()
    save_prices(prices, fear_greed)
    ok   = sum(1 for v in prices.values() if v.get("latest") is not None)
    fail = sum(1 for v in prices.values() if v.get("latest") is None)
    logger.info(f"=== 取得完了: 成功{ok}件 / 失敗{fail}件 ===")
    return prices, fear_greed


if __name__ == "__main__":
    run()
