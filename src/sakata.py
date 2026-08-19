"""
酒田五法（Step SK）— 本間宗久の五法を機械判定する

五法の内訳:
  三山（さんざん）… 三つの山。中央が最も高い形が三尊天井（ヘッドアンドショルダー）
  三川（さんせん）… 三つの谷。中央が最も低い形が逆三尊
  三空（さんくう）… 窓が三つ続く。買われすぎ/売られすぎの極み
                     三空踏み上げ＝上に三空→売り転換 ／ 三空叩き込み＝下に三空→買い転換
  三兵（さんぺい）… 同色の足が三本続く。赤三兵＝上昇、三羽烏（黒三兵）＝下降
  三法（さんぽう）… 大きな足のあと小さな逆行が三本、その後に抜ける。トレンド継続

なぜ別モジュールにしたか:
  candlestick.py は西洋のローソク足パターンを1〜3本で見る。
  酒田五法は「三」を単位とする体系で、山や谷の並び（数十本規模）まで含む。
  判定の粒度が違うため混ぜると読みにくくなる。ただし重複には注意が必要で、
  明けの明星は本来「三川明けの明星」として五法の一部だが、
  candlestick.py 側で既に3本組として検出しているため、こちらでは扱わない
  （同じ形を二重に通知しないため）。

⚠️ 効果は src/pattern_validation.py で検証する。
   「江戸時代から伝わる」ことは「今の相場で通用する」ことの証拠にならない。
   検証前に信頼度を語らない、というのがこのプロジェクトの決まり。

analyze(df) → 検出した形のリスト
"""
import traceback

import pandas as pd

from src.utils import setup_logger

logger = setup_logger("sakata")

# 判定パラメータ。五法の教科書的な定義を数値に落としたもの。
_MIN_BODY_ATR = 0.4     # 実体がATRのこの倍数未満なら「大きな足」とみなさない
_SMALL_BODY = 0.5       # 三法の中の小さな足は、大きな足のこの割合以下
_SHOULDER_TOL = 0.5     # 三山の両肩の高さのズレ許容（ATR基準）
_HEAD_MARGIN = 0.3      # 中央の山は両肩よりATRのこの倍数以上高いこと
_SWING_LR = 3           # 前後この本数より高い/安い点をスイングとする
_MIN_SWING_GAP = 3      # 山と山は最低この本数離れていること
_MAX_SWING_GAP = 60     # 離れすぎは無関係
_RECENT = 8             # 完成が直近この本数以内のものだけ拾う（出来たてのみ）


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


def _body(row) -> tuple:
    o, c = float(row["Open"]), float(row["Close"])
    return abs(c - o), c > o


# ── 三山 / 三尊天井 ────────────────────────────────────────────
def _sanzan(df, atr) -> dict | None:
    """
    三山（三尊天井）: 山が三つ並び、中央が最も高い。
    天井を三度試して抜けられなかった＝上値の重さの証明、とされる。
    """
    highs, _ = _swings(df)
    if len(highs) < 3:
        return None
    a, b, c = highs[-3], highs[-2], highs[-1]
    if not (_MIN_SWING_GAP <= b - a <= _MAX_SWING_GAP):
        return None
    if not (_MIN_SWING_GAP <= c - b <= _MAX_SWING_GAP):
        return None
    if len(df) - 1 - c > _RECENT:
        return None                      # 古い形は拾わない

    ha, hb, hc = (float(df["High"].iloc[a]), float(df["High"].iloc[b]),
                  float(df["High"].iloc[c]))
    # 中央が頭、両肩は同程度の高さであること
    if hb < ha + atr * _HEAD_MARGIN or hb < hc + atr * _HEAD_MARGIN:
        return None
    if abs(ha - hc) > atr * _SHOULDER_TOL:
        return None

    # ネックライン（肩と肩の間の安値）を割ったかで完成を判定する。
    # 形だけできてもネックを割らなければ、まだ天井とは言えない。
    neck = float(df["Low"].iloc[a:c + 1].min())
    close = float(df["Close"].iloc[-1])
    broken = close < neck
    return {
        "name": "三尊天井（三山）", "dir": "sell", "need": "up",
        "desc": (f"高値を三度試し、中央が最も高い形。両肩 {ha:,.0f}／{hc:,.0f}、"
                 f"頭 {hb:,.0f}。" + ("首値 {:,.0f} を割り込み完成。".format(neck)
                                     if broken else f"首値 {neck:,.0f} を割れば完成。")),
        "confirmed": broken,
    }


