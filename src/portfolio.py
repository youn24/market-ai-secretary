"""
Level 3: ポートフォリオ管理
保有銘柄の登録・損益計算・アラート通知
data/portfolio.json に設定を保存する
"""
import os
import json
import traceback
from pathlib import Path
from src.utils import setup_logger, get_today_str, get_jst_now, get_dirs

logger = setup_logger("portfolio")

PORTFOLIO_FILE = Path("data/portfolio.json")

# ── デフォルトポートフォリオ（初回起動時に作成） ─────────────
DEFAULT_PORTFOLIO = {
    "holdings": [
        # 例: {"symbol":"7203.T","name":"トヨタ","qty":100,"buy_price":2500.0,"currency":"JPY"}
        # 初期は空（ユーザーが追加）
    ],
    "watchlist": [
        {"symbol": "^N225",   "name": "日経平均"},
        {"symbol": "^GSPC",   "name": "S&P500"},
        {"symbol": "USDJPY=X","name": "ドル円"},
        {"symbol": "BTC-USD", "name": "Bitcoin"},
    ],
    "alerts": {
        "loss_pct":  -5.0,   # 含み損が-5%を超えたらアラート
        "gain_pct":   10.0,  # 含み益が+10%を超えたらアラート
    },
    "history": []
}


def load_portfolio() -> dict:
    try:
        if PORTFOLIO_FILE.exists():
            with open(PORTFOLIO_FILE, encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"ポートフォリオ読込エラー: {e}")
    return DEFAULT_PORTFOLIO.copy()


def save_portfolio(pf: dict):
    try:
        PORTFOLIO_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
            json.dump(pf, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"ポートフォリオ保存エラー: {e}")


def add_holding(symbol: str, name: str, qty: float, buy_price: float,
                currency: str = "JPY"):
    """保有銘柄を追加"""
    pf = load_portfolio()
    # 既存なら更新
    for h in pf["holdings"]:
        if h["symbol"] == symbol:
            h.update({"name": name, "qty": qty, "buy_price": buy_price, "currency": currency})
            save_portfolio(pf)
            logger.info(f"ポートフォリオ更新: {name}({symbol})")
            return
    pf["holdings"].append({
        "symbol":    symbol,
        "name":      name,
        "qty":       qty,
        "buy_price": buy_price,
        "currency":  currency,
        "added_date": get_today_str()
    })
    save_portfolio(pf)
    logger.info(f"ポートフォリオ追加: {name}({symbol})")


