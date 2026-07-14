"""
分析要約ナレーション動画（Telegram 通知③用）

サマリーカード画像に、AIガネーシャ＆AIカワウソの要約を日本語音声で載せた
短いMP4を生成する。音声は edge-tts（無料・APIキー不要）、動画合成は ffmpeg。

設計原則:
  - ffmpeg / edge-tts が無い環境では available=False を返し、全体を止めない
  - どこで失敗しても例外を飲み込み、通知①②には影響させない
  - ガネーシャ=男性声(Keita) / カワウソ=女性声(Nanami) で2声ナレーション
"""

import os
import re
import shutil
import asyncio
import tempfile
import logging
import traceback

logger = logging.getLogger(__name__)

# 絵文字・記号（TTSが変な読み上げをするので除去）
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF"
    "\U0001F1E6-\U0001F1FF⬀-⯿←-⇿✀-➿️]"
)


def _clean(t) -> str:
    return _EMOJI.sub("", str(t or "")).replace("　", " ").strip()


def run(prices=None, fear_greed=None, risk=None, ai_summary=None, news=None,
        character_comments=None, mode: str = "morning") -> dict:
    """要約ナレーション動画を生成して {"available":bool, "path":str} を返す"""
    result = {"available": False, "path": ""}

    if not shutil.which("ffmpeg"):
        logger.info("ffmpeg が無いため要約動画をスキップ")
        return result
    try:
        import edge_tts  # noqa: F401
    except Exception:
        logger.info("edge-tts が無いため要約動画をスキップ")
        return result

    cc = character_comments or {}
    gane = _clean(cc.get("ganesha"))
    otter = _clean(cc.get("otter"))
    if not gane and not otter:
        return result

    try:
        # ── 背景画像（サマリーカードを流用） ──
        bg = ""
        try:
            from src.summary_card import make_summary_card
            bg = make_summary_card(
                prices=prices or {}, fear_greed=fear_greed or {}, risk=risk or {},
                ai_summary=ai_summary or {}, news=list(news or []),
                character_comments=cc,
            )
        except Exception:
            logger.debug(traceback.format_exc())
        if not bg or not os.path.exists(bg):
            logger.info("背景画像が無いため要約動画をスキップ")
            return result

        tmp = tempfile.mkdtemp(prefix="vsum_")

        # ── ナレーション（2声） ──
        intro = "おはようございます。今朝の相場を、ガネーシャとカワウソがお届けします。"
        plan = [(intro, "ja-JP-NanamiNeural"),
                (gane,  "ja-JP-KeitaNeural"),
                (otter, "ja-JP-NanamiNeural")]
        plan = [(t, v) for t, v in plan if t]

        async def _tts(text, voice, out):
            import edge_tts
            await edge_tts.Communicate(text, voice, rate="+4%").save(out)

        segs = []
        for i, (t, v) in enumerate(plan):
            p = os.path.join(tmp, f"s{i}.mp3")
            try:
                asyncio.run(_tts(t, v, p))
                if os.path.exists(p) and os.path.getsize(p) > 0:
                    segs.append(p)
            except Exception:
                logger.debug(traceback.format_exc())
        if not segs:
            return result

        import subprocess

        # ── 音声を結合 ──
        audio = os.path.join(tmp, "audio.mp3")
        if len(segs) == 1:
            shutil.copy(segs[0], audio)
        else:
            inputs = []
            for s in segs:
                inputs += ["-i", s]
            fc = "".join(f"[{i}:a]" for i in range(len(segs))) + \
                 f"concat=n={len(segs)}:v=0:a=1[a]"
            subprocess.run(["ffmpeg", "-y", *inputs, "-filter_complex", fc,
                            "-map", "[a]", audio], check=True, capture_output=True)

        # ── 静止画 + 音声 → MP4 ──
        out_mp4 = os.path.join(tmp, "summary.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-loop", "1", "-i", bg, "-i", audio,
             "-c:v", "libx264", "-tune", "stillimage", "-c:a", "aac", "-b:a", "160k",
             "-pix_fmt", "yuv420p", "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
             "-shortest", out_mp4],
            check=True, capture_output=True,
        )
        if os.path.exists(out_mp4) and os.path.getsize(out_mp4) > 0:
            result["available"] = True
            result["path"] = out_mp4
            logger.info(f"✅ 要約動画生成: {out_mp4}")
    except Exception:
        logger.warning("要約動画生成エラー")
        logger.debug(traceback.format_exc())

    return result
