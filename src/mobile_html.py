"""
スマホ対応・美しいHTMLレポート生成モジュール
- CSS変数 / カード / グラデーション / ダークモード
- iPhone Safari / Android Chrome 最適化
"""
import base64
import traceback
from pathlib import Path
from src.utils import setup_logger, get_jst_now, get_today_str, get_dirs

logger = setup_logger("mobile_html")

# ── CSS ───────────────────────────────────────────────────────────
_CSS = """
:root {
  --bg:       #0a0a10;
  --bg2:      #111118;
  --card:     #16161f;
  --border:   #252535;
  --text:     #e2e2f0;
  --muted:    #8888a8;
  --green:    #00e676;
  --red:      #ff4d4d;
  --yellow:   #ffd740;
  --orange:   #ff8c00;
  --blue:     #40c4ff;
  --purple:   #b388ff;
  --accent:   #7c4dff;
  --radius:   16px;
  --shadow:   0 4px 24px rgba(0,0,0,.4);
}
*{margin:0;padding:0;box-sizing:border-box;}
body{
  font-family:-apple-system,BlinkMacSystemFont,'SF Pro Text','Segoe UI',
              'Helvetica Neue',Arial,sans-serif;
  background:var(--bg);
  color:var(--text);
  font-size:15px;
  line-height:1.6;
  -webkit-text-size-adjust:100%;
}
a{color:var(--blue);text-decoration:none;}
a:hover{text-decoration:underline;}

/* ── HERO ── */
.hero{
  background:linear-gradient(145deg,#1a1028 0%,#0d0d1a 60%,#0a1020 100%);
  padding:28px 20px 20px;
  text-align:center;
  border-bottom:1px solid var(--border);
}
.hero-date{font-size:12px;color:var(--muted);letter-spacing:.05em;}
.hero-title{font-size:22px;font-weight:700;margin:6px 0 4px;
  background:linear-gradient(90deg,#7c4dff,#40c4ff);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;}
.hero-signal{
  display:inline-block;margin-top:10px;
  padding:10px 28px;border-radius:40px;
  font-size:16px;font-weight:700;
  box-shadow:var(--shadow);
}
.signal-green {background:rgba(0,230,118,.15);border:1.5px solid var(--green);color:var(--green);}
.signal-yellow{background:rgba(255,215,64,.12);border:1.5px solid var(--yellow);color:var(--yellow);}
.signal-orange{background:rgba(255,140,0,.12); border:1.5px solid var(--orange);color:var(--orange);}
.signal-red   {background:rgba(255,77,77,.13); border:1.5px solid var(--red);   color:var(--red);}

/* ── LAYOUT ── */
.container{max-width:600px;margin:0 auto;padding:14px 12px 40px;}
.section-title{
  font-size:13px;font-weight:700;letter-spacing:.08em;
  color:var(--muted);text-transform:uppercase;
  margin:22px 0 10px 2px;
}

/* ── CARD ── */
.card{
  background:var(--card);
  border:1px solid var(--border);
  border-radius:var(--radius);
  padding:16px;
  margin-bottom:12px;
  box-shadow:var(--shadow);
}
.card-title{font-size:13px;color:var(--muted);margin-bottom:10px;font-weight:600;}

/* ── PRICE GRID ── */
.price-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;}
@media(min-width:420px){.price-grid{grid-template-columns:repeat(3,1fr);}}
.p-cell{
  background:var(--bg2);
  border:1px solid var(--border);
  border-radius:12px;
  padding:12px 10px;
  text-align:center;
}
.p-label{font-size:11px;color:var(--muted);margin-bottom:4px;}
.p-val  {font-size:16px;font-weight:700;line-height:1.2;}
.p-chg  {font-size:12px;margin-top:3px;font-weight:600;}
.up  {color:var(--green);}
.dn  {color:var(--red);}
.neu {color:var(--muted);}

/* ── FG BAR ── */
.fg-wrap{margin-top:8px;}
.fg-label{display:flex;justify-content:space-between;font-size:11px;color:var(--muted);margin-bottom:4px;}
.fg-track{
  height:12px;border-radius:6px;
  background:linear-gradient(90deg,#7c4dff,#ff1744);
  overflow:hidden;position:relative;
}
.fg-needle{
  position:absolute;top:0;height:100%;width:3px;
  background:white;border-radius:2px;
  transition:left .3s;
}
.fg-score{text-align:center;font-size:20px;font-weight:700;margin-top:6px;}

/* ── AI BUBBLE ── */
.bubble{border-radius:12px;padding:14px;margin-bottom:10px;border-left:3px solid;}
.bubble-title{font-size:12px;font-weight:700;margin-bottom:6px;}
.bubble-body {font-size:14px;line-height:1.7;color:var(--text);}
.b-bull{border-color:var(--green);background:rgba(0,230,118,.06);}
.b-bear{border-color:var(--red);  background:rgba(255,77,77,.06);}
.b-neu {border-color:var(--yellow);background:rgba(255,215,64,.06);}

/* ── NEWS ── */
.news-item{
  display:flex;align-items:flex-start;gap:10px;
  padding:10px 0;border-bottom:1px solid var(--border);
}
.news-item:last-child{border-bottom:none;}
.nbadge{
  flex-shrink:0;font-size:10px;padding:2px 7px;
  border-radius:8px;margin-top:3px;font-weight:700;
}
.nb-a{background:#ff4444;color:white;}
.nb-b{background:#ffd740;color:#111;}
.nb-c{background:#2a2a3a;color:var(--muted);}
.news-title{font-size:14px;line-height:1.5;flex:1;}
.news-src  {font-size:11px;color:var(--muted);margin-top:3px;}

/* ── SCENARIO CARDS ── */
.scenario-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;}
@media(max-width:380px){.scenario-grid{grid-template-columns:1fr;}}
.sc-card{border-radius:12px;padding:12px;text-align:center;}
.sc-bull{background:rgba(0,230,118,.1);border:1px solid var(--green);}
.sc-base{background:rgba(255,215,64,.1);border:1px solid var(--yellow);}
.sc-bear{background:rgba(255,77,77,.1); border:1px solid var(--red);}
.sc-prob{font-size:22px;font-weight:700;}
.sc-label{font-size:11px;margin-top:4px;color:var(--muted);}
.sc-text {font-size:12px;margin-top:6px;line-height:1.5;text-align:left;}

/* ── CHART IMAGE ── */
.chart-img{width:100%;border-radius:var(--radius);display:block;margin-bottom:12px;}

/* ── TECH TABLE ── */
.tech-table{width:100%;border-collapse:collapse;font-size:13px;}
.tech-table th{
  text-align:left;padding:6px 8px;
  font-size:11px;color:var(--muted);
  border-bottom:1px solid var(--border);font-weight:600;
}
.tech-table td{
  padding:8px 8px;border-bottom:1px solid var(--border);
}
.sig-chip{
  display:inline-block;padding:2px 10px;
  border-radius:8px;font-size:11px;font-weight:700;
}
.sig-buy {background:rgba(0,230,118,.15);color:var(--green);}
.sig-sell{background:rgba(255,77,77,.15); color:var(--red);}
.sig-hold{background:rgba(255,215,64,.12);color:var(--yellow);}

/* ── PRED TRACKER ── */
.pred-bar{
  height:10px;border-radius:5px;
  background:linear-gradient(90deg,var(--red),var(--yellow),var(--green));
  position:relative;margin:6px 0;
}
.pred-needle{
  position:absolute;top:-3px;width:6px;height:16px;
  background:white;border-radius:3px;transform:translateX(-50%);
}
.pred-day{display:flex;align-items:center;gap:8px;padding:6px 0;
  border-bottom:1px solid var(--border);font-size:13px;}
.pred-day:last-child{border-bottom:none;}

/* ── RISK GAUGE ── */
.risk-badge{
  display:inline-block;border-radius:12px;padding:6px 16px;
  font-size:13px;font-weight:700;
}

/* ── FOOTER ── */
.footer{
  text-align:center;font-size:11px;color:var(--muted);
  padding:20px 12px 32px;
  border-top:1px solid var(--border);
  margin-top:24px;
}
"""

