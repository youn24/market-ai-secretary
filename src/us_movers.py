"""
米国ザラ場ムーバー（Step UM）— 通常取引時間に大きく動いた銘柄を拾う

既存モジュールとの違い:
  us_afterhours … 時間外（プレ/アフター）専用。決算直後の反応を見る
  us_movers(本体)… 米国の**通常取引時間**を見る。時間外では拾えなかった
                    「本セッション中に崩れた/急伸した」動きを捉える

なぜ必要か:
  これまで米国株は時間外しか見ていなかった。しかし2026-08-18の半導体安のように、
  通常取引の最中に崩れる日がある。日本時間の深夜に進行するため、
  朝起きた時には「もう終わっている」状態で、備える時間が無かった。

しきい値の考え方（risk_gauges と同じ方式）:
  「5%動いたら通知」の固定値は使わない。テスラは平常時でも日々4%動くが、
  ジョンソン&ジョンソンが4%動けば異常事態で、同じ数字では意味が違う。
  各銘柄の過去1年の日次変化率の90パーセンタイルを基準にする。

セクター単位の判定を入れている理由:
  1銘柄だけの急落は個別の材料（決算・不祥事）である可能性が高い。
  しかし同じセクターの複数銘柄が同時に動いたなら、それは業界全体の話で、
  翌日の日本の関連株にほぼ確実に波及する。個別とセクターは別物として扱う。

run() → 検出結果 / run_movers_alert() → 通知（1セッション1回）
"""
import json
import os
import ssl
import statistics
import traceback
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

from src.utils import setup_logger, BASE_DIR, get_jst_now

logger = setup_logger("us_movers")

_STATE_FILE = BASE_DIR / "data" / "us_movers_state.json"
_JST = timezone(timedelta(hours=9))

# 過去1年の変化率のうち、この順位を超えたら「大きく動いた」とみなす
_PCTL = 0.90
# 統計だけに任せると凪の期間に基準が下がるため、最低これだけは動いていること
_MIN_MOVE_PCT = 2.0
# 履歴がこの日数に満たない銘柄は基準を作れないので固定値で代用する
_MIN_HISTORY = 60
_FALLBACK_PCT = 4.0
# 同じセクターでこの数以上が同方向に動いたら「業界全体の動き」とみなす
_SECTOR_MIN = 3
# 通知に載せる上限（多すぎると読まれない）
_TOP_N = 10


def _fetch_chart(sym: str, rng: str = "1d", interval: str = "1d") -> dict | None:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
           f"?range={rng}&interval={interval}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        d = json.loads(urllib.request.urlopen(req, context=ctx, timeout=20).read())
        return d["chart"]["result"][0]
    except Exception:
        logger.debug(traceback.format_exc())
        return None


def market_phase() -> str:
    """
    いま米国市場がどの時間帯かを返す（pre / regular / post / closed）。

    夏時間と冬時間で1時間ずれるため、時刻を決め打ちにすると年2回ずれる。
    Yahooが返す currentTradingPeriod を使えば切替を自動で吸収できる。
    """
    r = _fetch_chart("NVDA")
    if not r:
        return "unknown"
    tp = (r.get("meta") or {}).get("currentTradingPeriod") or {}
    now = datetime.now(timezone.utc).timestamp()
    for phase in ("regular", "pre", "post"):
        p = tp.get(phase) or {}
        if p.get("start") and p.get("end") and p["start"] <= now < p["end"]:
            return phase
    return "closed"


def _threshold(daily: list) -> tuple:
    """その銘柄にとっての「大きな動き」を過去から求める。"""
    if len(daily) < _MIN_HISTORY:
        return _FALLBACK_PCT, None
    s = sorted(daily)
    i = min(len(s) - 1, max(0, int(round(_PCTL * (len(s) - 1)))))
    return max(s[i], _MIN_MOVE_PCT), statistics.median(daily)


