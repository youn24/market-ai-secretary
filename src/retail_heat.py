"""
src/retail_heat.py — 個人投資家の過熱度スコア

「何を言っているか」ではなく「実際にどう動いたか」から
個人投資家の過熱・悲観を1つの数値にまとめる。

SNSの発言はポジショントークが混ざるが、
騰落レシオ・空売り比率・新高値/新安値は **実際の売買の結果** なので嘘をつかない。
すでに取得済みのデータを組み合わせるだけなので追加の負荷もない。

【使う指標と考え方】
  騰落レシオ25日   … 120超で過熱、70未満で底値圏（最も有名な逆張り指標）
  空売り比率       … 高いほど弱気だが、行き過ぎると踏み上げの燃料になる
  新高値 - 新安値  … 市場の勢い。新高値だらけは過熱、新安値だらけは投げ
  騰落銘柄比率     … 何%の銘柄が上げたか
  日経VI           … 恐怖指数。低すぎる油断も、高すぎる恐怖も逆張り材料

【スコアの読み方】
  70以上 … 🔴 過熱（個人が強気に傾きすぎ。反落に注意）
  55-70  … 🟠 やや過熱
  45-55  … ⚪ 中立
  30-45  … 🔹 やや悲観
  30未満 … 🟢 悲観（売られすぎ。反発の芽）

⚠️ 逆張り指標であり、タイミングを当てるものではない。
   「過熱＝明日下がる」ではなく「そろそろ無理が利かない」という目安。

【Gemini は使用しない】既存データの計算のみ。
"""

import traceback

from src.utils import setup_logger

logger = setup_logger("retail_heat")


def _score_trk(trk) -> tuple:
    """騰落レシオ25日（最も実績のある逆張り指標）"""
    if trk is None:
        return None, ""
    if trk >= 130: return 95, f"騰落レシオ {trk:.0f}＝明確な過熱圏"
    if trk >= 120: return 80, f"騰落レシオ {trk:.0f}＝過熱圏"
    if trk >= 100: return 60, f"騰落レシオ {trk:.0f}＝やや買い優勢"
    if trk >= 80:  return 45, f"騰落レシオ {trk:.0f}＝中立"
    if trk >= 70:  return 25, f"騰落レシオ {trk:.0f}＝売られすぎ気味"
    return 10, f"騰落レシオ {trk:.0f}＝底値圏（反発の芽）"


def _score_breadth(b) -> tuple:
    """値上がり銘柄の比率"""
    if b is None:
        return None, ""
    if b >= 75: return 85, f"値上がり銘柄 {b:.0f}%＝全面高"
    if b >= 60: return 65, f"値上がり銘柄 {b:.0f}%＝買い優勢"
    if b >= 40: return 50, f"値上がり銘柄 {b:.0f}%＝拮抗"
    if b >= 25: return 30, f"値上がり銘柄 {b:.0f}%＝売り優勢"
    return 12, f"値上がり銘柄 {b:.0f}%＝全面安"


def _score_highlow(nh, nl) -> tuple:
    """新高値と新安値の力関係"""
    if nh is None or nl is None:
        return None, ""
    total = nh + nl
    if total < 10:
        return 50, "新高値・新安値とも少なく方向感が乏しい"
    ratio = nh / total * 100
    if ratio >= 90: return 88, f"新高値{nh} vs 新安値{nl}＝勢いが強い（過熱寄り）"
    if ratio >= 70: return 68, f"新高値{nh} vs 新安値{nl}＝上昇基調"
    if ratio >= 30: return 50, f"新高値{nh} vs 新安値{nl}＝拮抗"
    if ratio >= 10: return 30, f"新高値{nh} vs 新安値{nl}＝下落基調"
    return 12, f"新高値{nh} vs 新安値{nl}＝投げ売り優勢"


def _score_short(sr) -> tuple:
    """
    空売り比率。高い＝弱気だが、極端だと踏み上げ（買い戻し）の燃料になる。
    過熱度としては「低いほど過熱（誰も売っていない）」と読む。
    """
    if sr is None:
        return None, ""
    if sr >= 48: return 20, f"空売り比率 {sr:.1f}%＝弱気が多い（踏み上げの燃料）"
    if sr >= 44: return 38, f"空売り比率 {sr:.1f}%＝やや弱気寄り"
    if sr >= 40: return 52, f"空売り比率 {sr:.1f}%＝標準的"
    if sr >= 36: return 68, f"空売り比率 {sr:.1f}%＝売り方が少ない"
    return 82, f"空売り比率 {sr:.1f}%＝ほとんど売られていない（過熱）"


