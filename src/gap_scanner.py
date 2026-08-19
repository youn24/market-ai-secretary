"""
窓開け検出（Step GAP）— 寄り付きの飛びと、その後の埋め具合を見る

なぜ必要か:
  前日終値と当日始値が離れて始まること（窓・ギャップ）は、
  夜のうちに前提が変わったことの表れで、日中の値動きとは意味が違う。
  さらに実務で効くのは「窓を開けた後どうなったか」のほうで、
    ・窓を維持したまま伸びる  … 新しい水準が受け入れられた
    ・その日のうちに埋め戻す  … 行き過ぎだった（反対売買が入った）
  この2つは同じ「窓開け」でも読み方が正反対になる。開けた事実だけでなく
  埋め具合まで測るのが本モジュールの役割。

しきい値の考え方:
  「3%以上で通知」のような固定値は使わない。値動きの荒い新興株と
  ディフェンシブ株では、同じ3%の重みがまるで違うため。
  risk_gauges と同じく、その銘柄の過去1年の窓の大きさから
  「その銘柄にとって大きい窓」を求める。

run() → 窓を開けた銘柄の一覧
"""
import json
import statistics
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from src.utils import setup_logger, BASE_DIR, get_jst_now

logger = setup_logger("gap_scanner")

_STATE_FILE = BASE_DIR / "data" / "gap_state.json"

# 監視する銘柄。日経への影響が大きいものと、値動きの主役になりやすいものを選ぶ。
# 全225銘柄を毎回取ると時間がかかりすぎるため、指数を動かす顔ぶれに絞る。
WATCH = [
    ("8035.T", "東京エレクトロン"), ("6857.T", "アドバンテスト"),
    ("6920.T", "レーザーテック"),   ("9984.T", "ソフトバンクG"),
    ("6501.T", "日立"),            ("6758.T", "ソニーG"),
    ("7203.T", "トヨタ"),          ("6098.T", "リクルート"),
    ("4063.T", "信越化学"),        ("6367.T", "ダイキン"),
    ("8306.T", "三菱UFJ"),         ("8316.T", "三井住友FG"),
    ("8411.T", "みずほFG"),        ("9433.T", "KDDI"),
    ("9432.T", "NTT"),            ("4661.T", "オリエンタルランド"),
    ("7974.T", "任天堂"),          ("6902.T", "デンソー"),
    ("6954.T", "ファナック"),      ("4519.T", "中外製薬"),
    ("9983.T", "ファーストリテイリング"), ("4062.T", "イビデン"),
    ("5803.T", "フジクラ"),        ("6146.T", "ディスコ"),
    ("6723.T", "ルネサス"),        ("8058.T", "三菱商事"),
    ("^N225",  "日経平均"),
]

# 過去1年の窓のうち、この順位を超えたら「大きな窓」とみなす
_PCTL = 0.90
# 統計だけに任せると凪の期間に基準が下がるので、最低これだけは必要
_MIN_GAP_PCT = 1.0
_MIN_HISTORY = 60
# 窓の何割が埋まったら「埋めた」と判定するか
_FILL_DONE = 0.8


def _pctl(vals: list, q: float) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    return s[min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))]


def _scan_one(sym: str, name: str) -> dict | None:
    """1銘柄ぶんの窓を測る。"""
    try:
        import yfinance as yf
        h = yf.Ticker(sym).history(period="1y")
        if h is None or len(h) < 30 or "Open" not in h:
            return None
        o = [float(x) for x in h["Open"].tolist()]
        c = [float(x) for x in h["Close"].tolist()]
        hi = [float(x) for x in h["High"].tolist()]
        lo = [float(x) for x in h["Low"].tolist()]
        date = h.index[-1].strftime("%Y-%m-%d")

        prev_close, today_open = c[-2], o[-1]
        if not prev_close:
            return None
        gap = (today_open - prev_close) / prev_close * 100

        # その銘柄にとっての「大きい窓」を過去から求める
        past = [abs((o[i] - c[i - 1]) / c[i - 1] * 100)
                for i in range(1, len(o) - 1) if c[i - 1]]
        threshold = None
        if len(past) >= _MIN_HISTORY:
            threshold = max(_pctl(past, _PCTL), _MIN_GAP_PCT)

        # 窓埋めの進み具合。
        # 上に開けた窓は、その日の安値がどこまで前日終値に近づいたかで測る。
        # 完全に埋めた場合は1.0を超えるので、そこで頭打ちにする。
        filled = 0.0
        if abs(gap) > 0.01:
            if gap > 0:
                filled = (today_open - lo[-1]) / (today_open - prev_close)
            else:
                filled = (hi[-1] - today_open) / (prev_close - today_open)
            filled = max(0.0, min(1.0, filled))

        # 現時点の値が窓を維持しているか
        cur = c[-1]
        held = (cur >= today_open) if gap > 0 else (cur <= today_open)

        return {
            "symbol": sym, "name": name, "date": date,
            "prev_close": round(prev_close, 1), "open": round(today_open, 1),
            "current": round(cur, 1),
            "gap_pct": round(gap, 2),
            "threshold": round(threshold, 2) if threshold else None,
            "typical": round(statistics.median(past), 2) if past else None,
            "big": bool(threshold and abs(gap) >= threshold),
            "filled_ratio": round(filled, 2),
            "filled": filled >= _FILL_DONE,
            "held": bool(held),
            "day_change_pct": round((cur - prev_close) / prev_close * 100, 2),
        }
    except Exception:
        logger.debug(traceback.format_exc())
        return None


