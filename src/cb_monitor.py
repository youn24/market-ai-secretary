"""
src/cb_monitor.py
中央銀行・為替介入監視モジュール（FX専用）
────────────────────────────────────────────
■ 機能
  1. 介入リスクゾーン判定 — USDJPY 水準 × 過去介入実績
  2. Google News RSS — 介入・口先介入・レートチェック関連ニュース取得
  3. IMM 投機筋ポジション要約テキスト生成
  4. すべて無料・APIキー不要
"""

import re
import warnings
import requests
from datetime import datetime, timezone, timedelta

warnings.filterwarnings("ignore")
JST = timezone(timedelta(hours=9))

# ─────────────────────────────────────────────────────────────────────────────
# 過去の主要為替介入実績（参考水準）
# ─────────────────────────────────────────────────────────────────────────────
_INTERVENTION_HISTORY = [
    {"date": "2022年9月",  "level": 145.90, "note": "22年ぶり円買い介入（3.6兆円）"},
    {"date": "2022年10月", "level": 151.94, "note": "最高値後に大規模3回介入（約9兆円）"},
    {"date": "2024年4月",  "level": 160.17, "note": "34年ぶり円安・日銀介入（約9兆円）"},
    {"date": "2024年7月",  "level": 161.70, "note": "追加介入（161円台で2回）"},
]

# 介入リスクゾーン（円安方向、USDJPY水準）
_RISK_ZONES = [
    (162.0, float("inf"), "🚨 超危険",  "超危険", 95),
    (158.0, 162.0,        "🔴 最高警戒", "最高警戒", 80),
    (153.0, 158.0,        "🟠 高警戒",  "高警戒",  60),
    (148.0, 153.0,        "🟡 警戒",    "警戒",    40),
    (143.0, 148.0,        "🔸 注意",    "注意",    20),
    (0.0,   143.0,        "🟢 安全圏",  "安全圏",   5),
]

# 口先介入・介入示唆フレーズ（ニュースに含まれると介入リスク UP）
_HOT_PHRASES = [
    "一方的な動き", "投機的な動き", "断固たる措置", "あらゆる手段",
    "秩序ある動き", "介入辞さず", "為替の安定", "急激な変動",
    "適切な措置", "高い緊張感", "必要な対応", "強い危機感",
    "為替水準を注視", "レートチェック",
]

# 検索クエリ（Google News RSS）
_NEWS_QUERIES = [
    "為替介入 OR 口先介入 OR レートチェック 財務省",
    "日銀 円安 為替 植田",
    "加藤 財務大臣 為替 円安",
]


# ─────────────────────────────────────────────────────────────────────────────
# 1. 介入リスク判定
# ─────────────────────────────────────────────────────────────────────────────

def calc_intervention_risk(usdjpy: float | None) -> dict:
    """
    USDJPY 水準から介入リスクレベルを算出
    Returns: {score, level, emoji, note, history_ref}
    """
    if usdjpy is None:
        return {"score": 0, "level": "🟢 安全圏", "emoji": "🟢",
                "note": "データなし", "history_ref": ""}

    # ゾーン判定
    score = 5
    level = "🟢 安全圏"
    emoji = "🟢"
    for lo, hi, lv, _, sc in _RISK_ZONES:
        if lo <= usdjpy < hi:
            score = sc
            level = lv
            emoji = lv[:2]
            break

    # 直近介入水準との距離
    history_ref = ""
    closest = min(_INTERVENTION_HISTORY, key=lambda x: abs(x["level"] - usdjpy))
    dist    = usdjpy - closest["level"]
    if abs(dist) < 10:
        direction = "上" if dist > 0 else "下"
        history_ref = (
            f"過去介入: {closest['date']} {closest['level']:.2f}円"
            f"（現在より{abs(dist):.1f}円{direction}）"
        )

    # ニュース検索でホットフレーズが見つかればスコアを+20
    note = _level_note(score)
    return {
        "score":       min(score, 100),
        "level":       level,
        "emoji":       emoji,
        "note":        note,
        "history_ref": history_ref,
        "usdjpy":      usdjpy,
    }


def _level_note(score: int) -> str:
    if score >= 80:
        return "介入が現実的なレベル。過去実績を踏まえ最大限の警戒が必要です"
    if score >= 60:
        return "要警戒。口先介入やレートチェックが実施される可能性があります"
    if score >= 40:
        return "注意水準。財務省の動向に注目が集まるレンジです"
    if score >= 20:
        return "介入警戒ゾーンに近づいています。財務省コメントに要注意"
    return "現時点で介入リスクは限定的です"


# ─────────────────────────────────────────────────────────────────────────────
# 2. 介入関連ニュース取得（Google News RSS）
# ─────────────────────────────────────────────────────────────────────────────

def fetch_intervention_news(max_items: int = 5) -> list:
    """
    Google News RSS から介入・口先介入・レートチェック関連ニュースを取得
    Returns: [{"title": str, "source": str, "hot": bool}, ...]
    """
    try:
        import feedparser
    except ImportError:
        return []

    seen   = set()
    result = []

    for q in _NEWS_QUERIES:
        try:
            url = (
                "https://news.google.com/rss/search?q="
                + requests.utils.quote(q)
                + "&hl=ja&gl=JP&ceid=JP:ja"
            )
            feed = feedparser.parse(url)
            for entry in feed.entries[:6]:
                title = entry.get("title", "").strip()
                if not title or title in seen:
                    continue
                seen.add(title)
                source = ""
                if " - " in title:
                    parts  = title.rsplit(" - ", 1)
                    title  = parts[0].strip()
                    source = parts[1].strip()
                # ホットフレーズ（口先介入示唆）チェック
                hot = any(p in title for p in _HOT_PHRASES)
                result.append({
                    "title":  title[:70],
                    "source": source[:25],
                    "hot":    hot,
                })
                if len(result) >= max_items:
                    return result
        except Exception:
            pass
    return result


