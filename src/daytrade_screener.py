"""
本日のデイトレ注目銘柄スクリーナー（事前分析エンジン）

朝7:30（寄り付き前）に、その日「動きそうな・ボラのある銘柄」をスコアで抽出する。
材料分析AI・ADR夜間・ボラティリティ・出来高・価格レベルを統合してランキング化し、
各銘柄に重要価格レベル＋「場が開いてから見るルール」を付ける。

スコアの考え方（今日動く度）：
  ・ボラティリティ（日中値幅％が大きいほどデイトレ向き）
  ・流動性（売買代金。小さすぎると約定しづらく除外）
  ・材料の強さ（材料分析AIの資金妙味）
  ・夜間の動き（ADR乖離の大きさ）
  ・出来高の異常（直近平均比で急増）

⚠️ できないことは正直に：
  - VWAP・寄り5分高安・歩み値・板読みは9:00以降のリアルタイム情報で、寄り前・無料データには存在しない。
    これらは銘柄ごとの「場が開いたら自分の目で確認するルール」として提示する（ライブ監視はしない）。
  - AIの事前シナリオであり、株価を保証するものではない。最終判断はご自身で。
"""
import json
import math

from src.utils import BASE_DIR, setup_logger

logger = setup_logger("daytrade_screener")

# ── デイトレ向きの流動性・ボラのある定番ユニバース ───────────────────
_CURATED = [
    ("8035", "東京エレクトロン"), ("6857", "アドバンテスト"), ("6920", "レーザーテック"),
    ("6146", "ディスコ"), ("3436", "SUMCO"), ("6526", "ソシオネクスト"),
    ("285A", "キオクシア"), ("6723", "ルネサス"), ("6963", "ローム"),
    ("9984", "ソフトバンクG"), ("6758", "ソニーG"), ("7974", "任天堂"),
    ("6098", "リクルート"), ("4385", "メルカリ"), ("4751", "サイバーA"),
    ("3659", "ネクソン"), ("5253", "カバー"), ("3778", "さくらネット"),
    ("8306", "三菱UFJ"), ("8316", "三井住友FG"), ("8411", "みずほFG"),
    ("7203", "トヨタ"), ("7267", "ホンダ"), ("7201", "日産"),
    ("8058", "三菱商事"), ("8031", "三井物産"), ("6501", "日立"),
    ("7011", "三菱重工"), ("7012", "川崎重工"), ("7013", "IHI"),
    ("9101", "日本郵船"), ("9104", "商船三井"), ("5401", "日本製鉄"),
    ("6594", "ニデック"), ("4063", "信越化学"), ("6954", "ファナック"),
]


def _load_watchlist():
    out = []
    try:
        with open(BASE_DIR / "data" / "watchlist.json", encoding="utf-8") as f:
            data = json.load(f)
        for s in data.get("stocks", []):
            code = s.get("symbol", "").split(".")[0].strip().upper()
            if code:
                out.append((code, s.get("name", code)))
    except Exception as e:
        logger.warning(f"watchlist読み込み失敗: {e}")
    return out


def _gather_candidates(catalyst, adr):
    """分析対象の銘柄集合（コード→{name, reasons, cat_appeal, adr_div}）"""
    cand = {}

    def add(code, name, reason=None):
        code = str(code).split(".")[0].strip().upper()
        if not code:
            return
        if code not in cand:
            cand[code] = {"name": name or code, "reasons": [], "cat_appeal": "", "adr_div": None}
        if name and cand[code]["name"] == code:
            cand[code]["name"] = name
        if reason:
            cand[code]["reasons"].append(reason)

    for c, n in _load_watchlist():
        add(c, n)
    for c, n in _CURATED:
        add(c, n)

    for c in (catalyst or {}).get("catalysts", []):
        code = str(c.get("code", "")).split(".")[0].upper()
        add(code, c.get("name", ""), f"材料：{c.get('catalyst_type','')}")
        if code in cand:
            cand[code]["cat_appeal"] = c.get("appeal", "")

    for x in (adr or {}).get("all", []):
        if abs(x.get("divergence", 0)) >= 0.7:
            code = str(x.get("code", "")).split(".")[0].upper()
            add(code, x.get("name", ""), f"夜間ADR {x['divergence']:+.1f}%")
            if code in cand:
                cand[code]["adr_div"] = x.get("divergence")

    return cand


