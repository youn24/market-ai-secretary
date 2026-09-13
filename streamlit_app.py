"""
市場AI秘書 - インタラクティブダッシュボード
Streamlit Community Cloud（無料）でホスティング

起動方法（ローカル）:
  pip install streamlit
  streamlit run streamlit_app.py

Streamlit Cloudデプロイ:
  https://share.streamlit.io/ → GitHubリポジトリを選択
"""
import json
import ssl
import urllib.request
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

# ─────────────────────────────────────────
st.set_page_config(
    page_title="市場AI秘書ダッシュボード",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ダークテーマCSS
st.markdown("""
<style>
    .main { background-color: #07111e; color: #e0e8f0; }
    .stMetric { background-color: #0d1f33; border-radius: 8px; padding: 10px; }
    .big-number { font-size: 2rem; font-weight: bold; color: #00d4ff; }
    .up { color: #00ff88; }
    .down { color: #ff4444; }
    h1, h2, h3 { color: #00d4ff; }
</style>
""", unsafe_allow_html=True)

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE


@st.cache_data(ttl=300)  # 5分キャッシュ
def fetch_price(symbol: str) -> dict:
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=6mo"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        resp = urllib.request.urlopen(req, context=_ctx, timeout=10)
        data = json.loads(resp.read())
        result = data["chart"]["result"][0]
        timestamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
        dates = [datetime.fromtimestamp(t).strftime("%Y-%m-%d") for t in timestamps]
        df = pd.DataFrame({"Date": dates, "Close": closes}).dropna()
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date").sort_index()
        latest = float(df["Close"].iloc[-1])
        prev = float(df["Close"].iloc[-2])
        chg = (latest - prev) / prev * 100
        return {"df": df, "latest": latest, "change_pct": chg}
    except Exception:
        return {}


def load_predictions() -> list:
    path = Path("data/predictions.json")
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data.get("predictions", [])
        except Exception:
            pass
    return []


def load_ai_memory() -> dict:
    path = Path("data/ai_memory.json")
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


# ─────────────────────────────────────────
# サイドバー
st.sidebar.title("📊 市場AI秘書")
st.sidebar.markdown("**オーナー**: 中田 洋介")
st.sidebar.markdown(f"**更新**: {datetime.now().strftime('%H:%M JST')}")
st.sidebar.markdown("---")
page = st.sidebar.radio("ページ", [
    "🏠 メインダッシュボード",
    "📈 価格チャート",
    "🤖 AI予測履歴",
    "🌐 セクター分析",
    "📚 歴史分析",
])
if st.sidebar.button("🔄 データ更新"):
    st.cache_data.clear()
    st.rerun()

# ─────────────────────────────────────────
SYMBOLS = {
    "日経225":  ("^N225",   "円",   "🗾"),
    "S&P500":   ("^GSPC",  "pt",   "🇺🇸"),
    "VIX":      ("^VIX",   "",     "😱"),
    "ドル円":   ("JPY=X",  "円",   "💴"),
    "金(Gold)": ("GC=F",   "$/oz", "🥇"),
    "NASDAQ":   ("^IXIC",  "pt",   "💻"),
}


# ─────────────────────────────────────────
if page == "🏠 メインダッシュボード":
    st.title("📊 市場AI秘書 ダッシュボード")
    st.caption(f"リアルタイム市場データ（15分遅延）| {datetime.now().strftime('%Y-%m-%d %H:%M JST')}")

    # 価格カード
    cols = st.columns(3)
    prices = {}
    for i, (name, (sym, unit, icon)) in enumerate(SYMBOLS.items()):
        data = fetch_price(sym)
        prices[name] = data
        if not data:
            continue
        latest = data["latest"]
        chg = data["change_pct"]
        color = "normal" if abs(chg) < 0.5 else ("inverse" if chg < 0 else "off")
        col = cols[i % 3]
        with col:
            st.metric(
                label=f"{icon} {name}",
                value=f"{latest:,.2f} {unit}",
                delta=f"{chg:+.2f}%",
                delta_color="normal" if chg >= 0 else "inverse",
            )

    st.markdown("---")

    # 最新レポートリンク
    report_url = "https://youn24.github.io/market-ai-secretary"
    st.markdown(f"### 📄 最新HTMLレポート")
    st.markdown(f"[📊 レポートを開く]({report_url})")

    # AI予測サマリー
    st.markdown("### 🤖 AI予測精度")
    preds = load_predictions()
    verified = [p for p in preds if p.get("verified")]
    if len(verified) >= 3:
        wins = sum(1 for p in verified if p.get("correct"))
        rate = wins / len(verified) * 100
        col1, col2, col3 = st.columns(3)
        col1.metric("検証済み予測", f"{len(verified)}件")
        col2.metric("正解数", f"{wins}件")
        col3.metric("正解率", f"{rate:.1f}%")
    else:
        st.info(f"予測データ蓄積中... （{len(preds)}件 / 最低3件必要）")

    # VIX警戒ゾーン表示
    vix_data = prices.get("VIX", {})
    if vix_data and vix_data.get("latest"):
        vix = vix_data["latest"]
        if vix >= 30:
            st.error(f"⚠️ VIX警戒: {vix:.1f} — パニック水準！急落リスク高")
        elif vix >= 20:
            st.warning(f"⚠️ VIX注意: {vix:.1f} — 警戒水準。リスク管理を")
        else:
            st.success(f"✅ VIX安定: {vix:.1f} — 市場は落ち着いています")


# ─────────────────────────────────────────
elif page == "📈 価格チャート":
    st.title("📈 価格チャート")
    selected = st.selectbox("銘柄を選択", list(SYMBOLS.keys()))
    period_map = {"1ヶ月": "1mo", "3ヶ月": "3mo", "6ヶ月": "6mo", "1年": "1y", "5年": "5y"}
    period_label = st.select_slider("期間", options=list(period_map.keys()), value="6ヶ月")
    period = period_map[period_label]

    sym, unit, icon = SYMBOLS[selected]

    @st.cache_data(ttl=300)
    def fetch_period(symbol, p):
        url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range={p}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            resp = urllib.request.urlopen(req, context=_ctx, timeout=15)
            data = json.loads(resp.read())
            r = data["chart"]["result"][0]
            dates = [datetime.fromtimestamp(t).strftime("%Y-%m-%d") for t in r["timestamp"]]
            closes = r["indicators"]["quote"][0]["close"]
            df = pd.DataFrame({"Close": closes}, index=pd.to_datetime(dates)).dropna()
            return df
        except Exception:
            return pd.DataFrame()

    df = fetch_period(sym, period)
    if not df.empty:
        latest = df["Close"].iloc[-1]
        first = df["Close"].iloc[0]
        total_chg = (latest - first) / first * 100
        col1, col2 = st.columns(2)
        col1.metric(f"{icon} {selected}", f"{latest:,.2f} {unit}",
                    delta=f"{total_chg:+.2f}% ({period_label})")

        # 移動平均追加
        df["MA25"] = df["Close"].rolling(25).mean()
        df["MA75"] = df["Close"].rolling(75).mean()

        import plotly.graph_objects as go
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df.index, y=df["Close"], name=selected,
                                 line=dict(color="#00d4ff", width=2)))
        fig.add_trace(go.Scatter(x=df.index, y=df["MA25"], name="25日MA",
                                 line=dict(color="#ff6b35", width=1, dash="dot")))
        fig.add_trace(go.Scatter(x=df.index, y=df["MA75"], name="75日MA",
                                 line=dict(color="#ffcc00", width=1, dash="dot")))
        fig.update_layout(
            paper_bgcolor="#07111e", plot_bgcolor="#0d1f33",
            font_color="white", height=450,
            xaxis=dict(gridcolor="#1a2a3a"),
            yaxis=dict(gridcolor="#1a2a3a"),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.error("データ取得失敗")


# ─────────────────────────────────────────
elif page == "🤖 AI予測履歴":
    st.title("🤖 AI予測履歴")
    preds = load_predictions()
    if not preds:
        st.info("まだ予測データがありません。毎朝7:30のGitHub Actions実行後に蓄積されます。")
    else:
        df = pd.DataFrame(preds)
        verified = df[df.get("verified", pd.Series([False]*len(df))).fillna(False)]
        st.write(f"総予測数: {len(df)}件 / 検証済み: {len(verified)}件")
        if len(verified) > 0:
            wins = verified["correct"].sum() if "correct" in verified.columns else 0
            st.metric("正解率", f"{wins/len(verified)*100:.1f}%", delta=f"{wins}勝{len(verified)-wins}敗")
        cols_show = [c for c in ["date", "direction", "correct", "verified", "actual_change_pct"] if c in df.columns]
        st.dataframe(df[cols_show].tail(30).sort_values("date", ascending=False) if "date" in df.columns else df.tail(30))


# ─────────────────────────────────────────
elif page == "🌐 セクター分析":
    st.title("🌐 米国セクターローテーション")
    SECTORS = {
        "XLK": "テクノロジー", "XLF": "金融", "XLE": "エネルギー",
        "XLV": "ヘルスケア", "XLI": "資本財", "XLY": "一般消費財",
        "XLP": "生活必需品", "XLC": "通信", "XLB": "素材",
        "XLU": "公益", "XLRE": "不動産",
    }

    @st.cache_data(ttl=300)
    def fetch_sectors():
        results = {}
        for sym, name in SECTORS.items():
            url = f"https://query2.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=1mo"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            try:
                resp = urllib.request.urlopen(req, context=_ctx, timeout=10)
                data = json.loads(resp.read())
                r = data["chart"]["result"][0]
                closes = [c for c in r["indicators"]["quote"][0]["close"] if c]
                if len(closes) >= 2:
                    chg_1d = (closes[-1] - closes[-2]) / closes[-2] * 100
                    chg_1m = (closes[-1] - closes[0]) / closes[0] * 100
                    results[sym] = {"name": name, "1d": chg_1d, "1m": chg_1m, "price": closes[-1]}
            except Exception:
                pass
        return results

    sectors = fetch_sectors()
    if sectors:
        df_sec = pd.DataFrame(sectors).T
        df_sec = df_sec.sort_values("1d", ascending=False)

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("日次変化率 TOP")
            st.dataframe(
                df_sec[["name", "1d", "1m"]].rename(columns={"name":"セクター","1d":"前日比%","1m":"1ヶ月%"}),
                use_container_width=True
            )
        with col2:
            import plotly.express as px
            fig = px.bar(df_sec.reset_index(), x="name", y="1d",
                         color="1d", color_continuous_scale="RdYlGn",
                         title="セクター別 前日比%")
            fig.update_layout(paper_bgcolor="#07111e", plot_bgcolor="#0d1f33",
                              font_color="white", height=350)
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.error("セクターデータ取得失敗")


# ─────────────────────────────────────────
elif page == "📚 歴史分析":
    st.title("📚 長期歴史分析（20年）")
    st.info("過去20年のデータで現在の市場を歴史的文脈から読み解きます")

    @st.cache_data(ttl=3600)
    def fetch_long_history(symbol, period="20y"):
        url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range={period}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            resp = urllib.request.urlopen(req, context=_ctx, timeout=20)
            data = json.loads(resp.read())
            r = data["chart"]["result"][0]
            dates = [datetime.fromtimestamp(t).strftime("%Y-%m-%d") for t in r["timestamp"]]
            closes = r["indicators"]["quote"][0]["close"]
            df = pd.DataFrame({"Close": closes}, index=pd.to_datetime(dates)).dropna()
            return df
        except Exception:
            return pd.DataFrame()

    import plotly.graph_objects as go

    selected_sym = st.selectbox("銘柄", ["S&P500 (^GSPC)", "日経225 (^N225)", "VIX (^VIX)"])
    sym_map = {"S&P500 (^GSPC)": "^GSPC", "日経225 (^N225)": "^N225", "VIX (^VIX)": "^VIX"}
    sym = sym_map[selected_sym]

    with st.spinner("20年分データを取得中..."):
        df = fetch_long_history(sym)

    if not df.empty:
        latest = df["Close"].iloc[-1]
        percentile = (df["Close"] < latest).sum() / len(df) * 100
        st.metric("現在値", f"{latest:,.2f}", delta=f"過去20年中 {percentile:.1f}%ile")

        # 長期チャート + 年次注釈
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df.index, y=df["Close"], fill="tozeroy",
                                 line=dict(color="#00d4ff", width=1.5),
                                 fillcolor="rgba(0,212,255,0.1)", name=selected_sym))

        # リセッション帯（主要な暴落期）
        recessions = [
            ("2008-09-01", "2009-03-31", "リーマンショック"),
            ("2020-02-20", "2020-03-23", "コロナショック"),
        ]
        for start, end, label in recessions:
            fig.add_vrect(x0=start, x1=end, fillcolor="red", opacity=0.15,
                          annotation_text=label, annotation_position="top left",
                          annotation_font_color="white")

        fig.update_layout(
            paper_bgcolor="#07111e", plot_bgcolor="#0d1f33",
            font_color="white", height=500,
            title=f"{selected_sym} 長期チャート（20年）",
            xaxis=dict(gridcolor="#1a2a3a"),
            yaxis=dict(gridcolor="#1a2a3a"),
        )
        st.plotly_chart(fig, use_container_width=True)

        col1, col2, col3 = st.columns(3)
        col1.metric("20年最高値", f"{df['Close'].max():,.2f}")
        col2.metric("20年最安値", f"{df['Close'].min():,.2f}")
        col3.metric("歴史的位置", f"{percentile:.1f}%ile")
    else:
        st.error("データ取得失敗")
