"""
需給分析エンジン（Supply & Demand）
株価は最終的に「買いたい人」と「売りたい人」の力関係で動く。
出来高・資金フローから需給を読み、上昇しやすいパターンを判定する。

使う指標（すべて価格＋出来高から計算・APIキー不要）：
  - 出来高比率   : 直近の商いが平常時の何倍か（エネルギーの強さ）
  - OBV          : 買い圧力と売り圧力どちらが蓄積しているか
  - MFI          : 出来高加重RSI。資金が流入か流出か（売られすぎ/買われすぎ）
  - CMF          : チャイキンマネーフロー。機関の買い集め/売り抜けの目安
  - Volume Profile: 価格帯別出来高。最も商いが多い価格(POC)＝上値抵抗/下値支持

これらから「上がりやすい需給パターン」を判定し、ウォッチリストをランキングする。

⚠️ 需給は上昇の「確率を高める材料」であって確実な予知ではない。
   信用買い残・売り残（銘柄別）は無料での確実な取得が難しいため未使用。
"""
import os
import time

import numpy as np
import pandas as pd

from src.utils import setup_logger, get_jst_now, BASE_DIR

logger = setup_logger("supply_demand")


def _load_watchlist():
    import json
    path = BASE_DIR / "data" / "watchlist.json"
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for s in data.get("stocks", []):
            if s.get("symbol"):
                out.append((s["symbol"], s.get("name", s["symbol"])))
    except Exception as e:
        logger.warning(f"watchlist読み込み失敗: {e}")
    return out


# ── 需給指標の計算 ───────────────────────────────────────────
def analyze_one(hist: pd.DataFrame) -> dict | None:
    """1銘柄の価格×出来高ヒストリーから需給指標を計算"""
    if hist is None or len(hist) < 30:
        return None
    c = hist["Close"]; v = hist["Volume"]
    hi = hist["High"]; lo = hist["Low"]

    # 出来高比率（直近5日平均 / 25日平均）
    vol_ratio = float(v.tail(5).mean() / (v.tail(25).mean() + 1e-9))

    # OBV（オンバランスボリューム）
    obv = (np.sign(c.diff()) * v).fillna(0).cumsum()
    obv_rising = bool(obv.iloc[-1] > obv.iloc[-10])
    obv_slope = float((obv.iloc[-1] - obv.iloc[-10]) / (abs(obv.iloc[-10]) + 1e-9) * 100)

    # MFI(14) マネーフローインデックス
    tp = (hi + lo + c) / 3
    mf = tp * v
    pos = mf.where(tp > tp.shift(), 0).rolling(14).sum()
    neg = mf.where(tp < tp.shift(), 0).rolling(14).sum()
    mfi = float((100 - 100 / (1 + pos / (neg + 1e-9))).iloc[-1])

    # CMF(20) チャイキンマネーフロー
    mfm = ((c - lo) - (hi - c)) / ((hi - lo).replace(0, np.nan))
    mfv = (mfm * v).fillna(0)
    cmf = float(mfv.tail(20).sum() / (v.tail(20).sum() + 1e-9))

    # Volume Profile（価格帯別出来高 → POC）
    cl = c.values; vl = v.values
    pmin, pmax = cl.min(), cl.max()
    bins = np.linspace(pmin, pmax, 20)
    idx = np.digitize(cl, bins)
    prof = {}
    for i, vol in zip(idx, vl):
        prof[i] = prof.get(i, 0) + vol
    poc_bin = max(prof, key=prof.get)
    poc_price = float(bins[min(poc_bin - 1, len(bins) - 1)])
    cur = float(c.iloc[-1])
    above_poc = bool(cur > poc_price)

    # 価格トレンド
    chg5 = float((c.iloc[-1] / c.iloc[-6] - 1) * 100)
    chg25 = float((c.iloc[-1] / c.iloc[-26] - 1) * 100)
    ma25 = float(c.tail(25).mean())
    above_ma25 = bool(cur > ma25)

    return {
        "current": round(cur, 1),
        "vol_ratio": round(vol_ratio, 2),
        "obv_rising": obv_rising,
        "obv_slope": round(obv_slope, 1),
        "mfi": round(mfi, 0),
        "cmf": round(cmf, 3),
        "poc": round(poc_price, 1),
        "above_poc": above_poc,
        "chg5": round(chg5, 1),
        "chg25": round(chg25, 1),
        "above_ma25": above_ma25,
    }


