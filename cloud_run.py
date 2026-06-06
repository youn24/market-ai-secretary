"""
クラウド実行スクリプト（GitHub Actions用）
Ollama・matplotlib不要の軽量版
PC電源OFFでもGitHub上で毎日自動実行される
"""
import argparse
import sys
import traceback
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))
from src.utils import ensure_dirs, setup_logger, get_jst_now, get_dirs, get_today_str

logger = setup_logger("cloud_run")


def run(mode: str):
    ensure_dirs()
    logger.info(f"====== クラウド実行開始 [mode={mode}] ======")
    logger.info(f"実行時刻(JST): {get_jst_now().strftime('%Y-%m-%d %H:%M:%S')}")

    prices     = {}
    fear_greed = {"score": None, "rating_ja": "取得失敗"}
    news       = []
    risk       = {"score":0,"sentiment":"不明","meter":"NEUTRAL","signals":[]}
    analysis   = {}

    # Step 1: 価格取得
    try:
        logger.info("--- Step 1: 価格データ取得 ---")
        from src.fetch_prices import run as fp
        prices, fear_greed = fp()
    except Exception:
        logger.error("価格取得エラー"); logger.debug(traceback.format_exc())

    # Step 2: ニュース取得
    try:
        logger.info("--- Step 2: ニュース取得 ---")
        from src.fetch_news import run as fn
        news = fn()
    except Exception:
        logger.error("ニュース取得エラー"); logger.debug(traceback.format_exc())

    # Step 3: 追加ニュース
    try:
        logger.info("--- Step 3: 追加ニュース取得 ---")
        from src.fetch_extra_news import run as fen
        extra_news, _ = fen()
        news = news + extra_news
    except Exception:
        logger.error("追加ニュース取得エラー"); logger.debug(traceback.format_exc())

    # Step 4: 指標計算
    try:
        logger.info("--- Step 4: 指標計算 ---")
        from src.indicators import calc_risk_score
        risk = calc_risk_score(prices)
    except Exception:
        logger.error("指標計算エラー"); logger.debug(traceback.format_exc())

    # Step 5: 分析
    try:
        logger.info("--- Step 5: 分析 ---")
        from src.analyze import build_analysis
        analysis = build_analysis(prices, risk)
    except Exception:
        logger.error("分析エラー"); logger.debug(traceback.format_exc())

    # Step 6: iPhone通知（ntfy.sh）
    try:
        logger.info("--- Step 6: iPhone通知 ---")
        from src.notify_iphone import run as notify_iphone
        ai_summary = {"available": False}
        result = notify_iphone(risk, fear_greed, prices, ai_summary, mode)
        if result:
            logger.info("✅ iPhone通知送信成功")
    except Exception:
        logger.error("iPhone通知エラー"); logger.debug(traceback.format_exc())

    # Step 7: Telegram通知
    try:
        logger.info("--- Step 7: Telegram通知 ---")
        from src.notify_telegram import run as notify_tg
        report_paths = {"md": f"reports/{get_today_str()}_{mode}.md"}
        notify_tg(risk, analysis, report_paths, mode)
    except Exception:
        logger.error("Telegram通知エラー"); logger.debug(traceback.format_exc())

    # Step 8: 簡易レポート保存（チャートなし版）
    try:
        logger.info("--- Step 8: レポート保存 ---")
        _save_cloud_report(mode, prices, news, risk, analysis, fear_greed)
    except Exception:
        logger.error("レポート保存エラー"); logger.debug(traceback.format_exc())

    logger.info(f"====== クラウド実行完了 ======")
    print(f"\n✅ 完了 | 地合い: {risk.get('sentiment')} | "
          f"F&G: {fear_greed.get('score')} ({fear_greed.get('rating_ja')}) | "
          f"ニュース: {len(news)}件")


def _save_cloud_report(mode, prices, news, risk, analysis, fear_greed):
    """チャートなしの軽量Markdownレポートを保存"""
    today = get_today_str()
    dirs  = get_dirs()
    now   = get_jst_now().strftime("%Y-%m-%d %H:%M JST")

    sentiment = risk.get("sentiment","不明")
    score     = risk.get("score",0)
    fg_score  = fear_greed.get("score","N/A")
    fg_rating = fear_greed.get("rating_ja","N/A")

    def p(sym, unit=""):
        d   = prices.get(sym,{})
        v   = d.get("latest")
        chg = d.get("change_pct")
        if v is None: return "取得失敗"
        s = f"+{chg:.2f}%" if (chg or 0)>=0 else f"{chg:.2f}%"
        return f"{v:,.2f}{unit} ({s})" if chg else f"{v:,.2f}{unit}"

    lines = [
        f"# 市場レポート {today} [{mode.upper()}]",
        f"生成: {now} | ⚠️投資助言ではありません\n",
        f"## 地合い: {sentiment} (スコア: {score:+.2f})",
        f"## Fear & Greed: {fg_score} ({fg_rating})\n",
        "## 主要指数",
        f"- 日経平均: {p('^N225','円')}",
        f"- S&P500: {p('^GSPC')}",
        f"- NASDAQ: {p('^IXIC')}",
        f"- ダウ: {p('^DJI')}",
        f"- VIX: {p('^VIX')}",
        "",
        "## 為替・金利",
        f"- ドル円: {p('USDJPY=X','円')}",
        f"- ユーロドル: {p('EURUSD=X')}",
        f"- 米10年金利: {p('^TNX','%')}",
        "",
        "## コモディティ",
        f"- 金: {p('GC=F','$')}",
        f"- 原油: {p('CL=F','$')}",
        f"- Bitcoin: {p('BTC-USD','$')}",
        "",
        "## 注目ニュース（上位10件）",
    ]

    sorted_news = sorted(news,
        key=lambda x: {"A":0,"B":1,"C":2}.get(x.get("importance","C"),2))
    for item in sorted_news[:10]:
        lines.append(f"- [{item.get('importance','?')}] {item.get('title','')} ({item.get('source_name') or item.get('source','')})")

    lines.append(f"\n⚠️ 本レポートはGitHub Actionsで自動生成されました。投資助言ではありません。")

    md_path = dirs["reports"] / f"{today}_{mode}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    logger.info(f"クラウドレポート保存: {md_path}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["morning","noon","evening","test"], default="morning")
    run(p.parse_args().mode)


if __name__ == "__main__":
    main()
