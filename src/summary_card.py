"""
朝イチ・サマリーカード画像生成モジュール（A案）
- Telegram の「①今日の市場まとめ」に添える、一目でわかるカード型ビジュアル
- 6つの主要指標タイル ＋ Fear&Greed バー ＋ 今日の天気図
- 既存の visualize.py / risk_gauge.py とは独立（フォールバックで安全運用）
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import traceback

matplotlib.rcParams.update({
    "font.family": ["Noto Sans CJK JP", "IPAexGothic", "Hiragino Sans",
                    "Meiryo", "Yu Gothic", "sans-serif"],
    "axes.unicode_minus": False,
})
try:
    import japanize_matplotlib  # noqa: F401
except ImportError:
    pass

from src.utils import get_today_str, get_jst_now, get_dirs, setup_logger

logger = setup_logger("summary_card")

# ── パレット（ダークモダン）──────────────────────────────────────────
BG     = "#0f1420"   # 背景
CARD   = "#16213a"   # タイル背景
PANEL  = "#111a2e"   # 下部パネル
BORDER = "#243454"
WHITE  = "#eaf2ff"
MUTED  = "#8aa0c0"
GREEN  = "#27c281"
RED    = "#ef4d4d"
AMBER  = "#ff9f2e"
BLUE   = "#5b9bf3"
ACCENT = "#7b9fe8"

_WEEKDAYS_JA = ["月", "火", "水", "木", "金", "土", "日"]

# ── タイルに描く6指標 (symbol, label, 単位, 小数桁) ───────────────────
_TILES = [
    ("^N225",    "日経225",  "",  0),
    ("^GSPC",    "S&P500",   "",  0),
    ("USDJPY=X", "ドル円",   "",  2),
    ("^VIX",     "VIX",      "",  1),
    ("GC=F",     "金",       "$", 0),
    ("NT_RATIO", "NT倍率",   "",  2),
]


def _now_label() -> str:
    n = get_jst_now()
    return f"{n.month}/{n.day}({_WEEKDAYS_JA[n.weekday()]}) {n.strftime('%H:%M')}"


def _fmt_val(val, unit, dp):
    if val is None:
        return "---"
    if dp == 0:
        return f"{unit}{val:,.0f}"
    return f"{unit}{val:,.{dp}f}"


def _tile_color(chg):
    if chg is None:
        return MUTED
    return GREEN if chg >= 0 else RED


def _weather(prices: dict) -> tuple:
    """ざっくり今日の天気図を判定 → (絵文字, ラベル, 一言, 色)"""
    reds = 0
    notes = []

    vix = (prices.get("^VIX") or {}).get("latest")
    nvi = (prices.get("NIKKEI_VI") or {}).get("latest")
    if vix is not None and nvi is not None and (nvi - vix) >= 10:
        reds += 1
        notes.append("日本発の不安が優勢")
    if vix is not None and vix >= 25:
        reds += 1
        notes.append("VIX高水準で警戒")

    # CME先物ギャップ（寄りの方向）
    n225 = (prices.get("^N225") or {}).get("latest")
    fut  = (prices.get("NIY=F") or {}).get("latest")
    if n225 and fut:
        gap = (fut - n225) / n225 * 100
        if gap >= 0.8:
            notes.append(f"先物が現物より{gap:+.1f}%高く寄りは買い優勢")
        elif gap <= -0.8:
            reds += 1
            notes.append(f"先物が現物より{gap:+.1f}%安く寄りは売り優勢")

    # 半導体
    sox = (prices.get("^SOX") or {}).get("change_pct")
    if sox is not None and sox <= -2.0:
        reds += 1
        notes.append("半導体軟調で上値は重い")

    if reds >= 2:
        return "嵐に備える日", "、".join(notes[:2]) or "複数の警戒シグナル点灯", RED
    elif reds == 1:
        return "くもり・局地的強風", "、".join(notes[:2]) or "一部に注意サイン", AMBER
    else:
        return "おおむね晴れ", "、".join(notes[:2]) or "大きな波乱サインは見当たらず", GREEN


def _fg_info(score):
    n = int(score) if score is not None else 50
    if   n >= 75: return n, AMBER, "超強欲"
    elif n >= 55: return n, GREEN, "強欲"
    elif n >= 45: return n, ACCENT, "中立"
    elif n >= 25: return n, AMBER, "恐怖"
    else:         return n, RED, "超恐怖"


def make_summary_card(prices: dict, fear_greed: dict, risk: dict) -> str | None:
    """サマリーカードPNGを生成してパスを返す。失敗時 None。"""
    try:
        prices     = prices or {}
        fear_greed = fear_greed or {}

        fig = plt.figure(figsize=(7.2, 7.4), facecolor=BG)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(0, 100)
        ax.set_ylim(0, 100)
        ax.axis("off")
        ax.set_facecolor(BG)

        def rrect(x, y, w, h, fc, ec=None, lw=1.0, rad=2.2, z=2):
            p = FancyBboxPatch(
                (x, y), w, h,
                boxstyle=f"round,pad=0,rounding_size={rad}",
                facecolor=fc, edgecolor=ec or fc, linewidth=lw, zorder=z,
            )
            ax.add_patch(p)
            return p

        # ── ヘッダー ───────────────────────────────────────────────
        ax.text(5, 95.5, "市場AI秘書", color=ACCENT, fontsize=18,
                fontweight="bold", va="center")
        ax.text(5, 91.5, "今日の市場まとめ", color=MUTED, fontsize=11, va="center")
        ax.text(95, 94.5, _now_label(), color=MUTED, fontsize=11,
                ha="right", va="center")
        ax.plot([5, 95], [89, 89], color=BORDER, lw=1.2, zorder=1)

        # ── 6タイル（2列×3行）─────────────────────────────────────
        gx, gw, ggap = 5, 28.7, 1.95          # x開始, 幅, 横間隔
        gy_top, gh, gvgap = 73.5, 11.8, 1.8    # y上端, 高さ, 縦間隔
        for i, (sym, label, unit, dp) in enumerate(_TILES):
            col = i % 3
            row = i // 3
            x = gx + col * (gw + ggap)
            y = gy_top - row * (gh + gvgap)
            d   = prices.get(sym, {})
            val = d.get("latest")
            chg = d.get("change_pct")
            c   = _tile_color(chg)

            rrect(x, y, gw, gh, CARD, ec=BORDER, lw=1.0)
            # 左の色付きアクセントバー
            rrect(x + 0.6, y + 1.0, 1.1, gh - 2.0, c, rad=0.5, z=3)

            ax.text(x + 3.2, y + gh - 2.6, label, color=MUTED, fontsize=10.5,
                    va="center", zorder=4)
            ax.text(x + 3.2, y + gh - 6.3, _fmt_val(val, unit, dp),
                    color=WHITE, fontsize=16.5, fontweight="bold",
                    va="center", zorder=4)
            if chg is not None:
                arrow = "▲" if chg >= 0 else "▼"
                unit2 = "pt" if sym == "NT_RATIO" else "%"
                ax.text(x + 3.2, y + 2.3, f"{arrow} {abs(chg):.2f}{unit2}",
                        color=c, fontsize=11, fontweight="bold",
                        va="center", zorder=4)
            else:
                ax.text(x + 3.2, y + 2.3, "—", color=MUTED, fontsize=11,
                        va="center", zorder=4)

        # ── Fear & Greed バー ──────────────────────────────────────
        fg_y = 45.0
        fg_n, fg_c, fg_lbl = _fg_info(fear_greed.get("score"))
        rrect(5, fg_y, 90, 9.5, PANEL, ec=BORDER, lw=1.0)
        ax.text(8, fg_y + 7.0, "みんなの心理（Fear & Greed）",
                color=MUTED, fontsize=10.5, va="center", zorder=4)
        ax.text(92, fg_y + 7.0, f"{fg_lbl} {fg_n}", color=fg_c, fontsize=12,
                fontweight="bold", ha="right", va="center", zorder=4)
        # トラック
        bar_x, bar_w, bar_y, bar_h = 8, 84, fg_y + 2.0, 2.6
        rrect(bar_x, bar_y, bar_w, bar_h, "#22304d", rad=1.3, z=3)
        fill_w = max(bar_w * fg_n / 100, 1.5)
        rrect(bar_x, bar_y, fill_w, bar_h, fg_c, rad=1.3, z=4)
        # マーカー
        ax.plot(bar_x + fill_w, bar_y + bar_h / 2, "o", color=WHITE, ms=7,
                markeredgecolor=BG, markeredgewidth=1.5, zorder=6)
        ax.text(bar_x, fg_y + 0.0, "0 怖い", color=MUTED, fontsize=8, va="center", zorder=4)
        ax.text(bar_x + bar_w, fg_y + 0.0, "強気 100", color=MUTED, fontsize=8,
                ha="right", va="center", zorder=4)

        # ── 今日の天気図 ───────────────────────────────────────────
        wx, wy, ww, wh = 5, 6.0, 90, 31.0
        wlabel, wtext, wc = _weather(prices)
        rrect(wx, wy, ww, wh, PANEL, ec=wc, lw=1.6)
        rrect(wx, wy, 1.4, wh, wc, rad=0.6, z=3)
        ax.text(wx + 4.5, wy + wh - 6.0, "今日の天気図", color=MUTED,
                fontsize=11, va="center", zorder=4)
        # 天気を表す色付きドット
        ax.plot(wx + 6.2, wy + wh - 14.5, "o", color=wc, ms=15, zorder=4,
                markeredgecolor=BG, markeredgewidth=1.5)
        ax.text(wx + 10.5, wy + wh - 14.5, wlabel, color=wc,
                fontsize=17, fontweight="bold", va="center", zorder=4)
        # 折り返し
        import textwrap
        wrapped = "\n".join(textwrap.wrap(wtext, width=32)) or wtext
        ax.text(wx + 4.5, wy + 7.5, wrapped, color=WHITE, fontsize=11,
                va="center", zorder=4, linespacing=1.5)

        out = get_dirs()["charts"] / f"summary_card_{get_today_str()}.png"
        plt.savefig(str(out), dpi=160, facecolor=BG, edgecolor="none")
        plt.close(fig)
        logger.info(f"✅ サマリーカード: {out}")
        return str(out)

    except Exception as e:
        logger.error(f"summary_card エラー: {e}")
        logger.debug(traceback.format_exc())
        try:
            plt.close("all")
        except Exception:
            pass
        return None
