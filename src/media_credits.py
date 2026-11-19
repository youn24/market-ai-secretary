# -*- coding: utf-8 -*-
"""写真と動画を、出典つきで正式に引用する（Step MC）

オーナー指示（2026-11-19）: 「画像や動画をサイトや公式から出典を引用してほしい」
　　　　　　　　　　　　　　「誤情報やハルシネーションが無いように」

**この2つは同じ話である。** 外から素材を持ってくる仕組みは、作りを誤ると
「それらしいが実際とは違うもの」を自信満々に並べる装置になる。
だからこのモジュールは、速さや量ではなく**嘘をつかないこと**を軸に設計してある。

────────────────────────────────────────
嘘を防ぐための決まり（ここが本体）
────────────────────────────────────────

**① 検索で素材を選ばない。手で検証した固定リストだけを使う。**
   実測（2026-11-19）: Commons で "Tokyo Stock Exchange building" を全文検索したら、
   上位に **米国農務省の文書**・**バングラデシュの官報**・"History of the Mansion House"
   が並んだ。語が一致しただけで被写体は無関係。
   そのまま使えば「東京証券取引所」として農務省の文書を載せることになる。
   同じく YouTube で `@BloombergTelevision` を開いたら**韓国の日記チャンネル**、
   `@telebiz` は**オーストリアの電話営業会社**だった。
   → **名前からの推測は必ず間違える。** 下の表は全件、実際に取得して目で確かめた。

**② 表示する文字は、APIが返したものをそのまま出す。**
   写真の説明も動画の要約もこちらで書かない。見ていないものを説明するのが
   ハルシネーションそのもの。作者名・ライセンス・題名は API の値を素通しする。

**③ ライセンスを機械で確かめる。**
   CC0 / パブリックドメイン / CC BY / CC BY-SA 以外は**使わない**。
   再アップロードでライセンスが変わることがあるので、毎回確認する。

**④ 取れなかったら出さない。** 代わりの素材を探しに行かない
   （探しに行くと①の検索に戻ってしまう）。

**⑤ 写真は「その日の相場の写真」ではない。**
   Commons にあるのは建物の一般写真である。今日の数字の隣に無断で置くと
   今日の光景と誤読される。**いつ撮られた何の写真か**を必ず添える。
"""
import json
import re
import ssl
import time
import urllib.parse
import urllib.request

from src.utils import setup_logger, BASE_DIR, get_jst_now

logger = setup_logger("media_credits")

_CACHE_FILE = BASE_DIR / "data" / "media_cache.json"
_CACHE_HOURS = 24 * 7          # 写真は変わらない。動画は下で別に短くする
_UA = "market-ai-secretary/1.0 (personal market report; https://github.com/youn24)"

# ⚠️ ここに無いライセンスは使わない。
_OK_LICENSE = ("cc0", "public domain", "cc by", "cc by-sa", "pd-")

# ── 写真（全件 2026-11-19 に取得して実在・ライセンス・作者を確認済み）──
# 鍵 → (Commonsのファイル名, 日本語の説明)
# ⚠️ 説明はこちらで書いた「何の写真か」。中身を見て書くこと。
#    増やすときは必ず `python -m src.media_credits` で実物を確認してから。
PHOTOS = {
    "tse":   ("File:The Entrance of Tokyo Stock Exchange Main Building 20240329.jpg",
              "東京証券取引所 本館の入口"),
    "tse2":  ("File:Tokyo Stock Exchange Main Building (1988).jpg",
              "東京証券取引所 本館"),
    "boj":   ("File:Bank of Japan building (14490).jpg",
              "日本銀行 本店"),
    "mof":   ("File:Ministry of Finance Building (Japan).jpg",
              "財務省 庁舎"),
    "nyse":  ("File:Sign of the New York Stock Exchange, Broad Street.jpg",
              "ニューヨーク証券取引所の看板（ブロード通り）"),
    "nyse2": ("File:NEW YORK STOCK EXCHANGE 20240521.jpg",
              "ニューヨーク証券取引所"),
    "fed":   ("File:Eccles Building (26088200676).jpg",
              "米連邦準備制度理事会（FRB）エクルズ・ビル"),
}

