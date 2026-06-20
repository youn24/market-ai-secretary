"""
src/design_ai.py — ミセスワタナベ 市場ダッシュボード v5
ガネーシャ🐘＆カワウソ🦦キャラクター完全統合版
"""

import traceback
from pathlib import Path
from src.utils import setup_logger, get_jst_now, get_today_str, get_dirs

logger = setup_logger("design_ai")

# ──────────────────────────────────────────
# カラーパレット（ネオン系ダーク）
# ──────────────────────────────────────────
BG      = "#06080f"
CARD    = "rgba(255,255,255,0.04)"
CARD2   = "rgba(255,255,255,0.07)"
BORDER  = "rgba(255,255,255,0.09)"
TEXT    = "#f0f4ff"
MUTED   = "#5a6a85"
GREEN   = "#00ff87"
RED     = "#ff3d5a"
YELLOW  = "#ffc837"
BLUE    = "#00b4ff"
ORANGE  = "#ff7b2c"
PURPLE  = "#b06eff"
CYAN    = "#00e5ff"
PINK    = "#ff4fa8"


# ──────────────────────────────────────────
# 共通ユーティリティ
# ──────────────────────────────────────────

def _p(sym, prices, key="price", fallback=0):
    return (prices.get(sym) or {}).get(key, fallback) or fallback

def _chg(sym, prices):
    return (prices.get(sym) or {}).get("change_pct", 0) or 0

def _col(v):
    if v > 0:  return GREEN
    if v < 0:  return RED
    return MUTED

def _arrow(v):
    if v > 0: return "▲"
    if v < 0: return "▼"
    return "━"

def _fmt(v, dec=2):
    if v == 0: return "—"
    if abs(v) >= 10000: return f"{v:,.0f}"
    if abs(v) >= 1000:  return f"{v:,.0f}"
    return f"{v:,.{dec}f}"

def _score_info(s):
    if s >= 1.5:  return GREEN,  "強気相場",     "#00ff8711", "📈", "BULL"
    if s >= 0.3:  return GREEN,  "やや強気",     "#00ff8708", "📗", "BULL"
    if s >= -0.3: return YELLOW, "中立・様子見", "#ffc83708", "📊", "NEUTRAL"
    if s >= -1.5: return ORANGE, "やや弱気",     "#ff7b2c08", "📉", "BEAR"
    return RED,    "弱気相場",     "#ff3d5a10", "🔴", "BEAR"

def _vix_info(v):
    if v >= 30: return RED,    "極度警戒", "VIXが30超。市場は非常に不安定です。"
    if v >= 22: return ORANGE, "警 戒",   "VIXがやや高い。荒れやすい相場に注意。"
    if v >= 15: return YELLOW, "注 意",   "VIXは普通。大きな動きへの備えを。"
    return GREEN,  "安 定",   "VIXが低く、市場は落ち着いています。"

def _fg_info(s):
    if s >= 75: return "極度の欲望", RED,    "⚠️ 過熱感が強い。調整リスクあり。"
    if s >= 55: return "欲 望",     ORANGE, "強気ムードが優勢。"
    if s >= 45: return "中 立",     YELLOW, "どちらとも言えない状態。"
    if s >= 25: return "恐 怖",     BLUE,   "弱気ムードが漂っています。"
    return "極度の恐怖", PURPLE, "🔥 逆張りの好機になることも。"


# ──────────────────────────────────────────
# キャラクターSVG（ガネーシャ & カワウソ）
# ──────────────────────────────────────────

_GANESHA_SVG = """<svg width="72" height="88" viewBox="0 0 100 120" xmlns="http://www.w3.org/2000/svg">
  <ellipse cx="18" cy="52" rx="17" ry="23" fill="#FFBF00" stroke="#E6A800" stroke-width="1.5"/>
  <ellipse cx="82" cy="52" rx="17" ry="23" fill="#FFBF00" stroke="#E6A800" stroke-width="1.5"/>
  <ellipse cx="18" cy="52" rx="11" ry="16" fill="#FFD6DC" opacity="0.75"/>
  <ellipse cx="82" cy="52" rx="11" ry="16" fill="#FFD6DC" opacity="0.75"/>
  <ellipse cx="50" cy="90" rx="33" ry="28" fill="#FFD700" stroke="#E6A800" stroke-width="2"/>
  <circle cx="50" cy="50" r="29" fill="#FFD700" stroke="#E6A800" stroke-width="2"/>
  <polygon points="28,28 34,12 43,24 50,10 57,24 66,12 72,28" fill="#FFC200" stroke="#E6A800" stroke-width="1.5"/>
  <circle cx="50" cy="17" r="5.5" fill="#E91E63"/>
  <circle cx="34" cy="25" r="3.5" fill="#9C27B0"/>
  <circle cx="66" cy="25" r="3.5" fill="#9C27B0"/>
  <path d="M 43 68 Q 28 82 33 98 Q 38 110 50 106" stroke="#E6A800" stroke-width="9" fill="none" stroke-linecap="round"/>
  <path d="M 43 68 Q 28 82 33 98 Q 38 110 50 106" stroke="#FFD700" stroke-width="5" fill="none" stroke-linecap="round"/>
  <circle cx="40" cy="46" r="5.5" fill="#2C1810"/>
  <circle cx="60" cy="46" r="5.5" fill="#2C1810"/>
  <circle cx="41.5" cy="44" r="2.2" fill="white"/>
  <circle cx="61.5" cy="44" r="2.2" fill="white"/>
  <path d="M 42 62 Q 50 69 58 62" stroke="#C07A00" stroke-width="2.5" fill="none" stroke-linecap="round"/>
  <path d="M50 83 C50 83 44 77 40 79.5 C36 82 36 87 40 90 L50 98 L60 90 C64 87 64 82 60 79.5 C56 77 50 83 50 83Z" fill="#E91E63"/>
  <circle cx="34" cy="92" r="4" fill="#FFA500" stroke="#E6A800" stroke-width="1"/>
  <circle cx="66" cy="92" r="4" fill="#FFA500" stroke="#E6A800" stroke-width="1"/>
  <rect x="36" y="102" width="28" height="5" rx="2.5" fill="#FFA500" stroke="#E6A800" stroke-width="1"/>
  <ellipse cx="22" cy="92" rx="11" ry="9" fill="#FFD700" stroke="#E6A800" stroke-width="1.5"/>
  <ellipse cx="78" cy="92" rx="11" ry="9" fill="#FFD700" stroke="#E6A800" stroke-width="1.5"/>
</svg>"""

