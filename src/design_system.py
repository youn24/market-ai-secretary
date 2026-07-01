"""
デザインシステム（市場AI秘書の唯一の見た目の真実）

各モジュールが色や余白を個別にハードコードしていた問題を解消し、
全出力（HTMLレポート・Telegram画像・チャート）を一つのデザイン言語に統一する。

含むもの:
  - デザイントークン: 2テーマ（dark=データ・ターミナル / warm=マガジン）
  - 意味色: 上昇=緑 / 下落=赤 / 警戒=琥珀 / 情報=青 を全モジュール共通化
  - 再利用HTML部品: card / stat / badge / section_header / data_table /
                    sparkline / confidence_pill / divider / up_down
  - chart_theme(): Chart.js 共通配色  / mpl_style(): matplotlib 共通スタイル

設計原則（プロのデザイン規範）:
  - 視覚階層は1画面に主役1つ・余白の呼吸・アクセント1色・data-ink比重視
  - iPhone幅(≤540px)最優先・初心者でも一目でわかる可読性
  - 信頼度をデザイン言語に: 高=実線濃 / 中=細枠 / 低=点線淡＋「要確認」

依存なし（純Python・文字列生成のみ）。
"""

# ── デザイントークン ─────────────────────────────────────────────────
THEMES = {
    "dark": {
        "bg":          "#0d1117",
        "surface":     "#161b22",
        "surface2":    "#0f1623",
        "border":      "#1e2d42",
        "border_soft": "#21262d",
        "text":        "#e6edf3",
        "text_muted":  "#9fb4d4",
        "text_dim":    "#7a8fa8",
        "text_faint":  "#5a6b82",
        "accent":      "#58a6ff",
        "up":          "#3fb950",
        "up_soft":     "rgba(63,185,80,.10)",
        "down":        "#f85149",
        "down_soft":   "rgba(248,81,73,.10)",
        "warn":        "#d29922",
        "info":        "#58a6ff",
        "neutral":     "#8aa0c0",
        "font":        '"Hiragino Sans","Yu Gothic","Meiryo",-apple-system,sans-serif',
        "shadow":      "0 1px 3px rgba(0,0,0,.35)",
    },
    "warm": {
        "bg":          "#f4e8cc",
        "surface":     "#fffdf6",
        "surface2":    "#faf3e0",
        "border":      "#e6d4a8",
        "border_soft": "#ede0bd",
        "text":        "#4a3b22",
        "text_muted":  "#8a7550",
        "text_dim":    "#a8946a",
        "text_faint":  "#bфа",  # placeholder fixed below
        "accent":      "#9c6b2f",
        "up":          "#2f9e4f",
        "up_soft":     "rgba(47,158,79,.10)",
        "down":        "#d8483d",
        "down_soft":   "rgba(216,72,61,.10)",
        "warn":        "#c79a3a",
        "info":        "#3b6db3",
        "neutral":     "#8a7550",
        "font":        '"Hiragino Maru Gothic ProN","Hiragino Sans","Yu Gothic","Meiryo",sans-serif',
        "shadow":      "0 1px 3px rgba(140,110,60,.12)",
    },
}
THEMES["warm"]["text_faint"] = "#b6a47a"

# 余白リズム（8px系）・角丸
SPACE = {"xs": "4px", "sm": "8px", "md": "12px", "lg": "16px", "xl": "24px"}
RADIUS = {"sm": "8px", "md": "10px", "lg": "14px", "pill": "20px"}

# 信頼度の見た目（精度をデザイン言語に変換）
_CONFIDENCE = {
    "high": {"label": "信頼度 高", "icon": "🟢", "border": "solid",  "alpha": "1"},
    "mid":  {"label": "信頼度 中", "icon": "🟡", "border": "solid",  "alpha": ".85"},
    "low":  {"label": "信頼度 低", "icon": "⚪", "border": "dashed", "alpha": ".6"},
}


def get_theme(name: str = "dark") -> dict:
    return THEMES.get(name, THEMES["dark"])


# ── 基本ヘルパ ───────────────────────────────────────────────────────
def fmt_num(v, dp: int = 0, unit: str = "") -> str:
    if v is None:
        return "—"
    try:
        if dp == 0:
            return f"{unit}{v:,.0f}"
        return f"{unit}{v:,.{dp}f}"
    except (ValueError, TypeError):
        return str(v)


def sem_color(theme: dict, chg) -> str:
    """騰落→意味色（上昇=緑 / 下落=赤 / 0近傍=中立）"""
    if chg is None:
        return theme["neutral"]
    if chg > 0:
        return theme["up"]
    if chg < 0:
        return theme["down"]
    return theme["neutral"]


def up_down(chg, theme=None, size: str = "13px", with_arrow: bool = True) -> str:
    """+/-% を色・矢印つきで（最頻出の表示部品）"""
    theme = theme or get_theme()
    if chg is None:
        return f'<span style="color:{theme["text_dim"]};font-size:{size};">—</span>'
    c = sem_color(theme, chg)
    arrow = ("▲" if chg >= 0 else "▼") if with_arrow else ""
    sign = "+" if chg >= 0 else ""
    return f'<span style="color:{c};font-size:{size};font-weight:700;">{arrow}{sign}{chg:.2f}%</span>'