def _batch_fetch(codes):
    """yfinanceで複数銘柄の1ヶ月足を一括取得"""
    import warnings
    warnings.filterwarnings("ignore")
    import yfinance as yf

    tickers = [f"{c}.T" for c in codes]
    data = {}
    try:
        df = yf.download(tickers, period="1mo", group_by="ticker",
                         progress=False, auto_adjust=True, threads=True)
    except Exception as e:
        logger.warning(f"バッチ取得失敗: {e}")
        return data

    for code in codes:
        t = f"{code}.T"
        try:
            h = df[t].dropna() if len(tickers) > 1 else df.dropna()
            if len(h) >= 6:
                data[code] = h
        except Exception:
            continue
    return data


def _pivot(h):
    high = float(h["High"].iloc[-1]); low = float(h["Low"].iloc[-1]); close = float(h["Close"].iloc[-1])
    pp = (high + low + close) / 3
    return {
        "prev_high": round(high), "prev_low": round(low), "prev_close": round(close),
        "pivot": round(pp), "r1": round(2 * pp - low), "s1": round(2 * pp - high),
        "r2": round(pp + (high - low)), "s2": round(pp - (high - low)),
    }


def _metrics(h):
    close = h["Close"]; high = h["High"]; low = h["Low"]; vol = h["Volume"]
    last_c = float(close.iloc[-1])
    rng = ((high - low) / close * 100).tail(14)
    atr_pct = round(float(rng.mean()), 1)
    turnover = round(last_c * float(vol.iloc[-1]) / 1e8, 0)
    v20 = float(vol.tail(20).mean())
    vol_ratio = round(float(vol.iloc[-1]) / v20, 1) if v20 > 0 else 0
    hi20 = float(high.tail(20).max()); lo20 = float(low.tail(20).min())
    pos = round((last_c - lo20) / (hi20 - lo20) * 100, 0) if hi20 > lo20 else 50
    chg_1d = round((last_c / float(close.iloc[-2]) - 1) * 100, 1) if len(close) >= 2 else 0
    chg_5d = round((last_c / float(close.iloc[-6]) - 1) * 100, 1) if len(close) >= 6 else 0
    return {
        "close": round(last_c), "atr_pct": atr_pct, "turnover": turnover,
        "vol_ratio": vol_ratio, "hi20": round(hi20), "lo20": round(lo20),
        "pos_20d": pos, "chg_1d": chg_1d, "chg_5d": chg_5d, **_pivot(h),
    }


def _score(m, info):
    """今日動く度スコア（流動性が低すぎる銘柄は None で除外）"""
    if m["turnover"] < 5:
        return None
    score = 0.0
    score += min(m["atr_pct"] / 6.0, 1.0) * 35                      # ボラ
    score += min(math.log10(max(m["turnover"], 1)) / 3.5, 1.0) * 20  # 流動性
    score += min(max(m["vol_ratio"] - 1.0, 0) / 1.5, 1.0) * 12       # 出来高急増
    score += {"高": 18, "中": 10, "低": 4}.get(info.get("cat_appeal", ""), 0)  # 材料
    if info.get("adr_div") is not None:
        score += min(abs(info["adr_div"]) / 2.0, 1.0) * 15            # 夜間ADR
    return round(score, 1)


def _playbook(m):
    return {
        "long_trigger": f"寄り後、前日高値 {m['prev_high']:,}円 を出来高を伴って上抜け＋VWAP上で推移",
        "target": f"R1 {m['r1']:,}円 → R2 {m['r2']:,}円（直近20日高値 {m['hi20']:,}円も意識）",
        "stop": f"前日安値 {m['prev_low']:,}円 割れ、またはVWAPを明確に割ったら撤退",
        "eyes": "板：厚い売り板を食って上がるか・買い板が切り上がるか／歩み値：買い約定が続くか（自分の目で確認）",
    }


