"""
L4d: 資産間相関分析モジュール
「円安が進むと日経はどう動くか」を統計的に計算して毎朝更新
"""
import ssl
import json
import urllib.request
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
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

PAIRS = {
    "nikkei":  "^N225",
    "sp500":   "^GSPC",
    "vix":     "^VIX",
    "usdjpy":  "JPY=X",
    "gold":    "GC=F",
    "nasdaq":  "^IXIC",
}

PAIR_NAMES = {
    "nikkei": "日経225",
    "sp500":  "S&P500",
    "vix":    "VIX",
    "usdjpy": "ドル円",
    "gold":   "金",
    "nasdaq": "NASDAQ",
}


def _fetch(symbol: str, period: str = "2y") -> pd.Series:
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
        closes = result["indicators"]["quote"][0]["close"]
        dates = [datetime.fromtimestamp(t).strftime("%Y-%m-%d") for t in timestamps]
        s = pd.Series(closes, index=pd.to_datetime(dates), name=symbol).dropna()
        return s
    except Exception as e:
        logger.warning(f"fetch失敗 {symbol}: {e}")
        return pd.Series(dtype=float)


def _key_insights(corr_matrix: pd.DataFrame) -> list:
    """重要な相関関係を日本語で説明"""
    insights = []
    pairs_to_check = [
        ("nikkei", "usdjpy", "日経225とドル円"),
        ("nikkei", "sp500",  "日経225とS&P500"),
        ("nikkei", "vix",    "日経225とVIX"),
        ("sp500",  "vix",    "S&P500とVIX"),
        ("gold",   "usdjpy", "金とドル円"),
        ("nikkei", "gold",   "日経225と金"),
    ]
    for a, b, label in pairs_to_check:
        if a not in corr_matrix.index or b not in corr_matrix.columns:
            continue
        r = corr_matrix.loc[a, b]
        if abs(r) < 0.3:
            strength = "ほぼ無関係"
            direction = ""
        elif abs(r) < 0.6:
            strength = "やや相関あり"
            direction = "正" if r > 0 else "逆"
        else:
            strength = "強い相関"
            direction = "正" if r > 0 else "逆"

        if a == "nikkei" and b == "usdjpy":
            if r > 0.5:
                comment = "→ 円安が進むと日経も上がりやすい状況"
            elif r < -0.3:
                comment = "→ 円安でも日経が上がらない異常な状態"
            else:
                comment = "→ ドル円と日経の連動性が薄れている"
        elif a == "nikkei" and b == "sp500":
            if r > 0.7:
                comment = "→ 日経は米株に強く連動中（追随型）"
            else:
                comment = "→ 日経が米株と独自の動きをしている"
        elif a == "nikkei" and b == "vix":
            if r < -0.5:
                comment = "→ VIX上昇=日経下落の典型的なリスクオフ"
            else:
                comment = "→ 恐怖指数と日経の連動が弱まっている"
        else:
            comment = ""

        insights.append({
            "label": label,
            "r": round(float(r), 3),
            "strength": strength,
            "direction": direction,
            "comment": comment,
        })
    return insights


