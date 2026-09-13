"""
ファンダメンタル分析・市場統計モジュール
PER/PBR・レーティング・先物・オプション・市場統計を取得
"""
import json
import time
from urllib.parse import quote
from datetime import datetime, timedelta, timezone

import feedparser
import pandas as pd
import requests
import yfinance as yf

from src.utils import setup_logger, get_jst_now, get_today_str, get_dirs, BASE_DIR

logger = setup_logger("fundamental")
JST = timezone(timedelta(hours=9))

# ─── ファンダメンタル指標 ──────────────────────────────────
FUNDAMENTAL_SYMBOLS = {
    # 米国
    "NVDA":  "NVIDIA",
    "AAPL":  "Apple",
    "TSLA":  "Tesla",
    "MSFT":  "Microsoft",
    "AMZN":  "Amazon",
    "META":  "Meta",
    # 日本
    "7203.T": "トヨタ",
    "9984.T": "SBG",
    "6758.T": "ソニーG",
    "8306.T": "三菱UFJ",
    "6857.T": "アドバンテスト",
}

RATING_JA = {
    "strong_buy":  "強気買い ⭐⭐⭐",
    "buy":         "買い ⭐⭐",
    "hold":        "中立 ➡️",
    "underperform":"弱含み ⬇️",
    "sell":        "売り ⛔",
}


def fetch_fundamentals() -> dict:
    results = {}
    for sym, name in FUNDAMENTAL_SYMBOLS.items():
        try:
            info = yf.Ticker(sym).info
            per  = info.get("trailingPE")
            pbr  = info.get("priceToBook")
            fwd_per = info.get("forwardPE")
            mkt_cap = info.get("marketCap")
            div_yield = info.get("dividendYield")
            rec = info.get("recommendationKey","")
            target_price = info.get("targetMeanPrice")
            curr_price   = info.get("currentPrice") or info.get("regularMarketPrice")

            upside = None
            if target_price and curr_price:
                upside = round((target_price - curr_price) / curr_price * 100, 1)

            results[sym] = {
                "name":          name,
                "per":           round(float(per), 1)        if per       else None,
                "forward_per":   round(float(fwd_per), 1)    if fwd_per   else None,
                "pbr":           round(float(pbr), 2)        if pbr       else None,
                "market_cap":    mkt_cap,
                "div_yield":     round(float(div_yield)*100, 2) if div_yield else None,
                "rating":        rec,
                "rating_ja":     RATING_JA.get(rec, rec),
                "target_price":  round(float(target_price),2) if target_price else None,
                "current_price": round(float(curr_price),2)   if curr_price   else None,
                "upside_pct":    upside,
                "fetch_time":    get_jst_now().isoformat(),
            }
            logger.info(f"[OK] ファンダ {name}: PER={per} レーティング={rec}")
        except Exception as e:
            logger.error(f"[FAIL] ファンダ {name}: {e}")
            results[sym] = {"name": name, "error": str(e)}
        time.sleep(0.5)
    return results


# ─── 先物データ ────────────────────────────────────────────
FUTURES_SYMBOLS = {
    "ES=F":  "S&P500先物",
    "NQ=F":  "NASDAQ先物",
    "YM=F":  "ダウ先物",
    "GC=F":  "金先物",
    "CL=F":  "原油先物",
    "ZN=F":  "米10年債先物",
}


def fetch_futures() -> dict:
    results = {}
    for sym, name in FUTURES_SYMBOLS.items():
        try:
            tk   = yf.Ticker(sym)
            hist = tk.history(period="3d")
            if hist.empty:
                results[sym] = {"name": name, "error": "データなし"}
                continue
            latest = float(hist["Close"].iloc[-1])
            prev   = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else None
            chg    = round((latest - prev) / abs(prev) * 100, 2) if prev else None
            results[sym] = {
                "name":       name,
                "latest":     round(latest, 2),
                "prev_close": round(prev, 2) if prev else None,
                "change_pct": chg,
            }
            logger.info(f"[OK] 先物 {name}: {latest}")
        except Exception as e:
            logger.error(f"[FAIL] 先物 {name}: {e}")
            results[sym] = {"name": name, "error": str(e)}
        time.sleep(0.4)
    return results


