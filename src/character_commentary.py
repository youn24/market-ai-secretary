"""
AIキャラクター解説モジュール
AIガネーシャ（知恵の象の神）とAIカワウソが市場を解説する。
ガネーシャ: 格調高く・深い分析
カワウソ: かわいく・中学生でもわかる言葉で
"""
import os
import logging

logger = logging.getLogger(__name__)

# ── SVG定義 ──────────────────────────────────────────────────────

GANESHA_SVG = """<svg width="90" height="110" viewBox="0 0 100 120" xmlns="http://www.w3.org/2000/svg">
  <!-- 耳（大きな象耳） -->
  <ellipse cx="18" cy="52" rx="17" ry="23" fill="#FFBF00" stroke="#E6A800" stroke-width="1.5"/>
  <ellipse cx="82" cy="52" rx="17" ry="23" fill="#FFBF00" stroke="#E6A800" stroke-width="1.5"/>
  <ellipse cx="18" cy="52" rx="11" ry="16" fill="#FFD6DC" opacity="0.75"/>
  <ellipse cx="82" cy="52" rx="11" ry="16" fill="#FFD6DC" opacity="0.75"/>
  <!-- 体 -->
  <ellipse cx="50" cy="90" rx="33" ry="28" fill="#FFD700" stroke="#E6A800" stroke-width="2"/>
  <!-- 頭 -->
  <circle cx="50" cy="50" r="29" fill="#FFD700" stroke="#E6A800" stroke-width="2"/>
  <!-- 王冠 -->
  <polygon points="28,28 34,12 43,24 50,10 57,24 66,12 72,28" fill="#FFC200" stroke="#E6A800" stroke-width="1.5"/>
  <circle cx="50" cy="17" r="5.5" fill="#E91E63"/>
  <circle cx="34" cy="25" r="3.5" fill="#9C27B0"/>
  <circle cx="66" cy="25" r="3.5" fill="#9C27B0"/>
  <!-- 鼻（象の長い鼻） -->
  <path d="M 43 68 Q 28 82 33 98 Q 38 110 50 106" stroke="#E6A800" stroke-width="9" fill="none" stroke-linecap="round"/>
  <path d="M 43 68 Q 28 82 33 98 Q 38 110 50 106" stroke="#FFD700" stroke-width="5" fill="none" stroke-linecap="round"/>
  <!-- 目 -->
  <circle cx="40" cy="46" r="5.5" fill="#2C1810"/>
  <circle cx="60" cy="46" r="5.5" fill="#2C1810"/>
  <circle cx="41.5" cy="44" r="2.2" fill="white"/>
  <circle cx="61.5" cy="44" r="2.2" fill="white"/>
  <!-- 笑顔 -->
  <path d="M 42 62 Q 50 69 58 62" stroke="#C07A00" stroke-width="2.5" fill="none" stroke-linecap="round"/>
  <!-- 胸のハート -->
  <path d="M50 83 C50 83 44 77 40 79.5 C36 82 36 87 40 90 L50 98 L60 90 C64 87 64 82 60 79.5 C56 77 50 83 50 83Z" fill="#E91E63"/>
  <!-- アクセサリー -->
  <circle cx="34" cy="92" r="4" fill="#FFA500" stroke="#E6A800" stroke-width="1"/>
  <circle cx="66" cy="92" r="4" fill="#FFA500" stroke="#E6A800" stroke-width="1"/>
  <rect x="36" y="102" width="28" height="5" rx="2.5" fill="#FFA500" stroke="#E6A800" stroke-width="1"/>
  <!-- 腕 -->
  <ellipse cx="22" cy="92" rx="11" ry="9" fill="#FFD700" stroke="#E6A800" stroke-width="1.5"/>
  <ellipse cx="78" cy="92" rx="11" ry="9" fill="#FFD700" stroke="#E6A800" stroke-width="1.5"/>
</svg>"""

