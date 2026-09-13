"""
src/signal_reliability.py — シグナルの「実績」と「だましリスク」

シグナルが出たかどうかより、**そのシグナルが過去どれだけ機能したか**の方が
実戦では重要になる。ここでは2つを扱う。

  ① 実績（バックテスト）
     過去10年のドル円で、各シグナル発生後に
     「+1ATR に先に届いたか、-1ATR に先に届いたか」を20本以内で判定し、
     勝率を出す（トリプルバリア法の簡易版）。

  ② だましリスク
     実データ検証で分かった「だましが増える条件」を点数化する。

────────────────────────────────────────────────────────
【2016-2026年のドル円 実データ検証で分かったこと】

1. 買いと売りで信頼度がまったく違う（ドル円の長期上昇バイアス）
     ゴールデンクロス 59%  ／ デッドクロス   38%
     MACD上抜け      55%  ／ MACD下抜け     42%
   → 売りシグナルは単体ではコイン投げ以下。過大評価してはいけない。

2. 週足との一致は「買いには効くが、売りには効かない」
     買い: 週足一致 66% ／ レンジ 51% ／ 逆行 42%   ← 24ptの差
     売り: 週足一致 38% ／ レンジ 48% ／ 逆行 38%   ← 差が出ない
   → マルチタイムフレームの効果は方向によって非対称。

3. ボラティリティ急拡大中はだましが激増
     ATR比 1.3倍以上 37% ／ 1.0-1.3倍 54% ／ 1.0倍未満 45%
   → 荒れている最中のブレイクは信用しない。

4. ローソク足のヒゲ分析はFXでは使えない
     yfinanceのFX日足は Open がほぼ Close と同値（実体比の中央値1%）。
     実体・ヒゲを使った判定は成立しないため、意図的に採用していない。
────────────────────────────────────────────────────────
"""

import json
import traceback
from datetime import timedelta

import numpy as np
import pandas as pd

from src.utils import setup_logger, get_jst_now, BASE_DIR

logger = setup_logger("signal_reliability")

_STATS_FILE = BASE_DIR / "data" / "signal_stats.json"
_CACHE_DAYS = 7            # 実績は週1回だけ再計算すればよい

_HORIZON  = 20             # 何本先まで見るか
_ATR_MULT = 1.0            # 勝ち負けの判定幅（±1ATR）

# 検証で分かった「だましが増える条件」の配点
_RISK_VOL_SPIKE   = 30     # ボラ急拡大
_RISK_SELL_BIAS   = 25     # 売り方向（構造的に実績が低い）
_RISK_AGAINST_WK  = 25     # 週足と逆行
_RISK_WK_RANGE    = 10     # 週足がレンジ
_RISK_EVENT_NEAR  = 20     # 重要指標が近い


# ── 共通計算 ────────────────────────────────────────────────────
def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["High"], df["Low"], df["Close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()],
                   axis=1).max(axis=1)
    return tr.rolling(n).mean()


def _barrier_hit(c: pd.Series, atr: pd.Series, i: int, direction: int) -> bool | None:
    """i本目のシグナルが機能したか（+1ATRと-1ATRのどちらに先に届いたか）"""
    if i + _HORIZON >= len(c) or pd.isna(atr.iloc[i]):
        return None
    entry, a = c.iloc[i], atr.iloc[i] * _ATR_MULT
    fut = c.iloc[i + 1: i + 1 + _HORIZON].values
    up   = next((j for j, v in enumerate(fut) if v >= entry + a), 999)
    down = next((j for j, v in enumerate(fut) if v <= entry - a), 999)
    if up == 999 and down == 999:
        return None                      # どちらにも届かず＝判定不能
    return (up < down) if direction == 1 else (down < up)


def _cross_indices(series: pd.Series) -> tuple[list, list]:
    """符号が変わった位置（上抜け, 下抜け）を返す"""
    d = np.sign(series).diff()
    up   = [i for i, v in enumerate(d.values) if v == 2]
    down = [i for i, v in enumerate(d.values) if v == -2]
    return up, down


