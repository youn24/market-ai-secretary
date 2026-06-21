"""
完全自律エージェント（L5b）
毎朝「今日は何が最重要か」をAI自身が市場状態を読んで決める。
VIX急騰なら暴落分析を優先、FOMC週なら金利分析を優先、など。
すべての分析結果を統合して「今日のミッションブリーフィング」を生成する。
"""
import os
import logging
from src.utils import get_jst_now

logger = logging.getLogger(__name__)

# 市場レジームの定義とそれぞれで重要なこと
REGIME_RULES = {
    "crisis": {
        "condition": lambda vix, fg, rs: vix >= 35 or rs <= -3,
        "label": "🚨 市場危機モード",
        "focus": "暴落リスク・歴史的暴落との比較・ポジション縮小検討",
        "priority": ["historical_crash", "vix_extreme", "safe_haven"],
    },
    "fear": {
        "condition": lambda vix, fg, rs: vix >= 25 or fg <= 25,
        "label": "😰 恐怖モード",
        "focus": "恐怖心理の分析・逆張りチャンスの評価・下値サポート確認",
        "priority": ["sentiment_extreme", "technical_support", "contrarian"],
    },
    "greed": {
        "condition": lambda vix, fg, rs: fg >= 75 or rs >= 3,
        "label": "😱 過熱モード",
        "focus": "バブル兆候・過熱感・利確タイミング・リスク管理",
        "priority": ["bubble_check", "take_profit", "risk_management"],
    },
    "normal": {
        "condition": lambda vix, fg, rs: True,
        "label": "😊 通常モード",
        "focus": "トレンドフォロー・セクターローテーション・次週の予定確認",
        "priority": ["trend", "sector_rotation", "calendar"],
    },
}

# 曜日別の特別タスク
WEEKDAY_TASKS = {
    0: "📅 週初め：先週の振り返りと今週の戦略立案",
    1: "🔍 火曜日：テクニカル指標の精査",
    2: "🌍 水曜日：マクロ指標・FRB動向確認（FOMC多い曜日）",
    3: "📊 木曜日：週次統計発表確認・セクター状況確認",
    4: "📆 金曜日：週末ポジション調整・来週のリスクチェック",
}


def _detect_regime(prices, risk, fear_greed) -> dict:
    """現在の市場レジームを判定"""
    vix = prices.get("^VIX", {}).get("latest", 20) or 20
    fg = fear_greed.get("score", 50) or 50
    rs = risk.get("score", 0)

    for name, rule in REGIME_RULES.items():
        if rule["condition"](vix, fg, rs):
            return {
                "name": name,
                "label": rule["label"],
                "focus": rule["focus"],
                "priority": rule["priority"],
                "vix": vix,
                "fg": fg,
                "risk_score": rs,
            }
    return REGIME_RULES["normal"]


def _build_synthesis_prompt(prices, risk, fear_greed, news,
                            technical, historical_analysis, fred_data,
                            fomc_sentiment, multi_consensus, regime) -> str:
    """全分析結果をまとめて自律エージェントに渡すプロンプト"""
    now = get_jst_now().strftime("%Y-%m-%d %H:%M")
    weekday_task = WEEKDAY_TASKS.get(get_jst_now().weekday(), "")

    # 主要指標
    vix = prices.get("^VIX", {}).get("latest", "---")
    sp_chg = prices.get("^GSPC", {}).get("change_pct", 0) or 0
    nk_chg = prices.get("^N225", {}).get("change_pct", 0) or 0
    fg = fear_greed.get("score", 50) or 50

    # マルチエージェント合議結果
    consensus_summary = ""
    if multi_consensus and multi_consensus.get("available"):
        v = multi_consensus.get("verdict", {})
        dir_ja = {"bull": "上昇", "bear": "下落", "neutral": "中立"}
        consensus_summary = (
            f"4エージェント合議: {dir_ja.get(v.get('direction','neutral'),'---')}"
            f" ({v.get('consensus_level','')}) 票比{v.get('vote_ratio',0):.0%}"
        )

    # テクニカル要約
    tech_summary = ""
    if technical and technical.get("available"):
        signals = []
        for r in technical.get("results", [])[:3]:
            rsi = r.get("rsi", 50)
            sig = "過熱" if rsi > 70 else "売られすぎ" if rsi < 30 else "中立"
            signals.append(f"{r.get('label','')}:{sig}")
        tech_summary = " / ".join(signals)

    # 歴史分析
    hist_summary = ""
    if historical_analysis and historical_analysis.get("available"):
        reg = historical_analysis.get("regime", {})
        hist_summary = f"市場レジーム:{reg.get('regime','---')} ({reg.get('description','')[:50]})"

    # FOMC
    fomc_summary = ""
    if fomc_sentiment and fomc_sentiment.get("available"):
        sent = fomc_sentiment.get("sentiment", {})
        fomc_summary = f"FOMCスタンス: {sent.get('label','---')}"

    prompt = f"""あなたは市場分析の司令官AIです。今日（{now} JST）の市場状態を総合評価して、
投資家にとって「今日最も重要なこと」を特定してください。

【現在の市場レジーム】
{regime.get('label','')} — {regime.get('focus','')}

【市場データ】
VIX: {vix} | Fear&Greed: {fg} | S&P500: {sp_chg:+.2f}% | 日経225: {nk_chg:+.2f}%

【各分析の結果】
{f'・合議: {consensus_summary}' if consensus_summary else ''}
{f'・テクニカル: {tech_summary}' if tech_summary else ''}
{f'・歴史分析: {hist_summary}' if hist_summary else ''}
{f'・FOMC: {fomc_summary}' if fomc_summary else ''}
{f'・曜日タスク: {weekday_task}' if weekday_task else ''}

以下の形式で回答してください（日本語・各項目100字以内）：

【今日のミッション】（一行で今日の最重要テーマ）

【最優先で見るべきこと】
1. （具体的なシグナルや指標）
2. （具体的なシグナルや指標）
3. （具体的なシグナルや指標）

【今日のリスク】（最大のリスク要因を一文で）

【推奨アクション】（中学生でもわかる言葉で、具体的に）"""

    return prompt