_OTTER_SVG = """<svg width="72" height="88" viewBox="0 0 100 120" xmlns="http://www.w3.org/2000/svg">
  <path d="M72 105 Q90 98 88 112 Q85 120 75 116" stroke="#7A5230" stroke-width="9" fill="none" stroke-linecap="round"/>
  <path d="M72 105 Q90 98 88 112 Q85 120 75 116" stroke="#8B6340" stroke-width="5" fill="none" stroke-linecap="round"/>
  <ellipse cx="50" cy="88" rx="31" ry="29" fill="#8B6340"/>
  <ellipse cx="50" cy="92" rx="21" ry="21" fill="#F5E6D3"/>
  <circle cx="50" cy="50" r="27" fill="#8B6340"/>
  <circle cx="25" cy="29" r="11" fill="#8B6340"/>
  <circle cx="75" cy="29" r="11" fill="#8B6340"/>
  <circle cx="25" cy="29" r="7" fill="#C4956A"/>
  <circle cx="75" cy="29" r="7" fill="#C4956A"/>
  <ellipse cx="50" cy="56" rx="19" ry="16" fill="#F5E6D3"/>
  <circle cx="41" cy="47" r="6.5" fill="#2C1810"/>
  <circle cx="59" cy="47" r="6.5" fill="#2C1810"/>
  <circle cx="39" cy="44.5" r="2.8" fill="white"/>
  <circle cx="57" cy="44.5" r="2.8" fill="white"/>
  <ellipse cx="50" cy="58" rx="5.5" ry="4.5" fill="#3D2010"/>
  <path d="M 44 64 Q 50 70 56 64" stroke="#2C1810" stroke-width="2.5" fill="none" stroke-linecap="round"/>
  <line x1="53" y1="59" x2="71" y2="54" stroke="#6B4A2A" stroke-width="1.2" opacity="0.55"/>
  <line x1="53" y1="61.5" x2="73" y2="61.5" stroke="#6B4A2A" stroke-width="1.2" opacity="0.55"/>
  <line x1="47" y1="59" x2="29" y2="54" stroke="#6B4A2A" stroke-width="1.2" opacity="0.55"/>
  <line x1="47" y1="61.5" x2="27" y2="61.5" stroke="#6B4A2A" stroke-width="1.2" opacity="0.55"/>
  <ellipse cx="28" cy="93" rx="13" ry="10" fill="#7A5230"/>
  <ellipse cx="72" cy="93" rx="13" ry="10" fill="#7A5230"/>
  <ellipse cx="28" cy="102" rx="10" ry="7" fill="#6B4423"/>
  <ellipse cx="72" cy="102" rx="10" ry="7" fill="#6B4423"/>
  <circle cx="33" cy="55" r="7" fill="#FFB6C1" opacity="0.4"/>
  <circle cx="67" cy="55" r="7" fill="#FFB6C1" opacity="0.4"/>
</svg>"""


# ──────────────────────────────────────────
# CSS（完全新設計）
# ──────────────────────────────────────────

_CSS = f"""
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;700;900&family=Inter:wght@400;600;700;900&display=swap');

*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html{{scroll-behavior:smooth}}
body{{
  font-family:'Noto Sans JP','Inter',sans-serif;
  background:{BG};
  color:{TEXT};
  font-size:14px;
  line-height:1.6;
  min-height:100vh;
  -webkit-font-smoothing:antialiased;
}}

/* グラスカード */
.glass{{
  background:rgba(255,255,255,0.04);
  backdrop-filter:blur(20px);
  -webkit-backdrop-filter:blur(20px);
  border:1px solid rgba(255,255,255,0.09);
  border-radius:16px;
}}
.glass-sm{{
  background:rgba(255,255,255,0.04);
  border:1px solid rgba(255,255,255,0.08);
  border-radius:12px;
}}

/* ネオングロー */
.glow-green {{ box-shadow:0 0 20px rgba(0,255,135,.20), 0 0 60px rgba(0,255,135,.08); }}
.glow-red   {{ box-shadow:0 0 20px rgba(255,61,90,.20),  0 0 60px rgba(255,61,90,.08); }}
.glow-yellow{{ box-shadow:0 0 20px rgba(255,200,55,.20), 0 0 60px rgba(255,200,55,.08); }}

/* ラベル共通 */
.label{{font-size:10px;font-weight:700;letter-spacing:1.2px;color:{MUTED};text-transform:uppercase;margin-bottom:5px}}

/* フェードイン */
@keyframes fadeUp{{
  from{{opacity:0;transform:translateY(16px)}}
  to  {{opacity:1;transform:translateY(0)}}
}}
.fade{{animation:fadeUp .5s ease forwards;opacity:0}}

/* ティッカー */
.ticker-wrap{{position:sticky;top:0;z-index:100;background:{BG};border-bottom:1px solid {BORDER}}}

/* スクロールバー非表示 */
.scroll-x{{overflow-x:auto;scrollbar-width:none}}
.scroll-x::-webkit-scrollbar{{display:none}}

/* バッジ */
.badge{{display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:20px;font-size:10px;font-weight:700;white-space:nowrap}}

/* シグナルバー */
.sig-bar{{height:3px;border-radius:2px;margin-top:4px}}

/* ニュースアイテム */
.news-item{{padding:9px 0;border-bottom:1px solid {BORDER};display:flex;align-items:flex-start;gap:8px}}
.news-item:last-child{{border-bottom:none}}

/* カレンダー */
.cal-row{{padding:7px 0;border-bottom:1px solid {BORDER};display:flex;align-items:flex-start;gap:8px}}
.cal-row:last-child{{border-bottom:none}}

/* デバイスの幅に合わせてmax-width */
@media(min-width:540px){{
  .wrap{{max-width:520px;margin:0 auto}}
}}

/* ── キャラクターカード ── */
.char-card{{
  display:flex;align-items:flex-start;gap:0;
  border-radius:14px;overflow:hidden;margin-bottom:8px;
}}
.char-ganesha{{
  background:linear-gradient(135deg,#1c1600,#271e00);
  border:1px solid rgba(255,215,0,.22);
}}
.char-otter{{
  background:linear-gradient(135deg,#160e09,#1f130c);
  border:1px solid rgba(196,149,106,.22);
}}
.char-avatar{{
  width:80px;flex-shrink:0;text-align:center;
  padding:10px 4px 8px;
}}
.char-name-g{{font-size:9px;font-weight:800;color:#FFD700;margin-top:3px;white-space:nowrap}}
.char-name-o{{font-size:9px;font-weight:800;color:#C4956A;margin-top:3px;white-space:nowrap}}
.char-bubble{{flex:1;padding:11px 13px 11px 10px;min-width:0}}
.char-bubble-r{{flex:1;padding:11px 10px 11px 13px;min-width:0}}
.char-badge-g{{
  font-size:9px;font-weight:800;color:#FFD700;letter-spacing:.6px;
  background:rgba(255,215,0,.12);border:1px solid rgba(255,215,0,.28);
  border-radius:10px;padding:2px 9px;display:inline-block;margin-bottom:6px;
}}
.char-badge-o{{
  font-size:9px;font-weight:800;color:#C4956A;letter-spacing:.6px;
  background:rgba(196,149,106,.12);border:1px solid rgba(196,149,106,.28);
  border-radius:10px;padding:2px 9px;display:inline-block;margin-bottom:6px;
}}
.char-text{{font-size:11.5px;line-height:1.8;word-break:break-word}}
@media(max-width:400px){{
  .char-card{{flex-direction:column;padding:10px}}
  .char-avatar{{width:100%;padding:4px 0}}
  .char-bubble,.char-bubble-r{{padding:8px 0 0}}
}}
"""


