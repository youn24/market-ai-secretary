"""
src/design_ai.py  ─  デザインAIエージェント
プロ品質の HTMLデイリーレポートを自動生成し docs/daily_report.html に保存する。
"""

import math
import json
import traceback
from pathlib import Path
from src.utils import setup_logger, get_jst_now, get_today_str, get_dirs

logger = setup_logger("design_ai")

# ────────────────────────────────────────────────────────────────
# 定数
# ────────────────────────────────────────────────────────────────
BG      = "#090d14"
CARD    = "#111827"
CARD2   = "#141d2b"
BORDER  = "#1e2d3d"
TEXT    = "#eaf6ff"
MUTED   = "#8194a8"
GREEN   = "#00e676"
RED     = "#ff5c6c"
YELLOW  = "#d29922"
ORANGE  = "#db6d28"
BLUE    = "#00d4ff"
PURPLE  = "#7b61ff"
TEAL    = "#39d353"
CYAN    = "#00d4ff"
VIOLET  = "#7b61ff"

# ────────────────────────────────────────────────────────────────
# CSS
# ────────────────────────────────────────────────────────────────
_CSS = f"""
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@300;400;500;700;900&display=swap');

:root {{
  --bg:      {BG};
  --card:    {CARD};
  --card2:   {CARD2};
  --border:  {BORDER};
  --text:    {TEXT};
  --muted:   {MUTED};
  --green:   {GREEN};
  --red:     {RED};
  --yellow:  {YELLOW};
  --orange:  {ORANGE};
  --blue:    {BLUE};
  --purple:  {PURPLE};
  --cyan:    {CYAN};
  --violet:  {VIOLET};
}}

*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

.cj-toggle {{ display:flex; gap:4px; }}
.cj-btn {{ background:transparent; color:var(--muted); border:1px solid var(--border);
  border-radius:7px; padding:4px 10px; font-size:11px; font-weight:700;
  cursor:pointer; transition:all .15s; }}
.cj-btn:hover {{ border-color:var(--blue); color:var(--text); }}
.cj-btn-on {{ background:var(--blue); color:#fff; border-color:var(--blue); }}

.yt-sub {{ font-size:12px; font-weight:700; color:var(--blue); margin:10px 0 3px; }}
.yt-body {{ font-size:13px; line-height:1.7; color:var(--text); }}

html {{ scroll-behavior: smooth; }}

body {{
  font-family: 'Noto Sans JP', sans-serif;
  background: var(--bg);
  color: var(--text);
  font-size: 14px;
  line-height: 1.6;
  min-height: 100vh;
}}

/* ── Layout ── */
.container {{ max-width: 960px; margin: 0 auto; padding: 16px; }}
.grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
.grid-3 {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }}
.grid-auto {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 12px; }}

@media (max-width: 600px) {{
  .grid-2, .grid-3 {{ grid-template-columns: 1fr; }}
  .grid-auto {{ grid-template-columns: repeat(2, 1fr); }}
}}

/* ── Card ── */
.card {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px;
  transition: border-color .2s, box-shadow .2s;
}}
.card:hover {{
  border-color: rgba(0,212,255,.2);
  box-shadow: 0 0 24px rgba(0,212,255,.05);
}}
.card-title {{
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 1.2px;
  color: var(--muted);
  margin-bottom: 12px;
}}

/* ── Header ── */
.header {{
  background: linear-gradient(135deg, #0d1117 0%, #161b22 100%);
  border-bottom: 1px solid var(--border);
  padding: 20px 0 16px;
  margin-bottom: 20px;
}}
.header-inner {{
  max-width: 960px;
  margin: 0 auto;
  padding: 0 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}}
.header-title {{
  font-size: 20px;
  font-weight: 900;
  background: linear-gradient(90deg, {GREEN}, {BLUE});
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}}
.header-sub {{
  font-size: 12px;
  color: var(--muted);
  margin-top: 2px;
}}
.signal-badge {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 700;
  border: 1.5px solid;
}}
.signal-bull   {{ color: {GREEN};  border-color: {GREEN};  background: rgba(63,185,80,.1); }}
.signal-bear   {{ color: {RED};    border-color: {RED};    background: rgba(248,81,73,.1); }}
.signal-neutral {{ color: {YELLOW}; border-color: {YELLOW}; background: rgba(210,153,34,.1); }}

/* ── Gauge (SVG) ── */
.gauge-wrap {{
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}}
.gauge-svg {{ width: 200px; height: 130px; overflow: visible; }}
.gauge-score-label {{
  font-size: 11px;
  color: var(--muted);
  text-align: center;
}}

/* ── Stat row ── */
.stat-row {{
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin-bottom: 4px;
}}
.stat-value {{ font-size: 22px; font-weight: 700; }}
.stat-unit  {{ font-size: 11px; color: var(--muted); }}

/* ── Price cards ── */
.price-card {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px;
}}
.price-name  {{ font-size: 11px; color: var(--muted); margin-bottom: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.price-value {{ font-size: 18px; font-weight: 700; }}
.price-chg   {{ font-size: 12px; margin-top: 3px; }}
.chg-up   {{ color: {GREEN}; }}
.chg-down {{ color: {RED}; }}
.chg-flat {{ color: {MUTED}; }}
.rsi-bar-wrap {{
  margin-top: 6px;
  height: 4px;
  background: var(--border);
  border-radius: 2px;
  overflow: hidden;
}}
.rsi-bar {{ height: 100%; border-radius: 2px; transition: width .3s; }}
.rsi-label {{ font-size: 10px; color: var(--muted); margin-top: 3px; }}

/* ── Sector heatmap ── */
.sector-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(110px, 1fr));
  gap: 8px;
}}
.sector-cell {{
  border-radius: 8px;
  padding: 10px 8px;
  text-align: center;
  font-size: 11px;
  font-weight: 700;
  border: 1px solid transparent;
}}
.sector-name {{ font-size: 10px; opacity: .75; margin-top: 2px; }}

/* ── News ── */
.news-item {{
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
}}
.news-item:last-child {{ border-bottom: none; }}
.news-badge {{
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 700;
  padding: 2px 7px;
  border-radius: 4px;
  margin-top: 2px;
}}
.badge-high   {{ background: rgba(248,81,73,.2);   color: {RED}; }}
.badge-mid    {{ background: rgba(210,153,34,.2);  color: {YELLOW}; }}
.badge-low    {{ background: rgba(139,148,158,.15); color: {MUTED}; }}
.news-title   {{ font-size: 13px; line-height: 1.5; color: var(--text); text-decoration: none; }}
.news-title:hover {{ color: {BLUE}; }}
.news-source  {{ font-size: 11px; color: var(--muted); margin-top: 2px; }}

/* ── AI discussion ── */
.debate-member {{
  display: flex;
  gap: 10px;
  margin-bottom: 14px;
}}
.debate-avatar {{
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  border: 2px solid;
}}
.av-bull   {{ border-color: {GREEN}; background: rgba(63,185,80,.12); }}
.av-bear   {{ border-color: {RED};   background: rgba(248,81,73,.12); }}
.av-neutral {{ border-color: {YELLOW}; background: rgba(210,153,34,.12); }}
.debate-bubble {{
  background: var(--card2);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 12px;
  font-size: 13px;
  line-height: 1.6;
  flex: 1;
}}
.debate-name {{ font-size: 11px; font-weight: 700; margin-bottom: 4px; }}
.debate-verdict {{
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  padding: 10px 12px;
  background: var(--card2);
  border-radius: 8px;
  border: 1px solid var(--border);
}}
.verdict-icon {{ font-size: 22px; }}
.verdict-text {{ font-size: 14px; font-weight: 700; }}
.verdict-conf {{ font-size: 12px; color: var(--muted); margin-top: 1px; }}

/* ── Calendar ── */
.cal-item {{
  display: flex;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px solid var(--border);
  align-items: flex-start;
}}
.cal-item:last-child {{ border-bottom: none; }}
.cal-date {{
  flex-shrink: 0;
  background: var(--card2);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 4px 8px;
  font-size: 11px;
  font-weight: 700;
  min-width: 60px;
  text-align: center;
}}
.cal-event {{ font-size: 13px; line-height: 1.5; }}
.cal-impact-high   {{ color: {RED}; font-weight: 700; }}
.cal-impact-mid    {{ color: {YELLOW}; }}

/* ── Prediction tracker ── */
.acc-bar-wrap {{
  height: 8px;
  background: var(--border);
  border-radius: 4px;
  overflow: hidden;
  margin: 8px 0;
}}
.acc-bar {{
  height: 100%;
  background: linear-gradient(90deg, {BLUE}, {GREEN});
  border-radius: 4px;
  transition: width .5s;
}}
.pred-row {{
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  padding: 4px 0;
  border-bottom: 1px solid var(--border);
}}
.pred-row:last-child {{ border-bottom: none; }}
.pred-hit  {{ color: {GREEN}; font-weight: 700; }}
.pred-miss {{ color: {RED};   font-weight: 700; }}

/* ── Fear & Greed meter ── */
.fg-meter {{
  position: relative;
  height: 10px;
  background: linear-gradient(90deg, {RED}, {YELLOW}, {GREEN});
  border-radius: 5px;
  margin: 8px 0 4px;
}}
.fg-pointer {{
  position: absolute;
  top: -4px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: white;
  border: 2px solid var(--bg);
  transform: translateX(-50%);
  box-shadow: 0 0 6px rgba(0,0,0,.5);
}}

/* ── Scroll anim ── */
@keyframes fadeUp {{
  from {{ opacity: 0; transform: translateY(12px); }}
  to   {{ opacity: 1; transform: translateY(0); }}
}}
.fade-up {{
  animation: fadeUp .5s ease forwards;
  opacity: 0;
}}
section {{ margin-bottom: 20px; }}
.section-header {{
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(0,212,255,.12);
}}
.section-icon {{ font-size: 18px; }}
.section-title {{ font-size: 16px; font-weight: 700; color: {TEXT}; }}
.section-tag {{
  margin-left: auto;
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(0,212,255,.06);
  color: {CYAN};
  border: 1px solid rgba(0,212,255,.15);
}}

/* ── キャラクターヘッダー ── */
.char-header {{
  background:
    radial-gradient(110% 90% at 85% 0%, rgba(0,212,255,.14), transparent 52%),
    radial-gradient(100% 90% at 5% 110%, rgba(123,97,255,.12), transparent 55%),
    linear-gradient(160deg, #0b1018 0%, #090d14 50%, #070a10 100%);
  border-bottom: 1px solid rgba(0,212,255,.2);
  padding: 0;
  overflow: hidden;
  position: relative;
  margin-bottom: 20px;
}}
.char-header-inner {{
  max-width: 960px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
}}
.char-title-block {{
  text-align: center;
  flex: 1;
  padding: 20px 10px 16px;
}}
.char-brand-badge {{
  display: inline-block;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 1.5px;
  color: {CYAN};
  background: rgba(0,212,255,.08);
  border: 1px solid rgba(0,212,255,.25);
  border-radius: 4px;
  padding: 2px 10px;
  margin-bottom: 8px;
}}
.char-title-row {{
  display: flex;
  align-items: center;
  gap: 8px;
  justify-content: center;
  margin-bottom: 4px;
}}
.char-M-chip {{
  width: 28px; height: 28px;
  border-radius: 7px;
  background: linear-gradient(135deg, {VIOLET}, {CYAN});
  color: #060a0f;
  font-size: 14px;
  font-weight: 900;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}}
.char-main-title {{
  font-size: 20px;
  font-weight: 900;
  background: linear-gradient(90deg, {VIOLET}, {CYAN}, {GREEN});
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  line-height: 1.2;
}}
.char-sub-title {{
  font-size: 11px;
  color: #6b7d90;
  margin-top: 4px;
  letter-spacing: 1.5px;
}}
.char-date-badge {{
  display: inline-block;
  background: rgba(0,212,255,.08);
  border: 1px solid rgba(0,212,255,.2);
  border-radius: 20px;
  padding: 3px 14px;
  font-size: 11px;
  color: #aebccb;
  margin-top: 8px;
}}
.char-signal-badge {{
  display: inline-block;
  padding: 5px 18px;
  border-radius: 20px;
  font-size: 14px;
  font-weight: 900;
  margin-top: 8px;
  border: 1.5px solid;
}}
.char-figure {{
  width: 130px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 16px 0;
}}
.char-figure-label {{
  font-size: 10px;
  color: #6b7d90;
  font-weight: 700;
  text-align: center;
  margin-top: 4px;
}}
.char-svg {{ width: 100px; height: 100px; }}
.char-balloon {{
  background: rgba(255,255,255,.04);
  border: 1px solid rgba(0,212,255,.15);
  border-radius: 8px;
  padding: 4px 8px;
  font-size: 10px;
  color: #8194a8;
  text-align: center;
  max-width: 110px;
  margin-top: 4px;
}}
@media (max-width: 600px) {{
  .char-main-title {{ font-size: 15px; }}
  .char-figure {{ width: 80px; }}
  .char-svg {{ width: 70px; height: 70px; }}
}}

/* ── クイックサマリーカード ── */
.qs-grid {{
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 10px;
  margin-bottom: 20px;
}}
@media (max-width: 600px) {{
  .qs-grid {{ grid-template-columns: repeat(2, 1fr); }}
}}
.qs-card {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 12px 8px;
  text-align: center;
  transition: transform .2s, box-shadow .2s;
}}
.qs-card:hover {{ transform: translateY(-3px); box-shadow: 0 6px 16px rgba(0,0,0,.4); }}
.qs-icon  {{ font-size: 18px; margin-bottom: 4px; }}
.qs-label {{ font-size: 10px; color: var(--muted); margin-bottom: 5px; }}
.qs-value {{ font-size: 16px; font-weight: 800; }}
.qs-chg   {{ font-size: 11px; margin-top: 4px; }}

/* ── ウォッチリスト ── */
.watch-item {{
  display: flex;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
  gap: 8px;
}}
.watch-item:last-child {{ border-bottom: none; }}
.watch-rank  {{ font-size: 12px; color: var(--muted); min-width: 20px; }}
.watch-name  {{ flex: 1; font-size: 13px; font-weight: 700; }}
.watch-theme {{ font-size: 10px; color: var(--muted); }}
.watch-price {{ font-size: 14px; font-weight: 700; min-width: 80px; text-align: right; }}
.watch-chg   {{ font-size: 13px; font-weight: 700; min-width: 55px; text-align: right; }}
.watch-signal {{ font-size: 10px; padding: 2px 7px; border-radius: 4px; white-space: nowrap; }}
.sig-buy  {{ background: rgba(63,185,80,.2); color: {GREEN}; }}
.sig-sell {{ background: rgba(248,81,73,.2); color: {RED}; }}
.sig-hold {{ background: rgba(210,153,34,.2); color: {YELLOW}; }}

/* ── シナリオカード(改良) ── */
.scenario-card-new {{
  border-radius: 12px;
  padding: 16px;
  border: 2px solid;
  text-align: center;
}}
.sc-icon   {{ font-size: 30px; margin-bottom: 6px; }}
.sc-label  {{ font-size: 13px; font-weight: 700; margin-bottom: 4px; }}
.sc-prob   {{ font-size: 26px; font-weight: 900; }}
.sc-range  {{ font-size: 12px; margin-top: 4px; opacity: .85; }}
.sc-desc   {{ font-size: 11px; line-height: 1.6; margin-top: 8px; text-align: left; }}

/* ── 市場ステータスバー ── */
.market-status-bar {{
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  padding: 12px 16px;
  background: var(--card2);
  border: 1px solid var(--border);
  border-radius: 10px;
  margin-bottom: 16px;
  align-items: center;
}}
.ms-item {{ display: flex; flex-direction: column; align-items: center; min-width: 70px; }}
.ms-label {{ font-size: 9px; color: var(--muted); margin-bottom: 2px; }}
.ms-value {{ font-size: 13px; font-weight: 700; }}
.ms-chg   {{ font-size: 10px; }}
.ms-sep   {{ width: 1px; height: 30px; background: var(--border); }}
"""


