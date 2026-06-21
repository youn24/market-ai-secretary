"""
自己批判エンジン（L5e）
過去の予測結果を振り返り、「なぜ間違えたか」をAI自身が反省して
今後の分析に活かす。人間の投資家が日記をつけるのと同じ発想。
"""
import json
import logging
import os
from pathlib import Path
from datetime import datetime, timedelta
from src.utils import get_jst_now

logger = logging.getLogger(__name__)

DATA_PATH = Path("data/predictions.json")
MEMORY_PATH = Path("data/ai_memory.json")


def _load_recent_verified(days: int = 14) -> list:
    """直近N日の検証済み予測を取得"""
    if not DATA_PATH.exists():
        return []
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            all_preds = json.load(f)
        if not isinstance(all_preds, list):
            return []
        cutoff = (get_jst_now() - timedelta(days=days)).strftime("%Y-%m-%d")
        verified = [
            p for p in all_preds
            if p.get("correct") is not None and p.get("date", "") >= cutoff
        ]
        return verified
    except Exception:
        return []


def _load_memory_summary() -> str:
    """AI記憶から過去の分析要約を取得"""
    if not MEMORY_PATH.exists():
        return ""
    try:
        with open(MEMORY_PATH, "r", encoding="utf-8") as f:
            mem = json.load(f)
        entries = mem.get("entries", [])
        if not entries:
            return ""
        # 直近5件の記憶を返す
        recent = entries[-5:]
        return "\n".join(
            f"  [{e.get('date','')}] {e.get('summary','')[:80]}"
            for e in recent
        )
    except Exception:
        return ""


def _build_critique_prompt(verified: list, memory_summary: str) -> str:
    """自己批判用プロンプトを構築"""
    correct = [p for p in verified if p.get("correct")]
    wrong = [p for p in verified if not p.get("correct")]

    wrong_desc = ""
    for p in wrong[:5]:
        direction = {"bull": "上昇予測", "bear": "下落予測", "neutral": "中立予測"}.get(
            p.get("direction", ""), p.get("direction", ""))
        vix = p.get("vix", "不明")
        move = p.get("move")
        move_str = f"{move:+.1f}%" if move is not None else "不明"
        wrong_desc += (
            f"  ・{p.get('date','')} {direction} → 実際{move_str}"
            f" (VIX={vix})\n"
        )

    prompt = f"""あなたは市場AI秘書の自己批判・学習担当AIです。
過去の予測実績を振り返り、次の分析に活かすための「反省と改善点」を生成してください。

【直近{len(verified)}件の予測結果】
正解: {len(correct)}件 / 不正解: {len(wrong)}件
正解率: {len(correct)/max(len(verified),1)*100:.0f}%

【間違えた予測（詳細）】
{wrong_desc if wrong_desc else "  なし（全問正解）"}

【AI記憶（過去の分析メモ）】
{memory_summary if memory_summary else "  記録なし"}

以下の形式で200字以内で回答してください：

【反省点】（なぜ間違えたか、パターンの分析）
【改善点】（今後どう気をつけるか、具体的に）
【今日への教訓】（今日の分析で特に注意すべき1点）"""

    return prompt


def run(prices: dict = None, risk: dict = None) -> dict:
    """自己批判エンジンを実行"""
    logger.info("--- 自己批判エンジン ---")
    result = {"available": False}

    api_key = os.getenv("GEMINI_API_KEY", "").strip()

    verified = _load_recent_verified(days=14)
    memory_summary = _load_memory_summary()

    if not verified:
        logger.info("  検証済みデータなし — 自己批判スキップ")
        return {"available": False, "reason": "予測データ蓄積中"}

    wrong = [p for p in verified if not p.get("correct")]
    correct = [p for p in verified if p.get("correct")]
    accuracy = len(correct) / len(verified) * 100

    # データがあればGeminiで自己批判
    ai_critique = ""
    if api_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
            prompt = _build_critique_prompt(verified, memory_summary)
            resp = model.generate_content(prompt)
            ai_critique = resp.text.strip()
            logger.info("  Gemini自己批判生成完了")
        except Exception as e:
            logger.warning(f"  Gemini呼び出し失敗: {e}")

    # パターン分析
    # VIX帯別の間違い分析
    vix_wrong = {}
    for p in wrong:
        vix = float(p.get("vix", 20) or 20)
        zone = "低(VIX<15)" if vix < 15 else "中(VIX15-25)" if vix < 25 else "高(VIX>25)"
        vix_wrong[zone] = vix_wrong.get(zone, 0) + 1

    worst_zone = max(vix_wrong, key=vix_wrong.get) if vix_wrong else None

    # 方向別の間違い
    dir_wrong = {}
    for p in wrong:
        d = p.get("direction", "neutral")
        dir_wrong[d] = dir_wrong.get(d, 0) + 1

    worst_direction = max(dir_wrong, key=dir_wrong.get) if dir_wrong else None
    dir_ja = {"bull": "上昇予測", "bear": "下落予測", "neutral": "中立予測"}

    lessons = []
    if worst_zone:
        lessons.append(f"{worst_zone}での間違いが多い（{vix_wrong[worst_zone]}回）")
    if worst_direction:
        lessons.append(f"{dir_ja.get(worst_direction,worst_direction)}が外れやすい（{dir_wrong[worst_direction]}回）")

    result = {
        "available": True,
        "period_days": 14,
        "total_verified": len(verified),
        "correct_count": len(correct),
        "wrong_count": len(wrong),
        "accuracy": round(accuracy, 1),
        "ai_critique": ai_critique,
        "lessons": lessons,
        "vix_wrong_pattern": vix_wrong,
        "direction_wrong_pattern": dir_wrong,
    }

    logger.info(f"✅ 自己批判完了: 正解率{accuracy:.0f}% 教訓{len(lessons)}件")
    return result


def format_telegram(data: dict) -> str:
    if not data.get("available"):
        return ""
    acc = data.get("accuracy", 0)
    total = data.get("total_verified", 0)
    wrong = data.get("wrong_count", 0)
    emoji = "🎯" if acc >= 65 else "🔶" if acc >= 50 else "⚠️"

    lines = [
        "🔍 *自己批判エンジン — AI反省日記*",
        "━━━━━━━━━━━━━━━",
        f"{emoji} 直近14日: {acc:.0f}% ({total-wrong}/{total}件正解)",
        "",
    ]
    if data.get("lessons"):
        lines.append("📌 発見した弱点:")
        for lesson in data["lessons"]:
            lines.append(f"  ・{lesson}")
        lines.append("")
    critique = data.get("ai_critique", "")
    if critique:
        # 「今日への教訓」の部分だけ抽出
        for line in critique.split("\n"):
            if "教訓" in line or "改善" in line:
                clean = line.replace("【今日への教訓】", "").replace("【改善点】", "").strip("：: 】")
                if clean:
                    lines.append(f"💡 {clean}")
                    break
    return "\n".join(lines)
