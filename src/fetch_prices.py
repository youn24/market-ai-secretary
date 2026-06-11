"""
価格データ取得モジュール
優先順位: yfinance → Stooq CSV フォールバック
Fear & Greed Index（CNN非公式エンドポイント）も取得
APIキー不要の公開データのみ使用
"""
import json
import time
from pathlib import Path

import pandas as pd
import requests
import yaml

from src.utils import BASE_DIR, get_jst_now, get_today_str, get_dirs, setup_logger

logger = setup_logger("fetch_prices")


def load_symbols() -> dict:
    with open(BASE_DIR / "config" / "symbols.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _fetch_yahoo_direct(symbol: str) -> pd.DataFrame | None:
    """Yahoo Finance chart API に直接リクエスト（yfinanceレート制限時のフォールバック）"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d"
    _HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Accept-Language": "ja,en;q=0.9",
    }
    try:
        r = requests.get(url, headers=_HEADERS, timeout=15)
        r.raise_for_status()
        result = r.json()["chart"]["result"][0]
        timestamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
        rows = [(pd.Timestamp(t, unit="s", tz="UTC"), c) for t, c in zip(timestamps, closes) if c is not None]
        if not rows:
            return None
        df = pd.DataFrame(rows, columns=["Date", "Close"])
        df = df.set_index("Date")
        return df
    except Exception as e:
        logger.warning(f"Yahoo直接API 失敗 [{symbol}]: {e}")
    return None


def _fetch_yfinance(symbol: str, period: str = "5d") -> pd.DataFrame | None:
    try:
        import yfinance as yf
        tk = yf.Ticker(symbol)
        df = tk.history(period=period, auto_adjust=True)
        if df is not None and not df.empty:
            return df
    except Exception as e:
        logger.warning(f"yfinance 失敗 [{symbol}]: {e}")
    # フォールバック: Yahoo直接API
    return _fetch_yahoo_direct(symbol)


def _fetch_stooq(stooq_symbol: str) -> pd.DataFrame | None:
    url = f"https://stooq.com/q/d/l/?s={stooq_symbol}&i=d"
    try:
        resp = requests.get(url, timeout=15,
                            headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        from io import StringIO
        df = pd.read_csv(StringIO(resp.text))
        if df.empty or "Close" not in df.columns:
            return None
        df["Date"] = pd.to_datetime(df["Date"])
        return df.sort_values("Date").tail(5)
    except Exception as e:
        logger.warning(f"Stooq 失敗 [{stooq_symbol}]: {e}")
    return None


def _extract_latest(df: pd.DataFrame) -> dict:
    try:
        closes = df["Close"].dropna()
        if len(closes) < 1:
            return {}
        latest = float(closes.iloc[-1])
        prev = float(closes.iloc[-2]) if len(closes) >= 2 else None
        change = round((latest - prev) / abs(prev) * 100, 2) if prev else None
        return {
            "latest": round(latest, 4),
            "prev_close": round(prev, 4) if prev else None,
            "change_pct": change,
        }
    except Exception as e:
        logger.warning(f"データ抽出失敗: {e}")
        return {}


def fetch_fear_and_greed() -> dict:
    """
    CNN Fear & Greed Index（株式市場版）を取得する
    APIキー不要。スコア 0〜100
    0-24: Extreme Fear / 25-44: Fear / 45-55: Neutral / 56-74: Greed / 75-100: Extreme Greed
    """
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
        data    = resp.json()
        fg      = data.get("fear_and_greed", {})
        score   = float(fg.get("score", 50))
        prev_1w = fg.get("previous_1_week")
        prev_1m = fg.get("previous_1_month")
        prev_cl = fg.get("previous_close")
        rating_en, rating_ja = _rating(score)
        result = {
            "score":         round(score, 1),
            "rating":        rating_en,
            "rating_ja":     rating_ja,
            "prev_close":    round(float(prev_cl), 1)  if prev_cl else None,
            "prev_1_week":   round(float(prev_1w), 1)  if prev_1w else None,
            "prev_1_month":  round(float(prev_1m), 1)  if prev_1m else None,
            "fetch_time":    get_jst_now().isoformat(),
            "source":        "CNN Fear & Greed Index（株式市場版）",
        }
        logger.info(f"[OK] CNN Fear & Greed: {score:.1f} ({rating_ja})")
        return result
    except Exception as e:
        logger.error(f"[FAIL] CNN Fear & Greed 取得失敗: {e}")
        return {
            "score": None, "rating": "", "rating_ja": "取得失敗",
            "prev_close": None, "prev_1_week": None, "prev_1_month": None,
            "fetch_time": get_jst_now().isoformat(),
            "source": "CNN Fear & Greed Index",
        }


def _fetch_single(sym: str, name: str, category: str,
                  fallback_map: dict) -> dict:
    fetch_time = get_jst_now().isoformat()
    record = {
        "symbol": sym, "name": name, "category": category,
        "fetch_time": fetch_time, "source": None,
        "latest": None, "prev_close": None,
        "change_pct": None, "error": None,
    }
    # yfinance
    df = _fetch_yfinance(sym)
    if df is not None and not df.empty:
        extracted = _extract_latest(df)
        if extracted:
            record.update(extracted)
            record["source"] = "yfinance"
            logger.info(f"[OK] {name}({sym}) = {record['latest']}")
            return record
    # Stooq フォールバック
    stooq_sym = fallback_map.get(sym)
    if stooq_sym:
        df2 = _fetch_stooq(stooq_sym)
        if df2 is not None and not df2.empty:
            extracted = _extract_latest(df2)
            if extracted:
                record.update(extracted)
                record["source"] = f"stooq({stooq_sym})"
                logger.info(f"[Stooq] {name}({sym}) = {record['latest']}")
                return record
    record["error"] = "全ソースで取得失敗"
    logger.error(f"[FAIL] {name}({sym}): 全ソースで取得失敗")
    return record


def fetch_all_prices() -> dict:
    cfg = load_symbols()
    fallback_map = cfg.get("stooq_fallback", {})
    all_categories = ["indices", "fear_indices", "forex", "rates",
                      "commodities", "crypto", "us_stocks", "jp_stocks"]
    results = {}
    for cat in all_categories:
        for item in cfg.get(cat, []):
            results[item["symbol"]] = _fetch_single(
                item["symbol"], item["name"],
                item.get("category", cat), fallback_map
            )
            time.sleep(0.4)
    return results


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
