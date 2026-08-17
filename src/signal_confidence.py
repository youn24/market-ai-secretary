"""
シグナル信頼度ランク（Step SC）— そのサインをどれだけ信じていいかを表示する

なぜ必要か:
  「今日は下げ」とだけ言われても、それが勝率85%の下げなのか勝率50%の
  コイン投げなのか分からない。実際 failure_analysis で調べたところ、
  上げ/下げを明言した日の勝率は信号の強さで 50% → 85% まで開いていた。
  同じ「下げ」でも中身が全く違う。
  平均を一つ出すより、その日のサインがどのクラスかを添える方が役に立つ。

設計方針:
  ランクの境界と勝率は「勘」ではなく過去データから作る。
  backtest_result.json を集計して config/confidence_tiers.json に焼き、
  実運用ではそれを読むだけにする。バックテストを回し直せば表も更新される。

  方向(bull/bear)ごとに別々に集計するのが肝。
  下げ予想は同じスコアの強さでも上げ予想より当たりにくいという偏りが
  実際に出ているため、まとめて平均すると下げの弱さが隠れてしまう。

calibrate() → 表を作り直す（バックテスト後に実行）
evaluate(direction, adjusted_score) → その日のランク
"""
import json
import statistics
from datetime import datetime

from src.utils import setup_logger, BASE_DIR

logger = setup_logger("signal_confidence")

_TABLE = BASE_DIR / "config" / "confidence_tiers.json"
_BACKTEST = BASE_DIR / "data" / "backtest_result.json"

# 強さの区切り。|補正後スコア| で分ける。
# バックテストの分布を見て、各段に十分な件数が入るように設定した。
_EDGES = [3.0, 6.0, 10.0, 15.0]

# 勝率からランク名へ。数字だけ出しても初心者には判断できないので、
# 「どう扱えばいいか」まで言葉にする。
_TIERS = [
    (80, "S", "★★★★", "かなり信頼できる"),
    (70, "A", "★★★",  "信頼できる"),
    (60, "B", "★★",    "やや信頼できる"),
    (0,  "C", "★",     "参考程度（コイン投げに近い）"),
]

# 1マスあたりこれ未満の件数なら、偶然の可能性が高いので採用しない
_MIN_N = 15


def _bucket(score: float) -> int:
    a = abs(score)
    for i, e in enumerate(_EDGES):
        if a < e:
            return i
    return len(_EDGES)


def _bucket_label(i: int) -> str:
    if i == 0:            return f"|スコア|<{_EDGES[0]:.0f}"
    if i >= len(_EDGES):  return f"|スコア|≥{_EDGES[-1]:.0f}"
    return f"|スコア|{_EDGES[i-1]:.0f}〜{_EDGES[i]:.0f}"


def _tier_of(win_rate: float) -> tuple:
    for th, rank, stars, advice in _TIERS:
        if win_rate >= th:
            return rank, stars, advice
    return "C", "★", "参考程度"


def _adjusted(sample: dict) -> float:
    """
    バックテストのサンプルは補正前スコアで保存されているため、
    実運用と同じ Fear&Greed 補正を掛け直して比較可能にする。
    （prediction_tracker._extract_direction と同じ係数）
    """
    a = sample["score"]
    fg = sample.get("fg_est")
    if fg is None:
        return a
    if fg < 25:    return a - 3.0
    if fg < 35:    return a - 1.5
    if fg >= 75:   return a + 3.0
    if fg >= 65:   return a + 1.5
    return a