# ──────────────────────────────────────────
# セクション 0：ヘッダー
# ──────────────────────────────────────────

def _header(score, today, label, color):
    dot_shadow = f"0 0 8px {color}"
    return f"""
<div style="background:rgba(255,255,255,0.03);border-bottom:1px solid {BORDER};padding:11px 16px">
  <div class="wrap" style="display:flex;align-items:center;justify-content:space-between">
    <div style="display:flex;align-items:center;gap:10px">
      <div style="width:32px;height:32px;background:linear-gradient(135deg,{PURPLE},{BLUE});border-radius:9px;display:flex;align-items:center;justify-content:center;font-size:16px">📊</div>
      <div>
        <div style="font-size:14px;font-weight:900;color:{TEXT}">市場AI秘書</div>
        <div style="font-size:10px;color:{MUTED}">{today}</div>
      </div>
    </div>
    <div style="display:flex;align-items:center;gap:7px;background:rgba(255,255,255,0.05);border:1px solid {BORDER};border-radius:20px;padding:5px 12px">
      <div style="width:7px;height:7px;border-radius:50%;background:{color};box-shadow:{dot_shadow}"></div>
      <span style="font-size:12px;font-weight:700;color:{color}">{label}</span>
    </div>
  </div>
</div>"""


# ──────────────────────────────────────────
# セクション 1：ヒーローカード（今日の総合判断）
# ──────────────────────────────────────────

def _hero(score, prices, fear_greed, risk, now):
    color, label, bg_hex, emoji, mode = _score_info(score)

    n225  = _p("^N225",    prices)
    nchg  = _chg("^N225",    prices)
    usd   = _p("USDJPY=X", prices)
    uchg  = _chg("USDJPY=X", prices)
    vix   = _p("^VIX",    prices, fallback=18)
    vc, vl, vd = _vix_info(vix)

    glow_cls = "glow-green" if color == GREEN else ("glow-red" if color == RED else "glow-yellow")

    # 3行まとめ
    def row(ic, c, txt):
        return f'<div style="display:flex;align-items:flex-start;gap:9px;padding:8px 0;border-bottom:1px solid {BORDER}"><span style="font-size:17px;flex-shrink:0;margin-top:1px">{ic}</span><div style="font-size:12px;line-height:1.75;color:{c}">{txt}</div></div>'

    if   nchg >= 1.0:  r1 = row("📈", GREEN,  f'日経平均 <b style="font-size:14px">{_fmt(n225,0)}円</b> <span style="color:{MUTED}">前日比</span> <b style="color:{GREEN}">+{nchg:.1f}%</b> — 上昇中です。')
    elif nchg <= -1.0: r1 = row("📉", RED,    f'日経平均 <b style="font-size:14px">{_fmt(n225,0)}円</b> <span style="color:{MUTED}">前日比</span> <b style="color:{RED}">{nchg:.1f}%</b> — 下落しています。')
    else:              r1 = row("📊", YELLOW, f'日経平均 <b style="font-size:14px">{_fmt(n225,0)}円</b> <span style="color:{MUTED}">前日比</span> <b style="color:{YELLOW}">{nchg:+.1f}%</b> — ほぼ横ばいです。')

    if   usd > 158: r2 = row("🚨", RED,    f'ドル円 <b style="font-size:14px">{usd:.2f}円</b> — <b>強い円安。財務省の為替介入リスク</b>に警戒。')
    elif usd > 153: r2 = row("⚠️", ORANGE, f'ドル円 <b style="font-size:14px">{usd:.2f}円</b>（{uchg:+.2f}%）— 円安傾向。輸入品が高くなりやすい水準。')
    elif usd > 0:   r2 = row("💴", TEXT,   f'ドル円 <b style="font-size:14px">{usd:.2f}円</b>（{uchg:+.2f}%）— 比較的安定した水準です。')
    else:           r2 = row("💴", MUTED,  'ドル円データを取得中...')

    r3 = row("😨", vc, f'恐怖指数VIX <b style="font-size:14px">{vix:.1f}</b> <span style="background:rgba(255,255,255,.07);border-radius:4px;padding:1px 6px;font-size:10px;font-weight:700;color:{vc}">{vl}</span> — {vd}')

    return f"""
<div class="glass fade {glow_cls}" style="border-color:{color}33;padding:16px 16px 12px;margin-bottom:12px;position:relative;overflow:hidden">
  <!-- 背景グラデーション -->
  <div style="position:absolute;top:-40px;right:-40px;width:140px;height:140px;border-radius:50%;background:radial-gradient(circle,{color}18,transparent 70%);pointer-events:none"></div>

  <div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:12px">
    <div>
      <div class="label">今日の相場まとめ</div>
      <div style="font-size:22px;font-weight:900;color:{color};line-height:1.2">{emoji} {label}</div>
    </div>
    <div style="text-align:right">
      <div style="font-size:32px;font-weight:900;color:{color};line-height:1;text-shadow:0 0 20px {color}44">{score:+.2f}</div>
      <div style="font-size:9px;color:{MUTED};margin-top:1px">AIスコア / −3〜+3</div>
    </div>
  </div>

  {r1}{r2}{r3}

  <div style="margin-top:8px;font-size:9px;color:{MUTED};text-align:right">{now} 更新</div>
</div>"""


# ──────────────────────────────────────────
# セクション 2：主要4指標カード（2×2グリッド）
# ──────────────────────────────────────────

def _quick4(prices, fear_greed):
    n225 = _p("^N225",    prices)
    nchg = _chg("^N225",    prices)
    usd  = _p("USDJPY=X", prices)
    uchg = _chg("USDJPY=X", prices)
    vix  = _p("^VIX",    prices, fallback=18)
    vchg = _chg("^VIX",    prices)
    fg_s = (fear_greed or {}).get("score", 50) or 50
    fgl, fgc, _ = _fg_info(fg_s)
    vc, _, _ = _vix_info(vix)

    def card(icon, title, value, change, val_color, note=""):
        chg_color = _col(change) if change != 0 else MUTED
        bar_w = min(abs(change) * 20, 100)
        bar_c = GREEN if change > 0 else (RED if change < 0 else MUTED)
        note_html = f'<div style="font-size:9px;color:{MUTED};margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{note}</div>' if note else ""
        return f"""<div class="glass-sm fade" style="padding:12px 10px">
  <div style="font-size:10px;color:{MUTED};margin-bottom:4px;display:flex;align-items:center;gap:5px"><span>{icon}</span>{title}</div>
  <div style="font-size:20px;font-weight:900;color:{val_color};line-height:1.1">{value}</div>
  <div style="font-size:11px;color:{chg_color};font-weight:700;margin-top:2px">{_arrow(change)} {abs(change):.2f}%</div>
  <div style="height:2px;background:rgba(255,255,255,.06);border-radius:1px;margin-top:5px"><div style="width:{bar_w}%;height:100%;background:{bar_c};border-radius:1px"></div></div>
  {note_html}
</div>"""

    vix_chg_inv = -vchg  # VIXは逆方向表示
    cards = [
        card("🇯🇵", "日経225",      _fmt(n225,0),    nchg,        _col(nchg),  f"円建て / 前日終値比"),
        card("💴",  "ドル円",        f"{usd:.2f}円",  uchg,        _col(uchg),  f"1ドル = {usd:.2f}円"),
        card("😨",  "VIX 恐怖指数", f"{vix:.1f}",    vix_chg_inv, vc,          "低いほど市場は安定"),
        card("🎭",  "Fear & Greed", f"{fg_s:.0f}",   0,           fgc,         fgl),
    ]
    return f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px">{"".join(cards)}</div>'


