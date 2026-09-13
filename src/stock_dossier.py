"""
銘柄カルテ（プロアナリスト × 熟練トレーダー統合ビュー）
既存の kabuyoho / financial_analyzer / prices を 1 枚のカードに束ね
合わせ技スコア（コンフルエンス）と TradingView ディープリンクを付与する。

run(prices, risk, ...) → {"available": True, "dossiers": [...]}

各 dossier:
  code         : 証券コード（数字のみ）
  name         : 銘柄名
  close        : 現在値
  change_pct   : 前日比 (%)
  target       : 目標株価（kabuyoho）
  upside       : 目標までの上値余地 (%)
  per / pbr    : バリュエーション指標
  yield_       : 配当利回り (%)
  pos_52w      : 52 週レンジ内位置 (%)
  rating       : アナリストレーティング
  roe          : ROE (%)
  op_margin    : 営業利益率 (%)
  confluence   : 合わせ技スコア (0–10)
  breakdown    : dict  各要素のスコアと理由
  tv_link      : TradingView チャートリンク
  entry_zone   : エントリー目安テキスト
  stop_loss    : 損切り目安テキスト
  risk_reward  : リスクリワード比テキスト
  confidence   : high / mid / low
"""

import yaml
from pathlib import Path
from src.utils import BASE_DIR, setup_logger

logger = setup_logger("stock_dossier")

_TV_BASE = "https://jp.tradingview.com/chart/?symbol=TSE:{code}"
_WATCHLIST_FILE = BASE_DIR / "config" / "watchlist.yaml"
_SYMBOLS_FILE   = BASE_DIR / "config" / "symbols.yaml"


def _load_watchlist() -> list[tuple[str, str]]:
    """watchlist.yaml → [(code, name), ...]. なければ symbols.yaml の jp_stocks を使う"""
    if _WATCHLIST_FILE.exists():
        try:
            data = yaml.safe_load(_WATCHLIST_FILE.read_text(encoding="utf-8")) or {}
            items = data.get("stocks", data.get("watchlist", []))
            return [(str(i.get("code", i.get("symbol", ""))).split(".")[0],
                     i.get("name", "")) for i in items if i]
        except Exception:
            pass

    # フォールバック: symbols.yaml の jp_stocks
    try:
        cfg = yaml.safe_load(_SYMBOLS_FILE.read_text(encoding="utf-8")) or {}
        return [(str(i["symbol"]).split(".")[0], i.get("name", ""))
                for i in cfg.get("jp_stocks", [])]
    except Exception:
        return []


def _tv_link(code: str) -> str:
    return _TV_BASE.format(code=code)


def _confluence_score(kb: dict, fa: dict, price_entry: dict, risk: dict) -> tuple[int, dict]:
    """
    5 軸で合わせ技スコアを算出（各 0–2 点 → 合計 0–10）。
    トップダウン（地合い→バリュエ→テクニカル→モメンタム→需給）の順。
    """
    bd = {}

    # 1. 地合い（環境）: market risk score
    rscore = risk.get("score", 0)
    if rscore >= 2:
        s1, r1 = 2, f"強気地合い (+{rscore:.1f}pt)"
    elif rscore >= 0:
        s1, r1 = 1, f"中立地合い ({rscore:+.1f}pt)"
    else:
        s1, r1 = 0, f"弱気地合い ({rscore:.1f}pt)"
    bd["環境(地合い)"] = {"score": s1, "reason": r1}

    # 2. バリュエーション（上値余地 × 割安感）
    upside = kb.get("upside")
    per    = kb.get("per") or fa.get("per") or 999
    if upside is not None and upside >= 15 and per < 20:
        s2, r2 = 2, f"目標まで+{upside:.0f}% PER={per:.1f}で割安"
    elif upside is not None and upside >= 8:
        s2, r2 = 1, f"目標まで+{upside:.0f}%の余地"
    else:
        s2, r2 = 0, f"上値余地小または割高"
    bd["バリュエーション"] = {"score": s2, "reason": r2}

    # 3. テクニカル（52 週レンジ位置）
    pos = kb.get("pos_52w")
    if pos is not None and 25 <= pos <= 65:
        s3, r3 = 2, f"52週中間帯 {pos:.0f}%（過熱せず底値でもない）"
    elif pos is not None and pos < 25:
        s3, r3 = 1, f"52週安値圏 {pos:.0f}%（リバウンド候補）"
    elif pos is not None and pos > 80:
        s3, r3 = 0, f"52週高値圏 {pos:.0f}%（調整リスク大）"
    else:
        s3, r3 = 1, "52週位置不明（中立扱い）"
    bd["テクニカル(52W位置)"] = {"score": s3, "reason": r3}

    # 4. モメンタム（当日変化率）
    chg = price_entry.get("change_pct") or 0
    if chg >= 1.5:
        s4, r4 = 2, f"強いモメンタム (+{chg:.2f}%)"
    elif chg >= 0:
        s4, r4 = 1, f"小幅高 ({chg:+.2f}%)"
    else:
        s4, r4 = 0, f"下落 ({chg:.2f}%)"
    bd["モメンタム(当日)"] = {"score": s4, "reason": r4}

    # 5. 需給（レーティング）
    rating = (kb.get("rating") or "").strip()
    if "強く買い" in rating or "Buy" in rating:
        s5, r5 = 2, f"レーティング: {rating}"
    elif "買い" in rating or "中立" in rating:
        s5, r5 = 1, f"レーティング: {rating}"
    else:
        s5, r5 = 0, f"レーティング: {rating or '未取得'}"
    bd["需給(レーティング)"] = {"score": s5, "reason": r5}

    total = s1 + s2 + s3 + s4 + s5
    return total, bd


