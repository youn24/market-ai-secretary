"""
決算書・財務分析モジュール
yfinance + Gemini で企業の財務を深掘り分析する
"""
import os
import json
import traceback
from pathlib import Path

from src.utils import setup_logger, get_jst_now

logger = setup_logger("financial_analyzer")

WATCHLIST_PATH = Path(__file__).parent.parent / "data" / "watchlist.json"


def _load_watchlist() -> list:
    try:
        with open(WATCHLIST_PATH, encoding="utf-8") as f:
            return json.load(f).get("stocks", [])
    except Exception:
        return []


def _fetch_financials(symbol: str) -> dict:
    """yfinanceで財務データを取得"""
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        info = ticker.info or {}

        # 基本情報
        data = {
            "symbol":   symbol,
            "name":     info.get("longName") or info.get("shortName", symbol),
            "sector":   info.get("sector", ""),
            "industry": info.get("industry", ""),
            "currency": info.get("currency", "JPY"),
        }

        # 株価指標
        data["per"]           = info.get("trailingPE")
        data["pbr"]           = info.get("priceToBook")
        data["roe"]           = info.get("returnOnEquity")
        data["roa"]           = info.get("returnOnAssets")
        data["profit_margin"] = info.get("profitMargins")
        data["op_margin"]     = info.get("operatingMargins")
        data["current_price"] = info.get("currentPrice") or info.get("regularMarketPrice")
        data["52w_high"]      = info.get("fiftyTwoWeekHigh")
        data["52w_low"]       = info.get("fiftyTwoWeekLow")
        data["dividend_yield"]= info.get("dividendYield")
        data["market_cap"]    = info.get("marketCap")

        # 財務数値（直近年度）
        data["revenue"]       = info.get("totalRevenue")
        data["gross_profit"]  = info.get("grossProfits")
        data["ebitda"]        = info.get("ebitda")
        data["net_income"]    = info.get("netIncomeToCommon")
        data["total_debt"]    = info.get("totalDebt")
        data["total_cash"]    = info.get("totalCash")
        data["debt_equity"]   = info.get("debtToEquity")
        data["current_ratio"] = info.get("currentRatio")
        data["fcf"]           = info.get("freeCashflow")

        # 成長率（直近）
        data["revenue_growth"]  = info.get("revenueGrowth")
        data["earnings_growth"] = info.get("earningsGrowth")

        # 四半期売上・利益トレンド（最新4四半期）
        try:
            qf = ticker.quarterly_financials
            if qf is not None and not qf.empty:
                rev_row = qf.loc["Total Revenue"] if "Total Revenue" in qf.index else None
                op_row  = qf.loc["Operating Income"] if "Operating Income" in qf.index else None
                if rev_row is not None:
                    data["quarterly_revenue"] = [
                        {"date": str(c)[:10], "value": int(v) if v == v else None}
                        for c, v in zip(rev_row.index[:4], rev_row.values[:4])
                    ]
                if op_row is not None:
                    data["quarterly_op_income"] = [
                        {"date": str(c)[:10], "value": int(v) if v == v else None}
                        for c, v in zip(op_row.index[:4], op_row.values[:4])
                    ]
        except Exception:
            pass

        return data

    except Exception as e:
        logger.warning(f"yfinance取得失敗 {symbol}: {e}")
        return {"symbol": symbol, "error": str(e)}


def _fmt_num(val, unit="億円", divisor=1e8):
    """数値を億円単位にフォーマット"""
    if val is None or val != val:
        return "N/A"
    try:
        v = val / divisor
        if abs(v) >= 10000:
            return f"{v/10000:.1f}兆円"
        return f"{v:.0f}{unit}"
    except Exception:
        return "N/A"


def _fmt_pct(val):
    if val is None or val != val:
        return "N/A"
    return f"{val*100:.1f}%"


