"""
予測精度モニタリング（週次）
- 直近4週分の週別正解率をグラフ化
- 外れパターン分析（方向別・VIX帯・スコア幅）
- 改善傾向をGeminiが一言コメント
"""
import os
import json
import traceback
from datetime import datetime, timedelta
from pathlib import Path

from src.utils import setup_logger, get_jst_now, get_dirs

logger = setup_logger("accuracy_monitor")

PRED_FILE = Path("data/predictions.json")


def _load_predictions() -> list:
    try:
        if PRED_FILE.exists():
            with open(PRED_FILE, encoding="utf-8") as f:
                data = json.load(f)
            return [p for p in data.get("predictions", []) if p.get("verified")]
    except Exception:
        logger.debug(traceback.format_exc())
    return []


def _week_range(weeks_ago: int) -> tuple[str, str]:
    """weeks_ago週前の月曜〜日曜の日付範囲を返す"""
    now = get_jst_now()
    # 今週の月曜日を基点（月曜スタートの週）
    this_monday = now - timedelta(days=now.weekday())
    start = this_monday - timedelta(weeks=weeks_ago)
    end   = start + timedelta(days=6)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def _calc_weekly_stats(preds: list) -> list:
    """直近4週分の週別成績を計算"""
    weeks = []
    for i in range(3, -1, -1):   # 3週前 → 今週
        start, end = _week_range(i)
        week_preds = [p for p in preds if start <= p["date"] <= end]
        total   = len(week_preds)
        correct = sum(1 for p in week_preds if p.get("correct"))
        rate    = round(correct / total * 100) if total > 0 else None
        label   = f"W-{i}" if i > 0 else "今週"
        weeks.append({
            "label":   label,
            "start":   start,
            "end":     end,
            "total":   total,
            "correct": correct,
            "rate":    rate,
        })
    return weeks


def _analyze_patterns(preds: list) -> dict:
    """外れパターンを分析する（方向別・VIX帯・スコア幅）"""
    if not preds:
        return {}

    # ── 方向別正解率 ──
    dir_stats = {}
    for d in ("bull", "bear", "neutral"):
        group = [p for p in preds if p.get("direction") == d]
        total   = len(group)
        correct = sum(1 for p in group if p.get("correct"))
        rate    = round(correct / total * 100) if total > 0 else None
        dir_stats[d] = {"total": total, "correct": correct, "rate": rate}

    # ── VIX帯別正解率（低<15 / 普通15-25 / 高>25）──
    vix_bands = {
        "低(VIX<15)":    [p for p in preds if p.get("vix") and p["vix"] < 15],
        "普通(15-25)":   [p for p in preds if p.get("vix") and 15 <= p["vix"] <= 25],
        "高(VIX>25)":    [p for p in preds if p.get("vix") and p["vix"] > 25],
    }
    vix_stats = {}
    for band, group in vix_bands.items():
        total   = len(group)
        correct = sum(1 for p in group if p.get("correct"))
        rate    = round(correct / total * 100) if total > 0 else None
        vix_stats[band] = {"total": total, "correct": correct, "rate": rate}

    # ── スコア幅別正解率（強気高・強気低・弱気低・弱気高） ──
    score_bands = {
        "強強気(>8)":   [p for p in preds if (p.get("score") or 0) > 8],
        "強気(4-8)":    [p for p in preds if 4 < (p.get("score") or 0) <= 8],
        "中立(-4〜4)":  [p for p in preds if -4 <= (p.get("score") or 0) <= 4],
        "弱気(-8〜-4)": [p for p in preds if -8 <= (p.get("score") or 0) < -4],
        "強弱気(<-8)":  [p for p in preds if (p.get("score") or 0) < -8],
    }
    score_stats = {}
    for band, group in score_bands.items():
        total   = len(group)
        correct = sum(1 for p in group if p.get("correct"))
        rate    = round(correct / total * 100) if total > 0 else None
        score_stats[band] = {"total": total, "correct": correct, "rate": rate}

    # ── 苦手パターンを特定（正解率30%以下でデータが3件以上） ──
    weak_patterns = []
    for name, st in {**dir_stats, **vix_stats, **score_stats}.items():
        if st["total"] >= 3 and st["rate"] is not None and st["rate"] <= 35:
            weak_patterns.append(f"{name}: {st['rate']}% ({st['correct']}/{st['total']}件)")

    return {
        "direction": dir_stats,
        "vix":       vix_stats,
        "score":     score_stats,
        "weak_patterns": weak_patterns,
    }