# ── 動画（全件 2026-11-19 に youtube.com/@handle から channelId を実取得）──
# 鍵 → (channelId, フィードが名乗る名義, 画面に出す名前)
#
# ⚠️ ハンドル名から推測して書かない。上のコメントの実例のとおり別人に当たる。
# ⚠️ **「フィードが名乗る名義」はページの表示名と違うことがある。**
#    @nikkei のページは『日本経済新聞』だが、RSSの名義は
#    『NIKKEI PODCAST 日経ポッドキャスト』だった（同じチャンネル）。
#    照合に使うのは**RSSの名義**。ここを表示名で書くと毎回弾かれる。
YOUTUBE_CHANNELS = {
    "nikkei":    ("UCa5GTH97HPtpXNuysWvWL_A", "NIKKEI PODCAST 日経ポッドキャスト",
                  "日本経済新聞（日経ポッドキャスト）"),
    "reuters":   ("UChqUTb7kYRX8-EiaN3XFrSQ", "Reuters", "Reuters"),
    "bloomberg": ("UCIALMKvObZNtJ6AmdCLP7Lg", "Bloomberg Television",
                  "Bloomberg Television"),
    "tvtokyo":   ("UCkKVQ_GNjd8FbAuT6xDcWgg", "テレ東BIZ ダイジェスト",
                  "テレ東BIZ ダイジェスト"),
}


# ══════════════════════════════════════════════════════════
def _ctx():
    """証明書。手元のWindowsは期限切れのことがあるので certifi を優先する。

    ⚠️ ここで落ちるのを「先方が落ちている」と誤診しないこと。
       実際 Commons が CERTIFICATE_VERIFY_FAILED になり、
       一度「到達不可」と判断しかけた（原因はこちらの証明書ストア）。
    """
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _get(url: str, timeout: int = 20, tries: int = 3) -> str:
    """429（出しすぎ）は待って引き下がる。相手の迷惑になるので粘らない。"""
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            return urllib.request.urlopen(
                req, timeout=timeout, context=_ctx()).read().decode("utf-8", "ignore")
        except Exception as e:
            last = e
            if getattr(e, "code", None) == 429 and i < tries - 1:
                time.sleep(20 * (i + 1))
                continue
            break
    raise last


def _cache_load() -> dict:
    try:
        return json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _cache_save(d: dict) -> None:
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=1),
                               encoding="utf-8")
    except Exception:
        logger.debug("媒体キャッシュを保存できませんでした")


def _fresh(entry, hours) -> bool:
    try:
        return (time.time() - float(entry.get("_at", 0))) < hours * 3600
    except Exception:
        return False


def _text(x) -> str:
    """APIが返すHTML混じりの値を、そのままの意味で平文にする。

    ⚠️ 中身を言い換えない。タグを外して空白を詰めるだけ。
    """
    return re.sub(r"\s+", " ", re.sub("<[^>]+>", "", str(x or ""))).strip()


# ══════════════════════════════════════════════════════════
def photo(key: str) -> dict | None:
    """固定リストの写真1枚を、ライセンスと作者つきで返す。

    返り値: {url, page, license, author, caption, width, height}
    使えない（存在しない・ライセンスが条件外・取得失敗）なら None。
    """
    item = PHOTOS.get(key)
    if not item:
        logger.warning(f"写真の鍵が一覧にありません: {key}")
        return None
    title, caption = item

    cache = _cache_load()
    ck = f"photo:{title}"
    if _fresh(cache.get(ck), _CACHE_HOURS):
        return cache[ck]["v"]

    try:
        u = ("https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(
            {"format": "json", "action": "query", "prop": "imageinfo",
             "iiprop": "url|extmetadata|size", "titles": title}))
        d = json.loads(_get(u, timeout=25))
        pages = list((d.get("query") or {}).get("pages", {}).values())
        if not pages or "missing" in pages[0]:
            logger.warning(f"Commonsにその写真がありません: {title}")
            return None
        p = pages[0]
        ii = (p.get("imageinfo") or [{}])[0]
        em = ii.get("extmetadata") or {}
        lic = _text((em.get("LicenseShortName") or {}).get("value"))

        # ③ ライセンスの確認。条件外なら使わない。
        if not any(k in lic.lower() for k in _OK_LICENSE):
            logger.warning(f"ライセンスが条件外なので使いません: {title} / {lic}")
            return None
        if not ii.get("url"):
            return None

        v = {
            "url": ii["url"],
            "page": ii.get("descriptionurl") or "",
            "license": lic,
            "author": _text((em.get("Artist") or {}).get("value"))[:60],
            "taken": _text((em.get("DateTimeOriginal") or {}).get("value"))[:30],
            "caption": caption,
            "width": ii.get("width"), "height": ii.get("height"),
        }
        cache[ck] = {"_at": time.time(), "v": v}
        _cache_save(cache)
        return v
    except Exception as e:
        logger.warning(f"写真を取得できませんでした [{title}]: {e}")
        # ④ 代わりを探さない。黙って出さない。
        return None


