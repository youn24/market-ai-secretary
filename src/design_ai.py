"""
src/design_ai.py — ミセスワタナベ 市場ダッシュボード v5
ガネーシャ🐘＆カワウソ🦦キャラクター完全統合版
"""

import os
import traceback
from pathlib import Path
from src.utils import setup_logger, get_jst_now, get_today_str, get_dirs

logger = setup_logger("design_ai")

# Cloudflare Worker等のCORSプロキシURL（業種別ランキングのザラ場リアルタイム取得用）
# 未設定なら従来どおりサーバー生成JSONのポーリングのみ（朝の値）
CF_PROXY_URL = os.getenv("CF_PROXY_URL", "").strip().rstrip("/")

# ──────────────────────────────────────────
# カラーパレット（ネオン系ダーク）
# ──────────────────────────────────────────
# デザイントークンは design_system が唯一の真実（失敗時は従来値へフォールバック）
try:
    from src.design_system import get_theme as _get_theme
    _T = _get_theme("dark")
except Exception:
    _T = {}
BG      = _T.get("bg", "#06080f")
CARD    = "rgba(255,255,255,0.04)"
CARD2   = "rgba(255,255,255,0.07)"
BORDER  = "rgba(255,255,255,0.09)"
TEXT    = _T.get("text", "#f0f4ff")
MUTED   = _T.get("text_dim", "#5a6a85")
GREEN   = _T.get("up", "#00ff87")
RED     = _T.get("down", "#ff3d5a")
YELLOW  = _T.get("warn", "#ffc837")
BLUE    = _T.get("info", "#00b4ff")
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
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700;900&family=Outfit:wght@400;500;600;700;800;900&display=swap');

*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html{{scroll-behavior:smooth}}
body{{
  font-family:'Noto Sans JP','Outfit',sans-serif;
  background:{BG};
  color:{TEXT};
  font-size:14px;
  line-height:1.65;
  min-height:100vh;
  -webkit-font-smoothing:antialiased;
  text-rendering:optimizeLegibility;
  position:relative;
}}

/* ── プレミアム・タイポグラフィ ── */
.num{{font-family:'Outfit','Noto Sans JP',sans-serif;font-variant-numeric:tabular-nums;letter-spacing:-.5px;font-weight:800}}
.display{{font-family:'Outfit','Noto Sans JP',sans-serif;letter-spacing:-.3px}}
.sect-title{{font-family:'Outfit','Noto Sans JP',sans-serif;font-size:16px;font-weight:800;letter-spacing:.2px;color:{TEXT};display:flex;align-items:center;gap:7px;margin:0 2px 9px}}
.sect-title::before{{content:"";width:4px;height:16px;border-radius:3px;background:linear-gradient(180deg,{PURPLE},{BLUE});display:inline-block}}

/* ── 動くオーロラ背景（固定・最背面）── */
.aurora{{
  position:fixed;inset:0;z-index:-2;overflow:hidden;pointer-events:none;
}}
.aurora::before,.aurora::after{{
  content:"";position:absolute;border-radius:50%;
  filter:blur(70px);opacity:.30;mix-blend-mode:screen;
}}
.aurora::before{{
  width:60vw;height:60vw;top:-15vw;left:-12vw;
  background:radial-gradient(circle,{PURPLE},transparent 65%);
  animation:auroraA 22s ease-in-out infinite alternate;
}}
.aurora::after{{
  width:55vw;height:55vw;top:25vh;right:-15vw;
  background:radial-gradient(circle,{BLUE},transparent 65%);
  animation:auroraB 26s ease-in-out infinite alternate;
}}
.aurora i{{
  position:absolute;width:45vw;height:45vw;bottom:-12vw;left:20vw;border-radius:50%;
  filter:blur(80px);opacity:.18;mix-blend-mode:screen;
  background:radial-gradient(circle,{GREEN},transparent 65%);
  animation:auroraC 30s ease-in-out infinite alternate;
}}
@keyframes auroraA{{from{{transform:translate(0,0) scale(1)}}to{{transform:translate(8vw,6vh) scale(1.15)}}}}
@keyframes auroraB{{from{{transform:translate(0,0) scale(1.1)}}to{{transform:translate(-7vw,-5vh) scale(.9)}}}}
@keyframes auroraC{{from{{transform:translate(0,0) scale(1)}}to{{transform:translate(-6vw,-7vh) scale(1.2)}}}}
@media(prefers-reduced-motion:reduce){{
  .aurora::before,.aurora::after,.aurora i{{animation:none}}
}}

/* グラスカード */
.glass{{
  background:linear-gradient(160deg,rgba(255,255,255,0.06),rgba(255,255,255,0.025));
  backdrop-filter:blur(20px);
  -webkit-backdrop-filter:blur(20px);
  border:1px solid rgba(255,255,255,0.10);
  border-radius:16px;
  box-shadow:inset 0 1px 0 rgba(255,255,255,0.06), 0 8px 30px rgba(0,0,0,0.35);
}}
.glass-sm{{
  background:linear-gradient(160deg,rgba(255,255,255,0.055),rgba(255,255,255,0.02));
  border:1px solid rgba(255,255,255,0.09);
  border-radius:13px;
  box-shadow:inset 0 1px 0 rgba(255,255,255,0.05), 0 4px 16px rgba(0,0,0,0.28);
}}

/* ネオングロー */
.glow-green {{ box-shadow:0 0 20px rgba(0,255,135,.20), 0 0 60px rgba(0,255,135,.08); }}
.glow-red   {{ box-shadow:0 0 20px rgba(255,61,90,.20),  0 0 60px rgba(255,61,90,.08); }}
.glow-yellow{{ box-shadow:0 0 20px rgba(255,200,55,.20), 0 0 60px rgba(255,200,55,.08); }}