def _scan_one(sym: str, name: str, sector: str) -> dict | None:
    """1銘柄の当日の値動きと、その銘柄にとっての大きさを測る。"""
    r = _fetch_chart(sym, rng="1y", interval="1d")
    if not r:
        return None
    meta = r.get("meta") or {}
    try:
        raw = r["indicators"]["quote"][0]["close"]
        ts = r["timestamp"]
        pairs = [(t, c) for t, c in zip(ts, raw) if c]
    except Exception:
        return None
    if len(pairs) < 2:
        return None
    closes = [c for _, c in pairs]

    cur = meta.get("regularMarketPrice") or closes[-1]

    # ⚠️ meta の previousClose / chartPreviousClose を使ってはいけない。
    # range=1y だと chartPreviousClose は「1年前の直前の終値」を指す。
    # 実際にサンディスクで 44.4 が返り、前日比が +3505% と表示される事故になった。
    #
    # 正しくは「当日より前の最後の終値」。取引所の日付で判定する。
    off = meta.get("gmtoffset")
    tzinfo = timezone(timedelta(seconds=off)) if off is not None else timezone.utc
    mkt_time = meta.get("regularMarketTime")
    today = (datetime.fromtimestamp(mkt_time, tzinfo).date()
             if mkt_time else datetime.now(tzinfo).date())
    prev = None
    for t, c in reversed(pairs):
        if datetime.fromtimestamp(t, tzinfo).date() < today:
            prev = c
            break
    if prev is None:
        prev = closes[-2]
    if not prev:
        return None
    chg = (cur - prev) / prev * 100

    daily = [abs((b - a) / a * 100) for a, b in zip(closes, closes[1:]) if a]
    th, typical = _threshold(daily)

    return {
        "symbol": sym, "name": name, "sector": sector,
        "price": round(float(cur), 2), "prev": round(float(prev), 2),
        "chg_pct": round(chg, 2),
        "threshold": round(th, 2),
        "typical": round(typical, 2) if typical is not None else None,
        "big": abs(chg) >= th,
        "day_high": meta.get("regularMarketDayHigh"),
        "day_low": meta.get("regularMarketDayLow"),
    }


def _watchlist() -> list:
    """
    監視銘柄。時間外モジュールと同じ顔ぶれを使う。
    別々に持つと片方だけ更新されてズレるため、必ず一箇所から読む。
    """
    try:
        from src.us_afterhours import WATCHLIST
        return list(WATCHLIST)
    except Exception:
        logger.error("監視リストを読めませんでした", exc_info=True)
        return []


def run(only_big: bool = True) -> dict:
    phase = market_phase()
    logger.info(f"=== 米国ザラ場ムーバー（市場は {phase}）===")

    wl = _watchlist()
    if not wl:
        return {"available": False}

    rows = []
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(_scan_one, s, n, c): s for s, n, c in wl}
        for f in as_completed(futs):
            r = f.result()
            if r:
                rows.append(r)

    if not rows:
        return {"available": False}

    big = [r for r in rows if r["big"]]
    big.sort(key=lambda x: -abs(x["chg_pct"]))
    rows.sort(key=lambda x: -abs(x["chg_pct"]))

    sectors = _sector_moves(rows)
    logger.info(f"✅ {len(rows)}銘柄 / 大きく動いた {len(big)}件 / "
                f"セクター単位 {len(sectors)}件")

    return {
        "available": True,
        "phase": phase,
        "scanned_at": get_jst_now().strftime("%Y-%m-%d %H:%M"),
        "all": rows,
        "movers": big if only_big else rows,
        "sectors": sectors,
        "jp_impact": _jp_impact(big, sectors),
    }


def _sector_moves(rows: list) -> list:
    """
    セクター単位でまとまった動きを検出する。

    個別の急落は決算などの固有材料かもしれないが、
    同業が揃って動いたなら業界全体の話であり、翌日の日本株にほぼ波及する。
    平均だけでなく「何銘柄が同じ方向か」を数えるのは、
    1銘柄の極端な値で平均が引っ張られるのを避けるため。
    """
    by_sec = {}
    for r in rows:
        by_sec.setdefault(r["sector"], []).append(r)

    out = []
    for sec, members in by_sec.items():
        if len(members) < _SECTOR_MIN:
            continue
        up = [m for m in members if m["chg_pct"] > 0]
        dn = [m for m in members if m["chg_pct"] < 0]
        side, group = ("up", up) if len(up) > len(dn) else ("down", dn)
        if len(group) < _SECTOR_MIN:
            continue
        avg = statistics.mean(m["chg_pct"] for m in group)
        # セクターとして意味のある大きさか（小さな動きが揃っても事件ではない）
        if abs(avg) < 1.5:
            continue
        out.append({
            "sector": sec, "direction": side,
            "count": len(group), "total": len(members),
            "avg_pct": round(avg, 2),
            "leaders": sorted(group, key=lambda x: abs(x["chg_pct"]),
                              reverse=True)[:3],
        })
    out.sort(key=lambda x: -abs(x["avg_pct"]))
    return out