# ── UI部品（HTML文字列を返す） ───────────────────────────────────────
def card(body_html: str, theme=None, accent: str = None, pad: str = "14px",
         radius: str = None) -> str:
    """サーフェスカード。accent指定で左ボーダー強調"""
    theme = theme or get_theme()
    radius = radius or RADIUS["lg"]
    border_left = (f"border-left:3px solid {accent};border-radius:0 {radius} {radius} 0;"
                   if accent else f"border-radius:{radius};")
    return (f'<div style="background:{theme["surface"]};border:1px solid {theme["border"]};'
            f'{border_left}padding:{pad};box-shadow:{theme["shadow"]};">{body_html}</div>')


def stat(label: str, value: str, sub: str = "", color: str = None,
         theme=None, min_w: str = "120px") -> str:
    """指標チップ（ラベル・大きな値・小さな補足）"""
    theme = theme or get_theme()
    color = color or theme["text"]
    sub_html = (f'<div style="font-size:0.66em;color:{theme["text_dim"]};margin-top:2px;'
                f'line-height:1.35;">{sub}</div>') if sub else ""
    return (f'<div style="flex:1;min-width:{min_w};background:{theme["surface2"]};'
            f'border:1px solid {theme["border"]};border-radius:{RADIUS["md"]};padding:11px 13px;">'
            f'<div style="font-size:0.7em;color:{theme["text_dim"]};">{label}</div>'
            f'<div style="font-size:1.25em;font-weight:800;color:{color};margin-top:2px;">{value}</div>'
            f'{sub_html}</div>')


def badge(text: str, kind: str = "neutral", theme=None) -> str:
    """意味色つきピル（kind: up/down/warn/info/neutral または任意の色）"""
    theme = theme or get_theme()
    c = theme.get(kind, kind if str(kind).startswith("#") else theme["neutral"])
    return (f'<span style="display:inline-flex;align-items:center;gap:4px;padding:2px 10px;'
            f'border-radius:{RADIUS["pill"]};font-size:0.7em;font-weight:700;'
            f'background:{c}1f;color:{c};white-space:nowrap;">{text}</span>')


def section_header(title: str, icon: str = "", tag: str = "", theme=None) -> str:
    """セクション見出し（アイコン＋タイトル＋任意タグ）"""
    theme = theme or get_theme()
    tag_html = badge(tag, "info", theme) if tag else ""
    icon_html = f'<span style="font-size:1.05em;">{icon}</span>' if icon else ""
    return (f'<div style="display:flex;align-items:center;gap:8px;margin:18px 0 10px;">'
            f'{icon_html}<span style="font-size:1.0em;font-weight:800;color:{theme["text"]};">{title}</span>'
            f'{tag_html}</div>')


def confidence_pill(level: str, theme=None, note: str = "") -> str:
    """信頼度ピル。level: high/mid/low。低いほど淡く点線＋要確認"""
    theme = theme or get_theme()
    cfg = _CONFIDENCE.get(level, _CONFIDENCE["mid"])
    c = {"high": theme["up"], "mid": theme["warn"], "low": theme["text_dim"]}[level if level in _CONFIDENCE else "mid"]
    extra = f' ・ {note}' if note else ""
    return (f'<span style="display:inline-flex;align-items:center;gap:4px;padding:2px 9px;'
            f'border-radius:{RADIUS["pill"]};font-size:0.68em;font-weight:700;color:{c};'
            f'border:1px {cfg["border"]} {c};opacity:{cfg["alpha"]};white-space:nowrap;">'
            f'{cfg["icon"]} {cfg["label"]}{extra}</span>')


def needs_check(theme=None) -> str:
    """データ異常時の「⚠️要確認」マーク"""
    theme = theme or get_theme()
    return (f'<span style="color:{theme["warn"]};font-size:0.72em;font-weight:700;">⚠️ 要確認</span>')


def divider(theme=None, margin: str = "12px 0") -> str:
    theme = theme or get_theme()
    return f'<div style="height:1px;background:{theme["border"]};margin:{margin};"></div>'


def data_table(headers: list, rows: list, theme=None, align=None) -> str:
    """表（headers: [str], rows: [[cell_html or (text,color)]]）"""
    theme = theme or get_theme()
    align = align or (["left"] + ["right"] * (len(headers) - 1))
    thead = "".join(
        f'<th style="padding:7px 10px;text-align:{align[i]};font-size:0.7em;'
        f'color:{theme["text_dim"]};font-weight:700;">{h}</th>'
        for i, h in enumerate(headers))
    body = ""
    for row in rows:
        tds = ""
        for i, cell in enumerate(row):
            if isinstance(cell, (tuple, list)):
                txt, col = cell[0], cell[1]
            else:
                txt, col = cell, theme["text"]
            weight = "800" if i == 0 else "700"
            tds += (f'<td style="padding:9px 10px;text-align:{align[i]};color:{col};'
                    f'font-weight:{weight};border-bottom:1px solid {theme["border_soft"]};'
                    f'font-variant-numeric:tabular-nums;">{txt}</td>')
        body += f"<tr>{tds}</tr>"
    return (f'<div style="background:{theme["surface"]};border:1px solid {theme["border"]};'
            f'border-radius:{RADIUS["lg"]};overflow:hidden;box-shadow:{theme["shadow"]};">'
            f'<table style="width:100%;border-collapse:collapse;font-size:0.9em;">'
            f'<thead><tr style="background:{theme["surface2"]};">{thead}</tr></thead>'
            f'<tbody>{body}</tbody></table></div>')


