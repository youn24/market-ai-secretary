"""
朝イチ・サマリーカード画像生成（プロ級デザイン版）
- グラデーション背景 ＋ グロー演出 ＋ 地合いバッジ ＋ 6指標タイル
  ＋ ミニ棒グラフ ＋ AI3視点 ＋ 注目ニュース
- Telegram の最初のメッセージとして送る「一目でわかるカード」
"""
import matplotlib
matplotlib.use("Agg")
import numpy as np
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

# ── パレット（深いネイビー基調＋ネオンアクセント）──────────────────────
BG_TOP = "#0a1020"      # 上部グラデ
BG_BOT = "#05080f"      # 下部グラデ
CARD   = "#141c2b"
CARD2  = "#0f1623"
PANEL  = "#0d1422"
BORDER = "#243044"
WHITE  = "#eef4fb"
MUTED  = "#8a96a8"
GREEN  = "#21d07a"
RED    = "#ff5470"
AMBER  = "#ffc857"
BLUE   = "#5bc0ff"
ACCENT = "#7aa2ff"
GOLD   = "#ffd45e"

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
    wd = _WEEKDAYS_JA[n.weekday()]
    return f"{n.strftime('%Y.%m.%d')}（{wd}）  朝のサマリー"


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


def _hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) / 255 for i in (0, 2, 4))


