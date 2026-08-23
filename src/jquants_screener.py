"""
J-Quants 日本個別株スクリーナー（L5j）
JPX公式の無料APIで日経225銘柄のROE・PBR・増益率等を取得し、
「今日注目の日本株3選」をGeminiが生成する。

セットアップ（無料）:
1. https://application.jpx.co.jp/jquants/ でアカウント登録
2. GitHub Secrets に JQUANTS_EMAIL と JQUANTS_PASSWORD を設定

APIキーなしの場合: Yahoo Financeの日本株データで代替スクリーニング
"""
import ssl
import json
import logging
import os
import urllib.request
from datetime import datetime
from src.utils import get_jst_now

logger = logging.getLogger(__name__)

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE

JQUANTS_BASE = "https://api.jquants.com/v1"

# 日本株スクリーニング対象（Nikkei225主要銘柄）
NIKKEI_PICKS = [
    ("7203", "トヨタ自動車"),
    ("6758", "ソニーグループ"),
    ("9984", "ソフトバンクグループ"),
    ("6861", "キーエンス"),
    ("8306", "三菱UFJ"),
    ("9433", "KDDI"),
    ("6954", "ファナック"),
    ("4063", "信越化学"),
    ("8035", "東京エレクトロン"),
    ("6501", "日立製作所"),
    ("7267", "本田技研工業"),
    ("9432", "日本電信電話"),
    ("4502", "武田薬品工業"),
    ("6902", "デンソー"),
    ("3382", "セブン&アイ"),
]


def _get(url: str, headers: dict = None, timeout: int = 15) -> bytes | None:
    h = {"User-Agent": "Mozilla/5.0"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    try:
        resp = urllib.request.urlopen(req, context=_ctx, timeout=timeout)
        return resp.read()
    except Exception as e:
        logger.debug(f"  取得失敗: {url[:50]}... → {e}")
        return None


def _jquants_auth() -> str | None:
    """J-Quants 認証トークン取得"""
    email = os.getenv("JQUANTS_EMAIL", "").strip()
    password = os.getenv("JQUANTS_PASSWORD", "").strip()
    if not email or not password:
        return None

    # Step 1: refresh token
    import urllib.parse
    payload = json.dumps({"mailaddress": email, "password": password}).encode()
    req = urllib.request.Request(
        f"{JQUANTS_BASE}/token/auth_user",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        resp = urllib.request.urlopen(req, context=_ctx, timeout=15)
        refresh_token = json.loads(resp.read()).get("refreshToken")
        if not refresh_token:
            return None
        logger.info("  J-Quants リフレッシュトークン取得")
    except Exception as e:
        logger.warning(f"  J-Quants 認証失敗: {e}")
        return None

    # Step 2: ID token
    url = f"{JQUANTS_BASE}/token/auth_refresh?refreshtoken={refresh_token}"
    raw = _get(url)
    if not raw:
        return None
    id_token = json.loads(raw).get("idToken")
    if id_token:
        logger.info("  J-Quants IDトークン取得")
    return id_token


def _fetch_jquants_prices(code: str, token: str) -> dict:
    """J-Quants から株価情報を取得"""
    today = get_jst_now().strftime("%Y-%m-%d")
    url = f"{JQUANTS_BASE}/prices/daily_quotes?code={code}&date={today}"
    raw = _get(url, headers={"Authorization": f"Bearer {token}"})
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        quotes = data.get("daily_quotes", [])
        if not quotes:
            return {}
        q = quotes[0]
        return {
            "code": q.get("Code", code),
            "close": q.get("Close"),
            "volume": q.get("Volume"),
            "turnover": q.get("TurnoverValue"),
        }
    except Exception:
        return {}


def _fetch_yahoo_jp(code: str, name: str) -> dict:
    """Yahoo Financeから日本株を取得（J-Quantsが使えない場合のフォールバック）"""
    symbol = f"{code}.T"  # 東証コード
    url = (
        f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?interval=1d&range=5d"
    )
    raw = _get(url)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        result = data.get("chart", {}).get("result", [{}])[0]
        meta = result.get("meta", {})
        closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])

        # ⚠️ meta の previousClose はチャートAPIでは基本 None が返る。
        # 既定値0で受けると変化率が常に0になり、実際そうなっていた。
        # 前日終値の判定は src/quote_util.py に一本化してある。
        current = meta.get("regularMarketPrice", 0)
        prev = 0
        try:
            from src.quote_util import previous_close
            ts = result.get("timestamp") or []
            pairs = [(t, c) for t, c in zip(ts, closes) if c]
            prev = previous_close(pairs, meta) or 0
        except Exception:
            pass
        chg_pct = ((current - prev) / prev * 100) if prev else 0

        return {
            "code": code,
            "name": name,
            "close": round(current, 0),
            "change_pct": round(chg_pct, 2),
            "52w_high": round(meta.get("fiftyTwoWeekHigh", 0), 0),
            "52w_low": round(meta.get("fiftyTwoWeekLow", 0), 0),
        }
    except Exception:
        return {}


