"""
複数AIが議論して分析するモジュール
マーケット太郎・ニュース花子・リスク次郎が相互に反論・賛成する本格的なディベートシステム
"""
import os
import json
import traceback
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from typing import Dict, List, Tuple
from src.utils import setup_logger, get_jst_now, get_today_str, get_dirs

logger = setup_logger("ai_debate")


def _get_gemini_model():
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    return genai.GenerativeModel("gemini-1.5-flash")


def _load_history() -> dict:
    """過去30日のデータを読み込む"""
    dirs = get_dirs()
    history = {}
    try:
        for f in sorted(dirs["data_raw"].glob("*_prices.json"))[-30:]:
            date = f.stem.replace("_prices", "")
            with open(f, encoding="utf-8") as fp:
                history[date] = json.load(fp)
    except Exception as e:
        logger.error(f"履歴読み込みエラー: {e}")
    return history


def _save_today_prices(prices: dict):
    """本日の価格を保存"""
    try:
        dirs = get_dirs()
        path = dirs["data_raw"] / f"{get_today_str()}_prices.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(prices, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"価格保存エラー: {e}")


def _compare_with_history(prices: dict, history: dict) -> str:
    """過去データと比較してコメントを生成"""
    if not history:
        return "過去データなし"

    comparisons = []
    key_symbols = {
        "^N225": "日経平均",
        "^GSPC": "S&P500",
        "USDJPY=X": "ドル円",
        "^VIX": "VIX",
        "GC=F": "金",
    }

    dates = sorted(history.keys())

    for sym, name in key_symbols.items():
        current = prices.get(sym, {}).get("latest")
        if current is None:
            continue

        values = []
        for d in dates:
            v = history[d].get(sym, {}).get("latest")
            if v:
                values.append((d, v))

        if not values:
            continue

        # 1週間前・1ヶ月前と比較
        if len(values) >= 5:
            week_ago_val = values[-5][1]
            week_chg = (current - week_ago_val) / week_ago_val * 100
            comparisons.append(f"{name}: 1週間前比 {'▲' if week_chg >= 0 else '▼'}{abs(week_chg):.1f}%")

        if len(values) >= 20:
            month_ago_val = values[-20][1]
            month_chg = (current - month_ago_val) / month_ago_val * 100
            comparisons.append(f"{name}: 1ヶ月前比 {'▲' if month_chg >= 0 else '▼'}{abs(month_chg):.1f}%")

        # 最高値・最安値
        all_vals = [v for _, v in values]
        if current >= max(all_vals):
            comparisons.append(f"⭐ {name}: 過去{len(values)}日間の最高値！")
        elif current <= min(all_vals):
            comparisons.append(f"⚠️ {name}: 過去{len(values)}日間の最安値！")

    return "\n".join(comparisons) if comparisons else "比較データ不足"