# ─── オプション（VIX） ─────────────────────────────────────
def fetch_options_summary() -> dict:
    """VIXオプションのPut/Call比率を取得"""
    try:
        tk   = yf.Ticker("^VIX")
        exps = tk.options
        if not exps:
            return {"error": "オプションデータなし"}

        chain = tk.option_chain(exps[0])
        calls = chain.calls
        puts  = chain.puts

        call_vol = float(calls["volume"].sum()) if "volume" in calls else 0
        put_vol  = float(puts["volume"].sum())  if "volume" in puts  else 0
        pcr      = round(put_vol / call_vol, 2) if call_vol > 0 else None

        signal = "強い弱気(リスクオフ警戒)" if pcr and pcr > 1.5 else \
                 "弱気寄り"                  if pcr and pcr > 1.0 else \
                 "中立"                      if pcr and pcr > 0.7 else \
                 "強気寄り"

        logger.info(f"[OK] VIXオプション PCR={pcr}")
        return {
            "expiry":     exps[0],
            "call_vol":   int(call_vol),
            "put_vol":    int(put_vol),
            "put_call_ratio": pcr,
            "signal":     signal,
            "fetch_time": get_jst_now().isoformat(),
        }
    except Exception as e:
        logger.error(f"[FAIL] オプション: {e}")
        return {"error": str(e)}


# ─── NT倍率 ────────────────────────────────────────────────
def calc_nt_ratio(prices: dict) -> dict:
    """NT倍率 = 日経平均 / TOPIX（TOPIXが取れない場合は概算）"""
    n225  = prices.get("^N225",  {}).get("latest")
    topix = prices.get("^TOPX",  {}).get("latest")
    if n225 and topix:
        nt = round(n225 / topix, 2)
        signal = "日経優位(グロース選好)" if nt > 15 else \
                 "TOPIX優位(バリュー選好)" if nt < 13 else "中立"
        return {"nt_ratio": nt, "n225": n225, "topix": topix,
                "signal": signal, "method": "実測値"}
    elif n225:
        # TOPIXなし→概算（過去平均14.0付近）
        return {"nt_ratio": None, "n225": n225, "topix": None,
                "signal": "TOPIX取得失敗のため計算不可", "method": "取得失敗"}
    return {"nt_ratio": None, "signal": "データなし"}


# ─── 騰落レシオ（計算） ────────────────────────────────────
def calc_torakuhi(period: int = 25) -> dict:
    """
    騰落レシオ = 25日間の値上がり銘柄数 / 値下がり銘柄数 × 100
    個別銘柄データから簡易計算（東証全銘柄は取れないため主要銘柄で近似）
    """
    proxy_symbols = [
        "7203.T","9984.T","6758.T","8306.T","6857.T","4063.T",
        "^N225","^GSPC","^IXIC","USDJPY=X","GC=F","CL=F",
        "NVDA","AAPL","TSLA","MSFT",
    ]
    up_days = 0
    down_days = 0
    try:
        for sym in proxy_symbols[:8]:
            hist = yf.Ticker(sym).history(period=f"{period+5}d")
            if hist.empty: continue
            diff = hist["Close"].diff().dropna().tail(period)
            up_days   += int((diff > 0).sum())
            down_days += int((diff < 0).sum())
            time.sleep(0.2)

        if down_days == 0:
            return {"ratio": None, "signal": "計算不可"}
        ratio = round(up_days / down_days * 100, 1)
        signal = "過熱(売られすぎ注意)" if ratio > 120 else \
                 "売られすぎ(反発に注意)" if ratio < 70  else "中立"
        logger.info(f"[OK] 騰落レシオ近似: {ratio}")
        return {
            "ratio":      ratio,
            "up_days":    up_days,
            "down_days":  down_days,
            "signal":     signal,
            "note":       "主要銘柄による近似値（東証全銘柄ではありません）",
        }
    except Exception as e:
        logger.error(f"[FAIL] 騰落レシオ: {e}")
        return {"ratio": None, "signal": "計算失敗", "error": str(e)}


