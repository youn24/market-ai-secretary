"""
チャート生成モジュール（初心者向けビジュアル重視）
ダークテーマ・大きな文字・わかりやすいラベル付き
"""
import os, traceback
from pathlib import Path
from src.utils import setup_logger, get_dirs, get_today_str

logger = setup_logger("visualize")

# ─────────────────────────────────────────────────────────────
# カラーパレット
# ─────────────────────────────────────────────────────────────
BG      = "#0d1117"
CARD    = "#161b22"
BORDER  = "#30363d"
UP      = "#3fb950"
DOWN    = "#f85149"
NEUTRAL = "#8b949e"
ACCENT  = "#58a6ff"
GOLD    = "#f0c060"
TEXT    = "#e6edf3"
TEXT2   = "#8b949e"


def _font_setup():
    try:
        import matplotlib
        matplotlib.rcParams.update({
            "font.family": ["Noto Sans CJK JP","IPAexGothic","Hiragino Sans",
                            "Meiryo","Yu Gothic","sans-serif"],
        })
        import japanize_matplotlib  # noqa
    except Exception:
        pass


def _draw_gauge(ax, value: float, title: str, subtitle: str = ""):
    """半円ゲージ（0-100）を描画するヘルパー"""
    try:
        import matplotlib.patches as mpatches
        import numpy as np

        ax.set_facecolor(CARD)
        ax.set_xlim(-1.3, 1.3)
        ax.set_ylim(-0.3, 1.3)
        ax.axis("off")

        # 背景弧（5段階カラー）
        colors = ["#7c4dff","#2196f3","#8bc34a","#ff9800","#f44336"]
        for i, c in enumerate(colors):
            theta1 = 180 - i * 36
            theta2 = 180 - (i + 1) * 36
            arc = mpatches.Arc((0, 0), 2, 2, angle=0,
                               theta1=theta2, theta2=theta1,
                               color=c, lw=16, zorder=1)
            ax.add_patch(arc)

        # 針
        angle_rad = __import__("numpy").deg2rad(180 - (value / 100) * 180)
        ax.annotate("", xy=(0.75 * __import__("numpy").cos(angle_rad),
                              0.75 * __import__("numpy").sin(angle_rad)),
                    xytext=(0, 0),
                    arrowprops=dict(arrowstyle="-|>", color="white", lw=2.5,
                                   mutation_scale=15))
        # 中心ドット
        circle = mpatches.Circle((0, 0), 0.12, color=CARD, zorder=5)
        ax.add_patch(circle)

        ax.text(0, 0.55, f"{value:.0f}", ha="center", va="center",
                fontsize=20, fontweight="bold", color=TEXT, zorder=6)
        ax.text(0, 0.32, title, ha="center", va="center",
                fontsize=9, color=TEXT2, zorder=6)
        if subtitle:
            ax.text(0, -0.18, subtitle, ha="center", va="center",
                    fontsize=7.5, color=TEXT2)
        ax.text(-1.1, -0.1, "低/恐怖", ha="center", fontsize=7, color=TEXT2)
        ax.text( 1.1, -0.1, "高/強欲", ha="center", fontsize=7, color=TEXT2)

    except Exception as e:
        logger.debug(f"_draw_gauge: {e}")


