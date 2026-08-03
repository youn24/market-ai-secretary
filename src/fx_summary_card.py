"""
src/fx_summary_card.py — ミセスワタナベFX 統合サマリーカード（HTML→PNG / Playwright）

FX午後レポートを「1通で完結する1枚」に集約したカード。
  ドル円ヒーロー / 週足×日足マルチタイムフレーム / クロス円 / テクニカル
  / マクロ環境 / 投機筋ポジション・介入警戒 / 地政学リスク / 主要価格ボード
  / Gemini AI解説

Playwright が無い環境では None を返す（呼び出し側でスキップ）。
"""
import traceback
from datetime import datetime, timedelta, timezone

from src.utils import setup_logger, get_dirs

logger = setup_logger("fx_summary_card")

JST = timezone(timedelta(hours=9))
CARD_W = 760
_WD = ["月", "火", "水", "木", "金", "土", "日"]

# パレット（ミセスワタナベ＝ダーク×ゴールド基調）
GOLD  = "#e8c474"
GREEN = "#21d07a"
RED   = "#ff5470"
CYAN  = "#5bc0ff"
AMBER = "#ffc857"
MUTE  = "#9aa6b6"
TEXT  = "#f4f1e8"


def _g(data, sym, key="latest", d=None):
    return (data.get(sym) or {}).get(key, d)


def _verdict(uj_chg, vix):
    """ドル円の前日比とVIXから簡易判定"""
    if vix is not None and vix >= 25:
        return RED, "リスク警戒", "変動が大きく、慎重に見たい局面"
    if uj_chg is None:
        return AMBER, "様子見", "方向感を見極めたい場面"
    if uj_chg >= 0.6:
        return GREEN, "円安進行", "ドル買い・円売りが優勢"
    if uj_chg <= -0.6:
        return CYAN, "円高進行", "円買い戻しが優勢"
    return AMBER, "もみ合い", "大きな方向感は出ていない"


# ── 週足×日足 マルチタイムフレーム（精度向上） ─────────────────────────
def _weekly_trend() -> dict:
    """ドル円の週足トレンド（大きな流れ）を取得"""
    try:
        from src.setup_scanner import _weekly_trend as wk
        return wk("USDJPY=X")
    except Exception:
        logger.debug(traceback.format_exc())
        return {"available": False, "trend": "unknown", "label": ""}


def _mtf_verdict(weekly: dict, uj_chg) -> tuple:
    """週足の流れと当日の方向が一致しているかを判定"""
    t = (weekly or {}).get("trend", "unknown")
    if t == "unknown" or uj_chg is None:
        return MUTE, "", ""
    day_up = uj_chg >= 0
    if t == "up":
        return ((GREEN, "◎ 大きな流れと一致", "週足も上昇 — 円安方向に素直な地合い") if day_up
                else (AMBER, "△ 大きな流れに逆行", "週足は上昇 — 今日の円高は一時的な調整の可能性"))
    if t == "down":
        return ((AMBER, "△ 大きな流れに逆行", "週足は下降 — 今日の円安は戻りの可能性") if day_up
                else (GREEN, "◎ 大きな流れと一致", "週足も下降 — 円高方向に素直な地合い"))
    return (CYAN, "○ 週足はレンジ", "大きな方向感は乏しく、短期の値動き中心")


# ── テクニカル（RSI / MACD） ────────────────────────────────────────
def _technicals(data: dict) -> dict:
    """ドル円のRSI・MACDを日足データから算出"""
    out = {"rsi": None, "rsi_label": "", "rsi_color": MUTE, "macd": ""}
    try:
        df = (data.get("USDJPY=X") or {}).get("df")
        if df is None or "Close" not in df:
            return out
        from src.fx_visual_report import calc_rsi, calc_macd
        close = df["Close"]

        r = calc_rsi(close)
        if len(r) > 0:
            rsi = float(r.iloc[-1])
            out["rsi"] = rsi
            if rsi >= 70:
                out["rsi_label"], out["rsi_color"] = "買われすぎ", RED
            elif rsi <= 30:
                out["rsi_label"], out["rsi_color"] = "売られすぎ", GREEN
            else:
                out["rsi_label"], out["rsi_color"] = "中立", AMBER

        _, _, hist = calc_macd(close)
        if len(hist) >= 2:
            lh, ph = float(hist.iloc[-1]), float(hist.iloc[-2])
            if ph < 0 <= lh:
                out["macd"] = "▲ ゴールデンクロス発生"
            elif ph > 0 >= lh:
                out["macd"] = "▼ デッドクロス発生"
            elif lh > 0:
                out["macd"] = "↑ 上昇の勢いが継続"
            else:
                out["macd"] = "↓ 下落の勢いが継続"
    except Exception:
        logger.debug(traceback.format_exc())
    return out


