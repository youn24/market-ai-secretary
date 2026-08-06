"""
高信頼テクニカルシグナル検出（Step TS・アラート用）

「明確で信頼性の強いシグナルが出たときだけ知らせる」ための専用モジュール。
毎日出るような弱いシグナルは無視し、次の2条件を満たしたものだけ通知する:

  1) 単独でも希少・信頼性の高い節目シグナル（ゴールデンクロス/200日線ブレイク等）
  2) 弱〜中程度のシグナルでも「同じ方向に複数重なった（コンフルエンス）」場合

各シグナルは信頼度の重み(weight)を持ち、同方向の合計が ALERT_SCORE 以上で発火。
逆方向のシグナルが混在する場合は打ち消して減点する（迷いのある相場では鳴らさない）。

detect(symbol, name) → {"available", "direction", "score", "signals":[...], "price"}
run()               → 主要5銘柄を判定して発火分を返す
"""
import traceback
from src.utils import setup_logger

logger = setup_logger("technical_signal")

# 監視対象（主要指数のみ。個別株まで広げるとノイズになる）
WATCH = [
    ("^N225",    "日経平均"),
    ("NIY=F",    "日経225先物"),
    ("^GSPC",    "S&P500"),
    ("^IXIC",    "NASDAQ"),
    ("USDJPY=X", "ドル円"),
]

# 発火に必要な合計スコア（重み3の単独シグナル or 重み2×2の重なりで到達）
ALERT_SCORE = 3.0


def _sma(a, n):
    return sum(a[-n:]) / n if len(a) >= n else None


def _rsi(close, n=14):
    if len(close) < n + 1:
        return None
    gains = losses = 0.0
    for i in range(-n, 0):
        d = close[i] - close[i - 1]
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    if losses == 0:
        return 100.0
    rs = (gains / n) / (losses / n)
    return 100 - 100 / (1 + rs)