# ── 上昇パターン判定 ─────────────────────────────────────────
def detect_patterns(m: dict) -> list[dict]:
    """需給指標から該当する「上がりやすいパターン」「警戒パターン」を判定"""
    pats = []

    # 📈 出来高を伴う上昇 = 買いの本気度（最も信頼できる上昇）
    if m["vol_ratio"] >= 1.3 and m["chg5"] > 0 and m["obv_rising"]:
        pats.append({"sig": "bull", "emoji": "🚀", "name": "大商いを伴う上昇",
                     "desc": "出来高が増えながら上昇＝買いの本気度が高い。最も信頼できる上昇サイン"})

    # 📈 ブレイクアウト = しこりを抜けた
    if m["above_poc"] and m["vol_ratio"] >= 1.4:
        pats.append({"sig": "bull", "emoji": "⛰", "name": "上値ブレイク",
                     "desc": "最も商いの多い価格帯(POC)を大商いで上抜け。上値が軽くなった"})

    # 📈 機関の買い集め = CMFプラスでOBV上昇
    if m["cmf"] >= 0.1 and m["obv_rising"]:
        pats.append({"sig": "bull", "emoji": "🏦", "name": "資金流入（買い集め）",
                     "desc": "資金が継続的に流入。大口が静かに買い集めている可能性"})

    # 🔄 売られすぎ反転期待 = MFI低位
    if m["mfi"] <= 25:
        pats.append({"sig": "bull", "emoji": "🔄", "name": "売られすぎ反転期待",
                     "desc": "資金流出が極端で売られすぎ。反発（リバウンド）が起きやすい水準"})

    # ⚠️ 高値圏の過熱 = MFI高位
    if m["mfi"] >= 80:
        pats.append({"sig": "warn", "emoji": "🔥", "name": "過熱（買われすぎ）",
                     "desc": "資金流入が過熱。短期的な利益確定売りに注意"})

    # ⚠️ 資金流出（売り抜け） = CMFマイナス
    if m["cmf"] <= -0.1 and not m["obv_rising"]:
        pats.append({"sig": "warn", "emoji": "📉", "name": "資金流出（売り抜け）",
                     "desc": "資金が継続的に流出。大口が手仕舞っている可能性"})

    # ⚠️ 上昇だが出来高が伴わない = だましの可能性
    if m["chg5"] > 2 and m["vol_ratio"] < 0.8:
        pats.append({"sig": "warn", "emoji": "🪶", "name": "薄商いの上昇",
                     "desc": "出来高を伴わない上昇。買いの勢いが弱く戻り売りに押されやすい"})

    if not pats:
        pats.append({"sig": "neutral", "emoji": "➡️", "name": "中立",
                     "desc": "需給は拮抗。明確な方向感は出ていない"})
    return pats


def score_supply_demand(m: dict) -> int:
    """需給の総合スコア（0〜100。高いほど上がりやすい需給）"""
    s = 50
    s += 12 if m["obv_rising"] else -12
    if m["vol_ratio"] >= 1.3: s += 12
    elif m["vol_ratio"] < 0.7: s -= 6
    if m["cmf"] >= 0.1: s += 14
    elif m["cmf"] <= -0.1: s -= 14
    if m["above_poc"]: s += 8
    if m["above_ma25"]: s += 6
    # MFI：健全な流入は加点、過熱は減点、売られすぎは反発期待で小加点
    if 45 <= m["mfi"] <= 70: s += 10
    elif m["mfi"] >= 85: s -= 10
    elif m["mfi"] <= 25: s += 4
    # 空売り残高：踏み上げ余地（買い戻し進行）は加点、売り増しは減点
    sr = m.get("short_ratio", 0)
    st = m.get("short_trend", "")
    if sr >= 1.5:
        if st == "decreasing": s += 12   # 踏み上げ進行＝買い戻しの燃料
        elif st == "increasing": s -= 10  # 機関が売り増し＝弱気
        else: s += 6                      # 高水準で踏み上げ余地
    return int(max(0, min(100, s)))