def make_correlation_chart(corr_matrix: pd.DataFrame, returns: pd.DataFrame) -> str | None:
    """相関ヒートマップ + 散布図を生成"""
    try:
        dirs = Path("reports/charts")
        dirs.mkdir(parents=True, exist_ok=True)
        out_path = str(dirs / "correlation.png")

        labels = [PAIR_NAMES.get(k, k) for k in corr_matrix.columns]
        n = len(labels)

        fig, axes = plt.subplots(1, 2, figsize=(14, 6),
                                 facecolor="#07111e")
        fig.suptitle("資産間 相関分析", color="white", fontsize=14, fontweight="bold", y=1.01)

        # 左: 相関ヒートマップ
        ax1 = axes[0]
        ax1.set_facecolor("#0d1f33")
        mat = corr_matrix.values
        im = ax1.imshow(mat, cmap="RdYlGn", vmin=-1, vmax=1)
        ax1.set_xticks(range(n))
        ax1.set_yticks(range(n))
        ax1.set_xticklabels(labels, color="white", fontsize=8, rotation=45, ha="right")
        ax1.set_yticklabels(labels, color="white", fontsize=8)
        for i in range(n):
            for j in range(n):
                val = mat[i, j]
                color = "black" if abs(val) > 0.5 else "white"
                ax1.text(j, i, f"{val:.2f}", ha="center", va="center",
                         color=color, fontsize=7, fontweight="bold")
        ax1.set_title("相関係数マトリクス（2年）", color="white", fontsize=10)
        plt.colorbar(im, ax=ax1, shrink=0.8)

        # 右: 日経 vs ドル円 散布図
        ax2 = axes[1]
        ax2.set_facecolor("#0d1f33")
        if "nikkei" in returns.columns and "usdjpy" in returns.columns:
            x = returns["usdjpy"].dropna()
            y = returns["nikkei"].reindex(x.index).dropna()
            x = x.reindex(y.index)
            ax2.scatter(x, y, alpha=0.4, color="#00d4ff", s=8)
            # 回帰線
            if len(x) > 10:
                z = np.polyfit(x, y, 1)
                p = np.poly1d(z)
                xline = np.linspace(x.min(), x.max(), 100)
                ax2.plot(xline, p(xline), color="#ff6b35", linewidth=2)
            ax2.axhline(0, color="#555", linewidth=0.5)
            ax2.axvline(0, color="#555", linewidth=0.5)
            ax2.set_xlabel("ドル円 日次騰落率(%)", color="#aaa", fontsize=9)
            ax2.set_ylabel("日経225 日次騰落率(%)", color="#aaa", fontsize=9)
            ax2.set_title("日経225 vs ドル円（散布図）", color="white", fontsize=10)
            ax2.tick_params(colors="white")
            for spine in ax2.spines.values():
                spine.set_color("#334455")

        plt.tight_layout()
        plt.savefig(out_path, dpi=130, bbox_inches="tight",
                    facecolor="#07111e", edgecolor="none")
        plt.close()
        return out_path
    except Exception as e:
        logger.error(f"相関チャート生成エラー: {e}")
        return None


def run() -> dict:
    """相関分析を実行"""
    logger.info("--- Step L4d: 資産間相関分析 ---")
    result = {"available": False}

    try:
        series = {}
        for key, sym in PAIRS.items():
            s = _fetch(sym, "2y")
            if not s.empty:
                series[key] = s
                logger.info(f"  ✅ {PAIR_NAMES[key]}: {len(s)}件")

        if len(series) < 3:
            logger.warning("データ不足 → 相関分析スキップ")
            return result

        # 日次リターン
        df = pd.DataFrame(series).pct_change().dropna() * 100
        corr = df.corr()

        insights = _key_insights(corr)
        chart_path = make_correlation_chart(corr, df)

        # 最重要インサイトを抽出
        nk_usd = corr.loc["nikkei", "usdjpy"] if "usdjpy" in corr.columns else None
        nk_sp  = corr.loc["nikkei", "sp500"]  if "sp500"  in corr.columns else None
        nk_vix = corr.loc["nikkei", "vix"]    if "vix"    in corr.columns else None

        result = {
            "available": True,
            "correlations": corr.to_dict(),
            "insights": insights,
            "chart_path": chart_path,
            "key": {
                "nikkei_usdjpy": round(float(nk_usd), 3) if nk_usd is not None else None,
                "nikkei_sp500":  round(float(nk_sp),  3) if nk_sp  is not None else None,
                "nikkei_vix":    round(float(nk_vix),  3) if nk_vix  is not None else None,
            },
            "period": "2年間の日次データ",
            "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        logger.info(f"✅ 相関分析完了: 日経-ドル円r={nk_usd:.2f}" if nk_usd else "✅ 相関分析完了")

    except Exception as e:
        logger.error(f"相関分析エラー: {e}")
        import traceback
        logger.debug(traceback.format_exc())

    return result
