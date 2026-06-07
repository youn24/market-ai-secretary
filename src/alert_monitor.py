"""
急変アラートモニター
15分ごとに市場を監視して急変時にTelegram通知
"""
import os
import json
import traceback
from pathlib import Path
from src.utils import setup_logger, get_jst_now, get_dirs

logger = setup_logger("alert_monitor")

# アラートの閾値
THRESHOLDS = {
    "^N225":    {"name": "日経平均",   "pct": 1.5},
    "^GSPC":    {"name": "S&P500",    "pct": 1.0},
    "^IXIC":    {"name": "NASDAQ",    "pct": 1.2},
    "^VIX":     {"name": "VIX恐怖指数","pct": 10.0},
    "USDJPY=X": {"name": "ドル円",    "pct": 0.8},
    "GC=F":     {"name": "金",        "pct": 1.5},
    "BTC-USD":  {"name": "Bitcoin",   "pct": 3.0},
    "^TNX":     {"name": "米10年金利", "pct": 2.0},
}


def check_alerts(prices: dict) -> list:
    """急変アラートをチェックして通知リストを返す"""
    alerts = []
    for sym, config in THRESHOLDS.items():
        p = prices.get(sym, {})
        chg = p.get("change_pct")
        val = p.get("latest")
        if chg is None or val is None:
            continue
        threshold = config["pct"]
        if abs(chg) >= threshold:
            direction = "急騰🔺" if chg > 0 else "急落🔻"
            alerts.append({
                "symbol": sym,
                "name": config["name"],
                "value": val,
                "change": chg,
                "direction": direction,
                "threshold": threshold,
            })
    return alerts


def build_alert_message(alerts: list, prices: dict, fear_greed: dict, risk: dict) -> str:
    """アラートメッセージを生成"""
    now = get_jst_now().strftime("%Y-%m-%d %H:%M JST")
    fg  = fear_greed.get("score")
    fg_r= fear_greed.get("rating_ja","---")

    lines = [
        f"🚨 *市場急変アラート* 🚨",
        f"⏰ {now}",
        f"━━━━━━━━━━━━━━━",
    ]

    for a in alerts:
        chg = a["change"]
        s   = "▲" if chg > 0 else "▼"
        lines.append(f"{a['direction']} *{a['name']}*: {a['value']:,.2f} ({s}{abs(chg):.2f}%)")

    lines += [
        f"━━━━━━━━━━━━━━━",
        f"🌡 地合い: {risk.get('sentiment','---')}",
        f"😱 Fear&Greed: {fg:.0f if fg else '---'} ({fg_r})",
        f"📱 市場AI秘書",
    ]
    return "\n".join(lines)


def run_alert_check(prices: dict, fear_greed: dict, risk: dict) -> bool:
    """アラートチェックを実行してTelegram通知"""
    try:
        alerts = check_alerts(prices)
        if not alerts:
            logger.info(f"アラートなし（{len(prices)}銘柄チェック済み）")
            return False

        logger.info(f"🚨 急変検知: {len(alerts)}件")
        msg = build_alert_message(alerts, prices, fear_greed, risk)

        from src.notify_telegram import send_message
        send_message(msg)

        # Gemini AIによる急変分析
        try:
            api_key = os.getenv("GEMINI_API_KEY","").strip()
            if api_key:
                import google.generativeai as genai
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel("gemini-1.5-flash")

                alert_text = "\n".join(
                    f"・{a['name']}: {a['direction']} {abs(a['change']):.2f}%"
                    for a in alerts
                )
                prompt = f"""市場で以下の急変が発生しました：
{alert_text}

投資家への簡潔なコメントを150文字以内で書いてください。
事実と推測を分け、断定表現は使わないでください。"""

                resp = model.generate_content(prompt)
                ai_comment = resp.text[:300]
                send_message(f"🤖 *Gemini AI緊急分析*\n\n{ai_comment}\n\n📱 市場AI秘書")
                logger.info("Gemini急変分析送信完了")
        except Exception as e:
            logger.error(f"Gemini急変分析エラー: {e}")

        return True

    except Exception as e:
        logger.error(f"アラートチェックエラー: {e}")
        logger.debug(traceback.format_exc())
        return False
