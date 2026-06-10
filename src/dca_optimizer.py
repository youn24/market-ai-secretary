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
    return df[["Close"]].dropna()


def _calc_avg_cost_by_day(df: pd.DataFrame) -> dict:
    """日付(1〜28)別の平均終値を計算"""
    df = df.copy()
    df["day"] = df.index.day
    result = {}
    for day in range(1, 29):
        prices = df[df["day"] == day]["Close"]
        if len(prices) >= 12:  # 最低12ヶ月分のデータが必要
            result[day] = float(prices.mean())
    return result


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

    # insight文章
    insight = (
        f"毎月{best_day}日の積立が最もお得です。"
        f"{worst_day}日と比べると平均{saving_pct:.1f}%コストを節約できます"
        f"（過去{years}年のデータより）"
    )

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