# ── Gemini 総評 ──────────────────────────────────────────────
def _gemini_comment(ranked: list) -> str:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or not ranked:
        return ""
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
        top = ranked[:5]
        txt = "\n".join(
            f"{i+1}. {r['name']}（需給スコア{r['score']}・{r['patterns'][0]['name']}）"
            for i, r in enumerate(top)
        )
        prompt = f"""以下は出来高・資金フローから見た需給良好な銘柄ランキングです。
投資初心者向けに、今どんな需給状況か・何に注目すべきかを150字以内でやさしく解説してください。

{txt}

解説（150字以内・「必ず上がる」等の断定は避ける）:"""
        return model.generate_content(prompt).text.strip()
    except Exception as e:
        logger.warning(f"Gemini需給コメント失敗: {e}")
        return ""


# ── メイン ───────────────────────────────────────────────────
def run(prices: dict = None, risk: dict = None, fear_greed: dict = None) -> dict:
    try:
        import yfinance as yf
    except Exception:
        return {"available": False, "reason": "yfinance不在"}

    symbols = _load_watchlist()
    if not symbols:
        return {"available": False, "reason": "watchlist空"}

    # 空売り残高アナライザー（karauri.net）
    try:
        from src.short_selling import fetch_short_interest, judge_squeeze
        _has_short = True
    except Exception:
        _has_short = False

    ranked = []
    for sym, name in symbols:
        try:
            hist = yf.Ticker(sym).history(period="4mo")
            m = analyze_one(hist)
            if not m:
                continue
            # 空売り残高を取得して需給に反映
            squeeze = None
            if _has_short:
                try:
                    si = fetch_short_interest(sym)
                    if si.get("available"):
                        m["short_ratio"] = si["total_ratio"]
                        m["short_trend"] = si["trend"]
                        squeeze = judge_squeeze(si)
                except Exception:
                    pass
            pats = detect_patterns(m)
            if squeeze and squeeze["sig"] != "none" and squeeze["name"]:
                pats.insert(0, squeeze)  # 空売りシグナルを先頭に
            score = score_supply_demand(m)
            ranked.append({
                "symbol": sym, "code": sym.split(".")[0], "name": name,
                "metrics": m, "patterns": pats, "score": score,
                "squeeze": squeeze,
            })
            time.sleep(0.15)
        except Exception:
            pass

    if not ranked:
        return {"available": False, "reason": "データ取得失敗"}

    ranked.sort(key=lambda x: x["score"], reverse=True)
    comment = _gemini_comment(ranked)

    result = {
        "available": True,
        "ranked": ranked,
        "top": ranked[:5],
        "count": len(ranked),
        "ai_comment": comment,
    }
    result["html"] = get_html(result)
    result["telegram_message"] = build_telegram_message(result)
    return result


# ── 出力 ─────────────────────────────────────────────────────
def build_telegram_message(result: dict) -> str:
    if not result.get("available"):
        return ""
    lines = ["📊 *需給分析ランキング（上がりやすい順）*", ""]
    for i, r in enumerate(result["top"]):
        medal = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][i]
        p = r["patterns"][0]
        lines.append(f"{medal} *[{r['code']}] {r['name']}*  需給{r['score']}点")
        lines.append(f"　{p['emoji']} {p['name']}")
    if result.get("ai_comment"):
        lines.append("")
        lines.append(f"💡 {result['ai_comment']}")
    lines.append("")
    lines.append("※需給は上昇の確率を高める材料であり確約ではありません")
    return "\n".join(lines)


