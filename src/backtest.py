"""
L4e: バックテストモジュール
過去20年のデータで「この戦略が通じたか」を自動検証
"""
import ssl
import json
import urllib.request
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
try:
    import japanize_matplotlib  # noqa: F401
except ImportError:
    pass
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE


def _fetch(symbol: str, period: str = "20y") -> pd.DataFrame:
    url = (
        f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?interval=1d&range={period}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        resp = urllib.request.urlopen(req, context=_ctx, timeout=15)
        data = json.loads(resp.read())
        result = data["chart"]["result"][0]
        timestamps = result["timestamp"]
        q = result["indicators"]["quote"][0]
        dates = [datetime.fromtimestamp(t).strftime("%Y-%m-%d") for t in timestamps]
        df = pd.DataFrame({
            "Close": q.get("close", []),
            "High":  q.get("high", []),
            "Low":   q.get("low", []),
        }, index=pd.to_datetime(dates)).dropna()
        return df.sort_index()
    except Exception as e:
        logger.warning(f"fetch失敗 {symbol}: {e}")
        return pd.DataFrame()


def _run_strategy(df: pd.DataFrame, name: str, signal_fn) -> dict:
    """汎用バックテストエンジン"""
    df = df.copy()
    df["signal"] = signal_fn(df)
    df["ret"] = df["Close"].pct_change()
    df["strategy_ret"] = df["signal"].shift(1) * df["ret"]
    df["bnh_cum"] = (1 + df["ret"]).cumprod()
    df["strat_cum"] = (1 + df["strategy_ret"]).cumprod()

    years = (df.index[-1] - df.index[0]).days / 365.25
    bnh_cagr = (df["bnh_cum"].iloc[-1] ** (1 / years) - 1) * 100
    strat_cagr = (df["strat_cum"].iloc[-1] ** (1 / years) - 1) * 100

    # 最大ドローダウン
    roll_max = df["strat_cum"].cummax()
    dd = (df["strat_cum"] - roll_max) / roll_max
    max_dd = dd.min() * 100

    bnh_roll_max = df["bnh_cum"].cummax()
    bnh_dd = (df["bnh_cum"] - bnh_roll_max) / bnh_roll_max
    bnh_max_dd = bnh_dd.min() * 100

    # 勝率
    wins = (df["strategy_ret"] > 0).sum()
    total = (df["strategy_ret"] != 0).sum()
    win_rate = wins / total * 100 if total > 0 else 0

    return {
        "name": name,
        "cagr": round(strat_cagr, 2),
        "bnh_cagr": round(bnh_cagr, 2),
        "max_drawdown": round(max_dd, 2),
        "bnh_max_drawdown": round(bnh_max_dd, 2),
        "win_rate": round(win_rate, 1),
        "alpha": round(strat_cagr - bnh_cagr, 2),
        "years": round(years, 1),
        "cum_series": df["strat_cum"],
        "bnh_series": df["bnh_cum"],
    }


def strategy_ma200(df: pd.DataFrame) -> pd.Series:
    """200日移動平均を上回ったら買い（ゴールデンクロス型）"""
    ma = df["Close"].rolling(200).mean()
    return (df["Close"] > ma).astype(int)


def strategy_vix_timing(df_sp: pd.DataFrame, df_vix: pd.DataFrame) -> pd.Series:
    """VIX < 20のときだけ買い（恐怖指数タイミング）"""
    vix_aligned = df_vix["Close"].reindex(df_sp.index, method="ffill")
    return (vix_aligned < 20).astype(int)


def strategy_buy_the_dip(df: pd.DataFrame) -> pd.Series:
    """10%以上の下落後に買い（押し目買い）"""
    ma = df["Close"].rolling(252).max()
    drawdown = (df["Close"] - ma) / ma
    return (drawdown < -0.10).astype(int)


def make_backtest_chart(results: list) -> str | None:
    """バックテスト結果の資産曲線チャートを生成"""
    try:
        dirs = Path("reports/charts")
        dirs.mkdir(parents=True, exist_ok=True)
        out_path = str(dirs / "backtest.png")

        colors = ["#00d4ff", "#ff6b35", "#00ff88", "#ffcc00"]
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), facecolor="#07111e")

        # 上段: 資産曲線
        ax1.set_facecolor("#0d1f33")
        for i, res in enumerate(results):
            if "cum_series" in res:
                ax1.plot(res["cum_series"].index, res["cum_series"].values,
                         color=colors[i % len(colors)], linewidth=1.5,
                         label=f"{res['name']} (CAGR:{res['cagr']:.1f}%)")
        if results and "bnh_series" in results[0]:
            ax1.plot(results[0]["bnh_series"].index, results[0]["bnh_series"].values,
                     color="#888", linewidth=1, linestyle="--", label="Buy&Hold")
        ax1.set_title("バックテスト: 戦略比較（S&P500 20年間）", color="white", fontsize=12)
        ax1.legend(fontsize=8, facecolor="#0d1f33", labelcolor="white")
        ax1.tick_params(colors="white")
        ax1.set_ylabel("資産倍率", color="white")
        for spine in ax1.spines.values():
            spine.set_color("#334455")
        ax1.grid(color="#1a2a3a", linewidth=0.5)

        # 下段: 成績比較バーチャート
        ax2.set_facecolor("#0d1f33")
        names = [r["name"] for r in results] + ["Buy&Hold"]
        cagrs = [r["cagr"] for r in results] + [results[0]["bnh_cagr"] if results else 0]
        bar_colors = colors[:len(results)] + ["#888"]
        bars = ax2.bar(names, cagrs, color=bar_colors, alpha=0.8)
        ax2.set_title("年率リターン比較 (CAGR)", color="white", fontsize=10)
        ax2.tick_params(colors="white")
        ax2.set_ylabel("年率(%)", color="white")
        for spine in ax2.spines.values():
            spine.set_color("#334455")
        for bar, val in zip(bars, cagrs):
            ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1,
                     f"{val:.1f}%", ha="center", va="bottom", color="white", fontsize=8)

        plt.tight_layout()
        plt.savefig(out_path, dpi=130, bbox_inches="tight",
                    facecolor="#07111e", edgecolor="none")
        plt.close()
        return out_path
    except Exception as e:
        logger.error(f"バックテストチャート生成エラー: {e}")
        return None