def _sansen(df, atr) -> dict | None:
    """三川（逆三尊）: 谷が三つ並び、中央が最も低い。三尊天井の裏返し。"""
    _, lows = _swings(df)
    if len(lows) < 3:
        return None
    a, b, c = lows[-3], lows[-2], lows[-1]
    if not (_MIN_SWING_GAP <= b - a <= _MAX_SWING_GAP):
        return None
    if not (_MIN_SWING_GAP <= c - b <= _MAX_SWING_GAP):
        return None
    if len(df) - 1 - c > _RECENT:
        return None

    la, lb, lc = (float(df["Low"].iloc[a]), float(df["Low"].iloc[b]),
                  float(df["Low"].iloc[c]))
    if lb > la - atr * _HEAD_MARGIN or lb > lc - atr * _HEAD_MARGIN:
        return None
    if abs(la - lc) > atr * _SHOULDER_TOL:
        return None

    neck = float(df["High"].iloc[a:c + 1].max())
    close = float(df["Close"].iloc[-1])
    broken = close > neck
    return {
        "name": "逆三尊（三川）", "dir": "buy", "need": "down",
        "desc": (f"安値を三度試し、中央が最も低い形。両肩 {la:,.0f}／{lc:,.0f}、"
                 f"底 {lb:,.0f}。" + ("首値 {:,.0f} を上抜け完成。".format(neck)
                                     if broken else f"首値 {neck:,.0f} を抜ければ完成。")),
        "confirmed": broken,
    }


# ── 三空 ──────────────────────────────────────────────────────
def _sanku(df, atr) -> dict | None:
    """
    三空: 窓が三つ続く。

    窓が三つも空くのは一方向に偏りすぎた証拠で、
    「買い一色の極み＝そろそろ終わり」と読むのが五法の考え方。
    そのため三空踏み上げ（上に三空）は売り、三空叩き込み（下に三空）は買いになる。
    順張りではなく逆張りのサインである点が、他の形と大きく違う。
    """
    if len(df) < 5:
        return None
    o = df["Open"].tolist()
    c = df["Close"].tolist()
    h = df["High"].tolist()
    l = df["Low"].tolist()

    # 直近3本すべてが窓を開けているか（前の足の高値/安値を跨がずに始まる）
    up_gaps, down_gaps = [], []
    for k in (3, 2, 1):
        i = len(df) - k
        if o[i] > h[i - 1]:
            up_gaps.append((h[i - 1], o[i]))
        elif o[i] < l[i - 1]:
            down_gaps.append((l[i - 1], o[i]))

    if len(up_gaps) == 3:
        return {"name": "三空踏み上げ", "dir": "sell", "need": "up",
                "desc": ("上へ三日続けて窓を開けた。買いが一方向に偏りすぎた状態で、"
                         "五法では『買い尽くし』として売り転換のサインとされる。"),
                "confirmed": True}
    if len(down_gaps) == 3:
        return {"name": "三空叩き込み", "dir": "buy", "need": "down",
                "desc": ("下へ三日続けて窓を開けた。売りが出尽くした状態で、"
                         "五法では『売り尽くし』として買い転換のサインとされる。"),
                "confirmed": True}
    return None


