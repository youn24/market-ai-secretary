"""
データ正確性の監査（Step AUDIT）— 表示している数字が本当に正しいか検算する

なぜ必要か:
  2026-08-23に「業種別ランキングの前日比が17業種すべて誤り」というバグが見つかった。
  医薬品は +3.80% と表示していたが実際は −1.47% で、符号まで逆だった。
  しかも**このバグは偶然見つかった**。Actionsは緑、例外も出ず、
  数字が入っている以上どの点検も異常なしと判定していた。

  「壊れて止まる」バグは検知できるが、「もっともらしい嘘の数字を出す」バグは
  自分では気づけない。だから**独立した経路でもう一度取得して突き合わせる**。

設計の考え方:
  ・同じAPIの同じフィールドを二度読んでも意味がない。必ず別経路で照合する
    （yfinanceライブラリ経由 vs チャートAPI直叩き、など）
  ・誤差ゼロは求めない。取得時刻の差で小数点以下はずれる。
    ずれの大きさが「意味を変えるか」で判定する
  ・符号が逆になるのは最悪の誤り。別扱いで強く警告する

⚠️ ここで検算するのは「利用者が目にする数字」に限る。
   内部の中間値まで見ると量が多すぎて、肝心な誤りが埋もれる。

run() → 監査結果 / run_audit_alert() → 異常時のみ通知
"""
import json
import statistics
import traceback
from datetime import datetime

from src.utils import setup_logger, BASE_DIR, get_jst_now

logger = setup_logger("data_audit")

_STATE_FILE = BASE_DIR / "data" / "audit_state.json"

# 変化率のずれがこの割合を超えたら異常とみなす（%ポイント）
_PCT_TOL = 0.35
# 価格のずれがこの割合を超えたら異常（取得時刻の差を考慮して緩めに）
_PRICE_TOL = 0.02      # 2%
# 符号が逆なら、大きさに関わらず重大
_SIGN_MIN = 0.3        # ただし±0.3%未満の微小な値は符号を問わない


def _yf_change(sym: str) -> tuple:
    """
    yfinanceライブラリ経由で前日比を出す（照合用の独立経路）。
    本体はチャートAPIを直接叩いているので、経路が違えば同じ誤りは再現しない。
    """
    try:
        import yfinance as yf
        h = yf.Ticker(sym).history(period="5d")
        if h is None or len(h) < 2:
            return None, None
        cur, prev = float(h["Close"].iloc[-1]), float(h["Close"].iloc[-2])
        if not prev:
            return None, None
        return cur, (cur - prev) / prev * 100
    except Exception:
        logger.debug(traceback.format_exc())
        return None, None


def _judge(name: str, ours: float, theirs: float, kind: str = "pct") -> dict:
    """1件の突き合わせ結果。ずれの意味づけまで返す。"""
    if ours is None or theirs is None:
        return {"name": name, "status": "skip", "reason": "照合値を取得できず"}

    if kind == "pct":
        diff = abs(ours - theirs)
        # 符号の逆転は最悪の誤り。「上がっている」と読んで買う判断につながる
        flipped = (ours * theirs < 0 and
                   abs(ours) >= _SIGN_MIN and abs(theirs) >= _SIGN_MIN)
        if flipped:
            return {"name": name, "status": "critical", "ours": ours,
                    "theirs": theirs, "diff": round(diff, 2),
                    "reason": f"符号が逆（表示{ours:+.2f}% / 実際{theirs:+.2f}%）"}
        if diff > _PCT_TOL:
            return {"name": name, "status": "warn", "ours": ours,
                    "theirs": theirs, "diff": round(diff, 2),
                    "reason": f"{diff:.2f}ポイントのずれ"}
        return {"name": name, "status": "ok", "ours": ours, "theirs": theirs,
                "diff": round(diff, 2)}

    rel = abs(ours - theirs) / theirs if theirs else 1
    if rel > _PRICE_TOL:
        return {"name": name, "status": "warn", "ours": ours, "theirs": theirs,
                "reason": f"{rel*100:.1f}%のずれ"}
    return {"name": name, "status": "ok", "ours": ours, "theirs": theirs}


