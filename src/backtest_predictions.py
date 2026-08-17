"""
予測ロジックの過去検証（Step BT）— 実データで一気にサンプルを積む

なぜ必要か:
  予測の答え合わせは1日1件しか増えない。2026-08時点で検証済み26件しかなく、
  「強気の的中率27%」と言っても11件の話で、偶然か実力か区別できない。
  統計的に判断できる100件に達するには4か月以上かかる。

  そこで、過去の実データに「今と同じ判定ロジック」を当てて答え合わせを行い、
  数百件のサンプルを一度に得る。閾値をいくつにすべきかを、勘ではなく
  データで決められるようにするのが狙い。

正直な限界（結果を読むときは必ず考慮すること）:
  - シナリオ補正（Geminiが生成する3シナリオ）は過去を再現できないため除外する。
    実運用の判定とは完全には一致しない。
  - Fear&Greedの過去値は無料で遡れないため、VIXから近似する。
  - 重み(signal_weights.json)は過去データから較正されている。その較正に
    使った期間を検証に使うと成績が実力以上に良く出る（後知恵バイアス）。
    そのため較正期間より後だけを見る「期間外検証」も併せて出す。

run(years=2) → {"available", "samples":[...], "stats":{...}}
"""
import json
import statistics
import traceback
from datetime import datetime, timedelta

from src.utils import setup_logger, BASE_DIR

logger = setup_logger("backtest_predictions")

_OUT_FILE = BASE_DIR / "data" / "backtest_result.json"

# 実運用と同じ判定閾値（prediction_tracker._extract_direction と揃える）
BULL_TH = 9.0
BEAR_TH = -3.0
# 正解の定義（実運用と同じ）: 翌営業日の日経が±0.3%を超えたら上げ/下げ
FLAT_BAND = 0.3


def _load_weights() -> dict:
    """実運用が使っている較正済みの重みをそのまま読む。"""
    try:
        d = json.loads((BASE_DIR / "config" / "signal_weights.json").read_text(encoding="utf-8"))
        return {k: v["weight"] for k, v in d.get("weights", {}).items()
                if isinstance(v, dict) and v.get("weight") is not None}
    except Exception:
        logger.warning("重み設定を読めないため既定値を使います")
        return {"^GSPC": 0.985, "^IXIC": 0.988, "^SOX": 1.0, "^VIX": -0.8}


_CACHE = BASE_DIR / ".cache" / "hist.json"


def _fetch_history(symbols: list, years: int) -> dict:
    """
    各シンボルの日足終値を {シンボル: {日付: 終値}} で返す。
    まず Yahoo のチャートAPIを直接叩き、失敗したら yfinance に落とす。
    （実行環境によって yfinance が通らないことがあるため二段構え）
    """
    import json as _json
    import ssl
    import urllib.request
    from datetime import datetime as _dt, UTC

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    out = {}
    for sym in symbols:
        try:
            url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
                   f"?range={years}y&interval=1d")
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            d = _json.loads(urllib.request.urlopen(req, context=ctx, timeout=25).read())
            res = d["chart"]["result"][0]
            ts, cl = res["timestamp"], res["indicators"]["quote"][0]["close"]
            out[sym] = {_dt.fromtimestamp(t, UTC).strftime("%Y-%m-%d"): float(c)
                        for t, c in zip(ts, cl) if c}
            logger.info(f"{sym}: {len(out[sym])}日分")
        except Exception:
            logger.warning(f"直接取得に失敗、yfinanceを試します: {sym}")

    missing = [s for s in symbols if s not in out]
    if not missing:
        return out

    try:
        import yfinance as yf
        symbols = missing
        for sym in symbols:
            try:
                h = yf.Ticker(sym).history(period=f"{years}y")
                if h is None or h.empty:
                    logger.warning(f"取得できず: {sym}")
                    continue
                out[sym] = {d.strftime("%Y-%m-%d"): float(c)
                            for d, c in zip(h.index, h["Close"]) if c == c}
                logger.info(f"{sym}: {len(out[sym])}日分")
            except Exception:
                logger.warning(f"取得失敗: {sym}")
    except Exception:
        logger.error("yfinance が使えません")
        logger.debug(traceback.format_exc())
    return out


