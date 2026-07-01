"""
多重ソース照合（フェーズ2・精度土台 L1）
Yahoo Finance（主）＋ Stooq CSV（副）の 2 ソースで主要シンボルを照合する。

返り値: (verified_prices, summary)
  - verified_prices: prices の各エントリに以下フィールドを追記
      verified      : bool  両ソースが許容差内で一致
      single_source : bool  片方しか取得できなかった
      disagreement  : bool  2 ソース乖離（中央値で上書き済み）
      spread_pct    : float | None  ソース間乖離率 (%)
      sources       : dict  {"yahoo": val, "stooq": val}
  - summary: {"verified":N, "single_source":N, "disagreement":N, "unavailable":N}
"""
import statistics
from io import StringIO

import pandas as pd
import requests

from src.utils import setup_logger

logger = setup_logger("source_verify")

# Yahoo シンボル → Stooq シンボル（照合対象のみ）
_STOOQ_MAP = {
    "^N225":    "^nkx",
    "^GSPC":    "^spx",
    "^IXIC":    "^ndq",
    "USDJPY=X": "usdjpy",
    "^VIX":     "^vix",
    "GC=F":     "gc.f",
    "CL=F":     "cl.f",
    "^TNX":     "^tnx",
}

# 許容乖離率 (%) — この範囲内なら「一致」
_TOL = {
    "^N225":    0.5,
    "^GSPC":    0.5,
    "^IXIC":    0.5,
    "USDJPY=X": 0.3,
    "^VIX":     1.5,
    "GC=F":     0.8,
    "CL=F":     0.8,
    "^TNX":     2.0,
}

_HEADERS = {"User-Agent": "Mozilla/5.0"}


def _fetch_stooq(stooq_sym: str) -> float | None:
    url = f"https://stooq.com/q/d/l/?s={stooq_sym}&i=d"
    try:
        r = requests.get(url, timeout=12, headers=_HEADERS)
        r.raise_for_status()
        df = pd.read_csv(StringIO(r.text))
        if df.empty or "Close" not in df.columns:
            return None
        closes = df.sort_values("Date")["Close"].dropna()
        if closes.empty:
            return None
        return round(float(closes.iloc[-1]), 4)
    except Exception as e:
        logger.warning(f"Stooq取得失敗 [{stooq_sym}]: {e}")
        return None


def verify(prices: dict) -> tuple[dict, dict]:
    # 内側の dict も独立コピーして元データを汚染しない
    prices = {k: (dict(v) if isinstance(v, dict) else v) for k, v in prices.items()}
    summary = {"verified": 0, "single_source": 0, "disagreement": 0, "unavailable": 0}

    for sym, stooq_sym in _STOOQ_MAP.items():
        entry = prices.get(sym)
        if not isinstance(entry, dict):
            continue

        yahoo_val = entry.get("latest")
        stooq_val = _fetch_stooq(stooq_sym)

        sources = {"yahoo": yahoo_val, "stooq": stooq_val}
        available = [v for v in [yahoo_val, stooq_val] if v is not None]

        entry["sources"] = sources

        if len(available) == 0:
            entry.update({"verified": False, "single_source": False, "spread_pct": None})
            summary["unavailable"] += 1
            logger.warning(f"[{sym}] 全ソース取得失敗")

        elif len(available) == 1:
            entry.update({"verified": False, "single_source": True, "spread_pct": None})
            summary["single_source"] += 1
            logger.info(f"[{sym}] 単一ソース（未照合）: {available[0]}")

        else:
            # 2 ソース揃い → 照合
            median_val = statistics.median(available)
            spread_pct = abs(yahoo_val - stooq_val) / abs(median_val) * 100 if median_val else 0.0
            tol = _TOL.get(sym, 0.5)
            entry["spread_pct"] = round(spread_pct, 3)

            if spread_pct <= tol:
                entry.update({"verified": True, "single_source": False, "disagreement": False})
                summary["verified"] += 1
                logger.info(f"[{sym}] ✅ 2ソース一致 spread={spread_pct:.3f}%")
            else:
                entry.update({"verified": False, "single_source": False, "disagreement": True,
                              "latest": round(median_val, 4), "source": "中央値(ソース不一致)"})
                summary["disagreement"] += 1
                logger.warning(
                    f"[{sym}] ⚠️ ソース乖離 spread={spread_pct:.3f}% > {tol}% "
                    f"yahoo={yahoo_val} stooq={stooq_val} → 中央値={round(median_val,4)}"
                )

        prices[sym] = entry

    logger.info(
        f"多重ソース照合完了: 一致={summary['verified']} 単独={summary['single_source']} "
        f"乖離={summary['disagreement']} 取得不能={summary['unavailable']}"
    )
    return prices, summary


def run(prices: dict) -> tuple[dict, dict]:
    return verify(prices)


if __name__ == "__main__":
    import json
    test = {
        "^N225":    {"latest": 38000.0, "prev_close": 37900.0, "change_pct": 0.26, "name": "日経225"},
        "^GSPC":    {"latest": 5200.0,  "prev_close": 5180.0,  "change_pct": 0.39, "name": "S&P500"},
        "USDJPY=X": {"latest": 149.5,   "prev_close": 149.0,   "change_pct": 0.34, "name": "USD/JPY"},
        "^VIX":     {"latest": 18.2,    "prev_close": 17.9,    "change_pct": 1.68, "name": "VIX"},
    }
    result, summary = run(test)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    for sym in _STOOQ_MAP:
        if sym in result:
            d = result[sym]
            print(f"{sym}: verified={d.get('verified')} spread={d.get('spread_pct')}%")
