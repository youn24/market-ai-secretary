"""
note.com カバー画像生成モジュール
HTML/CSS → PNG（Playwright）でプロ品質のサムネイル(1200×630)を生成する。
2テーマ（cyan / gold）を日替わりで自動切替。
Playwright が使えない環境では matplotlib フォールバックに自動で切り替わる。
"""
import random
from datetime import date as _date
from src.utils import setup_logger, get_today_str, get_dirs

logger = setup_logger("note_cover")

# ── 出力サイズ（OGP標準） ─────────────────────────────────────
COVER_W, COVER_H = 1200, 630

# ── テーマ定義 ────────────────────────────────────────────────
THEMES = {
    "cyan": {
        "accent":  "#00d4ff", "accent2": "#7b61ff",
        "brand":   "DAILY REPORT",
        "bg": ("radial-gradient(110% 90% at 85% 8%, rgba(0,212,255,.18), transparent 52%),"
               "radial-gradient(100% 90% at 5% 105%, rgba(123,97,255,.16), transparent 55%),"
               "linear-gradient(160deg,#0b1018 0%,#090d14 50%,#070a10 100%)"),
        "grid":   "rgba(0,212,255,.04)",
        "text":   "#eaf6ff", "text2": "#aebccb", "text3": "#8194a8",
        "text4":  "#6b7d90", "date_dim": "#5a6b7e",
        "up": "#00e676", "down": "#ff5c6c",
        "fg_grad": "linear-gradient(90deg,#7b61ff,#00d4ff,#00e676)",
    },
    "gold": {
        "accent":  "#e8c474", "accent2": "#b8893c",
        "brand":   "MORNING BRIEF",
        "bg": ("radial-gradient(120% 90% at 82% 12%, rgba(232,196,116,.16), transparent 55%),"
               "radial-gradient(90% 80% at 8% 100%, rgba(232,196,116,.06), transparent 60%),"
               "linear-gradient(150deg,#0c0e14 0%,#0a0c12 45%,#08090e 100%)"),
        "grid":   "rgba(255,255,255,.025)",
        "text":   "#f4f1e8", "text2": "#c4bfae", "text3": "#9a9587",
        "text4":  "#7a7567", "date_dim": "#6b6759",
        "up": "#5fd38a", "down": "#ff6b7a",
        "fg_grad": "linear-gradient(90deg,#b8893c,#e8c474,#5fd38a)",
    },
}


# ── 判定（スコア → ラベル・絵文字・サブ文） ──────────────────────
def _verdict(score: float):
    if score >= 3:
        return "強気相場", "🚀", "市場は上昇ムード。リスクオンが鮮明で、<br>主要指数は揃って堅調な滑り出し。"
    if score >= 1:
        return "やや強気", "😊", "落ち着いた上昇基調。過熱感は乏しく、<br>買い安心感のある地合いです。"
    if score >= -1:
        return "中立・様子見", "😐", "方向感に乏しい横ばい展開。<br>材料待ちで様子見が優勢です。"
    if score >= -3:
        return "やや弱気", "😟", "下押し圧力がやや優勢。<br>無理せず慎重に見極めたい局面。"
    return "弱気相場", "😱", "リスクオフが鮮明。値動きが荒く、<br>守りを固めたい一日です。"


def _fg_label(v: float) -> str:
    if v >= 75: return "超強欲"
    if v >= 55: return "強欲"
    if v >= 45: return "中立"
    if v >= 25: return "恐怖"
    return "超恐怖"


def _pick_theme() -> str:
    """日付で安定・日替わりでランダムに見えるテーマ選択"""
    return random.Random(get_today_str()).choice(["cyan", "gold"])


# ── 価格整形 ──────────────────────────────────────────────────
def _price_rows(prices: dict, t: dict) -> str:
    items = [
        ("🇯🇵 日経平均", "^N225",    "{:,.0f}"),
        ("🇺🇸 S&P500",   "^GSPC",    "{:,.0f}"),
        ("💵 ドル円",     "USDJPY=X", "{:,.2f}"),
    ]
    rows = ""
    for name, sym, fmt in items:
        d   = prices.get(sym, {})
        v   = d.get("latest")
        chg = d.get("change_pct")
        if v is None:
            val_s, chg_s, c = "—", "", t["text3"]
        else:
            val_s = fmt.format(v)
            if chg is None:
                chg_s, c = "", t["text3"]
            else:
                c     = t["up"] if chg >= 0 else t["down"]
                arrow = "▲" if chg >= 0 else "▼"
                chg_s = f"{arrow} {abs(chg):.2f}%"
        rows += (
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:13px 0;border-bottom:1px solid rgba(255,255,255,.08);">'
            f'<span style="font-size:15px;color:{t["text2"]};font-weight:600;">{name}</span>'
            f'<span style="text-align:right;">'
            f'<span style="font-size:20px;font-weight:800;color:{t["text"]};font-variant-numeric:tabular-nums;">{val_s}</span>'
            f'<br><span style="font-size:14px;font-weight:700;color:{c};">{chg_s}</span></span>'
            f'</div>'
        )
    return rows


