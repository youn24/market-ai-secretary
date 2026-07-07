"""
src/kabudragon.py — 株ドラゴン デイトレランキング取得
https://kabudragon.com/ranking/*.html （静的HTML・テーブル形式）から
デイトレーダー注目のランキングを毎日取得する。

取得ランキング:
  - 値上がり率（age）     : きょう勢いのある銘柄
  - ストップ高（stopdaka）: 買い殺到で値幅上限に張り付いた銘柄
  - 出来高急増（dekizou） : 普段より売買が急増＝資金が集まり始めた銘柄
  - 値下がり率（sage）    : 急落銘柄（逆張り・警戒の両面で参考）

データ行フォーマット（2026-07時点・11列）:
  順位 | コード | 名称 | 市場 | 日付 | 取引値 | 前日比 | 前日比% | 出来高 | 高値 | 安値
"""

import re
import time
import traceback
import requests

from src.utils import setup_logger

logger = setup_logger("kabudragon")

BASE_URL = "https://kabudragon.com/ranking/{key}.html"
HEADERS  = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# (key, 表示名, アイコン, やさしい説明)
RANKINGS = [
    ("age",      "値上がり率",  "🚀", "きょう一番上がった銘柄"),
    ("stopdaka", "ストップ高",  "🔥", "買いが殺到し値幅の上限まで上がった銘柄"),
    ("dekizou",  "出来高急増",  "👀", "普段より売買が急増＝注目が集まり始めた銘柄"),
    ("sage",     "値下がり率",  "📉", "きょう一番下がった銘柄（警戒・逆張りの参考）"),
]

TOP_N = 5  # 各ランキング上位何件を保持するか

_CODE_RE = re.compile(r"^\d{3}[0-9A-Z]$")  # 4桁コード（285A等の英字末尾にも対応）


def _plain_tds(tr_html: str) -> list[str]:
    """<tr>内の<td>をプレーンテキスト化して返す"""
    tds = re.findall(r"<td[^>]*>(.*?)</td>", tr_html, re.S)
    out = []
    for td in tds:
        t = re.sub(r"<[^>]+>", "", td)
        t = re.sub(r"&[a-z]+;", " ", t)
        out.append(re.sub(r"\s+", " ", t).strip())
    return out


def _parse_ranking(html: str) -> list[dict]:
    """ランキングページのHTMLから銘柄行を抽出"""
    items = []
    for tr in re.findall(r"<tr[^>]*>.*?</tr>", html, re.S):
        tds = _plain_tds(tr)
        if len(tds) < 9:
            continue
        if not tds[0].isdigit() or not _CODE_RE.match(tds[1]):
            continue

        # 前日比% の列を探す（通常 index 7 だがページ差に備え走査）
        pct = None
        pct_idx = None
        for i, t in enumerate(tds[5:], start=5):
            m = re.match(r"^[+\-±]?([\d.]+)%$", t.replace(",", ""))
            if m:
                pct = float(t.replace("%", "").replace("+", "").replace(",", "").replace("±", "0") or 0)
                if t.startswith("-"):
                    pct = -abs(pct)
                pct_idx = i
                break

        def _num(s):
            s = s.replace(",", "").replace("+", "")
            try:
                return float(s)
            except ValueError:
                return None

        price  = _num(tds[5]) if len(tds) > 5 else None
        volume = _num(tds[pct_idx + 1]) if (pct_idx is not None and len(tds) > pct_idx + 1) else None

        items.append({
            "rank":   int(tds[0]),
            "code":   tds[1],
            "name":   tds[2][:20],
            "market": tds[3],
            "price":  price,
            "chg_pct": pct,
            "volume": volume,
        })
        if len(items) >= TOP_N:
            break
    return items


def _fetch_ranking(key: str) -> list[dict]:
    try:
        r = requests.get(BASE_URL.format(key=key), headers=HEADERS, timeout=15)
        if r.status_code != 200:
            logger.warning(f"株ドラゴン {key}: status={r.status_code}")
            return []
        r.encoding = r.apparent_encoding
        return _parse_ranking(r.text)
    except Exception:
        logger.debug(traceback.format_exc())
        return []


def run(*_args, **_kwargs) -> dict:
    """
    株ドラゴンのランキングを取得。
    返り値: {available, rankings: {key: {label, icon, note, items}}, telegram_block}
    """
    result = {"available": False, "rankings": {}}
    try:
        got = 0
        for key, label, icon, note in RANKINGS:
            items = _fetch_ranking(key)
            result["rankings"][key] = {
                "label": label, "icon": icon, "note": note, "items": items,
            }
            if items:
                got += 1
            time.sleep(1.0)  # サイトへの負荷配慮

        if got == 0:
            logger.warning("株ドラゴン: 全ランキング取得失敗")
            return result

        result["available"] = True
        result["telegram_block"] = _build_telegram_block(result["rankings"])
        logger.info(f"✅ 株ドラゴン取得完了（{got}/{len(RANKINGS)}ランキング）")
        return result
    except Exception:
        logger.error("株ドラゴンエラー")
        logger.debug(traceback.format_exc())
        return result


def _build_telegram_block(rankings: dict) -> str:
    """通知②（詳細メッセージ）用のコンパクトなブロック"""
    lines = ["🐉 *株ドラゴン・デイトレ注目*"]

    def _top(key, n=3):
        return (rankings.get(key) or {}).get("items", [])[:n]

    ups = _top("age")
    if ups:
        s = " / ".join(f"{x['name']} {x['chg_pct']:+.1f}%" for x in ups if x.get("chg_pct") is not None)
        lines.append(f"🚀 値上がり: {s}")

    stops = _top("stopdaka", 3)
    if stops:
        s = " / ".join(x["name"] for x in stops)
        lines.append(f"🔥 S高: {s}")

    deki = _top("dekizou", 2)
    if deki:
        s = " / ".join(x["name"] for x in deki)
        lines.append(f"👀 出来高急増: {s}")

    downs = _top("sage", 2)
    if downs:
        s = " / ".join(f"{x['name']} {x['chg_pct']:+.1f}%" for x in downs if x.get("chg_pct") is not None)
        lines.append(f"📉 急落: {s}")

    return "\n".join(lines) if len(lines) > 1 else ""
