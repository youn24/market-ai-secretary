"""
温かいマガジン風レポート（ガネ先生＆カワウソくんの相場ダイジェスト）

design_ai.py（ダーク・ダッシュボード）とは別系統の、ベージュ背景＋キャラ画像＋
リボン見出しの「雑誌インフォグラフィック」スタイル。note/X/Telegram用に画像化して
シェアする縦長レポートを想定。

方針（ユーザー決定）：
  ・構造と数字は HTML/CSS で正確に（株価・指標は実データ）
  ・イラストは既存のAI生成キャラPNG（docs/assets/char_*.png）をbase64で埋め込み
  ・温かい・やさしい・わかりやすい雰囲気（初心者向け）

出力：docs/digest.html（GitHub Pagesで公開＆スクショして各SNSへ）
"""
import base64

from src.utils import BASE_DIR, get_jst_now, setup_logger

logger = setup_logger("magazine_report")

# ── 温かいマガジン・パレット ──────────────────────────────────────────
CREAM_BG  = "#f4e8cc"
CREAM_BG2 = "#efe0bf"
PAPER     = "#fffdf6"
INK       = "#4a3b22"
INK_SOFT  = "#8a7550"
GREEN     = "#2f9e4f"
RED       = "#d8483d"
GOLD      = "#c79a3a"
RIBBON    = "#9c6b2f"
RIBBON_D  = "#7d5322"
GREEN_RB  = "#3f7d2f"
GREEN_RBD = "#2f6022"


def _b64(path: str) -> str:
    try:
        with open(path, "rb") as f:
            return "data:image/png;base64," + base64.b64encode(f.read()).decode()
    except Exception:
        return ""


def _char_mood(score):
    if score is None:
        return "analyzing"
    if score >= 1.0:
        return "bullish"
    if score <= -2.0:
        return "crash"
    if score <= -0.5:
        return "bearish"
    return "analyzing"


def _p(prices, sym):
    d = (prices or {}).get(sym, {}) or {}
    return d.get("latest"), d.get("change_pct")


def _fmt(v, dp=0):
    if v is None:
        return "---"
    return f"{v:,.{dp}f}"


def _chg_cell(chg):
    if chg is None:
        return f'<span style="color:{INK_SOFT};">―</span>'
    c = GREEN if chg >= 0 else RED
    sign = "+" if chg >= 0 else ""
    return f'<span style="color:{c};font-weight:800;">{sign}{chg:.2f}%</span>'


def _diff_cell(v, chg):
    if v is None or chg is None:
        return f'<span style="color:{INK_SOFT};">―</span>'
    diff = v * chg / 100.0
    c = GREEN if chg >= 0 else RED
    sign = "+" if diff >= 0 else ""
    dp = 2 if abs(v) < 1000 else 0
    return f'<span style="color:{c};font-weight:700;">{sign}{diff:,.{dp}f}</span>'


def _ribbon(num, title, green=False):
    a, b = (GREEN_RB, GREEN_RBD) if green else (RIBBON, RIBBON_D)
    badge = (f'<span style="background:#fff;color:{a};border-radius:50%;width:23px;height:23px;'
             f'display:inline-flex;align-items:center;justify-content:center;font-size:14px;'
             f'font-weight:900;margin-right:9px;">{num}</span>') if num else ""
    return f'''
<div style="margin:20px 0 11px;">
  <div style="display:inline-block;background:linear-gradient(180deg,{a},{b});color:#fff8e7;
              padding:9px 24px 9px 14px;border-radius:9px;font-size:16px;font-weight:900;
              box-shadow:0 2px 0 rgba(90,60,20,.35);">
    {badge}{title}
  </div>
</div>'''


def _market_table(rows):
    """指数テーブル（指数 / 現在値 / 前日比 / 騰落率）"""
    body = ""
    for label, v, chg, dp, flag in rows:
        body += f'''
<tr>
  <td style="padding:9px 10px;font-weight:800;color:{INK};border-bottom:1px solid #ede0bd;">{flag}{label}</td>
  <td style="padding:9px 10px;text-align:right;font-weight:800;color:{INK};border-bottom:1px solid #ede0bd;font-variant-numeric:tabular-nums;">{_fmt(v,dp)}</td>
  <td style="padding:9px 10px;text-align:right;border-bottom:1px solid #ede0bd;font-variant-numeric:tabular-nums;">{_diff_cell(v,chg)}</td>
  <td style="padding:9px 12px;text-align:right;border-bottom:1px solid #ede0bd;font-variant-numeric:tabular-nums;">{_chg_cell(chg)}</td>
</tr>'''
    return f'''
<div style="background:{PAPER};border:1px solid #e6d4a8;border-radius:12px;overflow:hidden;box-shadow:0 1px 4px rgba(140,110,60,.1);">
  <table style="width:100%;border-collapse:collapse;font-size:14px;">
    <thead><tr style="background:{CREAM_BG};">
      <th style="padding:7px 10px;text-align:left;font-size:11px;color:{INK_SOFT};">指数</th>
      <th style="padding:7px 10px;text-align:right;font-size:11px;color:{INK_SOFT};">現在値</th>
      <th style="padding:7px 10px;text-align:right;font-size:11px;color:{INK_SOFT};">前日比</th>
      <th style="padding:7px 12px;text-align:right;font-size:11px;color:{INK_SOFT};">騰落率</th>
    </tr></thead>
    <tbody>{body}</tbody>
  </table>
</div>'''