def run_ai_debate(prices: dict, news: list, risk: dict, fear_greed: dict) -> dict:
    """複数のAI視点で議論して分析"""
    model = _get_gemini_model()
    if not model:
        return {"available": False}

    try:
        # 過去データ保存・比較
        _save_today_prices(prices)
        history = _load_history()
        history_comment = _compare_with_history(prices, history)

        def fmt(sym, unit=""):
            d = prices.get(sym, {})
            v = d.get("latest")
            chg = d.get("change_pct")
            if v is None: return "---"
            s = f"+{chg:.2f}%" if (chg or 0) >= 0 else f"{chg:.2f}%"
            return f"{v:,.2f}{unit}({s})"

        market_data = f"""
日経平均: {fmt('^N225','円')} | S&P500: {fmt('^GSPC')} | NASDAQ: {fmt('^IXIC')}
ダウ: {fmt('^DJI')} | VIX: {fmt('^VIX')} | ドル円: {fmt('USDJPY=X','円')}
米10年金利: {fmt('^TNX','%')} | 金: {fmt('GC=F','$')} | 原油: {fmt('CL=F','$')}
Bitcoin: {fmt('BTC-USD','$')}
地合い: {risk.get('sentiment','---')} (スコア:{risk.get('score',0):+.2f})
Fear&Greed: {fear_greed.get('score','---')} ({fear_greed.get('rating_ja','---')})
"""

        news_text = "\n".join(f"・{n.get('title','')}" for n in
                              sorted(news, key=lambda x: {"A":0,"B":1,"C":2}.get(x.get("importance","C"),2))[:8])

        # ━━━ AI①：強気派アナリスト ━━━
        prompt_bull = f"""あなたは強気派の金融アナリストです。
以下のデータを見て、ポジティブな視点から分析してください（150文字以内）。

{market_data}
【過去比較】{history_comment}
【ニュース】{news_text}

強気の根拠を簡潔に述べてください。"""

        bull_response = model.generate_content(prompt_bull)
        bull_view = bull_response.text[:300]

        # ━━━ AI②：弱気派アナリスト ━━━
        prompt_bear = f"""あなたは慎重派・弱気派の金融アナリストです。
以下のデータを見て、リスクやネガティブな視点から分析してください（150文字以内）。

{market_data}
【過去比較】{history_comment}
【ニュース】{news_text}

弱気・リスクの根拠を簡潔に述べてください。"""

        bear_response = model.generate_content(prompt_bear)
        bear_view = bear_response.text[:300]

        # ━━━ AI③：中立・総合判断 ━━━
        prompt_neutral = f"""あなたは中立的な市場アナリストです。
強気派の意見：{bull_view}
弱気派の意見：{bear_view}

両者の意見を踏まえて、バランスの取れた総合判断を200文字以内で述べてください。
事実と推測を分けて、断定表現は使わないでください。"""

        neutral_response = model.generate_content(prompt_neutral)
        neutral_view = neutral_response.text[:400]

        logger.info("✅ AI議論分析完了（強気・弱気・中立）")

        return {
            "available": True,
            "bull_view": bull_view,
            "bear_view": bear_view,
            "neutral_view": neutral_view,
            "history_comment": history_comment,
            "overall_summary": neutral_view,
        }

    except Exception as e:
        logger.error(f"AI議論エラー: {e}")
        logger.debug(traceback.format_exc())
        return {"available": False, "error": str(e)}


# ============================================================================
# PART 2: 本格的なAIディベートシステム（相互反論・賛成機能付き）
# ============================================================================

class DebateTeamMember:
    """ディベートチームメンバーの基底クラス"""
    
    def __init__(self, name: str, role: str, emoji: str):
        self.name = name
        self.role = role
        self.emoji = emoji
        self.opinion = None
        self.model = _get_gemini_model()
        
    def analyze(self, market_data: str, news_text: str) -> str:
        """独立した分析を実施"""
        raise NotImplementedError
    
    def respond_to(self, other_name: str, other_opinion: str, market_data: str) -> str:
        """他のメンバーの意見に対して反論・賛成する"""
        raise NotImplementedError
    
    def vote(self) -> str:
        """投票（買い/売り/保有）"""
        raise NotImplementedError


class MarketTaro(DebateTeamMember):
    """📊 マーケット太郎（データ担当）"""
    
    def __init__(self):
        super().__init__(
            name="マーケット太郎",
            role="データ担当",
            emoji="📊"
        )
    
    def analyze(self, market_data: str, news_text: str) -> str:
        """市場データから分析"""
        if not self.model:
            return "テクニカル分析中..."
        
        prompt = f"""あなたはマーケット太郎。データ駆動型のテクニカルアナリストです。
以下の市場データを分析し、テクニカルな視点から意見を述べてください（200字以内）。

【市場データ】
{market_data}

【ニュース】
{news_text}

VIX、トレンド、テクニカル指標を重視して分析してください。"""
        
        try:
            response = self.model.generate_content(prompt)
            self.opinion = response.text[:300]
            logger.info(f"✅ {self.emoji} {self.name}: {self.opinion[:50]}...")
            return self.opinion
        except Exception as e:
            logger.error(f"❌ {self.name} 分析エラー: {e}")
            return "分析失敗"
    
    def respond_to(self, other_name: str, other_opinion: str, market_data: str) -> str:
        """他の意見に反論・賛成"""
        if not self.model:
            return "反論検討中..."
        
        prompt = f"""あなたはマーケット太郎。
{other_name}が以下の意見を述べました：
「{other_opinion}」

あなたのテクニカル分析からすると、この意見に対して賛成しますか？反論しますか？
100字以内で簡潔に述べてください。"""
        
        try:
            response = self.model.generate_content(prompt)
            return response.text[:200]
        except:
            return f"データから判断不可"
    
    def vote(self) -> str:
        if not self.opinion:
            return "保有"
        if not self.model:
            if "上昇" in self.opinion or "強気" in self.opinion:
                return "買い"
            elif "下落" in self.opinion or "弱気" in self.opinion:
                return "売り"
            return "保有"
        prompt = f"""あなたはマーケット太郎（テクニカルアナリスト）です。
あなたの分析：{self.opinion[:200]}

この分析に基づき「買い」「売り」「保有」の一語だけ答えてください。"""
        try:
            resp = self.model.generate_content(prompt)
            text = resp.text.strip()
            for opt in ["買い", "売り", "保有"]:
                if opt in text:
                    return opt
            return "保有"
        except Exception:
            return "買い" if "上昇" in self.opinion else "保有"


