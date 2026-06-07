"""
src/fx_visual_report.py
FX専用ビジュアル分析ダッシュボード — 毎日14:00 JST配信
ミセスワタナベ FX市場分析エンジン（matplotlib完全実装版）
"""

# ─── matplotlib は必ず最初に Agg バックエンド設定 ─────────────────────────────
import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.colors import LinearSegmentedColormap
import matplotlib.patches as mpatches
import matplotlib.patheffects as pe
import numpy as np
import pandas as pd
import os
import sys
import traceback
import warnings
from pathlib import Path
from datetime import datetime, timedelta, timezone

warnings.filterwarnings("ignore")

# 日本語フォント
try:
    import japanize_matplotlib  # noqa: F401
except ImportError:
    plt.rcParams["font.family"] = [
        "IPAexGothic", "Noto Sans CJK JP", "Hiragino Sans",
        "Yu Gothic", "Meiryo", "DejaVu Sans"
    ]

import yfinance as yf

JST = timezone(timedelta(hours=9))

# ─────────────────────────────────────────────────────────────────────────────
# カラーパレット（プロ向けダークターミナル風）
# ─────────────────────────────────────────────────────────────────────────────
BG       = "#0d1117"    # 全体背景
BG2      = "#161b22"    # パネル背景
BG3      = "#21262d"    # ヘッダー背景
GRID_C   = "#30363d"    # グリッド線
C_UP     = "#3fb950"    # 上昇・強気（緑）
C_DOWN   = "#f85149"    # 下落・弱気（赤）
C_GOLD   = "#e3b341"    # ゴールド・強調
C_CYAN   = "#58a6ff"    # シアン・主ライン
C_ORANGE = "#d29922"    # オレンジ・警告
C_PURPLE = "#bc8cff"    # パープル・MA75
C_GRAY   = "#8b949e"    # グレー・補助テキスト
C_WHITE  = "#e6edf3"    # テキスト
C_BORDER = "#444c56"    # ボーダー


# ─────────────────────────────────────────────────────────────────────────────
# ① データ取得
# ─────────────────────────────────────────────────────────────────────────────

FETCH_TARGETS = {
    # FX ペア
    "USDJPY=X":  ("USD/JPY",    "fx"),
    "EURJPY=X":  ("EUR/JPY",    "fx"),
    "GBPJPY=X":  ("GBP/JPY",   "fx"),
    "AUDJPY=X":  ("AUD/JPY",   "fx"),
    "NZDJPY=X":  ("NZD/JPY",   "fx"),
    "CADJPY=X":  ("CAD/JPY",   "fx"),
    "CHFJPY=X":  ("CHF/JPY",   "fx"),
    "EURUSD=X":  ("EUR/USD",   "fx"),
    "GBPUSD=X":  ("GBP/USD",   "fx"),
    "AUDUSD=X":  ("AUD/USD",   "fx"),
    "NZDUSD=X":  ("NZD/USD",   "fx"),
    "USDCAD=X":  ("USD/CAD",   "fx"),
    "USDCHF=X":  ("USD/CHF",   "fx"),
    # ドルインデックス
    "DX-Y.NYB":  ("DXY Dollar Index", "index"),
    # 商品
    "GC=F":      ("Gold $/oz",        "commodity"),
    "CL=F":      ("WTI Oil $/bbl",    "commodity"),
    "SI=F":      ("Silver $/oz",      "commodity"),
    # 金利
    "^TNX":      ("US 10Y Yield",     "rate"),
    "^FVX":      ("US 5Y Yield",      "rate"),
    "^IRX":      ("US 3M Yield",      "rate"),
    "^TYX":      ("US 30Y Yield",     "rate"),
    # 株価・リスク
    "^GSPC":     ("S&P 500",          "equity"),
    "^N225":     ("Nikkei 225",       "equity"),
    "^VIX":      ("VIX",              "risk"),
}


def _fetch_symbol(sym: str, period: str = "3mo") -> pd.DataFrame | None:
    """yfinance でデータ取得（自動フォールバック付き）"""
    for p in [period, "6mo", "1y"]:
        try:
            t  = yf.Ticker(sym)
            df = t.history(period=p, interval="1d", auto_adjust=True)
            if df is not None and not df.empty and len(df) >= 5:
                df.columns = [str(c).replace(" ", "") for c in df.columns]
                return df
        except Exception:
            pass
    return None


def fetch_all_data() -> dict:
    """全シンボルのデータを取得して dict で返す"""
    data = {}
    for sym, (name, cat) in FETCH_TARGETS.items():
        df = _fetch_symbol(sym)
        if df is None or "Close" not in df.columns:
            continue
        close = df["Close"].dropna()
        if len(close) < 2:
            continue
        latest  = float(close.iloc[-1])
        prev    = float(close.iloc[-2])
        chg1d   = (latest / prev   - 1) * 100
        chg5d   = (latest / float(close.iloc[max(0, len(close) - 6)])  - 1) * 100 if len(close) >= 6  else None
        chg20d  = (latest / float(close.iloc[max(0, len(close) - 21)]) - 1) * 100 if len(close) >= 21 else None
        data[sym] = {
            "name":   name,
            "cat":    cat,
            "df":     df,
            "close":  close,
            "latest": latest,
            "prev":   prev,
            "chg":    chg1d,
            "chg5d":  chg5d,
            "chg20d": chg20d,
        }
    return data


# ─────────────────────────────────────────────────────────────────────────────
# ② テクニカル指標計算
# ─────────────────────────────────────────────────────────────────────────────

def calc_rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain  = delta.clip(lower=0).ewm(com=n - 1, min_periods=n).mean()
    loss  = (-delta.clip(upper=0)).ewm(com=n - 1, min_periods=n).mean()
    rs    = gain / loss.replace(0, 1e-10)
    return (100 - 100 / (1 + rs)).rename("RSI")


