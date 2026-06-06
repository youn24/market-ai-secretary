"""
レポート生成（Plotly動くチャート + TradingViewウィジェット + Ollama AI要約）
"""
from pathlib import Path
from src.utils import get_jst_now, get_today_str, get_dirs, setup_logger

logger = setup_logger("report_writer")

DISCLAIMER = ("本レポートは情報提供を目的とした分析補助資料です。"
              "投資助言ではありません。すべての投資判断はご自身の責任で行ってください。"
              "データ取得失敗・遅延・誤差がある可能性があります。")

# ── TradingView ウィジェット設定 ──────────────────────
TV_SYMBOLS = [
    ("NI225",   "日経平均",  "OSAKA"),
    ("SPX",     "S&P500",    "SP"),
    ("USDJPY",  "ドル円",    "FX"),
    ("XAUUSD",  "金(GOLD)",  "OANDA"),
    ("BTCUSD",  "Bitcoin",   "BITSTAMP"),
    ("US10Y",   "米10年金利","TVC"),
]


def _tv_widget(symbol: str, exchange: str, height: int = 300) -> str:
    """TradingView ミニチャートウィジェットのHTMLを生成する"""
    full_sym = f"{exchange}:{symbol}" if exchange else symbol
    return f"""
<div class="tradingview-widget-container" style="height:{height}px;width:100%">
  <div class="tradingview-widget-container__widget"></div>
  <script type="text/javascript"
    src="https://s3.tradingview.com/external-embedding/embed-widget-mini-symbol-overview.js"
    async>
  {{
    "symbol": "{full_sym}",
    "width": "100%",
    "height": {height},
    "locale": "ja",
    "dateRange": "1M",
    "colorTheme": "light",
    "isTransparent": false,
    "autosize": true,
    "largeChartUrl": "https://www.tradingview.com/chart/?symbol={full_sym}"
  }}
  </script>
</div>"""


def _tv_ticker_tape() -> str:
    """TradingView ティッカーテープ（上部に流れる価格帯）"""
    return """
<div class="tradingview-widget-container" style="margin-bottom:0">
  <div class="tradingview-widget-container__widget"></div>
  <script type="text/javascript"
    src="https://s3.tradingview.com/external-embedding/embed-widget-ticker-tape.js"
    async>
  {
    "symbols": [
      {"proName":"OSAKA:NI225","title":"日経平均"},
      {"proName":"SP:SPX","title":"S&P500"},
      {"proName":"NASDAQ:NDX","title":"NASDAQ"},
      {"proName":"FX:USDJPY","title":"ドル円"},
      {"proName":"TVC:US10Y","title":"米10年金利"},
      {"proName":"OANDA:XAUUSD","title":"金"},
      {"proName":"TVC:USOIL","title":"WTI原油"},
      {"proName":"BITSTAMP:BTCUSD","title":"Bitcoin"},
      {"proName":"CBOE:VIX","title":"VIX"}
    ],
    "showSymbolLogo": true,
    "isTransparent": false,
    "displayMode": "adaptive",
    "colorTheme": "light",
    "locale": "ja"
  }
  </script>
</div>"""


def _chg_html(chg, size="14px"):
    if chg is None:
        return f'<span style="color:#aaa;font-size:{size}">―</span>'
    c = "#e05252" if chg >= 0 else "#4a90d9"
    a = "▲" if chg >= 0 else "▼"
    return f'<span style="color:{c};font-weight:700;font-size:{size}">{a} {abs(chg):.2f}%</span>'


def _fmt_val(latest, unit):
    if latest is None: return "―"
    if unit == "$":  return f"${latest:,.2f}"
    if unit == "円": return f"¥{latest:,.2f}"
    if unit == "%":  return f"{latest:.3f}%"
    return f"{latest:,.4f}"


def _build_key_moves(prices):
    items = [
        ("^N225","日経平均","円"), ("^GSPC","S&P500",""),
        ("^IXIC","NASDAQ",""),    ("^DJI","ダウ",""),
        ("USDJPY=X","ドル円","円"),("EURUSD=X","ユーロドル",""),
        ("^TNX","米10年金利","%"), ("^VIX","VIX",""),
        ("GC=F","金","$"),        ("CL=F","原油","$"),
        ("BTC-USD","Bitcoin","$"),
    ]
    return [{"name":n,"unit":u,
             "latest": prices.get(s,{}).get("latest"),
             "change_pct": prices.get(s,{}).get("change_pct")}
            for s,n,u in items]


