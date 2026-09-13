"""
bargain_scanner.py — 日経225割安株スキャナー
グレアム係数（PER×PBR）と配当利回りを組み合わせてスコアリングし、
割安な日本株TOP Nを返す。
"""

import yfinance as yf

from src.utils import setup_logger

logger = setup_logger("bargain_scanner")

WATCH_STOCKS = {
    "7203.T": "トヨタ自動車",
    "6758.T": "ソニーG",
    "8306.T": "三菱UFJ",
    "9984.T": "ソフトバンクG",
    "6861.T": "キーエンス",
    "7267.T": "本田技研",
    "8316.T": "三井住友FG",
    "9432.T": "NTT",
    "4063.T": "信越化学",
    "6501.T": "日立製作所",
    "8058.T": "三菱商事",
    "8031.T": "三井物産",
    "4502.T": "武田薬品",
    "9433.T": "KDDI",
    "7751.T": "キヤノン",
    "6367.T": "ダイキン工業",
    "4519.T": "中外製薬",
    "8001.T": "伊藤忠商事",
    "6098.T": "リクルートHD",
    "2914.T": "日本たばこ産業",
}

MEDAL = ["🥇", "🥈", "🥉"]
BADGE_COLOR = ["#FFD700", "#C0C0C0", "#CD7F32"]  # 金・銀・銅


# グレアムの基準: PER × PBR が 22.5 以下なら割安。
# （PER15 × PBR1.5 = 22.5 が上限、というベンジャミン・グレアムの目安）
# これを超えるものは「割安株」と呼べないので、一覧から外す。
_GRAHAM_MAX = 22.5


def _dividend_yield_pct(info: dict, per: float) -> float:
    """配当利回りを％で返す。

    ⚠️ 2026-09-09までここが**100倍**になっていた。
       `info["dividendYield"] * 100` と書いていたが、yfinanceは既に
       ％の数字（本田技研なら 4.35）を返すため、435% と表示されていた。
       しかもその値がスコアに ×8 で効いていたので、
       **PER41の武田薬品が「割安株4位」になる**という結果になっていた。

    版によって「割合(0.0435)」を返すこともあるため、値そのもので
    判断せず、**配当額 ÷ 株価**という定義から計算し直すのを第一手にする。
    """
    try:
        rate = info.get("dividendRate")
        price = (info.get("currentPrice") or info.get("regularMarketPrice")
                 or info.get("previousClose"))
        if rate and price and float(price) > 0:
            return float(rate) / float(price) * 100
    except (TypeError, ValueError):
        pass
    # 配当額が取れないときだけ dividendYield を使う。
    # 配当利回りが25%を超える上場企業は現実にはほぼ無いので、
    # それを境に「％で来ているのか割合で来ているのか」を見分ける。
    try:
        raw = float(info.get("dividendYield") or 0)
    except (TypeError, ValueError):
        return 0.0
    if raw <= 0:
        return 0.0
    return raw if raw <= 25 else 0.0 if raw > 2500 else raw / 100


def _fetch_stock_data(sym: str, name: str) -> dict | None:
    """1銘柄の指標を取得。取得失敗またはPER/PBR欠損時はNoneを返す。"""
    try:
        info = yf.Ticker(sym).info
        per = info.get("trailingPE") or info.get("forwardPE") or 999
        pbr = info.get("priceToBook") or 999
        div = _dividend_yield_pct(info, per)

        # PERやPBRが取得できない場合はスキャン対象外
        if per == 999 or pbr == 999:
            return None

        graham = per * pbr
        # ⚠️ 以前は配当を `div * 8` で足していた。配当が100倍だったので
        #    3,480点になり、割安さ（最大60点）を完全に押し流していた。
        #    配当は「割安さの補強」であって主役ではないので、上限を付ける。
        score = max(0, (_GRAHAM_MAX - graham) / _GRAHAM_MAX * 60)
        score += min(div, 6.0) * 5          # 配当は最大30点まで
        score += 20 if pbr < 1.0 else 0

        return {
            "symbol": sym,
            "name": name,
            "per": round(per, 1),
            "pbr": round(pbr, 2),
            "dividend_yield": round(div, 1),
            "graham_score": round(graham, 2),
            "total_score": round(score, 1),
        }
    except Exception:
        return None


