"""
ドルコスト平均法 積立タイミング最適化モジュール
月のどの日に積立すると最もコストが低いかを分析する
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta


def _fetch_historical(symbol: str, years: int) -> pd.DataFrame:
    """過去N年の日次終値データを取得"""
    end = datetime.now()
    start = end - timedelta(days=years * 365)
    df = yf.download(symbol, start=start, end=end, auto_adjust=True, progress=False)
    # ⚠️ yfinanceは1銘柄でも列を2段（('Close','^N225')）で返すようになった。
    #    そのまま df["Close"] を取るとSeriesではなくDataFrameが返り、
    #    float() に渡した時点で落ちる（2026-09-09に実測。この関数は
    #    ずっと動いていなかった）。1段に潰してから使う。
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df[["Close"]].dropna()


def _calc_avg_cost_by_day(df: pd.DataFrame) -> dict:
    """日付(1〜28)別の「その月の平均に対する割高・割安度」を返す。

    ⚠️ 以前はここで**終値の平均そのもの**を日ごとに比べていた。
       10年で指数が2倍3倍になっていると、その値上がりが差の大半を占めるので、
       「何日が安いか」ではなく「たまたまどの日が期間の前半に多く落ちたか」を
       測ってしまう。これでは答えにならない。

       そこで各月ごとに「その月の平均株価」を1.0として正規化してから、
       日ごとに平均する。こうすると長期の値上がりが打ち消され、
       **月の中での安い日・高い日**だけが残る。
       1.0より小さいほど、その日に買うと平均より安く買えていたことになる。
    """
    df = df.copy()
    close = df["Close"]
    if hasattr(close, "columns"):        # 念のため（2段列が残っていた場合）
        close = close.iloc[:, 0]
    df = pd.DataFrame({"close": pd.to_numeric(close, errors="coerce")}).dropna()
    df["day"] = df.index.day
    df["ym"] = df.index.strftime("%Y-%m")

    monthly_mean = df.groupby("ym")["close"].transform("mean")
    df["rel"] = df["close"] / monthly_mean      # その月の平均＝1.0

    # 右肩上がりのぶんを引く。これをしないと必ず「月初が安い」が出る。
    df, _slope = _detrend(df)

    result = {}
    for day in range(1, 29):
        rel = df.loc[df["day"] == day, "rel_adj"]
        if len(rel) >= 12:               # 最低12ヶ月分
            result[day] = float(rel.mean())
    return result


def _rel_frame(df: pd.DataFrame):
    """終値を「その月の平均＝1.0」に正規化した表を返す。"""
    close = df["Close"]
    if hasattr(close, "columns"):
        close = close.iloc[:, 0]
    d = pd.DataFrame({"close": pd.to_numeric(close, errors="coerce")}).dropna()
    d["day"] = d.index.day
    d["ym"] = d.index.strftime("%Y-%m")
    d["rel"] = d["close"] / d.groupby("ym")["close"].transform("mean")
    return d


def _detrend(d):
    """右肩上がりのぶんを取り除く。

    ⚠️ ここが一番間違えやすい。相場は長い目で見れば上がっていくので、
       **月の後半の日ほど、その月の平均より自動的に高くなる**。
       この「上がっているだけ」の効果を除かずに日付を比べると、
       必ず「月初が安く、月末が高い」という結論が出る。
       それは日付のクセではなく、ただの値上がりである。

       実際 2026-09-09 に日経10年で測ると 2日=0.9928 / 27日=1.0078 となり、
       並べ替え検定は p=0.0115 で「有意」と答えた。だが日数差25日ぶんの
       値上がりだけでこの差の大半が説明できてしまう。

       そこで「日付が進むほど直線的に高くなる」ぶんを最小二乗で求めて引き、
       残ったものだけを日付のクセとして扱う。
    """
    import numpy as np
    x = d["day"].to_numpy(dtype=float)
    y = d["rel"].to_numpy(dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    d = d.copy()
    d["rel_adj"] = y - (slope * x + intercept) + 1.0
    return d, float(slope)


def _is_real_difference(d_adj, observed_gap: float, trials: int = 2000) -> tuple:
    """観測された差が「偶然でも出る程度」かどうかを確かめる。

    やり方は並べ替え検定。日付のラベルをシャッフルして同じ計算を何度もやり、
    「本物の差以上に大きな差」が偶然どれくらいの頻度で出るかを数える。
    それが5%以上なら、その差は偶然の範囲で、**特定の日を勧める根拠にならない**。

    28通りの中から一番大きい差を選んでいるので、比較先も毎回
    「シャッフル後の最大差」にしている。こうしないと
    「28回引いて一番良かったもの」を1回の当たりと数えることになる。

    なぜここまでするか:
      「毎月2日に買うのが一番安い」は、初心者にはとても具体的で
      信じやすい助言に見える。だが月内の日付効果はほとんどノイズで、
      28通りの中で一番を選べば**必ず何かが1位になる**。
      検定を通さずに出すのは、サイコロの目を予言と呼ぶのと同じになる。
    """
    import numpy as np
    rel = d_adj["rel_adj"].to_numpy()
    days = d_adj["day"].to_numpy()
    valid = [x for x in range(1, 29) if (days == x).sum() >= 12]
    if len(valid) < 5:
        return False, 1.0

    rng = np.random.default_rng(20260909)
    hits = 0
    for _ in range(trials):
        sh = rng.permutation(days)
        means = [rel[sh == x].mean() for x in valid]
        if (max(means) - min(means)) >= observed_gap:
            hits += 1
    pval = (hits + 1) / (trials + 1)
    return pval < 0.05, round(pval, 4)


def _build_html(
    symbol: str,
    years: int,
    best_day: int,
    worst_day: int,
    best_avg_cost_index: float,
    worst_avg_cost_index: float,
    saving_pct: float,
    day_ranking: list,
    insight: str,
) -> str:
    """分析結果のHTMLを生成（ダークテーマ）"""

    # コスト指数 → 色マッピング（低=緑、高=赤）
    def cost_to_color(cost_index: float) -> str:
        # 95〜105 の範囲でグラデーション
        ratio = (cost_index - 95.0) / 10.0  # 0.0(安い)〜1.0(高い)
        ratio = max(0.0, min(1.0, ratio))
        # 緑 (0,180,0) → 赤 (220,0,0)
        r = int(0 + ratio * 220)
        g = int(180 - ratio * 180)
        b = 0
        return f"rgb({r},{g},{b})"

    # day_rankingをdictに変換
    day_info = {item["day"]: item for item in day_ranking}

    # カレンダーセルを生成（1〜28）
    calendar_cells = ""
    for day in range(1, 29):
        if day in day_info:
            info = day_info[day]
            ci = info["cost_index"]
            color = cost_to_color(ci)
            rank = info["rank"]
            is_best = day == best_day
            is_worst = day == worst_day
            border = ""
            if is_best:
                border = "border: 2px solid #00ff88;"
            elif is_worst:
                border = "border: 2px solid #ff4444;"
            label = ""
            if is_best:
                label = '<div class="badge best">最安</div>'
            elif is_worst:
                label = '<div class="badge worst">最高</div>'
            calendar_cells += f"""
            <div class="cal-cell" style="background:{color};{border}">
                {label}
                <div class="cal-day">{day}日</div>
                <div class="cal-ci">{ci:.1f}</div>
            </div>"""
        else:
            calendar_cells += f"""
            <div class="cal-cell no-data">
                <div class="cal-day">{day}日</div>
                <div class="cal-ci">-</div>
            </div>"""

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>積立タイミング最適化 - {symbol}</title>
<style>
  body {{
    background: #0d1117;
    color: #e6edf3;
    font-family: 'Segoe UI', 'Hiragino Kaku Gothic Pro', sans-serif;
    margin: 0;
    padding: 20px;
    max-width: 900px;
    margin: 0 auto;
    padding: 20px;
  }}
  h1 {{
    font-size: 1.4rem;
    color: #58a6ff;
    margin-bottom: 4px;
  }}
  .subtitle {{
    color: #8b949e;
    font-size: 0.85rem;
    margin-bottom: 20px;
  }}
  .banner {{
    background: linear-gradient(135deg, #0d2137 0%, #112240 100%);
    border: 1px solid #00ff88;
    border-radius: 12px;
    padding: 20px 24px;
    margin-bottom: 24px;
    text-align: center;
  }}
  .banner-main {{
    font-size: 1.6rem;
    font-weight: bold;
    color: #00ff88;
    margin-bottom: 8px;
  }}
  .banner-sub {{
    color: #8b949e;
    font-size: 0.9rem;
  }}
  .stats-row {{
    display: flex;
    gap: 16px;
    margin-bottom: 24px;
    flex-wrap: wrap;
  }}
  .stat-card {{
    flex: 1;
    min-width: 160px;
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 10px;
    padding: 16px;
    text-align: center;
  }}
  .stat-label {{
    font-size: 0.75rem;
    color: #8b949e;
    margin-bottom: 8px;
  }}
  .stat-value {{
    font-size: 1.4rem;
    font-weight: bold;
  }}
  .stat-value.good {{ color: #00ff88; }}
  .stat-value.bad {{ color: #ff4444; }}
  .stat-value.saving {{ color: #ffd700; }}
  .section-title {{
    font-size: 0.9rem;
    color: #8b949e;
    margin-bottom: 12px;
    padding-bottom: 6px;
    border-bottom: 1px solid #30363d;
  }}
  .calendar {{
    display: grid;
    grid-template-columns: repeat(7, 1fr);
    gap: 4px;
    margin-bottom: 24px;
  }}
  .cal-cell {{
    border-radius: 6px;
    padding: 8px 4px;
    text-align: center;
    position: relative;
    min-height: 56px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
  }}
  .cal-cell.no-data {{
    background: #1c2128;
    opacity: 0.5;
  }}
  .cal-day {{
    font-size: 0.75rem;
    font-weight: bold;
    color: #fff;
  }}
  .cal-ci {{
    font-size: 0.65rem;
    color: rgba(255,255,255,0.8);
    margin-top: 2px;
  }}
  .badge {{
    font-size: 0.55rem;
    padding: 1px 4px;
    border-radius: 3px;
    margin-bottom: 2px;
    font-weight: bold;
  }}
  .badge.best {{ background: #00ff88; color: #000; }}
  .badge.worst {{ background: #ff4444; color: #fff; }}
  .insight-box {{
    background: #161b22;
    border: 1px solid #30363d;
    border-left: 3px solid #58a6ff;
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 20px;
    font-size: 0.9rem;
    line-height: 1.6;
    color: #c9d1d9;
  }}
  .legend {{
    display: flex;
    align-items: center;
    gap: 16px;
    font-size: 0.75rem;
    color: #8b949e;
    margin-bottom: 20px;
  }}
  .legend-item {{
    display: flex;
    align-items: center;
    gap: 6px;
  }}
  .legend-color {{
    width: 16px;
    height: 16px;
    border-radius: 3px;
  }}
  .footer {{
    color: #484f58;
    font-size: 0.75rem;
    text-align: center;
    margin-top: 20px;
    padding-top: 16px;
    border-top: 1px solid #21262d;
  }}
</style>
</head>
<body>
  <h1>📅 積立タイミング最適化</h1>
  <div class="subtitle">{symbol} ／ 過去{years}年のデータ分析</div>

  <div class="banner">
    <div class="banner-main">毎月 {best_day}日 に積立するのが最適！</div>
    <div class="banner-sub">コスト指数: {best_avg_cost_index:.1f}（全日平均=100）</div>
  </div>

  <div class="stats-row">
    <div class="stat-card">
      <div class="stat-label">最安日</div>
      <div class="stat-value good">{best_day}日</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">最高値日</div>
      <div class="stat-value bad">{worst_day}日</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">最悪日比 コスト節約</div>
      <div class="stat-value saving">{saving_pct:.1f}%</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">最安日コスト指数</div>
      <div class="stat-value good">{best_avg_cost_index:.1f}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">最高値日コスト指数</div>
      <div class="stat-value bad">{worst_avg_cost_index:.1f}</div>
    </div>
  </div>

  <div class="insight-box">
    💡 {insight}
  </div>

  <div class="section-title">月次コストカレンダー（コスト指数で色分け）</div>
  <div class="legend">
    <div class="legend-item">
      <div class="legend-color" style="background:rgb(0,180,0)"></div> 安い（良い日）
    </div>
    <div class="legend-item">
      <div class="legend-color" style="background:rgb(110,90,0)"></div> 平均
    </div>
    <div class="legend-item">
      <div class="legend-color" style="background:rgb(220,0,0)"></div> 高い（避けたい日）
    </div>
  </div>

  <div class="calendar">
    {calendar_cells}
  </div>

  <div class="footer">
    ※ コスト指数：全日平均を100としたときの相対的な株価水準。100未満が平均より安い。<br>
    ※ 過去のデータに基づく分析であり、将来の投資成果を保証するものではありません。
  </div>
</body>
</html>"""
    return html


