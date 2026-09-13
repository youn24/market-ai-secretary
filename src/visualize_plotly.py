"""
Plotly インタラクティブチャート生成モジュール
マウスで触れる・ズームできる動くチャートを生成する
"""
import warnings
warnings.filterwarnings("ignore")

import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import plotly.io as pio

from src.utils import get_today_str, setup_logger

logger = setup_logger("visualize_plotly")

# カラーパレット
UP    = "#e05252"
DOWN  = "#4a90d9"
GOLD  = "#c9a84c"
BTC   = "#f7931a"
OIL   = "#5c8a5c"
BG    = "#ffffff"
PAPER = "#f8f9fa"
GRID  = "#e9ecef"
TEXT  = "#212529"
MUTED = "#6c757d"


def _color(val):
    if val is None: return MUTED
    return UP if val >= 0 else DOWN


def _arrow(val):
    if val is None: return "―"
    return f"{'▲' if val >= 0 else '▼'}{abs(val):.2f}%"


# ─────────────────────────────────────────
# 1. 主要指数 横棒チャート
# ─────────────────────────────────────────
def plotly_indices(prices: dict) -> str:
    targets = [
        ("^N225","日経平均"), ("^TOPX","TOPIX"),
        ("^GSPC","S&P500"),  ("^IXIC","NASDAQ"),
        ("^DJI","ダウ"),     ("^VIX","VIX"),
    ]
    names, vals, colors, texts, hovers = [], [], [], [], []
    for sym, name in targets:
        p   = prices.get(sym, {})
        chg = p.get("change_pct")
        lat = p.get("latest")
        names.append(name)
        vals.append(chg if chg is not None else 0)
        colors.append(_color(chg))
        texts.append(_arrow(chg))
        hovers.append(
            f"<b>{name}</b><br>"
            f"現在値: {lat:,.2f}<br>"
            f"前日比: {_arrow(chg)}<br>"
            f"<i>※投資助言ではありません</i>"
            if lat else f"<b>{name}</b><br>取得失敗"
        )

    fig = go.Figure(go.Bar(
        x=vals, y=names, orientation="h",
        marker_color=colors,
        text=texts, textposition="outside",
        textfont=dict(size=12, color=colors),
        hovertext=hovers, hoverinfo="text",
        marker_line_width=0,
    ))
    fig.add_vline(x=0, line_color=GRID, line_width=2)
    fig.update_layout(
        title=dict(text=f"📊 主要指数 前日比　{get_today_str()}",
                   font=dict(size=16, color=TEXT), x=0.02),
        xaxis=dict(title="変化率 (%)", gridcolor=GRID, zeroline=False,
                   tickfont=dict(color=MUTED)),
        yaxis=dict(autorange="reversed", tickfont=dict(size=13, color=TEXT)),
        plot_bgcolor=PAPER, paper_bgcolor=BG,
        margin=dict(l=10, r=80, t=60, b=40),
        height=360,
        showlegend=False,
        hoverlabel=dict(bgcolor="white", font_size=13, bordercolor=GRID),
    )
    return pio.to_html(fig, full_html=False, include_plotlyjs=False,
                       config={"displayModeBar": False, "responsive": True})


