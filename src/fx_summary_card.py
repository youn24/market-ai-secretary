"""
src/fx_summary_card.py — FX サマリーカード（HTML→PNG / Playwright）
ミセスワタナベ FX の「一目でわかる」Canva級カードを生成する。
主要レート＋マクロ＋地政学リスク＋AI解説を1枚に集約。
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

    # マクロ
    fred = (premium or {}).get("fred", {}) or {}
    fw   = (premium or {}).get("fedwatch", {}) or {}
    ffr  = fred.get("FEDFUNDS", {}).get("value") or fw.get("current_ffr")
    cutp = (fw.get("cut_prob", [None]) or [None])[0]
    jp10 = fred.get("IRLTLT01JPM156N", {}).get("value")
    us10 = _g(data, "^TNX", "latest")
    diff = (us10 - jp10) if (us10 is not None and jp10 is not None) else None

    macro_chips = ""
    if ffr is not None:
        cut_s = f"（利下げ {cutp:.0f}%）" if cutp is not None else ""
        macro_chips += f'<div class="mchip"><span class="mk">米政策金利</span><span class="mv">{ffr:.2f}%<small>{cut_s}</small></span></div>'
    if diff is not None:
        ds = "円安圧力" if diff >= 3.0 else "中立圏" if diff >= 2.0 else "円高圧力"
        macro_chips += f'<div class="mchip"><span class="mk">日米金利差</span><span class="mv">{diff:.2f}%<small>（{ds}）</small></span></div>'
    if vix is not None:
        vc = GREEN if vix < 20 else AMBER if vix < 25 else RED
        vt = "安定" if vix < 20 else "警戒" if vix < 25 else "危険"
        macro_chips += f'<div class="mchip"><span class="mk">恐怖指数VIX</span><span class="mv" style="color:{vc}">{vix:.1f} {vt}</span></div>'

    # 地政学
    geo_html = ""
    try:
        from src.macro_geopolitics import calc_geopolitical_risk
        gr = calc_geopolitical_risk(data)
        gscore = gr.get("score", 0)
        gc = GREEN if gscore < 34 else AMBER if gscore < 67 else RED
        facs = "".join(f'<li>{f}</li>' for f in (gr.get("factors") or [])[:2])
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

    ai_html = ""
    if ai_comment:
        ai_html = f"""
      <div class="panel">
        <div class="ptitle">🤖 AI市場解説（Gemini）</div>
        <div class="aitxt">{ai_comment}</div>
      </div>"""

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700;900&family=Outfit:wght@500;700;800;900&display=swap" rel="stylesheet">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Noto Sans JP','Outfit',sans-serif}}
.num{{font-family:'Outfit','Noto Sans JP',sans-serif;font-variant-numeric:tabular-nums;letter-spacing:-.5px}}
#card{{position:relative;width:{CARD_W}px;padding:26px 24px 20px;overflow:hidden;color:#f4f1e8;
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

.hero{{display:grid;grid-template-columns:1.15fr 1fr;gap:13px;margin-bottom:13px}}
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
.verd{{padding:17px 17px;display:flex;flex-direction:column;justify-content:center;border-color:{v_c}40}}
.verd-v{{font-family:'Outfit','Noto Sans JP';font-size:30px;font-weight:900;color:{v_c};line-height:1.1;margin-top:4px}}
.verd-s{{font-size:12.5px;color:{MUTE};margin-top:6px;line-height:1.5}}

.rates{{padding:6px 19px 8px}}
.rrow{{display:flex;justify-content:space-between;align-items:center;padding:11px 0;border-bottom:1px solid rgba(255,255,255,.07)}}
.rrow:last-child{{border-bottom:none}}
.rlbl{{font-size:14px;color:#d8d2c4;font-weight:600}}
.rnum{{font-family:'Outfit','Noto Sans JP';font-size:19px;font-weight:800;font-variant-numeric:tabular-nums}}
.runit{{font-size:13px;color:{MUTE};margin-left:1px}}
.rchg{{font-size:13px;font-weight:800;margin-left:10px}}

.panel{{background:linear-gradient(160deg,rgba(255,255,255,.05),rgba(255,255,255,.018));
  border:1px solid rgba(255,255,255,.09);border-radius:16px;padding:15px 18px;margin-bottom:12px;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.05)}}
.ptitle{{font-size:14px;font-weight:800;margin-bottom:13px;display:flex;align-items:center;gap:7px}}
.ptitle::before{{content:"";width:4px;height:15px;border-radius:3px;background:linear-gradient(180deg,{GOLD},#b8893c)}}
.mgrid{{display:flex;flex-direction:column;gap:10px}}
.mchip{{display:flex;justify-content:space-between;align-items:center}}
.mk{{font-size:13.5px;color:{MUTE};font-weight:600}}
.mv{{font-family:'Outfit','Noto Sans JP';font-size:16px;font-weight:800}}
.mv small{{font-size:12px;color:{MUTE};font-weight:600;margin-left:4px}}

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
      <div class="num uj-big">{uj:,.2f}<span class="uj-unit">円</span></div>
      <div class="uj-chg">{uj_arr} 前日比 {abs(uj_chg):.2f}%</div>
    </div>
    <div class="card verd">
      <div class="lbl">本日の見立て</div>
      <div class="verd-v">{v_label}</div>
      <div class="verd-s">{v_sub}</div>
    </div>
  </div>

  <div class="card rates">
    {_rate_row(data, "EURJPY=X", "ユーロ円", "🇪🇺")}
    {_rate_row(data, "GBPJPY=X", "ポンド円", "🇬🇧")}
    {_rate_row(data, "AUDJPY=X", "豪ドル円", "🇦🇺")}
  </div>

  <div class="panel">
    <div class="ptitle">📊 マクロ & 市場環境</div>
    <div class="mgrid">{macro_chips or '<div class="mk">データ取得中…</div>'}</div>
  </div>
  {geo_html}
  {ai_html}

  <div class="foot">youn24.github.io/market-ai-secretary　|　毎日 14:00 JST 自動配信</div>
</div>
</body></html>"""


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
                viewport={"width": CARD_W, "height": 1100},
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