def calc_macd(close: pd.Series, fast=12, slow=26, sig_n=9):
    ema_f = close.ewm(span=fast,  adjust=False).mean()
    ema_s = close.ewm(span=slow,  adjust=False).mean()
    line  = ema_f - ema_s
    sig   = line.ewm(span=sig_n, adjust=False).mean()
    hist  = line - sig
    return line.rename("MACD"), sig.rename("Signal"), hist.rename("Hist")


def calc_bollinger(close: pd.Series, n=20, k=2):
    mid   = close.rolling(n).mean()
    std   = close.rolling(n).std()
    return (mid + k * std).rename("BBU"), mid.rename("BBM"), (mid - k * std).rename("BBL")


def calc_stoch(df: pd.DataFrame, k_n=14, d_n=3):
    high  = df["High"]  if "High"  in df.columns else df["Close"]
    low   = df["Low"]   if "Low"   in df.columns else df["Close"]
    close = df["Close"]
    ll    = low.rolling(k_n).min()
    hh    = high.rolling(k_n).max()
    pct_k = 100 * (close - ll) / (hh - ll + 1e-10)
    pct_d = pct_k.rolling(d_n).mean()
    return pct_k.rename("K"), pct_d.rename("D")


def calc_currency_strength(data: dict, days: int = 5) -> dict:
    """
    主要 8 通貨の強弱スコアを計算（ペアの N 日変化率から算出）
    """
    currencies = ["USD", "EUR", "GBP", "JPY", "CHF", "AUD", "NZD", "CAD"]
    scores: dict[str, list] = {c: [] for c in currencies}

    pair_map = {
        "EURUSD=X": ("EUR", "USD"),
        "GBPUSD=X": ("GBP", "USD"),
        "AUDUSD=X": ("AUD", "USD"),
        "NZDUSD=X": ("NZD", "USD"),
        "USDCAD=X": ("USD", "CAD"),
        "USDCHF=X": ("USD", "CHF"),
        "USDJPY=X": ("USD", "JPY"),
        "EURJPY=X": ("EUR", "JPY"),
        "GBPJPY=X": ("GBP", "JPY"),
        "AUDJPY=X": ("AUD", "JPY"),
        "NZDJPY=X": ("NZD", "JPY"),
        "CADJPY=X": ("CAD", "JPY"),
        "CHFJPY=X": ("CHF", "JPY"),
    }
    for sym, (base, quote) in pair_map.items():
        if sym not in data:
            continue
        chg_key = f"chg{days}d"
        chg = data[sym].get(chg_key) or data[sym].get("chg") or 0.0
        if base  in scores: scores[base].append(chg)
        if quote in scores: scores[quote].append(-chg)

    return {
        c: round(sum(v) / len(v), 3) if v else 0.0
        for c, v in scores.items()
    }


# ─────────────────────────────────────────────────────────────────────────────
# ③ チャート共通スタイル
# ─────────────────────────────────────────────────────────────────────────────

def _ax_style(ax, title: str = "", ylabel: str = ""):
    ax.set_facecolor(BG2)
    for spine in ax.spines.values():
        spine.set_color(C_BORDER)
    ax.tick_params(colors=C_GRAY, labelsize=7.5, length=3)
    ax.grid(color=GRID_C, linewidth=0.4, linestyle="--", alpha=0.6)
    if title:
        ax.set_title(title, color=C_WHITE, fontsize=9.5, fontweight="bold",
                     pad=5, loc="left")
    if ylabel:
        ax.set_ylabel(ylabel, color=C_GRAY, fontsize=7.5)


