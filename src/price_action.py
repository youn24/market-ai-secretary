"""
プライスアクション（Step PA）— 値動きそのものから状況を読む

扱う形:
  ① 支持線・抵抗線   … 何度も止められた価格帯。接近と突破を知らせる
  ② ブレイク後のリテスト … 抜けた線まで戻って支えられた形（本物のブレイクの証）
  ③ 押し目・戻りの完成 … トレンド中の一時的な逆行が終わり、再開した形
  ④ ダマシ（だまし抜け）… 抜けたと見せてすぐ戻る。逆方向に強く動きやすいとされる
  ⑤ 三角保ち合い     … 高値切り下げ×安値切り上げの収束。抜けた方向に走りやすい
  ⑥ フラッグ・ペナント … 急騰/急落のあとの小休止。元の方向へ再開しやすいとされる
  ⑦ トレンド構造     … 高値安値の切り上げ/切り下げ（旧 candlestick.py から移設）
  ⑧ ダブルトップ/ボトム（同上）
  ⑨ レンジブレイク（同上）

なぜ candlestick.py から分けたか:
  ローソク足は1〜3本の「形」、プライスアクションは数十本の「構造」を見る。
  同じ関数群に置くと、どちらの粒度で判断しているのか読めなくなる。
  移設であって複製ではない点に注意（同じ判定を二重に持たない）。

共通の考え方:
  ・水準の同一視は必ずATR基準で行う。「1円以内」のような絶対値は
    銘柄の株価水準によって意味が変わってしまう。
  ・完成していない形は出さない。三角保ち合いは「抜けたとき」に意味があり、
    収束しているだけの段階で通知すると毎日鳴る。

⚠️ 効果は src/pattern_validation.py で検証する。検証前に信頼度を語らない。

analyze(df) → 検出した形のリスト
"""
import traceback

import pandas as pd

from src.utils import setup_logger

logger = setup_logger("price_action")

# ⚠️ パターン名に回数などの可変値を入れないこと。
# 「15回意識された水準」「30回意識された水準」が別々の形として集計され、
# 検証でどれも件数不足になる（実際に一度そうなった）。可変値は desc に書く。
_SWING_LR = 3          # 前後この本数より高い/安い点をスイングとする
_LEVEL_TOL = 0.6       # 同じ水準とみなす許容（ATRの倍数）
_MIN_TOUCH = 3         # 支持/抵抗と認めるのに必要な接触回数
_NEAR_TOL = 0.8        # 「線に接近」とみなす距離（ATRの倍数）
_BREAK_MARGIN = 0.2    # 抜けたと認める余裕（ATRの倍数）
_FAKE_BARS = 3         # ダマシ判定の猶予（抜けてから戻るまでの本数）
_RECENT = 5            # 直近この本数以内に起きたものだけ拾う