def calc_pnl() -> dict:
    """保有銘柄の現在損益を計算"""
    pf = load_portfolio()
    holdings = pf.get("holdings", [])

    if not holdings:
        return {"available": False, "holdings": [], "total_pnl_pct": 0, "alerts": []}

    try:
        import yfinance as yf
        results  = []
        alerts   = []
        total_cost  = 0.0
        total_value = 0.0

        for h in holdings:
            sym       = h["symbol"]
            qty       = h.get("qty", 0)
            buy_price = h.get("buy_price", 0)
            name      = h.get("name", sym)

            try:
                ticker = yf.Ticker(sym)
                info   = ticker.fast_info
                cur    = float(info.last_price) if hasattr(info, "last_price") and info.last_price else None
                if cur is None:
                    hist = ticker.history(period="2d")
                    cur  = float(hist["Close"].iloc[-1]) if not hist.empty else None
            except Exception:
                cur = None

            if cur is None:
                results.append({
                    "symbol": sym, "name": name,
                    "qty": qty, "buy_price": buy_price,
                    "current": None, "pnl": None, "pnl_pct": None,
                    "status": "データ取得エラー"
                })
                continue

            pnl     = (cur - buy_price) * qty
            pnl_pct = (cur - buy_price) / buy_price * 100 if buy_price > 0 else 0
            cost    = buy_price * qty
            value   = cur * qty
            total_cost  += cost
            total_value += value

            arrow = "📈▲" if pnl_pct >= 0 else "📉▼"
            status = f"{arrow}{abs(pnl_pct):.2f}%  損益:{pnl:+,.0f}"

            # アラート判定
            alert_loss = pf["alerts"].get("loss_pct", -5.0)
            alert_gain = pf["alerts"].get("gain_pct", 10.0)
            if pnl_pct <= alert_loss:
                alerts.append({
                    "type":    "loss",
                    "symbol":  sym,
                    "name":    name,
                    "pnl_pct": pnl_pct,
                    "msg":     f"⚠️ {name} 含み損 {pnl_pct:.1f}% 警告ライン超過！"
                })
            elif pnl_pct >= alert_gain:
                alerts.append({
                    "type":    "gain",
                    "symbol":  sym,
                    "name":    name,
                    "pnl_pct": pnl_pct,
                    "msg":     f"🎉 {name} 含み益 +{pnl_pct:.1f}% 目標ライン到達！"
                })

            results.append({
                "symbol":  sym,
                "name":    name,
                "qty":     qty,
                "buy_price": buy_price,
                "current": cur,
                "pnl":     pnl,
                "pnl_pct": pnl_pct,
                "cost":    cost,
                "value":   value,
                "status":  status,
            })

        total_pnl     = total_value - total_cost
        total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0

        # 履歴に今日のスナップショットを保存
        _save_snapshot(pf, total_pnl_pct, results)

        return {
            "available":    True,
            "holdings":     results,
            "total_cost":   total_cost,
            "total_value":  total_value,
            "total_pnl":    total_pnl,
            "total_pnl_pct":total_pnl_pct,
            "alerts":       alerts,
        }

    except Exception as e:
        logger.error(f"損益計算エラー: {e}")
        logger.debug(traceback.format_exc())
        return {"available": False, "holdings": [], "total_pnl_pct": 0, "alerts": []}


def _save_snapshot(pf: dict, total_pnl_pct: float, results: list):
    """今日のスナップショットを履歴に追加"""
    today = get_today_str()
    snap  = {
        "date":     today,
        "pnl_pct":  round(total_pnl_pct, 2),
        "holdings": [
            {"symbol": r["symbol"], "pnl_pct": round(r.get("pnl_pct") or 0, 2)}
            for r in results if r.get("pnl_pct") is not None
        ]
    }
    # 重複防止
    pf["history"] = [h for h in pf.get("history",[]) if h.get("date") != today]
    pf["history"].append(snap)
    pf["history"] = sorted(pf["history"], key=lambda x: x.get("date",""))[-90:]
    save_portfolio(pf)