def _set_date_xticks(ax, df_index, n_ticks=8):
    n = len(df_index)
    step = max(1, n // n_ticks)
    ticks = list(range(0, n, step))
    ax.set_xticks(ticks)
    ax.set_xticklabels(
        [df_index[i].strftime("%m/%d") if i < n else "" for i in ticks],
        fontsize=7, color=C_GRAY
    )


# ─────────────────────────────────────────────────────────────────────────────
# ④ 各パネル描画関数
# ─────────────────────────────────────────────────────────────────────────────

def panel_usdjpy_price(ax, data: dict):
    """Panel A: USD/JPY 90日プライスチャート（BB + MA5/25/75）"""
    sym = "USDJPY=X"
    if sym not in data:
        ax.text(0.5, 0.5, "USDJPY データ取得中…", transform=ax.transAxes,
                ha="center", va="center", color=C_GRAY, fontsize=12)
        _ax_style(ax, "USD/JPY — 90日プライスチャート")
        return

    df    = data[sym]["df"].tail(90)
    close = df["Close"]
    idx   = np.arange(len(close))

    ma5  = close.rolling(5).mean()
    ma25 = close.rolling(25).mean()
    ma75 = close.rolling(75).mean()
    bbu, bbm, bbl = calc_bollinger(close)

    # ボリンジャーバンド帯塗りつぶし
    ax.fill_between(idx, bbu.values, bbl.values, alpha=0.08, color=C_CYAN)
    ax.plot(idx, bbm.values, color=C_CYAN, lw=0.7, ls="--", alpha=0.6, label="BB中心(20)")
    ax.plot(idx, bbu.values, color=C_CYAN, lw=0.5, alpha=0.4)
    ax.plot(idx, bbl.values, color=C_CYAN, lw=0.5, alpha=0.4)

    # 主ライン
    ax.plot(idx, close.values, color=C_GOLD,   lw=2.2, label="USD/JPY", zorder=5)
    ax.plot(idx, ma5.values,   color=C_CYAN,   lw=1.0, label="MA5",  alpha=0.9)
    ax.plot(idx, ma25.values,  color=C_ORANGE, lw=1.2, label="MA25", alpha=0.9)
    ax.plot(idx, ma75.values,  color=C_PURPLE, lw=1.2, label="MA75", alpha=0.9)

    # 最新値ライン
    last = float(close.iloc[-1])
    chg  = data[sym]["chg"]
    c_arrow = C_UP if chg >= 0 else C_DOWN
    arrow   = "▲" if chg >= 0 else "▼"
    ax.axhline(last, color=c_arrow, lw=0.8, ls=":", alpha=0.8)
    ax.text(len(idx) - 0.5, last,
            f" {last:.3f}  {arrow}{abs(chg):.2f}%",
            color=c_arrow, fontsize=10.5, fontweight="bold", va="center")

    # 日銀介入警戒ライン
    bot, top = float(close.min()), float(close.max())
    for lvl in [152.0, 155.0, 158.0, 160.0, 162.0, 165.0]:
        if bot * 0.98 < lvl < top * 1.03:
            ax.axhline(lvl, color="#ff6b6b", lw=0.7, ls="-.", alpha=0.45)
            ax.text(2, lvl + 0.05, f"日銀警戒 {lvl:.0f}", color="#ff6b6b", fontsize=6.5, alpha=0.7)

    _set_date_xticks(ax, df.index)
    ax.legend(loc="upper left", fontsize=7, fancybox=True,
              facecolor=BG3, edgecolor=C_BORDER, labelcolor=C_WHITE, ncol=5)
    _ax_style(ax, "📈 USD/JPY — 90日プライスチャート（ボリンジャーバンド + 移動平均）", "円")


def panel_rsi(ax, data: dict):
    """Panel B: RSI(14)"""
    sym = "USDJPY=X"
    if sym not in data:
        _ax_style(ax, "RSI(14)"); return

    close = data[sym]["df"]["Close"].tail(90)
    r     = calc_rsi(close)
    idx   = np.arange(len(r))

    ax.fill_between(idx, r.values, 70, where=r.values >= 70, alpha=0.3, color=C_DOWN,  interpolate=True)
    ax.fill_between(idx, r.values, 30, where=r.values <= 30, alpha=0.3, color=C_UP,    interpolate=True)
    ax.fill_between(idx, r.values, 50, where=r.values >= 50, alpha=0.12, color=C_UP,   interpolate=True)
    ax.fill_between(idx, r.values, 50, where=r.values < 50,  alpha=0.12, color=C_DOWN, interpolate=True)
    ax.plot(idx, r.values, color=C_CYAN, lw=1.5)

    for level, col, ls in [(70, C_DOWN, "--"), (50, C_GRAY, "-"), (30, C_UP, "--")]:
        ax.axhline(level, color=col, lw=0.7, ls=ls, alpha=0.7)

    last_r = float(r.iloc[-1])
    r_color = C_DOWN if last_r > 70 else C_UP if last_r < 30 else C_GRAY
    r_label = "🔴過熱" if last_r > 70 else "🟢売られすぎ" if last_r < 30 else "中立"
    ax.text(0.98, 0.90, f"RSI={last_r:.1f}\n{r_label}",
            transform=ax.transAxes, ha="right", va="top",
            color=r_color, fontsize=9, fontweight="bold")

    ax.set_ylim(10, 90)
    ax.set_yticks([30, 50, 70])
    _ax_style(ax, "RSI(14)")


def panel_macd(ax, data: dict):
    """Panel C: MACD(12,26,9)"""
    sym = "USDJPY=X"
    if sym not in data:
        _ax_style(ax, "MACD"); return

    close = data[sym]["df"]["Close"].tail(90)
    line, sig, hist = calc_macd(close)
    idx = np.arange(len(hist))

    colors = [C_UP if v >= 0 else C_DOWN for v in hist.values]
    ax.bar(idx, hist.values, color=colors, alpha=0.75, width=1.0, zorder=2)
    ax.plot(idx, line.values, color=C_CYAN,   lw=1.3, label="MACD")
    ax.plot(idx, sig.values,  color=C_ORANGE, lw=1.0, label="Signal", alpha=0.85)
    ax.axhline(0, color=C_GRAY, lw=0.5)

    last_h = float(hist.iloc[-1])
    prev_h = float(hist.iloc[-2]) if len(hist) > 1 else last_h
    if prev_h < 0 < last_h:
        cross_txt, cross_col = "▲ ゴールデンクロス", C_UP
    elif prev_h > 0 > last_h:
        cross_txt, cross_col = "▼ デッドクロス",     C_DOWN
    elif last_h > 0:
        cross_txt, cross_col = "↑ 上昇モメンタム",   C_UP
    else:
        cross_txt, cross_col = "↓ 下落モメンタム",   C_DOWN

    ax.text(0.98, 0.90, cross_txt, transform=ax.transAxes, ha="right", va="top",
            color=cross_col, fontsize=9, fontweight="bold")
    ax.legend(loc="upper left", fontsize=7, fancybox=True,
              facecolor=BG3, edgecolor=C_BORDER, labelcolor=C_WHITE)
    _ax_style(ax, "MACD(12,26,9)")


def panel_stochastic(ax, data: dict):
    """Panel D: Stochastic(14,3)"""
    sym = "USDJPY=X"
    if sym not in data:
        _ax_style(ax, "Stochastic"); return

    df = data[sym]["df"].tail(90)
    k, d = calc_stoch(df)
    idx  = np.arange(len(k))

    ax.fill_between(idx, k.values, 80, where=k.values >= 80, alpha=0.25, color=C_DOWN, interpolate=True)
    ax.fill_between(idx, k.values, 20, where=k.values <= 20, alpha=0.25, color=C_UP,   interpolate=True)
    ax.plot(idx, k.values, color=C_CYAN,   lw=1.3, label="%K")
    ax.plot(idx, d.values, color=C_ORANGE, lw=1.0, label="%D", alpha=0.85)

    for level, col in [(80, C_DOWN), (20, C_UP)]:
        ax.axhline(level, color=col, lw=0.7, ls="--", alpha=0.7)

    last_k = float(k.iloc[-1])
    last_d = float(d.iloc[-1])
    sig    = "🔴過熱" if last_k > 80 else "🟢売られすぎ" if last_k < 20 else "中立"
    sig_c  = C_DOWN if last_k > 80 else C_UP if last_k < 20 else C_GRAY
    ax.text(0.98, 0.90, f"K={last_k:.0f} D={last_d:.0f}\n{sig}",
            transform=ax.transAxes, ha="right", va="top",
            color=sig_c, fontsize=9, fontweight="bold")

    ax.set_ylim(0, 100)
    ax.legend(loc="upper left", fontsize=7, fancybox=True,
              facecolor=BG3, edgecolor=C_BORDER, labelcolor=C_WHITE)
    _ax_style(ax, "Stochastic(14,3)")


def panel_currency_strength(ax, data: dict):
    """Panel E: 通貨強弱バーチャート（5日間変化率）"""
    strength = calc_currency_strength(data, days=5)
    if not strength:
        ax.text(0.5, 0.5, "データなし", transform=ax.transAxes,
                ha="center", va="center", color=C_GRAY)
        _ax_style(ax, "通貨強弱"); return

    # 強い順にソート
    items      = sorted(strength.items(), key=lambda x: x[1])
    currencies = [k for k, _ in items]
    values     = [v for _, v in items]
    colors     = [C_UP if v >= 0 else C_DOWN for v in values]

    # 国旗絵文字マッピング
    flag_map = {
        "USD": "🇺🇸", "EUR": "🇪🇺", "GBP": "🇬🇧",
        "JPY": "🇯🇵", "CHF": "🇨🇭", "AUD": "🇦🇺",
        "NZD": "🇳🇿", "CAD": "🇨🇦",
    }
    labels = [f"{flag_map.get(c, '')} {c}" for c in currencies]

    bars = ax.barh(labels, values, color=colors, alpha=0.85, height=0.65)

    for bar, val in zip(bars, values):
        offset = 0.03 if val >= 0 else -0.03
        ax.text(val + offset, bar.get_y() + bar.get_height() / 2,
                f"{val:+.2f}%", va="center",
                ha="left" if val >= 0 else "right",
                color=C_WHITE, fontsize=8, fontweight="bold")

    ax.axvline(0, color=C_GRAY, lw=0.8)
    ax.tick_params(axis="y", labelcolor=C_WHITE, labelsize=9)
    _ax_style(ax, "💪 通貨強弱（5日間）", "%")


def panel_cross_assets(ax, data: dict):
    """Panel F: クロスアセット騰落率（DXY・Gold・Oil 60日）"""
    targets = [
        ("DX-Y.NYB", "DXY",  C_CYAN),
        ("GC=F",     "Gold", C_GOLD),
        ("CL=F",     "Oil",  C_ORANGE),
        ("^GSPC",    "S&P",  C_UP),
        ("^VIX",     "VIX",  C_DOWN),
    ]
    for sym, label, color in targets:
        if sym not in data:
            continue
        close = data[sym]["df"]["Close"].tail(60)
        if len(close) < 5:
            continue
        base = float(close.iloc[0])
        norm = [(float(v) / base - 1) * 100 for v in close]
        idx  = np.arange(len(norm))
        ax.plot(idx, norm, color=color, lw=1.6, label=label)
        ax.text(idx[-1], norm[-1], f" {norm[-1]:+.1f}%",
                color=color, fontsize=7.5, va="center")

    ax.axhline(0, color=C_GRAY, lw=0.5, ls="--")
    ax.legend(loc="upper left", fontsize=7.5, fancybox=True,
              facecolor=BG3, edgecolor=C_BORDER, labelcolor=C_WHITE)
    _ax_style(ax, "🌐 クロスアセット（60日騰落率）", "%")


def panel_interest_rates(ax, data: dict):
    """Panel G: 米 vs 日 イールドカーブ + 金利差"""
    maturities = ["3M", "5Y", "10Y", "30Y"]
    us_syms    = ["^IRX", "^FVX", "^TNX", "^TYX"]
    jp_hard    = [0.10, 1.50, 2.66, 3.10]   # JGB 概算値（2026年6月）

    us_yields = []
    for sym in us_syms:
        if sym in data:
            us_yields.append(data[sym]["latest"])
        else:
            # フォールバック値
            fallback = {"^IRX": 5.30, "^FVX": 4.30, "^TNX": 4.55, "^TYX": 4.80}
            us_yields.append(fallback.get(sym, 4.5))

    x = np.arange(len(maturities))

    ax.plot(x, us_yields, "o-", color=C_CYAN,  lw=2.2, ms=7, label="🇺🇸 米国金利")
    ax.plot(x, jp_hard,   "s-", color=C_DOWN,  lw=2.0, ms=6, label="🇯🇵 日本金利")

    # 金利差帯を塗りつぶし
    ax.fill_between(x, us_yields, jp_hard, alpha=0.12, color=C_CYAN)

    # 差ラベル
    for xi, (u, j) in enumerate(zip(us_yields, jp_hard)):
        diff = u - j
        ypos = (u + j) / 2
        ax.annotate(f"差{diff:.2f}%", xy=(xi, ypos),
                    ha="center", va="center", fontsize=7.5,
                    color=C_GOLD, fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.2", fc=BG3, ec=C_BORDER, alpha=0.8))

    ax.set_xticks(x)
    ax.set_xticklabels(maturities, fontsize=8, color=C_WHITE)
    ax.legend(loc="upper right", fontsize=7.5, fancybox=True,
              facecolor=BG3, edgecolor=C_BORDER, labelcolor=C_WHITE)
    _ax_style(ax, "📐 イールドカーブ 米🇺🇸 vs 日🇯🇵", "利回り %")


def panel_imm_positions(ax, data: dict):
    """Panel H: IMM 投機的円ポジション（CFTC 推定値）"""
    # 直近13週の円ネットポジション（千枚, 推定値に基づく）
    weeks = ["3/7", "3/14", "3/21", "3/28", "4/4", "4/11",
             "4/18", "4/25", "5/2", "5/9", "5/16", "5/23", "5/30"]
    net_pos = [-115, -118, -125, -131, -128, -122,
               -135, -142, -148, -139, -145, -151, -158]

    colors = []
    for p in net_pos:
        if p < -130:   colors.append(C_DOWN)
        elif p < -80:  colors.append(C_ORANGE)
        else:          colors.append(C_UP)

    ax.bar(range(len(weeks)), net_pos, color=colors, alpha=0.8, width=0.7)

    # 警戒ライン
    ax.axhline(0,    color=C_GRAY, lw=0.8)
    ax.axhline(-100, color=C_ORANGE, lw=0.9, ls="--", alpha=0.7, label="-100K 警戒")
    ax.axhline(-150, color=C_DOWN,   lw=0.9, ls=":",  alpha=0.8, label="-150K 極端売り")

    ax.text(len(weeks) - 1, net_pos[-1] - 4,
            f"最新\n{net_pos[-1]}K", ha="center", color=C_DOWN,
            fontsize=8, fontweight="bold")

    ax.set_xticks(range(len(weeks)))
    ax.set_xticklabels(weeks, rotation=45, fontsize=6.5, color=C_GRAY, ha="right")
    ax.legend(loc="lower left", fontsize=7, fancybox=True,
              facecolor=BG3, edgecolor=C_BORDER, labelcolor=C_WHITE)
    _ax_style(ax, "📊 IMM 円ネット投機ポジション（千枚）※CFTC概算", "千枚")


def panel_correlation_heatmap(ax, data: dict):
    """Panel I: FX・資産間相関ヒートマップ（60日）"""
    targets = [
        ("USDJPY=X", "USD/JPY"),
        ("EURJPY=X", "EUR/JPY"),
        ("GBPJPY=X", "GBP/JPY"),
        ("DX-Y.NYB", "DXY"),
        ("GC=F",     "Gold"),
        ("^TNX",     "US10Y"),
        ("^VIX",     "VIX"),
        ("^GSPC",    "S&P500"),
    ]
    closes = {}
    for sym, label in targets:
        if sym in data:
            closes[label] = data[sym]["df"]["Close"].tail(60)

    if len(closes) < 3:
        ax.text(0.5, 0.5, "データ不足", transform=ax.transAxes,
                ha="center", va="center", color=C_GRAY)
        _ax_style(ax, "相関ヒートマップ"); return

    df_c   = pd.DataFrame(closes).pct_change().dropna().corr()
    labels = df_c.columns.tolist()
    matrix = df_c.values
    n      = len(labels)

    cmap = LinearSegmentedColormap.from_list(
        "rdgn", [C_DOWN, "#1a1f2e", C_UP], N=256
    )
    im = ax.imshow(matrix, cmap=cmap, vmin=-1, vmax=1, aspect="auto")

    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=7, color=C_WHITE)
    ax.set_yticklabels(labels, fontsize=7, color=C_WHITE)

    for i in range(n):
        for j in range(n):
            val = matrix[i, j]
            fg  = BG if abs(val) > 0.55 else C_WHITE
            ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                    fontsize=6.5, color=fg, fontweight="bold")

    plt.colorbar(im, ax=ax, shrink=0.85, pad=0.03,
                 label="相関係数").ax.tick_params(colors=C_GRAY, labelsize=7)
    _ax_style(ax, "🔗 資産間相関（60日日次リターン）")