# ──────────────────────────────────────────
# セクション 3：横スクロール価格ストリップ
# ──────────────────────────────────────────

def _price_strip(prices):
    items = [
        ("^GSPC",    "S&P500",  "🇺🇸"),
        ("^IXIC",    "Nasdaq",  "💻"),
        ("GC=F",     "金(Gold)","🥇"),
        ("CL=F",     "原 油",   "🛢"),
        ("BTC-USD",  "BTC",     "₿"),
        ("^TNX",     "米10年債","📄"),
        ("EURJPY=X", "EUR/JPY", "🇪🇺"),
    ]
    chips = []
    for sym, name, icon in items:
        p = prices.get(sym, {})
        if not p: continue
        val  = p.get("price", 0) or p.get("latest", 0) or 0
        chg  = p.get("change_pct", 0) or 0
        if val == 0: continue
        c = _col(chg)
        chips.append(f"""<div style="display:inline-flex;flex-direction:column;align-items:center;background:rgba(255,255,255,.04);border:1px solid {BORDER};border-radius:10px;padding:8px 12px;min-width:72px;flex-shrink:0">
  <div style="font-size:14px">{icon}</div>
  <div style="font-size:9px;color:{MUTED};margin:2px 0;white-space:nowrap">{name}</div>
  <div style="font-size:12px;font-weight:700;color:{TEXT}">{_fmt(val)}</div>
  <div style="font-size:10px;color:{c};font-weight:700">{_arrow(chg)}{abs(chg):.1f}%</div>
</div>""")

    if not chips: return ""
    return f"""
<div style="margin-bottom:12px">
  <div class="label" style="padding:0 2px;margin-bottom:6px">📊 その他の主要市場</div>
  <div class="scroll-x" style="display:flex;gap:7px;padding-bottom:4px">
    {"".join(chips)}
  </div>
</div>"""


# ──────────────────────────────────────────
# セクション 4：ライブチャート（TradingView）
# ──────────────────────────────────────────

def _charts():
    return f"""
<div style="margin-bottom:12px">
  <div class="label" style="padding:0 2px;margin-bottom:6px">📈 リアルタイムチャート</div>
  <div class="glass" style="overflow:hidden;margin-bottom:8px;padding:0">
    <div style="padding:8px 12px 4px;font-size:10px;font-weight:700;color:{MUTED}">🇯🇵 日経225</div>
    <div class="tradingview-widget-container">
      <div class="tradingview-widget-container__widget"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-mini-symbol-overview.js" async>
      {{"symbol":"TVC:NI225","width":"100%","height":160,"locale":"ja","dateRange":"1D","colorTheme":"dark","isTransparent":true}}
      </script>
    </div>
  </div>
  <div class="glass" style="overflow:hidden;padding:0">
    <div style="padding:8px 12px 4px;font-size:10px;font-weight:700;color:{MUTED}">💴 ドル円（USD/JPY）</div>
    <div class="tradingview-widget-container">
      <div class="tradingview-widget-container__widget"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-mini-symbol-overview.js" async>
      {{"symbol":"FX:USDJPY","width":"100%","height":140,"locale":"ja","dateRange":"1D","colorTheme":"dark","isTransparent":true}}
      </script>
    </div>
  </div>
</div>"""


# ──────────────────────────────────────────
# セクション 5：AI分析（チャット吹き出し風）
# ──────────────────────────────────────────

def _ai_section(ai_summary, team_debate, score, character_comments=None):
    color, label, _, emoji, mode = _score_info(score)

    # メイン分析テキスト（ai_summary または team_debate から取得）
    txt = ""
    if ai_summary:
        for k in ["summary", "text", "analysis", "comment", "conclusion"]:
            v = ai_summary.get(k, "")
            if isinstance(v, str) and len(v) > 40:
                txt = v; break

    verdict = ""
    if isinstance(team_debate, dict):
        for k in ["verdict", "conclusion", "summary"]:
            v = team_debate.get(k, "")
            if isinstance(v, str) and len(v) > 20:
                verdict = v; break

    main_txt = (txt or verdict or f"現在のAIシグナルは「{label}」（スコア {score:+.2f}）です。")[:280]

    # ── ガネーシャ & カワウソ キャラクターカード ──
    char_html = ""
    cc = character_comments or {}
    g_txt = cc.get("ganesha", "")
    o_txt = cc.get("otter", "")
    # フォールバック: ai_summary から抽出
    if not g_txt and ai_summary:
        g_txt = str(ai_summary.get("neutral_view") or ai_summary.get("analysis") or "")[:200]
    if not o_txt and ai_summary:
        raw = str(ai_summary.get("summary") or ai_summary.get("text") or "")[:120]
        o_txt = raw

    if g_txt or o_txt:
        g_display = g_txt or "市場データを分析中ですぞ…"
        o_display = o_txt or "データ取得中だよ〜♪"
        char_html = f"""
<div style="margin-top:10px">
  <!-- 🐘 ガネーシャ -->
  <div class="char-card char-ganesha">
    <div class="char-avatar">
      {_GANESHA_SVG}
      <div class="char-name-g">🐘 AIガネーシャ</div>
    </div>
    <div class="char-bubble">
      <div class="char-badge-g">📜 プロの相場解説</div>
      <div class="char-text" style="color:{TEXT}">{g_display}</div>
    </div>
  </div>
  <!-- 🦦 カワウソ -->
  <div class="char-card char-otter">
    <div class="char-bubble-r">
      <div class="char-badge-o">✨ カンタンまとめ</div>
      <div class="char-text" style="color:{TEXT}">{o_display}</div>
    </div>
    <div class="char-avatar">
      {_OTTER_SVG}
      <div class="char-name-o">🦦 AIカワウソ</div>
    </div>
  </div>
</div>"""

    # ── 3視点バブル（bull / neutral / bear）──
    bubbles = []
    src = team_debate if isinstance(team_debate, dict) and team_debate else (ai_summary or {})
    view_cfg = [
        ("bull_view",    "🐂", "強気派",  GREEN),
        ("neutral_view", "😐", "中立派",  YELLOW),
        ("bear_view",    "🐻", "弱気派",  RED),
    ]
    for key, ic, lbl, c in view_cfg:
        raw = src.get(key, "")
        if isinstance(raw, dict):
            pt = str(raw.get("point") or raw.get("text") or raw.get("summary") or "")
        else:
            pt = str(raw or "")
        pt = pt[:100]
        if not pt: continue
        bubbles.append(f"""<div style="display:flex;align-items:flex-start;gap:8px;margin-bottom:7px">
  <div style="width:30px;height:30px;border-radius:50%;background:rgba(255,255,255,.06);border:1.5px solid {c};display:flex;align-items:center;justify-content:center;font-size:15px;flex-shrink:0">{ic}</div>
  <div style="background:rgba(255,255,255,.04);border:1px solid {BORDER};border-radius:4px 12px 12px 12px;padding:7px 10px;flex:1">
    <div style="font-size:10px;font-weight:700;color:{c};margin-bottom:2px">{lbl}</div>
    <div style="font-size:11px;line-height:1.65;color:{TEXT}">{pt}</div>
  </div>
</div>""")

    bubbles_html = "".join(bubbles)
    has_below = bool(char_html or bubbles_html)

    return f"""
<div style="margin-bottom:12px">
  <div class="label" style="padding:0 2px;margin-bottom:6px">🤖 AIチーム分析</div>
  <div class="glass" style="border-color:{color}33;padding:14px;position:relative;overflow:hidden">
    <div style="position:absolute;top:-30px;left:-30px;width:100px;height:100px;border-radius:50%;background:radial-gradient(circle,{color}15,transparent 70%);pointer-events:none"></div>

    <!-- スコアヘッダー -->
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;padding-bottom:10px;border-bottom:1px solid {BORDER}">
      <div style="width:38px;height:38px;border-radius:50%;background:linear-gradient(135deg,{PURPLE},{BLUE});display:flex;align-items:center;justify-content:center;font-size:18px">{emoji}</div>
      <div>
        <div style="font-size:10px;color:{MUTED}">AIチームの総合判断</div>
        <div style="font-size:15px;font-weight:900;color:{color}">{label}</div>
      </div>
      <div style="margin-left:auto;font-size:22px;font-weight:900;color:{color};text-shadow:0 0 15px {color}55">{score:+.2f}</div>
    </div>

    <!-- メインコメント -->
    <div style="background:rgba(255,255,255,.03);border-left:3px solid {color};border-radius:0 8px 8px 0;padding:10px 12px;font-size:12px;line-height:1.8;color:{TEXT};margin-bottom:{'10px' if has_below else '0'}">{main_txt}</div>

    <!-- ガネーシャ & カワウソ -->
    {char_html}

    <!-- 3視点バブル -->
    {f'<div style="margin-top:10px">{bubbles_html}</div>' if bubbles_html else ""}
  </div>
</div>"""


