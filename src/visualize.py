"""
チャート生成モジュール（高品質ダッシュボード版）
Telegram送信用の美しいビジュアライズ
"""
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
import matplotlib.patheffects as pe
import numpy as np

from src.utils import get_today_str, get_dirs, setup_logger

warnings.filterwarnings("ignore")
logger = setup_logger("visualize")

plt.rcParams["font.family"] = ["MS Gothic", "Meiryo", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# ━━━━ カラーパレット ━━━━
BG         = "#0d1117"   # 背景（ダーク）
CARD_BG    = "#161b22"   # カード背景
BORDER     = "#30363d"   # ボーダー
UP_COLOR   = "#3fb950"   # 上昇（緑）
DOWN_COLOR = "#f85149"   # 下落（赤）
NEUTRAL_C  = "#8b949e"   # 中立（グレー）
GOLD       = "#d4a017"   # ゴールド
ACCENT     = "#58a6ff"   # アクセント（青）
TEXT_MAIN  = "#e6edf3"   # メインテキスト
TEXT_SUB   = "#8b949e"   # サブテキスト
GRID_C     = "#21262d"   # グリッド


def _c(val):
    if val is None: return NEUTRAL_C
    return UP_COLOR if val >= 0 else DOWN_COLOR


def _add_watermark(fig):
    fig.text(0.99, 0.005, "⚠️ 分析補助 / 投資助言ではありません",
             ha="right", va="bottom", fontsize=7, color="#444c56",
             style="italic")


def _fmt(v, unit=""):
    if v is None: return "---"
    if abs(v) >= 1_000_000: return f"{v/1_000_000:.2f}M{unit}"
    if abs(v) >= 1_000:     return f"{v:,.0f}{unit}"
    return f"{v:.2f}{unit}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# メインダッシュボード（1枚画像）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def chart_overview(prices: dict, risk: dict, fear_greed: dict, news: list) -> Path | None:
    """全情報を1枚に集約したメインダッシュボード"""
    today = get_today_str()
    fig = plt.figure(figsize=(18, 14), facecolor=BG)
    fig.patch.set_facecolor(BG)

    gs = gridspec.GridSpec(4, 4, figure=fig,
                           hspace=0.55, wspace=0.4,
                           left=0.05, right=0.97, top=0.93, bottom=0.06)

    # ── タイトルバー ──
    fig.text(0.5, 0.965, f"📊  市場AI秘書  ダッシュボード  |  {today}",
             ha="center", fontsize=18, fontweight="bold",
             color=TEXT_MAIN, va="top")
    fig.text(0.5, 0.945, "⚠️ 投資助言ではありません  |  分析補助レポート",
             ha="center", fontsize=9, color=TEXT_SUB, va="top")

    # ── 行0: 指数カード（4枚）──
    index_cards = [
        ("^N225",   "🇯🇵 日経平均", "円"),
        ("^GSPC",   "🇺🇸 S&P500",   ""),
        ("^IXIC",   "🇺🇸 NASDAQ",   ""),
        ("USDJPY=X","💵 ドル円",    "円"),
    ]
    for col, (sym, label, unit) in enumerate(index_cards):
        ax = fig.add_subplot(gs[0, col])
        ax.set_facecolor(CARD_BG)
        for sp in ax.spines.values():
            sp.set_color(BORDER); sp.set_linewidth(1.2)
        p   = prices.get(sym, {})
        val = p.get("latest")
        chg = p.get("change_pct")
        col_c = _c(chg)
        sign  = "▲" if (chg or 0) >= 0 else "▼"
        ax.text(0.5, 0.82, label, ha="center", fontsize=10,
                color=TEXT_SUB, transform=ax.transAxes)
        ax.text(0.5, 0.50, _fmt(val, unit), ha="center", fontsize=17,
                color=TEXT_MAIN, fontweight="bold", transform=ax.transAxes)
        ax.text(0.5, 0.18, f"{sign}{abs(chg):.2f}%" if chg else "---",
                ha="center", fontsize=13, color=col_c, fontweight="bold",
                transform=ax.transAxes)
        ax.set_xlim(0,1); ax.set_ylim(0,1)
        ax.set_xticks([]); ax.set_yticks([])
        # 下線（色付き）
        ax.axhline(0.05, color=col_c, lw=3, alpha=0.8)

    # ── 行1左: 主要指数 横棒グラフ ──
    ax_bar = fig.add_subplot(gs[1, :2])
    ax_bar.set_facecolor(CARD_BG)
    for sp in ax_bar.spines.values(): sp.set_color(BORDER)
    targets = [
        ("^N225","日経"), ("^GSPC","S&P"), ("^IXIC","NASDAQ"),
        ("^DJI","ダウ"), ("^VIX","VIX"), ("^TNX","米10Y"),
    ]
    names = [t[1] for t in targets]
    vals  = [prices.get(t[0], {}).get("change_pct") or 0 for t in targets]
    colors= [_c(v) for v in vals]
    bars  = ax_bar.barh(names, vals, color=colors, height=0.55,
                         edgecolor=BORDER, linewidth=0.8)
    ax_bar.axvline(0, color=BORDER, lw=1.5)
    ax_bar.set_facecolor(CARD_BG)
    ax_bar.grid(axis="x", color=GRID_C, lw=0.6, alpha=0.5)
    ax_bar.set_axisbelow(True)
    for i, v in enumerate(vals):
        s = "▲" if v >= 0 else "▼"
        ax_bar.text(v + (0.03 if v >= 0 else -0.03), i,
                    f"{s}{abs(v):.2f}%", va="center",
                    ha="left" if v >= 0 else "right",
                    fontsize=9, color=_c(v), fontweight="bold")
    ax_bar.set_title("主要指数  前日比", fontsize=11, fontweight="bold",
                     color=TEXT_MAIN, pad=8)
    ax_bar.invert_yaxis()
    ax_bar.tick_params(colors=TEXT_SUB, labelsize=9)
    ax_bar.set_facecolor(CARD_BG)

    # ── 行1右: Fear & Greed ゲージ ──
    ax_fg = fig.add_subplot(gs[1, 2:], projection="polar")
    ax_fg.set_facecolor(BG)
    _draw_gauge(ax_fg, fig,
                score=fear_greed.get("score"),
                rating=fear_greed.get("rating_ja","---"),
                prev=fear_greed.get("prev_score"),
                title="CNN Fear & Greed",
                zone_colors=["#f85149","#ff8c42","#e3b341","#3fb950","#2ea043"],
                zone_labels=["極度\n恐怖","恐怖","中立","強欲","極度\n強欲"],
                text_x=0.75, text_y_base=0.62, fig_ref=fig, gs_pos=gs[1,2:])

    # ── 行2左: コモディティ ──
    ax_com = fig.add_subplot(gs[2, :2])
    ax_com.set_facecolor(CARD_BG)
    for sp in ax_com.spines.values(): sp.set_color(BORDER)
    com_targets = [
        ("GC=F","🥇 金(GOLD)","#d4a017"),
        ("CL=F","🛢 WTI原油","#5c8a5c"),
        ("BTC-USD","₿ Bitcoin","#f7931a"),
        ("EURUSD=X","💶 EUR/USD","#58a6ff"),
    ]
    for i, (sym, name, accent) in enumerate(com_targets):
        p   = prices.get(sym, {})
        val = p.get("latest")
        chg = p.get("change_pct")
        cc  = _c(chg)
        x   = 0.12 + i * 0.24
        ax_com.text(x, 0.78, name, ha="center", fontsize=9,
                    color=accent, fontweight="bold", transform=ax_com.transAxes)
        ax_com.text(x, 0.50, _fmt(val), ha="center", fontsize=13,
                    color=TEXT_MAIN, fontweight="bold", transform=ax_com.transAxes)
        sign = "▲" if (chg or 0) >= 0 else "▼"
        ax_com.text(x, 0.22, f"{sign}{abs(chg):.2f}%" if chg else "---",
                    ha="center", fontsize=11, color=cc, fontweight="bold",
                    transform=ax_com.transAxes)
        # 区切り線
        if i < 3:
            ax_com.axvline(0.25 + i*0.24, color=BORDER, lw=1, alpha=0.5)
    ax_com.set_xlim(0,1); ax_com.set_ylim(0,1)
    ax_com.set_xticks([]); ax_com.set_yticks([])
    ax_com.set_title("コモディティ・為替", fontsize=11, fontweight="bold",
                     color=TEXT_MAIN, pad=8)

    # ── 行2右: リスクメーター ──
    ax_rm = fig.add_subplot(gs[2, 2:], projection="polar")
    ax_rm.set_facecolor(BG)
    score = risk.get("score", 0)
    clamped = max(-5, min(5, score))
    needle_val = (clamped + 5) / 10 * 100
    _draw_gauge(ax_rm, fig,
                score=needle_val,
                rating=risk.get("sentiment","---"),
                prev=None,
                title="リスクオン / オフ 指数",
                zone_colors=[DOWN_COLOR, "#ff8c42", NEUTRAL_C, "#3fb950", UP_COLOR],
                zone_labels=["強い\nRISK OFF","RISK\nOFF","中立","RISK\nON","強い\nRISK ON"],
                text_x=0.75, text_y_base=0.62, fig_ref=fig, gs_pos=gs[2,2:],
                score_override=f"{score:+.2f}")

    # ── 行3: ニュース ──
    ax_news = fig.add_subplot(gs[3, :])
    ax_news.set_facecolor(CARD_BG)
    for sp in ax_news.spines.values(): sp.set_color(BORDER)
    ax_news.set_xlim(0,1); ax_news.set_ylim(0,1)
    ax_news.set_xticks([]); ax_news.set_yticks([])
    ax_news.set_title("📰  本日の注目ニュース（重要度順）", fontsize=11,
                      fontweight="bold", color=TEXT_MAIN, pad=8)

    sorted_news = sorted(news, key=lambda x: {"A":0,"B":1,"C":2}.get(x.get("importance","C"),2))
    imp_colors_map = {"A": DOWN_COLOR, "B": "#e3b341", "C": NEUTRAL_C}
    cols = 2
    for idx, item in enumerate(sorted_news[:8]):
        row = idx // cols
        col_n = idx % cols
        x = 0.02 + col_n * 0.50
        y = 0.85 - row * 0.22
        imp = item.get("importance","C")
        ic  = imp_colors_map.get(imp, NEUTRAL_C)
        title = item.get("title","")[:45]
        src   = item.get("source_name") or item.get("source","")
        ax_news.text(x, y, f"[{imp}]", ha="left", fontsize=8,
                     color=ic, fontweight="bold", transform=ax_news.transAxes)
        ax_news.text(x+0.04, y, title, ha="left", fontsize=8.5,
                     color=TEXT_MAIN, transform=ax_news.transAxes)
        ax_news.text(x+0.04, y-0.10, f"  📌 {src}", ha="left", fontsize=7,
                     color=TEXT_SUB, transform=ax_news.transAxes)

    _add_watermark(fig)
    out = get_dirs()["charts"] / f"{today}_overview.png"
    fig.savefig(out, dpi=160, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    logger.info(f"メインダッシュボード保存: {out}")
    return out


def _draw_gauge(ax, fig, score, rating, prev, title,
                zone_colors, zone_labels,
                text_x, text_y_base, fig_ref, gs_pos,
                score_override=None):
    """半円ゲージを描画するヘルパー"""
    theta = np.linspace(0, np.pi, 300)
    n = len(zone_colors)
    seg = 300 // n
    for i, col in enumerate(zone_colors):
        t = theta[i*seg: (i+1)*seg+1]
        ax.fill_between(t, 0.5, 1.0, alpha=0.65, color=col)
    for i, (col, lbl) in enumerate(zip(zone_colors, zone_labels)):
        mid = theta[i*seg + seg//2]
        ax.text(mid, 1.25, lbl, ha="center", va="center",
                fontsize=7.5, color=col, fontweight="bold")

    ax.plot(theta, [1.0]*len(theta), color=BORDER, lw=1)
    ax.plot(theta, [0.5]*len(theta), color=BORDER, lw=1)

    if score is not None:
        needle = np.pi * (1 - score / 100)
        ax.annotate("", xy=(needle, 0.88), xytext=(0, 0),
                    arrowprops=dict(arrowstyle="-|>", color=TEXT_MAIN,
                                   lw=2.5, mutation_scale=18))
        ax.plot(0, 0, "o", color=TEXT_MAIN, markersize=7, zorder=10)

    ax.set_ylim(0, 1.45)
    ax.set_theta_zero_location("W")
    ax.set_theta_direction(-1)
    ax.set_thetamin(0)
    ax.set_thetamax(180)
    ax.set_yticks([]); ax.set_xticks([])
    ax.spines["polar"].set_visible(False)
    ax.set_facecolor(BG)
    ax.set_title(title, fontsize=10, fontweight="bold",
                 color=TEXT_MAIN, pad=20)

    # 数値テキスト（figureレベルで描画）
    disp = score_override if score_override else (f"{score:.0f}" if score is not None else "---")
    rating_col = _rating_color(rating)
    # ゲージ下にテキスト配置
    ax.text(np.pi/2, 0.1, disp, ha="center", va="center",
            fontsize=20, fontweight="bold", color=rating_col)
    ax.text(np.pi/2, -0.1, rating, ha="center", va="center",
            fontsize=10, fontweight="bold", color=rating_col)


def _rating_color(rating: str) -> str:
    m = {
        "極度の恐怖": DOWN_COLOR, "恐怖": "#ff8c42",
        "中立": NEUTRAL_C, "強欲": UP_COLOR, "極度の強欲": "#2ea043",
        "強気": UP_COLOR, "やや強気": "#3fb950",
        "弱気": DOWN_COLOR, "やや弱気": "#ff8c42",
    }
    return m.get(rating, TEXT_MAIN)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 個別チャート群
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def chart_indices(prices: dict) -> Path | None:
    today = get_today_str()
    targets = [
        ("^N225","日経平均"), ("^TOPX","TOPIX"),
        ("^GSPC","S&P500"),  ("^IXIC","NASDAQ"),
        ("^DJI","ダウ"),     ("^VIX","VIX"),
        ("^TNX","米10Y金利"),
    ]
    names, vals, colors = [], [], []
    for sym, name in targets:
        chg = prices.get(sym, {}).get("change_pct")
        names.append(name)
        vals.append(chg or 0)
        colors.append(_c(chg))

    fig, ax = plt.subplots(figsize=(10, 5.5), facecolor=BG)
    ax.set_facecolor(CARD_BG)
    for sp in ax.spines.values(): sp.set_color(BORDER)
    ax.barh(names, vals, color=colors, height=0.55, edgecolor=BG, linewidth=1)
    ax.axvline(0, color=BORDER, lw=1.5)
    ax.grid(axis="x", color=GRID_C, lw=0.6)
    ax.set_axisbelow(True)
    for i, v in enumerate(vals):
        s = "▲" if v >= 0 else "▼"
        ax.text(v + (0.03 if v >= 0 else -0.03), i,
                f"{s}{abs(v):.2f}%", va="center",
                ha="left" if v >= 0 else "right",
                fontsize=10, color=_c(v), fontweight="bold")
    ax.set_title(f"主要指数  前日比  {today}", fontsize=13,
                 fontweight="bold", color=TEXT_MAIN, pad=12)
    ax.invert_yaxis()
    ax.tick_params(colors=TEXT_SUB, labelsize=10)
    _add_watermark(fig)
    plt.tight_layout()
    out = get_dirs()["charts"] / f"{today}_indices.png"
    fig.savefig(out, dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    return out


def chart_fear_greed(fear_greed: dict) -> Path | None:
    today  = get_today_str()
    score  = fear_greed.get("score")
    rating = fear_greed.get("rating_ja","取得失敗")
    prev   = fear_greed.get("prev_score")

    fig = plt.figure(figsize=(8, 5.5), facecolor=BG)
    ax  = fig.add_subplot(111, projection="polar")
    ax.set_facecolor(BG)

    theta = np.linspace(0, np.pi, 300)
    zone_colors = ["#f85149","#ff8c42","#e3b341","#3fb950","#2ea043"]
    zone_labels = ["極度の恐怖","恐怖","中立","強欲","極度の強欲"]
    seg = 60
    for i, (col, lbl) in enumerate(zip(zone_colors, zone_labels)):
        t = theta[i*seg:(i+1)*seg+1]
        ax.fill_between(t, 0.5, 1.0, alpha=0.7, color=col)
        mid = theta[i*seg+30]
        ax.text(mid, 1.25, lbl, ha="center", va="center",
                fontsize=8.5, color=col, fontweight="bold")

    ax.plot(theta, [1.0]*len(theta), color=BORDER, lw=1)
    ax.plot(theta, [0.5]*len(theta), color=BORDER, lw=1)

    if score is not None:
        needle = np.pi * (1 - score/100)
        ax.annotate("", xy=(needle, 0.88), xytext=(0,0),
                    arrowprops=dict(arrowstyle="-|>", color=TEXT_MAIN,
                                   lw=3, mutation_scale=20))
        ax.plot(0, 0, "o", color=TEXT_MAIN, markersize=8, zorder=10)

    ax.set_ylim(0,1.45)
    ax.set_theta_zero_location("W")
    ax.set_theta_direction(-1)
    ax.set_thetamin(0); ax.set_thetamax(180)
    ax.set_yticks([]); ax.set_xticks([])
    ax.spines["polar"].set_visible(False)

    rc = _rating_color(rating)
    score_str = f"{score:.0f}" if score else "---"
    fig.text(0.5, 0.30, score_str, ha="center", fontsize=42,
             fontweight="bold", color=rc)
    fig.text(0.5, 0.17, rating, ha="center", fontsize=15,
             fontweight="bold", color=rc)
    if prev and score:
        diff = score - prev
        s = "▲" if diff >= 0 else "▼"
        fig.text(0.5, 0.09, f"前日比 {s}{abs(diff):.1f}  (前日: {prev:.0f})",
                 ha="center", fontsize=9, color=TEXT_SUB)
    fig.text(0.5, 0.96, f"CNN Fear & Greed Index  {today}",
             ha="center", fontsize=13, fontweight="bold", color=TEXT_MAIN)
    _add_watermark(fig)
    out = get_dirs()["charts"] / f"{today}_fear_greed.png"
    fig.savefig(out, dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    return out


def chart_risk_meter(risk: dict) -> Path | None:
    today     = get_today_str()
    score     = risk.get("score", 0)
    sentiment = risk.get("sentiment","中立")
    meter     = risk.get("meter","NEUTRAL")

    fig = plt.figure(figsize=(8, 5.5), facecolor=BG)
    ax  = fig.add_subplot(111, projection="polar")
    ax.set_facecolor(BG)
    theta = np.linspace(0, np.pi, 300)
    ax.fill_between(theta[:60],   0.5, 1.0, alpha=0.7, color="#f85149")
    ax.fill_between(theta[60:120],0.5, 1.0, alpha=0.6, color="#ff8c42")
    ax.fill_between(theta[120:180],0.5,1.0, alpha=0.5, color=NEUTRAL_C)
    ax.fill_between(theta[180:240],0.5,1.0, alpha=0.6, color="#3fb950")
    ax.fill_between(theta[240:],  0.5, 1.0, alpha=0.7, color=UP_COLOR)
    ax.plot(theta, [1.0]*300, color=BORDER, lw=1)
    ax.plot(theta, [0.5]*300, color=BORDER, lw=1)

    clamped = max(-5, min(5, score))
    needle  = np.pi * (1 - (clamped+5)/10)
    ax.annotate("", xy=(needle,0.88), xytext=(0,0),
                arrowprops=dict(arrowstyle="-|>", color=TEXT_MAIN,
                               lw=3, mutation_scale=20))
    ax.plot(0,0,"o",color=TEXT_MAIN,markersize=8,zorder=10)

    for angle, lbl, col in [
        (np.pi*0.92,"強い\nRISK OFF","#f85149"),
        (np.pi*0.72,"RISK OFF","#ff8c42"),
        (np.pi*0.50,"中立",NEUTRAL_C),
        (np.pi*0.28,"RISK ON","#3fb950"),
        (np.pi*0.08,"強い\nRISK ON",UP_COLOR),
    ]:
        ax.text(angle, 1.27, lbl, ha="center", va="center",
                fontsize=8, color=col, fontweight="bold")

    ax.set_ylim(0,1.45)
    ax.set_theta_zero_location("W")
    ax.set_theta_direction(-1)
    ax.set_thetamin(0); ax.set_thetamax(180)
    ax.set_yticks([]); ax.set_xticks([])
    ax.spines["polar"].set_visible(False)

    cm = {"RISK_ON":UP_COLOR,"RISK_OFF":DOWN_COLOR,"NEUTRAL":NEUTRAL_C}
    c  = cm.get(meter, NEUTRAL_C)
    fig.text(0.5, 0.28, sentiment, ha="center", fontsize=18,
             fontweight="bold", color=c)
    fig.text(0.5, 0.16, f"スコア: {score:+.2f}",
             ha="center", fontsize=11, color=TEXT_SUB)
    fig.text(0.5, 0.96, f"リスクオン / オフ 判定  {today}",
             ha="center", fontsize=13, fontweight="bold", color=TEXT_MAIN)
    _add_watermark(fig)
    out = get_dirs()["charts"] / f"{today}_risk_meter.png"
    fig.savefig(out, dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    return out


def chart_stocks(prices: dict) -> Path | None:
    today = get_today_str()
    us = [("NVDA","NVIDIA"),("AAPL","Apple"),("TSLA","Tesla"),
          ("MSFT","Microsoft"),("AMZN","Amazon"),("META","Meta")]
    jp = [("7203.T","トヨタ"),("9984.T","SBG"),
          ("6758.T","ソニーG"),("8306.T","三菱UFJ"),
          ("6857.T","アドバンテスト"),("4063.T","信越化学")]

    fig, (ax1,ax2) = plt.subplots(1,2,figsize=(14,5.5),facecolor=BG)
    for ax, stocks, title in [(ax1,us,"🇺🇸 米国 主要銘柄"),(ax2,jp,"🇯🇵 日本 主要銘柄")]:
        ax.set_facecolor(CARD_BG)
        for sp in ax.spines.values(): sp.set_color(BORDER)
        names,vals,colors=[],[],[]
        for sym,name in stocks:
            chg=prices.get(sym,{}).get("change_pct")
            names.append(name); vals.append(chg or 0); colors.append(_c(chg))
        ax.barh(names,vals,color=colors,height=0.55,edgecolor=BG,linewidth=0.8)
        ax.axvline(0,color=BORDER,lw=1.5)
        ax.grid(axis="x",color=GRID_C,lw=0.6)
        ax.set_axisbelow(True)
        for i,v in enumerate(vals):
            s="▲" if v>=0 else "▼"
            ax.text(v+(0.03 if v>=0 else -0.03),i,f"{s}{abs(v):.2f}%",
                    va="center",ha="left" if v>=0 else "right",
                    fontsize=9,color=_c(v),fontweight="bold")
        ax.set_title(title,fontsize=12,fontweight="bold",color=TEXT_MAIN,pad=10)
        ax.invert_yaxis()
        ax.tick_params(colors=TEXT_SUB,labelsize=10)
        ax.set_xlabel("前日比 (%)",color=TEXT_SUB,fontsize=9)
    fig.suptitle(f"主要銘柄  前日比  {today}",
                 fontsize=14,fontweight="bold",color=TEXT_MAIN,y=1.02)
    _add_watermark(fig)
    plt.tight_layout()
    out = get_dirs()["charts"] / f"{today}_stocks.png"
    fig.savefig(out,dpi=150,bbox_inches="tight",facecolor=BG)
    plt.close(fig)
    return out


def chart_commodities(prices: dict) -> Path | None:
    today = get_today_str()
    targets = [
        ("GC=F","🥇 金(GOLD)","$","#d4a017"),
        ("CL=F","🛢 WTI原油","$","#5c8a5c"),
        ("BTC-USD","₿ Bitcoin","$","#f7931a"),
        ("USDJPY=X","💵 ドル円","¥","#58a6ff"),
        ("EURUSD=X","💶 EUR/USD","","#a371f7"),
        ("^TNX","📊 米10Y金利","%","#e3b341"),
    ]
    fig, axes = plt.subplots(2,3,figsize=(14,7),facecolor=BG)
    axes_flat = axes.flatten()
    for ax,(sym,name,unit,accent) in zip(axes_flat,targets):
        p=prices.get(sym,{}); val=p.get("latest"); chg=p.get("change_pct")
        cc=_c(chg)
        ax.set_facecolor(CARD_BG)
        for sp in ax.spines.values(): sp.set_color(accent); sp.set_linewidth(2)
        ax.axhspan(0.85,1.0,alpha=0.15,color=accent)
        ax.text(0.5,0.88,name,ha="center",fontsize=11,color=accent,
                fontweight="bold",transform=ax.transAxes)
        val_str=f"{unit}{val:,.2f}" if val else "---"
        ax.text(0.5,0.55,val_str,ha="center",fontsize=20,
                color=TEXT_MAIN,fontweight="bold",transform=ax.transAxes)
        s="▲" if (chg or 0)>=0 else "▼"
        chg_str=f"{s}{abs(chg):.2f}%" if chg else "---"
        ax.text(0.5,0.28,chg_str,ha="center",fontsize=15,
                color=cc,fontweight="bold",transform=ax.transAxes)
        ax.set_xlim(0,1); ax.set_ylim(0,1)
        ax.set_xticks([]); ax.set_yticks([])
    fig.suptitle(f"コモディティ・為替・金利  {today}",
                 fontsize=14,fontweight="bold",color=TEXT_MAIN)
    _add_watermark(fig)
    plt.tight_layout()
    out = get_dirs()["charts"] / f"{today}_commodities.png"
    fig.savefig(out,dpi=150,bbox_inches="tight",facecolor=BG)
    plt.close(fig)
    return out


def chart_news_importance(news: list) -> Path | None:
    if not news: return None
    today = get_today_str()
    from collections import Counter
    cats = Counter(item.get("category","その他") for item in news)
    labels = sorted(cats.keys(), key=lambda x: -cats[x])[:10]
    counts = [cats[l] for l in labels]

    # 重要度で色付け
    imp_map = {}
    for item in news:
        cat = item.get("category","その他")
        cur = imp_map.get(cat,"C")
        new_imp = item.get("importance","C")
        if new_imp < cur: imp_map[cat] = new_imp
    imp_colors = {"A":DOWN_COLOR,"B":"#e3b341","C":ACCENT}
    colors = [imp_colors.get(imp_map.get(l,"C"),ACCENT) for l in labels]

    fig, ax = plt.subplots(figsize=(10,max(4,len(labels)*0.7+1.5)),facecolor=BG)
    ax.set_facecolor(CARD_BG)
    for sp in ax.spines.values(): sp.set_color(BORDER)
    ax.barh(labels,counts,color=colors,height=0.55,edgecolor=BG,linewidth=0.8)
    ax.grid(axis="x",color=GRID_C,lw=0.6)
    ax.set_axisbelow(True)
    for bar,c in zip(ax.patches,counts):
        ax.text(c+0.1,bar.get_y()+bar.get_height()/2,
                f" {c}件",va="center",fontsize=10,color=TEXT_MAIN)
    ax.set_title(f"ニュース カテゴリ別件数  {today}",
                 fontsize=13,fontweight="bold",color=TEXT_MAIN,pad=12)
    ax.invert_yaxis()
    ax.tick_params(colors=TEXT_SUB,labelsize=10)
    patches=[mpatches.Patch(color=v,label=f"重要度{k}") for k,v in imp_colors.items()]
    ax.legend(handles=patches,fontsize=9,facecolor=CARD_BG,
              labelcolor=TEXT_MAIN,edgecolor=BORDER)
    _add_watermark(fig)
    plt.tight_layout()
    out = get_dirs()["charts"] / f"{today}_news.png"
    fig.savefig(out,dpi=150,bbox_inches="tight",facecolor=BG)
    plt.close(fig)
    return out


def run(prices: dict, news: list, risk: dict, fear_greed: dict = None) -> dict:
    logger.info("=== チャート生成開始 ===")
    if fear_greed is None: fear_greed = {}
    chart_paths = {}
    tasks = [
        ("overview",    chart_overview,        (prices, risk, fear_greed, news)),
        ("indices",     chart_indices,          (prices,)),
        ("stocks",      chart_stocks,           (prices,)),
        ("commodities", chart_commodities,      (prices,)),
        ("fear_greed",  chart_fear_greed,       (fear_greed,)),
        ("risk_meter",  chart_risk_meter,       (risk,)),
        ("news",        chart_news_importance,  (news,)),
    ]
    for key, fn, args in tasks:
        try:
            path = fn(*args)
            if path:
                chart_paths[key] = str(path)
        except Exception as e:
            logger.error(f"チャート生成失敗 [{key}]: {e}")
    logger.info(f"=== チャート生成完了: {len(chart_paths)}件 ===")
    return chart_paths
