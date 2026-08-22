"""
src/fx_data_premium.py
無料 API から取得できるプレミアム経済データ
─────────────────────────────────────────────
提供データ:
  - FRED:        FFR実効金利, M2, CPI, 失業率, HYスプレッド, 日本長短期金利
  - US Treasury: 全期間イールドカーブ (12 maturities)
  - CFTC:        JPY IMM 投機ポジション (Leveraged Money Net)
  - T-bill 金利: FedWatch 近似確率 (T-bill implied rate path)
  - yfinance:    マルチタイムフレーム USDJPY, VIXターム構造

全関数は失敗時に空 dict / フォールバック値を返す（例外を外に漏らさない）
"""

import io
import warnings
import zipfile
from datetime import datetime, timezone, timedelta, date
from typing import Optional

import pandas as pd
import requests
import yfinance as yf

warnings.filterwarnings("ignore")

JST = timezone(timedelta(hours=9))

# ─── リクエスト共通ヘッダー ────────────────────────────────────────────────────
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

# ─── モジュールレベルキャッシュ（同一実行内で重複 DL 防止） ──────────────────
_cache: dict = {}
_CACHE_TTL  = 3600  # 秒


def _cache_get(key: str):
    entry = _cache.get(key)
    if entry and (datetime.now().timestamp() - entry["ts"]) < _CACHE_TTL:
        return entry["data"]
    return None


def _cache_set(key: str, data):
    _cache[key] = {"ts": datetime.now().timestamp(), "data": data}


# ─────────────────────────────────────────────────────────────────────────────
# 1. FRED API（APIキー不要）
# ─────────────────────────────────────────────────────────────────────────────

_FRED_SERIES = {
    "FEDFUNDS":          ("FFR実効金利 (%)",         "%"),
    "M2SL":              ("M2マネーサプライ (10億ドル)", "B$"),
    "CPIAUCSL":          ("CPI 指数",                 ""),
    "UNRATE":            ("失業率 (%)",               "%"),
    "BAMLH0A0HYM2":      ("HY社債スプレッド (%)",     "%"),
    "IRLTLT01JPM156N":   ("日本長期金利 (%)",          "%"),   # Japan 10Y (OECD)
    "IRSTCI01JPM156N":   ("日本短期金利 (%)",          "%"),   # Japan short-term
    "T10Y2Y":            ("米10Y-2Yスプレッド (%)",   "%"),   # 逆イールド指標
    "T10Y3M":            ("米10Y-3Mスプレッド (%)",   "%"),
    "DFII10":            ("米実質10Y金利 TIPS (%)",   "%"),
    "T10YIE":            ("BEIインフレ期待 (%)",       "%"),
}


def fetch_fred_data() -> dict:
    """
    FRED API から主要経済指標を取得する (APIキー不要)
    Returns:
        {series_id: {"name": str, "value": float, "date": str, "unit": str}}
    """
    cached = _cache_get("fred")
    if cached:
        return cached

    result = {}
    for sid, (name, unit) in _FRED_SERIES.items():
        try:
            url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
            r = requests.get(url, timeout=15, headers=_HEADERS)
            if r.status_code != 200:
                continue
            df = pd.read_csv(io.StringIO(r.text), na_values=".")
            df.columns = ["date", "value"]
            df = df.dropna()
            if df.empty:
                continue
            latest_val  = float(df["value"].iloc[-1])
            latest_date = df["date"].iloc[-1]
            prev_val    = float(df["value"].iloc[-2]) if len(df) > 1 else latest_val
            result[sid] = {
                "name":  name,
                "unit":  unit,
                "value": latest_val,
                "prev":  prev_val,
                "chg":   latest_val - prev_val,
                "date":  latest_date,
            }
        except Exception:
            pass

    _cache_set("fred", result)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 2. 米財務省 イールドカーブ (全12期間)
# ─────────────────────────────────────────────────────────────────────────────