def _market_cards_html(prices):
    out = ""
    for m in _build_key_moves(prices):
        chg = m.get("change_pct")
        val = _fmt_val(m.get("latest"), m.get("unit",""))
        bg  = "rgba(224,82,82,0.06)" if (chg or 0)>=0 else "rgba(74,144,217,0.06)"
        bdr = "#e05252" if (chg or 0)>=0 else "#4a90d9"
        out += f"""<div class="mcard" style="background:{bg};border-top:3px solid {bdr}">
          <div class="mcard-name">{m['name']}</div>
          <div class="mcard-val">{val}</div>
          <div>{_chg_html(chg)}</div>
        </div>"""
    return out


def _stocks_table(prices):
    us = [("NVDA","NVIDIA","🟢"),("AAPL","Apple","🍎"),
          ("TSLA","Tesla","⚡"),("MSFT","Microsoft","🪟"),
          ("AMZN","Amazon","📦"),("META","Meta","💬")]
    jp = [("7203.T","トヨタ","🚗"),("9984.T","SBG","📱"),
          ("6758.T","ソニーG","🎮"),("8306.T","三菱UFJ","🏦"),
          ("6857.T","アドバンテスト","💾"),("4063.T","信越化学","🔬")]

    def tbl(stocks):
        rows = ""
        for sym, name, icon in stocks:
            p   = prices.get(sym, {})
            lat = p.get("latest")
            chg = p.get("change_pct")
            val = f"{lat:,.2f}" if lat else "―"
            bg  = "rgba(224,82,82,0.05)" if (chg or 0)>=0 else "rgba(74,144,217,0.05)"
            rows += f'<tr style="background:{bg}"><td>{icon} {name}</td>' \
                    f'<td style="text-align:right;font-weight:600">{val}</td>' \
                    f'<td style="text-align:right">{_chg_html(chg)}</td></tr>'
        return rows

    return f"""<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
      <div><div class="tbl-title">🗽 米国 主要銘柄</div>
           <table class="stk-tbl"><tbody>{tbl(us)}</tbody></table></div>
      <div><div class="tbl-title">🗾 日本 主要銘柄</div>
           <table class="stk-tbl"><tbody>{tbl(jp)}</tbody></table></div>
    </div>"""


def _fear_greed_box(fg):
    score  = fg.get("score")
    rating = fg.get("rating_ja","取得失敗")
    if score is None:
        return '<div class="fg-box"><div class="fg-label">Fear &amp; Greed: 取得失敗</div></div>'
    if score >= 75:   col,emoji = "#2d9a6b","😄"
    elif score >= 55: col,emoji = "#74c69d","🙂"
    elif score >= 45: col,emoji = "#aaaaaa","😐"
    elif score >= 25: col,emoji = "#ff8c42","😟"
    else:             col,emoji = "#e05252","😱"
    return f"""<div class="fg-box" style="border-color:{col}">
      <div class="fg-label">😨 Crypto Fear &amp; Greed <span style="font-size:10px;color:#aaa">by alternative.me</span></div>
      <div class="fg-score" style="color:{col}">{emoji} {score:.0f}</div>
      <div style="font-size:15px;font-weight:700;color:{col}">{rating}</div>
    </div>"""


def _analysis_card(icon, title, analysis):
    facts = "".join(f"<li>{f}</li>" for f in analysis.get("facts",[]))
    hyps  = "".join(f"<li>{h}</li>" for h in analysis.get("hypotheses",[]))
    caut  = "".join(f"<li class='caut-li'>{c}</li>" for c in analysis.get("cautions",[]))
    return f"""<div class="card">
      <div class="card-title">{icon} {title}</div>
      {"<div class='ltag ftag'>📊 事実</div><ul class='ful'>"+facts+"</ul>" if facts else ""}
      {"<div class='ltag htag'>💭 推測・考察</div><ul class='hul'>"+hyps+"</ul>" if hyps else ""}
      {"<div class='ltag ctag'>⚠️ 注意点</div><ul class='cul'>"+caut+"</ul>" if caut else ""}
    </div>"""


