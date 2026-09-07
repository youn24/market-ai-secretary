"""
保有銘柄パーソナルアラート
data/portfolio.json を読み込み、各銘柄の現在価格・含み損益を取得し、
アラート条件に該当する銘柄を通知する。
"""

import json
import os
from pathlib import Path
from typing import Optional

try:
    import yfinance as yf
    YF_AVAILABLE = True
except ImportError:
    YF_AVAILABLE = False


# data/portfolio.json のデフォルトパス
_DEFAULT_PORTFOLIO_PATH = Path(__file__).parent.parent / "data" / "portfolio.json"


# アラートのしきい値。portfolio.json の "alerts" が無いときだけ使う。
_DEFAULT_ALERTS = {"loss_pct": -10.0, "gain_pct": 20.0, "move_pct": 3.0}


def _load_portfolio(portfolio_path: Optional[str] = None) -> list[dict]:
    """portfolio.json を読み込んで holdings リストを返す。"""
    return _load_all(portfolio_path)[0]


def _load_all(portfolio_path: Optional[str] = None) -> tuple[list[dict], dict]:
    """(holdings, alerts設定) を返す。

    ⚠️ 2026-09-06まで、しきい値は -10% / +20% / ±3% とコードに直書きで、
       portfolio.json の "alerts": {"loss_pct": -5, "gain_pct": 10} は
       **一度も読まれていなかった**。設定した本人は効いているつもりなのに
       効いていない、という一番たちの悪い形なので、設定を正とする。
    """
    path = Path(portfolio_path) if portfolio_path else _DEFAULT_PORTFOLIO_PATH
    if not path.exists():
        return [], dict(_DEFAULT_ALERTS)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return [], dict(_DEFAULT_ALERTS)
    cfg = dict(_DEFAULT_ALERTS)
    for k, v in (data.get("alerts") or {}).items():
        if k in cfg and isinstance(v, (int, float)):
            cfg[k] = float(v)
    # 損切り側は負の数で扱う。設定に 5 と書かれても -5% の意味に直す
    cfg["loss_pct"] = -abs(cfg["loss_pct"])
    cfg["gain_pct"] = abs(cfg["gain_pct"])
    cfg["move_pct"] = abs(cfg["move_pct"])
    return (data.get("holdings") or []), cfg


def _fetch_price(symbol: str) -> Optional[tuple[float, float]]:
    """
    yfinance で直近2日の終値を取得し (current_price, change_pct) を返す。
    取得できない場合は None を返す。
    """
    if not YF_AVAILABLE:
        return None
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="2d")
        if len(hist) >= 2:
            current = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[-2])
            change_pct = (current - prev) / prev * 100
            return current, change_pct
        elif len(hist) == 1:
            current = float(hist["Close"].iloc[-1])
            return current, 0.0
    except Exception:
        pass
    return None