def run() -> dict:
    """バックテストを実行"""
    logger.info("--- Step L4e: バックテスト ---")
    result = {"available": False}

    try:
        logger.info("  S&P500 20年データ取得中...")
        df_sp = _fetch("^GSPC", "20y")
        if df_sp.empty or len(df_sp) < 500:
            logger.warning("S&P500データ不足 → バックテストスキップ")
            return result

        logger.info("  VIX 20年データ取得中...")
        df_vix = _fetch("^VIX", "20y")

        results = []

        # 戦略1: 200日MA
        r1 = _run_strategy(df_sp, "200日MA戦略", strategy_ma200)
        results.append(r1)
        logger.info(f"  200日MA: CAGR={r1['cagr']}% MaxDD={r1['max_drawdown']}%")

        # 戦略2: VIXタイミング（VIXデータがある場合）
        if not df_vix.empty:
            df_sp_vix = df_sp[df_sp.index.isin(df_vix.index) | True].copy()
            r2 = _run_strategy(
                df_sp_vix, "VIX<20買い戦略",
                lambda df: strategy_vix_timing(df, df_vix)
            )
            results.append(r2)
            logger.info(f"  VIXタイミング: CAGR={r2['cagr']}% MaxDD={r2['max_drawdown']}%")

        # 戦略3: 押し目買い
        r3 = _run_strategy(df_sp, "押し目買い戦略", strategy_buy_the_dip)
        results.append(r3)
        logger.info(f"  押し目買い: CAGR={r3['cagr']}% MaxDD={r3['max_drawdown']}%")

        chart_path = make_backtest_chart(results)

        # serializable用にcum_seriesを除去
        results_clean = [
            {k: v for k, v in r.items() if k not in ("cum_series", "bnh_series")}
            for r in results
        ]

        result = {
            "available": True,
            "strategies": results_clean,
            "chart_path": chart_path,
            "period": "S&P500 20年間",
            "best_strategy": max(results_clean, key=lambda x: x["cagr"])["name"],
            "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        logger.info(f"✅ バックテスト完了: 最良={result['best_strategy']}")

    except Exception as e:
        logger.error(f"バックテストエラー: {e}")
        import traceback
        logger.debug(traceback.format_exc())

    return result