# ── ユーティリティ ───────────────────────────────────────────────

def _img_b64(path: str) -> str:
    if not path or not Path(path).exists():
        return ""
    try:
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        return f'<img src="data:image/png;base64,{b64}" class="chart-img" loading="lazy">'
    except Exception:
        return ""


def _fmt(prices: dict, sym: str, unit: str = "") -> tuple:
    d   = prices.get(sym, {})
    v   = d.get("latest")
    chg = d.get("change_pct")
    if v is None:
        return "---", "---", "neu"
    val_str = f"{v:,.2f}{unit}"
    if chg is None:
        return val_str, "---", "neu"
    cls = "up" if chg >= 0 else "dn"
    arrow = "▲" if chg >= 0 else "▼"
    return val_str, f"{arrow}{abs(chg):.2f}%", cls


def _price_cell(emoji: str, label: str, prices: dict, sym: str, unit: str = "") -> str:
    val, chg, cls = _fmt(prices, sym, unit)
    return (
        f'<div class="p-cell">'
        f'<div class="p-label">{emoji} {label}</div>'
        f'<div class="p-val {cls}">{val}</div>'
        f'<div class="p-chg {cls}">{chg}</div>'
        f'</div>'
    )


def _signal_class(score: float) -> tuple:
    if score >= 2:    return "signal-green",  "🟢 強気シグナル！"
    elif score >= 0.5: return "signal-green",  "🟢 やや強気"
    elif score >= -0.5: return "signal-yellow", "🟡 中立・様子見"
    elif score >= -2:  return "signal-orange",  "🟠 要注意"
    else:               return "signal-red",    "🔴 危険シグナル"


