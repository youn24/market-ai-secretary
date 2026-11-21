"""
iPhoneウィジェット用の配信ファイル docs/widget_feed.json を作る（Gemini不使用・通知なし）

なぜ別ファイルか:
  ウィジェットが端末から直接Yahooを叩くと、取得制限・端末ごとの失敗・電池消費の影響を受ける。
  Actionsで数時間ごとに1回だけ取得してGitHub Pagesに置き、端末は静的ファイルを読むだけにする。
  GitHub Actions / Pages は公開リポジトリなら無料。

形式は iOS 側の `Snapshot`（Codable・iso8601）と一致させてある。変えるなら両方直すこと。

失敗の扱い:
  ・1銘柄も取れなければ exit 1（古いファイルを新しく見せない・Actionsを赤にする）
  ・一部だけ失敗した銘柄は前回の値を引き継ぎ、その銘柄の `updated` は前回のまま
    （取得時刻を偽らない。アプリ側が古さを判断できる）

python -m scripts.build_widget_feed
"""
import json
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
from src.quote_util import quote  # noqa: E402  前日終値の求め方は必ずここを通す

OUT = BASE / "docs" / "widget_feed.json"

# 先頭の銘柄がウィジェットの主役。iOS側 Watchlist.defaults と同じ並び
WATCH = [
    ("^N225", "日経225"), ("USDJPY=X", "ドル円"), ("^GSPC", "S&P500"),
    ("^IXIC", "ナスダック"), ("^VIX", "VIX"),
]
NEWS_Q = "日経平均 OR 株価 OR 為替 OR 米国株 when:1d"
NEWS_N = 8


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def downsample(p: list, n: int = 60) -> list:
    if len(p) <= n:
        return p
    step = (len(p) - 1) / (n - 1)
    return [p[round(i * step)] for i in range(n)]


def fetch_news() -> list:
    url = ("https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": NEWS_Q, "hl": "ja", "gl": "JP", "ceid": "JP:ja"}))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    root = ET.fromstring(urllib.request.urlopen(req, timeout=20).read())
    items, seen = [], set()
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        src = (it.findtext("source") or "").strip()
        if not title or not link:
            continue
        # 末尾の「 - 配信元」は配信元と一致したときだけ落とす（題名の一部を削らない）
        if src and title.endswith(f" - {src}"):
            title = title[: -(len(src) + 3)]
        if title in seen:
            continue
        seen.add(title)
        try:
            d = iso(parsedate_to_datetime(it.findtext("pubDate")))
        except Exception:
            d = None
        items.append({"title": title, "source": src, "date": d, "url": link})
    items.sort(key=lambda x: x["date"] or "", reverse=True)
    return items[:NEWS_N]


def main() -> int:
    prev = {}
    try:
        old = json.loads(OUT.read_text(encoding="utf-8"))
        prev = {q["symbol"]: q for q in old.get("quotes", [])}
        old_news = old.get("news", [])
    except Exception:
        old_news = []

    now = iso(datetime.now(timezone.utc))
    quotes, fresh = [], 0
    for sym, name in WATCH:
        q = None
        try:
            q = quote(sym, "1d", "5m")   # range=1d だけが chartPreviousClose＝前日終値
        except Exception as e:
            print(f"::warning::{sym}: {type(e).__name__}: {e}")
        if q:
            fresh += 1
            quotes.append({"symbol": sym, "name": name, "price": q["price"],
                           "prevClose": q["prev"], "points": downsample(q["closes"]),
                           "updated": now})
        elif sym in prev:
            print(f"::warning::{sym}: 取得失敗。前回の値を引き継ぎ（updated は前回のまま）")
            quotes.append(prev[sym])
        else:
            print(f"::warning::{sym}: 取得失敗（前回の値も無いので除外）")

    if fresh == 0:
        print("::error::価格を1銘柄も取得できませんでした。ファイルを更新しません")
        return 1

    try:
        news = fetch_news() or old_news
    except Exception as e:
        print(f"::warning::ニュース取得失敗 {type(e).__name__}: {e}（前回分を使用）")
        news = old_news

    OUT.write_text(json.dumps({"quotes": quotes, "news": news, "fetched": now},
                              ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"✅ {OUT.name}: 価格{fresh}/{len(WATCH)}件更新 ニュース{len(news)}件 {OUT.stat().st_size}B")
    return 0


if __name__ == "__main__":
    sys.exit(main())
