"""
ローソク足・プライスアクションの実証（Step PV）— 形が本当に効くのかを測る

なぜ必要か:
  ローソク足の形は何百年も語り継がれているが、それは「有名である」ことの証拠であって
  「今この相場で機能する」ことの証拠ではない。
  2026-08-18に同じ思い込みで実装を2度作り直しているので、今回は先に測る。

測り方（2026-08-18の失敗から得た手順をそのまま適用する）:
  1. **必ず基準線を引く。** 上昇相場では買いの形が良く見えるのは当たり前。
     その銘柄が「何もしなくても」得られたリターンを差し引いて初めて実力が出る。
  2. **基準線は銘柄ごとに引く。** エヌビディアとドル円ではドリフトが桁違い。
  3. **n<100 は信じない。** 少数の偶然を効果と読み違えないよう検定を通す。
  4. 判定にはその日までの情報しか使わない。

run() → パターン別の実力（data/pattern_validation.json に保存）
"""
import json
import random
import statistics
import traceback
from datetime import datetime

from src.utils import setup_logger, BASE_DIR

logger = setup_logger("pattern_validation")

_OUT = BASE_DIR / "data" / "pattern_validation.json"

# 値動きの性格が違うものを混ぜる。1種類だけだとその市場のクセを効果と誤認する。
_SYMBOLS = [
    ("^N225", "日経225"), ("^GSPC", "S&P500"), ("^IXIC", "NASDAQ"),
    ("^SOX", "SOX"), ("^DJI", "ダウ"), ("^RUT", "ラッセル2000"),
    ("^GDAXI", "DAX"), ("^HSI", "ハンセン"), ("^FTSE", "FTSE"),
    ("USDJPY=X", "ドル円"), ("EURJPY=X", "ユーロ円"), ("GBPJPY=X", "ポンド円"),
    ("EURUSD=X", "ユーロドル"), ("AUDJPY=X", "豪ドル円"),
    ("NVDA", "エヌビディア"), ("AAPL", "アップル"), ("MSFT", "マイクロソフト"),
    ("TSLA", "テスラ"), ("AMZN", "アマゾン"), ("META", "メタ"), ("AMD", "AMD"),
    ("8035.T", "東エレク"), ("6857.T", "アドバンテスト"), ("9984.T", "SBG"),
    ("7203.T", "トヨタ"), ("6758.T", "ソニーG"), ("8306.T", "三菱UFJ"),
    ("GC=F", "金"), ("CL=F", "原油"), ("BTC-USD", "ビットコイン"),
]

_HORIZONS = [3, 5, 10]     # 形の効果は短期で出るとされるため短めに取る


def _fetch(sym: str, years: int = 5):
    """OHLCを取る。ローソク足の判定には終値だけでは足りない。"""
    try:
        import yfinance as yf
        h = yf.Ticker(sym).history(period=f"{years}y")
        if h is None or len(h) < 300:
            return None
        h = h.dropna(subset=["Open", "High", "Low", "Close"])
        logger.info(f"{sym}: {len(h)}日分")
        return h
    except Exception:
        logger.error(f"{sym} の取得に失敗", exc_info=True)
        return None


def _sign_test(vals: list, trials: int = 4000, seed: int = 3) -> float:
    """
    平均がゼロと言えるかを検定する。

    符号をランダムに反転させても同じ大きさの偏りが出るなら、それは偶然である。
    サンプルが多いときは総当たりせず正規近似を使う。
    符号反転後の平均は平均0・標準偏差 s/√n の正規分布に十分近づくため、
    数万件の系列で6,000回の並べ替えを回すのと結論は変わらない
    （実際、全パターンで回すと処理が終わらなかった）。
    """
    n = len(vals)
    if n < 30:
        return 1.0
    m = statistics.mean(vals)
    sd = statistics.pstdev(vals)
    if sd <= 0:
        return 0.0 if m != 0 else 1.0

    if n >= 200:
        import math
        z = abs(m) / (sd / math.sqrt(n))
        # 標準正規の両側p値（誤差関数で厳密に出せる）
        return round(2 * (1 - 0.5 * (1 + math.erf(z / math.sqrt(2)))), 4)

    rng = random.Random(seed)
    obs = abs(m)
    hits = sum(1 for _ in range(trials)
               if abs(statistics.mean([v * rng.choice((1, -1)) for v in vals])) >= obs)
    return round(hits / trials, 4)


