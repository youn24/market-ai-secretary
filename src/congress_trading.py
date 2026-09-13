"""
米議員株取引トラッカー
上院・下院議員の株式売買は法律で開示義務あり（STOCK Act）。
Senate Stock Watcher の公開S3データを使用（無料・APIキー不要）。

ペロシ元議長やバフィット上院議員など「賢い政治家」の取引は
市場より先に動くことが多い → 有力な先行指標。
"""
import ssl
import json
import urllib.request
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE

# Senate Stock Watcher / Capitol Trades の公開データ（複数フォールバック）
SENATE_URLS = [
    "https://senate-stock-watcher-data.s3-us-gov-west-1.amazonaws.com/aggregate/all_transactions.json",
    "https://raw.githubusercontent.com/elemental-machine/stock-watcher/main/data/all_transactions.json",
]
HOUSE_URLS = [
    "https://house-stock-watcher-data.s3-us-gov-west-1.amazonaws.com/data/all_transactions.json",
    "https://raw.githubusercontent.com/elemental-machine/house-stock-watcher/main/data/all_transactions.json",
]
# SEC EDGAR 全Form4ファイリングAPIでのフォールバック
SEC_EDGAR_URL = "https://efts.sec.gov/LATEST/search-index?q=%22section+16%22&forms=4&dateRange=custom&startdt={start}&enddt={end}"

# 注目すべき議員（影響力・精度の高い取引者）
NOTABLE_SENATORS = {
    "Thomas Tuberville", "Dan Sullivan", "Sheldon Whitehouse",
    "David Perdue", "Kelly Loeffler", "Richard Burr",
}

# 注目ティッカー（主要テクノロジー・金融）
NOTABLE_TICKERS = {
    "NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA",
    "JPM", "GS", "BAC", "XOM", "CVX", "AMD", "INTC",
}


def _get(url: str) -> bytes | None:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        resp = urllib.request.urlopen(req, context=_ctx, timeout=20)
        return resp.read()
    except Exception as e:
        logger.warning(f"取得失敗: {url[:60]}... → {e}")
        return None


def _parse_senate(raw: list, days: int = 30) -> list:
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    trades = []
    for item in raw:
        try:
            # Senate Stock Watcher の形式に対応
            transactions = item.get("transactions", [item]) if isinstance(item, dict) else []
            if isinstance(item, dict) and "transaction_date" in item:
                transactions = [item]
            for tx in transactions:
                date = tx.get("transaction_date", "")
                if date < cutoff:
                    continue
                ticker = tx.get("ticker", "").upper().strip()
                amount = tx.get("amount", "")
                tx_type = tx.get("type", "").lower()
                senator = tx.get("senator", item.get("senator", "不明"))
                if not ticker or ticker in ("--", "N/A"):
                    continue
                trades.append({
                    "chamber": "Senate",
                    "name": senator,
                    "ticker": ticker,
                    "date": date,
                    "type": "purchase" if "purchase" in tx_type or "buy" in tx_type else "sale",
                    "amount": amount,
                    "notable_person": senator in NOTABLE_SENATORS,
                    "notable_ticker": ticker in NOTABLE_TICKERS,
                })
        except Exception:
            continue
    return trades


def _parse_house(raw: list, days: int = 30) -> list:
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    trades = []
    for item in raw:
        try:
            date = item.get("transaction_date", "")
            if not date or date < cutoff:
                continue
            ticker = item.get("ticker", "").upper().strip()
            if not ticker or ticker in ("--", "N/A", ""):
                continue
            rep = item.get("representative", "不明")
            trades.append({
                "chamber": "House",
                "name": rep,
                "ticker": ticker,
                "date": date,
                "type": "purchase" if item.get("type", "").lower() in ("purchase", "buy") else "sale",
                "amount": item.get("amount", ""),
                "notable_person": False,
                "notable_ticker": ticker in NOTABLE_TICKERS,
            })
        except Exception:
            continue
    return trades


def run(days: int = 14) -> dict:
    """直近N日間の議員株取引を取得して分析"""
    logger.info("--- 米議員株取引トラッカー ---")
    result = {"available": False}

    all_trades = []

    # Senate（複数URLをフォールバック）
    senate_raw = None
    for url in SENATE_URLS:
        senate_raw = _get(url)
        if senate_raw:
            break
    if senate_raw:
        try:
            data = json.loads(senate_raw)
            trades = _parse_senate(data if isinstance(data, list) else data.get("transactions", []), days)
            all_trades.extend(trades)
            logger.info(f"  上院: {len(trades)}件（直近{days}日）")
        except Exception as e:
            logger.warning(f"上院データ解析エラー: {e}")
    else:
        logger.warning("  上院データ取得失敗（全URL試行済み）")

    # House（複数URLをフォールバック）
    house_raw = None
    for url in HOUSE_URLS:
        house_raw = _get(url)
        if house_raw:
            break
    if house_raw:
        try:
            data = json.loads(house_raw)
            trades = _parse_house(data if isinstance(data, list) else [], days)
            all_trades.extend(trades)
            logger.info(f"  下院: {len(trades)}件（直近{days}日）")
        except Exception as e:
            logger.warning(f"下院データ解析エラー: {e}")
    else:
        logger.warning("  下院データ取得失敗（全URL試行済み）")

    if not all_trades:
        logger.warning("議員取引データ取得失敗")
        return result

    # 集計
    # 注目銘柄ランキング（直近14日で最も多く買われた銘柄）
    from collections import Counter
    buys = [t["ticker"] for t in all_trades if t["type"] == "purchase"]
    sells = [t["ticker"] for t in all_trades if t["type"] == "sale"]
    buy_ranking = Counter(buys).most_common(5)
    sell_ranking = Counter(sells).most_common(5)

    # 注目取引（著名議員 or 注目ティッカー）
    notable = [
        t for t in all_trades
        if t.get("notable_person") or t.get("notable_ticker")
    ]
    notable.sort(key=lambda x: x["date"], reverse=True)

    result = {
        "available": True,
        "total_trades": len(all_trades),
        "buy_ranking": buy_ranking,
        "sell_ranking": sell_ranking,
        "notable_trades": notable[:10],
        "period_days": days,
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }

    logger.info(
        f"✅ 議員取引: 計{len(all_trades)}件 "
        f"買い上位={[t[0] for t in buy_ranking[:3]]}"
    )
    return result


def format_telegram(data: dict) -> str:
    """Telegram用フォーマット"""
    if not data.get("available"):
        return ""
    lines = [
        f"🏛️ *米議員 株取引 直近{data['period_days']}日*",
        "━━━━━━━━━━━━━━━",
        f"📊 総取引: {data['total_trades']}件",
        "",
        "🟢 最も買われた銘柄",
    ]
    for ticker, count in data["buy_ranking"][:5]:
        flag = "⭐" if ticker in NOTABLE_TICKERS else ""
        lines.append(f"  {flag} {ticker}: {count}件")
    lines += ["", "🔴 最も売られた銘柄"]
    for ticker, count in data["sell_ranking"][:3]:
        lines.append(f"  {ticker}: {count}件")

    notable = data.get("notable_trades", [])
    if notable:
        lines += ["", "⭐ 注目取引（直近）"]
        for t in notable[:3]:
            icon = "🟢" if t["type"] == "purchase" else "🔴"
            lines.append(
                f"  {icon} {t['name'][:15]} → {t['ticker']} "
                f"{'買い' if t['type']=='purchase' else '売り'} {t['date']}"
            )
    return "\n".join(lines)