def _score_vi(vi) -> tuple:
    """日経VI（恐怖指数）。低すぎる＝油断＝過熱。"""
    if vi is None:
        return None, ""
    if vi >= 35: return 12, f"日経VI {vi:.1f}＝強い恐怖（売られすぎの目安）"
    if vi >= 28: return 30, f"日経VI {vi:.1f}＝警戒感が強い"
    if vi >= 22: return 48, f"日経VI {vi:.1f}＝標準"
    if vi >= 18: return 65, f"日経VI {vi:.1f}＝落ち着いている"
    return 82, f"日経VI {vi:.1f}＝油断ムード（過熱のサイン）"


# (関数, データのキー, 重み) — 実績のある指標ほど重くする
_FACTORS = [
    ("trk",     3.0),   # 騰落レシオが最も有名で実績がある
    ("breadth", 2.0),
    ("highlow", 2.0),
    ("short",   1.5),
    ("vi",      1.5),
]


def run(nikkei_internals: dict = None, **_kwargs) -> dict:
    """
    個人投資家の過熱度を算出する。
    nikkei_internals: src/nikkei_market_data.run() の戻り値
    """
    result = {"available": False}
    try:
        nd = nikkei_internals or {}
        if not nd.get("available"):
            # 単体実行時は自前で取りに行く
            try:
                from src.nikkei_market_data import run as run_nd
                nd = run_nd({}, {}, {})
            except Exception:
                logger.debug(traceback.format_exc())
        if not nd.get("available"):
            logger.info("過熱度: 内部データが無いためスキップ")
            return result

        scored = {
            "trk":     _score_trk(nd.get("trk25")),
            "breadth": _score_breadth(nd.get("breadth_pct")),
            "highlow": _score_highlow(nd.get("new_high"), nd.get("new_low")),
            "short":   _score_short(nd.get("short_ratio")),
            "vi":      _score_vi(nd.get("nvi")),
        }

        total_w = 0.0
        total_s = 0.0
        reasons = []
        for key, w in _FACTORS:
            s, note = scored.get(key, (None, ""))
            if s is None:
                continue
            total_s += s * w
            total_w += w
            reasons.append((w, note))
        if total_w == 0:
            return result

        score = round(total_s / total_w, 1)
        if   score >= 70: emoji, label = "🔴", "過熱"
        elif score >= 55: emoji, label = "🟠", "やや過熱"
        elif score >= 45: emoji, label = "⚪", "中立"
        elif score >= 30: emoji, label = "🔹", "やや悲観"
        else:             emoji, label = "🟢", "悲観"

        # 重みの大きい順に理由を並べる
        reasons.sort(key=lambda x: -x[0])
        result.update({
            "available": True,
            "score": score, "emoji": emoji, "label": label,
            "reasons": [n for _, n in reasons if n],
            "raw": {k: v[0] for k, v in scored.items() if v[0] is not None},
            "telegram_block": _block(score, emoji, label,
                                     [n for _, n in reasons if n]),
        })
        logger.info(f"✅ 個人投資家の過熱度: {score}（{label}）")
        return result
    except Exception:
        logger.error("過熱度算出エラー")
        logger.debug(traceback.format_exc())
        return result


def _advice(score: float) -> str:
    if score >= 70:
        return "個人の買いが行き過ぎている水準。新規の追いかけ買いは不利になりやすい。"
    if score >= 55:
        return "やや買いに傾いている。押し目を待つ余裕を持ちたい。"
    if score >= 45:
        return "偏りは小さい。個別の材料で動きやすい地合い。"
    if score >= 30:
        return "売りに傾きつつある。急ぐ必要はないが下値を拾う準備の局面。"
    return "投げ売りが進んだ水準。反発の芽が出やすいが、落ちるナイフには注意。"


def _block(score, emoji, label, reasons) -> str:
    lines = [f"🌡 *個人投資家の過熱度: {emoji} {label}*（{score:.0f}/100）"]
    for r in reasons[:3]:
        lines.append(f"　・{r}")
    lines.append(f"💡 {_advice(score)}")
    lines.append("※実際の売買結果から算出した逆張り指標です。"
                 "「過熱＝明日下がる」ではありません。")
    return "\n".join(lines)


def run_report(nikkei_internals: dict = None) -> bool:
    try:
        res = run(nikkei_internals)
        if not res.get("available"):
            return False
        from src.notify_telegram import send_message
        ok = send_message(res["telegram_block"])
        if ok:
            logger.info("✅ 過熱度レポート送信")
        return bool(ok)
    except Exception:
        logger.error("過熱度レポート送信エラー")
        logger.debug(traceback.format_exc())
        return False


if __name__ == "__main__":
    run_report()
