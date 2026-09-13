"""
日本 業種別ランキング（TOPIX-17 業種ETF）
Yahoo chart APIで17業種ETFの最新値・前日比を取得し、前日比降順でランキング化する。
docs/sector_ranking.json に書き出し、HTML側がポーリングして準リアルタイム更新する。
APIキー不要・外部ライブラリ不要（標準ライブラリのみ）。
"""
import json
import urllib.request
from pathlib import Path
from src.utils import setup_logger, get_jst_now

logger = setup_logger("sector_ranking_jp")

# TOPIX-17 業種別ETF（NEXT FUNDS シリーズ）
ETFS = {
    "1617.T": "食品",
    "1618.T": "エネルギー資源",
    "1619.T": "建設・資材",
    "1620.T": "素材・化学",
    "1621.T": "医薬品",
    "1622.T": "自動車・輸送機",
    "1623.T": "鉄鋼・非鉄",
    "1624.T": "機械",
    "1625.T": "電機・精密",
    "1626.T": "情報通信・サービス他",
    "1627.T": "電力・ガス",
    "1628.T": "運輸・物流",
    "1629.T": "商社・卸売",
    "1630.T": "小売",
    "1631.T": "銀行",
    "1632.T": "金融(除く銀行)",
    "1633.T": "不動産",
}

# 業種ETFは流動性が低く終値が飛ぶことがある。この%を超える日次変動は異常値として除外
_ABNORMAL_PCT = 18.0


def _fetch_one(sym: str) -> dict | None:
    """1銘柄の現在値・前日終値を取得"""
    # ⚠️ chartPreviousClose を前日終値に使わないこと。
    # range=5d でも「5日前の直前」を指すため、実測で17業種すべての前日比が
    # 誤っていた（医薬品は +3.80% と表示していたが実際は -1.47% で符号まで逆）。
    # 前日終値の判定は src/quote_util.py に一本化してある。
    try:
        from src.quote_util import quote
        q = quote(sym, rng="5d")
        if not q:
            return None
        return {"price": q["price"], "prev": q["prev"],
                "state": q["meta"].get("marketState", "")}
    except Exception as e:
        logger.debug(f"{sym} 取得失敗: {e}")
        return None


def fetch_ranking() -> dict:
    """17業種ETFを取得し前日比降順でランキング化"""
    rows = []
    market_state = ""
    for sym, name in ETFS.items():
        r = _fetch_one(sym)
        if not r:
            continue
        market_state = market_state or r["state"]
        cur, prev = r["price"], r["prev"]
        chg = cur - prev
        pct = chg / prev * 100
        if abs(pct) > _ABNORMAL_PCT:
            # 流動性による飛び値の可能性が高い → ランキングから除外
            logger.warning(f"{name}({sym}) 異常変動 {pct:+.1f}% を除外")
            continue
        rows.append({
            "symbol": sym,
            "name":   name,
            "price":  round(cur, 2),
            "prev":   round(prev, 2),
            "chg":    round(chg, 2),
            "pct":    round(pct, 2),
        })

    rows.sort(key=lambda x: x["pct"], reverse=True)
    for i, row in enumerate(rows, 1):
        row["rank"] = i

    # 市場状態の日本語化
    state_ja = {
        "REGULAR": "ザラ場（取引中）",
        "PRE":     "寄付前",
        "POST":    "引け後",
        "POSTPOST":"引け後",
        "CLOSED":  "場が閉じています",
        "PREPRE":  "寄付前",
    }.get(market_state, "")

    return {
        "available":    bool(rows),
        "generated_at": get_jst_now().strftime("%Y-%m-%d %H:%M JST"),
        "market_state": state_ja,
        "count":        len(rows),
        "ranking":      rows,
        "top":          rows[0] if rows else None,
        "bottom":       rows[-1] if rows else None,
    }


def _write_json(data: dict):
    """docs/sector_ranking.json に書き出す（HTML側がポーリングして読む）"""
    try:
        docs = Path(__file__).parent.parent / "docs"
        docs.mkdir(exist_ok=True)
        out = docs / "sector_ranking.json"
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"✅ docs/sector_ranking.json 書き出し（{data.get('count',0)}業種）")
    except Exception as e:
        logger.error(f"JSON書き出しエラー: {e}")


def run() -> dict:
    """メイン（cloud_run.py / intraday_run.py から呼ぶ）"""
    logger.info("--- 日本業種別ランキング取得 ---")
    data = fetch_ranking()
    if data.get("available"):
        _write_json(data)
        t = data.get("top", {})
        b = data.get("bottom", {})
        logger.info(f"首位: {t.get('name')} {t.get('pct'):+.2f}% / "
                    f"最下位: {b.get('name')} {b.get('pct'):+.2f}%")
    else:
        logger.warning("業種別ランキング: データ取得失敗")
    return data


if __name__ == "__main__":
    import sys
    r = run()
    print(json.dumps(r, ensure_ascii=False, indent=2))