def generate_portfolio_chart(pnl_data: dict) -> str | None:
    """ポートフォリオの損益チャートを生成"""
    holdings = pnl_data.get("holdings", [])
    if not holdings:
        return None

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
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

        valid = [h for h in holdings if h.get("pnl_pct") is not None]
        if not valid:
            return None

        fig, axes = plt.subplots(1, 2, figsize=(12, 5), facecolor=BG)
        fig.patch.set_facecolor(BG)

        total_pnl_pct = pnl_data.get("total_pnl_pct", 0)
        total_pnl     = pnl_data.get("total_pnl", 0)
        total_c = UP if total_pnl_pct >= 0 else DOWN

        fig.suptitle(
            f"💼 ポートフォリオ損益  "
            f"{'▲' if total_pnl_pct>=0 else '▼'}{abs(total_pnl_pct):.2f}%  "
            f"（{total_pnl:+,.0f}円）",
            fontsize=14, fontweight="bold", color=total_c
        )

        # ── 左: 横棒グラフ（各銘柄の損益率） ──────────
        ax1 = axes[0]
        ax1.set_facecolor(CARD)
        for sp in ax1.spines.values(): sp.set_color(BORD)

        names  = [h.get("name", h["symbol"])[:8] for h in valid]
        pcts   = [h["pnl_pct"] for h in valid]
        colors = [UP if p >= 0 else DOWN for p in pcts]
        y_pos  = np.arange(len(names))

        bars = ax1.barh(y_pos, pcts, color=colors, alpha=0.85, height=0.6)
        ax1.axvline(0, color=BORD, linewidth=1.5)
        ax1.set_yticks(y_pos)
        ax1.set_yticklabels(names, color=TEXT, fontsize=10)
        ax1.tick_params(colors=TEXT2)
        ax1.set_xlabel("損益率 (%)", color=TEXT2, fontsize=9)
        ax1.set_title("銘柄別損益率", color=TEXT, fontsize=11, pad=6)
        ax1.grid(axis="x", color=BORD, linewidth=0.5)

        for bar, pct in zip(bars, pcts):
            x_pos = pct + (0.1 if pct >= 0 else -0.1)
            ax1.text(x_pos, bar.get_y() + bar.get_height()/2,
                     f"{pct:+.1f}%", va="center", fontsize=9,
                     color=UP if pct>=0 else DOWN, fontweight="bold")

        # ── 右: 時価構成ドーナツグラフ ──────────────
        ax2 = axes[1]
        ax2.set_facecolor(CARD)

        values = [h.get("value") or h.get("cost",0) for h in valid]
        names2 = [h.get("name", h["symbol"])[:8] for h in valid]
        palette = ["#58a6ff","#3fb950","#f0c060","#bc8cff",
                   "#ff7b72","#40c4ff","#ff9800","#ef5350"]
        pie_colors = palette[:len(values)]

        if sum(values) > 0:
            wedges, texts, autotexts = ax2.pie(
                values, labels=names2, autopct="%1.1f%%",
                colors=pie_colors, startangle=90,
                wedgeprops={"edgecolor": BG, "linewidth": 2},
                pctdistance=0.8
            )
            for t in texts:   t.set_color(TEXT); t.set_fontsize(9)
            for at in autotexts: at.set_color(BG); at.set_fontsize(8); at.set_fontweight("bold")
            ax2.set_title("時価構成比", color=TEXT, fontsize=11, pad=6)

        # 過去推移チャート（履歴があれば）
        pf = load_portfolio()
        history = pf.get("history", [])
        if len(history) >= 3:
            dates  = [h["date"][-5:] for h in history[-14:]]
            pnls   = [h["pnl_pct"] for h in history[-14:]]
            ax1.set_title("銘柄別損益率  (履歴あり)", color=TEXT, fontsize=11, pad=6)

        plt.tight_layout(rect=[0, 0, 1, 0.95])
        out = get_dirs()["charts"] / f"portfolio_{get_today_str()}.png"
        plt.savefig(str(out), dpi=130, bbox_inches="tight",
                    facecolor=BG, edgecolor="none")
        plt.close(fig)
        logger.info(f"✅ ポートフォリオチャート: {out}")
        return str(out)

    except Exception as e:
        logger.error(f"ポートフォリオチャートエラー: {e}")
        return None


def run() -> dict:
    """ポートフォリオ管理モジュール実行"""
    logger.info("=== ポートフォリオ管理開始 ===")

    # 初回起動時はデフォルトファイルを作成
    if not PORTFOLIO_FILE.exists():
        save_portfolio(DEFAULT_PORTFOLIO.copy())
        logger.info("ポートフォリオファイルを新規作成しました")
        return {"available": False, "reason": "保有銘柄未登録（data/portfolio.jsonに追加してください）"}

    pnl_data = calc_pnl()
    if not pnl_data.get("available"):
        return pnl_data

    chart_path = generate_portfolio_chart(pnl_data)
    pnl_data["chart_path"] = chart_path

    logger.info(f"✅ ポートフォリオ完了: {len(pnl_data.get('holdings',[]))}銘柄")
    return pnl_data