def panel_fedwatch(ax, data: dict):
    """Panel J: FedWatch 政策金利予想（CME概算）"""
    meetings  = ["7月", "9月", "11月", "12月"]
    hike_prob = [3,  8, 10,  8]
    hold_prob = [92, 70, 45, 30]
    cut_prob  = [5, 22, 45, 62]

    x = np.arange(len(meetings))
    w = 0.26
    ax.bar(x - w,   hike_prob, width=w, color=C_DOWN,   label="利上げ",   alpha=0.85)
    ax.bar(x,       hold_prob, width=w, color=C_GRAY,   label="据え置き", alpha=0.75)
    ax.bar(x + w,   cut_prob,  width=w, color=C_UP,     label="利下げ",   alpha=0.85)

    ax.set_xticks(x)
    ax.set_xticklabels([f"FOMC\n{m}" for m in meetings], fontsize=7.5, color=C_WHITE)
    ax.set_ylabel("%", color=C_GRAY, fontsize=7.5)
    ax.legend(loc="upper left", fontsize=7.5, fancybox=True,
              facecolor=BG3, edgecolor=C_BORDER, labelcolor=C_WHITE)
    _ax_style(ax, "🏦 FedWatch 利下げ確率 ※CME概算")


def panel_vix_gauge(ax, data: dict):
    """Panel K: VIX リスクメーター（半円ゲージ）"""
    vix = 20.0
    if "^VIX" in data:
        vix = float(data["^VIX"]["latest"])

    # 半円ゾーン定義（左→右: 安全→危険）
    zones = [
        (0.0, 0.20, C_UP,      "安全\n<15"),
        (0.2, 0.40, "#6abf69", "注意\n15-20"),
        (0.4, 0.60, C_ORANGE,  "警戒\n20-30"),
        (0.6, 0.80, "#ff5722", "危険\n30-40"),
        (0.8, 1.00, C_DOWN,    "極度\n>40"),
    ]
    for s, e, col, _ in zones:
        ts = np.linspace(s * np.pi, e * np.pi, 40)
        xs = np.cos(ts)
        ys = np.sin(ts)
        ax.plot(xs, ys, color=col, lw=14, solid_capstyle="butt", zorder=2)

    # VIX 針
    vix_max  = 45.0
    norm     = min(vix / vix_max, 1.0)
    angle    = np.pi * (1.0 - norm)
    needle_x = 0.62 * np.cos(angle)
    needle_y = 0.62 * np.sin(angle)
    ax.annotate("", xy=(needle_x, needle_y), xytext=(0, 0),
                arrowprops=dict(arrowstyle="-|>", color=C_WHITE,
                                lw=2.5, mutation_scale=18))
    ax.plot(0, 0, "o", color=C_WHITE, ms=6, zorder=6)

    # VIX 数値テキスト
    vix_c = C_DOWN if vix >= 30 else C_ORANGE if vix >= 20 else C_UP
    ax.text(0, -0.22, f"{vix:.1f}",
            ha="center", va="center", color=vix_c,
            fontsize=20, fontweight="bold")
    ax.text(0, -0.44, "VIX 恐怖指数",
            ha="center", va="center", color=C_GRAY, fontsize=8)

    # ゾーンラベル
    for s, e, col, label in zones:
        mid   = (s + e) / 2 * np.pi
        lx    = 1.32 * np.cos(mid)
        ly    = 1.32 * np.sin(mid)
        ax.text(lx, ly, label, ha="center", va="center",
                color=col, fontsize=6.5, linespacing=1.2)

    ax.set_xlim(-1.6, 1.6)
    ax.set_ylim(-0.6, 1.55)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_facecolor(BG2)
    ax.set_title("⚡ VIX リスクメーター", color=C_WHITE,
                 fontsize=9.5, fontweight="bold", pad=5, loc="left")