def _screen_stocks(stocks: list) -> list:
    """スクリーニング: 当日の上昇率・出来高でランキング"""
    valid = [s for s in stocks if s.get("close") and s.get("change_pct") is not None]
    # 当日上昇率上位
    rising = sorted(valid, key=lambda x: x.get("change_pct", 0), reverse=True)
    # ATH近辺（52週高値の95%以上）
    near_ath = [
        s for s in valid
        if s.get("52w_high") and s.get("close", 0) >= s.get("52w_high", 0) * 0.95
    ]
    # 急落後回復（52週安値の110%以内でかつ当日プラス）
    recovery = [
        s for s in valid
        if s.get("52w_low") and s.get("close", 0) <= s.get("52w_low", 0) * 1.1
        and s.get("change_pct", 0) > 0
    ]
    return {
        "rising_top3": rising[:3],
        "near_ath": near_ath[:3],
        "recovery": recovery[:3],
    }


def _generate_picks(screened: dict, model) -> str:
    """Geminiで「今日注目の日本株3選」を生成"""
    rising_desc = ""
    for s in screened.get("rising_top3", []):
        rising_desc += f"  {s.get('name','')} ({s.get('code','')}): {s.get('change_pct',0):+.1f}%\n"

    prompt = f"""日本株のデイトレーダー・長期投資家向けに「今日注目の銘柄」を紹介してください。

【本日上昇率上位の日本株】
{rising_desc if rising_desc else '  データ取得中'}

以下の形式で3銘柄を紹介してください（各銘柄2行以内・日本語・初心者向け）：

1. （銘柄名）: 注目理由を一言で
2. （銘柄名）: 注目理由を一言で
3. （銘柄名）: 注目理由を一言で

注意: 個別銘柄の推薦ではなく、今日の市場で話題になりそうな観点から紹介してください。"""

    try:
        resp = model.generate_content(prompt)
        return resp.text.strip()
    except Exception as e:
        logger.warning(f"  Gemini呼び出し失敗: {e}")
        return ""


def run() -> dict:
    """J-Quantsスクリーナーを実行"""
    logger.info("--- J-Quants 日本株スクリーナー ---")
    result = {"available": False}

    api_key = os.getenv("GEMINI_API_KEY", "").strip()

    # J-Quants認証を試みる
    jq_token = _jquants_auth()
    use_jquants = jq_token is not None

    logger.info(f"  データソース: {'J-Quants API' if use_jquants else 'Yahoo Finance（フォールバック）'}")

    # 株価データ取得
    stocks = []
    for code, name in NIKKEI_PICKS:
        if use_jquants:
            s = _fetch_jquants_prices(code, jq_token)
            s["name"] = name
            s["code"] = code
        else:
            s = _fetch_yahoo_jp(code, name)

        if s.get("close"):
            stocks.append(s)

    logger.info(f"  取得: {len(stocks)}/{len(NIKKEI_PICKS)}銘柄")

    if len(stocks) < 3:
        logger.warning("  データ不足")
        return result

    # スクリーニング
    screened = _screen_stocks(stocks)

    # Geminiで注目銘柄コメント生成
    ai_picks = ""
    if api_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
            ai_picks = _generate_picks(screened, model)
        except Exception as e:
            logger.warning(f"  Gemini呼び出し失敗: {e}")

    result = {
        "available": True,
        "data_source": "J-Quants" if use_jquants else "Yahoo Finance",
        "total_stocks": len(stocks),
        "screened": screened,
        "ai_picks": ai_picks,
        "all_stocks": sorted(stocks, key=lambda x: x.get("change_pct", 0), reverse=True)[:10],
    }

    logger.info(f"✅ 日本株スクリーナー: {len(stocks)}銘柄分析完了")
    return result


def format_telegram(data: dict) -> str:
    if not data.get("available"):
        return ""
    all_stocks = data.get("all_stocks", [])
    ai_picks = data.get("ai_picks", "")
    source = data.get("data_source", "")

    lines = [
        "🗾 *日本株スクリーナー（J-Quants）*",
        "━━━━━━━━━━━━━━━",
        f"📊 {source}より {data.get('total_stocks',0)}銘柄分析",
        "",
        "📈 本日の上昇率上位:",
    ]
    for s in all_stocks[:5]:
        chg = s.get("change_pct", 0)
        arrow = "▲" if chg >= 0 else "▼"
        lines.append(
            f"  {arrow} {s.get('name','')}({s.get('code','')}) "
            f"{chg:+.1f}% ¥{s.get('close',0):,.0f}"
        )
    if ai_picks:
        lines += ["", "🤖 AI注目銘柄コメント:", ai_picks[:200]]
    return "\n".join(lines)