# ── 各モジュールの検算 ─────────────────────────────────────────
def _audit_sector_ranking() -> list:
    """業種別ランキング（前回バグが出た箇所）。"""
    out = []
    try:
        from src.sector_ranking_jp import _fetch_one, ETFS
        for sym, name in list(ETFS.items())[:8]:
            d = _fetch_one(sym)
            if not d:
                continue
            ours = (d["price"] - d["prev"]) / d["prev"] * 100
            _, theirs = _yf_change(sym)
            out.append({**_judge(f"業種:{name}", ours, theirs), "module": "sector_ranking_jp"})
    except Exception:
        logger.error("業種ランキングの監査に失敗", exc_info=True)
    return out


def _audit_us_movers() -> list:
    """米国ムーバー（前日終値の判定を使っている）。"""
    out = []
    try:
        from src.us_movers import _scan_one, _watchlist
        for sym, name, sec in _watchlist()[:8]:
            r = _scan_one(sym, name, sec)
            if not r:
                continue
            _, theirs = _yf_change(sym)
            out.append({**_judge(f"米国:{name}", r["chg_pct"], theirs),
                        "module": "us_movers"})
    except Exception:
        logger.error("米国ムーバーの監査に失敗", exc_info=True)
    return out


def _audit_nikkei_impact() -> list:
    """日経寄与度（構成銘柄の前日比）。"""
    out = []
    try:
        from src.nikkei_impact import _fetch, CONSTITUENTS
        for sym, name, _ in CONSTITUENTS[:8]:
            d = _fetch(sym)
            if not d or not d["prev"]:
                continue
            ours = (d["cur"] - d["prev"]) / d["prev"] * 100
            _, theirs = _yf_change(sym)
            out.append({**_judge(f"日経寄与:{name}", ours, theirs),
                        "module": "nikkei_impact"})
    except Exception:
        logger.error("日経寄与度の監査に失敗", exc_info=True)
    return out


def _audit_prices() -> list:
    """
    主要指標の価格そのもの。
    変化率が合っていても、水準がずれていれば別の問題（シンボル取り違え等）。
    """
    out = []
    try:
        from src.fetch_prices import run as fp
        prices, _ = fp()
        for sym, label in (("^N225", "日経平均"), ("^GSPC", "S&P500"),
                           ("USDJPY=X", "ドル円"), ("^VIX", "VIX")):
            p = (prices.get(sym) or {}).get("latest")
            cur, _ = _yf_change(sym)
            out.append({**_judge(f"価格:{label}", p, cur, kind="price"),
                        "module": "fetch_prices"})
    except Exception:
        logger.error("価格の監査に失敗", exc_info=True)
    return out


def _audit_gap() -> list:
    """窓開け（始値と前日終値を使う）。"""
    out = []
    try:
        import yfinance as yf
        from src.gap_scanner import _scan_one as gap_scan, WATCH
        for sym, name in WATCH[:6]:
            r = gap_scan(sym, name)
            if not r:
                continue
            h = yf.Ticker(sym).history(period="5d")
            if h is None or len(h) < 2:
                continue
            o, pc = float(h["Open"].iloc[-1]), float(h["Close"].iloc[-2])
            theirs = (o - pc) / pc * 100 if pc else None
            out.append({**_judge(f"窓:{name}", r["gap_pct"], theirs),
                        "module": "gap_scanner"})
    except Exception:
        logger.error("窓開けの監査に失敗", exc_info=True)
    return out


_AUDITS = (
    ("業種別ランキング", _audit_sector_ranking),
    ("米国ムーバー", _audit_us_movers),
    ("日経寄与度", _audit_nikkei_impact),
    ("主要価格", _audit_prices),
    ("窓開け", _audit_gap),
)


