# -*- coding: utf-8 -*-
"""HTMLメールで記事を届ける（Step MAIL）

オーナー要望（2026-11-19）:
  「文章の間に画像を挟みたい」「クリックせずとも見たい」「拡大するとぼやける」

**なぜメールなのか**

Telegramの1通の中に文章と画像を交互に置くことは**仕様上できない**
（メッセージ本文が使えるHTMLに `<img>` が無い）。
写真1枚＋キャプションの形しか無く、しかも写真は圧縮されて滲む。

メールなら全部解決する:

| | |
|---|---|
| 文章の間に画像 | 何枚でも置ける。これはメールが元からHTMLだから |
| タップ | **不要**。メールを開いた時点で記事が目の前にある |
| 拡大したとき | **滲まない**。文字は端末の字、画像は原寸のまま添付 |
| 長さ | 制限なし（Telegramは本文4096字・キャプション1024字） |

⚠️ **メールのHTMLは、ブラウザのHTMLとは別物として書く。**
  1. **SVGは表示されない。** この案件の図はすべてSVGなので、
     メール版は**PNGで描き直す**（matplotlib）。ここを間違えると
     グラフの場所が全部空白になる。
  2. **外部スタイルシートもclassも効かない。** すべて `style=` で直接書く。
  3. **画像は添付して埋め込む（CID）。** 外部URLのままだと、
     メールアプリが「画像を読み込みますか？」と聞いてきて、
     許可するまで空白になる。添付なら最初から見える。

⚠️ **宛先はコードに書かない。** 環境変数から読む。
   個人のメールアドレスをリポジトリ（公開）に置かないため。

設定（.env か GitHub Secrets）:
    SMTP_HOST   例: smtp.gmail.com
    SMTP_PORT   例: 587
    SMTP_USER   送信に使うアカウント
    SMTP_PASS   アプリパスワード（通常のログイン用パスワードは使えない）
    MAIL_TO     受け取るアドレス（複数ならカンマ区切り）
    MAIL_FROM   省略時は SMTP_USER
"""
import os
import smtplib
import ssl
import urllib.request
from email.message import EmailMessage
from email.utils import make_msgid

from src.utils import setup_logger, get_jst_now, get_dirs

logger = setup_logger("notify_email")

_BG, _CARD, _LINE = "#0b0e14", "#121722", "rgba(255,255,255,0.10)"
_TEXT, _DIM, _ACC = "#eaf0fa", "#8a99ae", "#6aa9ff"
_UP, _DOWN, _WARN = "#2fd98a", "#ff4d63", "#ffc24d"
_FONT = ("-apple-system,'Hiragino Kaku Gothic ProN','Noto Sans JP',"
         "'Yu Gothic UI',Meiryo,sans-serif")


def _is_configured() -> bool:
    need = ("SMTP_HOST", "SMTP_USER", "SMTP_PASS", "MAIL_TO")
    missing = [k for k in need if not (os.getenv(k) or "").strip()]
    if missing:
        logger.info(f"メール未設定のためスキップします（未設定: {', '.join(missing)}）")
        return False
    return True


# ══════════════════════════════════════════════════════════
class _Images:
    """本文に埋め込む画像をためておく入れ物。

    HTMLからは `cid:xxx` で参照し、実体はメールに添付する。
    こうすると「画像を読み込みますか」を聞かれず、最初から見える。
    """

    def __init__(self):
        self.items = []          # [(cid, bytes, subtype)]

    def add(self, data: bytes, subtype: str = "png") -> str:
        if not data:
            return ""
        cid = make_msgid(domain="market-ai.local")
        self.items.append((cid, data, subtype))
        return f"cid:{cid[1:-1]}"      # <...> を外したものがHTML側の書き方

    def attach_to(self, msg: EmailMessage) -> None:
        for cid, data, subtype in self.items:
            msg.get_payload()[1].add_related(
                data, maintype="image", subtype=subtype, cid=cid)


