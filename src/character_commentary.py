"""
AIキャラクター解説モジュール
AIガネーシャ（知恵の象の神）とAIカワウソが市場を解説する。

【画像スプライトシート仕様】
  ファイル: src/assets/characters.png
  グリッド: 4列 × 9行 = 36コマ（各206×203px）
  上段(行0-2): カワウソ（一部混在）
  下段(行2-8): ガネーシャ（一部混在）

  カワウソ配置:
    (col=0,row=0): 指差し上・電球・ノート   → analytical
    (col=1,row=0): パニック・急落チャート   → crisis
    (col=2,row=0): 余裕・サムズアップ       → bull
    (col=3,row=0): 悲しい・下落チャート     → bear
    (col=0,row=1): 大興奮・バンザイ         → strong_bull
    (col=1,row=1): 疲れた・モニター前       → neutral（疲弊）
    (col=2,row=1): ?マーク・困惑            → fear
    (col=3,row=1): 勉強・ノート記録         → neutral
    (col=0,row=2): 集中・目標ダーツ         → analytical
    (col=1,row=2): 目が回る・急落急騰       → volatile
    (col=2,row=7): ノート・単体立ち姿       → neutral（サブ）
    (col=1,row=8): ハート背景・かわいい     → strong_bull（特別）
    (col=3,row=8): ハート背景・かわいい     → strong_bull（特別）

  ガネーシャ配置:
    (col=2,row=2): ボード・ポインター        → analytical
    (col=3,row=2): サムズアップ・上昇        → bull
    (col=0,row=3): 指差し上・急上昇         → bull
    (col=1,row=3): 眠い・退屈相場（YAWN）   → neutral（低ボラ）
    (col=2,row=3): 悲しい・LOSS表示         → bear
    (col=3,row=3): 防御・シールド（PLAN.PROTECT.PROSPER） → cautious
    (col=0,row=4): 考え中・ロウソク足       → analytical
    (col=1,row=4): 強気・指差し上           → bull
    (col=2,row=4): パニック・急落・貯金箱壊 → crisis
    (col=3,row=4): 大喜び・急上昇・コイン   → strong_bull
    (col=0,row=5): 指差し・目標             → analytical
    (col=1,row=5): 眠い・フラット相場       → neutral
    (col=2,row=5): ピースサイン・上昇       → bull
    (col=3,row=5): ガッツポーズ・急上昇     → strong_bull
    (col=0,row=6): ノート・サムズアップ     → bull（サブ）
    (col=1,row=6): ボード・プレゼン         → analytical
    (col=2,row=6): 考え中・ロウソク足       → neutral
    (col=3,row=6): 防御・警告サイン・下落   → fear
    (col=0,row=7): パニック・急落           → crisis（サブ）
    (col=1,row=7): 悲しい・下落チャート     → bear（サブ）
    (col=3,row=7): 指差し・上昇グラフ       → bull（サブ）
    (col=0,row=8): ハート背景・かわいい     → strong_bull（特別）
    (col=2,row=8): ハート背景・バルーン     → strong_bull（特別）

ガネーシャ: 格調高く・深い分析（〜じゃ / 〜ですぞ / 〜であります）
カワウソ: かわいく・中学生でもわかる言葉で（〜だよ〜！ / 〜なの〜♪）
"""
import os
import base64
import random
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# フォールバック・セリフ集（APIなし or エラー時に使用）
# 各気分6パターン。ガネーシャは相場格言・故事を、カワウソは擬音・
# 多彩な語尾を盛り込み語彙を豊かに。random.choice で毎回変える。
# ══════════════════════════════════════════════════════════════
_GANESHA_LINES = {
    "crisis": [
        "🐘 これは荒れ模様じゃのう。されど『人の行く裏に道あり花の山』、皆が恐れる時こそ機が潜むものじゃ。",
        "🐘 嵐の海でこそ真の船乗りの価値が問われるのじゃ。慌てず、舵をしかと握りなされ。",
        "🐘 暴落は天の試練ですぞ。『落ちるナイフは掴むな』と申す、まずは身を守るが肝要じゃ。",
        "🐘 市場が悲鳴をあげておるな。じゃが歴史を見よ、夜明け前が最も暗いのが常であります。",
        "🐘 恐慌の渦中にあっても冷静さを失うでないぞ。退くも相場、現金もまた立派な戦略じゃ。",
        "🐘 こういう日は無理に動かぬが勝ちじゃ。『休むも相場』、英気を養うがよいですぞ。",
    ],
    "bear": [
        "🐘 重き雲が垂れこめておるな。されど下げ相場は次の上げの種を蒔く時節でもありますぞ。",
        "🐘 弱気の風が吹いておる。『二度に買うべし二度に売るべし』、一度に動かぬが賢明じゃ。",
        "🐘 軟調な地合いじゃのう。じっと根を張る竹のごとく、辛抱の時と心得なされ。",
        "🐘 下落基調ですぞ。されど『閑散に売りなし』、売り疲れの兆しも見えてくる頃合いじゃ。",
        "🐘 市場に元気がないのう。こういう時は優良な企業を吟味する好機でもありますぞ。",
        "🐘 弱含みの相場じゃ。焦りは禁物、『遠くのものは避けよ』、無理な深追いは慎むべし。",
    ],
    "fear": [
        "🐘 投資家の心に不安が宿っておるな。されど恐怖は時に過剰、冷静な目が利を生むのじゃ。",
        "🐘 ざわめく相場ですぞ。『もうはまだなり、まだはもうなり』、決めつけは禁物であります。",
        "🐘 警戒の色濃き一日じゃ。されど備えあれば憂いなし、現金と分散こそ盾となりますぞ。",
        "🐘 ドキリとする値動きじゃのう。じゃが恐怖指数が高い時ほど、後の反発も大きいものよ。",
        "🐘 不穏な空気が漂うな。群衆が騒ぐ時こそ、己の物差しを信じるが肝要じゃ。",
        "🐘 揺らぎの大きい相場ですぞ。『人みな強気なら売り、弱気なら買い』を思い出されよ。",
    ],
    "neutral": [
        "🐘 本日は凪の相場じゃのう。方向定まらぬ時は、無理せず次の波を待つが上策ですぞ。",
        "🐘 もみ合いの一日であります。『相場は相場に聞け』、焦らず流れを見極めなされ。",
        "🐘 とりたてて動きなき日じゃ。こういう静かな時こそ、学びを深める好機ですぞ。",
        "🐘 横ばいの地合いじゃのう。退屈に見えても、エネルギーを溜める大切な期間であります。",
        "🐘 方向感に乏しい相場ですな。『迷う時は何もせぬが一番』とも申しますぞ。",
        "🐘 穏やかな一日じゃ。次の一手に備え、英気を養うておくがよいでありましょう。",
    ],
    "bull": [
        "🐘 上昇の風が吹いておるぞ！『上げ百日、下げ三日』、好機は逃さぬが肝要じゃ。",
        "🐘 強気の流れですな。されど『山高ければ谷深し』、慢心せず利も確かめておきなされ。",
        "🐘 買い手が優勢の一日じゃ。波に乗りつつも、足元はしかと固めておくが賢明ですぞ。",
        "🐘 明るい地合いじゃのう。『順張りは相場の王道』、流れに沿うが自然であります。",
        "🐘 力強い上げ相場ですぞ。されど高値掴みには用心、欲を出しすぎぬよう心得なされ。",
        "🐘 上機嫌の市場じゃ。良き風が吹くうちに、着実に果実を育てていくがよいでありますぞ。",
    ],
    "strong_bull": [
        "🐘 おお、見事な急騰じゃ！祭りの賑わいよのう。されど宴の後を忘れぬのが賢者ですぞ。",
        "🐘 市場は大盛り上がりであります！『強気相場は悲観の中に生まれる』を体現しておるな。",
        "🐘 天井知らずの勢いじゃ！じゃが『過ぎたるは猶及ばざるが如し』、利益確定も視野にな。",
        "🐘 素晴らしき上昇ですぞ！皆が熱狂する時こそ、一歩引いた目も持ち合わせなされ。",
        "🐘 爆発的な買いじゃのう！喜ばしき限り、されど『強欲は身を滅ぼす』の戒めも忘れずに。",
        "🐘 これぞ大相場の様相じゃ！波に乗るは結構、じゃが降り際の支度も怠るでないぞ。",
    ],
}

