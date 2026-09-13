"""
予測の「クセ」分析（Step FA）— どういう時に外すのかを条件別に洗い出す

なぜ必要か:
  「全体の的中率41%」だけ見ても使い道がない。知りたいのは
  「今日のこのサインは信用していいのか」であって、平均値ではない。
  そこでバックテスト470件を条件で切り分け、
    ・信号が強い日と弱い日で成績は変わるのか
    ・荒れ相場(高VIX)と凪相場で変わるのか
    ・外したとき、どれくらい逆に動かれるのか
  を出す。的中率が同じでも「外したときの痛みが小さい」なら実用になる。

読むときの注意:
  的中率より「期待値(expectancy)」を重視すること。
  上げ予想の日の翌日平均が +0.2% なら、的中率が40%でも方向としては機能している。
  逆に的中率が高くても期待値がマイナスなら、当たる時に小さく外す時に大きい。

run() → dict（data/failure_analysis.json にも保存）
"""
import json
import statistics
from collections import defaultdict
from datetime import datetime

from src.utils import setup_logger, BASE_DIR

logger = setup_logger("failure_analysis")

_SRC = BASE_DIR / "data" / "backtest_result.json"
_OUT = BASE_DIR / "data" / "failure_analysis.json"

# VIX近似値(fg_est)から相場環境をラベル付けする。
# backtest側は VIX が低いほど fg_est を高くしているので、低いfg = 荒れ相場。
_REGIME = [
    (0, 25, "パニック(VIX高)"),
    (25, 40, "警戒"),
    (40, 60, "平常"),
    (60, 101, "楽観(VIX低)"),
]


def _regime(fg: float) -> str:
    for lo, hi, name in _REGIME:
        if lo <= fg < hi:
            return name
    return "平常"


def _bucket_score(score: float) -> str:
    """信号の強さ。絶対値で階層化する（上げ下げどちらでも強さは強さ）。"""
    a = abs(score)
    if a < 3:   return "① ほぼ無風 (|score|<3)"
    if a < 6:   return "② 弱い (3-6)"
    if a < 10:  return "③ 中程度 (6-10)"
    if a < 15:  return "④ 強い (10-15)"
    return "⑤ 極端 (15以上)"


def _agg(rows: list) -> dict:
    """1グループ分の成績。的中率だけでなく期待値と最悪値まで出す。"""
    if not rows:
        return {}
    n = len(rows)
    hit = sum(1 for r in rows if r["correct"])
    moves = [r["move"] for r in rows]

    # 期待値: 予測方向に賭けた場合の翌日リターン（下げ予想は符号反転）
    edge = []
    for r in rows:
        if r["direction"] == "bull":
            edge.append(r["move"])
        elif r["direction"] == "bear":
            edge.append(-r["move"])
        # neutral は賭けないので期待値の計算に入れない

    wrong = [r for r in rows if not r["correct"] and r["direction"] != "neutral"]
    adverse = []
    for r in wrong:
        m = r["move"] if r["direction"] == "bull" else -r["move"]
        if m < 0:
            adverse.append(m)

    out = {
        "n": n,
        "acc": round(hit / n * 100, 1),
        "avg_move": round(statistics.mean(moves), 2),
    }
    if edge:
        out["expectancy"] = round(statistics.mean(edge), 3)
        out["bet_n"] = len(edge)
        out["win_rate"] = round(sum(1 for e in edge if e > 0) / len(edge) * 100, 1)
    if adverse:
        out["avg_adverse"] = round(statistics.mean(adverse), 2)
        out["worst"] = round(min(adverse), 2)
    return out


