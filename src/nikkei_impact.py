"""
日経平均への寄与度（Step NI）— 指数を動かしている銘柄を特定する

なぜ必要か:
  日経平均は「株価の平均」であって時価総額加重ではない。
  つまり**株価の高い銘柄ほど指数を動かす力が強い**。
  ファーストリテイリング（5万円台）が1%動くと指数は100円以上動くが、
  同じ1%でも1,000円の銘柄なら数円にしかならない。

  「日経が下げた」と言われても、それが1銘柄のせいなのか全体なのかで
  意味がまるで違う。前者なら明日には戻るかもしれないが、
  後者は地合いそのものが変わったことになる。

  そのため本モジュールは、
    ・各銘柄が指数を何円動かしたか（寄与度）
    ・上位数銘柄だけで説明できてしまう偏った下げか
  を数字で出す。

計算方法:
  日経平均 = Σ(調整後株価) ÷ 除数
  1銘柄の寄与度 = (その日の値動き × みなし額面調整) ÷ 除数

  除数は日経が公表しているが機械可読の形では取りにくいため、
  「構成銘柄の株価合計 ÷ 日経平均」から逆算する。
  近似だが、寄与度の**順位と相対的な大きさ**を知る用途には十分。
  ⚠️ 絶対値そのものを他所の数字と突き合わせる用途には使わないこと。

run() → 寄与度の一覧と偏りの判定
"""
import json
import ssl
import traceback
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

from src.utils import setup_logger, BASE_DIR, get_jst_now

logger = setup_logger("nikkei_impact")

_STATE_FILE = BASE_DIR / "data" / "nikkei_impact_state.json"

# 日経平均への影響が大きい主力銘柄。
# 全225銘柄を毎回取ると時間がかかりすぎるため、寄与度の大きい顔ぶれに絞る。
# 値がさ株（株価の高い銘柄）を厚くしているのは、日経が株価の平均であり
# 高い銘柄ほど指数を動かす力が強いという構造そのものによる。
CONSTITUENTS = [
    ("9983.T", "ファーストリテイリング", 1.0),
    ("8035.T", "東京エレクトロン",       1.0),
    ("9984.T", "ソフトバンクG",          1.0),
    ("6857.T", "アドバンテスト",         1.0),
    ("6920.T", "レーザーテック",         1.0),
    ("6146.T", "ディスコ",               1.0),
    ("4063.T", "信越化学",               1.0),
    ("6367.T", "ダイキン",               1.0),
    ("6098.T", "リクルート",             1.0),
    ("4568.T", "第一三共",               1.0),
    ("6954.T", "ファナック",             1.0),
    ("7974.T", "任天堂",                 1.0),
    ("6758.T", "ソニーG",                1.0),
    ("6501.T", "日立",                   1.0),
    ("7203.T", "トヨタ",                 1.0),
    ("8306.T", "三菱UFJ",                1.0),
    ("8316.T", "三井住友FG",             1.0),
    ("8411.T", "みずほFG",               1.0),
    ("9433.T", "KDDI",                   1.0),
    ("9432.T", "NTT",                    1.0),
    ("4661.T", "オリエンタルランド",     1.0),
    ("4519.T", "中外製薬",               1.0),
    ("6902.T", "デンソー",               1.0),
    ("4062.T", "イビデン",               1.0),
    ("5803.T", "フジクラ",               1.0),
    ("6723.T", "ルネサス",               1.0),
    ("8058.T", "三菱商事",               1.0),
    ("2413.T", "エムスリー",             1.0),
    ("4543.T", "テルモ",                 1.0),
    ("6594.T", "ニデック",               1.0),
]

# 上位何銘柄で指数の変動が説明できたら「偏っている」とみなすか。
# 3銘柄で7割を説明できるなら、それは全体の地合いではなく個別の話。
_TOP_K = 3
_CONCENTRATION = 0.7
# 寄与度がこの円数を超えたら「指数を動かした」として個別に取り上げる
_BIG_YEN = 30.0


