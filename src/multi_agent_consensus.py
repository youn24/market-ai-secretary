"""
マルチエージェント合議システム（L5a）
4人のAIエージェントが異なる視点で分析し、多数決で最終判断を下す。
全員一致 → 高確信シグナル / 分裂 → 要注意シグナル。
"""
import os
import logging
from src.utils import get_jst_now

logger = logging.getLogger(__name__)

# 4つのエージェント定義
AGENTS = [
    {
        "id": "bull",
        "name": "強気派エージェント",
        "emoji": "🐂",
        "role": (
            "あなたは楽観的な強気の投資家AIです。"
            "以下の市場データから「なぜ市場が上昇する可能性があるか」を分析してください。"
            "ポジティブなシグナルを見つけ、強気の根拠を3つ挙げてください。"
            "【必須】日経平均・VIX・S&P500など実際の数値を必ず引用して根拠を示してください。"
            "最後に必ず「予測: 上昇/中立/下落」と「確信度: 1〜5」を明記してください。"
        ),
    },
    {
        "id": "bear",
        "name": "弱気派エージェント",
        "emoji": "🐻",
        "role": (
            "あなたは慎重なリスク管理者AIです。"
            "以下の市場データから「なぜ市場が下落するリスクがあるか」を分析してください。"
            "ネガティブなシグナルを見つけ、弱気の根拠を3つ挙げてください。"
            "【必須】VIX・ドル円・金利など実際の数値を必ず引用して根拠を示してください。"
            "最後に必ず「予測: 上昇/中立/下落」と「確信度: 1〜5」を明記してください。"
        ),
    },
    {
        "id": "macro",
        "name": "マクロ分析エージェント",
        "emoji": "🌍",
        "role": (
            "あなたはマクロ経済の専門家AIです。"
            "金利・為替・地政学リスク・経済指標の観点から市場環境を分析してください。"
            "短期・中期のマクロトレンドを評価し、今後の市場方向性を示してください。"
            "【必須】ドル円レート・米10年金利・Fear&Greed指数など実数値を引用してください。"
            "最後に必ず「予測: 上昇/中立/下落」と「確信度: 1〜5」を明記してください。"
        ),
    },
    {
        "id": "risk",
        "name": "リスク管理エージェント",
        "emoji": "🛡️",
        "role": (
            "あなたはリスク・リワード比の専門家AIです。"
            "現在の市場のリスク水準を評価し、リスク・リワード比を計算してください。"
            "投資家が取るべきポジションサイズとリスク管理の観点から予測を行ってください。"
            "【必須】VIX水準・リスクスコアなど実数値を根拠に使ってください。"
            "最後に必ず「予測: 上昇/中立/下落」と「確信度: 1〜5」を明記してください。"
        ),
    },
]


def _build_market_brief(prices, risk, fear_greed, news, technical=None, fred_data=None) -> str:
    """全エージェントに渡す市場データのブリーフィング"""
    vix = prices.get("^VIX", {}).get("latest", "---")
    sp_chg = prices.get("^GSPC", {}).get("change_pct", 0) or 0
    nk_chg = prices.get("^N225", {}).get("change_pct", 0) or 0
    usdjpy = prices.get("USDJPY=X", {}).get("latest", "---")
    gold = prices.get("GC=F", {}).get("latest", "---")
    fg = fear_greed.get("score", 50) or 50
    fg_label = fear_greed.get("rating_ja", "---")
    risk_score = risk.get("score", 0)
    risk_signals = " / ".join(risk.get("signals", [])[:3])

    tech_summary = ""
    if technical and technical.get("available"):
        for r in technical.get("results", []):
            if "S&P" in r.get("label", "") or "SP500" in r.get("label", ""):
                rsi = r.get("rsi", "---")
                macd = r.get("macd_hist", 0)
                bb = r.get("bb_pct", "---")
                tech_summary = f"S&P500 RSI:{rsi:.0f} MACD:{macd:+.3f} BB位置:{bb:.0f}%"
                break

    fred_summary = ""
    if fred_data and fred_data.get("available"):
        fred_summary = fred_data.get("summary", "")

    top_news = [n.get("title", "")[:60] for n in (news or [])[:5] if n.get("importance") in ("A","B")]

    return f"""【市場データブリーフィング】
日時: {get_jst_now().strftime('%Y-%m-%d %H:%M')} JST

■ リスクスコア: {risk_score:+.2f}（主要シグナル: {risk_signals}）
■ VIX恐怖指数: {vix}
■ Fear&Greed指数: {fg}（{fg_label}）
■ S&P500変化: {sp_chg:+.2f}%
■ 日経225変化: {nk_chg:+.2f}%
■ ドル円: {usdjpy}円
■ 金: {gold}ドル
{f'■ テクニカル: {tech_summary}' if tech_summary else ''}
{f'■ マクロ指標: {fred_summary}' if fred_summary else ''}

■ 重要ニュース:
{''.join(f'  ・{t}' + chr(10) for t in top_news) if top_news else '  なし'}

上記データを踏まえて分析してください。回答は日本語で200字以内に簡潔にまとめてください。"""