# ────────────────────────────────────────────────────────────────
# ヘルパー関数
# ────────────────────────────────────────────────────────────────

def _gane_svg(mood: str) -> str:
    """ガネ先生のインラインSVGキャラクター（相場ムードに応じた表情）"""
    # 体の色 / 表情パラメータ
    body_color  = "#f0c040"
    skin_color  = "#e8b830"
    eye_l = eye_r = "😊"

    if mood in ("bullish",):
        mouth = "M 55,70 Q 65,80 75,70"   # 笑顔
        eyebrow = "M 52,52 L 60,48  M 68,48 L 76,52"
        sparkle = '<text x="80" y="25" font-size="14" opacity=".9">✨</text>'
    elif mood in ("bearish", "crash"):
        mouth = "M 55,75 Q 65,68 75,75"   # 下がり口
        eyebrow = "M 52,50 L 60,54  M 68,54 L 76,50"
        sparkle = '<text x="78" y="28" font-size="12" opacity=".7">💧</text>'
    elif mood in ("volatile", "uncertain"):
        mouth = "M 57,72 Q 65,72 73,72"   # まっすぐ
        eyebrow = "M 52,51 L 60,48  M 68,48 L 76,51"
        sparkle = '<text x="79" y="26" font-size="13" opacity=".8">❓</text>'
    else:  # analyzing / neutral
        mouth = "M 55,70 Q 65,77 75,70"   # 軽い笑顔
        eyebrow = "M 52,50 L 60,48  M 68,48 L 76,50"
        sparkle = '<text x="80" y="26" font-size="12" opacity=".8">📊</text>'

    return f"""<svg class="char-svg" viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <!-- 後光 -->
  <circle cx="60" cy="58" r="48" fill="rgba(240,192,64,.08)"/>
  <!-- 胴体 -->
  <ellipse cx="60" cy="95" rx="26" ry="18" fill="{skin_color}"/>
  <!-- 腕(左) -->
  <ellipse cx="32" cy="90" rx="9" ry="14" fill="{body_color}" transform="rotate(-20 32 90)"/>
  <!-- 腕(右) -->
  <ellipse cx="88" cy="90" rx="9" ry="14" fill="{body_color}" transform="rotate(20 88 90)"/>
  <!-- 頭 -->
  <circle cx="60" cy="55" r="36" fill="{body_color}"/>
  <!-- 耳(左) -->
  <ellipse cx="22" cy="50" rx="14" ry="20" fill="{skin_color}" opacity=".9"/>
  <ellipse cx="22" cy="50" rx="9" ry="14" fill="rgba(240,192,64,.5)"/>
  <!-- 耳(右) -->
  <ellipse cx="98" cy="50" rx="14" ry="20" fill="{skin_color}" opacity=".9"/>
  <ellipse cx="98" cy="50" rx="9" ry="14" fill="rgba(240,192,64,.5)"/>
  <!-- 王冠 -->
  <polygon points="44,28 52,18 60,26 68,18 76,28 78,35 42,35" fill="#e8b830" stroke="#c8992a" stroke-width="1.5"/>
  <circle cx="60" cy="22" r="4" fill="#ff6060"/>
  <circle cx="47" cy="31" r="3" fill="#60a0ff"/>
  <circle cx="73" cy="31" r="3" fill="#60ff60"/>
  <!-- 白い顔面 -->
  <ellipse cx="60" cy="60" rx="24" ry="20" fill="rgba(255,255,240,.15)"/>
  <!-- 目(左) -->
  <circle cx="50" cy="56" r="6" fill="white"/>
  <circle cx="51" cy="56" r="4" fill="#2a1800"/>
  <circle cx="52" cy="54" r="1.5" fill="white"/>
  <!-- 目(右) -->
  <circle cx="70" cy="56" r="6" fill="white"/>
  <circle cx="71" cy="56" r="4" fill="#2a1800"/>
  <circle cx="72" cy="54" r="1.5" fill="white"/>
  <!-- 眉毛 -->
  <path d="{eyebrow}" stroke="#8B5A2B" stroke-width="2.5" fill="none" stroke-linecap="round"/>
  <!-- 鼻(象の鼻) -->
  <path d="M 60,65 Q 58,72 62,78 Q 66,84 60,88" stroke="{skin_color}" stroke-width="8"
        fill="none" stroke-linecap="round"/>
  <!-- 口 -->
  <path d="{mouth}" stroke="#8B5A2B" stroke-width="2.5" fill="none" stroke-linecap="round"/>
  <!-- ほっぺ -->
  <circle cx="44" cy="65" r="7" fill="rgba(255,100,100,.2)"/>
  <circle cx="76" cy="65" r="7" fill="rgba(255,100,100,.2)"/>
  <!-- スパークル -->
  {sparkle}
</svg>"""


def _kawauso_svg(mood: str) -> str:
    """カワウソくんのインラインSVGキャラクター"""
    body_color = "#6B3A2A"
    face_color = "#C4956A"

    if mood in ("bullish",):
        mouth = "M 52,70 Q 60,78 68,70"
        accessory = '<text x="72" y="35" font-size="14">🎉</text>'
    elif mood in ("bearish", "crash"):
        mouth = "M 52,74 Q 60,68 68,74"
        accessory = '<text x="72" y="35" font-size="13">💧</text>'
    elif mood in ("volatile", "uncertain"):
        mouth = "M 54,72 Q 60,72 66,72"
        accessory = '<text x="70" y="33" font-size="13">❓</text>'
    else:
        mouth = "M 52,70 Q 60,76 68,70"
        accessory = '<text x="72" y="34" font-size="12">📝</text>'

    return f"""<svg class="char-svg" viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <!-- 胴体 -->
  <ellipse cx="60" cy="96" rx="22" ry="16" fill="{body_color}"/>
  <!-- 耳(左) -->
  <ellipse cx="30" cy="38" rx="10" ry="12" fill="{body_color}"/>
  <ellipse cx="30" cy="38" rx="6" ry="8" fill="{face_color}" opacity=".6"/>
  <!-- 耳(右) -->
  <ellipse cx="90" cy="38" rx="10" ry="12" fill="{body_color}"/>
  <ellipse cx="90" cy="38" rx="6" ry="8" fill="{face_color}" opacity=".6"/>
  <!-- 頭 -->
  <circle cx="60" cy="58" r="34" fill="{body_color}"/>
  <!-- 顔の白い部分 -->
  <ellipse cx="60" cy="64" rx="22" ry="18" fill="{face_color}"/>
  <!-- 目(左) -->
  <circle cx="50" cy="55" r="7" fill="white"/>
  <circle cx="51" cy="55" r="4.5" fill="#1a0a00"/>
  <circle cx="52" cy="53" r="1.5" fill="white"/>
  <!-- 目(右) -->
  <circle cx="70" cy="55" r="7" fill="white"/>
  <circle cx="71" cy="55" r="4.5" fill="#1a0a00"/>
  <circle cx="72" cy="53" r="1.5" fill="white"/>
  <!-- 鼻 -->
  <ellipse cx="60" cy="66" rx="5" ry="3.5" fill="#3a1a10"/>
  <!-- ひげ(左) -->
  <line x1="36" y1="67" x2="50" y2="66" stroke="rgba(255,255,255,.6)" stroke-width="1.2"/>
  <line x1="36" y1="70" x2="50" y2="69" stroke="rgba(255,255,255,.6)" stroke-width="1.2"/>
  <!-- ひげ(右) -->
  <line x1="70" y1="66" x2="84" y2="67" stroke="rgba(255,255,255,.6)" stroke-width="1.2"/>
  <line x1="70" y1="69" x2="84" y2="70" stroke="rgba(255,255,255,.6)" stroke-width="1.2"/>
  <!-- 口 -->
  <path d="{mouth}" stroke="#3a1a10" stroke-width="2.5" fill="none" stroke-linecap="round"/>
  <!-- ほっぺ -->
  <circle cx="44" cy="67" r="7" fill="rgba(255,120,120,.25)"/>
  <circle cx="76" cy="67" r="7" fill="rgba(255,120,120,.25)"/>
  <!-- しっぽ -->
  <path d="M 72,105 Q 95,110 100,98 Q 105,86 90,84" stroke="{body_color}" stroke-width="10"
        fill="none" stroke-linecap="round"/>
  <!-- アクセサリー -->
  {accessory}
</svg>"""