# ── HTML 組み立て ─────────────────────────────────────────────
def _build_html(prices: dict, risk: dict, fear_greed: dict, theme_name: str) -> str:
    t = THEMES[theme_name]

    score    = risk.get("score", 0)
    score_s  = f"+{score:.1f}" if score >= 0 else f"{score:.1f}"
    v_label, v_emoji, v_sub = _verdict(score)

    fg_score = float(fear_greed.get("score") or 50)
    fg_lbl   = _fg_label(fg_score)
    fg_c     = t["up"] if fg_score >= 55 else t["accent"] if fg_score >= 45 else t["down"]

    today_dt = _date.today()
    date_s   = today_dt.strftime("%Y.%m.%d")
    wd       = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"][today_dt.weekday()]

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{font-family:'Noto Sans JP','Noto Sans CJK JP','Hiragino Sans','Meiryo',sans-serif;}}
</style></head><body>
<div id="cover" style="position:relative;width:{COVER_W}px;height:{COVER_H}px;overflow:hidden;background:{t['bg']};">

  <!-- 微細グリッド -->
  <div style="position:absolute;inset:0;opacity:.45;
    background-image:linear-gradient({t['grid']} 1px,transparent 1px),linear-gradient(90deg,{t['grid']} 1px,transparent 1px);
    background-size:46px 46px;"></div>

  <!-- 上部アクセントライン -->
  <div style="position:absolute;top:0;left:0;right:0;height:6px;
    background:linear-gradient(90deg,{t['accent']},{t['accent2']} 65%,transparent);"></div>

  <!-- ブランドバー -->
  <div style="position:absolute;top:34px;left:54px;right:54px;display:flex;justify-content:space-between;align-items:center;">
    <div style="display:flex;align-items:center;gap:11px;">
      <span style="width:32px;height:32px;border-radius:9px;display:grid;place-items:center;font-size:17px;
        background:linear-gradient(135deg,{t['accent']},{t['accent2']});color:#070a10;font-weight:900;">M</span>
      <span style="font-size:19px;font-weight:800;color:{t['text']};letter-spacing:.04em;">市場AI秘書</span>
      <span style="font-size:13px;font-weight:700;color:{t['accent']};letter-spacing:.22em;
        border-left:1px solid {t['accent']}55;padding-left:12px;margin-left:4px;">{t['brand']}</span>
    </div>
    <span style="font-size:16px;color:{t['text3']};letter-spacing:.06em;font-weight:600;">
      {date_s} <span style="color:{t['date_dim']};">{wd}</span></span>
  </div>

  <!-- 左：エディトリアル -->
  <div style="position:absolute;left:54px;top:178px;width:55%;">
    <div style="font-size:16px;font-weight:700;color:{t['accent']};letter-spacing:.18em;margin-bottom:14px;">本日の判定</div>
    <div style="display:flex;align-items:baseline;gap:16px;">
      <span style="font-size:78px;line-height:.9;font-weight:900;color:{t['text']};letter-spacing:-.02em;">{v_label}</span>
      <span style="font-size:58px;">{v_emoji}</span>
    </div>
    <div style="font-size:21px;color:{t['text2']};margin-top:20px;line-height:1.55;font-weight:500;">{v_sub}</div>
    <div style="display:inline-flex;align-items:center;gap:13px;margin-top:28px;padding:11px 22px;border-radius:999px;
      background:{t['accent']}1a;border:1px solid {t['accent']}59;">
      <span style="font-size:15px;color:{t['text3']};font-weight:600;letter-spacing:.05em;">リスクスコア</span>
      <span style="font-size:26px;font-weight:900;color:{t['accent']};">{score_s}</span>
    </div>
  </div>

  <!-- 右：データパネル -->
  <div style="position:absolute;right:54px;top:172px;width:30%;">
    {_price_rows(prices, t)}
    <div style="margin-top:22px;">
      <div style="display:flex;justify-content:space-between;font-size:14px;color:{t['text3']};font-weight:600;margin-bottom:8px;">
        <span>Fear &amp; Greed</span><span style="color:{fg_c};font-weight:800;">{fg_score:.0f} {fg_lbl}</span></div>
      <div style="height:9px;border-radius:99px;background:rgba(255,255,255,.08);overflow:hidden;position:relative;">
        <div style="position:absolute;left:0;top:0;bottom:0;width:{fg_score:.0f}%;border-radius:99px;background:{t['fg_grad']};"></div>
      </div>
    </div>
  </div>

  <!-- フッター -->
  <div style="position:absolute;left:54px;right:54px;bottom:34px;display:flex;justify-content:space-between;align-items:center;
    border-top:1px solid rgba(255,255,255,.08);padding-top:14px;">
    <span style="font-size:14px;color:{t['text4']};letter-spacing:.04em;">🤖 Gemini AI × AI 3視点分析</span>
    <span style="font-size:14px;color:{t['accent']};font-weight:700;letter-spacing:.05em;">毎朝 7:30 自動配信</span>
  </div>