def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["High"], df["Low"], df["Close"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def _swings(df: pd.DataFrame, lr: int = _SWING_LR) -> tuple:
    h, l = df["High"].tolist(), df["Low"].tolist()
    highs, lows = [], []
    for i in range(lr, len(h) - lr):
        if h[i] == max(h[i - lr:i + lr + 1]):
            highs.append(i)
        if l[i] == min(l[i - lr:i + lr + 1]):
            lows.append(i)
    return highs, lows


# ── ① 支持線・抵抗線 ──────────────────────────────────────────
def _levels(df, atr) -> list:
    """
    何度も止められた価格帯を洗い出す。

    スイングの高値・安値を集め、ATR基準で近いものを一つの束にする。
    束の中の点が多いほど、その価格帯は多くの参加者に意識されている。
    高値と安値を混ぜて数えるのは、一度抜けた抵抗線が支持線に変わる
    （役割転換）ため。区別すると同じ水準を二重に数えてしまう。
    """
    highs, lows = _swings(df)
    pts = ([(i, float(df["High"].iloc[i]), "high") for i in highs] +
           [(i, float(df["Low"].iloc[i]), "low") for i in lows])
    if len(pts) < _MIN_TOUCH:
        return []
    pts.sort(key=lambda x: x[1])

    clusters, cur = [], [pts[0]]
    for p in pts[1:]:
        if abs(p[1] - cur[-1][1]) <= atr * _LEVEL_TOL:
            cur.append(p)
        else:
            clusters.append(cur)
            cur = [p]
    clusters.append(cur)

    out = []
    for c in clusters:
        if len(c) < _MIN_TOUCH:
            continue
        price = sum(x[1] for x in c) / len(c)
        out.append({
            "price": price,
            "touches": len(c),
            "last_idx": max(x[0] for x in c),
        })
    out.sort(key=lambda x: -x["touches"])
    return out


def _pa_level(df, atr) -> dict | None:
    """現在値が、意識されている水準に接近／突破したかを見る。"""
    lv = _levels(df, atr)
    if not lv:
        return None
    close = float(df["Close"].iloc[-1])
    prev = float(df["Close"].iloc[-2])

    # 最も接触回数が多く、かつ現在値の近くにあるものを選ぶ
    near = [x for x in lv if abs(close - x["price"]) <= atr * 3]
    if not near:
        return None
    best = max(near, key=lambda x: x["touches"])
    price, touches = best["price"], best["touches"]

    # 突破したか（前の足では反対側にいたこと）
    if prev <= price + atr * _BREAK_MARGIN < close:
        return {"name": "抵抗線を突破",
                "dir": "buy", "need": "any",
                "desc": (f"{price:,.0f} は過去{touches}回止められてきた価格帯。"
                         f"そこを終値で上抜けた。"),
                "level": price, "touches": touches}
    if prev >= price - atr * _BREAK_MARGIN > close:
        return {"name": "支持線を割り込み",
                "dir": "sell", "need": "any",
                "desc": (f"{price:,.0f} は過去{touches}回支えられてきた価格帯。"
                         f"そこを終値で下抜けた。"),
                "level": price, "touches": touches}

    # 接近しているだけの場合は方向を断定しない（どちらに動くか未確定のため）
    if abs(close - price) <= atr * _NEAR_TOL and touches >= 4:
        side = "上" if close < price else "下"
        return {"name": "意識された水準に接近",
                "dir": "neutral", "need": "any",
                "desc": (f"{price:,.0f} は過去{touches}回止められてきた価格帯。"
                         f"現在値はその{side}すぐ近くにあり、抜けるか跳ね返るかの分岐点。"),
                "level": price, "touches": touches}
    return None


# ── ② ブレイク後のリテスト ────────────────────────────────────
def _pa_retest(df, atr) -> dict | None:
    """
    抜けた線まで戻って支えられた形。

    ブレイクは往々にしてダマシになるが、一度戻って同じ水準で
    跳ね返されると「その水準の役割が入れ替わった」ことの裏づけになる。
    教科書が「リテストを待て」と言うのはこのため。
    """
    if len(df) < 30:
        return None
    lv = _levels(df, atr)
    if not lv:
        return None
    close = float(df["Close"].iloc[-1])
    lows = df["Low"].tolist()
    highs = df["High"].tolist()
    closes = df["Close"].tolist()

    # 最も意識されている1本だけを見る。
    # 全ての水準を対象にすると、どこかの線には必ず当てはまってしまい、
    # 実測で32%の日に発火した（＝毎日出るサインで意味がない）。
    best = max(lv, key=lambda x: x["touches"])
    price = best["price"]
    n = len(df)

    # 抜けたのは直近20〜4本前まで（戻る余地を残すため直近3本は除く）
    broke_up = broke_dn = None
    for k in range(20, 3, -1):
        i = n - k
        if i < 1:
            continue
        if closes[i - 1] <= price < closes[i]:
            broke_up = i
        if closes[i - 1] >= price > closes[i]:
            broke_dn = i

    # 戻ってきたのは「直近3本以内」であること。
    # いつ戻ったか問わないと、抜けた直後に一度触れただけで
    # その後何週間も条件を満たし続けてしまう。
    recent = range(max(0, n - 3), n)

    if broke_up is not None and broke_up < n - 3:
        touched = any(lows[j] <= price + atr * _NEAR_TOL for j in recent)
        held = close > price + atr * _BREAK_MARGIN
        if touched and held:
            return {"name": "上抜け後のリテスト成功", "dir": "buy", "need": "any",
                    "desc": (f"{price:,.0f}（過去{best['touches']}回意識された水準）を"
                             f"上抜けたあと、直近でその水準まで戻り、再び上へ離れた。"
                             f"抵抗が支持に変わった形。"),
                    "level": price}
    if broke_dn is not None and broke_dn < n - 3:
        touched = any(highs[j] >= price - atr * _NEAR_TOL for j in recent)
        held = close < price - atr * _BREAK_MARGIN
        if touched and held:
            return {"name": "下抜け後のリテスト成立", "dir": "sell", "need": "any",
                    "desc": (f"{price:,.0f}（過去{best['touches']}回意識された水準）を"
                             f"下抜けたあと、直近でその水準まで戻り、再び下へ離れた。"
                             f"支持が抵抗に変わった形。"),
                    "level": price}
    return None


# ── ③ 押し目・戻りの完成 ──────────────────────────────────────
def _pa_pullback(df, atr) -> dict | None:
    """
    トレンド中の一時的な逆行が終わり、元の方向へ再開した形。

    「押し目買い」の入り口を機械的に定義したもの。
    トレンドが出ていること・押しが浅すぎず深すぎないこと・
    直近の高値（安値）を取り返したこと、の三つを満たしたときだけ拾う。
    """
    if len(df) < 40:
        return None
    highs_i, lows_i = _swings(df)
    if len(highs_i) < 2 or len(lows_i) < 2:
        return None
    close = float(df["Close"].iloc[-1])

    h1, h2 = float(df["High"].iloc[highs_i[-2]]), float(df["High"].iloc[highs_i[-1]])
    l1, l2 = float(df["Low"].iloc[lows_i[-2]]), float(df["Low"].iloc[lows_i[-1]])

    # 上昇トレンド（高値・安値とも切り上げ）で、直近の押しから戻って高値を更新
    if h2 > h1 and l2 > l1 and lows_i[-1] > highs_i[-1]:
        depth = (h2 - l2) / h2 * 100
        if 1.0 <= depth <= 12.0 and close > h2:
            return {"name": "押し目からの再上昇", "dir": "buy", "need": "any",
                    "desc": (f"上昇トレンドの中で {depth:.1f}% の押しを入れたあと、"
                             f"直近高値 {h2:,.0f} を取り返した。"),
                    "depth": round(depth, 1)}
    # 下降トレンドの戻り売り
    if h2 < h1 and l2 < l1 and highs_i[-1] > lows_i[-1]:
        depth = (h2 - l2) / l2 * 100
        if 1.0 <= depth <= 12.0 and close < l2:
            return {"name": "戻りからの再下落", "dir": "sell", "need": "any",
                    "desc": (f"下降トレンドの中で {depth:.1f}% の戻りを入れたあと、"
                             f"直近安値 {l2:,.0f} を再び割り込んだ。"),
                    "depth": round(depth, 1)}
    return None


# ── ④ ダマシ（だまし抜け） ────────────────────────────────────
def _pa_fakeout(df, atr) -> dict | None:
    """
    抜けたと見せてすぐ戻る形。

    抜けにつられて入った参加者が、戻された時点で反対売買を迫られるため、
    元の方向より逆方向へ強く動きやすいとされる。
    ヒゲで一瞬抜けただけでは足りず、「終値で抜けたあと終値で戻る」ことを条件にする。
    """
    if len(df) < 30:
        return None
    closes = df["Close"].tolist()
    n = len(df)
    seg = df.iloc[-(25 + _FAKE_BARS):-_FAKE_BARS - 1]
    if len(seg) < 10:
        return None
    hi, lo = float(seg["High"].max()), float(seg["Low"].min())
    close = closes[-1]

    for k in range(1, _FAKE_BARS + 1):
        i = n - 1 - k
        if i < 1:
            continue
        # 上に抜けたあと、レンジ内へ戻ってきた
        if closes[i] > hi + atr * _BREAK_MARGIN and close < hi:
            return {"name": "上へのダマシ抜け", "dir": "sell", "need": "any",
                    "desc": (f"{hi:,.0f} を一度上抜けたが、{k}本で戻された。"
                             f"高値づかみが投げを迫られやすく、下へ振れやすい形。"),
                    "level": hi}
        if closes[i] < lo - atr * _BREAK_MARGIN and close > lo:
            return {"name": "下へのダマシ抜け", "dir": "buy", "need": "any",
                    "desc": (f"{lo:,.0f} を一度下抜けたが、{k}本で戻された。"
                             f"投げ売りが一巡し、上へ振れやすい形。"),
                    "level": lo}
    return None


# ── ⑤ 三角保ち合い ────────────────────────────────────────────
def _pa_triangle(df, atr) -> dict | None:
    """
    高値が切り下がり、安値が切り上がって値幅が狭まる形。

    抜けたときにだけ通知する。収束している最中に知らせても
    「どちらに抜けるか分からない」ままで、毎日鳴るだけになるため。
    """
    if len(df) < 40:
        return None
    highs_i, lows_i = _swings(df)
    if len(highs_i) < 3 or len(lows_i) < 3:
        return None

    hs = [float(df["High"].iloc[i]) for i in highs_i[-3:]]
    ls = [float(df["Low"].iloc[i]) for i in lows_i[-3:]]
    # 高値切り下げ・安値切り上げ＝収束
    if not (hs[0] > hs[1] > hs[2] and ls[0] < ls[1] < ls[2]):
        return None
    # 実際に幅が狭まっていること
    # 幅が縮んでいることが条件。0.7倍では厳しすぎて2年で1回しか成立しなかった。
    # 三角保ち合いの本質は「明確に狭まっていること」なので0.85倍まで許容する。
    if (hs[2] - ls[2]) >= (hs[0] - ls[0]) * 0.85:
        return None

    close = float(df["Close"].iloc[-1])
    prev = float(df["Close"].iloc[-2])
    if prev <= hs[2] < close:
        return {"name": "三角保ち合いを上放れ", "dir": "buy", "need": "any",
                "desc": (f"値幅が狭まったあと、上限 {hs[2]:,.0f} を上抜けた。"
                         f"溜まったエネルギーが上に出た形とされる。")}
    if prev >= ls[2] > close:
        return {"name": "三角保ち合いを下放れ", "dir": "sell", "need": "any",
                "desc": (f"値幅が狭まったあと、下限 {ls[2]:,.0f} を下抜けた。"
                         f"溜まったエネルギーが下に出た形とされる。")}
    return None


# ── ⑥ フラッグ・ペナント ──────────────────────────────────────
def _pa_flag(df, atr) -> dict | None:
    """
    急な動き（旗竿）のあと、小さく逆行しながら値幅が縮む形。

    旗竿の勢いが一服しただけで、元の方向へ再開しやすいとされる。
    三角保ち合いと違い「直前に大きな動きがあること」が必須条件で、
    そこを外すとただのもみ合いと区別できなくなる。
    """
    if len(df) < 30:
        return None
    closes = df["Close"].tolist()
    n = len(df)
    pole_end = n - 8          # 旗の部分を直近7本とみなす
    if pole_end < 12:
        return None

    pole_start = pole_end - 6
    pole = (closes[pole_end] - closes[pole_start]) / closes[pole_start] * 100
    # 「5%」の固定値は指数には大きすぎ、2年で一度も成立しなかった。
    # 旗竿と呼べるかは銘柄の平均的な値幅で測るべきなので、ATRの3倍を基準にする。
    pole_abs = abs(closes[pole_end] - closes[pole_start])
    if pole_abs < atr * 3:
        return None

    flag = df.iloc[pole_end:]
    f_hi, f_lo = float(flag["High"].max()), float(flag["Low"].min())
    width = (f_hi - f_lo) / f_lo * 100
    # 旗の部分は旗竿より明らかに小さいこと
    if (f_hi - f_lo) > pole_abs * 0.6:
        return None

    close = closes[-1]
    prev = closes[-2]
    if pole > 0 and prev <= f_hi < close:
        return {"name": "フラッグを上放れ", "dir": "buy", "need": "any",
                "desc": (f"{abs(pole):.1f}% 上昇したあとの小休止（値幅{width:.1f}%）を抜けた。"
                         f"上昇再開の形とされる。")}
    if pole < 0 and prev >= f_lo > close:
        return {"name": "フラッグを下放れ", "dir": "sell", "need": "any",
                "desc": (f"{abs(pole):.1f}% 下落したあとの小休止（値幅{width:.1f}%）を割った。"
                         f"下落再開の形とされる。")}
    return None


# ── ⑦⑧⑨ 既存分（candlestick.py から移設）─────────────────────
def _pa_structure(df, atr) -> dict | None:
    """
    高値・安値の切り上げ/切り下げ＝トレンドの骨格。
    移動平均より素直にトレンドを表す。
    """
    highs, lows = _swings(df)
    if len(highs) < 2 or len(lows) < 2:
        return None
    h1, h2 = df["High"].iloc[highs[-2]], df["High"].iloc[highs[-1]]
    l1, l2 = df["Low"].iloc[lows[-2]], df["Low"].iloc[lows[-1]]
    hh, hl = h2 > h1, l2 > l1
    if hh and hl:
        return {"name": "高値・安値ともに切り上げ", "dir": "buy", "need": "any",
                "desc": "上昇トレンドの骨格が保たれている形。"}
    if not hh and not hl:
        return {"name": "高値・安値ともに切り下げ", "dir": "sell", "need": "any",
                "desc": "下降トレンドの骨格が保たれている形。"}
    if hh and not hl:
        return {"name": "高値は更新も安値を切り下げ", "dir": "neutral", "need": "any",
                "desc": "値動きが荒くなり、方向が定まらなくなっている形。"}
    return None


def _pa_double(df, atr) -> dict | None:
    """ダブルトップ / ダブルボトム: 同じ水準で2度跳ね返された跡。"""
    highs, lows = _swings(df)
    if atr <= 0:
        return None
    n = len(df)
    if len(highs) >= 2:
        a, b = highs[-2], highs[-1]
        if 5 <= b - a <= 40 and n - b <= 5:
            ha, hb = float(df["High"].iloc[a]), float(df["High"].iloc[b])
            if abs(ha - hb) <= atr * 0.5 and float(df["Close"].iloc[-1]) < min(ha, hb):
                return {"name": "ダブルトップ", "dir": "sell", "need": "up",
                        "desc": f"{ha:,.0f}付近で2度跳ね返された。上値の重さを示す形。"}
    if len(lows) >= 2:
        a, b = lows[-2], lows[-1]
        if 5 <= b - a <= 40 and n - b <= 5:
            la, lb = float(df["Low"].iloc[a]), float(df["Low"].iloc[b])
            if abs(la - lb) <= atr * 0.5 and float(df["Close"].iloc[-1]) > max(la, lb):
                return {"name": "ダブルボトム", "dir": "buy", "need": "down",
                        "desc": f"{la:,.0f}付近で2度下げ止まった。下値の堅さを示す形。"}
    return None


def _pa_range_break(df, atr, look: int = 20) -> dict | None:
    """レンジ抜け: 一定期間もみ合った幅を抜けた瞬間。"""
    if len(df) < look + 5:
        return None
    seg = df.iloc[-(look + 1):-1]
    hi, lo = float(seg["High"].max()), float(seg["Low"].min())
    if hi <= lo:
        return None
    width = (hi - lo) / lo * 100
    c = float(df["Close"].iloc[-1])
    if width > 15:
        return None
    if c > hi and (c - hi) >= atr * 0.2:
        return {"name": f"{look}日のもみ合いを上抜け", "dir": "buy", "need": "any",
                "desc": f"{hi:,.0f}を上抜け（もみ合い幅{width:.1f}%）。"}
    if c < lo and (lo - c) >= atr * 0.2:
        return {"name": f"{look}日のもみ合いを下抜け", "dir": "sell", "need": "any",
                "desc": f"{lo:,.0f}を下抜け（もみ合い幅{width:.1f}%）。"}
    return None


_DETECTORS = (_pa_level, _pa_retest, _pa_pullback, _pa_fakeout,
              _pa_triangle, _pa_flag, _pa_structure, _pa_double, _pa_range_break)


def _prior_trend(c: pd.Series, bars: int = 5) -> str:
    if len(c) < bars + 2:
        return "flat"
    seg = c.iloc[-(bars + 1):-1]
    chg = (float(seg.iloc[-1]) - float(seg.iloc[0])) / float(seg.iloc[0]) * 100
    if chg <= -2.0:
        return "down"
    if chg >= 2.0:
        return "up"
    return "flat"


def analyze(df: pd.DataFrame) -> list:
    """最新の足に出ているプライスアクションを拾う。"""
    if df is None or len(df) < 40:
        return []
    for col in ("Open", "High", "Low", "Close"):
        if col not in df.columns:
            return []
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    if len(df) < 40:
        return []

    atr_s = _atr(df)
    atr = float(atr_s.iloc[-1]) if not pd.isna(atr_s.iloc[-1]) else 0.0
    if atr <= 0:
        return []

    trend = _prior_trend(df["Close"])
    found = []
    for fn in _DETECTORS:
        try:
            r = fn(df, atr)
        except Exception:
            logger.debug(traceback.format_exc())
            continue
        if not r:
            continue
        need = r.get("need")
        if need in ("up", "down") and trend != need:
            continue
        r["kind"] = "price_action"
        r["prior_trend"] = trend
        found.append(r)
    return found
