"""
通知台帳（Step LEDGER）— 同じ内容を1日に二度送らないための共通の記録

問題:
  シグナル検知モジュールが増えた結果、同じ出来事が複数の入口から
  通知されうる状態になっていた。例えばVIXが急騰した日は
  「リスクオフ判定」「市場心理の極値」「相場変動の要因」「急変アラート」の
  4か所が同時に反応する。受け取る側には同じ話が4回届いて見える。

解決:
  すべての通知をこの台帳に通す。台帳は「セッション（JST6時〜翌5時59分）」
  単位で、送信済みのキーを記録する。すでに送ったキーは二度通さない。

  さらに「トピック」の概念を持たせ、表現が違っても中身が同じもの
  （VIX急騰／恐怖指数の上昇 など）を1つにまとめる。

使い方:
    from src.notify_ledger import filter_new, mark_sent
    fresh = filter_new([...])       # 未通知のものだけ返る（記録も同時に行う）
"""
import json
import traceback
from datetime import timedelta
from src.utils import setup_logger, get_jst_now, BASE_DIR

logger = setup_logger("notify_ledger")

_LEDGER_FILE = BASE_DIR / "data" / "notify_ledger.json"

# 同じ出来事を指す別名をまとめるための対応表。
# ここに載っているキーワードを含むイベントは、同じトピックとして1回だけ通す。
_TOPIC_RULES = [
    ("vix",        ("vix", "恐怖指数")),
    ("fear_greed", ("fear&greed", "fear＆greed", "強欲", "恐怖のピーク", "極端な恐怖")),
    ("nikkei",     ("日経", "n225")),
    ("us_stock",   ("s&p", "sp500", "nasdaq", "米国株")),
    ("usdjpy",     ("ドル円", "usdjpy", "円高", "円安")),
    ("gold",       ("金(", "ゴールド", "gc=f")),
    ("rates",      ("金利", "イールド", "国債")),
    ("credit",     ("ハイイールド", "スプレッド", "信用不安")),
    ("policy",     ("利上げ", "利下げ", "政策金利", "frb", "日銀")),
    ("risk_flow",  ("リスクオフ", "リスクオン")),
]


def _session_key(now=None) -> str:
    """JST 6時始まりの取引セッション。夜間の出来事が日付をまたいでも同一に保つ。"""
    now = now or get_jst_now()
    return (now - timedelta(hours=6)).strftime("%Y-%m-%d")


def _load() -> dict:
    try:
        data = json.loads(_LEDGER_FILE.read_text(encoding="utf-8"))
        if data.get("session") != _session_key():
            return {"session": _session_key(), "keys": [], "topics": []}
        return data
    except Exception:
        return {"session": _session_key(), "keys": [], "topics": []}


def _save(data: dict) -> None:
    try:
        _LEDGER_FILE.parent.mkdir(exist_ok=True)
        _LEDGER_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        logger.debug(traceback.format_exc())


def topic_of(text: str) -> str | None:
    """テキストから「何についての話か」を推定する。該当なしは None。"""
    if not text:
        return None
    low = str(text).lower()
    for topic, words in _TOPIC_RULES:
        if any(w in low for w in words):
            return topic
    return None


def already_sent(key: str) -> bool:
    return key in _load().get("keys", [])


def mark_sent(keys) -> None:
    """通知済みとして記録する（キーの文字列、またはその集合）。"""
    if isinstance(keys, str):
        keys = [keys]
    data = _load()
    data["keys"] = list(dict.fromkeys(list(data.get("keys", [])) + list(keys)))
    _save(data)


def mark_topics(topics) -> None:
    """
    トピックだけを先に押さえる。
    上位概念の通知（例: 極端なリスクオフ）は、その構成要素（VIX・株・金…）を
    まとめて説明しているため、構成要素の個別通知を後から出す必要がない。
    そうした場合に、関連トピックをまとめて済みにするために使う。
    """
    if isinstance(topics, str):
        topics = [topics]
    topics = [t for t in topics if t]
    if not topics:
        return
    data = _load()
    data["topics"] = list(dict.fromkeys(list(data.get("topics", [])) + list(topics)))
    data["session"] = _session_key()
    _save(data)
    logger.info(f"上位通知により話題を消化: {topics}")


def filter_new(items, key_func=None, topic_func=None, source: str = "") -> list:
    """
    未通知のものだけを返し、同時に台帳へ記録する。

    items      : 通知候補（dict のリストを想定）
    key_func   : 各要素から一意キーを作る関数（省略時は "key" または "title"）
    topic_func : 各要素からトピックを作る関数（省略時はラベル類から自動推定）

    同一セッションで、同じキーまたは同じトピックが既に送られていればスキップする。
    """
    if not items:
        return []

    def _key(it):
        if key_func:
            return key_func(it)
        if isinstance(it, dict):
            return str(it.get("key") or it.get("title") or it.get("label") or it)[:80]
        return str(it)[:80]

    def _topic(it):
        if topic_func:
            return topic_func(it)
        if isinstance(it, dict):
            for f in ("label", "title", "name", "key"):
                t = topic_of(it.get(f))
                if t:
                    return t
        return topic_of(str(it))

    data = _load()
    sent_keys = set(data.get("keys", []))
    sent_topics = set(data.get("topics", []))

    fresh, new_keys, new_topics = [], [], []
    for it in items:
        k = f"{source}:{_key(it)}" if source else _key(it)
        t = _topic(it)
        if k in sent_keys:
            logger.info(f"重複のためスキップ（同一シグナル）: {k}")
            continue
        if t and t in sent_topics:
            logger.info(f"重複のためスキップ（同じ話題を通知済み）: {k} / topic={t}")
            continue
        fresh.append(it)
        new_keys.append(k)
        sent_keys.add(k)
        if t:
            new_topics.append(t)
            sent_topics.add(t)

    if new_keys:
        data["keys"] = list(dict.fromkeys(list(data.get("keys", [])) + new_keys))
        data["topics"] = list(dict.fromkeys(list(data.get("topics", [])) + new_topics))
        data["session"] = _session_key()
        _save(data)
    return fresh


def reset() -> None:
    """テスト用。台帳を空にする。"""
    _save({"session": _session_key(), "keys": [], "topics": []})


if __name__ == "__main__":
    reset()
    a = [{"key": "vix_spike", "title": "VIXが急騰"}]
    b = [{"key": "risk_off", "title": "極端なリスクオフ（恐怖指数の上昇）"}]
    print("1回目:", len(filter_new(a, source="se")))
    print("2回目(同一):", len(filter_new(a, source="se")))
    print("別モジュールの同話題:", len(filter_new(b, source="rs")))