# その銘柄・セクターが動いたとき、日本のどこに効くか。
# 「NVDAが下げた」だけでは初心者は何をすればいいか分からないため、
# 明日の東京で見るべき銘柄名まで落とす。
_JP_BY_SYMBOL = {
    "NVDA": "東エレク・アドバンテスト・レーザーテック",
    "TSM":  "東エレク・SCREEN・ディスコ",
    "ASML": "東エレク・レーザーテック",
    "AMAT": "東エレク・SCREEN", "LRCX": "東エレク・SCREEN",
    "KLAC": "レーザーテック", "MU": "キオクシア・サンディスク関連",
    "AVGO": "半導体全般", "ARM": "ソフトバンクG",
    "AAPL": "村田製作所・TDK・イビデン",
    "TSLA": "パナソニック・デンソー",
    "SONY": "ソニーG（ADR＝同じ会社）",
    "TM":   "トヨタ（ADR＝同じ会社）",
    "HMC":  "ホンダ（ADR＝同じ会社）",
    "MUFG": "三菱UFJ（ADR）", "SMFG": "三井住友FG（ADR）",
    "MFG":  "みずほFG（ADR）",
    "CAT":  "コマツ・日立建機", "DE": "クボタ",
    "GE":   "三菱重工・IHI", "BA": "重工・航空部品",
    "JPM":  "メガバンク", "GS": "野村・大和",
    "FCX":  "非鉄・商社", "XOM": "資源・商社", "CVX": "資源・商社",
    "NKE":  "アシックス・ゴールドウイン",
    "DIS":  "オリエンタルランド",
    "COIN": "マネックス・暗号資産関連", "MSTR": "暗号資産関連",
    "FDX":  "物流（景気の先行指標）", "UPS": "物流",
    "PLTR": "AI関連（さくらインターネット等）",
}
_JP_BY_SECTOR = {
    "半導体":     "東エレク・アドバンテスト・レーザーテック・ディスコ",
    "半導体装置": "東エレク・SCREEN・ディスコ",
    "ハイテク":   "ソフトバンクG・電子部品株",
    "AI":         "AI関連・データセンター関連",
    "AIサーバー": "AI関連・電子部品株",
    "日本株ADR": "同じ企業の東京上場分",
    "金融":       "メガバンク・証券",
    "EV":         "パナソニック・デンソー",
    "自動車":     "トヨタ・ホンダ・日産",
    "資本財":     "コマツ・日立建機・三菱重工",
    "防衛":       "三菱重工・IHI・川崎重工",
    "エネルギー": "INPEX・商社",
    "資源":       "商社・非鉄",
    "暗号資産":   "マネックス・暗号資産関連",
    "物流":       "日本郵船・商船三井（景気の目安）",
    "宇宙":       "宇宙関連（IHI・三菱重工）",
}


def _jp_impact(movers: list, sectors: list) -> list:
    """
    日本市場への波及を、具体的な銘柄名で示す。
    セクター単位の動きを先に置くのは、そちらの方が翌日への影響が確実なため。
    """
    out = []
    for s in sectors:
        jp = _JP_BY_SECTOR.get(s["sector"])
        if not jp:
            continue
        d = "上昇" if s["direction"] == "up" else "下落"
        out.append({
            "kind": "sector",
            "text": (f"米国の{s['sector']}が{s['count']}銘柄そろって{d}"
                     f"（平均{s['avg_pct']:+.2f}%）。"
                     f"明日の東京では **{jp}** に波及しやすい形です。"),
            "direction": s["direction"],
        })

    seen = set()
    for m in movers[:6]:
        jp = _JP_BY_SYMBOL.get(m["symbol"])
        if not jp or jp in seen:
            continue
        seen.add(jp)
        d = "上昇" if m["chg_pct"] > 0 else "下落"
        out.append({
            "kind": "stock",
            "text": (f"{m['name']} が{m['chg_pct']:+.2f}%の{d}。"
                     f"→ **{jp}** に効きやすい銘柄です。"),
            "direction": "up" if m["chg_pct"] > 0 else "down",
        })
    return out


# ── 通知 ───────────────────────────────────────────────────────
def _session_key(now=None) -> str:
    """
    JST 6時始まりのセッション。
    米国市場は日本時間の深夜〜早朝にまたがるため、日付で切ると
    同じ取引日の前半と後半が別の日として扱われてしまう。
    """
    n = now or get_jst_now()
    return (n - timedelta(hours=6)).strftime("%Y-%m-%d")


