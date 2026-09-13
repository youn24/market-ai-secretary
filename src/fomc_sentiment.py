"""
FOMC議事録・Fed声明文 NLP感情分析
連邦準備制度のウェブサイトから最新声明を取得し、
「タカ派（利上げ志向）」か「ハト派（利下げ志向）」かをGeminiで分析する。

FOMCは年8回（約6週間ごと）開催。声明文は会議直後に公開される。
この分析で「次の会合で何が起きるか」の事前把握が可能になる。
"""
import ssl
import urllib.request
import re
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE

FED_STATEMENTS_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
FED_BASE_URL = "https://www.federalreserve.gov"

# タカ派ワード（利上げ・引き締め志向）
HAWKISH_WORDS = [
    "inflation", "price stability", "restrictive", "firm", "tighter",
    "raise", "increase", "elevated", "persistent", "remain high",
    "overheated", "reduce balance sheet", "runoff",
]

# ハト派ワード（利下げ・緩和志向）
DOVISH_WORDS = [
    "cut", "reduce", "lower", "easing", "accommodate", "support",
    "maximum employment", "softening", "slowdown", "below target",
    "uncertainty", "risks", "downside",
]


def _get(url: str, timeout: int = 15) -> str | None:
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    })
    try:
        resp = urllib.request.urlopen(req, context=_ctx, timeout=timeout)
        return resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        logger.warning(f"取得失敗: {url[:60]}... {e}")
        return None


def fetch_latest_statement() -> dict:
    """Fed公式サイトから最新のFOMC声明文URLを取得"""
    html = _get(FED_STATEMENTS_URL)
    if not html:
        return {}

    # 最新の声明文リンクを探す
    pattern = r'href="(/monetarypolicy/files/monetary\d+a\.htm)"'
    matches = re.findall(pattern, html)
    if not matches:
        # 別パターンを試す
        pattern2 = r'href="(/newsevents/pressreleases/monetary\d+a\.htm)"'
        matches = re.findall(pattern2, html)

    if not matches:
        logger.warning("FOMC声明文URLが見つからない")
        return {}

    latest_url = FED_BASE_URL + matches[0]
    logger.info(f"  最新FOMC声明: {latest_url}")

    stmt_html = _get(latest_url)
    if not stmt_html:
        return {}

    # HTMLタグを除去してテキスト抽出
    text = re.sub(r'<[^>]+>', ' ', stmt_html)
    text = re.sub(r'\s+', ' ', text).strip()

    # 本文部分を抽出（Releaseから始まる部分）
    start = text.find("For release")
    if start > 0:
        text = text[start:start + 3000]

    return {
        "url": latest_url,
        "text": text[:2000],
        "fetched_at": datetime.now().strftime("%Y-%m-%d"),
    }


def score_sentiment(text: str) -> dict:
    """タカ派/ハト派スコアをキーワードカウントで計算"""
    text_lower = text.lower()
    hawk_count = sum(1 for w in HAWKISH_WORDS if w in text_lower)
    dove_count = sum(1 for w in DOVISH_WORDS if w in text_lower)
    total = hawk_count + dove_count

    if total == 0:
        return {"score": 0, "label": "中立", "hawk": 0, "dove": 0}

    net = hawk_count - dove_count
    if net >= 3:
        label = "タカ派（強い利上げ志向）"
        score = min(net * 15, 100)
    elif net >= 1:
        label = "やや タカ派"
        score = min(net * 10, 50)
    elif net <= -3:
        label = "ハト派（強い利下げ志向）"
        score = max(net * 15, -100)
    elif net <= -1:
        label = "やや ハト派"
        score = max(net * 10, -50)
    else:
        label = "中立"
        score = 0

    return {
        "score": score,
        "label": label,
        "hawk_count": hawk_count,
        "dove_count": dove_count,
        "net": net,
    }


def gemini_analyze(text: str) -> str:
    """GeminiでFOMC声明文を分析"""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or not text:
        return ""
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
        prompt = f"""以下はFOMC（米連邦公開市場委員会）の最新声明文の抜粋です：

{text[:1500]}

以下の点を100文字以内で日本語で分析してください：
1. タカ派（利上げ方向）かハト派（利下げ方向）か
2. 次回会合での金利方向の見通し
3. 日本株・円相場への影響の示唆"""

        resp = model.generate_content(prompt)
        return resp.text[:300]
    except Exception as e:
        logger.warning(f"Gemini分析失敗: {e}")
        return ""


def run() -> dict:
    """FOMC分析を実行"""
    logger.info("--- FOMC議事録 NLP分析 ---")
    result = {"available": False}

    try:
        stmt = fetch_latest_statement()
        if not stmt or not stmt.get("text"):
            logger.warning("FOMC声明文取得失敗")
            return result

        keyword_score = score_sentiment(stmt["text"])
        logger.info(
            f"  キーワード分析: {keyword_score['label']} "
            f"(タカ:{keyword_score['hawk_count']} ハト:{keyword_score['dove_count']})"
        )

        ai_analysis = gemini_analyze(stmt["text"])

        result = {
            "available": True,
            "sentiment": keyword_score,
            "ai_analysis": ai_analysis,
            "statement_url": stmt.get("url", ""),
            "fetched_at": stmt.get("fetched_at", ""),
        }

        # 日本語説明
        label = keyword_score["label"]
        if "タカ" in label:
            japan_impact = "円安・日本株の重荷になりやすい（米金利上昇が円安圧力）"
        elif "ハト" in label:
            japan_impact = "円高・日本株の追い風になりやすい（米金利低下で円高）"
        else:
            japan_impact = "方向感が出るまで様子見"
        result["japan_impact"] = japan_impact

        logger.info(f"✅ FOMC分析完了: {label}")

    except Exception as e:
        logger.error(f"FOMC分析エラー: {e}")
        import traceback
        logger.debug(traceback.format_exc())

    return result
