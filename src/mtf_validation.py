"""
マルチタイムフレーム判定の実証（Step MTFV）— 効くという理論を過去データで確かめる

なぜ必要か:
  2026-08-18に「大きな時間軸に逆らうシグナルは信頼度を下げる」という仕組みを入れた。
  これはトレードの教科書に載っている考え方だが、この相場・この銘柄で
  本当に成立するかは別問題である。検証せずに使い続けると、
  「もっともらしいが効かないフィルタ」で有効なシグナルを捨てることになる。

  そこで、過去に発生したシグナルを全部拾い、その時点の時間軸の状態と
  その後の値動きを突き合わせて、フィルタの有無で成績が変わるかを測る。

未来を見ないための約束:
  ある日tの判定には、t日までの終値しか使わない。
  移動平均も時間軸判定も、その日までのデータだけで計算する。
  週足はt日までの日足から合成する（週足データを直接使うと、
  週の途中でその週の確定値を見てしまい未来を覗くことになる）。

run() → 検証結果（data/mtf_validation.json にも保存）
"""
import json
import ssl
import statistics
import urllib.request
from datetime import datetime, UTC

from src.utils import setup_logger, BASE_DIR

logger = setup_logger("mtf_validation")

_OUT = BASE_DIR / "data" / "mtf_validation.json"

# 検証対象。サンプル数を稼ぐため、実運用の監視対象より広く取る。
# 少数の銘柄だけだと、その銘柄固有のクセを「フィルタの効果」と誤認する。
# 値動きの性格が違うもの（指数・為替・個別株・商品）を混ぜて一般性を確かめる。
_SYMBOLS = [
    ("^N225", "日経225"), ("^GSPC", "S&P500"), ("^IXIC", "NASDAQ"),
    ("^SOX", "SOX半導体"), ("^DJI", "ダウ"), ("^RUT", "ラッセル2000"),
    ("^FTSE", "FTSE100"), ("^GDAXI", "DAX"), ("^HSI", "ハンセン"),
    ("USDJPY=X", "ドル円"), ("EURJPY=X", "ユーロ円"), ("GBPJPY=X", "ポンド円"),
    ("EURUSD=X", "ユーロドル"), ("AUDJPY=X", "豪ドル円"),
    ("NVDA", "エヌビディア"), ("AAPL", "アップル"), ("MSFT", "マイクロソフト"),
    ("TSLA", "テスラ"), ("AMZN", "アマゾン"), ("META", "メタ"),
    ("GC=F", "金"), ("CL=F", "原油"), ("BTC-USD", "ビットコイン"),
]

# 何日後の値動きで成否を測るか。
# 1日だけだとノイズに埋もれ、長すぎると別の材料が混ざる。複数見て傾向を確かめる。
_HORIZONS = [5, 10, 20]

# 時間軸判定のパラメータ（tech_signals._tf_trend と揃える）
_FLAT_PCT = 0.3