def _fetch(sym: str) -> dict | None:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(sym)}?range=5d&interval=1d")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        d = json.loads(urllib.request.urlopen(req, context=ctx, timeout=20).read())
        r = d["chart"]["result"][0]
        meta = r.get("meta") or {}
        raw = r["indicators"]["quote"][0]["close"]
        ts = r["timestamp"]
        pairs = [(t, c) for t, c in zip(ts, raw) if c]
        if len(pairs) < 2:
            return None

        cur = meta.get("regularMarketPrice") or pairs[-1][1]
        # 前日終値は日付で特定する。meta の chartPreviousClose はレンジの
        # 直前を指すため、レンジを変えると値が変わってしまう（us_movers で事故済み）。
        off = meta.get("gmtoffset")
        tz = timezone(timedelta(seconds=off)) if off is not None else timezone.utc
        mt = meta.get("regularMarketTime")
        today = (datetime.fromtimestamp(mt, tz).date() if mt
                 else datetime.now(tz).date())
        prev = next((c for t, c in reversed(pairs)
                     if datetime.fromtimestamp(t, tz).date() < today), pairs[-2][1])
        return {"cur": float(cur), "prev": float(prev)}
    except Exception:
        logger.debug(traceback.format_exc())
        return None


def _divisor(prices: dict, nikkei_level: float) -> float | None:
    """
    除数を「株価合計 ÷ 指数」から逆算する。

    本来の除数は全225銘柄の合計から決まるが、ここでは主要30銘柄しか見ていない。
    そのため得られるのは「この30銘柄ぶんの縮尺」であり、絶対値としては正しくない。
    ただし寄与度の順位と相対的な大きさを知るには十分に働く。
    """
    total = sum(p["cur"] for p in prices.values() if p)
    if not total or not nikkei_level:
        return None
    return total / nikkei_level


def run(*_args, **_kwargs) -> dict:
    logger.info("=== 日経平均への寄与度 ===")

    # 日経平均の水準（現物）。取得できないと縮尺が決まらない
    try:
        from src.fetch_prices import _fetch_nikkei_official_csv
        nk = _fetch_nikkei_official_csv("nikkei_stock_average_daily_jp.csv") or {}
        level, nk_chg = nk.get("latest"), nk.get("change_pct")
    except Exception:
        logger.error("日経平均の水準を取得できませんでした", exc_info=True)
        level, nk_chg = None, None
    if not level:
        return {"available": False}

    prices = {}
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(_fetch, s): (s, n) for s, n, _ in CONSTITUENTS}
        for f in as_completed(futs):
            s, n = futs[f]
            d = f.result()
            if d:
                prices[s] = d

    if len(prices) < 10:
        logger.error(f"取得できた銘柄が少なすぎます（{len(prices)}件）")
        return {"available": False}

    div = _divisor(prices, level)
    if not div:
        return {"available": False}

    rows = []
    for sym, name, adj in CONSTITUENTS:
        p = prices.get(sym)
        if not p or not p["prev"]:
            continue
        diff = p["cur"] - p["prev"]
        rows.append({
            "symbol": sym, "name": name,
            "price": round(p["cur"], 1), "prev": round(p["prev"], 1),
            "chg_pct": round(diff / p["prev"] * 100, 2),
            # 寄与度＝その銘柄の値動きが指数を何円動かしたか
            "impact_yen": round(diff * adj / div, 1),
        })
    rows.sort(key=lambda x: -abs(x["impact_yen"]))

    up = sum(r["impact_yen"] for r in rows if r["impact_yen"] > 0)
    down = sum(r["impact_yen"] for r in rows if r["impact_yen"] < 0)
    net = up + down
    total_abs = sum(abs(r["impact_yen"]) for r in rows) or 1

    # 上位数銘柄だけで説明できてしまう「偏った動き」かを見る
    top = rows[:_TOP_K]
    top_share = sum(abs(r["impact_yen"]) for r in top) / total_abs
    concentrated = top_share >= _CONCENTRATION

    big = [r for r in rows if abs(r["impact_yen"]) >= _BIG_YEN]

    logger.info(f"✅ {len(rows)}銘柄 / 押し上げ{up:+.0f}円 押し下げ{down:+.0f}円 "
                f"/ 上位{_TOP_K}銘柄の割合 {top_share*100:.0f}%")

    return {
        "available": True,
        "scanned_at": get_jst_now().strftime("%Y-%m-%d %H:%M"),
        "nikkei_level": level, "nikkei_chg_pct": nk_chg,
        "rows": rows, "big": big,
        "up_yen": round(up, 1), "down_yen": round(down, 1), "net_yen": round(net, 1),
        "top_share": round(top_share, 3),
        "concentrated": concentrated,
        "summary": _summary(rows, up, down, top, top_share, concentrated),
    }