_TREASURY_MATS = [
    ("BC_1MONTH",  "1M"),  ("BC_2MONTH",  "2M"),  ("BC_3MONTH",  "3M"),
    ("BC_6MONTH",  "6M"),  ("BC_1YEAR",   "1Y"),  ("BC_2YEAR",   "2Y"),
    ("BC_3YEAR",   "3Y"),  ("BC_5YEAR",   "5Y"),  ("BC_7YEAR",   "7Y"),
    ("BC_10YEAR", "10Y"),  ("BC_20YEAR", "20Y"),  ("BC_30YEAR", "30Y"),
]

_NS_ATOM = "{http://www.w3.org/2005/Atom}"
_NS_DS   = "{http://schemas.microsoft.com/ado/2007/08/dataservices}"


def fetch_treasury_yield_curve() -> dict:
    """
    米財務省 XML API から全 12 期間のイールドカーブを取得する
    Returns:
        {"1M": float, "2M": float, ..., "30Y": float, "date": str}
    """
    cached = _cache_get("treasury")
    if cached:
        return cached

    # 今月 → 先月の順に試す
    now = datetime.now(JST)
    for delta_months in [0, 1]:
        year  = now.year
        month = now.month - delta_months
        if month <= 0:
            month += 12
            year  -= 1
        ym  = f"{year}{month:02d}"
        url = (
            "https://home.treasury.gov/resource-center/data-chart-center/"
            f"interest-rates/pages/xml?data=daily_treasury_yield_curve"
            f"&field_tdr_date_value_month={ym}"
        )
        try:
            r = requests.get(url, timeout=15, headers=_HEADERS)
            if r.status_code != 200:
                continue

            import xml.etree.ElementTree as ET
            root    = ET.fromstring(r.content)
            entries = root.findall(f"{_NS_ATOM}entry")
            if not entries:
                continue

            last_entry = entries[-1]
            content    = last_entry.find(f"{_NS_ATOM}content")
            props      = content[0] if content is not None else None
            if props is None:
                continue

            curve = {}
            for tag, label in _TREASURY_MATS:
                el = props.find(f"{_NS_DS}{tag}")
                if el is not None and el.text:
                    curve[label] = float(el.text)

            # 日付取得
            updated = last_entry.find(f"{_NS_ATOM}updated")
            curve["date"] = updated.text[:10] if updated is not None else ym

            if len(curve) >= 8:
                _cache_set("treasury", curve)
                return curve
        except Exception:
            pass

    return {}


# ─────────────────────────────────────────────────────────────────────────────
# 3. CFTC COT — JPY Leveraged Money 投機ポジション
# ─────────────────────────────────────────────────────────────────────────────

def fetch_cftc_jpy_positions(weeks: int = 13) -> dict:
    """
    CFTC 金融先物 COT から JPY の Leveraged Money ポジションを取得
    URL: https://www.cftc.gov/files/dea/history/fut_fin_txt_{YEAR}.zip
    Returns:
        {
          "dates":   [str, ...],   # 週次日付
          "net":     [int, ...],   # ネットポジション (枚)
          "longs":   [int, ...],
          "shorts":  [int, ...],
          "latest_date": str,
          "latest_net":  int,
        }
    """
    cached = _cache_get("cftc_jpy")
    if cached:
        return cached

    now  = datetime.now(JST)
    dfs  = []

    for year in [now.year, now.year - 1]:
        url = f"https://www.cftc.gov/files/dea/history/fut_fin_txt_{year}.zip"
        try:
            r = requests.get(url, timeout=30, headers=_HEADERS)
            if r.status_code != 200:
                continue
            with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
                with zf.open(zf.namelist()[0]) as f:
                    df = pd.read_csv(f, encoding="latin-1")

            # JAPANESE YEN - CHICAGO MERCANTILE EXCHANGE (code: 097741)
            jpy_mask = (
                df["Market_and_Exchange_Names"].str.contains(
                    "^JAPANESE YEN", na=False, case=False, regex=True
                )
            )
            jpy_df = df[jpy_mask][
                ["Report_Date_as_YYYY-MM-DD",
                 "Lev_Money_Positions_Long_All",
                 "Lev_Money_Positions_Short_All"]
            ].copy()

            if jpy_df.empty:
                continue

            jpy_df.columns = ["date", "long", "short"]
            jpy_df["long"]  = pd.to_numeric(jpy_df["long"],  errors="coerce").fillna(0).astype(int)
            jpy_df["short"] = pd.to_numeric(jpy_df["short"], errors="coerce").fillna(0).astype(int)
            jpy_df["net"]   = jpy_df["long"] - jpy_df["short"]
            dfs.append(jpy_df)
        except Exception:
            pass

    if not dfs:
        return {}

    combined = (
        pd.concat(dfs, ignore_index=True)
        .drop_duplicates("date")
        .sort_values("date")
    )
    tail = combined.tail(weeks)

    result = {
        "dates":        tail["date"].tolist(),
        "net":          tail["net"].tolist(),
        "longs":        tail["long"].tolist(),
        "shorts":       tail["short"].tolist(),
        "latest_date":  tail["date"].iloc[-1],
        "latest_net":   int(tail["net"].iloc[-1]),
    }
    _cache_set("cftc_jpy", result)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 4. FedWatch 近似確率 (T-bill implied rate path)