</div>
</body></html>"""


# ── Playwright で PNG 化（主経路） ────────────────────────────
def _render_with_playwright(html: str, out_path: str) -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("playwright 未インストール。matplotlibフォールバックを使用します")
        return False
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox"])
            page = browser.new_page(
                viewport={"width": COVER_W, "height": COVER_H},
                device_scale_factor=2,   # Retina 相当（2400×1260で生成→くっきり）
            )
            page.set_content(html, wait_until="networkidle")
            page.locator("#cover").screenshot(path=out_path)
            browser.close()
        return True
    except Exception as e:
        logger.warning(f"Playwright描画失敗（フォールバックへ）: {e}")
        return False


# ── matplotlib フォールバック（保険） ────────────────────────────
def _generate_matplotlib(prices, risk, fear_greed, theme_name, out_path) -> bool:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import FancyBboxPatch
        try:
            import japanize_matplotlib  # noqa: F401
        except ImportError:
            pass

        t = THEMES[theme_name]
        bg = "#0b1018" if theme_name == "cyan" else "#0c0e14"
        accent = t["accent"]
        score  = risk.get("score", 0)
        score_s = f"+{score:.1f}" if score >= 0 else f"{score:.1f}"
        v_label, v_emoji, _ = _verdict(score)
        fg_score = float(fear_greed.get("score") or 50)

        fig = plt.figure(figsize=(12.0, 6.3), facecolor=bg)
        ax  = fig.add_axes([0, 0, 1, 1], facecolor=bg)
        ax.set_xlim(0, 12); ax.set_ylim(0, 6.3); ax.axis("off")
        ax.add_patch(plt.Circle((11, 5.8), 2.4, color=accent, alpha=0.08, zorder=0))
        ax.axhline(y=6.15, xmin=0.02, xmax=0.7, color=accent, linewidth=2)
        ax.text(0.4, 5.85, "📊 市場AI秘書", fontsize=11, color=t["text3"], va="bottom", fontweight="bold")
        ax.text(0.4, 5.3, f"本日の判定：{v_label} {v_emoji}", fontsize=26, color=t["text"], va="top", fontweight="bold")
        ax.text(0.4, 4.5, f"リスクスコア {score_s}", fontsize=16, color=accent, va="top", fontweight="bold")

        ys = [3.6, 2.5, 1.4]
        rows = [("🇯🇵 日経平均", "^N225", "円"), ("🇺🇸 S&P500", "^GSPC", ""), ("💵 ドル円", "USDJPY=X", "円")]
        for y, (name, sym, unit) in zip(ys, rows):
            d = prices.get(sym, {}); v = d.get("latest"); chg = d.get("change_pct")
            ax.text(0.4, y, name, fontsize=12, color=t["text2"], va="center")
            if v is not None:
                ax.text(5.6, y, f"{v:,.2f}{unit}", fontsize=14, color=t["text"], va="center",
                        ha="right", fontweight="bold")
                if chg is not None:
                    c = t["up"] if chg >= 0 else t["down"]
                    ax.text(7.4, y, f"{'▲' if chg>=0 else '▼'} {abs(chg):.2f}%", fontsize=12,
                            color=c, va="center", ha="right", fontweight="bold")

        ax.text(0.4, 0.7, f"😱 Fear & Greed  {fg_score:.0f}", fontsize=12, color=t["text3"], va="center")
        ax.add_patch(FancyBboxPatch((4.2, 0.55), 7.4, 0.3, boxstyle="round,pad=0",
                                    facecolor="#ffffff", alpha=0.08, linewidth=0))
        ax.add_patch(FancyBboxPatch((4.2, 0.55), 7.4 * fg_score / 100, 0.3, boxstyle="round,pad=0",
                                    facecolor=accent, alpha=0.85, linewidth=0))
        fig.savefig(out_path, dpi=100, facecolor=bg, edgecolor="none")
        plt.close(fig)
        return True
    except Exception as e:
        logger.error(f"matplotlibフォールバックも失敗: {e}")
        return False


# ── エントリーポイント ────────────────────────────────────────
def generate(prices=None, risk=None, fear_greed=None) -> str:
    prices     = prices or {}
    risk       = risk or {"score": 0}
    fear_greed = fear_greed or {}

    theme_name = _pick_theme()
    out_path   = str(get_dirs()["reports"] / f"{get_today_str()}_note_cover.png")
    html       = _build_html(prices, risk, fear_greed, theme_name)

    if _render_with_playwright(html, out_path):
        logger.info(f"✅ note カバー画像生成（HTML/{theme_name}）: {out_path}")
        return out_path

    if _generate_matplotlib(prices, risk, fear_greed, theme_name, out_path):
        logger.info(f"✅ note カバー画像生成（matplotlib/{theme_name}）: {out_path}")
        return out_path

    return ""


def run(prices=None, risk=None, fear_greed=None) -> dict:
    result = {"available": False, "path": "", "theme": ""}
    try:
        path = generate(prices=prices, risk=risk, fear_greed=fear_greed)
        if path:
            result["available"] = True
            result["path"]      = path
            result["theme"]     = _pick_theme()
    except Exception as e:
        logger.error(f"note_cover run エラー: {e}")
        import traceback; logger.debug(traceback.format_exc())
    return result
