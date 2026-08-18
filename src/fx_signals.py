"""
為替シグナル（Step FXS）— 信頼度の高いサインが3つ以上重なった通貨ペアだけ通知

なぜ独立させたか:
  tech_signals は株価指数が主役で、為替はドル円1本しか見ていなかった。
  為替は「クロス円が全部同じ方向」のように通貨をまたいだ見方が要るうえ、
  配信先も株とは別グループ（ようちゃん相場通知）なので、対象と経路を分ける。

  検出ロジックそのものは tech_signals を使い回す。
  同じ判定を二重に実装すると、片方だけ直して食い違う事故が起きるため
  （実際に technical_signal.py と tech_signals.py の重複で二重通知が発生した）。

通知条件:
  「信頼度の高いシグナルが同じ方向に3つ以上」を満たしたペアのみ。
  条件を緩めると毎日鳴って読み飛ばされる。鳴ったら必ず見る状態を保つのが狙い。

run_fx_alert() → 送信したか
"""
import json
import os
import re
import traceback
from datetime import datetime

from src.utils import setup_logger, BASE_DIR, get_jst_now

logger = setup_logger("fx_signals")

_STATE_FILE = BASE_DIR / "data" / "fx_signal_state.json"

# 監視する通貨ペア。(yfinanceシンボル, 表示名, 単位, 表記)
# クロス円を厚くしているのは、日本の相場と直接効き合うため。
# ドルストレートも入れるのは、クロス円の動きが「円が動いた」のか
# 「ドルが動いた」のかを切り分けるのに要るから。
FX_TARGETS = [
    ("USDJPY=X", "ドル円",     "円", "USD/JPY"),
    ("EURJPY=X", "ユーロ円",   "円", "EUR/JPY"),
    ("GBPJPY=X", "ポンド円",   "円", "GBP/JPY"),
    ("AUDJPY=X", "豪ドル円",   "円", "AUD/JPY"),
    ("CHFJPY=X", "スイス円",   "円", "CHF/JPY"),
    ("EURUSD=X", "ユーロドル", "",   "EUR/USD"),
    ("GBPUSD=X", "ポンドドル", "",   "GBP/USD"),
    ("AUDUSD=X", "豪ドルドル", "",   "AUD/USD"),
]

# 通知する最低条件: 信頼度の高いシグナルが同方向にこの数以上
_MIN_STRONG = 3


def _session_key(now=None) -> str:
    """
    JST 6時を境に1日を区切る。為替は24時間動くため、日付だけで区切ると
    夜中のシグナルと朝のシグナルが別セッション扱いになり重複する。
    """
    n = now or get_jst_now()
    d = n.date()
    if n.hour < 6:
        from datetime import timedelta
        d = d - timedelta(days=1)
    return d.isoformat()


