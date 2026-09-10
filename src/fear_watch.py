"""
恐怖指数の見張り（Step FW）— 毎日みて、異常なときだけ知らせる

なぜ必要か:
  既存の `risk_gauges` は恐怖指数を25種類も並べて監視しているが、
  判定しているのは **前日比だけ** である。日経VIのしきい値は±22.35%で、
  これは実測すると年9.2回の発報になり、較正としては妥当だった。

  ⚠️ しかし**水準をまったく見ていない**。
     日経VIが45（過去3年で上位1%の異常値）で1週間張り付いても、
     日々の変化が小さければ一度も鳴らない。
     実際 2026年8月17〜21日の週、日経平均は-4.63%下げたのに、
     計器はすべて静かなままだった。

  そこで「前日比」ではなく「**過去の中でどのあたりの水準にいるか**」で
  見張る。日経公式CSVが約900営業日ぶんの履歴を無料で返すので、
  パーセンタイルで判定できる。しきい値を人が決め直す必要がない。

較正（2026-09-10・日経VI 903営業日＝約3.7年で実測）:
  ・上位10%ゾーンに入った初日だけ数えると **年7.6回**
  ・上位5%ゾーンなら **年5.4回**
  これをゾーンの出入りで1回ずつ通知するので、
  年15回前後に収まる。プロジェクトの基準「年5〜15回」の範囲内。

ゾーンの「出入り」で判定する理由:
  水準そのもので毎回鳴らすと、高い水準が続く週は毎日鳴って読まれなくなる
  （上位10%に該当する日は年24.7日ある）。
  行動が変わるのは「入った日」と「出た日」だけなので、そこだけ知らせる。
  出た日＝「落ち着きました」も、待つべきか動くべきかの判断に必要なので送る。

日経VIとVIXを組で見る理由:
  ・日経VI … 日本株そのものの警戒度。**これが主**
  ・VIX    … 世界共通の話か、日本固有の話かの切り分け
  日本だけ跳ねているなら日本の材料（半導体・円・政策）であり、
  世界同時なら米国発の話になる。取るべき行動が変わる。

Gemini は使わない。水準の判定であって解釈ではないうえ、
枠が尽きた日にこそ知りたい情報だからである。
"""
import json
import traceback
from datetime import timedelta

from src.utils import setup_logger, get_jst_now, BASE_DIR

logger = setup_logger("fear_watch")

_STATE = BASE_DIR / "data" / "fear_watch_state.json"

# ── ゾーンの定義（過去の中での位置）────────────────────────
# (下限パーセンタイル, キー, 表示名, 絵文字)
_ZONES = [
    (95.0, "extreme", "異常に高い",  "🔴"),
    (90.0, "high",    "高い",        "🟠"),
    (75.0, "warm",    "やや高い",    "🟡"),
    (25.0, "normal",  "普通",        "⚪"),
    (0.0,  "calm",    "低い",        "🟢"),
]
# ゾーンの危険度の順番（小さいほど危険）。
# 現在の判定はパーセンタイルの数値で直接おこなうので使っていないが、
# ゾーンを増やして「悪化したら再通知」を入れる場合に必要になる。
_ORDER = {k: i for i, (_, k, _n, _e) in enumerate(_ZONES)}

# ── いつ知らせるか（実データ843営業日を流して較正）────────────
#
# ⚠️ 最初は「上位10%に入った初日」だけで年7.6回のはずだった。
#    ところが**実際に履歴を流したら年42.4回**になった。
#    見積りは履歴全体から固定したパーセンタイルで数えたもので、
#    本番（その日までの履歴で毎日計算）とは別物だった。
#
#    ログを見ると原因は明白で、境界線の上下でパタパタ鳴っていた:
#      7/17 入った → 7/22 出た → 7/23 入った → 7/24 出た …
#
#    そこで**入る線と出る線を分ける**（ヒステリシス）。
#    いったん入ったら、はっきり下がるまで「出た」と言わない。
#
# 較正結果（843営業日＝約3.4年）:
#   入る95 / 出る75 / 急騰25% → 入11回・出11回・急騰19回 = **年11.9回**
#   基準の「年5〜15回」に収まる。
_ENTER_PCT = 95.0    # 上位5%に入ったら知らせる
_EXIT_PCT  = 75.0    # 上位25%より下まで下がったら「落ち着いた」

