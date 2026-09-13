"""
価格ヒストリー取得モジュール（B案：HTMLレポートのChart.js用）
- Yahoo Finance chart API から主要指標の約1ヶ月分の日次終値を取得
- HTMLレポートに埋め込むインタラクティブチャート（Chart.js）のデータ源
- 失敗しても {} を返すだけ（レポート生成は止めない）
"""
import requests
from src.utils import setup_logger

logger = setup_logger("price_history")

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}

# Chart.js に載せる主要指標 (symbol, 表示名, カラー)
HISTORY_SYMBOLS = [
    ("^N225",    "日経225",  "#5b9bf3"),
    ("^GSPC",    "S&P500",   "#27c281"),
    ("USDJPY=X", "ドル円",   "#ff9f2e"),
    ("^VIX",     "VIX",      "#ef4d4d"),
]


def _fetch_one(symbol: str, rng: str = "1mo") -> dict | None:
    """1銘柄の日次終値を取得 → {"dates": [...], "closes": [...]}"""
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
           f"?interval=1d&range={rng}")
    try:
        r = requests.get(url, headers=_HEADERS, timeout=15)
        r.raise_for_status()
        result = r.json()["chart"]["result"][0]
        ts     = result.get("timestamp", []) or []
        quote  = result["indicators"]["quote"][0]["close"]
        dates, closes = [], []
        from datetime import datetime, timezone
        for t, c in zip(ts, quote):
            if c is None:
                continue
            d = datetime.fromtimestamp(t, tz=timezone.utc).strftime("%m/%d")
            dates.append(d)
            closes.append(round(c, 2))
        if len(closes) < 2:
            return None
        return {"dates": dates, "closes": closes}
    except Exception as e:
        logger.warning(f"ヒストリー取得失敗 [{symbol}]: {e}")
        return None


def fetch_history() -> dict:
    """主要指標のヒストリーをまとめて取得。

    返り値:
      {
        "labels": ["05/13", ...],          # 共通の日付軸（日経基準）
        "series": [
            {"name": "日経225", "color": "#..", "data": [..], "pct": [..]},
            ...
        ]
      }
    pct は初日を 100 とした基準化指数（複数資産を同じスケールで比較するため）。
    """
    raw = {}
    for sym, name, color in HISTORY_SYMBOLS:
        h = _fetch_one(sym)
        if h:
            raw[sym] = h

    if not raw:
        logger.warning("ヒストリーを1件も取得できませんでした")
        return {}

    # 日付軸は最も長いものを基準にする
    base_sym = max(raw, key=lambda s: len(raw[s]["dates"]))
    labels   = raw[base_sym]["dates"]
    n        = len(labels)

    series = []
    for sym, name, color in HISTORY_SYMBOLS:
        h = raw.get(sym)
        if not h:
            continue
        closes = h["closes"][-n:]            # 末尾を軸長に合わせる
        if not closes:
            continue
        base = closes[0] or 1
        pct  = [round((c / base - 1) * 100, 2) for c in closes]
        # ⚠️ 市場ごとに休場日が違うので、日数は揃わない（日経23日・ドル円25日など）。
        #    長さが違うまま描くと、短い系列が**先頭に詰められて数日ぶん左にずれる**。
        #    合わせたいのは末尾（最新日）なので、足りない分は先頭を None で埋める。
        pad = n - len(closes)
        if pad > 0:
            closes = [None] * pad + closes
            pct    = [None] * pad + pct
        series.append({
            "name":  name,
            "color": color,
            "data":  closes,
            "pct":   pct,
        })

    logger.info(f"✅ ヒストリー取得: {len(series)}系列 / {n}日分")
    return {"labels": labels, "series": series}


if __name__ == "__main__":
    import json
    print(json.dumps(fetch_history(), ensure_ascii=False, indent=2))