def _point_card(emoji, title, txt, c):
    return f'''
<div style="display:flex;gap:9px;align-items:flex-start;background:{PAPER};border:1px solid #e6d4a8;
            border-left:4px solid {c};border-radius:0 10px 10px 0;padding:9px 12px;margin-bottom:8px;">
  <div style="font-size:18px;">{emoji}</div>
  <div>
    <div style="font-size:13px;font-weight:800;color:{c};margin-bottom:1px;">{title}</div>
    <div style="font-size:12px;color:{INK};line-height:1.5;">{txt}</div>
  </div>
</div>'''


def generate(prices=None, news=None, risk=None, fear_greed=None,
             ai_summary=None, scenario=None, sector_ranking=None, mode="morning") -> str:
    prices = prices or {}
    risk = risk or {}
    fear_greed = fear_greed or {}
    ai_summary = ai_summary or {}
    scenario = scenario or {}
    news = news or []

    now = get_jst_now()
    wd = ["月", "火", "水", "木", "金", "土", "日"][now.weekday()]
    date_str = f"{now.year}/{now.month}/{now.day}（{wd}）"

    score = risk.get("score", 0)
    sentiment = risk.get("sentiment", "中立")
    mood = _char_mood(score)
    gane = _b64(str(BASE_DIR / "docs" / "assets" / f"char_gane_{mood}.png")) or _b64(str(BASE_DIR / "docs" / "assets" / "char_gane_analyzing.png"))
    kawa = _b64(str(BASE_DIR / "docs" / "assets" / f"char_kawa_{mood}.png")) or _b64(str(BASE_DIR / "docs" / "assets" / "char_kawa_analyzing.png"))

    if score >= 1.0:
        mood_c, mood_emo = GREEN, "📈"
    elif score >= 0.3:
        mood_c, mood_emo = GREEN, "🌤"
    elif score >= -0.3:
        mood_c, mood_emo = GOLD, "☁️"
    elif score >= -1.0:
        mood_c, mood_emo = RED, "🌧"
    else:
        mood_c, mood_emo = RED, "⛈"

    # ── クイックサマリー ──
    def _qs(label, sym, emoji):
        _, chg = _p(prices, sym)
        if chg is None:
            t, c = "―", INK_SOFT
        elif chg >= 0.5:
            t, c = "上昇", GREEN
        elif chg >= -0.0:
            t, c = "やや高", GREEN
        elif chg > -0.5:
            t, c = "やや安", RED
        else:
            t, c = "下落", RED
        return f'''
<div style="text-align:center;flex:1;">
  <div style="font-size:24px;">{emoji}</div>
  <div style="font-size:11px;color:{INK_SOFT};font-weight:800;margin:3px 0 1px;">{label}</div>
  <div style="font-size:12px;color:{c};font-weight:900;">{t}</div>
</div>'''

    quick = f'''
<div style="display:flex;gap:4px;background:{PAPER};border:1px solid #e6d4a8;border-radius:12px;padding:12px 6px;">
  {_qs("日本株","^N225","🗾")}
  {_qs("米国株","^GSPC","🇺🇸")}
  {_qs("為替","USDJPY=X","💱")}
  {_qs("半導体","^SOX","🔌")}
  {_qs("BTC","BTC-USD","₿")}
</div>'''

    # ── 日本市場テーブル ──
    jp_v, jp_c = _p(prices, "^N225")
    usd_v, usd_c = _p(prices, "USDJPY=X")
    jp_table = _market_table([
        ("日経225", jp_v, jp_c, 2, "🗾 "),
        ("TOPIX", *_p(prices, "^TOPX"), 2, ""),
        ("グロース250", *_p(prices, "GROWTH250"), 2, ""),
        ("日経先物(CME)", *_p(prices, "NIY=F"), 0, ""),
        ("ドル円", usd_v, usd_c, 2, "💱 "),
    ])

    # ── 米国市場テーブル ──
    us_table = _market_table([
        ("S&P500", *_p(prices, "^GSPC"), 2, "🇺🇸 "),
        ("NASDAQ", *_p(prices, "^IXIC"), 2, ""),
        ("ダウ", *_p(prices, "^DJI"), 2, ""),
        ("SOX半導体", *_p(prices, "^SOX"), 2, "🔌 "),
        ("VIX", *_p(prices, "^VIX"), 2, ""),
    ])

    # ── AI3視点 ──
    bull = (ai_summary.get("bull_view") or "")[:64]
    bear = (ai_summary.get("bear_view") or "")[:64]
    neut = (ai_summary.get("neutral_view") or "")[:64]
    points = ""
    if bull:
        points += _point_card("🌱", "地合い", bull, GREEN)
    if bear:
        points += _point_card("⚠️", "注意点", bear, GOLD)
    if neut:
        points += _point_card("🎯", "方針", neut, RIBBON)

    # ── 3シナリオ ──
    scen_html = ""
    if scenario.get("available"):
        def _sc(emo, name, d, c, bg):
            return f'''
<div style="flex:1;background:{bg};border:1px solid {c}55;border-radius:11px;padding:11px 8px;text-align:center;">
  <div style="font-size:20px;">{emo}</div>
  <div style="font-size:13px;font-weight:900;color:{c};margin:2px 0;">{name} {d.get("prob","?")}%</div>
  <div style="font-size:11px;color:{INK};line-height:1.4;">{(d.get("text","") or "")[:42]}</div>
</div>'''
        scen_html = (f'<div style="display:flex;gap:8px;">'
                     f'{_sc("🐂","強気",scenario.get("bull",{}),GREEN,"#eaf6ec")}'
                     f'{_sc("⚖️","中立",scenario.get("base",{}),GOLD,"#fbf3df")}'
                     f'{_sc("🐻","弱気",scenario.get("bear",{}),RED,"#fbeae8")}</div>')

    # ── セクター勝敗 ──
    sector_html = ""
    sr = sector_ranking or {}
    ups = sr.get("top", []) or sr.get("gainers", []) or []
    downs = sr.get("bottom", []) or sr.get("losers", []) or []
    if ups or downs:
        def _sec_col(title, items, c, bg, emo):
            rows = ""
            for i, s in enumerate(items[:3], 1):
                nm = s.get("name", "") if isinstance(s, dict) else str(s)
                ch = s.get("change_pct") or s.get("chg") if isinstance(s, dict) else None
                chs = f'{"+" if (ch or 0)>=0 else ""}{ch:.2f}%' if ch is not None else ""
                rows += f'''<div style="display:flex;align-items:center;gap:7px;padding:6px 0;border-bottom:1px dashed #e0cfa0;">
  <span style="background:{c};color:#fff;border-radius:50%;width:18px;height:18px;display:inline-flex;align-items:center;justify-content:center;font-size:11px;font-weight:800;">{i}</span>
  <span style="flex:1;font-size:12.5px;font-weight:700;color:{INK};">{nm}</span>
  <span style="font-size:12.5px;font-weight:800;color:{c};">{chs}</span>
</div>'''
            return f'''
<div style="flex:1;background:{bg};border:1px solid {c}44;border-radius:11px;padding:6px 12px 10px;">
  <div style="text-align:center;font-size:13px;font-weight:900;color:{c};padding:5px 0;">{emo} {title}</div>
  {rows}
</div>'''
        sector_html = (f'<div style="display:flex;gap:8px;">'
                       f'{_sec_col("上昇セクター", ups, GREEN, "#eaf6ec", "📈")}'
                       f'{_sec_col("下落セクター", downs, RED, "#fbeae8", "📉")}</div>')

    # ── 注目ニュース ──
    news_html = ""
    for n in [x for x in news if isinstance(x, dict) and x.get("title")][:3]:
        news_html += f'''<div style="display:flex;gap:8px;align-items:flex-start;padding:7px 0;border-bottom:1px dashed #e0cfa0;">
  <span style="color:{GOLD};font-size:14px;">●</span>
  <span style="font-size:12.5px;color:{INK};line-height:1.5;">{n["title"][:46]}</span>
</div>'''

    # ── まとめ 3列（全体感・追い風・注意点）──
    overall = f"全体は{sentiment}。" + ("押し目を拾いやすい地合い。" if score >= 0.3 else "無理せず守りも意識。" if score <= -0.5 else "方向感が出るまで様子見も手。")
    tailwind = "円安・米株高が追い風。" if (usd_c or 0) >= 0 else "為替の振れに注意。"
    if bull:
        tailwind = bull[:30]
    caution = bear[:30] if bear else "高値圏は寄り天・利確売りに注意。"
    summary3 = f'''
<div style="display:flex;gap:8px;">
  <div style="flex:1;background:{PAPER};border:1px solid #e6d4a8;border-radius:11px;padding:10px;">
    <div style="text-align:center;font-size:12px;font-weight:900;color:{RIBBON};margin-bottom:5px;">📋 全体感</div>
    <div style="font-size:11.5px;color:{INK};line-height:1.5;">{overall}</div>
  </div>
  <div style="flex:1;background:{PAPER};border:1px solid #e6d4a8;border-radius:11px;padding:10px;">
    <div style="text-align:center;font-size:12px;font-weight:900;color:{GREEN};margin-bottom:5px;">🍃 追い風</div>
    <div style="font-size:11.5px;color:{INK};line-height:1.5;">{tailwind}</div>
  </div>
  <div style="flex:1;background:{PAPER};border:1px solid #e6d4a8;border-radius:11px;padding:10px;">
    <div style="text-align:center;font-size:12px;font-weight:900;color:{RED};margin-bottom:5px;">⚠️ 注意点</div>
    <div style="font-size:11.5px;color:{INK};line-height:1.5;">{caution}</div>
  </div>
</div>'''

    fg = fear_greed.get("score")
    fg_txt = fear_greed.get("rating_ja", "—")

    html = f'''<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>相場ダイジェスト {date_str}</title>
<style>
  *{{margin:0;padding:0;box-sizing:border-box;}}
  body{{font-family:"Hiragino Maru Gothic ProN","Hiragino Sans","Yu Gothic","Meiryo",sans-serif;
    background:linear-gradient(160deg,{CREAM_BG},{CREAM_BG2});color:{INK};-webkit-font-smoothing:antialiased;}}
  .wrap{{max-width:540px;margin:0 auto;padding:16px 16px 26px;}}
</style></head>
<body><div class="wrap">

  <div style="background:linear-gradient(180deg,{RIBBON},{RIBBON_D});border-radius:10px;text-align:center;padding:5px;margin-bottom:10px;">
    <span style="color:#fff8e7;font-size:12px;font-weight:800;">🌅 1日1分でサクッと把握！ AIチーム自動分析レポート</span>
  </div>

  <div style="display:flex;align-items:center;gap:4px;margin-bottom:10px;">
    <img src="{gane}" alt="ガネ先生" style="width:88px;height:88px;object-fit:contain;filter:drop-shadow(0 2px 3px rgba(120,90,40,.25));">
    <div style="flex:1;text-align:center;">
      <div style="font-size:12px;color:{INK_SOFT};font-weight:800;">ガネ先生とカワウソくんの</div>
      <div style="font-size:25px;font-weight:900;color:{INK};line-height:1.15;">リアルタイム相場ダイジェスト</div>
      <div style="display:inline-block;background:{INK};color:{CREAM_BG};font-size:11px;font-weight:800;border-radius:20px;padding:3px 15px;margin-top:5px;">📅 {date_str} 朝</div>
    </div>
    <img src="{kawa}" alt="カワウソくん" style="width:88px;height:88px;object-fit:contain;filter:drop-shadow(0 2px 3px rgba(120,90,40,.25));">
  </div>

  <div style="background:{PAPER};border:2px solid {mood_c};border-radius:14px;padding:12px 16px;display:flex;align-items:center;gap:14px;margin-bottom:4px;box-shadow:0 2px 5px rgba(140,110,60,.12);">
    <div style="width:50px;height:50px;border-radius:50%;background:{mood_c};display:flex;align-items:center;justify-content:center;font-size:25px;">{mood_emo}</div>
    <div style="flex:1;">
      <div style="font-size:12px;color:{INK_SOFT};font-weight:800;">本日の地合い</div>
      <div style="font-size:23px;font-weight:900;color:{mood_c};line-height:1.1;">{sentiment}</div>
    </div>
    <div style="text-align:center;background:{CREAM_BG};border-radius:10px;padding:6px 13px;">
      <div style="font-size:10px;color:{INK_SOFT};font-weight:800;">リスク心理</div>
      <div style="font-size:20px;font-weight:900;color:{mood_c};">{fg if fg is not None else "—"}</div>
      <div style="font-size:10px;color:{INK_SOFT};">{fg_txt}</div>
    </div>
  </div>

  {_ribbon("", "本日のクイックまとめ")}
  {quick}

  {_ribbon("1", "今日の日本市場（概況）")}
  {jp_table}

  {_ribbon("2", "昨夜の米国市場（主要指数）")}
  {us_table}

  {_ribbon("3", "AIの見立て（3つの視点）")}
  {points or f'<div style="text-align:center;color:{INK_SOFT};font-size:12px;padding:8px;">AI分析データなし</div>'}

  {(_ribbon("4", "今日の見通し（3シナリオ）") + scen_html) if scen_html else ""}

  {(_ribbon("5", "注目セクター", green=True) + sector_html) if sector_html else ""}

  {(_ribbon("6", "注目ニュース") + f'<div style="background:{PAPER};border:1px solid #e6d4a8;border-radius:12px;padding:5px 14px;">{news_html}</div>') if news_html else ""}

  {_ribbon("★", "今日のまとめ（全体感・追い風・注意点）")}
  {summary3}

  <div style="text-align:center;font-size:10px;color:{INK_SOFT};margin-top:18px;line-height:1.6;">
    🐘 ガネ先生 ＆ 🦦 カワウソくん｜AIチーム自動生成レポート<br>
    ※数値は取得時点の参考値です。最新は各社ニュース・取引所公表をご確認ください。
  </div>

</div></body></html>'''
    return html


