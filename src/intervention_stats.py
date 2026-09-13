"""
src/intervention_stats.py — 為替介入の実績・統計・警戒度スコア

財務省が公表する「外国為替平衡操作の実施状況」（1991年4月〜）の
公式CSVを直接取得し、円買い介入（＝円安を止める介入）の実績を集計する。

  データ元: https://www.mof.go.jp/policy/international_policy/reference/feio/
            foreign_exchange_intervention_operations.csv
  ※日次の実績は四半期ごとに公表される（＝直近数ヶ月は未反映のことがある）

【この実装の考え方】
「次にいつ介入するか」を当てることはできない。できるのは
  “過去に介入が起きたときの条件” と “今の条件” がどれだけ似ているか
を測ることだけ。よって出力は確率ではなく「条件一致度スコア」として扱う。

過去データから読み取れた重要な性質:
  1. 水準だけでは決まらない。2022年以降の介入は144〜162円と幅がある
  2. 「1ヶ月で何円円安が進んだか」という“速さ”が効く
     （財務省は一貫して「急激な変動」「投機的な動き」を理由に挙げている）
  3. 一度介入すると数日〜数週間のうちに追撃介入が続く傾向がある
     2026年5月の2回は、初回介入で円高方向に振れている最中に実施された
     → 直近に介入があるときは「円高方向だから安心」とは言えない
"""

import io
import csv
import traceback
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

from src.utils import setup_logger

logger = setup_logger("intervention_stats")

JST = timezone(timedelta(hours=9))
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
_MOF_CSV = ("https://www.mof.go.jp/policy/international_policy/reference/"
            "feio/foreign_exchange_intervention_operations.csv")

_MONTHS = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
           "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}

# 「近代の介入」とみなす起点（この頃から水準・規模の性質が変わった）
_MODERN_FROM = "2022-01-01"


def fetch_interventions() -> pd.DataFrame | None:
    """財務省CSVを取得して介入実績のDataFrameを返す"""
    try:
        r = requests.get(_MOF_CSV, headers=_HEADERS, timeout=60)
        if r.status_code != 200:
            logger.warning(f"財務省CSV取得失敗 status={r.status_code}")
            return None
        text = None
        for enc in ("cp932", "utf-8-sig", "utf-8"):
            try:
                text = r.content.decode(enc)
                break
            except Exception:
                continue
        if text is None:
            return None

        recs, year, month = [], None, None
        for row in csv.reader(io.StringIO(text)):
            if len(row) < 8 or "期計" in row[0]:
                continue
            y, m, d = row[3].strip(), row[4].strip(), row[5].strip()
            if y:
                year = y
            if m:
                month = m
            if not d or not year or month not in _MONTHS:
                continue
            amt, pair = row[6].replace(",", "").strip(), row[7].strip()
            if not amt or not pair:
                continue
            try:
                recs.append({
                    "date":   pd.Timestamp(int(year), _MONTHS[month], int(d)),
                    "amount": float(amt),          # 億円
                    "pair":   pair,
                })
            except Exception:
                continue

        if not recs:
            return None
        df = pd.DataFrame(recs)
        # 円買い＝円安を止める介入 / 円売り＝円高を止める介入
        df["kind"] = df["pair"].apply(
            lambda p: "yen_buy" if "日本円買い" in p
            else ("yen_sell" if "日本円売り" in p else "other"))
        return df
    except Exception:
        logger.error("財務省CSV取得エラー")
        logger.debug(traceback.format_exc())
        return None


def _usdjpy_series() -> pd.Series | None:
    try:
        import yfinance as yf
        df = yf.Ticker("USDJPY=X").history(period="max", interval="1d",
                                           auto_adjust=True)
        if df is None or df.empty:
            return None
        s = df["Close"].dropna()
        s.index = pd.to_datetime(s.index).tz_localize(None)
        return s
    except Exception:
        logger.debug(traceback.format_exc())
        return None


