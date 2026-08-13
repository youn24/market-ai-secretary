"""
src/us_afterhours.py — 米国主要株の時間外取引ムーバー
yfinance の quote情報（preMarketChangePercent / postMarketChangePercent）から、
米国主要銘柄の時間外（プレ/アフターマーケット）での大きな値動きを取得する。

タイミングの意味:
  朝7:30 JST は米国のアフターアワーズ（16:00〜20:00 ET）の真っ最中。
  引け後の決算発表・ガイダンスへの最初の反応がここに出る。
  「NVIDIAが時間外で急落」→ その日の日本の半導体株に波及、のように
  日本市場ザラ場の先行シグナルになる。
"""

import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.utils import setup_logger

logger = setup_logger("us_afterhours")

# 監視する米国主要銘柄（シンボル, 日本語名, 分類）
WATCHLIST = [
    ("NVDA",  "エヌビディア",     "半導体"),
    ("AAPL",  "アップル",         "ハイテク"),
    ("MSFT",  "マイクロソフト",   "ハイテク"),
    ("GOOGL", "グーグル",         "ハイテク"),
    ("AMZN",  "アマゾン",         "ハイテク"),
    ("META",  "メタ",             "ハイテク"),
    ("TSLA",  "テスラ",           "EV"),
    ("AVGO",  "ブロードコム",     "半導体"),
    ("AMD",   "AMD",              "半導体"),
    ("TSM",   "TSMC",             "半導体"),
    ("MU",    "マイクロン",       "半導体"),
    ("INTC",  "インテル",         "半導体"),
    ("QCOM",  "クアルコム",       "半導体"),
    ("ARM",   "アーム",           "半導体"),
    ("NFLX",  "ネットフリックス", "ハイテク"),
    ("ORCL",  "オラクル",         "ハイテク"),
    ("CRM",   "セールスフォース", "ハイテク"),
    ("LLY",   "イーライリリー",   "医薬"),
    ("JPM",   "JPモルガン",       "金融"),
    ("XOM",   "エクソン",         "エネルギー"),
    ("BA",    "ボーイング",       "資本財"),
    ("COST",  "コストコ",         "小売"),

    # ── AI・データ解析（決算やAI関連ニュースで大きく動く）──
    ("PLTR",  "パランティア",     "AI"),
    ("SNOW",  "スノーフレーク",   "AI"),
    ("CRWD",  "クラウドストライク", "サイバー"),
    ("NOW",   "サービスナウ",     "ハイテク"),

    # ── 半導体・メモリ（日本の半導体株に直結する）──
    # サンディスクは2025年にウエスタンデジタルから分離して再上場（SNDK）
    ("SNDK",  "サンディスク",     "半導体"),
    ("WDC",   "ウエスタンデジタル", "半導体"),
    ("STX",   "シーゲイト",       "半導体"),
    ("LRCX",  "ラムリサーチ",     "半導体装置"),
    ("AMAT",  "アプライドマテリアルズ", "半導体装置"),
    ("KLAC",  "KLA",              "半導体装置"),
    ("ASML",  "ASML",             "半導体装置"),
    ("TXN",   "テキサスインスツルメンツ", "半導体"),
    ("MRVL",  "マーベル",         "半導体"),
    ("SMCI",  "スーパーマイクロ", "AIサーバー"),
    ("DELL",  "デル",             "AIサーバー"),

    # ── 宇宙・防衛（スペースXは非上場のため関連銘柄で代替）──
    # スペースXは未上場で株価が存在しない。動向は出資元のASTSや
    # 競合のRKLB・LUNRなど上場している宇宙関連で間接的に捉える。
    ("RKLB",  "ロケットラボ",     "宇宙"),
    ("ASTS",  "ASTスペースモバイル", "宇宙"),
    ("LUNR",  "インテュイティブマシンズ", "宇宙"),
    ("LMT",   "ロッキードマーチン", "防衛"),
    ("RTX",   "RTX",              "防衛"),

    # ── EV・自動車（日本の自動車株に影響）──
    ("RIVN",  "リビアン",         "EV"),
    ("GM",    "ゼネラルモーターズ", "自動車"),
    ("F",     "フォード",         "自動車"),

    # ── 金融・決済 ──
    ("GS",    "ゴールドマンサックス", "金融"),
    ("BAC",   "バンクオブアメリカ", "金融"),
    ("V",     "ビザ",             "決済"),
    ("COIN",  "コインベース",     "暗号資産"),
    ("MSTR",  "ストラテジー",     "暗号資産"),

    # ── 医薬・生活・その他の主要銘柄 ──
    ("NVO",   "ノボノルディスク", "医薬"),
    ("UNH",   "ユナイテッドヘルス", "医薬"),
    ("WMT",   "ウォルマート",     "小売"),
    ("DIS",   "ディズニー",       "メディア"),
    ("UBER",  "ウーバー",         "サービス"),
    ("CVX",   "シェブロン",       "エネルギー"),
    ("CAT",   "キャタピラー",     "資本財"),
]