def _fg_from_vix(vix: float) -> float:
    """
    Fear&Greedの過去値は無料で遡れないため、VIXから近似する。
    VIXが低い＝強欲、高い＝恐怖という逆相関を線形で当てはめた粗い推定。
    実運用のF&Gとは別物なので、あくまで補正の方向を再現するためのもの。
    """
    if vix is None:
        return 50.0
    if vix <= 12:  return 80.0
    if vix <= 15:  return 65.0
    if vix <= 18:  return 55.0
    if vix <= 22:  return 45.0
    if vix <= 28:  return 32.0
    if vix <= 35:  return 20.0
    return 10.0


def _direction(score: float, fg: float) -> str:
    """prediction_tracker._extract_direction と同じ判定（シナリオ補正を除く）。"""
    adj = score
    if fg < 25:    adj -= 3.0
    elif fg < 35:  adj -= 1.5
    elif fg >= 75: adj += 3.0
    elif fg >= 65: adj += 1.5
    if adj >= BULL_TH:   return "bull"
    if adj <= BEAR_TH:   return "bear"
    return "neutral"


def run(years: int = 2, calib_end: str = None) -> dict:
    """
    過去 years 年分で予測ロジックを再現し、答え合わせまで行う。
    calib_end: 重みの較正に使われた期間の終わり。これ以降を「期間外検証」として別集計する。
    """
    weights = _load_weights()
    symbols = list(weights.keys()) + ["^N225"]
    hist = _fetch_history(sorted(set(symbols)), years)

    n225 = hist.get("^N225") or {}
    if len(n225) < 60:
        logger.error("日経のデータが不足しているため中止します")
        return {"available": False, "reason": "データ不足"}

    dates = sorted(n225.keys())
    samples = []

    for i in range(1, len(dates) - 1):
        d_prev, d_now, d_next = dates[i - 1], dates[i], dates[i + 1]

        # その日までに分かっている情報だけでスコアを作る（未来を見ない）
        score = 0.0
        used = 0
        for sym, w in weights.items():
            s = hist.get(sym) or {}
            a, b = s.get(d_prev), s.get(d_now)
            if a is None or b is None or a == 0:
                continue
            score += (b - a) / a * 100 * w
            used += 1
        if used < 2:
            continue

        vix_s = hist.get("^VIX") or {}
        fg = _fg_from_vix(vix_s.get(d_now))
        direction = _direction(score, fg)

        # 答え合わせ: 翌営業日の日経の変化率
        cur, nxt = n225.get(d_now), n225.get(d_next)
        if not cur or not nxt:
            continue
        move = (nxt - cur) / cur * 100
        actual = "bull" if move > FLAT_BAND else "bear" if move < -FLAT_BAND else "neutral"

        samples.append({
            "date": d_now, "direction": direction, "score": round(score, 2),
            "fg_est": fg, "actual": actual, "move": round(move, 2),
            "correct": direction == actual,
        })

    if not samples:
        return {"available": False, "reason": "サンプルを作れませんでした"}

    def _stats(rows: list) -> dict:
        if not rows:
            return {}
        out = {"n": len(rows),
               "accuracy": round(sum(1 for r in rows if r["correct"]) / len(rows) * 100, 1)}
        for d in ("bull", "bear", "neutral"):
            sub = [r for r in rows if r["direction"] == d]
            hit = sum(1 for r in sub if r["correct"])
            out[d] = {"n": len(sub),
                      "acc": round(hit / len(sub) * 100, 1) if sub else None,
                      "share": round(len(sub) / len(rows) * 100, 1)}
        # 実際の相場がどうだったか（予測の偏りを見るための基準）
        for d in ("bull", "bear", "neutral"):
            out[f"actual_{d}_share"] = round(
                sum(1 for r in rows if r["actual"] == d) / len(rows) * 100, 1)
        return out

    result = {
        "available": True,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "years": years,
        "thresholds": {"bull": BULL_TH, "bear": BEAR_TH, "flat_band": FLAT_BAND},
        "total": _stats(samples),
        "samples": samples,
    }
    if calib_end:
        out_of_sample = [s for s in samples if s["date"] > calib_end]
        result["out_of_sample"] = _stats(out_of_sample)
        result["calib_end"] = calib_end

    try:
        _OUT_FILE.parent.mkdir(exist_ok=True)
        _OUT_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=1),
                             encoding="utf-8")
    except Exception:
        logger.debug(traceback.format_exc())

    # 信頼度ランク表を作り直す。
    # ここで一緒に更新しないと、表だけ古いデータのまま残って
    # 「過去83%的中」と嘘の数字を出し続けることになる。
    try:
        from src.signal_confidence import calibrate
        calibrate()
    except Exception:
        logger.error("信頼度表の再較正に失敗しました", exc_info=True)

    t = result["total"]
    logger.info(f"✅ バックテスト完了: {t['n']}件 / 全体的中率 {t['accuracy']}%")
    return result


