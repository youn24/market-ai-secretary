"""
AIキャラクター解説モジュール
AIガネーシャ（知恵の象の神）とAIカワウソが市場を解説する。

【画像スプライトシート仕様】
  ファイル: src/assets/characters.png
  グリッド: 4列 × 9行 = 36コマ
  上段(行0-2): カワウソ
  下段(行2-8): ガネーシャ

  カワウソ配置:
    (col=0,row=0): 調査・ルーペ           → neutral/analytical
    (col=1,row=0): アラーム・赤い稲妻      → crisis
    (col=2,row=0): ハッピー・チャート上昇  → bull
    (col=3,row=0): 悲しい・お金袋          → bear
    (col=0,row=1): 大興奮・バンザイ        → strong_bull
    (col=1,row=1): ショック・モニター前    → crash
    (col=2,row=1): 困惑・？マーク          → fear/uncertain
    (col=3,row=1): 勉強中・ノート分析      → neutral
    (col=0,row=2): 集中・ターゲット        → analytical
    (col=1,row=2): 怖い・上下チャート      → volatile

  ガネーシャ配置:
    (col=2,row=2): 発表・緑チャート        → bull
    (col=3,row=2): コイン・好調            → very_bull
    (col=0,row=3): 説明・指差し            → neutral
    (col=1,row=3): 心配・不安              → fear
    (col=2,row=3): 損失・落ち込み          → bear
    (col=3,row=3): 防御・シールド警告      → cautious
    (col=0,row=4): ロウソク足分析          → analytical
    (col=1,row=4): 強気・指さし上           → bull
    (col=2,row=4): ショック・赤い稲妻       → crisis
    (col=3,row=4): 大喜び・お祝い           → strong_bull
    (col=0,row=5): ターゲット・目標         → goal
    (col=1,row=5): ボード説明              → neutral
    (col=2,row=5): 喜び・お祝い2           → bull
    (col=3,row=5): 超喜び                  → strong_bull
    (col=0,row=6): 勉強・分析中            → analytical
    (col=1,row=6): ホワイトボード          → presenting
    (col=2,row=6): メモ・記録              → research
    (col=3,row=6): 警告シールド            → cautious
    (col=0,row=7): 悲しい・赤い矢印        → bear/crash
    (col=1,row=7): ニュートラル立ち姿      → neutral
    (col=3,row=7): 成長・上昇              → bull
    (col=0,row=8): コイン・繁栄            → wealth/bull

ガネーシャ: 格調高く・深い分析（〜じゃ / 〜ですぞ / 〜であります）
カワウソ: かわいく・中学生でもわかる言葉で（〜だよ〜！ / 〜なの〜♪）
"""
import os
import base64
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ── スプライトシート設定 ──────────────────────────────────────────
SPRITE_PATH = Path(__file__).parent / "assets" / "characters.png"
SPRITE_COLS = 4
SPRITE_ROWS = 9

# ── 気分マッピング（相場状況 → スプライト座標） ───────────────────
# カワウソ: mood → (col, row)
OTTER_MOOD_MAP = {
    "crisis":      (1, 1),   # ショック・モニター前
    "bear":        (3, 0),   # 悲しい・お金袋
    "fear":        (2, 1),   # 困惑・？マーク
    "neutral":     (3, 1),   # 勉強中・ノート
    "bull":        (2, 0),   # ハッピー・チャート上昇
    "strong_bull": (0, 1),   # 大興奮・バンザイ
    "analytical":  (0, 0),   # 調査・ルーペ
    "volatile":    (1, 2),   # 怖い・上下チャート
}

# ガネーシャ: mood → (col, row)
GANESHA_MOOD_MAP = {
    "crisis":      (2, 4),   # ショック・赤い稲妻
    "bear":        (2, 3),   # 損失・落ち込み
    "fear":        (1, 3),   # 心配・不安
    "neutral":     (1, 5),   # ボード説明
    "bull":        (1, 4),   # 強気・指さし上
    "strong_bull": (3, 4),   # 大喜び・お祝い
    "cautious":    (3, 3),   # 防御・シールド
    "analytical":  (0, 4),   # ロウソク足分析
}


