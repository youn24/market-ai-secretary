"""
急変アラートモニター
15分ごとに市場を監視して急変時にTelegram通知
"""
import os
import json
import traceback
from datetime import datetime
from pathlib import Path
from src.utils import setup_logger, get_jst_now, get_dirs, BASE_DIR

logger = setup_logger("alert_monitor")

# アラートの閾値（暴落級のみ通知）
# 細かい急変通知は廃止。本当に大きな暴落・恐怖急騰の時だけ安全網として通知する。
#   dir="down" … その%以上の「下落」で発火
#   dir="up"   … その%以上の「上昇」で発火（VIX＝恐怖の急騰用）
# 日経はほぼ24時間動くCME先物(NIY=F)を主監視 — 夜間の暴落も検知できる。
# 現物(^N225)は先物取得失敗時の安全網としてザラ場中のみ機能する。
THRESHOLDS = {
    "NIY=F": {"name": "日経先物(CME 24h)", "pct": 3.0,  "dir": "down"},
    "^N225": {"name": "日経平均(現物)",     "pct": 3.0,  "dir": "down"},
    "^GSPC": {"name": "S&P500",           "pct": 2.5,  "dir": "down"},
    "^IXIC": {"name": "NASDAQ",           "pct": 3.0,  "dir": "down"},
    "^VIX":  {"name": "VIX恐怖指数",       "pct": 25.0, "dir": "up"},
}

# クールダウン: 同一銘柄のアラートは4時間抑制（さらに1pt以上悪化したら再通知）
_STATE_FILE     = BASE_DIR / "data" / "alert_state.json"
_COOLDOWN_HOURS = 4
_ESCALATE_PT    = 1.0


def _apply_cooldown(alerts: list) -> list:
    """15分ごとの実行で同じ暴落を連発通知しないためのゲート。"""
    now = get_jst_now()
    try:
        st = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        st = {}
    kept = []
    for a in alerts:
        rec = st.get(a["symbol"])
        if rec:
            try:
                hours = (now - datetime.fromisoformat(rec["ts"])).total_seconds() / 3600
            except Exception:
                hours = 99
            if hours < _COOLDOWN_HOURS and abs(a["change"]) < abs(rec.get("chg", 0)) + _ESCALATE_PT:
                logger.info(f"クールダウン中のためスキップ: {a['name']} ({a['change']:+.2f}%)")
                continue
        kept.append(a)
    if kept:
        for a in kept:
            st[a["symbol"]] = {"ts": now.isoformat(), "chg": a["change"]}
        try:
            _STATE_FILE.parent.mkdir(exist_ok=True)
            _STATE_FILE.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
        except Exception:
            logger.debug(traceback.format_exc())
    return kept


def check_alerts(prices: dict) -> list:
    """暴落級アラートをチェックして通知リストを返す"""
    alerts = []
    for sym, config in THRESHOLDS.items():
        p = prices.get(sym, {})
        chg = p.get("change_pct")
        val = p.get("latest")
        if chg is None or val is None:
            continue
        threshold = config["pct"]
        direction = config.get("dir", "down")
        hit = (chg <= -threshold) if direction == "down" else (chg >= threshold)
        if hit:
            arrow = "急騰🔺" if chg > 0 else "急落🔻"
            alerts.append({
                "symbol": sym,
                "name": config["name"],
                "value": val,
                "change": chg,
                "direction": arrow,
                "threshold": threshold,
            })
    return alerts


def build_alert_message(alerts: list, prices: dict, fear_greed: dict, risk: dict) -> str:
    """アラートメッセージを生成"""
    now = get_jst_now().strftime("%Y-%m-%d %H:%M JST")
    fg  = fear_greed.get("score")
    fg_r= fear_greed.get("rating_ja","---")
    fg_disp = f"{fg:.0f}" if fg is not None else "---"

    lines = [
        f"🚨 *重大アラート：市場が大きく動いています* 🚨",
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
        f"😱 Fear&Greed: {fg_disp} ({fg_r})",
        f"📱 市場AI秘書",
    ]
    return "\n".join(lines)


# 米国時間外の個別株アラート閾値（決算級の大きな反応のみ・スパム防止）
AH_ALERT_PCT = 5.0


def run_afterhours_alert() -> bool:
    """
    米国主要株の時間外（アフターアワーズ/プレマーケット）±5%級の大変動を通知。
    決算発表への最初の反応など、翌朝の東京市場に波及しやすい動きを夜のうちに知らせる。
    クールダウン（4時間・1pt悪化で再通知）は指数アラートと同じゲートを共用。
    """
    try:
        from src.us_afterhours import run as run_us
        us = run_us()
        movers = [m for m in us.get("movers", [])
                  if abs(m.get("chg_pct") or 0) >= AH_ALERT_PCT]
        if not movers:
            logger.info(f"時間外±{AH_ALERT_PCT:.0f}%級の個別株変動なし")
            return False

        alerts = [{
            "symbol": f"AH:{m['symbol']}",
            "name":   f"{m['name']}({m['symbol']})",
            "value":  m.get("price"),
            "change": m["chg_pct"],
            "direction": "急騰🔺" if m["chg_pct"] > 0 else "急落🔻",
        } for m in movers]
        alerts = _apply_cooldown(alerts)
        if not alerts:
            return False

        session = movers[0].get("session", "post")
        s_label = "引け後の時間外" if session == "post" else "寄り付き前の時間外"
        now = get_jst_now().strftime("%m-%d %H:%M JST")
        lines = [
            "🇺🇸 *時間外で大きな動き* 🚨",
            f"⏰ {now}（{s_label}）",
            "━━━━━━━━━━━━━━━",
        ]
        for a in alerts[:5]:
            price_s = f"${a['value']:,.2f}" if a.get("value") else "—"
            s = "▲" if a["change"] > 0 else "▼"
            lines.append(f"{a['direction']} *{a['name']}*: {price_s} ({s}{abs(a['change']):.1f}%)")
        lines += [
            "━━━━━━━━━━━━━━━",
            "決算・材料への時間外反応。翌朝の東京市場の関連銘柄・セクターに波及しやすい動きです。",
            "📱 市場AI秘書",
        ]

        from src.notify_telegram import send_message
        send_message("\n".join(lines))
        logger.info(f"🚨 時間外ムーバーアラート送信: {len(alerts)}銘柄")
        return True
    except Exception:
        logger.error("時間外アラートエラー")
        logger.debug(traceback.format_exc())
        return False


def run_alert_check(prices: dict, fear_greed: dict, risk: dict) -> bool:
    """アラートチェックを実行してTelegram通知"""
    try:
        # 日経先物(CME・ほぼ24時間)を取得して監視対象へ注入 — 夜間の暴落も捕捉
        try:
            from src.cfd_sq import _fetch_one
            f = _fetch_one("NIY=F")
            if f and f.get("latest") and f.get("change_pct") is not None:
                prices = {**prices, "NIY=F": f}
                logger.info(f"日経先物: {f['latest']:,.0f} ({f['change_pct']:+.2f}%)")
        except Exception:
            logger.debug(traceback.format_exc())

        alerts = check_alerts(prices)
        # 先物と現物が同時ヒットした場合は先物のみ通知（重複排除）
        syms = {a["symbol"] for a in alerts}
        if "NIY=F" in syms and "^N225" in syms:
            alerts = [a for a in alerts if a["symbol"] != "^N225"]
        alerts = _apply_cooldown(alerts)
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
                model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))

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
