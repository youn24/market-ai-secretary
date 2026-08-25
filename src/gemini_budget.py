"""
Gemini予算（Step BUDGET）— 1日20回の無料枠を、価値の高い順に配る

なぜ必要か:
  2026-08-25の本番ログで、Geminiの無料枠が
  **1日20回**（limit: 20, model: gemini-2.5-flash）と判明した。
  一方でGeminiを呼ぶモジュールは35個まで増えていた。

  その結果、朝8:05に枠が尽き、それ以降のAI機能が全滅していた。
  問題は「枠が足りない」ことより、**cloud_run での並び順だけで
  勝ち負けが決まっていた**ことにある。
  たまたま後ろに置かれた材料分析や予測の学習が、毎日必ず落ちる。
  分析の価値ではなく、記述順が結果を決めていた。

考え方:
  ・**コードは消さない。** 呼ぶかどうかだけをここで決める。
    消すと戻せないが、この表なら1行変えれば戻る
  ・**価値の高い順に先に確保する。** 余りを下位に回す
  ・**曜日で散らす。** 重い分析を月曜に集中させない
  ・**予備を残す。** 急変アラートと14時のFXも同じ枠を使うため、
    朝の実行で使い切ると、肝心の急変時にAIコメントが出せない

⚠️ ここで止めたモジュールは「動かない」のではなく「今日は順番が来ない」。
   翌日には回ってくる。完全に不要なものは OFF に置いてある。
"""
import json
import os
import traceback
from datetime import timedelta

from src.utils import setup_logger, get_jst_now, BASE_DIR

logger = setup_logger("gemini_budget")

_STATE = BASE_DIR / "data" / "gemini_budget.json"

# 無料枠の実測値。将来Googleが変えたら環境変数で追従できるようにしておく。
DAILY_LIMIT = int(os.getenv("GEMINI_DAILY_LIMIT", "20"))

# 急変アラート・14時FX・夜の振り返り用に空けておく分。
# 朝の実行で使い切ると、いちばん知らせてほしい急変時に何も出せなくなる。
RESERVE = int(os.getenv("GEMINI_RESERVE", "4"))

# 出力トークンの上限。実測(scripts/measure_prompts.py)では入力は
# 全モジュール合計で2,798トークンしかなく、入力側は問題ではなかった。
# 一方 max_output_tokens はどこにも設定されておらず伸び放題だった。
# 各プロンプトは「150文字以内」等と指示しているので、日本語500字＝約280トークン。
# 2048は十分な余裕がありつつ、暴走を止められる高さ。
# ⚠️ 下げすぎると出力が途中で切れ、JSONの解析失敗などの
#    「静かに壊れる」形になるので、切り詰めすぎないこと。
MAX_OUTPUT = int(os.getenv("GEMINI_MAX_OUTPUT", "2048"))

# ── 毎日動かすもの（届いていて、かつ中身が重ならないもの）──────
# 数字は「1回の実行で使う想定の回数」。実測に合わせて調整する。
CORE = {
    # 2026-08-25: ai_debate(3)・scenario(1)・market_driver(1) の計5回を
    # ai_brief の1回に統合した。同じ材料を見て解釈を書く仕事が5回に
    # 分かれていただけで、まとめても内容は落ちない。
    # 実測: 6回2,798トークン → 1回537トークン。
    "ai_brief":           1,   # 3視点＋3シナリオ＋変動要因を1回で
    "technical_ai":       1,   # テクニカル解釈（入力が別系統なので分けたまま）
    "prediction_tracker": 1,   # 予測の検証。唯一、効果を実測した仕組み
}

# ── 統合が失敗したときの受け皿 ───────────────────────
# 通常は呼ばれない。ai_brief が応答を返せなかった日だけ、
# cloud_run が個別版へ落ちる。**予定回数には数えない**
# （数えると毎日「17回使う予定」と見えてしまい、実態とずれる）。
FALLBACK = {
    "ai_debate":     3,
    "scenario":      1,
    "market_driver": 1,
}

# ── 余裕があれば動かすもの ────────────────────────────
NICE = {
    "character_commentary": 2,  # キャラクター会話。オーナーが気に入っている表示
    "catalyst_analyzer":    3,  # 材料分析。銘柄数ぶん使うので上限を切る
    "sector_analysis":      1,  # セクターローテーション
}

# ── 曜日で散らすもの（重い分析。1日1つだけ順番が来る）──────────
# 月曜に5つ重なって全滅していたのを、1つずつに分けた。
# 週1回になるが、もともと週次の性質の分析なので頻度は足りている。
BY_WEEKDAY = {
    0: ("theme_ranker",       3),   # 月 テーマ株ランキング
    1: ("supply_demand",      3),   # 火 需給分析
    2: ("financial_analyzer", 3),   # 水 財務・決算書分析
    3: ("jquants_screener",   3),   # 木 日本株スクリーナー
    4: ("economic_calendar",  3),   # 金 来週の経済カレンダー
    5: ("fomc_sentiment",     2),   # 土 FOMC議事録
    6: ("note_article",       1),   # 日 note記事
}

