"""
実行記録（Step REC）— 「ログが見られない環境」でも原因を追えるようにする

背景:
  公開レポートが更新されない障害を追ううえで、最大の壁は
  GitHub Actions のログが認証なしでは読めないことだった。
  ジョブは success、ステップも全部 success。それでも成果物は生まれていない。
  ログの中にしか手がかりがないのに、そのログに手が届かない。

解決:
  実行のたびに「何が起きたか」をリポジトリ内のJSONへ残し、workflowが
  それをコミットする。次回以降は git から読むだけで、どのStepが失敗し、
  どんな例外だったのかが分かる。ログを開かなくても追跡できる状態にする。

使い方:
    from src.run_recorder import record, save
    record("Step 7a2", ok=False, detail="TypeError: ...")
    save(mode="morning")     # 実行の最後に一度だけ
"""
import json
import traceback
from pathlib import Path
from src.utils import setup_logger, get_jst_now, BASE_DIR

logger = setup_logger("run_recorder")

_FILE = BASE_DIR / "data" / "last_run_report.json"

# 実行中に積み上げる記録（プロセス内で共有）
_steps: list = []


def record(name: str, ok: bool, detail: str = "", extra: dict = None) -> None:
    """1ステップの結果を記録する。例外を投げないことを最優先にする。"""
    try:
        item = {"step": name, "ok": bool(ok),
                "at": get_jst_now().strftime("%H:%M:%S")}
        if detail:
            item["detail"] = str(detail)[:300]
        if extra:
            item["extra"] = {k: str(v)[:120] for k, v in extra.items()}
        _steps.append(item)
    except Exception:
        pass


def save(mode: str = "", note: str = "") -> None:
    """
    実行記録をファイルへ書き出す。
    次回の実行で上書きされるため、常に「最後の1回」の状況が残る。
    """
    try:
        ng = [s for s in _steps if not s["ok"]]
        data = {
            "run_at": get_jst_now().strftime("%Y-%m-%d %H:%M:%S JST"),
            "mode": mode,
            "total": len(_steps),
            "failed": len(ng),
            "failed_steps": [s["step"] for s in ng],
            "steps": _steps,
        }
        if note:
            data["note"] = note
        _FILE.parent.mkdir(exist_ok=True)
        _FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                         encoding="utf-8")
        if ng:
            logger.warning(f"📝 実行記録: {len(ng)}件の失敗を記録 → {_FILE.name}")
        else:
            logger.info(f"📝 実行記録を保存: 全{len(_steps)}件正常")
    except Exception:
        logger.debug(traceback.format_exc())


def load() -> dict:
    """前回の実行記録を読む（調査用）。"""
    try:
        return json.loads(_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


if __name__ == "__main__":
    d = load()
    if not d:
        print("実行記録がありません")
    else:
        print(f"{d.get('run_at')} [{d.get('mode')}] "
              f"{d.get('total')}件中 {d.get('failed')}件失敗")
        for s in d.get("steps", []):
            mark = "✅" if s["ok"] else "❌"
            print(f"  {mark} {s['step']}: {s.get('detail', '')[:120]}")
