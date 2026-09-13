"""
チャート生成モジュール（プレミアムデザイン版）
iPhone / Telegram 向けに最適化された見やすいビジュアル
"""
import os
import traceback
from pathlib import Path
from src.utils import setup_logger, get_dirs, get_today_str

logger = setup_logger("visualize")

# ─────────────────────────────────────────────────────────────
# カラーパレット（ダークプレミアム）
# ─────────────────────────────────────────────────────────────
BG      = "#07111e"   # 最暗背景
CARD    = "#0d1f33"   # カード背景
CARD2   = "#112540"   # カード背景2
BORDER  = "#1e3a5a"   # 枠線
UP      = "#00e676"   # 上昇（緑）
UP2     = "#00c853"
DOWN    = "#ff4444"   # 下落（赤）
DOWN2   = "#dd2200"
NEUTRAL = "#8899bb"
ACCENT  = "#00d4ff"   # アクセント（水色）
GOLD    = "#ffd740"   # 重要（金）
TEXT    = "#e8f4ff"
TEXT2   = "#6a8eae"
PURPLE  = "#bb86fc"


def _font_setup():
    try:
        import matplotlib
        matplotlib.rcParams.update({
            "font.family": ["Noto Sans CJK JP", "IPAexGothic", "Hiragino Sans",
                            "Meiryo", "Yu Gothic", "sans-serif"],
            "axes.unicode_minus": False,
        })
        import japanize_matplotlib  # noqa
    except Exception:
        pass


def _add_glow_rect(ax, x, y, w, h, color, alpha=0.12, radius=0.015):
    """グロー付き角丸矩形を描画"""
    try:
        from matplotlib.patches import FancyBboxPatch
        # 外側グロー
        glow = FancyBboxPatch((x - 0.003, y - 0.003), w + 0.006, h + 0.006,
                              boxstyle=f"round,pad=0", linewidth=0,
                              facecolor=color, alpha=alpha * 0.5,
                              transform=ax.transAxes, zorder=1)
        ax.add_patch(glow)
        # 本体
        rect = FancyBboxPatch((x, y), w, h,
                              boxstyle=f"round,pad=0", linewidth=1,
                              facecolor=CARD2, edgecolor=f"{color}66",
                              transform=ax.transAxes, zorder=2)
        ax.add_patch(rect)
    except Exception:
        pass


def _draw_premium_gauge(ax, value: float, label: str, sub: str = ""):
    """プレミアムデザインの半円ゲージ"""
    try:
        import numpy as np
        import matplotlib.patches as mpatches
        from matplotlib.patches import Arc, FancyBboxPatch

        ax.set_facecolor(CARD)
        ax.set_xlim(-1.4, 1.4)
        ax.set_ylim(-0.5, 1.4)
        ax.axis("off")

        # 背景トラック
        track = Arc((0, 0), 2.2, 2.2, angle=0, theta1=0, theta2=180,
                    color=BORDER, lw=14, zorder=1)
        ax.add_patch(track)

        # グラデーション弧（5色セグメント）
        seg_colors = ["#7c4dff", "#2196f3", "#00e676", "#ff9800", "#f44336"]
        for i, c in enumerate(seg_colors):
            t1 = i * 36
            t2 = (i + 1) * 36
            arc = Arc((0, 0), 2.2, 2.2, angle=0,
                      theta1=t1, theta2=t2,
                      color=c, lw=14, zorder=2, alpha=0.9)
            ax.add_patch(arc)

        # 現在値マーカー（白い点）
        angle_rad = np.deg2rad((value / 100) * 180)
        mx = 1.1 * np.cos(angle_rad)
        my = 1.1 * np.sin(angle_rad)
        ax.plot(mx, my, "o", color="white", ms=10, zorder=6,
                markeredgecolor=BG, markeredgewidth=2)

        # 針（細い三角矢印）
        ax.annotate("", xy=(0.78 * np.cos(angle_rad), 0.78 * np.sin(angle_rad)),
                    xytext=(0, 0),
                    arrowprops=dict(arrowstyle="-|>", color="white", lw=2.2,
                                   mutation_scale=18),
                    zorder=5)

        # 中央ドット
        dot = mpatches.Circle((0, 0), 0.13, color=CARD, zorder=7)
        ax.add_patch(dot)
        dot2 = mpatches.Circle((0, 0), 0.07, color=ACCENT, zorder=8)
        ax.add_patch(dot2)

        # 中央数値
        ax.text(0, 0.48, f"{value:.0f}",
                ha="center", va="center", fontsize=26, fontweight="bold",
                color=TEXT, zorder=9)
        ax.text(0, 0.22, label,
                ha="center", va="center", fontsize=10, color=TEXT2, zorder=9)
        if sub:
            ax.text(0, -0.25, sub,
                    ha="center", va="center", fontsize=9,
                    color=GOLD, fontweight="bold", zorder=9)

        # 端ラベル
        ax.text(-1.3, -0.15, "恐怖\n0", ha="center", fontsize=7.5, color=TEXT2)
        ax.text(1.3,  -0.15, "強欲\n100", ha="center", fontsize=7.5, color=TEXT2)

    except Exception as e:
        logger.debug(f"_draw_premium_gauge: {e}")


