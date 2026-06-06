"""
Ollama ローカルAI 要約モジュール（カテゴリ別対応版）
Ollamaが起動していれば自動でカテゴリ別にニュース要約・市場コメントを生成
起動していない場合はスキップ（エラーにしない）
"""
import json
import requests
from src.utils import setup_logger, get_jst_now

logger = setup_logger("ai_summary")

OLLAMA_URL    = "http://localhost:11434"
PREFER_MODELS = ["gemma3:4b", "gemma2:2b", "llama3.2:3b", "qwen2.5:3b", "phi3:mini"]


def _is_ollama_running() -> bool:
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def _get_model() -> str | None:
    try:
        r      = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        models = [m["name"] for m in r.json().get("models", [])]
        if not models:
            return None
        for prefer in PREFER_MODELS:
            for m in models:
                if prefer.split(":")[0] in m:
                    return m
        return models[0]
    except Exception:
        return None


def _call(model: str, prompt: str, timeout: int = 90) -> str:
    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=timeout,
        )
        return r.json().get("response", "").strip()
    except Exception as e:
        logger.warning(f"Ollama呼び出し失敗: {e}")
        return ""


def _base_rules() -> str:
    return """【必須ルール】
・投資助言・売買指示は絶対に禁止
・「必ず上がる」「確実に下がる」などの断定は禁止
・事実は「〜です」、推測は「〜の可能性があります」「〜と見られます」と区別
・初心者にもわかりやすい言葉で
・200字以内で簡潔に
"""


def summarize_category(category_name: str, news_items: list[dict],
                        model: str) -> str:
    """カテゴリ別ニュースをAIで要約する"""
    if not news_items:
        return "このカテゴリのニュースはありません。"

    titles = "\n".join(
        f"- {n.get('title','')}" for n in news_items[:6]
    )
    cat_clean = category_name.split(" ", 1)[-1]  # アイコン除去

    prompt = f"""{_base_rules()}

以下は「{cat_clean}」カテゴリの本日のニュース見出しです。
投資初心者向けに3点の箇条書きで要約してください。

ニュース:
{titles}

要約（3点・箇条書き・日本語）:"""

    return _call(model, prompt, timeout=60) or "（要約取得失敗）"


def generate_market_comment(prices: dict, risk: dict,
                             fear_greed: dict, model: str) -> str:
    """市場全体のAIコメントを生成する"""
    sentiment = risk.get("sentiment", "不明")
    score     = risk.get("score", 0)
    fg_score  = fear_greed.get("score", "不明")
    fg_rating = fear_greed.get("rating_ja", "不明")

    def fmt(sym, d=2):
        p = prices.get(sym, {})
        v = p.get("latest")
        c = p.get("change_pct")
        if v is None: return "取得失敗"
        chg = f"({'+' if (c or 0)>=0 else ''}{c:.2f}%)" if c else ""
        return f"{v:,.{d}f}{chg}"

    data = f"""
地合い: {sentiment}（スコア: {score:+.2f}）
Fear & Greed: {fg_score}（{fg_rating}）
日経平均: {fmt('^N225')}
S&P500: {fmt('^GSPC')}
ドル円: {fmt('USDJPY=X', 4)}
米10年金利: {fmt('^TNX', 3)}
VIX: {fmt('^VIX', 2)}
金: {fmt('GC=F')}
原油: {fmt('CL=F')}
Bitcoin: {fmt('BTC-USD')}
"""
    prompt = f"""{_base_rules()}

以下の市場データをもとに「今日の市場の状況」を3〜4文で解説してください。
地合い判定の根拠と、今日注目すべきポイントを含めてください。

市場データ:
{data}

解説（日本語・3〜4文）:"""

    return _call(model, prompt, timeout=90) or "（市場コメント取得失敗）"


def run_ai_summary(prices: dict, news: list[dict],
                   risk: dict, fear_greed: dict = None) -> dict:
    """
    カテゴリ別AI要約を生成する
    Ollamaが利用できない場合はスキップ
    """
    if fear_greed is None:
        fear_greed = {}

    result = {
        "available":       False,
        "model":           "",
        "market_comment":  "",
        "category_summaries": {},
        "fetch_time":      get_jst_now().isoformat(),
    }

    if not _is_ollama_running():
        logger.info("Ollama未起動のためAI要約をスキップ")
        return result

    model = _get_model()
    if not model:
        logger.warning("Ollamaにモデルが見つかりません。`ollama pull gemma3:4b` を実行してください。")
        return result

    logger.info(f"Ollama AI要約開始: モデル={model}")
    result["available"] = True
    result["model"]     = model

    # カテゴリ別仕分け
    try:
        from src.news_categories import CATEGORIES, categorize_news
        categorized = categorize_news(news)

        # 優先度の高いカテゴリから要約（時間制限のため上位6カテゴリ）
        priority_cats = [
            "🏦 日銀・日本政府",
            "🇺🇸 FRB・米国金融政策",
            "📈 米国株市場",
            "🗾 日本株市場",
            "💱 為替・FX",
            "🌍 地政学リスク",
        ]
        for cat in priority_cats:
            items = categorized.get(cat, [])
            if items:
                logger.info(f"AI要約生成中: {cat}（{len(items)}件）")
                result["category_summaries"][cat] = summarize_category(
                    cat, items, model
                )
    except Exception as e:
        logger.error(f"カテゴリ別要約エラー: {e}")

    # 市場全体コメント
    try:
        result["market_comment"] = generate_market_comment(
            prices, risk, fear_greed, model
        )
        logger.info("市場全体コメント生成完了")
    except Exception as e:
        logger.error(f"市場コメント生成エラー: {e}")

    logger.info(f"AI要約完了: {len(result['category_summaries'])}カテゴリ")
    return result
