"""
朝イチ・サマリーカード画像生成
- 地合いバッジ ＋ 6指標タイル ＋ ミニ棒グラフ ＋ AI3視点 ＋ 注目ニュース
- Telegram の最初のメッセージとして送る「一目でわかるカード」
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import traceback
import textwrap

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

# ── パレット ───────────────────────────────────────────────────────────
BG     = "#0d1117"
CARD   = "#161b22"
PANEL  = "#0f1623"
BORDER = "#21262d"
WHITE  = "#e6edf3"
MUTED  = "#7d8590"
GREEN  = "#3fb950"
RED    = "#f85149"
AMBER  = "#d29922"
BLUE   = "#58a6ff"
ACCENT = "#6e86b3"

_WEEKDAYS_JA = ["月", "火", "水", "木", "金", "土", "日"]

_TILES = [
    ("^N225",    "日経平均",  "",  0),
    ("^GSPC",    "S&P500",   "",  0),
    ("^IXIC",    "NASDAQ",   "",  0),
    ("USDJPY=X", "ドル円",   "",  2),
    ("^VIX",     "VIX",      "",  1),
    ("BTC-USD",  "BTC",      "$", 0),
]

_TILE_SHORT = ["日経", "S&P", "NDX", "ドル円", "VIX", "BTC"]

_SENT_COLOR = {
    "強気": GREEN, "やや強気": GREEN,
    "弱気": RED,   "やや弱気": RED,
    "中立": AMBER, "警戒": RED, "不明": MUTED,
}


def _now_label() -> str:
    n = get_jst_now()
    return f"{n.strftime('%Y-%m-%d')}  朝のサマリー"


def _fmt_val(val, unit, dp):
    if val is None:
        return "---"
    if dp == 0:
        return f"{unit}{val:,.0f}"
    return f"{unit}{val:,.{dp}f}"


def _tile_color(chg):
    return GREEN if (chg or 0) >= 0 else RED


def _clip(txt, n):
    txt = (txt or "").replace("\n", " ").strip()
    return txt[:n] + ("…" if len(txt) > n else "")


def make_summary_card(prices: dict, fear_greed: dict, risk: dict,
                      ai_summary: dict = None, news: list = None) -> str | None:
    """サマリーカードPNGを生成してパスを返す。失敗時 None。"""
    try:
        prices     = prices or {}
        fear_greed = fear_greed or {}
        risk       = risk or {}
        ai_summary = ai_summary or {}
        news       = [n for n in (news or []) if isinstance(n, dict) and n.get("title")]

        fig = plt.figure(figsize=(7.5, 11.0), facecolor=BG)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(0, 100)
        ax.set_ylim(0, 100)
        ax.axis("off")
        ax.set_facecolor(BG)

        def rr(x, y, w, h, fc, ec=None, lw=1.0, rad=1.8, z=2):
            ax.add_patch(FancyBboxPatch(
                (x, y), w, h,
                boxstyle=f"round,pad=0,rounding_size={rad}",
                facecolor=fc, edgecolor=(ec or fc), linewidth=lw, zorder=z,
            ))

        # ─── ① ヘッダー ──────────────────────────────────────────────
        rr(0, 95, 100, 5, "#131a28", rad=0, z=1)
        ax.text(4, 97.5, "🤖 市場AI秘書", color=ACCENT, fontsize=15,
                fontweight="bold", va="center")
        ax.text(96, 97.5, _now_label(), color=MUTED, fontsize=9.5,
                ha="right", va="center")
        ax.plot([4, 96], [95, 95], color=BORDER, lw=0.8, zorder=3)

        # ─── ② 地合いバッジ（左）＋ リスクスコア（右）───────────────
        sent    = risk.get("sentiment", "不明")
        sent_c  = _SENT_COLOR.get(sent, MUTED)
        score_v = risk.get("score", 0)
        if score_v >= 1.0:   sent_sub = "買い優勢・上昇トレンド"
        elif score_v >= 0.3: sent_sub = "やや買い優勢"
        elif score_v >= -0.3: sent_sub = "方向感なし・様子見"
        elif score_v >= -1.0: sent_sub = "やや売り優勢"
        else:                  sent_sub = "売り優勢・要警戒"

        rr(4, 83.5, 56, 10.5, CARD, ec=sent_c, lw=1.5)
        rr(4, 83.5, 2.0, 10.5, sent_c, rad=0.7, z=3)
        ax.text(8, 92.0, "本日の地合い", color=MUTED, fontsize=9.5, va="center", zorder=4)
        ax.text(8, 88.0, f"  {sent}", color=sent_c, fontsize=17,
                fontweight="bold", va="center", zorder=4)
        ax.text(8, 84.8, sent_sub, color=MUTED, fontsize=8.5, va="center", zorder=4)

        fg_n = fear_greed.get("score")
        fg_n = int(fg_n) if fg_n is not None else 50
        if   fg_n >= 75: fg_c, fg_lbl = AMBER, "超強欲"
        elif fg_n >= 55: fg_c, fg_lbl = GREEN, "強欲"
        elif fg_n >= 45: fg_c, fg_lbl = ACCENT, "中立"
        elif fg_n >= 25: fg_c, fg_lbl = AMBER, "恐怖"
        else:            fg_c, fg_lbl = RED,   "超恐怖"

        rr(62, 83.5, 34, 10.5, CARD, ec=BORDER, lw=1.0)
        ax.text(79, 92.5, "リスクスコア", color=MUTED, fontsize=9,
                ha="center", va="center", zorder=4)
        ax.text(79, 88.0, str(fg_n), color=fg_c, fontsize=22,
                fontweight="bold", ha="center", va="center", zorder=4)
        ax.text(79, 84.7, f"/ 100  {fg_lbl}", color=fg_c, fontsize=8.5,
                ha="center", va="center", zorder=4)

        # ─── ③ 6タイル（3列×2行）────────────────────────────────────
        gx, gw, ggap   = 4, 29.8, 1.3
        gy0, gh, gvgap = 82.2, 9.8, 1.2
        tile_chgs = []

        for i, (sym, label, unit, dp) in enumerate(_TILES):
            col = i % 3
            row = i // 3
            x = gx + col * (gw + ggap)
            y = gy0 - 10.5 - row * (gh + gvgap)
            d   = prices.get(sym, {})
            val = d.get("latest")
            chg = d.get("change_pct")
            tile_chgs.append(chg)
            c   = _tile_color(chg)

            rr(x, y, gw, gh, CARD, ec=BORDER, lw=0.8)
            rr(x + 0.5, y + 0.8, 1.1, gh - 1.6, c, rad=0.4, z=3)
            ax.text(x + 3.0, y + gh - 2.0, label, color=MUTED, fontsize=9.5,
                    va="center", zorder=4)
            ax.text(x + 3.0, y + gh - 5.8, _fmt_val(val, unit, dp),
                    color=WHITE, fontsize=14, fontweight="bold", va="center", zorder=4)
            if chg is not None:
                arrow = "▲" if chg >= 0 else "▼"
                ax.text(x + 3.0, y + 1.8, f"{arrow}{abs(chg):.2f}%",
                        color=c, fontsize=9.5, fontweight="bold", va="center", zorder=4)
            else:
                ax.text(x + 3.0, y + 1.8, "—", color=MUTED, fontsize=9,
                        va="center", zorder=4)

        # ─── ④ ミニ棒グラフ ──────────────────────────────────────────
        bax, bay, baw, bah = 4, 47.5, 92, 10.5
        rr(bax, bay, baw, bah + 1.5, PANEL, ec=BORDER, lw=0.8)
        ax.text(bax + 2, bay + bah + 0.7, "主要指数の騰落率 (%)",
                color=MUTED, fontsize=8.5, va="center", zorder=4)

        center_y  = bay + bah / 2
        max_pct   = 3.0
        bar_scale = (bah * 0.44) / max_pct
        bspacing  = baw / 6
        bw_bar    = bspacing * 0.55

        ax.plot([bax + 1, bax + baw - 1], [center_y, center_y],
                color=BORDER, lw=0.8, zorder=3)

        for i, (chg, lbl) in enumerate(zip(tile_chgs, _TILE_SHORT)):
            bx = bax + bspacing * i + bspacing / 2 - bw_bar / 2
            if chg is not None and chg != 0:
                bh = min(abs(chg) * bar_scale, bah * 0.44)
                by = center_y if chg > 0 else center_y - bh
                bc = GREEN if chg > 0 else RED
                rr(bx, by, bw_bar, bh, bc, rad=0.4, lw=0, z=4)
                offset = bh + 1.3
                va     = "bottom" if chg > 0 else "top"
                ty     = center_y + offset if chg > 0 else center_y - offset
                ax.text(bx + bw_bar / 2, ty, f"{chg:+.2f}",
                        color=bc, fontsize=7.5, ha="center", va=va, zorder=5)
            ax.text(bx + bw_bar / 2, bay + 0.5, lbl,
                    color=MUTED, fontsize=8, ha="center", va="bottom", zorder=5)

        # ─── ⑤ AI 3視点分析 ──────────────────────────────────────────
        aiy, aih = 34.0, 13.0
        rr(4, aiy, 92, aih, PANEL, ec=BORDER, lw=0.8)
        ax.text(6, aiy + aih - 1.8, "🤖 AI 3視点分析",
                color=MUTED, fontsize=9.5, va="center", zorder=4)

        bull = _clip(ai_summary.get("bull_view", ""), 28)
        bear = _clip(ai_summary.get("bear_view", ""), 28)
        neut = _clip(ai_summary.get("neutral_view", ""), 28)

        point_rows = [
            ("●", "地合い", GREEN, bull or "データなし"),
            ("▲", "注意点", AMBER, bear or "データなし"),
            ("◆", "方針",   BLUE,  neut or "データなし"),
        ]
        ry = aiy + aih - 4.5
        for icon, lbl, c, txt in point_rows:
            ax.text(7, ry, icon, color=c, fontsize=10, va="center", zorder=4)
            ax.text(11, ry, lbl, color=c, fontsize=9.5,
                    fontweight="bold", va="center", zorder=4)
            ax.text(22, ry, txt, color=WHITE, fontsize=9, va="center", zorder=4)
            ry -= 3.5

        # ─── ⑥ 注目ニュース ──────────────────────────────────────────
        ny_top = aiy - 1.0
        ny_h   = ny_top - 3.0
        rr(4, 3.0, 92, ny_h, PANEL, ec=BORDER, lw=0.8)
        ax.text(6, ny_top - 1.8, "📰 注目ニュース",
                color=MUTED, fontsize=9.5, va="center", zorder=4)

        news_items = news[:3]
        nry = ny_top - 5.0
        for item in news_items:
            title = _clip(item.get("title", ""), 30)
            ax.text(7, nry, "・", color=ACCENT, fontsize=11,
                    va="center", zorder=4)
            ax.text(11, nry, title, color=WHITE, fontsize=9,
                    va="center", zorder=4)
            nry -= 4.0

        if not news_items:
            ax.text(7, nry, "ニュースデータなし", color=MUTED,
                    fontsize=9, va="center", zorder=4)

        out = get_dirs()["charts"] / f"summary_card_{get_today_str()}.png"
        plt.savefig(str(out), dpi=160, facecolor=BG, edgecolor="none",
                    bbox_inches="tight")
        plt.close(fig)
        logger.info(f"✅ サマリーカード生成: {out}")
        return str(out)

    except Exception as e:
        logger.error(f"summary_card エラー: {e}")
        logger.debug(traceback.format_exc())
        try:
            plt.close("all")
        except Exception:
            pass
        return None
