"""
モンテカルロシミュレーション + マーコウィッツ効率的フロンティア
「1年後に資産がどうなっているか」を1万回シミュレートして確率で見せる。
効率的フロンティア：リスクを最小化しながらリターンを最大化する配分を計算。
"""
import ssl
import json
import urllib.request
import numpy as np
import pandas as pd
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

ASSETS = {
    "日経225": "^N225",
    "S&P500":  "^GSPC",
    "金(Gold)": "GC=F",
    "米国債(TLT)": "TLT",
}


def _fetch(symbol: str, period: str = "5y") -> pd.Series:
    url = (
        f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?interval=1d&range={period}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        resp = urllib.request.urlopen(req, context=_ctx, timeout=15)
        data = json.loads(resp.read())
        r = data["chart"]["result"][0]
        dates = [datetime.fromtimestamp(t).strftime("%Y-%m-%d") for t in r["timestamp"]]
        closes = r["indicators"]["quote"][0]["close"]
        s = pd.Series(closes, index=pd.to_datetime(dates), name=symbol).dropna()
        return s.sort_index()
    except Exception as e:
        logger.warning(f"fetch失敗 {symbol}: {e}")
        return pd.Series(dtype=float)


def run_monte_carlo(returns: pd.Series, n_simulations: int = 5000,
                    n_days: int = 252, initial: float = 100.0) -> dict:
    """
    単一資産のモンテカルロシミュレーション
    returns: 日次リターンのSeries
    """
    mu = returns.mean()
    sigma = returns.std()

    # ランダムパスをシミュレート
    np.random.seed(42)
    random_returns = np.random.normal(mu, sigma, (n_simulations, n_days))
    paths = initial * np.cumprod(1 + random_returns, axis=1)

    final_values = paths[:, -1]
    percentiles = {
        "p5":  round(float(np.percentile(final_values, 5)), 2),
        "p25": round(float(np.percentile(final_values, 25)), 2),
        "p50": round(float(np.percentile(final_values, 50)), 2),
        "p75": round(float(np.percentile(final_values, 75)), 2),
        "p95": round(float(np.percentile(final_values, 95)), 2),
    }
    prob_profit = float((final_values > initial).mean() * 100)
    prob_loss10 = float((final_values < initial * 0.9).mean() * 100)

    return {
        "paths": paths,
        "final_values": final_values,
        "percentiles": percentiles,
        "prob_profit": round(prob_profit, 1),
        "prob_loss10": round(prob_loss10, 1),
        "mu_annual": round(mu * 252 * 100, 2),
        "sigma_annual": round(sigma * np.sqrt(252) * 100, 2),
    }


def markowitz_optimize(returns_df: pd.DataFrame, n_portfolios: int = 3000) -> dict:
    """
    マーコウィッツの現代ポートフォリオ理論
    ランダムな重みで3000ポートフォリオを生成し、効率的フロンティアを描く。
    """
    mean_returns = returns_df.mean() * 252
    cov_matrix = returns_df.cov() * 252
    n_assets = len(returns_df.columns)

    port_returns = []
    port_risks = []
    port_weights = []
    port_sharpes = []

    risk_free = 0.05  # 無リスク金利 5%（米国FF金利近辺）

    np.random.seed(42)
    for _ in range(n_portfolios):
        w = np.random.dirichlet(np.ones(n_assets))
        ret = float(np.dot(w, mean_returns))
        risk = float(np.sqrt(np.dot(w.T, np.dot(cov_matrix, w))))
        sharpe = (ret - risk_free) / risk if risk > 0 else 0
        port_returns.append(ret)
        port_risks.append(risk)
        port_weights.append(w)
        port_sharpes.append(sharpe)

    # 最大シャープレシオポートフォリオ
    max_sharpe_idx = np.argmax(port_sharpes)
    # 最小リスクポートフォリオ
    min_risk_idx = np.argmin(port_risks)

    asset_names = list(returns_df.columns)

    def _weight_dict(idx):
        return {name: round(float(port_weights[idx][i]) * 100, 1)
                for i, name in enumerate(asset_names)}

    return {
        "max_sharpe": {
            "weights": _weight_dict(max_sharpe_idx),
            "return": round(port_returns[max_sharpe_idx] * 100, 2),
            "risk": round(port_risks[max_sharpe_idx] * 100, 2),
            "sharpe": round(port_sharpes[max_sharpe_idx], 3),
        },
        "min_risk": {
            "weights": _weight_dict(min_risk_idx),
            "return": round(port_returns[min_risk_idx] * 100, 2),
            "risk": round(port_risks[min_risk_idx] * 100, 2),
            "sharpe": round(port_sharpes[min_risk_idx], 3),
        },
        "all_returns": port_returns,
        "all_risks": port_risks,
        "all_sharpes": port_sharpes,
        "asset_names": asset_names,
    }


def make_monte_carlo_chart(mc_result: dict, asset_name: str,
                           markowitz: dict = None) -> str | None:
    """モンテカルロ + 効率的フロンティアのチャートを生成"""
    try:
        dirs = Path("reports/charts")
        dirs.mkdir(parents=True, exist_ok=True)
        out = str(dirs / "monte_carlo.png")

        ncols = 2 if markowitz else 1
        fig, axes = plt.subplots(1, ncols, figsize=(14 if ncols == 2 else 8, 6),
                                 facecolor="#07111e")
        if ncols == 1:
            axes = [axes]

        # 左: モンテカルロ
        ax1 = axes[0]
        ax1.set_facecolor("#0d1f33")
        paths = mc_result["paths"]
        days = paths.shape[1]
        x = range(days)

        # 薄いパスを100本だけ描画
        for i in range(min(100, len(paths))):
            color = "#00ff88" if paths[i, -1] > 100 else "#ff4444"
            ax1.plot(x, paths[i], alpha=0.05, color=color, linewidth=0.5)

        # パーセンタイル帯を描画
        p = mc_result["percentiles"]
        ax1.axhline(100, color="#fff", linewidth=1, linestyle="--", alpha=0.5, label="元本")
        ax1.fill_between(x,
                         np.percentile(paths, 5, axis=0),
                         np.percentile(paths, 95, axis=0),
                         alpha=0.2, color="#00d4ff", label="5-95%ile")
        ax1.fill_between(x,
                         np.percentile(paths, 25, axis=0),
                         np.percentile(paths, 75, axis=0),
                         alpha=0.3, color="#00d4ff", label="25-75%ile")
        ax1.plot(x, np.percentile(paths, 50, axis=0),
                 color="#ffcc00", linewidth=2, label="中央値")

        ax1.set_title(f"{asset_name} 1年後シミュレーション（{len(paths):,}回）",
                      color="white", fontsize=10)
        ax1.set_xlabel("取引日数", color="#aaa")
        ax1.set_ylabel("資産額（元本=100）", color="#aaa")
        ax1.tick_params(colors="white")
        ax1.legend(fontsize=7, facecolor="#0d1f33", labelcolor="white")
        for spine in ax1.spines.values():
            spine.set_color("#334455")

        # テキスト注釈
        ax1.text(0.02, 0.97,
                 f"利益確率: {mc_result['prob_profit']:.0f}%\n"
                 f"10%損失確率: {mc_result['prob_loss10']:.0f}%\n"
                 f"中央値: {p['p50']:.1f}",
                 transform=ax1.transAxes, color="white", fontsize=8,
                 va="top", bbox=dict(boxstyle="round", facecolor="#0a1a2a", alpha=0.8))

        # 右: 効率的フロンティア
        if markowitz and ncols == 2:
            ax2 = axes[1]
            ax2.set_facecolor("#0d1f33")
            sc = ax2.scatter(
                [r * 100 for r in markowitz["all_risks"]],
                [r * 100 for r in markowitz["all_returns"]],
                c=markowitz["all_sharpes"], cmap="plasma",
                alpha=0.4, s=5
            )
            plt.colorbar(sc, ax=ax2, label="シャープレシオ", shrink=0.8)

            ms = markowitz["max_sharpe"]
            mr = markowitz["min_risk"]
            ax2.scatter(ms["risk"], ms["return"], color="#ffcc00", s=200,
                        marker="*", zorder=5, label=f"最大シャープ（SR={ms['sharpe']:.2f}）")
            ax2.scatter(mr["risk"], mr["return"], color="#00ff88", s=200,
                        marker="^", zorder=5, label=f"最小リスク")

            ax2.set_title("効率的フロンティア", color="white", fontsize=10)
            ax2.set_xlabel("リスク(年率%)", color="#aaa")
            ax2.set_ylabel("リターン(年率%)", color="#aaa")
            ax2.tick_params(colors="white")
            ax2.legend(fontsize=7, facecolor="#0d1f33", labelcolor="white")
            for spine in ax2.spines.values():
                spine.set_color("#334455")

        plt.tight_layout()
        plt.savefig(out, dpi=130, bbox_inches="tight",
                    facecolor="#07111e", edgecolor="none")
        plt.close()
        return out
    except Exception as e:
        logger.error(f"チャート生成エラー: {e}")
        return None


def run() -> dict:
    """モンテカルロ + マーコウィッツを実行"""
    logger.info("--- モンテカルロ + マーコウィッツ ---")
    result = {"available": False}

    try:
        # データ取得
        series_dict = {}
        for name, sym in ASSETS.items():
            s = _fetch(sym, "5y")
            if not s.empty:
                series_dict[name] = s
                logger.info(f"  ✅ {name}: {len(s)}件")

        if "日経225" not in series_dict:
            logger.warning("日経データなし → スキップ")
            return result

        # 日次リターン
        returns_df = pd.DataFrame(series_dict).pct_change().dropna()

        # 日経225のモンテカルロ（メイン）
        nk_returns = returns_df["日経225"].dropna()
        mc = run_monte_carlo(nk_returns, n_simulations=5000, n_days=252)
        logger.info(
            f"  モンテカルロ: 利益確率={mc['prob_profit']}% "
            f"年率リターン={mc['mu_annual']}%"
        )

        # マーコウィッツ（3資産以上ある場合）
        markowitz = None
        if len(series_dict) >= 2:
            markowitz = markowitz_optimize(returns_df)
            ms = markowitz["max_sharpe"]
            logger.info(
                f"  最適ポートフォリオ: return={ms['return']}% "
                f"risk={ms['risk']}% sharpe={ms['sharpe']}"
            )

        chart_path = make_monte_carlo_chart(mc, "日経225", markowitz)

        result = {
            "available": True,
            "monte_carlo": {
                "asset": "日経225",
                "percentiles": mc["percentiles"],
                "prob_profit": mc["prob_profit"],
                "prob_loss10": mc["prob_loss10"],
                "mu_annual": mc["mu_annual"],
                "sigma_annual": mc["sigma_annual"],
            },
            "markowitz": {
                "max_sharpe": markowitz["max_sharpe"],
                "min_risk": markowitz["min_risk"],
            } if markowitz else None,
            "chart_path": chart_path,
            "run_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        logger.info("✅ モンテカルロ + マーコウィッツ完了")

    except Exception as e:
        logger.error(f"モンテカルロエラー: {e}")
        logger.debug(traceback.format_exc())

    return result


import traceback  # noqa: E402（末尾importだが動作上問題なし）
