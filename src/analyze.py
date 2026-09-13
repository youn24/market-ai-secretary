"""
マクロ分析モジュール
事実・推測・意見を分けてテキスト分析を生成する
買い煽り・売り煽り・断定は禁止
"""
from src.utils import sign_label, setup_logger

logger = setup_logger("analyze")


def _fmt(p: dict, unit: str = "") -> str:
    v = p.get("latest")
    c = p.get("change_pct")
    if v is None:
        return "取得失敗"
    base = f"{v:,.2f}{unit}"
    if c is not None:
        chg = f"+{c:.2f}%" if c >= 0 else f"{c:.2f}%"
        return f"{base} ({chg})"
    return base


def analyze_forex(prices: dict) -> dict:
    """為替分析（事実・推測・注意点）"""
    usdjpy = prices.get("USDJPY=X", {})
    eurusd = prices.get("EURUSD=X", {})
    tnx = prices.get("^TNX", {})

    usdjpy_chg = usdjpy.get("change_pct")
    tnx_latest = tnx.get("latest")

    facts = []
    hypotheses = []
    cautions = []

    facts.append(f"ドル円: {_fmt(usdjpy, '円')}")
    facts.append(f"ユーロドル: {_fmt(eurusd)}")
    if tnx_latest:
        facts.append(f"米10年金利: {_fmt(tnx, '%')}")

    if usdjpy_chg is not None:
        if usdjpy_chg > 0.5:
            hypotheses.append("ドルが対円で上昇している。米金利動向や日米金利差の拡大が一因として考えられる（推測）。")
        elif usdjpy_chg < -0.5:
            hypotheses.append("ドルが対円で下落している。リスク回避や円買い需要が生じている可能性がある（推測）。")
        else:
            hypotheses.append("ドル円は小幅な動きにとどまっている（推測：方向感なし）。")

    cautions.append("為替は政策変更・要人発言・経済指標で急変する場合があります。")

    return {"facts": facts, "hypotheses": hypotheses, "cautions": cautions}


def analyze_us_market(prices: dict) -> dict:
    """米国株分析"""
    sp500 = prices.get("^GSPC", {})
    nasdaq = prices.get("^IXIC", {})
    dow = prices.get("^DJI", {})
    vix = prices.get("^VIX", {})

    facts = [
        f"S&P500: {_fmt(sp500)}",
        f"NASDAQ: {_fmt(nasdaq)}",
        f"ダウ: {_fmt(dow)}",
        f"VIX: {_fmt(vix)}",
    ]

    hypotheses = []
    vix_val = vix.get("latest")
    sp500_chg = sp500.get("change_pct")

    if vix_val and vix_val > 25:
        hypotheses.append(f"VIXが{vix_val:.1f}と高水準にある。市場参加者の不安感が高まっている可能性がある（推測）。")
    elif vix_val and vix_val < 15:
        hypotheses.append(f"VIXが{vix_val:.1f}と低水準にある。市場が比較的落ち着いていることを示唆する可能性がある（推測）。")

    if sp500_chg is not None:
        if sp500_chg > 1.0:
            hypotheses.append("S&P500が1%超の上昇。強い買い意欲がある可能性がある（推測）。")
        elif sp500_chg < -1.0:
            hypotheses.append("S&P500が1%超の下落。何らかの売り圧力が生じている可能性がある（推測）。")

    cautions = ["米国株は決算・経済指標・FRB発言に大きく反応します。個別の動きに注意してください。"]
    return {"facts": facts, "hypotheses": hypotheses, "cautions": cautions}


def analyze_japan_market(prices: dict) -> dict:
    """日本株分析"""
    nk = prices.get("^N225", {})
    topix = prices.get("^TOPX", {})
    usdjpy = prices.get("USDJPY=X", {})

    facts = [
        f"日経平均: {_fmt(nk, '円')}",
        f"TOPIX: {_fmt(topix)}",
        f"ドル円参考: {_fmt(usdjpy, '円')}",
    ]

    hypotheses = []
    nk_chg = nk.get("change_pct")
    usdjpy_chg = usdjpy.get("change_pct")

    if nk_chg is not None and usdjpy_chg is not None:
        if nk_chg > 0 and usdjpy_chg > 0:
            hypotheses.append("日経平均の上昇と円安が同時に見られる。輸出企業の業績期待が背景にある可能性がある（推測）。")
        elif nk_chg < 0 and usdjpy_chg < 0:
            hypotheses.append("日経平均の下落と円高が同時に見られる。リスクオフ的な動きである可能性がある（推測）。")

    cautions = ["日本株は米国株の動向・為替・日銀政策の影響を強く受けます。"]
    return {"facts": facts, "hypotheses": hypotheses, "cautions": cautions}


def analyze_rates(prices: dict) -> dict:
    """金利分析"""
    tnx = prices.get("^TNX", {})
    facts = [f"米10年金利(^TNX): {_fmt(tnx, '%')}"]
    hypotheses = []
    tnx_val = tnx.get("latest")
    tnx_chg = tnx.get("change_pct")

    if tnx_val and tnx_chg is not None:
        if tnx_chg > 0:
            hypotheses.append("米金利が上昇傾向にある。ドル高・株式のバリュエーション圧迫要因となる可能性がある（推測）。")
        else:
            hypotheses.append("米金利が低下傾向にある。景気不安や安全資産への逃避が反映されている可能性がある（推測）。")

    cautions = ["金利は日次で大きく動くことがあります。FRBの声明や雇用統計に注意してください。"]
    return {"facts": facts, "hypotheses": hypotheses, "cautions": cautions}


def analyze_commodities(prices: dict) -> dict:
    """コモディティ分析"""
    gold = prices.get("GC=F", {})
    oil = prices.get("CL=F", {})
    btc = prices.get("BTC-USD", {})

    facts = [
        f"金(GOLD): {_fmt(gold, 'USD')}",
        f"WTI原油: {_fmt(oil, 'USD')}",
        f"Bitcoin: {_fmt(btc, 'USD')}",
    ]

    hypotheses = []
    gold_chg = gold.get("change_pct")
    oil_chg = oil.get("change_pct")
    btc_chg = btc.get("change_pct")

    if gold_chg and gold_chg > 1.0:
        hypotheses.append("金が大幅上昇。安全資産への需要や地政学リスクの高まりが考えられる（推測）。")
    if oil_chg and abs(oil_chg) > 2.0:
        direction = "上昇" if oil_chg > 0 else "下落"
        hypotheses.append(f"原油が{direction}。供給・需要・地政学要因を確認することが望まれる（推測）。")
    if btc_chg and abs(btc_chg) > 5.0:
        direction = "大幅上昇" if btc_chg > 0 else "大幅下落"
        hypotheses.append(f"Bitcoinが{direction}。仮想通貨市場はボラティリティが高い点に注意が必要（推測）。")

    cautions = ["コモディティは地政学リスク・需給・為替の影響を受けます。Bitcoinは価格変動が非常に大きいです。"]
    return {"facts": facts, "hypotheses": hypotheses, "cautions": cautions}


def build_analysis(prices: dict, risk: dict) -> dict:
    """全分析を統合して返す。"""
    logger.info("=== 分析開始 ===")
    result = {
        "risk": risk,
        "forex":       analyze_forex(prices),
        "us_market":   analyze_us_market(prices),
        "japan_market": analyze_japan_market(prices),
        "rates":       analyze_rates(prices),
        "commodities": analyze_commodities(prices),
    }
    logger.info("=== 分析完了 ===")
    return result
