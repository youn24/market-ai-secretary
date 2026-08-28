"""
公開物の実地点検（Step PC）— 利用者が実際に見るページを外から確認する

なぜ必要か:
  これまでの点検はすべて「リポジトリ内のファイル」を見ていた。
  ところが2026-08-18に起きた事故は、ファイルは正しく生成されていたのに
  公開サイトへ届いていない、という型だった。生成物を見る限り健全なので
  self_diagnosis も Actions も異常なしと判定し、1週間気づけなかった。

  だから、この点検だけは HTTP で実物を取りに行く。
  中間の状態ではなく、利用者の目に映るものだけを真実として扱う。

  失敗しても静かに終わらせないこと。通知を出し、終了コードで落とす。
  「緑なのに届いていない」を二度と作らないのがこのモジュールの存在理由。

run() → dict / __main__ で実行すると異常時 exit 1
"""
import os
import re
import ssl
import sys
import urllib.request
from datetime import datetime, timedelta

from src.utils import setup_logger, get_today_str

logger = setup_logger("publish_check")

# ⚠️ os.getenv(名前, 既定値) は「変数が無いとき」しか既定値を返さない。
# 変数が**空文字で存在する**と空文字がそのまま返る。
# ワークフローは未登録のSecretを空文字として渡すため、
# GITHUB_PAGES_URL 未登録の状態でこの既定値が上書きされていた。
# 結果 "/daily_report.html" という相対URLになり、点検が
# ValueError: unknown url type で毎回失敗していた（2026-08-27発覚）。
# or で受けると「空なら既定値」になる。
_BASE = (os.getenv("GITHUB_PAGES_URL", "").strip()
         or "https://youn24.github.io/market-ai-secretary").rstrip("/")

# 見るページと、そこに必ず入っているべき目印。
# 目印まで確認するのは、ページが200を返しても中身が空になる壊れ方があるため。
_TARGETS = [
    {"path": "/daily_report.html", "name": "公開レポート",
     "min_size": 20000, "must_contain": ["市場AI秘書"], "required": True},
]

# 相場が休みの日は更新されない。何日前まで許すかの上限。
# 3連休を挟むと3日空くため、4日を超えたら異常とみなす。
_MAX_AGE_DAYS = 4