# ── 投機筋ポジション（CFTC IMM） ────────────────────────────────────
def _imm(premium: dict) -> dict:
    """IMM円ポジション（千枚）と水準判定"""
    cftc = (premium or {}).get("cftc_jpy", {}) or {}
    if not cftc.get("dates"):
        return {}
    try:
        net_k = cftc["latest_net"] / 1000
        prev  = (cftc["net"][-2] / 1000) if len(cftc.get("net", [])) >= 2 else None
        chg   = (net_k - prev) if prev is not None else None
        if net_k < -100:   label, color = "極端な円売り越し（介入リスク増）", RED
        elif net_k < -70:  label, color = "大幅な円売り越し（警戒水準）",     AMBER
        elif net_k < -40:  label, color = "円売り越し（注意）",               AMBER
        elif net_k < 0:    label, color = "小幅な円売り越し",                 MUTE
        elif net_k < 40:   label, color = "小幅な円買い越し",                 CYAN
        else:              label, color = "大幅な円買い越し（円高圧力）",     GREEN
        return {"net_k": net_k, "chg": chg, "label": label, "color": color,
                "date": cftc.get("latest_date", "")}
    except Exception:
        logger.debug(traceback.format_exc())
        return {}


def _intervention(uj, uj_chg=None) -> dict:
    """
    為替介入の警戒度。
    cb_monitor は「ドル円の水準」だけで判定するが、円買い介入は
    “円安が急に進んだとき”に行われる。当日の方向を加味して補正する
    （円高が進んだ日は警戒後退、円安が進んだ日は警戒強まる）。
    """
    try:
        from src.cb_monitor import calc_intervention_risk
        r = dict(calc_intervention_risk(uj) or {})
    except Exception:
        logger.debug(traceback.format_exc())
        return {}
    if not r:
        return {}

    r["dir_note"] = ""
    if uj_chg is not None and r.get("score", 0) >= 30:
        if uj_chg <= -0.8:
            r["score"] = max(0, r["score"] - 25)
            r["dir_note"] = f"本日は円高方向（{uj_chg:+.2f}%）→ 介入警戒は後退"
        elif uj_chg >= 0.8:
            r["score"] = min(100, r["score"] + 15)
            r["dir_note"] = f"本日は円安方向（{uj_chg:+.2f}%）→ 介入警戒が強まる"
    return r