def calibrate() -> dict:
    """
    過去データから信頼度表を作り直す。
    勝率は「予測方向に賭けたとき翌日その方向に動いた割合」で測る。
    的中率（±0.3%を中立とみなす3択）ではなく勝率を使うのは、
    実際に知りたいのが「方向が合っているか」だからだ。
    """
    try:
        samples = json.loads(_BACKTEST.read_text(encoding="utf-8"))["samples"]
    except Exception:
        logger.error("バックテスト結果が読めないため較正できません")
        return {"available": False}

    table = {}
    for direction in ("bull", "bear"):
        sign = 1 if direction == "bull" else -1
        cells = {}
        all_edge = []
        for s in samples:
            if s["direction"] != direction:
                continue
            edge = s["move"] * sign
            cells.setdefault(_bucket(_adjusted(s)), []).append(edge)
            all_edge.append(edge)

        if not all_edge:
            continue

        fallback_win = sum(1 for e in all_edge if e > 0) / len(all_edge) * 100
        out = {}
        for b, rows in sorted(cells.items()):
            if len(rows) < _MIN_N:
                # 件数が足りないマスは方向全体の平均で代用する。
                # 少数のマスに引っ張られて過大・過小評価するのを避けるため。
                win, n, borrowed = fallback_win, len(rows), True
            else:
                win, n, borrowed = (sum(1 for e in rows if e > 0) / len(rows) * 100,
                                    len(rows), False)
            rank, stars, advice = _tier_of(win)
            out[str(b)] = {
                "range": _bucket_label(b),
                "n": n,
                "win_rate": round(win, 1),
                "expectancy": round(statistics.mean(rows), 3),
                "rank": rank, "stars": stars, "advice": advice,
                "estimated": borrowed,
            }
        table[direction] = {"buckets": out,
                            "overall_win_rate": round(fallback_win, 1),
                            "n": len(all_edge)}

    result = {
        "available": bool(table),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source_n": len(samples),
        "period": f'{samples[0]["date"]}〜{samples[-1]["date"]}' if samples else "",
        "edges": _EDGES,
        "min_n": _MIN_N,
        "table": table,
    }
    try:
        _TABLE.parent.mkdir(exist_ok=True)
        _TABLE.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
        logger.info(f"✅ 信頼度表を更新: {len(samples)}件から生成")
    except Exception:
        logger.error("信頼度表の保存に失敗しました", exc_info=True)
    return result


def evaluate(direction: str, adjusted_score: float) -> dict:
    """
    その日のサインの信頼度を返す。
    表が無い・方向が中立などで判定できない場合は available=False を返し、
    呼び出し側は何も表示しない（分からないものを分かった風に出さない）。
    """
    if direction not in ("bull", "bear"):
        return {"available": False, "reason": "中立の日は信頼度を出さない"}
    try:
        t = json.loads(_TABLE.read_text(encoding="utf-8"))
    except Exception:
        return {"available": False, "reason": "信頼度表が未生成"}
    cell = ((t.get("table") or {}).get(direction) or {}).get("buckets", {}) \
        .get(str(_bucket(adjusted_score)))
    if not cell:
        return {"available": False, "reason": "該当データなし"}
    return {
        "available": True,
        "direction": direction,
        "score": round(adjusted_score, 2),
        "rank": cell["rank"],
        "stars": cell["stars"],
        "win_rate": cell["win_rate"],
        "expectancy": cell["expectancy"],
        "advice": cell["advice"],
        "sample_n": cell["n"],
        "estimated": cell.get("estimated", False),
        "range": cell["range"],
        "period": t.get("period", ""),
    }


def format_line(conf: dict) -> str:
    """通知に1行で差し込む用。"""
    if not conf.get("available"):
        return ""
    d = "上げ" if conf["direction"] == "bull" else "下げ"
    tail = "（参考値）" if conf.get("estimated") else f"（過去{conf['sample_n']}件）"
    return (f"信頼度 {conf['stars']} {conf['rank']}ランク｜"
            f"同条件の{d}予想は過去 {conf['win_rate']}% 的中{tail}")


def format_html(conf: dict) -> str:
    """公開レポート用。色は信頼度の高さで変える。"""
    if not conf.get("available"):
        return ""
    color = {"S": "#16a34a", "A": "#0ea5e9", "B": "#f59e0b", "C": "#94a3b8"}.get(
        conf["rank"], "#94a3b8")
    d = "上げ" if conf["direction"] == "bull" else "下げ"
    note = "参考値（データ少）" if conf.get("estimated") else f"過去{conf['sample_n']}件"
    return (
        f'<div style="display:inline-flex;align-items:center;gap:.6em;'
        f'padding:.5em .9em;border-radius:10px;border:1px solid {color}44;'
        f'background:{color}11;font-size:.95em;">'
        f'<span style="color:{color};font-weight:700;font-size:1.1em;">'
        f'{conf["stars"]} {conf["rank"]}ランク</span>'
        f'<span style="opacity:.85;">同条件の{d}予想は <b>{conf["win_rate"]}%</b> 的中'
        f'<span style="opacity:.6;font-size:.9em;"> / {note}</span></span>'
        f'<span style="opacity:.7;">— {conf["advice"]}</span></div>')


if __name__ == "__main__":
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    r = calibrate()
    for d, v in (r.get("table") or {}).items():
        print(f'== {d} (全体勝率 {v["overall_win_rate"]}%, n={v["n"]})')
        for b, c in v["buckets"].items():
            mark = " *推定" if c["estimated"] else ""
            print(f'   {c["range"]:16} {c["stars"]:4} {c["rank"]} '
                  f'勝率{c["win_rate"]:5.1f}% n={c["n"]:3}{mark}')
