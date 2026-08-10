"""
リスクオン／リスクオフの複合判定（Step RS）

株・為替・金・債券・VIX が「同時に同じ方向を向いた」ときだけ、
市場全体の資金の向きが変わったと判断する。

なぜ複合で見るか:
  株が下げただけなら、個別の材料かもしれない。しかし
  「株安 × 円高 × 金高 × 金利低下 × VIX上昇」が同時に起きたなら、
  それは市場参加者が一斉にリスクを降ろしている（リスクオフ）証拠になる。
  単独の指標では見えない“資金の総意”を捉えるのが本モジュールの役割。

各資産をリスクオフ方向／リスクオン方向に点数化し、合計が閾値を超えた
場合のみ「極端なリスクオフ／リスクオン」として通知する。

run(prices) → {"available", "direction", "score", "factors":[...], "telegram_block"}
"""
import json
import traceback
from src.utils import setup_logger, get_jst_now, BASE_DIR

logger = setup_logger("risk_sentiment")

_STATE_FILE = BASE_DIR / "data" / "risk_sentiment_state.json"

# 合計スコアがこの値を超えたら「極端」と判断する
_EXTREME = 4.0

# (シンボル, 表示名, 閾値%, 重み, オフ方向の符号, オフ時の説明, オン時の説明)
#   off_sign = -1 … 下落がリスクオフ（株など）
#   off_sign = +1 … 上昇がリスクオフ（VIX・金など）
_ASSETS = [
    ("^N225",    "日経平均",   1.0,  1.5, -1, "株が売られた",       "株が買われた"),
    ("^GSPC",    "S&P500",    1.0,  1.5, -1, "米国株が売られた",   "米国株が買われた"),
    ("^VIX",     "VIX",       10.0, 1.5, +1, "恐怖指数が急上昇",   "恐怖指数が低下"),
    ("USDJPY=X", "ドル円",     0.5,  1.0, -1, "円が買われた(円高)", "円が売られた(円安)"),
    ("GC=F",     "金",         1.0,  1.0, +1, "安全資産の金が買われた", "金が売られた"),
    ("^TNX",     "米10年金利", 3.0,  1.0, -1, "債券が買われ金利低下", "金利上昇(債券売り)"),
    ("BTC-USD",  "ビットコイン", 3.0, 0.5, -1, "暗号資産が売られた", "暗号資産が買われた"),
]


def _load_state() -> dict:
    try:
        return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(st: dict) -> None:
    try:
        _STATE_FILE.parent.mkdir(exist_ok=True)
        _STATE_FILE.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    except Exception:
        logger.debug(traceback.format_exc())


def title_probe(direction: str) -> str:
    """台帳のトピック判定に使うタイトル。"""
    return ("極端なリスクオフ（資金が一斉に逃げている）" if direction == "risk_off"
            else "極端なリスクオン（資金が一斉に戻っている）")


def run(prices: dict = None) -> dict:
    prices = prices or {}
    off_score = on_score = 0.0
    off_factors, on_factors = [], []

    for sym, name, th, weight, off_sign, off_txt, on_txt in _ASSETS:
        d = prices.get(sym) or {}
        chg = d.get("change_pct")
        if chg is None or abs(chg) < th:
            continue
        # off_sign と実際の変化方向が一致すればリスクオフ側
        is_off = (chg > 0) if off_sign > 0 else (chg < 0)
        item = {"name": name, "chg": chg,
                "text": off_txt if is_off else on_txt}
        if is_off:
            off_score += weight
            off_factors.append(item)
        else:
            on_score += weight
            on_factors.append(item)

    net = off_score - on_score
    direction = "risk_off" if net > 0 else "risk_on" if net < 0 else "mixed"
    score = abs(net)
    factors = off_factors if direction == "risk_off" else on_factors

    st = _load_state()
    prev_dir = st.get("direction")
    _save_state({"direction": direction if score >= _EXTREME else "normal",
                 "score": round(score, 1),
                 "date": get_jst_now().strftime("%Y-%m-%d")})

    if score < _EXTREME or direction == "mixed":
        logger.info(f"リスク選好: 通常範囲（off={off_score} on={on_score}）")
        return {"available": False, "direction": direction,
                "score": round(score, 1), "factors": factors}

    # 前回も同じ極端状態なら「継続」として扱い、通知は初日のみ
    if prev_dir == direction:
        logger.info(f"リスク選好: {direction} 継続中のため通知はスキップ")
        return {"available": False, "direction": direction,
                "score": round(score, 1), "factors": factors, "continued": True}

    # 共通台帳で重複を排除（同じ話題を他モジュールが伝えていれば出さない）
    try:
        from src.notify_ledger import filter_new
        if not filter_new([{"key": f"risk_{direction}", "title": title_probe(direction)}],
                          source="risk"):
            logger.info("リスク選好: 同じ話題を通知済みのためスキップ")
            return {"available": False, "direction": direction,
                    "score": round(score, 1), "factors": factors, "duplicated": True}
    except Exception:
        logger.debug(traceback.format_exc())

    is_off = direction == "risk_off"
    title = "極端なリスクオフ（資金が一斉に逃げている）" if is_off \
            else "極端なリスクオン（資金が一斉に戻っている）"
    meaning = ("株・為替・金・債券が揃ってリスク回避の動きを示しています。"
               "個別の材料ではなく、市場全体が守りに入ったサインです。" if is_off else
               "株・為替・金・債券が揃ってリスクを取る動きを示しています。"
               "市場全体に安心感が戻ったサインです。")
    tip = ("下げが一日で終わらないことも多い局面。無理に拾わず、"
           "VIXの低下や反発を確認してからでも遅くありません。" if is_off else
           "上昇が続きやすい地合いですが、急な戻りは反動も出やすい。"
           "追いかけ買いは慎重に。")

    now = get_jst_now().strftime("%m/%d")
    lines = [f"{'🔴' if is_off else '🟢'} *{title}* （{now}）",
             "━━━━━━━━━━━━━━━",
             f"一致度スコア *{score:.1f}*（{len(factors)}資産が同じ方向）"]
    for f in factors[:6]:
        arrow = "🔺" if f["chg"] > 0 else "🔻"
        lines.append(f"　{arrow} {f['name']} {f['chg']:+.2f}% — {f['text']}")
    lines += ["", f"　{meaning}", f"　💡 {tip}",
              "━━━━━━━━━━━━━━━",
              "複数の資産が同時に同じ方向を向いたときだけ通知しています。"]

    # この通知は構成資産（VIX・株・為替・金・金利）をまとめて説明しているので、
    # 同じ資産についての個別通知は後から出さない
    try:
        from src.notify_ledger import mark_topics, topic_of
        mark_topics([topic_of(f["name"]) for f in factors])
    except Exception:
        logger.debug(traceback.format_exc())

    logger.info(f"🚨 極端な{direction}: スコア{score:.1f}（{len(factors)}資産一致）")
    return {"available": True, "direction": direction, "score": round(score, 1),
            "factors": factors, "title": title, "meaning": meaning, "tip": tip,
            "telegram_block": "\n".join(lines)}


if __name__ == "__main__":
    p = {"^N225": {"change_pct": -2.4}, "^GSPC": {"change_pct": -1.8},
         "^VIX": {"change_pct": 25.0}, "USDJPY=X": {"change_pct": -1.1},
         "GC=F": {"change_pct": 1.6}, "^TNX": {"change_pct": -4.0}}
    print(run(p).get("telegram_block", "通常範囲"))