# ── 止めるもの ────────────────────────────────────
# 「動かない」のではなく「Geminiを使わない」。理由を必ず書く。
# 2026-08-25に**コードごと削除**したもの（記録として残す）:
#   multi_agent_consensus … ai_debate と同じ「複数AIで多数決」。二重払い
#   self_critique         … prediction_tracker の振り返りと重複
#   macro_summary         … market_driver と重複
#   autonomous_orchestrator … 内部処理で、利用者に届く出力が無かった
#   multimodal_analysis   … チャート画像の解釈。効果未検証
#   ai_memory の Gemini分析 … 出力先がバックアップHTMLのみ
#     （update_memory による学習データの記録は残してある）
#   ai_gemini / investment_tutor / news_bias_detector / weekly_performance
#     … どこからも呼ばれていなかった
# いずれも git 履歴には残っているので、必要になれば復元できる。

# ── 残してあるが今は呼ばないもの ────────────────────
# 消していないのは「時期が来れば価値がある」ため。
OFF = {
    "economic_indicators": "market_driver の入力用。market_driver 自身がニュースを読むので無くても成立",
    "youtube_summary":     "動画要約。最大10回使うわりに、朝の判断に効かない",
    "earnings_brief":      "決算PDF要約。**決算期には価値があるので消していない**",
    "earnings_preview":    "同上。決算シーズンに戻す場合はこの2行を消す",
}


def _key(now=None) -> str:
    """JST 6時始まり。夜間の実行が前日ぶんに数えられないようにする。"""
    now = now or get_jst_now()
    return (now - timedelta(hours=6)).strftime("%Y-%m-%d")


def _load() -> dict:
    try:
        d = json.loads(_STATE.read_text(encoding="utf-8"))
        if d.get("day") != _key():
            return {"day": _key(), "used": 0, "by": {}}
        return d
    except Exception:
        return {"day": _key(), "used": 0, "by": {}}


def _save(d: dict) -> None:
    try:
        _STATE.parent.mkdir(parents=True, exist_ok=True)
        _STATE.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    except Exception:
        logger.debug(traceback.format_exc())


def remaining() -> int:
    return max(0, DAILY_LIMIT - _load().get("used", 0))


def should_run(module: str, now=None) -> bool:
    """
    このモジュールを今日呼んでよいか。

    予算を実際に減らすのは spend()。ここは「順番が来ているか」の判定のみ。
    判定と計上を分けているのは、モジュールが内部で失敗して1回も呼ばずに
    終わることがあり、その場合まで予算を引くと枠を無駄にするため。
    """
    if module in OFF:
        logger.info(f"⏭ {module}: 停止中（{OFF[module]}）")
        return False

    now = now or get_jst_now()
    wd = now.weekday()

    if module in CORE:
        need = CORE[module]
    elif module in FALLBACK:
        need = FALLBACK[module]
    elif module in NICE:
        need = NICE[module]
    else:
        day_mod, day_need = BY_WEEKDAY.get(wd, (None, 0))
        if module != day_mod:
            # 曜日表に載っているが今日ではない
            if any(module == m for m, _ in BY_WEEKDAY.values()):
                when = [d for d, (m, _) in BY_WEEKDAY.items() if m == module]
                names = "月火水木金土日"
                logger.info(f"⏭ {module}: 今日は順番待ち"
                            f"（{'・'.join(names[d] for d in when)}曜に実行）")
                return False
            # 表に無いものは想定外。止めずに通すが、必ず記録に残す
            logger.warning(f"{module}: 予算表に未登録。とりあえず通します")
            need = 1
        else:
            need = day_need

    st = _load()
    used = st.get("used", 0)

    # 中核と受け皿だけが予備枠まで使える。
    # 統合が失敗した日に受け皿まで止めると、朝の中身が丸ごと消えてしまう。
    cap = (DAILY_LIMIT if module in CORE or module in FALLBACK
           else DAILY_LIMIT - RESERVE)
    if used + need > cap:
        logger.warning(f"⏭ {module}: 予算不足でスキップ"
                       f"（使用{used}/{DAILY_LIMIT}・必要{need}・上限{cap}）")
        return False
    return True


def spend(module: str, n: int = None) -> None:
    """実際に呼んだぶんを計上する。モジュールの実行直後に呼ぶ。"""
    if n is None:
        n = (CORE.get(module) or FALLBACK.get(module) or NICE.get(module)
             or dict(BY_WEEKDAY.values()).get(module, 1))
    st = _load()
    st["used"] = st.get("used", 0) + int(n)
    st.setdefault("by", {})[module] = st["by"].get(module, 0) + int(n)
    _save(st)
    logger.info(f"💰 Gemini予算: {module} が{n}回使用 → "
                f"合計 {st['used']}/{DAILY_LIMIT}（残り{remaining()}）")