def _entry_guidance(kb: dict, price_entry: dict) -> tuple[str, str, str]:
    """エントリー目安・損切り・リスクリワードを文字列で返す"""
    close = kb.get("close") or price_entry.get("latest")
    prev  = price_entry.get("prev_close")
    target = kb.get("target")
    pos  = kb.get("pos_52w")
    lo52 = kb.get("w52_low")

    if not close:
        return "現値付近", "前日安値または直近サポート", "未算出"

    # 損切り: 前日終値 vs 52W安値の近い方
    if prev and lo52:
        stop = min(prev * 0.99, lo52 * 1.01)
    elif prev:
        stop = prev * 0.99
    else:
        stop = close * 0.97

    risk_yen = close - stop
    reward   = (target - close) if target else close * 0.05
    rr_ratio = reward / risk_yen if risk_yen > 0 else 0

    entry_str = f"現値 {close:,.0f}円 付近（or 押し目）"
    stop_str  = f"{stop:,.0f}円 割れで損切り（前日安値/支持線目安）"
    rr_str    = f"RR={rr_ratio:.1f}:1 (目標 {target:,.0f}円)" if target else "目標株価未取得"

    return entry_str, stop_str, rr_str


def _confidence(confluence: int, kb: dict) -> str:
    if confluence >= 8 and kb.get("available"):
        return "high"
    if confluence >= 5:
        return "mid"
    return "low"


def build_dossier(code: str, name: str, prices: dict, risk: dict) -> dict:
    """1 銘柄のカルテを構築して返す"""
    # Yahoo Finance の prices に JP コードがある場合（例 "7203.T"）
    sym_yf  = f"{code}.T"
    price_entry = prices.get(sym_yf) or prices.get(code) or {}

    # kabuyoho から基本データ取得
    kb = {"available": False}
    try:
        from src.kabuyoho import fetch_kabuyoho
        kb = fetch_kabuyoho(code)
    except Exception as e:
        logger.warning(f"kabuyoho 取得失敗 [{code}]: {e}")

    # financial_analyzer から財務データ取得（軽量モード: AI呼ばず rawのみ）
    fa = {"available": False}
    try:
        from src.financial_analyzer import analyze_company
        fa = analyze_company(sym_yf, name)
    except Exception as e:
        logger.warning(f"financial_analyzer 取得失敗 [{code}]: {e}")

    confluence, bd = _confluence_score(kb, fa, price_entry, risk)
    entry_str, stop_str, rr_str = _entry_guidance(kb, price_entry)
    conf_level = _confidence(confluence, kb)

    # close は kabuyoho → prices の順で取得
    close = kb.get("close") or price_entry.get("latest")
    chg   = price_entry.get("change_pct")

    return {
        "code":        code,
        "name":        name or kb.get("name", sym_yf),
        "close":       close,
        "change_pct":  chg,
        "target":      kb.get("target"),
        "upside":      kb.get("upside"),
        "per":         kb.get("per") or fa.get("per"),
        "pbr":         kb.get("pbr") or fa.get("pbr"),
        "yield_":      kb.get("yield"),
        "pos_52w":     kb.get("pos_52w"),
        "w52_high":    kb.get("w52_high"),
        "w52_low":     kb.get("w52_low"),
        "rating":      kb.get("rating"),
        "roe":         fa.get("roe"),
        "op_margin":   fa.get("op_margin"),
        "revenue":     fa.get("revenue"),
        "net_income":  fa.get("net_income"),
        "confluence":  confluence,
        "breakdown":   bd,
        "tv_link":     _tv_link(code),
        "entry_zone":  entry_str,
        "stop_loss":   stop_str,
        "risk_reward": rr_str,
        "confidence":  conf_level,
        "kb_ok":       kb.get("available", False),
        "fa_ok":       fa.get("available", False),
    }


def run(prices: dict = None, risk: dict = None, fear_greed: dict = None,
        max_stocks: int = 10) -> dict:
    """
    ウォッチリスト全銘柄のカルテを構築し、合わせ技スコア上位を返す。
    max_stocks: 上位何件を返すか（デフォルト 10）
    """
    prices = prices or {}
    risk   = risk   or {"score": 0, "sentiment": "不明"}

    watchlist = _load_watchlist()
    if not watchlist:
        logger.warning("ウォッチリストが空のため stock_dossier をスキップ")
        return {"available": False, "dossiers": []}

    dossiers = []
    for code, name in watchlist:
        if not code:
            continue
        try:
            d = build_dossier(code, name, prices, risk)
            dossiers.append(d)
        except Exception as e:
            logger.warning(f"dossier 構築失敗 [{code}]: {e}")

    # 合わせ技スコア降順にソートして上位を返す
    dossiers.sort(key=lambda x: x.get("confluence", 0), reverse=True)
    top = dossiers[:max_stocks]

    logger.info(
        f"stock_dossier 完了: {len(dossiers)}銘柄 → 上位{len(top)}件 "
        f"最高スコア={top[0]['confluence'] if top else 0}"
    )
    return {"available": True, "dossiers": top, "total": len(dossiers)}


if __name__ == "__main__":
    import json
    # 簡易テスト（ネットワーク呼び出し発生）
    result = run(prices={}, risk={"score": 1.5, "sentiment": "やや強気"}, max_stocks=3)
    if result.get("available"):
        for d in result["dossiers"]:
            print(f"{d['code']} {d['name']}: confluence={d['confluence']} conf={d['confidence']}")
            print(f"  TradingView: {d['tv_link']}")
            print(f"  エントリー: {d['entry_zone']}")
            print(f"  損切り: {d['stop_loss']}")
    else:
        print("スキップ（ウォッチリスト空または取得失敗）")