# 前日比の急騰。水準に関わらず知らせる（年5.6回）。
# 下落側は「落ち着いた」という良い知らせなので、ゾーンの出入りで扱う。
_JUMP_PCT = 25.0

# 互換のため残す（notify_line などが参照する場合に備えて）
_ALERT_ZONES = {"extreme"}


def _zone(pctile):
    """パーセンタイルからゾーンを決める。"""
    if pctile is None:
        return None
    for lo, key, name, emoji in _ZONES:
        if pctile >= lo:
            return {"key": key, "name": name, "emoji": emoji}
    return None


def _session_key(now=None) -> str:
    """朝6時を境に1日とみなす（夜間の連続通知を1日と数えるため）。"""
    now = now or get_jst_now()
    return (now - timedelta(hours=6)).strftime("%Y-%m-%d")


def _load_state() -> dict:
    try:
        return json.loads(_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(st: dict) -> None:
    try:
        _STATE.parent.mkdir(parents=True, exist_ok=True)
        _STATE.write_text(json.dumps(st, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    except Exception:
        logger.debug(traceback.format_exc())


def run() -> dict:
    """
    恐怖指数の今の状態を返す。通知はしない（判定だけ）。

    返り値:
      available, nvi, nvi_chg, nvi_pctile, zone{key,name,emoji},
      vix, vix_chg, jump(bool), world(bool), message
    """
    out = {"available": False}
    try:
        from src.fetch_prices import _fetch_nikkei_vi
        d = _fetch_nikkei_vi() or {}
        nvi = d.get("latest")
        nvi_chg = d.get("change_pct")
        pct = d.get("pctile")
        if nvi is None:
            logger.warning("日経VIを取得できませんでした")
            return out

        z = _zone(pct)

        # VIXは切り分けのための補助。取れなくても止めない。
        vix = vix_chg = None
        try:
            from src.quote_util import quote
            q = quote("^VIX", rng="5d")
            if q:
                vix, vix_chg = q["price"], q["change_pct"]
        except Exception:
            logger.debug(traceback.format_exc())

        jump = nvi_chg is not None and nvi_chg >= _JUMP_PCT
        # 世界同時か日本固有か。VIXも一緒に跳ねていれば世界の話。
        world = vix_chg is not None and vix_chg >= 8

        return {"available": True, "nvi": nvi, "nvi_chg": nvi_chg,
                "nvi_pctile": pct, "zone": z, "history_days": d.get("history_days"),
                "vix": vix, "vix_chg": vix_chg,
                "jump": jump, "world": world}
    except Exception:
        logger.error("恐怖指数の判定に失敗", exc_info=True)
        return out


def _num(v, fmt=".1f", default="—"):
    """数値のときだけ書式を当てる。

    ⚠️ f"{v:.1f}" は v が None だと **TypeError で落ちる**。
       通知の本文を作る関数が落ちると、その通知は丸ごと届かない。
       取得できなかった値は「—」で埋めて、残りを届けるほうがよい。
    """
    if isinstance(v, (int, float)) and v == v:      # NaN も弾く
        return format(v, fmt)
    return default


def _explain(r: dict) -> list:
    """中学生でも分かる言葉で、今どういう状態かを説明する。"""
    nvi = r.get("nvi")
    pct = r.get("nvi_pctile")
    z = r.get("zone") or {}
    lines = []

    yrs = (r.get("history_days") or 0) // 245
    if isinstance(pct, (int, float)):
        lines.append(f"日経VI（日本株の恐怖指数）は *{_num(nvi)}*。"
                     + (f"過去約{yrs}年で上から{100.0 - pct:.0f}%の高さです。"
                        if yrs else f"過去の分布で上から{100.0 - pct:.0f}%の高さです。"))
    else:
        lines.append(f"日経VI（日本株の恐怖指数）は *{_num(nvi)}* です。")

    if isinstance(r.get("nvi_chg"), (int, float)):
        lines.append(f"前日からの変化は *{_num(r['nvi_chg'], '+.1f')}%*。")

    # 恐怖指数が何を意味するかを毎回添える。用語だけでは伝わらない。
    lines.append("恐怖指数は「これから株価がどれだけ荒れそうか」を"
                 "投資家がお金を賭けて見積もった数字です。"
                 "高いほど、上下どちらにも大きく振れやすい状態を表します。")

    if r.get("world"):
        lines.append("米国のVIXも同時に上がっているので、"
                     "**世界共通の不安**が広がっています。")
    elif isinstance(r.get("vix"), (int, float)):
        lines.append(f"一方で米国のVIXは {_num(r['vix'])}"
                     f"（{_num(r.get('vix_chg'), '+.1f')}%）で、"
                     "**日本側固有の材料**の可能性があります。")

    # ⚠️ 危険水準の説明は**1つだけ**にする。
    #    extreme と high で別々に足すと、片方の条件を広げたときに
    #    2段とも出て同じことを二度言う文になる（一度やらかした）。
    if z.get("key") in ("extreme", "high"):
        lines.append("この水準になると値動きが普段より荒くなります。"
                     "**同じ株数で売買しても、損得の振れ幅が大きくなります。**"
                     "いつもより株数を減らす、損切りの逆指値を普段より広めに置く、"
                     "落ち着くまで待つ——このどれかを選ぶ場面です。")
    return lines


def build_message(r: dict, kind: str) -> str:
    """
    kind: "enter"（危険ゾーンに入った）/ "exit"（出た）/ "jump"（急騰）
    """
    z = r.get("zone") or {}
    if kind == "exit":
        head = "🟢 *恐怖指数が落ち着きました*"
    elif kind == "jump":
        head = f"⚡ *恐怖指数が急上昇*（前日比 {_num(r.get('nvi_chg'), '+.1f')}%）"
    else:
        head = f"{z.get('emoji', '⚠️')} *恐怖指数が{z.get('name', '高い')}水準です*"

    lines = [head, "━━━━━━━━━━━━━━", ""]
    if kind == "exit":
        pct = r.get("nvi_pctile")
        lines.append(f"日経VIは *{_num(r.get('nvi'))}* まで下がり、"
                     f"警戒しておく水準から抜けました"
                     + (f"（過去の下から{pct:.0f}%の位置）。"
                        if isinstance(pct, (int, float)) else "。"))
        lines.append("")
        lines.append("荒れやすい時期はいったん終わりました。"
                     "ただし恐怖指数は下がるときは一気に下がるので、"
                     "また跳ねることもあります。")
    else:
        lines += _explain(r)

    lines += ["", "※恐怖指数の水準を過去約3年の分布と比べて、"
                  "普段と違うときだけお知らせしています"]
    return "\n".join(lines)


def run_fear_alert() -> bool:
    """
    monitor_run.py から呼ぶ。毎回みて、状態が変わったときだけ送る。

    ゾーンの出入りで1回ずつしか送らないので、
    高い水準が続く週に毎日鳴ることはない。
    """
    try:
        r = run()
        if not r.get("available"):
            return False
        z = r.get("zone") or {}
        zk = z.get("key")
        if not zk:
            return False

        st = _load_state()
        sess = _session_key()
        pct = r.get("nvi_pctile")
        # 位置が取れない日は判定しない。水準の話なので、位置が無いと
        # 「異常かどうか」を言えない（前日比だけで異常と呼ぶと鳴りすぎる）。
        if pct is None:
            logger.info("恐怖指数: 過去との比較ができないため判定を見送ります")
            return False

        was_in = bool(st.get("in_alert"))

        kind = None
        if r.get("jump") and st.get("jump_session") != sess:
            # 急騰は水準に関わらず知らせる。ただし1日1回まで。
            kind = "jump"
        elif not was_in and pct >= _ENTER_PCT:
            kind = "enter"
        elif was_in and pct <= _EXIT_PCT:
            kind = "exit"

        # ⚠️ 入る線と出る線の間（75〜95）にいる間は、入っていた状態を保つ。
        #    ここを毎回 pct>=95 で上書きすると、96→94 と少し下がっただけで
        #    「出た」ことになり、また上がったら「入った」と鳴る。
        #    それが年42回のパタパタの原因だった。
        now_in = was_in
        if kind == "enter":
            now_in = True
        elif kind == "exit":
            now_in = False

        # 状態は毎回記録する。通知しなくても位置は追い続ける。
        new_st = {"in_alert": now_in, "zone": zk, "pctile": pct,
                  "nvi": r.get("nvi"), "at": get_jst_now().isoformat(),
                  "jump_session": st.get("jump_session")}

        if not kind:
            logger.info(f"恐怖指数: 日経VI {r['nvi']:.1f}"
                        f"（{z.get('name')}・上から"
                        f"{100 - (r.get('nvi_pctile') or 0):.0f}%）変化なし")
            _save_state(new_st)
            return False

        if kind == "jump":
            new_st["jump_session"] = sess

        from src.notify_telegram import send_message
        # ⚠️ FXグループではなくメインへ送る。日経VIは**日本株**の恐怖指数で、
        #    株を持ち続けるか・株数を減らすかという判断に直接効く。
        #    為替・マクロをFXグループに分けている方針とは別の話。
        ok = send_message(build_message(r, kind))
        if ok:
            logger.info(f"✅ 恐怖指数アラート送信（{kind}・"
                        f"日経VI {r['nvi']:.1f}／{z.get('name')}）")
            _save_state(new_st)
        else:
            # 送れていないのに状態を進めると、次回「もう知らせた」と
            # 判断して**永久に届かない**。送信できた時だけ記録する。
            logger.error("恐怖指数アラートの送信に失敗しました（状態は更新しません）")
        return bool(ok)
    except Exception:
        logger.error("恐怖指数アラートの処理に失敗", exc_info=True)
        return False


def notify_line(r: dict = None) -> str:
    """朝の通知に1行だけ載せる用（毎日みている、を見える形にする）。"""
    r = r or run()
    if not r.get("available"):
        return ""
    z = r.get("zone") or {}
    pct = r.get("nvi_pctile")
    pos = f"上から{100 - pct:.0f}%" if isinstance(pct, (int, float)) else ""
    return (f"{z.get('emoji', '')} *恐怖指数* 日経VI {_num(r.get('nvi'))}"
            f"（{z.get('name', '')}{'・' + pos if pos else ''}）")


if __name__ == "__main__":
    import io
    import sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace")
    r = run()
    if not r.get("available"):
        print("取得できませんでした")
    else:
        z = r["zone"]
        print(f"日経VI {r['nvi']:.1f}  前日比 {r['nvi_chg']:+.1f}%")
        print(f"位置    下から{r['nvi_pctile']:.1f}%"
              f"（上から{100 - r['nvi_pctile']:.1f}%）／履歴{r['history_days']}日")
        print(f"ゾーン  {z['emoji']} {z['name']}（{z['key']}）")
        print(f"VIX     {r.get('vix')}（{r.get('vix_chg')}%）"
              f" 世界同時={r.get('world')} 急騰={r.get('jump')}")
        print()
        print("■ 通知に載せる1行")
        print(" ", notify_line(r))
        print()
        for k in ("enter", "jump", "exit"):
            print(f"■ {k} のときの本文")
            print(build_message(r, k))
            print()
