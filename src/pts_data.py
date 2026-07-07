"""
src/pts_data.py — PTS夜間取引で大きく動いた銘柄（株探）
https://kabutan.jp/warning/pts_night_price_increase / _decrease から
夜間PTS（16:30〜23:59）の急騰・急落銘柄を取得する。

夜間PTSは「昼間の取引終了後に出たニュース（決算・材料）への最初の反応」。
翌朝の寄り付きで同方向に動きやすく、ADR（米国夜間）の国内個別株版として
朝レポートの寄り付き先行ヒントになる。

データ行（12td・2026-07時点）:
  コード | 銘柄名 | 市場 | (ニュース欄) | 通常終値 | PTS株価 | 前日比 | 前日比% | % | PTS出来高 | PER | PBR/利回り
"""

import re
import time
import traceback
import requests

from src.utils import setup_logger

logger = setup_logger("pts_data")

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

PAGES = [
    ("up",   "https://kabutan.jp/warning/pts_night_price_increase", "🌙⬆️ PTS夜間 急騰", "#00ff87"),
    ("down", "https://kabutan.jp/warning/pts_night_price_decrease", "🌙⬇️ PTS夜間 急落", "#ff3d5a"),
]

TOP_N = 5
_CODE_RE = re.compile(r"^\d{3}[0-9A-Z]$")


def _plain_tds(tr_html: str) -> list[str]:
    tds = re.findall(r"<td[^>]*>(.*?)</td>", tr_html, re.S)
    out = []
    for td in tds:
        t = re.sub(r"<[^>]+>", "", td)
        t = t.replace("&nbsp;", " ").replace("&amp;", "&")
        out.append(re.sub(r"\s+", " ", t).strip())
    return out


def _num(s: str):
    s = (s or "").replace(",", "").replace("+", "").replace("%", "").strip()
    if s in ("", "－", "-", "―"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _parse_page(html: str) -> list[dict]:
    """
    PTSランキングページから銘柄行を抽出。
    行構造: <td>コード</td><th>銘柄名</th><td>市場</td><td icon/><td icon/>
            <td>通常終値</td><td>PTS株価</td><td>前日比</td><td>前日比% %</td><td>出来高</td>…
    """
    items = []
    for tr in re.findall(r"<tr[^>]*>.*?</tr>", html, re.S):
        tds = _plain_tds(tr)
        if len(tds) < 8 or not tds or not _CODE_RE.match(tds[0]):
            continue

        # 銘柄名は <th scope="row"> に入っている
        ths = re.findall(r"<th[^>]*>(.*?)</th>", tr, re.S)
        name = ""
        if ths:
            name = re.sub(r"<[^>]+>", "", ths[0])
            name = re.sub(r"\s+", " ", name).strip()[:14]

        code, market = tds[0], tds[1]
        # アイコン用の空セルを除いた数値列を順に拾う
        nums = [t for t in tds[2:] if t not in ("", "%")]
        # nums: [通常終値, PTS株価, 前日比, "±x.xx %", 出来高, PER, PBR, 利回り...]
        if len(nums) < 4:
            continue
        close_p = _num(nums[0])
        pts_p   = _num(nums[1])
        chg_pct = _num(nums[3])
        volume  = _num(nums[4]) if len(nums) > 4 else None
        if chg_pct is None or pts_p is None or not name:
            continue
        if nums[3].lstrip().startswith("-"):
            chg_pct = -abs(chg_pct)

        items.append({
            "code": code, "name": name, "market": market,
            "close_price": close_p, "pts_price": pts_p,
            "chg_pct": chg_pct, "volume": volume,
        })
        if len(items) >= TOP_N:
            break
    return items


def run(*_args, **_kwargs) -> dict:
    """
    PTS夜間の急騰・急落銘柄を取得。
    返り値: {available, up: [...], down: [...], telegram_block}
    """
    result = {"available": False, "up": [], "down": []}
    try:
        for key, url, _label, _color in PAGES:
            try:
                r = requests.get(url, headers=HEADERS, timeout=15)
                if r.status_code == 200:
                    result[key] = _parse_page(r.text)
            except Exception:
                logger.debug(traceback.format_exc())
            time.sleep(1.0)  # サイトへの負荷配慮

        if not result["up"] and not result["down"]:
            logger.warning("PTS: データ取得できず")
            return result

        result["available"] = True
        result["telegram_block"] = _build_telegram_block(result)
        logger.info(f"✅ PTS取得完了（急騰{len(result['up'])}件・急落{len(result['down'])}件）")
        return result
    except Exception:
        logger.error("PTSエラー")
        logger.debug(traceback.format_exc())
        return result


def _build_telegram_block(res: dict) -> str:
    """通知②（詳細メッセージ）用のコンパクトなブロック"""
    lines = ["🌙 *PTS夜間で大きく動いた銘柄*"]
    ups = res.get("up", [])[:3]
    if ups:
        s = " / ".join(f"{x['name']} {x['chg_pct']:+.1f}%" for x in ups)
        lines.append(f"⬆️ 急騰: {s}")
    downs = res.get("down", [])[:3]
    if downs:
        s = " / ".join(f"{x['name']} {x['chg_pct']:+.1f}%" for x in downs)
        lines.append(f"⬇️ 急落: {s}")
    if len(lines) > 1:
        lines.append("（夜間の材料反応 → 寄り付きで同方向に動きやすい）")
        return "\n".join(lines)
    return ""
