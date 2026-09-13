"""
リスクゲージ画像生成モジュール
- 半円スピードメーター（緑〜赤グラデーション）
- 信号機シグナル（買い / 中立 / 売り）
- 注目銘柄 6 銘柄の騰落率
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.cm import RdYlGn
from matplotlib.colors import Normalize
import numpy as np
import traceback

try:
    import japanize_matplotlib  # noqa: F401
except ImportError:
    pass

from src.utils import get_today_str, get_jst_now, get_dirs, setup_logger

logger = setup_logger("risk_gauge")

# ── パレット ──────────────────────────────────────────────────────
BG    = "#0d1117"
CARD  = "#161b22"
WHITE = "#e6edf3"
MUTED = "#8b949e"
GREEN  = "#3fb950"
YELLOW = "#d29922"
ORANGE = "#db6d28"
RED    = "#f85149"

# ── 描画する注目銘柄リスト（最大 6 件）─────────────────────────────
_WATCH = [
    ("^N225",    "日経平均", ""),
    ("^GSPC",    "S&P500",  ""),
    ("USDJPY=X", "ドル円",  "¥"),
    ("^VIX",     "VIX",     ""),
    ("GC=F",     "金",      "$"),
    ("BTC-USD",  "BTC",     "$"),
]


# ── 信号機ロジック ───────────────────────────────────────────────
def _signal(score: float, vix: float):
    if score >= 2.0 and vix < 20:
        return GREEN,  "🟢 買い目線",   "積極的に注目できる環境"
    elif score >= 0.5:
        return GREEN,  "🟢 やや強気",   "通常ポジションで問題なし"
    elif score >= -0.5:
        return YELLOW, "🟡 中立・様子見", "急いで動く必要はない"
    elif score >= -2.0:
        return ORANGE, "🟠 要注意",     "リスク管理を強化する"
    else:
        return RED,    "🔴 危険信号",   "守りのポジションを優先"


# ── 各セクションの描画 ────────────────────────────────────────────

def _draw_gauge(ax, score: float):
    """半円スピードメーター"""
    ax.set_facecolor(BG)
    ax.set_xlim(-1.45, 1.45)
    ax.set_ylim(-0.35, 1.3)
    ax.set_aspect("equal")
    ax.axis("off")

    # グラデーション半円（100 セグメント）
    norm = Normalize(vmin=0, vmax=100)
    n = 100
    for i in range(n):
        t1 = i * 180 / n
        t2 = (i + 1) * 180 / n
        c = RdYlGn(norm(t1 * 100 / 180))     # t=0(右/弱気)→赤, t=180(左/強気)→緑
        ax.add_patch(mpatches.Wedge((0, 0), 1.0, t1, t2, width=0.28, color=c, zorder=1))

    # 内側を暗くして視認性 UP
    ax.add_patch(mpatches.Wedge((0, 0), 0.72, 0, 180, color=BG, zorder=2))

    # 目盛り線
    for deg, lbl in [(0, "弱気"), (45, ""), (90, "中立"), (135, ""), (180, "強気")]:
        r = np.radians(deg)
        x1, y1 = 0.72 * np.cos(r), 0.72 * np.sin(r)
        x2, y2 = 0.78 * np.cos(r), 0.78 * np.sin(r)
        ax.plot([x1, x2], [y1, y2], color=MUTED, lw=1.2, zorder=3)
        if lbl:
            xT = 0.56 * np.cos(r)
            yT = 0.56 * np.sin(r)
            c_lbl = GREEN if "強" in lbl else (RED if "弱" in lbl else YELLOW)
            ax.text(xT, yT, lbl, color=c_lbl, fontsize=8, ha="center", va="center",
                    fontweight="bold", zorder=4)

    # 針
    clamped   = max(-3.0, min(3.0, float(score)))
    theta_deg = (clamped + 3.0) / 6.0 * 180.0
    theta_rad = np.radians(theta_deg)
    nx, ny = 0.68 * np.cos(theta_rad), 0.68 * np.sin(theta_rad)
    ax.annotate("", xy=(nx, ny), xytext=(0, 0),
                arrowprops=dict(arrowstyle="-|>", color=WHITE, lw=2.0, mutation_scale=12),
                zorder=5)
    ax.add_patch(mpatches.Circle((0, 0), 0.06, color=WHITE, zorder=6))

    # スコア表示
    score_color = GREEN if score >= 0.5 else (YELLOW if score >= -0.5 else RED)
    ax.text(0, -0.22, f"スコア {score:+.2f}", color=score_color,
            fontsize=12, ha="center", fontweight="bold", zorder=7)
    ax.text(0, 1.2, "📊 リスクゲージ", color=WHITE,
            fontsize=11, ha="center", fontweight="bold")


def _draw_signal(ax, score: float, vix: float, fg: float):
    """信号機 + VIX + Fear&Greed"""
    ax.set_facecolor(BG)
    ax.axis("off")

    color, label, action = _signal(score, vix)

    ax.text(0.5, 0.95, "🚦 今日のシグナル", color=WHITE, fontsize=11,
            ha="center", va="top", transform=ax.transAxes, fontweight="bold")

    # シグナルボックス
    rect = mpatches.FancyBboxPatch(
        (0.05, 0.60), 0.90, 0.28,
        boxstyle="round,pad=0.03",
        linewidth=2, edgecolor=color, facecolor=CARD,
        transform=ax.transAxes, zorder=1
    )
    ax.add_patch(rect)
    ax.text(0.5, 0.79, label,  color=color,  fontsize=13, ha="center",
            transform=ax.transAxes, fontweight="bold", zorder=2)
    ax.text(0.5, 0.65, action, color=MUTED, fontsize=9,  ha="center",
            transform=ax.transAxes, style="italic", zorder=2)

    # VIX
    vix_color = (GREEN if vix < 15 else YELLOW if vix < 20 else ORANGE if vix < 30 else RED)
    ax.text(0.5, 0.50, f"VIX: {vix:.1f}", color=vix_color, fontsize=10,
            ha="center", transform=ax.transAxes, fontweight="bold")

    # Fear & Greed バー
    fg_color = GREEN if fg >= 60 else (YELLOW if fg >= 40 else RED)
    if   fg >= 75: fg_label = "超強欲 😱"
    elif fg >= 55: fg_label = "強欲 😤"
    elif fg >= 45: fg_label = "中立 😐"
    elif fg >= 25: fg_label = "恐怖 😰"
    else:          fg_label = "超恐怖 😭"

    ax.text(0.5, 0.38, f"Fear&Greed: {fg:.0f}  {fg_label}", color=fg_color, fontsize=9,
            ha="center", transform=ax.transAxes)

    # プログレスバー
    ax.barh(0.27, fg / 100 * 0.80, height=0.055, left=0.10,
            color=fg_color, alpha=0.85, transform=ax.transAxes)
    ax.barh(0.27, 0.80, height=0.055, left=0.10,
            color=CARD, zorder=-1, transform=ax.transAxes)
    ax.text(0.10, 0.19, "0  恐怖", color=MUTED, fontsize=7, transform=ax.transAxes)
    ax.text(0.82, 0.19, "強欲  100", color=MUTED, fontsize=7, ha="right",
            transform=ax.transAxes)


def _draw_stocks(ax, prices: dict):
    """注目銘柄 2 行 × 3 列"""
    ax.set_facecolor(BG)
    ax.axis("off")
    ax.text(0.5, 0.97, "📈 注目銘柄", color=WHITE, fontsize=11,
            ha="center", va="top", transform=ax.transAxes, fontweight="bold")

    cols  = [0.07, 0.40, 0.73]
    rows  = [0.70, 0.30]
    idx   = 0
    for row_y in rows:
        for col_x in cols:
            if idx >= len(_WATCH):
                break
            sym, name, unit = _WATCH[idx]
            d    = prices.get(sym, {})
            val  = d.get("latest")
            chg  = d.get("change_pct")
            idx += 1
            if val is None:
                continue

            val_str = f"{val:,.1f}" if val < 1000 else (f"{val:,.0f}" if val < 100000 else f"{val/1000:.1f}K")
            if unit:
                val_str = f"{unit}{val_str}"

            chg_color = WHITE
            arrow_str = ""
            if chg is not None:
                chg_color = GREEN if chg >= 0 else RED
                arrow_str = f"{'▲' if chg >= 0 else '▼'}{abs(chg):.2f}%"

            ax.text(col_x, row_y + 0.22, name,     color=MUTED, fontsize=8,
                    transform=ax.transAxes)
            ax.text(col_x, row_y + 0.10, val_str,  color=WHITE, fontsize=10,
                    transform=ax.transAxes, fontweight="bold")
            ax.text(col_x, row_y,        arrow_str, color=chg_color, fontsize=9,
                    transform=ax.transAxes, fontweight="bold")


# ── メイン生成関数 ────────────────────────────────────────────────

def make_gauge_image(risk: dict, fear_greed: dict, prices: dict) -> str:
    """
    リスクゲージ画像を生成してファイルパスを返す。
    失敗時は空文字列を返す。
    """
    try:
        score = float(risk.get("score", 0))
        vix   = float(prices.get("^VIX", {}).get("latest") or 20)
        fg    = float(fear_greed.get("score") or 50)

        fig = plt.figure(figsize=(12, 7), facecolor=BG)
        gs  = fig.add_gridspec(
            2, 2, hspace=0.12, wspace=0.08,
            top=0.93, bottom=0.06, left=0.03, right=0.97
        )
        ax_gauge  = fig.add_subplot(gs[0, 0])
        ax_signal = fig.add_subplot(gs[0, 1])
        ax_stocks = fig.add_subplot(gs[1, :])

        _draw_gauge(ax_gauge, score)
        _draw_signal(ax_signal, score, vix, fg)
        _draw_stocks(ax_stocks, prices)

        now = get_jst_now().strftime("%Y/%m/%d %H:%M JST")
        fig.suptitle(f"市場AI秘書 — リスクダッシュボード  {now}",
                     color=MUTED, fontsize=10, y=0.99)

        dirs = get_dirs()
        path = dirs["data_raw"] / f"risk_gauge_{get_today_str()}.png"
        plt.savefig(str(path), dpi=130, bbox_inches="tight", facecolor=BG)
        plt.close(fig)
        logger.info(f"✅ リスクゲージ画像生成: {path}")
        return str(path)

    except Exception as e:
        logger.error(f"ゲージ画像生成エラー: {e}")
        logger.debug(traceback.format_exc())
        return ""
