"""
週次AIパフォーマンス報告モジュール
先週（月〜日）の予測記録を集計し、Geminiで失敗パターンを分析してTelegramに送信する
"""
import os
import json
import traceback
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from src.utils import setup_logger
    logger = setup_logger("weekly_performance")
except Exception:
    import logging
    logger = logging.getLogger("weekly_performance")
    logging.basicConfig(level=logging.INFO)

JST = timezone(timedelta(hours=9))
PRED_FILE = Path("data/predictions.json")


# ────────────────────────────────────────────────────────────────
# 内部ユーティリティ
# ────────────────────────────────────────────────────────────────

def _get_jst_now() -> datetime:
    return datetime.now(JST)


def _week_range(offset_weeks: int = 0):
    """
    offset_weeks=0 → 先週月〜日
    offset_weeks=-1 → 先々週月〜日
    戻り値: (start: date, end: date)
    """
    today = _get_jst_now().date()
    # 今日の曜日（月=0 … 日=6）
    days_since_monday = today.weekday()
    # 今週月曜日
    this_monday = today - timedelta(days=days_since_monday)
    # 先週月曜日
    target_monday = this_monday + timedelta(weeks=offset_weeks - 1)
    target_sunday = target_monday + timedelta(days=6)
    return target_monday, target_sunday


def _load_predictions() -> list:
    try:
        if PRED_FILE.exists():
            with open(PRED_FILE, encoding="utf-8") as f:
                data = json.load(f)
            return data.get("predictions", [])
    except Exception as e:
        logger.error(f"predictions.json 読込エラー: {e}")
    return []


def _filter_week(predictions: list, start, end) -> list:
    """指定週の検証済み予測のみ返す"""
    result = []
    for p in predictions:
        try:
            d = datetime.strptime(p["date"], "%Y-%m-%d").date()
        except Exception:
            continue
        if start <= d <= end and p.get("verified") is True and p.get("correct") is not None:
            result.append(p)
    return result


def _calc_accuracy(records: list) -> float:
    if not records:
        return 0.0
    wins = sum(1 for r in records if r.get("correct") is True)
    return wins / len(records)


def _gemini_analyze(wrong_records: list) -> list:
    """外れた予測記録をGeminiで分析して共通失敗パターンを返す"""
    if not wrong_records:
        return []

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        logger.warning("GEMINI_API_KEY 未設定 → フォールバック")
        return ["データ不足のため分析できません"]

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))

        records_text = json.dumps(wrong_records, ensure_ascii=False, indent=2)
        prompt = (
            f"先週の予測で外れた記録:\n{records_text}\n\n"
            "これらの共通点や失敗パターンを3点以内で簡潔に教えてください。日本語で。"
        )
        response = model.generate_content(prompt)
        text = response.text.strip()

        # 箇条書きを行分割してリストに変換
        patterns = []
        for line in text.splitlines():
            line = line.strip().lstrip("・•-*123456789. ")
            if line:
                patterns.append(line)
        return patterns[:3] if patterns else ["分析結果が取得できませんでした"]

    except Exception as e:
        logger.error(f"Gemini 分析エラー: {e}")
        logger.debug(traceback.format_exc())
        return ["データ不足のため分析できません"]


def _build_telegram_message(
    week_label: str,
    wins: int,
    losses: int,
    total: int,
    accuracy_pct: str,
    trend_arrow: str,
    weak_patterns: list,
) -> str:
    patterns_str = "\n".join(f"・{p}" for p in weak_patterns) if weak_patterns else "・パターンなし"

    # 今週の注意点（最初のパターンから抽出）
    caution = weak_patterns[0] if weak_patterns else "引き続き慎重に予測してください"

    msg = (
        f"📊 週次AIパフォーマンスレポート\n"
        f"{week_label}\n\n"
        f"✅ 正解: {wins}回  ❌ 不正解: {losses}回\n"
        f"🎯 正解率: {accuracy_pct}  {trend_arrow}\n\n"
        f"❌ 外れたパターン:\n"
        f"{patterns_str}\n\n"
        f"💡 今週の注意: {caution}\n\n"
        f"━━━━━━━━━━━━━━\n"
        f"🤖 AIは自分のミスから学んでいます\n"
        f"今週もよろしくお願いします！"
    )
    return msg