def run(prices=None, news=None, risk=None, fear_greed=None,
        ai_summary=None, scenario=None, sector_ranking=None, mode="morning", **_kw) -> dict:
    try:
        html = generate(prices=prices, news=news, risk=risk, fear_greed=fear_greed,
                        ai_summary=ai_summary, scenario=scenario,
                        sector_ranking=sector_ranking, mode=mode)
        out_path = BASE_DIR / "docs" / "digest.html"
        out_path.parent.mkdir(exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)
        logger.info(f"✅ マガジン風レポート生成: {out_path}")
        return {"available": True, "path": str(out_path), "html": html}
    except Exception as e:
        import traceback
        logger.error(f"マガジン風レポートエラー: {e}")
        logger.debug(traceback.format_exc())
        return {"available": False, "reason": str(e)}


if __name__ == "__main__":
    prices = {
        "^N225": {"latest": 64689.38, "change_pct": -1.11},
        "^TOPX": {"latest": 3870.84, "change_pct": -0.65},
        "GROWTH250": {"latest": 722.21, "change_pct": -2.51},
        "NIY=F": {"latest": 64600, "change_pct": -0.9},
        "USDJPY=X": {"latest": 160.83, "change_pct": 0.01},
        "^GSPC": {"latest": 5386.69, "change_pct": -0.26},
        "^IXIC": {"latest": 18957.13, "change_pct": 0.46},
        "^DJI": {"latest": 42760, "change_pct": -0.03},
        "^SOX": {"latest": 5625.71, "change_pct": -1.93},
        "^VIX": {"latest": 19.37, "change_pct": 5.02},
        "BTC-USD": {"latest": 64007, "change_pct": 1.22},
    }
    risk = {"score": -0.8, "sentiment": "やや弱気"}
    fear_greed = {"score": 38, "rating_ja": "恐怖"}
    ai_summary = {
        "bull_view": "銀行・不動産などディフェンシブが相対的に底堅い",
        "bear_view": "半導体・グロースの下落リスクに警戒",
        "neutral_view": "戻りは限定的、出来高の伴う銘柄を厳選",
    }
    scenario = {"available": True,
        "bull": {"prob": 30, "text": "半導体反発なら戻り試す"},
        "base": {"prob": 50, "text": "もみ合い・ディフェンシブ優勢"},
        "bear": {"prob": 20, "text": "米中摩擦再燃で再下押し"}}
    sector_ranking = {
        "top": [{"name": "不動産", "change_pct": 2.53}, {"name": "小売", "change_pct": 1.58}, {"name": "銀行", "change_pct": 1.20}],
        "bottom": [{"name": "半導体・電子部品", "change_pct": -3.91}, {"name": "機械・重電", "change_pct": -2.25}, {"name": "海運", "change_pct": -1.78}],
    }
    news = [{"title": "FRB高官：利下げ時期はデータ次第、慎重姿勢を維持"},
            {"title": "日銀の国債買い入れ減額観測で金利は上昇基調"},
            {"title": "米中貿易協議に進展の期待、ハイテク株が反発"}]
    r = run(prices=prices, news=news, risk=risk, fear_greed=fear_greed,
            ai_summary=ai_summary, scenario=scenario, sector_ranking=sector_ranking)
    print("生成:", r.get("path"))
