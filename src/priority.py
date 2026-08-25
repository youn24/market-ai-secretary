"""
情報の優先順位（Step PRI）— 何を先に見せるかを1か所で決める

なぜ必要か:
  朝の通知は1024字しか入らない。何を上に置くかで、読まれるかどうかが決まる。
  これまでは「cloud_run に書いた順」がそのまま表示順になっていた。
  記述順は開発の都合であって、読む人にとっての重要度ではない。

  実際、Geminiの枠切れも同じ構図だった（記述順が後ろの分析が毎日落ちる）。
  表示でも同じことが起きていた。

順位の決め方 — 「緊急性 × 信頼度」の2軸:

  **緊急性** … 今すぐ行動が変わるか。
    市場が壊れているという知らせは、明日には価値がない。
    一方「テーマ株ランキング」は今日読んでも明日読んでも同じ。

  **信頼度** … 検証で裏が取れているか。
    この案件では、検証した結果 *効かなかった* ものが多く見つかっている。
      ・ローソク足16種 … ドリフト調整＋多重比較補正の後に残ったのは2種で、
        どちらも教科書と**逆**の結果（[[CLAUDE.md]] 参照）
      ・酒田五法6種 … すべて統計的に有意でない
      ・テクニカル8種 … ドリフト調整後、優位性を確認できず
      ・唯一裏が取れているのは **|score| による信頼度ランク**（50%→85.1%）

    したがって「形が出た」系は下位に置く。消すのではなく、
    **確かなものより上には出さない**。

⚠️ ここは表示順だけを決める。何を計算するかには関与しない。
   計算の可否は gemini_budget、送るかどうかは notify_ledger の担当。
"""
from src.utils import setup_logger

logger = setup_logger("priority")

# 数字が小さいほど先に出る。飛び番にしてあるのは後から差し込めるようにするため。
#
# 10番台 … 緊急。市場が壊れている可能性。今すぐ知る必要がある
# 20番台 … 今日の行動が変わる事実（値と時刻が確定しているもの）
# 30番台 … 検証で裏の取れた判断
# 40番台 … 参考になる観測（裏は取れていない）
# 50番台 … 読み物。今日でなくてもよい
RANK = {
    # ── 10番台: 緊急 ────────────────────────────
    "emergency_breadth":  10,   # 監視銘柄の広がりで見た全面安/高（年5〜15回に較正済み）
    "alert_escalation":   11,   # 発報後さらに1.5倍悪化した（悪化の伝達）
    "alert_monitor":      12,   # 日経先物などの急変
    "data_audit":         13,   # 表示中の数字が誤り。判断の土台が崩れている

    # ── 20番台: 今日の行動が変わる確定した事実 ──────────
    "morning_outlook":    20,   # 寄り付きの見当（先物と終値の差。事実）
    "risk_temp":          21,   # 緊張度（日経VI・VIX・円）
    "nikkei_impact":      22,   # 日経を動かした銘柄と、その偏り
    "us_movers":          23,   # 米国で大きく動いた業界と日本への波及先
    "gap_scan":           24,   # 窓開けと埋め具合
    "today_events":       25,   # 今日の予定（決算・指標の時刻）

    # ── 30番台: 検証で裏が取れた判断 ────────────────
    "prediction_verify":  30,   # 昨日の予測が当たったか（実績）
    "signal_confidence":  31,   # 信頼度ランク S/A/B/C（|score|別に実測済み）
    "scenario":           32,   # 3シナリオ
    "market_driver":      33,   # なぜ動いたか

    # ── 40番台: 参考の観測（効果は確認できていない）─────
    "technical":          40,
    "sector":             41,
    "catalyst":           42,
    "kabutan_warning":    43,
    "price_action":       44,   # 検証で優位性を確認できず
    "candlestick":        45,   # 同上。16種中2種のみ有意で、どちらも逆効果
    "sakata":             46,   # 同上。6種すべて有意でない

    # ── 50番台: 読み物 ────────────────────────
    "theme_ranking":      50,
    "character":          51,
    "note_article":       52,
}

# 裏が取れていないものに付ける但し書き。
# 黙って並べると「システムが推奨している」と読まれてしまう。
UNVERIFIED = {"technical", "price_action", "candlestick", "sakata",
              "sector", "catalyst", "kabutan_warning", "theme_ranking"}

# この順位より上は「緊急」として扱う（枠が足りなくても必ず出す）
URGENT_MAX = 19


def rank(key: str) -> int:
    """未登録は最後尾に置く。黙って上位に紛れ込ませない。"""
    r = RANK.get(key)
    if r is None:
        logger.warning(f"{key}: 優先順位が未登録。最後尾に置きます")
        return 99
    return r


def is_urgent(key: str) -> bool:
    return rank(key) <= URGENT_MAX


def is_verified(key: str) -> bool:
    return key not in UNVERIFIED


def order(blocks: list) -> list:
    """
    [{"key": ..., "text": ...}] を優先順位に並べ替える。

    同じ順位なら渡された順を保つ（安定ソート）ので、
    呼び出し側で細かい順序を調整できる。
    """
    return sorted([b for b in blocks if b and b.get("text")],
                  key=lambda b: rank(b.get("key", "")))


def fit(blocks: list, limit: int = 1024, joiner: str = "\n") -> str:
    """
    優先順位の高いものから詰めて、上限に収める。

    ⚠️ 途中で切らない。ブロック単位で落とす。
       文の途中で切れると意味が変わり、誤読のもとになる。

    ⚠️ 緊急（10番台）は上限を超えても必ず入れる。
       「市場が壊れている」という知らせを字数の都合で落とすのは本末転倒。
    """
    out, used = [], 0
    dropped = []
    for b in order(blocks):
        t = b["text"]
        cost = len(t) + len(joiner)
        if used + cost <= limit or is_urgent(b.get("key", "")):
            out.append(t)
            used += cost
        else:
            dropped.append(b.get("key", "?"))
    if dropped:
        logger.info(f"字数のため省略: {', '.join(dropped)}")
    return joiner.join(out)


if __name__ == "__main__":
    import io
    import sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace")
    groups = [("緊急（必ず出す）", 0, 19), ("今日の行動が変わる事実", 20, 29),
              ("検証で裏が取れた判断", 30, 39),
              ("参考の観測（効果は未確認）", 40, 49), ("読み物", 50, 99)]
    print("■ 表示の優先順位 — 緊急性 × 信頼度")
    for name, lo, hi in groups:
        print(f"\n【{name}】")
        for k, v in sorted(RANK.items(), key=lambda x: x[1]):
            if lo <= v <= hi:
                mark = "" if is_verified(k) else "  ※効果は未確認"
                print(f"  {v:>3}  {k}{mark}")