_OTTER_LINES = {
    "crisis": [
        "😱 わわっ大変だよ〜！市場がぐらぐら揺れてるの〜！こんな日は無理しないでね！",
        "😨 きゃ〜！株がドーンって下がってるよ〜！あわてず深呼吸しよ〜すぅ〜はぁ〜🫧",
        "💦 ぷるぷる…こわい値動きだよ〜。今日はおやすみして様子見が安心なの〜！",
        "🌀 ぐるぐる〜！相場が嵐みたいだよ〜！大事なお金は守ろうね〜🛡️",
        "😵 うぅ〜ジェットコースターみたい〜！こういう時こそ落ち着くのが大事なんだよ〜！",
        "🆘 たいへんたいへん〜！でもね、嵐はいつか過ぎ去るの〜。それまで踏ん張ろ〜♪",
    ],
    "bear": [
        "🐻 ちょっと元気ない相場だよ〜。あせらず、のんびり待つのがいいの〜♪",
        "🍂 しょんぼり下げ相場だね〜。でも下がった時はバーゲンのチャンスでもあるんだよ〜！",
        "😔 株さんが疲れてるみたい〜。今日はそっと見守ってあげよ〜♪",
        "🌧️ どんより気味だよ〜。こんな日は欲しい銘柄をリストアップして待つの〜📝",
        "🦦 む〜下げ下げだね〜。でもあわてて売らないで、ゆっくり考えよ〜！",
        "💤 元気のない相場なの〜。無理に動かず、おやつでも食べて待とっか〜🍪",
    ],
    "fear": [
        "😰 なんだかドキドキする相場だよ〜！ふか呼吸して落ち着こ〜♪",
        "😟 そわそわ〜。みんな不安そうだけど、こわがりすぎも良くないんだって〜！",
        "🫨 ぷるぷる…値動きが読めないよ〜。こういう時は無理しないのが一番なの〜！",
        "😣 う〜ん不安な空気だね〜。でもね、こわい時ほどチャンスが隠れてるんだよ〜✨",
        "🌫️ もやもや相場だよ〜。あせらず、自分のペースを大事にしてね〜♪",
        "😖 きんちょうしちゃうね〜！でも大丈夫、ゆっくり様子を見ようね〜🫶",
    ],
    "neutral": [
        "🦦 今日はなんとも言えない感じの相場だよ〜♪ のんびり見守ろ〜！",
        "😌 ぽけ〜っとした相場だね〜。こういう静かな日は勉強日和なの〜📚",
        "🍃 ゆらゆら横ばいだよ〜。あわてず次の動きを待とうね〜♪",
        "💭 う〜ん、どっちつかずだね〜。むりに動かず、まったりいこ〜🍵",
        "🦦 平和な一日だよ〜♪ こんな日はおやつタイムにしちゃお〜🍡",
        "😴 とくに動きなしだよ〜。エネルギー溜めてる時期なの、のんびりね〜！",
    ],
    "bull": [
        "📈 今日は株が元気だよ〜！いい感じだね〜♪",
        "😊 るんるん〜上げ相場だよ〜！でも調子に乗りすぎないようにね〜♪",
        "🌟 ぴょんぴょん上がってるよ〜！流れに乗れてラッキーなの〜！",
        "🦦 わ〜い、明るい相場だね〜♪ こういう日は気分もうきうきなの〜！",
        "✨ 買いが優勢だよ〜！いい波が来てるけど、足元も見てね〜♪",
        "🎈 ふわ〜っと上昇中だよ〜！ニコニコしながら見守ろ〜😊",
    ],
    "strong_bull": [
        "🚀 わあ〜すごく上がってるよ〜！！最高だね〜♪🎉",
        "🎆 ばーん！大上昇だよ〜！！みんなニコニコなの〜♪でも浮かれすぎ注意だよ〜！",
        "🌈 きゃ〜！株がぐんぐん伸びてる〜！！うれしくてしっぽフリフリなの〜🦦💨",
        "🥳 おまつりだ〜！！こんな日はうれしいけど、利益確定も考えてみてね〜♪",
        "💖 ぴかぴか絶好調だよ〜！！わくわくが止まらないの〜！でも欲張りはダメよ〜♪",
        "🎊 すごいすごい〜爆上げだよ〜！！この嬉しさ、忘れず記録しておこ〜📸",
    ],
}