# ── ① 実績（バックテスト）────────────────────────────────────────
def _compute_stats(symbol: str = "USDJPY=X") -> dict:
    """過去10年から各シグナルの勝率を算出する"""
    import yfinance as yf
    df = yf.Ticker(symbol).history(period="10y", interval="1d",
                                   auto_adjust=True).dropna(subset=["Close"])
    if df is None or len(df) < 300:
        return {}
    c   = df["Close"]
    atr = _atr(df)

    ma25, ma75, ma200 = c.rolling(25).mean(), c.rolling(75).mean(), c.rolling(200).mean()
    macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    hist = macd - macd.ewm(span=9, adjust=False).mean()

    gc, dc         = _cross_indices(ma25 - ma75)
    ma200u, ma200d = _cross_indices(c - ma200)
    macdu, macdd   = _cross_indices(hist)

    def rate(idxs, direction):
        w = t = 0
        for i in idxs:
            r = _barrier_hit(c, atr, i, direction)
            if r is None:
                continue
            t += 1
            w += 1 if r else 0
        return {"win": w, "total": t,
                "rate": round(w / t * 100, 1) if t else None}

    stats = {
        "golden_cross": rate(gc, 1),
        "dead_cross":   rate(dc, -1),
        "ma200_up":     rate(ma200u, 1),
        "ma200_down":   rate(ma200d, -1),
        "macd_gc":      rate(macdu, 1),
        "macd_dc":      rate(macdd, -1),
    }
    stats["_meta"] = {
        "symbol": symbol,
        "from": str(df.index[0].date()), "to": str(df.index[-1].date()),
        "bars": len(df), "horizon": _HORIZON, "atr_mult": _ATR_MULT,
        "computed": get_jst_now().isoformat(),
    }
    return stats