def _call_agent(agent: dict, brief: str, model) -> dict:
    """1エージェントを呼び出して結果を返す"""
    prompt = agent["role"] + "\n\n" + brief
    try:
        resp = model.generate_content(prompt)
        text = resp.text.strip()

        # 予測方向を抽出
        direction = "neutral"
        if "予測: 上昇" in text or "上昇" in text[:50]:
            direction = "bull"
        elif "予測: 下落" in text or "下落" in text[:50]:
            direction = "bear"

        # 確信度を抽出 (1-5)
        confidence = 3
        for line in text.split("\n"):
            if "確信度" in line:
                for c in ["5", "4", "3", "2", "1"]:
                    if c in line:
                        confidence = int(c)
                        break

        return {
            "agent_id": agent["id"],
            "name": agent["name"],
            "emoji": agent["emoji"],
            "direction": direction,
            "confidence": confidence,
            "analysis": text[:300],
        }
    except Exception as e:
        logger.warning(f"{agent['name']} エラー: {e}")
        return {
            "agent_id": agent["id"],
            "name": agent["name"],
            "emoji": agent["emoji"],
            "direction": "neutral",
            "confidence": 1,
            "analysis": f"分析エラー: {e}",
        }


def run(prices, risk, fear_greed, news, technical=None, fred_data=None) -> dict:
    """4エージェント合議を実行して最終判断を返す"""
    logger.info("--- マルチエージェント合議 ---")
    result = {"available": False}

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return result

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")

        brief = _build_market_brief(prices, risk, fear_greed, news, technical, fred_data)

        agents_results = []
        for agent in AGENTS:
            ar = _call_agent(agent, brief, model)
            agents_results.append(ar)
            logger.info(f"  {agent['emoji']} {agent['name']}: {ar['direction']} (確信度{ar['confidence']})")

        # 多数決集計
        votes = {"bull": 0, "bear": 0, "neutral": 0}
        total_confidence = 0
        for ar in agents_results:
            votes[ar["direction"]] += ar["confidence"]
            total_confidence += ar["confidence"]

        # 最多票の方向
        final_direction = max(votes, key=votes.get)
        vote_ratio = votes[final_direction] / max(total_confidence, 1)

        # 確信レベル
        if vote_ratio >= 0.85:
            consensus_level = "全員一致"
            consensus_emoji = "🔥"
        elif vote_ratio >= 0.65:
            consensus_level = "強い合意"
            consensus_emoji = "✅"
        elif vote_ratio >= 0.45:
            consensus_level = "弱い合意"
            consensus_emoji = "🟡"
        else:
            consensus_level = "意見分裂"
            consensus_emoji = "⚠️"

        # 全エージェントが同方向なら特別フラグ
        directions_set = set(ar["direction"] for ar in agents_results)
        unanimous = len(directions_set) == 1

        # 確信度（0.5〜1.0）: vote_ratioを0.5〜1.0にマッピング
        # vote_ratio=1.0(全員一致)→1.0, vote_ratio=0.5(拮抗)→0.75
        consensus_confidence = round(0.5 + vote_ratio * 0.5, 3)

        result = {
            "available": True,
            "agents": agents_results,
            "verdict": {
                "direction": final_direction,
                "votes": votes,
                "consensus_level": consensus_level,
                "consensus_emoji": consensus_emoji,
                "unanimous": unanimous,
                "vote_ratio": round(vote_ratio, 2),
                "consensus_confidence": consensus_confidence,
            },
            "brief": brief[:200],
        }

        dir_ja = {"bull": "上昇", "bear": "下落", "neutral": "中立"}[final_direction]
        logger.info(f"✅ 合議結果: {dir_ja} ({consensus_level} / 票比{vote_ratio:.0%})")
        return result

    except Exception as e:
        logger.error(f"マルチエージェント合議エラー: {e}")
        return result


def format_telegram(data: dict) -> str:
    if not data.get("available"):
        return ""
    verdict = data.get("verdict", {})
    agents = data.get("agents", [])
    dir_ja = {"bull": "📈 上昇優勢", "bear": "📉 下落優勢", "neutral": "➡️ 中立"}
    direction_label = dir_ja.get(verdict.get("direction", "neutral"), "---")
    lines = [
        f"🗳️ *マルチエージェント合議*",
        "━━━━━━━━━━━━━━━",
        f"最終判断: {direction_label}",
        f"{verdict.get('consensus_emoji','')} {verdict.get('consensus_level','')}",
        "",
        "各エージェントの意見:",
    ]
    dir_icons = {"bull": "📈", "bear": "📉", "neutral": "➡️"}
    for ag in agents:
        icon = dir_icons.get(ag.get("direction", "neutral"), "")
        lines.append(
            f"  {ag.get('emoji','')} {ag.get('name','')}: "
            f"{icon} 確信{ag.get('confidence','')}点"
        )
    if verdict.get("unanimous"):
        lines += ["", "🔥 *全員一致シグナル！* 高確信の方向感です"]
    return "\n".join(lines)