def _copy_char_to_docs(root: Path) -> tuple:
    """キャラクター画像をdocs/assets/にコピーして相対パスを返す。なければNone"""
    import shutil
    docs_assets = root / "docs" / "assets"
    docs_assets.mkdir(parents=True, exist_ok=True)

    def find_and_copy(names, dest_name):
        search_dirs = [
            root / "assets",
            root / "docs" / "assets",
            root / "src" / "assets",
        ]
        for d in search_dirs:
            for name in names:
                p = d / name
                if p.exists() and p.stat().st_size > 10000:  # 10KB以上のみ
                    dest = docs_assets / dest_name
                    if p != dest:
                        shutil.copy2(str(p), str(dest))
                    return f"assets/{dest_name}"
        return None

    gane_path = find_and_copy(["gane_sensei.png"], "gane_sensei.png")
    kawa_path = find_and_copy(["kawauso.png"],     "kawauso.png")
    return gane_path, kawa_path


def _character_header(score: float, prices: dict, mood: str, today: str, now: str) -> str:
    """キャラクター入りヘッダーHTML — PNG画像があれば相対パスで使い、なければSVG"""
    signal_text = _signal_text(score)

    if score >= 0.5:
        sig_style    = f"color:{GREEN};border-color:{GREEN};background:rgba(63,185,80,.15)"
        gane_mood    = "bullish"
        kawauso_mood = "bullish"
        gane_say     = "相場が良さそう\nですね！"
        kawa_say     = "チャンスかも！\n積極的に！"
    elif score >= -0.5:
        sig_style    = f"color:{YELLOW};border-color:{YELLOW};background:rgba(210,153,34,.15)"
        gane_mood    = "analyzing"
        kawauso_mood = "uncertain"
        gane_say     = "様子を見ながら\n慎重に判断を"
        kawa_say     = "うーん...\n迷うところ"
    else:
        sig_style    = f"color:{RED};border-color:{RED};background:rgba(248,81,73,.15)"
        gane_mood    = "bearish"
        kawauso_mood = "bearish"
        gane_say     = "リスク管理を\n徹底しましょう"
        kawa_say     = "気をつけて！\n守りが大事"

    root = Path(__file__).parent.parent
    gane_path, kawa_path = _copy_char_to_docs(root)

    gane_html    = (f'<img src="{gane_path}" style="width:110px;height:110px;object-fit:contain;filter:drop-shadow(0 4px 12px rgba(0,0,0,.6))">'
                    if gane_path else _gane_svg(gane_mood))
    kawauso_html = (f'<img src="{kawa_path}" style="width:110px;height:110px;object-fit:contain;filter:drop-shadow(0 4px 12px rgba(0,0,0,.6))">'
                    if kawa_path else _kawauso_svg(kawauso_mood))

    nikkei  = prices.get("^N225",   {})
    sp500   = prices.get("^GSPC",   {})
    usdjpy  = prices.get("USDJPY=X",{})
    nk_val  = nikkei.get("price",  0)
    nk_chg  = nikkei.get("change_pct", 0)
    sp_val  = sp500.get("price",   0)
    sp_chg  = sp500.get("change_pct",  0)
    fx_val  = usdjpy.get("price",  0)
    nk_cls  = "chg-up" if nk_chg >= 0 else "chg-down"
    sp_cls  = "chg-up" if sp_chg >= 0 else "chg-down"
    nk_sign = "+" if nk_chg >= 0 else ""
    sp_sign = "+" if sp_chg >= 0 else ""

    return f"""<header class="char-header">
  <div class="char-header-inner">
    <!-- ガネ先生 (左) -->
    <div class="char-figure">
      {gane_html}
      <div class="char-figure-label">ガネ先生</div>
      <div class="char-balloon">{gane_say.replace(chr(10), '<br>')}</div>
    </div>

    <!-- タイトル (中央) -->
    <div class="char-title-block">
      <div class="char-brand-badge">DAILY REPORT</div>
      <div class="char-title-row">
        <div class="char-M-chip">M</div>
        <div class="char-main-title">市場AI秘書</div>
      </div>
      <div class="char-sub-title">AI MARKET BRIEFING · GEMINI POWERED</div>
      <div class="char-date-badge">📅 {today} {now.split()[1] if ' ' in now else ''}</div><br>
      <span class="char-signal-badge" style="{sig_style}">{signal_text}</span>
      <div style="margin-top:10px;display:flex;gap:12px;justify-content:center;flex-wrap:wrap">
        <span style="font-size:12px;color:#f0c040">
          🇯🇵 日経 <b style="color:{'#3fb950' if nk_chg>=0 else '#f85149'}">{nk_val:,.0f}</b>
          <span class="{nk_cls}">({nk_sign}{nk_chg:.2f}%)</span>
        </span>
        <span style="font-size:12px;color:#f0c040">
          🇺🇸 S&P <b style="color:{'#3fb950' if sp_chg>=0 else '#f85149'}">{sp_val:,.0f}</b>
          <span class="{sp_cls}">({sp_sign}{sp_chg:.2f}%)</span>
        </span>
        <span style="font-size:12px;color:#f0c040">
          💴 USD/JPY <b>{fx_val:.2f}</b>
        </span>
      </div>
    </div>

    <!-- カワウソくん (右) -->
    <div class="char-figure">
      {kawauso_html}
      <div class="char-figure-label">カワウソくん</div>
      <div class="char-balloon">{kawa_say.replace(chr(10), '<br>')}</div>
    </div>
  </div>
</header>"""


def _quick_summary(prices: dict, risk: dict, fear_greed: dict, technical: dict) -> str:
    """5つのクイックサマリーカード（日本株・米国株・為替・VIX・FearGreed）"""
    def _fmt(sym, label, icon):
        p   = prices.get(sym, {})
        val = p.get("price", 0)
        chg = p.get("change_pct", 0)
        cls = "chg-up" if chg >= 0 else "chg-down"
        sgn = "+" if chg >= 0 else ""
        fmt_val = f"{val:,.0f}" if val > 100 else f"{val:.2f}"
        return f"""<div class="qs-card">
  <div class="qs-icon">{icon}</div>
  <div class="qs-label">{label}</div>
  <div class="qs-value">{fmt_val}</div>
  <div class="qs-chg {cls}">{sgn}{chg:.2f}%</div>
</div>"""

    vix_p = prices.get("^VIX", {})
    vix_v = vix_p.get("price", 0)
    vix_chg = vix_p.get("change_pct", 0)
    vix_cls = "chg-down" if vix_chg >= 0 else "chg-up"  # VIXは逆
    vix_sgn = "+" if vix_chg >= 0 else ""

    fg   = fear_greed or {}
    fg_s = fg.get("score") or 50
    fg_r = fg.get("rating_ja", fg.get("rating", "---"))
    fg_c = GREEN if fg_s >= 60 else (YELLOW if fg_s >= 40 else RED)

    cards = [
        _fmt("^N225",    "日経平均",  "🇯🇵"),
        _fmt("^GSPC",    "S&P500",   "🇺🇸"),
        _fmt("USDJPY=X", "USD/JPY",  "💴"),
        f"""<div class="qs-card">
  <div class="qs-icon">😨</div>
  <div class="qs-label">VIX 恐怖指数</div>
  <div class="qs-value" style="color:{'#f85149' if vix_v>=25 else ('#d29922' if vix_v>=18 else '#3fb950')}">{vix_v:.1f}</div>
  <div class="qs-chg {vix_cls}">{vix_sgn}{vix_chg:.2f}%</div>
</div>""",
        f"""<div class="qs-card">
  <div class="qs-icon">🎭</div>
  <div class="qs-label">Fear &amp; Greed</div>
  <div class="qs-value" style="color:{fg_c}">{fg_s:.0f}</div>
  <div class="qs-chg" style="color:{fg_c}">{fg_r}</div>
</div>""",
    ]
    return f'<div class="qs-grid">{"".join(cards)}</div>'


def _watchlist(prices: dict, technical: dict) -> str:
    """注目銘柄ウォッチリスト"""
    tech = technical or {}
    watch_syms = [
        ("^N225",    "日経225",      "🇯🇵", "総合指数"),
        ("^IXIC",    "Nasdaq",       "💻", "テック"),
        ("GC=F",     "金 (Gold)",    "🥇", "安全資産"),
        ("BTC-USD",  "Bitcoin",      "₿",  "暗号資産"),
        ("CL=F",     "原油 WTI",     "🛢",  "コモディティ"),
    ]
    rows = []
    for i, (sym, name, icon, theme) in enumerate(watch_syms, 1):
        p   = prices.get(sym, {})
        val = p.get("price", 0)
        chg = p.get("change_pct", 0)
        cls = "chg-up" if chg >= 0 else "chg-down"
        sgn = "+" if chg >= 0 else ""
        fmt_val = f"{val:,.0f}" if val > 100 else f"{val:.2f}"

        # テクニカルシグナル
        t   = tech.get(sym, {})
        rsi = t.get("rsi", 0)
        if rsi:
            if rsi >= 70:   sig, sig_cls = "過熱", "sig-sell"
            elif rsi <= 30: sig, sig_cls = "売られ過ぎ", "sig-buy"
            else:           sig, sig_cls = f"RSI {rsi:.0f}", "sig-hold"
        else:
            sig, sig_cls = "---", "sig-hold"

        rows.append(f"""<div class="watch-item">
  <span class="watch-rank">{i}</span>
  <div class="watch-name">{icon} {name}<br><span class="watch-theme">{theme}</span></div>
  <span class="watch-price {'chg-up' if chg >= 0 else 'chg-down'}">{fmt_val}</span>
  <span class="watch-chg {cls}">{sgn}{chg:.2f}%</span>
  <span class="watch-signal {sig_cls}">{sig}</span>
</div>""")

    return "\n".join(rows)


def _scenarios_html(scenario: dict) -> str:
    """3シナリオカード (強気/基本/弱気)"""
    sc = scenario or {}
    if not sc.get("available"):
        return ""

    cards = []
    configs = [
        ("bull", "🚀 強気シナリオ", GREEN,  "rgba(63,185,80,.08)"),
        ("base", "😐 基本シナリオ", YELLOW, "rgba(210,153,34,.08)"),
        ("bear", "🐻 弱気シナリオ", RED,    "rgba(248,81,73,.08)"),
    ]
    for key, label, color, bg in configs:
        sec  = sc.get(key, {})
        if not sec:
            continue
        prob = sec.get("probability", sec.get("prob", 0))
        desc = sec.get("description", sec.get("desc", sec.get("text", "")))
        prob_str = f"{prob*100:.0f}%" if prob and prob <= 1 else (f"{prob}%" if prob else "?")
        nikkei_range = sec.get("nikkei_range", sec.get("range", ""))
        range_html = f'<div class="sc-range">日経 {nikkei_range}</div>' if nikkei_range else ""
        cards.append(f"""<div class="scenario-card-new" style="border-color:{color};background:{bg}">
  <div class="sc-label" style="color:{color}">{label}</div>
  <div class="sc-prob" style="color:{color}">{prob_str}</div>
  {range_html}
  <div class="sc-desc">{str(desc)[:160]}</div>
</div>""")

    if not cards:
        return ""
    return f"""<section>
  <div class="section-header">
    <span class="section-icon">🔭</span>
    <span class="section-title">3シナリオ分析</span>
    <span class="section-tag">AI確率算出</span>
  </div>
  <div class="grid-3">{"".join(cards)}</div>
</section>"""