def sparkline(values: list, color: str = None, theme=None,
              width: int = 90, height: int = 26) -> str:
    """インラインSVGスパークライン"""
    theme = theme or get_theme()
    vals = [v for v in (values or []) if isinstance(v, (int, float))]
    if len(vals) < 2:
        return ""
    color = color or (theme["up"] if vals[-1] >= vals[0] else theme["down"])
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    n = len(vals)
    pts = " ".join(
        f"{round(i / (n - 1) * width, 1)},{round(height - (v - lo) / rng * (height - 4) - 2, 1)}"
        for i, v in enumerate(vals))
    return (f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
            f'style="vertical-align:middle;"><polyline points="{pts}" fill="none" '
            f'stroke="{color}" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/></svg>')


def page_wrap(inner_html: str, theme_name: str = "dark", max_w: str = "540px") -> str:
    """テーマ背景つきのページラッパ（プレビュー/単体出力用）"""
    t = get_theme(theme_name)
    return (f'<div style="background:{t["bg"]};color:{t["text"]};font-family:{t["font"]};'
            f'padding:16px;max-width:{max_w};margin:0 auto;-webkit-font-smoothing:antialiased;">'
            f'{inner_html}</div>')


# ── Chart.js 共通テーマ ──────────────────────────────────────────────
def chart_theme(theme_name: str = "dark") -> dict:
    """Chart.js の options に使う共通配色。JSON化してそのまま埋め込み可"""
    t = get_theme(theme_name)
    return {
        "grid":   "rgba(255,255,255,.05)" if theme_name == "dark" else "rgba(120,90,40,.08)",
        "ticks":  t["text_dim"],
        "legend": t["text_muted"],
        "palette": [t["accent"], t["warn"], t["up"], t["down"], "#a371f7", "#e8a0c0"],
        "up": t["up"], "down": t["down"], "neutral": t["neutral"],
    }


# ── matplotlib 共通スタイル（Telegram画像用） ───────────────────────
def mpl_style(theme_name: str = "dark") -> dict:
    """matplotlib rcParams 風の色セット。summary_card 等で使用"""
    t = get_theme(theme_name)
    return {
        "bg": t["bg"], "surface": t["surface"], "surface2": t["surface2"],
        "border": t["border"], "text": t["text"], "muted": t["text_muted"],
        "dim": t["text_dim"], "up": t["up"], "down": t["down"],
        "warn": t["warn"], "info": t["info"], "accent": t["accent"],
        "font_family": ["Noto Sans CJK JP", "IPAexGothic", "Hiragino Sans",
                        "Meiryo", "Yu Gothic", "sans-serif"],
    }


if __name__ == "__main__":
    # 両テーマで全部品を並べたプレビューHTMLを出力
    def showcase(theme_name):
        t = get_theme(theme_name)
        parts = [section_header("デザインシステム プレビュー", "🎨", theme_name.upper(), t)]
        # stat 行
        chips = (stat("日経平均", "39,500", "▲+1.55%", t["up"], t)
                 + stat("S&P500", "5,600", "▼-0.40%", t["down"], t)
                 + stat("信頼度", "中", "ソース一致", t["warn"], t))
        parts.append(f'<div style="display:flex;gap:8px;flex-wrap:wrap;">{chips}</div>')
        # badges + confidence
        parts.append(f'<div style="margin-top:12px;display:flex;gap:6px;flex-wrap:wrap;">'
                     f'{badge("上昇","up",t)}{badge("下落","down",t)}{badge("警戒","warn",t)}'
                     f'{confidence_pill("high",t)}{confidence_pill("low",t,"データ要確認")}'
                     f'{needs_check(t)}</div>')
        # table
        parts.append("<div style='margin-top:12px;'>" + data_table(
            ["指数", "現在値", "騰落率"],
            [["日経225", "39,500", ("+1.55%", t["up"])],
             ["S&P500", "5,600", ("-0.40%", t["down"])]], t) + "</div>")
        # sparkline in card
        sp = sparkline([1, 3, 2, 5, 4, 6, 5, 8], theme=t)
        parts.append("<div style='margin-top:12px;'>" + card(
            f'<div style="display:flex;align-items:center;justify-content:space-between;">'
            f'<span>直近トレンド</span>{sp}</div>', t, accent=t["accent"]) + "</div>")
        return page_wrap("".join(parts), theme_name)

    html = ("<div style='display:flex;gap:16px;flex-wrap:wrap;background:#222;padding:16px;'>"
            + showcase("dark") + showcase("warm") + "</div>")
    with open("design_preview.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("design_preview.html を出力しました")