# ─────────────────────────────────────────────────────────────────────────────

def calc_fedwatch_implied(fred_data: dict, treasury_curve: dict) -> dict:
    """
    FRED FFR + 米財務省 T-bill カーブから利下げ確率を近似計算
    標準 FedWatch (ZQ先物) の無料近似版

    FOMC 予定スケジュール（2026年）:
      7月29-30日, 9月16-17日, 11月4-5日, 12月9-10日
    Returns:
        {
          "meetings": [str, ...],
          "cut_prob":  [float, ...],
          "hold_prob": [float, ...],
          "hike_prob": [float, ...],
          "current_ffr": float,
          "note": str,
        }
    """
    try:
        # FRED が取れない場合は T-bill 1M を代替 (1M T-bill ≈ FFR + 6bp)
        fred_ffr = fred_data.get("FEDFUNDS", {}).get("value")
        if fred_ffr is not None:
            ffr, ffr_src = fred_ffr, "FRED実績"
        elif "1M" in treasury_curve:
            # FRED取得失敗時の代替。近似値であることを呼び出し側に伝える
            ffr, ffr_src = treasury_curve["1M"] - 0.06, "1M T-bill近似"
        else:
            ffr, ffr_src = 4.33, "固定フォールバック"

        # 各 FOMC 対応 T-bill 期間マッピング
        # ※開催日を持たせ、過ぎた会合は自動で落とす（過去の会合を
        #   「次回」として表示してしまう事故を防ぐ）
        _today = datetime.now(JST).date()
        _schedule = [
            (date(2026, 7, 29), "7月(7/29)",   "3M"),
            (date(2026, 9, 16), "9月(9/16)",   "6M"),
            (date(2026, 11, 4), "11月(11/4)",  "1Y"),
            (date(2026, 12, 9), "12月(12/9)",  "1Y"),
        ]
        meetings_map = [(lbl, mat) for d, lbl, mat in _schedule if d >= _today]
        if not meetings_map:
            # 予定表を使い切った場合は年をまたいだ想定で最長期を1件だけ返す
            meetings_map = [("次回会合", "1Y")]

        cut_p, hold_p, hike_p = [], [], []
        meetings = []

        for label, mat in meetings_map:
            tbill = treasury_curve.get(mat)
            if tbill is None:
                # フォールバック: 隣接 maturity
                tbill = treasury_curve.get("2Y", ffr)

            spread = tbill - ffr   # T-bill - FFR
            # T-bill は通常 FFR + 5~15bp のプレミアム
            # プレミアムを差し引いた後の超過分を利下げ/利上げシグナルとして使用
            adj_spread = spread - 0.08  # 8bp正常プレミアム調整

            # ±25bp per rate change (標準的なFOMCステップ)
            raw_cut  = max(0.0, -adj_spread / 0.25 * 100)
            raw_hike = max(0.0,  adj_spread / 0.25 * 100)
            raw_hold = max(0.0, 100.0 - raw_cut - raw_hike)

            # 正規化
            total = raw_cut + raw_hold + raw_hike
            if total > 0:
                cut_p.append( round(raw_cut  / total * 100, 1))
                hold_p.append(round(raw_hold / total * 100, 1))
                hike_p.append(round(raw_hike / total * 100, 1))
            else:
                cut_p.append(20.0)
                hold_p.append(70.0)
                hike_p.append(10.0)
            meetings.append(label)

        return {
            "meetings":    meetings,
            "cut_prob":    cut_p,
            "hold_prob":   hold_p,
            "hike_prob":   hike_p,
            "current_ffr": ffr,
            "ffr_source":  ffr_src,
            "note":        "T-bill implied (CME FedWatch 近似)",
        }
    except Exception:
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# 5. マルチタイムフレーム USDJPY 分析
# ─────────────────────────────────────────────────────────────────────────────

