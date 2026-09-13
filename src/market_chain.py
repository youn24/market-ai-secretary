"""
グローバル市場連鎖分析（L5h）
「日経が下がった→欧州は？→米国先物は？」という
時間軸をまたいだ市場間の連鎖反応パターンを2年分のデータから学習する。
今日の日経終値から翌日の米国市場方向性を予測する先行指標として活用。
"""
import ssl
import json
import logging
import urllib.request
from src.utils import get_jst_now

logger = logging.getLogger(__name__)

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE

# 分析対象市場（時系列順: 日本→欧州→米国）
MARKETS = {
    "^N225":  {"name": "日経225",     "region": "Asia",   "timezone": "JST"},
    "^GDAXI": {"name": "DAX（独）",   "region": "Europe", "timezone": "CET"},
    "^FTSE":  {"name": "FTSE100（英）","region": "Europe", "timezone": "GMT"},
    "^GSPC":  {"name": "S&P500",      "region": "US",     "timezone": "ET"},
    "^IXIC":  {"name": "NASDAQ",      "region": "US",     "timezone": "ET"},
}


def _fetch_returns(symbol: str, period: str = "2y") -> list:
    """Yahoo Finance から日次リターン系列を取得"""
    url = (
        f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?interval=1d&range={period}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        resp = urllib.request.urlopen(req, context=_ctx, timeout=20)
        data = json.loads(resp.read())
        result = data.get("chart", {}).get("result", [{}])[0]
        closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        timestamps = result.get("timestamps", [])
        if not closes or len(closes) < 10:
            return []
        # 日次リターン計算
        returns = []
        for i in range(1, len(closes)):
            c = closes[i]
            p = closes[i - 1]
            if c and p and p != 0:
                returns.append({
                    "timestamp": timestamps[i] if timestamps else 0,
                    "return_pct": round((c - p) / p * 100, 3),
                })
        return returns
    except Exception as e:
        logger.debug(f"  {symbol} 取得失敗: {e}")
        return []


def _calc_correlation(series_a: list, series_b: list, lag: int = 1) -> float | None:
    """2系列間のラグ相関を計算（series_a[t] vs series_b[t+lag]）"""
    if not series_a or not series_b:
        return None
    # 最短系列に合わせる（ラグ分ずらす）
    n = min(len(series_a) - lag, len(series_b) - lag)
    if n < 30:
        return None
    a_vals = [series_a[i]["return_pct"] for i in range(n)]
    b_vals = [series_b[i + lag]["return_pct"] for i in range(n)]

    mean_a = sum(a_vals) / n
    mean_b = sum(b_vals) / n
    cov = sum((a - mean_a) * (b - mean_b) for a, b in zip(a_vals, b_vals)) / n
    std_a = (sum((a - mean_a) ** 2 for a in a_vals) / n) ** 0.5
    std_b = (sum((b - mean_b) ** 2 for b in b_vals) / n) ** 0.5

    if std_a == 0 or std_b == 0:
        return None
    return round(cov / (std_a * std_b), 3)


def _predict_sp500(nikkei_ret: float, corr: float, avg_sp_ret: float) -> dict:
    """日経リターンからS&P500翌日リターンを線形予測"""
    if corr is None:
        return {"direction": "neutral", "predicted_ret": 0.0}
    predicted = corr * nikkei_ret + avg_sp_ret * (1 - abs(corr))
    direction = "bull" if predicted > 0.2 else "bear" if predicted < -0.2 else "neutral"
    return {
        "direction": direction,
        "predicted_ret": round(predicted, 2),
    }


def run(prices: dict = None) -> dict:
    """グローバル市場連鎖を分析"""
    logger.info("--- グローバル市場連鎖分析 ---")
    result = {"available": False}

    # 日次リターンを取得
    returns = {}
    for symbol in ["^N225", "^GDAXI", "^GSPC"]:
        r = _fetch_returns(symbol, period="2y")
        if r:
            returns[symbol] = r
            logger.info(f"  {symbol}: {len(r)}日分取得")

    if len(returns) < 2:
        logger.warning("  データ不足")
        return result

    # 日経 → S&P500（1日ラグ）相関
    corr_nk_sp = None
    if "^N225" in returns and "^GSPC" in returns:
        corr_nk_sp = _calc_correlation(returns["^N225"], returns["^GSPC"], lag=1)
        logger.info(f"  日経→S&P500 ラグ1相関: r={corr_nk_sp}")

    # 日経 → DAX（同日）相関
    corr_nk_dax = None
    if "^N225" in returns and "^GDAXI" in returns:
        corr_nk_dax = _calc_correlation(returns["^N225"], returns["^GDAXI"], lag=0)
        logger.info(f"  日経↔DAX 同日相関: r={corr_nk_dax}")

    # 今日の日経リターン
    today_nk_ret = 0.0
    if prices:
        today_nk_ret = prices.get("^N225", {}).get("change_pct", 0) or 0

    # S&P500の平均日次リターン（ベース）
    sp_avg = 0.0
    if "^GSPC" in returns and len(returns["^GSPC"]) > 0:
        sp_avg = sum(r["return_pct"] for r in returns["^GSPC"]) / len(returns["^GSPC"])

    # 翌日S&P500方向予測
    sp_prediction = _predict_sp500(today_nk_ret, corr_nk_sp, sp_avg)

    # 連鎖シナリオ作成
    chain_label = ""
    if today_nk_ret > 0.5:
        chain_label = f"日経が上昇({today_nk_ret:+.1f}%)→過去パターンでは欧州・米国も連動しやすい"
    elif today_nk_ret < -0.5:
        chain_label = f"日経が下落({today_nk_ret:+.1f}%)→過去パターンでは欧州・米国にも波及しやすい"
    else:
        chain_label = f"日経は小動き({today_nk_ret:+.1f}%)→単独要因に注目"

    result = {
        "available": True,
        "correlations": {
            "nikkei_sp500_lag1": corr_nk_sp,
            "nikkei_dax_same":   corr_nk_dax,
        },
        "today_nikkei_ret": today_nk_ret,
        "sp500_prediction": sp_prediction,
        "chain_label": chain_label,
        "data_period": "2年分",
        "data_points": {sym: len(ret) for sym, ret in returns.items()},
    }

    dir_ja = {"bull": "上昇方向", "bear": "下落方向", "neutral": "中立"}
    pred_dir = dir_ja.get(sp_prediction.get("direction", "neutral"), "")
    logger.info(f"✅ 連鎖分析: 日経{today_nk_ret:+.1f}% → S&P500翌日予測: {pred_dir}")
    return result


def format_telegram(data: dict) -> str:
    if not data.get("available"):
        return ""
    corrs = data.get("correlations", {})
    sp_pred = data.get("sp500_prediction", {})
    nk_ret = data.get("today_nikkei_ret", 0)

    dir_icons = {"bull": "📈 上昇方向", "bear": "📉 下落方向", "neutral": "➡️ 中立"}
    pred_icon = dir_icons.get(sp_pred.get("direction", "neutral"), "")

    lines = [
        "🌐 *グローバル市場連鎖分析*（2年データ）",
        "━━━━━━━━━━━━━━━",
    ]

    nk_sp = corrs.get("nikkei_sp500_lag1")
    nk_dax = corrs.get("nikkei_dax_same")

    if nk_sp is not None:
        strength = "強い" if abs(nk_sp) > 0.5 else "中程度" if abs(nk_sp) > 0.3 else "弱い"
        lines.append(f"日経→S&P500(翌日): r={nk_sp:.2f} ({strength}連動)")
    if nk_dax is not None:
        lines.append(f"日経↔DAX(同日): r={nk_dax:.2f}")

    lines += [
        "",
        f"📊 今日の日経: {nk_ret:+.1f}%",
        data.get("chain_label", ""),
        "",
        f"🔮 S&P500 翌日予測: {pred_icon}",
        f"  予測リターン: {sp_pred.get('predicted_ret', 0):+.2f}%",
        f"  ※過去の統計的パターンに基づく参考値",
    ]
    return "\n".join(lines)