def run(only_big: bool = True) -> dict:
    logger.info("=== 窓開けスキャン ===")
    rows = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(_scan_one, s, n): n for s, n in WATCH}
        for f in as_completed(futs):
            r = f.result()
            if r:
                rows.append(r)

    if not rows:
        return {"available": False}

    big = [r for r in rows if r.get("big")]
    big.sort(key=lambda x: -abs(x["gap_pct"]))
    rows.sort(key=lambda x: -abs(x["gap_pct"]))

    up = [r for r in big if r["gap_pct"] > 0]
    down = [r for r in big if r["gap_pct"] < 0]
    logger.info(f"✅ {len(rows)}銘柄 / 大きな窓 {len(big)}件（上{len(up)}・下{len(down)}）")

    return {
        "available": True,
        "scanned_at": get_jst_now().strftime("%Y-%m-%d %H:%M"),
        "all": rows,
        "gaps": big if only_big else rows,
        "gap_up": up, "gap_down": down,
        "summary": _summary(big, rows),
    }


def _summary(big: list, rows: list) -> list:
    """
    窓を開けた銘柄の顔ぶれから、相場全体の状況を読む。
    銘柄名を並べるだけでは「全体で何が起きたか」が伝わらない。
    """
    if not big:
        return ["大きな窓を開けた銘柄はありません。落ち着いた寄り付きでした。"]

    up = [r for r in big if r["gap_pct"] > 0]
    down = [r for r in big if r["gap_pct"] < 0]
    out = []

    if down and not up:
        out.append(f"🔻 *{len(down)}銘柄が下に窓を開けて始まりました*。"
                   f"夜のうちに売り材料が出た形です。")
    elif up and not down:
        out.append(f"🔺 *{len(up)}銘柄が上に窓を開けて始まりました*。"
                   f"夜のうちに買い材料が出た形です。")
    else:
        out.append(f"上に{len(up)}銘柄・下に{len(down)}銘柄が窓を開けました。"
                   f"銘柄ごとに事情が分かれています。")

    # 窓埋めの状況は、その日の力関係を映す
    filled = [r for r in big if r["filled"]]
    held = [r for r in big if r["held"] and not r["filled"]]
    if filled:
        names = "・".join(r["name"] for r in filled[:3])
        out.append(f"↩️ {names} は窓をほぼ埋め戻しました。"
                   f"寄り付きの動きが行き過ぎだった可能性があります。")
    if held:
        names = "・".join(r["name"] for r in held[:3])
        out.append(f"➡️ {names} は窓を維持したままです。"
                   f"新しい価格水準が受け入れられている形です。")

    n225 = next((r for r in rows if r["symbol"] == "^N225"), None)
    if n225 and n225.get("big"):
        d = "下" if n225["gap_pct"] < 0 else "上"
        out.append(f"日経平均自体が{d}に {abs(n225['gap_pct']):.2f}% の窓を開けており、"
                   f"個別要因ではなく市場全体の動きです。")
    return out


def build_block(data: dict, limit: int = 8) -> str:
    if not data.get("available"):
        return ""
    gaps = data.get("gaps") or []
    lines = ["🪟 *窓開け（ギャップ）*", ""]
    for s in data.get("summary", []):
        lines.append(f"　{s}")
    if not gaps:
        return "\n".join(lines)

    lines.append("")
    for r in gaps[:limit]:
        arrow = "🔺上" if r["gap_pct"] > 0 else "🔻下"
        state = ("窓を埋め戻し" if r["filled"]
                 else "窓を維持" if r["held"]
                 else f"{r['filled_ratio']*100:.0f}%ほど埋め")
        lines.append(f"{arrow} *{r['name']}* {r['gap_pct']:+.2f}%"
                     f"（{r['prev_close']:,.0f} → {r['open']:,.0f}）")
        lines.append(f"　└ 現在 {r['current']:,.0f}（{r['day_change_pct']:+.2f}%）・{state}")
        if r.get("typical") is not None:
            lines.append(f"　└ 普段の窓は{r['typical']:.1f}%程度")
    lines.append("")
    lines.append("ℹ️ 「大きな窓」の基準は銘柄ごとに過去1年から自動計算しています。")
    return "\n".join(lines)


def _session_key(now=None) -> str:
    n = now or get_jst_now()
    return n.strftime("%Y-%m-%d")


def run_gap_alert() -> bool:
    """monitor_run.py から呼ぶ。大きな窓が出た日に1回だけ通知する。"""
    try:
        r = run()
        gaps = r.get("gaps") or []
        if not gaps:
            logger.info("窓開け: 大きな窓なし")
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
            st = {"session": skey, "ts": datetime.now().isoformat(),
                  "count": len(gaps)}
            try:
                _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
                _STATE_FILE.write_text(json.dumps(st, ensure_ascii=False),
                                       encoding="utf-8")
            except Exception:
                logger.error("状態の保存に失敗しました", exc_info=True)
            logger.info(f"✅ 窓開けを通知（{len(gaps)}件）")
        return bool(ok)
    except Exception:
        logger.error("窓開けスキャンに失敗しました", exc_info=True)
        return False


if __name__ == "__main__":
    import io, sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    print(build_block(run(), limit=12))