def run(prices: dict = None, risk: dict = None, fear_greed: dict = None,
        catalyst: dict = None, adr: dict = None, top_n: int = 6) -> dict:
    cand = _gather_candidates(catalyst, adr)
    if not cand:
        return {"available": False, "reason": "候補なし"}

    codes = list(cand.keys())
    logger.info(f"デイトレ候補 {len(codes)}銘柄を分析…")
    hist = _batch_fetch(codes)
    if not hist:
        return {"available": False, "reason": "価格取得失敗"}

    ranked = []
    for code, h in hist.items():
        try:
            m = _metrics(h)
        except Exception:
            continue
        info = cand.get(code, {})
        sc = _score(m, info)
        if sc is None:
            continue
        ranked.append({
            "code": code, "name": info.get("name", code), "score": sc,
            "reasons": info.get("reasons", []), "cat_appeal": info.get("cat_appeal", ""),
            "adr_div": info.get("adr_div"), "metrics": m, "playbook": _playbook(m),
        })

    if not ranked:
        return {"available": False, "reason": "条件を満たす銘柄なし"}

    ranked.sort(key=lambda x: x["score"], reverse=True)
    top = ranked[:top_n]
    result = {"available": True, "count": len(ranked), "top": top, "universe_size": len(codes)}
    result["telegram_message"] = build_telegram_message(result)
    result["html"] = get_html(result)
    logger.info(f"✅ デイトレ抽出: {len(codes)}銘柄→上位{len(top)}（首位 {top[0]['name']} {top[0]['score']}点）")
    return result


def _mark(appeal):
    return {"高": "🟢", "中": "🟡", "低": "⚪"}.get(appeal, "")


def build_telegram_message(result: dict) -> str:
    if not result.get("available"):
        return ""
    top = result["top"]
    head = f"🎰 本日のデイトレ注目：{top[0]['name']}ほか{len(top)}銘柄"
    lines = [head, "", f"今日ボラが出やすい順（材料・夜間・出来高・値幅で {result['universe_size']}銘柄から抽出）", ""]
    for i, s in enumerate(top, 1):
        m = s["metrics"]
        rs = "／".join(s["reasons"][:2]) if s["reasons"] else "ボラ・流動性"
        lines.append(f"*{i}. [{s['code']}] {s['name']}*　{s['score']:.0f}点{_mark(s['cat_appeal'])}")
        lines.append(f"　値幅{m['atr_pct']}%・売買代金{m['turnover']:.0f}億・出来高{m['vol_ratio']}x")
        lines.append(f"　{rs}")
        lines.append(f"　🎯 {s['playbook']['long_trigger']}")
        lines.append(f"　🛑 {s['playbook']['stop']}")
        lines.append("")
    lines.append("※板・VWAP・歩み値は寄り後に自分の目で確認。AIの事前シナリオです")
    return "\n".join(lines).strip()


