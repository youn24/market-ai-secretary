"""
複数AIが議論して分析するモジュール
Geminiに異なる役割を与えて議論させる
"""
import os
import json
import traceback
from pathlib import Path
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
