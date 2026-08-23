"""
決算前AI事前分析（L5g）
決算発表2〜3日前の企業について、過去の決算反応パターンと
現在のテクニカル状況からGeminiが「決算プレビュー」を生成する。
Yahoo Finance APIで決算カレンダーを取得（APIキー不要）。
"""
import ssl
import json
import logging
import os
import urllib.request
from datetime import datetime, timedelta
from src.utils import get_jst_now

logger = logging.getLogger(__name__)

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE

# 注目企業と基本情報（主要銘柄をカバー）
MAJOR_COMPANIES = {
    "AAPL": "Apple（iPhone・Mac）",
    "MSFT": "Microsoft（Azure・AI）",
    "GOOGL": "Alphabet（Google・広告）",
    "AMZN": "Amazon（EC・AWS）",
    "META": "Meta（Facebook・広告）",
    "NVDA": "NVIDIA（GPU・AI半導体）",
    "TSLA": "Tesla（EV・自動運転）",
    "JPM": "JPMorgan（銀行・金融）",
    "AMD": "AMD（CPU・GPU）",
    "INTC": "Intel（半導体）",
    "NFLX": "Netflix（動画配信）",
    "DIS": "Disney（エンタメ）",
    "BAC": "Bank of America（銀行）",
    "GS": "Goldman Sachs（投資銀行）",
}



def _prev_close_safe(result: dict, meta: dict) -> float:
    """前日終値。判定は src/quote_util.py に一本化してある。"""
    try:
        from src.quote_util import previous_close
        closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        ts = result.get("timestamp") or []
        return float(previous_close([(t, c) for t, c in zip(ts, closes) if c], meta) or 0)
    except Exception:
        return 0.0

def _get(url: str, timeout: int = 15) -> bytes | None:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    )
    try:
        resp = urllib.request.urlopen(req, context=_ctx, timeout=timeout)
        return resp.read()
    except Exception as e:
        logger.debug(f"  取得失敗: {url[:60]}... → {e}")
        return None


def _get_upcoming_earnings(days_ahead: int = 5) -> list:
    """直近N日以内に決算発表予定の企業を取得"""
    today = get_jst_now()
    upcoming = []

    for symbol, desc in MAJOR_COMPANIES.items():
        # Yahoo Finance 決算日チェック
        url = (
            f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{symbol}"
            f"?modules=calendarEvents"
        )
        raw = _get(url)
        if not raw:
            continue
        try:
            data = json.loads(raw)
            result = data.get("quoteSummary", {}).get("result", [])
            if not result:
                continue
            cal = result[0].get("calendarEvents", {})
            earnings = cal.get("earnings", {})
            dates = earnings.get("earningsDate", [])
            if not dates:
                continue
            for d in dates:
                # Unixタイムスタンプ or 日付文字列
                raw_date = d.get("raw")
                if raw_date:
                    try:
                        earnings_dt = datetime.fromtimestamp(raw_date)
                        delta = (earnings_dt - today).days
                        if 0 <= delta <= days_ahead:
                            upcoming.append({
                                "symbol": symbol,
                                "name": desc,
                                "earnings_date": earnings_dt.strftime("%Y-%m-%d"),
                                "days_until": delta,
                            })
                    except Exception:
                        pass
        except Exception:
            continue

    return upcoming


def _get_price_context(symbol: str) -> dict:
    """銘柄の直近価格・変化率を取得"""
    url = (
        f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?interval=1d&range=5d"
    )
    raw = _get(url)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        result = data.get("chart", {}).get("result", [{}])[0]
        meta = result.get("meta", {})
        return {
            "current_price": round(meta.get("regularMarketPrice", 0), 2),
            # meta の previousClose はチャートAPIでは基本 None。
            # quote_util 経由で当日より前の終値を求める
            "prev_close": round(_prev_close_safe(result, meta), 2),
            "52w_high": round(meta.get("fiftyTwoWeekHigh", 0), 2),
            "52w_low": round(meta.get("fiftyTwoWeekLow", 0), 2),
        }
    except Exception:
        return {}


def _generate_preview(upcoming: list, model) -> list:
    """Geminiで各銘柄の決算プレビューを生成"""
    previews = []
    for item in upcoming[:3]:  # 上位3銘柄のみ（API呼び出し節約）
        symbol = item["symbol"]
        name = item["name"]
        price_ctx = _get_price_context(symbol)

        prompt = f"""投資家向けに決算前の簡潔な分析をしてください。

銘柄: {name} ({symbol})
決算日: {item['earnings_date']}（{item['days_until']}日後）
現在株価: {price_ctx.get('current_price','不明')}ドル
52週高値: {price_ctx.get('52w_high','不明')} / 安値: {price_ctx.get('52w_low','不明')}

以下を各1行（30字以内）で回答してください（日本語）：
注目ポイント: （今決算で最も注目される点）
過去の傾向: （一般的なこの企業の決算後の反応）
リスク要因: （最大のダウンサイドリスク）
ポジション: （買い/様子見/売り場探し）"""

        try:
            resp = model.generate_content(prompt)
            text = resp.text.strip()
            item["preview"] = text
        except Exception as e:
            item["preview"] = f"AI分析エラー: {e}"
        item["price"] = price_ctx
        previews.append(item)

    return previews


def run() -> dict:
    """決算前AI事前分析を実行"""
    logger.info("--- 決算前AI事前分析 ---")
    result = {"available": False}

    api_key = os.getenv("GEMINI_API_KEY", "").strip()

    logger.info("  直近5日内の決算を検索中...")
    upcoming = _get_upcoming_earnings(days_ahead=5)
    logger.info(f"  発見: {len(upcoming)}件")

    if not upcoming:
        # 決算がない場合でも「今週は主要決算なし」として返す
        result = {
            "available": True,
            "upcoming": [],
            "previews": [],
            "no_earnings_week": True,
            "message": "今週は主要銘柄の決算発表はありません",
        }
        logger.info("✅ 今週の主要決算なし")
        return result

    # Geminiでプレビュー生成
    previews = []
    if api_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
            previews = _generate_preview(upcoming, model)
            logger.info(f"  プレビュー生成: {len(previews)}件")
        except Exception as e:
            logger.warning(f"  Gemini呼び出し失敗: {e}")
            previews = upcoming  # AIなしで日程のみ返す

    result = {
        "available": True,
        "upcoming": upcoming,
        "previews": previews,
        "no_earnings_week": False,
        "count": len(upcoming),
    }

    logger.info(f"✅ 決算前分析: {len(upcoming)}件発見")
    return result


def format_telegram(data: dict) -> str:
    if not data.get("available"):
        return ""
    if data.get("no_earnings_week") or not data.get("upcoming"):
        return "📅 *決算前AI分析*\n今週は主要銘柄の決算発表はありません"

    lines = [
        "📅 *決算前AI分析 — 直近の注目決算*",
        "━━━━━━━━━━━━━━━",
    ]
    for item in data.get("previews", data.get("upcoming", []))[:3]:
        symbol = item.get("symbol", "")
        name = item.get("name", "")
        date = item.get("earnings_date", "")
        days = item.get("days_until", "?")
        price = item.get("price", {})
        preview = item.get("preview", "")

        lines += [
            "",
            f"⚡ *{symbol}*（{name}）",
            f"  決算日: {date}（{days}日後）",
        ]
        if price.get("current_price"):
            lines.append(f"  現在: ${price['current_price']} (52w: ${price.get('52w_low','?')}〜${price.get('52w_high','?')})")
        if preview:
            for line in preview.split("\n")[:3]:
                lines.append(f"  {line}")

    return "\n".join(lines)