def make_summary_card(prices: dict, fear_greed: dict, risk: dict,
                      ai_summary: dict = None, news: list = None) -> str | None:
    """サマリーカードPNGを生成してパスを返す。失敗時 None。"""
    try:
        prices     = prices or {}
        fear_greed = fear_greed or {}
        risk       = risk or {}
        ai_summary = ai_summary or {}
        news       = [n for n in (news or []) if isinstance(n, dict) and n.get("title")]

        fig = plt.figure(figsize=(7.5, 11.0), facecolor=BG_BOT)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(0, 100)
        ax.set_ylim(0, 100)
        ax.axis("off")

        # ─── 背景：縦グラデーション ───────────────────────────────────
        grad = np.linspace(0, 1, 256).reshape(-1, 1)
        c_top, c_bot = np.array(_hex_rgb(BG_TOP)), np.array(_hex_rgb(BG_BOT))
        grad_rgb = c_bot + (c_top - c_bot) * grad  # 下→上
        grad_img = np.repeat(grad_rgb[:, np.newaxis, :], 2, axis=1)
        ax.imshow(grad_img, extent=[0, 100, 0, 100], aspect="auto", zorder=0)

        # 上部のソフトなアクセントグロー
        gx = np.linspace(0, 100, 120)
        gy = np.linspace(0, 100, 120)
        GXm, GYm = np.meshgrid(gx, gy)
        glow = np.exp(-(((GXm - 22) ** 2) / 900 + ((GYm - 97) ** 2) / 120))
        ax.imshow(glow, extent=[0, 100, 0, 100], aspect="auto",
                  cmap="Blues", alpha=0.10, zorder=0)

        def rr(x, y, w, h, fc, ec=None, lw=1.0, rad=1.8, z=2, alpha=1.0):
            ax.add_patch(FancyBboxPatch(
                (x, y), w, h,
                boxstyle=f"round,pad=0,rounding_size={rad}",
                facecolor=fc, edgecolor=(ec or fc), linewidth=lw,
                zorder=z, alpha=alpha,
            ))

        def glow_box(x, y, w, h, color, rad=1.8, z=2, layers=4):
            """枠の外側に薄いグローを重ねる"""
            for k in range(layers, 0, -1):
                pad = k * 0.55
                rr(x - pad, y - pad, w + 2 * pad, h + 2 * pad, "none",
                   ec=color, lw=1.0, rad=rad + pad, z=z, alpha=0.05 * k)

        # ─── ① ヘッダー ──────────────────────────────────────────────
        ax.text(4, 97.4, "🤖 市場AI秘書", color=WHITE, fontsize=16,
                fontweight="bold", va="center", zorder=4)
        rr(4, 95.6, 13, 0.45, ACCENT, rad=0.2, z=4)  # アクセント下線
        ax.text(96, 97.4, _now_label(), color=MUTED, fontsize=9.5,
                ha="right", va="center", zorder=4)
        ax.plot([4, 96], [94.6, 94.6], color=BORDER, lw=0.8, zorder=3)

        # ─── ② 地合いバッジ（左）＋ 恐怖指数（右）───────────────────
        sent    = risk.get("sentiment", "不明")
        sent_c  = _SENT_COLOR.get(sent, MUTED)
        score_v = risk.get("score", 0)
        if score_v >= 1.0:    sent_sub = "買い優勢・上昇トレンド"
        elif score_v >= 0.3:  sent_sub = "やや買い優勢"
        elif score_v >= -0.3: sent_sub = "方向感なし・様子見"
        elif score_v >= -1.0: sent_sub = "やや売り優勢"
        else:                 sent_sub = "売り優勢・要警戒"

        glow_box(4, 82.8, 56, 10.5, sent_c, rad=2.0, z=2)
        rr(4, 82.8, 56, 10.5, CARD, ec=sent_c, lw=1.6, z=3)
        rr(4, 82.8, 2.2, 10.5, sent_c, rad=0.8, z=4)
        ax.text(9, 91.0, "本日の地合い", color=MUTED, fontsize=9.5, va="center", zorder=5)
        ax.text(9, 87.0, sent, color=sent_c, fontsize=19,
                fontweight="bold", va="center", zorder=5)
        ax.text(9, 83.9, sent_sub, color=MUTED, fontsize=8.5, va="center", zorder=5)

        fg_n = fear_greed.get("score")
        fg_n = int(fg_n) if fg_n is not None else 50
        if   fg_n >= 75: fg_c, fg_lbl = GOLD,  "超強欲"
        elif fg_n >= 55: fg_c, fg_lbl = GREEN, "強欲"
        elif fg_n >= 45: fg_c, fg_lbl = ACCENT, "中立"
        elif fg_n >= 25: fg_c, fg_lbl = AMBER, "恐怖"
        else:            fg_c, fg_lbl = RED,   "超恐怖"

        rr(62, 82.8, 34, 10.5, CARD2, ec=BORDER, lw=1.0, z=3)
        ax.text(79, 91.2, "恐怖＆強欲指数", color=MUTED, fontsize=8.5,
                ha="center", va="center", zorder=5)
        ax.text(75.5, 86.6, str(fg_n), color=fg_c, fontsize=23,
                fontweight="bold", ha="center", va="center", zorder=5)
        ax.text(85, 86.6, "/100", color=MUTED, fontsize=9,
                ha="center", va="center", zorder=5)
        # ミニゲージ
        gauge_x, gauge_w = 65.5, 27
        rr(gauge_x, 83.6, gauge_w, 0.9, "#1b2433", rad=0.45, z=4)
        rr(gauge_x, 83.6, gauge_w * (fg_n / 100), 0.9, fg_c, rad=0.45, z=5)
        ax.text(79, 84.9, fg_lbl, color=fg_c, fontsize=8.5,
                ha="center", va="center", fontweight="bold", zorder=5)

        # ─── ③ 6タイル（3列×2行）────────────────────────────────────
        gx0, gw, ggap   = 4, 29.8, 1.3
        gy_top, gh, gvg = 80.5, 9.8, 1.3
        tile_chgs = []

        for i, (sym, label, unit, dp) in enumerate(_TILES):
            col = i % 3
            row = i // 3
            x = gx0 + col * (gw + ggap)
            y = gy_top - 10.0 - row * (gh + gvg)
            d   = prices.get(sym, {})
            val = d.get("latest")
            chg = d.get("change_pct")
            tile_chgs.append(chg)
            c   = _tile_color(chg)

            rr(x, y, gw, gh, CARD2, ec=BORDER, lw=0.8, z=3)
            rr(x, y, gw, 0.5, c, rad=0.25, z=4)  # 上部アクセントライン
            rr(x + 0.6, y + 0.9, 1.0, gh - 1.8, c, rad=0.4, z=4, alpha=0.5)
            ax.text(x + 3.2, y + gh - 2.1, label, color=MUTED, fontsize=9.5,
                    va="center", zorder=5)
            ax.text(x + 3.2, y + gh - 5.9, _fmt_val(val, unit, dp),
                    color=WHITE, fontsize=14.5, fontweight="bold", va="center", zorder=5)
            if chg is not None:
                arrow = "▲" if chg >= 0 else "▼"
                ax.text(x + 3.2, y + 1.9, f"{arrow} {abs(chg):.2f}%",
                        color=c, fontsize=10, fontweight="bold", va="center", zorder=5)
            else:
                ax.text(x + 3.2, y + 1.9, "—", color=MUTED, fontsize=9,
                        va="center", zorder=5)

        # ─── ④ ミニ棒グラフ ──────────────────────────────────────────
        bax, bay, baw, bah = 4, 46.5, 92, 11.0
        rr(bax, bay, baw, bah + 1.8, PANEL, ec=BORDER, lw=0.8, z=3)
        ax.text(bax + 2.5, bay + bah + 0.9, "📊 主要指数の騰落率 (%)",
                color=WHITE, fontsize=9.5, fontweight="bold", va="center", zorder=5)

        center_y  = bay + bah / 2 - 0.5
        max_pct   = 3.0
        bar_scale = (bah * 0.40) / max_pct
        bspacing  = baw / 6
        bw_bar    = bspacing * 0.50

        ax.plot([bax + 2, bax + baw - 2], [center_y, center_y],
                color=BORDER, lw=0.9, zorder=4)

        for i, (chg, lbl) in enumerate(zip(tile_chgs, _TILE_SHORT)):
            bx = bax + bspacing * i + bspacing / 2 - bw_bar / 2
            if chg is not None and chg != 0:
                bh = min(abs(chg) * bar_scale, bah * 0.40)
                by = center_y if chg > 0 else center_y - bh
                bc = GREEN if chg > 0 else RED
                rr(bx, by, bw_bar, bh, bc, rad=0.5, lw=0, z=5)
                offset = bh + 1.3
                va     = "bottom" if chg > 0 else "top"
                ty     = center_y + offset if chg > 0 else center_y - offset
                ax.text(bx + bw_bar / 2, ty, f"{chg:+.2f}",
                        color=bc, fontsize=8, fontweight="bold",
                        ha="center", va=va, zorder=6)
            ax.text(bx + bw_bar / 2, bay + 0.6, lbl,
                    color=MUTED, fontsize=8.5, ha="center", va="bottom", zorder=6)

        # ─── ⑤ AI 3視点分析 ──────────────────────────────────────────
        aiy, aih = 32.5, 13.2
        rr(4, aiy, 92, aih, PANEL, ec=BORDER, lw=0.8, z=3)
        rr(4, aiy + aih - 0.5, 92, 0.5, ACCENT, rad=0.25, z=4, alpha=0.6)
        ax.text(6.5, aiy + aih - 2.0, "🤖 AI 3視点分析",
                color=WHITE, fontsize=9.5, fontweight="bold", va="center", zorder=5)

        bull = _clip(ai_summary.get("bull_view", ""), 26)
        bear = _clip(ai_summary.get("bear_view", ""), 26)
        neut = _clip(ai_summary.get("neutral_view", ""), 26)

        point_rows = [
            ("▲", "強気", GREEN, bull or "データなし"),
            ("▼", "弱気", RED,   bear or "データなし"),
            ("◆", "中立", BLUE,  neut or "データなし"),
        ]
        ry = aiy + aih - 5.2
        for icon, lbl, c, txt in point_rows:
            rr(6.5, ry - 1.1, 8.5, 2.4, c, rad=0.6, z=4, alpha=0.16)
            ax.text(8.0, ry, icon, color=c, fontsize=9, va="center", zorder=5)
            ax.text(11.0, ry, lbl, color=c, fontsize=9,
                    fontweight="bold", va="center", zorder=5)
            ax.text(17.5, ry, txt, color=WHITE, fontsize=9, va="center", zorder=5)
            ry -= 3.5

        # ─── ⑥ 注目ニュース ──────────────────────────────────────────
        ny_top = aiy - 1.2
        ny_h   = ny_top - 3.0
        rr(4, 3.0, 92, ny_h, PANEL, ec=BORDER, lw=0.8, z=3)
        ax.text(6.5, ny_top - 2.0, "📰 注目ニュース",
                color=WHITE, fontsize=9.5, fontweight="bold", va="center", zorder=5)

        news_items = news[:3]
        nry = ny_top - 5.6
        for item in news_items:
            title = _clip(item.get("title", ""), 29)
            imp   = item.get("importance", "C")
            dot_c = {"A": RED, "B": AMBER, "C": ACCENT}.get(imp, ACCENT)
            ax.scatter([7.5], [nry], s=42, color=dot_c, zorder=5,
                       edgecolors="none")
            ax.text(10.5, nry, title, color=WHITE, fontsize=9.2,
                    va="center", zorder=5)
            nry -= 4.2

        if not news_items:
            ax.text(7.5, nry, "ニュースデータなし", color=MUTED,
                    fontsize=9, va="center", zorder=5)

        # フッター
        ax.text(50, 1.2, "youn24.github.io/market-ai-secretary",
                color=MUTED, fontsize=7.5, ha="center", va="center", zorder=5)

        out = get_dirs()["charts"] / f"summary_card_{get_today_str()}.png"
        plt.savefig(str(out), dpi=170, facecolor=BG_BOT, edgecolor="none",
                    bbox_inches="tight", pad_inches=0.15)
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
