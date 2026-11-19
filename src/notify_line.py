# -*- coding: utf-8 -*-
"""LINE通知（Step L5i）— LINE公式アカウントの Messaging API で送る

⚠️ **2025-03-31 に LINE Notify は終了した。**
   旧実装は `https://notify-api.line.me/api/notify` を叩いていた。
   今このURLを叩いても届かない。復活させないこと。

   ただし「毎朝失敗していた」というのは**誤り**だった。
   `LINE_NOTIFY_TOKEN` はどこにも設定されていなかったため
   （`.env` にも GitHub Secrets にもワークフローにも無い）、
   未設定として黙って skip されていただけで、通信は一度も発生していない。
   つまり**害はなかったが、何の役にも立っていなかった**。

セットアップ（オーナー作業）:
  1. https://developers.line.biz/console/ で Messaging API チャネルを作る
     （LINE公式アカウントが同時に作られる）
  2. 「Messaging API設定」→ チャネルアクセストークン（長期）を発行
     → GitHub Secrets / .env の `LINE_CHANNEL_TOKEN`
  3. そのLINE公式アカウントを自分のLINEで友だち追加する
  4. 自分のユーザーID（`U` で始まる33文字）を
     → `LINE_TO`
     ※ Webhookを立てずに調べるなら、チャネル基本設定の「あなたのユーザーID」
  5. 両方そろった日から届きはじめる。片方でも欠けていれば何もしない

⚠️ 無料枠は **月200通**。1日1通（平日のみ＝月22通）に収めてあるので、
   ここを増やすときは枠を計算してからにすること。
   Messaging API は「1回のpushリクエスト＝1通」と数える
   （中に複数のメッセージを入れても1通）。
"""
import os
import re
import logging
import requests
from src.utils import setup_logger, get_today_str

logger = setup_logger("notify_line")

PUSH_URL = "https://api.line.me/v2/bot/message/push"

# LINEのテキスト上限は5000字。余裕を見て切る。
_TEXT_LIMIT = 4800


def _token() -> str:
    return os.getenv("LINE_CHANNEL_TOKEN", "").strip()


def _to() -> str:
    return os.getenv("LINE_TO", "").strip()


def _is_configured() -> bool:
    """送れる状態か。鍵の中身はログにも出さない。"""
    return bool(_token()) and bool(_to())


def _plain(text: str) -> str:
    """TelegramのMarkdownをLINE用の素の文字に直す。

    ⚠️ LINEのテキストメッセージに装飾は無い。`*強調*` をそのまま送ると
       星印が画面に出てしまう。出典の `[名前](URL)` も同様に、
       そのままだと記号だらけで読めなくなるので「名前 URL」に開く。
    """
    s = str(text or "")
    # [表示名](URL) → 表示名 URL
    s = re.sub(r"\[([^\]]+)\]\((https?://[^\s)]+)\)", r"\1 \2", s)
    # *強調* / _強調_ の記号を落とす（装飾が無いので意味がない）
    s = s.replace("*", "").replace("_", "")
    return s


def push(messages: list) -> bool:
    """1回のpushで送る（＝無料枠の消費は1通）。"""
    if not _is_configured():
        logger.info("LINE 未設定 — スキップ（LINE_CHANNEL_TOKEN / LINE_TO）")
        return False
    if not messages:
        return False
    try:
        r = requests.post(
            PUSH_URL,
            headers={"Authorization": f"Bearer {_token()}",
                     "Content-Type": "application/json"},
            json={"to": _to(), "messages": messages[:5]},
            timeout=20,
        )
        if r.status_code != 200:
            # ⚠️ 理由を必ず残す。無言で失敗すると「静かに壊れる」形になる。
            logger.error(f"LINE 送信失敗: HTTP {r.status_code} / {r.text[:200]}")
            return False
        logger.info(f"LINE 送信 ✅（{len(messages[:5])}件）")
        return True
    except Exception as e:
        logger.error(f"LINE 送信失敗: {type(e).__name__}: {e}")
        return False