/* ラベル共通 */
.label{{display:inline-flex;align-items:center;gap:8px;font-size:11px;font-weight:800;letter-spacing:1.7px;color:{MUTED};text-transform:uppercase;margin-bottom:9px;font-family:'Outfit','Noto Sans JP',sans-serif;padding-bottom:5px;border-bottom:2px solid rgba(255,255,255,.06)}}
.label::before{{content:'';width:4px;height:15px;border-radius:3px;background:currentColor;box-shadow:0 0 10px currentColor;opacity:.9}}
.cat-mkt{{color:#7aa2ff;border-bottom-color:rgba(122,162,255,.28)}}
.cat-news{{color:#35d6c6;border-bottom-color:rgba(53,214,198,.28)}}
.cat-ai{{color:#b98cff;border-bottom-color:rgba(185,140,255,.28)}}
.cat-heat{{color:#ff8a4c;border-bottom-color:rgba(255,138,76,.28)}}
.cat-cal{{color:#4fd67a;border-bottom-color:rgba(79,214,122,.28)}}
.cat-stock{{color:#ffc837;border-bottom-color:rgba(255,200,55,.28)}}

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

/* ── キャラクター（立体アバター＋しっぽ付き吹き出し） ── */
.char-card{{
  display:flex;align-items:center;gap:11px;
  margin-bottom:13px;overflow:visible;
}}
.char-avatar{{
  flex-shrink:0;text-align:center;position:relative;z-index:3;
}}
.char-sprite{{
  width:86px;height:86px;margin:0 auto;border-radius:50%;
  background-repeat:no-repeat;background-size:400% 900%;
  box-shadow:0 13px 24px rgba(0,0,0,.6), 0 3px 8px rgba(0,0,0,.5), 0 0 0 3px rgba(255,255,255,.10);
}}
.char-ganesha .char-sprite{{box-shadow:0 13px 24px rgba(0,0,0,.6),0 3px 8px rgba(0,0,0,.5),0 0 0 3px rgba(255,215,0,.30)}}
.char-otter   .char-sprite{{box-shadow:0 13px 24px rgba(0,0,0,.6),0 3px 8px rgba(0,0,0,.5),0 0 0 3px rgba(196,149,106,.30)}}
.char-name-g{{font-size:9.5px;font-weight:800;color:#FFD700;margin-top:6px;white-space:nowrap;text-shadow:0 1px 3px #000}}
.char-name-o{{font-size:9.5px;font-weight:800;color:#C4956A;margin-top:6px;white-space:nowrap;text-shadow:0 1px 3px #000}}
.char-bubble,.char-bubble-r{{
  flex:1;min-width:0;position:relative;padding:12px 15px;border-radius:15px;
}}
.char-bubble{{
  background:rgba(255,215,0,.08);border:1px solid rgba(255,215,0,.30);border-bottom-left-radius:5px;
}}
.char-bubble::before{{
  content:'';position:absolute;left:-9px;top:26px;width:0;height:0;
  border-top:8px solid transparent;border-bottom:8px solid transparent;
  border-right:10px solid rgba(255,215,0,.32);
}}
.char-bubble-r{{
  background:rgba(196,149,106,.10);border:1px solid rgba(196,149,106,.30);border-bottom-right-radius:5px;
}}
.char-bubble-r::after{{
  content:'';position:absolute;right:-9px;top:26px;width:0;height:0;
  border-top:8px solid transparent;border-bottom:8px solid transparent;
  border-left:10px solid rgba(196,149,106,.32);
}}
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
  .char-card{{gap:8px}}
  .char-sprite{{width:70px;height:70px}}
  .char-bubble::before,.char-bubble-r::after{{display:none}}
}}
"""


# ──────────────────────────────────────────
# セクション 0：ヘッダー
# ──────────────────────────────────────────

def _header(score, today, label, color):
    dot_shadow = f"0 0 8px {color}"
    return f"""
<div style="background:rgba(255,255,255,0.03);border-bottom:1px solid {BORDER};padding:14px 16px">
  <div class="wrap" style="display:flex;align-items:center;justify-content:space-between">
    <div style="display:flex;align-items:center;gap:11px">
      <div style="width:38px;height:38px;background:linear-gradient(135deg,{PURPLE},{BLUE});border-radius:11px;display:flex;align-items:center;justify-content:center;font-size:19px;box-shadow:0 4px 14px {PURPLE}44">📊</div>
      <div>
        <div class="display" style="font-size:19px;font-weight:900;color:{TEXT};line-height:1.05">市場AI秘書</div>
        <div style="font-size:11px;color:{MUTED};margin-top:1px">{today}</div>
      </div>
    </div>
    <div style="display:flex;align-items:center;gap:7px;background:{color}15;border:1px solid {color}40;border-radius:20px;padding:6px 13px">
      <div style="width:8px;height:8px;border-radius:50%;background:{color};box-shadow:{dot_shadow}"></div>
      <span style="font-size:13px;font-weight:800;color:{color}">{label}</span>
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
        return f'<div style="display:flex;align-items:flex-start;gap:10px;padding:10px 0;border-bottom:1px solid {BORDER}"><span style="font-size:19px;flex-shrink:0;margin-top:1px">{ic}</span><div style="font-size:13.5px;line-height:1.8;color:{c}">{txt}</div></div>'

    if   nchg >= 1.0:  r1 = row("📈", GREEN,  f'日経平均 <b class="num" style="font-size:16px">{_fmt(n225,0)}円</b> <span style="color:{MUTED}">前日比</span> <b style="color:{GREEN}">+{nchg:.1f}%</b> — 上昇中です。')
    elif nchg <= -1.0: r1 = row("📉", RED,    f'日経平均 <b class="num" style="font-size:16px">{_fmt(n225,0)}円</b> <span style="color:{MUTED}">前日比</span> <b style="color:{RED}">{nchg:.1f}%</b> — 下落しています。')
    else:              r1 = row("📊", YELLOW, f'日経平均 <b class="num" style="font-size:16px">{_fmt(n225,0)}円</b> <span style="color:{MUTED}">前日比</span> <b style="color:{YELLOW}">{nchg:+.1f}%</b> — ほぼ横ばいです。')

    if   usd > 158: r2 = row("🚨", RED,    f'ドル円 <b class="num" style="font-size:16px">{usd:.2f}円</b> — <b>強い円安。財務省の為替介入リスク</b>に警戒。')
    elif usd > 153: r2 = row("⚠️", ORANGE, f'ドル円 <b class="num" style="font-size:16px">{usd:.2f}円</b>（{uchg:+.2f}%）— 円安傾向。輸入品が高くなりやすい水準。')
    elif usd > 0:   r2 = row("💴", TEXT,   f'ドル円 <b class="num" style="font-size:16px">{usd:.2f}円</b>（{uchg:+.2f}%）— 比較的安定した水準です。')
    else:           r2 = row("💴", MUTED,  'ドル円データを取得中...')

    r3 = row("😨", vc, f'恐怖指数VIX <b class="num" style="font-size:16px">{vix:.1f}</b> <span style="background:rgba(255,255,255,.07);border-radius:4px;padding:1px 6px;font-size:10px;font-weight:700;color:{vc}">{vl}</span> — {vd}')

    return f"""
<div class="glass fade {glow_cls}" style="border-color:{color}33;padding:18px 18px 14px;margin-bottom:14px;position:relative;overflow:hidden">
  <!-- 背景グラデーション -->
  <div style="position:absolute;top:-50px;right:-50px;width:170px;height:170px;border-radius:50%;background:radial-gradient(circle,{color}22,transparent 70%);pointer-events:none"></div>

  <div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:13px">
    <div>
      <div class="label">今日の相場まとめ</div>
      <div class="display" style="font-size:28px;font-weight:900;color:{color};line-height:1.15">{emoji} {label}</div>
    </div>
    <div style="text-align:right">
      <div class="num" style="font-size:42px;font-weight:900;color:{color};line-height:1;text-shadow:0 0 24px {color}55">{score:+.2f}</div>
      <div style="font-size:10px;color:{MUTED};margin-top:2px">AIスコア / −3〜+3</div>
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
        note_html = f'<div style="font-size:10px;color:{MUTED};margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{note}</div>' if note else ""
        return f"""<div class="glass-sm fade" style="padding:15px 13px;position:relative;overflow:hidden">
  <div style="position:absolute;top:0;left:0;width:100%;height:3px;background:{val_color};opacity:.85"></div>
  <div style="font-size:11px;color:{MUTED};margin-bottom:6px;display:flex;align-items:center;gap:6px;font-weight:600"><span style="font-size:14px">{icon}</span>{title}</div>
  <div class="num" style="font-size:27px;font-weight:900;color:{val_color};line-height:1.05">{value}</div>
  <div style="font-size:12px;color:{chg_color};font-weight:800;margin-top:3px">{_arrow(change)} {abs(change):.2f}%</div>
  <div style="height:3px;background:rgba(255,255,255,.06);border-radius:2px;margin-top:7px"><div style="width:{bar_w}%;height:100%;background:{bar_c};border-radius:2px;box-shadow:0 0 8px {bar_c}66"></div></div>
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
        chips.append(f"""<div style="display:inline-flex;flex-direction:column;align-items:center;background:linear-gradient(160deg,rgba(255,255,255,.05),rgba(255,255,255,.02));border:1px solid {BORDER};border-radius:12px;padding:10px 14px;min-width:78px;flex-shrink:0">
  <div style="font-size:16px">{icon}</div>
  <div style="font-size:10px;color:{MUTED};margin:3px 0;white-space:nowrap">{name}</div>
  <div class="num" style="font-size:14px;font-weight:800;color:{TEXT}">{_fmt(val)}</div>
  <div style="font-size:11px;color:{c};font-weight:800;margin-top:1px">{_arrow(chg)}{abs(chg):.1f}%</div>
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

def _categorize_labels(html: str) -> str:
    """各セクション見出し(.label)にカテゴリ色クラスを自動付与（キーワード/絵文字で判定）"""
    import re
    rules = [
        ("cat-stock", ("ランキング", "銘柄", "デイトレ", "ADR", "PTS", "時間外", "株ドラゴン", "🐉", "🌙", "💴")),
        ("cat-news",  ("ニュース", "📰")),
        ("cat-ai",    ("AI", "予測", "シナリオ", "クロス", "シグナル", "スキャナー", "🤖", "🎯", "🔬", "🔎", "🔭")),
        ("cat-heat",  ("ヒートマップ", "強弱", "🔥")),
        ("cat-cal",   ("カレンダー", "イベント", "経済指標", "📅")),
    ]

    def cls_of(text):
        for cls, keys in rules:
            if any(k in text for k in keys):
                return cls
        return "cat-mkt"

    def repl(m):
        return f'<div class="label {cls_of(m.group(2))}"{m.group(1)}>{m.group(2)}</div>'

    return re.sub(r'<div class="label"([^>]*)>(.*?)</div>', repl, html, flags=re.S)


def _char_avatar(col: int, row: int, b64: str) -> str:
    """スプライト1コマを丸く切り抜き、影で浮かせた立体アバターを返す（4列×9行）"""
    x = col * 100 / 3
    y = row * 100 / 8
    return (
        f'<div class="char-sprite" style="'
        f"background-image:url('data:image/png;base64,{b64}');"
        f'background-position:{x:.2f}% {y:.2f}%"></div>'
    )


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

        # 本物のキャラ画像（気分別スプライトを丸く切り抜き・立体表示）。無ければSVGフォールバック
        mood = cc.get("mood", "neutral")
        gane_av, otter_av = _GANESHA_SVG, _OTTER_SVG
        try:
            from src.character_commentary import (
                _load_sprite_b64, OTTER_MOOD_MAP, GANESHA_MOOD_MAP,
            )
            _b64 = _load_sprite_b64()
            if _b64:
                gc, gr = GANESHA_MOOD_MAP.get(mood, GANESHA_MOOD_MAP["neutral"])
                oc, orw = OTTER_MOOD_MAP.get(mood, OTTER_MOOD_MAP["neutral"])
                gane_av  = _char_avatar(gc, gr, _b64)
                otter_av = _char_avatar(oc, orw, _b64)
        except Exception:
            pass

        char_html = f"""
<div style="margin-top:10px">
  <!-- 🐘 ガネーシャ -->
  <div class="char-card char-ganesha">
    <div class="char-avatar">
      {gane_av}
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
      {otter_av}
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
# セクション 8.5：業種別ヒートマップ（リアルタイム）
# ──────────────────────────────────────────

def _sector_heatmap_live():
    """TradingView Stock Heatmap（業種別）。日本株/米国セクターをタブ切替・リアルタイム描画。"""
    def widget(ds):
        return f'''<div class="tradingview-widget-container" style="height:420px">
      <div class="tradingview-widget-container__widget" style="height:100%"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-stock-heatmap.js" async>
      {{"dataSource":"{ds}","blockSize":"market_cap_basic","blockColor":"change","grouping":"sector","locale":"ja","colorTheme":"dark","hasTopBar":false,"isDataSetEnabled":false,"isZoomEnabled":true,"hasSymbolTooltip":true,"isMonoSize":false,"width":"100%","height":"100%"}}
      </script>
    </div>'''
    return f"""
<div style="margin-bottom:12px">
  <div class="label" style="padding:0 2px;margin-bottom:6px">🔥 業種別ヒートマップ（リアルタイム）</div>
  <div style="display:flex;gap:6px;margin-bottom:8px">
    <button type="button" onclick="shmTab(this,'jp')" class="shm-btn shm-on">🇯🇵 日本株（東証）</button>
    <button type="button" onclick="shmTab(this,'us')" class="shm-btn">🇺🇸 米国セクター</button>
  </div>
  <div id="shm-jp" style="border-radius:14px;overflow:hidden;border:1px solid {BORDER}">{widget("NIKKEI225")}</div>
  <div id="shm-us" style="display:none;border-radius:14px;overflow:hidden;border:1px solid {BORDER}">{widget("SPX500")}</div>
  <div style="font-size:10px;color:{MUTED};margin-top:6px">💡 タイルの色＝今の上がり下がり（緑=上昇・赤=下落）／ 大きさ＝会社の規模。緑が多い業種に今お金が集まっています</div>
</div>
<style>
.shm-btn{{flex:1;background:rgba(255,255,255,.04);border:1px solid {BORDER};color:{MUTED};border-radius:9px;padding:8px;font-size:12px;font-weight:700;cursor:pointer;font-family:inherit;transition:all .2s}}
.shm-btn.shm-on{{background:rgba(0,180,255,.12);border-color:{BLUE};color:{BLUE}}}
</style>
<script>
function shmTab(btn, which){{
  document.getElementById('shm-jp').style.display = (which==='jp')?'block':'none';
  document.getElementById('shm-us').style.display = (which==='us')?'block':'none';
  document.querySelectorAll('.shm-btn').forEach(function(b){{b.classList.remove('shm-on');}});
  btn.classList.add('shm-on');
  window.dispatchEvent(new Event('resize'));
}}
</script>"""


# ──────────────────────────────────────────
# セクション 8.6：業種別ランキング表（準リアルタイム・自動更新）
# ──────────────────────────────────────────

def _sector_ranking(ranking: dict):
    """日本の業種別ランキング表。初期はサーバー生成、JSで60秒ごとに自動更新。"""
    rk = ranking or {}
    if not rk.get("available"):
        return ""
    rows = rk.get("ranking", [])
    gen  = rk.get("generated_at", "")
    state = rk.get("market_state", "")

    def row_html(r):
        pct = r.get("pct", 0) or 0
        up  = pct > 0
        flat = pct == 0
        col = GREEN if up else (RED if not flat else MUTED)
        arrow = "▲" if up else ("▼" if not flat else "－")
        chg = r.get("chg", 0) or 0
        return (f'<tr>'
                f'<td style="text-align:center;color:{MUTED};font-weight:700">{r.get("rank","")}</td>'
                f'<td style="font-weight:700;color:{TEXT}">{r.get("name","")}</td>'
                f'<td style="text-align:right;color:{TEXT};font-variant-numeric:tabular-nums">{r.get("price",0):,.1f}</td>'
                f'<td style="text-align:right;color:{col};font-weight:700;font-variant-numeric:tabular-nums">{arrow}{abs(chg):,.1f}</td>'
                f'<td style="text-align:right;color:{col};font-weight:800;font-variant-numeric:tabular-nums">{pct:+.2f}%</td>'
                f'</tr>')

    body = "".join(row_html(r) for r in rows)
    cf_proxy = CF_PROXY_URL  # JSに埋め込むCORSプロキシURL（空ならポーリングのみ）
    live_note = ("ザラ場中（9:00〜15:30）は約30秒ごとにリアルタイム更新されます"
                 if cf_proxy else "約1分ごとに自動更新されます")

    return f"""
<div style="margin-bottom:12px">
  <div class="label" style="padding:0 2px;margin-bottom:6px">📊 業種別ランキング（自動更新）</div>
  <div class="glass" style="padding:12px 12px 14px">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
      <span id="srk-state" style="font-size:10px;color:{BLUE};font-weight:700">{state}</span>
      <span id="srk-time" style="font-size:9px;color:{MUTED}">{gen} 時点</span>
    </div>
    <table style="width:100%;border-collapse:collapse;font-size:11px">
      <thead>
        <tr style="color:{MUTED};font-size:9px;border-bottom:1px solid {BORDER}">
          <th style="text-align:center;padding:4px 2px;font-weight:700">順位</th>
          <th style="text-align:left;padding:4px 2px;font-weight:700">業種</th>
          <th style="text-align:right;padding:4px 2px;font-weight:700">現在値</th>
          <th style="text-align:right;padding:4px 2px;font-weight:700">前日比</th>
          <th style="text-align:right;padding:4px 2px;font-weight:700">前日比%</th>
        </tr>
      </thead>
      <tbody id="srk-body">{body}</tbody>
    </table>
    <div style="font-size:10px;color:{MUTED};margin-top:8px">💡 緑▲＝上昇／赤▼＝下落。上位の業種に今お金が集まっています。{live_note}</div>
  </div>
</div>
<style>
#srk-body tr{{border-bottom:1px solid rgba(255,255,255,.04)}}
#srk-body td{{padding:6px 2px}}
@keyframes srkFlash{{0%{{background:rgba(0,180,255,.18)}}100%{{background:transparent}}}}
.srk-upd{{animation:srkFlash 1s ease}}
</style>
<script>
(function(){{
  var GREEN="{GREEN}", RED="{RED}", MUTED="{MUTED}", TEXT="{TEXT}";
  function render(d){{
    if(!d || !d.ranking) return;
    var body=document.getElementById('srk-body');
    if(!body) return;
    body.innerHTML = d.ranking.map(function(r){{
      var pct=r.pct||0, up=pct>0, flat=pct===0;
      var col= up?GREEN:(flat?MUTED:RED);
      var arrow= up?'▲':(flat?'－':'▼');
      var chg=Math.abs(r.chg||0);
      return '<tr>'
        +'<td style="text-align:center;color:'+MUTED+';font-weight:700">'+r.rank+'</td>'
        +'<td style="font-weight:700;color:'+TEXT+'">'+r.name+'</td>'
        +'<td style="text-align:right;color:'+TEXT+';font-variant-numeric:tabular-nums">'+r.price.toLocaleString(undefined,{{minimumFractionDigits:1,maximumFractionDigits:1}})+'</td>'
        +'<td style="text-align:right;color:'+col+';font-weight:700;font-variant-numeric:tabular-nums">'+arrow+chg.toLocaleString(undefined,{{minimumFractionDigits:1,maximumFractionDigits:1}})+'</td>'
        +'<td style="text-align:right;color:'+col+';font-weight:800;font-variant-numeric:tabular-nums">'+(pct>=0?'+':'')+pct.toFixed(2)+'%</td>'
        +'</tr>';
    }}).join('');
    body.classList.remove('srk-upd'); void body.offsetWidth; body.classList.add('srk-upd');
    var st=document.getElementById('srk-state'), tm=document.getElementById('srk-time');
    if(st && d.market_state) st.textContent=d.market_state;
    if(tm && d.generated_at) tm.textContent=d.generated_at+' 時点';
  }}
  function poll(){{
    fetch('./sector_ranking.json?cb='+Date.now()).then(function(r){{return r.json();}}).then(render).catch(function(){{}});
  }}
  // ── ザラ場リアルタイム（Cloudflare Worker経由でYahooを直接取得）──
  var PROXY="{cf_proxy}";
  var SYMS=["1617.T","1618.T","1619.T","1620.T","1621.T","1622.T","1623.T","1624.T","1625.T","1626.T","1627.T","1628.T","1629.T","1630.T","1631.T","1632.T","1633.T"];
  var NAMES={{"1617.T":"食品","1618.T":"エネルギー資源","1619.T":"建設・資材","1620.T":"素材・化学","1621.T":"医薬品","1622.T":"自動車・輸送機","1623.T":"鉄鋼・非鉄","1624.T":"機械","1625.T":"電機・精密","1626.T":"情報通信・サービス他","1627.T":"電力・ガス","1628.T":"運輸・物流","1629.T":"商社・卸売","1630.T":"小売","1631.T":"銀行","1632.T":"金融(除く銀行)","1633.T":"不動産"}};
  function jstNow(){{var n=new Date();return new Date(n.getTime()+(n.getTimezoneOffset()+540)*60000);}}
  function isZaraba(){{var j=jstNow(),dy=j.getDay();if(dy===0||dy===6)return false;var hm=j.getHours()*100+j.getMinutes();return (hm>=900&&hm<=1130)||(hm>=1230&&hm<=1530);}}
  function tstr(){{var j=jstNow();function z(x){{return(x<10?'0':'')+x;}}return j.getFullYear()+'-'+z(j.getMonth()+1)+'-'+z(j.getDate())+' '+z(j.getHours())+':'+z(j.getMinutes())+' JST';}}
  function live(){{
    var spark='https://query1.finance.yahoo.com/v8/finance/spark?symbols='+SYMS.join(',')+'&range=1d&interval=1d';
    fetch(PROXY+'?url='+encodeURIComponent(spark)).then(function(r){{return r.json();}}).then(function(j){{
      var rows=[];
      SYMS.forEach(function(s){{
        var d=j[s]; if(!d) return;
        var c=(d.close&&d.close.length)?d.close[d.close.length-1]:null;
        var p=d.chartPreviousClose;
        if(c==null||!p) return;
        var pct=(c-p)/p*100; if(Math.abs(pct)>18) return;
        rows.push({{name:NAMES[s],price:c,chg:c-p,pct:pct}});
      }});
      if(!rows.length) return;
      rows.sort(function(a,b){{return b.pct-a.pct;}});
      rows.forEach(function(r,i){{r.rank=i+1;}});
      render({{ranking:rows,market_state:'🔴 ザラ場・リアルタイム',generated_at:tstr()}});
    }}).catch(function(){{}});
  }}
  function tick(){{ if(PROXY && isZaraba()) live(); else poll(); }}
  tick();
  setInterval(tick, 30000);
}})();
</script>"""


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
    # prediction_tracker.run() の戻り値は stats 構造（stats["10d"]["rate"] 等）
    stats = pt.get("stats", {})
    d10   = stats.get("10d", {})
    n     = int(d10.get("total", 0) or 0)
    hits  = int(d10.get("correct", 0) or 0)
    if not n: return ""

    acc   = float(d10.get("rate") or 0)
    miss  = n - hits
    bar_c = GREEN if acc >= 60 else (YELLOW if acc >= 45 else RED)
    grade = "A" if acc>=70 else ("B" if acc>=60 else ("C" if acc>=50 else "D"))
    grade_c = GREEN if grade=="A" else (BLUE if grade=="B" else (YELLOW if grade=="C" else RED))

    # Brierスコア（確信度の信頼性）— 0=完璧 / 0.25=勘 / 高いほど過信
    brier = stats.get("brier_30d")
    brier_html = ""
    if brier is not None:
        if   brier <= 0.12: bl, bc = "優秀",     GREEN
        elif brier <= 0.20: bl, bc = "良好",     BLUE
        elif brier <= 0.25: bl, bc = "普通",     YELLOW
        else:               bl, bc = "過信ぎみ", ORANGE
        brier_html = f"""
    <div style="display:flex;align-items:center;gap:8px;margin-top:9px;padding-top:9px;border-top:1px solid {BORDER}">
      <span style="font-size:10px;color:{MUTED}">確信度の信頼性（Brier）</span>
      <span style="font-size:13px;font-weight:800;color:{bc}">{brier:.3f}</span>
      <span style="font-size:9px;color:{bc};background:{bc}1a;padding:1px 6px;border-radius:4px">{bl}</span>
      <span style="font-size:9px;color:{MUTED};margin-left:auto">0=完璧 / 0.25=勘 / 大=過信</span>
    </div>"""

    return f"""
<div style="margin-bottom:12px">
  <div class="label" style="padding:0 2px;margin-bottom:6px">🎯 AIの予測精度（直近10日）</div>
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
        <div style="font-size:10px;color:{MUTED};margin-top:3px">直近10日 {n}回の予測</div>
      </div>
      <div style="width:38px;height:38px;border-radius:50%;border:2px solid {grade_c};display:flex;align-items:center;justify-content:center;font-size:18px;font-weight:900;color:{grade_c}">{grade}</div>
    </div>{brier_html}
    <div style="font-size:10px;color:{MUTED};margin-top:9px">📖 毎日翌日の相場を予測し、翌朝に答え合わせした成績です。Brierは「自信の正確さ」を測る指標です</div>
  </div>
</div>"""


def _crosscheck(cross_check):
    """情報源クロスチェック：複数手法の方向一致度＝信頼度"""
    cc = cross_check or {}
    if not cc.get("available"): return ""
    sources   = cc.get("sources", [])
    agreement = cc.get("agreement", 0) or 0
    pct       = int(agreement * 100)
    conflict  = cc.get("conflict")
    verdict_ja = cc.get("verdict_ja", "")
    level     = cc.get("level", "")
    emoji     = cc.get("emoji", "")
    bar_c = GREEN if agreement >= 0.66 else (YELLOW if agreement >= 0.5 else RED)

    dir_icon = {"上昇": "📈", "下落": "📉", "中立": "➡️"}
    dir_col  = {"上昇": GREEN, "下落": RED, "中立": YELLOW}
    chips = "".join(
        f"""<div style="display:flex;align-items:center;gap:5px;background:rgba(255,255,255,.04);border:1px solid {BORDER};border-radius:8px;padding:6px 9px">
      <span style="font-size:10px;color:{MUTED}">{s.get('name','')}</span>
      <span style="font-size:11px;font-weight:700;color:{dir_col.get(s.get('dir_ja'),MUTED)}">{dir_icon.get(s.get('dir_ja'),'')}{s.get('dir_ja','')}</span>
    </div>"""
        for s in sources
    )
    note = ("複数の分析が同じ方向を示しています → 信頼度が高い相場です"
            if not conflict else
            "分析手法によって見解が割れています → いつもより慎重に判断しましょう")
    note_c = GREEN if not conflict else ORANGE

    return f"""
<div style="margin-bottom:12px">
  <div class="label" style="padding:0 2px;margin-bottom:6px">🔎 情報源クロスチェック（信頼度）</div>
  <div class="glass" style="padding:14px">
    <div style="display:flex;align-items:center;gap:14px;margin-bottom:10px">
      <div style="text-align:center;min-width:70px">
        <div style="font-size:34px;font-weight:900;color:{bar_c};line-height:1;text-shadow:0 0 20px {bar_c}55">{pct}%</div>
        <div style="font-size:9px;color:{MUTED};margin-top:2px">一致度</div>
      </div>
      <div style="flex:1">
        <div style="font-size:13px;font-weight:800;color:{bar_c};margin-bottom:4px">{emoji} {level}・総合「{verdict_ja}」</div>
        <div style="background:rgba(255,255,255,.06);border-radius:4px;height:7px;overflow:hidden">
          <div style="width:{pct}%;height:100%;background:{bar_c};border-radius:4px;box-shadow:0 0 10px {bar_c}66"></div>
        </div>
      </div>
    </div>
    <div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:9px">{chips}</div>
    <div style="font-size:10px;color:{note_c};background:{note_c}14;padding:6px 9px;border-radius:6px">💡 {note}</div>
  </div>
</div>"""


# ──────────────────────────────────────────
# セクション 12b：手法シグナル・スキャナー
# ──────────────────────────────────────────

def _setups(setups):
    sc = setups or {}
    if not sc.get("available"):
        return ""
    items = sc.get("setups", [])
    if not items:
        return ""

    dir_badge = {
        "buy":     (GREEN,  "買い目線"),
        "sell":    (RED,    "売り目線"),
        "caution": (RED,    "警戒"),
        "neutral": (YELLOW, "中立"),
    }
    cards = []
    for s in items:
        c = s.get("color", YELLOW)
        bc, btxt = dir_badge.get(s.get("direction", "neutral"), (YELLOW, "中立"))

        wk_html = ""
        if s.get("weekly_label"):
            wk_html = f'<div style="font-size:10.5px;color:{MUTED};margin-bottom:5px">{s["weekly_label"]}</div>'

        mtf_html = ""
        if s.get("mtf_note"):
            mc = s.get("mtf_color", YELLOW)
            mtf_html = f'<div style="font-size:10.5px;font-weight:700;color:{mc};margin-bottom:5px">{s["mtf_note"]}</div>'

        cards.append(f"""<div class="glass-sm fade" style="padding:12px;border-left:3px solid {c}">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:5px">
    <span style="font-size:13px;font-weight:900;color:{TEXT}">{s.get('name','')}</span>
    <span class="badge" style="background:{bc}1a;color:{bc};border:1px solid {bc}55">{btxt}</span>
    <span style="margin-left:auto;font-size:13px;font-weight:800;color:{c}">{s.get('label','')}</span>
  </div>
  {wk_html}
  <div style="font-size:11.5px;line-height:1.7;color:{TEXT};margin-bottom:5px">{s.get('desc','')}</div>
  {mtf_html}
  <div style="font-size:11px;line-height:1.65;color:{BLUE};background:rgba(0,180,255,.07);padding:6px 9px;border-radius:7px">💡 {s.get('tip','')}</div>
</div>""")

    return f"""
<div style="margin-bottom:12px">
  <div class="label" style="padding:0 2px;margin-bottom:6px">📐 手法シグナル・スキャナー（週足×日足 マルチタイムフレーム）</div>
  <div style="display:flex;flex-direction:column;gap:8px">{"".join(cards)}</div>
  <div style="font-size:9px;color:{MUTED};margin-top:5px;padding:0 2px">押し目買い・ブレイク・売られすぎ等を機械的に判定。週足の大きな流れと日足シグナルの一致度も表示。教科書的なシグナルの有無を示すものです。</div>
</div>"""


# ──────────────────────────────────────────
# セクション 12c：TradingView 高度ウィジェット
# （通貨強弱ヒートマップ＋経済指標カレンダー）
# ──────────────────────────────────────────

def _tv_advanced():
    return f"""
<div style="margin-bottom:12px">
  <div class="label" style="padding:0 2px;margin-bottom:6px">🔥 通貨の強弱ヒートマップ（リアルタイム）</div>
  <div class="glass" style="overflow:hidden;border-radius:14px;border:1px solid {BORDER}">
    <div class="tradingview-widget-container">
      <div class="tradingview-widget-container__widget"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-forex-heat-map.js" async>
      {{"width":"100%","height":340,"currencies":["EUR","USD","JPY","GBP","AUD","CAD","CHF","CNY"],"isTransparent":true,"colorTheme":"dark","locale":"ja"}}
      </script>
    </div>
  </div>
  <div style="font-size:9px;color:{MUTED};margin:4px 2px 12px">緑＝その通貨が強い／赤＝弱い。<b style="color:{TEXT}">JPY（円）の行が赤いほど円安</b>、緑なら円高です。</div>

  <div class="label" style="padding:0 2px;margin-bottom:6px">📅 経済指標カレンダー（重要イベント）</div>
  <div class="glass" style="overflow:hidden;border-radius:14px;border:1px solid {BORDER}">
    <div class="tradingview-widget-container">
      <div class="tradingview-widget-container__widget"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-events.js" async>
      {{"width":"100%","height":380,"colorTheme":"dark","isTransparent":true,"locale":"ja","importanceFilter":"0,1","countryFilter":"us,jp,eu,gb"}}
      </script>
    </div>
  </div>
  <div style="font-size:9px;color:{MUTED};margin:4px 2px 0">★が多い指標ほど相場が動きやすい。<b style="color:{TEXT}">発表の前後はトレードを控えめに</b>するのがプロの基本です。</div>
</div>"""


# ──────────────────────────────────────────
# セクション 12d：ドル円の見方（常設・初心者ガイド）
# ──────────────────────────────────────────

def _usdjpy_guide(prices):
    usd = _p("USDJPY=X", prices)
    # 現在地のひとこと
    if   usd > 158: loc = (RED,    f"今は {usd:.1f}円 — かなりの円安。介入リスクに警戒する水準。")
    elif usd > 152: loc = (ORANGE, f"今は {usd:.1f}円 — 円安ぎみ。輸入品が高くなりやすい。")
    elif usd > 0:   loc = (GREEN,  f"今は {usd:.1f}円 — 比較的おだやかな水準。")
    else:           loc = (MUTED,  "現在値を取得中…")

    movers = [
        ("📊", "日米の金利差", BLUE,
         "アメリカの金利が日本より高いほど、利息の高いドルが買われて<b>円安</b>に。"
         "「米金利↑＝ドル円↑（円安）」が基本。"),
        ("🌊", "リスクオン・オフ", PURPLE,
         "世界が強気（リスクオン）だと円が売られ<b>円安</b>、"
         "不安（リスクオフ）だと安全資産の円が買われ<b>円高</b>になりやすい。"),
        ("🏛", "為替介入", RED,
         "急激な円安が進むと、日本の財務省・日銀が<b>円買い介入</b>することがある。"
         "155〜160円超は要警戒ゾーン。"),
    ]
    mv_html = "".join(f"""<div style="display:flex;align-items:flex-start;gap:9px;padding:9px 0;border-bottom:1px solid {BORDER}">
  <span style="font-size:18px;flex-shrink:0">{ic}</span>
  <div>
    <div style="font-size:12px;font-weight:800;color:{c};margin-bottom:2px">{title}</div>
    <div style="font-size:11px;line-height:1.7;color:{TEXT}">{desc}</div>
  </div>
</div>""" for ic, title, c, desc in movers)

    return f"""
<div style="margin-bottom:12px">
  <div class="label" style="padding:0 2px;margin-bottom:6px">💴 ドル円の見方（はじめての方へ）</div>
  <div class="glass" style="padding:13px 14px">
    <div style="font-size:12px;line-height:1.7;color:{TEXT};margin-bottom:10px">
      <b style="color:{loc[0]}">ドル円</b>は「1ドル＝何円か」。
      <b>数字が大きい＝円安</b>（円の価値が下がる）、<b>小さい＝円高</b>です。
    </div>
    <div style="background:{loc[0]}14;border:1px solid {loc[0]}44;border-radius:9px;padding:8px 11px;font-size:12px;font-weight:700;color:{loc[0]};margin-bottom:11px">📍 {loc[1]}</div>

    <div style="font-size:11px;font-weight:800;color:{MUTED};margin-bottom:2px">何で動く？（3つの力）</div>
    {mv_html}

    <div style="margin-top:10px;font-size:11px;line-height:1.7;color:{BLUE};background:rgba(0,180,255,.07);padding:8px 11px;border-radius:8px">
      🧭 <b>プロのコツ</b>：まず週足で大きな方向を見て、日足で「節目（過去に何度も止まった価格）」を確認。
      指標発表の直前直後は動きが荒れるので、無理に飛び込まないこと。
    </div>
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


def _ensemble_section(ensemble: dict) -> str:
    """アンサンブル予測の視覚カード"""
    if not ensemble or not ensemble.get("available"):
        return ""
    direction   = ensemble.get("direction", "neutral")
    agree_pct   = ensemble.get("agreement_pct", 0)
    confidence  = ensemble.get("confidence", "low")
    brier       = ensemble.get("brier_score")
    members     = ensemble.get("members", [])

    dir_icon  = {"bull": "📈", "bear": "📉", "neutral": "➡️"}.get(direction, "➡️")
    dir_label = {"bull": "強気", "bear": "弱気", "neutral": "中立"}.get(direction, direction)
    conf_color = {"high": "#3fb950", "mid": "#d29922", "low": "#f85149"}.get(confidence, "#8b949e")
    bar_w = int(agree_pct)

    members_html = "".join(
        f'<div style="display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid rgba(255,255,255,.05)">'
        f'<span style="color:#8b949e;font-size:11px">{m["name"]}</span>'
        f'<span style="font-size:11px;color:{"#3fb950" if m["direction"]=="bull" else "#f85149" if m["direction"]=="bear" else "#8b949e"}">'
        f'{"▲" if m["direction"]=="bull" else "▼" if m["direction"]=="bear" else "—"} {m["direction"]}'
        f'</span></div>'
        for m in members
    )

    brier_s = f'<span style="color:#8b949e;font-size:11px">Brier={brier:.3f}</span>' if brier is not None else ""

    return f'''<section class="fade" style="background:#0d1117;border:1px solid #30363d;border-radius:12px;padding:14px;margin:10px 0">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
    <span style="font-size:18px">{dir_icon}</span>
    <span style="font-weight:700;font-size:14px">アンサンブル予測</span>
    <span style="margin-left:auto;background:{conf_color}22;border:1px solid {conf_color};color:{conf_color};border-radius:6px;padding:2px 8px;font-size:11px">{confidence.upper()}</span>
    {brier_s}
  </div>
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
    <span style="font-size:22px;font-weight:900;color:{conf_color}">{dir_label}</span>
    <div style="flex:1;background:#21262d;border-radius:4px;height:8px;overflow:hidden">
      <div style="width:{bar_w}%;height:100%;background:{conf_color};border-radius:4px"></div>
    </div>
    <span style="color:{conf_color};font-weight:700">{agree_pct:.0f}%</span>
  </div>
  <div style="font-size:11px;color:#8b949e;margin-bottom:6px">各手法の方向</div>
  {members_html}
</section>'''


def _dossier_section(stock_dossier: dict) -> str:
    """銘柄カルテ上位3件のHTMLカード"""
    if not stock_dossier or not stock_dossier.get("available"):
        return ""
    dossiers = [d for d in stock_dossier.get("dossiers", []) if d.get("confluence", 0) >= 5][:3]
    if not dossiers:
        return ""

    cards = []
    for d in dossiers:
        code    = d.get("code", "")
        name    = d.get("name", "")
        close   = d.get("close")
        chg     = d.get("change_pct")
        target  = d.get("target")
        upside  = d.get("upside")
        conf    = d.get("confluence", 0)
        tv_link = d.get("tv_link", "")
        entry   = d.get("entry_zone", "")
        stop    = d.get("stop_loss", "")
        rr      = d.get("risk_reward", "")

        chg_color = "#3fb950" if (chg or 0) >= 0 else "#f85149"
        chg_s  = f"{chg:+.2f}%" if chg is not None else "---"
        close_s = f"{close:,.0f}円" if close else "---"
        bar_w  = int(conf / 10 * 100)

        target_row = (
            f'<div style="display:flex;justify-content:space-between"><span style="color:#8b949e;font-size:11px">目標株価</span>'
            f'<span style="font-size:11px">{target:,.0f}円 (+{upside:.0f}%)</span></div>'
            if target else ""
        )
        tv_btn = (
            f'<a href="{tv_link}" target="_blank" style="display:inline-block;margin-top:8px;'
            f'padding:4px 10px;background:#1e2a3a;border:1px solid #388bfd;color:#58a6ff;'
            f'border-radius:6px;font-size:11px;text-decoration:none">📈 TradingViewで確認</a>'
            if tv_link else ""
        )

        cards.append(f'''<div style="background:#161b22;border:1px solid #30363d;border-radius:10px;padding:12px;margin-bottom:8px">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
    <span style="font-weight:700">{name}</span>
    <span style="color:#8b949e;font-size:11px">({code})</span>
    <span style="margin-left:auto;font-size:13px;font-weight:700">{close_s}</span>
    <span style="color:{chg_color};font-size:12px">{chg_s}</span>
  </div>
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
    <span style="font-size:11px;color:#8b949e">合わせ技</span>
    <div style="flex:1;background:#21262d;border-radius:3px;height:6px;overflow:hidden">
      <div style="width:{bar_w}%;height:100%;background:#3fb950;border-radius:3px"></div>
    </div>
    <span style="font-size:12px;font-weight:700;color:#3fb950">{conf}/10</span>
  </div>
  {target_row}
  <div style="display:flex;justify-content:space-between;margin-top:4px">
    <span style="color:#8b949e;font-size:11px">エントリー</span>
    <span style="font-size:11px">{entry[:30]}</span>
  </div>
  <div style="display:flex;justify-content:space-between">
    <span style="color:#f85149;font-size:11px">損切り</span>
    <span style="font-size:11px">{stop[:30]}</span>
  </div>
  <div style="display:flex;justify-content:space-between">
    <span style="color:#8b949e;font-size:11px">RR</span>
    <span style="font-size:11px">{rr[:25]}</span>
  </div>
  {tv_btn}
</div>''')

    return f'''<section class="fade" style="background:#0d1117;border:1px solid #30363d;border-radius:12px;padding:14px;margin:10px 0">
  <div style="font-weight:700;font-size:14px;margin-bottom:10px">🎯 今日の注目銘柄カルテ（合わせ技上位）</div>
  {''.join(cards)}
</section>'''


# ──────────────────────────────────────────
# メイン生成関数
# ──────────────────────────────────────────

def _kabudragon_section(kd):
    """株ドラゴン・デイトレランキング（値上がり/S高/出来高急増/値下がり）"""
    kd = kd or {}
    if not kd.get("available"):
        return ""
    rankings = kd.get("rankings", {})
    if not any(v.get("items") for v in rankings.values()):
        return ""

    accent = {"age": GREEN, "stopdaka": ORANGE, "dekizou": CYAN, "sage": RED}
    blocks = []
    for key in ("age", "stopdaka", "dekizou", "sage"):
        v = rankings.get(key) or {}
        items = v.get("items", [])
        if not items:
            continue
        c = accent.get(key, YELLOW)
        rows = []
        for it in items[:5]:
            pct = it.get("chg_pct")
            pc  = _col(pct or 0)
            pct_s = f"{pct:+.1f}%" if pct is not None else "—"
            rows.append(f"""<div style="display:flex;align-items:center;gap:7px;padding:6px 0;border-bottom:1px solid {BORDER}">
  <span style="font-size:10px;font-weight:800;color:{MUTED};min-width:14px">{it.get('rank','')}</span>
  <span style="font-size:9.5px;color:{MUTED};background:rgba(255,255,255,.05);border-radius:4px;padding:1px 5px;min-width:38px;text-align:center">{it.get('code','')}</span>
  <span style="font-size:11.5px;font-weight:700;color:{TEXT};flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{it.get('name','')}</span>
  <span class="num" style="font-size:12px;font-weight:800;color:{pc}">{pct_s}</span>
</div>""")
        blocks.append(f"""<div class="glass-sm fade" style="padding:12px;border-top:3px solid {c}">
  <div style="font-size:12.5px;font-weight:900;color:{c};margin-bottom:2px">{v.get('icon','')} {v.get('label','')}</div>
  <div style="font-size:9.5px;color:{MUTED};margin-bottom:6px">{v.get('note','')}</div>
  {"".join(rows)}
</div>""")

    if not blocks:
        return ""
    return f"""
<div style="margin-bottom:12px">
  <div class="label" style="padding:0 2px;margin-bottom:6px">🐉 株ドラゴン・デイトレランキング</div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">{"".join(blocks)}</div>
  <div style="font-size:9px;color:{MUTED};margin-top:5px;padding:0 2px">出典: 株ドラゴン（kabudragon.com）。デイトレーダーが注目する4大ランキングの上位銘柄です。</div>
</div>"""


def _us_afterhours_section(us_ah):
    """米国主要株の時間外ムーバー（日本のザラ場への先行シグナル）"""
    us_ah = us_ah or {}
    if not us_ah.get("available"):
        return ""
    movers = us_ah.get("movers", [])
    if not movers:
        return f"""
<div class="glass-sm fade" style="padding:10px 12px;margin-bottom:12px;font-size:11px;color:{MUTED}">🇺🇸 米国時間外: 主要銘柄チェック済み — ±1%超の大きな変動なし（静かな夜）</div>"""

    rows = []
    for m in movers[:6]:
        c = _col(m.get("chg_pct") or 0)
        price_s = f"${m['price']:,.2f}" if m.get("price") else "—"
        rows.append(f"""<div style="display:flex;align-items:center;gap:8px;padding:7px 0;border-bottom:1px solid {BORDER}">
  <span style="font-size:9.5px;color:{MUTED};background:rgba(255,255,255,.05);border-radius:4px;padding:1px 6px;min-width:44px;text-align:center">{m.get('symbol','')}</span>
  <span style="font-size:12px;font-weight:700;color:{TEXT};flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{m.get('name','')}</span>
  <span style="font-size:9px;color:{MUTED};background:rgba(255,255,255,.04);border-radius:4px;padding:1px 6px">{m.get('sector','')}</span>
  <span style="font-size:10px;color:{MUTED}">{price_s}</span>
  <span class="num" style="font-size:13px;font-weight:800;color:{c}">{m['chg_pct']:+.1f}%</span>
</div>""")

    # 半導体への波及ヒント
    hint_html = ""
    semis = [m for m in movers if m.get("sector") == "半導体" and abs(m.get("chg_pct") or 0) >= 2.0]
    if semis:
        big = max(semis, key=lambda x: abs(x["chg_pct"]))
        direction = "追い風" if big["chg_pct"] > 0 else "逆風"
        hc = GREEN if big["chg_pct"] > 0 else RED
        hint_html = f'<div style="margin-top:8px;font-size:11px;line-height:1.7;color:{hc};background:{hc}12;border:1px solid {hc}33;padding:7px 10px;border-radius:8px">💡 {big["name"]}が時間外で{big["chg_pct"]:+.1f}% → 今日の日本の半導体株に{direction}になりやすい</div>'

    return f"""
<div style="margin-bottom:12px">
  <div class="label" style="padding:0 2px;margin-bottom:6px">🇺🇸 米国 時間外で大きく動いた主要銘柄</div>
  <div class="glass-sm fade" style="padding:12px;border-top:3px solid {BLUE}">
    <div style="font-size:10px;color:{MUTED};margin-bottom:4px">{us_ah.get('session_label','')}の値動き（±1%以上）</div>
    {"".join(rows)}
    {hint_html}
  </div>
  <div style="font-size:9px;color:{MUTED};margin-top:5px;padding:0 2px">米国の時間外は引け後の決算・材料への最初の反応。日本のザラ場（特に半導体・ハイテク）に波及しやすい先行シグナルです。</div>
</div>"""


def _pts_section(pts):
    """PTS夜間取引の急騰・急落銘柄（翌朝の寄り付き先行ヒント）"""
    pts = pts or {}
    if not pts.get("available"):
        return ""
    ups, downs = pts.get("up", []), pts.get("down", [])
    if not ups and not downs:
        return ""

    def _block(items, label, c, icon):
        if not items:
            return ""
        rows = []
        for it in items[:5]:
            pc = _col(it.get("chg_pct") or 0)
            close_s = f"{it['close_price']:,.0f}" if it.get("close_price") else "—"
            pts_s   = f"{it['pts_price']:,.1f}".rstrip("0").rstrip(".") if it.get("pts_price") else "—"
            rows.append(f"""<div style="display:flex;align-items:center;gap:7px;padding:6px 0;border-bottom:1px solid {BORDER}">
  <span style="font-size:9.5px;color:{MUTED};background:rgba(255,255,255,.05);border-radius:4px;padding:1px 5px;min-width:38px;text-align:center">{it.get('code','')}</span>
  <span style="font-size:11.5px;font-weight:700;color:{TEXT};flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{it.get('name','')}</span>
  <span style="font-size:9.5px;color:{MUTED}">{close_s}→{pts_s}</span>
  <span class="num" style="font-size:12px;font-weight:800;color:{pc}">{it['chg_pct']:+.1f}%</span>
</div>""")
        return f"""<div class="glass-sm fade" style="padding:12px;border-top:3px solid {c}">
  <div style="font-size:12.5px;font-weight:900;color:{c};margin-bottom:6px">{icon} {label}</div>
  {"".join(rows)}
</div>"""

    up_html   = _block(ups,   "PTS夜間 急騰", GREEN, "🌙⬆️")
    down_html = _block(downs, "PTS夜間 急落", RED,   "🌙⬇️")

    return f"""
<div style="margin-bottom:12px">
  <div class="label" style="padding:0 2px;margin-bottom:6px">🌙 PTS夜間取引で大きく動いた銘柄</div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">{up_html}{down_html}</div>
  <div style="font-size:9px;color:{MUTED};margin-top:5px;padding:0 2px">夜間PTS（16:30〜23:59）は取引終了後のニュースへの最初の反応。翌朝の寄り付きで同じ方向に動きやすい先行ヒントです。出典: 株探</div>
</div>"""


def _risk_sentiment_section(risk_sentiment):
    """極端なリスクオフ/オン（複数資産の一致）"""
    rs = risk_sentiment or {}
    if not rs.get("available"):
        return ""
    off = rs["direction"] == "risk_off"
    c = RED if off else GREEN
    rows = []
    for f in (rs.get("factors") or [])[:6]:
        fc = _col(f["chg"])
        rows.append(f"""<div style="display:flex;align-items:center;gap:8px;padding:5px 0;border-bottom:1px solid {BORDER}">
  <span style="font-size:11.5px;font-weight:700;color:{TEXT};min-width:88px">{f['name']}</span>
  <span class="num" style="font-size:12px;font-weight:800;color:{fc};min-width:62px">{f['chg']:+.2f}%</span>
  <span style="font-size:10.5px;color:{MUTED}">{f['text']}</span>
</div>""")
    return f"""
<div style="margin-bottom:12px">
  <div class="label" style="padding:0 2px;margin-bottom:6px">🌊 市場全体の資金の向き</div>
  <div class="glass-sm fade" style="padding:12px;border-left:3px solid {c}">
    <div style="font-size:13.5px;font-weight:900;color:{c}">{'🔴' if off else '🟢'} {rs['title']}</div>
    <div style="font-size:10.5px;color:{MUTED};margin:3px 0 6px">一致度スコア {rs['score']:.1f}（{len(rs.get('factors', []))}資産が同じ方向）</div>
    {"".join(rows)}
    <div style="font-size:10.5px;color:{TEXT};margin-top:7px">{rs.get('meaning','')}</div>
    <div style="font-size:10.5px;color:{YELLOW};margin-top:3px">💡 {rs.get('tip','')}</div>
  </div>
  <div style="font-size:9px;color:{MUTED};margin-top:5px;padding:0 2px">株・為替・金・債券・VIXが同時に同じ方向を向いたときだけ表示されます。個別の材料ではなく市場全体の判断を示します。</div>
</div>"""


def _sentiment_extreme_section(sentiment):
    """市場心理の極値・反転（底や天井で市場が反応した瞬間）"""
    se = sentiment or {}
    evs = se.get("events") or []
    if not evs:
        return ""
    cards = []
    for e in evs[:3]:
        c = GREEN if any(k in e["title"] for k in ("底打ち", "落ち着き", "反発")) else RED
        cards.append(f"""<div style="background:{CARD2};border:1px solid {BORDER};border-left:3px solid {c};border-radius:8px;padding:10px 12px;margin-bottom:8px">
  <div style="font-size:12.5px;font-weight:900;color:{c}">{e['emoji']} {e['title']}</div>
  <div style="font-size:11px;color:{TEXT};margin-top:3px">{e['detail']}</div>
  <div style="font-size:10px;color:{MUTED};margin-top:3px">{e['meaning']}</div>
  <div style="font-size:10px;color:{YELLOW};margin-top:3px">💡 {e['tip']}</div>
</div>""")
    return f"""
<div style="margin-bottom:12px">
  <div class="label" style="padding:0 2px;margin-bottom:6px">🎭 市場心理が節目に到達</div>
  {"".join(cards)}
  <div style="font-size:9px;color:{MUTED};padding:0 2px">恐怖・強欲が極端に振れた時と、そこから戻り始めた時だけ表示されます。極値からの反転は歴史的な底・天井になりやすい形です。</div>
</div>"""


def _policy_driver_section(policy, market_driver):
    """政策金利の推移＋相場を動かした要因"""
    pol = policy or {}
    md = market_driver or {}
    blocks = []
    for info in (pol.get("fed"), pol.get("boj")):
        if not info:
            continue
        chg = info.get("change")
        c = RED if info.get("direction") == "利上げ" else GREEN if info.get("direction") == "利下げ" else MUTED
        sub = ""
        if info.get("changed_on"):
            days = f"・{info['days_since']}日据え置き" if info.get("days_since") else ""
            sub = f"{info['changed_on']} に {info['prev_rate']:.2f}%→{info['rate']:.2f}%（{info['direction']}{chg:+.2f}%）{days}"
        blocks.append(f"""<div style="background:{CARD2};border:1px solid {BORDER};border-left:3px solid {c};border-radius:8px;padding:9px 11px">
  <div style="font-size:9.5px;color:{MUTED}">{info['name']} 政策金利</div>
  <div class="num" style="font-size:19px;font-weight:900;color:{TEXT};margin:1px 0">{info['rate']:.2f}<span style="font-size:10px;color:{MUTED}">%</span></div>
  <div style="font-size:9.5px;color:{c}">{sub}</div>
</div>""")
    driver_html = ""
    if md.get("available") and md.get("summary"):
        body = md["summary"].replace(chr(10), "<br>")
        driver_html = f"""<div class="glass-sm fade" style="padding:11px 13px;margin-top:8px;border-left:3px solid {YELLOW}">
  <div style="font-size:10px;color:{MUTED};margin-bottom:3px">🔍 相場を動かした要因（AI分析）</div>
  <div style="font-size:11.5px;color:{TEXT};line-height:1.65">{body}</div>
</div>"""
    if not blocks and not driver_html:
        return ""
    grid = f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">{"".join(blocks)}</div>' if blocks else ""
    return f"""
<div style="margin-bottom:12px">
  <div class="label" style="padding:0 2px;margin-bottom:6px">🏛 政策金利と相場の要因</div>
  {grid}{driver_html}
  <div style="font-size:9px;color:{MUTED};margin-top:5px;padding:0 2px">金利は水準より「方向が変わった瞬間」が相場の転換点になります。要因分析は大きく動いた日のみ表示されます。</div>
</div>"""


def _market_signals_section(market_signals, prices=None):
    """市場内部シグナル（SOX/SKEW/VVIX/ドル指数/NT倍率）"""
    ms = market_signals or {}
    cur = ms.get("current") or {}
    if not cur:
        return ""
    _JA = {
        "skew": ("SKEW", "暴落への備えの厚さ", ""),
        "vvix": ("VVIX", "恐怖指数の荒れ具合", ""),
        "dxy":  ("ドル指数", "ドル自身の強さ", ""),
        "nt":   ("NT倍率", "相場の質（偏りの度合い）", "倍"),
        "margin_pl": ("信用評価損益率", "個人の含み損。-20%で底値圏", "%"),
    }
    def _c(name):
        if any(k in name for k in ("強い警戒", "極端", "極めて")):
            return RED
        if any(k in name for k in ("警戒", "不安定", "ドル高", "偏重", "楽観")):
            return YELLOW
        if "過熱" in name:
            return RED
        return GREEN

    changed = {e["key"] for e in ms.get("events", [])}
    cards = []
    for k in ("skew", "vvix", "dxy", "nt", "margin_pl"):
        d = cur.get(k)
        if not d or d.get("value") is None:
            continue
        name, sub, unit = _JA[k]
        c = _c(d.get("name", ""))
        badge = (f'<span style="font-size:8.5px;color:{BG};background:{c};border-radius:4px;'
                 f'padding:1px 5px;margin-left:4px;font-weight:800">変化</span>'
                 if k in changed else "")
        cards.append(f"""<div style="background:{CARD2};border:1px solid {BORDER};border-left:3px solid {c};border-radius:8px;padding:9px 11px">
  <div style="font-size:9.5px;color:{MUTED}">{name}<span style="font-size:8px;margin-left:4px">{sub}</span></div>
  <div class="num" style="font-size:18px;font-weight:900;color:{TEXT};margin:1px 0">{d['value']:.2f}<span style="font-size:10px;color:{MUTED}">{unit}</span></div>
  <div style="font-size:10px;font-weight:800;color:{c}">{d.get('name','')}{badge}</div>
</div>""")

    # SOXは水準でなく「昨夜どれだけ動いたか」が翌朝に効くので別枠で見せる
    sox_html = ""
    sx = (prices or {}).get("^SOX") or {}
    if sx.get("latest") and sx.get("change_pct") is not None:
        chg = sx["change_pct"]
        c = _col(chg)
        note = ("日本の半導体株に追い風が吹きやすい" if chg >= 2.5 else
                "日本の半導体株に逆風が吹きやすい" if chg <= -2.5 else
                "日本の半導体株への影響は限定的")
        sox_html = f"""<div style="background:{CARD2};border:1px solid {BORDER};border-left:3px solid {c};border-radius:8px;padding:9px 11px;margin-top:8px">
  <div style="font-size:9.5px;color:{MUTED}">🔥 SOX指数（米半導体）<span style="font-size:8px;margin-left:4px">東エレク・アドテスト等の先行指標</span></div>
  <div style="display:flex;align-items:baseline;gap:8px">
    <span class="num" style="font-size:18px;font-weight:900;color:{TEXT}">{sx['latest']:,.0f}</span>
    <span class="num" style="font-size:13px;font-weight:800;color:{c}">{chg:+.2f}%</span>
  </div>
  <div style="font-size:9.5px;color:{MUTED};margin-top:2px">{note}</div>
</div>"""

    if not cards and not sox_html:
        return ""
    return f"""
<div style="margin-bottom:12px">
  <div class="label" style="padding:0 2px;margin-bottom:6px">🧭 市場内部シグナル（相場の中身）</div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">{''.join(cards)}</div>
  {sox_html}
  <div style="font-size:9px;color:{MUTED};margin-top:5px;padding:0 2px">価格そのものではなく「相場の中身」を示す指標です。SKEW・VVIXは急落への警戒度、NT倍率は上昇が一部の値がさ株に偏っていないかを表します。</div>
</div>"""


def _macro_section(macro_watch):
    """景気・信用の先行シグナル（何を意味するかを添えて常時表示）"""
    mw = macro_watch or {}
    cur = mw.get("current") or {}
    if not cur:
        return ""
    _JA = {
        "hy_spread":   ("信用不安", "企業の資金繰りの苦しさ", "%"),
        "yield_curve": ("逆イールド", "景気後退の先行指標", "%"),
        "sahm":        ("雇用の悪化速度", "0.5超で景気後退サイン", "pt"),
        "real_rate":   ("実質金利", "高いと株に逆風", "%"),
        "buffett":     ("バフェット指数", "米国株が経済規模の何倍か", "%"),
    }
    # 良い状態=緑 / 注意=黄 / 悪い状態=赤（ゾーン名から判定）
    def _c(name):
        if any(k in name for k in ("危険", "後退", "警戒", "割高", "高い")):
            return RED
        if any(k in name for k in ("悪化", "平坦", "やや")):
            return YELLOW
        if any(k in name for k in ("安定", "健全", "正常", "割安", "低い", "マイナス", "急峻")):
            return GREEN
        return YELLOW

    changed = {e["key"] for e in mw.get("events", [])}
    cards = []
    for k in ("hy_spread", "yield_curve", "sahm", "real_rate", "buffett"):
        d = cur.get(k)
        if not d or d.get("value") is None:
            continue
        name, sub, unit = _JA[k]
        c = _c(d.get("name", ""))
        badge = (f'<span style="font-size:8.5px;color:{BG};background:{c};border-radius:4px;'
                 f'padding:1px 5px;margin-left:4px;font-weight:800">変化</span>'
                 if k in changed else "")
        cards.append(f"""<div style="background:{CARD2};border:1px solid {BORDER};border-left:3px solid {c};border-radius:8px;padding:9px 11px">
  <div style="font-size:9.5px;color:{MUTED}">{name}<span style="font-size:8px;margin-left:4px">{sub}</span></div>
  <div class="num" style="font-size:18px;font-weight:900;color:{TEXT};margin:1px 0">{d['value']:.2f}<span style="font-size:10px;color:{MUTED}">{unit}</span></div>
  <div style="font-size:10px;font-weight:800;color:{c}">{d.get('name','')}{badge}</div>
</div>""")

    eps = mw.get("eps")
    eps_html = ""
    if eps:
        ec = GREEN if eps["state"] == "増益トレンド" else RED if eps["state"] == "減益トレンド" else YELLOW
        eps_html = f"""<div style="background:{CARD2};border:1px solid {BORDER};border-left:3px solid {ec};border-radius:8px;padding:9px 11px;margin-top:8px">
  <div style="font-size:9.5px;color:{MUTED}">日経平均のEPS（1株あたり利益）<span style="font-size:8px;margin-left:4px">株価の土台になる数字</span></div>
  <div style="display:flex;align-items:baseline;gap:8px">
    <span class="num" style="font-size:18px;font-weight:900;color:{TEXT}">{eps['value']:,.0f}<span style="font-size:10px;color:{MUTED}">円</span></span>
    <span class="num" style="font-size:12px;font-weight:800;color:{ec}">3か月で{eps['chg_pct']:+.1f}%・{eps['state']}</span>
  </div>
  <div style="font-size:9.5px;color:{MUTED};margin-top:2px">{eps['meaning']}</div>
</div>"""

    if not cards and not eps_html:
        return ""
    return f"""
<div style="margin-bottom:12px">
  <div class="label" style="padding:0 2px;margin-bottom:6px">🌡 景気・信用の先行シグナル（この先どうなりそうか）</div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">{''.join(cards)}</div>
  {eps_html}
  <div style="font-size:9px;color:{MUTED};margin-top:5px;padding:0 2px">PER・PBRが「今が高いか安いか」なのに対し、こちらは「この先どうなりそうか」を示す指標です。緑=良好、黄=注意、赤=警戒。「変化」は意味の変わる節目を跨いだ指標です。</div>
</div>"""


def _valuation_section(valuation):
    """バリュエーション（PER/PBR/配当利回り/イールドスプレッド）の現在ゾーン"""
    vw = valuation or {}
    cur = vw.get("current") or {}
    if not cur:
        return ""
    _JA = {"per": "PER", "pbr": "PBR",
           "dividend_yield": "配当利回り", "spread": "イールドスプレッド"}
    _SUB = {"per": "株価は利益の何倍か", "pbr": "株価は純資産の何倍か",
            "dividend_yield": "配当の魅力", "spread": "株 vs 国債の魅力差"}
    _UNIT = {"per": "倍", "pbr": "倍", "dividend_yield": "%", "spread": "%"}
    # 割安側=緑 / 標準=黄 / 割高側=赤（ゾーン名から判定）
    def _c(name):
        if any(k in name for k in ("割安", "妙味", "高利回り", "解散価値")):
            return GREEN
        if any(k in name for k in ("割高", "高評価", "低い")):
            return RED
        return YELLOW

    changed = {e["key"] for e in vw.get("events", [])}
    cards = []
    for k in ("per", "pbr", "dividend_yield", "spread"):
        d = cur.get(k)
        if not d:
            continue
        c = _c(d.get("name", ""))
        badge = (f'<span style="font-size:8.5px;color:{BG};background:{c};'
                 f'border-radius:4px;padding:1px 5px;margin-left:4px;font-weight:800">節目通過</span>'
                 if k in changed else "")
        cards.append(f"""<div style="background:{CARD2};border:1px solid {BORDER};border-left:3px solid {c};border-radius:8px;padding:9px 11px">
  <div style="font-size:9.5px;color:{MUTED}">{_JA[k]}<span style="font-size:8px;margin-left:4px">{_SUB[k]}</span></div>
  <div class="num" style="font-size:19px;font-weight:900;color:{TEXT};margin:1px 0">{d['value']:.2f}<span style="font-size:10px;color:{MUTED}">{_UNIT[k]}</span></div>
  <div style="font-size:10px;font-weight:800;color:{c}">{d.get('name','')}{badge}</div>
</div>""")
    if not cards:
        return ""
    return f"""
<div style="margin-bottom:12px">
  <div class="label" style="padding:0 2px;margin-bottom:6px">📐 日経平均のバリュエーション（割安・割高の物差し）</div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">{''.join(cards)}</div>
  <div style="font-size:9px;color:{MUTED};margin-top:5px;padding:0 2px">PER・PBRは低いほど割安、配当利回り・イールドスプレッドは高いほど株の魅力が大きい状態です。「節目通過」は投資判断の分かれ目を跨いだ指標です。</div>
</div>"""


def _upcoming_section(upcoming):
    """今後の注目イベント（SQ・雇用統計・FOMC・週次カレンダー）"""
    up = upcoming or {}
    if not up.get("available") or not up.get("events"):
        return ""
    rows = []
    for e in up["events"][:8]:
        days = e.get("days_to", 99)
        hot  = e.get("importance") == "high"
        when = "★今日" if days == 0 else "明日" if days == 1 else f"あと{days}日"
        wc   = RED if days <= 1 else YELLOW if days <= 3 else MUTED
        d_s  = str(e.get("date", ""))[5:].replace("-", "/")
        rows.append(f"""<div style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid {BORDER}">
  <span class="num" style="font-size:10px;color:{MUTED};min-width:36px">{d_s}</span>
  <span style="font-size:12px">{e.get('icon','🌐')}</span>
  <span style="font-size:11.5px;font-weight:{'800' if hot else '600'};color:{TEXT};flex:1;min-width:0">{e.get('label','')}</span>
  <span style="font-size:10px;font-weight:800;color:{wc};white-space:nowrap">{when}</span>
</div>""")
    return f"""
<div style="margin-bottom:12px">
  <div class="label" style="padding:0 2px;margin-bottom:6px">📅 今後の注目イベント</div>
  <div class="glass-sm fade" style="padding:8px 12px">{"".join(rows)}</div>
  <div style="font-size:9px;color:{MUTED};margin-top:5px;padding:0 2px">SQ・米雇用統計・FOMCは確定日程を自動計算。そのほかは週次カレンダーから今日以降の予定を毎日表示します。</div>
</div>"""


def _cfd_sq_section(cfd_sq):
    """CFD/24時間先物（CME日経ギャップ・米先物）＋SQ日程"""
    cf = cfd_sq or {}
    if not cf.get("available"):
        return ""
    futures = cf.get("futures", [])
    gap = cf.get("cme_gap_pct")
    sq  = cf.get("sq") or {}

    # CME日経ギャップ（主役）
    cme = next((f for f in futures if f.get("symbol") == "NIY=F"), None)
    gap_html = ""
    if cme:
        if gap is not None:
            gc  = GREEN if gap > 0.3 else RED if gap < -0.3 else YELLOW
            gt  = "上ギャップ示唆" if gap > 0.3 else "下ギャップ示唆" if gap < -0.3 else "横ばい示唆"
            sub = f"大阪終値比 <b style='color:{gc}'>{gap:+.2f}%</b> → 寄り付き{gt}"
        else:
            c   = _col(cme.get("change_pct") or 0)
            sub = f"前日比 <b style='color:{c}'>{cme['change_pct']:+.2f}%</b>"
        gap_html = f"""<div style="flex:1;min-width:150px">
  <div style="font-size:10px;color:{MUTED};margin-bottom:2px">🌐 CME日経225先物（24時間・CFD価格の実体）</div>
  <div class="num" style="font-size:20px;font-weight:900;color:{TEXT}">{cme['latest']:,.0f}<span style="font-size:11px;color:{MUTED}">円</span></div>
  <div style="font-size:10.5px;color:{MUTED};margin-top:1px">{sub}</div>
</div>"""

    # 米先物チップ
    chips = []
    for f in futures:
        if f.get("symbol") == "NIY=F":
            continue
        c = _col(f.get("change_pct") or 0)
        nm = f["name"].replace("先物", "")
        chips.append(f"""<div style="background:{CARD2};border:1px solid {BORDER};border-radius:8px;padding:6px 10px;text-align:center">
  <div style="font-size:9px;color:{MUTED}">{nm}</div>
  <div class="num" style="font-size:13px;font-weight:800;color:{c}">{f['change_pct']:+.2f}%</div>
</div>""")
    # コモディティ・欧州指数チップ（24時間CFD銘柄）
    for cm in (cf.get("commodities") or []):
        c = _col(cm.get("change_pct") or 0)
        chips.append(f"""<div style="background:{CARD2};border:1px solid {BORDER};border-radius:8px;padding:6px 10px;text-align:center">
  <div style="font-size:9px;color:{MUTED}">{cm.get('icon','')}{cm['name']}</div>
  <div class="num" style="font-size:13px;font-weight:800;color:{c}">{cm['change_pct']:+.2f}%</div>
</div>""")
    chips_html = f"""<div style="display:flex;gap:6px;flex-wrap:wrap">{''.join(chips)}</div>""" if chips else ""

    # SQカウントダウン
    sq_html = ""
    if sq:
        sqc = RED if sq.get("is_today") else YELLOW if sq.get("is_sq_week") else MUTED
        sq_stat = "★本日SQ日" if sq.get("is_today") else f"あと{sq.get('days_to')}日"
        sq_note = "⚠️ SQ週は清算に向けたポジション調整で荒れやすい" if sq.get("is_sq_week") and not sq.get("is_today") else ""
        sq_html = f"""<div style="border-left:3px solid {sqc};padding:4px 10px;min-width:130px">
  <div style="font-size:10px;color:{MUTED}">📅 {sq.get('type','SQ')}</div>
  <div style="font-size:14px;font-weight:900;color:{sqc}">{sq.get('date','')} <span style="font-size:11px">{sq_stat}</span></div>
  {f'<div style="font-size:9px;color:{YELLOW};margin-top:1px">{sq_note}</div>' if sq_note else ''}
</div>"""

    return f"""
<div style="margin-bottom:12px">
  <div class="label" style="padding:0 2px;margin-bottom:6px">🌐 CFD/24時間先物・SQ情報</div>
  <div class="glass-sm fade" style="padding:12px;display:flex;gap:12px;flex-wrap:wrap;align-items:center">
    {gap_html}{sq_html}
  </div>
  {f'<div style="margin-top:8px">{chips_html}</div>' if chips_html else ''}
  <div style="font-size:9px;color:{MUTED};margin-top:5px;padding:0 2px">CME先物はCFD価格のベース。大阪終値との差が今朝の寄り付きギャップの目安です。SQ=毎月第2金曜の特別清算指数（3/6/9/12月はメジャーSQ）。</div>
</div>"""


def _adr_section(adr):
    """日本株ADR（米国夜間の値動き・寄り付き先行ヒント）"""
    adr = adr or {}
    if not adr.get("available"):
        return ""
    top, bottom = adr.get("top", []), adr.get("bottom", [])
    if not top and not bottom:
        return ""
    mav = adr.get("major_avg_divergence", 0) or 0
    mav_c = GREEN if mav > 0.5 else RED if mav < -0.5 else YELLOW

    def _block(items, label, c, icon):
        if not items:
            return ""
        rows = []
        for it in items[:5]:
            dv = it.get("divergence", 0) or 0
            pc = _col(dv)
            adr_s = f"{it['adr_yen']:,.0f}" if it.get("adr_yen") else "—"
            tky_s = f"{it['tokyo_close']:,.0f}" if it.get("tokyo_close") else "—"
            rows.append(f"""<div style="display:flex;align-items:center;gap:7px;padding:6px 0;border-bottom:1px solid {BORDER}">
  <span style="font-size:9.5px;color:{MUTED};background:rgba(255,255,255,.05);border-radius:4px;padding:1px 5px;min-width:38px;text-align:center">{it.get('code','')}</span>
  <span style="font-size:11.5px;font-weight:700;color:{TEXT};flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{it.get('name','')}</span>
  <span style="font-size:9.5px;color:{MUTED}">{tky_s}→{adr_s}</span>
  <span class="num" style="font-size:12px;font-weight:800;color:{pc}">{dv:+.1f}%</span>
</div>""")
        return f"""<div class="glass-sm fade" style="padding:12px;border-top:3px solid {c}">
  <div style="font-size:12.5px;font-weight:900;color:{c};margin-bottom:6px">{icon} {label}</div>
  {"".join(rows)}
</div>"""

    up_html   = _block(top,    "ADR 買い先行期待", GREEN, "🌏⬆️")
    down_html = _block(bottom, "ADR 売り先行懸念", RED,   "🌏⬇️")

    return f"""
<div style="margin-bottom:12px">
  <div class="label" style="padding:0 2px;margin-bottom:6px">🌏 日本株ADR（米国夜間の値動き）
    <span class="num" style="font-weight:800;color:{mav_c};margin-left:6px">主要平均乖離 {mav:+.2f}%</span></div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">{up_html}{down_html}</div>
  <div style="font-size:9px;color:{MUTED};margin-top:5px;padding:0 2px">ADRは米国市場で取引される日本株。東京終値との乖離＝NY時間の評価変化で、寄り付きが同じ方向に動きやすい先行ヒントです。</div>
</div>"""


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
    cross_check: dict = None,
    sector_ranking: dict = None,
    setups: dict = None,
    ensemble: dict = None,
    stock_dossier: dict = None,
    kabudragon: dict = None,
    pts: dict = None,
    us_afterhours: dict = None,
    adr: dict = None,
    cfd_sq: dict = None,
    upcoming: dict = None,
    valuation: dict = None,
    macro_watch: dict = None,
    market_signals: dict = None,
    policy: dict = None,
    market_driver: dict = None,
    sentiment: dict = None,
    risk_sentiment: dict = None,
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
    setups_html  = _setups(setups)
    sc_html      = _scenarios(scenario)
    mkt_html     = _market_grid(prices, technical)
    tv_html      = _tv_overview()
    tvadv_html   = _tv_advanced()
    ujguide_html = _usdjpy_guide(prices)
    shm_html     = _sector_heatmap_live()
    srk_html     = _sector_ranking(sector_ranking)
    kd_html      = _kabudragon_section(kabudragon)
    pts_html     = _pts_section(pts)
    usah_html    = _us_afterhours_section(us_afterhours)
    adr_html     = _adr_section(adr)
    cfdsq_html   = _cfd_sq_section(cfd_sq)
    upcoming_html = _upcoming_section(upcoming)
    valuation_html = _valuation_section(valuation)
    macro_html = _macro_section(macro_watch)
    msignal_html = _market_signals_section(market_signals, prices)
    policy_html = _policy_driver_section(policy, market_driver)
    sent_html = _sentiment_extreme_section(sentiment)
    risk_html = _risk_sentiment_section(risk_sentiment)
    pro_html     = _pro_cross(prices)
    news_html    = _news(news)
    cal_html     = _calendar(weekly_calendar)
    pred_html     = _pred(prediction_tracker)
    ensemble_html = _ensemble_section(ensemble)
    dossier_html  = _dossier_section(stock_dossier)
    cc_html       = _crosscheck(cross_check)
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

<!-- ── 動くオーロラ背景 ── -->
<div class="aurora"><i></i></div>

<!-- ── トップグラデーションライン ── -->
<div style="height:3px;background:linear-gradient(90deg,{PURPLE},{BLUE},{CYAN},{GREEN});background-size:300% 100%;animation:topbar 8s linear infinite"></div>
<style>@keyframes topbar{{0%{{background-position:0% 0}}100%{{background-position:300% 0}}}}</style>

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
  {setups_html}
  {ensemble_html}
  {dossier_html}
  {cc_html}
  {sc_html}
  {mkt_html}
  {ujguide_html}
  {tv_html}
  {tvadv_html}
  {srk_html}
  {upcoming_html}
  {valuation_html}
  {macro_html}
  {risk_html}
  {sent_html}
  {msignal_html}
  {policy_html}
  {cfdsq_html}
  {usah_html}
  {adr_html}
  {pts_html}
  {kd_html}
  {shm_html}
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
    html = _categorize_labels(html)
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
    cross_check: dict        = None,
    sector_ranking: dict     = None,
    setups: dict             = None,
    ensemble: dict           = None,
    stock_dossier: dict      = None,
    kabudragon: dict         = None,
    pts: dict                = None,
    us_afterhours: dict      = None,
    adr: dict                = None,
    cfd_sq: dict             = None,
    upcoming: dict           = None,
    valuation: dict          = None,
    macro_watch: dict        = None,
    market_signals: dict     = None,
    policy: dict             = None,
    market_driver: dict      = None,
    sentiment: dict          = None,
    risk_sentiment: dict     = None,
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
            cross_check=cross_check, sector_ranking=sector_ranking, setups=setups,
            ensemble=ensemble, stock_dossier=stock_dossier, kabudragon=kabudragon,
            pts=pts, us_afterhours=us_afterhours, adr=adr, cfd_sq=cfd_sq,
            upcoming=upcoming, valuation=valuation, macro_watch=macro_watch, market_signals=market_signals,
            policy=policy, market_driver=market_driver, sentiment=sentiment,
            risk_sentiment=risk_sentiment,
        )
        # 生成できたと言い切る前に、ファイルが実在し中身があるかを必ず確かめる。
        # ここを検証していなかったため、本番で生成に失敗していたことに
        # 長期間気づけなかった（公開ページが古いまま固定されていた）。
        try:
            from pathlib import Path as _P
            f = _P(path)
            size = f.stat().st_size if f.exists() else 0
            if size < 5000:
                logger.error(f"❌ デザインAIレポートが不完全です（{size}バイト）: {path}")
                return {"available": False, "path": path, "size": size}
            logger.info(f"✅ デザインAIレポート生成: {path}（{size:,}バイト）")
        except Exception:
            logger.info(f"✅ デザインAIレポート生成: {path}")
        return {"available": True, "path": path}
    except Exception as e:
        # 例外の中身をerrorレベルで残す。debugだと本番ログに出ず、
        # 「成功表示なのにレポートが更新されない」事故の原因が追えなくなる。
        logger.error(f"❌ デザインAIレポート生成に失敗: {type(e).__name__}: {e}")
        logger.error(traceback.format_exc())
        return {"available": False, "error": f"{type(e).__name__}: {e}"}