# ──────────────────────────────────────────
# セクション 6：3シナリオ（確率バー付き）
# ──────────────────────────────────────────

def _scenarios(scenario):
    sc = scenario or {}
    if not sc.get("available"): return ""

    cfgs = [
        ("bull", "🚀 強気シナリオ", GREEN,  "rgba(0,255,135,.06)"),
        ("base", "😐 基本シナリオ", YELLOW, "rgba(255,200,55,.06)"),
        ("bear", "🐻 弱気シナリオ", RED,    "rgba(255,61,90,.06)"),
    ]
    cards = []
    for key, lbl, c, bg in cfgs:
        s = sc.get(key, {})
        if not s: continue
        prob = s.get("probability", s.get("prob", 0))
        desc = str(s.get("description", s.get("desc", s.get("text", ""))))[:100]
        pct  = int(prob * 100) if prob and prob <= 1 else (int(prob) if prob else 0)
        cards.append(f"""<div style="background:{bg};border:1.5px solid {c}44;border-radius:14px;padding:13px 12px">
  <div style="font-size:11px;font-weight:700;color:{c};margin-bottom:5px">{lbl}</div>
  <div style="font-size:30px;font-weight:900;color:{c};line-height:1;text-shadow:0 0 18px {c}44;margin-bottom:6px">{pct}%</div>
  <div style="background:rgba(0,0,0,.3);border-radius:3px;height:4px;margin-bottom:8px;overflow:hidden">
    <div style="width:{pct}%;height:100%;background:{c};border-radius:3px;box-shadow:0 0 8px {c}66"></div>
  </div>
  <div style="font-size:10px;line-height:1.6;color:rgba(240,244,255,.7)">{desc}</div>
</div>""")

    if not cards: return ""
    return f"""
<div style="margin-bottom:12px">
  <div class="label" style="padding:0 2px;margin-bottom:6px">🔭 シナリオ分析（確率別）</div>
  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:7px">{"".join(cards)}</div>
  <div style="font-size:9px;color:{MUTED};text-align:center;margin-top:5px">棒グラフの長さ＝AIが予測する発生確率</div>
</div>"""


# ──────────────────────────────────────────
# セクション 7：詳細マーケットデータ（RSIバー付き）
# ──────────────────────────────────────────

def _market_grid(prices, technical):
    items = [
        ("^N225",    "🇯🇵 日経225",   ""),
        ("^GSPC",    "🇺🇸 S&P500",    ""),
        ("^IXIC",    "💻 Nasdaq",     ""),
        ("USDJPY=X", "💴 ドル円",     "¥"),
        ("GC=F",     "🥇 金(Gold)",   "$"),
        ("CL=F",     "🛢 原油(WTI)",  "$"),
        ("BTC-USD",  "₿ ビットコイン","$"),
        ("^VIX",     "😨 VIX",        ""),
        ("^TNX",     "📄 米10年金利", "%"),
    ]
    tech = (technical or {}).get("signals", {})

    cards = []
    for sym, name, unit in items:
        p = prices.get(sym, {})
        if not p: continue
        val  = p.get("price", 0) or p.get("latest", 0) or 0
        chg  = p.get("change_pct", 0) or 0
        rsi  = p.get("rsi") or tech.get(sym, {}).get("rsi") or 0
        c    = _col(chg)
        vstr = _fmt(val)

        rsi_html = ""
        if rsi:
            rc  = RED if rsi >= 70 else (GREEN if rsi <= 30 else YELLOW)
            rtx = "過熱" if rsi >= 70 else ("売られすぎ" if rsi <= 30 else "中立")
            rsi_html = f"""
<div style="margin-top:6px">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:2px">
    <span style="font-size:9px;color:{MUTED}">RSI</span>
    <span style="font-size:9px;color:{rc};font-weight:700">{rsi:.0f} {rtx}</span>
  </div>
  <div style="height:3px;background:rgba(255,255,255,.06);border-radius:2px;overflow:hidden">
    <div style="width:{int(rsi)}%;height:100%;background:{rc};border-radius:2px"></div>
  </div>
</div>"""

        cards.append(f"""<div class="glass-sm fade" style="padding:10px">
  <div style="font-size:9px;color:{MUTED};margin-bottom:3px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{name}</div>
  <div style="font-size:16px;font-weight:800;color:{TEXT}">{vstr}{(' '+unit) if unit else ''}</div>
  <div style="font-size:10px;color:{c};font-weight:700;margin-top:1px">{_arrow(chg)} {abs(chg):.2f}%</div>
  {rsi_html}
</div>""")

    if not cards: return ""
    return f"""
<div style="margin-bottom:12px">
  <div class="label" style="padding:0 2px;margin-bottom:6px">💹 マーケットデータ詳細</div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:7px">{"".join(cards)}</div>
  <div style="font-size:9px;color:{MUTED};margin-top:5px;padding:0 2px">RSI: 70↑＝買われすぎ注意 / 30↓＝売られすぎ・反発期待</div>
</div>"""


