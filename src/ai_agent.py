"""
Level 3: 自律AIエージェント
GeminiのFunction Callingを使い、AIが自分でツールを選んで多段分析する
"""
import os
import json
import traceback
from src.utils import setup_logger, get_jst_now

logger = setup_logger("ai_agent")

# ──────────────────────────────────────────────
# エージェントが使えるツール定義
# ──────────────────────────────────────────────
TOOLS = [
    {
        "name": "get_market_prices",
        "description": "株価指数・為替・コモディティの現在価格と前日比を取得する",
        "parameters": {
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "取得するティッカーシンボルのリスト例: ['^N225','^GSPC','USDJPY=X']"
                }
            },
            "required": []
        }
    },
    {
        "name": "get_news_summary",
        "description": "指定キーワードに関する最新ニュースを取得する",
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "検索キーワード例: '日銀', 'FRB', '米国株', '為替'"
                },
                "max_items": {
                    "type": "integer",
                    "description": "取得件数（デフォルト5）"
                }
            },
            "required": ["keyword"]
        }
    },
    {
        "name": "get_technical_signals",
        "description": "指定シンボルのRSI・MACD・ボリンジャーバンドなどテクニカル指標を取得する",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "ティッカーシンボル例: '^N225', '^GSPC', 'BTC-USD'"
                }
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "get_fear_greed",
        "description": "Fear & Greed Index（恐怖と強欲指数）を取得する",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_history_comparison",
        "description": "指定シンボルの過去30日・90日との比較データを取得する",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "ティッカーシンボル"
                },
                "days": {
                    "type": "integer",
                    "description": "比較する日数（30または90）"
                }
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "get_scenario_data",
        "description": "楽観・基本・悲観シナリオの分析データを取得する",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
]


# ──────────────────────────────────────────────
# ツール実行関数
# ──────────────────────────────────────────────

def _exec_get_market_prices(args: dict, prices: dict) -> str:
    symbols = args.get("symbols", list(prices.keys())[:8])
    result = []
    for sym in symbols:
        d = prices.get(sym, {})
        v = d.get("latest")
        chg = d.get("change_pct")
        if v:
            arrow = "▲" if (chg or 0) >= 0 else "▼"
            result.append(f"{sym}: {v:,.2f} {arrow}{abs(chg or 0):.2f}%")
        else:
            result.append(f"{sym}: データなし")
    return "\n".join(result)


def _exec_get_news_summary(args: dict, news: list) -> str:
    kw = args.get("keyword", "")
    mx = args.get("max_items", 5)
    filtered = [n for n in news if kw.lower() in n.get("title","").lower()]
    if not filtered:
        filtered = news
    filtered = sorted(filtered, key=lambda x: {"A":0,"B":1,"C":2}.get(x.get("importance","C"),2))
    lines = [f"・{n.get('title','')} [{n.get('source_name','')}]" for n in filtered[:mx]]
    return f"【{kw}関連ニュース】\n" + "\n".join(lines) if lines else f"'{kw}'に関するニュースなし"


def _exec_get_technical_signals(args: dict) -> str:
    """yfinanceでテクニカル指標を計算"""
    sym = args.get("symbol", "^N225")
    try:
        import yfinance as yf
        import numpy as np
        ticker = yf.Ticker(sym)
        hist = ticker.history(period="60d")
        if hist.empty or len(hist) < 14:
            return f"{sym}: データ不足"

        close = hist["Close"].values

        # RSI (14日)
        delta = np.diff(close)
        gain  = np.where(delta > 0, delta, 0)
        loss  = np.where(delta < 0, -delta, 0)
        avg_gain = np.mean(gain[-14:])
        avg_loss = np.mean(loss[-14:])
        rsi = 100 - (100 / (1 + avg_gain / avg_loss)) if avg_loss > 0 else 100

        # MACD (12,26,9)
        ema12 = _ema(close, 12)
        ema26 = _ema(close, 26)
        macd_line = ema12[-1] - ema26[-1]

        # ボリンジャーバンド (20日)
        ma20  = np.mean(close[-20:])
        std20 = np.std(close[-20:])
        upper = ma20 + 2 * std20
        lower = ma20 - 2 * std20
        cur   = close[-1]

        # シグナル判定
        rsi_sig  = "過買い⚠️" if rsi > 70 else "過売り💡" if rsi < 30 else "中立"
        macd_sig = "強気📈" if macd_line > 0 else "弱気📉"
        bb_pos   = (cur - lower) / (upper - lower) * 100 if upper != lower else 50
        bb_sig   = "上限付近⚠️" if bb_pos > 80 else "下限付近💡" if bb_pos < 20 else "中央付近"

        return (
            f"【{sym} テクニカル指標】\n"
            f"RSI(14): {rsi:.1f} → {rsi_sig}\n"
            f"MACD:    {macd_line:+.2f} → {macd_sig}\n"
            f"BB位置:  {bb_pos:.0f}% → {bb_sig}\n"
            f"MA20:    {ma20:,.2f} / 現値: {cur:,.2f}"
        )
    except Exception as e:
        return f"{sym}: テクニカル計算エラー ({e})"


