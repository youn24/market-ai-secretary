"""
データ健全性チェック（精度向上②）
- 取得した価格データに異常がないかを検査し、誤データが分析を汚染するのを防ぐ
- 「取得失敗(None)」「ありえない変動率」「範囲外の値」「前日と同値＝固着の疑い」を検出
- 純Python・依存なし。重要指標の欠損は high、異常値は warn として返す

返り値:
  {available, checked, ok, issues[{symbol,name,severity,msg}], max_severity, summary, flagged:set}
"""
from src.utils import setup_logger

logger = setup_logger("data_integrity")

# 欠損していたら分析の前提が崩れる重要指標
CRITICAL = {"^N225", "^GSPC", "USDJPY=X", "^VIX"}

# カテゴリ別の「1日の変動率」常識的上限（%）。これを超えたら要確認（warn）
_MOVE_LIMIT = {
    "index":      8.0,
    "japan":      8.0,
    "us":         8.0,
    "forex":      5.0,
    "rate":      20.0,
    "commodity": 12.0,
    "crypto":    30.0,
    "stock":     25.0,
    "fear":      60.0,   # VIX等は荒い
}
# 値そのものの妥当レンジ（latestの絶対水準）
_VALUE_RANGE = {
    "^VIX":      (5, 95),
    "NIKKEI_VI": (8, 95),
    "NT_RATIO":  (8, 20),
}


def _move_limit(category: str) -> float:
    c = (category or "").lower()
    for key, lim in _MOVE_LIMIT.items():
        if key in c:
            return lim
    return 15.0  # 不明カテゴリは緩め


def check(prices: dict) -> dict:
    prices = prices or {}
    issues = []
    flagged = set()
    checked = 0

    for sym, d in prices.items():
        if not isinstance(d, dict):
            continue
        checked += 1
        name = d.get("name", sym)
        latest = d.get("latest")
        prev   = d.get("prev_close")
        chg    = d.get("change_pct")
        cat    = d.get("category", "")

        # 1) 重要指標の欠損
        if latest is None:
            sev = "high" if sym in CRITICAL else "warn"
            issues.append({"symbol": sym, "name": name, "severity": sev,
                           "msg": "取得失敗（値なし）"})
            flagged.add(sym)
            continue

        # 2) ありえない変動率
        if chg is not None:
            lim = _move_limit(cat)
            if abs(chg) > lim:
                sev = "high" if abs(chg) > lim * 2 else "warn"
                issues.append({"symbol": sym, "name": name, "severity": sev,
                               "msg": f"変動率が異常: {chg:+.1f}%（目安±{lim:.0f}%以内）"})
                flagged.add(sym)

        # 3) 値の妥当レンジ
        lo_hi = _VALUE_RANGE.get(sym)
        if lo_hi and latest is not None:
            lo, hi = lo_hi
            if not (lo <= latest <= hi):
                issues.append({"symbol": sym, "name": name, "severity": "high",
                               "msg": f"値が想定範囲外: {latest}（{lo}〜{hi}）"})
                flagged.add(sym)

        # 4) 前日と完全同値＝固着（取得失敗の疑い）。重要指標のみ warn
        if (prev is not None and latest == prev and (chg == 0 or chg is None)
                and sym in CRITICAL):
            issues.append({"symbol": sym, "name": name, "severity": "warn",
                           "msg": "前日と同値で変化なし（更新されていない可能性）"})
            flagged.add(sym)

    highs = [i for i in issues if i["severity"] == "high"]
    warns = [i for i in issues if i["severity"] == "warn"]
    if highs:
        max_sev = "high"
    elif warns:
        max_sev = "warn"
    else:
        max_sev = "ok"

    ok = checked - len(flagged)
    if max_sev == "ok":
        summary = f"全{checked}指標すべて正常"
    elif max_sev == "warn":
        summary = f"{checked}指標中 {len(flagged)}件に軽微な要確認（重大な異常なし）"
    else:
        summary = f"{checked}指標中 {len(highs)}件に重大な異常（要注意）"

    logger.info(f"データ健全性: {max_sev} / {summary}")
    return {
        "available": True,
        "checked": checked,
        "ok": ok,
        "issues": issues,
        "max_severity": max_sev,
        "summary": summary,
        "flagged": flagged,
    }


def run(prices: dict) -> dict:
    return check(prices)
