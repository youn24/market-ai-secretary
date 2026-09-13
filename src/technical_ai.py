"""
Level 3: テクニカル分析＋AI予測
RSI・MACD・ボリンジャーバンドを計算し、Geminiが解釈・予測する
"""
import os
import traceback
from src.utils import setup_logger, get_dirs, get_today_str

logger = setup_logger("technical_ai")

# 分析対象シンボル
TARGET_SYMBOLS = [
    ("^N225",   "日経平均",  "円"),
    ("^GSPC",   "S&P500",    ""),
    ("USDJPY=X","ドル円",    "円"),
    ("BTC-USD",  "Bitcoin",  "$"),
]


def calc_indicators(symbol: str) -> dict:
    """RSI・MACD・ボリンジャー・移動平均を計算"""
    try:
        import yfinance as yf
        import numpy as np

        ticker = yf.Ticker(symbol)
        hist   = ticker.history(period="90d")
        if hist.empty or len(hist) < 26:
            return {"symbol": symbol, "error": "データ不足"}

        close = hist["Close"].values
        high  = hist["High"].values
        low   = hist["Low"].values
        vol   = hist["Volume"].values if "Volume" in hist else None

        cur   = close[-1]
        prev  = close[-2] if len(close) >= 2 else cur

        # ── RSI (14) ──────────────────────────────
        delta = np.diff(close)
        gain  = np.where(delta > 0, delta, 0.0)
        loss  = np.where(delta < 0, -delta, 0.0)
        ag    = np.mean(gain[-14:])
        al    = np.mean(loss[-14:])
        rsi   = 100 - 100 / (1 + ag / al) if al > 0 else 100.0

        # ── EMA helper ────────────────────────────
        def ema(arr, p):
            k   = 2 / (p + 1)
            out = [arr[0]]
            for v in arr[1:]:
                out.append(v * k + out[-1] * (1 - k))
            return out

        # ── MACD (12, 26, 9) ──────────────────────
        e12       = ema(close, 12)
        e26       = ema(close, 26)
        macd_line = [a - b for a, b in zip(e12, e26)]
        signal    = ema(macd_line, 9)
        histogram = macd_line[-1] - signal[-1]
        macd_cross = "ゴールデンクロス📈" if macd_line[-1] > signal[-1] and macd_line[-2] <= signal[-2] else \
                     "デッドクロス📉"     if macd_line[-1] < signal[-1] and macd_line[-2] >= signal[-2] else \
                     "MACD>シグナル"      if macd_line[-1] > signal[-1] else "MACD<シグナル"

        # ── ボリンジャーバンド (20, ±2σ) ──────────
        ma20  = np.mean(close[-20:])
        std20 = np.std(close[-20:])
        bb_up = ma20 + 2 * std20
        bb_lo = ma20 - 2 * std20
        bb_pct = (cur - bb_lo) / (bb_up - bb_lo) * 100 if bb_up != bb_lo else 50

        # ── 移動平均 ───────────────────────────────
        ma5  = np.mean(close[-5:])
        ma25 = np.mean(close[-25:]) if len(close) >= 25 else None
        ma75 = np.mean(close[-75:]) if len(close) >= 75 else None

        # ── ATR (14) ──────────────────────────────
        tr_list = []
        for i in range(1, min(15, len(close))):
            tr = max(high[-i] - low[-i],
                     abs(high[-i] - close[-i-1]),
                     abs(low[-i]  - close[-i-1]))
            tr_list.append(tr)
        atr = float(np.mean(tr_list)) if tr_list else 0

        # ── 出来高トレンド ─────────────────────────
        vol_comment = ""
        if vol is not None and len(vol) >= 5:
            avg_vol = np.mean(vol[-20:]) if len(vol) >= 20 else np.mean(vol)
            cur_vol = vol[-1]
            if avg_vol > 0:
                vol_ratio = cur_vol / avg_vol
                vol_comment = f"平均比{vol_ratio:.1f}x {'📈急増' if vol_ratio>1.5 else '📉急減' if vol_ratio<0.5 else '普通'}"

        # ── シグナル判定 ───────────────────────────
        rsi_signal = "🔴過買い" if rsi > 70 else "🟢過売り（反発期待）" if rsi < 30 else "🟡中立"
        bb_signal  = "🔴上限突破(過熱)" if bb_pct > 95 else \
                     "🟢下限付近(反発期待)" if bb_pct < 5 else \
                     "上限圏" if bb_pct > 75 else "下限圏" if bb_pct < 25 else "中央圏"
        trend      = "📈上昇トレンド" if ma5 > (ma25 or ma5) else "📉下降トレンド" if ma5 < (ma25 or ma5) else "➡横ばい"

        return {
            "symbol":    symbol,
            "current":   float(cur),
            "prev":      float(prev),
            "rsi":       float(rsi),
            "rsi_signal":rsi_signal,
            "macd":      float(macd_line[-1]),
            "macd_sig":  float(signal[-1]),
            "macd_hist": float(histogram),
            "macd_cross":macd_cross,
            "bb_upper":  float(bb_up),
            "bb_lower":  float(bb_lo),
            "bb_ma20":   float(ma20),
            "bb_pct":    float(bb_pct),
            "bb_signal": bb_signal,
            "ma5":       float(ma5),
            "ma25":      float(ma25) if ma25 else None,
            "ma75":      float(ma75) if ma75 else None,
            "atr":       float(atr),
            "vol_comment":vol_comment,
            "trend":     trend,
        }

    except Exception as e:
        logger.error(f"テクニカル計算エラー {symbol}: {e}")
        return {"symbol": symbol, "error": str(e)}


