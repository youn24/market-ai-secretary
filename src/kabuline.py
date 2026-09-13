"""
src/kabuline.py — 株ライン（kabuline.com）から株クラのツイートを取得

X（旧Twitter）のAPIは無料枠では検索・読み取りができず、株クラの投稿を
直接集めるには月200ドル以上の課金が必要になる。
株ラインは X 上の株関連ツイートを銘柄ごとに集計して公開しているため、
ここを経由すれば「株クラが何を言っているか」を取得できる。

  取得元: https://kabuline.com/search/tw/{証券コード}/
  1銘柄あたり直近30件程度のツイート本文が サーバー描画のHTMLに含まれる。

【感情の判定】
辞書ベースで強気・弱気の語を数える簡易判定。
AIに投げるより高速で、なぜそう判定したかを説明できる。
※Gemini など外部AIは一切使わない（APIトークンを消費しない）。

⚠️ 注意:
  ・株クラの投稿はポジショントーク（自分の持ち株を上げたい発言）が混ざる。
    「多数派＝正しい」ではないため、あくまで“話題の温度感”として扱う。
  ・サイトへの負荷を避けるため、1銘柄ごとに1秒の間隔を空ける。
"""

import re
import time
import traceback
from collections import Counter

import requests

from src.utils import setup_logger

logger = setup_logger("kabuline")

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36"}
_URL = "https://kabuline.com/search/tw/{code}/"

# 強気・弱気の語（株クラでよく使われる表現）
_BULL = ["買い", "買った", "買増", "買い増", "上昇", "上がる", "上げ", "急騰", "高値",
         "強い", "強気", "期待", "好決算", "上方修正", "ホールド", "握る",
         "仕込", "狙い", "反発", "底打ち", "利益", "含み益", "テンバガー", "有望"]
_BEAR = ["売り", "売った", "損切", "下落", "下がる", "下げ", "暴落", "急落", "安値",
         "弱い", "弱気", "警戒", "悪決算", "下方修正", "撤退", "逃げ",
         "含み損", "やられた", "退場", "危険", "厳しい", "重い"]

# 誤検出しやすい語を除外（「売り込まれ」は弱気だが「売り優勢が一巡」は違う等）
_NEG_PREFIX = ["買われ過ぎ", "買われすぎ"]


def _fetch(code: str) -> str | None:
    try:
        r = requests.get(_URL.format(code=code), headers=_HEADERS, timeout=25)
        if r.status_code != 200:
            logger.warning(f"株ライン {code}: status={r.status_code}")
            return None
        return r.text
    except Exception:
        logger.debug(traceback.format_exc())
        return None


def _parse_tweets(html: str) -> list[dict]:
    """tweet_container ブロックからツイート本文とユーザー名を抜き出す"""
    out = []
    blocks = re.findall(
        r'<div[^>]*class="[^"]*tweet_container[^"]*"[^>]*>(.*?)'
        r'(?=<div[^>]*class="[^"]*tweet_container|\Z)', html, re.S)
    for b in blocks:
        body = (re.search(r'class="[^"]*TweetPopText[^"]*"[^>]*>(.*?)</', b, re.S)
                or re.search(r'class="[^"]*tweet_body[^"]*"[^>]*>(.*?)</div>', b, re.S))
        if not body:
            continue
        txt = re.sub(r"<[^>]+>", " ", body.group(1))
        txt = re.sub(r"&[a-z]+;", " ", txt)
        txt = re.sub(r"\s+", " ", txt).strip()
        if len(txt) < 10:
            continue
        u = re.search(r"@([A-Za-z0-9_]{2,15})", b)
        out.append({"user": u.group(1) if u else "", "text": txt})
    return out


def _sentiment(tweets: list[dict]) -> dict:
    """辞書ベースで強気・弱気を数える"""
    bull = bear = 0
    for t in tweets:
        s = t["text"]
        for ng in _NEG_PREFIX:
            s = s.replace(ng, "")
        b = sum(s.count(w) for w in _BULL)
        r = sum(s.count(w) for w in _BEAR)
        t["bull"], t["bear"] = b, r
        if b > r:
            bull += 1
            t["tone"] = "bull"
        elif r > b:
            bear += 1
            t["tone"] = "bear"
        else:
            t["tone"] = "neutral"

    n = len(tweets)
    scored = bull + bear
    ratio = (bull / scored * 100) if scored else 50.0
    if   ratio >= 70: label, emoji = "強気優勢", "🟢"
    elif ratio >= 55: label, emoji = "やや強気", "🔸"
    elif ratio > 45:  label, emoji = "拮抗",     "⚪"
    elif ratio > 30:  label, emoji = "やや弱気", "🔹"
    else:             label, emoji = "弱気優勢", "🔴"
    return {"total": n, "bull": bull, "bear": bear,
            "neutral": n - bull - bear,
            "bull_ratio": round(ratio, 1), "label": label, "emoji": emoji}