def _fetch(url: str, timeout: int = 20) -> bytes:
    """画像の実体を取ってくる。

    ⚠️ 証明書は `media_credits._ctx()` と同じものを使う。
       手元のWindowsは証明書ストアが期限切れで、素の urllib だと
       `CERTIFICATE_VERIFY_FAILED` になる。**先方の問題ではない**ので、
       ここで「取れない」と判断して写真を諦めてはいけない。
    """
    try:
        from src.media_credits import _ctx
        ctx = _ctx()
    except Exception:
        ctx = None
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "market-ai-secretary/1.0"})
        return urllib.request.urlopen(req, timeout=timeout, context=ctx).read()
    except Exception as e:
        logger.warning(f"画像を取れませんでした: {e}")
        return b""


def _png(path: str) -> bytes:
    try:
        with open(path, "rb") as f:
            return f.read()
    except Exception:
        return b""


# ══════════════════════════════════════════════════════════
def _h2(title: str) -> str:
    return (f'<h2 style="font-size:19px;font-weight:800;color:{_TEXT};'
            f'margin:30px 0 12px;padding-top:22px;'
            f'border-top:1px solid rgba(255,255,255,0.10)">{title}</h2>')


def _para(text: str) -> str:
    text = str(text or "").replace("**", "\x00")
    out, bold = "", False
    for part in text.split("\x00"):
        out += (f'<b style="color:{_TEXT}">{part}</b>' if bold else part)
        bold = not bold
    return (f'<p style="font-size:16px;line-height:1.95;color:{_TEXT};'
            f'margin:0 0 14px">{out}</p>')


def _figure(src: str, caption: str = "") -> str:
    """文章の間に挟む画像。これがこのモジュールの存在理由。"""
    if not src:
        return ""
    cap = (f'<div style="font-size:12px;color:{_DIM};margin-top:6px;'
           f'line-height:1.6">{caption}</div>') if caption else ""
    return (f'<div style="margin:18px 0 22px">'
            f'<img src="{src}" alt="" width="560" '
            f'style="width:100%;max-width:560px;display:block;'
            f'border-radius:12px;border:1px solid rgba(255,255,255,0.10)">'
            f'{cap}</div>')


def _rows(pairs) -> str:
    """数値の並び。メールでは table で書くのが最も崩れにくい。"""
    tr = ""
    for label, value, color in pairs:
        tr += (f'<tr>'
               f'<td style="padding:9px 0;font-size:15px;color:{_TEXT};'
               f'border-bottom:1px solid rgba(255,255,255,0.08)">{label}</td>'
               f'<td align="right" style="padding:9px 0;font-size:16px;'
               f'font-weight:700;color:{color};'
               f'border-bottom:1px solid rgba(255,255,255,0.08)">{value}</td>'
               f'</tr>')
    return (f'<table role="presentation" width="100%" cellpadding="0" '
            f'cellspacing="0" style="margin:4px 0 8px">{tr}</table>')