def _level_at(s: pd.Series, d) -> float | None:
    w = s[:d]
    return float(w.iloc[-1]) if len(w) else None


def _speed_at(s: pd.Series, d, bars: int = 22) -> float | None:
    """その日までの直近1ヶ月で何円動いたか（＋＝円安）"""
    w = s[:d]
    return float(w.iloc[-1] - w.iloc[-bars]) if len(w) > bars else None


def analyze() -> dict:
    """
    実績の集計と、現在の条件一致度スコアを算出する。
    返り値: {available, stats, current, score, level_label, telegram_message}
    """
    result = {"available": False}
    try:
        df = fetch_interventions()
        s  = _usdjpy_series()
        if df is None or s is None:
            return result

        buy  = df[df["kind"] == "yen_buy"].copy()
        sell = df[df["kind"] == "yen_sell"]
        if buy.empty:
            return result

        buy["level"] = buy["date"].apply(lambda d: _level_at(s, d))
        buy["speed"] = buy["date"].apply(lambda d: _speed_at(s, d))
        modern = buy[buy["date"] >= _MODERN_FROM].dropna(subset=["level"])

        now_px    = float(s.iloc[-1])
        now_speed = float(s.iloc[-1] - s.iloc[-22]) if len(s) > 22 else 0.0
        last_date = buy["date"].max()
        days_since = (pd.Timestamp(datetime.now(JST).date()) - last_date).days

        # ── 条件一致度スコア（0〜100・確率ではない）──
        score, reasons = 0, []

        # ① 水準（2022年以降の介入水準と比べてどこか）
        if not modern.empty:
            lo, hi = modern["level"].min(), modern["level"].max()
            if now_px >= hi:
                score += 45; reasons.append(f"過去の介入最高水準({hi:.1f}円)を上回っている")
            elif now_px >= modern["level"].median():
                score += 35; reasons.append(f"過去の介入水準の中央値({modern['level'].median():.1f}円)超え")
            elif now_px >= lo:
                score += 20; reasons.append(f"過去の介入レンジ({lo:.1f}〜{hi:.1f}円)の中にいる")
            else:
                reasons.append(f"過去の介入レンジ({lo:.1f}円〜)より下")

        # ② 速さ（財務省が重視する「急激な変動」）
        if now_speed >= 6.0:
            score += 35; reasons.append(f"1ヶ月で{now_speed:+.1f}円の急速な円安")
        elif now_speed >= 3.0:
            score += 20; reasons.append(f"1ヶ月で{now_speed:+.1f}円の円安が進行")
        elif now_speed <= -3.0:
            reasons.append(f"1ヶ月で{now_speed:+.1f}円と円高方向")

        # ③ 追撃リスク（直近に介入があると連続しやすい）
        if days_since <= 30:
            score += 25; reasons.append(f"{days_since}日前に介入済み（追撃が続きやすい局面）")
        elif days_since <= 90:
            score += 10; reasons.append(f"{days_since}日前に介入（警戒は継続）")

        score = max(0, min(100, score))
        if   score >= 70: label, emoji = "最大警戒", "🚨"
        elif score >= 50: label, emoji = "高警戒",   "🔴"
        elif score >= 30: label, emoji = "警戒",     "🟠"
        elif score >= 15: label, emoji = "やや注意", "🟡"
        else:             label, emoji = "低い",     "🟢"

        stats = {
            "buy_count":   len(buy),
            "buy_total":   float(buy["amount"].sum()),
            "sell_count":  len(sell),
            "sell_total":  float(sell["amount"].sum()),
            "first_date":  str(df["date"].min().date()),
            "last_date":   str(last_date.date()),
            "modern":      modern,
            "biggest":     buy.loc[buy["amount"].idxmax()],
        }
        current = {"price": now_px, "speed_1m": now_speed,
                   "days_since": int(days_since)}

        result.update({
            "available": True, "stats": stats, "current": current,
            "score": score, "level_label": label, "emoji": emoji,
            "reasons": reasons,
        })
        result["telegram_message"] = build_message(result)
        logger.info(f"✅ 介入分析: 円買い{len(buy)}回 / 警戒度{score}({label})")
        return result
    except Exception:
        logger.error("介入分析エラー")
        logger.debug(traceback.format_exc())
        return result