# ─────────────────────────────────────────
# 2. 主要銘柄 横棒チャート（米国・日本並列）
# ─────────────────────────────────────────
def plotly_stocks(prices: dict) -> str:
    us_stocks = [
        ("NVDA","NVIDIA"),("AAPL","Apple"),("TSLA","Tesla"),
        ("MSFT","Microsoft"),("AMZN","Amazon"),("META","Meta"),
    ]
    jp_stocks = [
        ("7203.T","トヨタ"),("9984.T","SBG"),("6758.T","ソニーG"),
        ("8306.T","三菱UFJ"),("6857.T","アドバンテスト"),("4063.T","信越化学"),
    ]

    fig = make_subplots(rows=1, cols=2,
                        subplot_titles=("🗽 米国 主要銘柄", "🗾 日本 主要銘柄"),
                        horizontal_spacing=0.12)

    for col, stocks in [(1, us_stocks), (2, jp_stocks)]:
        names, vals, colors, texts, hovers = [], [], [], [], []
        for sym, name in stocks:
            p   = prices.get(sym, {})
            chg = p.get("change_pct")
            lat = p.get("latest")
            names.append(name)
            vals.append(chg if chg is not None else 0)
            colors.append(_color(chg))
            texts.append(_arrow(chg))
            hovers.append(
                f"<b>{name}</b> ({sym})<br>"
                f"現在値: {lat:,.2f}<br>"
                f"前日比: {_arrow(chg)}"
                if lat else f"<b>{name}</b><br>取得失敗"
            )
        fig.add_trace(go.Bar(
            x=vals, y=names, orientation="h",
            marker_color=colors,
            text=texts, textposition="outside",
            textfont=dict(size=11, color=colors),
            hovertext=hovers, hoverinfo="text",
            marker_line_width=0,
            showlegend=False,
        ), row=1, col=col)
        fig.add_vline(x=0, line_color=GRID, line_width=1.5, row=1, col=col)

    fig.update_layout(
        title=dict(text=f"📋 主要銘柄 前日比　{get_today_str()}",
                   font=dict(size=16, color=TEXT), x=0.02),
        plot_bgcolor=PAPER, paper_bgcolor=BG,
        margin=dict(l=10, r=80, t=70, b=40),
        height=380,
        hoverlabel=dict(bgcolor="white", font_size=13, bordercolor=GRID),
    )
    fig.update_xaxes(gridcolor=GRID, zeroline=False,
                     tickfont=dict(color=MUTED), title_text="変化率 (%)")
    fig.update_yaxes(autorange="reversed", tickfont=dict(size=12, color=TEXT))
    return pio.to_html(fig, full_html=False, include_plotlyjs=False,
                       config={"displayModeBar": False, "responsive": True})


# ─────────────────────────────────────────
# 3. Fear & Greed ゲージ
# ─────────────────────────────────────────
def plotly_fear_greed(fear_greed: dict) -> str:
    score  = fear_greed.get("score")
    rating = fear_greed.get("rating_ja", "取得失敗")

    if score is None:
        score = 50

    # ゾーンカラー
    if score >= 75:   gauge_color = "#2d9a6b"
    elif score >= 55: gauge_color = "#74c69d"
    elif score >= 45: gauge_color = "#aaaaaa"
    elif score >= 25: gauge_color = "#ff8c42"
    else:             gauge_color = "#e05252"

    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=score,
        number=dict(font=dict(size=52, color=gauge_color),
                    suffix=""),
        title=dict(
            text=f"😨 Fear & Greed Index<br>"
                 f"<span style='font-size:18px;color:{gauge_color}'>{rating}</span><br>"
                 f"<span style='font-size:11px;color:#9ca3af'>出典: alternative.me / 暗号資産市場の心理指標</span>",
            font=dict(size=14, color=TEXT),
        ),
        gauge=dict(
            axis=dict(range=[0, 100], tickwidth=1,
                      tickcolor=MUTED, tickfont=dict(size=11)),
            bar=dict(color=gauge_color, thickness=0.25),
            bgcolor=PAPER,
            borderwidth=0,
            steps=[
                dict(range=[0,  25], color="rgba(224,82,82,0.2)"),
                dict(range=[25, 45], color="rgba(255,140,66,0.2)"),
                dict(range=[45, 55], color="rgba(170,170,170,0.2)"),
                dict(range=[55, 75], color="rgba(116,198,157,0.2)"),
                dict(range=[75,100], color="rgba(45,154,107,0.2)"),
            ],
            threshold=dict(
                line=dict(color=gauge_color, width=4),
                thickness=0.8, value=score,
            ),
        ),
        delta=dict(
            reference=fear_greed.get("prev_score") or score,
            valueformat=".1f",
        ) if fear_greed.get("prev_score") else None,
    ))

    # ゾーンラベル
    for x, label, color in [
        (0.08,"極度の\n恐怖","#e05252"),
        (0.28,"恐怖","#ff8c42"),
        (0.50,"中立","#aaaaaa"),
        (0.72,"強欲","#74c69d"),
        (0.92,"極度の\n強欲","#2d9a6b"),
    ]:
        fig.add_annotation(x=x, y=-0.12, text=label, showarrow=False,
                           font=dict(size=9, color=color), xref="paper", yref="paper")

    fig.update_layout(
        paper_bgcolor=BG, plot_bgcolor=BG,
        margin=dict(l=20, r=20, t=20, b=50),
        height=300,
    )
    return pio.to_html(fig, full_html=False, include_plotlyjs=False,
                       config={"displayModeBar": False, "responsive": True})