# ── 各セクションHTML ─────────────────────────────────────────────

def _hero_html(now: str, today: str, score: float) -> str:
    sig_cls, sig_txt = _signal_class(score)
    return f"""
<div class="hero">
  <div class="hero-date">{now}</div>
  <div class="hero-title">📊 市場AI秘書</div>
  <div>{today} のレポート</div>
  <div class="hero-signal {sig_cls}">{sig_txt}</div>
</div>"""


def _prices_html(prices: dict) -> str:
    cells = "".join([
        _price_cell("🇯🇵", "日経平均", prices, "^N225", "円"),
        _price_cell("🇺🇸", "S&P500",  prices, "^GSPC"),
        _price_cell("🇺🇸", "NASDAQ",  prices, "^IXIC"),
        _price_cell("💵", "ドル円",  prices, "USDJPY=X", "円"),
        _price_cell("🥇", "金",      prices, "GC=F", "$"),
        _price_cell("🛢",  "原油",    prices, "CL=F", "$"),
        _price_cell("₿",  "BTC",     prices, "BTC-USD", "$"),
        _price_cell("😱", "VIX",     prices, "^VIX"),
    ])
    return f"""
<p class="section-title">📈 マーケット概況</p>
<div class="card">
  <div class="price-grid">{cells}</div>
</div>"""


def _fg_html(fear_greed: dict) -> str:
    score = int(fear_greed.get("score") or 50)
    if score >= 75:   label, cls = "超強欲 😱", "up"
    elif score >= 55: label, cls = "強欲 😤",    "up"
    elif score >= 45: label, cls = "中立 😐",    "neu"
    elif score >= 25: label, cls = "恐怖 😰",    "dn"
    else:             label, cls = "超恐怖 😭",  "dn"
    pct = score
    return f"""
<div class="card">
  <div class="card-title">😱 Fear&amp;Greed 指数</div>
  <div class="fg-score {cls}">{score} — {label}</div>
  <div class="fg-wrap">
    <div class="fg-label"><span>0 超恐怖</span><span>50 中立</span><span>100 超強欲</span></div>
    <div class="fg-track">
      <div class="fg-needle" style="left:{pct}%;"></div>
    </div>
  </div>
</div>"""