def chart_overview(prices: dict, news: list, risk: dict, fear_greed: dict):
    """プレミアムダッシュボード画像"""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        import numpy as np
        _font_setup()

        today    = get_today_str()
        score    = risk.get("score", 0)
        sent     = risk.get("sentiment", "不明")
        fg_score = float(fear_greed.get("score") or 50)
        fg_lbl   = fear_greed.get("rating_ja", "---")

        # ヒーローカラー
        if score >= 2:
            hero_c = UP;      hero_lbl = "強気相場 🚀"
        elif score >= 0.5:
            hero_c = UP;      hero_lbl = "やや強気 😊"
        elif score >= -0.5:
            hero_c = GOLD;    hero_lbl = "中立 😐"
        elif score >= -2:
            hero_c = "#ff9800"; hero_lbl = "やや弱気 😟"
        else:
            hero_c = DOWN;    hero_lbl = "弱気相場 😱"

        fig = plt.figure(figsize=(14, 18), facecolor=BG)
        fig.patch.set_facecolor(BG)

        gs = fig.add_gridspec(
            6, 4,
            hspace=0.55, wspace=0.28,
            left=0.03, right=0.97,
            top=0.94, bottom=0.02
        )

        # ────── ヘッダー ──────────────────────────────────────────
        fig.text(0.5, 0.968,
                 f"📊  市場AI秘書  |  {today}",
                 ha="center", fontsize=20, fontweight="bold", color=TEXT)

        # 地合いバナー
        ax_hero = fig.add_axes([0.03, 0.920, 0.94, 0.038])
        ax_hero.set_facecolor(f"{hero_c}22")
        ax_hero.set_xlim(0, 1); ax_hero.set_ylim(0, 1)
        ax_hero.axis("off")
        ax_hero.axhline(0, color=hero_c, lw=2)
        ax_hero.axhline(1, color=hero_c, lw=2)
        ax_hero.text(0.5, 0.5,
                     f"今日の相場：{hero_lbl}   |   リスクスコア {score:+.2f}   |   F&G {fg_score:.0f} ({fg_lbl})",
                     ha="center", va="center", fontsize=11,
                     color=hero_c, fontweight="bold")

        # ── 1行目: 株価指数 4枚カード ──────────────────────────────
        idx_list = [
            ("^N225",  "🇯🇵 日経平均",  "円", "日本株の代表"),
            ("^GSPC",  "🇺🇸 S&P 500",   "",   "米500社平均"),
            ("^IXIC",  "🇺🇸 NASDAQ",    "",   "米テック中心"),
            ("^DJI",   "🇺🇸 ダウ平均",  "",   "米30社老舗指数"),
        ]
        for col, (sym, label, unit, hint) in enumerate(idx_list):
            ax = fig.add_subplot(gs[0, col])
            d    = prices.get(sym, {})
            val  = d.get("latest")
            chg  = d.get("change_pct") or 0
            c    = UP if chg >= 0 else DOWN
            arrow = "▲" if chg >= 0 else "▼"
            val_s = f"{val:,.0f}{unit}" if val else "---"
            if val and val < 100: val_s = f"{val:.2f}{unit}"

            ax.set_facecolor(f"{c}0d")
            for sp in ax.spines.values():
                sp.set_color(f"{c}55"); sp.set_linewidth(1.2)
            ax.tick_params(left=False, bottom=False,
                           labelleft=False, labelbottom=False)

            # ラベル
            ax.text(0.5, 0.87, label, ha="center", va="center",
                    transform=ax.transAxes, fontsize=9, color=TEXT2)
            # 数値（大きく）
            ax.text(0.5, 0.56, val_s, ha="center", va="center",
                    transform=ax.transAxes, fontsize=15, fontweight="black",
                    color=TEXT)
            # 騰落
            ax.text(0.5, 0.28, f"{arrow} {abs(chg):.2f}%", ha="center", va="center",
                    transform=ax.transAxes, fontsize=13, fontweight="bold", color=c)
            # ヒント
            ax.text(0.5, 0.08, hint, ha="center", va="center",
                    transform=ax.transAxes, fontsize=7.5, color=TEXT2, style="italic")

        # ── 2行目: 為替・商品 4枚カード ──────────────────────────────
        fx_list = [
            ("USDJPY=X", "💵 ドル/円",      "円", "円安なら輸出に有利"),
            ("GC=F",     "🥇 金(ゴールド)", "$",  "不安時に上がる安全資産"),
            ("CL=F",     "🛢 原油 WTI",     "$",  "エネルギーコスト"),
            ("BTC-USD",  "₿ ビットコイン",  "$",  "仮想通貨代表"),
        ]
        for col, (sym, label, unit, hint) in enumerate(fx_list):
            ax = fig.add_subplot(gs[1, col])
            d   = prices.get(sym, {})
            val = d.get("latest")
            chg = d.get("change_pct") or 0
            c   = UP if chg >= 0 else DOWN
            arrow = "▲" if chg >= 0 else "▼"
            if val is None:   val_s = "---"
            elif val > 9999:  val_s = f"{val:,.0f}{unit}"
            elif val > 99:    val_s = f"{val:,.2f}{unit}"
            else:             val_s = f"{val:.4f}{unit}"

            ax.set_facecolor(f"{c}0d")
            for sp in ax.spines.values():
                sp.set_color(f"{c}55"); sp.set_linewidth(1.2)
            ax.tick_params(left=False, bottom=False,
                           labelleft=False, labelbottom=False)
            ax.text(0.5, 0.87, label, ha="center", va="center",
                    transform=ax.transAxes, fontsize=9, color=TEXT2)
            ax.text(0.5, 0.56, val_s, ha="center", va="center",
                    transform=ax.transAxes, fontsize=14, fontweight="black", color=TEXT)
            ax.text(0.5, 0.28, f"{arrow} {abs(chg):.2f}%", ha="center", va="center",
                    transform=ax.transAxes, fontsize=12, fontweight="bold", color=c)
            ax.text(0.5, 0.08, hint, ha="center", va="center",
                    transform=ax.transAxes, fontsize=7.5, color=TEXT2, style="italic")

        # ── 3行目: 前日比バーチャート (3コル) + VIXカード (1コル) ──
        ax_bar = fig.add_subplot(gs[2, :3])
        ax_bar.set_facecolor(CARD)
        for sp in ax_bar.spines.values():
            sp.set_color(BORDER); sp.set_linewidth(0.8)
        ax_bar.tick_params(colors=TEXT2, labelsize=10)

        b_syms  = ["^N225","^GSPC","^IXIC","^DJI","USDJPY=X","GC=F","CL=F","BTC-USD"]
        b_labs  = ["日経", "S&P", "NDX", "ダウ", "ドル円", "金", "原油", "BTC"]
        b_vals  = [prices.get(s, {}).get("change_pct") or 0 for s in b_syms]
        b_colors = [UP if v >= 0 else DOWN for v in b_vals]
        x = np.arange(len(b_labs))

        bars = ax_bar.bar(x, b_vals, color=b_colors, alpha=0.85, width=0.6,
                          zorder=3, edgecolor=BG, linewidth=0.5)
        ax_bar.axhline(0, color=BORDER, lw=1.0, zorder=2)
        ax_bar.set_xticks(x)
        ax_bar.set_xticklabels(b_labs, color=TEXT, fontsize=10.5, fontweight="bold")
        ax_bar.set_ylabel("前日比 (%)", color=TEXT2, fontsize=9)
        ax_bar.set_title("📊 主要指標の前日比（%）",
                         color=ACCENT, fontsize=11, pad=8, loc="left",
                         fontweight="bold")
        ax_bar.grid(axis="y", color=BORDER, linewidth=0.5, alpha=0.7, zorder=0)
        ax_bar.set_facecolor(CARD)

        # バーに数値ラベル
        for bar, val, c in zip(bars, b_vals, b_colors):
            offset = 0.04 if val >= 0 else -0.06
            va_s   = "bottom" if val >= 0 else "top"
            ax_bar.text(bar.get_x() + bar.get_width() / 2, val + offset,
                        f"{val:+.2f}%", ha="center", va=va_s,
                        fontsize=8.5, color=c, fontweight="bold")

        # VIXカード
        ax_vix = fig.add_subplot(gs[2, 3])
        d_vix  = prices.get("^VIX", {})
        vix    = d_vix.get("latest") or 0
        vix_c  = DOWN if vix >= 30 else "#ff9800" if vix >= 20 else GOLD if vix >= 15 else UP
        vix_lbl = "危険！" if vix >= 30 else "警戒" if vix >= 20 else "注意" if vix >= 15 else "安定"
        ax_vix.set_facecolor(f"{vix_c}15")
        for sp in ax_vix.spines.values():
            sp.set_color(f"{vix_c}66"); sp.set_linewidth(1.5)
        ax_vix.tick_params(left=False, bottom=False,
                           labelleft=False, labelbottom=False)
        ax_vix.text(0.5, 0.82, "😰 VIX 恐怖指数", ha="center",
                    transform=ax_vix.transAxes, fontsize=9, color=TEXT2)
        ax_vix.text(0.5, 0.52, f"{vix:.1f}", ha="center",
                    transform=ax_vix.transAxes, fontsize=28, fontweight="black", color=vix_c)
        ax_vix.text(0.5, 0.24, vix_lbl, ha="center",
                    transform=ax_vix.transAxes, fontsize=13, fontweight="bold", color=vix_c)
        ax_vix.text(0.5, 0.06, "20超=警戒 / 30超=危険",
                    ha="center", transform=ax_vix.transAxes, fontsize=7.5, color=TEXT2)

        # ── 4行目: F&G ゲージ(2) + リスクメーター(2) ──────────────
        ax_fg = fig.add_subplot(gs[3, :2])
        ax_fg.set_facecolor(CARD)
        ax_fg.axis("off")
        _draw_premium_gauge(ax_fg, fg_score, "Fear & Greed Index", fg_lbl)
        ax_fg.set_title("😱 恐怖と強欲指数",
                        color=ACCENT, fontsize=11, pad=8, loc="center",
                        fontweight="bold")

        ax_rm = fig.add_subplot(gs[3, 2:])
        ax_rm.set_facecolor(CARD)
        ax_rm.axis("off")
        risk_pct = min(max((score + 5) / 10 * 100, 0), 100)
        _draw_premium_gauge(ax_rm, risk_pct, "市場リスクメーター", sent)
        ax_rm.set_title("🌡 地合いスコア",
                        color=ACCENT, fontsize=11, pad=8, loc="center",
                        fontweight="bold")

        # ── 5行目: 追加指標 4枚 ──────────────────────────────────
        extras = [
            ("^TNX",    "📊 米10年金利",  "%",  "上昇=株に逆風"),
            ("EURUSD=X","💶 EUR/USD",     "",   "欧米の力関係"),
            ("^HSI",    "🇨🇳 香港ハンセン","",   "中国市況"),
            ("ETH-USD", "⟠ イーサリアム", "$",  "仮想通貨2位"),
        ]
        for col, (sym, lbl, unit, hint) in enumerate(extras):
            ax = fig.add_subplot(gs[4, col])
            d   = prices.get(sym, {})
            val = d.get("latest")
            chg = d.get("change_pct") or 0
            c   = UP if chg >= 0 else DOWN
            if val is None:  vs = "---"
            elif val > 9999: vs = f"{val:,.0f}{unit}"
            elif val > 99:   vs = f"{val:,.2f}{unit}"
            else:            vs = f"{val:.4f}{unit}"
            arrow = "▲" if chg >= 0 else "▼"

            ax.set_facecolor(CARD)
            for sp in ax.spines.values():
                sp.set_color(BORDER); sp.set_linewidth(0.8)
            ax.tick_params(left=False, bottom=False,
                           labelleft=False, labelbottom=False)
            ax.text(0.5, 0.84, lbl, ha="center", transform=ax.transAxes,
                    fontsize=9, color=TEXT2)
            ax.text(0.5, 0.52, vs, ha="center", transform=ax.transAxes,
                    fontsize=13, fontweight="bold", color=TEXT)
            ax.text(0.5, 0.26, f"{arrow} {abs(chg):.2f}%", ha="center",
                    transform=ax.transAxes, fontsize=11, fontweight="bold", color=c)
            ax.text(0.5, 0.07, hint, ha="center", transform=ax.transAxes,
                    fontsize=7.5, color=TEXT2, style="italic")

        # ── 6行目: ニュース一覧 ───────────────────────────────────
        ax_n = fig.add_subplot(gs[5, :])
        ax_n.set_facecolor(CARD)
        for sp in ax_n.spines.values():
            sp.set_color(BORDER); sp.set_linewidth(0.8)
        ax_n.set_xticks([]); ax_n.set_yticks([])
        ax_n.set_title("📰 注目ニュース（重要度順）",
                       color=ACCENT, fontsize=11, pad=8, loc="left",
                       fontweight="bold")

        sorted_news = sorted(news,
                             key=lambda n: {"A": 0, "B": 1, "C": 2}.get(
                                 n.get("importance", "C"), 2))
        imp_icon = {"A": "🔴", "B": "🟡", "C": "⚪"}
        imp_color = {"A": DOWN, "B": GOLD, "C": TEXT2}

        # 2列レイアウト
        max_per_col = 5
        for i, item in enumerate(sorted_news[:10]):
            col_x = 0.02 if i < max_per_col else 0.52
            row_y = 0.88 - (i % max_per_col) * 0.175
            imp  = item.get("importance", "C")
            icon = imp_icon.get(imp, "⚪")
            clr  = imp_color.get(imp, TEXT2)
            cat  = item.get("category", "")
            title = item.get("title", "")[:44]
            ax_n.text(col_x, row_y,
                      f"{icon} [{cat}] {title}",
                      transform=ax_n.transAxes, fontsize=8.5,
                      color=clr, va="top", clip_on=True)

        # ── フッター ──────────────────────────────────────────────
        fig.text(0.5, 0.008,
                 f"市場AI秘書  |  {today}  |  GitHub Actions 自動生成  |  Powered by Gemini AI",
                 ha="center", fontsize=8, color=TEXT2)

        out = get_dirs()["charts"] / f"overview_{today}.png"
        plt.savefig(str(out), dpi=150, bbox_inches="tight",
                    facecolor=BG, edgecolor="none")
        plt.close(fig)
        logger.info(f"✅ overview: {out}")
        return str(out)

    except Exception as e:
        logger.error(f"chart_overview エラー: {e}")
        logger.debug(traceback.format_exc())
        return None