# ─────────────────────────────────────────
# 4. リスクオン/オフ ゲージ
# ─────────────────────────────────────────
def plotly_risk_meter(risk: dict) -> str:
    score     = risk.get("score", 0)
    sentiment = risk.get("sentiment", "中立")
    meter     = risk.get("meter", "NEUTRAL")

    # -5〜+5 を 0〜100 に変換
    gauge_val = (score + 5) / 10 * 100
    cm = {"RISK_ON": UP, "RISK_OFF": DOWN, "NEUTRAL": MUTED}
    gc = cm.get(meter, MUTED)

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=gauge_val,
        number=dict(
            suffix="",
            font=dict(size=1, color=BG),  # 数値は非表示
        ),
        title=dict(
            text=f"⚖️ リスクオン / オフ 判定<br>"
                 f"<span style='font-size:20px;font-weight:bold;color:{gc}'>{sentiment}</span><br>"
                 f"<span style='font-size:12px;color:#9ca3af'>スコア: {score:+.2f}</span>",
            font=dict(size=14, color=TEXT),
        ),
        gauge=dict(
            axis=dict(range=[0, 100],
                      tickvals=[0, 25, 50, 75, 100],
                      ticktext=["完全\nリスクオフ", "オフ寄り", "中立", "オン寄り", "完全\nリスクオン"],
                      tickfont=dict(size=9, color=MUTED)),
            bar=dict(color=gc, thickness=0.25),
            bgcolor=PAPER, borderwidth=0,
            steps=[
                dict(range=[0,  30], color="rgba(74,144,217,0.2)"),
                dict(range=[30, 45], color="rgba(74,144,217,0.1)"),
                dict(range=[45, 55], color="rgba(170,170,170,0.15)"),
                dict(range=[55, 70], color="rgba(224,82,82,0.1)"),
                dict(range=[70,100], color="rgba(224,82,82,0.2)"),
            ],
            threshold=dict(
                line=dict(color=gc, width=4),
                thickness=0.8, value=gauge_val,
            ),
        ),
    ))
    fig.update_layout(
        paper_bgcolor=BG, plot_bgcolor=BG,
        margin=dict(l=20, r=20, t=20, b=20),
        height=300,
    )
    return pio.to_html(fig, full_html=False, include_plotlyjs=False,
                       config={"displayModeBar": False, "responsive": True})


