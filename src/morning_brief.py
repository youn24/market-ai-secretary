"""
朝の3分ブリーフ（Step MB）— 起きて最初に見る一枚

なぜ必要か:
  レポートには30以上の区画があり、全部見るのは現実的でない。
  一方で「今日が普通の日か、特別な日か」の判断に本当に必要なのは
  ごく少数の数字だけである。それを最初の一枚にまとめる。

  優先順位は、この順に「行動が変わるか」で決めた。
    ① 寄り付きがどうなるか   … 今日いちばん先に知りたいこと
    ② 世界が怖がっているか   … VIXと円。2つ揃って初めて意味を持つ
    ③ 夜のうちに何が起きたか … 通知を見逃していても分かるように
    ④ 今日の予定           … 身構えるべき時間があるか

  「たくさん載せる」ことより「これだけ見れば済む」ことを優先する。
  詳細を知りたくなったら本編レポートへ進めばよい。

run() → ブリーフのデータ / build_message() → Telegram用
"""
import traceback
from datetime import datetime, timedelta

from src.utils import setup_logger, get_jst_now

logger = setup_logger("morning_brief")

# 寄り付きの乖離をどう言い表すか（円）。日経の1日の値幅を踏まえた区分。
_GAP_BANDS = [
    (200,  "ほぼ変わらず", "落ち着いて見ていて大丈夫です"),
    (500,  "やや動いた",   "普通の範囲です"),
    (1000, "大きめ",       "何か材料が出ています。注意して見てください"),
    (10**9, "非常に大きい", "大きな変化です。無理に動かない方が無難です"),
]

# VIXの水準。20未満は平常、25超で警戒というのが一般的な目安。
_VIX_CALM, _VIX_ALERT = 20.0, 25.0


def _band(diff_yen: float) -> tuple:
    a = abs(diff_yen)
    for limit, label, advice in _GAP_BANDS:
        if a < limit:
            return label, advice
    return _GAP_BANDS[-1][1], _GAP_BANDS[-1][2]


def _nikkei_outlook() -> dict:
    """
    ①寄り付きの見当。日経先物と東京終値の差を出す。
    この1つだけで「今日どう始まるか」がほぼ分かるので最優先で置く。
    """
    out = {"available": False}
    try:
        from src.fetch_prices import _fetch_nikkei_official_csv
        from src.quote_util import quote

        nk = _fetch_nikkei_official_csv("nikkei_stock_average_daily_jp.csv") or {}
        cash = nk.get("latest")
        # 先物は2契約から取り、片方が欠けても止まらないようにする
        fut = None
        for sym in ("NKD=F", "NIY=F"):
            q = quote(sym, rng="5d")
            if q:
                fut = q["price"]
                break
        if not cash or not fut:
            return out

        diff = fut - cash
        label, advice = _band(diff)
        return {
            "available": True,
            "cash": cash, "cash_chg": nk.get("change_pct"),
            "future": fut,
            "diff_yen": round(diff), "diff_pct": round(diff / cash * 100, 2),
            "band": label, "advice": advice,
        }
    except Exception:
        logger.error("寄り付きの見当を出せませんでした", exc_info=True)
        return out


def _risk_temp() -> dict:
    """
    ②世界が怖がっているか。VIXとドル円を組で見る。

    片方だけでは判断できない。VIXが上がっても円安なら
    「株の話」で済むが、VIXが上がって同時に円高なら本物の逃避になる。
    この2つを必ずセットで出すのはそのため。
    """
    out = {"available": False}
    try:
        from src.quote_util import quote
        v = quote("^VIX", rng="5d")
        f = quote("USDJPY=X", rng="5d")
        if not v or not f:
            return out

        vix, vix_chg = v["price"], v["change_pct"]
        fx, fx_chg = f["price"], f["change_pct"]
        yen_strong = fx_chg < -0.3        # 円高＝逃避の目印

        if vix >= _VIX_ALERT and yen_strong:
            level, msg = "警戒", "恐怖指数が高く、同時に円高。本物のリスク回避が出ています"
        elif vix >= _VIX_ALERT:
            level, msg = "やや警戒", "恐怖指数は高めですが、円高は伴っていません"
        elif yen_strong and vix_chg > 5:
            level, msg = "やや警戒", "円高と恐怖指数の上昇が同時に出ています"
        elif vix < _VIX_CALM:
            level, msg = "平常", "市場は落ち着いています"
        else:
            level, msg = "普通", "特に警戒すべき水準ではありません"

        return {"available": True, "vix": vix, "vix_chg": vix_chg,
                "fx": fx, "fx_chg": fx_chg, "level": level, "message": msg}
    except Exception:
        logger.error("リスク温度を出せませんでした", exc_info=True)
        return out