OTTER_SVG = """<svg width="90" height="110" viewBox="0 0 100 120" xmlns="http://www.w3.org/2000/svg">
  <!-- 尻尾 -->
  <path d="M72 105 Q90 98 88 112 Q85 120 75 116" stroke="#7A5230" stroke-width="9" fill="none" stroke-linecap="round"/>
  <path d="M72 105 Q90 98 88 112 Q85 120 75 116" stroke="#8B6340" stroke-width="5" fill="none" stroke-linecap="round"/>
  <!-- 体 -->
  <ellipse cx="50" cy="88" rx="31" ry="29" fill="#8B6340"/>
  <!-- おなか（白） -->
  <ellipse cx="50" cy="92" rx="21" ry="21" fill="#F5E6D3"/>
  <!-- 頭 -->
  <circle cx="50" cy="50" r="27" fill="#8B6340"/>
  <!-- 耳 -->
  <circle cx="25" cy="29" r="11" fill="#8B6340"/>
  <circle cx="75" cy="29" r="11" fill="#8B6340"/>
  <circle cx="25" cy="29" r="7" fill="#C4956A"/>
  <circle cx="75" cy="29" r="7" fill="#C4956A"/>
  <!-- 顔の白い部分 -->
  <ellipse cx="50" cy="56" rx="19" ry="16" fill="#F5E6D3"/>
  <!-- 目 -->
  <circle cx="41" cy="47" r="6.5" fill="#2C1810"/>
  <circle cx="59" cy="47" r="6.5" fill="#2C1810"/>
  <circle cx="39" cy="44.5" r="2.8" fill="white"/>
  <circle cx="57" cy="44.5" r="2.8" fill="white"/>
  <!-- 小さなハイライト -->
  <circle cx="43" cy="49" r="1.2" fill="white" opacity="0.6"/>
  <circle cx="61" cy="49" r="1.2" fill="white" opacity="0.6"/>
  <!-- 鼻 -->
  <ellipse cx="50" cy="58" rx="5.5" ry="4.5" fill="#3D2010"/>
  <ellipse cx="49" cy="57" rx="2" ry="1.5" fill="#5C3020" opacity="0.5"/>
  <!-- 口 -->
  <path d="M 44 64 Q 50 70 56 64" stroke="#2C1810" stroke-width="2.5" fill="none" stroke-linecap="round"/>
  <!-- ひげ -->
  <line x1="53" y1="59" x2="71" y2="54" stroke="#6B4A2A" stroke-width="1.2" opacity="0.55"/>
  <line x1="53" y1="61.5" x2="73" y2="61.5" stroke="#6B4A2A" stroke-width="1.2" opacity="0.55"/>
  <line x1="47" y1="59" x2="29" y2="54" stroke="#6B4A2A" stroke-width="1.2" opacity="0.55"/>
  <line x1="47" y1="61.5" x2="27" y2="61.5" stroke="#6B4A2A" stroke-width="1.2" opacity="0.55"/>
  <!-- 腕（折りたたんでいる） -->
  <ellipse cx="28" cy="93" rx="13" ry="10" fill="#7A5230"/>
  <ellipse cx="72" cy="93" rx="13" ry="10" fill="#7A5230"/>
  <!-- 前足の先 -->
  <ellipse cx="28" cy="102" rx="10" ry="7" fill="#6B4423"/>
  <ellipse cx="72" cy="102" rx="10" ry="7" fill="#6B4423"/>
  <!-- かわいい頬の赤み -->
  <circle cx="33" cy="55" r="7" fill="#FFB6C1" opacity="0.4"/>
  <circle cx="67" cy="55" r="7" fill="#FFB6C1" opacity="0.4"/>
</svg>"""


def generate_comments(prices: dict, risk: dict, fear_greed: dict, ai_summary: dict = None) -> dict:
    """AIガネーシャとAIカワウソのコメントを生成"""
    result = {
        "ganesha": "",
        "otter": "",
        "available": False,
    }

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return result

    vix = prices.get("^VIX", {}).get("latest", 20) or 20
    sp_chg = prices.get("^GSPC", {}).get("change_pct", 0) or 0
    nk_chg = prices.get("^N225", {}).get("change_pct", 0) or 0
    fg = fear_greed.get("score", 50) or 50
    rs = risk.get("score", 0)
    sentiment = risk.get("sentiment", "中立")

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
地合い: {sentiment}
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

        logger.info("✅ キャラクターコメント生成完了")
        return result

    except Exception as e:
        logger.warning(f"キャラクターコメント生成エラー: {e}")
        # フォールバックコメント
        if rs >= 1:
            result["ganesha"] = "🐘 本日の市場は強気の流れじゃ。上昇の波に乗る好機ですぞ。ただし慢心は禁物であります。"
            result["otter"] = "🦦 今日は株が上がってるよ〜！でも急に変わることもあるから気をつけてね〜♪"
        elif rs <= -1:
            result["ganesha"] = "🐘 市場に慎重さが漂っておりますぞ。嵐の前の静けさやもしれませぬ。"
            result["otter"] = "🦦 ちょっと怖い感じの相場だよ〜！無理しないでね〜！"
        else:
            result["ganesha"] = "🐘 本日は方向感の定まらぬ相場じゃ。様子を見るが賢明ですぞ。"
            result["otter"] = "🦦 今日はなんとも言えない感じの相場だよ〜♪ のんびり見守ろ〜！"
        result["available"] = True
        return result