class BudgetExceeded(RuntimeError):
    """予算のため呼ばなかった。障害ではないので、文面でそれと分かるようにする。"""


def install() -> bool:
    """
    Gemini の呼び出し口を1か所で押さえる。

    なぜこの形にしたか:
      generate_content の呼び出しは35モジュール・50箇所以上に散っている。
      1つずつ判定を書き足すと、必ずどこかで書き忘れる。
      そして書き忘れた1つが枠を食い切ると、全体が今日と同じ状態に戻る。

      呼び出し口を包めば、新しいモジュールが増えても自動的に対象になる。
      呼び出した本人を stack から特定するので、各所に引数を足す必要もない。

    cloud_run / monitor_run の最初に一度だけ呼ぶ。
    """
    try:
        import google.generativeai as genai
    except Exception:
        logger.info("google-generativeai が無いため予算管理は無効")
        return False

    GM = genai.GenerativeModel
    if getattr(GM, "_budget_installed", False):
        return True
    orig = GM.generate_content

    def guarded(self, *a, **kw):
        mod = _caller()
        if not should_run(mod):
            raise BudgetExceeded(f"Gemini予算のためスキップ（{mod}）")
        st = _load()
        if st.get("used", 0) >= DAILY_LIMIT:
            raise BudgetExceeded(f"本日のGemini枠を使い切りました（{DAILY_LIMIT}回）")

        # 出力の上限を全呼び出しに一律でかける。
        # 2026-08-25時点で max_output_tokens はどのモジュールにも
        # 設定されておらず、出力が伸び放題だった。
        # プロンプトは「150文字以内で」等と指示しているので実際は短いが、
        # 指示が無視された1回で無駄に使うのを防ぐ意味がある。
        # 呼び出し側が自分で指定している場合は尊重する（上書きしない）。
        if kw.get("generation_config") is None:
            kw["generation_config"] = {"max_output_tokens": MAX_OUTPUT}

        try:
            return orig(self, *a, **kw)
        finally:
            # 成否に関わらず1回ぶん消費される。失敗時に数えないと
            # 「使っていないつもりで使い切る」状態に戻る。
            _bump(mod, 1)

    GM.generate_content = guarded
    GM._budget_installed = True
    logger.info(f"✅ Gemini予算管理を有効化（1日{DAILY_LIMIT}回・"
                f"予備{RESERVE}回・残り{remaining()}回）")
    return True


def _bump(module: str, n: int = 1) -> None:
    st = _load()
    st["used"] = st.get("used", 0) + n
    st.setdefault("by", {})[module] = st["by"].get(module, 0) + n
    _save(st)


def _caller() -> str:
    """どのモジュールが呼んだかを stack から特定する。"""
    import inspect
    try:
        for fr in inspect.stack()[1:14]:
            m = fr.frame.f_globals.get("__name__", "")
            if m.startswith("src.") and m != "src.gemini_budget":
                return m.split(".")[-1]
            if m in ("cloud_run", "monitor_run", "weekly_run",
                     "fx_noon_run", "evening_run"):
                return m
    except Exception:
        pass
    return "unknown"


def plan(now=None) -> dict:
    """今日どれが動く予定かを返す。レポートやログで見せるため。"""
    now = now or get_jst_now()
    wd = now.weekday()
    day_mod, day_need = BY_WEEKDAY.get(wd, (None, 0))
    return {
        "limit": DAILY_LIMIT, "reserve": RESERVE,
        "core": CORE, "nice": NICE,
        "today_extra": day_mod, "today_extra_cost": day_need,
        "off": list(OFF),
        "planned_total": sum(CORE.values()) + sum(NICE.values()) + day_need,
        "used": _load().get("used", 0),
    }


if __name__ == "__main__":
    import io
    import sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace")
    p = plan()
    names = "月火水木金土日"
    print(f"■ Gemini予算  1日{p['limit']}回（うち予備{p['reserve']}回）")
    print(f"  今日は{names[get_jst_now().weekday()]}曜")
    print("─" * 50)
    print(f"  毎日（中核）      {sum(p['core'].values()):>2}回  "
          f"{'・'.join(p['core'])}")
    print(f"  毎日（余裕あれば）{sum(p['nice'].values()):>2}回  "
          f"{'・'.join(p['nice'])}")
    print(f"  今日の当番        {p['today_extra_cost']:>2}回  {p['today_extra']}")
    print("─" * 50)
    print(f"  合計予定 {p['planned_total']}回 / {p['limit']}回  "
          f"（本日使用 {p['used']}回）")
    if p["planned_total"] > p["limit"]:
        print("  ⚠️ 予定が上限を超えています。表を見直してください")
    print(f"\n  停止中 {len(p['off'])}件:")
    for m in p["off"]:
        print(f"    ・{m}  … {OFF[m]}")
