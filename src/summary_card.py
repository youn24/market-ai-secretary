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

# ── パレット（design_system が唯一の真実・HTMLレポートと同一トーン）──────
try:
    from src.design_system import get_theme as _get_theme
    _T = _get_theme("dark")
except Exception:
    _T = {}
BG_TOP = "#0a1020"      # 上部グラデ（画像専用の演出）
BG_BOT = _T.get("bg", "#05080f")
CARD   = _T.get("surface", "#141c2b")
CARD2  = "#0f1623"
PANEL  = _T.get("surface2", "#0d1422")
BORDER = _T.get("border", "#243044")
WHITE  = _T.get("text", "#eef4fb")
MUTED  = _T.get("text_muted", "#8a96a8")
GREEN  = _T.get("up", "#21d07a")
RED    = _T.get("down", "#ff5470")
AMBER  = _T.get("warn", "#ffc857")
BLUE   = _T.get("info", "#5bc0ff")
ACCENT = _T.get("accent", "#7aa2ff")
GOLD   = "#ffd45e"      # ガネ先生の金アクセント（キャラ専用色）

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


def _make_card_matplotlib(prices: dict, fear_greed: dict, risk: dict,
                          ai_summary: dict = None, news: list = None) -> str | None:
    """サマリーカードPNGを生成してパスを返す。失敗時 None。（matplotlibフォールバック）"""
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


# ══════════════════════════════════════════════════════════════════════════
# HTML → PNG（Playwright）版：Canva級デザインの主経路
# ══════════════════════════════════════════════════════════════════════════

CARD_W = 760  # 描画幅（device_scale_factor=2 で実質1520px・くっきり）

_H_TILES = [
    ("^N225",    "日経平均",  "",  0, "🇯🇵"),
    ("^GSPC",    "S&P500",   "",  0, "🇺🇸"),
    ("^IXIC",    "NASDAQ",   "",  0, "💻"),
    ("USDJPY=X", "ドル円",   "円", 2, "💴"),
    ("^VIX",     "VIX",      "",  1, "😨"),
    ("BTC-USD",  "BTC",      "$", 0, "₿"),
]


def _h_sent(score):
    if   score >= 2:   return GREEN, "強気", "買い優勢・上昇トレンド"
    elif score >= 0.5: return GREEN, "やや強気", "やや買い優勢"
    elif score >= -0.5:return AMBER, "中立", "方向感なし・様子見"
    elif score >= -2:  return RED,   "やや弱気", "やや売り優勢"
    else:              return RED,   "弱気", "売り優勢・要警戒"


def _char_section(character_comments: dict) -> str:
    """ガネーシャ🐘＆カワウソ🦦を分析・要約のサイドに配置するセクション"""
    cc = character_comments or {}
    ganesha = (cc.get("ganesha") or "").strip()
    otter   = (cc.get("otter") or "").strip()
    # コメントが無い日もキャラクターは必ず登場させる（デザイン重視）
    if not ganesha:
        ganesha = "市場の流れを読み解いておりますぞ。焦らず、大局を見るのが知恵の第一歩ですぞ。"
    if not otter:
        otter = "きょうもデータをチェックしたよ〜！ムリせずコツコツが いちばんだよ🌊"

    try:
        from src.design_ai import _GANESHA_SVG, _OTTER_SVG
    except Exception:
        return ""

    return f"""
  <div class="panel" style="padding:15px 15px 13px">
    <div class="ptitle">🐘🦦 AIキャラクター解説</div>

    <div class="chrow chrow-g">
      <div class="chava">
        {_GANESHA_SVG}
        <div class="chname" style="color:#FFD700">ガネーシャ</div>
      </div>
      <div class="chbub">
        <span class="chbadge" style="color:#FFD700;background:rgba(255,215,0,.12);border-color:rgba(255,215,0,.32)">📜 プロの相場解説</span>
        <div class="chtxt">{ganesha}</div>
      </div>
    </div>

    <div class="chrow chrow-o" style="margin-bottom:0">
      <div class="chava">
        {_OTTER_SVG}
        <div class="chname" style="color:#C4956A">カワウソ</div>
      </div>
      <div class="chbub">
        <span class="chbadge" style="color:#C4956A;background:rgba(196,149,106,.13);border-color:rgba(196,149,106,.34)">✨ カンタンまとめ</span>
        <div class="chtxt">{otter}</div>
      </div>
    </div>
  </div>"""


