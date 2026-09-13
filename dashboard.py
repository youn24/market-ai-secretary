"""
Streamlit ダッシュボード（カテゴリ別ニュース + AI要約版）
起動: python -m streamlit run dashboard.py
"""
import json, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import streamlit as st
import plotly.graph_objects as go

sys.path.insert(0, str(Path(__file__).parent))
from src.utils import BASE_DIR, get_today_str, JST
from src.news_categories import CATEGORIES, categorize_news

st.set_page_config(
    page_title="📊 投資経済 AI 秘書",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  section[data-testid="stSidebar"] { background:#1e3a8a; }
  section[data-testid="stSidebar"] * { color:white !important; }
  section[data-testid="stSidebar"] .stButton>button {
    background:#2563eb;color:white;border:none;
    border-radius:8px;width:100%;font-weight:700;font-size:14px;padding:8px;
  }
  .main-hdr {
    background:linear-gradient(135deg,#1e3a8a,#2563eb,#3b82f6);
    color:white;padding:18px 24px;border-radius:12px;margin-bottom:14px;
  }
  .sec-h {
    font-size:15px;font-weight:700;color:#1e3a8a;
    padding:6px 14px;margin:18px 0 10px;
    border-left:4px solid #2563eb;
    background:#f0f5ff;border-radius:0 6px 6px 0;
  }
  .cat-card {
    background:white;border-radius:12px;padding:16px;
    box-shadow:0 2px 8px rgba(0,0,0,.07);margin-bottom:12px;
  }
  .cat-title {
    font-size:16px;font-weight:700;color:#1e3a8a;
    margin-bottom:4px;
  }
  .cat-desc {
    font-size:12px;color:#6b7280;margin-bottom:10px;
    line-height:1.5;
  }
  .watch-box {
    background:#f0f5ff;border-radius:8px;padding:10px 14px;
    margin-bottom:10px;font-size:12px;color:#1e40af;
  }
  .ai-box {
    background:#faf5ff;border-radius:8px;padding:12px 14px;
    margin-bottom:10px;font-size:13px;color:#374151;
    line-height:1.8;border-left:3px solid #7c3aed;
  }
  .ai-label {
    font-size:11px;font-weight:700;color:#7c3aed;margin-bottom:4px;
  }
  .ai-waiting {
    background:#f9fafb;border-radius:8px;padding:10px 14px;
    font-size:12px;color:#9ca3af;border-left:3px solid #e5e7eb;
  }
  .news-item { padding:7px 0;border-bottom:1px solid #f3f4f6; }
  .news-link { font-size:13px;color:#1d4ed8;line-height:1.5; }
  .news-link:hover { color:#1e40af; }
  .news-meta { font-size:11px;color:#9ca3af; }
  .imp-a { color:#e05252;font-weight:700; }
  .imp-b { color:#d97706;font-weight:700; }
  .imp-c { color:#4a90d9; }
  .fear-card {
    background:white;border-radius:12px;padding:16px;
    box-shadow:0 2px 8px rgba(0,0,0,.07);text-align:center;
  }
  .vix-card {
    background:white;border-radius:10px;padding:14px;
    box-shadow:0 1px 4px rgba(0,0,0,.07);text-align:center;
  }
  .disc { font-size:11px;color:#9ca3af;text-align:center;
          background:#f9fafb;padding:8px;border-radius:6px;margin-top:8px; }
  .realtime-badge {
    display:inline-block;background:#dcfce7;color:#15803d;
    font-size:10px;font-weight:700;padding:2px 7px;
    border-radius:10px;margin-left:6px;
  }
</style>
""", unsafe_allow_html=True)

UP   = "#e05252"
DOWN = "#4a90d9"

# ─── データ読み込み ──────────────────────────────────────────
@st.cache_data(ttl=60)   # 1分キャッシュ（リアルタイム性重視）
def load_prices():
    p = BASE_DIR / "data" / "raw" / f"{get_today_str()}_prices.json"
    if not p.exists(): return {}, {}
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    return d.get("prices", {}), d.get("fear_and_greed", {})

@st.cache_data(ttl=60)
def load_news():
    items = []
    for fname in [f"{get_today_str()}_news.json",
                  f"{get_today_str()}_extra_news.json"]:
        p = BASE_DIR / "data" / "news" / fname
        if p.exists():
            with open(p, encoding="utf-8") as f:
                items.extend(json.load(f))
    return items

@st.cache_data(ttl=60)
def load_polymarket():
    p = BASE_DIR / "data" / "news" / f"{get_today_str()}_polymarket.json"
    if not p.exists(): return []
    with open(p, encoding="utf-8") as f: return json.load(f)

@st.cache_data(ttl=300)
def load_ai_summary():
    for mode in ["morning","noon","evening","test"]:
        p = BASE_DIR / "data" / "raw" / f"{get_today_str()}_ai_{mode}.json"
        if p.exists():
            with open(p, encoding="utf-8") as f:
                return json.load(f)
    return {"available": False, "category_summaries": {}, "market_comment": ""}

@st.cache_data(ttl=300)
def load_technical():
    p = BASE_DIR / "data" / "processed" / f"{get_today_str()}_technical.json"
    if not p.exists(): return {}
    with open(p, encoding="utf-8") as f: return json.load(f)

@st.cache_data(ttl=300)
def load_fundamental():
    p = BASE_DIR / "data" / "processed" / f"{get_today_str()}_fundamental.json"
    if not p.exists(): return {}
    with open(p, encoding="utf-8") as f: return json.load(f)

def _c(v):
    if v is None: return "#aaa"
    return UP if v >= 0 else DOWN

def _arrow(v):
    if v is None: return "―"
    return f"{'▲' if v>=0 else '▼'}{abs(v):.2f}%"

def _fmt(v, unit=""):
    if v is None: return "―"
    if unit=="$":  return f"${v:,.2f}"
    if unit=="円": return f"¥{v:,.2f}"
    if unit=="%":  return f"{v:.3f}%"
    return f"{v:,.4f}"

def _vix_level(val, sym):
    if val is None: return "取得失敗", "#aaa"
    if sym == "^SKEW":
        if val >= 150: return "⚠️ 極度の警戒", "#e05252"
        elif val >= 130: return "🔶 高警戒", "#ff8c42"
        else: return "🟢 平常", "#2d9a6b"
    elif sym == "^VVIX":
        if val >= 120: return "⚠️ 極度の不安", "#e05252"
        elif val >= 95: return "🔶 警戒", "#ff8c42"
        else: return "🟢 安定", "#2d9a6b"
    else:
        if val >= 30: return "⚠️ 恐怖圏", "#e05252"
        elif val >= 20: return "🔶 警戒圏", "#ff8c42"
        else: return "🟢 安定圏", "#2d9a6b"

# ─── ヘッダー ────────────────────────────────────────────────
now_str = datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")
st.markdown(f"""
<div class="main-hdr">
  <div style="font-size:22px;font-weight:700">
    📊 投資経済 AI 秘書ダッシュボード
    <span class="realtime-badge">● LIVE</span>
  </div>
  <div style="font-size:12px;opacity:.85;margin-top:4px">
    🕐 {now_str} &nbsp;|&nbsp;
    Yahoo Finance / CNN / 日銀 / 首相官邸 / 財務省 / トレーダーズウェブ /
    みんかぶ / 帝国DB / Polymarket / TradingView
  </div>
  <div style="font-size:11px;color:#fef3c7;margin-top:5px">
    ⚠️ 投資助言ではありません。分析補助目的です。
  </div>
</div>
""", unsafe_allow_html=True)


# ─── サイドバー ──────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ 操作パネル")

    if st.button("🔄 データを今すぐ更新", type="primary", use_container_width=True):
        with st.spinner("データ取得中... 2〜3分かかります"):
            import subprocess
            subprocess.run(
                [sys.executable, "run_daily.py", "--mode", "morning"],
                cwd=str(BASE_DIR), capture_output=True
            )
        st.cache_data.clear()
        st.success("✅ 更新完了！")
        st.rerun()

    st.markdown("---")

    # Ollamaステータス
    try:
        import requests as _req
        r = _req.get("http://localhost:11434/api/tags", timeout=2)
        models = [m["name"] for m in r.json().get("models", [])]
        if models:
            st.success(f"🤖 Ollama稼働中\n{models[0]}")
        else:
            st.warning("🤖 Ollama起動中\nモデルなし\n`ollama pull gemma3:4b`")
    except:
        st.info("🤖 Ollama未起動\nAI要約は使えません")

    st.markdown("---")
    st.markdown("### 📂 今日のレポート")
    today = get_today_str()
    for mode in ["morning","noon","evening","test"]:
        p = BASE_DIR / "reports" / f"{today}_{mode}.html"
        if p.exists():
            st.markdown(f"📄 [{mode}レポート]({p.as_uri()})")

    st.markdown("---")
    auto = st.checkbox("⏱️ 5分ごと自動更新")
    if auto:
        time.sleep(300); st.rerun()

    st.markdown("---")
    st.markdown("""
    **恐怖指数の目安**
    - VIX < 20 🟢 安定
    - VIX 20〜30 🔶 警戒
    - VIX > 30 ⚠️ 恐怖
    - SKEW > 130 🔶 暴落警戒
    """)

# ─── データ取得 ──────────────────────────────────────────────
prices, fear_greed = load_prices()
news        = load_news()
polymarket  = load_polymarket()
ai_data     = load_ai_summary()
technical   = load_technical()
fundamental = load_fundamental()

if not prices:
    st.warning("⚠️ データがまだありません。左の「🔄 データを今すぐ更新」を押してください。")
    st.stop()

# ─── ガネーシャ市場紹介 ──────────────────────────────────────
st.markdown('<div class="sec-h">🐘 ガネーシャの市場分析</div>',
            unsafe_allow_html=True)

try:
    from src.ganesha import generate_ganesha_comment
    ganesha_data = generate_ganesha_comment(risk, fear_greed, prices, ai_data)
    svg_html     = ganesha_data["svg"]
    mood         = ganesha_data["mood"]

    mood_bg = {
        "happy":"linear-gradient(135deg,#fff9e6,#fff3cd)",
        "excited":"linear-gradient(135deg,#fff3e0,#ffe0b2)",
        "sad":"linear-gradient(135deg,#e8eaf6,#c5cae9)",
        "warning":"linear-gradient(135deg,#fce4ec,#ffcdd2)",
        "thinking":"linear-gradient(135deg,#e8f5e9,#c8e6c9)",
        "neutral":"linear-gradient(135deg,#fffde7,#fff9c4)",
    }.get(mood, "linear-gradient(135deg,#fffde7,#fff9c4)")

    col_g1, col_g2 = st.columns([1, 2.8])
    with col_g1:
        st.markdown(f'<div style="text-align:center;padding:10px">{svg_html}</div>',
                    unsafe_allow_html=True)

    with col_g2:
        st.markdown(f"""
        <div style="background:{mood_bg};border-radius:16px;padding:20px;
             border:2px solid #FFD700;box-shadow:0 4px 16px rgba(255,215,0,0.25);
             position:relative;">

          <!-- 吹き出しの三角 -->
          <div style="position:absolute;left:-18px;top:30px;
               width:0;height:0;
               border-top:12px solid transparent;
               border-bottom:12px solid transparent;
               border-right:18px solid #FFD700;"></div>

          <div style="font-size:16px;font-weight:700;color:#8B6914;margin-bottom:12px">
            {ganesha_data['greeting']}
          </div>

          <div style="font-size:14px;color:#5D4037;line-height:1.9;margin-bottom:10px">
            📊 {ganesha_data['market_comment']}
          </div>

          {"<div style='font-size:13px;color:#4E342E;line-height:1.8;margin-bottom:8px'>📈 " + ganesha_data['price_comment'] + "</div>" if ganesha_data.get('price_comment') else ""}

          {"<div style='font-size:12px;color:#6A1B9A;line-height:1.7;background:rgba(255,255,255,0.6);padding:8px 12px;border-radius:8px;margin-bottom:8px'>🤖 " + ganesha_data['ai_comment'] + "</div>" if ganesha_data.get('ai_comment') else ""}

          <div style="font-size:11px;color:#9E9E9E;margin-top:8px;
               padding-top:8px;border-top:1px solid rgba(0,0,0,0.1)">
            🙏 {ganesha_data['disclaimer']}
          </div>
        </div>
        """, unsafe_allow_html=True)
except Exception as ex:
    st.info(f"ガネーシャの読み込み中... ({ex})")

# ─── ① Fear & Greed ─────────────────────────────────────────
st.markdown('<div class="sec-h">😨 Fear & Greed Index（株式市場）by CNN</div>',
            unsafe_allow_html=True)

fg_score  = fear_greed.get("score") or 50
fg_rating = fear_greed.get("rating_ja", "取得失敗")
fg_prev_c = fear_greed.get("prev_close")
fg_prev_w = fear_greed.get("prev_1_week")
fg_prev_m = fear_greed.get("prev_1_month")

if fg_score >= 75:   fg_col = "#2d9a6b"
elif fg_score >= 56: fg_col = "#74c69d"
elif fg_score >= 45: fg_col = "#aaaaaa"
elif fg_score >= 25: fg_col = "#ff8c42"
else:                fg_col = "#e05252"

col1, col2, col3 = st.columns([1.2, 1, 1])
with col1:
    fig_fg = go.Figure(go.Indicator(
        mode="gauge+number",
        value=fg_score,
        number=dict(font=dict(size=48, color=fg_col)),
        title=dict(text=f"<b style='color:{fg_col};font-size:17px'>{fg_rating}</b><br>"
                        f"<span style='font-size:10px;color:#9ca3af'>CNN Fear & Greed Index（株式市場版）</span>"),
        gauge=dict(
            axis=dict(range=[0,100], tickfont=dict(size=9)),
            bar=dict(color=fg_col, thickness=0.28),
            steps=[
                dict(range=[0,25],  color="rgba(224,82,82,.18)"),
                dict(range=[25,45], color="rgba(255,140,66,.18)"),
                dict(range=[45,56], color="rgba(170,170,170,.18)"),
                dict(range=[56,75], color="rgba(116,198,157,.18)"),
                dict(range=[75,100],color="rgba(45,154,107,.18)"),
            ],
            threshold=dict(line=dict(color=fg_col,width=4),
                           value=fg_score, thickness=.85),
        ),
    ))
    for xp,lbl,lc in [(.07,"😱 極度の恐怖","#e05252"),(.28,"😟 恐怖","#ff8c42"),
                       (.50,"😐 中立","#aaa"),(.72,"🙂 強欲","#74c69d"),
                       (.93,"😄 極度の強欲","#2d9a6b")]:
        fig_fg.add_annotation(x=xp,y=-.12,text=lbl,showarrow=False,
                              font=dict(size=8,color=lc),xref="paper",yref="paper")
    fig_fg.update_layout(height=300, margin=dict(l=20,r=20,t=40,b=55),
                         paper_bgcolor="white")
    st.plotly_chart(fig_fg, use_container_width=True)

with col2:
    # 推移バー
    if any([fg_prev_m, fg_prev_w, fg_prev_c]):
        hist = {}
        if fg_prev_m: hist["1ヶ月前"] = fg_prev_m
        if fg_prev_w: hist["1週間前"] = fg_prev_w
        if fg_prev_c: hist["前日"]    = fg_prev_c
        hist["現在"] = fg_score
        fig_h = go.Figure(go.Bar(
            x=list(hist.keys()), y=list(hist.values()),
            marker_color=[fg_col if k=="現在" else "#d1d5db" for k in hist],
            text=[f"{v:.0f}" for v in hist.values()],
            textposition="outside", marker_line_width=0,
        ))
        fig_h.add_hline(y=50, line_dash="dash", line_color="#aaa", line_width=1)
        fig_h.update_layout(
            title="📅 推移比較", title_font_size=12,
            yaxis=dict(range=[0,105], gridcolor="#f3f4f6"),
            plot_bgcolor="white", paper_bgcolor="white",
            height=280, margin=dict(l=10,r=10,t=40,b=10), showlegend=False,
        )
        st.plotly_chart(fig_h, use_container_width=True)

with col3:
    st.markdown(f"""
    <div class="fear-card">
      <div style="font-size:12px;color:#6b7280;margin-bottom:8px">読み方ガイド</div>
      <div style="font-size:13px;color:#374151;line-height:1.9;text-align:left">
        😱 <b>0〜24</b> 極度の恐怖<br>
        &nbsp;&nbsp;&nbsp;→ 投資家が非常に不安な状態<br>
        😟 <b>25〜44</b> 恐怖<br>
        &nbsp;&nbsp;&nbsp;→ 売り圧力が強い状態<br>
        😐 <b>45〜55</b> 中立<br>
        &nbsp;&nbsp;&nbsp;→ 方向感がない状態<br>
        🙂 <b>56〜74</b> 強欲<br>
        &nbsp;&nbsp;&nbsp;→ 買い意欲が強い状態<br>
        😄 <b>75〜100</b> 極度の強欲<br>
        &nbsp;&nbsp;&nbsp;→ 過熱・調整注意の状態
      </div>
    </div>
    """, unsafe_allow_html=True)

# ─── ② 恐怖指数パネル ───────────────────────────────────────
st.markdown('<div class="sec-h">🔴 恐怖指数・センチメント指標</div>',
            unsafe_allow_html=True)

FEAR_ITEMS = [
    ("^VIX",   "VIX",    "恐怖指数（30日）",  "30超:恐怖 / 20超:警戒 / 20以下:安定"),
    ("^VIX9D", "VIX9D",  "超短期恐怖（9日）", "直近のパニック度。VIXより敏感"),
    ("^VIX3M", "VIX3M",  "中期恐怖（3ヶ月）", "3ヶ月先の不安感"),
    ("^VVIX",  "VVIX",   "VIXのVIX",          "VIX自体の変動率。95超で警戒"),
    ("^SKEW",  "SKEW",   "テールリスク",       "暴落への備え。130超:警戒/150超:極度"),
    ("^TNX",   "10年金利","安全資産逃避指標",   "低下=安全資産へ逃避中の可能性"),
]
cols_f = st.columns(6)
for col, (sym, short, role, desc) in zip(cols_f, FEAR_ITEMS):
    p   = prices.get(sym, {})
    val = p.get("latest")
    chg = p.get("change_pct")
    lv_txt, lv_col = _vix_level(val, sym)
    with col:
        st.markdown(f"""
        <div class="vix-card">
          <div style="font-size:11px;color:#6b7280">{short}</div>
          <div style="font-size:10px;color:#9ca3af;margin-bottom:6px">{role}</div>
          <div style="font-size:24px;font-weight:800;color:{lv_col if val else '#aaa'}">
            {f'{val:.2f}' if val else '―'}</div>
          <div style="font-size:12px;font-weight:600;color:{_c(chg)}">{_arrow(chg)}</div>
          <div style="font-size:10px;font-weight:700;color:{lv_col};
               background:{lv_col}22;padding:2px 6px;border-radius:10px;
               display:inline-block;margin-top:4px">{lv_txt}</div>
          <div style="font-size:10px;color:#9ca3af;margin-top:5px;line-height:1.4">{desc}</div>
        </div>
        """, unsafe_allow_html=True)

# ─── ③ AI市場コメント ────────────────────────────────────────
st.markdown('<div class="sec-h">🤖 AI 市場コメント（Ollama）</div>',
            unsafe_allow_html=True)

if ai_data.get("available") and ai_data.get("market_comment"):
    model_name = ai_data.get("model","")
    comment = ai_data["market_comment"].replace("\n","<br>")
    st.markdown(f"""
    <div class="ai-box">
      <div class="ai-label">🤖 AI生成コメント by {model_name}</div>
      {comment}
    </div>
    <p style="font-size:11px;color:#9ca3af">
      ⚠️ AIが生成したコメントです。投資判断の参考にしないでください。
    </p>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
    <div class="ai-waiting">
      🤖 Ollamaが利用できないため、AI要約はスキップされています。<br>
      コマンドプロンプトで <code>ollama pull gemma3:4b</code> を実行後、
      「🔄 データを今すぐ更新」を押してください。
    </div>
    """, unsafe_allow_html=True)

# ─── ④ 主要指数 ──────────────────────────────────────────────
st.markdown('<div class="sec-h">📊 主要指数・マーケット数値</div>',
            unsafe_allow_html=True)

METRIC_ROWS = [
    [("^N225","日経平均","円"),("^GSPC","S&P500",""),
     ("^IXIC","NASDAQ",""),  ("^DJI","ダウ",""),
     ("^VIX","VIX",""),      ("USDJPY=X","ドル円","円")],
    [("EURUSD=X","ユーロドル",""),("^TNX","米10年金利","%"),
     ("GC=F","金","$"),       ("CL=F","原油","$"),
     ("BTC-USD","Bitcoin","$"),("^SKEW","SKEW","")],
]
for row in METRIC_ROWS:
    cols_m = st.columns(len(row))
    for col, (sym, name, unit) in zip(cols_m, row):
        p = prices.get(sym, {})
        with col:
            st.metric(name, _fmt(p.get("latest"), unit),
                      delta=_arrow(p.get("change_pct")) if p.get("change_pct") else None)

# ─── ⑤ カテゴリ別ニュース + AI要約 ─────────────────────────
st.markdown('<div class="sec-h">📰 カテゴリ別ニュース + AI要約</div>',
            unsafe_allow_html=True)

if not news:
    st.info("ニュースがありません。「🔄 データを今すぐ更新」を押してください。")
else:
    categorized = categorize_news(news)
    cat_summaries = ai_data.get("category_summaries", {})

    # カテゴリタブ
    cat_names = [c for c in CATEGORIES.keys() if categorized.get(c)]
    if cat_names:
        tabs = st.tabs(cat_names)
        for tab, cat_name in zip(tabs, cat_names):
            with tab:
                cfg   = CATEGORIES[cat_name]
                items = categorized.get(cat_name, [])

                # カテゴリ説明
                st.markdown(f"""
                <div class="cat-card">
                  <div class="cat-title">{cat_name}</div>
                  <div class="cat-desc">{cfg['description']}</div>
                """, unsafe_allow_html=True)

                # 監視ポイント
                if cfg.get("watch_points"):
                    wp_html = "".join(f"<li>{w}</li>" for w in cfg["watch_points"])
                    st.markdown(f"""
                    <div class="watch-box">
                      <b>👁️ 今日の監視ポイント</b>
                      <ul style="margin:4px 0 0 14px;line-height:1.8">{wp_html}</ul>
                    </div>
                    """, unsafe_allow_html=True)

                st.markdown("</div>", unsafe_allow_html=True)

                # AI要約
                ai_summary = cat_summaries.get(cat_name, "")
                if ai_summary and ai_data.get("available"):
                    summary_html = ai_summary.replace("\n", "<br>")
                    st.markdown(f"""
                    <div class="ai-box">
                      <div class="ai-label">🤖 AI要約 by {ai_data.get('model','Ollama')}</div>
                      {summary_html}
                    </div>
                    """, unsafe_allow_html=True)
                elif not ai_data.get("available"):
                    st.markdown("""
                    <div class="ai-waiting">
                      🤖 Ollamaを起動するとここにAI要約が表示されます
                    </div>
                    """, unsafe_allow_html=True)

                # ニュース一覧
                st.markdown(f"**📋 ニュース一覧（{len(items)}件）**")
                imp_icons = {"A":"🔴","B":"🟡","C":"🔵"}
                imp_labels = {"A":"重要","B":"中","C":"参考"}
                for item in items[:15]:
                    title = item.get("title","")
                    url   = item.get("url","")
                    src   = item.get("source_name") or item.get("source","")
                    pub   = item.get("published_jst","")
                    imp   = item.get("importance","C")
                    icon  = imp_icons.get(imp,"⚪")
                    lbl   = imp_labels.get(imp,"")
                    st.markdown(
                        f"{icon} **[{lbl}]** [{title}]({url})  \n"
                        f"<span class='news-meta'>📰 {src}　🕐 {pub}</span>",
                        unsafe_allow_html=True
                    )

# ─── ⑤b テクニカル分析 ──────────────────────────────────────
st.markdown('<div class="sec-h">📐 テクニカル分析</div>', unsafe_allow_html=True)

if not technical:
    st.info("テクニカルデータがありません。「🔄 データを今すぐ更新」を押してください。")
else:
    tech_tabs = st.tabs(list(technical.keys())[:6])
    for tab, sym in zip(tech_tabs, list(technical.keys())[:6]):
        data = technical[sym]
        with tab:
            if data.get("error"):
                st.warning(f"取得失敗: {data['error']}")
                continue
            name = data.get("name","")
            cur  = data.get("current",0)
            ma   = data.get("ma",{})
            rsi  = data.get("rsi")
            macd = data.get("macd",{})
            bb   = data.get("bb",{})
            sto  = data.get("stochastic",{})
            trend= data.get("trend","")
            rsi_sig = data.get("rsi_signal","")

            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown(f"**📊 移動平均（現在値: {cur:,.2f}）**")
                for k, label in [("ma5","MA5"),("ma25","MA25"),("ma75","MA75")]:
                    val = ma.get(k)
                    dev = ma.get(f"dev_{k}")
                    if val:
                        c   = UP if (dev or 0)>=0 else DOWN
                        st.markdown(f"- {label}: `{val:,.2f}` "
                                    f"<span style='color:{c}'>{'+' if (dev or 0)>=0 else ''}{dev:.2f}%乖離</span>",
                                    unsafe_allow_html=True)
                st.markdown(f"**トレンド:** {trend}")

            with col2:
                st.markdown("**📈 RSI / ストキャスティクス**")
                if rsi:
                    r_col = UP if rsi > 70 else DOWN if rsi < 30 else "#aaa"
                    st.markdown(f"- RSI(14): <span style='color:{r_col};font-weight:700'>{rsi}</span> {rsi_sig}",
                                unsafe_allow_html=True)
                if sto:
                    st.markdown(f"- %K: `{sto.get('k','―')}` / %D: `{sto.get('d','―')}`")
                    st.markdown(f"- シグナル: {sto.get('signal','')}")
                if bb:
                    st.markdown(f"**ボリンジャーバンド:** {bb.get('signal','')}")
                    st.markdown(f"- 上限: `{bb.get('upper','―'):,.2f}` / 下限: `{bb.get('lower','―'):,.2f}`")
                    st.markdown(f"- バンド内位置: `{bb.get('position','―')}%`")

            with col3:
                st.markdown("**📉 MACD**")
                if macd:
                    m_col = UP if (macd.get("hist") or 0) >= 0 else DOWN
                    st.markdown(f"- MACD: `{macd.get('macd','―')}`")
                    st.markdown(f"- シグナル: `{macd.get('signal','―')}`")
                    st.markdown(f"- ヒストグラム: <span style='color:{m_col};font-weight:700'>{macd.get('hist','―')}</span>",
                                unsafe_allow_html=True)
                    cross = macd.get("cross","")
                    if cross != "なし":
                        st.markdown(f"- ⚡ **{cross}発生！**")

# ─── ⑤c ファンダメンタル分析 ────────────────────────────────
st.markdown('<div class="sec-h">💼 ファンダメンタル分析</div>', unsafe_allow_html=True)

if not fundamental:
    st.info("ファンダデータがありません。「🔄 データを今すぐ更新」を押してください。")
else:
    fund_tab1, fund_tab2, fund_tab3, fund_tab4, fund_tab5 = st.tabs(
        ["📊 PER/PBR・レーティング", "📈 先物", "⚡ オプション/NT倍率",
         "📉 騰落レシオ/市場統計", "📅 経済指標カレンダー"]
    )

    # PER/PBR
    with fund_tab1:
        fundata = fundamental.get("fundamentals", {})
        if fundata:
            rows_us, rows_jp = [], []
            for sym, d in fundata.items():
                if d.get("error"): continue
                row = {
                    "銘柄": d.get("name",""),
                    "現在値": f"{d.get('current_price',0):,.2f}" if d.get("current_price") else "―",
                    "PER": f"{d.get('per','―')}",
                    "PBR": f"{d.get('pbr','―')}",
                    "予想PER": f"{d.get('forward_per','―')}",
                    "配当利回り": f"{d.get('div_yield','―')}%" if d.get("div_yield") else "―",
                    "目標株価": f"{d.get('target_price','―'):,.2f}" if d.get("target_price") else "―",
                    "上値余地": f"{'+' if (d.get('upside_pct') or 0)>=0 else ''}{d.get('upside_pct','―')}%" if d.get("upside_pct") else "―",
                    "レーティング": d.get("rating_ja","―"),
                }
                if sym.endswith(".T"):
                    rows_jp.append(row)
                else:
                    rows_us.append(row)

            st.markdown("**🗽 米国銘柄**")
            if rows_us:
                st.dataframe(rows_us, use_container_width=True)
            st.markdown("**🗾 日本銘柄**")
            if rows_jp:
                st.dataframe(rows_jp, use_container_width=True)
        else:
            st.info("データなし")

    # 先物
    with fund_tab2:
        futures = fundamental.get("futures", {})
        if futures:
            for sym, d in futures.items():
                if d.get("error"): continue
                chg = d.get("change_pct")
                c   = UP if (chg or 0) >= 0 else DOWN
                st.markdown(
                    f"**{d.get('name','')}**: `{d.get('latest',0):,.2f}` "
                    f"<span style='color:{c}'>{_arrow(chg)}</span>",
                    unsafe_allow_html=True
                )
        else:
            st.info("先物データなし")

    # オプション・NT倍率
    with fund_tab3:
        opts = fundamental.get("options", {})
        nt   = fundamental.get("nt_ratio", {})

        st.markdown("**⚡ VIX オプション Put/Call比率**")
        if opts and not opts.get("error"):
            pcr = opts.get("put_call_ratio")
            sig = opts.get("signal","")
            c   = UP if (pcr or 0) > 1.0 else DOWN
            st.markdown(f"- 期限: `{opts.get('expiry','―')}`")
            st.markdown(f"- コール出来高: `{opts.get('call_vol',0):,}`")
            st.markdown(f"- プット出来高: `{opts.get('put_vol',0):,}`")
            st.markdown(f"- PCR: <span style='color:{c};font-weight:700'>{pcr}</span>",
                        unsafe_allow_html=True)
            st.markdown(f"- シグナル: **{sig}**")
        else:
            st.info("オプションデータなし")

        st.markdown("---")
        st.markdown("**📊 NT倍率（日経平均÷TOPIX）**")
        if nt and nt.get("nt_ratio"):
            st.markdown(f"- NT倍率: **{nt['nt_ratio']}**")
            st.markdown(f"- シグナル: {nt.get('signal','')}")
        else:
            st.info(f"NT倍率: {nt.get('signal','データなし')}")

    # 市場統計ニュース
    with fund_tab4:
        stat_news = fundamental.get("market_stat_news", [])
        trkh      = fundamental.get("torakuhi", {})

        st.markdown(f"**騰落レシオ（近似）**")
        if trkh.get("ratio"):
            r   = trkh["ratio"]
            r_c = UP if r > 120 else DOWN if r < 70 else "#aaa"
            st.markdown(
                f"<span style='font-size:28px;font-weight:800;color:{r_c}'>{r}</span> "
                f"&nbsp; {trkh.get('signal','')}",
                unsafe_allow_html=True
            )
            st.caption(trkh.get("note",""))
        else:
            st.info("騰落レシオ計算失敗")

        st.markdown("---")
        st.markdown("**📰 市場統計関連ニュース**")
        if stat_news:
            labels = list(dict.fromkeys(n.get("label","") for n in stat_news))
            stat_tabs = st.tabs(labels[:8])
            by_label  = {}
            for item in stat_news:
                l = item.get("label","")
                by_label.setdefault(l, []).append(item)
            for tab, label in zip(stat_tabs, labels[:8]):
                with tab:
                    for item in by_label.get(label, [])[:5]:
                        st.markdown(
                            f"- [{item.get('title','')}]({item.get('url','')})"
                            f"  \n<span style='font-size:11px;color:#9ca3af'>"
                            f"{item.get('published_jst','')}</span>",
                            unsafe_allow_html=True
                        )
        else:
            st.info("市場統計ニュースなし")

    # 経済指標カレンダー
    with fund_tab5:
        calendar = fundamental.get("economic_calendar", [])
        st.markdown("**📅 経済指標・イベント関連ニュース**")
        if calendar:
            for item in calendar[:20]:
                st.markdown(
                    f"📌 [{item.get('title','')}]({item.get('url','')})"
                    f"  \n<span style='font-size:11px;color:#9ca3af'>"
                    f"🔍 {item.get('keyword','')} | {item.get('published_jst','')}</span>",
                    unsafe_allow_html=True
                )
        else:
            st.info("経済カレンダーデータなし")

# ─── ⑥ Polymarket ───────────────────────────────────────────
st.markdown('<div class="sec-h">🎲 Polymarket 予測市場（金融・経済）</div>',
            unsafe_allow_html=True)
st.caption("市場参加者の予測確率です。参考情報であり、投資助言ではありません。")

if not polymarket:
    st.info("データなし。「🔄 データを今すぐ更新」を押してください。")
else:
    cols_p = st.columns(2)
    for i, m in enumerate(polymarket[:8]):
        yes = m.get("yes_prob")
        q   = m.get("question","")
        url = m.get("url","")
        with cols_p[i % 2]:
            if yes is not None:
                bar_c = UP if yes >= 50 else DOWN
                st.markdown(f"""
                <div style="background:white;border-radius:10px;padding:14px;
                     margin-bottom:10px;box-shadow:0 1px 4px rgba(0,0,0,.08);
                     border-left:3px solid {bar_c}">
                  <div style="font-size:13px;font-weight:600;color:#1e3a8a;
                       margin-bottom:8px">{q[:65]}</div>
                  <div style="display:flex;justify-content:space-between;
                       font-size:12px;margin-bottom:5px">
                    <span style="color:{UP};font-weight:700">YES {yes}%</span>
                    <span style="color:{DOWN};font-weight:700">NO {m.get('no_prob','')}%</span>
                  </div>
                  <div style="background:#f3f4f6;border-radius:4px;height:8px">
                    <div style="background:{bar_c};width:{yes}%;
                         height:8px;border-radius:4px"></div>
                  </div>
                </div>
                """, unsafe_allow_html=True)
                if url:
                    st.caption(f"[Polymarketで詳細を見る]({url})")

# ─── ⑦ 銘柄チャート ─────────────────────────────────────────
st.markdown('<div class="sec-h">📈 主要銘柄チャート</div>',
            unsafe_allow_html=True)

tab_us, tab_jp = st.tabs(["🗽 米国銘柄","🗾 日本銘柄"])
for tab, stocks in [
    (tab_us,[("NVDA","NVIDIA"),("AAPL","Apple"),("TSLA","Tesla"),
             ("MSFT","Microsoft"),("AMZN","Amazon"),("META","Meta")]),
    (tab_jp,[("7203.T","トヨタ"),("9984.T","SBG"),("6758.T","ソニーG"),
             ("8306.T","三菱UFJ"),("6857.T","アドバンテスト"),("4063.T","信越化学")]),
]:
    with tab:
        names  = [s[1] for s in stocks]
        vals   = [prices.get(s[0],{}).get("change_pct") or 0 for s in stocks]
        colors = [UP if v>=0 else DOWN for v in vals]
        fig_s  = go.Figure(go.Bar(
            x=vals, y=names, orientation="h",
            marker_color=colors, marker_line_width=0,
            text=[_arrow(v) for v in vals], textposition="outside",
            textfont=dict(size=11, color=colors),
            hovertemplate="<b>%{y}</b><br>前日比: %{x:.2f}%<extra></extra>",
        ))
        fig_s.add_vline(x=0, line_color="#e5e7eb", line_width=2)
        fig_s.update_layout(
            height=280, margin=dict(l=10,r=80,t=10,b=10),
            plot_bgcolor="#f8f9fa", paper_bgcolor="white",
            yaxis=dict(autorange="reversed"),
            xaxis=dict(gridcolor="#e9ecef"),
        )
        st.plotly_chart(fig_s, use_container_width=True)

# ─── ⑧ TradingView ──────────────────────────────────────────
st.markdown('<div class="sec-h">📡 TradingView リアルタイムチャート</div>',
            unsafe_allow_html=True)
st.caption("※インターネット接続が必要。クリックするとTradingViewで大きなチャートが開きます。")

TV = [("OSAKA:NI225","日経平均"),("SP:SPX","S&P500"),("FX:USDJPY","ドル円"),
      ("OANDA:XAUUSD","金(GOLD)"),("BITSTAMP:BTCUSD","Bitcoin"),("TVC:US10Y","米10年金利")]
tv_cols = st.columns(3)
for i,(sym,label) in enumerate(TV):
    with tv_cols[i%3]:
        st.markdown(f"**{label}**")
        st.components.v1.html(f"""
        <div class="tradingview-widget-container" style="height:200px">
          <div class="tradingview-widget-container__widget"></div>
          <script src="https://s3.tradingview.com/external-embedding/embed-widget-mini-symbol-overview.js" async>
          {{"symbol":"{sym}","width":"100%","height":200,"locale":"ja",
            "dateRange":"1M","colorTheme":"light","isTransparent":false,"autosize":true}}
          </script>
        </div>""", height=210)

# ─── フッター ────────────────────────────────────────────────
st.markdown("---")
st.markdown(f"""
<div class="disc">
  📊 投資経済 AI 秘書システム &nbsp;|&nbsp; {now_str}<br>
  投資助言ではありません。断定表現は使用しません。データに遅延・誤差がある場合があります。
</div>
""", unsafe_allow_html=True)
