"""
ワークフローの「静かに壊れる書き方」を機械的に見つける（Step LINT）

なぜ必要か:
  このプロジェクトの重大事故は3回とも同じ形だった。
  失敗しているのにActionsが緑で、誰も気づけない。
    2026-06-26 例外を logger.debug で握りつぶし → 公開停止1.5ヶ月
    2026-08-12 git push || true → 学習データが毎回消失
    2026-08-18 git add に存在しないパス + 2>/dev/null || true → 公開停止1週間
  どれも「書いた時点では気づけないが、後から見れば明らか」だった。
  ならば人間の注意力ではなく検査に任せるべきなので、機械で毎回見る。

  ここで検出するのは「バグ」ではなく「バグを隠す書き方」である。
  隠れさえしなければ、壊れてもその日のうちに直せる。

python -m scripts.lint_workflows → 重大な指摘があれば exit 1
"""
import io
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
WF = BASE / ".github" / "workflows"

HIGH, LOW = "重大", "注意"


# 意図して失敗を許す行には `# lint:allow-fail 理由` を書く。
# 逃げ道を用意するのは、誤検知が多い検査は必ず読み飛ばされるようになり、
# 本物の指摘まで一緒に無視されてしまうため。理由の記述を必須にして、
# 「とりあえず黙らせる」ができないようにしている。
_ALLOW = re.compile(r"#\s*lint:allow-fail\s+\S+")


def _check_line(path: str, no: int, line: str) -> list:
    s = line.strip()
    out = []
    if s.startswith("#") or not s:
        return out
    if _ALLOW.search(s):
        return out

    # git add に複数パスを一度に渡すと、存在しないパスが1つでもあれば
    # git add はエラー終了し「何もステージしない」。2026-08-18の事故原因。
    if re.search(r"\bgit add\b", s) and not s.startswith("#"):
        args = re.sub(r".*\bgit add\b", "", s)
        args = re.sub(r"[|&;].*$", "", args)
        paths = [a for a in args.split()
                 if not a.startswith("-") and not a.startswith("2>")]
        if len(paths) > 1:
            out.append((HIGH, path, no,
                        f"git add に複数パス（{len(paths)}個）。存在しないパスが1つでもあると"
                        f"何もステージされません。1つずつ [ -f ] で確認して add してください"))

    # 成果物を扱うコマンドの失敗を握りつぶすと、失敗が完全に無音になる
    if "|| true" in s:
        m = re.search(r"\b(git (push|commit|add)|python|cp|mv)\b", s)
        if m:
            out.append((HIGH, path, no,
                        f"`{m.group(1)}` の失敗を `|| true` で握りつぶしています。"
                        f"失敗を検知できなくなります"))
        else:
            out.append((LOW, path, no, "`|| true` で失敗を握りつぶしています"))

    # ::error:: は注釈を出すだけでジョブを赤くしない。
    # 「エラーを出したのに緑」は、気づけないという点で沈黙と同じ。
    # 同じ行で exit していれば、注釈を出したうえで落ちているので問題ない
    if "::error::" in s and "exit 1" not in s:
        out.append((LOW, path, no,
                    "`::error::` はジョブを失敗させません。"
                    "本当に致命的なら exit 1 で落としてください"))
    return out


def run() -> dict:
    findings = []
    for f in sorted(WF.glob("*.yml")):
        for no, line in enumerate(f.read_text(encoding="utf-8").split("\n"), 1):
            findings += _check_line(f.name, no, line)

    high = [x for x in findings if x[0] == HIGH]
    return {"findings": findings, "high": high, "ok": not high}


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    r = run()
    if not r["findings"]:
        print("✅ ワークフローに静かに壊れる書き方は見つかりませんでした")
        return 0

    cur = None
    for level, path, no, msg in r["findings"]:
        if path != cur:
            print(f"\n── {path}")
            cur = path
        mark = "🚨" if level == HIGH else "・"
        print(f"  {mark} {level} L{no}: {msg}")

    print(f"\n重大 {len(r['high'])}件 / 注意 {len(r['findings']) - len(r['high'])}件")
    if r["high"]:
        print("::error::ワークフローに重大な指摘があります")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