def _fetch(sym: str, years: int = 5) -> dict | None:
    """日足の終値を {日付: 終値} で取る。"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/"
               f"{sym.replace('^', '%5E')}?range={years}y&interval=1d")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        d = json.loads(urllib.request.urlopen(req, context=ctx, timeout=30).read())
        res = d["chart"]["result"][0]
        ts, cl = res["timestamp"], res["indicators"]["quote"][0]["close"]
        out = [(datetime.fromtimestamp(t, UTC).strftime("%Y-%m-%d"), float(c))
               for t, c in zip(ts, cl) if c]
        logger.info(f"{sym}: {len(out)}日分")
        return out
    except Exception:
        logger.error(f"{sym} の取得に失敗しました", exc_info=True)
        return None


def _ma(vals: list, n: int, i: int) -> float | None:
    """i日目時点の単純移動平均（i日目を含む、それ以前だけを使う）。"""
    if i + 1 < n:
        return None
    return sum(vals[i - n + 1: i + 1]) / n


def _trend_at(vals: list, i: int, n: int = 25, look: int = 5) -> str:
    """
    i日目時点の地合い。tech_signals._tf_trend と同じ考え方
    （移動平均に対する位置と、その線の傾きの両方が揃ったときだけ方向あり）。
    """
    m = _ma(vals, n, i)
    if m is None or not m:
        return "flat"
    gap = (vals[i] - m) / m * 100
    if abs(gap) < _FLAT_PCT:
        return "flat"
    prev = _ma(vals, n, i - look)
    if prev is None:
        return "flat"
    slope = m - prev
    if gap > 0 and slope > 0:
        return "up"
    if gap < 0 and slope < 0:
        return "down"
    return "flat"


def _weekly_from_daily(vals: list, i: int) -> list:
    """
    i日目までの日足から週足の終値列を作る。

    週足データを直接取ると、週の途中でもその週の確定終値が入ってしまい、
    未来を覗いた判定になる。日足から5本ごとに区切って合成すれば、
    その日までに実際に見えていた情報だけで週足を再現できる。
    """
    seg = vals[: i + 1]
    weekly = [seg[j] for j in range(len(seg) - 1, -1, -5)][::-1]
    return weekly


def _signals_at(vals: list, i: int, ema12: list = None, ema26: list = None) -> list:
    """
    i日目に発生したシグナルを返す。
    tech_signals と同じ教科書的シグナルのうち、日足で判定できるものを使う。
    """
    out = []
    # ゴールデンクロス / デッドクロス（MA25 × MA75）
    a_now, b_now = _ma(vals, 25, i), _ma(vals, 75, i)
    a_pre, b_pre = _ma(vals, 25, i - 1), _ma(vals, 75, i - 1)
    if None not in (a_now, b_now, a_pre, b_pre):
        if a_pre <= b_pre and a_now > b_now:
            out.append(("golden_cross", "buy"))
        elif a_pre >= b_pre and a_now < b_now:
            out.append(("dead_cross", "sell"))

    # 200日線の上抜け / 下抜け
    m_now, m_pre = _ma(vals, 200, i), _ma(vals, 200, i - 1)
    if None not in (m_now, m_pre):
        if vals[i - 1] <= m_pre and vals[i] > m_now:
            out.append(("ma200_up", "buy"))
        elif vals[i - 1] >= m_pre and vals[i] < m_now:
            out.append(("ma200_down", "sell"))

    # MACDクロス（勢いの転換）。発生頻度が高くサンプルを稼げる
    e12n = ema12[i] if ema12 else None
    e26n = ema26[i] if ema26 else None
    e12p = ema12[i - 1] if ema12 else None
    e26p = ema26[i - 1] if ema26 else None
    if None not in (e12n, e26n, e12p, e26p):
        if (e12p - e26p) <= 0 < (e12n - e26n):
            out.append(("macd_gc", "buy"))
        elif (e12p - e26p) >= 0 > (e12n - e26n):
            out.append(("macd_dc", "sell"))

    # 52週高値・安値の更新（需給の節目）
    if i >= 260:
        window = vals[i - 259: i]
        if vals[i] > max(window):
            out.append(("high52w", "buy"))
        elif vals[i] < min(window):
            out.append(("low52w", "sell"))
    return out


def _ema_series(vals: list, span: int) -> list:
    """
    EMAを最初に一度だけ全期間ぶん計算しておく。

    各日ごとに先頭から計算し直すと計算量がO(n^2)になり、
    23銘柄×1250日では現実的な時間で終わらない。
    EMAは前日値から逐次更新できるので、一度舐めれば十分。
    値は「その日までの情報だけ」で決まるため、未来を覗く心配はない。
    """
    k = 2 / (span + 1)
    out, e = [], vals[0]
    for idx, v in enumerate(vals):
        e = v if idx == 0 else v * k + e * (1 - k)
        out.append(e if idx + 1 >= span * 2 else None)
    return out


def _mtf_at(vals: list, i: int) -> dict:
    """
    i日目時点の時間軸の状態。
    実運用は週足・日足・4時間足だが、過去5年の4時間足は取れないため
    ここでは週足・日足の2本で検証する。
    短期足を除いた分だけ効果は控えめに出るはずで、結果は保守的な見積もりになる。
    """
    daily = _trend_at(vals, i)
    wk = _weekly_from_daily(vals, i)
    weekly = _trend_at(wk, len(wk) - 1) if len(wk) >= 31 else "flat"

    # 実運用と同じく週足を重く見る（週足3・日足2）
    score = {"up": 0, "down": 0}
    for t, w in ((weekly, 3), (daily, 2)):
        if t in score:
            score[t] += w
    if score["up"] == score["down"]:
        direction = "flat"
    else:
        direction = "up" if score["up"] > score["down"] else "down"
    return {"weekly": weekly, "daily": daily, "direction": direction,
            "full": weekly == daily and weekly != "flat"}


def run(years: int = 5) -> dict:
    rows = []
    for sym, name in _SYMBOLS:
        series = _fetch(sym, years)
        if not series or len(series) < 300:
            continue
        dates = [d for d, _ in series]
        vals = [v for _, v in series]

        ema12, ema26 = _ema_series(vals, 12), _ema_series(vals, 26)
        for i in range(220, len(vals) - max(_HORIZONS) - 1):
            sigs = _signals_at(vals, i, ema12, ema26)
            if not sigs:
                continue
            mtf = _mtf_at(vals, i)
            for kind, direction in sigs:
                want = "up" if direction == "buy" else "down"
                if mtf["direction"] == "flat":
                    align = "中立"
                elif mtf["direction"] == want:
                    align = "一致" if not mtf["full"] else "完全一致"
                else:
                    align = "逆行"

                fwd = {}
                for h in _HORIZONS:
                    nxt = vals[i + h]
                    r = (nxt - vals[i]) / vals[i] * 100
                    # 売りシグナルは下がったら成功なので符号を反転して揃える
                    fwd[h] = r if direction == "buy" else -r
                rows.append({
                    "symbol": sym, "name": name, "date": dates[i],
                    "signal": kind, "direction": direction,
                    "align": align, "weekly": mtf["weekly"], "daily": mtf["daily"],
                    **{f"fwd{h}": round(fwd[h], 2) for h in _HORIZONS},
                })

    if len(rows) < 30:
        return {"available": False, "reason": f"サンプル不足（{len(rows)}件）"}

    def agg(subset: list) -> dict:
        if not subset:
            return {}
        out = {"n": len(subset)}
        for h in _HORIZONS:
            vals_h = [r[f"fwd{h}"] for r in subset]
            wins = sum(1 for v in vals_h if v > 0)
            out[f"{h}日後"] = {
                "勝率": round(wins / len(vals_h) * 100, 1),
                "平均": round(statistics.mean(vals_h), 2),
                "中央値": round(statistics.median(vals_h), 2),
                # 外したときの平均。当てることより「大きく外さない」が重要なため
                "負け時平均": round(statistics.mean([v for v in vals_h if v <= 0]), 2)
                if any(v <= 0 for v in vals_h) else None,
            }
        return out

    result = {
        "available": True,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "years": years,
        "total": len(rows),
        "period": f'{min(r["date"] for r in rows)} 〜 {max(r["date"] for r in rows)}',
        "by_align": {k: agg([r for r in rows if r["align"] == k])
                     for k in ("完全一致", "一致", "中立", "逆行")},
        "by_signal": {},
        "overall": agg(rows),
        "samples": rows,
    }
    for kind in ("golden_cross", "dead_cross", "ma200_up", "ma200_down",
                 "macd_gc", "macd_dc", "high52w", "low52w"):
        sub = [r for r in rows if r["signal"] == kind]
        if len(sub) >= 20:
            result["by_signal"][kind] = {
                "全体": agg(sub),
                "一致時": agg([r for r in sub if r["align"] in ("一致", "完全一致")]),
                "逆行時": agg([r for r in sub if r["align"] == "逆行"]),
            }

    result["significance"] = _significance(rows)
    result["findings"] = _findings(result)
    try:
        _OUT.parent.mkdir(exist_ok=True)
        _OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        logger.error("保存に失敗しました", exc_info=True)

    logger.info(f"✅ 検証完了: {len(rows)}件")
    return result


def _permutation_test(a: list, b: list, trials: int = 5000) -> float:
    """
    2群の平均差が偶然で説明できるかを調べる（並べ替え検定）。

    なぜ必要か:
      最初に6銘柄で試したとき「完全一致は逆行より+1.87%良い」と出たが、
      23銘柄に増やすと差はほぼ消えた。少ないサンプルでは、偶然の偏りが
      効果に見えてしまう。数字の大小だけで判断すると、実在しない効果を
      根拠にコードを変えることになる。

      ここでは全データのラベルをランダムに貼り替え直し、
      「たまたま今回くらいの差が出る確率」を数える。
      その確率(p値)が小さいほど、偶然では説明しにくい＝本物に近い。

    返り値: p値（0.05未満なら偶然とは考えにくい、が慣例）
    """
    import random
    if len(a) < 30 or len(b) < 30:
        return 1.0
    observed = abs(statistics.mean(a) - statistics.mean(b))
    pool = a + b
    n = len(a)
    rng = random.Random(42)          # 実行のたびに結論が変わらないよう固定
    hits = 0
    for _ in range(trials):
        rng.shuffle(pool)
        if abs(statistics.mean(pool[:n]) - statistics.mean(pool[n:])) >= observed:
            hits += 1
    return round(hits / trials, 4)


def _significance(rows: list) -> dict:
    """完全一致 vs それ以外を、期間ごとに検定する。"""
    out = {}
    for h in _HORIZONS:
        full = [r[f"fwd{h}"] for r in rows if r["align"] == "完全一致"]
        rest = [r[f"fwd{h}"] for r in rows if r["align"] != "完全一致"]
        against = [r[f"fwd{h}"] for r in rows if r["align"] == "逆行"]
        out[f"{h}日後"] = {
            "完全一致vsその他": {
                "差": round(statistics.mean(full) - statistics.mean(rest), 3)
                if full and rest else None,
                "p値": _permutation_test(full, rest),
                "n": [len(full), len(rest)],
            },
            "完全一致vs逆行": {
                "差": round(statistics.mean(full) - statistics.mean(against), 3)
                if full and against else None,
                "p値": _permutation_test(full, against),
                "n": [len(full), len(against)],
            },
        }
    return out


def _findings(r: dict) -> list:
    """数字を読んで、フィルタが効いているかどうかを日本語で結論づける。"""
    out = []
    ba = r["by_align"]
    for h in _HORIZONS:
        agree = ba.get("完全一致", {}).get(f"{h}日後")
        against = ba.get("逆行", {}).get(f"{h}日後")
        if not agree or not against:
            continue
        d_win = agree["勝率"] - against["勝率"]
        d_avg = agree["平均"] - against["平均"]
        out.append(
            f"{h}日後: 完全一致 勝率{agree['勝率']}%・平均{agree['平均']:+.2f}% "
            f"vs 逆行 勝率{against['勝率']}%・平均{against['平均']:+.2f}% "
            f"（差 {d_win:+.1f}pt / {d_avg:+.2f}%）")

    # 総合判定。複数の期間で一貫して差が出ているかを見る
    diffs = []
    for h in _HORIZONS:
        a = ba.get("完全一致", {}).get(f"{h}日後")
        b = ba.get("逆行", {}).get(f"{h}日後")
        if a and b:
            diffs.append(a["平均"] - b["平均"])
    if diffs:
        if all(d > 0 for d in diffs):
            out.append("✅ すべての期間で「時間軸が一致した方が成績が良い」。"
                       "このフィルタは機能していると判断できる。")
        elif all(d < 0 for d in diffs):
            out.append("❌ すべての期間で逆の結果。フィルタが有効なシグナルを"
                       "捨てている可能性があり、設定を見直すべき。")
        else:
            out.append("⚠️ 期間によって結果が異なり、効果は限定的。"
                       "強い根拠とは言えないため、格下げ幅は控えめが妥当。")
    return out


if __name__ == "__main__":
    import io, sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    r = run()
    if not r.get("available"):
        print(r.get("reason"))
        raise SystemExit
    print(f"検証期間 {r['period']} / シグナル {r['total']}件\n")
    for k, v in r["by_align"].items():
        if not v:
            continue
        print(f"■ {k} (n={v['n']})")
        for h in _HORIZONS:
            d = v[f"{h}日後"]
            print(f"   {h:>2}日後: 勝率{d['勝率']:>5}%  平均{d['平均']:+6.2f}%  "
                  f"負け時{d['負け時平均']}%")
    print("\n■ 所見")
    for f in r["findings"]:
        print(" ・" + f)
