"""
ガネーシャキャラクター生成モジュール
金色の可愛いガネーシャが市場を紹介・分析・考察する
"""
from src.utils import setup_logger

logger = setup_logger("ganesha")


# ─── ガネーシャ SVG（感情別） ──────────────────────────────

def _ganesha_svg(mood: str = "neutral", size: int = 160) -> str:
    """
    mood: happy / sad / excited / thinking / neutral / warning
    """
    # 感情別カラー
    mood_colors = {
        "happy":    {"body": "#FFD700", "accent": "#FF8C00", "eye": "#2d6a4f", "glow": "#fff176"},
        "sad":      {"body": "#B8860B", "accent": "#8B6914", "eye": "#1a3c6b", "glow": "#ffe082"},
        "excited":  {"body": "#FFA500", "accent": "#FF4500", "eye": "#7b2d8b", "glow": "#ffcc02"},
        "thinking": {"body": "#DAA520", "accent": "#B8860B", "eye": "#0d47a1", "glow": "#fff9c4"},
        "neutral":  {"body": "#FFD700", "accent": "#FFA500", "eye": "#1b5e20", "glow": "#fffde7"},
        "warning":  {"body": "#FF8C00", "accent": "#DC143C", "eye": "#b71c1c", "glow": "#ffe57f"},
    }
    c = mood_colors.get(mood, mood_colors["neutral"])
    b = c["body"]
    a = c["accent"]
    e = c["eye"]
    g = c["glow"]

    # 感情別口の形
    mouth_map = {
        "happy":    f'<path d="M80 105 Q90 118 100 105" stroke="{a}" stroke-width="2.5" fill="none" stroke-linecap="round"/>',
        "sad":      f'<path d="M80 115 Q90 105 100 115" stroke="{a}" stroke-width="2.5" fill="none" stroke-linecap="round"/>',
        "excited":  f'<ellipse cx="90" cy="110" rx="10" ry="7" fill="{a}" opacity="0.8"/>',
        "thinking": f'<path d="M82 110 Q90 113 98 110" stroke="{a}" stroke-width="2" fill="none"/>',
        "neutral":  f'<path d="M82 110 Q90 110 98 110" stroke="{a}" stroke-width="2" fill="none"/>',
        "warning":  f'<path d="M80 110 Q90 120 100 110" stroke="{a}" stroke-width="2.5" fill="none" stroke-linecap="round"/>',
    }
    mouth = mouth_map.get(mood, mouth_map["neutral"])

    # 感情別眉毛
    brow_map = {
        "happy":    f'<path d="M71 72 Q78 68 85 72" stroke="{a}" stroke-width="2" fill="none"/><path d="M95 72 Q102 68 109 72" stroke="{a}" stroke-width="2" fill="none"/>',
        "sad":      f'<path d="M71 72 Q78 76 85 72" stroke="{a}" stroke-width="2" fill="none"/><path d="M95 72 Q102 76 109 72" stroke="{a}" stroke-width="2" fill="none"/>',
        "excited":  f'<path d="M70 70 Q78 65 86 70" stroke="{a}" stroke-width="2.5" fill="none"/><path d="M94 70 Q102 65 110 70" stroke="{a}" stroke-width="2.5" fill="none"/>',
        "thinking": f'<path d="M71 73 Q78 69 85 73" stroke="{a}" stroke-width="2" fill="none"/><path d="M95 71 Q102 75 109 71" stroke="{a}" stroke-width="2" fill="none"/>',
        "neutral":  f'<path d="M72 72 Q79 69 86 72" stroke="{a}" stroke-width="2" fill="none"/><path d="M94 72 Q101 69 108 72" stroke="{a}" stroke-width="2" fill="none"/>',
        "warning":  f'<path d="M70 70 Q78 75 86 70" stroke="{a}" stroke-width="2.5" fill="none"/><path d="M94 70 Q102 75 110 70" stroke="{a}" stroke-width="2.5" fill="none"/>',
    }
    brow = brow_map.get(mood, brow_map["neutral"])

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size+40}" viewBox="0 0 180 220">
  <defs>
    <!-- グロー効果 -->
    <radialGradient id="bodyGrad" cx="45%" cy="40%" r="55%">
      <stop offset="0%" stop-color="{g}"/>
      <stop offset="60%" stop-color="{b}"/>
      <stop offset="100%" stop-color="{a}"/>
    </radialGradient>
    <radialGradient id="headGrad" cx="40%" cy="35%" r="55%">
      <stop offset="0%" stop-color="{g}"/>
      <stop offset="55%" stop-color="{b}"/>
      <stop offset="100%" stop-color="{a}"/>
    </radialGradient>
    <filter id="glow">
      <feGaussianBlur stdDeviation="3" result="coloredBlur"/>
      <feMerge><feMergeNode in="coloredBlur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <filter id="shadow">
      <feDropShadow dx="2" dy="3" stdDeviation="3" flood-color="{a}" flood-opacity="0.4"/>
    </filter>
  </defs>

  <!-- 後光（光輪） -->
  <circle cx="90" cy="75" r="62" fill="none" stroke="{g}"
          stroke-width="6" opacity="0.5"/>
  <circle cx="90" cy="75" r="68" fill="none" stroke="{b}"
          stroke-width="2" opacity="0.3" stroke-dasharray="8,4"/>

  <!-- ───── 左腕（奥） ───── -->
  <ellipse cx="42" cy="130" rx="14" ry="9" fill="url(#bodyGrad)"
           transform="rotate(-30,42,130)" filter="url(#shadow)"/>
  <!-- 左手：蓮の花 -->
  <circle cx="28" cy="118" r="10" fill="#FF69B4" opacity="0.85"/>
  <circle cx="28" cy="118" r="6"  fill="#FFB6C1"/>
  <circle cx="28" cy="118" r="3"  fill="#FFD700"/>

  <!-- ───── 右腕（奥） ───── -->
  <ellipse cx="138" cy="130" rx="14" ry="9" fill="url(#bodyGrad)"
           transform="rotate(30,138,130)" filter="url(#shadow)"/>
  <!-- 右手：巻物（スクロール） -->
  <rect x="146" y="113" width="16" height="22" rx="4" fill="#FFF8DC" stroke="{a}" stroke-width="1.5"/>
  <line x1="150" y1="120" x2="158" y2="120" stroke="{a}" stroke-width="1.2"/>
  <line x1="150" y1="124" x2="158" y2="124" stroke="{a}" stroke-width="1.2"/>
  <line x1="150" y1="128" x2="156" y2="128" stroke="{a}" stroke-width="1.2"/>

  <!-- ───── 胴体 ───── -->
  <ellipse cx="90" cy="158" rx="42" ry="48" fill="url(#bodyGrad)" filter="url(#shadow)"/>
  <!-- おなか模様 -->
  <ellipse cx="90" cy="162" rx="28" ry="30" fill="{g}" opacity="0.25"/>
  <!-- ベルト（腰飾り） -->
  <ellipse cx="90" cy="188" rx="40" ry="8" fill="{a}" opacity="0.6"/>
  <circle cx="90" cy="188" r="5" fill="{g}"/>
  <circle cx="70" cy="188" r="3" fill="{g}" opacity="0.8"/>
  <circle cx="110" cy="188" r="3" fill="{g}" opacity="0.8"/>

  <!-- ───── 左腕（手前） ───── -->
  <ellipse cx="48" cy="145" rx="13" ry="9" fill="url(#bodyGrad)"
           transform="rotate(-25,48,145)" filter="url(#shadow)"/>
  <!-- 左手：コイン（財運） -->
  <circle cx="32" cy="152" r="9" fill="{b}" stroke="{g}" stroke-width="2"/>
  <text x="32" y="156" text-anchor="middle" font-size="10" fill="{a}">¥</text>

  <!-- ───── 右腕（手前） ───── -->
  <ellipse cx="132" cy="145" rx="13" ry="9" fill="url(#bodyGrad)"
           transform="rotate(25,132,145)" filter="url(#shadow)"/>
  <!-- 右手：グラフ（チャート） -->
  <rect x="140" y="148" width="18" height="14" rx="2" fill="white" stroke="{a}" stroke-width="1.5"/>
  <polyline points="143,158 147,153 151,156 155,149" stroke="#e05252" stroke-width="1.5" fill="none"/>

  <!-- ───── 頭 ───── -->
  <ellipse cx="90" cy="82" rx="50" ry="52" fill="url(#headGrad)" filter="url(#shadow)"/>

  <!-- ───── 耳 ───── -->
  <ellipse cx="42" cy="82" rx="16" ry="22" fill="{b}" opacity="0.85"/>
  <ellipse cx="42" cy="82" rx="10" ry="15" fill="{a}" opacity="0.4"/>
  <ellipse cx="138" cy="82" rx="16" ry="22" fill="{b}" opacity="0.85"/>
  <ellipse cx="138" cy="82" rx="10" ry="15" fill="{a}" opacity="0.4"/>

  <!-- ───── 象の鼻 ───── -->
  <path d="M90 108 Q75 120 68 140 Q65 150 72 155 Q80 158 82 148 Q84 138 90 130"
        fill="{b}" stroke="{a}" stroke-width="1.5"/>
  <!-- 鼻先 -->
  <ellipse cx="74" cy="153" rx="8" ry="6" fill="{a}" opacity="0.7"/>

  <!-- ───── 目 ───── -->
  <!-- 左目 -->
  <ellipse cx="76" cy="82" rx="11" ry="12" fill="white"/>
  <ellipse cx="76" cy="83" rx="7"  ry="8"  fill="{e}"/>
  <ellipse cx="76" cy="83" rx="4"  ry="5"  fill="#111"/>
  <circle  cx="78" cy="81" r="1.5" fill="white"/>
  <ellipse cx="76" cy="78" rx="8"  ry="3"  fill="{a}" opacity="0.6"/>
  <!-- 右目 -->
  <ellipse cx="104" cy="82" rx="11" ry="12" fill="white"/>
  <ellipse cx="104" cy="83" rx="7"  ry="8"  fill="{e}"/>
  <ellipse cx="104" cy="83" rx="4"  ry="5"  fill="#111"/>
  <circle  cx="106" cy="81" r="1.5" fill="white"/>
  <ellipse cx="104" cy="78" rx="8"  ry="3"  fill="{a}" opacity="0.6"/>

  <!-- ほっぺたのチーク -->
  <ellipse cx="63" cy="95" rx="9" ry="6" fill="#FF9999" opacity="0.45"/>
  <ellipse cx="117" cy="95" rx="9" ry="6" fill="#FF9999" opacity="0.45"/>

  <!-- 眉毛 -->
  {brow}

  <!-- 口 -->
  {mouth}

  <!-- ───── 牙 ───── -->
  <path d="M83 108 Q79 120 77 125" stroke="white" stroke-width="3.5"
        fill="none" stroke-linecap="round"/>
  <path d="M97 108 Q101 120 103 125" stroke="white" stroke-width="3.5"
        fill="none" stroke-linecap="round" opacity="0.5"/>

  <!-- ───── 頭の飾り（ティアラ） ───── -->
  <ellipse cx="90" cy="36" rx="22" ry="10" fill="{b}" opacity="0.9"/>
  <ellipse cx="90" cy="36" rx="16" ry="7"  fill="{g}"/>
  <!-- 宝石 -->
  <polygon points="90,24 96,34 90,38 84,34" fill="#E91E63"/>
  <polygon points="90,24 96,34 90,38 84,34" fill="none" stroke="{g}" stroke-width="1"/>
  <!-- サイドの飾り -->
  <circle cx="70" cy="38" r="5" fill="{b}" stroke="{g}" stroke-width="1.2"/>
  <circle cx="110" cy="38" r="5" fill="{b}" stroke="{g}" stroke-width="1.2"/>
  <circle cx="70" cy="38" r="2.5" fill="{g}"/>
  <circle cx="110" cy="38" r="2.5" fill="{g}"/>

  <!-- ───── 足 ───── -->
  <ellipse cx="72"  cy="202" rx="18" ry="11" fill="{b}" opacity="0.9"/>
  <ellipse cx="108" cy="202" rx="18" ry="11" fill="{b}" opacity="0.9"/>
  <!-- 足の指 -->
  <circle cx="60"  cy="207" r="4" fill="{a}" opacity="0.8"/>
  <circle cx="70"  cy="210" r="4" fill="{a}" opacity="0.8"/>
  <circle cx="80"  cy="210" r="4" fill="{a}" opacity="0.8"/>
  <circle cx="96"  cy="210" r="4" fill="{a}" opacity="0.8"/>
  <circle cx="106" cy="210" r="4" fill="{a}" opacity="0.8"/>
  <circle cx="116" cy="207" r="4" fill="{a}" opacity="0.8"/>

  <!-- ───── グロー効果 ───── -->
  <ellipse cx="90" cy="75" rx="65" ry="70" fill="none"
           stroke="{g}" stroke-width="8" opacity="0.12" filter="url(#glow)"/>
