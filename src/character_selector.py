"""
src/character_selector.py
相場状況に応じてキャラクター画像を自動選択・切り出しするモジュール

■ キャラクターグリッド (4列 × 9行 = 36枚)
  assets/characters_grid.png に保存すること

■ レイアウト（上から）
  Row 0-1: カワウソちゃん (8枚) — 短期・FX向き
  Row 2-8: ガネーシャ象くん (28枚) — 中長期・総合分析向き

■ 列の感情マッピング (各行共通)
  Col 0: アイデア・分析中
  Col 1: 驚き・重大ニュース
  Col 2: 疑問・不確実
  Col 3: 落ち着いた分析・執筆中
"""

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import matplotlib.image as mpimg
import numpy as np
from pathlib import Path
import os
import traceback

GRID_PATH = Path(__file__).parent.parent / "assets" / "characters_grid.png"

# ─── キャラクターグリッド定義 ─────────────────────────────────────────────────
# (row, col) → 意味
CHARACTER_MAP = {
    # カワウソちゃん (Row 0-1)
    (0, 0): {"name": "カワウソ_アイデア",   "mood": "bullish",   "desc": "💡 アイデア発見！"},
    (0, 1): {"name": "カワウソ_急落ショック","mood": "crash",     "desc": "😱 急落！"},
    (0, 2): {"name": "カワウソ_様子見",      "mood": "neutral",   "desc": "😐 様子見"},
    (0, 3): {"name": "カワウソ_雨天分析",    "mood": "bearish",   "desc": "☔ 慎重に"},
    (1, 0): {"name": "カワウソ_強気",        "mood": "bullish",   "desc": "🎉 強気！"},
    (1, 1): {"name": "カワウソ_画面ショック","mood": "volatile",  "desc": "🖥 急変！"},
    (1, 2): {"name": "カワウソ_疑問",        "mood": "uncertain", "desc": "❓ 不確実"},
    (1, 3): {"name": "カワウソ_ノート分析",  "mood": "analyzing", "desc": "📝 分析中"},
    # ガネーシャ象くん (Row 2-8)
    (2, 0): {"name": "象_目標達成",          "mood": "bullish",   "desc": "🎯 目標達成！"},
    (2, 1): {"name": "象_急変警戒",          "mood": "volatile",  "desc": "⚡ 急変注意"},
    (2, 2): {"name": "象_プレゼン強気",      "mood": "bullish",   "desc": "📊 強気分析"},
    (2, 3): {"name": "象_チャート分析",      "mood": "analyzing", "desc": "📈 チャート確認"},
    (3, 0): {"name": "象_指差しOK",          "mood": "bullish",   "desc": "👆 注目！"},
    (3, 1): {"name": "象_市場低迷嘆き",      "mood": "bearish",   "desc": "😔 低迷..."},
    (3, 2): {"name": "象_損失ショック",      "mood": "crash",     "desc": "📉 損失警告"},
    (3, 3): {"name": "象_リスク防衛",        "mood": "defensive", "desc": "🛡 防衛モード"},
    (4, 0): {"name": "象_ローソク足分析",    "mood": "analyzing", "desc": "🕯 テクニカル分析"},
    (4, 1): {"name": "象_急騰興奮",          "mood": "bullish",   "desc": "🚀 急騰！"},
    (4, 2): {"name": "象_急落ショック",      "mood": "crash",     "desc": "💥 急落警報"},
    (4, 3): {"name": "象_強気ジャンプ",      "mood": "bullish",   "desc": "🏆 勝利！"},
    (5, 0): {"name": "象_分析指差し",        "mood": "analyzing", "desc": "🔍 分析"},
    (5, 1): {"name": "象_注目呼びかけ",      "mood": "alert",     "desc": "📢 注目！"},
    (5, 2): {"name": "象_上昇喜び",          "mood": "bullish",   "desc": "🎊 上昇！"},
    (5, 3): {"name": "象_勝利ガッツポーズ",  "mood": "bullish",   "desc": "✊ 強気！"},
    (6, 0): {"name": "象_ボード説明",        "mood": "analyzing", "desc": "📋 解説"},
    (6, 1): {"name": "象_直立説明",          "mood": "neutral",   "desc": "📝 説明"},
    (6, 2): {"name": "象_上昇チャート喜び",  "mood": "bullish",   "desc": "📈 上昇継続"},
    (6, 3): {"name": "象_リスク警戒ボード",  "mood": "defensive", "desc": "⚠️ リスク注意"},
    (7, 0): {"name": "象_急落悲しむ",        "mood": "bearish",   "desc": "😢 下落"},
    (7, 1): {"name": "象_下落チャート",      "mood": "bearish",   "desc": "📉 下落"},
    (7, 2): {"name": "カワウソ_ノート確認",  "mood": "analyzing", "desc": "📋 確認中"},
    (7, 3): {"name": "象_小さい強気",        "mood": "bullish",   "desc": "💪 強気"},
    (8, 0): {"name": "象_コイン集め",        "mood": "bullish",   "desc": "💰 利益！"},
    (8, 1): {"name": "カワウソ_ほのぼの",    "mood": "neutral",   "desc": "😊 安定"},
    (8, 2): {"name": "象_笑顔",              "mood": "bullish",   "desc": "😊 良好"},
    (8, 3): {"name": "カワウソ_ポーズ",      "mood": "neutral",   "desc": "👌 OK"},
}