def generate_chart(results: list) -> str | None:
    """テクニカル指標チャートを生成（4銘柄のダッシュボード）"""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.gridspec as gridspec
        import numpy as np
        try:
            import japanize_matplotlib  # noqa
        except Exception:
            pass

        BG    = "#0d1117"
        CARD  = "#161b22"
        BORD  = "#30363d"
        TEXT  = "#e6edf3"
        TEXT2 = "#8b949e"
        UP    = "#3fb950"
        DOWN  = "#f85149"
        BLUE  = "#58a6ff"
        GOLD  = "#f0c060"

        n = len(results)
        fig = plt.figure(figsize=(14, 5 * n), facecolor=BG)
        fig.patch.set_facecolor(BG)
        fig.suptitle("📐 テクニカル分析ダッシュボード",
                     fontsize=16, fontweight="bold", color=TEXT, y=0.99)

        for i, res in enumerate(results):
            if "error" in res:
                continue
            sym   = res["symbol"]
            label = next((lb for s, lb, _ in TARGET_SYMBOLS if s == sym), sym)

            gs_row = gridspec.GridSpec(1, 3, figure=fig,
                                       left=0.06, right=0.97,
                                       top=0.97 - i/n * 0.97,
                                       bottom=0.97 - (i+1)/n * 0.97 + 0.04,
                                       wspace=0.35)

            # ── RSIゲージ ──────────────────────────
            ax_rsi = fig.add_subplot(gs_row[0])
            ax_rsi.set_facecolor(CARD)
            for sp in ax_rsi.spines.values(): sp.set_color(BORD)
            rsi = res.get("rsi", 50)
            rsi_c = DOWN if rsi > 70 else UP if rsi < 30 else GOLD
            ax_rsi.barh(["RSI"], [rsi], color=rsi_c, alpha=0.8, height=0.4)
            ax_rsi.barh(["RSI"], [100], color=BORD, alpha=0.3, height=0.4)
            ax_rsi.axvline(70, color=DOWN, linewidth=1.5, linestyle="--", alpha=0.7)
            ax_rsi.axvline(30, color=UP,   linewidth=1.5, linestyle="--", alpha=0.7)
            ax_rsi.set_xlim(0, 100)
            ax_rsi.set_xticks([0, 30, 50, 70, 100])
            ax_rsi.tick_params(colors=TEXT2, labelsize=8)
            ax_rsi.set_title(f"{label}\nRSI: {rsi:.1f}  {res.get('rsi_signal','')}",
                             color=TEXT, fontsize=9, pad=4)
            ax_rsi.text(rsi + 1, 0, f"{rsi:.1f}", va="center", fontsize=10,
                        fontweight="bold", color=rsi_c)
            ax_rsi.text(72, -0.35, "過買い", fontsize=7, color=DOWN, va="center")
            ax_rsi.text(22, -0.35, "過売り", fontsize=7, color=UP,   va="center")

            # ── ボリンジャーバンド位置 ─────────────
            ax_bb = fig.add_subplot(gs_row[1])
            ax_bb.set_facecolor(CARD)
            for sp in ax_bb.spines.values(): sp.set_color(BORD)
            bb_pct = res.get("bb_pct", 50)
            bb_c   = DOWN if bb_pct > 80 else UP if bb_pct < 20 else GOLD
            ax_bb.barh(["BB"], [bb_pct], color=bb_c, alpha=0.8, height=0.4)
            ax_bb.barh(["BB"], [100], color=BORD, alpha=0.3, height=0.4)
            ax_bb.axvline(80, color=DOWN, linewidth=1.5, linestyle="--", alpha=0.7)
            ax_bb.axvline(20, color=UP,   linewidth=1.5, linestyle="--", alpha=0.7)
            ax_bb.set_xlim(0, 100)
            ax_bb.tick_params(colors=TEXT2, labelsize=8)
            ax_bb.set_title(f"ボリンジャーバンド位置\n{bb_pct:.0f}%  {res.get('bb_signal','')}",
                            color=TEXT, fontsize=9, pad=4)
            ax_bb.text(bb_pct + 1, 0, f"{bb_pct:.0f}%", va="center", fontsize=10,
                       fontweight="bold", color=bb_c)
            ax_bb.text(82,  -0.35, "上限", fontsize=7, color=DOWN, va="center")
            ax_bb.text(12,  -0.35, "下限", fontsize=7, color=UP,   va="center")

            # ── MACD ヒストグラム ─────────────────
            ax_macd = fig.add_subplot(gs_row[2])
            ax_macd.set_facecolor(CARD)
            for sp in ax_macd.spines.values(): sp.set_color(BORD)
            hist_val = res.get("macd_hist", 0)
            macd_c   = UP if hist_val >= 0 else DOWN
            ax_macd.bar([0], [hist_val], color=macd_c, alpha=0.85, width=0.5)
            ax_macd.axhline(0, color=BORD, linewidth=1.2)
            ax_macd.tick_params(colors=TEXT2, labelsize=8)
            ax_macd.set_xticks([])
            ax_macd.set_title(f"MACD ヒストグラム\n{hist_val:+.3f}  {res.get('macd_cross','')}",
                              color=TEXT, fontsize=9, pad=4)
            ax_macd.text(0, hist_val, f"{hist_val:+.3f}", ha="center",
                         va="bottom" if hist_val >= 0 else "top",
                         fontsize=9, fontweight="bold", color=macd_c)
            ax_macd.text(0, -abs(hist_val)*0.3,
                         f"トレンド: {res.get('trend','')}",
                         ha="center", va="top", fontsize=8, color=TEXT2)

        out = get_dirs()["charts"] / f"technical_{get_today_str()}.png"
        plt.savefig(str(out), dpi=130, bbox_inches="tight",
                    facecolor=BG, edgecolor="none")
        plt.close(fig)
        logger.info(f"✅ テクニカルチャート: {out}")
        return str(out)

    except Exception as e:
        logger.error(f"テクニカルチャート生成エラー: {e}")
        logger.debug(traceback.format_exc())
        return None


