# -*- coding: utf-8 -*-
"""出典の台帳（Step SRC）— 「この数字はどこから来たか」を1か所で持つ

オーナー指示（2026-11-19）:
  「画像などサイトや公式から必ず出典引用してほしい。どの緊急アラートでも。」

**なぜ台帳を1か所にするか**
  出典を各モジュールに直書きすると、必ず次の2つが起きる。

  1. **先方がURLを変えたとき、直し漏れる。** この案件では実際に
     nikkei225jp.com がフォルダ名を1語変えただけで日経内部データが
     1ヶ月止まっている。出典リンクでも同じことが起きる。
  2. **同じ数字に別々の出典が付く。** 朝のレポートと緊急アラートで
     日経VIの出典が食い違うと、どちらが本当か読む人には分からない。

  なので「名前・URL・何に使っているか」をここだけに置き、
  各モジュールは `cite("nikkei_vi")` のように**鍵で引く**。

**使い方**

    from src.sources import cite, cite_image, cite_html

    cite("yahoo", "nikkei225jp")   # → "📚 出典: [Yahoo Finance](...)・[...](...)"  Telegram用
    cite_image("yahoo")            # → "出典: Yahoo Finance（finance.yahoo.com）"   画像に焼く用
    cite_html("fred")              # → '<a href="...">FRED（セントルイス連銀）</a>' レポート用

⚠️ **出典に書いた場所から本当に取っていること。**
   「それらしい公式サイト」を飾りで並べてはいけない。実際に叩いている
   URLの持ち主を書く。ここが嘘だと、数字が正しくても信用が崩れる。
"""
from src.utils import setup_logger

logger = setup_logger("sources")


# 鍵: (表示名, 入口URL, 何に使っているか)
# ⚠️ URLは「人が開いて確かめられるページ」を書く。APIのエンドポイントを
#    そのまま貼ると、タップした人には中身が分からない。
SOURCES = {
    "yahoo": (
        "Yahoo Finance",
        "https://finance.yahoo.com/",
        "株価・指数・為替・商品の価格と値動き",
    ),
    "nikkei_vi": (
        "日本経済新聞社 日経平均VI",
        "https://indexes.nikkei.co.jp/nkave/index/profile?idx=nk225vi",
        "恐怖指数（日経平均ボラティリティー・インデックス）の公式日次データ",
    ),
    "nikkei_index": (
        "日本経済新聞社 日経平均プロフィル",
        "https://indexes.nikkei.co.jp/nkave/",
        "日経平均株価の公式値",
    ),
    "nikkei225jp": (
        "nikkei225jp.com",
        "https://nikkei225jp.com/nkd/touraku.php",
        "騰落レシオ・空売り比率・PER・東証の売買代金",
    ),
    "kabutan": (
        "株探",
        "https://kabutan.jp/",
        "夜間PTS・株価注意報（信用残・年初来更新）",
    ),
    "kabudragon": (
        "株ドラゴン",
        "https://www.kabudragon.com/",
        "値上がり率・ストップ高・出来高急増のランキング",
    ),
    "fred": (
        "FRED（セントルイス連邦準備銀行）",
        "https://fred.stlouisfed.org/",
        "米国の経済統計（政策金利・CPI・失業率・国債利回り）",
    ),
    "mof": (
        "財務省",
        "https://www.mof.go.jp/policy/international_policy/reference/feign/index.htm",
        "外国為替平衡操作（為替介入）の実施状況・国債金利情報",
    ),
    "boj": (
        "日本銀行",
        "https://www.boj.or.jp/",
        "日本の政策金利・金融政策決定会合",
    ),
    "fed": (
        "FRB（米連邦準備制度理事会）",
        "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
        "FOMCの日程と政策金利",
    ),
    "tdnet": (
        "TDnet（東京証券取引所 適時開示情報）",
        "https://www.release.tdnet.info/inbs/I_main_00.html",
        "決算・TOB・自社株買いなどの会社開示",
    ),
    "jpx": (
        "日本取引所グループ",
        "https://www.jpx.co.jp/",
        "売買代金・値上がり値下がり銘柄数",
    ),
    "cme": (
        "CME Group",
        "https://www.cmegroup.com/markets/equities/nikkei/nikkei-225-yen.html",
        "日経225先物（ほぼ24時間・夜間の急変）",
    ),
    "cnn_fg": (
        "CNN Business Fear & Greed Index",
        "https://edition.cnn.com/markets/fear-and-greed",
        "米国市場の投資家心理（恐怖と強欲）",
    ),
    "alternative_me": (
        "alternative.me Crypto Fear & Greed",
        "https://alternative.me/crypto/fear-and-greed-index/",
        "暗号資産の投資家心理",
    ),
    "cftc": (
        "CFTC（米商品先物取引委員会）建玉明細",
        "https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm",
        "投機筋の通貨・株価指数の持ち高（COTレポート）",
    ),
    "kabuline": (
        "株ライン",
        "https://kabuline.com/",
        "日経平均のトレンドライン・節目",
    ),
    "google_news": (
        "Google ニュース",
        "https://news.google.com/",
        "ニュース見出しの収集",
    ),
}