def _chartjs_section(history: dict, prices: dict) -> str:
    """B案：Chart.js インタラクティブチャート（1ヶ月の値動き比較＋本日の前日比）"""
    history = history or {}
    series  = history.get("series") or []
    labels  = history.get("labels") or []

    # ── 本日の前日比バー用データ（主要指標）──
    bar_syms = [
        ("^N225", "日経225"), ("^GSPC", "S&P500"), ("^IXIC", "Nasdaq"),
        ("USDJPY=X", "ドル円"), ("GC=F", "金"), ("CL=F", "原油"),
        ("BTC-USD", "BTC"), ("^VIX", "VIX"),
    ]
    bar_labels, bar_vals, bar_colors = [], [], []
    for sym, name in bar_syms:
        chg = (prices.get(sym) or {}).get("change_pct")
        if chg is None:
            continue
        bar_labels.append(name)
        bar_vals.append(chg)
        # VIXだけ上昇＝赤、それ以外は上昇＝緑
        up_is_good = sym != "^VIX"
        good = (chg >= 0) if up_is_good else (chg < 0)
        bar_colors.append("#3fb950" if good else "#f85149")

    # 何も無ければ非表示
    if not series and not bar_vals:
        return ""

    line_json   = json.dumps(series, ensure_ascii=False)
    labels_json = json.dumps(labels, ensure_ascii=False)
    bl_json     = json.dumps(bar_labels, ensure_ascii=False)
    bv_json     = json.dumps(bar_vals, ensure_ascii=False)
    bc_json     = json.dumps(bar_colors, ensure_ascii=False)

    line_card = ""
    if series:
        line_card = """
  <div class="card fade-up" style="margin-bottom:12px">
    <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;margin-bottom:6px">
      <div class="card-title" style="margin:0">過去1ヶ月の値動き比較</div>
      <div class="cj-toggle">
        <button id="cjModePct" class="cj-btn cj-btn-on" onclick="cjSetMode('pct')">騰落率 %</button>
        <button id="cjModeRaw" class="cj-btn" onclick="cjSetMode('raw')">実数</button>
      </div>
    </div>
    <div style="font-size:11px;color:var(--muted);margin-bottom:8px">
      初日を起点に、どの資産が強かったかを同じ物差しで比較できます（線をタップで数値表示）
    </div>
    <div style="position:relative;height:280px"><canvas id="cjLine"></canvas></div>
  </div>"""

    bar_card = ""
    if bar_vals:
        bar_card = """
  <div class="card fade-up">
    <div class="card-title">本日の前日比ランキング</div>
    <div style="font-size:11px;color:var(--muted);margin-bottom:8px">
      緑＝好材料方向 / 赤＝警戒方向（VIXは上昇が赤）。バーをタップで正確な数値が出ます
    </div>
    <div style="position:relative;height:260px"><canvas id="cjBar"></canvas></div>
  </div>"""

    return f"""
<!-- ── インタラクティブチャート（Chart.js・実データ）── -->
<section>
  <div class="section-header">
    <span class="section-icon">📊</span>
    <span class="section-title">インタラクティブ・データチャート</span>
    <span class="section-tag">タップで操作</span>
  </div>
{line_card}
{bar_card}
</section>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script>
(function(){{
  function init(){{
    if (typeof Chart === 'undefined') {{ return setTimeout(init, 200); }}
    Chart.defaults.color = '#8b949e';
    Chart.defaults.font.family = "-apple-system,'Hiragino Sans','Yu Gothic',sans-serif";
    Chart.defaults.font.size = 11;
    var grid = 'rgba(139,148,158,0.12)';

    var labels = {labels_json};
    var series = {line_json};
    var lineChart = null;

    function buildLine(mode){{
      var ds = series.map(function(s){{
        return {{
          label: s.name,
          data: (mode === 'raw' ? s.data : s.pct),
          borderColor: s.color,
          backgroundColor: s.color,
          borderWidth: 2,
          pointRadius: 0,
          pointHoverRadius: 4,
          tension: 0.25,
          yAxisID: (mode === 'raw' ? ('y_' + s.name) : 'y'),
        }};
      }});
      var scales;
      if (mode === 'raw') {{
        // 実数モードは資産ごとにスケールが違うので各系列を非表示の個別軸へ（重なり比較は％モード推奨）
        scales = {{ x: {{ grid: {{ color: grid }} }} }};
        series.forEach(function(s){{
          scales['y_' + s.name] = {{ display:false }};
        }});
      }} else {{
        scales = {{
          x: {{ grid: {{ color: grid }} }},
          y: {{ grid: {{ color: grid }},
                ticks: {{ callback: function(v){{ return v + '%'; }} }} }}
        }};
      }}
      if (lineChart) lineChart.destroy();
      lineChart = new Chart(document.getElementById('cjLine'), {{
        type: 'line',
        data: {{ labels: labels, datasets: ds }},
        options: {{
          responsive: true, maintainAspectRatio: false,
          interaction: {{ mode: 'index', intersect: false }},
          plugins: {{
            legend: {{ position: 'top', labels: {{ usePointStyle: true, boxWidth: 8 }} }},
            tooltip: {{ callbacks: {{ label: function(c){{
              var suf = (mode === 'raw' ? '' : '%');
              return c.dataset.label + ': ' + c.parsed.y + suf;
            }} }} }}
          }},
          scales: scales
        }}
      }});
    }}

    window.cjSetMode = function(mode){{
      document.getElementById('cjModePct').classList.toggle('cj-btn-on', mode==='pct');
      document.getElementById('cjModeRaw').classList.toggle('cj-btn-on', mode==='raw');
      buildLine(mode);
    }};

    if (document.getElementById('cjLine')) buildLine('pct');

    if (document.getElementById('cjBar')) {{
      new Chart(document.getElementById('cjBar'), {{
        type: 'bar',
        data: {{ labels: {bl_json},
                 datasets: [{{ data: {bv_json}, backgroundColor: {bc_json},
                              borderRadius: 4 }}] }},
        options: {{
          responsive: true, maintainAspectRatio: false, indexAxis: 'y',
          plugins: {{ legend: {{ display: false }},
            tooltip: {{ callbacks: {{ label: function(c){{
              return (c.parsed.x>=0?'+':'') + c.parsed.x + '%'; }} }} }} }},
          scales: {{
            x: {{ grid: {{ color: grid }},
                  ticks: {{ callback: function(v){{ return v + '%'; }} }} }},
            y: {{ grid: {{ display:false }} }}
          }}
        }}
      }});
    }}
  }}
  init();
}})();
</script>
"""


def _market_status_bar(prices: dict) -> str:
    """横並び市場ステータスバー"""
    syms = [
        ("^N225",    "日経225",  True),
        ("^GSPC",    "S&P500",   True),
        ("^IXIC",    "Nasdaq",   True),
        ("USDJPY=X", "USD/JPY",  True),
        ("^VIX",     "VIX",      False),  # VIXは逆色
        ("GC=F",     "金(USD)",  True),
    ]
    items = []
    for sym, label, normal_dir in syms:
        p   = prices.get(sym, {})
        val = p.get("price", 0)
        chg = p.get("change_pct", 0)
        if normal_dir:
            color = GREEN if chg >= 0 else RED
        else:
            color = RED if chg >= 0 else GREEN  # VIX上昇=悪い
        sgn = "+" if chg >= 0 else ""
        fmt_val = f"{val:,.0f}" if val > 100 else f"{val:.2f}"
        items.append(f"""<div class="ms-item">
  <span class="ms-label">{label}</span>
  <span class="ms-value" style="color:{color}">{fmt_val}</span>
  <span class="ms-chg" style="color:{color}">{sgn}{chg:.2f}%</span>
</div>""")
        items.append('<div class="ms-sep"></div>')

    if items and items[-1] == '<div class="ms-sep"></div>':
        items.pop()

    return f'<div class="market-status-bar">{"".join(items)}</div>'