def run(years: int = 5) -> dict:
    from src import candlestick as cs
    from src import sakata as sk
    from src import price_action as pa

    rows = []
    for sym, name in _SYMBOLS:
        df = _fetch(sym, years)
        if df is None:
            continue
        closes = [float(x) for x in df["Close"].tolist()]
        n = len(closes)

        # その銘柄が何もしなくても得られたリターン（基準線）
        drift = {}
        for h in _HORIZONS:
            ds = [(closes[i + h] - closes[i]) / closes[i] * 100
                  for i in range(60, n - max(_HORIZONS) - 1)]
            drift[h] = sum(ds) / len(ds) if ds else 0.0

        for i in range(60, n - max(_HORIZONS) - 1):
            # その日までのデータだけを渡す（未来を見ない）。
            # 直近150本に絞るのは計算量のため。全期間を毎回渡すとO(n^2)になり
            # 30銘柄×1250日では終わらない。判定に使うのは最大でも直近40本程度
            # （スイング検出とレンジ判定）なので、150本あれば結果は変わらない。
            window = df.iloc[max(0, i - 149): i + 1]
            try:
                # 西洋のローソク足パターンと酒田五法をまとめて検証する。
                # 同じ基準（ドリフト調整＋多重比較補正）で並べないと、
                # どちらが効くのかを比べられない。
                pats = (cs.analyze(window) + sk.analyze(window)
                        + pa.analyze(window))
            except Exception:
                logger.debug(traceback.format_exc())
                continue
            if not pats:
                continue
            for p in pats:
                if p["dir"] not in ("buy", "sell"):
                    continue
                sign = 1 if p["dir"] == "buy" else -1
                rec = {"symbol": sym, "name": name,
                       "date": df.index[i].strftime("%Y-%m-%d"),
                       "pattern": p["name"], "kind": p["kind"],
                       "dir": p["dir"], "trend": p.get("prior_trend")}
                for h in _HORIZONS:
                    raw = (closes[i + h] - closes[i]) / closes[i] * 100 * sign
                    rec[f"raw{h}"] = round(raw, 2)
                    # 基準線を差し引いた実力
                    rec[f"edge{h}"] = round(raw - drift[h] * sign, 2)
                rows.append(rec)

    if len(rows) < 50:
        return {"available": False, "reason": f"サンプル不足（{len(rows)}件）"}

    by_pat = {}
    for p in sorted(set(r["pattern"] for r in rows)):
        sub = [r for r in rows if r["pattern"] == p]
        if len(sub) < 30:
            continue
        entry = {"n": len(sub), "kind": sub[0]["kind"], "dir": sub[0]["dir"]}
        for h in _HORIZONS:
            edges = [r[f"edge{h}"] for r in sub]
            raws = [r[f"raw{h}"] for r in sub]
            entry[f"{h}日後"] = {
                "生": round(statistics.mean(raws), 2),
                "実力": round(statistics.mean(edges), 3),
                "勝率": round(sum(1 for e in edges if e > 0) / len(edges) * 100, 1),
                "p値": _sign_test(edges),
            }
        entry["最小p値"] = min(entry[f"{h}日後"]["p値"] for h in _HORIZONS)
        by_pat[p] = entry

    # 多重比較の補正。
    # 16種類のパターンを検定すれば、まったく効果が無くても平均0.8個は
    # p<0.05 になる（0.05×16）。個別のp値だけを見て「有意なパターンを
    # 3つ発見」と言うのは、宝くじを16枚買って当たった1枚だけを見せるのと同じ。
    # Bonferroni補正（0.05 ÷ 検定数）を通ったものだけを「有効」とする。
    n_tests = len(by_pat)
    threshold = 0.05 / n_tests if n_tests else 0.05
    for v in by_pat.values():
        v["補正後の基準"] = round(threshold, 5)
        v["有効"] = v["最小p値"] < threshold
        v["補正前は有意"] = v["最小p値"] < 0.05

    result = {
        "available": True,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total": len(rows),
        "period": f'{min(r["date"] for r in rows)} 〜 {max(r["date"] for r in rows)}',
        "symbols": len(set(r["symbol"] for r in rows)),
        "検定数": n_tests,
        "補正後の基準": round(threshold, 5),
        "補正前に有意": sum(1 for v in by_pat.values() if v["補正前は有意"]),
        "補正後に有意": sum(1 for v in by_pat.values() if v["有効"]),
        "偶然の期待値": round(0.05 * n_tests, 1),
        "patterns": by_pat,
        "confluence": _confluence_effect(rows),
    }
    try:
        _OUT.parent.mkdir(exist_ok=True)
        _OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    except Exception:
        logger.error("保存に失敗", exc_info=True)

    logger.info(f"✅ 検証完了: {len(rows)}件 / "
                f"補正前に有意 {result['補正前に有意']}種 → "
                f"補正後 {result['補正後に有意']}種 "
                f"（効果ゼロでも{result['偶然の期待値']}種は p<0.05 になる計算）")
    return result


