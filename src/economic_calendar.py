"""
週次経済カレンダー生成モジュール
今週の主要経済指標・決算・イベントを取得してカレンダー画像を生成する
"""
import os
import json
import traceback
import requests
from datetime import datetime, timedelta
from pathlib import Path
from src.utils import setup_logger, get_dirs, get_jst_now, BASE_DIR

logger = setup_logger("economic_calendar")

# 国旗絵文字マップ
FLAG = {
    "US": "🇺🇸", "JP": "🇯🇵", "EU": "🇪🇺", "UK": "🇬🇧",
    "CN": "🇨🇳", "CA": "🇨🇦", "AU": "🇦🇺", "DE": "🇩🇪",
    "FR": "🇫🇷", "CH": "🇨🇭", "NZ": "🇳🇿", "world": "🌐",
}

# 重要度カラー
IMP_COLOR = {
    "high":   "#f44336",   # 赤
    "medium": "#ff9800",   # 橙
    "low":    "#607d8b",   # グレー
    "決算":    "#ab47bc",   # 紫
    "日銀":    "#ef5350",   # 赤系
    "FRB":    "#e53935",   # 赤系
    "天体":    "#7e57c2",   # 紫（天体イベント）
}


def _load_watchlist_symbols() -> list[tuple[str, str]]:
    """data/watchlist.json から [(symbol, name), ...] を返す"""
    path = BASE_DIR / "data" / "watchlist.json"
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for s in data.get("stocks", []):
            sym = s.get("symbol", "")
            if sym:
                out.append((sym, s.get("name", sym)))
    except Exception as e:
        logger.warning(f"watchlist読み込み失敗: {e}")
    return out


def get_week_dates() -> list[datetime]:
    """今週月〜金の日付リストを返す（JST）"""
    now = get_jst_now()
    # 月曜日を起点に
    monday = now - timedelta(days=now.weekday())
    return [monday + timedelta(days=i) for i in range(5)]


def fetch_calendar_via_gemini(week_dates: list) -> list:
    """Geminiに今週の経済カレンダーを生成させる（最も確実な手法）"""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return []

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))

        mon_str = week_dates[0].strftime("%Y年%m月%d日")
        fri_str = week_dates[4].strftime("%Y年%m月%d日")

        prompt = f"""あなたは金融市場の専門家です。
{mon_str}（月）〜 {fri_str}（金）の週の
主要な経済イベントスケジュールをJSON形式で出力してください。

実際に予定されている（または毎月定期的に発表される）イベントを
以下のJSON配列形式で20件程度出力してください：

[
  {{
    "date": "2026-06-08",
    "time": "08:50",
    "country": "JP",
    "category": "経済指標",
    "importance": "high",
    "event": "1-3月期GDP・2次速報"
  }},
  ...
]

countryは JP/US/EU/UK/CN/CA/AU のいずれか。
importanceは high/medium/low のいずれか。
categoryは 経済指標/決算/金融政策/市場/その他 のいずれか。

重要度highのものを必ず含めてください（CPI、雇用統計、FOMC、日銀会合、GDP等）。
企業決算も含めてください（決算発表予定の主要企業）。
timeが不明な場合は "-" としてください。

JSONのみ出力し、説明文は不要です。"""

        response = model.generate_content(prompt)
        raw = response.text.strip()

        # JSON抽出
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        events = json.loads(raw)
        logger.info(f"✅ Geminiカレンダー取得: {len(events)}件")
        return events

    except Exception as e:
        logger.error(f"Geminiカレンダー取得エラー: {e}")
        logger.debug(traceback.format_exc())
        return []


def fetch_earnings_yfinance(week_dates: list) -> list:
    """yfinanceから主要企業決算を取得（米国主要株。今週分のみ・カレンダー画像用）"""
    events = []
    try:
        import yfinance as yf
        major_tickers = ["AAPL","MSFT","GOOGL","AMZN","META","NVDA","TSLA"]
        start = week_dates[0].strftime("%Y-%m-%d")
        end   = week_dates[4].strftime("%Y-%m-%d")

        for ticker in major_tickers:
            try:
                d_str, _ = _get_earnings_date(yf, ticker)
                if d_str and start <= d_str <= end:
                    events.append({
                        "date": d_str, "time": "早朝", "country": "US",
                        "category": "決算", "importance": "high",
                        "event": f"決算 {ticker}",
                    })
            except Exception:
                pass
    except Exception as e:
        logger.debug(f"yfinance決算取得: {e}")
    return events