class NewsHanako(DebateTeamMember):
    """📰 ニュース花子（ニュース担当）"""
    
    def __init__(self):
        super().__init__(
            name="ニュース花子",
            role="ニュース担当",
            emoji="📰"
        )
    
    def analyze(self, market_data: str, news_text: str) -> str:
        """ニュースから分析"""
        if not self.model:
            return "ニュース分析中..."
        
        prompt = f"""あなたはニュース花子。時事通を務めるアナリストです。
最新のニュースから市場への影響を分析してください（200字以内）。

【ニュース】
{news_text}

【市場反応】
{market_data}

ニュースの市場への影響を強調してください。"""
        
        try:
            response = self.model.generate_content(prompt)
            self.opinion = response.text[:300]
            logger.info(f"✅ {self.emoji} {self.name}: {self.opinion[:50]}...")
            return self.opinion
        except Exception as e:
            logger.error(f"❌ {self.name} 分析エラー: {e}")
            return "分析失敗"
    
    def respond_to(self, other_name: str, other_opinion: str, market_data: str) -> str:
        """他の意見に反論・賛成"""
        if not self.model:
            return "反論検討中..."
        
        prompt = f"""あなたはニュース花子。
{other_name}が以下の意見を述べました：
「{other_opinion}」

あなたの視点からは、このニュース解釈に対して賛成しますか？異なる見方がありますか？
100字以内で述べてください。"""
        
        try:
            response = self.model.generate_content(prompt)
            return response.text[:200]
        except:
            return "ニュース評価が異なる可能性あり"
    
    def vote(self) -> str:
        if not self.opinion:
            return "保有"
        if not self.model:
            if "慎重" in self.opinion or "リスク" in self.opinion:
                return "保有"
            elif "売り" in self.opinion or "下落" in self.opinion:
                return "売り"
            return "買い"
        prompt = f"""あなたはニュース花子（ニュースアナリスト）です。
あなたの分析：{self.opinion[:200]}

この分析に基づき「買い」「売り」「保有」の一語だけ答えてください。"""
        try:
            resp = self.model.generate_content(prompt)
            text = resp.text.strip()
            for opt in ["買い", "売り", "保有"]:
                if opt in text:
                    return opt
            return "保有"
        except Exception:
            return "保有" if "慎重" in self.opinion else "買い"