def _load_state() -> dict:
    try:
        return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _filter_new(groups: list) -> list:
    """
    同じペア・同じ方向は1セッション1回だけ。
    為替は同じ形が何時間も続くので、これが無いと同じ内容が鳴り続ける。
    """
    skey = _session_key()
    st = _load_state()
    kept = []
    for g in groups:
        key = f"{g['symbol']}:{g['direction']}"
        rec = st.get(key)
        if isinstance(rec, dict) and rec.get("session") == skey:
            logger.info(f"通知済みのためスキップ: {g['name']} {g['direction']}")
            continue
        kept.append(g)

    if kept:
        for g in kept:
            st[f"{g['symbol']}:{g['direction']}"] = {
                "session": skey, "ts": datetime.now().isoformat()}
        st = {k: v for k, v in st.items()
              if isinstance(v, dict) and v.get("session") == skey}
        try:
            _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            _STATE_FILE.write_text(json.dumps(st, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
        except Exception:
            logger.error("状態の保存に失敗しました", exc_info=True)
    return kept


def detect() -> list:
    """
    全通貨ペアを検査し、強いシグナルが3つ以上重なったものだけ返す。
    検出は tech_signals の実装をそのまま使う（判定の二重実装を避けるため）。
    """
    from src import tech_signals as ts

    hits = []
    for sym, name, unit, ticker in FX_TARGETS:
        for interval, tf_name, period, weight in ts._TF_SPECS:
            try:
                df = ts._fetch(sym, period, interval)
                if df is None or len(df) < 30:
                    continue
                c = df["Close"]
                hi = df["High"] if "High" in df else None
                lo = df["Low"] if "Low" in df else None
                for fn in ts._DETECTORS:
                    try:
                        r = fn(c, hi, lo) if fn is ts._sig_ichimoku else fn(c)
                    except Exception:
                        logger.debug(traceback.format_exc())
                        continue
                    if not r:
                        continue
                    r["label"] = ts._relabel(r.get("label", ""), tf_name)
                    r["desc"] = ts._relabel(r.get("desc", ""), tf_name)
                    r.update({
                        "symbol": sym, "name": name, "unit": unit, "ticker": ticker,
                        "tf": tf_name, "tf_weight": weight,
                        "base_type": r["type"],
                        "type": f"{r['type']}@{interval}",
                    })
                    hits.append(r)
            except Exception:
                logger.error(f"{name} の検査に失敗しました", exc_info=True)

    if not hits:
        return []

    groups = ts._confluence(hits)
    # 3つ以上そろったものだけを残す。ここを緩めると毎日鳴って意味を失う。
    strong = [g for g in groups if g.get("strong_count", 0) >= _MIN_STRONG]
    logger.info(f"為替: {len(groups)}ペアで検出 / うち{len(strong)}ペアが"
                f"強いシグナル{_MIN_STRONG}つ以上")
    return strong


def _currency_read(groups: list) -> list:
    """
    通貨ペアの並びから「どの通貨が強い/弱い」を読む。

    ペアごとに「ユーロ円が上」「ポンド円が上」と個別に言われても、
    それが円安なのか欧州通貨高なのかは初心者には分からない。
    クロス円が揃って上なら円が全面安、ドルストレートが揃って下ならドル高、
    というように、共通している通貨を見つけて言葉にする。
    """
    jpy_up = [g for g in groups if g["symbol"].endswith("JPY=X") and g["direction"] == "buy"]
    jpy_dn = [g for g in groups if g["symbol"].endswith("JPY=X") and g["direction"] == "sell"]
    usd_up = [g for g in groups if g["symbol"].endswith("USD=X") and g["direction"] == "sell"]
    usd_dn = [g for g in groups if g["symbol"].endswith("USD=X") and g["direction"] == "buy"]

    out = []
    if len(jpy_up) >= 2:
        out.append(f"🇯🇵 *円が全面安*（{len(jpy_up)}通貨に対して円売り）"
                   "。日本株の輸出企業には追い風になりやすい形です。")
    elif len(jpy_dn) >= 2:
        out.append(f"🇯🇵 *円が全面高*（{len(jpy_dn)}通貨に対して円買い）"
                   "。リスクを避ける動きが出ている可能性があり、日本株には重荷です。")

    # ドルストレートは「ドルが分母」なので、ペアの下落＝ドル高になる
    if len(usd_up) >= 2:
        out.append(f"💵 *ドルが全面高*（{len(usd_up)}通貨に対してドル買い）"
                   "。新興国や商品市況には逆風になりやすい形です。")
    elif len(usd_dn) >= 2:
        out.append(f"💵 *ドルが全面安*（{len(usd_dn)}通貨に対してドル売り）。")

    if not out and len(groups) == 1:
        g = groups[0]
        arrow = "上昇" if g["direction"] == "buy" else "下落"
        out.append(f"📖 いまのところ *{g['name']}単独* の{arrow}サインです。"
                   "他の通貨ペアには広がっていないため、この通貨固有の材料の可能性があります。")
    return out


def build_message(groups: list) -> str:
    from src import tech_signals as ts

    names = "・".join(g["name"] for g in groups)
    lines = [f"💱 *為替シグナル｜{names}*",
             f"強いサインが{_MIN_STRONG}つ以上重なった通貨ペアです",
             "━━━━━━━━━━━━━━"]

    # 個々のペアを見る前に、通貨全体で何が起きているかを先に言う
    read = _currency_read(groups)
    if read:
        lines += ["", "📖 *ひとことで言うと*"] + read

    for g in groups:
        same = [s for s in g["signals"] if s.get("direction") == g["direction"]]
        arrow = "上昇" if g["direction"] == "buy" else "下落"
        icon = "🔼" if g["direction"] == "buy" else "🔽"
        lines += ["",
                  f"{icon} *{g['name']}（{g['ticker']}）*　{arrow}方向 {g['stars']}",
                  f"　根拠 {g['strong_count']}つ一致・信頼度{g['rank']}"]

        lines += ts._mtf_text(g.get("mtf"))

        for s in g["signals"]:
            mark = "・" if s.get("direction") == g["direction"] else "※逆"
            lines.append(f"{mark}【{s.get('tf','')}】{s['emoji']} {s['label']}")

        if g.get("mtf_against"):
            lines.append("⚠️ 大きな時間軸は逆向きです。戻り/押し目の可能性があります。")
        if g["conflict"]:
            lines.append("⚠️ 逆方向のサインも出ており、勢いは不透明です。")

        lead = g["signals"][0]
        if lead.get("desc"):
            lines.append(lead["desc"])

    lines.append("\n🕐は週足・日足・4時間足それぞれの地合い。"
                 "⭐=全時間軸が同じ向き（最も逆らいにくい形）。"
                 "教科書的なシグナルを機械判定したものです。")
    # 空行を落とすと全部が詰まって読みにくくなる（見出しの区切りが消える）。
    # 空行は残しつつ、3行以上続く隙間だけ2行に詰める。
    text = "\n".join(lines).strip()
    return re.sub(r"\n{3,}", "\n\n", text)[:4000]


def run_fx_alert() -> bool:
    """monitor_run.py から呼ぶ。為替グループへ1通にまとめて送る。"""
    try:
        groups = detect()
        if not groups:
            logger.info("為替シグナル: 条件を満たすペアなし")
            return False

        groups = _filter_new(groups)
        if not groups:
            return False

        from src.notify_telegram import send_message
        # 為替・マクロは専用グループへ送る。未設定ならメイン側に落とす
        # （設定漏れで通知そのものが消えるのを防ぐ）。
        chat_id = os.getenv("TELEGRAM_FX_CHAT_ID", "").strip() or None
        ok = send_message(build_message(groups), chat_id=chat_id)
        if ok:
            logger.info(f"✅ 為替シグナル通知（{len(groups)}ペア）: "
                        + " / ".join(g["name"] for g in groups))
        return bool(ok)
    except Exception:
        logger.error("為替シグナルの検出に失敗しました", exc_info=True)
        return False


if __name__ == "__main__":
    import io, sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    gs = detect()
    print(build_message(gs) if gs else "条件を満たす通貨ペアはありません")
