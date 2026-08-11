"""
システム自己診断（Step DIAG）— 「静かに壊れる」を二度と起こさないための健康診断

なぜ必要か:
  2026-08-11、公開レポートが1.5か月間まったく更新されていなかったことが判明した。
  各Stepは try/except で継続する設計のため、ひとつ壊れても実行は最後まで完走し、
  GitHub Actions は緑、ログにも「✅生成」と出ていた。誰も異常に気づけなかった。

  個々のモジュールを直すだけでは同じ事故がまた別の場所で起きる。
  必要なのは「成果物がちゃんと届いているか」をシステム自身が毎朝点検し、
  壊れていたら黙っていない仕組みである。

診断する4つの観点:
  1. 成果物の鮮度   … 公開レポートは今日の内容か（届いていない＝最も重い障害）
  2. 学習データ     … 予測記録が更新され続けているか（学習が止まっていないか）
  3. データ取得     … 主要な価格が取れているか（欠損だらけの分析は無意味）
  4. 機能の稼働率   … 何割の機能が生きているか（静かに死んだ機能の検出）

健康なときは何も言わない（ノイズにしないため）。
異常があるときだけ、朝の通知に1行の警告として現れる。

run(prices, module_status) → {"healthy", "score", "issues":[...], "telegram_line"}
"""
import json
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from src.utils import setup_logger, get_jst_now, get_today_str, BASE_DIR

logger = setup_logger("self_diagnosis")

# 深刻度: critical=利用者に届いていない / warning=劣化 / info=参考
_CRITICAL, _WARNING = "critical", "warning"


def _check_report_freshness() -> dict | None:
    """
    公開レポートが今日の内容かを見る。
    これが古いままだと、どれだけ分析を足しても利用者には何も届かない。
    2026-08-11の事故はまさにこれだった。
    """
    f = BASE_DIR / "docs" / "daily_report.html"
    if not f.exists():
        return {"level": _CRITICAL, "key": "report_missing",
                "msg": "公開レポートが存在しません",
                "detail": f"{f} が見つかりません。design_ai の生成が失敗しています。"}
    try:
        size = f.stat().st_size
        head = f.read_text(encoding="utf-8", errors="ignore")[:4000]
    except Exception:
        return {"level": _CRITICAL, "key": "report_unreadable",
                "msg": "公開レポートを読めません", "detail": str(f)}

    if size < 5000:
        return {"level": _CRITICAL, "key": "report_broken",
                "msg": f"公開レポートが不完全です（{size:,}バイト）",
                "detail": "生成が途中で失敗している可能性があります。"}

    today = get_today_str()
    if today in head:
        return None                      # 正常
    # 何日前のものかを推定する
    import re
    m = re.search(r"20\d\d-\d\d-\d\d", head)
    old = m.group(0) if m else "不明"
    try:
        days = (datetime.strptime(today, "%Y-%m-%d")
                - datetime.strptime(old, "%Y-%m-%d")).days
    except Exception:
        days = None
    return {"level": _CRITICAL, "key": "report_stale",
            "msg": f"公開レポートが古いままです（{old}版"
                   + (f"・{days}日前" if days else "") + "）",
            "detail": "利用者には過去の内容が表示され続けています。"
                      "design_ai の生成失敗をログで確認してください。"}


def _check_learning_data() -> dict | None:
    """予測記録が増え続けているか。学習が止まると精度改善も止まる。"""
    f = BASE_DIR / "data" / "predictions.json"
    if not f.exists():
        return {"level": _WARNING, "key": "predictions_missing",
                "msg": "予測記録が見つかりません",
                "detail": "AIの学習データが失われている可能性があります。"}
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        preds = data.get("predictions", [])
        if not preds:
            return {"level": _WARNING, "key": "predictions_empty",
                    "msg": "予測記録が空です", "detail": ""}
        last = preds[-1].get("date", "")
        d = datetime.strptime(last[:10], "%Y-%m-%d")
        days = (datetime.strptime(get_today_str(), "%Y-%m-%d") - d).days
        # 土日を挟むと2〜3日空くのは正常。5日以上は明らかに止まっている
        if days >= 5:
            return {"level": _WARNING, "key": "predictions_stale",
                    "msg": f"予測記録が{days}日間更新されていません",
                    "detail": f"最終記録: {last[:10]}。学習ループが止まっている可能性があります。"}

        # 予測は記録されても「翌日の答え合わせ」が動かなければ精度は改善しない。
        # 直近20件のうち検証済みが極端に少なければ、検証処理が壊れている。
        recent = preds[-20:]
        # 当日と前営業日はまだ答えが出ていないのが正常なので対象から外す
        checkable = [p for p in recent if p.get("date", "")[:10] < last[:10]]
        if len(checkable) >= 5:
            verified = sum(1 for p in checkable if p.get("verified"))
            if verified == 0:
                return {"level": _WARNING, "key": "verification_stopped",
                        "msg": f"予測の答え合わせが行われていません（直近{len(checkable)}件すべて未検証）",
                        "detail": "正解率が計算できず、精度改善のループが止まっています。"}
    except Exception:
        logger.debug(traceback.format_exc())
    return None