def run() -> dict:
    logger.info("=== データ正確性の監査 ===")
    rows = []
    for label, fn in _AUDITS:
        try:
            r = fn()
            rows += r
            ng = sum(1 for x in r if x["status"] in ("warn", "critical"))
            logger.info(f"  {label}: {len(r)}件中 異常{ng}件")
        except Exception:
            logger.error(f"{label} の監査に失敗", exc_info=True)

    critical = [r for r in rows if r["status"] == "critical"]
    warn = [r for r in rows if r["status"] == "warn"]
    ok = [r for r in rows if r["status"] == "ok"]
    skip = [r for r in rows if r["status"] == "skip"]

    if critical:
        logger.error(f"🚨 符号が逆の項目が {len(critical)}件あります")
        for c in critical:
            logger.error(f"   {c['name']}: {c['reason']}")
    elif warn:
        logger.warning(f"⚠️ ずれのある項目が {len(warn)}件")
    else:
        logger.info(f"✅ 検算した{len(ok)}件すべて一致")

    return {
        "available": True,
        "checked_at": get_jst_now().strftime("%Y-%m-%d %H:%M"),
        "total": len(rows), "ok": len(ok),
        "warn": warn, "critical": critical, "skip": len(skip),
        "rows": rows,
        "healthy": not critical and not warn,
    }


def build_message(r: dict) -> str:
    bad = r["critical"] + r["warn"]
    lines = ["🔎 *データの検算で異常を検出*",
             f"⏰ {r['checked_at']}",
             "━━━━━━━━━━━━━━", ""]
    if r["critical"]:
        lines.append("🚨 *符号が逆になっている項目*")
        lines.append("　（上昇と下落が逆に表示されています）")
        for c in r["critical"]:
            lines.append(f"　❌ {c['name']}: {c['reason']}")
        lines.append("")
    if r["warn"]:
        lines.append("⚠️ *値がずれている項目*")
        for w in r["warn"][:8]:
            lines.append(f"　・{w['name']}: {w['reason']}")
        lines.append("")
    lines += [f"検算 {r['total']}件中 {len(bad)}件で不一致。",
              "別経路で取り直した値と突き合わせています。",
              "レポートの数字を鵜呑みにせず、原因の確認をお願いします。"]
    return "\n".join(lines)[:4000]


def run_audit_alert() -> bool:
    """
    cloud_run から呼ぶ。異常があるときだけ通知する。
    正常時に鳴らすと読み飛ばされ、肝心なときに気づけなくなる。
    """
    try:
        r = run()
        if r["healthy"]:
            return False
        skey = get_jst_now().strftime("%Y-%m-%d")
        try:
            st = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            st = {}
        if st.get("session") == skey:
            logger.info("本日は通知済みのためスキップ")
            return False

        from src.notify_telegram import send_message
        ok = send_message(build_message(r))
        if ok:
            try:
                _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
                _STATE_FILE.write_text(json.dumps(
                    {"session": skey, "ts": datetime.now().isoformat(),
                     "critical": len(r["critical"]), "warn": len(r["warn"])},
                    ensure_ascii=False), encoding="utf-8")
            except Exception:
                logger.error("状態の保存に失敗", exc_info=True)
            logger.warning(f"データ異常を通知（重大{len(r['critical'])}/"
                           f"注意{len(r['warn'])}）")
        return bool(ok)
    except Exception:
        logger.error("データ監査に失敗", exc_info=True)
        return False


if __name__ == "__main__":
    import io, sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    r = run()
    print(f"\n検算 {r['total']}件 / 一致 {r['ok']}件 / "
          f"ずれ {len(r['warn'])}件 / 符号逆 {len(r['critical'])}件")
    for x in r["critical"] + r["warn"]:
        print(f"  ❌ {x['name']:24} {x.get('reason','')}")
    if r["healthy"]:
        print("  ✅ 異常なし")