def run() -> dict:
    try:
        bt = json.loads(_SRC.read_text(encoding="utf-8"))
    except Exception:
        logger.error("バックテスト結果がありません。先に backtest_predictions.run() を実行してください")
        return {"available": False, "reason": "backtest_result.json が無い"}

    samples = bt.get("samples") or []
    if len(samples) < 50:
        return {"available": False, "reason": f"サンプル不足 ({len(samples)}件)"}

    for s in samples:
        s["_dt"] = datetime.strptime(s["date"], "%Y-%m-%d")

    result = {
        "available": True,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "n": len(samples),
        "period": f'{samples[0]["date"]} 〜 {samples[-1]["date"]}',
    }

    # --- 1. 全体（比較の基準線） -------------------------------------------
    result["overall"] = _agg(samples)

    # 「中立を除き、相場も動いた日」だけに絞った実質的中率。
    # 予測も実際も動いた日だけを見るので、方向を当てられているかの純粋な指標になる。
    committed = [s for s in samples
                 if s["direction"] != "neutral" and s["actual"] != "neutral"]
    if committed:
        hit = sum(1 for s in committed if s["correct"])
        result["directional"] = {
            "n": len(committed),
            "acc": round(hit / len(committed) * 100, 1),
            "note": "予測が上げ/下げを出し、かつ相場も±0.3%超動いた日だけの方向的中率",
        }

    # --- 2. 信号の強さ別（一番知りたいところ） ------------------------------
    by_strength = defaultdict(list)
    for s in samples:
        by_strength[_bucket_score(s["score"])].append(s)
    result["by_strength"] = {k: _agg(v) for k, v in sorted(by_strength.items())}

    # --- 3. 相場環境別 -------------------------------------------------------
    by_regime = defaultdict(list)
    for s in samples:
        by_regime[_regime(s["fg_est"])].append(s)
    result["by_regime"] = {k: _agg(v) for k, v in by_regime.items()}

    # --- 4. 予測方向 × 環境（どの組み合わせが鬼門か） ------------------------
    cross = defaultdict(list)
    for s in samples:
        if s["direction"] != "neutral":
            cross[f'{s["direction"]}×{_regime(s["fg_est"])}'].append(s)
    result["by_direction_regime"] = {k: _agg(v) for k, v in sorted(cross.items())
                                     if len(v) >= 8}

    # --- 5. 曜日別（週明け・週末のクセ） -------------------------------------
    wd = ["月", "火", "水", "木", "金", "土", "日"]
    by_wd = defaultdict(list)
    for s in samples:
        by_wd[wd[s["_dt"].weekday()]].append(s)
    result["by_weekday"] = {k: _agg(v) for k, v in by_wd.items() if len(v) >= 10}

    # --- 6. 相場の値幅別（そもそも当てようがない日を切り分ける） -------------
    by_size = defaultdict(list)
    for s in samples:
        a = abs(s["move"])
        key = ("A 静か (±0.3%以内)" if a <= 0.3 else
               "B 普通 (0.3-1%)" if a <= 1.0 else
               "C 大きい (1-2%)" if a <= 2.0 else "D 急変 (2%超)")
        by_size[key].append(s)
    result["by_move_size"] = {k: _agg(v) for k, v in sorted(by_size.items())}

    # --- 7. 大外し日トップ10（何が起きた日なのか調べる手がかり） -------------
    scored = []
    for s in samples:
        if s["direction"] == "neutral":
            continue
        m = s["move"] if s["direction"] == "bull" else -s["move"]
        if m < 0:
            scored.append({"date": s["date"], "direction": s["direction"],
                           "score": s["score"], "move": s["move"],
                           "damage": round(m, 2), "regime": _regime(s["fg_est"])})
    scored.sort(key=lambda x: x["damage"])
    result["worst_misses"] = scored[:10]

    # --- 8. 連続外しの分布（連敗がどこまで続くか） ---------------------------
    streak = cur = 0
    streaks = []
    for s in samples:
        if s["direction"] == "neutral":
            continue
        if s["correct"]:
            if cur:
                streaks.append(cur)
            cur = 0
        else:
            cur += 1
            streak = max(streak, cur)
    if cur:
        streaks.append(cur)
    result["losing_streak"] = {
        "max": streak,
        "avg": round(statistics.mean(streaks), 1) if streaks else 0,
        "count": len(streaks),
    }

    # --- 9. 寄り付きギャップの分解（期待値の正体を見破る） ------------------
    result["gap_decomposition"] = _gap_decomposition(samples)

    # --- 10. 読み取り結果を日本語の所見にする -------------------------------
    result["findings"] = _findings(result)

    for s in samples:
        s.pop("_dt", None)

    try:
        _OUT.parent.mkdir(exist_ok=True)
        _OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        logger.error("保存に失敗しました", exc_info=True)

    logger.info(f"✅ クセ分析完了: {result['n']}件 / 所見{len(result['findings'])}件")
    return result