def _news_html(news, max_items=30):
    if not news: return "<p>ニュースデータなし</p>"
    imp_order = {"A":0,"B":1,"C":2}
    imp_style = {
        "A":"background:#fff0f0;color:#e05252;border:1px solid #ffcccc",
        "B":"background:#fff8f0;color:#d97706;border:1px solid #ffd9a0",
        "C":"background:#f0f6ff;color:#4a90d9;border:1px solid #c0d8f5",
    }
    from collections import defaultdict
    grouped = defaultdict(list)
    for item in sorted(news, key=lambda x: imp_order.get(x.get("importance","C"),2)):
        grouped[item.get("label","その他")].append(item)
    out = ""
    for label, items in grouped.items():
        imp   = items[0].get("importance","C")
        style = imp_style.get(imp, imp_style["C"])
        out += f'<div class="ng"><div class="ng-title"><span class="ibadge" style="{style}">{imp}</span> {label}</div>'
        for item in items[:max_items]:
            out += f"""<div class="ni">
              <a href="{item.get('url','')}" target="_blank" class="nl">{item.get('title','')}</a>
              <span class="nm">{item.get('source','')} · {item.get('published_jst','')}</span>
            </div>"""
        out += "</div>"
    return out


def _ai_section(ai: dict) -> str:
    if not ai.get("available"):
        return """<div class="card" style="border-left:3px solid #e9ecef">
          <div class="card-title">🤖 AI要約（Ollama）</div>
          <p style="color:#9ca3af;font-size:13px">
            Ollamaが起動していないためスキップしました。<br>
            Ollamaをインストール・起動すると、ニュースの自動要約と市場コメントが生成されます。
            <br><a href="https://ollama.com/download" target="_blank">→ Ollamaのダウンロードはこちら</a>
          </p>
        </div>"""
    model = ai.get("model","")
    summary = ai.get("news_summary","").replace("\n","<br>")
    comment = ai.get("market_comment","").replace("\n","<br>")
    return f"""<div class="card" style="border-left:3px solid #7c3aed">
      <div class="card-title">🤖 AI要約　<span style="font-size:11px;color:#9ca3af">by Ollama / {model}</span></div>
      <div style="background:#faf5ff;border-radius:8px;padding:14px;margin-bottom:12px">
        <div style="font-size:12px;font-weight:700;color:#7c3aed;margin-bottom:6px">📰 本日のニュース要約</div>
        <div style="font-size:13px;color:#374151;line-height:1.8">{summary}</div>
      </div>
      <div style="background:#f0fdf4;border-radius:8px;padding:14px">
        <div style="font-size:12px;font-weight:700;color:#15803d;margin-bottom:6px">📊 今日の市場コメント</div>
        <div style="font-size:13px;color:#374151;line-height:1.8">{comment}</div>
      </div>
      <p style="font-size:11px;color:#9ca3af;margin-top:8px">
        ⚠️ AIが生成したコメントです。事実確認を行い、投資判断の参考にしないでください。
      </p>
    </div>"""


CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:#f0f2f5;color:#212529;
     font-family:'Meiryo','MS Gothic','Segoe UI',sans-serif;
     font-size:14px;line-height:1.7}