def _build_html(week_label: str, wins: int, losses: int, total: int,
                accuracy_pct: str, trend_arrow: str, weak_patterns: list) -> str:
    patterns_html = "".join(f"<li>{p}</li>" for p in weak_patterns) if weak_patterns else "<li>パターンなし</li>"
    html = f"""
<div class="weekly-performance" style="background:#1a1a2e;color:#eee;border-radius:12px;padding:20px;margin:16px 0;font-family:sans-serif;">
  <h3 style="color:#4fc3f7;margin-top:0;">📊 週次AIパフォーマンス</h3>
  <p style="color:#aaa;margin:0 0 12px;">{week_label}</p>
  <div style="display:flex;gap:20px;margin-bottom:12px;">
    <span>✅ 正解 <strong style="color:#81c784;">{wins}回</strong></span>
    <span>❌ 不正解 <strong style="color:#e57373;">{losses}回</strong></span>
    <span>🎯 正解率 <strong style="color:#ffb74d;">{accuracy_pct}</strong></span>
  </div>
  <p style="margin:4px 0;">{trend_arrow}</p>
  <p style="margin:12px 0 4px;color:#4fc3f7;">❌ 外れたパターン:</p>
  <ul style="margin:0;padding-left:20px;color:#eee;">{patterns_html}</ul>
</div>
"""
    return html


# ────────────────────────────────────────────────────────────────
# パブリック API
# ────────────────────────────────────────────────────────────────

def generate_weekly_report() -> dict:
    """
    先週（月〜日）の予測記録を集計してレポートを生成する。

    返り値:
        available: bool
        week_label: str       "2026年6月3日〜9日"
        wins: int
        losses: int
        total: int
        accuracy: float       0.0〜1.0
        accuracy_pct: str     "70.0%"
        prev_accuracy: float  先々週の正解率
        trend_arrow: str      "📈 +5.0%改善" or "📉 -3.0%悪化" or "➡️ 変化なし"
        weak_patterns: list[str]
        telegram_message: str
        html: str
    """
    try:
        predictions = _load_predictions()
        if not predictions:
            logger.info("predictions.json が空 → available=False")
            return {"available": False}

        # 先週の範囲
        week_start, week_end = _week_range(offset_weeks=0)
        week_records = _filter_week(predictions, week_start, week_end)

        if not week_records:
            logger.info(f"先週({week_start}〜{week_end})の検証済み予測なし → available=False")
            return {"available": False}

        # 先々週（比較用）
        prev_start, prev_end = _week_range(offset_weeks=-1)
        prev_records = _filter_week(predictions, prev_start, prev_end)

        wins   = sum(1 for r in week_records if r.get("correct") is True)
        losses = sum(1 for r in week_records if r.get("correct") is False)
        total  = len(week_records)
        accuracy = _calc_accuracy(week_records)
        accuracy_pct = f"{accuracy * 100:.1f}%"

        prev_accuracy = _calc_accuracy(prev_records) if prev_records else 0.0

        # トレンド矢印
        diff = (accuracy - prev_accuracy) * 100
        if abs(diff) < 0.1:
            trend_arrow = "➡️ 変化なし"
        elif diff > 0:
            trend_arrow = f"📈 先週比 +{diff:.1f}%改善"
        else:
            trend_arrow = f"📉 先週比 {diff:.1f}%悪化"

        # 週ラベル（例: 2026年6月3日〜9日）
        week_label = (
            f"{week_start.year}年{week_start.month}月{week_start.day}日"
            f"〜{week_end.month}月{week_end.day}日"
        )

        # 外れた予測を Gemini に渡して失敗パターン分析
        wrong_records = [r for r in week_records if r.get("correct") is False]
        weak_patterns = _gemini_analyze(wrong_records)

        telegram_message = _build_telegram_message(
            week_label=week_label,
            wins=wins,
            losses=losses,
            total=total,
            accuracy_pct=accuracy_pct,
            trend_arrow=trend_arrow,
            weak_patterns=weak_patterns,
        )

        html = _build_html(
            week_label=week_label,
            wins=wins,
            losses=losses,
            total=total,
            accuracy_pct=accuracy_pct,
            trend_arrow=trend_arrow,
            weak_patterns=weak_patterns,
        )

        logger.info(f"週次パフォーマンスレポート生成完了: {week_label} 正解率={accuracy_pct}")

        return {
            "available": True,
            "week_label": week_label,
            "wins": wins,
            "losses": losses,
            "total": total,
            "accuracy": accuracy,
            "accuracy_pct": accuracy_pct,
            "prev_accuracy": prev_accuracy,
            "trend_arrow": trend_arrow,
            "weak_patterns": weak_patterns,
            "telegram_message": telegram_message,
            "html": html,
        }

    except Exception as e:
        logger.error(f"週次レポート生成エラー: {e}")
        logger.debug(traceback.format_exc())
        return {"available": False}


def send_weekly_telegram(message: str) -> bool:
    """週次パフォーマンスメッセージをTelegramに送信する"""
    if not message:
        logger.info("送信メッセージが空のためスキップ")
        return False

    token   = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    skip = {"ここにBotFatherのトークン", "ここにあなたのChat ID", ""}
    if token in skip or chat_id in skip:
        logger.info("Telegram 未設定スキップ")
        return False

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message},
            timeout=15,
        )
        r.raise_for_status()
        logger.info("週次パフォーマンス Telegram 送信 ✅")
        return True
    except Exception as e:
        logger.error(f"週次パフォーマンス Telegram 送信失敗: {e}")
        return False
