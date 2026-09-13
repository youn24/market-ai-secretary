"""
鍵の流出を「コミットされる前」に止める検査

なぜ必要か:
  2026-08-24に、公開リポジトリの履歴に残っていたTelegramボットトークンが
  **今も有効**であることが判明した。初回コミットで .env をそのまま入れてしまい、
  後から削除しても履歴からは消えなかった。

  一度公開履歴に入った鍵は、削除コミットを積んでも取り消せない。
  つまり「入ってから気づく」では手遅れで、**入る前に止める**しかない。

考え方:
  ・置き場所ではなく「中身の形」で判定する。ファイル名を見るだけでは、
    うっかり別名で置かれた鍵を素通ししてしまう
  ・誤検知で作業が止まるのは困るので、形がはっきり決まっている鍵に絞る
  ・プレースホルダ（"ここに…"、"your-token" 等）は当然除外する

使い方:
  python -m scripts.check_secrets            … ステージ済みの変更を検査
  python -m scripts.check_secrets --all      … 追跡中の全ファイルを検査
  .git/hooks/pre-commit から呼ぶと、混入したコミットが作れなくなる
"""
import re
import subprocess
import sys

# 形がはっきり決まっている鍵だけを対象にする。
# 曖昧なパターン（"password=" 等）を入れると誤検知が増え、
# やがて誰も警告を読まなくなるので、あえて狭くしている。
PATTERNS = [
    ("Telegramボットトークン", re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b")),
    ("Google/Gemini APIキー", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("OpenAI APIキー",        re.compile(r"\bsk-[A-Za-z0-9]{32,}\b")),
    ("AWSアクセスキー",       re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Slackトークン",         re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b")),
    ("秘密鍵ファイルの中身",  re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
]

# 見本・説明用の値は鍵ではない
PLACEHOLDER = re.compile(
    r"ここに|your[-_ ]?|example|dummy|sample|xxxx|placeholder|<[^>]+>",
    re.IGNORECASE)

# 検査しても意味がない場所
SKIP = re.compile(r"(^|/)(\.git/|__pycache__/|node_modules/|\.venv/)"
                  r"|\.(png|jpg|jpeg|gif|webp|ico|pdf|zip|mp4|woff2?)$")


def _staged_files() -> list:
    r = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
                       capture_output=True, text=True)
    return [f for f in r.stdout.split("\n") if f.strip()]


def _all_files() -> list:
    r = subprocess.run(["git", "ls-files"], capture_output=True, text=True)
    return [f for f in r.stdout.split("\n") if f.strip()]


def _content(path: str, staged: bool) -> str:
    """
    ステージ済みの内容を見るのが肝。
    作業ツリーを見ると、直前に消した鍵を「無い」と誤判定してしまう。
    """
    try:
        if staged:
            r = subprocess.run(["git", "show", f":{path}"],
                               capture_output=True, text=True, errors="replace")
            return "" if r.returncode else r.stdout
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return ""


def scan(paths: list, staged: bool = True) -> list:
    hits = []
    for p in paths:
        if SKIP.search(p):
            continue
        text = _content(p, staged)
        if not text:
            continue
        for lineno, line in enumerate(text.split("\n"), 1):
            if PLACEHOLDER.search(line):
                continue
            for label, pat in PATTERNS:
                m = pat.search(line)
                if m:
                    v = m.group(0)
                    hits.append({
                        "file": p, "line": lineno, "kind": label,
                        "masked": f"{v[:6]}…{v[-4:]}" if len(v) > 12 else "…",
                    })
                    break
    return hits


def main() -> int:
    # Windowsの既定はcp932で、絵文字を出そうとすると検査自体が落ちる。
    # 「検査が死んでいるのに気づけない」のが一番まずいので最初に固定する。
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    every = "--all" in sys.argv
    paths = _all_files() if every else _staged_files()

    # .env そのものが混ざっていないかは、中身の形とは別に必ず見る
    env_staged = [p for p in paths
                  if p == ".env" or p.endswith("/.env")]

    hits = scan(paths, staged=not every)

    if not hits and not env_staged:
        print(f"✅ 鍵の混入なし（{len(paths)}ファイルを検査）")
        return 0

    print("🚨 コミットを中止しました — 鍵が混入しています")
    print("─" * 56)
    for p in env_staged:
        print(f"  ❌ {p} … .env は絶対にコミットしないでください")
    for h in hits:
        print(f"  ❌ {h['file']}:{h['line']}  {h['kind']}  {h['masked']}")
    print("─" * 56)
    print("一度コミットすると、後で削除しても**履歴からは消えません**。")
    print("公開リポジトリなら、その時点で鍵は漏れたものとして扱ってください。")
    print()
    print("対処:")
    print("  1. 鍵を .env に移し、コードからは os.getenv() で読む")
    print("  2. git restore --staged <ファイル> でステージから外す")
    print("  3. すでに公開済みなら、その鍵を再発行する（削除では戻せません）")
    return 1


if __name__ == "__main__":
    sys.exit(main())