def analyze_with_gemini(results: list) -> str:
    """Geminiがテクニカル指標を解釈して予測を出す"""
    api_key = os.getenv("GEMINI_API_KEY","").strip()
    if not api_key or not results:
        return ""

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))

        lines = []
        for r in results:
            if "error" in r: continue
            sym   = r["symbol"]
            label = next((lb for s, lb, _ in TARGET_SYMBOLS if s == sym), sym)
            lines.append(
                f"{label}({sym}): RSI={r.get('rsi',0):.1f} {r.get('rsi_signal','')} / "
                f"BB位置={r.get('bb_pct',50):.0f}% {r.get('bb_signal','')} / "
                f"MACD={r.get('macd_hist',0):+.3f} {r.get('macd_cross','')} / "
                f"トレンド={r.get('trend','')}"
            )

        data_text = "\n".join(lines)

        prompt = f"""あなたはテクニカル分析の専門家です。
以下の指標データを見て、初心者でもわかるように解説してください。

【テクニカルデータ】
{data_text}

以下を各100文字以内で回答してください（断定表現禁止・推測として述べること）：

【📐 テクニカル総評】
全体的な市場のテクニカル状況を一言で。

【⚠️ 注意シグナル】
特に気をつけるべき指標や銘柄は何か。

【💡 チャンスシグナル】
割安・反発期待のシグナルはあるか。

【🔮 短期見通し】
テクニカル的に見た今後1〜2週間の方向性（推測として）。"""

        resp = model.generate_content(prompt)
        return resp.text

    except Exception as e:
        logger.error(f"Geminiテクニカル解釈エラー: {e}")
        return ""


def run() -> dict:
    """テクニカル分析モジュール実行"""
    logger.info("=== テクニカル分析開始 ===")
    results = []
    for sym, label, unit in TARGET_SYMBOLS:
        logger.info(f"  計算中: {label}({sym})")
        r = calc_indicators(sym)
        r["label"] = label
        r["unit"]  = unit
        results.append(r)

    chart_path = generate_chart(results)
    ai_comment = analyze_with_gemini(results)

    logger.info(f"✅ テクニカル分析完了: {len(results)}銘柄")
    return {
        "available":   True,
        "results":     results,
        "chart_path":  chart_path,
        "ai_comment":  ai_comment,
    }