# 銘柄・指標 → 出典の鍵。緊急アラートは銘柄単位で鳴るので、
# 「その銘柄の数字はどこから来たか」を引けるようにしておく。
_BY_SYMBOL = {
    "NIY=F": "cme",
    "NKD=F": "cme",
    "^N225": "yahoo",
    "^NKVI": "nikkei_vi",
}


def _entry(key: str):
    e = SOURCES.get(key)
    if not e:
        # ⚠️ 黙って無視しない。鍵の打ち間違いは「出典が静かに消える」形になり、
        #    出典を付けた側は付いているつもりでいる（この案件で何度もやった形）。
        logger.warning(f"出典の鍵が台帳にありません: {key}")
    return e


def source_for_symbol(symbol: str) -> str:
    """銘柄コードから出典の鍵を返す。知らない銘柄は Yahoo 扱い。"""
    s = str(symbol or "").replace("CFD:", "")
    return _BY_SYMBOL.get(s, "yahoo")


def cite(*keys, label: str = "📚 出典") -> str:
    """Telegram用の出典行（Markdownリンク）。

    `send_message` は Markdown で送り、失敗したらプレーンで再送する作りなので、
    リンクが壊れても通知自体は必ず届く。
    """
    parts = []
    for k in dict.fromkeys(keys):          # 重複を除きつつ順番は保つ
        e = _entry(k)
        if e:
            parts.append(f"[{e[0]}]({e[1]})")
    return f"{label}: " + "・".join(parts) if parts else ""


def cite_plain(*keys, label: str = "出典") -> str:
    """リンクなしの出典行。Markdownが使えない場所・画像のキャプション用。"""
    parts = []
    for k in dict.fromkeys(keys):
        e = _entry(k)
        if e:
            parts.append(e[0])
    return f"{label}: " + "・".join(parts) if parts else ""


def cite_image(*keys, drawn: bool = True) -> str:
    """画像の中に焼き込む用の1行。

    ⚠️ **図を誰が描いたかまで書く。** 公式の数字を使っていても、
       線を引いたのはこちらである。その区別を書かないと、
       公式がこの形で発表したかのように読めてしまう。
    """
    parts = []
    for k in dict.fromkeys(keys):
        e = _entry(k)
        if e:
            host = e[1].split("/")[2] if "//" in e[1] else e[1]
            parts.append(f"{e[0]}（{host}）")
    if not parts:
        return ""
    s = "数値の出典: " + "・".join(parts)
    return s + "　／　作図: 市場AI秘書" if drawn else s


def cite_html(*keys, label: str = "📚 出典", color: str = "#8a99ae") -> str:
    """HTMLレポート用。別タブで開き、参照元を渡さない（rel）。"""
    parts = []
    for k in dict.fromkeys(keys):
        e = _entry(k)
        if e:
            parts.append(f'<a href="{e[1]}" target="_blank" '
                         f'rel="noopener noreferrer" style="color:{color}">{e[0]}</a>')
    if not parts:
        return ""
    return (f'<div style="font-size:10px;color:{color};margin-top:5px">'
            f'{label}: ' + "・".join(parts) + "</div>")


if __name__ == "__main__":
    print(cite("yahoo", "nikkei225jp"))
    print(cite_plain("nikkei_vi"))
    print(cite_image("yahoo", "cme"))
    print(f"NIY=F → {source_for_symbol('NIY=F')}")
