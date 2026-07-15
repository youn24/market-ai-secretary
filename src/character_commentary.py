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


def _sector_ctx(sector: dict = None, sector_ranking: dict = None) -> str:
    """セクター/業種データをプロンプト用テキストに整形（分析を厚くする材料）"""
    lines = []
    sa = sector or {}
    if sa.get("available"):
        rot = sa.get("rotation") or {}
        if rot.get("label") or rot.get("phase"):
            lines.append(f"・ローテーション判定: {rot.get('label','')}（フェーズ: {rot.get('phase','')}）")
        if rot.get("detail"):
            lines.append(f"・詳細: {str(rot['detail'])[:150]}")

        def _fmt(items):
            out = []
            for s in (items or [])[:3]:
                if isinstance(s, dict):
                    nm = s.get("name", "")
                    ch = s.get("chg_1d")
                    out.append(f"{nm}{f'({ch:+.2f}%)' if isinstance(ch,(int,float)) else ''}")
            return " / ".join(out)

        t3, b3 = _fmt(sa.get("top3")), _fmt(sa.get("bottom3"))
        if t3:
            lines.append(f"・米国セクター 強い順: {t3}")
        if b3:
            lines.append(f"・米国セクター 弱い順: {b3}")
        if isinstance(sa.get("ai_comment"), str) and len(sa["ai_comment"]) > 10:
            lines.append(f"・セクターAI所見: {sa['ai_comment'][:150]}")

    sr = sector_ranking or {}
    if sr.get("available"):
        rk = sr.get("ranking") or sr.get("sectors") or []
        ups, downs = [], []
        for it in rk:
            if isinstance(it, dict):
                nm = it.get("name") or it.get("sector") or ""
                ch = it.get("change_pct", it.get("chg_1d"))
                if nm and isinstance(ch, (int, float)):
                    (ups if ch >= 0 else downs).append(f"{nm}{ch:+.2f}%")
        if ups:
            lines.append("・日本の業種別 上昇上位: " + " / ".join(ups[:5]))
        if downs:
            lines.append("・日本の業種別 下落上位: " + " / ".join(downs[-5:]))

    return ("【セクター/業種データ】\n" + "\n".join(lines)) if lines else ""


def _market_extras_ctx(extras: dict) -> str:
    """経済指標・決算・大きく動いた銘柄・材料など、各モジュールの結果を
    プロンプト用の短いテキストに変換（分析を具体的にする核）。構造が違っても
    要約テキスト→ムーバーのリスト→HTMLの順に、防御的に中身を拾う。"""
    if not extras:
        return ""
    import re

    def _strip(h):
        t = re.sub(r"<[^>]+>", " ", str(h or ""))
        return re.sub(r"\s+", " ", t).strip()

    def _snippet(obj):
        if not isinstance(obj, dict) or not obj.get("available"):
            return ""
        # 1) 明示的な要約テキスト
        for k in ("summary", "text", "comment", "ai_comment", "headline",
                  "conclusion", "brief", "detail"):
            v = obj.get(k)
            if isinstance(v, str) and len(v.strip()) > 8:
                return v.strip()[:240]
        # 2) 銘柄ムーバー系のリスト（具体名＋変化率）
        for lk in ("movers", "gainers", "up", "ranking", "stocks", "items",
                   "top", "losers", "down", "list"):
            lst = obj.get(lk)
            if isinstance(lst, list) and lst:
                parts = []
                for it in lst[:5]:
                    if isinstance(it, dict):
                        nm = (it.get("name") or it.get("ticker") or it.get("symbol")
                              or it.get("code") or it.get("title") or "")
                        ch = it.get("change_pct", it.get("chg_1d", it.get("change")))
                        if nm:
                            suffix = f"({ch:+.1f}%)" if isinstance(ch, (int, float)) else ""
                            parts.append(f"{nm}{suffix}")
                if parts:
                    return " / ".join(parts)
        # 3) HTMLを素にする
        h = _strip(obj.get("html"))
        return h[:240] if len(h) > 12 else ""

    blocks = []
    for label, obj in extras.items():
        s = _snippet(obj)
        if s:
            blocks.append(f"・{label}: {s}")
    if not blocks:
        return ""
    return ("【今日の詳しい材料（経済指標・決算・大きく動いた銘柄・ニュース等）】\n"
            + "\n".join(blocks))


