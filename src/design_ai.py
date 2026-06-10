"""
src/design_ai.py  ─  デザインAIエージェント
プロ品質の HTMLデイリーレポートを自動生成し docs/daily_report.html に保存する。
"""

import math
import traceback
from pathlib import Path
from src.utils import setup_logger, get_jst_now, get_today_str, get_dirs

logger = setup_logger("design_ai")

# ────────────────────────────────────────────────────────────────
# 定数
# ────────────────────────────────────────────────────────────────
BG      = "#0d1117"
CARD    = "#161b22"
CARD2   = "#1c2128"
BORDER  = "#30363d"
TEXT    = "#c9d1d9"
MUTED   = "#8b949e"
GREEN   = "#3fb950"
RED     = "#f85149"
YELLOW  = "#d29922"
ORANGE  = "#db6d28"
BLUE    = "#58a6ff"
PURPLE  = "#bc8cff"
TEAL    = "#39d353"

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
}}

*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

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
  border-bottom: 1px solid var(--border);
}}
.section-icon {{ font-size: 18px; }}
.section-title {{ font-size: 16px; font-weight: 700; }}
.section-tag {{
  margin-left: auto;
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--card2);
  color: var(--muted);
}}
"""


# ────────────────────────────────────────────────────────────────
# ヘルパー関数
# ────────────────────────────────────────────────────────────────

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
    """AI予測精度セクション HTML"""
    pt    = prediction_tracker or {}
    stats = pt.get("stats", {})
    preds = pt.get("recent_predictions", pt.get("recent", []))

    acc   = stats.get("accuracy", stats.get("overall_accuracy", 0))
    total = stats.get("total",   0)
    hits  = stats.get("correct", int(total * acc) if total else 0)

    acc_pct  = int(acc * 100) if acc <= 1 else int(acc)
    bar_col  = GREEN if acc_pct >= 60 else (YELLOW if acc_pct >= 40 else RED)

    rows_html = ""
    for p in (preds or [])[:5]:
        if not isinstance(p, dict):
            continue
        dt  = p.get("date", "")[:10]
        sig = p.get("signal",    p.get("prediction", ""))
        res = p.get("result",    p.get("actual", ""))
        ok  = p.get("correct",   None)
        if ok is True:
            res_html = f'<span class="pred-hit">✓ 正解</span>'
        elif ok is False:
            res_html = f'<span class="pred-miss">✗ 不正解</span>'
        else:
            res_html = f'<span style="color:var(--muted)">検証中</span>'
        rows_html += f'<div class="pred-row"><span>{dt} {sig}</span>{res_html}</div>'

    return f"""
<div class="stat-row">
  <span class="stat-value" style="color:{bar_col}">{acc_pct}%</span>
  <span class="stat-unit">正解率 ({hits}/{total}件)</span>
</div>
<div class="acc-bar-wrap">
  <div class="acc-bar" style="width:{acc_pct}%;background:{bar_col}"></div>
</div>
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

    gauge_svg    = _gauge_svg(score)
    stocks_html  = _stock_cards(prices, technical)
    sector_html  = _sector_heatmap(sector_analysis)
    news_html    = _news_section(news)
    debate_html  = _ai_discussion(team_debate, ai_summary)
    cal_html     = _calendar_section(weekly_calendar)
    pred_html    = _prediction_section(prediction_tracker)
    fg_html      = _fg_section(fear_greed)

    # シナリオ
    sc = scenario or {}
    sc_html = ""
    if sc.get("available"):
        for key, icon, color in [("bull", "🐂", GREEN), ("base", "😐", YELLOW), ("bear", "🐻", RED)]:
            sec = sc.get(key, {})
            if not sec:
                continue
            label = {"bull":"楽観シナリオ","base":"基本シナリオ","bear":"悲観シナリオ"}.get(key, key)
            prob  = sec.get("probability", sec.get("prob", 0))
            desc  = sec.get("description", sec.get("desc", sec.get("text", "")))
            prob_str = f"{prob*100:.0f}%" if prob and prob <= 1 else (f"{prob}%" if prob else "?")
            sc_html += f"""
<div class="card fade-up" style="border-color:{color}22">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
    <span style="font-size:20px">{icon}</span>
    <span style="font-weight:700;color:{color}">{label}</span>
    <span style="margin-left:auto;font-size:12px;color:var(--muted)">確率 {prob_str}</span>
  </div>
  <div style="font-size:13px;line-height:1.6">{str(desc)[:180]}</div>
</div>"""

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>市場AI秘書 — {today} 日次レポート</title>
<style>
{_CSS}
</style>
</head>
<body>

<!-- ── Header ── -->
<header class="header">
  <div class="header-inner">
    <div>
      <div class="header-title">📊 市場AI秘書</div>
      <div class="header-sub">{now} ／ {mode.upper()}レポート</div>
    </div>
    <div class="signal-badge {signal_cls}">{signal_text}</div>
  </div>
</header>

<main class="container">

<!-- ── Row 1: ゲージ / FearGreed ── -->
<section>
  <div class="grid-2">
    <!-- リスクゲージ -->
    <div class="card fade-up">
      <div class="card-title">リスクゲージ</div>
      <div class="gauge-wrap">
        {gauge_svg}
        <div class="gauge-score-label">リスクスコア（−3〜＋3）</div>
      </div>
      <div style="margin-top:12px;font-size:12px;color:var(--muted)">
        シグナル: {", ".join(risk.get("signals", [])[:3]) or "なし"}
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

<!-- ── 銘柄カード ── -->
<section>
  <div class="section-header">
    <span class="section-icon">💹</span>
    <span class="section-title">マーケット概況</span>
    <span class="section-tag">{today}</span>
  </div>
  {stocks_html}
</section>

<!-- ── AIチーム議論 ── -->
<section>
  <div class="section-header">
    <span class="section-icon">🤖</span>
    <span class="section-title">AIチーム議論</span>
  </div>
  <div class="card fade-up">
    {debate_html}
  </div>
</section>

<!-- ── シナリオ分析 ── -->
{"" if not sc_html else f"""
<section>
  <div class="section-header">
    <span class='section-icon'>🔭</span>
    <span class='section-title'>3シナリオ分析</span>
  </div>
  <div class='grid-3'>{sc_html}</div>
</section>"""}

<!-- ── セクターヒートマップ ── -->
<section>
  <div class="section-header">
    <span class="section-icon">🏭</span>
    <span class="section-title">セクター別パフォーマンス</span>
  </div>
  <div class="card fade-up">
    {sector_html}
  </div>
</section>

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

<footer style="text-align:center;padding:20px;color:var(--muted);font-size:11px;border-top:1px solid var(--border);margin-top:20px">
  市場AI秘書 · 自動生成 {now} · データは参考情報です
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