def _fetch(url: str, timeout: int = 30) -> tuple:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={
        "User-Agent": "market-ai-secretary/publish-check",
        # CDNの古いキャッシュを掴むと誤検知になるため明示的に拒否する
        "Cache-Control": "no-cache", "Pragma": "no-cache",
    })
    with urllib.request.urlopen(req, context=ctx, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8", errors="replace")


def _check_one(t: dict) -> dict:
    url = _BASE + t["path"]
    out = {"name": t["name"], "url": url, "required": t.get("required", False)}
    try:
        status, body = _fetch(url)
    except Exception as e:
        out.update(ok=False, reason=f"取得できません（{type(e).__name__}: {e}）")
        return out

    if status != 200:
        out.update(ok=False, reason=f"HTTP {status}")
        return out

    size = len(body)
    out["size"] = size
    if size < t["min_size"]:
        out.update(ok=False, reason=f"中身が小さすぎます（{size:,}バイト）")
        return out

    missing = [k for k in t.get("must_contain", []) if k not in body]
    if missing:
        out.update(ok=False, reason=f"必須の要素がありません: {', '.join(missing)}")
        return out

    # 掲載されている日付を拾って鮮度を測る
    dates = sorted(set(re.findall(r"20\d\d-\d\d-\d\d", body)), reverse=True)
    if not dates:
        out.update(ok=False, reason="日付が見つからず、いつの内容か判断できません")
        return out

    latest = dates[0]
    out["published_date"] = latest
    today = get_today_str()
    try:
        age = (datetime.strptime(today, "%Y-%m-%d")
               - datetime.strptime(latest, "%Y-%m-%d")).days
    except Exception:
        age = None
    out["age_days"] = age

    if age is None:
        out.update(ok=True, note="日付を比較できませんでした")
    elif age < 0:
        out.update(ok=True, note=f"未来日付（{latest}）")
    elif age > _MAX_AGE_DAYS:
        out.update(ok=False,
                   reason=f"{age}日前（{latest}）の内容のまま止まっています")
    else:
        out.update(ok=True)
        if age > 0:
            out["note"] = f"{age}日前の内容（休場日なら正常）"
    return out


# 古い内容を掴んだときに、何回まで待って再確認するか。
# GitHub Actionsの実行開始はcronから10〜20分ずれ、そこからPagesの再ビルドにも
# 数分かかる。1回見ただけで判定すると、単に「まだ配信中」なだけで異常と叫ぶ。
# 2026-08-19に実際にこれで誤検知した。誤報が続くと点検が信用されなくなる。
_RETRY = 3
_RETRY_WAIT = 90        # 秒（配信待ちの可能性があるとき）
_RETRY_WAIT_SHORT = 20  # 秒（通信の一時的な失敗を想定するとき）


def run(notify: bool = True, retry: int = _RETRY) -> dict:
    import time

    logger.info(f"=== 公開物の実地点検 ({_BASE}) ===")
    results = [_check_one(t) for t in _TARGETS]

    # 失敗したら待って再確認する。
    #
    # 当初は「古い内容」のときだけ再試行していたが、2026-08-20に
    # 1分未満で失敗した。つまり鮮度以外の理由（通信の失敗やHTTPエラー）で
    # 即座に落ちていた。実行環境から一度取りに行って駄目でも、
    # 単なる一時的な失敗であることが多い。
    # 鮮度以外の理由なら短く、鮮度なら配信待ちなので長く待つ。
    for attempt in range(1, retry + 1):
        bad = [r for r in results if not r.get("ok") and r.get("required")]
        if not bad:
            break
        stale = any("止まっています" in (r.get("reason") or "") for r in bad)
        wait = _RETRY_WAIT if stale else _RETRY_WAIT_SHORT
        reasons = " / ".join(r.get("reason", "?") for r in bad)
        logger.warning(f"点検に失敗（{attempt}/{retry}）: {reasons} "
                       f"→ {wait}秒待って再確認します")
        time.sleep(wait)
        results = [_check_one(t) for t in _TARGETS]
    failures = [r for r in results if not r.get("ok")]
    critical = [r for r in failures if r.get("required")]

    for r in results:
        if r.get("ok"):
            extra = f" / {r['note']}" if r.get("note") else ""
            logger.info(f"✅ {r['name']}: {r.get('published_date','?')} "
                        f"({r.get('size',0):,}バイト){extra}")
        else:
            logger.error(f"❌ {r['name']}: {r['reason']}  [{r['url']}]")

    result = {"available": True, "ok": not critical,
              "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
              "base": _BASE, "results": results}

    if critical:
        # 何が理由で落ちたかを必ず残す。今回、理由が分からず調査に時間がかかった。
        for c in critical:
            logger.error(f"最終判定: 異常 — {c['name']}: {c['reason']} [{c['url']}]")
    if critical and notify:
        _notify(critical)
    return result


def _notify(failures: list) -> None:
    """
    異常時だけ通知する。正常時に送ると慣れて読み飛ばすようになり、
    肝心なときに気づけなくなるため、沈黙を既定にする。
    """
    try:
        from src.notify_telegram import send_message
    except Exception:
        logger.error("通知モジュールを読み込めませんでした", exc_info=True)
        return
    lines = ["🚨 *公開ページの異常を検知*", ""]
    for f in failures:
        lines.append(f"❌ {f['name']}")
        lines.append(f"　{f['reason']}")
        lines.append(f"　{f['url']}")
    lines += ["", "レポートが利用者に届いていません。", "Actionsのログを確認してください。"]
    try:
        send_message("\n".join(lines))
        logger.info("異常を通知しました")
    except Exception:
        logger.error("通知の送信に失敗しました", exc_info=True)


if __name__ == "__main__":
    r = run()
    if not r["ok"]:
        # 静かに終わらせない。ここで落とすことでActionsが赤くなる。
        print("::error::公開ページが正しく更新されていません")
        sys.exit(1)
    print("公開ページは正常です")
