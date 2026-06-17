"""
ザラバ中の急変銘柄ウォッチャー（リアルタイム強化）
15分ごとのmonitor実行時に、ウォッチリスト銘柄で大きく動いた銘柄を検知し、
関連ニュースを集めて「なぜ動いたか」をGeminiが推定して通知する。

仕組み：
  - ウォッチリスト銘柄の当日変化率を取得（fetch_prices と同じYahoo直接API）
  - 閾値（既定±3%）を超えた銘柄を「mover」として抽出
  - 各moverの関連ニュースをGoogle News RSSで検索
  - Geminiが値動きの理由を1〜2行で推定

⚠️ 理由は推定であり断定ではない。同じ銘柄を繰り返し通知しないよう、
   当日すでに通知した銘柄は記録して二重通知を避ける。
"""
import os
import json
import time
from datetime import timedelta, timezone

import requests

from src.utils import setup_logger, get_jst_now, get_dirs, BASE_DIR

logger = setup_logger("intraday_movers")

JST = timezone(timedelta(hours=9))
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

MOVE_THRESHOLD = 3.0   # この%以上動いたら急変とみなす


def _load_watchlist():
    path = BASE_DIR / "data" / "watchlist.json"
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for s in data.get("stocks", []):
            if s.get("symbol"):
                out.append((s["symbol"], s.get("name", s["symbol"])))
    except Exception as e:
        logger.warning(f"watchlist読み込み失敗: {e}")
    return out


def _fetch_change(symbol: str) -> float | None:
    """当日変化率(%)をYahoo直接APIで取得"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=2d"
    try:
        r = requests.get(url, headers=_HEADERS, timeout=12)
        r.raise_for_status()
        res = r.json()["chart"]["result"][0]
        meta = res.get("meta", {})
        cur = meta.get("regularMarketPrice")
        prev = meta.get("chartPreviousClose") or meta.get("previousClose")
        if cur and prev:
            return round((cur - prev) / prev * 100, 2)
    except Exception:
        pass
    return None


def _is_market_hours(now=None) -> bool:
    """日本株のザラバ中か（平日9:00-15:30 JST）"""
    now = now or get_jst_now()
    if now.weekday() >= 5:
        return False
    t = now.hour * 60 + now.minute
    return 9 * 60 <= t <= 15 * 60 + 30


# ── 通知済み記録（当日・二重通知防止） ──────────────────────────
def _seen_path():
    return get_dirs()["data_raw"] / f"{get_jst_now().strftime('%Y%m%d')}_intraday_seen.json"


def _load_seen() -> dict:
    p = _seen_path()
    if p.exists():
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_seen(seen: dict):
    try:
        json.dump(seen, open(_seen_path(), "w", encoding="utf-8"), ensure_ascii=False)
    except Exception as e:
        logger.warning(f"seen保存失敗: {e}")


def _fetch_related_news(name: str, max_items: int = 4) -> list[str]:
    """銘柄名でGoogle Newsを検索して最新見出しを取得"""
    import feedparser
    from urllib.parse import quote
    q = quote(f"{name} 株 OR 決算 OR 業績")
    url = f"https://news.google.com/rss/search?q={q}&hl=ja&gl=JP&ceid=JP:ja"
    try:
        feed = feedparser.parse(url)
        return [e.get("title", "") for e in feed.entries[:max_items] if e.get("title")]
    except Exception:
        return []


def _explain_move(name: str, chg: float, headlines: list[str]) -> str:
    """Geminiが値動きの理由を推定"""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    direction = "急騰" if chg > 0 else "急落"
    if not api_key:
        # フォールバック：最新見出しを根拠として返す
        return f"関連ニュース: {headlines[0]}" if headlines else "材料は調査中"
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        news_txt = "\n".join(f"・{h}" for h in headlines) or "（関連ニュース取得できず）"
        prompt = f"""銘柄「{name}」が本日{abs(chg):.1f}%{direction}しています。
以下の最新ニュース見出しを参考に、なぜ動いた可能性が高いかを初心者向けに1〜2行で推定してください。
ニュースに直接の理由がなければ「明確な材料は見当たらず、地合いや需給の影響か」と正直に書いてください。
断定せず「〜の可能性」と表現してください。

【最新ニュース】
{news_txt}

推定（1〜2行）:"""
        return model.generate_content(prompt).text.strip()
    except Exception as e:
        logger.warning(f"理由推定失敗 [{name}]: {e}")
        return f"関連ニュース: {headlines[0]}" if headlines else "材料は調査中"


def run(force: bool = False) -> dict:
    """ザラバ中の急変銘柄を検知して理由を推定。monitorから呼ばれる。"""
    now = get_jst_now()
    if not force and not _is_market_hours(now):
        return {"available": False, "reason": "ザラバ時間外"}

    seen = _load_seen()
    movers = []
    for symbol, name in _load_watchlist():
        chg = _fetch_change(symbol)
        if chg is None or abs(chg) < MOVE_THRESHOLD:
            continue
        code = symbol.split(".")[0]
        # 当日すでに同方向で通知済みならスキップ（さらに大きく動いたら再通知）
        prev = seen.get(code)
        if prev is not None and abs(chg) < abs(prev) + 2.0:
            continue
        headlines = _fetch_related_news(name)
        reason = _explain_move(name, chg, headlines)
        movers.append({
            "code": code, "name": name, "change": chg,
            "reason": reason, "headline": headlines[0] if headlines else "",
        })
        seen[code] = chg
        time.sleep(0.5)

    _save_seen(seen)

    if not movers:
        return {"available": False, "reason": "急変銘柄なし"}

    # 値動きの大きい順
    movers.sort(key=lambda x: abs(x["change"]), reverse=True)
    result = {"available": True, "movers": movers, "count": len(movers),
              "time": now.strftime("%H:%M")}
    result["telegram_message"] = build_telegram_message(result)
    logger.info(f"✅ ザラバ急変: {len(movers)}銘柄検知")
    return result


def build_telegram_message(result: dict) -> str:
    if not result.get("available"):
        return ""
    lines = [f"⚡ *ザラバ急変アラート（{result['time']}）*", ""]
    for m in result["movers"]:
        arrow = "🚀" if m["change"] > 0 else "🔻"
        lines.append(f"{arrow} *[{m['code']}] {m['name']}*  {m['change']:+.1f}%")
        lines.append(f"　{m['reason']}")
        lines.append("")
    lines.append("※理由はAIによる推定です")
    return "\n".join(lines).strip()


if __name__ == "__main__":
    r = run(force=True)   # テスト時は時間外でも実行
    out = []
    if r.get("available"):
        out.append(f"=== ザラバ急変 {r['count']}銘柄（{r['time']}）===")
        for m in r["movers"]:
            out.append(f"{'🚀' if m['change']>0 else '🔻'} [{m['code']}] {m['name']} {m['change']:+.1f}%")
            out.append(f"   理由推定: {m['reason']}")
            out.append("")
    else:
        out.append(f"急変なし: {r.get('reason','')}")
    text = "\n".join(out)
    try:
        print(text)
    except UnicodeEncodeError:
        with open("im_output.txt", "w", encoding="utf-8") as f:
            f.write(text)
        print("im_output.txt に保存しました")
