"""
株探・株価注意報（Step KW）— 信用の偏り・年初来更新・日経寄与度を取る

なぜ必要か:
  既存の株ドラゴン(kabudragon.py)は「今日どれだけ動いたか」の順位を扱う。
  こちらは値動きの結果ではなく、その裏側にある需給を見る。
    ・信用残がどちらに偏っているか（買い方が溜まれば戻り売り圧力になる）
    ・年初来の高値/安値を更新したか（節目を抜けたかどうか）
    ・日経を動かしたのはどの銘柄か（指数の変動理由の特定）
  値動きの順位だけでは「なぜそうなったか」が分からないため、両方を見る。

重複を避けるための整理:
  ストップ高・値上がり率・出来高急増は株ドラゴン側が担当しているので取らない。
  同じ内容を二重に通知すると読み飛ばされるようになる。

信用倍率の読み方:
  信用倍率 = 買い残 ÷ 売り残。
  高い（例: 10倍超）ほど買い方に偏っており、上値では戻り売りが出やすい。
  低い（1倍未満）と売り方が多く、上昇時に踏み上げが起きやすい。
  極端な値そのものより「前週からどれだけ動いたか」が転機の手がかりになる。

run() → 各カテゴリのランキング
"""
import re
import ssl
import traceback
import urllib.request
from datetime import datetime

from src.utils import setup_logger, get_jst_now

logger = setup_logger("kabutan_warning")

_BASE = "https://kabutan.jp/warning/?mode={mode}"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# 取得するカテゴリ。株ドラゴンと重複しないものだけを選んである。
# (mode, 表示名, 意味, 何件まで)
_CATEGORIES = [
    ("3_3", "年初来高値を更新", "節目を上抜けた銘柄。上昇が続きやすい形", 8),
    ("3_4", "年初来安値を更新", "節目を下抜けた銘柄。下落が続きやすい形", 8),
    ("3_2", "ストップ安",       "売り殺到で値幅下限に張り付いた銘柄", 6),
    ("7_2", "信用買い残の増加", "買い方が増加。上値では戻り売り圧力になりやすい", 8),
    ("7_1", "信用売り残の増加", "売り方が増加。上昇時に踏み上げが起きやすい", 8),
    ("8_1", "日経平均への寄与", "指数を動かした主因の銘柄", 8),
]

# 信用倍率がこの値を超えたら「買い方に大きく偏っている」とみなす。
# 一般に10倍超は買い長とされ、需給の重さとして意識される水準。
_RATIO_HEAVY = 10.0
# 1倍未満は売り残のほうが多い状態＝踏み上げ余地
_RATIO_SHORT = 1.0


def _get(url: str) -> str | None:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        req = urllib.request.Request(url, headers=_HEADERS)
        return urllib.request.urlopen(req, context=ctx, timeout=25).read().decode(
            "utf-8", errors="replace")
    except Exception:
        logger.error(f"取得できませんでした: {url}", exc_info=True)
        return None


def _cells(row_html: str) -> list:
    """1行ぶんのセルを、タグを剥がした文字列で返す。"""
    return [re.sub(r"\s+", " ", re.sub(r"<.*?>", "", c)).replace(" ", "").strip()
            for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.S)]


def _num(s: str) -> float | None:
    """「+7,367,700」「-2.61%」などを数値にする。"""
    if not s:
        return None
    t = re.sub(r"[,%＋+\s]", "", s).replace("－", "").replace("−", "-")
    if t in ("", "-", "---"):
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _parse(html: str, limit: int) -> list:
    """
    注意報ページの表を読む。

    列の並びは概ね
      コード | 銘柄名 | 市場 | (空) | (空) | 株価 | (空) | 前日比 | 前日比% | 以降はカテゴリ別
    ヘッダ行の見出しは列数と一致しないことがあるため、
    見出しに頼らず「先頭がコード（4桁または英数4桁）の行」だけを拾う。
    """
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        c = _cells(tr)
        if len(c) < 9 or not re.match(r"^[0-9A-Z]{4}$", c[0]):
            continue
        rows.append({
            "code": c[0], "name": c[1], "market": c[2],
            "price": _num(c[5]),
            "change": _num(c[7]),
            "change_pct": _num(c[8]),
            "extra": c[9:],          # カテゴリ固有の列（出来高・信用倍率など）
        })
        if len(rows) >= limit:
            break
    return rows