def _build_prompt(d: dict, name: str) -> str:
    """Gemini に渡す分析プロンプトを構築"""
    per  = f"{d['per']:.1f}倍" if d.get("per") else "N/A"
    pbr  = f"{d['pbr']:.2f}倍" if d.get("pbr") else "N/A"
    roe  = _fmt_pct(d.get("roe"))
    roa  = _fmt_pct(d.get("roa"))
    opm  = _fmt_pct(d.get("op_margin"))
    pm   = _fmt_pct(d.get("profit_margin"))
    de   = f"{d['debt_equity']:.1f}%" if d.get("debt_equity") else "N/A"
    cr   = f"{d['current_ratio']:.2f}" if d.get("current_ratio") else "N/A"
    rev  = _fmt_num(d.get("revenue"))
    ni   = _fmt_num(d.get("net_income"))
    mc   = _fmt_num(d.get("market_cap"))
    div  = _fmt_pct(d.get("dividend_yield"))
    rg   = _fmt_pct(d.get("revenue_growth"))
    eg   = _fmt_pct(d.get("earnings_growth"))
    hi52 = f"{d['52w_high']:,.0f}円" if d.get("52w_high") else "N/A"
    lo52 = f"{d['52w_low']:,.0f}円" if d.get("52w_low") else "N/A"
    cp   = f"{d['current_price']:,.0f}円" if d.get("current_price") else "N/A"

    # 四半期トレンド
    qtrd = ""
    if d.get("quarterly_revenue"):
        qr = d["quarterly_revenue"]
        qtrd = "四半期売上トレンド（新→旧）: " + " / ".join(
            f"{q['date']}: {_fmt_num(q['value'])}" for q in qr if q["value"]
        )

    prompt = f"""あなたは個人投資家向けの株式アナリストです。以下の財務データを分析して、投資初心者でも理解できる日本語で回答してください。

【対象企業】{name}（{d.get('symbol','')}）
【業種】{d.get('industry','')} / {d.get('sector','')}

【株価情報】
現在値: {cp}
52週高値: {hi52}  52週安値: {lo52}

【バリュエーション（割安・割高の目安）】
PER（株価収益率）: {per}  ← 15倍以下が割安目安
PBR（株価純資産倍率）: {pbr}  ← 1倍以下は資産より安い
配当利回り: {div}

【収益性（稼ぐ力）】
売上高: {rev}
純利益: {ni}
時価総額: {mc}
営業利益率: {opm}
純利益率: {pm}
ROE（自己資本利益率）: {roe}  ← 10%以上が優秀
ROA（総資産利益率）: {roa}

【成長性】
売上成長率: {rg}
利益成長率: {eg}
{qtrd}

【財務健全性（借金の状況）】
負債資本比率: {de}  ← 100%以下が健全目安
流動比率: {cr}  ← 1.5以上が安心

以下の4項目を日本語で分析してください：

1. **強み（買いたくなるポイント）**
2. **弱み・リスク（注意すべき点）**
3. **今の株価は割安？割高？**（PER・PBRから判断）
4. **AI総合判定**：【強気】【やや強気】【中立】【やや弱気】【弱気】のどれかを明記し、その理由を2〜3文で

各項目は3〜5行程度でわかりやすく説明してください。専門用語は使わず、中学生でもわかる言葉で。"""

    return prompt