def build_message(r: dict) -> str:
    movers = r.get("movers") or []
    sectors = r.get("sectors") or []
    phase_ja = {"regular": "取引時間中", "pre": "寄り付き前",
                "post": "引け後", "closed": "取引時間外"}.get(r.get("phase"), "")

    lines = [f"🇺🇸 *米国株が大きく動いています*（{phase_ja}）",
             "━━━━━━━━━━━━━━", ""]

    # ① 日本への影響を最初に置く。米国の銘柄名だけ並べても、
    #    明日どこを見ればいいのかが分からないため。
    jp = r.get("jp_impact") or []
    if jp:
        lines.append("📖 *日本市場への影響*")
        for x in jp[:4]:
            lines.append(f"　{'🔺' if x['direction'] == 'up' else '🔻'} {x['text']}")
        lines.append("")

    if sectors:
        lines.append("🏭 *業界単位の動き*")
        for s in sectors[:3]:
            arrow = "🔺" if s["direction"] == "up" else "🔻"
            names = "・".join(m["name"] for m in s["leaders"])
            lines.append(f"{arrow} *{s['sector']}*　{s['count']}/{s['total']}銘柄が"
                         f"同じ方向（平均 {s['avg_pct']:+.2f}%）")
            lines.append(f"　{names}")
        lines.append("")

    if movers:
        lines.append("📊 *大きく動いた銘柄*")
        for m in movers[:_TOP_N]:
            arrow = "🔺" if m["chg_pct"] > 0 else "🔻"
            lines.append(f"{arrow} *{m['name']}* {m['chg_pct']:+.2f}%"
                         f"（{m['price']:,.2f}）")
            if m.get("typical") is not None:
                lines.append(f"　└ 普段は{m['typical']:.1f}%程度の値動き"
                             f"（目安{m['threshold']:.1f}%を超えました）")
        lines.append("")

    lines.append("ℹ️ 「大きく動いた」の基準は銘柄ごとに過去1年から自動計算しています。"
                 "テスラのように普段から動く銘柄と、そうでない銘柄では"
                 "同じ%でも意味が違うためです。")
    return "\n".join(lines)[:4000]


def run_movers_alert() -> bool:
    """
    monitor_run.py から呼ぶ。
    通常取引の時間帯だけ動かし、同じ内容は1セッション1回に留める。
    """
    try:
        r = run()
        if not r.get("available"):
            return False
        if r.get("phase") != "regular":
            logger.info(f"通常取引の時間帯ではないためスキップ（{r.get('phase')}）")
            return False

        movers = r.get("movers") or []
        sectors = r.get("sectors") or []
        if not movers and not sectors:
            logger.info("大きく動いた銘柄なし")
            return False

        skey = _session_key()
        try:
            st = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            st = {}

        # 同じ銘柄を何度も送らない。ただしセクター単位の動きは
        # 個別より重いので、セクターが新規なら通す。
        new_syms = [m for m in movers
                    if st.get(f"S:{m['symbol']}", {}).get("session") != skey]
        new_secs = [s for s in sectors
                    if st.get(f"C:{s['sector']}", {}).get("session") != skey]
        if not new_syms and not new_secs:
            logger.info("すべて通知済みのためスキップ")
            return False

        now = datetime.now().isoformat()
        for m in new_syms:
            st[f"S:{m['symbol']}"] = {"session": skey, "ts": now, "chg": m["chg_pct"]}
        for s in new_secs:
            st[f"C:{s['sector']}"] = {"session": skey, "ts": now}
        st = {k: v for k, v in st.items()
              if isinstance(v, dict) and v.get("session") == skey}
        try:
            _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            _STATE_FILE.write_text(json.dumps(st, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
        except Exception:
            logger.error("状態の保存に失敗しました", exc_info=True)

        payload = {**r, "movers": new_syms or movers,
                   "sectors": new_secs or sectors}
        payload["jp_impact"] = _jp_impact(payload["movers"], payload["sectors"])

        from src.notify_telegram import send_message
        ok = send_message(build_message(payload))
        if ok:
            logger.info(f"✅ 米国ザラ場ムーバーを通知"
                        f"（銘柄{len(new_syms)}・業界{len(new_secs)}）")
        return bool(ok)
    except Exception:
        logger.error("米国ザラ場ムーバーの処理に失敗しました", exc_info=True)
        return False


if __name__ == "__main__":
    import io, sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    r = run()
    print(build_message(r) if r.get("available") else "取得できませんでした")