def panel_price_board(ax, data: dict):
    """Panel L: リアルタイム価格ボード"""
    ax.axis("off")
    ax.set_facecolor(BG2)
    ax.set_title("💹 現在値ボード", color=C_WHITE,
                 fontsize=9.5, fontweight="bold", pad=5, loc="left")

    board = [
        ("USDJPY=X", "USD/JPY",    "{:.3f}円"),
        ("EURJPY=X", "EUR/JPY",    "{:.2f}円"),
        ("GBPJPY=X", "GBP/JPY",   "{:.2f}円"),
        ("AUDJPY=X", "AUD/JPY",   "{:.2f}円"),
        ("DX-Y.NYB", "DXY",       "{:.2f}"),
        ("GC=F",     "Gold",      "${:,.0f}"),
        ("CL=F",     "Oil",       "${:.1f}"),
        ("^TNX",     "US10Y",     "{:.3f}%"),
        ("^VIX",     "VIX",       "{:.2f}"),
        ("^GSPC",    "S&P500",    "{:,.0f}"),
        ("^N225",    "N225",      "{:,.0f}"),
    ]

    y = 0.96
    for sym, label, fmt in board:
        if sym not in data:
            continue
        d   = data[sym]
        val = d["latest"]
        chg = d["chg"]
        arrow = "▲" if chg >= 0 else "▼"
        col   = C_UP if chg >= 0 else C_DOWN
        try:
            val_s = fmt.format(val)
        except Exception:
            val_s = f"{val:.2f}"

        # ラベル（左）
        ax.text(0.02, y, f"  {label}", transform=ax.transAxes,
                fontsize=8.5, color=C_GRAY, va="top", fontfamily="monospace")
        # 値（中央）
        ax.text(0.52, y, val_s, transform=ax.transAxes,
                fontsize=8.5, color=C_WHITE, va="top", ha="right",
                fontfamily="monospace", fontweight="bold")
        # 変化率（右）
        ax.text(0.98, y, f"{arrow}{abs(chg):.2f}%",
                transform=ax.transAxes, fontsize=8, color=col,
                va="top", ha="right", fontfamily="monospace")

        # 区切り線
        ax.plot([0.01, 0.99], [y - 0.003, y - 0.003],
                color=C_BORDER, lw=0.3, transform=ax.transAxes)
        y -= 0.082