def _get_mood(risk_score: float, vix: float) -> str:
    """相場状況 → 気分ラベル"""
    if vix >= 35 or risk_score <= -3:
        return "crisis"
    elif risk_score <= -2 or (vix >= 28 and risk_score < -1):
        return "bear"
    elif risk_score <= -0.5 or vix >= 22:
        return "fear"
    elif risk_score >= 2:
        return "strong_bull"
    elif risk_score >= 0.5:
        return "bull"
    else:
        return "neutral"


def _load_sprite_b64() -> str | None:
    """スプライトシートをbase64で読み込む"""
    if not SPRITE_PATH.exists():
        return None
    try:
        with open(SPRITE_PATH, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception as e:
        logger.warning(f"スプライト読み込み失敗: {e}")
        return None


def _sprite_div(col: int, row: int, b64: str, size: int = 120) -> str:
    """CSSスプライトでキャラクター1コマを表示するdivを生成"""
    # background-size: cols*100% rows*100% でグリッドを拡大
    # background-position: col/(cols-1)*100% row/(rows-1)*100%
    x_pct = col * 100 / (SPRITE_COLS - 1) if SPRITE_COLS > 1 else 0
    y_pct = row * 100 / (SPRITE_ROWS - 1) if SPRITE_ROWS > 1 else 0
    bg_size_x = SPRITE_COLS * 100
    bg_size_y = SPRITE_ROWS * 100
    return (
        f'<div style="'
        f'width:{size}px;height:{size}px;'
        f'background-image:url(\'data:image/png;base64,{b64}\');'
        f'background-size:{bg_size_x}% {bg_size_y}%;'
        f'background-position:{x_pct:.2f}% {y_pct:.2f}%;'
        f'background-repeat:no-repeat;'
        f'border-radius:12px;'
        f'overflow:hidden;'
        f'flex-shrink:0;'
        f'"></div>'
    )


# ── SVGフォールバック（画像がない場合） ──────────────────────────
GANESHA_SVG = """<svg width="90" height="110" viewBox="0 0 100 120" xmlns="http://www.w3.org/2000/svg">
  <ellipse cx="18" cy="52" rx="17" ry="23" fill="#FFBF00" stroke="#E6A800" stroke-width="1.5"/>
  <ellipse cx="82" cy="52" rx="17" ry="23" fill="#FFBF00" stroke="#E6A800" stroke-width="1.5"/>
  <ellipse cx="18" cy="52" rx="11" ry="16" fill="#FFD6DC" opacity="0.75"/>
  <ellipse cx="82" cy="52" rx="11" ry="16" fill="#FFD6DC" opacity="0.75"/>
  <ellipse cx="50" cy="90" rx="33" ry="28" fill="#FFD700" stroke="#E6A800" stroke-width="2"/>
  <circle cx="50" cy="50" r="29" fill="#FFD700" stroke="#E6A800" stroke-width="2"/>
  <polygon points="28,28 34,12 43,24 50,10 57,24 66,12 72,28" fill="#FFC200" stroke="#E6A800" stroke-width="1.5"/>
  <circle cx="50" cy="17" r="5.5" fill="#E91E63"/>
  <circle cx="34" cy="25" r="3.5" fill="#9C27B0"/>
  <circle cx="66" cy="25" r="3.5" fill="#9C27B0"/>
  <path d="M 43 68 Q 28 82 33 98 Q 38 110 50 106" stroke="#E6A800" stroke-width="9" fill="none" stroke-linecap="round"/>
  <path d="M 43 68 Q 28 82 33 98 Q 38 110 50 106" stroke="#FFD700" stroke-width="5" fill="none" stroke-linecap="round"/>
  <circle cx="40" cy="46" r="5.5" fill="#2C1810"/>
  <circle cx="60" cy="46" r="5.5" fill="#2C1810"/>
  <circle cx="41.5" cy="44" r="2.2" fill="white"/>
  <circle cx="61.5" cy="44" r="2.2" fill="white"/>
  <path d="M 42 62 Q 50 69 58 62" stroke="#C07A00" stroke-width="2.5" fill="none" stroke-linecap="round"/>
  <path d="M50 83 C50 83 44 77 40 79.5 C36 82 36 87 40 90 L50 98 L60 90 C64 87 64 82 60 79.5 C56 77 50 83 50 83Z" fill="#E91E63"/>
  <circle cx="34" cy="92" r="4" fill="#FFA500" stroke="#E6A800" stroke-width="1"/>
  <circle cx="66" cy="92" r="4" fill="#FFA500" stroke="#E6A800" stroke-width="1"/>
  <rect x="36" y="102" width="28" height="5" rx="2.5" fill="#FFA500" stroke="#E6A800" stroke-width="1"/>
  <ellipse cx="22" cy="92" rx="11" ry="9" fill="#FFD700" stroke="#E6A800" stroke-width="1.5"/>
  <ellipse cx="78" cy="92" rx="11" ry="9" fill="#FFD700" stroke="#E6A800" stroke-width="1.5"/>
</svg>"""

OTTER_SVG = """<svg width="90" height="110" viewBox="0 0 100 120" xmlns="http://www.w3.org/2000/svg">
  <path d="M72 105 Q90 98 88 112 Q85 120 75 116" stroke="#7A5230" stroke-width="9" fill="none" stroke-linecap="round"/>
  <path d="M72 105 Q90 98 88 112 Q85 120 75 116" stroke="#8B6340" stroke-width="5" fill="none" stroke-linecap="round"/>
  <ellipse cx="50" cy="88" rx="31" ry="29" fill="#8B6340"/>
  <ellipse cx="50" cy="92" rx="21" ry="21" fill="#F5E6D3"/>
  <circle cx="50" cy="50" r="27" fill="#8B6340"/>
  <circle cx="25" cy="29" r="11" fill="#8B6340"/>
  <circle cx="75" cy="29" r="11" fill="#8B6340"/>
  <circle cx="25" cy="29" r="7" fill="#C4956A"/>
  <circle cx="75" cy="29" r="7" fill="#C4956A"/>
  <ellipse cx="50" cy="56" rx="19" ry="16" fill="#F5E6D3"/>
  <circle cx="41" cy="47" r="6.5" fill="#2C1810"/>
  <circle cx="59" cy="47" r="6.5" fill="#2C1810"/>
  <circle cx="39" cy="44.5" r="2.8" fill="white"/>
  <circle cx="57" cy="44.5" r="2.8" fill="white"/>
  <ellipse cx="50" cy="58" rx="5.5" ry="4.5" fill="#3D2010"/>
  <path d="M 44 64 Q 50 70 56 64" stroke="#2C1810" stroke-width="2.5" fill="none" stroke-linecap="round"/>
  <line x1="53" y1="59" x2="71" y2="54" stroke="#6B4A2A" stroke-width="1.2" opacity="0.55"/>
  <line x1="53" y1="61.5" x2="73" y2="61.5" stroke="#6B4A2A" stroke-width="1.2" opacity="0.55"/>
  <line x1="47" y1="59" x2="29" y2="54" stroke="#6B4A2A" stroke-width="1.2" opacity="0.55"/>
  <line x1="47" y1="61.5" x2="27" y2="61.5" stroke="#6B4A2A" stroke-width="1.2" opacity="0.55"/>
  <ellipse cx="28" cy="93" rx="13" ry="10" fill="#7A5230"/>
  <ellipse cx="72" cy="93" rx="13" ry="10" fill="#7A5230"/>
  <ellipse cx="28" cy="102" rx="10" ry="7" fill="#6B4423"/>
  <ellipse cx="72" cy="102" rx="10" ry="7" fill="#6B4423"/>
  <circle cx="33" cy="55" r="7" fill="#FFB6C1" opacity="0.4"/>
  <circle cx="67" cy="55" r="7" fill="#FFB6C1" opacity="0.4"/>
</svg>"""


def generate_comments(prices: dict, risk: dict, fear_greed: dict, ai_summary: dict = None) -> dict:
    """AIガネーシャとAIカワウソのコメントを生成"""
    result = {
        "ganesha": "",
        "otter": "",
        "available": False,
        "mood": "neutral",
    }

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return result

    vix    = prices.get("^VIX", {}).get("latest", 20) or 20
    sp_chg = prices.get("^GSPC", {}).get("change_pct", 0) or 0
    nk_chg = prices.get("^N225", {}).get("change_pct", 0) or 0
    fg     = fear_greed.get("score", 50) or 50
    rs     = risk.get("score", 0)
    sentiment = risk.get("sentiment", "中立")
    mood   = _get_mood(rs, vix)
    result["mood"] = mood

    neut_view = ""
    if ai_summary and ai_summary.get("available"):
        neut_view = (ai_summary.get("neutral_view") or "")[:120]

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")

        # ── ガネーシャのコメント ──
        ganesha_prompt = f"""あなたは「AIガネーシャ」です。インドの知恵の神・ガネーシャとして市場を解説してください。
語尾は「〜じゃ」「〜ですぞ」「〜であります」のような、少し古風で威厳ある口調。
絵文字は🐘のみ使用可。3〜4文で。

市場状況: VIX={vix:.1f} / S&P500={sp_chg:+.2f}% / 日経={nk_chg:+.2f}% / F&G={fg} / リスクスコア={rs:+.2f}
地合い: {sentiment}（{mood}）
{f'AI要約: {neut_view}' if neut_view else ''}

今日の相場をガネーシャとして解説してください（200字以内）。"""

        ganesha_resp = model.generate_content(ganesha_prompt)
        result["ganesha"] = ganesha_resp.text.strip()

        # ── カワウソのコメント ──
        otter_prompt = f"""あなたは「AIカワウソ」です。めちゃくちゃかわいいカワウソとして、今日の相場を超シンプルに説明してください。
語尾は「〜だよ〜！」「〜なの〜♪」「〜してね！」のようなかわいい口調。
絵文字を2〜3個使用。中学生でもわかる言葉で2〜3文。専門用語は使わない。

市場状況: VIX={vix:.1f} / S&P500={sp_chg:+.2f}% / 日経={nk_chg:+.2f}% / F&G={fg}
地合い: {sentiment}

カワウソらしくかわいく説明してください（100字以内）。"""

        otter_resp = model.generate_content(otter_prompt)
        result["otter"] = otter_resp.text.strip()
        result["available"] = True

        logger.info(f"✅ キャラクターコメント生成完了 [mood={mood}]")
        return result

    except Exception as e:
        logger.warning(f"キャラクターコメント生成エラー: {e}")
        # フォールバックコメント（気分別）
        fallbacks = {
            "crisis":      ("🐘 これは大変な状況ですぞ！嵐の真っ只中、冷静さを保つが肝要じゃ。",
                           "😱 えっ大変だよ〜！市場がめちゃ揺れてるの〜！無理しないでね！"),
            "bear":        ("🐘 市場に重い空気が漂っておりますぞ。慎重に構えるが賢明じゃ。",
                           "🐻 ちょっと元気ない相場だよ〜。のんびり待とうね〜♪"),
            "fear":        ("🐘 不安の気配が漂う相場じゃ。焦らず静観するが吉でありましょう。",
                           "😰 なんかドキドキする相場だよ〜！落ち着いてね〜！"),
            "bull":        ("🐘 本日は強気の流れが来ておるぞ。上昇の波に乗る好機じゃ。",
                           "📈 今日は株が元気だよ〜！いい感じだね〜♪"),
            "strong_bull": ("🐘 素晴らしい！市場は大いに盛り上がっておるぞ。強気相場の恩恵を受けるべし！",
                           "🚀 わあ〜すごく上がってるよ〜！！最高だね〜♪🎉"),
            "neutral":     ("🐘 本日は方向感の定まらぬ相場じゃ。様子を見るが賢明ですぞ。",
                           "🦦 今日はなんとも言えない感じの相場だよ〜♪ のんびり見守ろ〜！"),
        }
        g, o = fallbacks.get(mood, fallbacks["neutral"])
        result["ganesha"] = g
        result["otter"]   = o
        result["available"] = True
        return result


def get_character_html(ganesha_comment: str, otter_comment: str, mood: str = "neutral") -> str:
    """
    HTMLキャラクターセクションを生成。
    src/assets/characters.png がある場合: イラスト画像スプライット
    ない場合: SVGフォールバック
    """
    g_text = ganesha_comment or "市場データを分析中ですぞ…"
    o_text = otter_comment   or "データ取得中だよ〜♪"

    # スプライット画像を優先して使う
    b64 = _load_sprite_b64()

    if b64:
        # ── 画像スプライットモード ──
        ot_col, ot_row = OTTER_MOOD_MAP.get(mood, OTTER_MOOD_MAP["neutral"])
        gn_col, gn_row = GANESHA_MOOD_MAP.get(mood, GANESHA_MOOD_MAP["neutral"])
        otter_img   = _sprite_div(ot_col, ot_row, b64, size=120)
        ganesha_img = _sprite_div(gn_col, gn_row, b64, size=120)
    else:
        # ── SVGフォールバックモード ──
        otter_img   = OTTER_SVG
        ganesha_img = GANESHA_SVG

    return f"""
<div class="char-section">
  <!-- ガネーシャ行：左にキャラ → 右に吹き出し -->
  <div class="char-row ganesha-row">
    <div class="char-avatar-wrap">
      {ganesha_img}
      <div class="char-name ganesha-name">🐘 AIガネーシャ</div>
    </div>
    <div class="speech-bubble ganesha-bubble">
      <div class="bubble-badge ganesha-badge">📜 プロの相場解説</div>
      <div class="bubble-text">{g_text}</div>
    </div>
  </div>

  <!-- カワウソ行：左に吹き出し ← 右にキャラ -->
  <div class="char-row otter-row">
    <div class="speech-bubble otter-bubble">
      <div class="bubble-badge otter-badge">✨ カンタンまとめ</div>
      <div class="bubble-text">{o_text}</div>
    </div>
    <div class="char-avatar-wrap">
      {otter_img}
      <div class="char-name otter-name">🦦 AIカワウソ</div>
    </div>
  </div>
</div>"""


CHARACTER_CSS = """
/* ══════════════════════════════════════
   キャラクター吹き出しセクション
══════════════════════════════════════ */
.char-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 14px 0;
}
.char-row {
  display: flex;
  align-items: center;
  gap: 0;
  border-radius: 16px;
  overflow: visible;
}
.ganesha-row {
  background: linear-gradient(135deg, #1c1600 0%, #271e00 100%);
  border: 1px solid #FFD70033;
}
.otter-row {
  background: linear-gradient(135deg, #160e09 0%, #1f130c 100%);
  border: 1px solid #C4956A33;
}
.char-avatar-wrap {
  flex-shrink: 0;
  width: 128px;
  text-align: center;
  padding: 6px 4px 6px;
}
.char-name {
  font-size: 0.58em;
  font-weight: 800;
  margin-top: 4px;
  white-space: nowrap;
  letter-spacing: 0.2px;
}
.ganesha-name { color: #FFD700; }
.otter-name   { color: #C4956A; }
.speech-bubble {
  flex: 1;
  border-radius: 14px;
  padding: 11px 14px;
  margin: 8px;
  position: relative;
  min-width: 0;
}
.ganesha-bubble {
  background: rgba(255, 215, 0, 0.07);
  border: 1px solid #FFD70044;
}
.ganesha-bubble::before {
  content: '';
  position: absolute;
  left: -9px;
  top: 20px;
  border-top: 8px solid transparent;
  border-bottom: 8px solid transparent;
  border-right: 9px solid #FFD70044;
}
.otter-bubble {
  background: rgba(196, 149, 106, 0.09);
  border: 1px solid #C4956A44;
}
.otter-bubble::after {
  content: '';
  position: absolute;
  right: -9px;
  top: 20px;
  border-top: 8px solid transparent;
  border-bottom: 8px solid transparent;
  border-left: 9px solid #C4956A44;
}
.bubble-badge {
  display: inline-block;
  font-size: 0.60em;
  font-weight: 800;
  letter-spacing: 0.8px;
  padding: 2px 8px;
  border-radius: 20px;
  margin-bottom: 6px;
  text-transform: uppercase;
}
.ganesha-badge {
  background: rgba(255,215,0,0.15);
  color: #FFD700;
  border: 1px solid #FFD70044;
}
.otter-badge {
  background: rgba(196,149,106,0.15);
  color: #C4956A;
  border: 1px solid #C4956A44;
}
.bubble-text {
  font-size: 0.84em;
  line-height: 1.75;
  color: var(--text);
  word-break: break-word;
}
@media(max-width:500px) {
  .char-row { flex-direction: column; padding: 10px; }
  .char-avatar-wrap { width: 100%; padding: 4px 0; }
  .speech-bubble { margin: 4px 0 0; width: 100%; }
  .ganesha-bubble::before,
  .otter-bubble::after { display: none; }
}
"""
