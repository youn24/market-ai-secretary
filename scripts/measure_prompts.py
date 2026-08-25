"""
Geminiに送っているプロンプトの実サイズを、APIを呼ばずに測る

なぜ必要か:
  無料枠は「1日20回」と「25万トークン」の2つで縛られている。
  どちらに効く手を打つべきかは、実際に何をどれだけ送っているかを
  見ないと決められない。勘で短くしても効かない場所を削るだけになる。

やり方:
  generate_content を差し替えて、**プロンプトを記録するだけで
  APIは呼ばない**。こうすれば1回も枠を使わずに全モジュールを測れる。
  戻り値はダミーを返すので、呼び出し側は「AIが答えなかった」として
  静かに終わる（実害なし）。

  日本語は1トークンおよそ1.8文字なので、そこから概算する
  （正確な数はAPIの count_tokens で出せるが、それ自体に通信が要る）。

使い方:
  python -m scripts.measure_prompts
"""
import io
import sys
import time
import traceback

# 日本語まじりの文章で1トークンあたりおよそ何文字か。
# 英数字だけなら4文字/トークン前後だが、日本語は1〜2文字で1トークンになる。
# 節約の効果を過大評価しないよう、辛め（少なめ）に見積もる。
_CHARS_PER_TOKEN = 1.8

_LOG = []


def _fake_key():
    """
    各モジュールは GEMINI_API_KEY が無いと generate_content まで到達せず
    早期returnする。APIは実際には呼ばないので、測定用のダミーを入れる。
    """
    import os
    if not os.getenv("GEMINI_API_KEY", "").strip():
        os.environ["GEMINI_API_KEY"] = "MEASURE_ONLY_NOT_A_REAL_KEY"
        print("（GEMINI_API_KEY 未設定のため測定用ダミーを使用。API通信は行いません）")


def _install_recorder():
    """generate_content を記録専用に差し替える。APIは呼ばない。"""
    import google.generativeai as genai

    class _Dummy:
        text = ""
        parts = []
        candidates = []

    def recorder(self, contents, *a, **kw):
        try:
            if isinstance(contents, str):
                text = contents
            elif isinstance(contents, (list, tuple)):
                text = "\n".join(str(c) for c in contents)
            else:
                text = str(contents)
        except Exception:
            text = ""

        import inspect
        mod = "unknown"
        try:
            for fr in inspect.stack()[1:14]:
                m = fr.frame.f_globals.get("__name__", "")
                if m.startswith("src.") and m != "src.gemini_budget":
                    mod = m.split(".")[-1]
                    break
        except Exception:
            pass

        _LOG.append({"module": mod, "chars": len(text),
                     "tokens": int(len(text) / _CHARS_PER_TOKEN),
                     "has_config": bool(kw.get("generation_config")),
                     "head": text[:80].replace("\n", " ")})
        return _Dummy()

    genai.GenerativeModel.generate_content = recorder
    # 予算管理が先に差し込まれていると記録側が呼ばれないので目印を消す
    genai.GenerativeModel._budget_installed = False


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace")
    _fake_key()
    _install_recorder()

    print("プロンプトの実サイズを測定します（APIは呼びません）\n")

    # 実データを一度だけ取る。各モジュールへ渡して本番同様に組み立てさせる。
    from src.fetch_prices import run as fp
    from src.fetch_news import run as fn
    from src.indicators import calc_risk_score
    prices, fg = fp()
    news = fn()
    risk = calc_risk_score(prices)

    # cloud_run.py と同じ引数で呼ぶ。違う呼び方をすると
    # プロンプトに入る情報量が変わり、測る意味がなくなる。
    ai_summary = {}
    scen = {}

    def _debate():
        from src.ai_debate import run_ai_debate
        return run_ai_debate(prices, news, risk, fg)

    def _scen():
        from src.scenario import run as r
        return r(prices, risk, fg, news)

    def _tech():
        from src.technical_ai import run as r
        return r()

    def _md():
        from src.market_driver import run as r
        return r(prices, news, {"available": False},
                 {"available": False}, {"available": False})

    def _pt():
        from src.prediction_tracker import run as r
        return r(prices, risk, fg, news, ai_summary, scen)

    targets = [("ai_debate", _debate), ("scenario", _scen),
               ("technical_ai", _tech), ("market_driver", _md),
               ("prediction_tracker", _pt)]

    for name, fn_ in targets:
        n0 = len(_LOG)
        t0 = time.time()
        try:
            fn_()
        except Exception:
            print(f"  ({name}: 実行時に例外。プロンプトは記録済みなら計上されます)")
            traceback.print_exc(limit=1)
        got = _LOG[n0:]
        if not got:
            print(f"  {name:22} 呼び出しなし")
            continue
        tot = sum(g["tokens"] for g in got)
        print(f"  {name:22} {len(got):>2}回  "
              f"合計 {tot:>6,}トークン  ({time.time()-t0:.1f}秒)")
        for g in got:
            print(f"      ・{g['tokens']:>6,}トークン  {g['head'][:52]}")

    print("\n" + "=" * 62)
    total = sum(g["tokens"] for g in _LOG)
    print(f"合計 {len(_LOG)}回 / {total:,}トークン（入力のみ）")
    cfg = sum(1 for g in _LOG if g["has_config"])
    print(f"出力上限(generation_config)を指定している呼び出し: {cfg}/{len(_LOG)}")
    if cfg == 0:
        print("  ⚠️ 1つも指定されていません。出力トークンが伸び放題です。")
    print("\n■ 消費の多い順")
    for g in sorted(_LOG, key=lambda x: -x["tokens"])[:10]:
        print(f"  {g['tokens']:>7,}トークン  {g['module']:20} {g['head'][:40]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