def _build_card_html(prices, fear_greed, risk, ai_summary, news,
                     character_comments=None) -> str:
    n = get_jst_now()
    wd = _WEEKDAYS_JA[n.weekday()]
    date_s = f"{n.strftime('%Y.%m.%d')}（{wd}）"

    score = risk.get("score", 0)
    sent_c, sent, sent_sub = _h_sent(score)

    fg_n = int(fear_greed.get("score") or 50)
    if   fg_n >= 75: fg_c, fg_lbl = GOLD,  "超強欲"
    elif fg_n >= 55: fg_c, fg_lbl = GREEN, "強欲"
    elif fg_n >= 45: fg_c, fg_lbl = ACCENT, "中立"
    elif fg_n >= 25: fg_c, fg_lbl = AMBER, "恐怖"
    else:            fg_c, fg_lbl = RED,   "超恐怖"

    # ── 6タイル ──
    tiles = ""
    for sym, label, unit, dp, icon in _H_TILES:
        d   = prices.get(sym, {})
        val = d.get("latest")
        chg = d.get("change_pct")
        c   = GREEN if (chg or 0) >= 0 else RED
        val_s = "---" if val is None else (f"{unit}{val:,.0f}" if dp == 0 else f"{unit}{val:,.{dp}f}")
        if chg is None:
            chg_s, chg_c = "—", MUTED
        else:
            chg_s = f"{'▲' if chg>=0 else '▼'} {abs(chg):.2f}%"
            chg_c = c
        tiles += f"""
      <div class="tile">
        <div class="tile-bar" style="background:{c}"></div>
        <div class="tile-lbl">{icon} {label}</div>
        <div class="tile-val">{val_s}</div>
        <div class="tile-chg" style="color:{chg_c}">{chg_s}</div>
      </div>"""

    # ── 騰落バー ──
    bars = ""
    short = ["日経", "S&P", "NDX", "ドル円", "VIX", "BTC"]
    for (sym, *_), nm in zip(_H_TILES, short):
        chg = prices.get(sym, {}).get("change_pct")
        if chg is None:
            h, bc, lbl = 0, MUTED, "—"
        else:
            h = min(abs(chg) / 3.0 * 100, 100)
            bc = GREEN if chg >= 0 else RED
            lbl = f"{chg:+.1f}"
        up = chg is None or chg >= 0
        bars += f"""
        <div class="bcol">
          <div class="bval" style="color:{bc}">{lbl}</div>
          <div class="btrack"><div class="bfill" style="height:{h:.0f}%;background:{bc};{'align-self:flex-end' if not up else ''}"></div></div>
          <div class="bnm">{nm}</div>
        </div>"""

    # ── AI 3視点 ──
    def _clip2(t, k):
        t = (t or "").replace("\n", " ").strip()
        return (t[:k] + "…") if len(t) > k else (t or "データなし")
    ai_rows = ""
    for icon, lbl, c, key in [("▲", "強気", GREEN, "bull_view"),
                               ("▼", "弱気", RED, "bear_view"),
                               ("◆", "中立", BLUE, "neutral_view")]:
        ai_rows += f"""
        <div class="airow">
          <span class="aichip" style="color:{c};background:{c}22;border:1px solid {c}55">{icon} {lbl}</span>
          <span class="aitxt">{_clip2(ai_summary.get(key, ''), 30)}</span>
        </div>"""

    # ── ニュース ──
    news_html = ""
    nv = [x for x in (news or []) if isinstance(x, dict) and x.get("title")][:3]
    for it in nv:
        imp = it.get("importance", "C")
        dot = {"A": RED, "B": AMBER, "C": ACCENT}.get(imp if isinstance(imp, str) else "C", ACCENT)
        title = (it.get("title", "")[:34]).replace("<", "").replace(">", "")
        news_html += f"""
        <div class="nrow"><span class="ndot" style="background:{dot}"></span><span class="ntxt">{title}</span></div>"""
    if not news_html:
        news_html = '<div class="nrow"><span class="ntxt" style="color:#8a96a8">ニュースデータなし</span></div>'

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700;900&family=Outfit:wght@500;700;800;900&display=swap" rel="stylesheet">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
.num{{font-family:'Outfit','Noto Sans JP',sans-serif;font-variant-numeric:tabular-nums;letter-spacing:-.5px}}
body{{font-family:'Noto Sans JP','Outfit',sans-serif}}
#card{{position:relative;width:{CARD_W}px;padding:26px 24px 20px;overflow:hidden;
  background:
    radial-gradient(60% 40% at 15% 0%, rgba(176,110,255,.18), transparent 60%),
    radial-gradient(60% 45% at 100% 25%, rgba(0,180,255,.15), transparent 60%),
    radial-gradient(70% 50% at 60% 110%, rgba(0,255,135,.10), transparent 60%),
    linear-gradient(165deg,#0b1322 0%,#070a12 55%,#05070d 100%);
  color:#eef4fb}}
.head{{display:flex;justify-content:space-between;align-items:center;margin-bottom:18px}}
.brand{{display:flex;align-items:center;gap:11px}}
.logo{{width:40px;height:40px;border-radius:11px;display:grid;place-items:center;font-size:20px;
  background:linear-gradient(135deg,#b06eff,#00b4ff);box-shadow:0 6px 18px rgba(176,110,255,.35)}}
.bname{{font-family:'Outfit','Noto Sans JP';font-size:21px;font-weight:900;line-height:1.05}}
.bsub{{font-size:12px;color:#8a96a8;margin-top:1px}}
.date{{font-size:13px;color:#8a96a8;font-weight:600}}

.topgrid{{display:grid;grid-template-columns:1.55fr 1fr;gap:12px;margin-bottom:13px}}
.card{{background:linear-gradient(160deg,rgba(255,255,255,.06),rgba(255,255,255,.02));
  border:1px solid rgba(255,255,255,.10);border-radius:16px;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.06),0 8px 26px rgba(0,0,0,.35)}}
.sent{{padding:16px 18px;position:relative;overflow:hidden;border-color:{sent_c}44}}
.sent::after{{content:"";position:absolute;top:-30px;right:-30px;width:120px;height:120px;border-radius:50%;
  background:radial-gradient(circle,{sent_c}33,transparent 70%)}}
.lbl{{font-size:11px;font-weight:700;letter-spacing:1.4px;color:#8a96a8;text-transform:uppercase}}
.sent-v{{font-family:'Outfit','Noto Sans JP';font-size:34px;font-weight:900;color:{sent_c};line-height:1.1;margin-top:4px}}
.sent-s{{font-size:12px;color:#8a96a8;margin-top:3px}}
.fg{{padding:16px 16px;text-align:center}}
.fg-n{{font-size:40px;font-weight:900;color:{fg_c};line-height:1}}
.fg-track{{height:7px;border-radius:5px;background:#1b2433;margin:9px 2px 6px;overflow:hidden}}
.fg-fill{{height:100%;width:{fg_n}%;background:{fg_c};border-radius:5px}}
.fg-l{{font-size:12px;font-weight:800;color:{fg_c}}}

.tiles{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:9px;margin-bottom:13px}}
.tile{{background:linear-gradient(160deg,rgba(255,255,255,.055),rgba(255,255,255,.02));
  border:1px solid rgba(255,255,255,.09);border-radius:14px;padding:13px 13px 11px;position:relative;overflow:hidden}}
.tile-bar{{position:absolute;top:0;left:0;width:100%;height:3px;opacity:.9}}
.tile-lbl{{font-size:12px;color:#8a96a8;font-weight:600;margin-bottom:5px}}
.tile-val{{font-family:'Outfit','Noto Sans JP';font-size:23px;font-weight:900;font-variant-numeric:tabular-nums;letter-spacing:-.5px;line-height:1}}
.tile-chg{{font-size:13px;font-weight:800;margin-top:4px}}

.panel{{background:linear-gradient(160deg,rgba(255,255,255,.05),rgba(255,255,255,.018));
  border:1px solid rgba(255,255,255,.09);border-radius:16px;padding:15px 17px;margin-bottom:12px;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.05)}}
.ptitle{{font-size:14px;font-weight:800;margin-bottom:12px;display:flex;align-items:center;gap:7px}}
.ptitle::before{{content:"";width:4px;height:15px;border-radius:3px;background:linear-gradient(180deg,#b06eff,#00b4ff)}}

.bars{{display:flex;justify-content:space-between;align-items:flex-end;gap:8px;height:96px}}
.bcol{{flex:1;display:flex;flex-direction:column;align-items:center;height:100%}}
.bval{{font-family:'Outfit';font-size:12px;font-weight:800;margin-bottom:4px}}
.btrack{{flex:1;width:60%;display:flex;align-items:flex-end;justify-content:center}}
.bfill{{width:100%;border-radius:5px;min-height:3px}}
.bnm{{font-size:11px;color:#8a96a8;margin-top:6px}}

.airow{{display:flex;align-items:center;gap:10px;padding:7px 0;border-bottom:1px solid rgba(255,255,255,.06)}}
.airow:last-child{{border-bottom:none}}
.aichip{{font-size:12px;font-weight:800;padding:3px 11px;border-radius:9px;white-space:nowrap;min-width:62px;text-align:center}}
.aitxt{{font-size:13px;color:#eef4fb}}

.chrow{{display:flex;align-items:stretch;gap:12px;border-radius:14px;padding:11px 13px;margin-bottom:10px;overflow:hidden}}
.chrow-g{{background:linear-gradient(135deg,#1c1600,#271e00);border:1px solid rgba(255,215,0,.24)}}
.chrow-o{{background:linear-gradient(135deg,#160e09,#1f130c);border:1px solid rgba(196,149,106,.26)}}
.chava{{width:82px;flex-shrink:0;display:flex;flex-direction:column;align-items:center;justify-content:center}}
.chava svg{{filter:drop-shadow(0 4px 10px rgba(0,0,0,.45))}}
.chname{{font-size:11px;font-weight:800;margin-top:4px;white-space:nowrap}}
.chbub{{flex:1;min-width:0;display:flex;flex-direction:column;justify-content:center}}
.chbadge{{font-size:10.5px;font-weight:800;letter-spacing:.6px;border:1px solid;border-radius:11px;padding:2px 10px;display:inline-block;margin-bottom:7px;align-self:flex-start}}
.chtxt{{font-size:13px;line-height:1.85;color:#eef4fb;word-break:break-word}}

.nrow{{display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid rgba(255,255,255,.06)}}
.nrow:last-child{{border-bottom:none}}
.ndot{{width:9px;height:9px;border-radius:50%;flex-shrink:0;box-shadow:0 0 8px currentColor}}
.ntxt{{font-size:13px;color:#eef4fb}}
.foot{{text-align:center;font-size:11px;color:#5a6a85;margin-top:6px}}
</style></head><body>
<div id="card">
  <div class="head">
    <div class="brand">
      <div class="logo">📊</div>
      <div><div class="bname">市場AI秘書</div><div class="bsub">朝のサマリー</div></div>
    </div>
    <div class="date">{date_s}</div>
  </div>

  <div class="topgrid">
    <div class="card sent">
      <div class="lbl">本日の地合い</div>
      <div class="sent-v">{sent}</div>
      <div class="sent-s">{sent_sub}　AIスコア {score:+.1f}</div>
    </div>
    <div class="card fg">
      <div class="lbl">恐怖＆強欲</div>
      <div class="num fg-n">{fg_n}</div>
      <div class="fg-track"><div class="fg-fill"></div></div>
      <div class="fg-l">{fg_lbl}</div>
    </div>
  </div>

  <div class="tiles">{tiles}</div>

  <div class="panel">
    <div class="ptitle">📊 主要指数の騰落率 (%)</div>
    <div class="bars">{bars}</div>
  </div>

  <div class="panel">
    <div class="ptitle">🤖 AI 3視点分析</div>
    {ai_rows}
  </div>

  {_char_section(character_comments)}

  <div class="panel">
    <div class="ptitle">📰 注目ニュース</div>
    {news_html}
  </div>

  <div class="foot">youn24.github.io/market-ai-secretary</div>
</div>
</body></html>"""


def _render_card_playwright(html: str, out_path: str) -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("playwright 未インストール → matplotlibフォールバック")
        return False
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox"])
            page = browser.new_page(
                viewport={"width": CARD_W, "height": 1200},
                device_scale_factor=2,
            )
            page.set_content(html, wait_until="networkidle")
            page.locator("#card").screenshot(path=out_path)
            browser.close()
        return True
    except Exception as e:
        logger.warning(f"Playwright描画失敗（フォールバックへ）: {e}")
        return False


def make_summary_card(prices: dict, fear_greed: dict, risk: dict,
                      ai_summary: dict = None, news: list = None,
                      character_comments: dict = None) -> str | None:
    """
    サマリーカードPNGを生成してパスを返す。
    主経路: HTML→PNG（Playwright・Canva級デザイン・ガネーシャ＆カワウソ入り）
    保険  : matplotlib 版（_make_card_matplotlib）
    """
    prices     = prices or {}
    fear_greed = fear_greed or {}
    risk       = risk or {}
    ai_summary = ai_summary or {}

    out = get_dirs()["charts"] / f"summary_card_{get_today_str()}.png"
    try:
        html = _build_card_html(prices, fear_greed, risk, ai_summary, news,
                                character_comments=character_comments)
        if _render_card_playwright(html, str(out)):
            logger.info(f"✅ サマリーカード生成（HTML→PNG）: {out}")
            return str(out)
    except Exception as e:
        logger.warning(f"HTMLカード生成失敗（フォールバックへ）: {e}")
        logger.debug(traceback.format_exc())

    return _make_card_matplotlib(prices, fear_greed, risk, ai_summary, news)
