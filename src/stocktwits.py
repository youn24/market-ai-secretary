"""
src/stocktwits.py — 米国個人投資家の感情（Stocktwits）

Stocktwits は米国の個人投資家向けSNS。投稿者自身が Bullish / Bearish の
タグを付けるため、文章を推測で判定する必要がなく精度が高い。

  取得元: https://api.stocktwits.com/api/2/streams/symbol/{SYMBOL}.json
  1銘柄あたり直近30件。うちタグ付きは7〜19件程度。

【重要: 生の強気率をそのまま信じない】
実測すると、ほぼ全銘柄で強気率が60〜100%に偏る。
SNSは「買った人が発言する」場なので構造的に強気に寄るため、
生の数字を「強気80%だから買い」と読むと必ず間違える。

そこで **相対評価** を採用する。
  ・監視銘柄全体の平均強気率を「その日の基準」として算出
  ・各銘柄がその基準からどれだけ離れているかで強弱を判定
これにより「他と比べて弱い（＝実は嫌われている）」銘柄が浮かび上がる。

【日本株との関係】
SONY / TM / MUFG などの日本株ADRも対象。
米国の個人投資家が日本企業をどう見ているかが分かる。

⚠️ 個人の投稿のため、ポジショントークが混ざる。
   多数派が正しいとは限らず、極端な偏りは逆張りの目安にもなる。

【Gemini は使用しない】タグの集計のみでAPIトークンを消費しない。
"""

import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from src.utils import setup_logger

logger = setup_logger("stocktwits")

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36"}
_URL = "https://api.stocktwits.com/api/2/streams/symbol/{sym}.json"

# (シンボル, 表示名, 分類)
WATCHLIST = [
    ("NVDA", "エヌビディア",   "半導体"),
    ("AVGO", "ブロードコム",   "半導体"),
    ("MU",   "マイクロン",     "半導体"),
    ("TSLA", "テスラ",         "EV"),
    ("AAPL", "アップル",       "ハイテク"),
    ("SONY", "ソニーG",        "日本株ADR"),
    ("TM",   "トヨタ",         "日本株ADR"),
    ("MUFG", "三菱UFJ",        "日本株ADR"),
]

_MIN_TAGGED = 5      # タグ付き投稿がこれ未満なら判定しない（サンプル不足）


def _fetch_one(sym: str, name: str, cat: str) -> dict | None:
    try:
        r = requests.get(_URL.format(sym=sym), headers=_HEADERS, timeout=20)
        if r.status_code != 200:
            logger.debug(f"Stocktwits {sym}: status={r.status_code}")
            return None
        msgs = (r.json() or {}).get("messages", []) or []
        bull = bear = 0
        samples = []
        for m in msgs:
            tag = ((m.get("entities") or {}).get("sentiment") or {}).get("basic")
            if tag == "Bullish":
                bull += 1
            elif tag == "Bearish":
                bear += 1
            else:
                continue
            if len(samples) < 2:
                body = (m.get("body") or "").replace("\n", " ")[:80]
                samples.append({"tag": tag, "body": body})
        tagged = bull + bear
        if tagged < _MIN_TAGGED:
            return None
        return {
            "symbol": sym, "name": name, "category": cat,
            "posts": len(msgs), "tagged": tagged,
            "bull": bull, "bear": bear,
            "bull_ratio": round(bull / tagged * 100, 1),
            "samples": samples,
        }
    except Exception:
        logger.debug(traceback.format_exc())
        return None


def _relative_label(ratio: float, base: float) -> tuple:
    """
    全体平均（base）と比べた相対評価。
    SNSは構造的に強気へ偏るため、生の数字ではなく偏差で見る。
    """
    diff = ratio - base
    if   diff >= 20: return "🔥", "突出して強気", "他銘柄より際立って買い意欲が強い"
    if   diff >= 8:  return "🟢", "やや強気",     "平均より強気寄り"
    if   diff > -8:  return "⚪", "平均並み",     "全体と同程度"
    if   diff > -20: return "🔹", "やや弱気",     "平均より弱気寄り"
    return "🔴", "際立って弱気", "他銘柄より明確に嫌われている（要注意）"


def run(*_args, **_kwargs) -> dict:
    """
    米国個人投資家の感情を取得し、相対評価する。
    返り値: {available, base_ratio, stocks: [...], telegram_block}
    """
    result = {"available": False, "stocks": []}
    try:
        rows = []
        with ThreadPoolExecutor(max_workers=4) as ex:
            futs = {ex.submit(_fetch_one, s, n, c): s for s, n, c in WATCHLIST}
            for f in as_completed(futs):
                r = f.result()
                if r:
                    rows.append(r)
        if len(rows) < 3:
            logger.info(f"Stocktwits: 有効データ{len(rows)}件のみ。判定を見送り")
            return result

        # その日の基準＝監視銘柄の平均強気率
        base = sum(r["bull_ratio"] for r in rows) / len(rows)
        for r in rows:
            emoji, label, note = _relative_label(r["bull_ratio"], base)
            r.update({"emoji": emoji, "label": label, "note": note,
                      "diff": round(r["bull_ratio"] - base, 1)})
        rows.sort(key=lambda x: -x["bull_ratio"])

        result.update({
            "available": True,
            "base_ratio": round(base, 1),
            "stocks": rows,
            "telegram_block": build_block(rows, base),
        })
        logger.info(f"✅ Stocktwits: {len(rows)}銘柄（基準強気率 {base:.0f}%）")
        return result
    except Exception:
        logger.error("Stocktwitsエラー")
        logger.debug(traceback.format_exc())
        return result


def build_block(rows: list, base: float) -> str:
    top, bottom = rows[0], rows[-1]
    lines = [
        "🇺🇸 *米国個人投資家の感情*（Stocktwits）",
        f"本日の基準（全体平均）強気率 {base:.0f}%",
    ]
    # 目立つものだけ出す（平均並みは省いて読みやすく）
    notable = [r for r in rows if abs(r["diff"]) >= 8]
    for r in notable[:4]:
        jp = "🗾" if r["category"] == "日本株ADR" else ""
        lines.append(f"{r['emoji']} {jp}*{r['name']}* 強気{r['bull_ratio']:.0f}%"
                     f"（基準比 {r['diff']:+.0f}pt）— {r['label']}")
    if not notable:
        lines.append("　全銘柄が平均並み。目立った偏りなし。")

    # 日本株ADRだけ別途まとめる（東京市場に効くため）
    adr = [r for r in rows if r["category"] == "日本株ADR"]
    if adr:
        s = " / ".join(f"{r['name']} {r['bull_ratio']:.0f}%" for r in adr)
        lines.append(f"🗾 日本株ADR: {s}")

    lines.append("※SNSは「買った人が発言する」場のため強気に偏ります。"
                 "生の数値ではなく“他銘柄との差”でご覧ください。")
    return "\n".join(lines)


def run_report() -> bool:
    try:
        res = run()
        if not res.get("available"):
            logger.info("Stocktwits: 送信スキップ")
            return False
        from src.notify_telegram import send_message
        ok = send_message(res["telegram_block"])
        if ok:
            logger.info("✅ 米国個人投資家の感情を送信")
        return bool(ok)
    except Exception:
        logger.error("Stocktwits 送信エラー")
        logger.debug(traceback.format_exc())
        return False


if __name__ == "__main__":
    run_report()