class RiskJiro(DebateTeamMember):
    """⚠️ リスク次郎（リスク担当）"""
    
    def __init__(self):
        super().__init__(
            name="リスク次郎",
            role="リスク担当",
            emoji="⚠️"
        )
    
    def analyze(self, market_data: str, news_text: str) -> str:
        """リスク分析"""
        if not self.model:
            return "リスク評価中..."
        
        prompt = f"""あなたはリスク次郎。リスク管理の専門家です。
市場のリスク要因を分析し、注意点を指摘してください（200字以内）。

【市場データ】
{market_data}

【ニュース】
{news_text}

VIX、相関性、ドローダウンなどからリスク要因を抽出してください。"""
        
        try:
            response = self.model.generate_content(prompt)
            self.opinion = response.text[:300]
            logger.info(f"✅ {self.emoji} {self.name}: {self.opinion[:50]}...")
            return self.opinion
        except Exception as e:
            logger.error(f"❌ {self.name} 分析エラー: {e}")
            return "分析失敗"
    
    def respond_to(self, other_name: str, other_opinion: str, market_data: str) -> str:
        """他の意見に反論・賛成"""
        if not self.model:
            return "反論検討中..."
        
        prompt = f"""あなたはリスク次郎。
{other_name}が以下の意見を述べました：
「{other_opinion}」

この意見には見落とされたリスクがありますか？あなたの評価は？
100字以内で述べてください。"""
        
        try:
            response = self.model.generate_content(prompt)
            return response.text[:200]
        except:
            return "リスクが高い可能性"
    
    def vote(self) -> str:
        if not self.opinion:
            return "保有"
        if not self.model:
            if "危険" in self.opinion or "警戒" in self.opinion or "高い" in self.opinion:
                return "売り"
            elif "低い" in self.opinion or "安定" in self.opinion:
                return "買い"
            return "保有"
        prompt = f"""あなたはリスク次郎（リスク管理専門家）です。
あなたの分析：{self.opinion[:200]}

この分析に基づき「買い」「売り」「保有」の一語だけ答えてください。"""
        try:
            resp = self.model.generate_content(prompt)
            text = resp.text.strip()
            for opt in ["買い", "売り", "保有"]:
                if opt in text:
                    return opt
            return "保有"
        except Exception:
            return "売り" if "危険" in self.opinion else "保有"


def run_team_debate(market_data_str: str, news_text: str) -> Dict:
    """本格的なAIディベートを実行
    
    1. 3名が並列で独立分析
    2. 相互に反論・賛成
    3. 多数決で最終判定
    """
    
    logger.info("="*70)
    logger.info("🤝 完全自律AIディベート開始")
    logger.info("="*70)
    
    # メンバー初期化
    members = [
        MarketTaro(),
        NewsHanako(),
        RiskJiro()
    ]
    
    # ━━━ フェーズ1: 並列分析 ━━━
    logger.info("\n【フェーズ1】3名が並列で独立分析...")
    
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            member: executor.submit(member.analyze, market_data_str, news_text)
            for member in members
        }
        
        for member, future in futures.items():
            member.opinion = future.result()
    
    # ━━━ フェーズ2: 相互反論・賛成（並列実行） ━━━
    logger.info("\n【フェーズ2】相互に反論・賛成（並列）...")

    responses = {m.name: {} for m in members}
    emoji_map = {m.name: m.emoji for m in members}

    def _respond(member, other):
        resp = member.respond_to(other.name, other.opinion, market_data_str)
        return member.name, other.name, resp

    pairs = [(m, o) for m in members for o in members if m.name != o.name]
    with ThreadPoolExecutor(max_workers=len(pairs)) as executor:
        futures = [executor.submit(_respond, m, o) for m, o in pairs]
        for future in as_completed(futures):
            m_name, o_name, resp = future.result()
            responses[m_name][o_name] = resp
            print(f"{emoji_map[m_name]} {m_name} → {emoji_map[o_name]} {o_name}: {resp[:80]}...")

    # ━━━ フェーズ3: 投票・多数決（並列実行） ━━━
    logger.info("\n【フェーズ3】投票・多数決...")

    votes = {}
    with ThreadPoolExecutor(max_workers=len(members)) as executor:
        vote_futures = {executor.submit(m.vote): m for m in members}
        for future, member in vote_futures.items():
            votes[member.name] = future.result()

    for member in members:
        print(f"🗳️ {member.emoji} {member.name}: 「{votes[member.name]}」")

    vote_counter = Counter(votes.values())
    final_decision, vote_count = vote_counter.most_common(1)[0]
    confidence = vote_count / len(members)

    logger.info(f"\n✅ 最終決定: 「{final_decision}」(信頼度: {confidence:.0%})")

    return {
        "available": True,
        "status": "success",
        "members": {
            member.name: {
                "emoji": member.emoji,
                "opinion": member.opinion,
                "vote": votes[member.name]
            }
            for member in members
        },
        "debate_responses": responses,
        "votes": votes,
        "final_decision": final_decision,
        "confidence": confidence,
        "summary": f"3名の投票により「{final_decision}」に決定。{vote_count}/3の合意。"
    }