def get_character_html(ganesha_comment: str, otter_comment: str) -> str:
    """HTMLキャラクターセクションを生成（吹き出しスタイル）"""
    g_text = ganesha_comment or "市場データを分析中ですぞ…"
    o_text = otter_comment or "データ取得中だよ〜♪"
    return f"""
<div class="char-section">
  <div class="char-row ganesha-row">
    <!-- ガネーシャ：左にキャラ、右に吹き出し -->
    <div class="char-avatar-wrap">
      {GANESHA_SVG}
      <div class="char-name ganesha-name">🐘 AIガネーシャ</div>
    </div>
    <div class="speech-bubble ganesha-bubble">
      <div class="bubble-badge ganesha-badge">📜 プロの相場解説</div>
      <div class="bubble-text">{g_text}</div>
    </div>
  </div>

  <div class="char-row otter-row">
    <!-- カワウソ：左に吹き出し、右にキャラ（左右反転で変化をつける） -->
    <div class="speech-bubble otter-bubble">
      <div class="bubble-badge otter-badge">✨ カンタンまとめ</div>
      <div class="bubble-text">{o_text}</div>
    </div>
    <div class="char-avatar-wrap">
      {OTTER_SVG}
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
/* 1行 = キャラ + 吹き出し */
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

/* アバター（SVG + 名前） */
.char-avatar-wrap {
  flex-shrink: 0;
  width: 96px;
  text-align: center;
  padding: 8px 4px 6px;
}
.char-name {
  font-size: 0.58em;
  font-weight: 800;
  margin-top: 2px;
  white-space: nowrap;
  letter-spacing: 0.2px;
}
.ganesha-name { color: #FFD700; }
.otter-name   { color: #C4956A; }

/* 吹き出し本体 */
.speech-bubble {
  flex: 1;
  border-radius: 14px;
  padding: 11px 14px;
  margin: 8px;
  position: relative;
  min-width: 0;
}
/* ガネーシャ吹き出し（左のキャラからの矢印：左端に三角） */
.ganesha-bubble {
  background: rgba(255, 215, 0, 0.07);
  border: 1px solid #FFD70044;
}
.ganesha-bubble::before {
  content: '';
  position: absolute;
  left: -9px;
  top: 18px;
  border-top: 8px solid transparent;
  border-bottom: 8px solid transparent;
  border-right: 9px solid #FFD70044;
}
/* カワウソ吹き出し（右のキャラへの矢印：右端に三角） */
.otter-bubble {
  background: rgba(196, 149, 106, 0.09);
  border: 1px solid #C4956A44;
}
.otter-bubble::after {
  content: '';
  position: absolute;
  right: -9px;
  top: 18px;
  border-top: 8px solid transparent;
  border-bottom: 8px solid transparent;
  border-left: 9px solid #C4956A44;
}

/* バッジ（タイトル） */
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

/* 本文 */
.bubble-text {
  font-size: 0.84em;
  line-height: 1.75;
  color: var(--text);
  word-break: break-word;
}

/* モバイル対応 */
@media(max-width:500px) {
  .char-row { flex-direction: column; padding: 10px; }
  .char-avatar-wrap { width: 100%; padding: 4px 0; }
  .speech-bubble { margin: 4px 0 0; width: 100%; }
  .ganesha-bubble::before,
  .otter-bubble::after { display: none; }
}
"""