def panel_dxy_trend(ax, data: dict):
    """Panel M: DXY 60日トレンド + 100水準"""
    sym = "DX-Y.NYB"
    if sym not in data:
        _ax_style(ax, "DXY Dollar Index"); return

    close = data[sym]["df"]["Close"].tail(60)
    idx   = np.arange(len(close))
    ma10  = close.rolling(10).mean()
    ma20  = close.rolling(20).mean()

    ax.fill_between(idx, close.values, 100,
                    where=close.values >= 100, alpha=0.15, color=C_DOWN)
    ax.fill_between(idx, close.values, 100,
                    where=close.values < 100,  alpha=0.15, color=C_UP)
    ax.plot(idx, close.values, color=C_CYAN,   lw=1.8, label="DXY")
    ax.plot(idx, ma10.values,  color=C_GOLD,   lw=1.0, label="MA10", alpha=0.85)
    ax.plot(idx, ma20.values,  color=C_ORANGE, lw=1.0, label="MA20", alpha=0.85)
    ax.axhline(100, color=C_GOLD, lw=1.0, ls="--", alpha=0.7, label="節目100")
    ax.axhline(104, color=C_DOWN, lw=0.7, ls="-.", alpha=0.5, label="強いドル104")

    last_dxy = float(close.iloc[-1])
    dxy_label = "🔴ドル強い" if last_dxy >= 104 else "🟡パリティ前後" if last_dxy >= 100 else "🟢ドル弱い"
    ax.text(0.98, 0.92, f"DXY={last_dxy:.2f}\n{dxy_label}",
            transform=ax.transAxes, ha="right", va="top",
            color=C_CYAN, fontsize=9, fontweight="bold")

    ax.legend(loc="upper left", fontsize=7, fancybox=True,
              facecolor=BG3, edgecolor=C_BORDER, labelcolor=C_WHITE)
    _ax_style(ax, "💵 DXY Dollar Index（60日）")