def _overnight() -> dict:
    """
    ③夜のうちに何が起きたか。
    通知を見逃していても朝に把握できるよう、直近1セッション分をまとめる。
    """
    out = {"available": False, "items": []}
    try:
        from src.quote_util import quote
        items = []
        for sym, label in (("^GSPC", "S&P500"), ("^SOX", "SOX半導体"),
                           ("^IXIC", "NASDAQ")):
            q = quote(sym, rng="5d")
            if q:
                items.append({"name": label, "chg": round(q["change_pct"], 2)})

        # 米国で全面的な動きがあったかは us_movers の判定を借りる
        big = None
        try:
            from src.us_movers import run as um_run
            r = um_run()
            if r.get("available"):
                big = {"emergency": bool(r.get("emergency")),
                       "sectors": [s["sector"] for s in (r.get("sectors") or [])[:2]],
                       "movers": [(m["name"], m["chg_pct"])
                                  for m in (r.get("movers") or [])[:3]]}
        except Exception:
            logger.debug(traceback.format_exc())

        return {"available": bool(items), "items": items, "us": big}
    except Exception:
        logger.error("夜間の動きをまとめられませんでした", exc_info=True)
        return out


def _today_events() -> dict:
    """④今日の予定。身構えるべき時間があるかだけ分かればよい。"""
    try:
        from src.economic_calendar import run as cal_run
        c = cal_run() or {}
        evs = c.get("today") or c.get("events") or []
        return {"available": bool(evs), "events": evs[:4]}
    except Exception:
        logger.debug(traceback.format_exc())
        return {"available": False, "events": []}


def run() -> dict:
    logger.info("=== 朝の3分ブリーフ ===")
    d = {
        "generated_at": get_jst_now().strftime("%Y-%m-%d %H:%M"),
        "outlook": _nikkei_outlook(),
        "risk": _risk_temp(),
        "overnight": _overnight(),
        "events": _today_events(),
    }
    d["available"] = d["outlook"].get("available") or d["risk"].get("available")
    d["headline"] = _headline(d)
    logger.info(f"✅ {d['headline']}")
    return d


def _headline(d: dict) -> str:
    """
    最初の1行。ここだけ読めば「今日が普通の日か」が分かるようにする。
    """
    o, r = d.get("outlook") or {}, d.get("risk") or {}
    parts = []
    if o.get("available"):
        diff = o["diff_yen"]
        arrow = "高く" if diff > 0 else "安く"
        parts.append(f"寄り付きは約{abs(diff):,}円{arrow}始まる見込み")
    if r.get("available") and r["level"] in ("警戒", "やや警戒"):
        parts.append(f"リスク {r['level']}")
    if not parts:
        return "今日は特筆すべき材料はありません"
    return " ／ ".join(parts)


def build_message(d: dict) -> str:
    lines = ["☀️ *おはようございます — 今日の3分ブリーフ*",
             f"　{d['headline']}",
             "━━━━━━━━━━━━━━", ""]

    o = d.get("outlook") or {}
    if o.get("available"):
        arrow = "🔺" if o["diff_yen"] > 0 else "🔻"
        lines += [f"① *寄り付きの見当*　{o['band']}",
                  f"　日経（昨日の終値）　{o['cash']:,.0f}円"
                  + (f"（{o['cash_chg']:+.2f}%）" if o.get("cash_chg") is not None else ""),
                  f"　日経先物（今）　　　{o['future']:,.0f}円",
                  f"　{arrow} 差 *{o['diff_yen']:+,}円*（{o['diff_pct']:+.2f}%）",
                  f"　→ {o['advice']}", ""]

    r = d.get("risk") or {}
    if r.get("available"):
        icon = {"警戒": "🔴", "やや警戒": "🟡"}.get(r["level"], "🟢")
        lines += [f"② *世界の緊張度*　{icon} {r['level']}",
                  f"　VIX（恐怖指数）　{r['vix']:.2f}（{r['vix_chg']:+.2f}%）",
                  f"　ドル円　　　　　　{r['fx']:.2f}（{r['fx_chg']:+.2f}%）",
                  f"　→ {r['message']}", ""]

    ov = d.get("overnight") or {}
    if ov.get("available"):
        lines.append("③ *夜のうちの動き*")
        lines.append("　" + "　".join(f"{x['name']} {x['chg']:+.2f}%"
                                      for x in ov["items"]))
        us = ov.get("us") or {}
        if us.get("emergency"):
            lines.append("　🚨 米国市場は全面的に動いています")
        if us.get("movers"):
            lines.append("　大きく動いた: " +
                         "・".join(f"{n} {c:+.1f}%" for n, c in us["movers"]))
        lines.append("")

    ev = d.get("events") or {}
    if ev.get("available"):
        lines.append("④ *今日の予定*")
        for e in ev["events"]:
            t = e.get("time") or e.get("時刻") or ""
            n = e.get("name") or e.get("event") or e.get("イベント") or str(e)
            lines.append(f"　{t} {n}".rstrip())
        lines.append("")

    lines += ["ℹ️ ①と②だけで「今日が普通の日か特別な日か」はほぼ判断できます。",
              "　 気になったときだけ、レポート本編へお進みください。"]
    return "\n".join(lines)[:4000]


if __name__ == "__main__":
    import io, sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    print(build_message(run()))
