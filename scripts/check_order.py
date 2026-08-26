"""
cloud_run の中で「まだ代入していない変数を使っていないか」を静的に調べる

なぜ必要か:
  2026-08-26に、夜間データの3ブロック（us_movers / adr_data / us_afterhours）を
  Step AIB の前へ移動した。移した先で、まだ代入されていない変数を
  参照していれば NameError で朝の実行ごと落ちる。

  cloud_run.run() は2,000行を超える1つの関数で、変数はすべて局所変数。
  目視で追うのは現実的でないし、実行して確かめるには20分かかるうえ
  Geminiの枠も使う。**構文木を辿れば実行せずに分かる**。

やり方:
  関数本体を上から順に辿り、代入より前に出てくる名前を報告する。
  try/except の中は「実行されないかもしれない」が、cloud_run は
  各Stepの前に必ず既定値を代入する書き方（`x = {"available": False}`）に
  統一されているので、この方式で十分に検出できる。

⚠️ 完全ではない。if/for の分岐で片方だけ代入される場合など、
   静的解析では判断できない形もある。あくまで「移動事故」の検出用。
"""
import ast
import builtins
import io
import sys


_OWN_SCOPE = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp,
              ast.Lambda, ast.FunctionDef, ast.AsyncFunctionDef)


_COMPS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


def _loads_outside_own_scope(node):
    """
    この式の中で「読んでいる」名前のうち、独自スコープの内側を除いたもの。

    内包表記・ラムダ・ネスト関数は自分の変数を自分で作るので、
    外側から見て未定義でも問題ない。ここを区別しないと誤検知に埋もれる。

    ⚠️ ただし完全には切り離せない部分がある:
       ・内包表記の**一番外側の iter** だけは外のスコープで評価される
         （[f(v) for v in xs] の xs は外側の変数）
       ・ラムダの既定値も定義時に外で評価される（lambda a=x: ...）
       この2つだけは中を覗きにいく。
    """
    out = []

    def walk(n):
        if isinstance(n, _COMPS):
            if n.generators:
                walk(n.generators[0].iter)     # 最外の iter のみ外のスコープ
            return
        if isinstance(n, ast.Lambda):
            for d in (n.args.defaults or []) + \
                     [d for d in (n.args.kw_defaults or []) if d]:
                walk(d)
            return
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            out.append(n)
        for child in ast.iter_child_nodes(n):
            walk(child)

    walk(node)
    return out


def check(path: str = "cloud_run.py", func: str = "run") -> list:
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)

    target = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func:
            target = node
            break
    if target is None:
        return [{"line": 0, "name": func, "msg": "関数が見つかりません"}]

    # モジュールに最初から在る名前。__file__ 等を未定義と数えないため。
    known = set(dir(builtins)) | {
        "__file__", "__name__", "__doc__", "__package__", "__spec__",
        "__loader__", "__builtins__",
    }
    # 引数とモジュール先頭のimport・グローバルは既知として扱う
    for a in target.args.args:
        known.add(a.arg)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for n in node.names:
                known.add((n.asname or n.name).split(".")[0])
        elif isinstance(node, ast.Assign) and getattr(node, "col_offset", 1) == 0:
            for t in node.targets:
                if isinstance(t, ast.Name):
                    known.add(t.id)
        elif isinstance(node, ast.FunctionDef):
            known.add(node.name)

    problems = []
    assigned = set()

    def record(n):
        """代入・import・for・withなどで名前が生まれる箇所を拾う"""
        if isinstance(n, ast.Name):
            assigned.add(n.id)
        elif isinstance(n, (ast.Tuple, ast.List)):
            for e in n.elts:
                record(e)
        elif isinstance(n, ast.Starred):
            record(n.value)

    for node in ast.walk(target):
        pass  # walk は順序が保証されないので、下で自前に辿る

    def scan(*nodes):
        """
        与えられた式の中で「読んでいる」名前を検査する。

        ⚠️ 内包表記・ラムダ・ネストした関数は**自分だけのスコープ**を持つ。
           そこで生まれる変数（[f(v) for v in xs] の v など）まで
           「未定義」と数えると誤検知だらけになり、本物の事故が埋もれる。
           最初の版がまさにそれで、50件のうち本物は0件だった。
        """
        for n in nodes:
            if n is None:
                continue
            for sub in _loads_outside_own_scope(n):
                nm = sub.id
                if nm not in known and nm not in assigned:
                    problems.append({"line": sub.lineno, "name": nm})
                    known.add(nm)      # 同じ名前を何度も報告しない

    def visit(body):
        """
        ⚠️ 複合文は「見出しの式」だけを先に検査し、本体は再帰で辿る。
           文まるごとを検査すると、for の本体を「ループ変数が入る前」に
           読んだことになり、これも誤検知の山になる。
        """
        for st in body:
            if isinstance(st, ast.Assign):
                scan(st.value)
                for t in st.targets:
                    record(t)
            elif isinstance(st, (ast.AugAssign, ast.AnnAssign)):
                scan(st.value, st.target)
                record(st.target)
            elif isinstance(st, (ast.Import, ast.ImportFrom)):
                for n in st.names:
                    assigned.add((n.asname or n.name).split(".")[0])
            elif isinstance(st, ast.For):
                scan(st.iter)          # 回す対象は本体より先に評価される
                record(st.target)
                visit(st.body)
                visit(st.orelse)
            elif isinstance(st, ast.While):
                scan(st.test)
                visit(st.body)
                visit(st.orelse)
            elif isinstance(st, ast.If):
                scan(st.test)
                visit(st.body)
                visit(st.orelse)
            elif isinstance(st, ast.With):
                for it in st.items:
                    scan(it.context_expr)
                    if it.optional_vars is not None:
                        record(it.optional_vars)
                visit(st.body)
            elif isinstance(st, ast.Try):
                visit(st.body)
                for h in st.handlers:
                    if h.name:
                        assigned.add(h.name)
                    visit(h.body)
                visit(st.orelse)
                visit(st.finalbody)
            elif isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # 中身は別スコープなので辿らない。名前だけ登録する
                assigned.add(st.name)
            else:
                scan(st)

    visit(target.body)
    return problems


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace")
    bad = 0
    for path, fn in (("cloud_run.py", "run"), ("monitor_run.py", "run")):
        try:
            probs = check(path, fn)
        except FileNotFoundError:
            continue
        if probs:
            bad += len(probs)
            print(f"❌ {path}:{fn}() — 代入前に使っている名前 {len(probs)}件")
            for p in probs[:20]:
                print(f"    {path}:{p['line']}  {p['name']}")
        else:
            print(f"✅ {path}:{fn}() — 代入前参照なし")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