# ─── 相場状況 → キャラクター選択ルール ───────────────────────────────────────
MOOD_TO_CHARS = {
    "bullish":   [(1, 0), (2, 0), (4, 3), (5, 2), (5, 3), (6, 2), (8, 0)],
    "bearish":   [(0, 3), (3, 1), (7, 0), (7, 1)],
    "crash":     [(0, 1), (3, 2), (4, 2)],
    "volatile":  [(0, 1), (1, 1), (2, 1), (4, 2)],
    "uncertain": [(0, 2), (1, 2)],
    "analyzing": [(0, 0), (1, 3), (2, 3), (4, 0), (5, 0), (6, 0), (7, 2)],
    "neutral":   [(0, 2), (6, 1), (8, 1), (8, 3)],
    "defensive": [(3, 3), (6, 3)],
    "alert":     [(5, 1)],
}


def determine_market_mood(usdjpy_chg: float, vix: float, rsi: float | None = None) -> str:
    """
    市場データから現在のムードを判定する

    Args:
        usdjpy_chg: USD/JPY 前日比変化率(%)
        vix       : VIX 指数
        rsi       : RSI(14) 値（任意）

    Returns:
        mood 文字列（bullish / bearish / crash / volatile / analyzing 等）
    """
    # 急変・クラッシュ判定
    if abs(usdjpy_chg) >= 1.5 or vix >= 35:
        if usdjpy_chg < -1.5:
            return "crash"
        return "volatile"

    # RSI 過熱・売られすぎ
    if rsi is not None:
        if rsi >= 75:
            return "defensive"   # 過熱 → 守り
        if rsi <= 25:
            return "bullish"     # 売られすぎ → 反発期待

    # VIX 水準
    if vix >= 25:
        return "defensive"
    if vix >= 20:
        return "uncertain"

    # 上昇・下落トレンド
    if usdjpy_chg >= 0.5:
        return "bullish"
    if usdjpy_chg <= -0.5:
        return "bearish"

    # それ以外
    return "analyzing"


def crop_character(row: int, col: int, out_path: str,
                   n_rows: int = 9, n_cols: int = 4) -> bool:
    """
    グリッド画像から 1 キャラクターを切り出して保存する

    Args:
        row, col  : グリッド座標 (0-origin)
        out_path  : 保存先 PNG パス
        n_rows    : グリッド行数（デフォルト9）
        n_cols    : グリッド列数（デフォルト4）

    Returns:
        True if successful
    """
    if not GRID_PATH.exists():
        return False
    try:
        img    = mpimg.imread(str(GRID_PATH))
        h, w   = img.shape[:2]
        cell_h = h // n_rows
        cell_w = w // n_cols

        y1 = row * cell_h
        y2 = y1 + cell_h
        x1 = col * cell_w
        x2 = x1 + cell_w

        cell = img[y1:y2, x1:x2]

        fig, ax = plt.subplots(1, 1, figsize=(2, 2), facecolor="none")
        ax.imshow(cell)
        ax.axis("off")
        plt.savefig(out_path, dpi=120, bbox_inches="tight",
                    transparent=True, facecolor="none")
        plt.close(fig)
        return True
    except Exception:
        return False


def get_character_for_market(
    usdjpy_chg: float,
    vix: float,
    rsi: float | None = None,
    out_dir: str = "data/fx_charts",
) -> dict:
    """
    相場状況から最適なキャラクターを選んで切り出す

    Returns:
        dict with keys: mood, desc, path (or None), row, col, available
    """
    import random
    from pathlib import Path

    mood    = determine_market_mood(usdjpy_chg, vix, rsi)
    choices = MOOD_TO_CHARS.get(mood, MOOD_TO_CHARS["analyzing"])
    row, col = random.choice(choices)
    info     = CHARACTER_MAP.get((row, col), {})

    result = {
        "available": False,
        "mood":      mood,
        "desc":      info.get("desc", ""),
        "name":      info.get("name", ""),
        "row":       row,
        "col":       col,
        "path":      None,
    }

    # グリッド画像がある場合は切り出す
    if GRID_PATH.exists():
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        out_path = str(Path(out_dir) / f"character_{mood}_{row}_{col}.png")
        if crop_character(row, col, out_path):
            result["available"] = True
            result["path"]      = out_path

    return result


def get_mood_emoji(mood: str) -> str:
    """ムードに対応するテキスト絵文字を返す（画像なし時の代替）"""
    return {
        "bullish":   "🐘✨",
        "bearish":   "🦦😔",
        "crash":     "🦦😱",
        "volatile":  "🐘⚡",
        "uncertain": "🦦❓",
        "analyzing": "🐘📊",
        "neutral":   "🦦😊",
        "defensive": "🐘🛡",
        "alert":     "🐘📢",
    }.get(mood, "🐘")
