"""
YouTube動画 本格分析モジュール（チャンネル登録制）
- config/youtube_channels.yaml に登録したチャンネルの最新動画を取得
- Gemini が動画の実際の中身（音声・字幕）を解析し、日経平均・銘柄の要点を要約
- 動画解析に失敗した場合はタイトルベース要約にフォールバック（必ず壊れない）

出力キー（既存HTMLとの互換を維持）:
  available, videos[{title,url,channel,analysis}], points, impact, full_text
"""
import os
import re
import traceback
from pathlib import Path
from datetime import datetime, timezone, timedelta

import requests
import feedparser
import yaml

from src.utils import setup_logger

logger = setup_logger("youtube_summary")

BASE_DIR = Path(__file__).parent.parent
_CONFIG  = BASE_DIR / "config" / "youtube_channels.yaml"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


# ─── 設定読み込み ──────────────────────────────────────────────────────────

def _load_config() -> dict:
    try:
        with open(_CONFIG, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning(f"YouTube設定読込失敗: {e}")
        return {}


# 明らかに相場・市場と無関係な動画を除外するためのキーワード
_SKIP_KEYWORDS = [
    "パスキー", "設定", "レクチャー", "使い方", "操作方法", "ログイン",
    "口座開設", "キャンペーン", "プレゼント", "抽選", "登録方法",
    "アプリの", "ツールの", "メンテナンス", "障害", "お知らせ", "求人",
    "#shorts",
]


def _is_market_relevant(title: str) -> bool:
    """タイトルから、相場と無関係そうな動画（操作案内・キャンペーン等）を除外。"""
    t = (title or "").lower()
    return not any(kw.lower() in t for kw in _SKIP_KEYWORDS)


def _resolve_handle(handle: str) -> str | None:
    """@handle からチャンネルID(UC...)を解決する。"""
    h = handle.lstrip("@")
    try:
        r = requests.get(f"https://www.youtube.com/@{h}", headers=_HEADERS, timeout=15)
        m = re.search(r'"channelId":"(UC[\w-]+)"', r.text)
        if m:
            return m.group(1)
    except Exception as e:
        logger.warning(f"handle解決失敗 [{handle}]: {e}")
    return None


# ─── 最新動画の取得（公式RSS）─────────────────────────────────────────────

def fetch_latest_videos() -> list:
    """登録チャンネルの最新動画を取得。"""
    cfg      = _load_config()
    settings = cfg.get("settings", {})
    channels = cfg.get("channels", []) or []
    within   = int(settings.get("within_hours", 30))
    max_v    = int(settings.get("max_videos", 3))

    cutoff = datetime.now(timezone.utc) - timedelta(hours=within)
    found  = []

    for ch in channels:
        cid  = ch.get("channel_id")
        name = ch.get("name", "")
        if not cid and ch.get("handle"):
            cid = _resolve_handle(ch["handle"])
        if not cid:
            continue
        try:
            rss = f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
            feed = feedparser.parse(rss)
            for entry in feed.entries[:5]:
                # 公開日時
                pub = entry.get("published_parsed")
                pub_dt = datetime(*pub[:6], tzinfo=timezone.utc) if pub else None
                if pub_dt and pub_dt < cutoff:
                    break  # これ以降は古い動画なので打ち切り
                title = entry.get("title", "")
                if not _is_market_relevant(title):
                    continue  # 操作案内・キャンペーン等はスキップして次の候補へ
                found.append({
                    "title":   title,
                    "url":     entry.get("link", ""),
                    "channel": name,
                    "published": pub_dt.isoformat() if pub_dt else "",
                })
                break  # 各チャンネル、相場関連の最新1本だけ
        except Exception as e:
            logger.warning(f"RSS取得失敗 [{name}]: {e}")

    # 新しい順に並べ、上限本数に絞る
    found.sort(key=lambda v: v.get("published", ""), reverse=True)
    found = found[:max_v]
    logger.info(f"YouTube最新動画: {len(found)}件（直近{within}時間以内）")
    return found


# ─── Gemini 動画解析（本体）────────────────────────────────────────────────

_VIDEO_PROMPT = """あなたは日本の金融メディアのアナリストです。
この動画の【実際の内容】を視聴・解析し、投資初心者にもわかるように要約してください。

以下の形式で、各項目100文字以内・やさしい日本語で：

【動画の要点】
動画で語られている最も重要なテーマ・主張は何か。

【日経平均・相場への言及】
日経平均や株式相場について、どんな見方・水準・方向感が示されたか。

【注目された銘柄・セクター】
具体的に挙げられた銘柄やセクターがあれば列挙（なければ「言及なし」）。

【視聴者へのヒント】
個人投資家が気をつけるべき点（推測として）。

※ 投資助言ではなく、動画内容の客観的な要約として述べてください。"""


def _analyze_video_new_sdk(url: str, model_name: str) -> str | None:
    """新SDK google-genai でYouTube URLを直接解析。"""
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY", "").strip())
        resp = client.models.generate_content(
            model=model_name,
            contents=types.Content(parts=[
                types.Part(file_data=types.FileData(file_uri=url)),
                types.Part(text=_VIDEO_PROMPT),
            ]),
        )
        return (resp.text or "").strip() or None
    except Exception as e:
        logger.warning(f"新SDK動画解析失敗 [{url}]: {e}")
        return None


def _summarize_titles_fallback(videos: list) -> dict:
    """動画解析に失敗したときのフォールバック（タイトルから推測）。"""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or not videos:
        return {"available": False}
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
        vlist = "\n".join(f"・{v['title']}（{v['channel']}）" for v in videos)
        prompt = (
            "以下の市場解説動画のタイトルから、本日の注目テーマと相場への示唆を"
            "推測してください（各100文字以内）。\n\n"
            f"【動画タイトル】\n{vlist}\n\n"
            "【動画のポイント】\n（最重要テーマ）\n\n【市場への示唆】\n（相場への影響・推測）"
        )
        text = model.generate_content(prompt).text
        points, impact = _split_points_impact(text)
        logger.info("✅ タイトルベース要約（フォールバック）完了")
        return {"available": True, "videos": videos, "points": points,
                "impact": impact, "full_text": text, "mode": "title"}
    except Exception as e:
        logger.error(f"フォールバック要約失敗: {e}")
        return {"available": False}


def _split_points_impact(text: str) -> tuple:
    points, impact, cur, buf = "", "", "all", []
    secs = {}
    for line in text.split("\n"):
        if "ポイント" in line or "要点" in line:
            if buf: secs[cur] = "\n".join(buf).strip()
            cur, buf = "points", []
        elif "示唆" in line or "影響" in line:
            if buf: secs[cur] = "\n".join(buf).strip()
            cur, buf = "impact", []
        elif line.strip():
            buf.append(line.strip())
    if buf: secs[cur] = "\n".join(buf).strip()
    return secs.get("points", ""), secs.get("impact", "")


def _aggregate(analyses: list) -> tuple:
    """各動画解析から「動画のポイント」「市場への示唆」をまとめる。"""
    points, impacts = [], []
    for a in analyses:
        txt = a.get("analysis", "")
        # 「日経平均・相場への言及」を示唆として拾う
        m_pt = re.search(r"【動画の要点】\s*(.+?)(?:【|$)", txt, re.S)
        m_im = re.search(r"【日経平均・相場への言及】\s*(.+?)(?:【|$)", txt, re.S)
        if m_pt: points.append(f"🎬 {a['channel']}：{m_pt.group(1).strip()[:120]}")
        if m_im: impacts.append(f"📈 {a['channel']}：{m_im.group(1).strip()[:120]}")
    return "\n\n".join(points), "\n\n".join(impacts)


# ─── エントリーポイント ────────────────────────────────────────────────────

def run(news: list = None) -> dict:
    """YouTube本格分析モジュール実行。"""
    logger.info("=== YouTube動画 本格分析開始 ===")
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        logger.info("GEMINI_API_KEY 未設定。スキップ")
        return {"available": False}

    videos = fetch_latest_videos()
    if not videos:
        logger.info("対象の最新動画なし")
        return {"available": False}

    cfg   = _load_config()
    model = cfg.get("settings", {}).get("model", "gemini-2.5-flash")

    # ① 各動画を本格解析（新SDK）
    analyses = []
    for v in videos:
        text = _analyze_video_new_sdk(v["url"], model)
        if text:
            analyses.append({**v, "analysis": text})
            logger.info(f"✅ 動画解析成功: {v['title'][:30]}")

    # ② 1本も解析できなければタイトルベースにフォールバック
    if not analyses:
        logger.warning("動画の本格解析に失敗 → タイトルベースへフォールバック")
        return _summarize_titles_fallback(videos)

    points, impact = _aggregate(analyses)
    logger.info(f"✅ YouTube本格分析完了: {len(analyses)}本")
    return {
        "available": True,
        "videos":    analyses,             # title,url,channel,analysis を含む
        "points":    points,
        "impact":    impact,
        "full_text": "\n\n".join(a["analysis"] for a in analyses),
        "mode":      "video",
    }


if __name__ == "__main__":
    import json
    print(json.dumps(run(), ensure_ascii=False, indent=2))