def _build_html(
    holdings_summary: list[dict],
    alerts: list[dict],
    total_value: float,
    total_unrealized_pnl: float,
) -> str:
    """ダークテーマの保有銘柄カード HTML を生成する。"""
    alert_symbols = {a["symbol"] for a in alerts}

    cards_html = ""
    for h in holdings_summary:
        sym = h["symbol"]
        name = h["name"]
        price = h["current_price"]
        chg = h["change_pct"]
        pnl_pct = h["unrealized_pnl_pct"]

        pnl_color = "#4caf50" if pnl_pct >= 0 else "#f44336"
        chg_color = "#4caf50" if chg >= 0 else "#f44336"
        alert_border = "border: 2px solid #ff9800;" if sym in alert_symbols else ""
        alert_badge = (
            '<span style="background:#ff9800;color:#000;padding:2px 8px;'
            'border-radius:4px;font-size:11px;margin-left:8px;">⚠ アラート</span>'
            if sym in alert_symbols
            else ""
        )

        cards_html += f"""
        <div style="background:#1e1e2e;border-radius:10px;padding:16px 20px;
                    margin-bottom:12px;{alert_border}">
          <div style="display:flex;align-items:center;margin-bottom:8px;">
            <span style="font-size:16px;font-weight:bold;color:#e0e0e0;">{name}</span>
            <span style="color:#888;margin-left:8px;font-size:13px;">({sym})</span>
            {alert_badge}
          </div>
          <div style="display:flex;gap:24px;flex-wrap:wrap;">
            <div>
              <div style="color:#888;font-size:11px;">現在値</div>
              <div style="color:#e0e0e0;font-size:18px;font-weight:bold;">
                {price:,.1f}円
              </div>
            </div>
            <div>
              <div style="color:#888;font-size:11px;">前日比</div>
              <div style="color:{chg_color};font-size:16px;font-weight:bold;">
                {chg:+.2f}%
              </div>
            </div>
            <div>
              <div style="color:#888;font-size:11px;">含み損益</div>
              <div style="color:{pnl_color};font-size:16px;font-weight:bold;">
                {pnl_pct:+.1f}%
              </div>
            </div>
          </div>
        </div>
        """

    pnl_color_total = "#4caf50" if total_unrealized_pnl >= 0 else "#f44336"
    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <title>保有銘柄アラート</title>
  <style>
    body {{
      background: #121212;
      color: #e0e0e0;
      font-family: 'Helvetica Neue', Arial, sans-serif;
      margin: 0;
      padding: 20px;
    }}
    h2 {{ color: #ffffff; margin-bottom: 4px; }}
    .summary {{
      background: #1e1e2e;
      border-radius: 10px;
      padding: 16px 20px;
      margin-bottom: 20px;
    }}
    .summary-row {{
      display: flex;
      gap: 32px;
      flex-wrap: wrap;
    }}
    .label {{ color: #888; font-size: 12px; }}
    .value {{ color: #e0e0e0; font-size: 20px; font-weight: bold; }}
  </style>
</head>
<body>
  <h2>📊 保有銘柄パーソナルアラート</h2>
  <div class="summary">
    <div class="summary-row">
      <div>
        <div class="label">保有評価額合計</div>
        <div class="value">{total_value:,.0f}円</div>
      </div>
      <div>
        <div class="label">総含み損益</div>
        <div class="value" style="color:{pnl_color_total};">
          {total_unrealized_pnl:+,.0f}円
        </div>
      </div>
    </div>
  </div>
  <h3 style="color:#aaa;margin-bottom:12px;">保有銘柄</h3>
  {cards_html}
</body>
</html>"""
    return html


def check_portfolio_alerts(prices: dict = None) -> dict:
    """
    保有銘柄のアラートをチェックする。

    Parameters
    ----------
    prices : dict, optional
        外部から渡す価格データ（省略時は yfinance で取得）。
        {"symbol": {"latest": float, "change_pct": float}} の形式。

    Returns
    -------
    dict
        {
            "available": bool,
            "alerts": list[dict],
            "holdings_summary": list[dict],
            "total_value": float,
            "total_unrealized_pnl": float,
            "html": str,
            "has_urgent_alert": bool,
            "telegram_message": str,
        }
    """
    holdings, cfg = _load_all()

    if not holdings:
        return {
            "available": False,
            "alerts": [],
            "holdings_summary": [],
            "total_value": 0.0,
            "total_unrealized_pnl": 0.0,
            "html": "<p>ポートフォリオデータがありません。</p>",
            "has_urgent_alert": False,
            "telegram_message": "",
        }

    alerts: list[dict] = []
    holdings_summary: list[dict] = []
    total_value = 0.0
    total_unrealized_pnl = 0.0

    for holding in holdings:
        # ⚠️ holding["symbol"] と書くと、1銘柄でキーが欠けただけで KeyError になり
        #    **保有銘柄の欄が丸ごと消える**。欠けた行だけ飛ばす。
        if not isinstance(holding, dict):
            continue
        symbol = str(holding.get("symbol") or "").strip()
        if not symbol:
            continue
        name = str(holding.get("name") or symbol)
        try:
            shares = float(holding.get("shares") or 0)
            avg_cost = float(holding.get("avg_cost") or 0)
        except (TypeError, ValueError):
            continue
        if shares <= 0:
            continue

        # 価格取得
        current_price: Optional[float] = None
        change_pct: float = 0.0

        if prices and symbol in prices:
            current_price = prices[symbol].get("latest")
            change_pct = prices[symbol].get("change_pct", 0.0) or 0.0
        else:
            result = _fetch_price(symbol)
            if result is not None:
                current_price, change_pct = result

        if current_price is None:
            # 価格が取れなかった場合はスキップ
            continue

        # 含み損益の計算
        cost_basis = avg_cost * shares
        current_total = current_price * shares
        unrealized_pnl = current_total - cost_basis
        unrealized_pnl_pct = (unrealized_pnl / cost_basis * 100) if cost_basis > 0 else 0.0

        total_value += current_total
        total_unrealized_pnl += unrealized_pnl

        holdings_summary.append({
            "symbol": symbol,
            "name": name,
            "current_price": current_price,
            "change_pct": change_pct,
            "unrealized_pnl_pct": unrealized_pnl_pct,
        })

        # --- アラート条件チェック ---
        holding_alerts: list[dict] = []

        # 大きな変動アラート
        if abs(change_pct) >= cfg["move_pct"]:
            direction = "上昇" if change_pct > 0 else "下落"
            holding_alerts.append({
                "alert_type": "large_change",
                "message": f"前日比 {change_pct:+.1f}% の大きな{direction}です",
            })

        # 損切り検討アラート
        if unrealized_pnl_pct <= cfg["loss_pct"]:
            holding_alerts.append({
                "alert_type": "stop_loss",
                "message": f"⚠️ 損切り検討ライン（{cfg['loss_pct']:+.0f}%）に届きました",
            })

        # 利確検討アラート
        if unrealized_pnl_pct >= cfg["gain_pct"]:
            holding_alerts.append({
                "alert_type": "take_profit",
                "message": f"💰 利確検討ライン（{cfg['gain_pct']:+.0f}%）に届きました",
            })

        for a in holding_alerts:
            alerts.append({
                "symbol": symbol,
                "name": name,
                "change_pct": change_pct,
                "current_price": current_price,
                "unrealized_pnl": unrealized_pnl,
                "unrealized_pnl_pct": unrealized_pnl_pct,
                "alert_type": a["alert_type"],
                "message": a["message"],
            })

    has_urgent_alert = len(alerts) > 0

    # --- Telegram メッセージ生成 ---
    telegram_message = ""
    if alerts:
        lines = ["⚠️ 保有銘柄アラート\n"]
        seen = set()
        for a in alerts:
            sym = a["symbol"]
            if sym not in seen:
                seen.add(sym)
                icon = "📈" if a["change_pct"] >= 0 else "📉"
                lines.append(
                    f"{icon} {a['name']} ({sym}) {a['change_pct']:+.1f}%"
                )
                pnl_label = "含み益" if a["unrealized_pnl"] >= 0 else "含み損"
                lines.append(
                    f"   {pnl_label}: {a['unrealized_pnl']:+,.0f}円 ({a['unrealized_pnl_pct']:+.1f}%)"
                )
                lines.append(f"   {a['message']}")
                lines.append("")

        pnl_label_total = "含み益" if total_unrealized_pnl >= 0 else "含み損"
        total_pnl_pct = (
            total_unrealized_pnl
            / (total_value - total_unrealized_pnl)
            * 100
            if (total_value - total_unrealized_pnl) > 0
            else 0.0
        )
        lines.append(f"現在の保有評価額: {total_value:,.0f}円")
        lines.append(
            f"総{pnl_label_total}: {total_unrealized_pnl:+,.0f}円 ({total_pnl_pct:+.1f}%)"
        )
        telegram_message = "\n".join(lines)

    # HTML 生成
    html = _build_html(
        holdings_summary=holdings_summary,
        alerts=alerts,
        total_value=total_value,
        total_unrealized_pnl=total_unrealized_pnl,
    )

    return {
        "available": True,
        "alerts": alerts,
        "holdings_summary": holdings_summary,
        "total_value": total_value,
        "total_unrealized_pnl": total_unrealized_pnl,
        "html": html,
        "has_urgent_alert": has_urgent_alert,
        "telegram_message": telegram_message,
    }


def run(prices: dict = None) -> dict:
    """cloud_run から呼ぶ入口。他モジュールと同じ run() の形に揃えてある。"""
    return check_portfolio_alerts(prices)