def fetch_multitf_usdjpy() -> dict:
    """
    1H / Daily / Weekly の USDJPY データを取得
    Returns:
        {"1H": df, "D": df, "W": df}
    """
    cached = _cache_get("mtf_usdjpy")
    if cached:
        return cached

    result = {}
    configs = [
        ("1H", "5d",  "1h"),
        ("D",  "6mo", "1d"),
        ("W",  "2y",  "1wk"),
    ]
    for label, period, interval in configs:
        try:
            df = yf.Ticker("USDJPY=X").history(period=period, interval=interval,
                                               auto_adjust=True)
            if not df.empty and len(df) >= 5:
                result[label] = df
        except Exception:
            pass

    _cache_set("mtf_usdjpy", result)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 6. VIX ターム構造
# ─────────────────────────────────────────────────────────────────────────────

def fetch_vix_term() -> dict:
    """
    VIX / VIX3M / VVIX を取得してコンタンゴ/バックワーデーション判定
    Returns:
        {"vix": float, "vix3m": float, "vvix": float, "structure": str}
    """
    cached = _cache_get("vix_term")
    if cached:
        return cached

    vals = {}
    for sym, key in [("^VIX", "vix"), ("^VIX3M", "vix3m"), ("^VVIX", "vvix")]:
        try:
            df = yf.Ticker(sym).history(period="5d")
            if not df.empty:
                vals[key] = float(df["Close"].iloc[-1])
        except Exception:
            pass

    if "vix" in vals and "vix3m" in vals:
        spread = vals["vix3m"] - vals["vix"]
        if spread > 1.5:
            vals["structure"] = f"コンタンゴ (+{spread:.1f}) 安定"
        elif spread < -1.5:
            vals["structure"] = f"バックワーデーション ({spread:.1f}) 警戒"
        else:
            vals["structure"] = f"フラット ({spread:+.1f})"
    else:
        vals["structure"] = "─"

    _cache_set("vix_term", vals)
    return vals


# ─────────────────────────────────────────────────────────────────────────────
# 7. 全プレミアムデータ一括取得
# ─────────────────────────────────────────────────────────────────────────────

def fetch_all_premium() -> dict:
    """
    全プレミアムデータを取得してまとめた dict を返す
    Returns:
        {
          "fred":      {series_id: {...}},
          "treasury":  {"1M": float, ..., "date": str},
          "cftc_jpy":  {...},
          "fedwatch":  {...},
          "vix_term":  {...},
        }
    """
    fred_data     = fetch_fred_data()
    treasury_data = fetch_treasury_yield_curve()
    cftc_data     = fetch_cftc_jpy_positions()
    fedwatch_data = calc_fedwatch_implied(fred_data, treasury_data)
    vix_term_data = fetch_vix_term()

    return {
        "fred":     fred_data,
        "treasury": treasury_data,
        "cftc_jpy": cftc_data,
        "fedwatch": fedwatch_data,
        "vix_term": vix_term_data,
    }