# ─────────────────────────────────────────
# 5. コモディティ 3指標
# ─────────────────────────────────────────
def plotly_commodities(prices: dict) -> str:
    targets = [
        ("GC=F",    "金 (GOLD)",  GOLD, "$"),
        ("CL=F",    "WTI原油",    OIL,  "$"),
        ("BTC-USD", "Bitcoin",    BTC,  "$"),
    ]

    fig = make_subplots(
        rows=1, cols=3,
        subplot_titles=[t[1] for t in targets],
        specs=[[{"type":"indicator"}, {"type":"indicator"}, {"type":"indicator"}]],
    )

    for i, (sym, name, color, unit) in enumerate(targets, 1):
        p      = prices.get(sym, {})
        latest = p.get("latest")
        chg    = p.get("change_pct")
        prev   = p.get("prev_close")
        fig.add_trace(go.Indicator(
            mode="number+delta",
            value=latest,
            number=dict(
                prefix=unit,
                valueformat=",.2f",
                font=dict(size=28, color=color),
            ),
            delta=dict(
                reference=prev,
                valueformat=".2f",
                prefix=unit,
                increasing=dict(color=UP),
                decreasing=dict(color=DOWN),
            ) if prev else None,
            title=dict(
                text=f"<b>{name}</b><br>"
                     f"<span style='color:{_color(chg)};font-size:16px'>"
                     f"{_arrow(chg)}</span>",
                font=dict(size=13),
            ),
        ), row=1, col=i)

    fig.update_layout(
        title=dict(text=f"⛽ コモディティ・仮想通貨　{get_today_str()}",
                   font=dict(size=16, color=TEXT), x=0.02),
        paper_bgcolor=BG, plot_bgcolor=BG,
        margin=dict(l=10, r=10, t=60, b=10),
        height=220,
    )
    return pio.to_html(fig, full_html=False, include_plotlyjs=False,
                       config={"displayModeBar": False, "responsive": True})


# ─────────────────────────────────────────
# 6. ニュース重要度 バーチャート
# ─────────────────────────────────────────
def plotly_news_chart(news: list[dict]) -> str:
    if not news:
        return ""
    from collections import Counter
    label_counts   = Counter(item.get("label","不明") for item in news)
    importance_map = {item.get("label"): item.get("importance","C") for item in news}
    imp_colors = {"A": UP, "B": "#ff8c42", "C": DOWN}

    labels = sorted(label_counts.keys(),
                    key=lambda x: {"A":0,"B":1,"C":2}.get(importance_map.get(x,"C"),2))
    counts = [label_counts[l] for l in labels]
    colors = [imp_colors.get(importance_map.get(l,"C"), MUTED) for l in labels]

    fig = go.Figure(go.Bar(
        x=counts, y=labels, orientation="h",
        marker_color=colors, marker_line_width=0,
        text=[f"{c}件" for c in counts],
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>%{x}件<extra></extra>",
    ))
    fig.update_layout(
        title=dict(text=f"📰 ニュース重要度別件数　{get_today_str()}",
                   font=dict(size=15, color=TEXT), x=0.02),
        xaxis=dict(title="件数", gridcolor=GRID, zeroline=False),
        yaxis=dict(autorange="reversed", tickfont=dict(size=11)),
        plot_bgcolor=PAPER, paper_bgcolor=BG,
        margin=dict(l=10, r=60, t=50, b=40),
        height=320,
        showlegend=False,
    )
    return pio.to_html(fig, full_html=False, include_plotlyjs=False,
                       config={"displayModeBar": False, "responsive": True})


# ─────────────────────────────────────────
# まとめて生成
# ─────────────────────────────────────────
def run_plotly(prices: dict, news: list[dict],
               risk: dict, fear_greed: dict) -> dict:
    logger.info("=== Plotly チャート生成開始 ===")
    charts = {}
    tasks = [
        ("indices",     plotly_indices,     (prices,)),
        ("stocks",      plotly_stocks,      (prices,)),
        ("fear_greed",  plotly_fear_greed,  (fear_greed,)),
        ("risk_meter",  plotly_risk_meter,  (risk,)),
        ("commodities", plotly_commodities, (prices,)),
        ("news",        plotly_news_chart,  (news,)),
    ]
    for key, fn, args in tasks:
        try:
            html = fn(*args)
            if html:
                charts[key] = html
                logger.info(f"[OK] {key}")
        except Exception as e:
            logger.error(f"[FAIL] {key}: {e}")
    logger.info(f"=== Plotly 完了: {len(charts)}件 ===")
    return charts