def generate_comments(prices: dict, risk: dict, fear_greed: dict,
                      ai_summary: dict = None, news: list = None,
                      sector: dict = None, sector_ranking: dict = None,
                      extras: dict = None) -> dict:
    """AIガネーシャとAIカワウソのコメントを生成

    ganesha/otter        = 詳細版（動画ナレーション・HTMLレポート・Telegram詳細用）
    ganesha_short/otter_short = ひとこと版（サマリーカード画像用・レイアウト崩れ防止）
    """
    result = {
        "ganesha": "",
        "otter": "",
        "ganesha_short": "",
        "otter_short": "",
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

    # ドル円（キー揺れに対応）＋ 状況を一言で（プロンプトの具体性を上げる）
    _fx = prices.get("JPY=X") or prices.get("USDJPY=X") or prices.get("ドル円") or {}
    usdjpy     = _fx.get("latest", 0) or 0
    usdjpy_chg = _fx.get("change_pct", 0) or 0
    _fx_note = "円安方向" if usdjpy_chg > 0.1 else ("円高方向" if usdjpy_chg < -0.1 else "ほぼ横ばい")
    _vix_note = "高く警戒" if vix >= 22 else ("やや高め" if vix >= 18 else "落ち着いている")

    # 分析力を最大化する追加素材（NASDAQ・米10年金利・AIチームの各論）
    nq_chg = prices.get("^IXIC", {}).get("change_pct", 0) or 0
    _t10 = prices.get("^TNX", {}).get("latest", 0) or 0
    us10y_str = f"{_t10:.2f}%" if 0 < _t10 < 20 else "—"
    _bits = []
    if ai_summary:
        for _k, _lbl in [("summary", "要約"), ("bull_view", "強気論"),
                         ("bear_view", "弱気論"), ("neutral_view", "中立論")]:
            _v = ai_summary.get(_k)
            if isinstance(_v, dict):
                _v = _v.get("point") or _v.get("text") or _v.get("summary")
            _v = str(_v or "").strip()
            if len(_v) > 15:
                _bits.append(f"・{_lbl}: {_v[:90]}")
    ai_context = ("【AIチーム分析メモ（参考）】\n" + "\n".join(_bits)) if _bits else ""

    # 今日の材料（ニュース見出し）— 分析の具体性を上げる
    _heads = []
    for n in (news or [])[:6]:
        t = (n.get("title") if isinstance(n, dict) else str(n)) or ""
        t = t.strip()
        if t:
            _heads.append(f"・{t[:70]}")
    news_ctx = ("【今日の主な材料（ニュース見出し）】\n" + "\n".join(_heads)) if _heads else ""
    sector_ctx = _sector_ctx(sector, sector_ranking)
    extras_ctx = _market_extras_ctx(extras)

    neut_view = ""
    if ai_summary and ai_summary.get("available"):
        neut_view = (ai_summary.get("neutral_view") or "")[:120]

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))

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
        ganesha_prompt = f"""あなたは「AIガネーシャ」。数十年の実戦を積んだ老練なマクロ・ストラテジストが、知恵の神ガネーシャの姿を借りて相場を語る——という設定です。
口調は「〜じゃ」「〜ですぞ」「〜であります」など古風で威厳ある調子。ただし中身は機関投資家水準の、洗練された語彙と鋭い洞察で。
今回の彩り: {ganesha_flavor}。

【必ず盛り込む分析の骨子（自然な文章に織り込む。箇条書きにはしない）】
1. 現状認識：主要指標の具体数値に触れる（VIX・ドル円・米株・日経・金利など）
2. 因果：なぜ今この地合いなのか、背景と主因を論理でつなぐ
3. 材料の読み：今日のニュース見出し・経済指標の結果・決算イベント・大きく動いた銘柄
   （国内外）が与えられていれば、必ず固有名や具体的な数値を挙げて、その意味と影響度を評価する。
   一般論で流さず「何が」「どれだけ」動いたかを具体的に述べること
4. 波及と目線：米国市場→日本株・為替への波及、寄り付きで意識される水準や方向感
5. 【最重要・厚く書く】セクター/物色戦略：与えられたセクターデータを必ず使い、
   (a) いま資金が向かっているセクターと、逃げているセクターを具体名と数値で挙げる
   (b) そのローテーションが景気サイクルのどの局面を示唆するのか解釈する
   (c) 米国のセクター動向が日本のどの業種に波及しやすいか、道筋をつけて説明する
   (d) 明日以降の物色の方向（グロース/バリュー、ディフェンシブ/シクリカル）を示す
   → この項目だけで全体の3分の1程度を割き、最も深く論じること
6. 需給とセンチメント：F&G・VIX・リスクスコアから市場心理を読む
7. 時間帯戦略：寄り付き・前場・後場で想定される値動きの型を述べる
9. 過去との類似：似た地合いの過去局面を引き、その後の展開の教訓を添える
10. リスク：見落とされがちな逆風、シナリオが崩れる条件を具体的に複数
11. 逆張りの視点：市場コンセンサスと逆の目線も一度だけ提示する
12. 着眼点：今日ひとつだけ最重要で注視すべきものを明示する
13. 相場格言をひとつだけ、文脈に品よく重ねて締める

状況に合致する相場用語（リスクオン/リスクオフ・ボラティリティ・押し目/戻り売り・需給・
イールドカーブ・タームプレミアム・センチメント・過熱感/リスクプレミアム・レンジ・節目・
キャリー・グロース/バリュー・ディフェンシブ・循環物色 など）を、正確に、文脈に合うものだけ用いる。
羅列・誤用は厳禁。断定は避け「〜の公算」「〜には一考の余地」など確度に応じた含みを持たせる。
絵文字は🐘のみ。

【出力形式（この2ブロックを必ずこの順で、見出し記号もそのまま出力）】
【詳細】
（ここに 1000〜1250字 の詳細分析。16〜20文。うちセクター/物色の論述に3分の1を割く。
　密度高く、具体的に、上記13項目をできるだけ盛り込む。ただし箇条書きにはせず、
　流れるような一続きの語りにし、途中で失速せず最後まで濃度を保つこと）
【ひとこと】
（ここに 90字以内 で今日の要点を1〜2文に凝縮）

【市場データ】
VIX={vix:.1f}（{_vix_note}） / S&P500={sp_chg:+.2f}% / NASDAQ={nq_chg:+.2f}% / 日経={nk_chg:+.2f}%
ドル円={usdjpy:.2f}（{usdjpy_chg:+.2f}%・{_fx_note}） / 米10年金利={us10y_str} / F&G={fg} / リスクスコア={rs:+.2f}
地合い: {sentiment}（{mood}）
{sector_ctx}
{extras_ctx}
{news_ctx}
{ai_context}

与えられた具体データ（指標・決算・動いた銘柄・材料）は積極的に固有名を挙げて引用すること。
老練なストラテジストの見識を、ガネーシャの威厳で、深く・長く・具体的に語ってください。"""

        ganesha_resp = model.generate_content(ganesha_prompt)
        g_long, g_short = _split_long_short(ganesha_resp.text)
        result["ganesha"] = g_long
        result["ganesha_short"] = g_short

        # ── カワウソのコメント ──
        otter_prompt = f"""あなたは「AIカワウソ」です。めちゃくちゃかわいいカワウソとして、今日の相場を超シンプルに通訳してください。
語尾は「〜だよ〜！」「〜なの〜♪」「〜してね！」のようなかわいい口調。
毎回ちがう言い回し・語尾を使って、ワンパターンにならないようにしてください。
今回は特に: {otter_flavor}。
【役割】ガネーシャの難しい話を、中学生にもわかる言葉に「通訳」すること。
今日のポイントを5つに分けて、順番にやさしく、たっぷり説明してください。
　①何が起きたの？（昨日の海外市場のできごと・経済指標の結果・大きなニュースを、
　　　具体的な数字や会社の名前も交えて。決算や大きく動いた銘柄があれば必ず名前を出してかわいく紹介）
　②どの業種が元気／元気ないの？（セクターの話を、身近な例えでかわいく。
　　　例:「半導体＝スマホやゲーム機の頭脳をつくる会社」のように必ず言い換える。強い業種と弱い業種の両方）
　③だから日本の株はどうなりそう？（どんな会社が上がりそうか、理由もセットで）
　④円やお金の流れはどうなってる？（円安/円高がどんな会社にうれしいか）
　⑤気をつけることは？（今日のリスクと、初心者さんへのやさしいアドバイス）
むずかしい専門用語（例: VIX・リスクオン/オフ・円安・押し目・ディフェンシブ など）を3〜4つ登場させ、
そのすぐ後に必ず「＝〜ってこと」と言い換えを添えること（用語を覚えてもらう役割）。
それ以外はやさしい言葉で。絵文字は5〜6個まで。

【出力形式（この2ブロックを必ずこの順で、見出し記号もそのまま出力）】
【詳細】
（ここに 560〜680字。11〜15文。5つのポイントを順にかわいく、たっぷり丁寧に説明）
【ひとこと】
（ここに 90字以内 で今日いちばん大事なことを1〜2文に凝縮）

市場状況: VIX={vix:.1f}（{_vix_note}） / 日経={nk_chg:+.2f}% / 米株(S&P)={sp_chg:+.2f}% / NASDAQ={nq_chg:+.2f}%
ドル円={usdjpy:.2f}（{usdjpy_chg:+.2f}%・{_fx_note}） / F&G={fg}
地合い: {sentiment}
{sector_ctx}
{extras_ctx}
{news_ctx}

具体的な会社名や指標の名前が材料にあれば、やさしく言い換えつつ実際に紹介してね。
カワウソらしくかわいく、5つのポイントをやさしく詳しく伝えてください。"""

        otter_resp = model.generate_content(otter_prompt)
        o_long, o_short = _split_long_short(otter_resp.text)
        result["otter"] = o_long
        result["otter_short"] = o_short
        result["available"] = True

        logger.info(f"✅ キャラクターコメント生成完了 [mood={mood}]")
        return result

    except Exception as e:
        logger.warning(f"キャラクターコメント生成エラー: {e}")
        result["ganesha"]       = _pick_fallback(_GANESHA_LINES, mood)
        result["otter"]         = _pick_fallback(_OTTER_LINES, mood)
        result["ganesha_short"] = result["ganesha"]
        result["otter_short"]   = result["otter"]
        result["available"]     = True
        return result


def _split_long_short(text: str):
    """Geminiの【詳細】【ひとこと】出力を (詳細, ひとこと) に分解"""
    import re
    t = (text or "").strip()
    m = re.search(r"【詳細】\s*(.+?)\s*【ひとこと】\s*(.+)", t, re.S)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    # マーカーが無い場合：全文を詳細とし、先頭1文をひとことに
    head = t.split("。")[0].strip()
    short = (head + "。") if head and not head.endswith("。") else head
    return t, short[:90]


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