def _pro_insights(prices: dict) -> str:
    """日本市場プロ・クロス分析セクション。
    単独指標ではなく「指標間の関係」から市場の歪みを自動検出する。
    ① 日米恐怖スプレッド ② CME先物ギャップ ③ VIX期間構造
    ④ NT倍率ローテーション ⑤ グロース体温計 ⑥ 半導体動脈(SOX→東京)
    """
    def val(sym):
        r = prices.get(sym) or {}
        v = r.get("latest")
        return v if v is not None else r.get("price")

    def chg(sym):
        return (prices.get(sym) or {}).get("change_pct")

    n225   = val("^N225")
    topix  = val("^TOPX")
    nt     = val("NT_RATIO")
    nvi    = val("NIKKEI_VI")
    vix    = val("^VIX")
    vix9   = val("^VIX9D")
    vix3m  = val("^VIX3M")
    fut    = val("NIY=F")
    nt_chg   = chg("NT_RATIO")
    n225_chg = chg("^N225")
    g250_chg = chg("GROWTH250")
    sox_chg  = chg("^SOX")
    nvi_chg  = chg("NIKKEI_VI")

    GREEN, YELLOW, RED = "#3fb950", "#d29922", "#f85149"
    cards = []
    reds = yellows = 0

    def card(no, title, big, sub, color, light, pro, easy):
        return f"""
    <div class="card" style="padding:16px">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <span style="font-size:12px;color:#8b949e;font-weight:600">{no} {title}</span>
        <span style="font-size:16px">{light}</span>
      </div>
      <div style="font-size:26px;font-weight:800;margin:6px 0;color:{color}">{big}</div>
      <div style="font-size:11px;color:#8b949e">{sub}</div>
      <div style="margin-top:10px;padding:10px;background:rgba(88,166,255,.05);border-left:3px solid {color};border-radius:6px">
        <div style="font-size:12px;font-weight:700;color:{color}">🎩 プロの読み</div>
        <div style="font-size:12px;margin-top:4px;line-height:1.7">{pro}</div>
        <div style="font-size:11px;color:#8b949e;margin-top:6px;line-height:1.6">🦦 やさしく言うと：{easy}</div>
      </div>
    </div>"""

    # ── ① 日米恐怖スプレッド（日経VI − VIX）──
    if nvi is not None and vix is not None:
        spread = nvi - vix
        if spread >= 12:
            c, l = RED, "🔴"; reds += 1
            pro  = (f"日経VI {nvi:.1f} に対し米VIX {vix:.1f}。スプレッド +{spread:.1f}pt は明確な異常値。"
                    f"恐怖の震源地は<b>日本側</b>にある（円金利・日銀・円キャリー巻き戻し等の国内要因）。"
                    f"米国だけ見ていると足をすくわれる局面。")
            easy = "アメリカは落ち着いているのに、日本だけが怖がっている状態。日本固有の悪材料に注意。"
        elif spread >= 6:
            c, l = YELLOW, "🟡"; yellows += 1
            pro  = f"スプレッド +{spread:.1f}pt。日本側の警戒がやや先行。国内イベント（日銀・決算）の重みを増やして見るべき水準。"
            easy = "日本のほうが少しだけ神経質になっています。"
        elif spread <= -3:
            c, l = YELLOW, "🟡"; yellows += 1
            pro  = f"スプレッド {spread:.1f}pt と逆転。恐怖の震源は<b>米国側</b>。東京は米国発の下げをもらいやすい。"
            easy = "アメリカのほうが怖がっています。米市場の下げが日本に飛び火しやすい形。"
        else:
            c, l = GREEN, "🟢"
            pro  = f"スプレッド {spread:+.1f}pt は正常レンジ。日米の恐怖感は均衡しており、どちらか一方の固有リスクは観測されない。"
            easy = "日本とアメリカ、どちらも同じくらいの緊張感。特別な歪みなし。"
        cards.append(card("①", "日米 恐怖スプレッド", f"{spread:+.1f}pt",
                          f"日経VI {nvi:.2f} − VIX {vix:.2f}", c, l, pro, easy))

    # ── ② CME先物ギャップ（寄り付き予測）──
    if fut is not None and n225 is not None:
        gap = fut - n225
        gap_pct = gap / n225 * 100
        if abs(gap_pct) < 0.3:
            c, l = GREEN, "🟢"
            pro  = f"CME先物 {fut:,.0f} vs 現物 {n225:,.0f}。ギャップ {gap_pct:+.2f}% はほぼ無風。寄り付きは前日終値近辺でスタートする公算。"
            easy = "明日の朝はだいたい昨日の続きから始まりそう。"
        elif abs(gap_pct) < 0.8:
            c, l = YELLOW, "🟡"; yellows += 1
            d = "高く" if gap > 0 else "安く"
            pro  = f"ギャップ {gap_pct:+.2f}%。寄り付きは小幅に{d}始まる示唆。ギャップ方向に飛びつかず、寄り後30分の値動きで本物か判断するのが定石。"
            easy = f"朝は少し{d}始まりそう。あわてて飛び乗らないのがコツ。"
        else:
            c, l = RED, "🔴"; reds += 1
            d = "大幅高" if gap > 0 else "大幅安"
            pro  = f"ギャップ {gap_pct:+.2f}% の{d}スタート示唆。窓開け局面では寄り成り注文が偏り、最初の5分は値が飛ぶ。指値主体で。"
            easy = f"朝から大きく動いて始まりそう。最初の数分は様子見が安全。"
        cards.append(card("②", "CME先物ギャップ（寄り付き予測）", f"{gap_pct:+.2f}%",
                          f"CME日経先物 {fut:,.0f} − 現物 {n225:,.0f} = {gap:+,.0f}円", c, l, pro, easy))

    # ── ③ VIX期間構造（パニックの時間軸）──
    if vix9 is not None and vix3m is not None:
        ts = vix9 - vix3m
        if ts >= 2:
            c, l = RED, "🔴"; reds += 1
            pro  = (f"VIX9D {vix9:.1f} > VIX3M {vix3m:.1f}（バックワーデーション {ts:+.1f}pt）。"
                    f"「今この瞬間」の保険料が3ヶ月先より高い＝市場は直近イベントに身構えている。歴史的に底打ち反転もこの形から生まれる。")
            easy = "「今週がいちばん怖い」とみんなが思っている形。荒れやすいけど、底打ちのサインになることも。"
        elif ts > 0:
            c, l = YELLOW, "🟡"; yellows += 1
            pro  = f"期間構造 {ts:+.1f}pt の軽い逆転。平常時は右肩上がり（短期＜長期）が正常なので、短期警戒がやや過熱気味。"
            easy = "ふだんより「直近への警戒」が少し強め。"
        else:
            c, l = GREEN, "🟢"
            pro  = f"期間構造 {ts:+.1f}pt の正常コンタンゴ。短期＜長期の健全な形状で、目先のパニックは織り込まれていない。"
            easy = "ボラティリティ市場は平常運転。差し迫った恐怖はなし。"
        cards.append(card("③", "VIX期間構造（恐怖の時間軸）", f"{ts:+.1f}pt",
                          f"VIX9D {vix9:.2f} − VIX3M {vix3m:.2f}", c, l, pro, easy))

    # ── ④ NT倍率ローテーション ──
    if nt is not None:
        if nt_chg is not None and nt_chg <= -0.5:
            c, l = "#58a6ff", "🔵"
            pro  = (f"NT倍率 {nt:.2f}（{nt_chg:+.2f}%）と急低下。日経平均（半導体・値がさグロース）より"
                    f"TOPIX（銀行・商社・バリュー）が相対的に強い。<b>金利上昇・バリュー回帰</b>の典型パターン。")
            easy = "ハイテク株から銀行などの「地味だけど堅い株」へお金が引っ越し中。"
        elif nt_chg is not None and nt_chg >= 0.5:
            c, l = "#bc8cff", "🟣"
            pro  = (f"NT倍率 {nt:.2f}（{nt_chg:+.2f}%）と上昇。半導体・値がさ株が指数を牽引する"
                    f"<b>日経主導相場</b>。SOX指数との連動が強まる局面。")
            easy = "半導体などの花形株が相場を引っ張っています。"
        else:
            c, l = GREEN, "⚪"
            chg_s = f"{nt_chg:+.2f}%" if nt_chg is not None else "—"
            pro  = f"NT倍率 {nt:.2f}（{chg_s}）。日経・TOPIXの力関係は拮抗。明確なローテーションは観測されない。"
            easy = "ハイテク株もバリュー株も、今日は引き分け。"
        cards.append(card("④", "NT倍率（資金ローテーション）", f"{nt:.2f}",
                          f"日経平均 ÷ TOPIX ＝ 資金の流れの方位磁石", c, l, pro, easy))

    # ── ⑤ グロース体温計（個人マネーのリスク食欲）──
    if g250_chg is not None and n225_chg is not None:
        rel = g250_chg - n225_chg
        if rel >= 1.0:
            c, l = GREEN, "🟢"
            pro  = (f"グロース250 {g250_chg:+.2f}% vs 日経 {n225_chg:+.2f}%（相対 {rel:+.2f}pt）。"
                    f"大型株が売られる中でも個人マネーは小型グロースを物色。<b>リスク食欲は維持</b>されており、全面リスクオフではない。")
            easy = "プロが売っても個人投資家は元気。総崩れの心配はまだ薄い。"
        elif rel <= -1.0:
            c, l = RED, "🔴"; reds += 1
            pro  = (f"グロース250が相対 {rel:+.2f}pt の劣後。小型グロースから先に資金が逃げるのは"
                    f"<b>リスクオフの初期症状</b>。個人の信用買い残の投げに警戒。")
            easy = "個人投資家が小型株から逃げ始めています。市場全体の弱気サイン。"
        else:
            c, l = GREEN, "⚪"
            pro  = f"グロース250 {g250_chg:+.2f}% vs 日経 {n225_chg:+.2f}%。大型・小型のリスク選好に偏りなし。"
            easy = "大きい株も小さい株も同じような動き。"
        cards.append(card("⑤", "グロース体温計（個人のリスク食欲）", f"{rel:+.2f}pt",
                          f"グロース250 {g250_chg:+.2f}% − 日経 {n225_chg:+.2f}%", c, l, pro, easy))

    # ── ⑥ 半導体動脈（SOX → 東京への伝播）──
    if sox_chg is not None:
        if sox_chg <= -2.0:
            c, l = RED, "🔴"; reds += 1
            pro  = (f"フィラデルフィア半導体指数 {sox_chg:+.2f}%。SOXは東京エレク・アドバンテスト・レーザーテック"
                    f"の翌日株価と高相関。日経の指数寄与度上位が直撃されるため、<b>指数の重し</b>として作用する。")
            easy = "アメリカの半導体株が大きく下落。日本の半導体株も明日つられやすい。"
        elif sox_chg <= -0.5:
            c, l = YELLOW, "🟡"; yellows += 1
            pro  = f"SOX {sox_chg:+.2f}%。東京の半導体関連には軽い逆風。指数寄与の大きいアドバンテストの寄り付きに注目。"
            easy = "半導体株にちょっと向かい風。"
        elif sox_chg >= 2.0:
            c, l = GREEN, "🟢"
            pro  = f"SOX {sox_chg:+.2f}% の急伸。東京の半導体株に強い追い風。日経はTOPIXをアウトパフォームしやすい（NT倍率上昇要因）。"
            easy = "アメリカの半導体株が絶好調。日本の半導体株にも追い風。"
        else:
            c, l = GREEN, "⚪"
            pro  = f"SOX {sox_chg:+.2f}%。半導体経由の東京への影響は限定的。"
            easy = "半導体株は今日は静か。"
        cards.append(card("⑥", "半導体動脈（SOX→東京）", f"{sox_chg:+.2f}%",
                          "SOX指数 → 東エレク・アドテスト → 日経への伝播経路", c, l, pro, easy))

    if not cards:
        return ""

    # ── 総合判定バナー（ガネ先生の天気図）──
    if reds >= 2:
        w_emoji, w_title, w_color = "⛈", "嵐に備える日", RED
        verdict = "複数の警報が同時点灯。ポジションを軽くして現金比率を上げ、嵐が過ぎるのを待つのが上策じゃ。"
    elif reds == 1 or yellows >= 2:
        w_emoji, w_title, w_color = "🌥", "くもり・局地的に強風", YELLOW
        verdict = "全面警戒ではないが、点灯中の警報の方角からの風には注意。新規の大口買いは急がんでよい。"
    else:
        w_emoji, w_title, w_color = "☀", "おおむね晴れ", GREEN
        verdict = "指標間に大きな歪みはない。淡々といつもの戦略を続けてよい日じゃ。"

    nvi_note = ""
    if nvi is not None and nvi_chg is not None and nvi_chg >= 10:
        nvi_note = f"""
  <div style="margin-top:8px;padding:8px 12px;background:rgba(248,81,73,.1);border:1px solid rgba(248,81,73,.4);border-radius:8px;font-size:12px">
    ⚡ <b>速報級シグナル:</b> 日経VIが前日比 <b>{nvi_chg:+.1f}%</b> の急騰。VI急騰日は値幅が普段の1.5〜2倍に拡がりやすい。指値は普段より深めに。
  </div>"""

    return f"""
<section class="fade-up">
  <h2 class="section-title">🏛 プロの目 — クロス指標分析</h2>
  <div style="background:linear-gradient(135deg,#161b22,#1c2128);border:1px solid {w_color};border-radius:12px;padding:14px 18px;margin-bottom:14px">
    <div style="display:flex;align-items:center;gap:12px">
      <span style="font-size:34px">{w_emoji}</span>
      <div>
        <div style="font-weight:800;font-size:15px;color:{w_color}">本日の市場天気図：{w_title}</div>
        <div style="font-size:12px;color:#c9d1d9;margin-top:3px;line-height:1.7">🐘 ガネ先生「{verdict}」</div>
      </div>
    </div>{nvi_note}
  </div>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:12px">
    {''.join(cards)}
  </div>
  <div style="font-size:10px;color:#484f58;margin-top:8px">
    分析対象: 日経VI(日経公式) / TOPIX・グロース250(東証) / CME先物・VIX系・SOX(CBOE・PHLX) — 全て一次ソースから自動取得
  </div>
</section>
"""


def _risk_color(score: float) -> str:
    if score >= 1.5:   return GREEN
    if score >= 0.3:   return TEAL
    if score >= -0.3:  return YELLOW
    if score >= -1.5:  return ORANGE
    return RED


def _signal_class(score: float) -> str:
    if score >= 0.5:   return "signal-bull"
    if score >= -0.5:  return "signal-neutral"
    return "signal-bear"


def _signal_text(score: float) -> str:
    if score >= 2:    return "🚀 強気相場"
    if score >= 0.5:  return "😊 やや強気"
    if score >= -0.5: return "😐 中立"
    if score >= -2:   return "😟 やや弱気"
    return "🐻 弱気相場"