def chart_overview(prices: dict, news: list, risk: dict, fear_greed: dict):
    """メインダッシュボード画像（全情報を1枚に）"""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        import numpy as np
        _font_setup()

        fig = plt.figure(figsize=(14, 16), facecolor=BG)
        fig.patch.set_facecolor(BG)

        gs = fig.add_gridspec(5, 4, hspace=0.55, wspace=0.35,
                              left=0.05, right=0.97, top=0.93, bottom=0.04)

        today     = get_today_str()
        score     = risk.get("score", 0)
        sentiment = risk.get("sentiment", "不明")
        fg_score  = fear_greed.get("score") or 50
        s_color   = UP if score >= 1 else DOWN if score <= -1 else NEUTRAL

        fig.text(0.5, 0.965, f"📊 市場AI秘書ダッシュボード  {today}",
                 ha="center", fontsize=18, fontweight="bold", color=TEXT)
        fig.text(0.5, 0.945, f"地合い: {sentiment}  スコア: {score:+.2f}  Fear&Greed: {fg_score:.0f}",
                 ha="center", fontsize=11, color=TEXT2)

        # ── 1行目: 株価指数カード ──
        idx_list = [
            ("^N225",  "🇯🇵 日経平均",  "円"),
            ("^GSPC",  "🇺🇸 S&P500",    ""),
            ("^IXIC",  "🇺🇸 NASDAQ",    ""),
            ("^DJI",   "🇺🇸 ダウ",       ""),
        ]
        for col, (sym, label, unit) in enumerate(idx_list):
            ax = fig.add_subplot(gs[0, col])
            d   = prices.get(sym, {})
            val = d.get("latest")
            chg = d.get("change_pct") or 0
            color = UP if chg >= 0 else DOWN
            val_str = f"{val:,.0f}{unit}" if val else "---"
            chg_str = f"{'▲' if chg>=0 else '▼'} {abs(chg):.2f}%"
            ax.set_facecolor(f"{color}15")
            for sp in ax.spines.values(): sp.set_color(BORDER)
            ax.text(0.5, 0.72, label,   ha="center", va="center",
                    transform=ax.transAxes, fontsize=9, color=TEXT2)
            ax.text(0.5, 0.45, val_str, ha="center", va="center",
                    transform=ax.transAxes, fontsize=13, fontweight="bold", color=TEXT)
            ax.text(0.5, 0.18, chg_str, ha="center", va="center",
                    transform=ax.transAxes, fontsize=11, fontweight="bold", color=color)
            ax.set_xticks([]); ax.set_yticks([])

        # ── 2行目: コモディティカード ──
        cmd_list = [
            ("USDJPY=X", "💵 ドル円",     "円"),
            ("GC=F",     "🥇 金 GOLD",    "$"),
            ("CL=F",     "🛢 原油 WTI",   "$"),
            ("BTC-USD",  "₿ Bitcoin",     "$"),
        ]
        for col, (sym, label, unit) in enumerate(cmd_list):
            ax = fig.add_subplot(gs[1, col])
            d   = prices.get(sym, {})
            val = d.get("latest")
            chg = d.get("change_pct") or 0
            color = UP if chg >= 0 else DOWN
            if val:
                val_str = f"{val:,.0f}{unit}" if val > 9999 else f"{val:,.2f}{unit}"
            else:
                val_str = "---"
            chg_str = f"{'▲' if chg>=0 else '▼'} {abs(chg):.2f}%"
            ax.set_facecolor(f"{color}15")
            for sp in ax.spines.values(): sp.set_color(BORDER)
            ax.text(0.5, 0.72, label,   ha="center", va="center",
                    transform=ax.transAxes, fontsize=9, color=TEXT2)
            ax.text(0.5, 0.45, val_str, ha="center", va="center",
                    transform=ax.transAxes, fontsize=12, fontweight="bold", color=TEXT)
            ax.text(0.5, 0.18, chg_str, ha="center", va="center",
                    transform=ax.transAxes, fontsize=11, fontweight="bold", color=color)
            ax.set_xticks([]); ax.set_yticks([])

        # ── 3行目左3: 前日比バーチャート ──
        ax_bar = fig.add_subplot(gs[2, :3])
        ax_bar.set_facecolor(CARD)
        for sp in ax_bar.spines.values(): sp.set_color(BORDER)
        bsyms  = ["^N225","^GSPC","^IXIC","^DJI","USDJPY=X","GC=F","BTC-USD","^VIX"]
        blabs  = ["日経","S&P","NDX","DOW","ドル円","金","BTC","VIX"]
        bvals  = [prices.get(s,{}).get("change_pct") or 0 for s in bsyms]
        bcolors= [UP if v >= 0 else DOWN for v in bvals]
        x = np.arange(len(blabs))
        bars = ax_bar.bar(x, bvals, color=bcolors, alpha=0.85, width=0.65, zorder=3,
                          edgecolor=BG, linewidth=0.5)
        ax_bar.axhline(0, color=BORDER, linewidth=1.2, zorder=2)
        ax_bar.set_xticks(x); ax_bar.set_xticklabels(blabs, color=TEXT, fontsize=10)
        ax_bar.set_ylabel("前日比 (%)", color=TEXT2, fontsize=9)
        ax_bar.tick_params(colors=TEXT2)
        ax_bar.set_title("📉 主要指標の前日比", color=TEXT, fontsize=11, pad=6, loc="left")
        ax_bar.grid(axis="y", color=BORDER, linewidth=0.5, zorder=0)
        for bar, val in zip(bars, bvals):
            y_pos = val + (0.05 if val >= 0 else -0.08)
            ax_bar.text(bar.get_x() + bar.get_width()/2, y_pos,
                        f"{val:+.1f}%", ha="center",
                        va="bottom" if val>=0 else "top",
                        fontsize=8, color=TEXT, fontweight="bold")

        # ── 3行目右1: F&G ゲージ ──
        ax_fg = fig.add_subplot(gs[2, 3])
        ax_fg.set_aspect("equal")
        _draw_gauge(ax_fg, fg_score, "Fear &\nGreed", "恐怖←→強欲")

        # ── 4行目左2: リスクメーター ──
        ax_risk = fig.add_subplot(gs[3, :2])
        ax_risk.set_aspect("equal")
        risk_pct = min(max((score + 5) / 10 * 100, 0), 100)
        _draw_gauge(ax_risk, risk_pct, "リスク\nメーター", "弱気←→強気")

        # ── 4行目右2: ニュース ──
        ax_news = fig.add_subplot(gs[3, 2:])
        ax_news.set_facecolor(CARD)
        for sp in ax_news.spines.values(): sp.set_color(BORDER)
        ax_news.set_xticks([]); ax_news.set_yticks([])
        ax_news.set_title("📰 重要ニュース", color=TEXT, fontsize=10, pad=6, loc="left")
        sorted_news = sorted(news, key=lambda n: {"A":0,"B":1,"C":2}.get(n.get("importance","C"),2))
        nc = {"A":DOWN,"B":GOLD,"C":TEXT2}
        for i, item in enumerate(sorted_news[:6]):
            t  = item.get("title","")[:38]
            c  = nc.get(item.get("importance","C"), TEXT2)
            px = "🔴" if item.get("importance")=="A" else "🟡" if item.get("importance")=="B" else "⚪"
            ax_news.text(0.02, 0.90 - i*0.15, f"{px} {t}",
                         transform=ax_news.transAxes, fontsize=8,
                         color=c, va="top", clip_on=True)

        # ── 5行目: VIX・金利・ユーロ・恒生 ──
        extras = [
            ("^VIX",   "😰 VIX恐怖指数", "",  "20超=危険/15未満=安定"),
            ("^TNX",   "📊 米10年金利",   "%", "上昇=株に逆風"),
            ("EURUSD=X","💶 EUR/USD",     "",  "欧米の力関係"),
            ("^HSI",   "🇨🇳 香港ハンセン","",  "中国市況"),
        ]
        for col, (sym, label, unit, hint) in enumerate(extras):
            ax = fig.add_subplot(gs[4, col])
            d   = prices.get(sym, {})
            val = d.get("latest")
            chg = d.get("change_pct") or 0
            color = UP if chg >= 0 else DOWN
            val_str = f"{val:,.2f}{unit}" if val else "---"
            if val and val > 1000: val_str = f"{val:,.0f}{unit}"
            chg_str = f"{'▲' if chg>=0 else '▼'} {abs(chg):.2f}%"
            ax.set_facecolor(CARD)
            for sp in ax.spines.values(): sp.set_color(BORDER)
            ax.text(0.5, 0.80, label,   ha="center", transform=ax.transAxes, fontsize=8,  color=TEXT2)
            ax.text(0.5, 0.50, val_str, ha="center", transform=ax.transAxes, fontsize=12, fontweight="bold", color=TEXT)
            ax.text(0.5, 0.26, chg_str, ha="center", transform=ax.transAxes, fontsize=10, fontweight="bold", color=color)
            ax.text(0.5, 0.07, hint,    ha="center", transform=ax.transAxes, fontsize=7,  color=TEXT2, style="italic")
            ax.set_xticks([]); ax.set_yticks([])

        out = get_dirs()["charts"] / f"overview_{today}.png"
        plt.savefig(str(out), dpi=130, bbox_inches="tight",
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
        fig, ax = plt.subplots(figsize=(8, 5), facecolor=BG)
        fig.patch.set_facecolor(BG)
        fg_score  = fear_greed.get("score") or 50
        fg_rating = fear_greed.get("rating_ja", "---")
        _draw_gauge(ax, fg_score, f"{fg_score:.0f}", fg_rating)
        ax.set_title("😱 Fear & Greed Index\n（0=超恐怖 ← → 100=超強欲）",
                     color=TEXT, fontsize=12, pad=12)
        out = get_dirs()["charts"] / f"fear_greed_{get_today_str()}.png"
        plt.savefig(str(out), dpi=120, bbox_inches="tight", facecolor=BG, edgecolor="none")
        plt.close(fig)
        return str(out)
    except Exception as e:
        logger.error(f"chart_fear_greed エラー: {e}"); return None


def chart_risk_meter(risk: dict):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        _font_setup()
        fig, ax = plt.subplots(figsize=(8, 5), facecolor=BG)
        fig.patch.set_facecolor(BG)
        score = risk.get("score", 0)
        pct   = min(max((score + 5) / 10 * 100, 0), 100)
        _draw_gauge(ax, pct, f"{score:+.2f}", risk.get("sentiment","---"))
        ax.set_title("🌡 市場リスクメーター\n（弱気 ← → 強気）",
                     color=TEXT, fontsize=12, pad=12)
        out = get_dirs()["charts"] / f"risk_meter_{get_today_str()}.png"
        plt.savefig(str(out), dpi=120, bbox_inches="tight", facecolor=BG, edgecolor="none")
        plt.close(fig)
        return str(out)
    except Exception as e:
        logger.error(f"chart_risk_meter エラー: {e}"); return None


def run(prices: dict, news: list, risk: dict, fear_greed: dict) -> dict:
    logger.info("=== チャート生成開始 ===")
    chart_paths = {}
    ov = chart_overview(prices, news, risk, fear_greed)
    if ov: chart_paths["overview"] = ov
    fg = chart_fear_greed(fear_greed)
    if fg: chart_paths["fear_greed"] = fg
    rm = chart_risk_meter(risk)
    if rm: chart_paths["risk_meter"] = rm
    logger.info(f"チャート完了: {len(chart_paths)}件")
    return chart_paths