def _build_html(stocks: list[dict]) -> str:
    """ダークテーマのランキングカードHTMLを生成する。"""
    cards_html = ""
    for i, s in enumerate(stocks):
        is_top3 = i < 3
        badge_html = ""
        if is_top3:
            medal = MEDAL[i]
            color = BADGE_COLOR[i]
            badge_html = (
                f'<span style="color:{color};font-size:1.4em;margin-right:6px">{medal}</span>'
            )
        bargain_tag = (
            '<span style="background:#e74c3c;color:#fff;font-size:0.72em;'
            'padding:2px 7px;border-radius:4px;margin-left:8px;vertical-align:middle">'
            "超割安</span>"
            if s["pbr"] < 1.0
            else ""
        )
        rank_num = f"#{i+1}"
        card_style = (
            "background:#1e2535;border-radius:10px;padding:14px 18px;"
            "margin-bottom:10px;border:1px solid #2d3a55;"
        )
        if is_top3:
            card_style += f"border-left:4px solid {BADGE_COLOR[i]};"
        cards_html += f"""
        <div style="{card_style}">
          <div style="display:flex;align-items:center;margin-bottom:6px">
            {badge_html}
            <span style="color:#cfd8dc;font-weight:bold;font-size:1.05em">{s['name']}</span>
            <span style="color:#78909c;font-size:0.85em;margin-left:8px">({s['symbol']})</span>
            {bargain_tag}
            <span style="margin-left:auto;color:#78909c;font-size:0.82em">{rank_num}</span>
          </div>
          <div style="display:flex;gap:18px;flex-wrap:wrap">
            <span style="color:#4fc3f7;font-size:0.9em">PER: <strong>{s['per']}</strong></span>
            <span style="color:#81c784;font-size:0.9em">PBR: <strong>{s['pbr']}</strong></span>
            <span style="color:#ffb74d;font-size:0.9em">配当: <strong>{s['dividend_yield']}%</strong></span>
            <span style="color:#ce93d8;font-size:0.9em">グレアム係数: <strong>{s['graham_score']}</strong></span>
            <span style="color:#f48fb1;font-size:0.9em">スコア: <strong>{s['total_score']}</strong></span>
          </div>
        </div>
        """

    html = f"""
<div style="background:#131929;color:#cfd8dc;font-family:'Hiragino Sans','Noto Sans JP',sans-serif;
            padding:20px;border-radius:14px;max-width:700px">
  <h2 style="color:#fff;margin-bottom:16px;font-size:1.2em;border-bottom:1px solid #2d3a55;padding-bottom:8px">
    🏆 今週の割安株ランキング
  </h2>
  {cards_html}
  <p style="color:#546e7a;font-size:0.78em;margin-top:14px">
    📌 グレアム係数(PER×PBR)が低く配当が高い銘柄を選定
  </p>
</div>
"""
    return html.strip()


def _build_telegram(stocks: list[dict]) -> str:
    """「今週の割安TOP3」Telegram用テキストを生成する。"""
    top3 = stocks[:3]
    lines = ["🏆 今週の割安株TOP3", ""]
    for i, s in enumerate(top3):
        medal = MEDAL[i]
        lines.append(f"{medal} {s['name']} ({s['symbol']})")
        lines.append(f"   PER: {s['per']} / PBR: {s['pbr']} / 配当: {s['dividend_yield']}%")
        lines.append("")
    lines.append("📌 グレアム係数(PER×PBR)が低く配当が高い銘柄を選定")
    return "\n".join(lines)


def scan_bargain_stocks(top_n: int = 5) -> dict:
    """
    主要20銘柄をスキャンし、グレアム係数と配当利回りで割安度をスコアリングして
    上位top_n銘柄を返す。

    Parameters
    ----------
    top_n : int
        返却する上位銘柄数（デフォルト5）

    Returns
    -------
    dict
        available, top_stocks, scanned_count, html, telegram_message
    """
    results = []
    for sym, name in WATCH_STOCKS.items():
        data = _fetch_stock_data(sym, name)
        if data is not None:
            results.append(data)

    if not results:
        return {
            "available": False,
            "top_stocks": [],
            "scanned_count": 0,
            "html": "<p>データ取得に失敗しました。</p>",
            "telegram_message": "⚠️ 割安株データの取得に失敗しました。",
        }

    # ⚠️ グレアム基準を満たさないものを「割安株」として出さない。
    #    以前は配当スコアだけで上位に来られたため、PER41の銘柄が
    #    4位に入っていた。名前と中身を一致させる。
    cheap = [r for r in results if r["graham_score"] <= _GRAHAM_MAX]
    if not cheap:
        logger.info(f"グレアム基準（PER×PBR≦{_GRAHAM_MAX}）を満たす銘柄は"
                    f"ありませんでした（{len(results)}銘柄を確認）")
        return {
            "available": False,
            "top_stocks": [],
            "scanned_count": len(results),
            "html": "",
            "telegram_message": "",
        }

    cheap.sort(key=lambda x: x["total_score"], reverse=True)
    top = cheap[:top_n]
    results = cheap

    return {
        "available": True,
        "top_stocks": top,
        "scanned_count": len(results),
        "html": _build_html(top),
        "telegram_message": _build_telegram(top),
    }
