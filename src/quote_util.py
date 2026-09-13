"""
前日終値の取得（共通）— Yahoo の meta を信用しないための唯一の入口

なぜこのモジュールが必要か:
  YahooのチャートAPIが返す `chartPreviousClose` は「前日の終値」ではなく
  **取得レンジの直前の終値**である。range=5d なら約6日前、range=1y なら1年前を指す。

  この仕様を知らずに使った結果、2026-08-22までに2種類の事故が起きていた:
    ・us_movers … range=1y で サンディスクの前日比が +3505% と表示された
    ・sector_ranking_jp … range=5d で17業種すべての前日比が誤り。
      医薬品は「+3.80%」と表示していたが実際は −1.47%（符号まで逆）だった

  さらに `previousClose` はチャートAPIの meta には基本入っていない（None）。
  `meta.get("previousClose", 0)` と書くと0になり、変化率が常に0になる。

  同じ間違いを各所で繰り返さないよう、前日終値を出す処理をここに一本化する。
  **新しくYahooから価格を取るときは必ずこの関数を使うこと。**

レンジごとの chartPreviousClose の意味（実測で確認）:
  range=1d  … 前日の終値（正しい）★ここだけは使ってよい
  range=5d  … 約6日前の終値（誤り）
  range=1y  … 1年前の終値（大きく誤る）
  つまり「レンジの直前」を返す仕様。range=1d 以外では使わないこと。
  design_ai.py のブラウザ側JSは range=1d なので正しい。

正しい求め方:
  終値の系列とタイムスタンプを突き合わせ、「取引所の日付が当日より前」の
  最後の終値を採用する。夏時間・冬時間は meta.gmtoffset から吸収する。
"""
import json
import ssl
import traceback
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from src.utils import setup_logger

logger = setup_logger("quote_util")

_UA = {"User-Agent": "Mozilla/5.0"}


def _ctx():
    c = ssl.create_default_context()
    c.check_hostname = False
    c.verify_mode = ssl.CERT_NONE
    return c


def fetch_chart(sym: str, rng: str = "5d", interval: str = "1d",
                timeout: int = 20) -> dict | None:
    """チャートAPIの result をそのまま返す。"""
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(sym)}?range={rng}&interval={interval}")
    try:
        req = urllib.request.Request(url, headers=_UA)
        d = json.loads(urllib.request.urlopen(req, context=_ctx(),
                                              timeout=timeout).read())
        return d["chart"]["result"][0]
    except Exception:
        logger.debug(traceback.format_exc())
        return None


def quote(sym: str, rng: str = "5d", interval: str = "1d") -> dict | None:
    """
    現在値・前日終値・変化率を返す。

    返り値: {price, prev, change, change_pct, closes, timestamps, meta}
    取得できなければ None。
    """
    r = fetch_chart(sym, rng, interval)
    if not r:
        return None
    meta = r.get("meta") or {}
    try:
        raw = r["indicators"]["quote"][0]["close"]
        ts = r.get("timestamp") or []
        pairs = [(t, c) for t, c in zip(ts, raw) if c]
    except Exception:
        return None
    if len(pairs) < 2:
        return None

    cur = meta.get("regularMarketPrice") or pairs[-1][1]
    prev = previous_close(pairs, meta)
    if not prev or not cur:
        return None

    return {
        "symbol": sym,
        "price": float(cur),
        "prev": float(prev),
        "change": float(cur) - float(prev),
        "change_pct": (float(cur) - float(prev)) / float(prev) * 100,
        "closes": [c for _, c in pairs],
        "timestamps": [t for t, _ in pairs],
        "meta": meta,
    }


def previous_close(pairs: list, meta: dict) -> float | None:
    """
    「当日より前の最後の終値」を返す。

    pairs は (unixtime, 終値) の並び（古い順）。
    取引所の現地日付で比較するのが肝。UTCや日本時間で比べると、
    米国株では日付が1日ずれて前々日を拾ってしまう。
    """
    if not pairs:
        return None
    off = meta.get("gmtoffset")
    tz = timezone(timedelta(seconds=off)) if off is not None else timezone.utc
    mt = meta.get("regularMarketTime")
    today = (datetime.fromtimestamp(mt, tz).date() if mt
             else datetime.now(tz).date())
    for t, c in reversed(pairs):
        if datetime.fromtimestamp(t, tz).date() < today:
            return c
    # 当日より前の足が無い場合（データが1本しかない等）は最後から2本目で代用
    return pairs[-2][1] if len(pairs) >= 2 else None