a{color:#2563eb;text-decoration:none}
a:hover{text-decoration:underline}
.ticker-wrap{position:sticky;top:0;z-index:100;
             box-shadow:0 2px 6px rgba(0,0,0,0.1)}
.header{background:linear-gradient(135deg,#1e3a8a 0%,#2563eb 60%,#3b82f6 100%);
        color:white;padding:22px 32px}
.header h1{font-size:21px;font-weight:700}
.header .meta{font-size:12px;opacity:.8;margin-top:4px}
.disc{background:rgba(255,255,255,0.15);border-left:3px solid #fbbf24;
      padding:7px 14px;font-size:12px;color:#fef3c7;margin-top:10px;border-radius:4px}
.container{max-width:1100px;margin:0 auto;padding:20px 14px}
.sec-h{font-size:16px;font-weight:700;color:#1e3a8a;
       margin:26px 0 10px;padding:7px 14px;
       background:white;border-left:4px solid #2563eb;
       border-radius:0 6px 6px 0;box-shadow:0 1px 3px rgba(0,0,0,.07)}
.card{background:white;border-radius:10px;padding:18px;
      margin-bottom:12px;box-shadow:0 1px 4px rgba(0,0,0,.07)}
.card-title{font-size:15px;font-weight:700;color:#1e3a8a;
            margin-bottom:12px;padding-bottom:7px;
            border-bottom:1px solid #e9ecef}
.ltag{display:inline-block;font-size:11px;font-weight:700;
      padding:2px 8px;border-radius:4px;margin:7px 0 3px}
.ftag{background:#e8f4fd;color:#1e6ea6}
.htag{background:#f0fdf4;color:#15803d}
.ctag{background:#fff7ed;color:#c2410c}
.ful li,.hul li{font-size:13px;margin:3px 0;padding-left:2px}
.cul{list-style:none}
.caut-li{font-size:13px;color:#c2410c;padding:4px 8px;
         background:#fff7ed;border-radius:4px;margin:3px 0}
.sent-wrap{display:flex;gap:14px;margin-bottom:12px;flex-wrap:wrap}
.sent-main{flex:1;min-width:230px;background:white;border-radius:10px;
           padding:22px;text-align:center;box-shadow:0 1px 4px rgba(0,0,0,.07)}
.sent-icon{font-size:50px;margin-bottom:6px}
.sent-lbl{font-size:13px;color:#6b7280;margin-bottom:5px}
.sent-val{font-size:22px;font-weight:700}
.sent-sc{font-size:12px;color:#9ca3af;margin-top:4px}
.sig-tbl{width:100%;border-collapse:collapse;font-size:13px;margin-top:10px}
.sig-tbl td{padding:5px 7px;border-bottom:1px solid #f3f4f6}
.sig-tbl td:first-child{font-weight:600;color:#374151}
.fg-box{background:white;border-radius:10px;padding:18px;text-align:center;
        box-shadow:0 1px 4px rgba(0,0,0,.07);border:2px solid #e5e7eb;
        flex:1;min-width:180px}
.fg-label{font-size:12px;color:#6b7280;margin-bottom:6px}
.fg-score{font-size:40px;font-weight:700;margin:3px 0}
.market-grid{display:grid;
             grid-template-columns:repeat(auto-fill,minmax(125px,1fr));
             gap:9px;margin-bottom:14px}
.mcard{background:white;border-radius:8px;padding:11px 9px;
       text-align:center;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.mcard-name{font-size:11px;color:#6b7280;margin-bottom:3px}
.mcard-val{font-size:14px;font-weight:700;color:#212529;margin-bottom:3px}
.plotly-wrap{background:white;border-radius:10px;padding:14px;
             margin-bottom:12px;box-shadow:0 1px 4px rgba(0,0,0,.07)}
.plotly-wrap h3{font-size:13px;color:#6b7280;margin-bottom:8px}
.tv-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:12px}
.tv-card{background:white;border-radius:10px;padding:12px;
         box-shadow:0 1px 4px rgba(0,0,0,.07)}
.tv-card h3{font-size:12px;color:#6b7280;margin-bottom:6px}
.tv-grid-2{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px}
.tbl-title{font-size:13px;font-weight:700;color:#374151;margin-bottom:5px}
.stk-tbl{width:100%;border-collapse:collapse;font-size:13px}
.stk-tbl td{padding:5px 7px;border-bottom:1px solid #f3f4f6}
.stk-tbl tr:hover{background:#f9fafb}
.ng{background:white;border-radius:8px;margin-bottom:9px;
    overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.ng-title{padding:9px 13px;font-size:13px;font-weight:700;
          color:#374151;background:#f9fafb;
          border-bottom:1px solid #e9ecef;
          display:flex;align-items:center;gap:7px}
.ibadge{display:inline-block;padding:2px 7px;border-radius:4px;
        font-size:11px;font-weight:700}
.ni{padding:9px 13px;border-bottom:1px solid #f3f4f6}
.ni:last-child{border-bottom:none}
.nl{font-size:13px;color:#1d4ed8;line-height:1.5;display:block;margin-bottom:2px}
.nl:hover{color:#1e40af}
.nm{font-size:11px;color:#9ca3af}
.footer{text-align:center;color:#9ca3af;font-size:11px;
        padding:18px;border-top:1px solid #e9ecef;
        margin-top:22px;background:white}
"""


def build_html(mode, prices, news, risk, analysis,
               chart_paths, fear_greed, ai_summary,
               plotly_charts) -> str:
    today     = get_today_str()
    now       = get_jst_now().strftime("%Y-%m-%d %H:%M JST")
    sentiment = risk.get("sentiment","不明")
    score     = risk.get("score",0)
    meter     = risk.get("meter","NEUTRAL")
    signals   = risk.get("signals",[])

    mc = {"RISK_ON":"#e05252","RISK_OFF":"#4a90d9","NEUTRAL":"#aaaaaa"}.get(meter,"#aaa")
    mi = {"RISK_ON":"🔥","RISK_OFF":"🛡️","NEUTRAL":"⚖️"}.get(meter,"⚖️")
    me = {"RISK_ON":"📈","RISK_OFF":"📉","NEUTRAL":"➡️"}.get(meter,"➡️")

    sig_rows = "".join(
        f"<tr><td>{s['indicator']}</td><td>{s['direction']}</td>"
        f"<td>{_chg_html(s.get('change'))}</td></tr>"
        for s in signals
    )

    # TradingView グリッド（3列）
    tv_grid_html = '<div class="tv-grid">'
    for sym, label, exc in TV_SYMBOLS[:3]:
        tv_grid_html += f'<div class="tv-card"><h3>📈 {label}</h3>{_tv_widget(sym, exc, 220)}</div>'
    tv_grid_html += '</div><div class="tv-grid">'
    for sym, label, exc in TV_SYMBOLS[3:]:
        tv_grid_html += f'<div class="tv-card"><h3>📈 {label}</h3>{_tv_widget(sym, exc, 220)}</div>'
    tv_grid_html += '</div>'

    # Plotly チャート HTML
    def pc(key, title=""):
        html = plotly_charts.get(key,"")
        if not html: return ""
        return f'<div class="plotly-wrap">{"<h3>"+title+"</h3>" if title else ""}{html}</div>'

    analysis_html = "".join([
        _analysis_card("💱","為替",           analysis.get("forex",{})),
        _analysis_card("🗽","米国株",         analysis.get("us_market",{})),
        _analysis_card("🗾","日本株",         analysis.get("japan_market",{})),
        _analysis_card("📈","金利",           analysis.get("rates",{})),
        _analysis_card("⛽","コモディティ・仮想通貨",analysis.get("commodities",{})),
    ])

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>市場レポート {today}</title>
<!-- Plotly.js -->
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js" charset="utf-8"></script>
<style>{CSS}</style>
</head>
<body>

<!-- ティッカーテープ（リアルタイム価格） -->
<div class="ticker-wrap">{_tv_ticker_tape()}</div>

<div class="header">
  <h1>📊 投資経済レポート　{today}
      <small style="opacity:.7;font-size:13px">[{mode.upper()}]</small></h1>
  <div class="meta">🕐 {now}　|　Yahoo Finance / CNN / Google News / TradingView（APIキー不要）</div>
  <div class="disc">⚠️ {DISCLAIMER}</div>
</div>

<div class="container">

  <!-- A. 今日の結論 -->
  <div class="sec-h">A. 今日の結論</div>
  <div class="sent-wrap">
    <div class="sent-main">
      <div class="sent-icon">{me}</div>
      <div class="sent-lbl">本日の地合い</div>
      <div class="sent-val" style="color:{mc}">{mi} {sentiment}</div>
      <div class="sent-sc">リスクスコア: {score:+.2f}　（-5=リスクオフ ／ +5=リスクオン）</div>
      <table class="sig-tbl">
        <thead><tr style="color:#9ca3af;font-size:11px">
          <th style="text-align:left;padding:3px 7px">指標</th>
          <th style="text-align:left;padding:3px 7px">動向</th>
          <th style="text-align:right;padding:3px 7px">変化率</th>
        </tr></thead>
        <tbody>{sig_rows}</tbody>
      </table>
    </div>
    {_fear_greed_box(fear_greed)}
  </div>

  <!-- Plotly: Fear & Greed + リスクメーター -->
  <div class="tv-grid-2">
    <div>{pc('fear_greed')}</div>
    <div>{pc('risk_meter')}</div>
  </div>

  <!-- B. 市場全体 数値 -->
  <div class="sec-h">B. 市場全体の数値</div>
  <div class="market-grid">{_market_cards_html(prices)}</div>

  <!-- Plotly: 主要指数 -->
  {pc('indices')}

  <!-- TradingView リアルタイムチャート -->
  <div class="sec-h">📡 TradingView リアルタイムチャート</div>
  <p style="font-size:12px;color:#9ca3af;margin-bottom:10px">
    ※インターネット接続が必要です。クリックするとTradingViewで大きなチャートを表示できます。
  </p>
  {tv_grid_html}

  <!-- AI要約 -->
  <div class="sec-h">🤖 AI要約（Ollama）</div>
  {_ai_section(ai_summary)}

  <!-- 主要銘柄 -->
  <div class="sec-h">📋 主要銘柄の動向</div>
  <div class="card">
    <div class="card-title">米国・日本 主要銘柄 前日比</div>
    {_stocks_table(prices)}
  </div>
  {pc('stocks')}

  <!-- コモディティ -->
  <div class="sec-h">⛽ コモディティ・仮想通貨</div>
  {pc('commodities')}

  <!-- 分析 -->
  <div class="sec-h">C〜G. 各市場の分析</div>
  {analysis_html}

  <!-- ニュース -->
  <div class="sec-h">I. 注目ニュース（キーワード別）</div>
  <div class="card" style="padding:12px">
    <div class="card-title">📰 本日のニュース一覧</div>
    {_news_html(news)}
  </div>
  {pc('news')}

  <!-- 免責 -->
  <div class="sec-h">K. 免責事項</div>
  <div class="card" style="border-left:4px solid #f59e0b">
    <p style="color:#92400e;font-size:13px">⚠️ {DISCLAIMER}</p>
    <p style="color:#9ca3af;font-size:12px;margin-top:7px">
      ・断定表現（「必ず上がる」「確実に下がる」など）は使用しません。<br>
      ・事実・推測・意見を明示的に区別しています。<br>
      ・データは公開情報から取得しており、遅延・誤差がある可能性があります。
    </p>
  </div>

</div>

<div class="footer">
  📊 投資経済 AI 秘書システム　|　{now}<br>
  本レポートは分析補助目的です。投資判断はご自身の責任で行ってください。
</div>
</body>
</html>"""


def build_markdown(mode, prices, news, risk, analysis,
                   chart_paths, fear_greed, ai_summary) -> str:
    today = get_today_str()
    now   = get_jst_now().strftime("%Y-%m-%d %H:%M JST")
    sentiment = risk.get("sentiment","不明")
    score     = risk.get("score",0)
    fg_score  = fear_greed.get("score","---")
    fg_rating = fear_greed.get("rating_ja","---")
    lines = [
        f"# 投資経済レポート ({today} / {mode})",
        f"生成時刻: {now}　※投資助言ではありません",
        f"\n## A. 今日の結論",
        f"**地合い: {sentiment}** (スコア: {score:+.2f})",
        f"**Fear & Greed: {fg_score} / {fg_rating}**",
    ]
    if ai_summary.get("available"):
        lines.append(f"\n## 🤖 AI要約 ({ai_summary.get('model','')})")
        lines.append(ai_summary.get("news_summary",""))
        lines.append(ai_summary.get("market_comment",""))
    lines.append(f"\n⚠️ {DISCLAIMER}")
    return "\n".join(lines)


def save_report(mode, prices, news, risk, analysis,
                chart_paths, fear_greed=None,
                ai_summary=None, plotly_charts=None) -> dict:
    if fear_greed    is None: fear_greed    = {}
    if ai_summary    is None: ai_summary    = {"available": False}
    if plotly_charts is None: plotly_charts = {}

    today = get_today_str()
    dirs  = get_dirs()
    md    = build_markdown(mode, prices, news, risk, analysis,
                           chart_paths, fear_greed, ai_summary)
    html  = build_html(mode, prices, news, risk, analysis,
                       chart_paths, fear_greed, ai_summary, plotly_charts)

    md_path   = dirs["reports"] / f"{today}_{mode}.md"
    html_path = dirs["reports"] / f"{today}_{mode}.html"
    arc_md    = dirs["archive"] / f"{today}_{mode}.md"

    for path, content in [(md_path, md), (arc_md, md)]:
        with open(path, "w", encoding="utf-8") as f: f.write(content)
    with open(html_path, "w", encoding="utf-8") as f: f.write(html)
    logger.info(f"レポート保存: {html_path}")
    return {"md": str(md_path), "html": str(html_path)}
