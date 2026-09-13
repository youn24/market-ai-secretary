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


def _find_jp_font() -> str | None:
    """字幕描画用の日本語フォントを探す（CI=Noto / Windows=游ゴシック等）"""
    for p in [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKjp-Regular.otf",
        "C:/Windows/Fonts/YuGothM.ttc",
        "C:/Windows/Fonts/meiryo.ttc",
        "C:/Windows/Fonts/msgothic.ttc",
    ]:
        if os.path.exists(p):
            return p
    return None


def _avatar_path(kind: str, mood: str = "neutral") -> str:
    """話者アバター用の高解像度キャラ画像パス"""
    import glob
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    if kind == "ganesha":
        name = {"strong_bull": "bullish", "bull": "bullish", "bear": "bearish",
                "crisis": "crash", "fear": "uncertain"}.get(mood, "analyzing")
        hits = sorted(glob.glob(str(root / "data" / "fx_charts" / f"character_{name}_*.png")))
        if hits:
            return hits[0]
        p = root / "assets" / "gane_sensei.png"
        return str(p) if p.exists() else ""
    p = root / "assets" / "kawauso (4).png"
    return str(p) if p.exists() else ""


def _gradient_canvas():
    """夜明け前グラデーションの縦型キャンバスを返す"""
    from PIL import Image, ImageDraw
    canvas = Image.new("RGB", (SLIDE_W, SLIDE_H), SLIDE_BG)
    draw = ImageDraw.Draw(canvas)
    top, bottom = (18, 26, 46), SLIDE_BG
    for y in range(SLIDE_H):
        t = y / (SLIDE_H - 1)
        draw.line([(0, y), (SLIDE_W, y)],
                  fill=(int(top[0] + (bottom[0] - top[0]) * t),
                        int(top[1] + (bottom[1] - top[1]) * t),
                        int(top[2] + (bottom[2] - top[2]) * t)))
    return canvas


def _wrap_jp(text: str, width: int = 21, max_lines: int = 3) -> list:
    """日本語向けの単純折り返し"""
    lines = [text[i:i + width] for i in range(0, len(text), width)]
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][:width - 1] + "…"
    return lines


_SPEAKER_STYLE = {
    "ganesha": {"label": "ガネーシャ", "color": (255, 215, 0)},
    "otter":   {"label": "カワウソ",   "color": (230, 168, 120)},
    "intro":   {"label": "市場AI秘書", "color": (122, 162, 255)},
}