def _ema_series(a, p):
    k = 2 / (p + 1)
    out = [a[0]]
    for v in a[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def detect(symbol: str, name: str) -> dict:
    """1銘柄の高信頼シグナルを検出する。"""
    out = {"available": False, "symbol": symbol, "name": name, "signals": []}
    try:
        import yfinance as yf
        hist = yf.Ticker(symbol).history(period="1y")
        if hist is None or hist.empty or len(hist) < 210:
            return out
        close = [float(x) for x in hist["Close"].dropna().values]
        price = close[-1]

        bull, bear = [], []   # (ラベル, 重み)

        # ノイズ耐性: 凪相場での微小なクロス（ダマシ）を無視するための最低変動幅。
        # 直近20日の平均日次変動率を基準にし、それ未満の“かすり”は採用しない。
        import statistics as st
        moves = [abs(close[i] - close[i - 1]) / close[i - 1] * 100
                 for i in range(-20, 0)]
        atr_pct = st.mean(moves) if moves else 0.0
        min_gap = max(atr_pct * 0.5, 0.15)   # %。最低0.15%は離れていることを要求

        # ── ① 50日線 × 200日線（ゴールデン/デッドクロス）── 重み3: 年数回の中長期転換
        # 2本の線が張り付いたままの“ゼロ距離クロス”は方向性がなくダマシになりやすい。
        # クロス後に明確に離れている（0.3%以上）ものだけを本物として扱う。
        ma50, ma200 = _sma(close, 50), _sma(close, 200)
        p50, p200 = _sma(close[:-1], 50), _sma(close[:-1], 200)
        if None not in (ma50, ma200, p50, p200):
            sep50 = abs(ma50 - ma200) / ma200 * 100
            if sep50 >= 0.3:
                if ma50 > ma200 and p50 <= p200:
                    bull.append(("ゴールデンクロス（50日線が200日線を上抜け）", 3.0))
                elif ma50 < ma200 and p50 >= p200:
                    bear.append(("デッドクロス（50日線が200日線を下抜け）", 3.0))

        # ── ② 200日線ブレイク ── 重み3: 強気相場/弱気相場の境界
        # 本物の転換だけを拾うため2条件を課す:
        #   (a) 1日の平均変動幅を超える明確な突破（最低0.4%）＝“かすり”を除外
        #   (b) 直近20日の7割以上が線の反対側にいた ＝ レンジ内の往復を除外
        if ma200:
            prev_c = close[-2]
            gap = abs(price - ma200) / ma200 * 100
            recent = close[-21:-1]
            below = sum(1 for c in recent if c < ma200)
            if gap >= max(atr_pct, 0.4):
                if price > ma200 and prev_c <= p200 and below >= 14:
                    bull.append(("200日移動平均を上抜け（相場の分水嶺）", 3.0))
                elif price < ma200 and prev_c >= p200 and (len(recent) - below) >= 14:
                    bear.append(("200日移動平均を下抜け（相場の分水嶺）", 3.0))

        # ── ③ RSI 極端値からの反転 ── 重み2: 売られすぎ/買われすぎの解消
        rsi_now, rsi_prev = _rsi(close), _rsi(close[:-1])
        if rsi_now is not None and rsi_prev is not None:
            if rsi_prev < 30 <= rsi_now:
                bull.append((f"RSIが売られすぎ圏から反転（{rsi_prev:.0f}→{rsi_now:.0f}）", 2.0))
            elif rsi_prev > 70 >= rsi_now:
                bear.append((f"RSIが買われすぎ圏から反落（{rsi_prev:.0f}→{rsi_now:.0f}）", 2.0))

        # ── ④ MACDクロス ── 重み2（ゼロラインの正しい側なら+0.5でトレンド一致）
        e12, e26 = _ema_series(close, 12), _ema_series(close, 26)
        macd = [a - b for a, b in zip(e12, e26)]
        sig = _ema_series(macd, 9)
        # クロス後の乖離が min_gap 未満（=ほぼ重なったまま）ならダマシとして無視
        if len(macd) >= 2:
            sep = abs(macd[-1] - sig[-1]) / price * 100
            if sep >= min_gap * 0.3:
                if macd[-1] > sig[-1] and macd[-2] <= sig[-2]:
                    w = 2.5 if macd[-1] > 0 else 2.0
                    bull.append(("MACDが買いシグナルに転換", w))
                elif macd[-1] < sig[-1] and macd[-2] >= sig[-2]:
                    w = 2.5 if macd[-1] < 0 else 2.0
                    bear.append(("MACDが売りシグナルに転換", w))

        # ── ⑤ ボリンジャーのスクイーズ→ブレイク ── 重み2: 値動き拡大の初動
        import statistics as st
        if len(close) >= 140:
            sd20 = st.pstdev(close[-20:])
            ma20 = _sma(close, 20)
            width = sd20 / ma20 * 100 if ma20 else 0
            widths = []
            for i in range(-120, -1):
                seg = close[i - 20:i]
                m = sum(seg) / 20
                if m:
                    widths.append(st.pstdev(seg) / m * 100)
            if widths and width <= sorted(widths)[len(widths) // 5]:   # 直近120日で下位20%＝収縮
                if price > ma20 + 2 * sd20:
                    bull.append(("値動き収縮からの上放れ（ボリンジャー上限突破）", 2.0))
                elif price < ma20 - 2 * sd20:
                    bear.append(("値動き収縮からの下放れ（ボリンジャー下限割れ）", 2.0))

        # ── 集計: 同方向の合計から逆方向を差し引く（迷いのある相場は鳴らさない）──
        bull_s = sum(w for _, w in bull)
        bear_s = sum(w for _, w in bear)
        net = bull_s - bear_s
        direction = "bull" if net > 0 else "bear" if net < 0 else "neutral"
        score = abs(net)
        picked = bull if direction == "bull" else bear if direction == "bear" else []

        out.update({
            "available": bool(picked) and score >= ALERT_SCORE,
            "direction": direction,
            "score": round(score, 1),
            "signals": [{"label": l, "weight": w} for l, w in picked],
            "price": price,
            "rsi": round(rsi_now, 1) if rsi_now is not None else None,
            "ma200": round(ma200, 2) if ma200 else None,
        })
        return out
    except Exception:
        logger.debug(traceback.format_exc())
        return out


def run() -> dict:
    """主要銘柄を判定し、発火した高信頼シグナルのみ返す。"""
    hits = []
    for sym, name in WATCH:
        d = detect(sym, name)
        if d.get("available"):
            hits.append(d)
            logger.info(f"高信頼シグナル: {name} {d['direction']} score={d['score']}")
    hits.sort(key=lambda x: x["score"], reverse=True)
    if not hits:
        logger.info(f"高信頼テクニカルシグナルなし（{len(WATCH)}銘柄チェック済み）")
    return {"available": bool(hits), "hits": hits}


if __name__ == "__main__":
    r = run()
    for h in r["hits"]:
        print(h["name"], h["direction"], h["score"])
        for s in h["signals"]:
            print("  -", s["label"], s["weight"])
