# -*- coding: utf-8 -*-
"""同じファイルの中で同じ名前の関数を二度定義していないか調べる。

    python -m scripts.check_dupe_defs

⚠️ なぜ要るか（2026-11-20 に実際にやった）。
   `src/feed_card.py` には見出しを作る `_headline(nk, internals)` が既にあったのに、
   ニュースの題名を整える関数を**同じ名前**で新しく足した。

   Python は**後ろの定義が勝つ**ので、新しく書いた呼び出しは
   既存の別物（引数の数が違う）を呼び、`TypeError` になった。
   運が悪ければ引数の数が偶然合って、**例外も出ずに違う文字が表示される**。
   この案件で繰り返している「静かに壊れる」の典型。

   構文は通る・import も通る（呼ぶまで分からない）ので、
   目で見つけるのは無理。ここで機械的に突き合わせる。

⚠️ クラスの中のメソッドや、`if`／`try` で振り分ける定義は別物なので数えない
   （`try: from x import y / except: def y()` のような受け皿は正しい書き方）。
"""
import ast
import io
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIRS = ("src", "scripts")
FILES = ("cloud_run.py", "monitor_run.py", "weekly_run.py",
         "evening_run.py", "fx_noon_run.py")


def _dupes(path: Path) -> dict:
    """モジュールの一番外側にある関数定義だけを数える。"""
    try:
        tree = ast.parse(io.open(path, encoding="utf-8").read())
    except SyntaxError as e:
        return {"__syntax__": [f"{e.lineno}行: {e.msg}"]}

    seen = defaultdict(list)
    for node in tree.body:          # ⚠️ body だけ。入れ子は見ない
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            seen[node.name].append(node.lineno)
    return {k: v for k, v in seen.items() if len(v) > 1}


def main() -> int:
    # ⚠️ Windowsの既定(cp932)では絵文字を印字できず、合格の行だけで落ちる。
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    paths = [p for d in DIRS for p in sorted((ROOT / d).glob("*.py"))]
    paths += [ROOT / f for f in FILES if (ROOT / f).exists()]

    bad = 0
    for p in paths:
        d = _dupes(p)
        if not d:
            continue
        rel = p.relative_to(ROOT).as_posix()
        for name, lines in sorted(d.items()):
            bad += 1
            where = "、".join(f"{n}行" for n in lines)
            print(f"❌ {rel}: `{name}` が {len(lines)}回定義されています（{where}）")

    if bad:
        print(f"\n{bad}件。**後ろの定義が勝つ**ので、手前の呼び出しが別物を呼びます。")
        print("どちらかを改名してください（例: _headline → _news_title）。")
        return 1

    print(f"✅ {len(paths)}ファイル、同名の二重定義なし")
    return 0


if __name__ == "__main__":
    sys.exit(main())