def _summary(rows, up, down, top, share, concentrated) -> list:
    """
    数字の羅列ではなく「どういう下げ方（上げ方）だったか」を言葉にする。
    偏りの有無は、翌日への持ち越し方が変わる重要な情報。
    """
    out = []
    net = up + down
    direction = "押し上げ" if net > 0 else "押し下げ"
    out.append(f"主要銘柄の寄与は差し引き {net:+.0f}円（{direction}）。"
               f"上げ要因 {up:+.0f}円 / 下げ要因 {down:+.0f}円。")

    names = "・".join(f"{r['name']}({r['impact_yen']:+.0f}円)" for r in top)
    if concentrated:
        out.append(f"⚠️ *上位{len(top)}銘柄だけで動きの{share*100:.0f}%を占めています*。"
                   f"（{names}）"
                   f"市場全体というより、特定銘柄の事情で指数が動いた形です。")
    else:
        out.append(f"寄与の大きい銘柄: {names}。"
                   f"上位に偏っておらず、幅広い銘柄が動いています。")

    ups = sum(1 for r in rows if r["chg_pct"] > 0)
    dns = sum(1 for r in rows if r["chg_pct"] < 0)
    if ups and dns:
        if ups >= dns * 3:
            out.append(f"値上がり{ups}／値下がり{dns}と、上げ優勢の広がりがあります。")
        elif dns >= ups * 3:
            out.append(f"値上がり{ups}／値下がり{dns}と、下げが広く波及しています。")
    return out


def build_block(r: dict, limit: int = 8) -> str:
    if not r.get("available"):
        return ""
    lines = ["🎯 *日経平均を動かした銘柄*", ""]
    for s in r.get("summary", []):
        lines.append(f"　{s}")
    lines.append("")
    for x in r["rows"][:limit]:
        arrow = "🔺" if x["impact_yen"] > 0 else "🔻"
        lines.append(f"{arrow} *{x['name']}* {x['impact_yen']:+.0f}円"
                     f"（株価 {x['price']:,.0f} / {x['chg_pct']:+.2f}%）")
    lines += ["",
              "ℹ️ 日経平均は株価の平均なので、株価の高い銘柄ほど指数を動かす力が"
              "強くなります。同じ1%でもファーストリテイリングと低位株では"
              "指数への影響がまるで違います。",
              "※ 主要30銘柄からの概算値です。"]
    return "\n".join(lines)[:4000]


def _session_key() -> str:
    return get_jst_now().strftime("%Y-%m-%d")


def run_impact_alert() -> bool:
    """
    monitor_run.py から呼ぶ。
    指数を大きく動かした銘柄が出た日に1回だけ知らせる。
    """
    try:
        r = run()
        if not r.get("available"):
            return False
        big = r.get("big") or []
        # 偏った動き（上位数銘柄で説明できる）も知らせる価値がある
        if not big and not r.get("concentrated"):
            logger.info("指数を大きく動かした銘柄なし")
            return False

        skey = _session_key()
        try:
            st = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            st = {}
        if st.get("session") == skey:
            logger.info("本日は通知済みのためスキップ")
            return False

        from src.notify_telegram import send_message
        ok = send_message(build_block(r))
        if ok:
            try:
                _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
                _STATE_FILE.write_text(
                    json.dumps({"session": skey,
                                "ts": datetime.now().isoformat(),
                                "net_yen": r["net_yen"]}, ensure_ascii=False),
                    encoding="utf-8")
            except Exception:
                logger.error("状態の保存に失敗しました", exc_info=True)
            logger.info(f"✅ 日経寄与度を通知（{len(big)}銘柄）")
        return bool(ok)
    except Exception:
        logger.error("日経寄与度の処理に失敗しました", exc_info=True)
        return False


if __name__ == "__main__":
    import io, sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    print(build_block(run(), limit=12))