def _cluster(modern: pd.DataFrame) -> list:
    """年ごとに介入をまとめる"""
    out = []
    for year, g in modern.groupby(modern["date"].dt.year):
        out.append({
            "year": int(year), "count": len(g),
            "total": float(g["amount"].sum()),
            "lo": float(g["level"].min()), "hi": float(g["level"].max()),
        })
    return out


def build_message(res: dict) -> str:
    st, cur = res["stats"], res["current"]
    modern  = st["modern"]
    big     = st["biggest"]

    lines = [
        f"{res['emoji']} *為替介入レポート* — 現在の警戒度: *{res['level_label']}*"
        f"（{res['score']}/100）",
        "━━━━━━━━━━━━━━",
        "",
        "*📊 これまでの実績（財務省公表）*",
        f"円買い介入（円安を止める）: *{st['buy_count']}回* / 累計 {st['buy_total']/10000:.1f}兆円",
        f"円売り介入（円高を止める）: {st['sell_count']}回 / 累計 {st['sell_total']/10000:.1f}兆円",
        f"最大の1日: {big['date'].date()} に {big['amount']/10000:.2f}兆円",
        f"直近の介入: *{st['last_date']}*（{cur['days_since']}日前）",
    ]

    # 近年のクラスター
    cl = _cluster(modern)
    if cl:
        lines += ["", "*🗓 2022年以降の介入*"]
        for c in cl:
            lines.append(f"　{c['year']}年: {c['count']}回 / {c['total']/10000:.1f}兆円"
                         f"（{c['lo']:.0f}〜{c['hi']:.0f}円台）")

    # 統計
    if not modern.empty:
        lines += [
            "",
            "*📐 介入が起きたときの条件*",
            f"　ドル円の水準: {modern['level'].min():.1f}〜{modern['level'].max():.1f}円"
            f"（中央 {modern['level'].median():.1f}円）",
        ]
        sp = modern["speed"].dropna()
        if len(sp):
            lines.append(f"　直前1ヶ月の円安幅: 平均 {sp.mean():+.1f}円"
                         f"（最大 {sp.max():+.1f}円）")

    # 現在地と判定根拠
    lines += [
        "",
        "*🔍 いまの状況*",
        f"　ドル円 `{cur['price']:.2f}円` / 直近1ヶ月 `{cur['speed_1m']:+.1f}円`",
    ]
    for r in res["reasons"]:
        lines.append(f"　・{r}")

    lines += [
        "",
        "⚠️ このスコアは「過去に介入が起きたときの条件と今がどれだけ似ているか」"
        "を測ったもので、介入の確率ではありません。"
        "実際の判断は財務省・日銀の裁量であり、事前に知ることはできません。",
        "※日次の介入実績は四半期ごとの公表のため、直近分は未反映の場合があります。",
    ]
    return "\n".join(lines)


def run(*_args, **_kwargs) -> dict:
    return analyze()


def run_report() -> bool:
    """週次ワークフロー等から呼ぶ。Telegramへ1通送る。"""
    try:
        res = analyze()
        if not res.get("available"):
            logger.info("介入レポート: 送信スキップ")
            return False
        from src.notify_telegram import send_message
        ok = send_message(res["telegram_message"])
        if ok:
            logger.info("✅ 為替介入レポート送信")
        return bool(ok)
    except Exception:
        logger.error("介入レポート送信エラー")
        logger.debug(traceback.format_exc())
        return False


if __name__ == "__main__":
    run_report()
