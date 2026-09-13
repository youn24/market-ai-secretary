"""
シグナル重みの自動較正モジュール（精度向上①）
- 「どの指標が実際に翌日の日経平均を当てたか」を過去データで計算し、
  リスクスコアの重みを“勘”から“実績”に置き換える
- 各指標の当日リターン と 日経の翌営業日リターン の相関を測定
- 結果を config/signal_weights.json に保存（indicators.py が読み込む）
- 取得・計算は Yahoo chart API のみ（APIキー不要）。失敗しても既存の既定重みで動く
"""
import json
import requests
from pathlib import Path
from datetime import datetime, timezone

from src.utils import setup_logger

logger = setup_logger("calibrate_weights")

BASE_DIR = Path(__file__).parent.parent
OUT_PATH = BASE_DIR / "config" / "signal_weights.json"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# 較正対象（翌日の日経を予測しうる指標）
PREDICTORS = {
    "^GSPC":    "S&P500",
    "^IXIC":    "NASDAQ",
    "^SOX":     "半導体SOX",
    "^VIX":     "VIX",
    "GC=F":     "金",
    "USDJPY=X": "ドル円",
    "^N225":    "日経(前日)",
}
TARGET = "^N225"


def _fetch_series(symbol: str, rng: str = "2y") -> dict:
    """日次終値を {YYYY-MM-DD: close} で返す。"""
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
           f"?interval=1d&range={rng}")
    try:
        r = requests.get(url, headers=_HEADERS, timeout=20)
        r.raise_for_status()
        res = r.json()["chart"]["result"][0]
        ts  = res.get("timestamp", []) or []
        cl  = res["indicators"]["quote"][0]["close"]
        out = {}
        for t, c in zip(ts, cl):
            if c is None:
                continue
            d = datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d")
            out[d] = c
        return out
    except Exception as e:
        logger.warning(f"履歴取得失敗 [{symbol}]: {e}")
        return {}


def _returns(series: dict) -> dict:
    """{date: close} → {date: 日次リターン%}"""
    dates = sorted(series)
    rets = {}
    for i in range(1, len(dates)):
        prev, cur = series[dates[i-1]], series[dates[i]]
        if prev:
            rets[dates[i]] = (cur / prev - 1) * 100
    return rets


def _pearson(xs: list, ys: list) -> float:
    n = len(xs)
    if n < 30:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    sxy = sum((x-mx)*(y-my) for x, y in zip(xs, ys))
    sxx = sum((x-mx)**2 for x in xs) ** 0.5
    syy = sum((y-my)**2 for y in ys) ** 0.5
    if sxx == 0 or syy == 0:
        return 0.0
    return sxy / (sxx * syy)


def calibrate() -> dict:
    """較正を実行し、重みdictを返す。"""
    nikkei = _fetch_series(TARGET)
    if len(nikkei) < 60:
        logger.warning("日経の履歴が不足。較正を中止")
        return {}

    nk_ret  = _returns(nikkei)
    nk_dates = sorted(nk_ret)                       # 日経の取引日（リターンあり）
    # 翌営業日リターン: nk_dates[i] の予測対象は nk_dates[i] 自身のリターンで、
    # 予測材料は「その前営業日」の各指標リターン
    prev_of = {nk_dates[i]: nk_dates[i-1] for i in range(1, len(nk_dates))}

    raw = {}
    for sym, name in PREDICTORS.items():
        series = nikkei if sym == TARGET else _fetch_series(sym)
        pr = _returns(series)
        xs, ys = [], []
        for d in nk_dates[1:]:
            pday = prev_of.get(d)
            if pday is None:
                continue
            # 指標は「前営業日まで」に出たリターンを使う（リーク防止）
            pv = pr.get(pday)
            tv = nk_ret.get(d)
            if pv is not None and tv is not None:
                xs.append(pv)
                ys.append(tv)
        corr = round(_pearson(xs, ys), 3)
        raw[sym] = {"name": name, "corr": corr, "n": len(xs)}
        logger.info(f"[{name}] 翌日日経との相関 r={corr:+.3f} (n={len(xs)})")

    # 正規化: 最大|corr|=1.0 になるよう揃える（スコアの規模を従来と同程度に保つ）
    max_abs = max((abs(v["corr"]) for v in raw.values()), default=0) or 1.0
    weights = {}
    for sym, v in raw.items():
        weights[sym] = {
            "name":   v["name"],
            "corr":   v["corr"],
            "weight": round(v["corr"] / max_abs, 3),   # 符号付き（VIXは自然に負）
            "n":      v["n"],
        }

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target": TARGET,
        "method": "各指標の前営業日リターン と 日経翌日リターン のPearson相関を正規化",
        "weights": weights,
    }
    return payload


def run() -> dict:
    logger.info("=== シグナル重み較正開始 ===")
    payload = calibrate()
    if not payload:
        return {"available": False}
    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"✅ 重み較正完了: {OUT_PATH}")
    return {"available": True, **payload}


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