def _enrich_margin(rows: list) -> list:
    """
    信用系のカテゴリに、倍率の読み方を添える。
    数字だけ出しても「10倍」が重いのか軽いのか初心者には分からない。
    列の並び: 出来高 | 信用倍率 | 買い残(または売り残) | 対前週増加幅
    """
    for r in rows:
        ex = r.get("extra") or []
        ratio = _num(ex[1]) if len(ex) > 1 else None
        r["margin_ratio"] = ratio
        r["balance"] = _num(ex[2]) if len(ex) > 2 else None
        r["weekly_change"] = _num(ex[3]) if len(ex) > 3 else None
        if ratio is None:
            r["margin_note"] = ""
        elif ratio >= _RATIO_HEAVY:
            r["margin_note"] = f"買い方に大きく偏り（{ratio:.1f}倍）。上値は重くなりやすい"
        elif ratio < _RATIO_SHORT:
            r["margin_note"] = f"売り方が多い（{ratio:.2f}倍）。上昇時は踏み上げに注意"
        else:
            r["margin_note"] = f"信用倍率 {ratio:.1f}倍"
    return rows


def run(*_args, **_kwargs) -> dict:
    logger.info("=== 株探・株価注意報 ===")
    out = {}
    for mode, label, meaning, limit in _CATEGORIES:
        html = _get(_BASE.format(mode=mode))
        if not html:
            continue
        rows = _parse(html, limit)
        if not rows:
            logger.info(f"該当なし: {label}")
            continue
        if mode.startswith("7_"):
            rows = _enrich_margin(rows)
        out[label] = {"meaning": meaning, "rows": rows}
        logger.info(f"{label}: {len(rows)}件")

    if not out:
        return {"available": False}

    return {
        "available": True,
        "fetched_at": get_jst_now().strftime("%Y-%m-%d %H:%M"),
        "categories": out,
        "highlights": _highlights(out),
    }


def _highlights(cats: dict) -> list:
    """
    全体から「これは押さえておきたい」ものだけを拾う。
    ランキングを全部読ませるのは負担なので、目を引く事実だけ文章にする。
    """
    out = []

    hi = (cats.get("年初来高値を更新") or {}).get("rows") or []
    lo = (cats.get("年初来安値を更新") or {}).get("rows") or []
    if hi and lo:
        if len(hi) >= len(lo) * 3:
            out.append(f"年初来高値の更新が{len(hi)}件と、安値更新（{len(lo)}件）を大きく上回っています。")
        elif len(lo) >= len(hi) * 3:
            out.append(f"年初来安値の更新が{len(lo)}件と、高値更新（{len(hi)}件）を大きく上回っています。"
                       f"下値を切り下げる銘柄が増えています。")

    sa = (cats.get("ストップ安") or {}).get("rows") or []
    if len(sa) >= 3:
        out.append(f"ストップ安が{len(sa)}件出ています。個別の材料か、地合いの悪化かの見極めが要ります。")

    heavy = [r for r in ((cats.get("信用買い残の増加") or {}).get("rows") or [])
             if (r.get("margin_ratio") or 0) >= _RATIO_HEAVY]
    if heavy:
        names = "・".join(r["name"] for r in heavy[:3])
        out.append(f"{names} は信用買いが大きく積み上がっています（10倍超）。"
                   f"戻り売りが出やすく、上値が重くなりがちです。")

    short = [r for r in ((cats.get("信用売り残の増加") or {}).get("rows") or [])
             if (r.get("margin_ratio") is not None
                 and r["margin_ratio"] < _RATIO_SHORT)]
    if short:
        names = "・".join(r["name"] for r in short[:3])
        out.append(f"{names} は売り残が買い残を上回っています。"
                   f"上昇に転じると踏み上げで急騰することがあります。")

    return out


def build_block(data: dict, max_cat: int = 4) -> str:
    """通知・レポートに差し込む文字列。"""
    if not data.get("available"):
        return ""
    lines = ["📋 *株価注意報（株探）*", ""]
    if data.get("highlights"):
        lines.append("📖 *注目点*")
        for h in data["highlights"]:
            lines.append(f"　・{h}")
        lines.append("")

    for label, c in list(data["categories"].items())[:max_cat]:
        rows = c["rows"][:5]
        if not rows:
            continue
        lines.append(f"*{label}*　{c['meaning']}")
        for r in rows:
            pct = r.get("change_pct")
            p = f"{pct:+.2f}%" if pct is not None else "—"
            note = f"　{r['margin_note']}" if r.get("margin_note") else ""
            lines.append(f"　{r['name']}({r['code']}) {p}{note}")
        lines.append("")
    return "\n".join(lines).strip()


if __name__ == "__main__":
    import io, sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    r = run()
    if not r.get("available"):
        print("取得できませんでした")
        raise SystemExit
    print(build_block(r, max_cat=6))
