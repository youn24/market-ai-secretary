"""
L4b: 長期歴史データ分析モジュール
Yahoo Finance APIから何十年分ものデータを取得し、
現在の市場環境を歴史的文脈で分析する
"""
import ssl
import json
import urllib.request
import pandas as pd
import numpy as np
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE

SYMBOLS = {
    "sp500":  {"sym": "^GSPC", "name": "S&P500",  "unit": "pt"},
    "nikkei": {"sym": "^N225", "name": "日経225",  "unit": "円"},
    "vix":    {"sym": "^VIX",  "name": "VIX恐怖指数", "unit": ""},
    "usdjpy": {"sym": "JPY=X", "name": "ドル円",   "unit": "円"},
    "gold":   {"sym": "GC=F",  "name": "金(Gold)", "unit": "$/oz"},
}


def _fetch(symbol: str, period: str = "20y") -> pd.DataFrame:
    """Yahoo Finance APIから日次データを取得"""
    url = (
        f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?interval=1d&range={period}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        resp = urllib.request.urlopen(req, context=_ctx, timeout=15)
        data = json.loads(resp.read())
        result = data["chart"]["result"][0]
        timestamps = result["timestamp"]
        quotes = result["indicators"]["quote"][0]
        closes = quotes.get("close", [])
        dates = [datetime.fromtimestamp(t).strftime("%Y-%m-%d") for t in timestamps]
        df = pd.DataFrame({"Date": dates, "Close": closes}).dropna()
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date").sort_index()
        return df
    except Exception as e:
        logger.warning(f"fetch失敗 {symbol}: {e}")
        return pd.DataFrame()


def _calc_stats(df: pd.DataFrame, current_val: float) -> dict:
    """現在値の歴史的統計を計算"""
    if df.empty or len(df) < 30:
        return {}
    closes = df["Close"].dropna()
    pct_rank = float((closes < current_val).sum() / len(closes) * 100)
    mean = float(closes.mean())
    std = float(closes.std())
    z_score = float((current_val - mean) / std) if std > 0 else 0
    max_val = float(closes.max())
    min_val = float(closes.min())
    from_ath = float((current_val - max_val) / max_val * 100)
    from_atl = float((current_val - min_val) / min_val * 100)
    return {
        "percentile": round(pct_rank, 1),
        "z_score": round(z_score, 2),
        "mean": round(mean, 2),
        "max": round(max_val, 2),
        "min": round(min_val, 2),
        "from_ath_pct": round(from_ath, 1),
        "from_atl_pct": round(from_atl, 1),
        "years": round(len(df) / 252, 1),
        "data_points": len(df),
    }


def _detect_regime(sp500_df: pd.DataFrame, vix_df: pd.DataFrame) -> dict:
    """
    現在の市場レジームを歴史的パターンから判定
    レジーム: Bull/Bear/Correction/Recovery
    """
    if sp500_df.empty or len(sp500_df) < 252:
        return {"regime": "不明", "description": "データ不足"}

    sp = sp500_df["Close"].dropna()
    current = float(sp.iloc[-1])
    peak_1y = float(sp.tail(252).max())
    ma200 = float(sp.tail(200).mean())

    drawdown = (current - peak_1y) / peak_1y * 100

    vix_current = 0
    if not vix_df.empty:
        vix_current = float(vix_df["Close"].dropna().iloc[-1])

    if drawdown > -5 and current > ma200:
        regime = "強気相場"
        emoji = "🚀"
        description = "高値圏で推移。上昇トレンド継続中"
    elif drawdown <= -20:
        regime = "弱気相場"
        emoji = "🐻"
        description = f"高値から{abs(drawdown):.0f}%下落。ベア市場入り"
    elif drawdown <= -10:
        regime = "調整局面"
        emoji = "⚠️"
        description = f"高値から{abs(drawdown):.0f}%下落。調整圏"
    elif current < ma200:
        regime = "回復途上"
        emoji = "🔄"
        description = "200日移動平均線を下回り、回復を試みる段階"
    else:
        regime = "中立"
        emoji = "➡️"
        description = "方向感に乏しいレンジ相場"

    vix_note = ""
    if vix_current >= 30:
        vix_note = "（VIX30超：パニック水準）"
    elif vix_current >= 20:
        vix_note = "（VIX20超：警戒水準）"
    elif vix_current < 15:
        vix_note = "（VIX低水準：楽観的）"

    return {
        "regime": regime,
        "emoji": emoji,
        "description": description + vix_note,
        "drawdown_from_peak": round(drawdown, 1),
        "vs_ma200": round((current - ma200) / ma200 * 100, 1),
        "vix": round(vix_current, 1),
    }


def _find_similar_periods(sp500_df: pd.DataFrame, vix_df: pd.DataFrame) -> list:
    """
    現在の市場環境に似た過去の時期を探す
    VIXと株価の下落率を組み合わせて類似度判定
    """
    if sp500_df.empty or vix_df.empty:
        return []

    sp = sp500_df["Close"].dropna()
    vix = vix_df["Close"].dropna()

    current_sp = float(sp.iloc[-1])
    current_vix = float(vix.iloc[-1])
    current_sp_peak = float(sp.tail(252).max())
    current_drawdown = (current_sp - current_sp_peak) / current_sp_peak * 100

    similar = []
    # 過去のデータを1年単位でスキャン（毎年1回ずつサンプル）
    common_dates = sp.index.intersection(vix.index)
    # 年ごとに代表日を選んで比較
    years = sorted(set(d.year for d in common_dates))
    for year in years[:-2]:  # 直近2年は除く
        year_dates = [d for d in common_dates if d.year == year]
        if not year_dates:
            continue
        mid_date = year_dates[len(year_dates) // 2]
        hist_sp = float(sp.get(mid_date, sp.asof(mid_date)))
        hist_vix = float(vix.get(mid_date, vix.asof(mid_date)))
        # 1年前ピーク
        prev_dates = [d for d in sp.index if d.year == year - 1]
        if not prev_dates:
            continue
        prev_peak = float(sp[prev_dates].max())
        hist_drawdown = (hist_sp - prev_peak) / prev_peak * 100 if prev_peak > 0 else 0
        vix_diff = abs(hist_vix - current_vix)
        draw_diff = abs(hist_drawdown - current_drawdown)
        score = vix_diff * 0.6 + draw_diff * 0.4
        similar.append({
            "year": year,
            "date": mid_date.strftime("%Y-%m"),
            "vix": round(hist_vix, 1),
            "drawdown": round(hist_drawdown, 1),
            "score": round(score, 1),
        })

    similar.sort(key=lambda x: x["score"])
    return similar[:3]


def run(current_prices: dict = None) -> dict:
    """
    長期歴史分析を実行
    current_prices: {"sp500": 5000, "nikkei": 35000, "vix": 18.5, ...}
    """
    logger.info("--- Step L4b: 長期歴史データ分析 ---")
    result = {"available": False}

    try:
        datasets = {}
        for key, info in SYMBOLS.items():
            logger.info(f"  {info['name']} を取得中...")
            df = _fetch(info["sym"], "20y")
            if not df.empty:
                datasets[key] = df
                logger.info(f"  ✅ {info['name']}: {len(df)}件 ({df.index[0].strftime('%Y')}〜)")
            else:
                logger.warning(f"  ⚠️ {info['name']}: 取得失敗")

        if "sp500" not in datasets:
            logger.error("S&P500データ取得失敗 → 歴史分析スキップ")
            return result

        # 現在値の統計
        stats = {}
        for key, df in datasets.items():
            if df.empty:
                continue
            current_val = float(df["Close"].iloc[-1])
            if current_prices and key in current_prices:
                current_val = current_prices[key]
            stats[key] = {
                "name": SYMBOLS[key]["name"],
                "current": current_val,
                **_calc_stats(df, current_val),
            }

        # 市場レジーム判定
        vix_df = datasets.get("vix", pd.DataFrame())
        regime = _detect_regime(datasets["sp500"], vix_df)

        # 類似過去期間
        similar = _find_similar_periods(datasets["sp500"], vix_df)

        result = {
            "available": True,
            "stats": stats,
            "regime": regime,
            "similar_periods": similar,
            "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        logger.info(f"✅ 歴史分析完了: レジーム={regime['regime']}")

    except Exception as e:
        logger.error(f"歴史分析エラー: {e}")
        import traceback
        logger.debug(traceback.format_exc())

    return result


def format_summary(hist: dict) -> str:
    """Telegram用の短いサマリー文字列を生成（最大150文字）"""
    if not hist.get("available"):
        return ""

    regime = hist.get("regime", {})
    stats = hist.get("stats", {})

    parts = []
    r = regime.get("regime", "")
    emoji = regime.get("emoji", "")
    if r:
        parts.append(f"{emoji}{r}")

    sp_stat = stats.get("sp500", {})
    if sp_stat:
        pct = sp_stat.get("percentile", 0)
        parts.append(f"S&P歴史的水準:{pct:.0f}%ile")

    vix_stat = stats.get("vix", {})
    if vix_stat:
        pct = vix_stat.get("percentile", 0)
        parts.append(f"VIX:{pct:.0f}%ile")

    similar = hist.get("similar_periods", [])
    if similar:
        top = similar[0]
        parts.append(f"類似期間:{top['year']}年頃")

    return " / ".join(parts)[:150]
