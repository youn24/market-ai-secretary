"""
drawdown_screener.py — 下落×割安スクリーナー（日米・Gemini不使用）

「直近6カ月で下げた銘柄」を拾い、それが
  ① 割安候補     … 指標が安く、来期の利益も減る予想になっていない
  ② 要注意       … 指標は安いが、減益予想・売上減・赤字のどれかがある
                    （利益が落ちる会社は指標のうえで必ず安く見える＝バリュートラップ候補）
  ③ 割高のまま   … 下げたが、まだ指標は高い
のどれにあたるかを仕分ける。

なぜ作ったか:
  2026-11 の AI・半導体の急落で「下げた銘柄＝買い場？」を毎回手で調べていた。
  ただ、下げた理由が「一時的な不安」か「利益のピークアウト」かで意味が逆になる。
  PERが低いだけで拾うと、メモリなど景気循環株の天井（利益最大＝PER最小）を掴む。
  そのため「来期EPS < 今期EPS」を必ず確認し、該当すれば要注意へ落とす。

設計:
  - 価格は yf.download で一括取得（1年分・日足）。銘柄数が多くても速い。
  - .info（PER等）は「下げた銘柄」だけに叩く。全銘柄に叩くと遅く、制限にもかかる。
  - 計算部分（_price_metrics / _classify）は取得と分離し、ネット無しで検証できる。

単体実行:
  python -m src.drawdown_screener            # 表を表示
  python -m src.drawdown_screener --json out.json
"""

import math
from datetime import timedelta

from src.utils import setup_logger

logger = setup_logger("drawdown_screener")

# ── 対象銘柄（編集して増減してよい）────────────────────────────────
US_STOCKS = {
    # 半導体・AIインフラ
    "NVDA": "エヌビディア", "AMD": "AMD", "AVGO": "ブロードコム", "MU": "マイクロン",
    "LRCX": "ラムリサーチ", "AMAT": "アプライド・マテリアルズ", "TSM": "TSMC(ADR)",
    "QCOM": "クアルコム", "INTC": "インテル", "SMCI": "スーパー・マイクロ",
    # 大型テック
    "MSFT": "マイクロソフト", "AAPL": "アップル", "GOOGL": "アルファベット",
    "AMZN": "アマゾン", "META": "メタ", "TSLA": "テスラ", "NFLX": "ネットフリックス",
    "ORCL": "オラクル",
    # ソフトウェア（AI置き換え懸念で売られた組）
    "CRM": "セールスフォース", "ADBE": "アドビ", "NOW": "サービスナウ",
    "INTU": "インテュイット", "WDAY": "ワークデイ", "PLTR": "パランティア",
    "ACN": "アクセンチュア",
    # 金融・フィンテック
    "JPM": "JPモルガン", "V": "ビザ", "PYPL": "ペイパル", "FIS": "FIS",
    "COIN": "コインベース",
    # 景気敏感・その他
    "BA": "ボーイング", "CAT": "キャタピラー", "CMI": "カミンズ", "APTV": "アプティブ",
    "FSLR": "ファーストソーラー", "ALB": "アルベマール", "XOM": "エクソンモービル",
    "NKE": "ナイキ", "LULU": "ルルレモン", "SBUX": "スターバックス", "DIS": "ディズニー",
    "UNH": "ユナイテッドヘルス", "LLY": "イーライリリー", "PFE": "ファイザー",
    "MRK": "メルク",
}

JP_STOCKS = {
    # 半導体・AIインフラ
    "8035.T": "東京エレクトロン", "6857.T": "アドバンテスト", "285A.T": "キオクシアHD",
    "5803.T": "フジクラ", "5801.T": "古河電気工業", "4062.T": "イビデン",
    "6920.T": "レーザーテック", "6146.T": "ディスコ", "4063.T": "信越化学",
    "6526.T": "ソシオネクスト", "6723.T": "ルネサス", "3436.T": "SUMCO",
    "6525.T": "KOKUSAI ELECTRIC", "5016.T": "JX金属", "9984.T": "ソフトバンクG",
    # 情報・通信（米ソフトウェア安が波及した組）
    "6702.T": "富士通", "6701.T": "NEC", "4307.T": "野村総合研究所",
    "3626.T": "TIS", "9432.T": "NTT", "9433.T": "KDDI", "9434.T": "ソフトバンク",
    "4385.T": "メルカリ", "2413.T": "エムスリー",
    # 主力・内需・その他
    "7203.T": "トヨタ自動車", "7267.T": "本田技研", "6758.T": "ソニーG",
    "6501.T": "日立製作所", "7011.T": "三菱重工業", "7013.T": "IHI",
    "6861.T": "キーエンス", "6954.T": "ファナック", "6367.T": "ダイキン工業",
    "6981.T": "村田製作所", "6762.T": "TDK", "7741.T": "HOYA",
    "9983.T": "ファーストリテイリング", "7974.T": "任天堂", "6098.T": "リクルートHD",
    "4661.T": "オリエンタルランド", "4519.T": "中外製薬", "4568.T": "第一三共",
    "4502.T": "武田薬品", "8306.T": "三菱UFJ", "8316.T": "三井住友FG",
    "8766.T": "東京海上HD", "8058.T": "三菱商事", "8001.T": "伊藤忠商事",
    "5401.T": "日本製鉄",
}

