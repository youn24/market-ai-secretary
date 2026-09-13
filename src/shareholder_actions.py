"""
株主還元とM&A・TOB（Step SH2）— 株価が跳ねる「事実」を全上場企業から拾う

なぜ必要か:
  TOBの発表は株価が買付価格まで一気に跳ぶ。決算のように予想の話ではなく、
  値段がほぼ決まる**事実**なので、知るのが早いほど意味がある。
  自社株買いと増配も、需給と配当の両面で直接効く。

  既存の `tdnet_watcher` はこれらを検出できるが**ウォッチリスト26銘柄限定**で、
  `catalyst_analyzer` 経由の市場全体版はGeminiを使う。
  TOBは4,000社のどこで出るか分からないうえ、Geminiの枠が尽きた日でも
  知りたい情報なので、**全上場企業を対象にルールベースで**拾う。

⚠️ 素朴なキーワード判定は逆の意味になる。2026-08-27の実データで確認した罠:

  1. **「無配」が「配当」に引っかかる**
     「期末配当予想の修正（無配）及び株主優待制度の廃止」を
     増配として拾うと、最悪の知らせを朗報として届けることになる。

  2. **株式報酬の自己株式取得は買い戻しではない**
     「業績連動型株式報酬制度の終了に伴う自己株式の**無償**取得及び消却」は
     現金を使わず需給にも効かない。本物の買い戻しと混ぜてはいけない。

  3. **TOBは「する側」と「される側」で意味がまるで違う**
     される側（対象）は買付価格まで跳ぶ。する側は資金流出でむしろ下げることもある。
     「株式会社カカクコム（証券コード：2371）の株券等に対する公開買付け」を
     コード2371が開示していれば、それは**される側**。

Gemini は使わない。事実の分類であって解釈ではないうえ、
枠が尽きた日にこそ知りたい情報だからである。
"""
import json
import re
import traceback
from datetime import timedelta

from src.utils import setup_logger, get_jst_now, BASE_DIR

logger = setup_logger("shareholder_actions")

_STATE = BASE_DIR / "data" / "shareholder_state.json"

# ── 除外する言い回し ────────────────────────────────
# 「配当」「自己株式取得」に一致しても、意味が逆または影響が無いもの。
_NEGATIVE_DIV = re.compile(r"無配|減配|配当.{0,6}(見送り|取りやめ|中止)|優待.{0,4}(廃止|中止)")
_NOT_BUYBACK = re.compile(r"無償取得|株式報酬|譲渡制限付|ストック・?オプション|"
                          r"取得.{0,6}(終了|完了)のお知らせ")

# ── 分類 ────────────────────────────────────────
# (キー, 絵文字, 見出し, 重み)。重みは通知の並び順に使う。
#  TOBされる側が最上位なのは、株価が買付価格へ跳ぶ＝最も行動が変わるため。
_KINDS = [
    ("tob_target",  "🎯", "TOBの対象になりました",   100),
    ("mbo",         "🏛", "MBO・非公開化",           90),
    ("delisting",   "⚠️", "上場廃止が決まりました",   85),
    ("buyback",     "💰", "自社株買い",              70),
    ("dividend_up", "🎁", "増配・復配・特別配当",     60),
    ("tob_bidder",  "🤝", "TOBを実施（買う側）",      50),
    ("ma",          "🤝", "M&A・子会社化",           45),
    ("benefit_up",  "🎫", "株主優待の新設・拡充",     30),
    # 逆のニュースも拾う。良い話だけ集めると判断を誤る。
    ("dividend_cut", "📉", "減配・無配・優待廃止",    80),
]
_ORDER = {k: w for k, _, _, w in _KINDS}
_LABEL = {k: (e, t) for k, e, t, _ in _KINDS}


def _classify(code: str, title: str) -> str | None:
    """開示1件を分類する。該当しなければ None。"""
    t = title

    # ① 悪い知らせを先に判定する。
    #    後回しにすると「無配」が「配当」の枝に吸われて朗報になる。
    if _NEGATIVE_DIV.search(t):
        return "dividend_cut"

    # ② TOB。する側とされる側を分ける
    if re.search(r"公開買付|TOB", t):
        # 「当社株式に対する」「当社株券等に対する」= 明確に対象
        if re.search(r"当社(株式|株券等).{0,10}に対する", t):
            return "tob_target"
        # 「（証券コード：1234）の株券等に対する」に自分のコードが入る＝対象
        m = re.search(r"証券コード[：:]\s*([0-9A-Z]{4})", t)
        if m and m.group(1) == (code or "")[:4]:
            return "tob_target"
        # 意見表明・応募推奨は対象側が出すもの
        if re.search(r"意見表明|応募.{0,4}推奨|賛同", t):
            return "tob_target"
        return "tob_bidder"

    if re.search(r"MBO|マネジメント・?バイアウト|非公開化", t):
        return "mbo"
    if re.search(r"上場廃止", t):
        return "delisting"

    # ③ 自社株買い。株式報酬まわりは需給に効かないので除く
    if re.search(r"自己株式.{0,6}取得|自社株買", t) and not _NOT_BUYBACK.search(t):
        return "buyback"

    # ④ 配当。ここに来る時点で否定形は①で除かれている
    if re.search(r"増配|復配|特別配当|記念配当", t):
        return "dividend_up"
    if re.search(r"配当予想の修正|剰余金の配当", t):
        return "dividend_up"

    if re.search(r"株主優待.{0,8}(新設|拡充|導入|変更)", t):
        return "benefit_up"

    if re.search(r"子会社化|株式取得|経営統合|合併|資本業務提携|買収", t):
        return "ma"
    return None