def _get_earnings_date(yf, ticker: str):
    """1銘柄の次回決算日(YYYY-MM-DD)と売上予想Averageを返す"""
    t = yf.Ticker(ticker)
    cal = t.calendar
    if not cal:
        return None, None
    earn_date = cal.get("Earnings Date") if isinstance(cal, dict) else None
    rev_avg   = cal.get("Revenue Average") if isinstance(cal, dict) else None
    if isinstance(earn_date, (list, tuple)) and earn_date:
        earn_date = earn_date[0]
    d_str = earn_date.strftime("%Y-%m-%d") if hasattr(earn_date, "strftime") else None
    return d_str, rev_avg


def fetch_watchlist_earnings(week_dates: list, days_ahead: int = 45) -> tuple[list, list]:
    """
    ウォッチリスト銘柄の決算予定を取得。
    返り値: (今週分events, 今後days_ahead日分のupcoming一覧)
    """
    week_events = []
    upcoming = []
    try:
        import yfinance as yf
        symbols = _load_watchlist_symbols()
        start = week_dates[0].strftime("%Y-%m-%d")
        end   = week_dates[4].strftime("%Y-%m-%d")
        today = get_jst_now().strftime("%Y-%m-%d")
        horizon = (get_jst_now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

        for sym, name in symbols:
            try:
                d_str, rev_avg = _get_earnings_date(yf, sym)
                if not d_str:
                    continue
                code4 = sym.split(".")[0]
                # 今週分 → カレンダー画像に
                if start <= d_str <= end:
                    week_events.append({
                        "date": d_str, "time": "決算", "country": "JP",
                        "category": "決算", "importance": "high",
                        "event": f"決算 {name}",
                    })
                # 今後days_ahead日分 → 先読みリストに
                if today <= d_str <= horizon:
                    upcoming.append({
                        "date": d_str, "code": code4, "name": name,
                        "rev_avg": rev_avg,
                    })
            except Exception:
                pass
        upcoming.sort(key=lambda x: x["date"])
        logger.info(f"ウォッチリスト決算: 今週{len(week_events)}件 / 今後{len(upcoming)}件")
    except Exception as e:
        logger.debug(f"ウォッチリスト決算取得: {e}")
    return week_events, upcoming


def generate_calendar_image(events: list, week_dates: list) -> str | None:
    """週次カレンダーをPNG画像として生成"""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        from matplotlib.patches import FancyBboxPatch

        try:
            import japanize_matplotlib  # noqa
        except Exception:
            pass

        BG     = "#0f1923"
        CARD   = "#1a2535"
        BORDER = "#2a3a50"
        TEXT   = "#e8f0fe"
        TEXT2  = "#8899aa"
        ACCENT = "#00d4ff"
        HDR    = "#0a1520"

        # 日付ごとにグループ化
        day_events: dict[str, list] = {}
        for d in week_dates:
            key = d.strftime("%Y-%m-%d")
            day_events[key] = []

        for ev in events:
            key = ev.get("date","")
            if key in day_events:
                day_events[key].append(ev)

        # 各日のイベントを時刻順にソート
        for key in day_events:
            day_events[key].sort(key=lambda x: x.get("time","99:99") or "99:99")

        # 全イベント数を数えて行数を決定
        total_rows = sum(max(len(v), 1) for v in day_events.values()) + 1  # +1 header
        total_rows = max(total_rows, 8)

        fig_h = max(total_rows * 0.52 + 1.5, 8)
        fig = plt.figure(figsize=(13, fig_h), facecolor=BG)
        fig.patch.set_facecolor(BG)

        # タイトル（Windows/Linux両対応）
        try:
            mon_str = week_dates[0].strftime("%Y年%m月%d日")
            fri_str = week_dates[4].strftime("%m月%d日")
        except Exception:
            mon_str = ""; fri_str = ""

        fig.text(0.5, 0.97, f"一週間の注目イベントスケジュール",
                 ha="center", va="top", fontsize=16, fontweight="bold",
                 color=TEXT)
        fig.text(0.5, 0.94, f"{mon_str} 〜 {fri_str}",
                 ha="center", va="top", fontsize=11, color=ACCENT)

        ax = fig.add_axes([0.01, 0.01, 0.98, 0.90])
        ax.set_facecolor(BG)
        ax.axis("off")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)

        # カラム定義 (x位置, 幅)
        cols = {
            "date":  (0.00, 0.12),
            "time":  (0.12, 0.08),
            "flag":  (0.20, 0.05),
            "cat":   (0.25, 0.10),
            "event": (0.35, 0.65),
        }
        headers = ["日付", "時刻", "国", "種別", "内容（決算結果は目安・時間は予定）"]

        # ヘッダー行
        row_h = 1.0 / (total_rows + 0.5)
        y     = 1.0 - row_h * 0.3

        # ヘッダー背景
        hdr_rect = FancyBboxPatch((0, y - row_h * 0.85), 1, row_h,
                                  boxstyle="square,pad=0", linewidth=0,
                                  facecolor=HDR, transform=ax.transAxes, zorder=1)
        ax.add_patch(hdr_rect)

        for (hk, (hx, hw)), ht in zip(cols.items(), headers):
            ax.text(hx + 0.005, y - row_h * 0.35, ht,
                    ha="left", va="center", fontsize=9,
                    fontweight="bold", color=ACCENT,
                    transform=ax.transAxes)

        cur_y = y - row_h

        # 日付ごとに描画
        day_labels = ["月", "火", "水", "木", "金"]
        for day_idx, d in enumerate(week_dates):
            key    = d.strftime("%Y-%m-%d")
            evlist = day_events.get(key, [])
            nrows  = max(len(evlist), 1)
            weekday_label = day_labels[day_idx]
            date_label = f"{d.month}/{d.day}\n（{weekday_label}）"

            # 行背景 (交互に色を変える)
            bg_color = "#1a2535" if day_idx % 2 == 0 else "#151f2e"
            for row_i in range(nrows):
                rect_y = cur_y - row_h * row_i - row_h
                rect = FancyBboxPatch((0, rect_y), 1, row_h,
                                      boxstyle="square,pad=0", linewidth=0,
                                      facecolor=bg_color, transform=ax.transAxes, zorder=1)
                ax.add_patch(rect)

            # 区切り線
            sep_y = cur_y - row_h * nrows
            ax.plot([0, 1], [sep_y, sep_y], color=BORDER, linewidth=0.8,
                    transform=ax.transAxes, zorder=2)

            # 日付（縦中央揃え）
            date_cy = cur_y - row_h * (nrows - 1) / 2 - row_h * 0.5
            ax.text(cols["date"][0] + 0.005, date_cy, date_label,
                    ha="left", va="center", fontsize=9, fontweight="bold",
                    color=TEXT, transform=ax.transAxes, zorder=3,
                    linespacing=1.4)

            # イベント行
            if not evlist:
                ax.text(cols["event"][0] + 0.01, cur_y - row_h * 0.5,
                        "（主要イベントなし）",
                        ha="left", va="center", fontsize=8.5,
                        color=TEXT2, transform=ax.transAxes, zorder=3)
            else:
                for ev_i, ev in enumerate(evlist):
                    ey = cur_y - row_h * ev_i - row_h * 0.5

                    # 時刻
                    t = ev.get("time","-") or "-"
                    ax.text(cols["time"][0] + 0.005, ey, t,
                            ha="left", va="center", fontsize=8.5, color=TEXT2,
                            transform=ax.transAxes, zorder=3)

                    # 国旗
                    flag = FLAG.get(ev.get("country",""), "🌐")
                    ax.text(cols["flag"][0] + 0.005, ey, flag,
                            ha="left", va="center", fontsize=10,
                            transform=ax.transAxes, zorder=3)

                    # 種別バッジ
                    cat  = ev.get("category","")
                    imp  = ev.get("importance","low")
                    cat_c = IMP_COLOR.get(imp, IMP_COLOR["low"])
                    if "決算" in cat: cat_c = IMP_COLOR["決算"]
                    elif "日銀" in ev.get("event",""): cat_c = IMP_COLOR["日銀"]
                    elif "FRB" in ev.get("event","") or "FOMC" in ev.get("event",""): cat_c = IMP_COLOR["FRB"]

                    badge = FancyBboxPatch(
                        (cols["cat"][0] + 0.002, ey - 0.012),
                        0.085, 0.024,
                        boxstyle="round,pad=0.003", linewidth=0,
                        facecolor=cat_c + "55", transform=ax.transAxes, zorder=3)
                    ax.add_patch(badge)
                    ax.text(cols["cat"][0] + 0.005, ey, cat[:5],
                            ha="left", va="center", fontsize=7.5,
                            color=cat_c, fontweight="bold",
                            transform=ax.transAxes, zorder=4)

                    # イベント名
                    event_text = ev.get("event","")
                    # 重要度が high なら色付き
                    ev_color = TEXT if imp != "high" else "#ffcc80"
                    fw = "bold" if imp == "high" else "normal"
                    ax.text(cols["event"][0] + 0.01, ey, event_text[:55],
                            ha="left", va="center", fontsize=9,
                            color=ev_color, fontweight=fw,
                            transform=ax.transAxes, zorder=3)

            cur_y -= row_h * nrows

        # 凡例
        legend_y = 0.005
        legend_items = [
            ("🔴 重要度：高", "#f44336"),
            ("🟠 重要度：中", "#ff9800"),
            ("🟣 企業決算", "#ab47bc"),
        ]
        for i, (lbl, lc) in enumerate(legend_items):
            ax.text(0.02 + i * 0.22, legend_y, lbl,
                    ha="left", va="bottom", fontsize=7.5, color=lc,
                    transform=ax.transAxes)

        out = get_dirs()["charts"] / f"weekly_calendar_{week_dates[0].strftime('%Y%m%d')}.png"
        plt.savefig(str(out), dpi=140, bbox_inches="tight",
                    facecolor=BG, edgecolor="none")
        plt.close(fig)
        logger.info(f"✅ カレンダー画像生成: {out}")
        return str(out)

    except Exception as e:
        logger.error(f"カレンダー画像生成エラー: {e}")
        logger.debug(traceback.format_exc())
        return None