def _make_trend_chart(weekly_stats: list, overall_30d_rate) -> str | None:
    """直近4週の正解率棒グラフを生成してパスを返す"""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        import japanize_matplotlib

        dirs = get_dirs()
        out_path = str(dirs["charts"] / "accuracy_trend.png")

        fig, ax = plt.subplots(figsize=(8, 4))
        fig.patch.set_facecolor("#0f1623")
        ax.set_facecolor("#0f1623")

        labels = [w["label"] for w in weekly_stats]
        rates  = [w["rate"] if w["rate"] is not None else 0 for w in weekly_stats]
        totals = [w["total"] for w in weekly_stats]
        colors = ["#00e676" if r >= 50 else "#ff4444" for r in rates]

        bars = ax.bar(labels, rates, color=colors, width=0.5,
                      edgecolor="#1e2d42", linewidth=1.2)

        # 50%ライン
        ax.axhline(y=50, color="#ffd740", linewidth=1.5, linestyle="--", alpha=0.8)
        ax.text(3.5, 51.5, "50% (基準)", color="#ffd740", fontsize=8, ha="right")

        # 30日平均ライン
        if overall_30d_rate is not None:
            ax.axhline(y=overall_30d_rate, color="#40c4ff", linewidth=1.5,
                       linestyle=":", alpha=0.8)
            ax.text(3.5, overall_30d_rate + 1.5, f"30日平均 {overall_30d_rate}%",
                    color="#40c4ff", fontsize=8, ha="right")

        # バーの上に数値とサンプル数
        for bar, rate, total in zip(bars, rates, totals):
            if total > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, rate + 1.5,
                        f"{rate}%\n({total}件)", ha="center", va="bottom",
                        color="#dde8ff", fontsize=9, fontweight="bold")
            else:
                ax.text(bar.get_x() + bar.get_width() / 2, 5,
                        "データなし", ha="center", va="bottom",
                        color="#7a8fa8", fontsize=8)

        ax.set_ylim(0, 105)
        ax.set_ylabel("正解率 (%)", color="#7a8fa8", fontsize=10)
        ax.set_title("AI予測 週別正解率トレンド（過去4週）",
                     color="#dde8ff", fontsize=13, fontweight="bold", pad=12)

        for spine in ax.spines.values():
            spine.set_color("#1e2d42")
        ax.tick_params(colors="#7a8fa8")
        ax.yaxis.label.set_color("#7a8fa8")

        plt.tight_layout()
        plt.savefig(out_path, dpi=130, bbox_inches="tight",
                    facecolor=fig.get_facecolor())
        plt.close(fig)

        logger.info(f"✅ 精度トレンドチャート生成: {out_path}")
        return out_path

    except Exception:
        logger.error("精度チャート生成エラー"); logger.debug(traceback.format_exc())
        return None


def _ai_trend_comment(weekly_stats: list, patterns: dict, overall_30d_rate) -> str:
    """Geminiが精度トレンドに一言コメントを生成"""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return ""

    # データが少なければスキップ
    total_verified = sum(w["total"] for w in weekly_stats)
    if total_verified < 5:
        return ""

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))

        # 週別サマリー文
        week_lines = []
        for w in weekly_stats:
            if w["total"] > 0:
                week_lines.append(f"{w['label']}: {w['rate']}% ({w['correct']}/{w['total']}件)")
            else:
                week_lines.append(f"{w['label']}: データなし")

        # 苦手パターン
        weak = patterns.get("weak_patterns", [])
        weak_txt = "\n".join(f"・{p}" for p in weak) if weak else "特になし"

        # 方向別
        dir_s = patterns.get("direction", {})
        dir_txt = "  ".join(
            f"{d}:{v.get('rate','?')}%({v.get('total',0)}件)"
            for d, v in dir_s.items() if v.get("total", 0) > 0
        )

        prompt = f"""あなたは市場AI秘書の予測精度コーチです。
過去4週間の予測成績を見て、中学生でもわかるように短く総評してください。

【週別正解率】
{chr(10).join(week_lines)}

【30日平均正解率】 {overall_30d_rate}%

【方向別正解率（直近30日）】
{dir_txt}

【苦手なパターン（正解率35%以下）】
{weak_txt}

以下の形式で答えてください（合計150文字以内）：

🔍 総評（1〜2文）: 精度が改善中か悪化中か、正直に。
⚠️ 注意点（1文）: 一番外れやすいパターンを一言で。
💡 来週のヒント（1文）: 来週どう使えばいいか。

断定は避け、「〜傾向があります」のような表現で。"""

        response = model.generate_content(prompt)
        return response.text.strip()

    except Exception:
        logger.debug(traceback.format_exc())
        return ""


def run() -> dict:
    """予測精度モニタリングのメイン処理"""
    logger.info("=== 精度モニタリング開始 ===")

    preds = _load_predictions()
    if not preds:
        return {"available": False, "reason": "検証済みデータなし"}

    # 直近30日の予測を対象に詳細分析
    cutoff30 = (get_jst_now() - timedelta(days=30)).strftime("%Y-%m-%d")
    preds_30d = [p for p in preds if p["date"] >= cutoff30]

    # 30日全体の正解率
    total_30  = len(preds_30d)
    correct_30 = sum(1 for p in preds_30d if p.get("correct"))
    rate_30   = round(correct_30 / total_30 * 100) if total_30 > 0 else None

    # 週別統計
    weekly_stats = _calc_weekly_stats(preds)

    # パターン分析（30日分）
    patterns = _analyze_patterns(preds_30d)

    # グラフ生成
    chart_path = _make_trend_chart(weekly_stats, rate_30)

    # AIコメント
    ai_comment = _ai_trend_comment(weekly_stats, patterns, rate_30)

    logger.info(f"✅ 精度モニタリング完了: 30日正解率={rate_30}%")

    return {
        "available":    True,
        "rate_30d":     rate_30,
        "total_30d":    total_30,
        "correct_30d":  correct_30,
        "weekly_stats": weekly_stats,
        "patterns":     patterns,
        "chart_path":   chart_path,
        "ai_comment":   ai_comment,
    }