def _jp10y(fred: dict):
    """
    日本10年金利。FRED一括取得が漏れた場合でも単発で取り直す。
    （日米金利差はドル円の最重要ドライバーなので欠損させない）
    """
    v = (fred or {}).get("IRLTLT01JPM156N", {}).get("value")
    if v is not None:
        return float(v)
    try:
        import io as _io
        import requests
        import pandas as pd
        r = requests.get(
            "https://fred.stlouisfed.org/graph/fredgraph.csv?id=IRLTLT01JPM156N",
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        if r.status_code != 200:
            return None
        df = pd.read_csv(_io.StringIO(r.text), na_values=".")
        df.columns = ["date", "value"]
        df = df.dropna()
        if df.empty:
            return None
        logger.info("日本10年金利をFREDから個別取得（一括取得の欠損を補完）")
        return float(df["value"].iloc[-1])
    except Exception:
        logger.debug(traceback.format_exc())
        return None


# ── 表示パーツ ──────────────────────────────────────────────────────
def _rate_row(data, sym, label, flag):
    v   = _g(data, sym, "latest")
    chg = _g(data, sym, "chg") or 0
    if v is None:
        return f'<div class="rrow"><span class="rlbl">{flag} {label}</span><span class="rval">—</span></div>'
    c = GREEN if chg >= 0 else RED
    arr = "▲" if chg >= 0 else "▼"
    return (f'<div class="rrow"><span class="rlbl">{flag} {label}</span>'
            f'<span class="rnum">{v:,.2f}<span class="runit">円</span>'
            f'<span class="rchg" style="color:{c}">{arr}{abs(chg):.2f}%</span></span></div>')


_BOARD = [
    ("GC=F",   "🥇 金",         "${:,.0f}"),
    ("CL=F",   "🛢 原油",       "${:.1f}"),
    ("^TNX",   "🇺🇸 米10年金利", "{:.2f}%"),
    ("^VIX",   "⚡ VIX",        "{:.1f}"),
    ("^GSPC",  "📈 S&P500",     "{:,.0f}"),
    ("^N225",  "🗾 日経225",    "{:,.0f}"),
]


def _board_html(data: dict) -> str:
    cells = []
    for sym, label, fmt in _BOARD:
        v   = _g(data, sym, "latest")
        chg = _g(data, sym, "chg")
        if v is None:
            continue
        c = GREEN if (chg or 0) >= 0 else RED
        chg_s = f"{chg:+.2f}%" if chg is not None else "—"
        cells.append(f"""<div class="bcell">
        <div class="blbl">{label}</div>
        <div class="num bval">{fmt.format(v)}</div>
        <div class="bchg" style="color:{c}">{chg_s}</div>
      </div>""")
    if not cells:
        return ""
    return f"""
  <div class="panel">
    <div class="ptitle">💹 主要マーケット（東京14時）</div>
    <div class="bgrid">{"".join(cells)}</div>
  </div>"""


def _build_html(data: dict, premium: dict, ai_comment: str = "") -> str:
    n = datetime.now(JST)
    date_s = f"{n.year}年{n.month}月{n.day}日（{_WD[n.weekday()]}）"
    time_s = f"{n.strftime('%H:%M')} JST"

    uj     = _g(data, "USDJPY=X", "latest")
    uj_chg = _g(data, "USDJPY=X", "chg") or 0
    vix    = _g(data, "^VIX", "latest")
    v_c, v_label, v_sub = _verdict(uj_chg, vix)
    uj_c   = GREEN if uj_chg >= 0 else RED
    uj_arr = "▲" if uj_chg >= 0 else "▼"
    uj_s   = f"{uj:,.2f}" if uj is not None else "—"

    # ── 週足×日足 ──
    weekly = _weekly_trend()
    mtf_c, mtf_label, mtf_note = _mtf_verdict(weekly, uj_chg)
    mtf_html = ""
    if mtf_label:
        mtf_html = f"""
  <div class="mtf" style="border-color:{mtf_c}44;background:{mtf_c}10">
    <div class="mtf-l">
      <span class="mtf-badge" style="color:{mtf_c};border-color:{mtf_c}66;background:{mtf_c}18">{mtf_label}</span>
      <span class="mtf-wk">{weekly.get('label','')}</span>
    </div>
    <div class="mtf-note">{mtf_note}</div>
  </div>"""

    # ── テクニカル ──
    tech = _technicals(data)
    tech_html = ""
    if tech.get("rsi") is not None or tech.get("macd"):
        rows = []
        if tech.get("rsi") is not None:
            rsi_pct = max(0, min(100, tech["rsi"]))
            rows.append(f"""<div class="mchip">
        <span class="mk">RSI（買われすぎ・売られすぎ）</span>
        <span class="mv" style="color:{tech['rsi_color']}">{tech['rsi']:.0f}<small>{tech['rsi_label']}</small></span>
      </div>
      <div class="rsibar"><div class="rsifill" style="width:{rsi_pct:.0f}%;background:{tech['rsi_color']}"></div></div>""")
        if tech.get("macd"):
            rows.append(f'<div class="mchip"><span class="mk">MACD（勢い）</span><span class="mv">{tech["macd"]}</span></div>')
        tech_html = f"""
  <div class="panel">
    <div class="ptitle">📐 ドル円テクニカル</div>
    <div class="mgrid">{"".join(rows)}</div>
  </div>"""

    # ── マクロ ──
    fred = (premium or {}).get("fred", {}) or {}
    fw   = (premium or {}).get("fedwatch", {}) or {}
    ffr  = fred.get("FEDFUNDS", {}).get("value") or fw.get("current_ffr")
    cutp = (fw.get("cut_prob", [None]) or [None])[0]
    jp10 = _jp10y(fred)          # 欠損時は個別に取り直す
    us10 = _g(data, "^TNX", "latest")
    diff = (us10 - jp10) if (us10 is not None and jp10 is not None) else None
    hy   = fred.get("BAMLH0A0HYM2", {}).get("value")

    macro_chips = ""
    if ffr is not None:
        cut_s = f"（次回利下げ {cutp:.0f}%）" if cutp is not None else ""
        macro_chips += f'<div class="mchip"><span class="mk">米政策金利</span><span class="mv">{ffr:.2f}%<small>{cut_s}</small></span></div>'
    if diff is not None:
        ds = "円安圧力" if diff >= 3.0 else "中立圏" if diff >= 2.0 else "円高圧力"
        dc = RED if diff >= 3.0 else AMBER if diff >= 2.0 else GREEN
        macro_chips += f'<div class="mchip"><span class="mk">日米金利差</span><span class="mv" style="color:{dc}">{diff:.2f}%<small>（{ds}）</small></span></div>'
    if vix is not None:
        vc = GREEN if vix < 20 else AMBER if vix < 25 else RED
        vt = "安定" if vix < 20 else "警戒" if vix < 25 else "危険"
        macro_chips += f'<div class="mchip"><span class="mk">恐怖指数VIX</span><span class="mv" style="color:{vc}">{vix:.1f} {vt}</span></div>'
    if hy is not None:
        hc = GREEN if hy < 3.5 else AMBER if hy < 5 else RED
        macro_chips += f'<div class="mchip"><span class="mk">信用スプレッド</span><span class="mv" style="color:{hc}">{hy:.2f}%</span></div>'

    # ── 投機筋・介入 ──
    imm = _imm(premium)
    itv = _intervention(uj, uj_chg)
    pos_rows = ""
    if imm:
        chg_s = f"<small>前週比 {imm['chg']:+.0f}千枚</small>" if imm.get("chg") is not None else ""
        pos_rows += (f'<div class="mchip"><span class="mk">IMM投機筋の円</span>'
                     f'<span class="mv" style="color:{imm["color"]}">{imm["net_k"]:+,.0f}<small>千枚</small>{chg_s}</span></div>'
                     f'<div class="subnote">{imm["label"]}</div>')
    if itv:
        sc = itv.get("score", 0)
        ic = GREEN if sc < 30 else AMBER if sc < 60 else RED
        pos_rows += (f'<div class="mchip"><span class="mk">為替介入の警戒度</span>'
                     f'<span class="mv" style="color:{ic}">{itv.get("level","")}</span></div>')
        if itv.get("dir_note"):
            pos_rows += f'<div class="subnote" style="color:{ic}">{itv["dir_note"]}</div>'
        if itv.get("history_ref"):
            pos_rows += f'<div class="subnote">{itv["history_ref"]}</div>'
    pos_html = f"""
  <div class="panel">
    <div class="ptitle">📡 投機筋ポジション & 介入監視</div>
    <div class="mgrid">{pos_rows}</div>
  </div>""" if pos_rows else ""

    # ── 地政学 ──
    geo_html = ""
    try:
        from src.macro_geopolitics import calc_geopolitical_risk
        gr = calc_geopolitical_risk(data)
        gscore = gr.get("score", 0)
        gc = GREEN if gscore < 34 else AMBER if gscore < 67 else RED
        facs = "".join(f"<li>{f}</li>" for f in (gr.get("factors") or [])[:2])
        geo_html = f"""
  <div class="panel">
    <div class="ptitle">🌍 地政学リスク</div>
    <div class="georow">
      <div class="gscore" style="color:{gc}">{gscore}<small>/100</small></div>
      <div class="gmeta">
        <div class="glevel" style="color:{gc}">{gr.get('level','')}</div>
        <ul class="gfac">{facs}</ul>
      </div>
    </div>
  </div>"""
    except Exception:
        logger.debug(traceback.format_exc())

    ai_html = f"""
  <div class="panel">
    <div class="ptitle">🤖 AI市場解説（Gemini）</div>
    <div class="aitxt">{ai_comment}</div>
  </div>""" if ai_comment else ""

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700;900&family=Outfit:wght@500;700;800;900&display=swap" rel="stylesheet">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Noto Sans JP','Outfit',sans-serif}}
.num{{font-family:'Outfit','Noto Sans JP',sans-serif;font-variant-numeric:tabular-nums;letter-spacing:-.5px}}
#card{{position:relative;width:{CARD_W}px;padding:26px 24px 20px;overflow:hidden;color:{TEXT};
  background:
    radial-gradient(60% 38% at 12% 0%, rgba(232,196,116,.16), transparent 60%),
    radial-gradient(55% 40% at 100% 18%, rgba(91,192,255,.12), transparent 60%),
    radial-gradient(70% 45% at 70% 112%, rgba(232,196,116,.07), transparent 60%),
    linear-gradient(165deg,#11141d 0%,#0b0e16 55%,#07090f 100%)}}
.head{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:18px}}
.brand{{display:flex;align-items:center;gap:12px}}
.logo{{width:42px;height:42px;border-radius:12px;display:grid;place-items:center;font-size:21px;
  background:linear-gradient(135deg,#e8c474,#b8893c);box-shadow:0 6px 18px rgba(232,196,116,.30);color:#11141d}}
.bname{{font-family:'Outfit','Noto Sans JP';font-size:22px;font-weight:900;line-height:1.05}}
.bsub{{font-size:12px;color:{GOLD};font-weight:700;letter-spacing:.12em;margin-top:2px}}
.dt{{text-align:right;font-size:13px;color:{MUTE};font-weight:600;line-height:1.5}}

.hero{{display:grid;grid-template-columns:1.15fr 1fr;gap:13px;margin-bottom:11px}}
.card{{background:linear-gradient(160deg,rgba(255,255,255,.06),rgba(255,255,255,.02));
  border:1px solid rgba(255,255,255,.10);border-radius:17px;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.06),0 8px 26px rgba(0,0,0,.35)}}
.uj{{padding:17px 19px;position:relative;overflow:hidden;border-color:{uj_c}40}}
.uj::after{{content:"";position:absolute;top:-30px;right:-30px;width:130px;height:130px;border-radius:50%;
  background:radial-gradient(circle,{uj_c}30,transparent 70%)}}
.lbl{{font-size:11px;font-weight:700;letter-spacing:1.4px;color:{MUTE};text-transform:uppercase}}
.uj-big{{font-family:'Outfit','Noto Sans JP';font-size:46px;font-weight:900;line-height:1.02;margin-top:3px;font-variant-numeric:tabular-nums;letter-spacing:-1px}}
.uj-unit{{font-size:22px;font-weight:800;color:{MUTE};margin-left:3px}}
.uj-chg{{font-size:16px;font-weight:800;color:{uj_c};margin-top:4px}}
.verd{{padding:17px;display:flex;flex-direction:column;justify-content:center;border-color:{v_c}40}}
.verd-v{{font-family:'Outfit','Noto Sans JP';font-size:30px;font-weight:900;color:{v_c};line-height:1.1;margin-top:4px}}
.verd-s{{font-size:12.5px;color:{MUTE};margin-top:6px;line-height:1.5}}

.mtf{{border:1px solid;border-radius:14px;padding:12px 16px;margin-bottom:11px}}
.mtf-l{{display:flex;align-items:center;gap:11px;flex-wrap:wrap}}
.mtf-badge{{font-size:12.5px;font-weight:800;border:1px solid;border-radius:11px;padding:3px 11px}}
.mtf-wk{{font-size:13px;font-weight:700;color:{TEXT}}}
.mtf-note{{font-size:12.5px;color:{MUTE};margin-top:6px;line-height:1.6}}

.rates{{padding:6px 19px 8px;margin-bottom:11px}}
.rrow{{display:flex;justify-content:space-between;align-items:center;padding:11px 0;border-bottom:1px solid rgba(255,255,255,.07)}}
.rrow:last-child{{border-bottom:none}}
.rlbl{{font-size:14px;color:#d8d2c4;font-weight:600}}
.rnum{{font-family:'Outfit','Noto Sans JP';font-size:19px;font-weight:800;font-variant-numeric:tabular-nums}}
.runit{{font-size:13px;color:{MUTE};margin-left:1px}}
.rchg{{font-size:13px;font-weight:800;margin-left:10px}}

.panel{{background:linear-gradient(160deg,rgba(255,255,255,.05),rgba(255,255,255,.018));
  border:1px solid rgba(255,255,255,.09);border-radius:16px;padding:15px 18px;margin-bottom:11px;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.05)}}
.ptitle{{font-size:14px;font-weight:800;margin-bottom:13px;display:flex;align-items:center;gap:7px}}
.ptitle::before{{content:"";width:4px;height:15px;border-radius:3px;background:linear-gradient(180deg,{GOLD},#b8893c)}}
.mgrid{{display:flex;flex-direction:column;gap:10px}}
.mchip{{display:flex;justify-content:space-between;align-items:center;gap:12px}}
.mk{{font-size:13.5px;color:{MUTE};font-weight:600}}
.mv{{font-family:'Outfit','Noto Sans JP';font-size:16px;font-weight:800;text-align:right}}
.mv small{{font-size:12px;color:{MUTE};font-weight:600;margin-left:5px}}
.subnote{{font-size:12px;color:{MUTE};line-height:1.6;margin-top:-4px}}
.rsibar{{height:6px;border-radius:4px;background:rgba(255,255,255,.08);overflow:hidden;margin-top:-4px}}
.rsifill{{height:100%;border-radius:4px}}

.bgrid{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px}}
.bcell{{background:rgba(255,255,255,.035);border:1px solid rgba(255,255,255,.07);border-radius:11px;padding:9px 10px}}
.blbl{{font-size:11.5px;color:{MUTE};font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.bval{{font-size:17px;font-weight:800;margin-top:3px}}
.bchg{{font-size:11.5px;font-weight:800;margin-top:1px}}

.georow{{display:flex;align-items:center;gap:18px}}
.gscore{{font-family:'Outfit';font-size:42px;font-weight:900;line-height:1}}
.gscore small{{font-size:15px;color:{MUTE}}}
.glevel{{font-size:15px;font-weight:800;margin-bottom:5px}}
.gfac{{list-style:none}}
.gfac li{{font-size:12.5px;color:#c4bfae;padding-left:14px;position:relative;line-height:1.6}}
.gfac li::before{{content:"•";position:absolute;left:0;color:{GOLD}}}

.aitxt{{font-size:13.5px;line-height:1.85;color:#e8e3d6}}
.foot{{text-align:center;font-size:11px;color:#6b6759;margin-top:6px;letter-spacing:.04em}}
</style></head><body>
<div id="card">
  <div class="head">
    <div class="brand">
      <div class="logo">〽️</div>
      <div><div class="bname">ミセスワタナベ FX</div><div class="bsub">為替マーケット速報</div></div>
    </div>
    <div class="dt">{date_s}<br>{time_s} ─ 東京市場</div>
  </div>

  <div class="hero">
    <div class="card uj">
      <div class="lbl">ドル円 USD/JPY</div>
      <div class="num uj-big">{uj_s}<span class="uj-unit">円</span></div>
      <div class="uj-chg">{uj_arr} 前日比 {abs(uj_chg):.2f}%</div>
    </div>
    <div class="card verd">
      <div class="lbl">本日の見立て</div>
      <div class="verd-v">{v_label}</div>
      <div class="verd-s">{v_sub}</div>
    </div>
  </div>
  {mtf_html}

  <div class="card rates">
    {_rate_row(data, "EURJPY=X", "ユーロ円", "🇪🇺")}
    {_rate_row(data, "GBPJPY=X", "ポンド円", "🇬🇧")}
    {_rate_row(data, "AUDJPY=X", "豪ドル円", "🇦🇺")}
  </div>
  {tech_html}

  <div class="panel">
    <div class="ptitle">📊 マクロ & 市場環境</div>
    <div class="mgrid">{macro_chips or '<div class="mk">データ取得中…</div>'}</div>
  </div>
  {pos_html}
  {geo_html}
  {_board_html(data)}
  {ai_html}

  <div class="foot">youn24.github.io/market-ai-secretary　|　毎日 14:00 JST 自動配信</div>
</div>
</body></html>"""


def build_caption(data: dict, premium: dict, ai_comment: str = "") -> str:
    """
    1通に集約したときの画像キャプション（Telegram上限1024字）。
    カードで見えない/読み取りにくい要点だけを文字で補う。
    """
    n = datetime.now(JST)
    uj     = _g(data, "USDJPY=X", "latest")
    uj_chg = _g(data, "USDJPY=X", "chg") or 0
    vix    = _g(data, "^VIX", "latest")
    _, v_label, _ = _verdict(uj_chg, vix)
    arr = "▲" if uj_chg >= 0 else "▼"
    uj_s = f"{uj:,.2f}円" if uj is not None else "—"

    lines = [
        f"〽️ *ミセスワタナベ FX* — {n.month}/{n.day}（{_WD[n.weekday()]}）{n.strftime('%H:%M')} JST",
        "━━━━━━━━━━━━━━",
        f"💵 *ドル円 {uj_s}*  {arr}{abs(uj_chg):.2f}%　→ *{v_label}*",
    ]

    weekly = _weekly_trend()
    _, mtf_label, mtf_note = _mtf_verdict(weekly, uj_chg)
    if mtf_label:
        lines.append(f"📈 {weekly.get('label','')}　{mtf_label}")
        if mtf_note:
            lines.append(f"　{mtf_note}")

    # 介入警戒（方向補正後のスコアが高いときだけ強調）
    itv = _intervention(uj, uj_chg)
    if itv and itv.get("score", 0) >= 40:
        lines.append(f"🚨 介入警戒: {itv.get('level','')}")
        if itv.get("dir_note"):
            lines.append(f"　{itv['dir_note']}")

    if ai_comment:
        lines += ["", f"🤖 {ai_comment[:280]}"]

    lines += ["", "👇 詳細チャート13面・イールドカーブ・通貨強弱はレポートへ"]

    text = "\n".join(lines)
    return text[:1024]


def make_fx_card(data: dict, premium: dict = None, ai_comment: str = "",
                 out_path: str = None) -> str | None:
    """FXサマリーカードPNGを生成してパスを返す。Playwright不可なら None。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("playwright 未インストール → FXカードはスキップ")
        return None

    try:
        if out_path is None:
            d = datetime.now(JST).strftime("%Y-%m-%d")
            out_path = str(get_dirs()["charts"] / f"fx_card_{d}.png")
        html = _build_html(data or {}, premium or {}, ai_comment or "")
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox"])
            page = browser.new_page(
                viewport={"width": CARD_W, "height": 1400},
                device_scale_factor=2,
            )
            page.set_content(html, wait_until="networkidle")
            page.locator("#card").screenshot(path=out_path)
            browser.close()
        logger.info(f"✅ FXサマリーカード生成（HTML→PNG）: {out_path}")
        return out_path
    except Exception as e:
        logger.warning(f"FXカード生成失敗（スキップ）: {e}")
        logger.debug(traceback.format_exc())
        return None