def _gauge_svg(score: float) -> str:
    """SVG + SMIL アニメーション付きリスクゲージを返す"""
    clamped = max(-3.0, min(3.0, score))
    # needle rotation: 0° = pointing up, ±90° = right/left
    needle_angle = clamped / 3.0 * 90.0
    color = _risk_color(clamped)

    # ゲージ弧: (20,110) → (180,110)  半径80の半円
    return f"""
<svg class="gauge-svg" viewBox="0 0 200 130" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="ggrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%"   stop-color="{RED}"/>
      <stop offset="30%"  stop-color="{ORANGE}"/>
      <stop offset="50%"  stop-color="{YELLOW}"/>
      <stop offset="75%"  stop-color="{TEAL}"/>
      <stop offset="100%" stop-color="{GREEN}"/>
    </linearGradient>
  </defs>
  <!-- 背景トラック -->
  <path d="M 20,110 A 80,80 0 0,1 180,110"
        stroke="{BORDER}" stroke-width="20" fill="none" stroke-linecap="round"/>
  <!-- カラーアーク -->
  <path d="M 20,110 A 80,80 0 0,1 180,110"
        stroke="url(#ggrad)" stroke-width="16" fill="none" stroke-linecap="round"/>
  <!-- マスク(中央を塗りつぶし) -->
  <circle cx="100" cy="110" r="60" fill="{CARD}"/>
  <!-- 針: 上向き基準(x1=100,y1=110 → x2=100,y2=40) をneedle_angle°回転 -->
  <line x1="100" y1="110" x2="100" y2="42"
        stroke="white" stroke-width="3" stroke-linecap="round">
    <animateTransform attributeName="transform" type="rotate"
      from="-90 100 110" to="{needle_angle:.1f} 100 110"
      dur="1.2s" calcMode="spline" keySplines="0.4 0 0.2 1" fill="freeze"/>
  </line>
  <!-- センタードット -->
  <circle cx="100" cy="110" r="6" fill="white" stroke="{CARD}" stroke-width="2"/>
  <!-- スコア表示 -->
  <text x="100" y="96" text-anchor="middle"
        fill="{color}" font-family="'Noto Sans JP', sans-serif"
        font-size="20" font-weight="900">{score:+.2f}</text>
  <!-- ラベル -->
  <text x="22"  y="128" fill="{RED}"    font-family="sans-serif" font-size="10">弱気</text>
  <text x="162" y="128" fill="{GREEN}"  font-family="sans-serif" font-size="10">強気</text>
  <text x="100" y="20"  fill="{YELLOW}" font-family="sans-serif" font-size="10"
        text-anchor="middle">中立</text>
</svg>"""


def _stock_cards(prices: dict, technical: dict) -> str:
    """銘柄カードグリッド HTML"""
    symbols = {
        "^N225":   ("日経225", "JPY"),
        "^GSPC":   ("S&P500",  "USD"),
        "USDJPY=X":("USD/JPY", ""),
        "^VIX":    ("VIX",     ""),
        "GC=F":    ("金",      "USD"),
        "BTC-USD": ("BTC",     "USD"),
        "^IXIC":   ("Nasdaq",  "USD"),
        "^TNX":    ("米10年債",""),
    }
    tech_signals = (technical or {}).get("signals", {})

    cards = []
    for sym, (name, unit) in symbols.items():
        p = (prices or {}).get(sym, {})
        if not p:
            continue
        latest = p.get("latest") or p.get("close") or 0
        chg    = p.get("change_pct") or p.get("chg_pct") or 0
        rsi    = p.get("rsi") or tech_signals.get(sym, {}).get("rsi") or 0

        if chg >= 0.3:
            chg_cls = "chg-up";   chg_mark = "▲"
        elif chg <= -0.3:
            chg_cls = "chg-down"; chg_mark = "▼"
        else:
            chg_cls = "chg-flat"; chg_mark = "━"

        # RSI バー
        rsi_color = GREEN if rsi >= 60 else (RED if rsi <= 40 else YELLOW)
        rsi_pct   = int(rsi) if rsi else 50
        rsi_bar   = ""
        if rsi:
            rsi_bar = f"""
<div class="rsi-bar-wrap">
  <div class="rsi-bar" style="width:{rsi_pct}%;background:{rsi_color}"></div>
</div>
<div class="rsi-label">RSI {rsi:.0f}</div>"""

        # 評価バッジ
        rating = ""
        if rsi >= 70:   rating = f'<span style="color:{RED};font-size:10px;font-weight:700"> 買われすぎ</span>'
        elif rsi <= 30: rating = f'<span style="color:{GREEN};font-size:10px;font-weight:700"> 売られすぎ</span>'

        # 価格フォーマット
        val_str = f"{latest:,.2f}" if latest < 1000 else f"{latest:,.0f}"

        cards.append(f"""
<div class="price-card fade-up">
  <div class="price-name">{name} <span style="font-size:9px;opacity:.6">{sym}</span></div>
  <div class="price-value" style="color:{_risk_color(chg)}">{val_str} <span style="font-size:11px;color:var(--muted)">{unit}</span></div>
  <div class="price-chg {chg_cls}">{chg_mark} {chg:+.2f}%{rating}</div>
  {rsi_bar}
</div>""")

    return f'<div class="grid-auto">{"".join(cards)}</div>'


def _sector_heatmap(sector_analysis: dict) -> str:
    """セクターヒートマップ HTML"""
    sa = sector_analysis or {}
    if not sa.get("available"):
        return '<p style="color:var(--muted);font-size:13px">セクターデータなし（平日のみ）</p>'

    sectors_raw = sa.get("sectors", [])

    # list形式: [{name, chg_1d, ...}, ...] → dict形式に正規化
    if isinstance(sectors_raw, list):
        sectors = {}
        for item in sectors_raw:
            if isinstance(item, dict):
                n = item.get("name") or item.get("symbol", "")
                c = item.get("chg_1d") or item.get("change_pct") or item.get("chg") or 0
                sectors[n] = {"change_pct": c}
    elif isinstance(sectors_raw, dict):
        sectors = sectors_raw
    else:
        sectors = {}

    if not sectors:
        top3    = sa.get("top3",    [])
        bottom3 = sa.get("bottom3", [])
        items   = [(s, 1.5) for s in top3] + [(s, -1.5) for s in bottom3]
        sectors = {s: {"change_pct": c} for s, c in items}

    cells = []
    for name, data in sectors.items():
        if isinstance(data, dict):
            chg = data.get("change_pct") or data.get("chg") or 0
        else:
            chg = float(data)

        if chg >= 2:
            bg, fg = "rgba(63,185,80,.25)",  GREEN
        elif chg >= 0.5:
            bg, fg = "rgba(63,185,80,.12)",  TEAL
        elif chg >= -0.5:
            bg, fg = "rgba(139,148,158,.1)", MUTED
        elif chg >= -2:
            bg, fg = "rgba(219,109,40,.2)",  ORANGE
        else:
            bg, fg = "rgba(248,81,73,.25)",  RED

        cells.append(f"""
<div class="sector-cell" style="background:{bg};color:{fg}">
  <div style="font-size:15px">{chg:+.1f}%</div>
  <div class="sector-name">{name}</div>
</div>""")

    return f'<div class="sector-grid">{"".join(cells)}</div>'


def _youtube_section(youtube_summary: dict) -> str:
    """YouTube動画 本格分析セクション HTML。"""
    yt = youtube_summary or {}
    if not yt.get("available"):
        return ""
    videos = yt.get("videos", []) or []
    if not videos:
        return ""

    def _fmt_analysis(text: str) -> str:
        # 【見出し】を装飾。本文は改行を <br> に。
        import re as _re
        text = (text or "").strip()
        if not text:
            return ""
        text = _re.sub(
            r"【(.+?)】",
            r'</div><div class="yt-sub">\1</div><div class="yt-body">',
            text,
        )
        return f'<div class="yt-body">{text}</div>'.replace("<br>\n", "<br>")\
            .replace("\n", "<br>")

    cards = []
    is_video = yt.get("mode") == "video"
    for v in videos:
        title   = (v.get("title", "") or "").replace("<", "&lt;").replace(">", "&gt;")
        url     = v.get("url", "#")
        channel = v.get("channel", "")
        analysis_html = _fmt_analysis(v.get("analysis", "")) if is_video else ""
        cards.append(f"""
  <div class="card fade-up" style="margin-bottom:10px">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
      <span style="font-size:18px">🎬</span>
      <div>
        <div style="font-size:11px;color:var(--muted)">{channel}</div>
        <a href="{url}" target="_blank" rel="noopener"
           style="font-size:13px;font-weight:700;color:var(--blue);text-decoration:none">{title}</a>
      </div>
    </div>
    {analysis_html}
  </div>""")

    # フォールバック（タイトル推測）のときは points/impact を補足表示
    extra = ""
    if not is_video:
        if yt.get("points"):
            extra += f'<div class="yt-sub">💡 動画のポイント</div><div class="yt-body">{yt["points"]}</div>'
        if yt.get("impact"):
            extra += f'<div class="yt-sub">📊 市場への示唆</div><div class="yt-body">{yt["impact"]}</div>'
        if extra:
            extra = f'<div class="card fade-up">{extra}</div>'

    tag = "AIが動画を視聴して要約" if is_video else "タイトルから推測"
    return f"""
<!-- ── YouTube 本格分析 ── -->
<section>
  <div class="section-header">
    <span class="section-icon">📺</span>
    <span class="section-title">YouTube相場解説 AI要約</span>
    <span class="section-tag">{tag}</span>
  </div>
{"".join(cards)}
{extra}
</section>
"""


def _news_section(news: list) -> str:
    """ニュース一覧 HTML（最大12件）"""
    items = []
    for n in (news or [])[:12]:
        title = n.get("title", "")
        url   = n.get("url",   "#")
        src   = n.get("source", n.get("category", ""))
        imp   = n.get("importance", n.get("imp", "mid"))

        # importance の正規化
        if isinstance(imp, str):
            imp_str = imp.lower()
        else:
            imp_str = "mid" if imp >= 0 else "low"
        if imp_str in ("high", "a", "高"):
            badge_cls, badge_lbl = "badge-high", "高"
        elif imp_str in ("mid", "b", "中"):
            badge_cls, badge_lbl = "badge-mid",  "中"
        else:
            badge_cls, badge_lbl = "badge-low",  "低"

        items.append(f"""
<div class="news-item">
  <span class="news-badge {badge_cls}">{badge_lbl}</span>
  <div>
    <a class="news-title" href="{url}" target="_blank" rel="noopener">{title}</a>
    <div class="news-source">{src}</div>
  </div>
</div>""")

    return "\n".join(items)


def _ai_discussion(team_debate: dict, ai_summary: dict) -> str:
    """AIチーム議論セクション HTML"""
    td = team_debate or {}
    ai = ai_summary  or {}

    members_html = ""

    if td.get("available") or td.get("status") == "success":
        members = td.get("members", {})
        configs = [
            ("マーケット太郎", "🐂", "av-bull",    "bull_view"),
            ("ニュース花子",   "📰", "av-neutral",  "neutral_view"),
            ("リスク次郎",    "🐻", "av-bear",     "bear_view"),
        ]
        for name, icon, av_cls, fallback_key in configs:
            m  = members.get(name, {})
            op = m.get("opinion") or m.get("view") or ai.get(fallback_key, "")
            vt = m.get("vote", "")
            if not op:
                continue
            vote_html = f'<span style="font-size:11px;color:var(--muted)"> → 投票: {vt}</span>' if vt else ""
            members_html += f"""
<div class="debate-member">
  <div class="debate-avatar {av_cls}">{icon}</div>
  <div class="debate-bubble">
    <div class="debate-name">{name}{vote_html}</div>
    {op[:200]}{"..." if len(op) > 200 else ""}
  </div>
</div>"""

        fd   = td.get("final_decision", "")
        conf = td.get("confidence", 0)
        if fd:
            conf_pct = f"{conf*100:.0f}%" if conf else "?"
            color    = GREEN if "強気" in fd or "楽観" in fd else (RED if "弱気" in fd or "悲観" in fd else YELLOW)
            members_html += f"""
<div class="debate-verdict">
  <div class="verdict-icon">⚖️</div>
  <div>
    <div class="verdict-text" style="color:{color}">{fd}</div>
    <div class="verdict-conf">合議信頼度: {conf_pct}</div>
  </div>
</div>"""
    else:
        # ai_summary フォールバック
        for label, icon, key, av_cls in [
            ("強気分析", "🐂", "bull_view",    "av-bull"),
            ("弱気分析", "🐻", "bear_view",    "av-bear"),
            ("中立分析", "😐", "neutral_view", "av-neutral"),
        ]:
            op = ai.get(key, "")
            if not op:
                continue
            members_html += f"""
<div class="debate-member">
  <div class="debate-avatar {av_cls}">{icon}</div>
  <div class="debate-bubble">
    <div class="debate-name">{label}</div>
    {op[:200]}{"..." if len(op) > 200 else ""}
  </div>
</div>"""

    return members_html or '<p style="color:var(--muted);font-size:13px">AI議論データなし</p>'