def _keywords(tweets: list[dict], top: int = 6) -> list:
    """話題になっている語を抽出（カタカナ・漢字の連続を拾う）"""
    stop = {"トヨタ", "自動車", "日本株", "ツイート", "ランキング", "ポイント",
            "アカウント", "フォロー", "リツイート", "プレゼント", "キャンペーン"}
    c = Counter()
    for t in tweets:
        for w in re.findall(r"[ァ-ヶー]{3,}|[一-龥]{2,}", t["text"]):
            if w not in stop and len(w) <= 8:
                c[w] += 1
    return [w for w, n in c.most_common(top * 3) if n >= 2][:top]


def fetch_stock(code: str, name: str = "") -> dict:
    """1銘柄ぶんの株クラの声を取得する"""
    result = {"available": False, "code": code, "name": name}
    html = _fetch(code)
    if not html:
        return result
    tweets = _parse_tweets(html)
    if not tweets:
        logger.info(f"株ライン {code}: ツイート抽出0件")
        return result
    result.update({
        "available": True,
        "tweets": tweets,
        "sentiment": _sentiment(tweets),
        "keywords": _keywords(tweets),
        "url": _URL.format(code=code),
    })
    return result


def run(codes: list | None = None, **_kwargs) -> dict:
    """
    複数銘柄の株クラ感情をまとめて取得。
    codes: [(コード, 表示名), ...]
    """
    codes = codes or [("7203", "トヨタ"), ("6758", "ソニーG"),
                      ("8306", "三菱UFJ"), ("6857", "アドテスト")]
    out = {"available": False, "stocks": []}
    try:
        for code, name in codes:
            r = fetch_stock(code, name)
            if r.get("available"):
                out["stocks"].append(r)
            time.sleep(1.0)          # サイトへの負荷配慮
        if not out["stocks"]:
            return out
        out["available"] = True
        out["telegram_message"] = build_message(out["stocks"])
        logger.info(f"✅ 株ライン: {len(out['stocks'])}銘柄の株クラ感情を取得")
        return out
    except Exception:
        logger.error("株ライン取得エラー")
        logger.debug(traceback.format_exc())
        return out


def build_message(stocks: list) -> str:
    """通知本文。1行目に最も偏った銘柄を出す。"""
    top = max(stocks, key=lambda s: abs(s["sentiment"]["bull_ratio"] - 50))
    ts  = top["sentiment"]
    if abs(ts["bull_ratio"] - 50) >= 20:
        title = (f"🗣 *株クラの声* — {top['name']}が{ts['label']}"
                 f"（強気{ts['bull_ratio']:.0f}%）")
    else:
        title = "🗣 *株クラの声*（X投稿の集計）"

    lines = [title, "━━━━━━━━━━━━━━"]
    for s in stocks:
        st = s["sentiment"]
        lines += [
            "",
            f"{st['emoji']} *{s['name']}（{s['code']}）* {st['label']}",
            f"　強気 {st['bull']}件 / 弱気 {st['bear']}件 / 中立 {st['neutral']}件"
            f"（強気率 {st['bull_ratio']:.0f}%）",
        ]
        if s.get("keywords"):
            lines.append(f"　🏷 話題: {' / '.join(s['keywords'][:5])}")

    lines += ["",
              "※X上の株関連ツイートを株ライン(kabuline.com)経由で集計したものです。",
              "※個人の投稿にはポジショントークが含まれます。"
              "「多数派＝正しい」ではなく、話題の温度感としてご覧ください。"]
    return "\n".join(lines)


def run_report(codes: list | None = None) -> bool:
    try:
        res = run(codes)
        if not res.get("available"):
            logger.info("株クラの声: 送信スキップ")
            return False
        from src.notify_telegram import send_message
        ok = send_message(res["telegram_message"])
        if ok:
            logger.info("✅ 株クラの声を送信")
        return bool(ok)
    except Exception:
        logger.error("株クラの声 送信エラー")
        logger.debug(traceback.format_exc())
        return False


if __name__ == "__main__":
    run_report()
