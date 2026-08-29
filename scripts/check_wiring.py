"""
cloud_run が渡す引数を、受け取り側が本当に受けられるか検査する

なぜ必要か:
  2026-08-26以降、レポートと通知に多くの項目を足した過程で、
  同じ形の事故を**2回**作りかけた。

    ① notify_telegram.run() に引数を足さずに cloud_run から渡す
       → TypeError で朝の通知が丸ごと落ちる
    ② _build_unified_caption の中で、引数に無い名前を参照する
       → NameError で同じく落ちる

  受け取り側の引数は60個を超えており、片側だけ直す事故が起きやすい。
  実行して確かめるには20分かかるうえ、Geminiの枠も使う。
  **構文木を読めば実行せずに分かる。**

検査するもの:
  1. cloud_run が渡すキーワード引数を、受け取り側が受けられるか
     （**kwargs があれば何でも受けられるので、その場合は通す）
  2. 受け取り側の関数本体で、引数にも局所変数にも無い名前を読んでいないか

⚠️ これは「引数の名前」だけを見る。中身が正しいかは別の話で、
   キー名の取り違え（chg_pct を change_pct と書く等）は検出できない。
   そちらは実データで確認するしかない。
"""
import ast
import builtins
import io
import sys


def _callsite_kwargs(path: str, func_name: str) -> set:
    """path の中で func_name(...) を呼んでいる箇所のキーワード引数名を集める。"""
    tree = ast.parse(open(path, encoding="utf-8").read())
    out = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        name = (f.id if isinstance(f, ast.Name)
                else f.attr if isinstance(f, ast.Attribute) else "")
        if name != func_name:
            continue
        for kw in node.keywords:
            if kw.arg:            # **d は arg=None なので除く
                out.add(kw.arg)
    return out


def _accepts(module_path: str, func_name: str):
    """(受けられる引数名の集合, **kwargs があるか) を返す。"""
    tree = ast.parse(open(module_path, encoding="utf-8").read())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            a = node.args
            names = {x.arg for x in a.args} | {x.arg for x in a.kwonlyargs}
            if a.vararg:
                names.add(a.vararg.arg)
            return names, a.kwarg is not None
    return None, False


_OWN_SCOPE = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp,
              ast.Lambda, ast.FunctionDef, ast.AsyncFunctionDef)


def _undefined_reads(module_path: str, func_name: str) -> list:
    """
    関数本体で、引数にも局所代入にも無い名前を読んでいないか。

    ⚠️ 内包表記・ラムダは自分のスコープを持つので中へ入らない。
       ここを区別しないと誤検知だらけになる（check_order.py で経験済み）。
    """
    src = open(module_path, encoding="utf-8").read()
    tree = ast.parse(src)
    target = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            target = node
            break
    if target is None:
        return []

    known = set(dir(builtins)) | {"__file__", "__name__"}
    for n in ast.walk(tree):
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            for x in n.names:
                known.add((x.asname or x.name).split(".")[0])
        elif isinstance(n, ast.FunctionDef):
            known.add(n.name)
        elif isinstance(n, ast.Assign) and getattr(n, "col_offset", 1) == 0:
            for t in n.targets:
                if isinstance(t, ast.Name):
                    known.add(t.id)
    a = target.args
    known |= {x.arg for x in a.args} | {x.arg for x in a.kwonlyargs}
    if a.vararg:
        known.add(a.vararg.arg)
    if a.kwarg:
        known.add(a.kwarg.arg)

    # 本体で代入される名前をすべて集める（順序は問わない。
    # 「定義前に読む」は check_order.py の担当で、ここは「そもそも無い」を見る）
    for n in ast.walk(target):
        if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            known.add(n.id)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for x in n.names:
                known.add((x.asname or x.name).split(".")[0])
        elif isinstance(n, ast.ExceptHandler) and n.name:
            known.add(n.name)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            known.add(n.name)
            known |= {x.arg for x in n.args.args}

    bad = []

    def walk(n):
        if isinstance(n, _OWN_SCOPE) and n is not target:
            return
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) \
                and n.id not in known:
            bad.append({"line": n.lineno, "name": n.id})
        for c in ast.iter_child_nodes(n):
            walk(c)

    for st in target.body:
        walk(st)
    return bad


# ⚠️ 呼び出し名は import の別名で書かれている。
#    `from src.design_ai import run as run_design` のように別名を付けるので、
#    受け側の関数名（run）で探しても見つからない。
#    最初この対応表を run/run と書いてしまい、「0個すべて受けられる」という
#    何も検査していない結果を「合格」として出していた。
#    **0件は合格ではなく、見つけられなかった疑い**として扱うこと。
PAIRS = [
    ("cloud_run.py", "run_design", "src/design_ai.py",       "run"),
    ("cloud_run.py", "notify_tg",  "src/notify_telegram.py", "run"),
    ("src/notify_telegram.py", "_build_unified_caption",
     "src/notify_telegram.py", "_build_unified_caption"),
]


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace")
    bad = 0
    for caller, cfunc, mod, mfunc in PAIRS:
        passed = _callsite_kwargs(caller, cfunc)
        accepted, has_kwargs = _accepts(mod, mfunc)
        if accepted is None:
            print(f"❌ {mod}:{mfunc}() が見つかりません")
            bad += 1
            continue
        # 0件は「合格」ではなく「呼び出しを見つけられなかった」疑い。
        # 別名importで探し損ねていても素通りしてしまうため、必ず知らせる。
        if not passed:
            print(f"⚠️ {caller} の中に {cfunc}(...) の呼び出しが見つかりません。"
                  f"別名importの可能性があります")
            bad += 1
            continue

        missing = sorted(passed - accepted)
        if missing and not has_kwargs:
            print(f"❌ {caller} → {mod}:{mfunc}() が受けられない引数 "
                  f"{len(missing)}件")
            for m in missing:
                print(f"    {m}")
            bad += len(missing)
        else:
            note = "（**kwargs で吸収）" if missing and has_kwargs else ""
            print(f"✅ {caller} → {mod}:{mfunc}()  "
                  f"{len(passed)}個すべて受けられる{note}")

    for mod, fn in (("src/notify_telegram.py", "_build_unified_caption"),
                    ("src/design_ai.py", "generate")):
        u = _undefined_reads(mod, fn)
        if u:
            print(f"❌ {mod}:{fn}() 定義されていない名前 {len(u)}件")
            for x in u[:10]:
                print(f"    {mod}:{x['line']}  {x['name']}")
            bad += len(u)
        else:
            print(f"✅ {mod}:{fn}() 未定義の参照なし")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
