"""
AI投資家庭教師モジュール
曜日別テーマで投資の基礎知識を中学生向けにわかりやすく解説
"""
import os
import re
import traceback
from src.utils import get_jst_now, get_today_str, setup_logger

logger = setup_logger("investment_tutor")

# 曜日別テーマ（月=0 〜 金=4）
WEEKDAY_TOPICS = {
    0: ("RSI（相対力指数）", "RSI(Relative Strength Index)は株が買われすぎか売られすぎかを0〜100で表す指標です"),
    1: ("PER（株価収益率）", "PER(Price-to-Earnings Ratio)は株価が1株あたり利益の何倍かを示します"),
    2: ("VIX（恐怖指数）", "VIXは市場参加者が「これからどれだけ株が激しく動くか」を予測した数字です"),
    3: ("ドルコスト平均法", "毎月同じ額を積立投資することで、高値づかみのリスクを減らせる方法です"),
    4: ("Fear & Greedとは", "市場全体が「欲深い（強気）」か「怖がっている（弱気）」かを示すCNNの指標です"),
}

CRASH_TOPIC = "暴落時の心得"
CRASH_EXPLANATION = "株が大きく下がった時ほど、実は買い場であることが多いです。歴史上、全ての暴落は最終的に回復しました"
DEFAULT_TAKEAWAY = "長期投資では焦らないことが最大の武器です"

VIX_CRASH_THRESHOLD = 30


def _get_change_pct(prices: dict, symbol: str) -> float:
    """価格辞書からシンボルの変化率（%）を取得"""
    d = prices.get(symbol, {})
    return d.get("change_pct") or 0.0


def _build_html(topic: str, lesson: str, key_takeaway: str) -> str:
    """青系ダークテーマのカードHTMLを生成"""
    return f"""<div style="background:#0d1117;border:1px solid #1f6feb;border-radius:12px;padding:20px;font-family:'Helvetica Neue',Arial,sans-serif;color:#e6edf3;max-width:680px;margin:16px 0;">
  <div style="font-size:18px;font-weight:bold;color:#58a6ff;margin-bottom:12px;">
    📚 今日の投資レッスン
  </div>
  <div style="border-top:1px solid #1f6feb;margin:8px 0;"></div>
  <div style="font-size:14px;color:#8b949e;margin-bottom:8px;">
    テーマ: <span style="color:#79c0ff;font-weight:bold;">{topic}</span>
  </div>
  <div style="border-top:1px solid #1f6feb;margin:8px 0;"></div>
  <div style="font-size:14px;line-height:1.7;color:#e6edf3;white-space:pre-wrap;">{lesson}</div>
  <div style="border-top:1px solid #1f6feb;margin:12px 0 8px;"></div>
  <div style="font-size:13px;color:#3fb950;font-weight:bold;">
    📌 今日の一言: {key_takeaway}
  </div>
</div>"""


def generate_daily_lesson(prices: dict, risk: dict, fear_greed: dict) -> dict:
    """
    曜日別テーマで投資レッスンを生成する。

    Parameters
    ----------
    prices : dict
        fetch_prices.py が返す価格辞書
    risk : dict
        indicators.py が返すリスク辞書
    fear_greed : dict
        fetch_prices.py が返す Fear & Greed 辞書

    Returns
    -------
    dict
        available, topic, lesson, key_takeaway, html
    """
    now = get_jst_now()
    today_str = get_today_str()
    weekday = now.weekday()  # 0=月, 4=金

    # VIX値を取得
    vix_val = prices.get("^VIX", {}).get("latest") or 0.0

    # テーマ決定: VIX > 30 なら暴落テーマ優先
    if vix_val > VIX_CRASH_THRESHOLD:
        topic = CRASH_TOPIC
        fallback_explanation = CRASH_EXPLANATION
    elif weekday in WEEKDAY_TOPICS:
        topic, fallback_explanation = WEEKDAY_TOPICS[weekday]
    else:
        # 土日は月曜テーマを使用
        topic, fallback_explanation = WEEKDAY_TOPICS[0]

    # 相場データ整形
    nikkei_chg = _get_change_pct(prices, "^N225")
    sp500_chg  = _get_change_pct(prices, "^GSPC")
    fg_score   = fear_greed.get("score", "不明")

    # Gemini API呼び出し
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        logger.info("GEMINI_API_KEY未設定。フォールバックを使用します。")
        html = _build_html(topic, fallback_explanation, DEFAULT_TAKEAWAY)
        return {
            "available": True,
            "topic": topic,
            "lesson": fallback_explanation,
            "key_takeaway": DEFAULT_TAKEAWAY,
            "html": html,
        }

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")

        prompt = f"""今日({today_str})の相場データ:
- 日経225: {nikkei_chg:+.2f}%
- S&P500: {sp500_chg:+.2f}%
- VIX: {vix_val:.2f}
- Fear&Greed: {fg_score}

今日の投資勉強テーマは「{topic}」です。
以下の条件で解説してください:
1. 今日の実際の数字を具体例に使う
2. 中学生でもわかる言葉（専門用語は括弧で説明）
3. 200字以内
4. 最後に「📌 今日の一言：（30字以内）」を必ず入れる"""

        response = model.generate_content(prompt)
        full_text = response.text.strip()

        # 「今日の一言」部分を抽出
        key_takeaway = DEFAULT_TAKEAWAY
        match = re.search(r"📌\s*今日の一言[：:]\s*(.+)", full_text)
        if match:
            key_takeaway = match.group(1).strip()

        # 本文（「📌」より前）
        lesson = re.split(r"📌\s*今日の一言", full_text)[0].strip()
        if not lesson:
            lesson = full_text

        html = _build_html(topic, lesson, key_takeaway)

        logger.info(f"✅ AI投資家庭教師 生成完了: テーマ={topic}")
        return {
            "available": True,
            "topic": topic,
            "lesson": lesson,
            "key_takeaway": key_takeaway,
            "html": html,
        }

    except Exception:
        logger.error("AI投資家庭教師 Geminiエラー")
        logger.debug(traceback.format_exc())
        html = _build_html(topic, fallback_explanation, DEFAULT_TAKEAWAY)
        return {
            "available": True,
            "topic": topic,
            "lesson": fallback_explanation,
            "key_takeaway": DEFAULT_TAKEAWAY,
            "html": html,
        }