def photo_credit(p: dict) -> str:
    """写真に必ず添える1行。これが無い写真は出さない。

    ⚠️ 「いつ撮られた何の写真か」まで書く。今日の光景と誤読させないため。
    """
    if not p:
        return ""
    bits = [p.get("caption") or ""]
    if p.get("taken"):
        bits.append(f"撮影 {p['taken']}")
    if p.get("author"):
        bits.append(f"{p['author']}")
    if p.get("license"):
        bits.append(f"{p['license']} / Wikimedia Commons")
    return "　".join(b for b in bits if b)


# ══════════════════════════════════════════════════════════
def videos(keys=None, limit: int = 3, max_age_days: int = 3) -> list:
    """公式チャンネルの最新動画を、題名とチャンネル名のまま返す。

    ⚠️ **要約しない。** 動画を見ていないのに中身を書くのがハルシネーション。
       出すのは YouTube が返した題名・チャンネル名・公開日・リンクだけ。
    """
    out = []
    cache = _cache_load()
    for key in (keys or list(YOUTUBE_CHANNELS)):
        ent = YOUTUBE_CHANNELS.get(key)
        if not ent:
            logger.warning(f"チャンネルの鍵が一覧にありません: {key}")
            continue
        cid, feed_expect, name = ent
        ck = f"yt:{cid}"
        if _fresh(cache.get(ck), 3):          # 動画は3時間で取り直す
            rows = cache[ck]["v"]
        else:
            try:
                x = _get(f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}",
                         timeout=20)
                # フィードが名乗っている名義を確認する。別チャンネルに
                # 差し替わっていたら（IDの打ち間違い等）そのまま使わない。
                a = re.search(r"<author>\s*<name>(.*?)</name>", x, re.S)
                feed_name = _text(a.group(1)) if a else ""
                if feed_name and feed_name != feed_expect:
                    # 改名かもしれないし、IDの打ち間違いで別人かもしれない。
                    # 機械には区別がつかないので、**人が確かめ直すまで使わない**。
                    # 「たぶん改名だろう」で通すと、別人の動画を公式として
                    # 載せる事故が起きる（@BloombergTelevision が韓国の
                    # 日記チャンネルだった実例がある）。
                    logger.warning(
                        f"チャンネルの名義が記録と違います（使いません）: "
                        f"記録『{feed_expect}』 / 実際『{feed_name}』。"
                        f"本物か確認して YOUTUBE_CHANNELS を更新してください")
                    continue
                rows = []
                for m in re.finditer(
                        r"<entry>.*?<yt:videoId>(.*?)</yt:videoId>.*?"
                        r"<title>(.*?)</title>.*?<published>(.*?)</published>",
                        x, re.S):
                    vid, title, pub = m.group(1), _text(m.group(2)), m.group(3)
                    rows.append({"id": vid, "title": title, "published": pub,
                                 "channel": feed_name or name,
                                 "url": f"https://www.youtube.com/watch?v={vid}",
                                 "thumb": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"})
                cache[ck] = {"_at": time.time(), "v": rows}
                _cache_save(cache)
            except Exception as e:
                logger.warning(f"動画一覧を取得できませんでした [{name}]: {e}")
                continue

        # 古い動画は出さない（「今日の関連動画」として先週の物が並ぶと誤解を生む）
        now = get_jst_now()
        for r in rows:
            try:
                from datetime import datetime
                t = datetime.fromisoformat(r["published"].replace("Z", "+00:00"))
                age = (now - t.astimezone(now.tzinfo)).days
            except Exception:
                age = 0
            if age <= max_age_days:
                out.append({**r, "age_days": age})

    out.sort(key=lambda r: r["published"], reverse=True)
    return out[:limit]


# ══════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("── 写真（固定リストを実際に取得して確認）──")
    ng = 0
    for k in PHOTOS:
        p = photo(k)
        if p:
            print(f"✅ {k:7} {p['license']:14} {p['author'][:22]:24} {p['caption']}")
        else:
            print(f"❌ {k:7} 使えません")
            ng += 1
        time.sleep(1)
    print("\n── 動画（公式チャンネルの最新）──")
    for v in videos(limit=6, max_age_days=7):
        print(f"  {v['published'][:10]}  [{v['channel']}] {v['title'][:52]}")
    print(f"\n使えない写真: {ng}件")