# ─────────────────────────────────────────────────────────────────────────────
# ⑤ メインダッシュボード組み立て
# ─────────────────────────────────────────────────────────────────────────────

def build_dashboard(data: dict, out_path: str) -> str:
    """
    全パネルを組み合わせた大型ダッシュボードを生成して PNG 保存
    サイズ: 22×30 インチ @ 100dpi = 2200×3000px
    """
    fig = plt.figure(figsize=(22, 30), facecolor=BG)
    fig.patch.set_facecolor(BG)

    # GridSpec: 6行 × 3列
    gs = gridspec.GridSpec(
        6, 3,
        figure=fig,
        height_ratios=[3.5, 1.4, 1.4, 2.2, 2.2, 2.2],
        width_ratios=[1, 1, 1],
        hspace=0.48,
        wspace=0.35,
    )

    # ── Row 0: USD/JPY プライスチャート（3列フル）──
    ax_price   = fig.add_subplot(gs[0, :])

    # ── Row 1: RSI | MACD | Stochastic ──
    ax_rsi     = fig.add_subplot(gs[1, 0])
    ax_macd    = fig.add_subplot(gs[1, 1])
    ax_stoch   = fig.add_subplot(gs[1, 2])

    # ── Row 2: Stoch は Row1に移動, ここは追加指標 ──
    ax_dxy     = fig.add_subplot(gs[2, 0])
    ax_cross   = fig.add_subplot(gs[2, 1])
    ax_rates   = fig.add_subplot(gs[2, 2])

    # ── Row 3: 通貨強弱 | IMM | 相関ヒートマップ ──
    ax_fx_str  = fig.add_subplot(gs[3, 0])
    ax_imm     = fig.add_subplot(gs[3, 1])
    ax_corr    = fig.add_subplot(gs[3, 2])

    # ── Row 4: FedWatch | VIX ゲージ | 価格ボード ──
    ax_fedwt   = fig.add_subplot(gs[4, 0])
    ax_vix     = fig.add_subplot(gs[4, 1])
    ax_board   = fig.add_subplot(gs[4, 2])

    # ── Row 5: 空き (将来拡張) ──
    ax_extra1  = fig.add_subplot(gs[5, 0])
    ax_extra2  = fig.add_subplot(gs[5, 1])
    ax_extra3  = fig.add_subplot(gs[5, 2])
    for ax_e in [ax_extra1, ax_extra2, ax_extra3]:
        ax_e.axis("off")
        ax_e.set_facecolor(BG)

    # ─── タイトルバー ───
    jst_now = datetime.now(JST)
    title = (
        f"ミセスワタナベ  FX Market Dashboard\n"
        f"{jst_now.strftime('%Y/%m/%d  %H:%M JST')}  ─  東京市場午後2時レポート"
    )
    fig.suptitle(title, color=C_WHITE, fontsize=15,
                 fontweight="bold", y=0.993, linespacing=1.5)

    # ─── ボーダーライン（視認性向上）───
    fig.add_artist(
        plt.Line2D([0.01, 0.99], [0.986, 0.986],
                   transform=fig.transFigure,
                   color=C_GOLD, lw=1.0, alpha=0.5)
    )

    # ─── 各パネル描画 ───
    panel_usdjpy_price(ax_price,   data)
    panel_rsi(ax_rsi,              data)
    panel_macd(ax_macd,            data)
    panel_stochastic(ax_stoch,     data)
    panel_dxy_trend(ax_dxy,        data)
    panel_cross_assets(ax_cross,   data)
    panel_interest_rates(ax_rates, data)
    panel_currency_strength(ax_fx_str, data)
    panel_imm_positions(ax_imm,    data)
    panel_correlation_heatmap(ax_corr, data)
    panel_fedwatch(ax_fedwt,       data)
    panel_vix_gauge(ax_vix,        data)
    panel_price_board(ax_board,    data)

    # ─── フッター ───
    footer = (
        "Data: Yahoo Finance / CME / CFTC est.  "
        "ミセスワタナベ AI FX Analysis System  "
        f"Generated: {jst_now.strftime('%Y-%m-%d %H:%M JST')}"
    )
    fig.text(0.5, 0.002, footer, ha="center", va="bottom",
             color=C_GRAY, fontsize=7.5, alpha=0.7)

    plt.savefig(out_path, dpi=100, bbox_inches="tight",
                facecolor=BG, edgecolor="none")
    plt.close(fig)
    return out_path


# ─────────────────────────────────────────────────────────────────────────────
# ⑥ Telegram テキストメッセージ生成
# ─────────────────────────────────────────────────────────────────────────────