# 「大きく動いた」と判定するしきい値（%）
THRESHOLD = 1.0
TOP_N     = 8   # 監視銘柄を50超に拡充したため表示上限も少し広げる


def _fetch_one(sym: str, name: str, sector: str) -> dict | None:
    """1銘柄のquote情報から時間外の変化率を取り出す"""
    try:
        import yfinance as yf
        info = yf.Ticker(sym).info or {}

        state = info.get("marketState", "")
        post  = info.get("postMarketChangePercent")
        pre   = info.get("preMarketChangePercent")

        if post is not None:
            chg, price, session = float(post), info.get("postMarketPrice"), "post"
        elif pre is not None:
            chg, price, session = float(pre), info.get("preMarketPrice"), "pre"
        else:
            return None

        return {
            "symbol": sym, "name": name, "sector": sector,
            "chg_pct": chg, "price": price, "session": session,
            "state": state,
            "regular_chg": info.get("regularMarketChangePercent"),
        }
    except Exception:
        logger.debug(traceback.format_exc())
        return None


def run(*_args, **_kwargs) -> dict:
    """
    米国主要株の時間外ムーバーを取得。
    返り値: {available, session_label, movers: [...], telegram_block}
    """
    result = {"available": False, "movers": [], "session_label": ""}
    try:
        quotes = []
        with ThreadPoolExecutor(max_workers=10) as ex:
            futs = {ex.submit(_fetch_one, s, n, c): s for s, n, c in WATCHLIST}
            for fut in as_completed(futs):
                q = fut.result()
                if q:
                    quotes.append(q)

        if not quotes:
            logger.info("米国時間外: 時間外データなし（通常取引中 or 週末）")
            return result

        # 大きく動いた順（絶対値）
        movers = [q for q in quotes if abs(q["chg_pct"]) >= THRESHOLD]
        movers.sort(key=lambda x: abs(x["chg_pct"]), reverse=True)
        movers = movers[:TOP_N]

        session = quotes[0]["session"]
        result["session_label"] = ("引け後の時間外（アフターアワーズ）" if session == "post"
                                   else "寄り付き前の時間外（プレマーケット）")

        if not movers:
            # 「動きなし」も必ず報告する（チェック済みであることを明示）
            logger.info(f"米国時間外: {THRESHOLD}%以上動いた主要銘柄なし（静かな夜）")
            result["available"] = True
            result["telegram_block"] = (
                f"🇺🇸 *米国時間外（{len(quotes)}銘柄チェック済み）*\n"
                f"±{THRESHOLD:.0f}%超の大きな変動なし — 静かな夜でした"
            )
            return result

        result["movers"] = movers
        result["available"] = True
        result["telegram_block"] = _build_telegram_block(movers, result["session_label"])
        logger.info(f"✅ 米国時間外: {len(movers)}銘柄が大きく変動")
        return result
    except Exception:
        logger.error("米国時間外エラー")
        logger.debug(traceback.format_exc())
        return result


def _build_telegram_block(movers: list, session_label: str) -> str:
    """通知②（詳細メッセージ）用のコンパクトなブロック"""
    lines = [f"🇺🇸 *米国 時間外で大きく動いた銘柄*"]
    for m in movers[:4]:
        e = "⬆️" if m["chg_pct"] >= 0 else "⬇️"
        lines.append(f"{e} {m['name']}({m['symbol']}) {m['chg_pct']:+.1f}%（{m['sector']}）")
    semis = [m for m in movers if m["sector"] == "半導体"]
    if semis:
        worst = min(semis, key=lambda x: x["chg_pct"])
        best  = max(semis, key=lambda x: x["chg_pct"])
        big   = worst if abs(worst["chg_pct"]) >= abs(best["chg_pct"]) else best
        if abs(big["chg_pct"]) >= 2.0:
            direction = "追い風" if big["chg_pct"] > 0 else "逆風"
            lines.append(f"💡 半導体が時間外で動意 → 日本の半導体株に{direction}の可能性")
    return "\n".join(lines)