def _check_price_coverage(prices: dict) -> dict | None:
    """主要な価格が取れているか。欠損だらけでは分析そのものが成り立たない。"""
    core = ["^N225", "^GSPC", "USDJPY=X", "^VIX"]
    got = [s for s in core if (prices or {}).get(s, {}).get("latest") is not None]
    if len(got) == len(core):
        return None
    missing = [s for s in core if s not in got]
    level = _CRITICAL if len(got) <= 1 else _WARNING
    return {"level": level, "key": "price_missing",
            "msg": f"主要価格が取得できていません（{len(got)}/{len(core)}）",
            "detail": f"欠損: {', '.join(missing)}。データ元の障害か通信制限の可能性があります。"}


def _check_module_health(module_status: list) -> dict | None:
    """
    稼働機能の割合を見る。
    個々の失敗は珍しくないが、半分以上が死んでいるなら共通の原因がある。
    """
    if not module_status:
        return None
    ok = [n for n, v in module_status if v]
    rate = len(ok) / len(module_status) * 100
    if rate >= 70:
        return None
    ng = [n for n, v in module_status if not v]
    level = _CRITICAL if rate < 40 else _WARNING
    return {"level": level, "key": "modules_down",
            "msg": f"稼働率が低下しています（{len(ok)}/{len(module_status)}・{rate:.0f}%）",
            "detail": f"停止中: {', '.join(ng[:8])}"}


def run(prices: dict = None, module_status: list = None) -> dict:
    """
    システムの健康診断を行う。
    module_status は [(機能名, 生きているか), ...] の形（cloud_run が集計したもの）。
    """
    issues = []
    for check in (
        lambda: _check_report_freshness(),
        lambda: _check_learning_data(),
        lambda: _check_price_coverage(prices),
        lambda: _check_module_health(module_status),
    ):
        try:
            r = check()
            if r:
                issues.append(r)
        except Exception:
            logger.debug(traceback.format_exc())

    criticals = [i for i in issues if i["level"] == _CRITICAL]
    warnings = [i for i in issues if i["level"] == _WARNING]
    # 100点から減点していく（重い障害ほど大きく引く）
    score = max(0, 100 - len(criticals) * 40 - len(warnings) * 15)
    healthy = not issues

    if healthy:
        logger.info("🩺 自己診断: 異常なし（100点）")
        return {"healthy": True, "score": 100, "issues": [], "telegram_line": ""}

    for i in issues:
        (logger.error if i["level"] == _CRITICAL else logger.warning)(
            f"🩺 {i['msg']} — {i['detail']}")

    # 通知に載せるのは最も重い1件だけ（毎朝の通知を診断結果で埋めない）
    top = (criticals or warnings)[0]
    icon = "🚨" if top["level"] == _CRITICAL else "⚠️"
    line = f"{icon} *システム点検: {top['msg']}*"

    # 重大な障害（＝利用者に何も届いていない状態）は、その場で知らせる。
    # ログに書くだけでは今回のように長期間気づけないため。
    # 同じ障害で毎日鳴らないよう、通知台帳で1セッション1回に制限する。
    if criticals:
        try:
            from src.notify_ledger import filter_new
            fresh = filter_new([{"key": f"diag_{c['key']}", "title": c["msg"]}
                                for c in criticals], source="diag")
            if fresh:
                from src.notify_telegram import send_message
                body = "\n".join(f"・{c['msg']}\n　{c['detail']}" for c in criticals[:3])
                send_message(
                    "🩺 *システム点検で問題を検出しました*\n"
                    "━━━━━━━━━━━━━━━\n"
                    f"{body}\n"
                    "━━━━━━━━━━━━━━━\n"
                    "分析そのものではなく、配信の仕組み側の問題です。"
                    "修正されるまで内容が最新でない可能性があります。"
                )
                logger.info("🩺 障害を通知しました")
        except Exception:
            logger.error("障害通知の送信に失敗")
            logger.debug(traceback.format_exc())

    logger.warning(f"🩺 自己診断: {len(criticals)}件の重大 / {len(warnings)}件の注意（{score}点）")
    return {"healthy": False, "score": score, "issues": issues,
            "criticals": criticals, "telegram_line": line}


if __name__ == "__main__":
    r = run({"^N225": {"latest": 39000}}, [("A", True), ("B", False)])
    print(f"score={r['score']} healthy={r['healthy']}")
    for i in r["issues"]:
        print(f"  [{i['level']}] {i['msg']}")