def _calendar_section(weekly_calendar: dict) -> str:
    """週次イベントカレンダー HTML"""
    wc = weekly_calendar or {}
    events = wc.get("events", [])
    if not events:
        return '<p style="color:var(--muted);font-size:13px">今週の主要イベントなし</p>'

    items = []
    for ev in events[:10]:
        if isinstance(ev, dict):
            date    = ev.get("date", ev.get("day", ""))
            title   = ev.get("title", ev.get("event", str(ev)))
            impact  = ev.get("impact", ev.get("importance", ""))
        else:
            date, title, impact = "", str(ev), ""

        imp_cls = ""
        if isinstance(impact, str) and impact.lower() in ("high", "★★★", "高"):
            imp_cls = "cal-impact-high"
        elif isinstance(impact, str) and impact.lower() in ("mid", "★★", "中"):
            imp_cls = "cal-impact-mid"

        items.append(f"""
<div class="cal-item">
  <div class="cal-date">{date}</div>
  <div class="cal-event {imp_cls}">{title}</div>
</div>""")

    return "\n".join(items)


def _prediction_section(prediction_tracker: dict) -> str:
    """AI予測精度セクション HTML（確信度 + Brierスコア付き）"""
    pt    = prediction_tracker or {}
    stats = pt.get("stats", {})
    preds = pt.get("recent_predictions", pt.get("recent",
                   stats.get("recent5", [])))

    # ── 正解率 ──
    d10  = stats.get("10d", {})
    rate = d10.get("rate")        # None or float (%)
    tot  = d10.get("total",  0)
    hits = d10.get("correct", 0)
    if rate is None:
        rate_txt  = "---"
        bar_col   = YELLOW
        acc_pct   = 50
    else:
        acc_pct   = int(rate)
        bar_col   = GREEN if acc_pct >= 60 else (YELLOW if acc_pct >= 40 else RED)
        rate_txt  = f"{acc_pct}%"

    # ── Brierスコア ──
    brier = stats.get("brier_30d")
    if brier is not None:
        if brier <= 0.12:
            brier_label = "優秀"
            brier_col   = GREEN
        elif brier <= 0.20:
            brier_label = "良好"
            brier_col   = TEAL
        elif brier <= 0.25:
            brier_label = "普通"
            brier_col   = YELLOW
        else:
            brier_label = "過信"
            brier_col   = ORANGE
        brier_html = (
            f'<div style="display:flex;align-items:center;gap:8px;margin-top:6px">'
            f'<span style="font-size:11px;color:var(--muted)">Brierスコア(30日):</span>'
            f'<span style="font-weight:700;color:{brier_col}">{brier:.3f}</span>'
            f'<span style="font-size:10px;color:{brier_col};background:rgba(0,0,0,.15);'
            f'padding:1px 5px;border-radius:4px">{brier_label}</span>'
            f'<span style="font-size:9px;color:var(--muted)">0=完璧/0.25=ランダム</span>'
            f'</div>'
        )
    else:
        brier_html = '<div style="font-size:10px;color:var(--muted);margin-top:4px">Brierスコア: 確信度データ蓄積中</div>'

    # ── 直近5日の予測履歴 ──
    dir_icons = {"bull": "📈", "bear": "📉", "neutral": "➡️"}
    rows_html = ""
    for p in (preds or [])[:5]:
        if not isinstance(p, dict):
            continue
        dt   = p.get("date", "")[:10]
        sig  = p.get("signal", p.get("prediction",
               dir_icons.get(p.get("direction",""), "") + " " + p.get("direction", "")))
        ok   = p.get("correct", None)
        conf = p.get("confidence")
        conf_txt = f' <span style="font-size:9px;color:var(--muted)">{conf:.0%}</span>' if conf else ""
        if ok is True:
            res_html = f'<span class="pred-hit">✓ 正解</span>'
        elif ok is False:
            res_html = f'<span class="pred-miss">✗ 不正解</span>'
        else:
            res_html = f'<span style="color:var(--muted)">検証中</span>'
        rows_html += f'<div class="pred-row"><span>{dt} {sig}{conf_txt}</span>{res_html}</div>'

    return f"""
<div class="stat-row">
  <span class="stat-value" style="color:{bar_col}">{rate_txt}</span>
  <span class="stat-unit">正解率・直近10日 ({hits}/{tot}件)</span>
</div>
<div class="acc-bar-wrap">
  <div class="acc-bar" style="width:{acc_pct}%;background:{bar_col}"></div>
</div>
{brier_html}
{rows_html}"""


def _fg_section(fear_greed: dict) -> str:
    """Fear & Greedメーターセクション"""
    fg      = fear_greed or {}
    score   = fg.get("score") or 50
    rating  = fg.get("rating_ja", fg.get("rating", ""))
    pct     = max(0, min(100, score))

    if score >= 75:     color = GREEN
    elif score >= 55:   color = TEAL
    elif score >= 45:   color = YELLOW
    elif score >= 25:   color = ORANGE
    else:               color = RED

    return f"""
<div class="stat-row">
  <span class="stat-value" style="color:{color}">{score}</span>
  <span class="stat-unit">/100 — {rating}</span>
</div>
<div class="fg-meter">
  <div class="fg-pointer" style="left:{pct}%"></div>
</div>
<div style="display:flex;justify-content:space-between;font-size:10px;color:var(--muted);margin-top:6px">
  <span>恐怖</span><span>中立</span><span>強欲</span>
</div>"""


# ────────────────────────────────────────────────────────────────
# メイン生成関数
# ────────────────────────────────────────────────────────────────

def _integrity_section(di: dict) -> str:
    """データ健全性バッジ（精度②）。異常があれば目立たせる。"""
    di = di or {}
    if not di.get("available"):
        return ""
    sev     = di.get("max_severity", "ok")
    checked = di.get("checked", 0)
    ok      = di.get("ok", 0)
    summary = di.get("summary", "")
    if sev == "ok":
        color, icon, label = "#3fb950", "✅", "データ健全性 良好"
    elif sev == "warn":
        color, icon, label = "#d29922", "⚠️", "データに軽微な要確認"
    else:
        color, icon, label = "#f85149", "🚨", "データに重大な異常"
    items = ""
    for i in (di.get("issues") or [])[:6]:
        items += (f'<div style="font-size:12px;color:var(--muted);padding:2px 0">'
                  f'• {i.get("name","")}: {i.get("msg","")}</div>')
    badge = (f'<span style="background:{color}22;color:{color};border:1px solid {color}55;'
             f'border-radius:6px;padding:2px 8px;font-size:11px;font-weight:700">'
             f'{ok}/{checked} 正常</span>')
    return f"""
<section>
  <div class="card fade-up" style="border-left:3px solid {color}">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;flex-wrap:wrap">
      <span style="font-size:16px">{icon}</span>
      <span style="font-weight:700;font-size:13px;color:{color}">{label}</span>
      {badge}
    </div>
    <div style="font-size:12px;color:var(--muted)">{summary}（取得した全データを毎朝自動検査）</div>
    {items}
  </div>
</section>
"""


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
    **_kwargs,
) -> str:
    """
    docs/daily_report.html を生成してパスを返す。
    失敗時は '' を返す。
    """
    prices           = prices           or {}
    news             = news             or []
    risk             = risk             or {}
    fear_greed       = fear_greed       or {}
    ai_summary       = ai_summary       or {}
    sector_analysis  = sector_analysis  or {}
    team_debate      = team_debate      or {}
    prediction_tracker = prediction_tracker or {}
    weekly_calendar  = weekly_calendar  or {}

    today = get_today_str()
    now   = get_jst_now().strftime("%Y-%m-%d %H:%M JST")
    score = risk.get("score", 0)

    signal_cls  = _signal_class(score)
    signal_text = _signal_text(score)
    risk_color  = _risk_color(score)

    # ムード判定（VIX/USD/JPY変化率から）
    usdjpy_chg = (prices.get("USDJPY=X") or {}).get("change_pct", 0) or 0
    vix_val    = (prices.get("^VIX")     or {}).get("price",      18) or 18
    if score >= 1:      mood = "bullish"
    elif score >= 0:    mood = "analyzing"
    elif score >= -1:   mood = "uncertain"
    else:               mood = "bearish"

    gauge_svg    = _gauge_svg(score)
    stocks_html  = _stock_cards(prices, technical)
    sector_html  = _sector_heatmap(sector_analysis)
    news_html    = _news_section(news)
    debate_html  = _ai_discussion(team_debate, ai_summary)
    cal_html     = _calendar_section(weekly_calendar)
    pred_html    = _prediction_section(prediction_tracker)
    yt_html      = _youtube_section(youtube_summary)
    di_html      = _integrity_section(data_integrity)
    fg_html      = _fg_section(fear_greed)
    char_header  = _character_header(score, prices, mood, today, now)
    qs_html      = _quick_summary(prices, risk, fear_greed, technical)
    watch_html   = _watchlist(prices, technical)
    status_bar   = _market_status_bar(prices)
    sc_html      = _scenarios_html(scenario)
    pro_html     = _pro_insights(prices)

    # B案：Chart.js 用ヒストリー（取得失敗してもレポートは継続）
    try:
        from src.price_history import fetch_history
        _history = fetch_history()
    except Exception as _e:
        logger.warning(f"ヒストリー取得スキップ: {_e}")
        _history = {}
    chartjs_html = _chartjs_section(_history, prices)

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ガネ先生とカワウソくんの相場ダイジェスト — {today}</title>
<style>
{_CSS}
</style>
</head>
<body>

<!-- ── アクセントライン ── -->
<div style="height:2px;background:linear-gradient(90deg,#7b61ff,#00d4ff,#00e676)"></div>

<!-- ── リアルタイムティッカーテープ（TradingView）── -->
<div style="position:sticky;top:0;z-index:100;background:#090d14;border-bottom:1px solid rgba(0,212,255,.1)">
  <div class="tradingview-widget-container">
    <div class="tradingview-widget-container__widget"></div>
    <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-ticker-tape.js" async>
    {{
      "symbols": [
        {{"proName":"TVC:NI225",      "title":"日経225"}},
        {{"proName":"TSE:TOPIX",      "title":"TOPIX"}},
        {{"proName":"SP:SPX",         "title":"S&P500"}},
        {{"proName":"NASDAQ:NDX",     "title":"Nasdaq100"}},
        {{"proName":"FX:USDJPY",      "title":"ドル円"}},
        {{"proName":"FX:EURJPY",      "title":"ユーロ円"}},
        {{"proName":"TVC:GOLD",       "title":"金"}},
        {{"proName":"TVC:USOIL",      "title":"原油"}},
        {{"proName":"BITSTAMP:BTCUSD","title":"BTC"}},
        {{"proName":"CBOE:VIX",       "title":"VIX"}}
      ],
      "showSymbolLogo": false,
      "isTransparent": true,
      "displayMode": "adaptive",
      "colorTheme": "dark",
      "locale": "ja",
      "width": "100%",
      "height": 44
    }}
    </script>
  </div>
</div>

<!-- ── キャラクターヘッダー ── -->
{char_header}

<main class="container">

<!-- ── データ生成時刻の注記 ── -->
<div style="background:rgba(0,212,255,.04);border:1px solid rgba(0,212,255,.12);border-radius:8px;padding:8px 14px;margin-bottom:12px;font-size:11px;color:#6b7d90;display:flex;align-items:center;gap:8px">
  <span style="color:#00d4ff">📊</span><span>下の数値はレポート生成時刻（{now}）のデータです。リアルタイムチャートはTradingViewウィジェットをご覧ください。</span>
</div>

<!-- ── クイックサマリー ── -->
{qs_html}

<!-- ── 市場ステータスバー ── -->
{status_bar}

<!-- ── データ健全性バッジ ── -->
{di_html}

<!-- ── プロの目: クロス指標分析 ── -->
{pro_html}