</svg>"""
    return svg


# ─── 感情判定 ────────────────────────────────────────────────

def _get_mood(risk: dict, fear_greed: dict) -> str:
    meter    = risk.get("meter", "NEUTRAL")
    fg_score = fear_greed.get("score")

    if meter == "RISK_ON" and (fg_score or 50) >= 60:
        return "excited"
    elif meter == "RISK_ON":
        return "happy"
    elif meter == "RISK_OFF" and (fg_score or 50) <= 25:
        return "warning"
    elif meter == "RISK_OFF":
        return "sad"
    elif fg_score and fg_score >= 70:
        return "excited"
    elif fg_score and fg_score <= 30:
        return "sad"
    else:
        return "thinking"


# ─── ガネーシャのセリフ ─────────────────────────────────────

def _get_greeting(mood: str) -> str:
    greetings = {
        "happy":    "🙏 ガネーシャじゃ！今日は良い風が吹いておるぞ！",
        "sad":      "🙏 ガネーシャじゃ...今日は少し嵐の予感がするのう...",
        "excited":  "🙏 ガネーシャじゃ！相場が熱くなっておるぞ！",
        "thinking": "🙏 ガネーシャじゃ。うむ、なかなか難しい相場じゃのう...",
        "neutral":  "🙏 ガネーシャじゃ！今日の相場を見ていこうぞ！",
        "warning":  "🙏 ガネーシャじゃ！気をつけるのじゃ、嵐が来るかもしれぬ！",
    }
    return greetings.get(mood, greetings["neutral"])


def generate_ganesha_comment(risk: dict, fear_greed: dict,
                              prices: dict, ai_summary: dict) -> dict:
    """ガネーシャのコメントを生成する"""
    mood      = _get_mood(risk, fear_greed)
    sentiment = risk.get("sentiment", "不明")
    score     = risk.get("score", 0)
    fg_score  = fear_greed.get("score")
    fg_rating = fear_greed.get("rating_ja", "不明")
    meter     = risk.get("meter", "NEUTRAL")

    # 地合いコメント
    market_comments = {
        "RISK_ON": [
            f"市場は活気づいておるぞ！リスクオン（スコア{score:+.1f}）じゃ。強欲になりすぎないよう気をつけるのじゃ。",
            f"買い意欲が高まっておる。Fear & Greedは{fg_score:.0f}（{fg_rating}）じゃ。過熱感も忘れずにな。",
        ],
        "RISK_OFF": [
            f"嵐の予感がするのう...リスクオフ（スコア{score:+.1f}）じゃ。焦らず冷静に見守ることじゃ。",
            f"市場に不安が広がっておる。Fear & Greedは{f'{fg_score:.0f}' if fg_score else '?'}（{fg_rating}）。守りを固めるのじゃ。",
        ],
        "NEUTRAL": [
            f"今日は方向感のない相場じゃのう（スコア{score:+.1f}）。じっくり観察するのが賢明じゃ。",
            f"強くも弱くもない地合い（{fg_rating}）。焦らず、機会を待つのじゃ。",
        ],
    }
    import random
    comments = market_comments.get(meter, market_comments["NEUTRAL"])
    market_comment = random.choice(comments)

    # 主要指数コメント
    def p(sym):
        d   = prices.get(sym, {})
        v   = d.get("latest")
        chg = d.get("change_pct")
        if v is None: return None, None
        return v, chg

    nk_v, nk_c = p("^N225")
    sp_v, sp_c = p("^GSPC")
    dj_v, dj_c = p("USDJPY=X")

    price_comment = ""
    if nk_c is not None:
        direction = "上昇" if nk_c >= 0 else "下落"
        price_comment += f"日経平均は{abs(nk_c):.2f}%の{direction}じゃ。"
    if sp_c is not None:
        direction = "上昇" if sp_c >= 0 else "下落"
        price_comment += f"S&P500は{abs(sp_c):.2f}%{direction}しておる。"
    if dj_c is not None:
        direction = "円安" if dj_c >= 0 else "円高"
        price_comment += f"ドル円は{direction}傾向じゃ。"

    # AI要約があれば使う
    ai_comment = ""
    if ai_summary.get("available") and ai_summary.get("market_comment"):
        raw = ai_summary["market_comment"][:200]
        ai_comment = f"AIの分析によれば...「{raw}」とのことじゃ。"

    # 注意事項（ガネーシャっぽく）
    disclaimer_comments = [
        "これはガネーシャの観察じゃ。投資の判断はお主自身でするのじゃぞ！",
        "断言はせぬ。相場は生き物じゃ。慎重に、されど大胆に！",
        "ガネーシャは助言せぬ。ただ、知恵を授けるのみじゃ。",
    ]
    disclaimer = random.choice(disclaimer_comments)

    return {
        "mood":           mood,
        "svg":            _ganesha_svg(mood),
        "greeting":       _get_greeting(mood),
        "market_comment": market_comment,
        "price_comment":  price_comment,
        "ai_comment":     ai_comment,
        "disclaimer":     disclaimer,
    }
