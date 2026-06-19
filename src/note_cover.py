"""
note.com カバー画像生成モジュール
市場AI秘書のデータから note.com サムネイル用 PNG (1200×630) を自動生成する
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from datetime import date as _date
from src.utils import setup_logger, get_today_str, get_dirs

logger = setup_logger("note_cover")

# ── カラーパレット ────────────────────────────────────────────
BG_COLOR = "#0f172a"
CARD_BG  = "#1e293b"
BORDER   = "#334155"
ACCENT   = "#3b82f6"
GREEN    = "#22c55e"
RED      = "#ef4444"
YELLOW   = "#f59e0b"
PURPLE   = "#8b5cf6"
TEXT_PRI = "#f1f5f9"
TEXT_SEC = "#94a3b8"


def _mood(score: float) -> tuple[str, str]:
    if score >= 2:    return GREEN,    "強気！上昇ムード 🚀"
    if score >= 0.5:  return GREEN,    "やや強気 😊"
    if score >= -0.5: return YELLOW,   "中立・様子見 😐"
    if score >= -2:   return "#f97316","やや弱気 😟"
    return RED, "弱気！慎重に 😱"


def _fg_label(v: float) -> str:
    if v >= 75: return "超強欲"
    if v >= 55: return "強欲"
    if v >= 45: return "中立"
    if v >= 25: return "恐怖"
    return "超恐怖"


def _fmt_val(prices: dict, sym: str, unit: str) -> tuple[str, str, str]:
    """(値文字列, 変化率文字列, 色) を返す"""
    d   = prices.get(sym, {})
    v   = d.get("latest")
    chg = d.get("change_pct")
    if v is None:
        return "―", "", TEXT_SEC
    val_s = f"{v:,.0f}{unit}" if abs(v) >= 100 else f"{v:.2f}{unit}"
    if chg is None:
        return val_s, "", TEXT_SEC
    chg_c = GREEN if chg >= 0 else RED
    arr   = "▲" if chg >= 0 else "▼"
    return val_s, f"{arr} {abs(chg):.2f}%", chg_c


def generate(prices=None, risk=None, fear_greed=None) -> str:
    """カバー画像を生成してパスを返す。失敗時は空文字。"""
    try:
        import japanize_matplotlib  # 日本語フォント
    except ImportError:
        logger.warning("japanize_matplotlib 未インストール。フォントが文字化けする可能性があります")

    prices     = prices or {}
    risk       = risk or {"score": 0, "sentiment": "不明"}
    fear_greed = fear_greed or {}

    score     = risk.get("score", 0)
    score_s   = f"+{score:.1f}" if score >= 0 else f"{score:.1f}"
    mood_color, mood_label = _mood(score)
    fg_score  = float(fear_greed.get("score") or 50)

    today   = get_today_str()
    weekday = ["月", "火", "水", "木", "金", "土", "日"][_date.today().weekday()]

    price_items = [
        ("^N225",    "🇯🇵 日経平均",  "円"),
        ("^GSPC",    "🇺🇸 S&P500",   ""),
        ("USDJPY=X", "💵 ドル円",     "円"),
        ("GC=F",     "🥇 金",        "$"),
        ("BTC-USD",  "₿ Bitcoin",   "$"),
        ("^VIX",     "⚡ VIX",       ""),
    ]

    try:
        fig = plt.figure(figsize=(12.0, 6.3), facecolor=BG_COLOR)
        ax  = fig.add_axes([0, 0, 1, 1], facecolor=BG_COLOR)
        ax.set_xlim(0, 12); ax.set_ylim(0, 6.3)
        ax.axis("off")

        # ── 背景アクセント円 ─────────────────────────────────
        ax.add_patch(plt.Circle((11.0, 5.8), 2.4, color=ACCENT, alpha=0.07, zorder=0))
        ax.add_patch(plt.Circle((0.8, 0.8), 1.6, color=PURPLE, alpha=0.06, zorder=0))
        ax.add_patch(plt.Circle((6.0, 3.2), 3.5, color="#1e3a8a", alpha=0.04, zorder=0))

        # ── 上部ライン ──────────────────────────────────────
        ax.axhline(y=6.1, xmin=0.02, xmax=0.98, color=ACCENT, linewidth=1.5, alpha=0.35)

        # ── ブランド名 ──────────────────────────────────────
        ax.text(0.38, 6.12, "📊 市場AI秘書", fontsize=10, color=TEXT_SEC,
                va="bottom", fontweight="bold")
        ax.text(11.62, 6.12, f"{today}（{weekday}）", fontsize=9, color=TEXT_SEC,
                va="bottom", ha="right")

        # ── メインタイトル ──────────────────────────────────
        ax.text(0.38, 5.85, "今日の相場レポート", fontsize=24, color=TEXT_PRI,
                va="top", fontweight="bold")
        ax.text(0.38, 5.25, "AIが3視点で徹底分析", fontsize=13, color=TEXT_SEC,
                va="top")

        # ── 判定バッジ ──────────────────────────────────────
        badge = FancyBboxPatch((0.38, 4.45), 5.3, 0.58,
                                boxstyle="round,pad=0.07",
                                facecolor=mood_color, alpha=0.12,
                                edgecolor=mood_color, linewidth=1.8)
        ax.add_patch(badge)
        ax.text(3.03, 4.74, f"今日の判定：{mood_label}　[スコア: {score_s}]",
                fontsize=13, color=mood_color, va="center", ha="center",
                fontweight="bold")

        # ── 価格カード 2列×3行 ──────────────────────────────
        col_x = [(6.5, 9.1), (9.2, 11.85)]
        col_data = [price_items[:3], price_items[3:]]

        for ci, (x0, x1) in enumerate(col_x):
            for ri, (sym, name, unit) in enumerate(col_data[ci]):
                val_s, chg_s, chg_c = _fmt_val(prices, sym, unit)
                y_top = 5.9 - ri * 1.85

                card = FancyBboxPatch((x0, y_top - 1.65), (x1 - x0), 1.55,
                                      boxstyle="round,pad=0.06",
                                      facecolor=CARD_BG, edgecolor=BORDER, linewidth=1.2)
                ax.add_patch(card)

                ax.text(x0 + 0.18, y_top - 0.22, name,
                        fontsize=8.5, color=TEXT_SEC, va="top")
                ax.text(x0 + 0.18, y_top - 0.65, val_s,
                        fontsize=13, color=TEXT_PRI, va="top", fontweight="bold")
                if chg_s:
                    ax.text(x0 + 0.18, y_top - 1.12, chg_s,
                            fontsize=9.5, color=chg_c, va="top", fontweight="bold")

        # ── Fear & Greed バー ────────────────────────────────
        bar_y, bar_x0, bar_w = 0.55, 0.38, 5.7

        ax.text(bar_x0, bar_y + 0.82, "😱 Fear & Greed Index",
                fontsize=10, color=TEXT_SEC, va="bottom", fontweight="bold")

        # レール
        ax.add_patch(FancyBboxPatch((bar_x0, bar_y), bar_w, 0.42,
                                     boxstyle="round,pad=0.0",
                                     facecolor=CARD_BG, edgecolor=BORDER, linewidth=1))

        # グラデーションセグメント
        segs = [
            (0.00, 0.25, PURPLE),
            (0.25, 0.45, RED),
            (0.45, 0.55, YELLOW),
            (0.55, 1.00, GREEN),
        ]
        fill_ratio = fg_score / 100
        for s, e, c in segs:
            drawn = min(fill_ratio, e) - s
            if drawn > 0:
                ax.add_patch(FancyBboxPatch(
                    (bar_x0 + s * bar_w, bar_y), drawn * bar_w, 0.42,
                    boxstyle="round,pad=0.0", facecolor=c, alpha=0.82, linewidth=0
                ))

        # ニードル
        nx = bar_x0 + fill_ratio * bar_w
        ax.plot([nx, nx], [bar_y - 0.12, bar_y + 0.54],
                color="white", linewidth=2.5, zorder=5, solid_capstyle="round")

        fg_c = GREEN if fg_score >= 55 else YELLOW if fg_score >= 45 else RED
        ax.text(nx, bar_y - 0.18,
                f"{fg_score:.0f}  {_fg_label(fg_score)}",
                fontsize=11, color=fg_c, ha="center", va="top", fontweight="bold")

        # ── ラベル（バー下） ─────────────────────────────────
        ax.text(bar_x0, bar_y - 0.08, "0\n超恐怖", fontsize=6.5, color=TEXT_SEC,
                ha="left", va="top", linespacing=1.2)
        ax.text(bar_x0 + bar_w, bar_y - 0.08, "100\n超強欲", fontsize=6.5, color=TEXT_SEC,
                ha="right", va="top", linespacing=1.2)

        # ── フッター ─────────────────────────────────────────
        ax.axhline(y=0.1, xmin=0.02, xmax=0.98, color=BORDER, linewidth=0.8)
        ax.text(6.0, 0.04,
                "🤖 Gemini AI × 市場AI秘書  ·  毎朝7:30 自動更新  ·  分析は参考情報です",
                fontsize=7.5, color=TEXT_SEC, ha="center", va="bottom")

        # ── 保存 ─────────────────────────────────────────────
        dirs     = get_dirs()
        out_path = dirs["reports"] / f"{today}_note_cover.png"
        fig.savefig(str(out_path), dpi=100, bbox_inches="tight",
                    facecolor=BG_COLOR, edgecolor="none")
        plt.close(fig)
        logger.info(f"✅ note カバー画像生成完了: {out_path}")
        return str(out_path)

    except Exception as e:
        logger.error(f"note カバー画像生成エラー: {e}")
        import traceback; logger.debug(traceback.format_exc())
        return ""


def run(prices=None, risk=None, fear_greed=None) -> dict:
    result = {"available": False, "path": ""}
    try:
        path = generate(prices=prices, risk=risk, fear_greed=fear_greed)
        if path:
            result["available"] = True
            result["path"]      = path
    except Exception as e:
        logger.error(f"note_cover run エラー: {e}")
    return result