def _ai_html(ai_summary: dict) -> str:
    if not ai_summary.get("available"):
        return ""
    bull = ai_summary.get("bull_view", "")
    bear = ai_summary.get("bear_view", "")
    neut = ai_summary.get("neutral_view", "")
    return f"""
<p class="section-title">🤖 AI 3視点ディベート</p>
<div class="card">
  <div class="bubble b-bull">
    <div class="bubble-title">📈 強気派 — 上がると思う理由</div>
    <div class="bubble-body">{bull or "---"}</div>
  </div>
  <div class="bubble b-bear">
    <div class="bubble-title">📉 弱気派 — リスク・下落理由</div>
    <div class="bubble-body">{bear or "---"}</div>
  </div>
  <div class="bubble b-neu">
    <div class="bubble-title">⚖️ AI総合判断</div>
    <div class="bubble-body">{neut or "---"}</div>
  </div>
</div>"""


def _scenario_html(scenario: dict) -> str:
    if not scenario or not scenario.get("available"):
        return ""
    def card(cls, emoji, label, prob, text):
        return (
            f'<div class="sc-card {cls}">'
            f'<div class="sc-prob">{emoji} {prob}%</div>'
            f'<div class="sc-label">{label}</div>'
            f'<div class="sc-text">{(text or "")[:120]}</div>'
            f'</div>'
        )
    b = scenario.get("bull", {}); m = scenario.get("base", {}); w = scenario.get("bear", {})
    return f"""
<p class="section-title">🎭 3シナリオ分析</p>
<div class="card">
  <div class="scenario-grid">
    {card("sc-bull","🟢","楽観シナリオ", b.get("prob","?"), b.get("text",""))}
    {card("sc-base","🟡","基本シナリオ", m.get("prob","?"), m.get("text",""))}
    {card("sc-bear","🔴","悲観シナリオ", w.get("prob","?"), w.get("text",""))}
  </div>
</div>"""


def _news_html(news: list) -> str:
    sorted_news = sorted(news, key=lambda x: {"A":0,"B":1,"C":2}.get(x.get("importance","C"),2))
    rows = ""
    for item in sorted_news[:20]:
        imp   = item.get("importance", "C")
        title = item.get("title", "")
        src   = item.get("source_name") or item.get("source","")
        url   = item.get("url","")
        badge_cls = {"A":"nb-a","B":"nb-b","C":"nb-c"}.get(imp,"nb-c")
        badge_txt = {"A":"🔴 重要","B":"🟡 注目","C":"⚪ 情報"}.get(imp,"情報")
        link = f'<a href="{url}" target="_blank" rel="noopener">{title}</a>' if url else title
        rows += f"""
<div class="news-item">
  <span class="nbadge {badge_cls}">{badge_txt}</span>
  <div><div class="news-title">{link}</div><div class="news-src">{src}</div></div>
</div>"""
    return f"""
<p class="section-title">📰 今日のニュース</p>
<div class="card">{rows}</div>"""


def _prediction_html(pt: dict) -> str:
    if not pt or not pt.get("available"):
        return ""
    stats = pt.get("stats", {})
    r10   = stats.get("10d", {})
    rate  = r10.get("rate")
    total = stats.get("total_verified", 0)
    if total < 3:
        return ""
    needle_pct = rate or 50
    icons = {"bull":"📈","bear":"📉","neutral":"➡️"}
    days_html = ""
    for p in stats.get("recent5", []):
        mark = "✅" if p.get("correct") else ("❌" if p.get("correct") is False else "⏳")
        icon = icons.get(p.get("direction",""),"")
        move = f"{p['move']:+.1f}%" if p.get("move") is not None else "---"
        days_html += f'<div class="pred-day">{mark} {p.get("date","")[-5:]} {icon} → <b>{move}</b></div>'

    today_pred = pt.get("today_prediction", {})
    today_dir  = today_pred.get("direction","neutral") if today_pred else "neutral"
    today_icon = icons.get(today_dir,"")
    today_str  = {"bull":"📈 強気（上昇予測）","bear":"📉 弱気（下落予測）","neutral":"➡️ 中立（横ばい予測）"}.get(today_dir,"")

    return f"""
<p class="section-title">🧠 AI予測学習レポート</p>
<div class="card">
  <div class="card-title">直近10日の正解率</div>
  <div style="font-size:28px;font-weight:700;margin:4px 0;">{rate or "---"}%</div>
  <div class="pred-bar"><div class="pred-needle" style="left:{needle_pct}%;"></div></div>
  <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--muted);margin-bottom:12px;">
    <span>0%</span><span>50%</span><span>100%</span>
  </div>
  <div class="card-title">直近の結果</div>
  {days_html}
  <div style="margin-top:12px;padding:10px;background:var(--bg2);border-radius:10px;">
    <div style="font-size:12px;color:var(--muted);">今日のAI予測</div>
    <div style="font-size:16px;font-weight:700;margin-top:4px;">{today_str}</div>
  </div>
</div>"""