# ── しきい値 ────────────────────────────────────────────────────
DROP_6M = -0.15        # 6カ月騰落率がこれ以下なら「下げた」
DROP_FROM_HIGH = -0.30  # または52週高値からの下落率がこれ以下
# 「指標が安い」と見なす予想PERの上限。
# 米国: S&P500の予想PERは長期平均で16〜18倍前後、近年は20倍超。18倍以下を安い側とする。
# 日本: プライム市場平均の予想PERが15倍前後（2026-11 株探の特集で14.6〜15.1倍）。
CHEAP_PER = {"US": 18.0, "JP": 14.0}
JP_PBR_CHEAP = 1.0      # 日本はPBR1倍割れも安い側に数える（ただしPER20倍以下に限る）

# ── 金利で基準を動かす（2026-11-29 追加）─────────────────────────
# PER の逆数＝益回り（利益÷株価）は、国債の利回りと比べられる。
# 国債で利息が多く取れるほど、株に求める益回りも上がる＝許されるPERが下がる。
# 上の CHEAP_PER は「金利が過去1年の平均くらいのとき」の基準とみなし、
# 今の10年金利が1年平均からずれた分だけ、求める益回りを同じだけ動かす。
#   例: 米国 基準18倍＝益回り5.56%。金利が平均より+0.5%高い → 6.06% → 16.5倍
# 絶対水準ではなく「1年平均からのずれ」を見るのは、日米で金利の水準が
# まったく違い、固定の数字を決めると片方が必ず歪むため。
RATE_SENSITIVITY = 1.0     # 金利の差を、求める益回りに何倍で効かせるか
PER_BOUNDS = (10.0, 25.0)  # 動かしすぎ防止（金利が急変した日の異常値対策）
RATE_SERIES = {"US": "米国10年国債", "JP": "日本10年国債"}
EPS_DROP_RATIO = 0.90   # 来期EPS が今期の90%未満なら「減益予想」
MAX_INFO_CALLS = 40     # .info を叩く上限（時間と制限対策）
MIN_HISTORY_ROWS = 120  # 6カ月比較に必要な最低本数


# ── 計算（ネット不要・単体で検証できる部分）────────────────────────
def _close_on_or_before(close, target_date):
    """target_date 以前で最も新しい終値。無ければ None。"""
    s = close[close.index <= target_date]
    return float(s.iloc[-1]) if len(s) else None


def _rsi(close, period: int = 14):
    """ワイルダー式RSI。データ不足なら None。"""
    if len(close) < period + 1:
        return None
    d = close.diff().dropna()
    up = d.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    u, l = float(up.iloc[-1]), float(dn.iloc[-1])
    if l == 0:
        return 100.0
    return round(100 - 100 / (1 + u / l), 1)


def _price_metrics(close):
    """1銘柄の終値系列から騰落率などを計算する。

    6カ月前・1カ月前は「営業日数」でなく**日付**で取る。
    日米で休場日が違うため、126本前と決め打ちすると比較期間がずれる。
    """
    close = close.dropna()
    close = close[close > 0]
    if len(close) < MIN_HISTORY_ROWS:
        return None
    last_d = close.index[-1]
    last = float(close.iloc[-1])
    p6 = _close_on_or_before(close, last_d - timedelta(days=182))
    p1 = _close_on_or_before(close, last_d - timedelta(days=30))
    hi = float(close.max())
    ma200 = float(close.tail(200).mean()) if len(close) >= 200 else None
    if not p6:
        return None
    return {
        "price": last,
        "as_of": str(last_d.date()) if hasattr(last_d, "date") else str(last_d),
        "ret_6m": last / p6 - 1,
        "ret_1m": (last / p1 - 1) if p1 else None,
        "from_high": last / hi - 1,
        "rsi14": _rsi(close),
        "vs_ma200": (last / ma200 - 1) if ma200 else None,
    }