def _fetch_n225_ohlc(years: int = 3) -> dict:
    """日経の始値・終値を取る。ギャップ分解に必要。"""
    import json as _json
    import ssl
    import urllib.request
    from datetime import datetime as _dt, UTC

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/%5EN225"
               f"?range={years}y&interval=1d")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        d = _json.loads(urllib.request.urlopen(req, context=ctx, timeout=25).read())
        res = d["chart"]["result"][0]
        ts = res["timestamp"]
        q = res["indicators"]["quote"][0]
        out = {}
        for t, o, c in zip(ts, q["open"], q["close"]):
            if o and c:
                out[_dt.fromtimestamp(t, UTC).strftime("%Y-%m-%d")] = {"open": float(o),
                                                                      "close": float(c)}
        return out
    except Exception:
        logger.warning("日経のOHLCを取得できませんでした（ギャップ分解はスキップ）")
        return {}


def _gap_decomposition(samples: list) -> dict:
    """
    翌日の値動きを「寄り付きギャップ」と「日中の値動き」に分解する。

    なぜこれが要るか:
      米国市場が引けた後にサインが出る以上、翌朝の寄り付きには既に
      その内容が織り込まれている。終値→終値の期待値が良く見えても、
      その大半がギャップなら「気づいた時にはもう動いた後」であり、
      実際には取れない数字ということになる。
      分けて見ないと、実力を過大評価したまま運用してしまう。
    """
    ohlc = _fetch_n225_ohlc()
    if not ohlc:
        return {"available": False}

    dates = sorted(ohlc.keys())
    idx = {d: i for i, d in enumerate(dates)}

    gap_edge, intraday_edge, total_edge = [], [], []
    for s in samples:
        if s["direction"] == "neutral":
            continue
        i = idx.get(s["date"])
        if i is None or i + 1 >= len(dates):
            continue
        cur = ohlc[dates[i]]["close"]
        nxt = ohlc[dates[i + 1]]
        if not cur:
            continue
        gap = (nxt["open"] - cur) / cur * 100
        intra = (nxt["close"] - nxt["open"]) / nxt["open"] * 100
        sign = 1 if s["direction"] == "bull" else -1
        gap_edge.append(gap * sign)
        intraday_edge.append(intra * sign)
        total_edge.append((nxt["close"] - cur) / cur * 100 * sign)

    if len(total_edge) < 30:
        return {"available": False}

    g, it, t = (statistics.mean(gap_edge), statistics.mean(intraday_edge),
                statistics.mean(total_edge))
    return {
        "available": True,
        "n": len(total_edge),
        "total": round(t, 3),
        "gap": round(g, 3),
        "intraday": round(it, 3),
        "gap_share": round(g / t * 100, 1) if t else None,
        "intraday_win_rate": round(
            sum(1 for x in intraday_edge if x > 0) / len(intraday_edge) * 100, 1),
        "note": "gap=寄り付きで既に動いた分（サインを見た時点では取れない） / "
                "intraday=寄り付き後に取れる分",
    }