def _technical_html(technical: dict, chart_paths: dict) -> str:
    if not technical or not technical.get("available"):
        return ""
    chart = _img_b64(str(technical.get("chart_path","")))
    signals = technical.get("signals", {})
    rows = ""
    for sym, sig_data in (signals.items() if isinstance(signals, dict) else []):
        sig = sig_data.get("signal","hold") if isinstance(sig_data, dict) else str(sig_data)
        sig_cls = "sig-buy" if sig in ("buy","強い買い","買い") else (
                  "sig-sell" if sig in ("sell","売り","強い売り") else "sig-hold")
        rows += f'<tr><td>{sym}</td><td><span class="sig-chip {sig_cls}">{sig}</span></td></tr>'

    table = f'<table class="tech-table"><thead><tr><th>銘柄</th><th>シグナル</th></tr></thead><tbody>{rows}</tbody></table>' if rows else ""
    ai_c = (technical.get("ai_comment") or "")[:200]
    return f"""
<p class="section-title">📐 テクニカル分析</p>
<div class="card">
  {chart}
  {f'<p style="font-size:13px;color:var(--muted);margin-bottom:10px;">{ai_c}</p>' if ai_c else ""}
  {table}
</div>"""


# ── メイン生成関数 ───────────────────────────────────────────────

def generate(mode: str, prices: dict, news: list, risk: dict,
             fear_greed: dict, chart_paths: dict,
             ai_summary: dict = None, scenario: dict = None,
             prediction_tracker: dict = None, technical: dict = None,
             **_kwargs) -> str:
    """
    スマホ最適化 HTML レポートを生成して保存パスを返す。
    """
    try:
        today = get_today_str()
        now   = get_jst_now().strftime("%Y年%m月%d日 %H:%M JST")
        score = risk.get("score", 0)
        dirs  = get_dirs()

        # チャート画像
        overview_img = _img_b64(str(chart_paths.get("overview","") or chart_paths.get("prices","")))

        body = (
            _hero_html(now, today, score)
            + f'<div class="container">'
            + _prices_html(prices)
            + _fg_html(fear_greed)
            + (f'<p class="section-title">📊 チャート</p><div class="card">{overview_img}</div>' if overview_img else "")
            + _ai_html(ai_summary or {})
            + _scenario_html(scenario or {})
            + _prediction_html(prediction_tracker or {})
            + _technical_html(technical or {}, chart_paths)
            + _news_html(news)
            + f'<div class="footer">© 市場AI秘書 — {now}</div>'
            + '</div>'
        )

        html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,viewport-fit=cover">
<meta name="theme-color" content="#0a0a10">
<meta name="apple-mobile-web-app-capable" content="yes">
<title>市場AI秘書 {today}</title>
<style>{_CSS}</style>
</head>
<body>
{body}
</body>
</html>"""

        path = dirs["reports"] / f"{today}_{mode}_mobile.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        logger.info(f"✅ モバイルHTMLレポート保存: {path}")
        return str(path)

    except Exception as e:
        logger.error(f"モバイルHTML生成エラー: {e}")
        logger.debug(traceback.format_exc())
        return ""
