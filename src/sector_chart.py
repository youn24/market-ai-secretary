"""
セクターヒートマップ画像生成（Level 4a）
11セクターのパフォーマンスをプレミアムダークデザインで可視化
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from pathlib import Path
from src.utils import get_dirs

BG    = "#07111e"
CARD  = "#0d1f33"
WHITE = "#e8edf2"
GRAY  = "#4a6080"


def _color(pct: float) -> str:
    """変化率に応じた色を返す"""
    if   pct >= 2.0:  return "#00e676"
    elif pct >= 0.5:  return "#69f0ae"
    elif pct >= 0:    return "#a5d6a7"
    elif pct >= -0.5: return "#ef9a9a"
    elif pct >= -2.0: return "#e53935"
    else:             return "#b71c1c"


def make_sector_chart(sector_data: dict) -> str | None:
    """
    セクターヒートマップ + バーチャートを生成してパスを返す
    sector_data: sector_analysis.run()の戻り値
    """
    if not sector_data.get("available"):
        return None

    sectors  = sector_data["sectors"]
    rotation = sector_data["rotation"]

    names   = [s["name"]   for s in sectors]
    chg_1d  = [s["chg_1d"] for s in sectors]
    chg_1w  = [s["chg_1w"] for s in sectors]
    chg_1m  = [s["chg_1m"] for s in sectors]

    fig = plt.figure(figsize=(14, 9), facecolor=BG)
    fig.subplots_adjust(left=0.06, right=0.97, top=0.88, bottom=0.06, hspace=0.45)

    # ── タイトル ──
    fig.text(0.5, 0.95, "🌐 米国セクター分析 & ローテーション",
             ha="center", va="top", color=WHITE, fontsize=16, fontweight="bold")
    fig.text(0.5, 0.91, f"フェーズ: {rotation['phase']}  {rotation['label']}",
             ha="center", va="top", color="#ffd54f", fontsize=11)

    # ──── 上段: ヒートマップ（11セクター × 3期間）────
    ax1 = fig.add_axes([0.06, 0.52, 0.91, 0.35])
    ax1.set_facecolor(BG)
    ax1.axis("off")

    cols   = ["日次\n(1日)", "週次\n(1週)", "月次\n(1ヶ月)"]
    matrix = [chg_1d, chg_1w, chg_1m]
    n      = len(names)

    cell_w = 0.91 / n
    col_h  = 0.35 / 3

    for ci, (col_label, values) in enumerate(zip(cols, matrix)):
        y = 0.35 - (ci + 1) * col_h
        for ri, (name, val) in enumerate(zip(names, values)):
            x   = ri * cell_w
            clr = _color(val)
            rect = mpatches.FancyBboxPatch(
                (x + 0.003, y + 0.01), cell_w - 0.006, col_h - 0.02,
                boxstyle="round,pad=0.005", linewidth=0,
                facecolor=clr, alpha=0.85,
                transform=ax1.transAxes
            )
            ax1.add_patch(rect)
            ax1.text(x + cell_w / 2, y + col_h * 0.65,
                     f"{val:+.1f}%",
                     ha="center", va="center", color="white",
                     fontsize=9, fontweight="bold",
                     transform=ax1.transAxes)
            if ci == 0:
                ax1.text(x + cell_w / 2, y + col_h * 1.6,
                         name,
                         ha="center", va="center", color=WHITE,
                         fontsize=8.5,
                         transform=ax1.transAxes)
        ax1.text(-0.005, y + col_h / 2, col_label,
                 ha="right", va="center", color=GRAY,
                 fontsize=8,
                 transform=ax1.transAxes)

    # ──── 下段: 日次変化率バーチャート ────
    ax2 = fig.add_axes([0.06, 0.06, 0.91, 0.38])
    ax2.set_facecolor(CARD)
    for spine in ax2.spines.values():
        spine.set_visible(False)
    ax2.tick_params(colors=GRAY)

    x_pos  = np.arange(n)
    colors = [_color(v) for v in chg_1d]
    bars   = ax2.bar(x_pos, chg_1d, color=colors, width=0.65, alpha=0.9)

    ax2.axhline(0, color=GRAY, linewidth=0.8, linestyle="--")
    ax2.set_xticks(x_pos)
    ax2.set_xticklabels(names, fontsize=9, color=WHITE)
    ax2.set_ylabel("日次変化率 (%)", color=GRAY, fontsize=9)
    ax2.yaxis.label.set_color(GRAY)
    ax2.tick_params(axis="y", colors=GRAY)
    ax2.set_title("日次パフォーマンス（棒グラフ）", color=WHITE, fontsize=11, pad=8)
    ax2.set_facecolor(CARD)

    for bar, val in zip(bars, chg_1d):
        ypos = val + (0.05 if val >= 0 else -0.12)
        ax2.text(bar.get_x() + bar.get_width() / 2, ypos,
                 f"{val:+.1f}%",
                 ha="center", va="bottom" if val >= 0 else "top",
                 color=WHITE, fontsize=8, fontweight="bold")

    # 保存
    dirs      = get_dirs()
    out_path  = dirs["charts"] / "sector_analysis.png"
    plt.savefig(str(out_path), dpi=130, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    return str(out_path)