def run() -> dict:
    """週次カレンダーを生成して返す"""
    logger.info("=== 週次カレンダー生成開始 ===")
    week_dates = get_week_dates()
    logger.info(f"対象週: {week_dates[0].strftime('%Y-%m-%d')} 〜 {week_dates[4].strftime('%Y-%m-%d')}")

    # Geminiでカレンダーデータ取得
    events = fetch_calendar_via_gemini(week_dates)

    # yfinanceで米国主要株の決算追加（今週分）
    events += fetch_earnings_yfinance(week_dates)

    # ウォッチリスト銘柄の決算（今週分 + 今後の先読みリスト）
    watch_week, upcoming_earnings = fetch_watchlist_earnings(week_dates, days_ahead=45)
    events += watch_week

    # 天体イベント（新月・満月・水星逆行）を今週分注入
    astro_summary = {"available": False, "events": [], "mercury_now": False}
    try:
        from src.astro_calendar import get_astro_events, get_upcoming_summary
        from datetime import timezone
        JST = timezone(timedelta(hours=9))
        wk_start = week_dates[0].replace(hour=0, minute=0)
        wk_end   = week_dates[4].replace(hour=23, minute=59)
        if wk_start.tzinfo is None:
            wk_start = wk_start.replace(tzinfo=JST); wk_end = wk_end.replace(tzinfo=JST)
        astro_week = get_astro_events(wk_start, wk_end)
        events += astro_week
        astro_summary = get_upcoming_summary(days=45)
        logger.info(f"天体イベント: 今週{len(astro_week)}件 / 水星逆行中={astro_summary.get('mercury_now')}")
    except Exception as e:
        logger.debug(f"天体イベント取得: {e}")

    # 重複除去（同じ日・同じイベント名）
    seen = set()
    unique_events = []
    for ev in events:
        key = f"{ev.get('date','')}-{ev.get('event','')}"
        if key not in seen:
            seen.add(key)
            unique_events.append(ev)

    # 画像生成
    image_path = generate_calendar_image(unique_events, week_dates)

    logger.info(f"カレンダー完了: {len(unique_events)}件")
    return {
        "available": image_path is not None,
        "image_path": image_path,
        "events": unique_events,
        "upcoming_earnings": upcoming_earnings,
        "astro": astro_summary,
        "week_start": week_dates[0].strftime("%Y-%m-%d"),
        "week_end":   week_dates[4].strftime("%Y-%m-%d"),
    }