# ── 三兵 ──────────────────────────────────────────────────────
def _sanpei(df, atr) -> dict | None:
    """
    三兵: 同じ色の足が三本続き、順に値を切り上げる（切り下げる）。
    赤三兵は上昇、三羽烏（黒三兵）は下降の勢いを表す。

    「先詰まり」の判定を入れているのは、三本目に長い上ヒゲが出た場合、
    勢いが続かず失速する形とされ、意味が変わるため。
    """
    if len(df) < 4:
        return None
    rows = [df.iloc[-3], df.iloc[-2], df.iloc[-1]]
    bodies = [_body(r) for r in rows]
    if any(b[0] < _MIN_BODY_ATR * atr for b in bodies):
        return None

    closes = [float(r["Close"]) for r in rows]
    opens = [float(r["Open"]) for r in rows]
    highs = [float(r["High"]) for r in rows]
    lows = [float(r["Low"]) for r in rows]

    if all(b[1] for b in bodies) and closes[0] < closes[1] < closes[2]:
        # 各足は前の足の実体の範囲内で始まるのが本来の形。
        # ただし完全に「終値以下」を求めると、わずかな窓開けで弾かれてしまう。
        # 五法が排除したいのは「飛び離れた寄り付き」なので、
        # ATRの3割までのズレは同じ形とみなす（実測で2回→現実的な頻度に改善）。
        tol = atr * 0.3
        if not (opens[1] <= closes[0] + tol and opens[2] <= closes[1] + tol):
            return None
        upper = highs[2] - closes[2]
        if upper > bodies[2][0] * 1.5:
            return {"name": "赤三兵先詰まり", "dir": "sell", "need": "any",
                    "desc": ("陽線が三本続いたが、三本目に長い上ヒゲ。"
                             "上値を抑えられ、勢いが止まりかけている形とされる。"),
                    "confirmed": True}
        return {"name": "赤三兵", "dir": "buy", "need": "any",
                "desc": ("陽線が三本続き、順に値を切り上げた。"
                         "買いが着実に入っている形で、五法では上昇の始まりとされる。"),
                "confirmed": True}

    if all(not b[1] for b in bodies) and closes[0] > closes[1] > closes[2]:
        tol = atr * 0.3
        if not (opens[1] >= closes[0] - tol and opens[2] >= closes[1] - tol):
            return None
        lower = closes[2] - lows[2]
        if lower > bodies[2][0] * 1.5:
            return {"name": "三羽烏の下ヒゲ", "dir": "buy", "need": "any",
                    "desc": ("陰線が三本続いたが、三本目に長い下ヒゲ。"
                             "売りが一巡し、買い戻しが入り始めた形とされる。"),
                    "confirmed": True}
        return {"name": "三羽烏（黒三兵）", "dir": "sell", "need": "any",
                "desc": ("陰線が三本続き、順に値を切り下げた。"
                         "売りが続いている形で、五法では下落の始まりとされる。"),
                "confirmed": True}
    return None


# ── 三法 ──────────────────────────────────────────────────────
def _sanpou(df, atr) -> dict | None:
    """
    三法: 大きな足のあと、小さな逆行が三本その値幅に収まり、
    最後に元の方向へ抜ける。「休むも相場」を形にしたもので、
    もみ合いを挟んでトレンドが続くことを示す継続のサイン。
    """
    if len(df) < 6:
        return None
    first = df.iloc[-5]
    mids = [df.iloc[-4], df.iloc[-3], df.iloc[-2]]
    last = df.iloc[-1]

    fb, f_bull = _body(first)
    lb, l_bull = _body(last)
    if fb < _MIN_BODY_ATR * atr or lb < _MIN_BODY_ATR * atr:
        return None
    if f_bull != l_bull:
        return None

    f_hi, f_lo = float(first["High"]), float(first["Low"])
    # 中の三本は最初の足の値幅に収まり、かつ小さいこと
    # 中の三本は最初の足の値幅に収まり、かつ小さいこと。
    # ヒゲが少しはみ出す例は実際に多く、完全内包を求めると一度も成立しない。
    # 本質は「大きな足の中でもみ合っている」ことなので、ATRの2割までは許す。
    tol = atr * 0.2
    for m in mids:
        mb, _ = _body(m)
        if mb > fb * _SMALL_BODY:
            return None
        if float(m["High"]) > f_hi + tol or float(m["Low"]) < f_lo - tol:
            return None

    if f_bull and float(last["Close"]) > f_hi:      # 高値を明確に更新して再開
        return {"name": "上げ三法", "dir": "buy", "need": "up",
                "desc": ("大陽線のあと小さな押しが三本入り、再び高値を抜いた。"
                         "一服を挟んで上昇が続く形とされる。"),
                "confirmed": True}
    if not f_bull and float(last["Close"]) < f_lo:
        return {"name": "下げ三法", "dir": "sell", "need": "down",
                "desc": ("大陰線のあと小さな戻しが三本入り、再び安値を割った。"
                         "一服を挟んで下落が続く形とされる。"),
                "confirmed": True}
    return None


_METHODS = (_sanzan, _sansen, _sanku, _sanpei, _sanpou)


def _prior_trend(c: pd.Series, bars: int = 5) -> str:
    """直前の流れ。転換の形は文脈があって初めて意味を持つ。"""
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
    """最新の足に出ている酒田五法の形を拾う。"""
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
    for fn in _METHODS:
        try:
            r = fn(df, atr)
        except Exception:
            logger.debug(traceback.format_exc())
            continue
        if not r:
            continue
        # 転換の形は、その前に反対方向の動きがあって初めて意味を持つ
        need = r.get("need")
        if need in ("up", "down") and trend != need:
            continue
        r["kind"] = "sakata"
        r["prior_trend"] = trend
        found.append(r)
    return found