def _ema(values, period):
    """指数移動平均"""
    import numpy as np
    k = 2 / (period + 1)
    ema = [values[0]]
    for v in values[1:]:
        ema.append(v * k + ema[-1] * (1 - k))
    return ema


def _exec_get_fear_greed(fear_greed: dict) -> str:
    score  = fear_greed.get("score") or 50
    rating = fear_greed.get("rating_ja","---")
    if score >= 75:   level = "😱 超強欲（バブル注意）"
    elif score >= 55: level = "😤 強欲（強気が優勢）"
    elif score >= 45: level = "😐 中立"
    elif score >= 25: level = "😰 恐怖（弱気が優勢）"
    else:             level = "😭 超恐怖（底値チャンスかも）"
    return f"Fear&Greed: {score:.0f}/100\n{rating} → {level}"


def _exec_get_history_comparison(args: dict) -> str:
    sym  = args.get("symbol","^N225")
    days = args.get("days", 30)
    try:
        import yfinance as yf
        ticker = yf.Ticker(sym)
        hist = ticker.history(period=f"{days+5}d")
        if hist.empty or len(hist) < 5:
            return f"{sym}: 履歴データなし"
        cur    = hist["Close"].iloc[-1]
        past   = hist["Close"].iloc[-(days if days <= len(hist) else len(hist))]
        chg    = (cur - past) / past * 100
        hi     = hist["High"].max()
        lo     = hist["Low"].min()
        arrow  = "▲" if chg >= 0 else "▼"
        return (
            f"【{sym} {days}日比較】\n"
            f"{days}日前比: {arrow}{abs(chg):.2f}%\n"
            f"{days}日高値: {hi:,.2f} / 安値: {lo:,.2f}\n"
            f"現在値: {cur:,.2f}"
        )
    except Exception as e:
        return f"{sym}: 履歴比較エラー ({e})"


def _exec_get_scenario_data(prices: dict, risk: dict) -> str:
    score = risk.get("score", 0)
    nk = prices.get("^N225",{}).get("latest") or 0
    sp = prices.get("^GSPC",{}).get("latest") or 0
    # 簡易シナリオ
    return (
        f"【シナリオデータ】\n"
        f"現在スコア: {score:+.2f}\n"
        f"楽観シナリオ: 日経{nk*1.05:,.0f}円 / S&P{sp*1.05:,.0f}（+5%）\n"
        f"基本シナリオ: 日経{nk:,.0f}円 / S&P{sp:,.0f}（現状維持）\n"
        f"悲観シナリオ: 日経{nk*0.95:,.0f}円 / S&P{sp*0.95:,.0f}（-5%）"
    )


# ──────────────────────────────────────────────
# エージェントメインループ
# ──────────────────────────────────────────────