def send_message(text: str) -> bool:
    """テキスト1通。"""
    t = _plain(text)[:_TEXT_LIMIT]
    if not t.strip():
        return False
    return push([{"type": "text", "text": t}])


def send_image(image_url: str, preview_url: str = "") -> bool:
    """画像1通。

    ⚠️ Messaging API は**公開HTTPSのURLしか受け取らない**。
       手元のPNGファイルを添付する口が無いので、GitHub Pages 等に
       置いてあるものだけを送れる。ローカルパスを渡しても送れない。
    """
    u = str(image_url or "").strip()
    if not u.startswith("https://"):
        logger.info("LINE 画像: 公開URLでないため送らない")
        return False
    return push([{"type": "image",
                  "originalContentUrl": u,
                  "previewImageUrl": (preview_url or u)}])


def _fallback_text(risk, fear_greed, prices, today) -> str:
    """記事が作れなかった日の短い代替。"""
    score = (risk or {}).get("score", 0)
    fg = (fear_greed or {}).get("score", 50) or 50
    fg_label = (fear_greed or {}).get("rating_ja", "---")

    if score >= 2:      mood = "🚀 強気"
    elif score >= 0.5:  mood = "😊 やや強気"
    elif score >= -0.5: mood = "😐 中立"
    elif score >= -2:   mood = "😟 やや弱気"
    else:               mood = "😱 弱気"

    def fmt(sym, unit=""):
        d = (prices or {}).get(sym, {}) or {}
        v = d.get("latest")
        chg = d.get("change_pct")
        if not isinstance(v, (int, float)):
            return "---"
        arrow = "▲" if (chg or 0) >= 0 else "▼"
        return f"{v:,.1f}{unit} {arrow}{abs(chg or 0):.1f}%"

    return (
        f"📊 市場AI秘書 [{today}]\n"
        f"{'─' * 18}\n"
        f"{mood}／Fear&Greed {fg}（{fg_label}）\n\n"
        f"🇯🇵 日経 {fmt('^N225', '円')}\n"
        f"🇺🇸 S&P {fmt('^GSPC')}\n"
        f"💵 ドル円 {fmt('USDJPY=X', '円')}\n"
        f"😱 VIX {fmt('^VIX')}"
    )


def run(risk=None, fear_greed=None, prices=None, report_paths=None,
        ai_summary=None, chart_paths=None,
        multi_consensus=None, autonomous_plan=None,
        internals=None, market_driver=None, fear=None,
        scenario=None, policy=None, mode="morning", **_extra) -> bool:
    """朝の記事をLINEへ**1通だけ**送る。

    ⚠️ 中身は Telegram と同じ `feed_card.build_text()` を使う。
       別々に書くと、同じ日に違うことを言う通知が2つできる
       （この案件で繰り返している失敗の形）。
    """
    if not _is_configured():
        logger.info("LINE 未設定 — スキップ（LINE_CHANNEL_TOKEN / LINE_TO）")
        return False

    today = get_today_str()
    text = ""
    try:
        from src.feed_card import build_text
        text = build_text(prices=prices, risk=risk, internals=internals,
                          ai_summary=ai_summary, market_driver=market_driver,
                          fear=fear, scenario=scenario, policy=policy,
                          mode=mode, limit=4300) or ""
    except Exception as e:
        logger.error(f"LINE 本文の組み立て失敗: {type(e).__name__}: {e}")

    if not text.strip():
        text = _fallback_text(risk, fear_greed, prices, today)

    # ⚠️ LINEにはインラインボタンが無い。Telegram向けの文末
    #    「…は下のボタンから」をそのまま送ると、存在しないボタンを探させる。
    text = "\n".join(l for l in text.splitlines()
                     if "下のボタンから" not in l).rstrip()

    url = str((report_paths or {}).get("url") or "").strip()
    if url:
        text += f"\n\n📖 グラフ・写真・動画つきの記事\n{url}"

    return send_message(text)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("設定:", "あり" if _is_configured() else "なし（LINE_CHANNEL_TOKEN / LINE_TO）")