def analyze_company(symbol: str, name: str = "") -> dict:
    """1社の財務分析を実行"""
    logger.info(f"財務分析: {name}({symbol})")
    d = _fetch_financials(symbol)
    if "error" in d:
        return {"available": False, "symbol": symbol, "name": name, "error": d["error"]}

    display_name = name or d.get("name", symbol)
    result = {
        "available": False,
        "symbol":    symbol,
        "name":      display_name,
        "raw":       d,
    }

    # Gemini 分析
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if api_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            model  = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
            prompt = _build_prompt(d, display_name)
            # 無料枠を使い切ると429が返り、ライブラリ既定では長時間リトライを続ける。
            # 実際にこれで朝の実行が30分のジョブ上限に達して打ち切られ、
            # 公開レポートの生成（Step 7a2）まで到達しなかった日があった。
            # 1銘柄あたり60秒で見切りをつけ、後続のStepを必ず動かす。
            resp = model.generate_content(
                prompt, request_options={"timeout": 60})
            result["ai_analysis"] = resp.text.strip()
            result["available"]   = True
        except Exception as e:
            logger.warning(f"Gemini分析失敗 {symbol}: {e}")
            result["ai_analysis"] = "AI分析取得失敗"
    else:
        result["available"]   = True
        result["ai_analysis"] = "（GEMINI_API_KEY未設定）"

    # HTML用サマリー数値
    result["per"]   = d.get("per")
    result["pbr"]   = d.get("pbr")
    result["roe"]   = d.get("roe")
    result["op_margin"]   = d.get("op_margin")
    result["revenue"]     = d.get("revenue")
    result["net_income"]  = d.get("net_income")
    result["current_price"] = d.get("current_price")
    result["dividend_yield"] = d.get("dividend_yield")
    result["revenue_growth"]  = d.get("revenue_growth")
    result["earnings_growth"] = d.get("earnings_growth")
    result["debt_equity"]     = d.get("debt_equity")

    # 判定ラベル抽出
    text = result.get("ai_analysis", "")
    for label in ["強気", "やや強気", "中立", "やや弱気", "弱気"]:
        if label in text:
            result["verdict"] = label
            break
    else:
        result["verdict"] = "中立"

    verdict_emoji = {
        "強気": "🟢", "やや強気": "🟩", "中立": "🟡",
        "やや弱気": "🟠", "弱気": "🔴"
    }
    result["verdict_emoji"] = verdict_emoji.get(result["verdict"], "⚪")

    return result


def run_watchlist_analysis(symbols: list = None) -> dict:
    """ウォッチリスト全銘柄を分析（月曜朝の定期実行用）"""
    stocks = _load_watchlist() if symbols is None else [
        {"symbol": s, "name": s} for s in symbols
    ]

    results = []
    for s in stocks:
        try:
            r = analyze_company(s["symbol"], s.get("name", ""))
            results.append(r)
        except Exception:
            logger.error(f"分析失敗: {s.get('symbol','?')}"); logger.debug(traceback.format_exc())

    available_count = sum(1 for r in results if r.get("available"))

    # Telegram メッセージ生成
    tg_lines = [f"📊 財務分析レポート（{get_jst_now().strftime('%m/%d')}）\n"]
    for r in results:
        if not r.get("available"):
            continue
        per_str = f"{r['per']:.1f}倍" if r.get("per") else "N/A"
        pbr_str = f"{r['pbr']:.2f}倍" if r.get("pbr") else "N/A"
        roe_str = f"{(r['roe']*100):.1f}%" if r.get("roe") else "N/A"
        rg_str  = f"{(r['revenue_growth']*100):+.1f}%" if r.get("revenue_growth") else "N/A"
        div_str = f"{(r['dividend_yield']*100):.1f}%" if r.get("dividend_yield") else "N/A"
        tg_lines.append(
            f"{r['verdict_emoji']} {r['name']}\n"
            f"  PER:{per_str} PBR:{pbr_str} ROE:{roe_str}\n"
            f"  売上成長:{rg_str} 配当:{div_str}\n"
            f"  判定:【{r['verdict']}】\n"
        )

    return {
        "available":      available_count > 0,
        "results":        results,
        "count":          available_count,
        "telegram_message": "\n".join(tg_lines),
    }


def run(prices=None, risk=None, fear_greed=None) -> dict:
    """cloud_run.py 標準インターフェース（月曜のみ実行想定）"""
    return run_watchlist_analysis()