def get_html(result: dict) -> str:
    if not result or not result.get("available"):
        return ""
    cards = ""
    for i, s in enumerate(result["top"], 1):
        m = s["metrics"]
        sc_col = "#3fb950" if s["score"] >= 60 else ("#d29922" if s["score"] >= 45 else "#58a6ff")
        reasons = "".join(
            f'<span style="display:inline-block;background:#1b2433;color:#9fb4d4;border-radius:5px;padding:1px 7px;margin:2px 3px 0 0;font-size:0.72em;">{r}</span>'
            for r in s["reasons"][:3])
        pb = s["playbook"]
        pos = m["pos_20d"]
        pos_col = "#3fb950" if pos >= 70 else ("#f85149" if pos <= 30 else "#8aa0c0")
        cards += f'''
<div style="background:#0f1623;border:1px solid #1e2d42;border-left:3px solid {sc_col};border-radius:12px;padding:14px;margin-bottom:12px;">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
    <div style="font-size:1.1em;font-weight:900;color:{sc_col};min-width:24px;">{i}</div>
    <div style="flex:1;font-weight:800;font-size:0.96em;">[{s['code']}] {s['name']} {_mark(s['cat_appeal'])}</div>
    <div style="text-align:right;">
      <div style="font-size:0.64em;color:#7a8fa8;">今日動く度</div>
      <div style="font-weight:900;color:{sc_col};font-size:1.05em;">{s['score']:.0f}</div>
    </div>
  </div>
  <div style="margin-bottom:8px;">{reasons}</div>
  <div style="display:flex;flex-wrap:wrap;gap:6px 14px;font-size:0.74em;color:#9fb4d4;margin-bottom:8px;">
    <span>📊 値幅 <b style="color:#eaf2ff;">{m['atr_pct']}%</b></span>
    <span>💴 売買代金 <b style="color:#eaf2ff;">{m['turnover']:.0f}億</b></span>
    <span>📈 出来高 <b style="color:#eaf2ff;">{m['vol_ratio']}x</b></span>
    <span>📍 20日内位置 <b style="color:{pos_col};">{pos:.0f}%</b></span>
  </div>
  <div style="display:flex;flex-wrap:wrap;gap:4px 12px;font-size:0.72em;color:#7a8fa8;background:#0d1117;border-radius:7px;padding:7px 10px;margin-bottom:8px;">
    <span>前日高 <b style="color:#3fb950;">{m['prev_high']:,}</b></span>
    <span>前日安 <b style="color:#f85149;">{m['prev_low']:,}</b></span>
    <span>ピボット <b style="color:#dde8ff;">{m['pivot']:,}</b></span>
    <span>R1 <b style="color:#3fb950;">{m['r1']:,}</b></span>
    <span>S1 <b style="color:#f85149;">{m['s1']:,}</b></span>
  </div>
  <div style="font-size:0.76em;line-height:1.7;color:#cdd9ec;">
    <div>🎯 <b>買い場</b>：{pb['long_trigger']}</div>
    <div>💰 <b>利確</b>：{pb['target']}</div>
    <div>🛑 <b>損切り</b>：{pb['stop']}</div>
    <div style="color:#8aa0c0;margin-top:3px;">👀 {pb['eyes']}</div>
  </div>
</div>'''
    return f'''
<div style="background:#0d1117;border:1px solid #1e2d42;border-radius:14px;padding:16px;">
  <div style="font-size:0.75em;color:#7a8fa8;margin-bottom:12px;">
    材料・夜間ADR・ボラティリティ・出来高・売買代金を統合し、今日デイトレで動きやすい銘柄を
    {result['universe_size']}銘柄から抽出（上位{len(result['top'])}）。各銘柄に重要価格レベルと、場が開いてからの確認ルールを付けています。
    <b style="color:#9fb4d4;">板・VWAP・歩み値はリアルタイム情報なので、寄り後にご自身の目で確認を。</b>
  </div>
  {cards}
  <div style="font-size:0.68em;color:#5a6b82;margin-top:4px;">
    🟢材料の妙味 高 ／ 🟡中 ／ ⚪低　・　「今日動く度」はボラ・流動性・材料・夜間の動きの合成スコア　※AIの事前シナリオで、株価を保証しません
  </div>
</div>'''


if __name__ == "__main__":
    r = run()
    out = []
    if r.get("available"):
        out.append(f"=== 本日のデイトレ注目銘柄（{r['count']}/{r['universe_size']}抽出）===\n")
        for i, s in enumerate(r["top"], 1):
            m = s["metrics"]
            out.append(f"{i}. [{s['code']}] {s['name']} — {s['score']:.0f}点 {s['cat_appeal']}")
            out.append(f"   値幅{m['atr_pct']}% 売買代金{m['turnover']:.0f}億 出来高{m['vol_ratio']}x 20日内位置{m['pos_20d']:.0f}%")
            out.append(f"   理由: {'／'.join(s['reasons']) if s['reasons'] else 'ボラ・流動性'}")
            out.append(f"   🎯買い場: {s['playbook']['long_trigger']}")
            out.append(f"   🛑損切り: {s['playbook']['stop']}")
            out.append("")
    else:
        out.append(f"抽出なし: {r.get('reason','')}")
    text = "\n".join(out)
    try:
        print(text)
    except UnicodeEncodeError:
        with open("dts_output.txt", "w", encoding="utf-8") as f:
            f.write(text)
        print("dts_output.txt に保存しました")