def run_agent(prices: dict, news: list, risk: dict, fear_greed: dict) -> dict:
    """
    自律AIエージェントを実行。
    GeminiがToolを自分で選んで多段分析し、最終レポートを返す。
    """
    api_key = os.getenv("GEMINI_API_KEY","").strip()
    if not api_key:
        return {"available": False, "reason": "GEMINI_API_KEY未設定"}

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)

        # Function Calling用ツール定義
        tools_def = [
            genai.protos.Tool(
                function_declarations=[
                    genai.protos.FunctionDeclaration(
                        name=t["name"],
                        description=t["description"],
                        parameters=genai.protos.Schema(
                            type=genai.protos.Type.OBJECT,
                            properties={
                                k: genai.protos.Schema(
                                    type=genai.protos.Type.STRING
                                    if v["type"] == "string"
                                    else genai.protos.Type.INTEGER
                                    if v["type"] == "integer"
                                    else genai.protos.Type.ARRAY,
                                    description=v.get("description","")
                                )
                                for k, v in t["parameters"].get("properties",{}).items()
                            }
                        )
                    )
                    for t in TOOLS
                ]
            )
        ]

        model = genai.GenerativeModel(
            "gemini-1.5-flash",
            tools=tools_def,
        )

        now_str = get_jst_now().strftime("%Y-%m-%d %H:%M JST")
        score   = risk.get("score", 0)
        fg      = fear_greed.get("score") or 50

        # 初期プロンプト（エージェントへの指示）
        system_prompt = f"""あなたは高度な市場分析AIエージェントです。
現在時刻: {now_str}
市場リスクスコア: {score:+.2f}
Fear&Greed: {fg:.0f}

以下の手順で自律的に分析してください：
1. まず重要な市場データ（価格・テクニカル・ニュース）を収集
2. 収集した情報を統合して深く分析
3. 楽観・基本・悲観の3シナリオを考察
4. 最終的な総合判断を出す

ツールを積極的に使って、できるだけ多角的に分析してください。
分析が完了したら「FINAL_REPORT」というキーワードを含めて最終レポートを出力してください。"""

        chat    = model.start_chat()
        response = chat.send_message(system_prompt)

        tool_results_log = []
        max_turns = 6  # 最大6回のツール呼び出し

        for turn in range(max_turns):
            # Function Call があるか確認
            has_tool_call = False
            for part in response.parts:
                if hasattr(part, "function_call") and part.function_call.name:
                    has_tool_call = True
                    fc   = part.function_call
                    name = fc.name
                    args = dict(fc.args) if fc.args else {}

                    logger.info(f"🔧 エージェントがツール呼び出し: {name}({args})")

                    # ツール実行
                    if name == "get_market_prices":
                        result = _exec_get_market_prices(args, prices)
                    elif name == "get_news_summary":
                        result = _exec_get_news_summary(args, news)
                    elif name == "get_technical_signals":
                        result = _exec_get_technical_signals(args)
                    elif name == "get_fear_greed":
                        result = _exec_get_fear_greed(fear_greed)
                    elif name == "get_history_comparison":
                        result = _exec_get_history_comparison(args)
                    elif name == "get_scenario_data":
                        result = _exec_get_scenario_data(prices, risk)
                    else:
                        result = f"{name}: 未知のツール"

                    tool_results_log.append({"tool": name, "result": result[:200]})
                    logger.info(f"   → 結果: {result[:80]}...")

                    # ツール結果を返す
                    response = chat.send_message(
                        genai.protos.Content(
                            parts=[genai.protos.Part(
                                function_response=genai.protos.FunctionResponse(
                                    name=name,
                                    response={"result": result}
                                )
                            )]
                        )
                    )
                    break  # 1ターン1ツール

            if not has_tool_call:
                # ツール呼び出しなし = 最終回答
                break

        # 最終テキスト取得
        final_text = ""
        for part in response.parts:
            if hasattr(part, "text") and part.text:
                final_text += part.text

        if not final_text:
            final_text = "エージェント分析完了（テキスト取得エラー）"

        logger.info(f"✅ エージェント完了 (ツール呼び出し{len(tool_results_log)}回)")

        # セクション分割
        sections = _parse_agent_report(final_text)

        return {
            "available":    True,
            "full_report":  final_text,
            "sections":     sections,
            "tools_used":   tool_results_log,
            "tool_count":   len(tool_results_log),
        }

    except Exception as e:
        logger.error(f"エージェントエラー: {e}")
        logger.debug(traceback.format_exc())
        return {"available": False, "reason": str(e)}


def _parse_agent_report(text: str) -> dict:
    """エージェントレポートをセクションに分割"""
    sections = {
        "summary":  "",
        "technical":"",
        "scenario": "",
        "judgment": "",
    }
    current = "summary"
    lines   = []

    keywords = {
        "テクニカル": "technical",
        "RSI": "technical",
        "MACD": "technical",
        "シナリオ": "scenario",
        "楽観": "scenario",
        "悲観": "scenario",
        "総合判断": "judgment",
        "FINAL_REPORT": "judgment",
        "最終": "judgment",
    }

    for line in text.split("\n"):
        switched = False
        for kw, sec in keywords.items():
            if kw in line and sec != current:
                if lines:
                    sections[current] += "\n".join(lines).strip()
                current = sec
                lines   = []
                switched = True
                break
        if not switched:
            if line.strip():
                lines.append(line)

    if lines:
        sections[current] += "\n".join(lines).strip()

    return sections