# ─── Google News RSS 市場統計ニュース ─────────────────────
MARKET_STAT_KEYWORDS = [
    ("信用残 買い残 売り残",           "信用残",       "A"),
    ("騰落レシオ",                     "騰落レシオ",   "B"),
    ("空売り比率",                     "空売り比率",   "B"),
    ("裁定残 裁定買い",               "裁定残",       "B"),
    ("投資主体別 外国人 個人投資家",  "投資主体別",   "A"),
    ("決算 業績 予想 結果",           "決算情報",     "A"),
    ("レーティング 目標株価 格上げ 格下げ", "レーティング", "B"),
    ("経済指標 発表 結果",            "経済指標",     "A"),
    ("FOMC 議事録 声明",             "FOMC",         "A"),
    ("日銀 金融政策決定会合",         "日銀会合",     "A"),
    ("先物 オプション",               "先物/オプション","B"),
    ("PER PBR 割安 割高",            "バリュエーション","B"),
]


def fetch_market_stat_news() -> list[dict]:
    base = "https://news.google.com/rss/search?q={}&hl=ja&gl=JP&ceid=JP:ja"
    all_news = []
    for keyword, label, importance in MARKET_STAT_KEYWORDS:
        url = base.format(quote(keyword))
        try:
            feed  = feedparser.parse(url)
            items = []
            for entry in feed.entries[:4]:
                t = entry.get("published_parsed")
                pub_jst = ""
                if t:
                    from datetime import datetime
                    dt = datetime(*t[:6], tzinfo=timezone.utc).astimezone(JST)
                    pub_jst = dt.strftime("%Y-%m-%d %H:%M JST")
                items.append({
                    "label":         label,
                    "source_name":   label,
                    "importance":    importance,
                    "title":         entry.get("title",""),
                    "url":           entry.get("link",""),
                    "published_jst": pub_jst,
                    "fetch_time":    get_jst_now().isoformat(),
                    "category":      "market_stats",
                })
            all_news.extend(items)
            logger.info(f"[OK] 市場統計ニュース [{label}]: {len(items)}件")
        except Exception as e:
            logger.error(f"[FAIL] 市場統計ニュース [{label}]: {e}")
        time.sleep(1.0)
    return all_news


# ─── 経済指標カレンダー ────────────────────────────────────
CALENDAR_KEYWORDS = [
    "米国 雇用統計 予想",
    "CPI 消費者物価指数 発表",
    "FOMC 会合 結果",
    "GDP 速報値",
    "日銀 政策金利 決定",
    "PMI 景況感指数",
]


def fetch_economic_calendar() -> list[dict]:
    base = "https://news.google.com/rss/search?q={}&hl=ja&gl=JP&ceid=JP:ja"
    events = []
    for kw in CALENDAR_KEYWORDS:
        try:
            f = feedparser.parse(base.format(quote(kw)))
            for e in f.entries[:3]:
                t = e.get("published_parsed")
                pub_jst = ""
                if t:
                    dt = datetime(*t[:6], tzinfo=timezone.utc).astimezone(JST)
                    pub_jst = dt.strftime("%Y-%m-%d %H:%M JST")
                events.append({
                    "keyword":     kw,
                    "title":       e.get("title",""),
                    "url":         e.get("link",""),
                    "published_jst": pub_jst,
                })
            time.sleep(0.8)
        except Exception:
            pass
    logger.info(f"[OK] 経済カレンダーニュース: {len(events)}件")
    return events


# ─── まとめて実行 ─────────────────────────────────────────
def run_fundamental(prices: dict) -> dict:
    logger.info("=== ファンダメンタル分析開始 ===")
    result = {
        "fundamentals":     fetch_fundamentals(),
        "futures":          fetch_futures(),
        "options":          fetch_options_summary(),
        "nt_ratio":         calc_nt_ratio(prices),
        "torakuhi":         calc_torakuhi(),
        "market_stat_news": fetch_market_stat_news(),
        "economic_calendar":fetch_economic_calendar(),
        "fetch_time":       get_jst_now().isoformat(),
    }

    # 保存
    today    = get_today_str()
    dirs     = get_dirs()
    savepath = dirs["data_processed"] / f"{today}_fundamental.json"
    with open(savepath, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    logger.info(f"=== ファンダ分析完了・保存: {savepath} ===")
    return result
