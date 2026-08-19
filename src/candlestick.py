"""
ローソク足・プライスアクション（Step CS）— 形の重なりを検出する

扱うもの:
  ローソク足   … 包み足・はらみ足・ハンマー・流れ星・明けの明星/宵の明星・
                  毛抜き天井/底・十字線
  プライスアクション … 高値安値の切り上げ/切り下げ（トレンド構造）・
                  ダブルトップ/ボトム・レンジブレイク・ブレイク後の押し目

設計の考え方:
  1. **文脈のない形は数えない。**
     ハンマーは「下落したあと」に出て初めて反転の意味を持つ。
     上昇の途中に同じ形が出ても、それはただの陽線である。
     教科書がどれも「トレンドのあとに」と書いているのはこのためで、
     文脈を無視すると毎日どこかで“シグナル”が出て意味を失う。

  2. **大きさを問う。**
     実体が極端に小さい包み足は、値がほとんど動いていないのと同じ。
     その銘柄の平均的な値幅(ATR)と比べて意味のある大きさかを必ず見る。

  3. **重なりを主役にする。**
     単独の形は当たり外れが大きい。方向の一致する形が複数そろったとき、
     または上位のトレンド構造と噛み合ったときだけ通知する。

⚠️ 効果の検証は src/pattern_validation.py で別途行う。
   「教科書に載っている」ことと「この相場で通用する」ことは別問題で、
   検証せずに信頼度を語ると利用者に誤った期待を持たせる。

detect(symbol_list) → 検出した形のリスト
"""
import traceback

import pandas as pd

from src.utils import setup_logger

logger = setup_logger("candlestick")

# 実体・ヒゲの判定に使う比率。教科書的な定義をそのまま数値化したもの。
_DOJI_BODY = 0.1        # 実体が値幅の10%未満なら十字線（迷い）
_LONG_TAIL = 2.0        # ヒゲが実体の2倍以上で「長いヒゲ」
_SMALL_TAIL = 0.3       # 反対側のヒゲは実体の30%以下であること
_MIN_BODY_ATR = 0.5     # 実体がATRの半分未満なら小さすぎて意味を持たない
_TREND_BARS = 5         # 直前のトレンドを見る本数


