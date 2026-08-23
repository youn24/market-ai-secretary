"""
通知メーター（Step METER）— 何通送っているかを記録し、暴走だけを止める

なぜ必要か:
  通知を送りうるモジュールが19個まで増えた。各モジュールは「1日1回」の
  上限を自前で持つが、**全体で何通になるかは誰も見ていなかった**。
  台帳（notify_ledger）は当日分しか残らないため、履歴も追えない。

  大きく動いた日には11の入口が同時に反応しうる。定期便3通と合わせて
  最大15通。そしてそれは、いちばん落ち着いて読んでほしい日に起きる。

なぜ「抑制」ではなく「記録」から始めるか:
  通知を黙って捨てるのは、この案件で何度も痛い目に遭った
  「静かに壊れる」構図そのものである（[[silent-failure-lessons]]）。
  多すぎるかどうかは実測してから判断すべきで、勘で絞ると
  肝心な通知を消してしまう。

  そこでまず全通知を記録する。数週間ぶんの実績が貯まれば、
  「どの入口が何通出しているか」「同じ日に重なるのはどれか」が分かり、
  根拠を持って減らせる。

例外は暴走だけ:
  ループのバグで同じ通知が何十通も飛ぶ事故は、記録を待つ意味がない。
  1セッションの上限を**普段は絶対に当たらない高さ**（既定30通）に置き、
  そこを超えたときだけ止める。これは「絞り込み」ではなく安全弁である。
"""
import json
import os
import traceback
from datetime import timedelta

from src.utils import setup_logger, get_jst_now, BASE_DIR

logger = setup_logger("notify_meter")

_HIST_FILE = BASE_DIR / "data" / "notify_history.json"

# 安全弁。通常運用（最大でも15通程度）では当たらない高さにする。
# ここに当たるのは実質「バグで暴走した」ときだけ。
_HARD_CAP = int(os.getenv("NOTIFY_HARD_CAP", "30"))

# 履歴の保持日数。長く持っても判断には使わないので、軽さを優先する。
_KEEP_DAYS = 60


def _session_key(now=None) -> str:
    """JST 6時始まり。夜間の通知が日付をまたいでも同じ日として数える。"""
    now = now or get_jst_now()
    return (now - timedelta(hours=6)).strftime("%Y-%m-%d")


def _load() -> dict:
    try:
        d = json.loads(_HIST_FILE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save(d: dict) -> None:
    try:
        _HIST_FILE.parent.mkdir(parents=True, exist_ok=True)
        _HIST_FILE.write_text(json.dumps(d, ensure_ascii=False),
                              encoding="utf-8")
    except Exception:
        # 記録に失敗しても通知そのものは止めない。
        # 「測るための仕組み」が本業を壊しては本末転倒。
        logger.debug(traceback.format_exc())


def _prune(d: dict) -> dict:
    keys = sorted(d.keys())
    return {k: d[k] for k in keys[-_KEEP_DAYS:]} if len(keys) > _KEEP_DAYS else d


def _caller() -> str:
    """
    どのモジュールが送ったかを、呼び出し元をたどって推定する。
    各所に引数を足して回るより確実で、付け忘れも起きない。
    """
    import inspect
    try:
        for fr in inspect.stack()[1:12]:
            mod = fr.frame.f_globals.get("__name__", "")
            if mod.startswith("src.") and mod not in (
                    "src.notify_meter", "src.notify_telegram"):
                return mod.split(".")[-1]
            if mod in ("__main__", "cloud_run", "monitor_run"):
                return mod
    except Exception:
        pass
    return "unknown"


def allow(kind: str = "text") -> bool:
    """
    送ってよいか。安全弁に当たったときだけ False を返す。
    ここで False になるのは異常事態なので、必ず error で記録を残す。
    """
    try:
        d = _load()
        cnt = len((d.get(_session_key()) or {}).get("sent", []))
        if cnt >= _HARD_CAP:
            logger.error(
                f"🚨 通知の安全弁が作動: 本日すでに{cnt}通。"
                f"上限{_HARD_CAP}通を超えたため送信を止めました。"
                f"どこかで通知が繰り返し発火している可能性があります。")
            return False
        return True
    except Exception:
        logger.debug(traceback.format_exc())
        return True      # 判定に失敗したら通す。止める方が危ない


def record(kind: str = "text", ok: bool = True, source: str = "") -> None:
    """1通ぶんの実績を残す。中身は残さない（個別の文面は追わない）。"""
    try:
        d = _prune(_load())
        sk = _session_key()
        day = d.setdefault(sk, {"sent": []})
        day["sent"].append({
            "t": get_jst_now().strftime("%H:%M"),
            "src": source or _caller(),
            "kind": kind,
            "ok": bool(ok),
        })
        _save(d)
    except Exception:
        logger.debug(traceback.format_exc())


def stats(days: int = 14) -> dict:
    """
    直近の通知実績。レポートに載せて「多すぎないか」を目で確かめるため。
    通知で知らせると、通知を減らす話なのに通知が増えて本末転倒になる。
    """
    try:
        d = _load()
        keys = sorted(d.keys())[-days:]
        if not keys:
            return {"available": False}

        per_day, by_src = {}, {}
        for k in keys:
            items = (d.get(k) or {}).get("sent", [])
            per_day[k] = len(items)
            for it in items:
                s = it.get("src", "unknown")
                by_src[s] = by_src.get(s, 0) + 1

        total = sum(per_day.values())
        vals = list(per_day.values())
        return {
            "available": True,
            "days": len(keys),
            "total": total,
            "avg": round(total / len(keys), 1),
            "max": max(vals),
            "max_day": max(per_day, key=per_day.get),
            "per_day": per_day,
            "by_source": dict(sorted(by_src.items(),
                                     key=lambda x: -x[1])),
            "cap": _HARD_CAP,
        }
    except Exception:
        logger.error("通知実績の集計に失敗", exc_info=True)
        return {"available": False}


if __name__ == "__main__":
    import io
    import sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace")
    s = stats()
    if not s.get("available"):
        print("まだ記録がありません（次回の通知から貯まります）")
    else:
        print(f"直近{s['days']}日 / 合計{s['total']}通 / "
              f"1日平均{s['avg']}通 / 最多{s['max']}通（{s['max_day']}）")
        print("─" * 46)
        for src, n in s["by_source"].items():
            print(f"  {src:26} {n:>4}通")