def _is_dropped(m: dict) -> bool:
    return m["ret_6m"] <= DROP_6M or m["from_high"] <= DROP_FROM_HIGH


def _num(v, lo=None, hi=None):
    """yfinance の値を数値に。NaN・範囲外は None（異常値をそのまま使わない）。"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    if lo is not None and f < lo:
        return None
    if hi is not None and f > hi:
        return None
    return f


def _fundamentals(info: dict) -> dict:
    """.info から使う項目だけ取り出し、ありえない値を捨てる。"""
    info = info or {}
    return {
        "fwd_per": _num(info.get("forwardPE"), 0.01, 500),
        "ttm_per": _num(info.get("trailingPE"), 0.01, 500),
        "pbr": _num(info.get("priceToBook"), 0.01, 100),
        "ttm_eps": _num(info.get("trailingEps")),
        "fwd_eps": _num(info.get("forwardEps")),
        # 売上成長率は割合（0.12=12%）で来る。±500%を超える値はデータ誤りとみなす
        "rev_growth": _num(info.get("revenueGrowth"), -5, 5),
    }


def _rate_adjusted_per(base_per: float, now, avg) -> float:
    """金利が1年平均からずれた分だけ、割安とみなすPERの上限を動かす。

    金利が取れない日は基準を動かさない（＝従来どおり）。
    """
    if not isinstance(now, (int, float)) or not isinstance(avg, (int, float)):
        return base_per
    ey = 1 / base_per + (now - avg) / 100 * RATE_SENSITIVITY
    if ey <= 0:
        return PER_BOUNDS[1]
    return round(min(max(1 / ey, PER_BOUNDS[0]), PER_BOUNDS[1]), 1)


def _thresholds(rates: dict) -> dict:
    """市場ごとの今日の基準PER。rates = {"US": {"now":..,"avg":..}, ...}"""
    out = {}
    for mkt, base in CHEAP_PER.items():
        r = (rates or {}).get(mkt) or {}
        out[mkt] = _rate_adjusted_per(base, r.get("now"), r.get("avg"))
    return out


def _classify(market: str, f: dict, cheap_per: float = None) -> dict:
    """指標から ①割安候補 ②要注意 ③割高のまま ④判定不可 を決める。

    ⚠️ 順序に意味がある。先に「罠の兆候」を集めてから安さを見る。
       安さだけで判定すると、利益のピークで一番安く見える銘柄が上位に来る。
    """
    flags = []
    ttm_eps, fwd_eps = f.get("ttm_eps"), f.get("fwd_eps")
    if ttm_eps is not None and ttm_eps <= 0:
        flags.append("いまは赤字")
    if (ttm_eps and fwd_eps and ttm_eps > 0 and fwd_eps > 0
            and fwd_eps < ttm_eps * EPS_DROP_RATIO):
        flags.append(f"来年の利益が今より{(1 - fwd_eps / ttm_eps) * 100:.0f}%減る予想")
    if fwd_eps is not None and fwd_eps <= 0:
        flags.append("来年も赤字の予想")
    rg = f.get("rev_growth")
    if rg is not None and rg < 0:
        flags.append(f"売上が前の年より{-rg * 100:.0f}%減")

    per = f.get("fwd_per") or f.get("ttm_per")
    pbr = f.get("pbr")
    limit = cheap_per if cheap_per else CHEAP_PER[market]
    if per is None and pbr is None:
        return {"bucket": "判定不可", "per_used": None, "flags": flags or ["指標なし"],
                "cheap_per": limit}

    cheap = per is not None and per <= limit
    if (market == "JP" and pbr is not None and pbr < JP_PBR_CHEAP
            and (per is None or per <= 20)):
        cheap = True

    if cheap:
        bucket = "要注意" if flags else "割安候補"
    else:
        bucket = "要注意" if any("赤字" in x for x in flags) else "割高のまま"
    return {"bucket": bucket, "per_used": per, "flags": flags, "cheap_per": limit}


def _rank_key(r: dict):
    """割安候補の並び順: PERが基準に対して安いほど、深く下げているほど上。"""
    per = r.get("per_used")
    base = r.get("cheap_per") or CHEAP_PER[r["market"]]
    per_score = (per / base) if per else 1.0
    return per_score + r["ret_6m"]  # ret_6m は負なので、深い下げほど小さくなる


# ── 取得（ネットが要る部分）──────────────────────────────────────
def _download_closes(symbols: list):
    """1年分の終値をまとめて取る。返り値 {symbol: Series}。"""
    import warnings
    warnings.filterwarnings("ignore")
    import yfinance as yf

    out = {}
    df = yf.download(symbols, period="1y", interval="1d", group_by="ticker",
                     progress=False, auto_adjust=True, threads=True)
    for s in symbols:
        try:
            sub = df[s] if len(symbols) > 1 else df
            c = sub["Close"].dropna()
            if len(c):
                out[s] = c
        except Exception:
            continue
    return out


def _fetch_rates() -> dict:
    """日米10年金利の「今」と「過去1年の平均」。取れなかった市場は入れない。"""
    out = {}
    try:
        import warnings
        warnings.filterwarnings("ignore")
        import yfinance as yf
        c = yf.download("^TNX", period="1y", interval="1d", progress=False,
                        auto_adjust=False)["Close"]
        c = c.squeeze().dropna() if hasattr(c, "squeeze") else c.dropna()
        if len(c) >= 100:
            out["US"] = {"now": round(float(c.iloc[-1]), 3), "avg": round(float(c.mean()), 3)}
        else:
            logger.warning(f"米10年金利の履歴が短い（{len(c)}本）。米国の基準は固定のまま")
    except Exception as e:
        logger.error(f"米10年金利の取得に失敗（米国の基準は固定のまま）: {type(e).__name__}: {e}")
    try:
        from src.risk_gauges import _fetch_jgb
        j = _fetch_jgb()
        g = next((x for x in (j.get("gauges") or []) if x.get("symbol") == "JGB10年"), None)
        if g and isinstance(g.get("value"), (int, float)) and isinstance(g.get("avg_1y"), (int, float)):
            out["JP"] = {"now": g["value"], "avg": g["avg_1y"]}
        else:
            logger.warning("日本10年国債の値が取れず、日本の基準は固定のまま")
    except Exception as e:
        logger.error(f"日本10年国債の取得に失敗（日本の基準は固定のまま）: {type(e).__name__}: {e}")
    return out


def _fetch_info(symbol: str) -> dict:
    import yfinance as yf
    return yf.Ticker(symbol).info or {}


# ── 本体 ────────────────────────────────────────────────────────
def scan(us: dict = None, jp: dict = None, downloader=None, info_fetcher=None,
         rates_fetcher=None) -> dict:
    """スクリーニングを実行する。

    downloader / info_fetcher を差し替えればネット無しで検証できる。
    """
    us = US_STOCKS if us is None else us
    jp = JP_STOCKS if jp is None else jp
    downloader = downloader or _download_closes
    info_fetcher = info_fetcher or _fetch_info
    rates_fetcher = rates_fetcher or _fetch_rates

    universe = {s: ("US", n) for s, n in us.items()}
    universe.update({s: ("JP", n) for s, n in jp.items()})

    try:
        closes = downloader(list(universe))
    except Exception as e:
        logger.error(f"価格の一括取得に失敗: {type(e).__name__}: {e}")
        return {"available": False, "error": f"価格取得失敗: {e}"}

    # 半分以上取れなかった日は結果を出さない（偏った一覧を「今日の結果」として見せない）
    if len(closes) < len(universe) * 0.5:
        msg = f"価格が取れた銘柄が少なすぎる（{len(closes)}/{len(universe)}）"
        logger.error(msg)
        return {"available": False, "error": msg}

    dropped, no_data = [], []
    for sym, (mkt, name) in universe.items():
        m = _price_metrics(closes[sym]) if sym in closes else None
        if not m:
            no_data.append(sym)
            continue
        if _is_dropped(m):
            dropped.append({"symbol": sym, "name": name, "market": mkt, **m})

    # 金利で今日の基準PERを決める（取れなければ固定値のまま）
    try:
        rates = rates_fetcher() or {}
    except Exception as e:
        logger.error(f"金利の取得に失敗（基準は固定のまま）: {type(e).__name__}: {e}")
        rates = {}
    per_limit = _thresholds(rates)

    # 深く下げた順に .info を叩く（上限あり）
    dropped.sort(key=lambda r: r["ret_6m"])
    rows, info_failed = [], []
    for r in dropped[:MAX_INFO_CALLS]:
        try:
            f = _fundamentals(info_fetcher(r["symbol"]))
        except Exception as e:
            logger.warning(f"  {r['symbol']} の指標取得失敗: {type(e).__name__}: {e}")
            info_failed.append(r["symbol"])
            f = _fundamentals({})
        rows.append({**r, **f, **_classify(r["market"], f, per_limit[r["market"]])})

    buckets = {k: [x for x in rows if x["bucket"] == k]
               for k in ("割安候補", "要注意", "割高のまま", "判定不可")}
    buckets["割安候補"].sort(key=_rank_key)
    for k in ("要注意", "割高のまま", "判定不可"):
        buckets[k].sort(key=lambda x: x["ret_6m"])

    as_of = max((x["as_of"] for x in rows), default=None)
    res = {
        "available": True,
        "as_of": as_of,
        "universe": len(universe),
        "priced": len(universe) - len(no_data),
        "dropped_count": len(dropped),
        "candidates": buckets["割安候補"],
        "caution": buckets["要注意"],
        "pricey": buckets["割高のまま"],
        "unknown": buckets["判定不可"],
        "no_data": no_data,
        "info_failed": info_failed,
        "truncated": max(0, len(dropped) - MAX_INFO_CALLS),
        "thresholds": {"drop_6m": DROP_6M, "drop_from_high": DROP_FROM_HIGH,
                       "cheap_per_base": CHEAP_PER, "cheap_per": per_limit,
                       "jp_pbr": JP_PBR_CHEAP},
        # 市場ごと: 今の10年金利・1年平均・今日の基準PER（金利が取れない市場は adjusted=False）
        "rates": {m: {**(rates.get(m) or {}), "name": RATE_SERIES[m],
                      "base_per": CHEAP_PER[m], "per": per_limit[m],
                      "adjusted": m in rates}
                  for m in CHEAP_PER},
    }
    return res


def run() -> dict:
    """cloud_run から呼ぶ入口。例外は外に出さず、内容は logger.error に残す。"""
    try:
        res = scan()
    except Exception as e:
        logger.error(f"下落×割安スクリーナー失敗: {type(e).__name__}: {e}", exc_info=True)
        return {"available": False, "error": str(e)}
    if res.get("available"):
        logger.info(
            f"下落×割安: {res['priced']}/{res['universe']}銘柄を計算、"
            f"下げた銘柄 {res['dropped_count']} → 割安候補 {len(res['candidates'])}・"
            f"要注意 {len(res['caution'])}・割高のまま {len(res['pricey'])}")
        if res["no_data"]:
            logger.warning(f"  価格データなし: {', '.join(res['no_data'][:15])}")
    return res


# ── 表示（ターミナル用）──────────────────────────────────────────
def _fmt_pct(v):
    return f"{v * 100:+.0f}%" if isinstance(v, (int, float)) else "—"


def _fmt_x(v, d=1):
    return f"{v:.{d}f}" if isinstance(v, (int, float)) else "—"


def format_text(res: dict) -> str:
    if not res.get("available"):
        return f"取得できませんでした: {res.get('error')}"
    lines = [f"下落×割安スクリーナー（{res['as_of']}時点・{res['priced']}/{res['universe']}銘柄）",
             f"6カ月{DROP_6M * 100:.0f}%以下 または 高値から{DROP_FROM_HIGH * 100:.0f}%以下 → {res['dropped_count']}銘柄"]
    for m, r in (res.get("rates") or {}).items():
        if r.get("adjusted"):
            lines.append(f"  {m} 基準PER {r['per']}倍（{r['name']} {r['now']:.2f}% ／ 1年平均 {r['avg']:.2f}%）")
        else:
            lines.append(f"  {m} 基準PER {r['per']}倍（金利が取れず固定）")
    lines.append("")
    for title, key in (("① 割安候補", "candidates"), ("② 要注意", "caution"),
                       ("③ 割高のまま", "pricey"), ("④ 判定不可", "unknown")):
        lines.append(f"{title}（{len(res[key])}）")
        for x in res[key]:
            lines.append(
                f"  {x['market']} {x['name'][:14]:<14} 6M {_fmt_pct(x['ret_6m']):>5} "
                f"高値比 {_fmt_pct(x['from_high']):>5}  PER {_fmt_x(x.get('per_used')):>5} "
                f"PBR {_fmt_x(x.get('pbr'), 2):>5}  RSI {_fmt_x(x.get('rsi14'), 0):>3}"
                + (f"  ⚠ {' / '.join(x['flags'])}" if x.get("flags") else ""))
        lines.append("")
    if res.get("truncated"):
        lines.append(f"※ 下げた銘柄が多いため、下落の浅い {res['truncated']} 銘柄は指標を取得していません")
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    import json

    ap = argparse.ArgumentParser(description="下落×割安スクリーナー（日米）")
    ap.add_argument("--json", help="結果をJSONで保存するパス")
    a = ap.parse_args()
    r = run()
    print(format_text(r))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fp:
            json.dump(r, fp, ensure_ascii=False, indent=2, default=str)
        print(f"保存: {a.json}")