def _fit_canvas(src: str, dst: str, subtitle: str = "", speaker: str = "",
                mood: str = "neutral") -> bool:
    """画像を縦型キャンバスに配置し、字幕＋話者アバターを重ねて保存。
    サイズを揃えないと連結できないため必須。余白はブランドのグラデーション。
    """
    try:
        from PIL import Image, ImageDraw, ImageFont

        canvas = _gradient_canvas()
        sub_h = 400 if subtitle else 0   # 下部の字幕エリア

        # ── 前景：画像を角丸カードで配置 ──
        pad = 40
        im = Image.open(src).convert("RGB")
        im.thumbnail((SLIDE_W - pad * 2, SLIDE_H - sub_h - pad * 2), Image.LANCZOS)
        radius = 28
        mask = Image.new("L", im.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, im.width, im.height], radius=radius, fill=255)
        pos = ((SLIDE_W - im.width) // 2, (SLIDE_H - sub_h - im.height) // 2)
        canvas.paste(im, pos, mask)
        ImageDraw.Draw(canvas).rounded_rectangle(
            [pos[0], pos[1], pos[0] + im.width, pos[1] + im.height],
            radius=radius, outline=(43, 56, 82), width=2)

        # ── 字幕（話者ラベル＋本文＋アバター） ──
        if subtitle:
            d = ImageDraw.Draw(canvas)
            style = _SPEAKER_STYLE.get(speaker, _SPEAKER_STYLE["intro"])
            fp = _find_jp_font()
            f_lbl = ImageFont.truetype(fp, 34) if fp else ImageFont.load_default()
            f_txt = ImageFont.truetype(fp, 40) if fp else ImageFont.load_default()

            box_x0, box_x1 = 40, SLIDE_W - 40
            box_y1 = SLIDE_H - 60
            box_y0 = box_y1 - 300
            edge = tuple(int(c * 0.55) for c in style["color"])
            d.rounded_rectangle([box_x0, box_y0, box_x1, box_y1], radius=24,
                                fill=(16, 22, 38), outline=edge, width=2)

            # アバター（丸抜き）
            text_x = box_x0 + 36
            av = _avatar_path("otter" if speaker == "otter" else "ganesha", mood) if speaker in ("ganesha", "otter") else ""
            if av and os.path.exists(av):
                size = 170
                a = Image.open(av).convert("RGB").resize((size, size), Image.LANCZOS)
                m = Image.new("L", (size, size), 0)
                ImageDraw.Draw(m).ellipse([0, 0, size, size], fill=255)
                ay = box_y0 - size // 2
                ax = box_x0 + 24
                canvas.paste(a, (ax, ay), m)
                ImageDraw.Draw(canvas).ellipse(
                    [ax, ay, ax + size, ay + size], outline=style["color"], width=4)

            # 話者ラベル（アバターの右隣に。重なり防止）
            lbl_x = box_x0 + 220 if speaker in ("ganesha", "otter") else text_x
            d.text((lbl_x, box_y0 + 22), style["label"], font=f_lbl, fill=style["color"])
            # 本文（折り返し）
            y = box_y0 + 80
            for ln in _wrap_jp(subtitle):
                d.text((text_x, y), ln, font=f_txt, fill=(243, 246, 255))
                y += 58

        canvas.save(dst)
        return True
    except Exception:
        logger.debug(traceback.format_exc())
        return False


def _make_title_card(path: str) -> bool:
    """オープニングのタイトルカード（ブランド名＋日付）"""
    try:
        from PIL import ImageDraw, ImageFont
        from datetime import datetime, timedelta, timezone

        canvas = _gradient_canvas()
        d = ImageDraw.Draw(canvas)
        fp = _find_jp_font()
        f_big = ImageFont.truetype(fp, 96) if fp else ImageFont.load_default()
        f_mid = ImageFont.truetype(fp, 46) if fp else ImageFont.load_default()
        f_sml = ImageFont.truetype(fp, 36) if fp else ImageFont.load_default()

        jst = datetime.now(timezone(timedelta(hours=9)))
        wd = ["月", "火", "水", "木", "金", "土", "日"][jst.weekday()]
        cy = SLIDE_H // 2 - 160

        # ブランドの脈（緑パルス）
        pts = [(SLIDE_W//2-220, cy-40), (SLIDE_W//2-120, cy-90), (SLIDE_W//2-40, cy-60),
               (SLIDE_W//2+80, cy-140), (SLIDE_W//2+220, cy-190)]
        d.line(pts, fill=(0, 255, 135), width=10, joint="curve")
        d.ellipse([pts[-1][0]-12, pts[-1][1]-12, pts[-1][0]+12, pts[-1][1]+12],
                  outline=(0, 255, 135), width=6)

        def center(y, text, font, fill):
            w = d.textlength(text, font=font)
            d.text(((SLIDE_W - w) // 2, y), text, font=font, fill=fill)

        center(cy + 40,  "市場AI秘書", f_big, (243, 246, 255))
        center(cy + 190, "今朝の相場サマリー", f_mid, (122, 162, 255))
        center(cy + 280, jst.strftime(f"%Y.%m.%d（{wd}）"), f_sml, (132, 146, 171))
        canvas.save(path)
        return True
    except Exception:
        logger.debug(traceback.format_exc())
        return False


def _sentences(t: str) -> list:
    """文単位に分割（字幕同期用）"""
    parts = re.split(r"(?<=[。！？!?])", t or "")
    return [p.strip() for p in parts if p.strip()]


# ── VOICEVOX（キャラ声・無料ローカルエンジン） ──
# GitHub ActionsではDockerで起動し VOICEVOX_URL で接続。無ければedge-ttsへ自動フォールバック
VOICEVOX_SPEAKERS = {
    "intro":   {"speaker": 8,  "speed": 1.02, "pitch": 0.0},    # 春日部つむぎ: 明るい案内役
    "ganesha": {"speaker": 13, "speed": 0.92, "pitch": -0.04},  # 青山龍星: 低く渋い長老声
    "otter":   {"speaker": 1,  "speed": 1.06, "pitch": 0.03},   # ずんだもん(あまあま): かわいい
}


def _voicevox_base() -> str:
    base = os.getenv("VOICEVOX_URL", "").strip().rstrip("/")
    if not base:
        return ""
    try:
        import requests
        r = requests.get(f"{base}/version", timeout=3)
        if r.status_code == 200:
            return base
    except Exception:
        pass
    return ""


def _tts_voicevox(base: str, text: str, kind: str, out_wav: str) -> bool:
    try:
        import requests
        cfg = VOICEVOX_SPEAKERS.get(kind, VOICEVOX_SPEAKERS["intro"])
        q = requests.post(f"{base}/audio_query",
                          params={"text": text, "speaker": cfg["speaker"]}, timeout=30).json()
        q["speedScale"] = cfg["speed"]
        q["pitchScale"] = cfg["pitch"]
        r = requests.post(f"{base}/synthesis", params={"speaker": cfg["speaker"]},
                          json=q, timeout=300)
        r.raise_for_status()
        with open(out_wav, "wb") as f:
            f.write(r.content)
        return os.path.getsize(out_wav) > 0
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

        async def _tts_edge(text, voice, rate, pitch, out):
            import edge_tts
            await edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(out)

        # VOICEVOX（キャラ声）が使えるなら優先。無ければedge-ttsへ自動フォールバック
        vv = _voicevox_base()
        if vv:
            logger.info(f"VOICEVOX使用（キャラ声モード）: {vv}")

        segs = []   # (kind, text, audiopath)
        for i, (kind, t, v, rate, pitch) in enumerate(plan):
            done = False
            if vv:
                p = os.path.join(tmp, f"s{i}.wav")
                done = _tts_voicevox(vv, t, kind, p)
            if not done:
                p = os.path.join(tmp, f"s{i}.mp3")
                try:
                    asyncio.run(_tts_edge(t, v, rate, pitch, p))
                    done = os.path.exists(p) and os.path.getsize(p) > 0
                except Exception:
                    logger.debug(traceback.format_exc())
            if done:
                segs.append((kind, t, p))
        if not segs:
            return result

        import subprocess

        # ── 音声を結合 ──
        audio = os.path.join(tmp, "audio.mp3")
        paths = [p for _, _, p in segs]
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

        # ── スライド構成（文単位の字幕つき・話の区切りで場面転換） ──
        charts = chart_paths or {}
        mood = cc.get("mood", "neutral")

        def _pick(*keys):
            for k in keys:
                p = charts.get(k)
                if p and os.path.exists(str(p)):
                    return str(p)
            return ""

        sector_img = _pick("sector", "sector_heatmap")
        market_img = _pick("indices", "overview", "prices", "technical")

        title_card = os.path.join(tmp, "title.png")
        has_title = _make_title_card(title_card)

        slides = []   # (元画像, 表示秒数, 字幕, 話者)
        for kind, text, ap in segs:
            seg_dur = _audio_dur(ap) or 6.0
            sents = _sentences(text) or [text]
            total = sum(len(s) for s in sents) or 1
            n = len(sents)
            for j, s in enumerate(sents):
                dur = max(seg_dur * len(s) / total, 1.2)
                if kind == "intro":
                    img = title_card if has_title else bg
                elif kind == "ganesha":
                    # 前半＝セクター図 / 後半＝市場チャート（無ければサマリーカード）
                    img = (sector_img if j < n / 2 else market_img) or sector_img or market_img or bg
                else:
                    img = bg
                slides.append((img, dur, s, kind))

        # 画像を共通キャンバスに整形＋字幕・アバター焼き込み（揃えないと連結できない）
        norm = []
        for i, (img, dur, sub, spk) in enumerate(slides):
            dst = os.path.join(tmp, f"slide{i}.png")
            if _fit_canvas(img, dst, subtitle=sub, speaker=spk, mood=mood):
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
