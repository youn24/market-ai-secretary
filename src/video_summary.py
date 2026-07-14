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


# スライドの共通キャンバス（縦型・スマホ最適）
SLIDE_W, SLIDE_H = 1080, 1920
SLIDE_BG = (10, 14, 23)   # ブランドの夜明け前の地色 #0a0e17


def _audio_dur(path: str) -> float:
    """mp3の長さ（秒）をffmpegの出力から取得"""
    import subprocess
    try:
        p = subprocess.run(["ffmpeg", "-i", path], capture_output=True, text=True)
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", p.stderr or "")
        if m:
            return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    except Exception:
        pass
    return 0.0


def _fit_canvas(src: str, dst: str) -> bool:
    """画像を共通キャンバス(縦型)に配置して保存。
    サイズを揃えないと連結できないため必須。余白は黒ベタではなく
    ブランドのグラデーション＋角丸カード風にして「間」を意図あるものにする。
    """
    try:
        from PIL import Image, ImageDraw

        # ── 背景：夜明け前のグラデーション ──
        canvas = Image.new("RGB", (SLIDE_W, SLIDE_H), SLIDE_BG)
        draw = ImageDraw.Draw(canvas)
        top, bottom = (18, 26, 46), SLIDE_BG      # 上をわずかに明るく
        for y in range(SLIDE_H):
            t = y / max(SLIDE_H - 1, 1)
            draw.line(
                [(0, y), (SLIDE_W, y)],
                fill=(int(top[0] + (bottom[0] - top[0]) * t),
                      int(top[1] + (bottom[1] - top[1]) * t),
                      int(top[2] + (bottom[2] - top[2]) * t)),
            )

        # ── 前景：画像を余白つきで最大化し、角丸に ──
        pad = 40
        im = Image.open(src).convert("RGB")
        im.thumbnail((SLIDE_W - pad * 2, SLIDE_H - pad * 2), Image.LANCZOS)

        radius = 28
        mask = Image.new("L", im.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, im.width, im.height],
                                               radius=radius, fill=255)
        pos = ((SLIDE_W - im.width) // 2, (SLIDE_H - im.height) // 2)
        canvas.paste(im, pos, mask)

        # 縁取り（うっすら）
        ImageDraw.Draw(canvas).rounded_rectangle(
            [pos[0], pos[1], pos[0] + im.width, pos[1] + im.height],
            radius=radius, outline=(43, 56, 82), width=2,
        )

        canvas.save(dst)
        return True
    except Exception:
        logger.debug(traceback.format_exc())
        return False


def run(prices=None, fear_greed=None, risk=None, ai_summary=None, news=None,
        character_comments=None, chart_paths=None, mode: str = "morning") -> dict:
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

        # ── ナレーション（キャラに合わせた声づくり） ──
        # edge-ttsの日本語はKeita(男)/Nanami(女)の2種のみ。
        # 音程(pitch)と速度(rate)でキャラの声色を作り分ける。
        #   ガネーシャ: 低く・ゆっくり → 知恵の神の威厳
        #   カワウソ  : 高く・軽やか   → かわいく元気
        intro = "おはようございます。今朝の相場を、ガネーシャとカワウソがお届けします。"
        plan = [
            ("intro",   intro, "ja-JP-NanamiNeural", "+0%", "+8Hz"),    # 導入：やわらかく自然に
            ("ganesha", gane,  "ja-JP-KeitaNeural",  "-8%", "-18Hz"),   # ガネーシャ：低音・ゆったり
            ("otter",   otter, "ja-JP-NanamiNeural", "+8%", "+28Hz"),   # カワウソ：高音・かわいく
        ]
        plan = [p for p in plan if p[1]]

        async def _tts(text, voice, rate, pitch, out):
            import edge_tts
            await edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(out)

        segs = []   # (kind, mp3path)
        for i, (kind, t, v, rate, pitch) in enumerate(plan):
            p = os.path.join(tmp, f"s{i}.mp3")
            try:
                asyncio.run(_tts(t, v, rate, pitch, p))
                if os.path.exists(p) and os.path.getsize(p) > 0:
                    segs.append((kind, p))
            except Exception:
                logger.debug(traceback.format_exc())
        if not segs:
            return result

        import subprocess

        # ── 音声を結合 ──
        audio = os.path.join(tmp, "audio.mp3")
        paths = [p for _, p in segs]
        if len(paths) == 1:
            shutil.copy(paths[0], audio)
        else:
            inputs = []
            for s in paths:
                inputs += ["-i", s]
            fc = "".join(f"[{i}:a]" for i in range(len(paths))) + \
                 f"concat=n={len(paths)}:v=0:a=1[a]"
            subprocess.run(["ffmpeg", "-y", *inputs, "-filter_complex", fc,
                            "-map", "[a]", audio], check=True, capture_output=True)

        # ── スライド構成（話の区切りで画面を切り替える） ──
        charts = chart_paths or {}

        def _pick(*keys):
            for k in keys:
                p = charts.get(k)
                if p and os.path.exists(str(p)):
                    return str(p)
            return ""

        sector_img = _pick("sector", "sector_heatmap")
        market_img = _pick("indices", "overview", "prices", "technical")

        slides = []   # (元画像, 表示秒数)
        for kind, mp3 in segs:
            dur = _audio_dur(mp3) or 6.0
            if kind == "ganesha":
                # セクターを語る長い区間 → セクター図と市場チャートで場面転換
                imgs = [i for i in (sector_img, market_img) if i]
                if len(imgs) >= 2 and dur > 40:
                    slides.append((imgs[0], dur / 2))
                    slides.append((imgs[1], dur / 2))
                elif imgs:
                    slides.append((imgs[0], dur))
                else:
                    slides.append((bg, dur))
            else:
                # 導入・カワウソ → キャラの写ったサマリーカード
                slides.append((bg, dur))

        # 画像サイズを揃える（揃えないと連結できない）
        norm = []
        for i, (img, dur) in enumerate(slides):
            dst = os.path.join(tmp, f"slide{i}.png")
            if _fit_canvas(img, dst):
                norm.append((f"slide{i}.png", dur))
        if not norm:
            return result

        # concat用リスト（tmpをcwdにして相対パス＝日本語パス問題を回避）
        listfile = os.path.join(tmp, "slides.txt")
        with open(listfile, "w", encoding="utf-8") as f:
            for name, dur in norm:
                f.write(f"file '{name}'\n")
                f.write(f"duration {max(dur, 1.0):.3f}\n")
            f.write(f"file '{norm[-1][0]}'\n")   # concat demuxerの仕様上、最後をもう一度

        out_mp4 = os.path.join(tmp, "summary.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "slides.txt",
             "-i", "audio.mp3", "-c:v", "libx264", "-r", "24", "-pix_fmt", "yuv420p",
             "-vf", f"scale={SLIDE_W}:{SLIDE_H}:force_original_aspect_ratio=decrease,"
                    f"pad={SLIDE_W}:{SLIDE_H}:(ow-iw)/2:(oh-ih)/2:color=0x0a0e17",
             "-c:a", "aac", "-b:a", "160k", "-shortest", "summary.mp4"],
            check=True, capture_output=True, cwd=tmp,
        )
        if os.path.exists(out_mp4) and os.path.getsize(out_mp4) > 0:
            result["available"] = True
            result["path"] = out_mp4
            logger.info(f"✅ 要約動画生成（スライド{len(norm)}枚）: {out_mp4}")
    except Exception:
        logger.warning("要約動画生成エラー")
        logger.debug(traceback.format_exc())

    return result