def _amount(title: str) -> str:
    """タイトルから規模を拾えたら返す（自社株買いの「〇億円」など）。"""
    m = re.search(r"([0-9,]+(?:\.[0-9]+)?)\s*(億円|百万円|万株|株)", title)
    return f"{m.group(1)}{m.group(2)}" if m else ""


def _session_key(now=None) -> str:
    now = now or get_jst_now()
    return (now - timedelta(hours=6)).strftime("%Y-%m-%d")


def run(date_str: str = None, limit: int = 8) -> dict:
    """
    前営業日のTDnet全開示から、株主還元とM&A・TOBを抽出する。

    ウォッチリストで絞らない。TOBは4,000社のどこで出るか分からず、
    26銘柄だけ見ていてはまず当たらないため。
    """
    out = {"available": False}
    try:
        from src.tdnet_watcher import _fetch_date, _prev_business_day
        now = get_jst_now()
        ds = date_str or _prev_business_day(now).strftime("%Y%m%d")
        items = _fetch_date(ds)
        if not items:
            logger.info(f"開示を取得できませんでした（{ds}）")
            return out

        hits = {}
        for it in items:
            code = (it.get("code") or "")[:4]
            title = it.get("title") or ""
            kind = _classify(code, title)
            if not kind:
                continue
            rec = {
                "code": code, "name": it.get("name", ""), "kind": kind,
                "emoji": _LABEL[kind][0], "label": _LABEL[kind][1],
                "title": title[:90], "time": it.get("time", ""),
                "pdf": it.get("pdf", ""), "amount": _amount(title),
                "weight": _ORDER[kind],
            }
            # 同じ銘柄で複数出たら、重い方だけ残す
            prev = hits.get(code)
            if prev is None or rec["weight"] > prev["weight"]:
                hits[code] = rec

        rows = sorted(hits.values(), key=lambda x: -x["weight"])
        if not rows:
            logger.info(f"該当なし（{ds}・全{len(items)}件を確認）")
            return {"available": False, "date": ds, "scanned": len(items)}

        by_kind = {}
        for r in rows:
            by_kind.setdefault(r["kind"], []).append(r)

        logger.info(f"✅ 株主還元・M&A: {len(rows)}件"
                    f"（全{len(items)}件から抽出・{ds}）"
                    + (f" TOB対象{len(by_kind.get('tob_target', []))}件"
                       if by_kind.get("tob_target") else ""))
        return {"available": True, "date": ds, "scanned": len(items),
                "count": len(rows), "rows": rows[:limit], "all": rows,
                "by_kind": by_kind}
    except Exception:
        logger.error("株主還元・M&Aの抽出に失敗", exc_info=True)
        return out


def notify_lines(result: dict, max_lines: int = 3) -> list:
    """
    Telegram通知に載せる行。

    ⚠️ 毎日出る自社株買い・配当まで並べると読み飛ばされる。
       **TOB対象・MBO・上場廃止・減配**という「株価が動くことが
       ほぼ確実な事実」だけを通知に出し、残りはレポートへ送る。
    """
    if not result.get("available"):
        return []
    urgent = {"tob_target", "mbo", "delisting", "dividend_cut"}
    lines = []
    for r in result.get("all", []):
        # ⚠️ r["kind"] と書くと、キーが1つ欠けただけで KeyError になり
        #    **その日の株主還元が丸ごと消える**。呼び出し側の try で
        #    通知自体は守られるが、材料は届かないまま静かに落ちる。
        #    ここは .get() で受けて、欠けている行だけを飛ばす。
        if not isinstance(r, dict) or r.get("kind") not in urgent:
            continue
        name = r.get("name") or r.get("code") or ""
        if not name:
            continue
        code = f"（{r['code']}）" if r.get("code") else ""
        lines.append(f"{r.get('emoji', '📌')} *{r.get('label', '')}*: {name}{code}")
        if len(lines) >= max_lines:
            break
    return lines


def _seen() -> set:
    try:
        d = json.loads(_STATE.read_text(encoding="utf-8"))
        return set(d.get("codes", [])) if d.get("session") == _session_key() else set()
    except Exception:
        return set()


def mark_seen(codes) -> None:
    """同じ開示を翌日も通知しないための記録。"""
    try:
        _STATE.parent.mkdir(parents=True, exist_ok=True)
        _STATE.write_text(json.dumps(
            {"session": _session_key(), "codes": sorted(set(_seen()) | set(codes))},
            ensure_ascii=False), encoding="utf-8")
    except Exception:
        logger.debug(traceback.format_exc())


if __name__ == "__main__":
    import io
    import sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace")
    r = run()
    if not r.get("available"):
        print(f"該当なし（{r.get('scanned', 0)}件を確認）")
    else:
        print(f"■ {r['date']} の株主還元・M&A  "
              f"（全{r['scanned']}件から{r['count']}件）")
        print("-" * 62)
        for k, _, label, _w in _KINDS:
            rows = (r.get("by_kind") or {}).get(k) or []
            if not rows:
                continue
            print(f"\n{_LABEL[k][0]} {label}  {len(rows)}件")
            for x in rows[:4]:
                amt = f"  [{x['amount']}]" if x["amount"] else ""
                print(f"   [{x['code']}] {x['name'][:14]:14}{amt}")
                print(f"        {x['title'][:64]}")
        print("\n■ 通知に出す行（緊急のものだけ）")
        for l in notify_lines(r) or ["   （なし）"]:
            print("  ", l)