def has_hot_phrase(news: list) -> bool:
    """ニュース一覧に口先介入示唆フレーズが含まれるか"""
    return any(n.get("hot") for n in news)


# ─────────────────────────────────────────────────────────────────────────────
# 3. 中央銀行動向テキスト生成
# ─────────────────────────────────────────────────────────────────────────────

def build_cb_monitor_text(data: dict | None = None) -> str:
    """
    中央銀行・為替介入監視テキストを返す（Telegram向け）
    data: fx_visual_report.fetch_all_data() の戻り値
    """
    data     = data or {}
    usdjpy   = data.get("USDJPY=X", {}).get("latest")
    risk     = calc_intervention_risk(usdjpy)
    news     = fetch_intervention_news()
    hot_news = has_hot_phrase(news)

    # スコアをニュースで補正
    score_adj = risk["score"]
    if hot_news:
        score_adj = min(score_adj + 20, 100)

    bar_n = round(score_adj / 10)
    bar   = "█" * bar_n + "░" * (10 - bar_n)

    lines = [
        "*🏛 中央銀行・為替介入監視*",
        "",
        f"🎯 *介入リスク温度*: {risk['level']}",
        f"`{bar}` {score_adj}/100",
    ]

    # USDJPY 水準と過去介入との比較
    if usdjpy:
        lines.append(f"💱 現在ドル円: `{usdjpy:.3f}円`")
    if risk["history_ref"]:
        lines.append(f"📌 {risk['history_ref']}")

    lines.append(f"💡 {risk['note']}")

    # ホットフレーズ発見時
    if hot_news:
        lines.append("⚠️ *口先介入・介入示唆フレーズを検出！*")

    # 過去の主要介入ポイント（参考）
    lines += [
        "",
        "*📋 過去の主要介入ポイント（参考水準）*",
    ]
    for h in _INTERVENTION_HISTORY:
        dist = (usdjpy - h["level"]) if usdjpy else 0
        dist_str = f"（現在より{abs(dist):.1f}円{'上' if dist > 0 else '下'}）" if usdjpy else ""
        lines.append(f"  • {h['date']} {h['level']:.2f}円 {dist_str}")
        lines.append(f"    └ {h['note']}")

    # 関連ニュース
    if news:
        lines += ["", "*📰 介入・口先介入関連ニュース*"]
        for n in news:
            hot_mark = " 🔥" if n["hot"] else ""
            src      = f" ({n['source']})" if n["source"] else ""
            lines.append(f"  🔹 {n['title']}{src}{hot_mark}")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# 4. IMM 投機筋ポジション要約テキスト
# ─────────────────────────────────────────────────────────────────────────────

def build_imm_summary_text(premium: dict | None = None) -> str:
    """
    CFTC IMM 投機筋円ポジション要約テキスト（Telegram向け）
    premium: fx_data_premium.fetch_all_premium() の戻り値
    """
    cftc = (premium or {}).get("cftc_jpy", {})

    if not cftc or not cftc.get("dates"):
        return (
            "*📊 IMM 投機筋ポジション（円）*\n"
            "  データ取得中（毎週金曜夜に CFTC 更新）"
        )

    dates   = cftc["dates"]
    net_raw = cftc["net"]
    latest  = cftc["latest_net"] / 1000     # 千枚に変換
    latest_date = cftc.get("latest_date", dates[-1])

    # 前週比
    prev = (net_raw[-2] / 1000) if len(net_raw) >= 2 else None
    chg  = (latest - prev) if prev is not None else None

    # 方向・水準判定
    if latest < -100:
        direction = "🔴 極端な円売り越し（介入リスク増）"
        icon      = "🔴"
    elif latest < -70:
        direction = "🟠 大幅円売り越し（警戒水準）"
        icon      = "🟠"
    elif latest < -40:
        direction = "🟡 円売り越し（注意）"
        icon      = "🟡"
    elif latest < 0:
        direction = "🔸 小幅円売り越し"
        icon      = "🔸"
    elif latest < 40:
        direction = "🔹 小幅円買い越し"
        icon      = "🔹"
    else:
        direction = "🟢 大幅円買い越し（円高圧力）"
        icon      = "🟢"

    # 前週比テキスト
    chg_str = ""
    if chg is not None:
        chg_arrow = "▲" if chg > 0 else "▼"
        chg_label = "円買い方向" if chg > 0 else "円売り方向"
        chg_str   = f"  前週比: {chg_arrow}{abs(chg):.1f}千枚（{chg_label}）"

    date_str = str(latest_date)[-5:] if len(str(latest_date)) >= 5 else str(latest_date)

    lines = [
        "*📊 IMM 投機筋ポジション（円）*",
        f"  {icon} ネットポジション: `{latest:+.1f}千枚`（{date_str}時点）",
        f"  {direction}",
    ]
    if chg_str:
        lines.append(chg_str)

    lines += [
        "  ──────────────────",
        "  💡 IMM = 先物市場の投機的ポジション",
        "     マイナスが大きいほど「円売り」が積み上がっており",
        "     巻き戻し（円買い）が起きると円高に動きやすい",
    ]

    return "\n".join(lines)