def get_html(result: dict) -> str:
    """今後の決算予定 + 天体イベントのHTMLセクションを生成"""
    if not result:
        return ""
    upcoming = result.get("upcoming_earnings", []) or []
    astro    = result.get("astro", {}) or {}

    html = ""

    # ── 今後の決算予定 ──
    if upcoming:
        rows = ""
        for u in upcoming[:20]:
            d = u["date"]
            md = f"{int(d[5:7])}/{int(d[8:10])}"
            rev = ""
            if u.get("rev_avg"):
                try:
                    rev = f'<span style="color:#7a8fa8;font-size:0.78em;">　予想売上 {u["rev_avg"]/1e8:,.0f}億円</span>'
                except Exception:
                    rev = ""
            rows += f'''
<div style="display:flex;gap:10px;padding:8px 0;border-bottom:1px solid #1e2d42;align-items:center;">
  <div style="min-width:54px;font-weight:700;color:#ab47bc;">{md}</div>
  <div style="flex:1;"><b>[{u["code"]}] {u["name"]}</b>{rev}</div>
</div>'''
        html += f'''
<div style="background:#0f1623;border:1px solid #1e2d42;border-radius:14px;padding:16px;margin-bottom:16px;">
  <div style="font-weight:700;margin-bottom:4px;">🗓️ 今後の決算予定（あなたの注目銘柄・45日先まで）</div>
  <div style="font-size:0.75em;color:#7a8fa8;margin-bottom:10px;">予想売上はアナリスト平均（yfinance）。結果がこれを超えれば好決算の目安</div>
  {rows}
</div>'''

    # ── 天体イベント（アノマリー） ──
    aev = astro.get("events", []) if astro else []
    if aev or astro.get("mercury_now"):
        merc = ""
        if astro.get("mercury_now"):
            merc = f'<div style="background:#2a1a3a;border:1px solid #7e57c2;border-radius:8px;padding:8px 12px;margin-bottom:10px;font-size:0.85em;">☿ <b>現在 水星逆行中</b>（{astro.get("mercury_period","")}）— 取引ミス・通信障害に注意という経験則</div>'
        rows = ""
        for e in aev[:12]:
            d = e["date"]
            md = f"{int(d[5:7])}/{int(d[8:10])}"
            rows += f'''
<div style="display:flex;gap:10px;padding:6px 0;border-bottom:1px solid #1e2d42;">
  <div style="min-width:54px;color:#7e57c2;font-weight:700;">{md}</div>
  <div style="flex:1;font-size:0.9em;">{e["event"]}</div>
</div>'''
        html += f'''
<div style="background:#0f1623;border:1px solid #1e2d42;border-radius:14px;padding:16px;margin-bottom:16px;">
  <div style="font-weight:700;margin-bottom:4px;">🌙 天体イベント（相場アノマリー・参考）</div>
  <div style="font-size:0.75em;color:#7a8fa8;margin-bottom:10px;">満月・新月や水星逆行は科学的根拠は薄いものの、投資家心理として意識されることがあります</div>
  {merc}{rows}
</div>'''

    return html