def _findings(r: dict) -> list:
    """
    数字を眺めるのは人間には辛いので、意味のある差だけを文章にする。
    差が小さいものを並べても判断材料にならないので、しきい値を設けて絞る。
    """
    out = []
    base = r["overall"]["acc"]

    # 信号の強さは「全体的中率」で比べると誤解を招く。
    # 弱い日はほぼ中立判定になり、中立は相場が凪いだ日しか正解にならないため、
    # 構造的に低く出るだけで実力差とは限らないからだ。
    # 上げ/下げを明言した日だけの勝率(win_rate)で比べれば、純粋な差が見える。
    st = r.get("by_strength") or {}
    graded = [(k, v) for k, v in sorted(st.items())
              if v.get("bet_n", 0) >= 20 and v.get("win_rate") is not None]
    if len(graded) >= 2:
        line = " → ".join(f"{k.split()[0]}{v['win_rate']}%(n={v['bet_n']})"
                          for k, v in graded)
        spread = graded[-1][1]["win_rate"] - graded[0][1]["win_rate"]
        if spread >= 10:
            out.append(f"信号が強いほど当たる（明言した日の勝率）: {line} "
                       f"— 強弱で {spread:.0f}ポイント差。弱いサインは見送る根拠になる")

    rg = r.get("by_regime") or {}
    for k, v in rg.items():
        if v.get("n", 0) >= 30 and abs(v["acc"] - base) >= 8:
            direction = "得意" if v["acc"] > base else "苦手"
            out.append(f"{k} は{direction}: {v['acc']}% (全体 {base}%, n={v['n']})")

    # 値幅別は「結果が出たあと」の分類なので、事前の判断材料には使えない。
    # 的中率が低く見える理由の説明としてだけ扱う。
    ms = r.get("by_move_size") or {}
    for k, v in ms.items():
        if v.get("n", 0) >= 25 and v["acc"] <= base - 12:
            out.append(f"{k} の日の的中率は {v['acc']}% "
                       f"（※これは結果が出た後の分類。事前に選べる条件ではない）")

    dr = r.get("by_direction_regime") or {}
    for k, v in sorted(dr.items(), key=lambda x: x[1].get("expectancy", 0)):
        e = v.get("expectancy")
        if e is not None and v["n"] >= 10 and e <= -0.15:
            out.append(f"{k} は期待値マイナス ({e:+.2f}%/日, n={v['n']}) — 鬼門の組み合わせ")
    for k, v in sorted(dr.items(), key=lambda x: -x[1].get("expectancy", 0)):
        e = v.get("expectancy")
        if e is not None and v["n"] >= 10 and e >= 0.15:
            out.append(f"{k} は期待値プラス ({e:+.2f}%/日, n={v['n']}) — 信頼できる組み合わせ")
            break

    ls = r.get("losing_streak") or {}
    if ls.get("max", 0) >= 4:
        out.append(f"連続で外すことがある: 最長 {ls['max']}連敗 — "
                   f"1回の結果で判断せず、連敗も想定内として扱うこと")

    gd = r.get("gap_decomposition") or {}
    if gd.get("available") and gd.get("gap_share") is not None:
        if gd["gap_share"] >= 70:
            out.append(
                f"⚠ 期待値の {gd['gap_share']}% は寄り付きギャップ "
                f"(全体{gd['total']:+.2f}% = ギャップ{gd['gap']:+.2f}% + "
                f"日中{gd['intraday']:+.2f}%) — サインを見た時点では既に織り込み済み。"
                f"数字ほど「取れる」わけではない")
        else:
            out.append(
                f"寄り付き後にも {gd['intraday']:+.2f}%/日 の傾向が残る "
                f"(勝率{gd['intraday_win_rate']}%, n={gd['n']}) — ギャップだけの現象ではない")

    d = r.get("directional") or {}
    if d:
        out.append(f"方向を明言した日の実質的中率は {d['acc']}% (n={d['n']}) — "
                   f"全体の {base}% は「動かない日」を含むため低く見えているだけ")

    return out


def format_report(r: dict) -> str:
    """人が読む形に整える（Telegram/レポート用）。"""
    if not r.get("available"):
        return ""
    L = [f"📊 予測のクセ分析 ({r['period']} / {r['n']}件)", ""]
    o = r["overall"]
    L.append(f"全体的中率 {o['acc']}%")
    if r.get("directional"):
        L.append(f"方向明言時の実質的中率 {r['directional']['acc']}% (n={r['directional']['n']})")
    L.append("")
    L.append("■ 信号の強さ別")
    for k, v in r.get("by_strength", {}).items():
        e = f" 期待値{v['expectancy']:+.2f}%" if v.get("expectancy") is not None else ""
        L.append(f"  {k}: {v['acc']}% (n={v['n']}){e}")
    L.append("")
    L.append("■ 相場環境別")
    for k, v in r.get("by_regime", {}).items():
        L.append(f"  {k}: {v['acc']}% (n={v['n']})")
    if r.get("findings"):
        L.append("")
        L.append("■ 所見")
        for f in r["findings"]:
            L.append(f"  ・{f}")
    return "\n".join(L)


if __name__ == "__main__":
    print(format_report(run()))