def run(prices, risk, fear_greed, news,
        technical=None, historical_analysis=None,
        fred_data=None, fomc_sentiment=None,
        multi_consensus=None) -> dict:
    """完全自律エージェントを実行して今日のミッションを決定"""
    logger.info("--- 完全自律エージェント ---")
    result = {"available": False}

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return result

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))

        # レジーム検出
        regime = _detect_regime(prices, risk, fear_greed)
        logger.info(f"  市場レジーム: {regime['label']}")

        # 合議結果を踏まえた総合判断プロンプト
        prompt = _build_synthesis_prompt(
            prices, risk, fear_greed, news,
            technical, historical_analysis, fred_data,
            fomc_sentiment, multi_consensus, regime
        )

        resp = model.generate_content(prompt)
        full_text = resp.text.strip()

        # セクション抽出
        mission = ""
        priorities = []
        risk_note = ""
        action = ""

        lines = full_text.split("\n")
        current_section = None
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if "ミッション" in line:
                current_section = "mission"
            elif "最優先" in line or "見るべき" in line:
                current_section = "priorities"
            elif "リスク" in line and "最大" not in line and len(line) < 20:
                current_section = "risk"
            elif "推奨" in line or "アクション" in line:
                current_section = "action"
            else:
                if current_section == "mission" and not mission:
                    mission = line
                elif current_section == "priorities" and line.startswith(("1.", "2.", "3.", "・")):
                    priorities.append(line.lstrip("123.・ "))
                elif current_section == "risk" and not risk_note:
                    risk_note = line
                elif current_section == "action" and not action:
                    action = line

        # フォールバック
        if not mission:
            mission = full_text[:100]

        result = {
            "available": True,
            "regime": regime,
            "todays_mission": mission,
            "priorities": priorities[:3],
            "risk_note": risk_note,
            "action": action,
            "full_report": full_text,
            "weekday_task": WEEKDAY_TASKS.get(get_jst_now().weekday(), ""),
        }

        logger.info(f"✅ 自律エージェント: {mission[:60]}")
        return result

    except Exception as e:
        logger.error(f"自律エージェントエラー: {e}")
        return result


def format_telegram(data: dict) -> str:
    if not data.get("available"):
        return ""
    regime = data.get("regime", {})
    lines = [
        "🧠 *完全自律エージェント — 今日のミッション*",
        "━━━━━━━━━━━━━━━",
        f"{regime.get('label', '')}",
        "",
        f"📋 *今日のテーマ*",
        data.get("todays_mission", "---"),
        "",
        "🎯 *最優先で見るべきこと*",
    ]
    for i, p in enumerate(data.get("priorities", []), 1):
        lines.append(f"  {i}. {p}")
    if data.get("risk_note"):
        lines += ["", f"⚠️ *今日のリスク*", data["risk_note"]]
    if data.get("action"):
        lines += ["", f"💡 *推奨アクション*", data["action"]]
    return "\n".join(lines)