# ── スプライトシート設定 ──────────────────────────────────────────
SPRITE_PATH = Path(__file__).parent / "assets" / "characters.png"
SPRITE_COLS = 4
SPRITE_ROWS = 9

# ── 気分マッピング（相場状況 → スプライト座標） ───────────────────
# カワウソ: mood → (col, row)
OTTER_MOOD_MAP = {
    "crisis":      (1, 0),   # パニック・急落チャート
    "bear":        (3, 0),   # 悲しい・下落チャート
    "fear":        (2, 1),   # ?マーク・困惑
    "neutral":     (3, 1),   # 勉強・ノート記録
    "bull":        (2, 0),   # 余裕・サムズアップ
    "strong_bull": (0, 1),   # 大興奮・バンザイ
    "analytical":  (0, 0),   # 指差し上・電球・ノート
    "volatile":    (1, 2),   # 目が回る・急落急騰
}

# ガネーシャ: mood → (col, row)
GANESHA_MOOD_MAP = {
    "crisis":      (2, 4),   # パニック・急落・貯金箱壊れる
    "bear":        (2, 3),   # 悲しい・LOSS表示
    "fear":        (3, 6),   # 防御・警告サイン・下落チャート
    "neutral":     (1, 5),   # 眠い・フラット相場（低ボラ）
    "bull":        (1, 4),   # 強気・指差し上
    "strong_bull": (3, 4),   # 大喜び・急上昇・コイン
    "cautious":    (3, 3),   # 防御・シールド（PLAN.PROTECT.PROSPER）
    "analytical":  (0, 4),   # 考え中・ロウソク足分析
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

        # 言い回しを毎回変えるためのスパイス（プロンプトに混ぜる）
        ganesha_flavor = random.choice([
            "相場格言（例：人の行く裏に道あり花の山／上げ百日下げ三日／休むも相場）をひとつ自然に織り込む",
            "故事やことわざ（例：山高ければ谷深し／過ぎたるは猶及ばざるが如し）をひとつ引いて諭す",
            "自然の比喩（嵐・凪・竹・大河など）を使って情景豊かに語る",
            "古の賢人が弟子に説くように、落ち着いた示唆を与える",
        ])
        otter_flavor = random.choice([
            "擬音（ぴょんぴょん／そわそわ／るんるん／ぷるぷる など）を入れて",
            "しっぽや手の動きなど、カワウソの仕草をひとつ混ぜて",
            "おやつや川遊びなど、カワウソらしい例えを使って",
            "語尾を毎回変えて（〜だよ〜！／〜なの〜♪／〜しよ〜！／〜だね〜）",
        ])

        # ── ガネーシャのコメント ──
        ganesha_prompt = f"""あなたは「AIガネーシャ」です。インドの知恵の神・ガネーシャとして市場を解説してください。
語尾は「〜じゃ」「〜ですぞ」「〜であります」のような、少し古風で威厳ある口調。
語彙豊かに、毎回ちがう表現を心がけ、決まり文句の繰り返しは避けてください。
今回は特に: {ganesha_flavor}。
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
毎回ちがう言い回し・語尾を使って、ワンパターンにならないようにしてください。
今回は特に: {otter_flavor}。
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
        result["ganesha"]   = _pick_fallback(_GANESHA_LINES, mood)
        result["otter"]     = _pick_fallback(_OTTER_LINES, mood)
        result["available"] = True
        return result


def _pick_fallback(lines: dict, mood: str) -> str:
    """気分に応じたセリフを語彙集からランダムに1つ選ぶ"""
    pool = lines.get(mood) or lines.get("neutral")
    return random.choice(pool)


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