<!-- ── Row 1: ゲージ / FearGreed ── -->
<section>
  <div class="grid-2">
    <!-- リスクゲージ -->
    <div class="card fade-up">
      <div class="card-title">AIリスクゲージ</div>
      <div class="gauge-wrap">
        {gauge_svg}
        <div class="gauge-score-label">リスクスコア（−3〜＋3）</div>
      </div>
      <div style="margin-top:12px;font-size:12px;color:var(--muted)">
        シグナル: {", ".join(s.get("indicator","") + s.get("direction","") for s in risk.get("signals", [])[:3]) or "なし"}
      </div>
    </div>

    <!-- Fear & Greed -->
    <div class="card fade-up">
      <div class="card-title">Fear &amp; Greed 指数</div>
      {fg_html}
      <div style="margin-top:14px">
        <div class="card-title">今日の判断</div>
        <div style="font-size:24px;margin:4px 0">{signal_text}</div>
        <div style="font-size:12px;color:var(--muted)">
          地合い: <span style="color:{risk_color};font-weight:700">{risk.get("sentiment","---")}</span>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- ── リアルタイムチャート（TradingView） ── -->
<section>
  <div class="section-header">
    <span class="section-icon">📈</span>
    <span class="section-title">リアルタイムチャート</span>
    <span class="section-tag">TradingView</span>
  </div>
  <div class="grid-2">
    <!-- 日経225 チャート -->
    <div class="card fade-up" style="padding:0;overflow:hidden">
      <div style="padding:10px 12px 6px;font-size:11px;font-weight:700;color:var(--muted)">🇯🇵 日経225（現物）</div>
      <div class="tradingview-widget-container">
        <div class="tradingview-widget-container__widget"></div>
        <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-mini-symbol-overview.js" async>
        {{
          "symbol": "TVC:NI225",
          "width": "100%",
          "height": 200,
          "locale": "ja",
          "dateRange": "1D",
          "colorTheme": "dark",
          "isTransparent": true,
          "autosize": true
        }}
        </script>
      </div>
    </div>
    <!-- 日経先物 チャート -->
    <div class="card fade-up" style="padding:0;overflow:hidden">
      <div style="padding:10px 12px 6px;font-size:11px;font-weight:700;color:var(--muted)">🇯🇵 日経225先物（CME）</div>
      <div class="tradingview-widget-container">
        <div class="tradingview-widget-container__widget"></div>
        <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-mini-symbol-overview.js" async>
        {{
          "symbol": "CME:NKD1!",
          "width": "100%",
          "height": 200,
          "locale": "ja",
          "dateRange": "1D",
          "colorTheme": "dark",
          "isTransparent": true,
          "autosize": true
        }}
        </script>
      </div>
    </div>
  </div>

  <div class="grid-2" style="margin-top:10px">
    <!-- S&P500 チャート -->
    <div class="card fade-up" style="padding:0;overflow:hidden">
      <div style="padding:10px 12px 6px;font-size:11px;font-weight:700;color:var(--muted)">🇺🇸 S&amp;P500（現物）</div>
      <div class="tradingview-widget-container">
        <div class="tradingview-widget-container__widget"></div>
        <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-mini-symbol-overview.js" async>
        {{
          "symbol": "SP:SPX",
          "width": "100%",
          "height": 200,
          "locale": "ja",
          "dateRange": "1D",
          "colorTheme": "dark",
          "isTransparent": true,
          "autosize": true
        }}
        </script>
      </div>
    </div>
    <!-- S&P500先物 チャート -->
    <div class="card fade-up" style="padding:0;overflow:hidden">
      <div style="padding:10px 12px 6px;font-size:11px;font-weight:700;color:var(--muted)">🇺🇸 S&amp;P500先物（E-mini）</div>
      <div class="tradingview-widget-container">
        <div class="tradingview-widget-container__widget"></div>
        <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-mini-symbol-overview.js" async>
        {{
          "symbol": "CME_MINI:ES1!",
          "width": "100%",
          "height": 200,
          "locale": "ja",
          "dateRange": "1D",
          "colorTheme": "dark",
          "isTransparent": true,
          "autosize": true
        }}
        </script>
      </div>
    </div>
  </div>

  <!-- ドル円チャート -->
  <div class="card fade-up" style="padding:0;overflow:hidden;margin-top:10px">
    <div style="padding:10px 12px 6px;font-size:11px;font-weight:700;color:var(--muted)">💴 USD/JPY ドル円（リアルタイム）</div>
    <div class="tradingview-widget-container">
      <div class="tradingview-widget-container__widget"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-mini-symbol-overview.js" async>
      {{
        "symbol": "FX:USDJPY",
        "width": "100%",
        "height": 160,
        "locale": "ja",
        "dateRange": "1D",
        "colorTheme": "dark",
        "isTransparent": true,
        "autosize": true
      }}
      </script>
    </div>
  </div>
</section>

<!-- ── インタラクティブ・データチャート（Chart.js）── -->
{chartjs_html}

<!-- ── マーケット概況（詳細カード）── -->
<section>
  <div class="section-header">
    <span class="section-icon">💹</span>
    <span class="section-title">マーケット詳細データ</span>
    <span class="section-tag">{today}</span>
  </div>
  {stocks_html}
</section>

<!-- ── 注目ウォッチリスト ── -->
<section>
  <div class="section-header">
    <span class="section-icon">👀</span>
    <span class="section-title">今日のウォッチリスト</span>
    <span class="section-tag">注目銘柄・資産</span>
  </div>
  <div class="card fade-up">
    {watch_html}
  </div>
</section>

<!-- ── 3シナリオ分析 ── -->
{sc_html}

<!-- ── セクターヒートマップ ── -->
<section>
  <div class="section-header">
    <span class="section-icon">🏭</span>
    <span class="section-title">セクター別ヒートマップ</span>
    <span class="section-tag">前日比</span>
  </div>
  <div class="card fade-up">
    {sector_html}
  </div>
  <!-- TradingView マーケット概況 -->
  <div style="margin-top:12px;border-radius:10px;overflow:hidden">
    <div class="tradingview-widget-container">
      <div class="tradingview-widget-container__widget"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-market-overview.js" async>
      {{
        "colorTheme": "dark",
        "dateRange": "1D",
        "showChart": true,
        "locale": "ja",
        "width": "100%",
        "height": 400,
        "largeChartUrl": "",
        "isTransparent": true,
        "showSymbolLogo": false,
        "showFloatingTooltip": false,
        "plotLineColorGrowing": "rgba(41, 98, 255, 1)",
        "plotLineColorFalling": "rgba(41, 98, 255, 1)",
        "gridLineColor": "rgba(240, 243, 250, 0)",
        "scaleFontColor": "rgba(120, 123, 134, 1)",
        "belowLineFillColorGrowing": "rgba(41, 98, 255, 0.12)",
        "belowLineFillColorFalling": "rgba(41, 98, 255, 0.12)",
        "belowLineFillColorGrowingBottom": "rgba(41, 98, 255, 0)",
        "belowLineFillColorFallingBottom": "rgba(41, 98, 255, 0)",
        "symbolActiveColor": "rgba(41, 98, 255, 0.12)",
        "tabs": [
          {{
            "title": "日本株",
            "symbols": [
              {{"s": "TVC:NI225",  "d": "日経225"}},
              {{"s": "TSE:TOPIX",  "d": "TOPIX"}},
              {{"s": "TVC:NI225",  "d": "グロース250"}}
            ]
          }},
          {{
            "title": "米国株",
            "symbols": [
              {{"s": "SP:SPX",     "d": "S&P500"}},
              {{"s": "NASDAQ:NDX", "d": "Nasdaq100"}},
              {{"s": "DJ:DJI",     "d": "Dow Jones"}}
            ]
          }},
          {{
            "title": "為替",
            "symbols": [
              {{"s": "FX:USDJPY",  "d": "ドル円"}},
              {{"s": "FX:EURJPY",  "d": "ユーロ円"}},
              {{"s": "FX:GBPJPY",  "d": "ポンド円"}}
            ]
          }},
          {{
            "title": "コモディティ",
            "symbols": [
              {{"s": "TVC:GOLD",   "d": "金"}},
              {{"s": "TVC:USOIL",  "d": "原油"}},
              {{"s": "TVC:SILVER", "d": "銀"}}
            ]
          }}
        ]
      }}
      </script>
    </div>
  </div>
</section>

<!-- ── AIチーム議論 ── -->
<section>
  <div class="section-header">
    <span class="section-icon">🤖</span>
    <span class="section-title">AIチーム分析・議論</span>
    <span class="section-tag">ガネ先生チーム</span>
  </div>
  <div class="card fade-up">
    {debate_html}
  </div>
</section>

<!-- ── YouTube 本格分析 ── -->
{yt_html}

<!-- ── ニュース ── -->
<section>
  <div class="section-header">
    <span class="section-icon">📰</span>
    <span class="section-title">注目ニュース</span>
    <span class="section-tag">重要度別</span>
  </div>
  <div class="card fade-up">
    {news_html}
  </div>
</section>

<!-- ── イベントカレンダー / 予測精度 ── -->
<section>
  <div class="grid-2">
    <div>
      <div class="section-header">
        <span class="section-icon">📅</span>
        <span class="section-title">今週のイベント</span>
      </div>
      <div class="card fade-up">
        {cal_html}
      </div>
    </div>
    <div>
      <div class="section-header">
        <span class="section-icon">🎯</span>
        <span class="section-title">AI予測精度</span>
      </div>
      <div class="card fade-up">
        {pred_html}
      </div>
    </div>
  </div>
</section>

</main>

<!-- ── フッター ── -->
<footer style="text-align:center;padding:24px 16px;color:var(--muted);font-size:11px;border-top:1px solid rgba(0,212,255,.1);margin-top:20px;background:linear-gradient(0deg,rgba(0,0,0,.3),transparent)">
  <div style="font-size:16px;margin-bottom:6px">🐘 ガネ先生 &amp; 🦦 カワウソくん</div>
  <div>AIチーム自動生成レポート · {now}</div>
  <div style="margin-top:6px;color:#00d4ff;font-weight:700">Powered by Gemini AI × 市場AI秘書</div>
</footer>

<script>
(function(){{
  const els = document.querySelectorAll('.fade-up');
  const io  = new IntersectionObserver(entries => {{
    entries.forEach(e => {{ if(e.isIntersecting) e.target.style.animationDelay = '0s'; }});
  }}, {{threshold:0.1}});
  els.forEach((el,i) => {{
    el.style.animationDelay = (i * 0.06) + 's';
    io.observe(el);
  }});
}})();

</script>

</body>
</html>"""

    # docs/ に保存
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


# ────────────────────────────────────────────────────────────────
# エントリーポイント（cloud_run.py から呼ぶ）
# ────────────────────────────────────────────────────────────────

def run(
    prices: dict = None,
    news: list   = None,
    risk: dict   = None,
    fear_greed: dict = None,
    ai_summary: dict = None,
    scenario: dict   = None,
    technical: dict  = None,
    sector_analysis: dict      = None,
    prediction_tracker: dict   = None,
    weekly_calendar: dict      = None,
    team_debate: dict          = None,
    youtube_summary: dict      = None,
    data_integrity: dict       = None,
    mode: str = "morning",
    **_kwargs,
) -> dict:
    try:
        path = generate(
            mode=mode,
            prices=prices,
            news=news,
            risk=risk,
            fear_greed=fear_greed,
            ai_summary=ai_summary,
            scenario=scenario,
            technical=technical,
            youtube_summary=youtube_summary,
            data_integrity=data_integrity,
            sector_analysis=sector_analysis,
            prediction_tracker=prediction_tracker,
            weekly_calendar=weekly_calendar,
            team_debate=team_debate,
        )
        logger.info(f"✅ デザインAIレポート生成: {path}")
        return {"available": True, "path": path}
    except Exception:
        logger.error("デザインAI生成エラー")
        logger.debug(traceback.format_exc())
        return {"available": False}
