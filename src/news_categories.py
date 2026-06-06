"""
ニュースカテゴリ定義
各カテゴリの説明・アイコン・対応ソース・キーワードを管理
"""

CATEGORIES = {
    "🏦 日銀・日本政府": {
        "icon":        "🏦",
        "description": "日本の金融政策・財政政策の最新動向。日銀の金利決定・量的緩和・政府の経済対策など。",
        "sources":     ["日銀公式", "日銀政策", "首相官邸", "財務省", "政府動向", "財務省動向"],
        "labels":      ["日銀政策", "日銀公式", "首相官邸", "財務省", "政府動向", "財務省動向"],
        "keywords":    ["日銀", "日本銀行", "政策金利", "量的緩和", "植田", "財務省", "首相"],
        "watch_points": [
            "政策金利の変更・示唆はあるか",
            "国債買い入れ額の変化",
            "円安への政府コメント",
            "財政政策の新発表",
        ],
    },
    "🇺🇸 FRB・米国金融政策": {
        "icon":        "🇺🇸",
        "description": "米国FRBの金融政策・利上げ/利下げ確率。FOMCの声明・パウエル議長発言・FedWatch確率など。",
        "sources":     ["FRB政策", "FedWatch", "FedWatch利上げ確率"],
        "labels":      ["FRB政策", "FedWatch", "FedWatch利上げ確率"],
        "keywords":    ["FRB", "Fed", "FOMC", "利上げ", "利下げ", "パウエル", "FedWatch"],
        "watch_points": [
            "次回FOMC会合での利下げ確率",
            "パウエル議長の発言トーン",
            "インフレ指標への反応",
            "雇用統計の解釈",
        ],
    },
    "📈 米国株市場": {
        "icon":        "📈",
        "description": "S&P500・NASDAQ・ダウの動向。米国主要銘柄の決算・テクノロジー株の動き・市場センチメントなど。",
        "sources":     ["米国株市場", "MarketWatch", "Yahoo Finance", "Investing.com"],
        "labels":      ["米国株市場", "MarketWatch", "Yahoo Finance", "Investing.com"],
        "keywords":    ["米国株", "S&P", "NASDAQ", "ダウ", "Wall Street", "NYSE"],
        "watch_points": [
            "S&P500の主要サポートライン",
            "決算シーズンの進捗",
            "セクターローテーションの動き",
            "機関投資家のポジション",
        ],
    },
    "🗾 日本株市場": {
        "icon":        "🗾",
        "description": "日経平均・TOPIX・日本主要銘柄の動向。外国人投資家の動き・円相場との関係・企業決算など。",
        "sources":     ["日本株市場", "みんかぶ株", "日経225分析", "トレーダーズウェブ"],
        "labels":      ["日本株市場", "みんかぶ株", "日経225分析", "トレーダーズウェブ"],
        "keywords":    ["日本株", "日経", "東証", "TOPIX", "日経平均"],
        "watch_points": [
            "日経平均の前日比・出来高",
            "外国人投資家の売買動向",
            "円安恩恵銘柄の動き",
            "決算発表銘柄への反応",
        ],
    },
    "💱 為替・FX": {
        "icon":        "💱",
        "description": "ドル円・ユーロドル・為替全般の動向。日米金利差・介入リスク・テクニカル分析など。",
        "sources":     ["為替動向", "ドル円", "OANDA為替情報", "みんかぶFX", "トレーダーズウェブFX", "FXStreet（FX専門）"],
        "labels":      ["為替（ドル円）", "OANDA為替情報", "みんかぶFX", "トレーダーズウェブFX", "FXStreet（FX専門）"],
        "keywords":    ["為替", "ドル円", "円安", "円高", "FX", "USDJPY", "ユーロ"],
        "watch_points": [
            "ドル円の主要レジスタンス・サポート",
            "日本の為替介入リスク水準",
            "日米金利差の方向感",
            "リスクオン/オフの為替への影響",
        ],
    },
    "📊 金利・債券": {
        "icon":        "📊",
        "description": "米10年金利・日本国債・各国金利の動向。インフレ期待・安全資産への逃避・イールドカーブなど。",
        "sources":     ["金利動向"],
        "labels":      ["金利動向"],
        "keywords":    ["金利", "国債", "利回り", "イールド", "債券"],
        "watch_points": [
            "米10年金利の方向性",
            "実質金利の変化",
            "日米金利差の推移",
            "逆イールドカーブの状況",
        ],
    },
    "⛽ コモディティ": {
        "icon":        "⛽",
        "description": "原油・天然ガス・金・農産物の動向。OPEC政策・地政学リスク・ドル相場との関係など。",
        "sources":     ["原油市場"],
        "labels":      ["原油市場"],
        "keywords":    ["原油", "WTI", "OPEC", "天然ガス", "コモディティ"],
        "watch_points": [
            "OPECプラスの生産方針",
            "米国在庫統計",
            "地政学リスクの原油への影響",
            "金の安全資産需要",
        ],
    },
    "💻 半導体・テクノロジー": {
        "icon":        "💻",
        "description": "半導体産業・AI・テクノロジー株の動向。NVIDIA・台湾TSMC・AI需要・輸出規制など。",
        "sources":     ["半導体産業"],
        "labels":      ["半導体産業"],
        "keywords":    ["半導体", "AI", "NVIDIA", "TSMC", "テクノロジー", "チップ"],
        "watch_points": [
            "AI関連需要の変化",
            "米中半導体規制の動き",
            "NVIDIA・TSMCの業績",
            "日本半導体株への影響",
        ],
    },
    "🏢 企業・決算・信用": {
        "icon":        "🏢",
        "description": "企業決算・倒産情報・企業信用動向。帝国データバンクの倒産統計・主要企業の業績発表など。",
        "sources":     ["企業決算", "帝国DB企業信用", "帝国データバンク", "PayPay証券情報"],
        "labels":      ["企業決算", "帝国DB企業信用", "帝国データバンク", "PayPay証券情報"],
        "keywords":    ["決算", "倒産", "企業", "業績", "売上", "利益"],
        "watch_points": [
            "主要企業の決算サプライズ",
            "倒産件数トレンド",
            "セクター別の業績傾向",
            "上方修正・下方修正の動き",
        ],
    },
    "🌍 地政学リスク": {
        "icon":        "🌍",
        "description": "地政学的リスク・国際情勢の動向。戦争・制裁・貿易摩擦・政治的不安定要素など。",
        "sources":     ["地政学リスク"],
        "labels":      ["地政学リスク"],
        "keywords":    ["地政学", "戦争", "制裁", "紛争", "貿易", "関税"],
        "watch_points": [
            "主要紛争地域の最新動向",
            "米中貿易摩擦の状況",
            "制裁・関税の新発表",
            "原油・商品市場への影響",
        ],
    },
    "📰 総合・その他": {
        "icon":        "📰",
        "description": "上記カテゴリに含まれないその他の経済・金融ニュース。",
        "sources":     ["NHK 経済", "NHK トップ", "Yahoo! ファイナンス", "東洋経済"],
        "labels":      ["NHK 経済", "NHK トップ", "Yahoo! ファイナンス", "東洋経済"],
        "keywords":    [],
        "watch_points": [],
    },
}


