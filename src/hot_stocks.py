"""
src/hot_stocks.py — 話題株ウォッチャー（数字 × 株クラの声）

株ドラゴンで「実際に資金が集まった銘柄」を拾い、
その銘柄を株クラ（X）がどう見ているかを株ライン経由で調べて突き合わせる。

【なぜ組み合わせるのか】
数字だけでは「なぜ動いたか」が分からず、
株クラの声だけでは「本当に買われたのか」が分からない。
両方そろって初めて意味を持つ。

【解釈のロジック】
値動きと株クラの温度感がズレているときこそ情報価値が高い。

  急騰 × 強気   … 順張り。ただし全員が強気＝過熱のサインでもある
  急騰 × 弱気   … 懐疑的な中の上昇。ふるい落としが済んでおらず伸び余地
  急落 × 強気   … 押し目待ちが多い＝まだ investors が降りておらず下げ止まりにくい
  急落 × 弱気   … 投げ売りが進行。一巡すれば反発の芽

⚠️ 株クラの投稿にはポジショントークが混ざる。
   「多数派＝正しい」ではなく、あくまで温度感として扱う。

【Gemini は使用しない】
感情判定は辞書ベース（src/kabuline.py）。API のトークンを一切消費しない。
"""

import traceback

from src.utils import setup_logger

logger = setup_logger("hot_stocks")

_TOP_N = 3          # 追跡する銘柄数（サイト負荷を考えて絞る）


def _verdict(chg_pct: float, bull_ratio: float) -> tuple:
    """値動き × 株クラ感情 の組み合わせを解釈する"""
    hot  = chg_pct >= 5.0
    cold = chg_pct <= -5.0
    bull = bull_ratio >= 60
    bear = bull_ratio <= 40

    if hot and bull:
        return ("🔥", "急騰 × 強気",
                "資金も評価も集まっている状態。ただし全員が強気＝過熱の裏返しでもある。"
                "高値づかみに注意。")
    if hot and bear:
        return ("👀", "急騰 × 懐疑的",
                "上がっているのに株クラは懐疑的。ふるい落としが済んでおらず、"
                "疑いが晴れると一段高になることがある。")
    if cold and bull:
        return ("⚠️", "急落 × 強気",
                "下げているのに強気が多い＝押し目待ちが降りていない。"
                "投げ売りが出切っておらず、下げ止まりにくい形。")
    if cold and bear:
        return ("🌱", "急落 × 弱気",
                "投げ売りが進行中。売り一巡なら反発の芽が出やすい局面。")
    if hot:
        return ("📈", "急騰 × 中立", "上昇しているが株クラの評価は割れている。")
    if cold:
        return ("📉", "急落 × 中立", "下落しているが株クラの見方は定まっていない。")
    return ("➡️", "小動き", "値動き・評価とも目立った偏りなし。")


def run(*_args, **_kwargs) -> dict:
    """
    株ドラゴンの上位銘柄 × 株クラの声 を突き合わせる。
    返り値: {available, stocks: [...], telegram_block}
    """
    result = {"available": False, "stocks": []}
    try:
        from src.kabudragon import run as kd_run
        kd = kd_run()
        if not kd.get("available"):
            logger.info("話題株: 株ドラゴンが取得できずスキップ")
            return result

        rankings = kd.get("rankings") or {}
        # 値上がり上位 → 値下がり上位 の順に候補を集め、重複は除く
        cands, seen = [], set()
        for key, tag in (("age", "値上がり"), ("sage", "値下がり")):
            for it in (rankings.get(key) or {}).get("items", []):
                code = str(it.get("code", "")).strip()
                if not code or code in seen:
                    continue
                if it.get("chg_pct") is None:
                    continue
                seen.add(code)
                cands.append({"code": code, "name": it.get("name", ""),
                              "chg_pct": float(it["chg_pct"]), "rank_type": tag})
                break                      # 各ランキングから1銘柄ずつ
        # 値上がり2位も加えて計3銘柄にする
        for it in (rankings.get("age") or {}).get("items", [])[1:]:
            if len(cands) >= _TOP_N:
                break
            code = str(it.get("code", "")).strip()
            if code and code not in seen and it.get("chg_pct") is not None:
                seen.add(code)
                cands.append({"code": code, "name": it.get("name", ""),
                              "chg_pct": float(it["chg_pct"]), "rank_type": "値上がり"})

        if not cands:
            return result

        from src.kabuline import fetch_stock
        import time
        stocks = []
        for c in cands[:_TOP_N]:
            kl = fetch_stock(c["code"], c["name"])
            time.sleep(1.0)               # サイトへの負荷配慮
            if not kl.get("available"):
                # 株クラの声が取れなくても、数字だけは残す
                stocks.append({**c, "has_voice": False})
                continue
            st = kl["sentiment"]
            emoji, title, note = _verdict(c["chg_pct"], st["bull_ratio"])
            stocks.append({
                **c, "has_voice": True,
                "sentiment": st, "keywords": kl.get("keywords", []),
                "verdict_emoji": emoji, "verdict": title, "note": note,
                "sample": (kl["tweets"][0]["text"][:70] if kl.get("tweets") else ""),
            })

        if not stocks:
            return result
        result["stocks"] = stocks
        result["available"] = True
        result["telegram_block"] = build_block(stocks)
        logger.info(f"✅ 話題株ウォッチ: {len(stocks)}銘柄（Gemini不使用）")
        return result
    except Exception:
        logger.error("話題株ウォッチャーエラー")
        logger.debug(traceback.format_exc())
        return result


def build_block(stocks: list) -> str:
    """朝レポート用のブロック"""
    lines = ["🔥 *話題株ウォッチ*（値動き × 株クラの声）"]
    for s in stocks:
        arrow = "▲" if s["chg_pct"] >= 0 else "▼"
        head = f"{arrow}{abs(s['chg_pct']):.1f}%"
        if not s.get("has_voice"):
            lines.append(f"・*{s['name']}*（{s['code']}）{head} — 株クラの声は取得できず")
            continue
        st = s["sentiment"]
        lines += [
            "",
            f"{s['verdict_emoji']} *{s['name']}*（{s['code']}）{head}"
            f"　→ *{s['verdict']}*",
            f"　株クラ: 強気{st['bull']} / 弱気{st['bear']}（強気率{st['bull_ratio']:.0f}%）",
            f"　{s['note']}",
        ]
        if s.get("keywords"):
            lines.append(f"　🏷 {' / '.join(s['keywords'][:4])}")
    lines.append("\n※株クラの投稿にはポジショントークが混ざります。"
                 "多数派が正しいとは限りません。")
    return "\n".join(lines)


def run_report() -> bool:
    try:
        res = run()
        if not res.get("available"):
            logger.info("話題株ウォッチ: 送信スキップ")
            return False
        from src.notify_telegram import send_message
        ok = send_message(res["telegram_block"])
        if ok:
            logger.info("✅ 話題株ウォッチを送信")
        return bool(ok)
    except Exception:
        logger.error("話題株ウォッチ 送信エラー")
        logger.debug(traceback.format_exc())
        return False


if __name__ == "__main__":
    run_report()