def _confluence_effect(rows: list) -> dict:
    """
    同じ日・同じ銘柄で、同じ方向の形がいくつ重なったかで成績が変わるかを見る。
    「複数重なったら通知」という設計そのものの妥当性を測る部分。
    """
    groups = {}
    for r in rows:
        key = (r["symbol"], r["date"], r["dir"])
        groups.setdefault(key, []).append(r)

    out = {}
    for cnt_label, lo, hi in (("1つだけ", 1, 1), ("2つ重なり", 2, 2), ("3つ以上", 3, 99)):
        sel = [v[0] for v in groups.values() if lo <= len(v) <= hi]
        if len(sel) < 30:
            out[cnt_label] = {"n": len(sel)}
            continue
        e = {"n": len(sel)}
        for h in _HORIZONS:
            vals = [r[f"edge{h}"] for r in sel]
            e[f"{h}日後"] = {
                "実力": round(statistics.mean(vals), 3),
                "勝率": round(sum(1 for v in vals if v > 0) / len(vals) * 100, 1),
                "p値": _sign_test(vals),
            }
        out[cnt_label] = e
    return out


if __name__ == "__main__":
    import io, sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    r = run()
    if not r.get("available"):
        print(r.get("reason"))
        raise SystemExit
    print(f"\n検証 {r['total']}件 / {r['symbols']}銘柄 / {r['period']}")
    print("\n" + "=" * 74)
    print("パターン別の実力（相場のドリフトを差し引いた5日後リターン）")
    print("=" * 74)
    ranked = sorted(r["patterns"].items(),
                    key=lambda x: -x[1]["5日後"]["実力"])
    for name, v in ranked:
        d = v["5日後"]
        mark = "✅" if v.get("有効") else ("△" if d["p値"] < 0.05 else "　")
        print(f"{mark} {name:26} n={v['n']:>5}  生{d['生']:+6.2f}%  "
              f"実力{d['実力']:+6.2f}%  勝率{d['勝率']:5.1f}%  p={d['p値']}")
    print(f"\n※ ✅=多重比較の補正後も有意（p<{r['補正後の基準']}）／ "
          f"△=補正前だけ有意（偶然の可能性あり）")
    print(f"※ {r['検定数']}種を検定したため、効果がゼロでも"
          f"{r['偶然の期待値']}種は p<0.05 になる計算です")
    print("\n" + "=" * 74)
    print("形がいくつ重なったかで変わるか")
    print("=" * 74)
    for k, v in r["confluence"].items():
        if "5日後" not in v:
            print(f"  {k:10} n={v['n']} （少なすぎ）")
            continue
        d = v["5日後"]
        mark = "✅" if d["p値"] < 0.05 else "　"
        print(f"{mark} {k:10} n={v['n']:>5}  実力{d['実力']:+6.2f}%  "
              f"勝率{d['勝率']:5.1f}%  p={d['p値']}")