def analyze_dca_timing(symbol: str = "^N225", years: int = 10) -> dict:
    """
    月のどの日に積立するのが最もコストが低いかを分析する

    Parameters
    ----------
    symbol : str
        対応: "^N225"（日経平均）, "^GSPC"（S&P500）, "2559.T"（S&P500連動ETF）
    years : int
        分析期間（年）

    Returns
    -------
    dict
        available, symbol, best_day, worst_day, best_avg_cost_index,
        worst_avg_cost_index, saving_pct, day_ranking, insight, html
    """
    error_result = {
        "available": False,
        "symbol": symbol,
        "best_day": None,
        "worst_day": None,
        "best_avg_cost_index": None,
        "worst_avg_cost_index": None,
        "saving_pct": None,
        "significant": False,
        "p_value": None,
        "day_ranking": [],
        "insight": "データを取得できませんでした。",
        "html": "<p>データを取得できませんでした。</p>",
    }

    try:
        df = _fetch_historical(symbol, years)
    except Exception as e:
        error_result["insight"] = f"データ取得エラー: {e}"
        return error_result

    if df is None or df.empty:
        return error_result

    # 日別平均コスト計算
    try:
        costs = _calc_avg_cost_by_day(df)
    except Exception as e:
        error_result["insight"] = f"コスト計算エラー: {e}"
        return error_result

    if len(costs) < 5:
        error_result["insight"] = "データ不足のため分析できませんでした。"
        return error_result

    # コスト指数計算（全日平均=100）
    mean_cost = sum(costs.values()) / len(costs)
    cost_index = {day: cost / mean_cost * 100 for day, cost in costs.items()}

    # 最安日・最高値日
    best_day = min(cost_index, key=lambda d: cost_index[d])
    worst_day = max(cost_index, key=lambda d: cost_index[d])
    best_avg_cost_index = cost_index[best_day]
    worst_avg_cost_index = cost_index[worst_day]

    # コスト節約率（最悪日比）
    saving_pct = (worst_avg_cost_index - best_avg_cost_index) / worst_avg_cost_index * 100

    # 日別ランキング生成（コスト低い順）
    sorted_days = sorted(cost_index.items(), key=lambda x: x[1])
    day_ranking = [
        {"day": day, "cost_index": round(ci, 2), "rank": rank + 1}
        for rank, (day, ci) in enumerate(sorted_days)
    ]

    # ⚠️ ここで「毎月◯日がお得」と言い切ってはいけない。
    #    28通りの中から一番良かった日を選べば、中身がただのノイズでも
    #    必ず何かが1位になる。初心者にとって「毎月23日に買え」は
    #    とても具体的で信じやすい助言に見えるだけに、根拠の確認は必須。
    #
    #    2026-09-09の実測（日経10年・S&P500 10年）:
    #      ドリフト調整前は p=0.0115 で「有意」に見えたが、
    #      右肩上がりのぶんを引くと p=0.996 / 0.986 と、完全に偶然の範囲だった。
    #      つまり「月初が安い」の正体は日付のクセではなく、ただの値上がり。
    #
    #    差があると言えるときだけ日付を出し、言えないときは
    #    **「どの日でも同じ」と正直に言う**。それ自体が役に立つ結論である。
    significant, pval = False, 1.0
    try:
        d_rel = _rel_frame(df)
        d_adj, _slope = _detrend(d_rel)
        gap = (max(costs.values()) - min(costs.values()))
        significant, pval = _is_real_difference(d_adj, gap)
    except Exception:
        pass

    if significant:
        insight = (
            f"毎月{best_day}日の積立が最も有利でした。"
            f"{worst_day}日と比べると平均{saving_pct:.1f}%安く買えています"
            f"（過去{years}年・相場全体の値上がりぶんを除いたうえで、"
            f"偶然では説明しにくい差 p={pval}）"
        )
    else:
        insight = (
            f"過去{years}年を調べた結果、"
            f"**どの日に積み立てても差はありませんでした**（p={pval}）。"
            f"見かけ上は{best_day}日が最安ですが、相場全体の値上がりぶんを除くと"
            f"差は偶然の範囲に収まります。"
            f"積立日は「給料日の直後」など、**続けやすい日**で選んで大丈夫です。"
        )
    _res_significant, _res_pval = significant, pval

    # HTML生成
    html = _build_html(
        symbol=symbol,
        years=years,
        best_day=best_day,
        worst_day=worst_day,
        best_avg_cost_index=round(best_avg_cost_index, 2),
        worst_avg_cost_index=round(worst_avg_cost_index, 2),
        saving_pct=round(saving_pct, 2),
        day_ranking=day_ranking,
        insight=insight,
    )

    return {
        "available": True,
        "symbol": symbol,
        "best_day": best_day,
        "worst_day": worst_day,
        "best_avg_cost_index": round(best_avg_cost_index, 2),
        "worst_avg_cost_index": round(worst_avg_cost_index, 2),
        "saving_pct": round(saving_pct, 2),
        "significant": _res_significant,
        "p_value": _res_pval,
        "day_ranking": day_ranking,
        "insight": insight,
        "html": html,
    }


if __name__ == "__main__":
    for sym in ["^N225", "^GSPC", "2559.T"]:
        print(f"\n=== {sym} ===")
        result = analyze_dca_timing(sym, years=10)
        if result["available"]:
            print(f"最安日: {result['best_day']}日 (コスト指数: {result['best_avg_cost_index']:.2f})")
            print(f"最高値日: {result['worst_day']}日 (コスト指数: {result['worst_avg_cost_index']:.2f})")
            print(f"節約率: {result['saving_pct']:.2f}%")
            print(f"insight: {result['insight']}")
        else:
            print(f"エラー: {result['insight']}")
