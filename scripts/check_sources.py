# -*- coding: utf-8 -*-
"""出典のURLが本当に開けるかを外から確かめる（scripts/check_sources.py）

**なぜ要るか**: 2026-11-19、出典の台帳を作ったその日に、財務省のURLを
`feign`（正しくは `feio`）と書き、**404のURLを出典として配信していた**。
出典は「正しそうに見える」だけでは意味がなく、むしろ有害で、
数字が合っていても信用を崩す。しかも誰かがタップするまで誰も気づけない。

机の上で見比べても気づけなかったので、**実際にHTTPで取りに行って確かめる**。
（この案件では「生成できた」と「利用者に届いた」は別物という教訓を
  publish_check.py で既に一度学んでいる。出典でも同じ形。）

    python -m scripts.check_sources          # 全部調べる
    python -m scripts.check_sources --quiet  # 異常だけ出す

異常があれば exit 1。ワークフローに繋げば赤くなって気づける。
"""
import sys
import time
import urllib.request
import urllib.error

sys.path.insert(0, ".")
from src.sources import SOURCES  # noqa: E402

_HEAD = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0 Safari/537.36"}
_TIMEOUT = 20


def check(url: str):
    """(状態, 説明) を返す。"""
    t = time.time()
    try:
        r = urllib.request.urlopen(
            urllib.request.Request(url, headers=_HEAD), timeout=_TIMEOUT)
        r.read(200)
        return "OK", f"HTTP {r.status} / {time.time() - t:.1f}秒"
    except urllib.error.HTTPError as e:
        # 403 は「人間のブラウザなら開ける」ことが多く、出典としては有効。
        # 404 は**ページが存在しない**ので出典として壊れている。
        kind = "NG" if e.code in (404, 410) else "注意"
        return kind, f"HTTP {e.code}"
    except Exception as e:
        # 到達できない＝こちらの回線から確認できないだけの場合もある。
        # 出典としては残してよいが、画像などを取りに行く先には使えない。
        return "注意", f"{type(e).__name__}: {str(e)[:40]}"


def main() -> int:
    quiet = "--quiet" in sys.argv
    bad, warn = [], []
    for key, (name, url, use) in SOURCES.items():
        state, detail = check(url)
        if state == "NG":
            bad.append((key, name, url, detail))
        elif state == "注意":
            warn.append((key, name, url, detail))
        if not quiet:
            mark = {"OK": "✅", "注意": "⚠️", "NG": "❌"}[state]
            print(f"{mark} {key:16} {detail:34} {url}")

    print()
    if warn:
        print(f"⚠️  確認できなかった出典 {len(warn)}件"
              f"（回線やbot除けの可能性。人がブラウザで開けるなら問題ない）")
        for k, n, u, d in warn:
            print(f"    {k:16} {d:28} {u}")
    if bad:
        print(f"\n❌ 壊れている出典 {len(bad)}件 — "
              f"**存在しないページを出典として配信している状態**")
        for k, n, u, d in bad:
            print(f"    {k:16} {d:28} {u}")
        return 1
    print("✅ 壊れている出典はありません"
          f"（{len(SOURCES)}件中 OK {len(SOURCES) - len(warn)}件）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