# ──────────────────────────────────────────
# セクション 8：TradingView 世界市場概況
# ──────────────────────────────────────────

def _tv_overview():
    return f"""
<div style="margin-bottom:12px">
  <div class="label" style="padding:0 2px;margin-bottom:6px">🌍 世界の主要市場（リアルタイム）</div>
  <div style="border-radius:14px;overflow:hidden;border:1px solid {BORDER}">
    <div class="tradingview-widget-container">
      <div class="tradingview-widget-container__widget"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-market-overview.js" async>
      {{"colorTheme":"dark","dateRange":"1D","showChart":false,"locale":"ja","width":"100%","height":300,"isTransparent":true,
        "tabs":[
          {{"title":"株・指数","symbols":[
            {{"s":"TVC:NI225","d":"日経225"}},{{"s":"TSE:TOPIX","d":"TOPIX"}},
            {{"s":"SP:SPX","d":"S&P500"}},{{"s":"NASDAQ:NDX","d":"Nasdaq100"}},{{"s":"INDEX:DAX","d":"DAX"}}
          ]}},
          {{"title":"FX・商品","symbols":[
            {{"s":"FX:USDJPY","d":"ドル円"}},{{"s":"FX:EURJPY","d":"ユーロ円"}},
            {{"s":"TVC:GOLD","d":"金"}},{{"s":"TVC:USOIL","d":"原油"}},{{"s":"BITSTAMP:BTCUSD","d":"BTC"}}
          ]}}
        ]}}
      </script>
    </div>
  </div>
</div>"""


# ──────────────────────────────────────────
# セクション 9：プロ向けクロス分析
# ──────────────────────────────────────────

def _pro_cross(prices):
    def val(sym):
        r = prices.get(sym) or {}
        v = r.get("latest")
        return v if v is not None else r.get("price")

    nvi  = val("NIKKEI_VI"); vix  = val("^VIX")
    vix9 = val("^VIX9D");    vix3m= val("^VIX3M")
    n225 = val("^N225");     fut  = val("NIY=F")

    rows = []

    if nvi and vix:
        s = nvi - vix
        c = RED if abs(s)>=12 else (YELLOW if abs(s)>=6 else GREEN)
        dot = "🟢" if c==GREEN else ("🔴" if c==RED else "🟡")
        easy = ("日本だけが怖がっている状態。日本固有リスクに注意。" if s>=12
                else "アメリカの方が怖がっています。米発の下げに警戒。" if s<=-3
                else "日米の恐怖感はほぼ均衡。特別な歪みなし。")
        rows.append((dot, f"日米 恐怖スプレッド", f"{s:+.1f}pt", f"日経VI {nvi:.1f} vs VIX {vix:.1f}", easy, c))

    if fut and n225:
        g = (fut - n225) / n225 * 100
        c = RED if abs(g)>=0.8 else (YELLOW if abs(g)>=0.3 else GREEN)
        dot = "🟢" if c==GREEN else ("🔴" if c==RED else "🟡")
        d = "高く" if g>0 else "安く"
        easy = (f"明日の朝は大きく{d}始まりそう。最初の数分は様子見を。" if abs(g)>=0.8
                else f"明日は少し{d}始まりそう。あわてず様子を見て。" if abs(g)>=0.3
                else "明日の朝はだいたい昨日の続きから始まりそう。")
        rows.append((dot, "CME先物ギャップ", f"{g:+.2f}%", f"先物 {fut:,.0f} vs 現物 {n225:,.0f}", easy, c))

    if vix9 and vix3m:
        ts = vix9 - vix3m
        c  = RED if ts>=2 else (YELLOW if ts>0 else GREEN)
        dot = "🟢" if c==GREEN else ("🔴" if c==RED else "🟡")
        easy = ("「今週がいちばん怖い」形。荒れやすいが底打ちサインにもなる。" if ts>=2
                else "ふだんより直近への警戒が少し強め。" if ts>0
                else "ボラ市場は平常運転。差し迫った恐怖はなし。")
        rows.append((dot, "VIX期間構造", f"{ts:+.1f}pt", f"VIX9D {vix9:.2f} vs VIX3M {vix3m:.2f}", easy, c))

    if not rows: return ""

    items_html = "".join(f"""<div style="padding:10px 0;border-bottom:1px solid {BORDER}">
  <div style="display:flex;align-items:center;gap:7px;margin-bottom:3px">
    <span style="font-size:13px">{dot}</span>
    <span style="font-size:12px;font-weight:700;color:{c}">{title} <span style="font-size:14px">{big}</span></span>
  </div>
  <div style="font-size:9px;color:{MUTED};padding-left:20px;margin-bottom:3px">{sub}</div>
  <div style="font-size:11px;color:{TEXT};line-height:1.65;padding-left:20px;padding-right:4px">💬 {easy}</div>
</div>""" for dot, title, big, sub, easy, c in rows)

    return f"""
<div style="margin-bottom:12px">
  <div class="label" style="padding:0 2px;margin-bottom:6px">🔬 プロ向けクロス分析</div>
  <div class="glass" style="padding:4px 14px">
    {items_html}
    <div style="padding-top:4px"></div>
  </div>
</div>"""


# ──────────────────────────────────────────
# セクション 10：ニュース
# ──────────────────────────────────────────

def _news(news_list):
    if not news_list: return ""

    items = []
    for n in news_list[:7]:
        if not isinstance(n, dict): continue
        title = str(n.get("title", ""))[:70]
        url   = n.get("url", n.get("link", "#"))
        src   = n.get("source", "")
        imp   = n.get("importance", n.get("score", 0))

        if imp >= 3 or n.get("high_impact"):
            bc, bb, bt = RED,    f"rgba(255,61,90,.15)",  "高"
        elif imp >= 1:
            bc, bb, bt = YELLOW, f"rgba(255,200,55,.12)", "中"
        else:
            bc, bb, bt = MUTED,  f"rgba(90,106,133,.15)", "低"

        items.append(f"""<div class="news-item">
  <span style="font-size:10px;font-weight:700;color:{bc};background:{bb};padding:2px 7px;border-radius:4px;flex-shrink:0;margin-top:2px">{bt}</span>
  <div>
    <a href="{url}" style="font-size:12px;line-height:1.55;color:{TEXT}">{title}</a>
    {f'<div style="font-size:9px;color:{MUTED};margin-top:1px">{src}</div>' if src else ""}
  </div>
</div>""")

    if not items: return ""
    return f"""
<div style="margin-bottom:12px">
  <div class="label" style="padding:0 2px;margin-bottom:6px">📰 今日の注目ニュース</div>
  <div class="glass" style="padding:4px 12px">
    {"".join(items)}
    <div style="padding-top:4px"></div>
  </div>
  <div style="font-size:9px;color:{MUTED};margin-top:4px;padding:0 2px">🔴高=市場への影響大 / 🟡中=要チェック</div>
</div>"""


