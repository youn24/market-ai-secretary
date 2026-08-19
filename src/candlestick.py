"""
ローソク足・プライスアクション（Step CS）— 形の重なりを検出する

扱うもの:
  ローソク足   … 包み足・はらみ足・ハンマー・流れ星・明けの明星/宵の明星・
                  毛抜き天井/底・十字線
  （プライスアクションは src/price_action.py、酒田五法は src/sakata.py に分離。
    通知の組み立てと配信はこのモジュールが3系統をまとめて担当する）

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


# ── プライスアクションは src/price_action.py へ移設 ───────────────
# 1〜3本の「形」と、数十本の「構造」を同じ場所に置くと、
# どちらの粒度で判断しているのか読めなくなるため分離した。
# 移設であって複製ではない（同じ判定を二重に持たない）。


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


def _honest_note() -> str:
    """
    重なりの効果について、検証結果から文章を作る。
    件数を固定で書くと再検証のたびに嘘になるので、必ずファイルから読む。
    """
    try:
        d = json.loads(_VALIDATION.read_text(encoding="utf-8"))
        c = (d.get("confluence") or {}).get("2つ重なり") or {}
        e = (c.get("5日後") or {}).get("実力")
        n = c.get("n")
        if e is None or not n:
            raise ValueError
        return (f"過去5年・{d.get('symbols', 30)}銘柄・{d.get('total', 0):,}件で検証したところ、"
                f"*形が重なっても成績が上がるとは確認できませんでした*"
                f"（2つ重なり n={n:,} で {e:+.2f}%）。")
    except Exception:
        return ("形が重なると当たりやすくなる、という効果は"
                "過去データでは確認できていません。")


def _track_record(pat_name: str, val: dict) -> str:
    """
    1つの形について、過去の実績を1行にする。

    「p<0.05だから有意」とは書かない。16種類を検定すれば効果がゼロでも
    平均0.8種は p<0.05 になるため、その基準では偶然を実力と呼ぶことになる。
    多重比較を補正した基準（validation側が計算）を通ったものだけ「確認できた」と書く。

    実力がマイナスの形は、教科書の説明と逆の結果になっている。
    形の名前だけ見て逆方向に受け取られるのが一番まずいので、その旨を明示する。
    """
    v = val.get(pat_name)
    if not v:
        return ""
    d = v.get("5日後") or {}
    edge, n = d.get("実力"), v.get("n")
    if edge is None:
        return ""

    head = f"過去{n}回・5日後 平均{edge:+.2f}%"
    if v.get("有効"):
        if edge < 0:
            return (f"（{head}／⚠️ *教科書と逆の結果*。"
                    f"この形が出たあと、期待と反対に動く傾向が確認されています）")
        return f"（{head}／検証で効果を確認）"
    if v.get("補正前は有意"):
        return f"（{head}／わずかな傾向はあるが、偶然の可能性も残る）"
    return f"（{head}／誤差の範囲。効果は確認できていません）"


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
            # 酒田五法も同じ土俵で扱う。五法は「三」を単位とする体系で
            # 判定の粒度が違うが、利用者にとっては同じ「チャートの形」なので
            # 別々の通知にせず1通にまとめる（通知が増えると読み飛ばされる）。
            from src import sakata, price_action
            pats = analyze(df) + sakata.analyze(df) + price_action.analyze(df)
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

            sakata_hits = [p for p in events if p.get("kind") == "sakata"]

            if len(events) >= _MIN_EVENTS:
                tier, tier_label = "A", f"形が{len(events)}つ重なり"
            elif sakata_hits:
                # 酒田五法は年に数回しか出ない稀な形なので、単独でも知らせる。
                # 三尊天井などは「重なり」を待っていると手遅れになる。
                tier = "A" if len(sakata_hits) >= 2 else "B"
                tier_label = f"酒田五法：{sakata_hits[0]['name']}"
            elif len(events) == 1 and aligned:
                tier, tier_label = "B", "形＋トレンド構造が一致"
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
            tag = {"candle": "🕯", "sakata": "🎌", "price_action": "📐"}.get(
                p.get("kind"), "📐")
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
              "🕯=ローソク足の形 ／ 🎌=酒田五法 ／ 📐=値動きの構造",
              "⭐=形が2つ以上重なった場面（1銘柄あたり年2回ほどしか出ません）",
              "",
              "ℹ️ *正直にお伝えします*",
              _honest_note(),
              "この通知は「いま何が起きているか」を知らせるもので、"
              "先を当てる道具としてはお使いにならないでください。"]
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
