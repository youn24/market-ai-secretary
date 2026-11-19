# -*- coding: utf-8 -*-
"""本番(Python 3.11)で構文が通るかを、手元から確かめる（scripts/check_py311.py）

**なぜ要るか**: 手元は Python 3.14、GitHub Actions は 3.11。
3.12 で f文字列の制限が緩くなった（PEP 701）ため、

    二重引用符で囲んだ f文字列の {…} の中で、また二重引用符を使う書き方
    （例: 辞書の添字を d[“key”] のように外と同じ引用符で書く）

のような書き方が **手元では通るのに本番だけ SyntaxError** になる。
しかもこれは実行時エラーではなく **import 自体が失敗する**ので、
そのモジュールを使う処理が丸ごと落ちる（朝のレポートが消える）。
2026-11-19 に実際に書いてしまい、コミット前に気づいた。

`ast.parse(..., feature_version=(3,11))` は 3.12 以降で入った書き方を
ちゃんと撥ねるので、本番に送る前にここで止められる。

    python -m scripts.check_py311

異常があれば exit 1。
"""
import ast
import io
import re
import sys
from pathlib import Path

# ⚠️ `ast.parse(feature_version=(3,11))` は**この問題を検出できない**。
#    f文字列の入れ子は字句解析側の変更なので、文法バージョンの指定が効かない
#    （実測: 3.14 で feature_version=(3,11) にしても素通りする）。
#    なので危ない書き方そのものを探す。
#
#  ① f文字列の中に f文字列（入れ子）           → 3.12以降だけ
#  ② f文字列の {…} の中で、外と同じ引用符       → 3.12以降だけ
_FSTR = re.compile(r"""(?P<p>\bf)(?P<q>'''|\"\"\"|'|")""")


def _risky_fstrings(src: str):
    """危ない f文字列の (行番号, 理由) を返す。"""
    out = []
    for m in _FSTR.finditer(src):
        q = m.group("q")
        i = m.end()
        depth, cur, exprs = 0, [], []
        while i < len(src):
            ch = src[i]
            if ch == "\\":
                i += 2
                continue
            if src.startswith(q, i) and depth == 0:
                break
            if ch == "{":
                if src.startswith("{{", i):
                    i += 2
                    continue
                depth += 1
            elif ch == "}":
                depth = max(0, depth - 1)
                if depth == 0 and cur:
                    exprs.append("".join(cur))
                    cur = []
            elif depth > 0:
                cur.append(ch)
            i += 1
        if cur:
            exprs.append("".join(cur))
        line = src.count("\n", 0, m.start()) + 1
        # ⚠️ 「入れ子の f文字列」そのものは 3.11 でも合法。
        #    違うのは**外と同じ引用符を {…} の中で使うこと**だけ。
        #    最初これを分けずに「入れ子は全部だめ」としたら、
        #    本番で動いている既存10ファイルを誤検知した。
        #    なお入れ子の内側も finditer が別件として走査するので、
        #    内側が同じ引用符を使っていればそこで捕まる。
        # ⚠️ 式ごとに分けて見る。全部つないで判定すると、隣り合う式の
        #    境界で `""` + `"` が `\"\"\"` に見えて誤検知する
        #    （report_writer.py で実際に起きた）。
        if any(q in e for e in exprs):
            out.append((line, f"f文字列の {{…}} の中で外と同じ引用符 {q} を使っています"))
    return out

TARGET = (3, 11)          # GitHub Actions の Python
ROOT = Path(__file__).resolve().parent.parent
DIRS = ("src", "scripts")
FILES = ("cloud_run.py", "monitor_run.py", "weekly_run.py",
         "evening_run.py", "fx_noon_run.py")


def main() -> int:
    # ⚠️ Windowsの既定(cp932)では ✅ が印字できず、**合格の行だけで落ちる**。
    #    検査自体は終わっているのに失敗に見えるので、出口を utf-8 に揃える。
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    paths = [p for d in DIRS for p in (ROOT / d).glob("*.py")]
    paths += [ROOT / f for f in FILES if (ROOT / f).exists()]

    bad = []
    for p in sorted(paths):
        src = io.open(p, encoding="utf-8").read()
        try:
            ast.parse(src, filename=str(p))
        except SyntaxError as e:
            bad.append((p, f"手元({sys.version_info.major}.{sys.version_info.minor})でも構文エラー: {e}"))
            continue
        try:
            ast.parse(src, filename=str(p), feature_version=TARGET)
        except SyntaxError as e:
            bad.append((p, f"Python{TARGET[0]}.{TARGET[1]}では通りません（{e.lineno}行目）: {e.msg}"))
        for line, why in _risky_fstrings(src):
            bad.append((p, f"{line}行目: {why}（Python3.12以降だけの書き方）"))

    if bad:
        print(f"❌ 本番(Python {TARGET[0]}.{TARGET[1]})で落ちる書き方が {len(bad)}件\n")
        for p, msg in bad:
            print(f"  {p.relative_to(ROOT)}")
            print(f"    {msg}")
        print("\n※ import 自体が失敗するため、そのモジュールを使う処理が"
              "丸ごと落ちます（ログには出ません）。")
        return 1
    print(f"✅ {len(paths)}ファイル、Python {TARGET[0]}.{TARGET[1]} で構文が通ります")
    return 0


if __name__ == "__main__":
    sys.exit(main())