def sweep(years: int = 2) -> list:
    """
    閾値を振って的中率がどう変わるかを調べる。
    「今の bull 9.0 / bear -3.0 は妥当か」をデータで検証するために使う。
    """
    weights = _load_weights()
    symbols = list(weights.keys()) + ["^N225"]
    hist = _fetch_history(sorted(set(symbols)), years)
    n225 = hist.get("^N225") or {}
    dates = sorted(n225.keys())

    base = []
    for i in range(1, len(dates) - 1):
        d_prev, d_now, d_next = dates[i - 1], dates[i], dates[i + 1]
        score, used = 0.0, 0
        for sym, w in weights.items():
            s = hist.get(sym) or {}
            a, b = s.get(d_prev), s.get(d_now)
            if a is None or b is None or a == 0:
                continue
            score += (b - a) / a * 100 * w
            used += 1
        if used < 2:
            continue
        cur, nxt = n225.get(d_now), n225.get(d_next)
        if not cur or not nxt:
            continue
        move = (nxt - cur) / cur * 100
        fg = _fg_from_vix((hist.get("^VIX") or {}).get(d_now))
        adj = score
        if fg < 25:    adj -= 3.0
        elif fg < 35:  adj -= 1.5
        elif fg >= 75: adj += 3.0
        elif fg >= 65: adj += 1.5
        base.append((adj, move))

    results = []
    for bull_th in (3.0, 5.0, 7.0, 9.0, 11.0, 13.0):
        for bear_th in (-1.0, -2.0, -3.0, -5.0, -7.0):
            hit = tot = 0
            per = {"bull": [0, 0], "bear": [0, 0], "neutral": [0, 0]}
            for adj, move in base:
                d = "bull" if adj >= bull_th else "bear" if adj <= bear_th else "neutral"
                a = "bull" if move > FLAT_BAND else "bear" if move < -FLAT_BAND else "neutral"
                ok = d == a
                tot += 1; hit += ok
                per[d][0] += 1; per[d][1] += ok
            results.append({
                "bull_th": bull_th, "bear_th": bear_th,
                "acc": round(hit / tot * 100, 1) if tot else 0,
                "bull_n": per["bull"][0],
                "bull_acc": round(per["bull"][1] / per["bull"][0] * 100, 1) if per["bull"][0] else None,
                "bear_n": per["bear"][0],
                "bear_acc": round(per["bear"][1] / per["bear"][0] * 100, 1) if per["bear"][0] else None,
            })
    results.sort(key=lambda r: r["acc"], reverse=True)
    return results


if __name__ == "__main__":
    r = run(years=2, calib_end="2026-08-09")
    if r.get("available"):
        t = r["total"]
        print(f"サンプル {t['n']}件 / 的中率 {t['accuracy']}%")
        for d in ("bull", "bear", "neutral"):
            x = t[d]
            print(f"  {d:8}: {x['n']:4}件 的中{x['acc']}% (予測比率{x['share']}%)")