# ──────────────────────────────────────────
# セクション 11：今週のイベント
# ──────────────────────────────────────────

def _calendar(weekly_calendar):
    cal = weekly_calendar or {}
    if not cal.get("available"): return ""
    events = cal.get("events", cal.get("items", []))
    if not events: return ""

    rows = []
    for ev in events[:6]:
        if not isinstance(ev, dict): continue
        date = str(ev.get("date", ev.get("day", "")))[:5]
        name = str(ev.get("name", ev.get("event", ev.get("title", ""))))[:48]
        imp  = ev.get("importance", ev.get("impact", 0))
        c    = RED if imp >= 3 else (YELLOW if imp >= 1 else MUTED)
        rows.append(f"""<div class="cal-row">
  <span style="font-size:10px;font-weight:700;color:{c};background:rgba(0,0,0,.3);padding:2px 8px;border-radius:5px;min-width:46px;text-align:center;flex-shrink:0">{date}</span>
  <span style="font-size:11px;line-height:1.5;color:{c if imp>=3 else TEXT}">{name}</span>
</div>""")

    if not rows: return ""
    return f"""
<div style="margin-bottom:12px">
  <div class="label" style="padding:0 2px;margin-bottom:6px">📅 今週の重要イベント</div>
  <div class="glass" style="padding:4px 12px">
    {"".join(rows)}
    <div style="padding-top:4px"></div>
  </div>
  <div style="font-size:9px;color:{MUTED};margin-top:4px;padding:0 2px">🔴赤＝相場が大きく動く可能性あり。発表前後は注意。</div>
</div>"""


# ──────────────────────────────────────────
# セクション 12：AI予測精度
# ──────────────────────────────────────────

def _pred(prediction_tracker):
    pt = prediction_tracker or {}
    if not pt.get("available"): return ""
    acc  = float(pt.get("accuracy", 0) or 0)
    n    = int(pt.get("total", 0) or 0)
    hits = int(pt.get("hits", 0) or 0)
    if not n: return ""

    miss  = n - hits
    bar_c = GREEN if acc >= 60 else (YELLOW if acc >= 45 else RED)
    grade = "A" if acc>=70 else ("B" if acc>=60 else ("C" if acc>=50 else "D"))
    grade_c = GREEN if grade=="A" else (BLUE if grade=="B" else (YELLOW if grade=="C" else RED))

    return f"""
<div style="margin-bottom:12px">
  <div class="label" style="padding:0 2px;margin-bottom:6px">🎯 AIの予測精度（累積）</div>
  <div class="glass" style="padding:14px">
    <div style="display:flex;align-items:center;gap:14px;margin-bottom:10px">
      <div style="text-align:center;min-width:70px">
        <div style="font-size:38px;font-weight:900;color:{bar_c};line-height:1;text-shadow:0 0 20px {bar_c}55">{acc:.0f}%</div>
        <div style="font-size:9px;color:{MUTED};margin-top:2px">正解率</div>
      </div>
      <div style="flex:1">
        <div style="background:rgba(255,255,255,.06);border-radius:4px;height:7px;margin-bottom:8px;overflow:hidden">
          <div style="width:{acc:.0f}%;height:100%;background:{bar_c};border-radius:4px;box-shadow:0 0 10px {bar_c}66"></div>
        </div>
        <div style="display:flex;gap:12px;font-size:10px">
          <span style="color:{GREEN}">✅ 正解 {hits}回</span>
          <span style="color:{RED}">❌ 不正解 {miss}回</span>
        </div>
        <div style="font-size:10px;color:{MUTED};margin-top:3px">累計 {n}回の予測</div>
      </div>
      <div style="width:38px;height:38px;border-radius:50%;border:2px solid {grade_c};display:flex;align-items:center;justify-content:center;font-size:18px;font-weight:900;color:{grade_c}">{grade}</div>
    </div>
    <div style="font-size:10px;color:{MUTED}">📖 毎日翌日の相場を予測し、翌朝に答え合わせした累積成績です</div>
  </div>
</div>"""


# ──────────────────────────────────────────
# セクション 13：用語ガイド（折りたたみ）
# ──────────────────────────────────────────

def _guide():
    terms = [
        ("📊", "AIスコア（−3〜+3）",      "複数の指標を総合した市場の強弱スコア。",         "+1以上=強気 / ±0=中立 / −1以下=弱気"),
        ("😨", "VIX（恐怖指数）",          "市場の荒れを予想しているかの度合い。",            "30↑=パニック / 20前後=警戒 / 15↓=安定"),
        ("📈", "RSI（相対力指数）",         "買われすぎ・売られすぎを0〜100で表示。",          "70↑=買われすぎ注意 / 30↓=売られすぎ反発期待"),
        ("🎭", "Fear & Greed",            "市場参加者の心理状態を0〜100で数値化。",           "25↓=極度の恐怖 / 75↑=極度の欲望"),
        ("💴", "ドル円（USD/JPY）",         "1ドル＝何円かを示す。大きい数字ほど円安。",         "155円↑=円安警戒 / 140円台=比較的安定"),
        ("📉", "CME先物",                  "夜間に米国で売買される翌日の日経の予約価格。",       "高い→翌朝高く始まる / 低い→翌朝安く始まる"),
    ]
    rows = "".join(f"""<div style="display:flex;align-items:flex-start;gap:9px;padding:9px 0;border-bottom:1px solid {BORDER}">
  <span style="font-size:16px;flex-shrink:0;margin-top:1px">{ic}</span>
  <div>
    <div style="font-size:11px;font-weight:700;color:{TEXT};margin-bottom:2px">{title}</div>
    <div style="font-size:10px;color:{MUTED};line-height:1.5">{desc}</div>
    <div style="font-size:9px;color:{BLUE};margin-top:3px;background:rgba(0,180,255,.07);padding:2px 8px;border-radius:4px;display:inline-block">{guide}</div>
  </div>
</div>""" for ic, title, desc, guide in terms)

    return f"""
<details style="margin-bottom:12px">
  <summary style="cursor:pointer;background:rgba(255,255,255,.04);border:1px solid {BORDER};border-radius:12px;padding:10px 14px;font-size:12px;font-weight:700;color:{TEXT};list-style:none;display:flex;align-items:center;gap:8px;user-select:none;-webkit-user-select:none">
    <span style="font-size:14px">📖</span>
    <span>用語がわからない方はこちら</span>
    <span style="margin-left:auto;font-size:9px;color:{MUTED}">タップして開く ▼</span>
  </summary>
  <div style="background:rgba(255,255,255,.04);border:1px solid {BORDER};border-top:none;border-radius:0 0 12px 12px;padding:0 12px 8px">
    {rows}
  </div>
</details>
<style>details[open] > summary {{ border-radius:12px 12px 0 0; }}</style>"""