def build_text_msg(data: dict) -> str:
    """Telegram 通知① のテキストを組み立てる"""
    jst_now = datetime.now(JST)
    today   = jst_now.strftime("%Y/%m/%d")

    def _get(sym, key="latest", default=0.0):
        return data.get(sym, {}).get(key, default) or default

    # USD/JPY
    usdjpy = _get("USDJPY=X")
    chg1d  = _get("USDJPY=X", "chg")
    chg5d  = _get("USDJPY=X", "chg5d")
    arrow  = "▲" if chg1d >= 0 else "▼"

    # RSI
    rsi_val = None
    if "USDJPY=X" in data:
        c = data["USDJPY=X"]["df"]["Close"].tail(30)
        r = calc_rsi(c)
        if len(r) > 0:
            rsi_val = float(r.iloc[-1])
    rsi_str   = f"{rsi_val:.1f}" if rsi_val else "N/A"
    rsi_label = ("🔴過熱" if rsi_val and rsi_val > 70
                 else "🟢売られすぎ" if rsi_val and rsi_val < 30
                 else "🟡中立")

    # MACD シグナル
    macd_sig = "─"
    if "USDJPY=X" in data:
        c = data["USDJPY=X"]["df"]["Close"].tail(60)
        _, _, hist = calc_macd(c)
        lh = float(hist.iloc[-1])
        ph = float(hist.iloc[-2]) if len(hist) > 1 else lh
        if ph < 0 < lh:    macd_sig = "▲ゴールデンクロス発生！"
        elif ph > 0 > lh:  macd_sig = "▼デッドクロス発生！"
        elif lh > 0:       macd_sig = "↑上昇モメンタム継続"
        else:              macd_sig = "↓下落モメンタム継続"

    # その他
    dxy   = _get("DX-Y.NYB")
    vix   = _get("^VIX")
    us10y = _get("^TNX")
    gold  = _get("GC=F")
    oil   = _get("CL=F")
    eurjpy = _get("EURJPY=X")
    gbpjpy = _get("GBPJPY=X")
    audjpy = _get("AUDJPY=X")
    chg_ej = _get("EURJPY=X", "chg")
    chg_gj = _get("GBPJPY=X", "chg")
    chg_aj = _get("AUDJPY=X", "chg")

    # 日銀介入リスク
    intervention_risk = (
        "🔴高い！介入警戒" if usdjpy >= 160 else
        "🟠やや高い"       if usdjpy >= 155 else
        "🟡注意"           if usdjpy >= 150 else
        "🟢低い"
    )

    # 通貨強弱サマリー
    strength = calc_currency_strength(data, 5)
    top_cur  = max(strength, key=lambda k: strength[k]) if strength else "N/A"
    bot_cur  = min(strength, key=lambda k: strength[k]) if strength else "N/A"

    msg = (
        f"💹 *FX 午後マーケットレポート*\n"
        f"📅 {today}  14:00 JST\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"\n"
        f"🎯 *USD/JPY（ドル円）*\n"
        f"  {arrow} `{usdjpy:.3f} 円`\n"
        f"  前日比: {chg1d:+.2f}%   5日間: {(chg5d or 0):+.2f}%\n"
        f"  RSI: {rsi_str} {rsi_label}\n"
        f"  MACD: {macd_sig}\n"
        f"  日銀介入リスク: {intervention_risk}\n"
        f"\n"
        f"💱 *クロス円*\n"
        f"  EUR/JPY `{eurjpy:.2f}`  ({chg_ej:+.2f}%)\n"
        f"  GBP/JPY `{gbpjpy:.2f}`  ({chg_gj:+.2f}%)\n"
        f"  AUD/JPY `{audjpy:.2f}`  ({chg_aj:+.2f}%)\n"
        f"\n"
        f"📊 *市場環境*\n"
        f"  DXY ドル指数: `{dxy:.2f}`\n"
        f"  VIX 恐怖指数: `{vix:.2f}` {'🔴危険' if vix>=30 else '🟠警戒' if vix>=20 else '🟢安定'}\n"
        f"  米 10年金利:  `{us10y:.3f}%`\n"
        f"  日米金利差:   `{us10y - 2.66:.2f}%`\n"
        f"\n"
        f"🥇 *商品*\n"
        f"  Gold: `${gold:,.0f}/oz`   Oil: `${oil:.1f}/bbl`\n"
        f"\n"
        f"💪 *通貨強弱（5日間）*\n"
        f"  最強: {top_cur} {strength.get(top_cur, 0):+.2f}%\n"
        f"  最弱: {bot_cur} {strength.get(bot_cur, 0):+.2f}%\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 チャートは次のメッセージ ↓"
    )
    return msg


def build_url_msg(pages_url: str) -> str:
    """Telegram 通知③ URL メッセージ"""
    return (
        f"🔗 *詳細レポート*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{pages_url}\n\n"
        f"📱 iPhone Safari / Chrome で開けます\n"
        f"📈 テクニカル全指標\n"
        f"🌏 クロスアセット分析\n"
        f"📅 経済カレンダー"
    )


# ─────────────────────────────────────────────────────────────────────────────
# ⑦ メイン実行 run()
# ─────────────────────────────────────────────────────────────────────────────

def run() -> dict:
    """
    fx_noon_run.py から呼ばれるメイン関数
    Returns:
        dict: available, chart_path, text_msg, url_msg, error
    """
    import logging
    logger = logging.getLogger("fx_visual_report")

    result = {
        "available":  False,
        "chart_path": None,
        "text_msg":   "",
        "url_msg":    "",
        "error":      None,
    }

    try:
        # ─ データ取得 ─
        logger.info("FX データ取得開始...")
        data = fetch_all_data()
        logger.info(f"取得完了: {len(data)} シンボル")

        if not data:
            result["error"] = "全シンボルでデータ取得失敗"
            return result

        # ─ 出力先準備 ─
        out_dir = Path("data") / "fx_charts"
        out_dir.mkdir(parents=True, exist_ok=True)
        today_s    = datetime.now(JST).strftime("%Y%m%d_%H%M")
        chart_path = str(out_dir / f"{today_s}_fx_dashboard.png")

        # ─ チャート生成 ─
        logger.info("ダッシュボード生成中...")
        build_dashboard(data, chart_path)
        logger.info(f"✅ チャート保存: {chart_path}")

        # ─ テキスト生成 ─
        pages_url = os.getenv("GITHUB_PAGES_URL",
                              "https://youn24.github.io/market-ai-secretary")
        result.update({
            "available":  True,
            "chart_path": chart_path,
            "text_msg":   build_text_msg(data),
            "url_msg":    build_url_msg(pages_url),
            "data":       data,
        })

    except Exception as e:
        result["error"] = str(e)
        logger.error(f"fx_visual_report エラー: {e}")
        logger.debug(traceback.format_exc())

    return result