def chart_fear_greed(fear_greed: dict):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        _font_setup()

        fg_score  = float(fear_greed.get("score") or 50)
        fg_rating = fear_greed.get("rating_ja", "---")

        if fg_score >= 75:   fg_c, fg_e = DOWN,    "😱 超強欲"
        elif fg_score >= 55: fg_c, fg_e = "#ff9800","😤 強欲"
        elif fg_score >= 45: fg_c, fg_e = GOLD,     "😐 中立"
        elif fg_score >= 25: fg_c, fg_e = ACCENT,   "😰 恐怖"
        else:                fg_c, fg_e = PURPLE,   "😭 超恐怖"

        fig, ax = plt.subplots(figsize=(8, 5), facecolor=BG)
        fig.patch.set_facecolor(BG)
        ax.set_facecolor(BG)
        _draw_premium_gauge(ax, fg_score, f"Score: {fg_score:.0f}", fg_e)
        ax.set_title(f"😱 Fear & Greed Index  ─  {fg_rating}",
                     color=fg_c, fontsize=14, pad=10, fontweight="bold")

        out = get_dirs()["charts"] / f"fear_greed_{get_today_str()}.png"
        plt.savefig(str(out), dpi=130, bbox_inches="tight",
                    facecolor=BG, edgecolor="none")
        plt.close(fig)
        return str(out)
    except Exception as e:
        logger.error(f"chart_fear_greed エラー: {e}")
        return None


