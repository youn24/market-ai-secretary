"""
スマート通知フィルター
市場データに基づいて通知の重要度をスコアリングし、
送信すべきレポートの種類を決定する。
"""

from typing import Optional


def score_notification_importance(
    prices: dict,
    risk: dict,
    fear_greed: dict,
    portfolio_changes: Optional[dict] = None,
) -> dict:
    """
    市場データを元に通知の重要度スコアを計算する。

    Parameters
    ----------
    prices : dict
        fetch_prices.py が返す価格データ。キーは symbol。
        各値は {"latest": float, "change_pct": float, ...} の形式。
    risk : dict
        analyze.py が返すリスク評価。{"score": float, ...} の形式。
    fear_greed : dict
        恐怖&貪欲指数。{"score": float, ...} の形式。
    portfolio_changes : dict, optional
        保有銘柄の変動率。{"symbol": change_pct, ...} の形式。

    Returns
    -------
    dict
        {
            "importance_score": float,
            "level": str,           # "LOW" / "MEDIUM" / "HIGH" / "CRITICAL"
            "reasons": list[str],
            "send_full_report": bool,
            "short_summary": str,
        }
    """
    score = 0
    reasons: list[str] = []

    # --- 各指標を取得 ---
    vix = prices.get("^VIX", {}).get("latest", 20) or 20
    sp_chg = abs(prices.get("^GSPC", {}).get("change_pct", 0) or 0)
    nk_chg = abs(prices.get("^N225", {}).get("change_pct", 0) or 0)
    usdjpy_chg = abs(prices.get("USDJPY=X", {}).get("change_pct", 0) or 0)
    rs = abs(risk.get("score", 0))
    fg = fear_greed.get("score", 50) or 50

    # --- VIX スコア ---
    if vix >= 35:
        score += 4
        reasons.append(f"VIX {vix:.1f}（極度の恐怖水準）")
    elif vix >= 30:
        score += 3
        reasons.append(f"VIX {vix:.1f}（高い恐怖水準）")
    elif vix >= 25:
        score += 2
        reasons.append(f"VIX {vix:.1f}（やや高い恐怖水準）")

    # --- S&P500 変動スコア ---
    if sp_chg >= 2:
        score += 3
        reasons.append(f"S&P500 変動率 {sp_chg:.1f}%（大幅変動）")
    elif sp_chg >= 1:
        score += 1
        reasons.append(f"S&P500 変動率 {sp_chg:.1f}%")

    # --- 日経225 変動スコア ---
    if nk_chg >= 2:
        score += 2
        reasons.append(f"日経225 変動率 {nk_chg:.1f}%（大幅変動）")
    elif nk_chg >= 1:
        score += 1
        reasons.append(f"日経225 変動率 {nk_chg:.1f}%")

    # --- ドル円 変動スコア ---
    if usdjpy_chg >= 1.5:
        score += 1
        reasons.append(f"ドル円 変動率 {usdjpy_chg:.1f}%")

    # --- リスクスコア ---
    if rs >= 2:
        score += 2
        reasons.append(f"リスクスコア {rs:.1f}（高リスク）")
    elif rs >= 1:
        score += 1
        reasons.append(f"リスクスコア {rs:.1f}（中程度リスク）")

    # --- 恐怖&貪欲 ---
    if fg <= 20 or fg >= 80:
        score += 2
        label = "極度の恐怖" if fg <= 20 else "極度の貪欲"
        reasons.append(f"恐怖&貪欲指数 {fg:.0f}（{label}）")

    # --- ポートフォリオ変動 ---
    if portfolio_changes:
        max_change = max(abs(c) for c in portfolio_changes.values())
        if max_change >= 3:
            score += 3
            top_symbol = max(portfolio_changes, key=lambda k: abs(portfolio_changes[k]))
            reasons.append(
                f"保有銘柄 {top_symbol} が {portfolio_changes[top_symbol]:+.1f}%（大幅変動）"
            )

    # --- レベル判定 ---
    if score >= 9:
        level = "CRITICAL"
        send_full_report = True
    elif score >= 6:
        level = "HIGH"
        send_full_report = True
    elif score >= 3:
        level = "MEDIUM"
        send_full_report = True
    else:
        level = "LOW"
        send_full_report = False

    # --- 表示用変動率（符号付き）---
    nk_raw = prices.get("^N225", {}).get("change_pct", 0) or 0
    sp_raw = prices.get("^GSPC", {}).get("change_pct", 0) or 0

    # --- 短縮サマリー（LOW 時に使用）---
    short_summary = (
        f"📊 市場は静かです（重要度: {score}/10）\n"
        f"日経 {nk_raw:+.2f}% / S&P {sp_raw:+.2f}% / VIX {vix:.0f}\n"
        f"今日の相場に大きな動きはありませんでした。"
    )

    return {
        "importance_score": float(score),
        "level": level,
        "reasons": reasons,
        "send_full_report": send_full_report,
        "short_summary": short_summary,
    }