# ══════════════════════════════════════════════════════════
def build_html(prices=None, risk=None, internals=None, ai_summary=None,
               market_driver=None, fear=None, scenario=None, policy=None,
               mode="morning", images: "_Images" = None) -> tuple:
    """メール本文のHTMLを作る。(件名, HTML) を返す。"""
    from src.feed_card import (_q, _n, _headline, _breadth, _importance,
                               _chain as _chain_items)
    prices, internals = prices or {}, internals or {}
    images = images if images is not None else _Images()

    nk = _q(prices, "^N225")
    now = get_jst_now()
    score = (risk or {}).get("score")
    nvi_pct = (fear or {}).get("nvi_pctile")
    nvi = internals.get("nvi")
    r = _breadth(internals)
    imp = _importance(nk["c"] if nk else None, score, nvi_pct, r)
    when = {"morning": "寄り付き前", "noon": "前場終了後",
            "evening": "大引け後", "test": "検証"}.get(mode, "")
    title = str(_headline(nk, internals) or "").replace("**", "")

    used = set()

    def _photo_src(*keys):
        """Commonsの写真を1枚、添付して cid: を返す。同じ写真は二度使わない。"""
        try:
            from src.media_credits import photo, photo_credit
            for k in keys:
                if k in used:
                    continue
                pm = photo(k)
                if not pm:
                    continue
                data = _fetch(pm["url"])
                if not data:
                    continue
                used.add(k)
                return images.add(data, "jpeg"), photo_credit(pm) + "　※当日の写真ではありません"
        except Exception:
            logger.error("写真を用意できませんでした", exc_info=True)
        return "", ""

    body = []

    # ── 見出し ──
    body.append(
        f'<div style="font-size:13px;color:{_DIM}">'
        f'{now.year}年{now.month}月{now.day}日'
        f'（{"月火水木金土日"[now.weekday()]}）'
        f'{"　" + when if when else ""} ｜ 日本株・米国株'
        f'　<span style="color:{_WARN}">重要度 {imp}/5</span></div>'
        f'<h1 style="font-size:24px;line-height:1.5;color:{_TEXT};'
        f'margin:12px 0 0;font-weight:800">{title}</h1>')

    # ── 記事の顔になる写真 ──
    src, cap = _photo_src("tse2", "tse")
    body.append(_figure(src, cap))

    # ── 📌 3秒で結論 ──
    concl = ""
    for cand in ((ai_summary or {}).get("neutral_view"),
                 (market_driver or {}).get("summary")):
        if isinstance(cand, str) and cand.strip():
            concl = cand.strip()[:300]
            break
    if len(concl) < 24 and nk:
        bits = [f"日経平均は{nk['c']:+.2f}%"]
        if isinstance(r, (int, float)):
            side = "下げ" if r >= .5 else "上げ"
            bits.append(f"{(r if r >= .5 else 1 - r) * 100:.0f}%の銘柄が{side}ました")
        concl = "。".join(bits) + "。"
    if concl:
        body.append(_h2("📌 3秒で結論") + _para(concl))

    # ── 📊 本日の数字 ──
    pairs = []
    for sym, nm, unit in (("^N225", "日経平均", "円"), ("^TOPX", "TOPIX", ""),
                          ("USDJPY=X", "ドル円", "円")):
        d = _q(prices, sym)
        if d:
            col = _UP if d["c"] >= 0 else _DOWN
            pairs.append((nm, f'{_n(d["v"], 2)}{unit}（{d["c"]:+.2f}%）', col))
    adv, dec = internals.get("advancing"), internals.get("declining")
    turn = internals.get("turnover_total")
    if isinstance(turn, (int, float)):
        pairs.append(("東証の売買代金", f"{turn / 1e6:.2f}兆円", _ACC))
    if isinstance(adv, (int, float)) and isinstance(dec, (int, float)):
        pairs.append(("値上がり ／ 値下がり",
                      f"{adv:,.0f} ／ {dec:,.0f}", _TEXT))
    if isinstance(nvi, (int, float)):
        pos = (f"（上から{100 - nvi_pct:.0f}%）"
               if isinstance(nvi_pct, (int, float)) else "")
        pairs.append(("恐怖指数 日経VI", f"{nvi:.1f}{pos}", _WARN))
    if pairs:
        body.append(_h2(f"📊 本日の数字") + _rows(pairs))

    # ── 🕯 ローソク足（PNG。メールではSVGが映らない）──
    try:
        from src.alert_chart import candle_chart
        out = str(get_dirs()["charts"] /
                  f"mail_candle_{now.strftime('%Y%m%d')}.png")
        p = candle_chart("^N225", "日経平均", out_path=out)
        if p:
            body.append(
                _h2("🕯 日経平均の日足")
                + _figure(images.add(_png(p), "png"),
                          "緑はその日上げた日、赤は下げた日。"
                          "細い線はその日の高値と安値。"
                          "オレンジ＝5日平均、青＝25日平均。"
                          "数値の出典: Yahoo Finance ／ 作図: 市場AI秘書"))
    except Exception:
        logger.error("ローソク足を作れませんでした", exc_info=True)

    # ── 📋 なぜ動いたのか（文章→画像→文章の本番）──
    try:
        ch = _chain_items(prices, internals, None, {})
        if ch:
            body.append(_h2("📋 なぜ動いたのか？"))
            for i, c in enumerate(ch[:3]):
                body.append(
                    f'<h3 style="font-size:17px;color:{_TEXT};margin:18px 0 8px">'
                    f'{c["no"]}. {c["title"]}</h3>'
                    + _para(f'{c["val"]}　{c["note"]}')
                    + f'<div style="font-size:12px;color:{_DIM};'
                      f'margin:-6px 0 0">出典: {c["src"]}</div>')
                # 中身に合う写真だけを挟む（順番で機械的に割らない）
                t = str(c.get("title") or "")
                keys = (("nyse2", "nyse") if any(k in t for k in ("米国", "NY"))
                        else ("boj",) if any(k in t for k in ("日銀", "金利"))
                        else ("mof",) if "為替" in t else ())
                if keys:
                    s2, c2 = _photo_src(*keys)
                    body.append(_figure(s2, c2))
    except Exception:
        logger.error("連鎖を作れませんでした", exc_info=True)

    # ── 💱 為替・金利 ──
    fx = []
    for sym, nm, unit in (("USDJPY=X", "ドル円", "円"),
                          ("^TNX", "米10年金利", "%")):
        d = _q(prices, sym)
        if d:
            fx.append((nm, f'{_n(d["v"], 2)}{unit}（{d["c"]:+.2f}%）',
                       _UP if d["c"] >= 0 else _DOWN))
    if fx:
        body.append(_h2("💱 為替・金利") + _rows(fx))

    # ── 🏦 政策金利 ──
    pol = []
    for key, nm in (("fed", "🇺🇸 FRB（米国）"), ("boj", "🇯🇵 日銀（日本）")):
        e = (policy or {}).get(key) or {}
        if isinstance(e.get("rate"), (int, float)):
            pol.append((nm, f'{e["rate"]:.2f}%', _TEXT))
    if pol:
        body.append(_h2("🏦 政策金利") + _rows(pol))
        s3, c3 = _photo_src("boj", "mof", "fed")
        body.append(_figure(s3, c3))

    # ── 🎯 3つの筋書き ──
    try:
        from src.feed_card import _scenarios
        rows = _scenarios(scenario)
        if rows:
            body.append(_h2("🎯 3つの筋書き"))
            for _k, nm, pr, txt in rows:
                col = {"強気": _UP, "中立": _WARN, "弱気": _DOWN}.get(nm, _DIM)
                pr_s = f"（{pr}%）" if pr is not None else ""
                body.append(
                    f'<p style="font-size:16px;line-height:1.9;margin:0 0 12px;'
                    f'color:{_TEXT}"><b style="color:{col}">{nm}{pr_s}</b>'
                    f'　{txt[:160]}</p>')
    except Exception:
        logger.error("シナリオを作れませんでした", exc_info=True)

    # ── 🐘 今日の構え ──
    act = ("恐怖指数が高い日です。**同じ株数でも損得の振れ幅が大きくなります。**"
           "株数を減らす・損切りを広めに置く・待つ、のどれかを選ぶ場面です。"
           if isinstance(nvi_pct, (int, float)) and nvi_pct >= 85 else
           "大きく荒れてはいません。いつもどおりで構いませんが、"
           "**決めた損切りの線は動かさない**ことだけ守ってください。")
    body.append(
        _h2("🐘 今日の構え")
        + f'<div style="border:1px solid {_WARN}55;background:rgba(255,194,77,.08);'
          f'border-radius:12px;padding:14px 16px">{_para(act)}</div>')

    # ── 出典 ──
    url = ((os.getenv("GITHUB_PAGES_URL") or "").strip()
           or "https://youn24.github.io/market-ai-secretary").rstrip("/")
    body.append(
        f'<div style="margin-top:30px;padding-top:20px;'
        f'border-top:1px solid rgba(255,255,255,0.10);font-size:12.5px;'
        f'color:{_DIM};line-height:1.9">'
        f'📚 出典: 日本経済新聞社・Yahoo Finance・nikkei225jp.com・株探<br>'
        f'写真は Wikimedia Commons（作者とライセンスは各写真に記載）。'
        f'<b style="color:{_WARN}">当日の相場の写真ではありません。</b><br>'
        f'グラフはすべて公式の数値から自前で作図しています。<br>'
        f'<a href="{url}/daily_report.html" style="color:{_ACC}">'
        f'動画つきの記事を開く →</a></div>')

    html = (f'<!doctype html><html lang="ja"><head>'
            f'<meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'</head>'
            f'<body style="margin:0;padding:0;background:{_BG}">'
            f'<div style="max-width:600px;margin:0 auto;padding:22px 18px 34px;'
            f'background:{_BG};font-family:{_FONT};'
            f'-webkit-text-size-adjust:100%">'
            + "".join(body) + '</div></body></html>')
    return title, html