def categorize_news(news_list: list[dict]) -> dict[str, list[dict]]:
    """ニュースをカテゴリ別に仕分けする"""
    categorized = {cat: [] for cat in CATEGORIES}
    used = set()

    for item in news_list:
        src_name = item.get("source_name", "") or item.get("source", "")
        label    = item.get("label", "")
        title    = item.get("title", "").lower()
        idx      = id(item)

        assigned = False
        for cat_name, cat_cfg in CATEGORIES.items():
            if cat_name == "📰 総合・その他":
                continue
            # ソース名・ラベルで判定
            if any(s in src_name for s in cat_cfg["sources"]) or \
               any(l in label for l in cat_cfg["labels"]):
                categorized[cat_name].append(item)
                used.add(idx)
                assigned = True
                break
            # キーワードで判定
            if any(k.lower() in title for k in cat_cfg["keywords"]):
                categorized[cat_name].append(item)
                used.add(idx)
                assigned = True
                break

        if not assigned:
            categorized["📰 総合・その他"].append(item)

    # 重複除去・重要度順ソート
    imp_order = {"A": 0, "B": 1, "C": 2}
    for cat in categorized:
        seen_titles = set()
        deduped = []
        for item in categorized[cat]:
            t = item.get("title", "")
            if t not in seen_titles:
                seen_titles.add(t)
                deduped.append(item)
        categorized[cat] = sorted(
            deduped,
            key=lambda x: imp_order.get(x.get("importance", "C"), 2)
        )

    return categorized