def chart_risk_meter(risk: dict):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        _font_setup()

        score = risk.get("score", 0)
        pct   = min(max((score + 5) / 10 * 100, 0), 100)
        sent  = risk.get("sentiment", "---")

        if score >= 2:    rm_c = UP;       rm_e = "🚀 強気相場"
        elif score >= 0.5: rm_c = UP;       rm_e = "😊 やや強気"
        elif score >= -0.5: rm_c = GOLD;    rm_e = "😐 中立"
        elif score >= -2:  rm_c = "#ff9800"; rm_e = "😟 やや弱気"
        else:              rm_c = DOWN;     rm_e = "😱 弱気相場"

        fig, ax = plt.subplots(figsize=(8, 5), facecolor=BG)
        fig.patch.set_facecolor(BG)
        ax.set_facecolor(BG)
        _draw_premium_gauge(ax, pct, f"{score:+.2f}", rm_e)
        ax.set_title(f"🌡 市場リスクメーター  ─  {sent}",
                     color=rm_c, fontsize=14, pad=10, fontweight="bold")

        out = get_dirs()["charts"] / f"risk_meter_{get_today_str()}.png"
        plt.savefig(str(out), dpi=130, bbox_inches="tight",
                    facecolor=BG, edgecolor="none")
        plt.close(fig)
        return str(out)
    except Exception as e:
        logger.error(f"chart_risk_meter エラー: {e}")
        return None


def run(prices: dict, news: list, risk: dict, fear_greed: dict) -> dict:
    logger.info("=== チャート生成開始（プレミアムデザイン）===")
    chart_paths = {}
    ov = chart_overview(prices, news, risk, fear_greed)
    if ov: chart_paths["overview"] = ov
    fg = chart_fear_greed(fear_greed)
    if fg: chart_paths["fear_greed"] = fg
    rm = chart_risk_meter(risk)
    if rm: chart_paths["risk_meter"] = rm
    logger.info(f"チャート完了: {len(chart_paths)}件")
    return chart_paths