# ══════════════════════════════════════════════════════════
def run(prices=None, risk=None, internals=None, ai_summary=None,
        market_driver=None, fear=None, scenario=None, policy=None,
        mode="morning", **_extra) -> bool:
    """記事をHTMLメールで送る。設定が無ければ何もしないで False。"""
    if not _is_configured():
        return False
    try:
        images = _Images()
        title, html = build_html(
            prices=prices, risk=risk, internals=internals,
            ai_summary=ai_summary, market_driver=market_driver, fear=fear,
            scenario=scenario, policy=policy, mode=mode, images=images)

        msg = EmailMessage()
        msg["Subject"] = title or "市場AI秘書"
        msg["From"] = (os.getenv("MAIL_FROM") or os.getenv("SMTP_USER")).strip()
        to = [a.strip() for a in (os.getenv("MAIL_TO") or "").split(",") if a.strip()]
        msg["To"] = ", ".join(to)
        # 文字だけで読む人・読み上げのために、必ず代替の文字版も入れる
        msg.set_content(
            f"{title}\n\n"
            "この案内はHTMLメールです。画像つきの記事が表示されない場合は、"
            "公開ページをご覧ください。\n"
            + ((os.getenv("GITHUB_PAGES_URL") or "").strip()
               or "https://youn24.github.io/market-ai-secretary")
            + "/daily_report.html")
        msg.add_alternative(html, subtype="html")
        images.attach_to(msg)

        host = (os.getenv("SMTP_HOST") or "").strip()
        port = int((os.getenv("SMTP_PORT") or "587").strip())
        user = (os.getenv("SMTP_USER") or "").strip()
        pw = (os.getenv("SMTP_PASS") or "").strip()

        ctx = ssl.create_default_context()
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=ctx, timeout=40) as sv:
                sv.login(user, pw)
                sv.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=40) as sv:
                sv.starttls(context=ctx)
                sv.login(user, pw)
                sv.send_message(msg)

        logger.info(f"✅ メール送信（宛先{len(to)}件・画像{len(images.items)}枚）")
        return True
    except Exception:
        # ⚠️ 失敗を握りつぶさない。型とメッセージごと残す
        #    （この案件では debug に落として2週間気づかなかった事故がある）。
        logger.error("メールを送れませんでした", exc_info=True)
        return False


if __name__ == "__main__":
    print("設定:", "あり" if _is_configured() else "なし")