def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """平均的な値幅。形の大きさが「その銘柄にとって意味があるか」の物差し。"""
    h, l, c = df["High"], df["Low"], df["Close"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def _parts(row) -> dict:
    """1本のローソクを、実体・上ヒゲ・下ヒゲに分解する。"""
    o, h, l, c = float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"])
    body = abs(c - o)
    return {
        "open": o, "high": h, "low": l, "close": c,
        "body": body,
        "range": h - l,
        "upper": h - max(o, c),
        "lower": min(o, c) - l,
        "bull": c > o,
    }


def _prior_trend(c: pd.Series, i: int, bars: int = _TREND_BARS) -> str:
    """
    形が出る「直前」の流れ。反転パターンは文脈があって初めて意味を持つ。
    当日を含めないのが肝で、含めるとその日の形自体が判定に混ざる。
    """
    if i < bars + 1:
        return "flat"
    seg = c.iloc[i - bars: i]
    if len(seg) < 2:
        return "flat"
    chg = (float(seg.iloc[-1]) - float(seg.iloc[0])) / float(seg.iloc[0]) * 100
    if chg <= -2.0:
        return "down"
    if chg >= 2.0:
        return "up"
    return "flat"


# ── ローソク足パターン ─────────────────────────────────────────
def _pat_engulfing(df, i, atr) -> dict | None:
    """包み足: 前の足を完全に包み込む反対色の足。勢いの転換を示す。"""
    if i < 1:
        return None
    a, b = _parts(df.iloc[i - 1]), _parts(df.iloc[i])
    if b["body"] < _MIN_BODY_ATR * atr or a["body"] <= 0:
        return None
    covers = max(b["open"], b["close"]) >= max(a["open"], a["close"]) and \
             min(b["open"], b["close"]) <= min(a["open"], a["close"])
    if not covers or b["bull"] == a["bull"]:
        return None
    if b["bull"]:
        return {"name": "強気の包み足", "dir": "buy", "need": "down",
                "desc": "前日の下げ幅をすべて包み込む陽線。売り方が力尽きた形。"}
    return {"name": "弱気の包み足", "dir": "sell", "need": "up",
            "desc": "前日の上げ幅をすべて包み込む陰線。買い方が力尽きた形。"}


def _pat_harami(df, i, atr) -> dict | None:
    """はらみ足: 前の大きな足の中に小さな足が収まる。勢いの衰え。"""
    if i < 1:
        return None
    a, b = _parts(df.iloc[i - 1]), _parts(df.iloc[i])
    if a["body"] < _MIN_BODY_ATR * atr or b["body"] >= a["body"] * 0.6:
        return None
    inside = max(b["open"], b["close"]) <= max(a["open"], a["close"]) and \
             min(b["open"], b["close"]) >= min(a["open"], a["close"])
    if not inside or b["bull"] == a["bull"]:
        return None
    if b["bull"]:
        return {"name": "強気のはらみ足", "dir": "buy", "need": "down",
                "desc": "大陰線の中に小さな陽線。下げの勢いが止まりつつある形。"}
    return {"name": "弱気のはらみ足", "dir": "sell", "need": "up",
            "desc": "大陽線の中に小さな陰線。上げの勢いが止まりつつある形。"}


def _pat_hammer(df, i, atr) -> dict | None:
    """ハンマー: 長い下ヒゲ。安値で買い戻された跡。"""
    b = _parts(df.iloc[i])
    if b["range"] <= 0 or b["body"] <= 0:
        return None
    if b["lower"] < b["body"] * _LONG_TAIL or b["upper"] > b["body"] * _SMALL_TAIL:
        return None
    if b["range"] < _MIN_BODY_ATR * atr:
        return None
    return {"name": "下ヒゲの長い足（ハンマー）", "dir": "buy", "need": "down",
            "desc": "安値まで売られたあと押し戻された跡。買い手が現れた形。"}


def _pat_shooting_star(df, i, atr) -> dict | None:
    """流れ星: 長い上ヒゲ。高値で売られた跡。"""
    b = _parts(df.iloc[i])
    if b["range"] <= 0 or b["body"] <= 0:
        return None
    if b["upper"] < b["body"] * _LONG_TAIL or b["lower"] > b["body"] * _SMALL_TAIL:
        return None
    if b["range"] < _MIN_BODY_ATR * atr:
        return None
    return {"name": "上ヒゲの長い足（流れ星）", "dir": "sell", "need": "up",
            "desc": "高値まで買われたあと押し戻された跡。売り手が現れた形。"}


def _pat_star(df, i, atr) -> dict | None:
    """明けの明星 / 宵の明星: 大きな足 → 小さな足 → 反対の大きな足の3本組。"""
    if i < 2:
        return None
    a, b, c = (_parts(df.iloc[i - 2]), _parts(df.iloc[i - 1]), _parts(df.iloc[i]))
    if a["body"] < _MIN_BODY_ATR * atr or c["body"] < _MIN_BODY_ATR * atr:
        return None
    if b["body"] > a["body"] * 0.5:      # 真ん中は小さいこと
        return None
    if not a["bull"] and c["bull"] and c["close"] > (a["open"] + a["close"]) / 2:
        return {"name": "明けの明星", "dir": "buy", "need": "down",
                "desc": "大陰線→小さな足→大陽線。底打ちの典型形とされる並び。"}
    if a["bull"] and not c["bull"] and c["close"] < (a["open"] + a["close"]) / 2:
        return {"name": "宵の明星", "dir": "sell", "need": "up",
                "desc": "大陽線→小さな足→大陰線。天井形成の典型形とされる並び。"}
    return None


def _pat_tweezer(df, i, atr) -> dict | None:
    """毛抜き: 2本の高値（安値）がほぼ同じ。同じ価格で跳ね返された跡。"""
    if i < 1:
        return None
    a, b = _parts(df.iloc[i - 1]), _parts(df.iloc[i])
    tol = atr * 0.1
    if tol <= 0:
        return None
    if abs(a["low"] - b["low"]) <= tol and not a["bull"] and b["bull"]:
        return {"name": "毛抜き底", "dir": "buy", "need": "down",
                "desc": "2日続けて同じ安値で下げ止まった。買い支えの跡。"}
    if abs(a["high"] - b["high"]) <= tol and a["bull"] and not b["bull"]:
        return {"name": "毛抜き天井", "dir": "sell", "need": "up",
                "desc": "2日続けて同じ高値で頭を抑えられた。売り圧力の跡。"}
    return None


def _pat_doji(df, i, atr) -> dict | None:
    """十字線: 実体がほとんどない。買いと売りが拮抗した迷いの形。"""
    b = _parts(df.iloc[i])
    if b["range"] <= 0 or b["range"] < _MIN_BODY_ATR * atr:
        return None
    if b["body"] > b["range"] * _DOJI_BODY:
        return None
    return {"name": "十字線", "dir": "neutral", "need": "any",
            "desc": "始値と終値がほぼ同じ。買いと売りが拮抗し、方向が定まらない形。"}


_CANDLES = (_pat_engulfing, _pat_harami, _pat_hammer, _pat_shooting_star,
            _pat_star, _pat_tweezer, _pat_doji)


# ── プライスアクション ─────────────────────────────────────────
def _swings(df, lr: int = 3) -> tuple:
    """前後 lr 本より高い/安い点をスイング高値・安値とする。"""
    h, l = df["High"].tolist(), df["Low"].tolist()
    highs, lows = [], []
    for i in range(lr, len(h) - lr):
        if h[i] == max(h[i - lr:i + lr + 1]):
            highs.append(i)
        if l[i] == min(l[i - lr:i + lr + 1]):
            lows.append(i)
    return highs, lows


def _pa_structure(df) -> dict | None:
    """
    高値・安値の切り上げ/切り下げ＝トレンドの骨格。

    移動平均より素直にトレンドを表す。
    高値も安値も切り上がっていれば上昇トレンド、両方切り下がれば下降トレンド。
    片方だけなら構造が崩れかけている＝転換の前触れになりうる。
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


def _pa_double(df) -> dict | None:
    """ダブルトップ / ダブルボトム: 同じ水準で2度跳ね返された跡。"""
    highs, lows = _swings(df)
    atr = float(_atr(df).iloc[-1] or 0)
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


def _pa_range_break(df, look: int = 20) -> dict | None:
    """
    レンジ抜け: 一定期間もみ合った幅を抜けた瞬間。
    もみ合いが狭いほど、抜けたあとの動きが大きくなりやすいとされる。
    """
    if len(df) < look + 5:
        return None
    seg = df.iloc[-(look + 1):-1]
    hi, lo = float(seg["High"].max()), float(seg["Low"].min())
    if hi <= lo:
        return None
    width = (hi - lo) / lo * 100
    atr = float(_atr(df).iloc[-1] or 0)
    c = float(df["Close"].iloc[-1])
    # 値幅が広すぎるものは「もみ合い」とは言えないので除外する
    if width > 15:
        return None
    if c > hi and (c - hi) >= atr * 0.2:
        return {"name": f"{look}日のもみ合いを上抜け", "dir": "buy", "need": "any",
                "desc": f"{hi:,.0f}を上抜け（もみ合い幅{width:.1f}%）。"}
    if c < lo and (lo - c) >= atr * 0.2:
        return {"name": f"{look}日のもみ合いを下抜け", "dir": "sell", "need": "any",
                "desc": f"{lo:,.0f}を下抜け（もみ合い幅{width:.1f}%）。"}
    return None


_PRICE_ACTION = (_pa_structure, _pa_double, _pa_range_break)


def analyze(df: pd.DataFrame) -> list:
    """1銘柄ぶんのデータから、最新の足に出ている形をすべて拾う。"""
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

    i = len(df) - 1
    trend = _prior_trend(df["Close"], i)
    found = []

    for fn in _CANDLES:
        try:
            r = fn(df, i, atr)
        except Exception:
            logger.debug(traceback.format_exc())
            continue
        if not r:
            continue
        # 文脈の確認。反転の形は、その前に反対方向の動きがあって初めて意味を持つ
        need = r.get("need")
        if need in ("up", "down") and trend != need:
            continue
        r["kind"] = "candle"
        r["prior_trend"] = trend
        found.append(r)

    for fn in _PRICE_ACTION:
        try:
            r = fn(df)
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


# ══════════════════════════════════════════════════════════════
# 通知（形の重なりを検出して知らせる）
# ══════════════════════════════════════════════════════════════
import json
import os
from datetime import datetime

from src.utils import BASE_DIR, get_jst_now

_STATE_FILE = BASE_DIR / "data" / "pattern_state.json"
_VALIDATION = BASE_DIR / "data" / "pattern_validation.json"

# 「状態」と「出来事」を分ける。
# 高値安値の切り上げ/切り下げは数週間続く“状態”であり、その日に起きた
# “出来事”ではない。これを1つと数えると、ローソク足が1つ出ただけで
# 「2つ重なった」ことになり、重なりの意味が失われる。
# 実測（6銘柄×2年）でも、状態を含めると重なりが年30回近くまで水増しされた。
_STATE_PATTERNS = {
    "高値・安値ともに切り上げ", "高値・安値ともに切り下げ",
    "高値は更新も安値を切り下げ",
}

# 通知の階層。実測した発生頻度に合わせてある（6銘柄×2年＝2,624日で計測）。
#   出来事2つ以上          … 0.76%の日＝1銘柄あたり年2回ほど。極めて稀
#   出来事1つ＋構造が一致  … 4.2%の日＝1銘柄あたり月1回ほど
# 単独の出来事だけでは通知しない。当たり外れが大きく、毎週鳴って読み飛ばされる。
_MIN_EVENTS = 2

# 監視対象。tech_signals（指数中心）と重ならないよう、
# 日本の主力株を厚めにする。同じ話題を二重に送らないため。
TARGETS = [
    ("^N225", "日経225"), ("NIY=F", "日経先物"), ("USDJPY=X", "ドル円"),
    ("8035.T", "東京エレクトロン"), ("6857.T", "アドバンテスト"),
    ("6920.T", "レーザーテック"), ("9984.T", "ソフトバンクG"),
    ("6758.T", "ソニーG"), ("7203.T", "トヨタ"), ("8306.T", "三菱UFJ"),
    ("6501.T", "日立"), ("9983.T", "ファーストリテイリング"),
    ("6146.T", "ディスコ"), ("5803.T", "フジクラ"),
    ("NVDA", "エヌビディア"), ("AAPL", "アップル"), ("TSLA", "テスラ"),
]


def _load_validation() -> dict:
    """
    検証結果を読み、パターンごとの実績を通知に添えられるようにする。
    「教科書に載っている形」ではなく「過去にどうだったか」を示すのが目的。
    ファイルが無ければ実績表示なしで動く（検証前でも通知自体は機能させる）。
    """
    try:
        return json.loads(_VALIDATION.read_text(encoding="utf-8")).get("patterns") or {}
    except Exception:
        return {}


def _track_record(pat_name: str, val: dict) -> str:
    """1つの形について、過去の実績を1行にする。"""
    v = val.get(pat_name)
    if not v:
        return ""
    d = v.get("5日後") or {}
    edge, p, n = d.get("実力"), d.get("p値"), v.get("n")
    if edge is None:
        return ""
    if p is not None and p < 0.05:
        return f"（過去{n}回・5日後 平均{edge:+.2f}%／統計的に有意）"
    return f"（過去{n}回・5日後 平均{edge:+.2f}%／誤差の範囲）"


def detect(targets: list = None) -> list:
    """
    対象を走査し、同じ方向の形が複数そろった銘柄だけを返す。
    """
    import yfinance as yf

    targets = targets or TARGETS
    val = _load_validation()
    out = []
    for sym, name in targets:
        try:
            df = yf.Ticker(sym).history(period="6mo")
            pats = analyze(df)
        except Exception:
            logger.error(f"{name} の解析に失敗しました", exc_info=True)
            continue
        if not pats:
            continue

        for direction in ("buy", "sell"):
            same = [p for p in pats if p["dir"] == direction]
            events = [p for p in same if p["name"] not in _STATE_PATTERNS]
            states = [p for p in pats if p["name"] in _STATE_PATTERNS]
            aligned = [s for s in states if s["dir"] == direction]

            if len(events) >= _MIN_EVENTS:
                tier, tier_label = "A", f"出来事が{len(events)}つ重なり"
            elif len(events) == 1 and aligned:
                tier, tier_label = "B", "出来事＋トレンド構造が一致"
            else:
                continue

            opposite = [p for p in pats if p["dir"] not in (direction, "neutral")]
            for p in same:
                p["record"] = _track_record(p["name"], val)
            out.append({
                "symbol": sym, "name": name, "direction": direction,
                "tier": tier, "tier_label": tier_label,
                "patterns": events,
                "structure": aligned[0] if aligned else None,
                "count": len(events),
                "conflict": bool(opposite),
                "neutral": [p for p in pats if p["dir"] == "neutral"],
                "price": round(float(df["Close"].iloc[-1]), 2),
                "change_pct": round(
                    (float(df["Close"].iloc[-1]) - float(df["Close"].iloc[-2]))
                    / float(df["Close"].iloc[-2]) * 100, 2),
            })
    # 稀なもの（Aランク）を先に見せる
    out.sort(key=lambda x: (x["tier"], -x["count"]))
    logger.info(f"形の重なり: {len(out)}件")
    return out


def build_message(groups: list) -> str:
    names = "・".join(g["name"] for g in groups)
    arrow = {"buy": "🔺上昇", "sell": "🔻下落"}
    n_a = sum(1 for g in groups if g["tier"] == "A")
    sub = ("複数の形が同時に出た、稀な場面です" if n_a
           else "形とトレンドの向きがそろった銘柄です")
    lines = [f"🕯 *チャートの形｜{names}*", sub, "━━━━━━━━━━━━━━"]

    for g in groups:
        mark = "⭐" if g["tier"] == "A" else ""
        lines += ["", f"{arrow[g['direction']]} *{g['name']}*　"
                      f"{g['price']:,.2f}（{g['change_pct']:+.2f}%）",
                  f"　{mark}{g['tier_label']}"]

        # 構造は背景として先に置く。個々の形より前に「どんな相場か」を示す
        if g.get("structure"):
            lines.append(f"📐 {g['structure']['name']}")
            lines.append(f"　{g['structure']['desc']}")

        for p in g["patterns"]:
            tag = "🕯" if p["kind"] == "candle" else "📐"
            lines.append(f"{tag} *{p['name']}*")
            lines.append(f"　{p['desc']}")
            if p.get("record"):
                lines.append(f"　📊 {p['record']}")
        if g["neutral"]:
            lines.append(f"　⚖️ 同時に「{g['neutral'][0]['name']}」も出ており、"
                         f"迷いのある場面です。")
        if g["conflict"]:
            lines.append("　⚠️ 逆方向の形も出ています。判断は慎重に。")

    lines += ["",
              "🕯=ローソク足の形 ／ 📐=値動きの構造（プライスアクション）",
              "⭐=形が2つ以上重なった場面（1銘柄あたり年2回ほどしか出ません）",
              "📊の実績は過去5年30銘柄での検証値で、"
              "相場全体の上昇分を差し引いた「実力」です。"]
    return "\n".join(lines)[:4000]


def _session_key() -> str:
    return get_jst_now().strftime("%Y-%m-%d")


def run_pattern_alert() -> bool:
    """monitor_run.py から呼ぶ。同じ銘柄・同じ方向は1日1回だけ。"""
    try:
        groups = detect()
        if not groups:
            logger.info("チャートの形: 条件を満たす銘柄なし")
            return False

        skey = _session_key()
        try:
            st = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            st = {}

        kept = []
        for g in groups:
            key = f"{g['symbol']}:{g['direction']}"
            rec = st.get(key)
            if isinstance(rec, dict) and rec.get("session") == skey:
                continue
            kept.append(g)
            st[key] = {"session": skey, "ts": datetime.now().isoformat()}
        if not kept:
            logger.info("すべて通知済みのためスキップ")
            return False

        st = {k: v for k, v in st.items()
              if isinstance(v, dict) and v.get("session") == skey}
        try:
            _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            _STATE_FILE.write_text(json.dumps(st, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
        except Exception:
            logger.error("状態の保存に失敗しました", exc_info=True)

        from src.notify_telegram import send_message
        ok = send_message(build_message(kept))
        if ok:
            logger.info(f"✅ チャートの形を通知（{len(kept)}件）")
        return bool(ok)
    except Exception:
        logger.error("チャートの形の検出に失敗しました", exc_info=True)
        return False


if __name__ == "__main__":
    import io, sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    g = detect()
    print(build_message(g) if g else "条件を満たす銘柄はありません")
