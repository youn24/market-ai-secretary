"""
セクター分析・ローテーション検出（Level 4a）
米国11セクターETFのパフォーマンスを取得し、資金フローとローテーションをAI分析
"""
import os
import traceback
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

SECTORS = {
    "テクノロジー":  "XLK",
    "金融":          "XLF",
    "エネルギー":    "XLE",
    "ヘルスケア":    "XLV",
    "資本財":        "XLI",
    "一般消費財":    "XLY",
    "生活必需品":    "XLP",
    "通信":          "XLC",
    "素材":          "XLB",
    "公益":          "XLU",
    "不動産":        "XLRE",
}

# ローテーション分類: 景気サイクルに応じた強弱グループ
CYCLICAL     = {"テクノロジー", "金融", "資本財", "一般消費財", "素材", "エネルギー"}
DEFENSIVE    = {"生活必需品", "公益", "ヘルスケア", "不動産"}


def fetch_sector_data():
    """セクターETFの1日/1週/1ヶ月パフォーマンスを取得"""
    symbols = list(SECTORS.values())
    try:
        end = datetime.now()
        start = end - timedelta(days=40)
        data = yf.download(symbols, start=start, end=end, progress=False, auto_adjust=True)["Close"]
        if isinstance(data, pd.Series):
            data = data.to_frame()

        results = []
        for name, sym in SECTORS.items():
            if sym not in data.columns:
                continue
            prices = data[sym].dropna()
            if len(prices) < 2:
                continue

            cur   = float(prices.iloc[-1])
            d1    = float(prices.iloc[-2])  if len(prices) >= 2  else cur
            w1    = float(prices.iloc[-6])  if len(prices) >= 6  else float(prices.iloc[0])
            m1    = float(prices.iloc[-22]) if len(prices) >= 22 else float(prices.iloc[0])

            results.append({
                "name":   name,
                "symbol": sym,
                "price":  cur,
                "chg_1d": (cur - d1) / d1 * 100,
                "chg_1w": (cur - w1) / w1 * 100,
                "chg_1m": (cur - m1) / m1 * 100,
            })

        return sorted(results, key=lambda x: x["chg_1d"], reverse=True)

    except Exception:
        return []


def detect_rotation(sectors: list) -> dict:
    """景気サイクル上のローテーションパターンを検出"""
    if not sectors:
        return {"label": "データなし", "phase": "不明", "detail": ""}

    rising  = [s for s in sectors if s["chg_1d"] > 0.3]
    falling = [s for s in sectors if s["chg_1d"] < -0.3]
    rising_names  = {s["name"] for s in rising}
    falling_names = {s["name"] for s in falling}

    cyc_up  = rising_names  & CYCLICAL
    def_up  = rising_names  & DEFENSIVE
    cyc_dn  = falling_names & CYCLICAL
    def_dn  = falling_names & DEFENSIVE

    if len(cyc_up) >= 3 and len(def_dn) >= 1:
        phase  = "リスクオン"
        label  = "景気敏感株に資金流入 🟢"
        detail = f"上昇: {', '.join(list(cyc_up)[:3])} ／ 下落: {', '.join(list(def_dn)[:2])}"
    elif len(def_up) >= 2 and len(cyc_dn) >= 2:
        phase  = "リスクオフ"
        label  = "ディフェンシブ株に資金退避 🔴"
        detail = f"上昇: {', '.join(list(def_up)[:3])} ／ 下落: {', '.join(list(cyc_dn)[:2])}"
    elif "エネルギー" in rising_names and len(rising_names) <= 4:
        phase  = "スタグフレーション懸念"
        label  = "エネルギー独歩高 ⚠️"
        detail = "原油高・インフレ圧力が示唆される動き"
    elif "金融" in rising_names and "テクノロジー" in rising_names:
        phase  = "景気拡大"
        label  = "金融+テクノロジー同時高 📈"
        detail = "金利上昇期待＋成長期待が共存する強い局面"
    elif len(rising) <= 2 and len(falling) >= 7:
        phase  = "全面安"
        label  = "広範な売り圧力 🔴🔴"
        detail = f"上昇は {', '.join(list(rising_names)[:2]) or 'なし'} のみ"
    else:
        top3 = [s["name"] for s in sectors[:3]]
        bot3 = [s["name"] for s in sectors[-3:]]
        phase  = "方向感なし"
        label  = "まちまち"
        detail = f"強い: {', '.join(top3)} ／ 弱い: {', '.join(bot3)}"

    return {"label": label, "phase": phase, "detail": detail}


def analyze_with_gemini(sectors: list, rotation: dict) -> str:
    """Geminiでセクターローテーションの意味を解説"""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or not sectors:
        return ""
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))

        sector_text = "\n".join(
            f"・{s['name']}({s['symbol']}): 日次{s['chg_1d']:+.1f}% ／ 週次{s['chg_1w']:+.1f}% ／ 月次{s['chg_1m']:+.1f}%"
            for s in sectors
        )
        prompt = f"""米国株セクター別パフォーマンスを分析してください（投資初心者向け）。

【セクター成績】
{sector_text}

【検出パターン】フェーズ: {rotation['phase']} / {rotation['label']}
{rotation['detail']}

以下を150字以内で日本語で答えてください：
①現在の資金の流れ（どのセクターに集まっているか）
②日経平均・日本株への影響
③来週注目すべき点（1つだけ）"""

        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception:
        return ""


def run() -> dict:
    """セクター分析メイン（cloud_run.pyから呼び出す）"""
    try:
        sectors  = fetch_sector_data()
        if not sectors:
            return {"available": False}

        rotation   = detect_rotation(sectors)
        ai_comment = analyze_with_gemini(sectors, rotation)

        return {
            "available":  True,
            "sectors":    sectors,          # 全11セクター（日次降順）
            "rotation":   rotation,         # ローテーション判定
            "ai_comment": ai_comment,       # Gemini解説
            "top3":       sectors[:3],      # 強いセクター上位3
            "bottom3":    sectors[-3:],     # 弱いセクター下位3
            "best":       sectors[0],
            "worst":      sectors[-1],
        }
    except Exception:
        return {"available": False}