def get_html(result: dict) -> str:
    if not result or not result.get("available"):
        return ""
    sig_color = {"bull": "#3fb950", "warn": "#ffa726", "neutral": "#7a8fa8"}
    rows = ""
    for i, r in enumerate(result["ranked"][:15]):
        m = r["metrics"]
        sc = r["score"]
        bar_c = "#3fb950" if sc >= 65 else "#ffa726" if sc >= 45 else "#f44336"
        pat_html = ""
        for p in r["patterns"]:
            c = sig_color.get(p["sig"], "#7a8fa8")
            pat_html += (f'<div style="font-size:0.78em;color:{c};margin-top:2px;">'
                         f'{p["emoji"]} {p["name"]}<span style="color:#8a9bb0;">'
                         f'　{p["desc"]}</span></div>')
        rows += f'''
<div style="padding:11px 0;border-bottom:1px solid #1e2d42;">
  <div style="display:flex;align-items:center;gap:10px;">
    <div style="width:26px;text-align:center;font-weight:700;color:#7a8fa8;">{i+1}</div>
    <div style="flex:1;font-weight:700;font-size:0.9em;">[{r["code"]}] {r["name"]}</div>
    <div style="text-align:right;">
      <div style="font-weight:900;color:{bar_c};">{sc}<span style="font-size:0.6em;color:#7a8fa8;">点</span></div>
    </div>
  </div>
  <div style="margin-left:36px;">
    <div style="font-size:0.72em;color:#7a8fa8;margin-top:3px;">
      出来高{m["vol_ratio"]}倍 ・ MFI{m["mfi"]:.0f} ・ 資金フロー{m["cmf"]:+.2f} ・ OBV{"↑" if m["obv_rising"] else "↓"} ・ {"POC上" if m["above_poc"] else "POC下"}{f' ・ 空売り{m["short_ratio"]}%' if m.get("short_ratio") else ""}
    </div>
    {pat_html}
  </div>
</div>'''

    ai = ""
    if result.get("ai_comment"):
        ai = (f'<div style="background:#070f1f;border:1px solid #00d4ff33;border-radius:10px;'
              f'padding:12px;margin-top:12px;font-size:0.85em;line-height:1.7;color:#dde8ff;">'
              f'💡 {result["ai_comment"]}</div>')

    return f'''
<div style="background:#0f1623;border:1px solid #1e2d42;border-radius:14px;padding:16px;">
  <div style="font-size:0.75em;color:#7a8fa8;margin-bottom:10px;">
    出来高・資金フローから「買いの勢い」が強い順にランキング。需給は上昇確率を高める材料です（確約ではありません）
  </div>
  {rows}{ai}
</div>'''


if __name__ == "__main__":
    r = run()
    out = []
    if r.get("available"):
        out.append(f"=== 需給分析ランキング（{r['count']}銘柄）===\n")
        for i, x in enumerate(r["ranked"]):
            m = x["metrics"]
            out.append(f"{i+1}位 [{x['code']}] {x['name']}  需給{x['score']}点")
            out.append(f"   出来高{m['vol_ratio']}倍 MFI{m['mfi']:.0f} CMF{m['cmf']:+.2f} OBV{'↑' if m['obv_rising'] else '↓'} {'POC上' if m['above_poc'] else 'POC下'}")
            for p in x["patterns"]:
                out.append(f"   {p['emoji']} {p['name']}: {p['desc']}")
            out.append("")
    else:
        out.append(f"取得失敗: {r.get('reason','')}")
    text = "\n".join(out)
    try:
        print(text)
    except UnicodeEncodeError:
        with open("sd_output.txt", "w", encoding="utf-8") as f:
            f.write(text)
        print("sd_output.txt に保存しました")