# ──────────────────────────────────────────
# メイン生成関数
# ──────────────────────────────────────────

def generate(
    mode: str = "morning",
    prices: dict = None,
    news: list = None,
    risk: dict = None,
    fear_greed: dict = None,
    ai_summary: dict = None,
    scenario: dict = None,
    technical: dict = None,
    sector_analysis: dict = None,
    prediction_tracker: dict = None,
    weekly_calendar: dict = None,
    team_debate: dict = None,
    youtube_summary: dict = None,
    data_integrity: dict = None,
    character_comments: dict = None,
    **_kwargs,
) -> str:
    prices      = prices      or {}
    news        = news        or []
    risk        = risk        or {}
    fear_greed  = fear_greed  or {}
    team_debate = team_debate or {}

    today = get_today_str()
    now   = get_jst_now().strftime("%Y-%m-%d %H:%M JST")
    score = float(risk.get("score", 0) or 0)
    color, label, _, emoji, mode_str = _score_info(score)

    # 各セクション生成
    header_html  = _header(score, today, label, color)
    hero_html    = _hero(score, prices, fear_greed, risk, now)
    q4_html      = _quick4(prices, fear_greed)
    strip_html   = _price_strip(prices)
    charts_html  = _charts()
    ai_html      = _ai_section(ai_summary, team_debate, score, character_comments)
    sc_html      = _scenarios(scenario)
    mkt_html     = _market_grid(prices, technical)
    tv_html      = _tv_overview()
    pro_html     = _pro_cross(prices)
    news_html    = _news(news)
    cal_html     = _calendar(weekly_calendar)
    pred_html    = _pred(prediction_tracker)
    guide_html   = _guide()

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=5">
<meta name="theme-color" content="{BG}">
<title>市場AI秘書 — {today}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;700;900&display=swap" rel="stylesheet">
<style>
{_CSS}
</style>
</head>
<body>

<!-- ── トップグラデーションライン ── -->
<div style="height:3px;background:linear-gradient(90deg,{PURPLE},{BLUE},{CYAN},{GREEN})"></div>

<!-- ── ティッカーテープ（リアルタイム）── -->
<div class="ticker-wrap">
  <div class="tradingview-widget-container">
    <div class="tradingview-widget-container__widget"></div>
    <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-ticker-tape.js" async>
    {{"symbols":[
      {{"proName":"TVC:NI225","title":"日経225"}},{{"proName":"FX:USDJPY","title":"ドル円"}},
      {{"proName":"SP:SPX","title":"S&P500"}},{{"proName":"TVC:GOLD","title":"金"}},
      {{"proName":"TVC:USOIL","title":"原油"}},{{"proName":"CBOE:VIX","title":"VIX"}},
      {{"proName":"BITSTAMP:BTCUSD","title":"BTC"}},{{"proName":"FX:EURJPY","title":"EUR/JPY"}}
    ],"showSymbolLogo":false,"isTransparent":true,"displayMode":"adaptive","colorTheme":"dark","locale":"ja","width":"100%","height":44}}
    </script>
  </div>
</div>

<!-- ── ヘッダー ── -->
{header_html}

<!-- ── メインコンテンツ ── -->
<div class="wrap" style="padding:12px 13px 36px" id="main">

  {hero_html}
  {q4_html}
  {strip_html}
  {charts_html}
  {ai_html}
  {sc_html}
  {mkt_html}
  {tv_html}
  {pro_html}
  {news_html}
  {cal_html}
  {pred_html}
  {guide_html}

  <!-- フッター -->
  <div style="text-align:center;padding:18px 0 10px;color:{MUTED};font-size:10px;border-top:1px solid {BORDER}">
    <div style="font-size:13px;margin-bottom:4px;color:{TEXT}">📊 市場AI秘書 / ミセスワタナベ</div>
    <div>AIチーム自動生成 · {now}</div>
    <div style="margin-top:4px;background:linear-gradient(90deg,{PURPLE},{BLUE});-webkit-background-clip:text;-webkit-text-fill-color:transparent;font-weight:700">Powered by Gemini AI</div>
  </div>

</div>

<script>
(function(){{
  /* フェードインアニメーション */
  const io = new IntersectionObserver(entries => {{
    entries.forEach(e => {{
      if (e.isIntersecting) {{
        e.target.style.opacity = '1';
        e.target.style.transform = 'translateY(0)';
      }}
    }});
  }}, {{threshold: 0.05}});

  document.querySelectorAll('.fade').forEach((el, i) => {{
    el.style.cssText += ';opacity:0;transform:translateY(14px);transition:opacity .45s ease '+(i*.05)+'s,transform .45s ease '+(i*.05)+'s';
    io.observe(el);
  }});

  /* summary の arrow をトグル */
  document.querySelectorAll('details').forEach(d => {{
    d.addEventListener('toggle', () => {{
      const arrow = d.querySelector('summary span:last-child');
      if (arrow) arrow.textContent = d.open ? 'タップして閉じる ▲' : 'タップして開く ▼';
    }});
  }});
}})();
</script>

</body>
</html>"""

    # docs/ に保存（GitHub Pages 公開先）
    docs_dir = Path(__file__).parent.parent / "docs"
    docs_dir.mkdir(exist_ok=True)
    out_path = docs_dir / "daily_report.html"
    out_path.write_text(html, encoding="utf-8")

    # reports/ にも日付付きで保存
    try:
        rep_dir = get_dirs()["reports"]
        dated   = rep_dir / f"{today}_{mode}_design.html"
        dated.write_text(html, encoding="utf-8")
    except Exception:
        pass

    return str(out_path)


# ──────────────────────────────────────────
# エントリーポイント（cloud_run.py から呼ぶ）
# ──────────────────────────────────────────

def run(
    prices: dict = None,
    news: list   = None,
    risk: dict   = None,
    fear_greed: dict = None,
    ai_summary: dict = None,
    scenario: dict   = None,
    technical: dict  = None,
    sector_analysis: dict    = None,
    prediction_tracker: dict = None,
    weekly_calendar: dict    = None,
    team_debate: dict        = None,
    youtube_summary: dict    = None,
    data_integrity: dict     = None,
    character_comments: dict = None,
    mode: str = "morning",
    **_kwargs,
) -> dict:
    try:
        path = generate(
            mode=mode, prices=prices, news=news, risk=risk,
            fear_greed=fear_greed, ai_summary=ai_summary, scenario=scenario,
            technical=technical, youtube_summary=youtube_summary,
            data_integrity=data_integrity, sector_analysis=sector_analysis,
            prediction_tracker=prediction_tracker, weekly_calendar=weekly_calendar,
            team_debate=team_debate, character_comments=character_comments,
        )
        logger.info(f"✅ デザインAIレポート生成: {path}")
        return {"available": True, "path": path}
    except Exception:
        logger.error("デザインAI生成エラー")
        logger.debug(traceback.format_exc())
        return {"available": False}