def get_stats(force: bool = False) -> dict:
    """実績を取得（7日キャッシュ）"""
    if not force:
        try:
            st = json.loads(_STATS_FILE.read_text(encoding="utf-8"))
            ts = pd.Timestamp(st.get("_meta", {}).get("computed"))
            if (get_jst_now() - ts.to_pydatetime()).days < _CACHE_DAYS:
                return st
        except Exception:
            pass
    try:
        st = _compute_stats()
        if st:
            _STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
            _STATS_FILE.write_text(json.dumps(st, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
            logger.info("✅ シグナル実績を再計算しました")
        return st
    except Exception:
        logger.error("シグナル実績の計算エラー")
        logger.debug(traceback.format_exc())
        return {}


def win_rate_text(base_type: str) -> str:
    """アラートに添える実績の一文（サンプルが少なければ出さない）"""
    st = get_stats()
    r  = st.get(base_type) or {}
    if not r or r.get("rate") is None or r.get("total", 0) < 8:
        return ""
    mark = "🎯" if r["rate"] >= 60 else "🔶" if r["rate"] >= 50 else "⚠️"
    return (f"{mark} このシグナルの過去実績: *{r['rate']:.0f}%*"
            f"（{r['total']}回中{r['win']}回機能）")


# ── ② だましリスク ──────────────────────────────────────────────
def fakeout_risk(direction: str, weekly_trend: str = "range",
                 df: pd.DataFrame | None = None,
                 event_near: bool = False) -> dict:
    """
    だまし（シグナルが機能せず反転する）に遭いやすい度合いを点数化する。
    返り値: {score, level, emoji, reasons}
    """
    score, reasons = 0, []

    # 売り方向は構造的に実績が低い（検証: DC 38% / MACD下抜け 42%）
    if direction == "sell":
        score += _RISK_SELL_BIAS
        reasons.append("売り方向は過去実績が低い（ドル円は長期の上昇バイアス）")

    # 週足との関係（買いのときだけ明確に効く）
    if weekly_trend == "range":
        score += _RISK_WK_RANGE
        reasons.append("週足がレンジ＝ブレイクが失敗しやすい地合い")
    else:
        aligned = (direction == "buy" and weekly_trend == "up") or \
                  (direction == "sell" and weekly_trend == "down")
        if not aligned:
            score += _RISK_AGAINST_WK
            reasons.append("週足の流れに逆らう方向（検証では勝率が2割以上低下）")

    # ボラティリティ急拡大（検証: ATR比1.3倍以上で勝率37%）
    if df is not None and len(df) > 70:
        try:
            atr = _atr(df)
            ratio = float(atr.iloc[-1] / atr.rolling(60).mean().iloc[-1])
            if ratio >= 1.3:
                score += _RISK_VOL_SPIKE
                reasons.append(f"ボラティリティ急拡大中（平常の{ratio:.1f}倍）"
                               "＝値が荒れてダマシが増える")
        except Exception:
            logger.debug(traceback.format_exc())

    if event_near:
        score += _RISK_EVENT_NEAR
        reasons.append("重要指標の発表が近く、値が飛びやすい")

    score = min(100, score)
    if   score >= 55: level, emoji = "高", "🔴"
    elif score >= 30: level, emoji = "中", "🟠"
    else:             level, emoji = "低", "🟢"
    return {"score": score, "level": level, "emoji": emoji, "reasons": reasons}


# ── ③ ブレイク失敗（だまし確定）の検知 ──────────────────────────
def detect_failed_break(df: pd.DataFrame, lookback: int = 20,
                        within: int = 3) -> dict | None:
    """
    直近で高値/安値をブレイクしたのに、数本以内に戻ってしまった状態を検出する。
    ＝「だましが確定した」場面。反対方向への警戒サインになる。
    """
    if df is None or len(df) < lookback + within + 5:
        return None
    c = df["Close"]
    try:
        for back in range(1, within + 1):
            i = len(c) - 1 - back
            base_hi = float(c.iloc[i - lookback:i].max())
            base_lo = float(c.iloc[i - lookback:i].min())
            broke_up   = c.iloc[i] > base_hi
            broke_down = c.iloc[i] < base_lo
            now = float(c.iloc[-1])
            if broke_up and now < base_hi:
                return {"kind": "failed_break_up", "emoji": "🪤",
                        "label": "上抜けのダマシ（ブレイク失敗）",
                        "direction": "sell",
                        "desc": (f"直近高値 {base_hi:,.2f} を一度上抜けたが、"
                                 f"{back}本で {now:,.2f} まで押し戻された。"),
                        "tip": "上値追いは危険。戻り売りが優勢になりやすい。"}
            if broke_down and now > base_lo:
                return {"kind": "failed_break_down", "emoji": "🪤",
                        "label": "下抜けのダマシ（ブレイク失敗）",
                        "direction": "buy",
                        "desc": (f"直近安値 {base_lo:,.2f} を一度下抜けたが、"
                                 f"{back}本で {now:,.2f} まで戻した。"),
                        "tip": "投げ売りが一巡した形。買い戻しが入りやすい。"}
    except Exception:
        logger.debug(traceback.format_exc())
    return None


def build_report() -> str:
    """実績の一覧（週次レポート用）"""
    st = get_stats()
    if not st:
        return ""
    meta = st.get("_meta", {})
    names = {
        "golden_cross": "✨ ゴールデンクロス（買い）",
        "dead_cross":   "⚠️ デッドクロス（売り）",
        "ma200_up":     "🚀 200日線 上抜け（買い）",
        "ma200_down":   "🛑 200日線 下抜け（売り）",
        "macd_gc":      "📈 MACD上抜け（買い）",
        "macd_dc":      "📉 MACD下抜け（売り）",
    }
    lines = ["📊 *ドル円 シグナル実績（過去10年）*",
             f"{meta.get('from','')} 〜 {meta.get('to','')}",
             "━━━━━━━━━━━━━━", ""]
    for k, nm in names.items():
        r = st.get(k) or {}
        if r.get("rate") is None:
            continue
        mark = "🎯" if r["rate"] >= 60 else "🔶" if r["rate"] >= 50 else "⚠️"
        lines.append(f"{mark} {nm}  *{r['rate']:.0f}%*（{r['total']}回中{r['win']}回）")
    lines += ["",
              "※発生後20本以内に +1ATR と -1ATR のどちらへ先に到達したかで判定。",
              "※50%未満はコイン投げ以下＝単体では使えないシグナルです。"]
    return "\n".join(lines)


def run(*_args, **_kwargs) -> dict:
    st = get_stats()
    return {"available": bool(st), "stats": st,
            "telegram_message": build_report() if st else ""}


if __name__ == "__main__":
    print(build_report())