def _company_html(r: dict) -> str:
    """1社分のHTMLカードを生成"""
    if not r.get("available"):
        return f'<div class="econ-row"><div class="econ-icon">❓</div><div><div class="econ-lbl">{r.get("name","?")}</div><div style="color:#8899aa;font-size:0.8em;">データ取得失敗</div></div></div>'

    per = f"{r['per']:.1f}倍" if r.get("per") else "N/A"
    pbr = f"{r['pbr']:.2f}倍" if r.get("pbr") else "N/A"
    roe = f"{r['roe']*100:.1f}%" if r.get("roe") else "N/A"
    opm = f"{r['op_margin']*100:.1f}%" if r.get("op_margin") else "N/A"
    rg  = f"{r['revenue_growth']*100:+.1f}%" if r.get("revenue_growth") else "N/A"
    div = f"{r['dividend_yield']*100:.1f}%" if r.get("dividend_yield") else "N/A"
    ve  = r.get("verdict_emoji", "⚪")
    vl  = r.get("verdict", "---")
    vc  = {"強気": "#3fb950", "やや強気": "#69f0ae", "中立": "#ffd740",
           "やや弱気": "#ff9800", "弱気": "#f44336"}.get(vl, "#8899aa")
    ai  = r.get("ai_analysis", "").replace("\n", "<br>")

    return f'''
<div style="background:#0f1623;border:1px solid #1e2d42;border-radius:14px;padding:16px;margin-bottom:14px;">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;">
    <div style="font-weight:800;font-size:1em;">{r.get("name","")}<span style="color:#7a8fa8;font-size:0.75em;margin-left:6px;">{r.get("symbol","")}</span></div>
    <div style="background:{vc}22;border:1px solid {vc}55;border-radius:20px;padding:3px 12px;color:{vc};font-size:0.8em;font-weight:700;">{ve} {vl}</div>
  </div>
  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-bottom:12px;">
    <div style="background:#141d2b;border-radius:8px;padding:8px;text-align:center;">
      <div style="color:#7a8fa8;font-size:0.65em;">PER</div>
      <div style="font-weight:700;font-size:0.9em;">{per}</div>
    </div>
    <div style="background:#141d2b;border-radius:8px;padding:8px;text-align:center;">
      <div style="color:#7a8fa8;font-size:0.65em;">PBR</div>
      <div style="font-weight:700;font-size:0.9em;">{pbr}</div>
    </div>
    <div style="background:#141d2b;border-radius:8px;padding:8px;text-align:center;">
      <div style="color:#7a8fa8;font-size:0.65em;">ROE</div>
      <div style="font-weight:700;font-size:0.9em;">{roe}</div>
    </div>
    <div style="background:#141d2b;border-radius:8px;padding:8px;text-align:center;">
      <div style="color:#7a8fa8;font-size:0.65em;">営業利益率</div>
      <div style="font-weight:700;font-size:0.9em;">{opm}</div>
    </div>
    <div style="background:#141d2b;border-radius:8px;padding:8px;text-align:center;">
      <div style="color:#7a8fa8;font-size:0.65em;">売上成長率</div>
      <div style="font-weight:700;font-size:0.9em;color:{"#3fb950" if r.get("revenue_growth",0) and r["revenue_growth"]>0 else "#f44336"};">{rg}</div>
    </div>
    <div style="background:#141d2b;border-radius:8px;padding:8px;text-align:center;">
      <div style="color:#7a8fa8;font-size:0.65em;">配当利回り</div>
      <div style="font-weight:700;font-size:0.9em;">{div}</div>
    </div>
  </div>
  <details>
    <summary style="color:#00d4ff;font-size:0.8em;cursor:pointer;font-weight:700;">🤖 AI詳細分析を見る</summary>
    <div style="margin-top:10px;font-size:0.85em;line-height:1.75;color:#dde8ff;border-top:1px solid #1e2d42;padding-top:10px;">{ai}</div>
  </details>
</div>'''


def get_html(analysis_result: dict) -> str:
    """HTMLレポート用のセクション全体を生成"""
    if not analysis_result.get("available"):
        return ""
    cards = "".join(_company_html(r) for r in analysis_result.get("results", []))
    return cards
