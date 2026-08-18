"""
リスク計器盤（Step RG）— 恐怖指数・金利・ドルの一覧と「大きく動いた時」の通知

既存モジュールとの違い:
  sentiment_extreme … VIXとF&Gが「極値ゾーンに入った/戻った」瞬間を見る
  risk_sentiment    … 複数資産が同時に同じ方向を向いたか（リスクオン/オフ）を見る
  risk_gauges(本体) … 恐怖指数を横並びで一覧し、平常時と比べて
                      「今日いつもより大きく動いた」計器を拾う
  役割が重ならないよう、ここでは水準判定ではなく“変化の大きさ”だけを扱う。

しきい値の決め方（ここが肝）:
  「VIXが5%動いたら通知」のような固定値は使わない。
  VIXは平常時でも日々5%動くが、MOVE指数やドル指数が5%動くのは異常事態で、
  同じ数字を当てても意味が違ってしまう。
  そこで各計器の過去1年の「1日の変化率の絶対値」を集め、その90パーセンタイルを
  基準にする。つまり「その計器にとって、年に約25日しか起きない大きさ」を
  超えたときだけ動いたとみなす。計器ごとの性格の違いを自動で吸収できる。

run() → 計器盤データ（レポート用）
run_gauge_alert() → 大きく動いた計器があれば通知（1セッション1回）
"""
import json
import os
import re
import ssl
import statistics
import traceback
import urllib.request
from datetime import datetime

from src.utils import setup_logger, BASE_DIR, get_jst_now

logger = setup_logger("risk_gauges")

_STATE_FILE = BASE_DIR / "data" / "risk_gauge_state.json"

# 計器の定義: (シンボル, 表示名, グループ, 単位, 上昇は危険か)
# 「上昇は危険か」を持つのは、色や矢印の意味が計器で逆になるため。
# VIXは上昇＝危険だが、株価やF&Gは上昇＝安心。ここを取り違えると
# 通知の色分けが嘘になる（実際にVIXで一度やらかしている）。
_GAUGES = [
    # ── 恐怖指数（株のボラティリティ）─────────────────────
    ("^VIX",    "VIX（米国恐怖指数）",   "vol",  "",  True),
    ("^VIX1D",  "VIX1D（当日物）",       "vol",  "",  True),
    ("^VIX9D",  "VIX9D（9日先）",        "vol",  "",  True),
    ("^VIX3M",  "VIX3M（3ヶ月先）",      "vol",  "",  True),
    ("^VVIX",   "VVIX（VIXの変動率）",   "vol",  "",  True),
    ("^VXN",    "VXN（NASDAQ版）",       "vol",  "",  True),
    ("^VXD",    "VXD（ダウ版）",         "vol",  "",  True),
    ("^SKEW",   "SKEW（暴落警戒度）",     "vol",  "",  True),
    ("NIKKEI_VI", "日経VI（日本版）",     "vol",  "",  True),
    # ── 株以外のボラティリティ ────────────────────────
    ("^MOVE",   "MOVE（米国債の変動率）", "vol2", "",  True),
    ("^OVX",    "OVX（原油の変動率）",    "vol2", "",  True),
    ("^GVZ",    "GVZ（金の変動率）",      "vol2", "",  True),
    # ── 金利 ──────────────────────────────────────
    ("^IRX",    "米3ヶ月金利",            "rate", "%", None),
    ("2YY=F",   "米2年金利",              "rate", "%", None),
    ("^FVX",    "米5年金利",              "rate", "%", None),
    ("^TNX",    "米10年金利",             "rate", "%", None),
    ("^TYX",    "米30年金利",             "rate", "%", None),
    # ── 通貨 ──────────────────────────────────────
    ("DX-Y.NYB", "ドル指数（DXY）",       "fx",   "",  None),
    ("USDJPY=X", "ドル円",                "fx",   "円", None),
]

_GROUP_JA = {
    "vol":  "😱 恐怖指数（株）",
    "vol2": "📉 債券・商品のボラティリティ",
    "rate": "🏦 金利",
    "fx":   "💵 通貨",
    "jgb":  "🇯🇵 日本国債利回り",
    "misc": "🧭 その他の温度計",
}

# 過去1年の変化率のうち、この順位を超えたら「大きく動いた」とみなす。
# 0.90 = 年に約25日しか起きない大きさ。これ以上緩めると毎日鳴る。
_PCTL = 0.90
# 統計だけに任せると、凪の期間に基準が下がりすぎて些細な動きで鳴る。
# どの計器でも最低これだけは動いていることを条件にする。
_MIN_MOVE_PCT = 1.5
# 過去データがこの日数に満たない計器は、基準を作れないので判定しない
_MIN_HISTORY = 60


def _pctl(vals: list, q: float) -> float:
    """パーセンタイル（numpy不要の素朴な実装）。"""
    if not vals:
        return 0.0
    s = sorted(vals)
    i = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return s[i]


def _fetch_series(sym: str) -> list | None:
    """終値の系列を新しい順ではなく古い順で返す。"""
    if sym == "NIKKEI_VI":
        return _fetch_nikkei_vi_series()
    try:
        import yfinance as yf
        h = yf.Ticker(sym).history(period="1y", auto_adjust=True)
        if h is None or h.empty or "Close" not in h:
            return None
        return [float(x) for x in h["Close"].dropna().tolist()]
    except Exception:
        logger.debug(traceback.format_exc())
        return None


def _fetch_nikkei_vi_series() -> list | None:
    """
    日経VIはYahooに無いため、日経公式のCSVを直接読んで履歴ごと取る。

    既存の _fetch_nikkei_vi() は最新値と前日値しか返さないため、
    それだけでは「この計器にとって大きな動きか」を判定する母数が作れない。
    しきい値を勘で置かずに済ませるため、ここでは履歴を自前で取得する。
    """
    url = "https://indexes.nikkei.co.jp/nkave/historical/nikkei_stock_average_vi_daily_jp.csv"
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        text = urllib.request.urlopen(req, context=ctx, timeout=25).read().decode(
            "cp932", errors="replace")
        vals = []
        for line in text.split("\n"):
            # 日経のCSVは各値が引用符で囲まれている（"2023/01/04","20.19",...）
            cells = [c.strip().strip('"') for c in line.strip().split(",")]
            if len(cells) < 2 or not re.match(r"^\d{4}/\d{1,2}/\d{1,2}$", cells[0]):
                continue
            try:
                vals.append(float(cells[1]))
            except ValueError:
                continue
        if len(vals) >= 2:
            return vals[-260:]            # 直近1年ぶん
    except Exception:
        logger.error("日経VIの履歴を取得できませんでした", exc_info=True)

    # 履歴が駄目でも、最新値と前日値だけは既存処理から拾って表示はする
    # （判定はできないが、一覧から消えてしまう方が不便なため）
    try:
        from src.fetch_prices import _fetch_nikkei_vi
        d = _fetch_nikkei_vi() or {}
        latest, prev = d.get("latest"), d.get("prev_close")
        if latest is not None and prev is not None:
            return [float(prev), float(latest)]
    except Exception:
        logger.debug(traceback.format_exc())
    return None


def _fetch_jgb() -> dict:
    """
    日本国債の利回りを財務省の公表CSVから取る。

    Yahooに日本国債の系列が無いため、一次情報である財務省のデータを直接読む。
    和暦（R8.8.3 = 令和8年8月3日）とShift-JISという癖があるので変換する。
    """
    # 財務省は2種類のCSVを出しており、用途が違うので両方使う。
    #   jgbcm.csv      … 直近10日ほど。最新の値はこちらでないと取れない
    #   data/jgbcm_all … 全期間(1.1MB)。ただし月次更新なので最新値は古い
    # 最新値は前者、しきい値の母数は後者、と役割を分ける。
    # 片方だけだと「新しいが判定できない」か「判定できるが古い」になる。
    _BASE = "https://www.mof.go.jp/jgbs/reference/interest_rate/"

    def _get(u: str) -> str | None:
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            return urllib.request.urlopen(req, context=ctx, timeout=30).read().decode(
                "cp932", errors="replace")
        except Exception:
            logger.error(f"国債金利CSVを取得できませんでした: {u}", exc_info=True)
            return None

    recent = _get(_BASE + "jgbcm.csv")
    history = _get(_BASE + "data/jgbcm_all.csv")
    text = recent or history
    if not text:
        return {"available": False}

    def _rows(t: str) -> list:
        return [r for r in t.split("\n") if re.match(r"^[RH]\d+\.\d+\.\d+,", r.strip())]

    rows = _rows(text)
    if len(rows) < 2:
        return {"available": False}

    header = None
    for line in text.split("\n"):
        if line.startswith("基準日") or "1年" in line and "10年" in line:
            header = [c.strip() for c in line.split(",")]
            break
    if not header:
        return {"available": False}

    want = {"2年": None, "5年": None, "10年": None, "30年": None}
    for k in want:
        if k in header:
            want[k] = header.index(k)

    def _parse(row: str) -> dict:
        cells = row.strip().split(",")
        out = {}
        for k, idx in want.items():
            if idx is None or idx >= len(cells):
                continue
            try:
                out[k] = float(cells[idx])
            except ValueError:
                pass
        return out

    latest_row, prev_row = _parse(rows[-1]), _parse(rows[-2])

    # 年限ごとの履歴を作り、他の計器と同じ統計しきい値を求める。
    # 金利は数字の桁が小さく、固定の%しきい値では判定が歪むため必須。
    # 履歴は全期間ファイル側から取る（最新値ファイルには10日分しか無い）。
    hist_rows = _rows(history) if history else rows
    series = {k: [] for k in want}
    for row in hist_rows[-260:]:
        parsed = _parse(row)
        for k, v in parsed.items():
            series[k].append(v)
    # 和暦を西暦に直す（R=令和は2018年が元年の前年）
    era = rows[-1].split(",")[0]
    m = re.match(r"^([RH])(\d+)\.(\d+)\.(\d+)$", era)
    date_str = era
    if m:
        base = 2018 if m.group(1) == "R" else 1988
        date_str = f"{base + int(m.group(2))}-{int(m.group(3)):02d}-{int(m.group(4)):02d}"

    gauges = []
    for k, v in latest_row.items():
        p = prev_row.get(k)
        chg = (v - p) if p is not None else None
        pct = round((v - p) / p * 100, 2) if p else None
        st = _stats_from_series(series.get(k) or [])
        gauges.append({
            "symbol": f"JGB{k}", "name": f"日本{k}国債", "group": "jgb",
            "unit": "%", "up_is_bad": None,
            "value": v, "prev": p,
            "change": round(chg, 3) if chg is not None else None,
            # 金利は「%が何%動いた」より「何ベーシスポイント動いた」で見るのが実務
            "change_bp": round(chg * 100, 1) if chg is not None else None,
            "change_pct": pct,
            "threshold": st["threshold"], "typical": st["typical"],
            "big": bool(st["threshold"] and pct is not None
                        and abs(pct) >= st["threshold"]),
        })
    return {"available": True, "date": date_str, "gauges": gauges}


def _stats_from_series(vals: list) -> dict:
    """
    系列から「この計器にとっての大きな動き」の目安を作る。
    yfinance系と同じ基準を使い回すことで、出所が違っても判定がぶれないようにする。
    vals は古い順。
    """
    daily = [abs((b - a) / a * 100) for a, b in zip(vals, vals[1:]) if a]
    if len(daily) < _MIN_HISTORY:
        return {"threshold": None, "typical": None}
    return {"threshold": round(max(_pctl(daily, _PCTL), _MIN_MOVE_PCT), 2),
            "typical": round(statistics.median(daily), 2)}


def _fetch_crypto_fng() -> dict | None:
    """
    暗号資産の恐怖・強欲指数（alternative.me・無料/キー不要）。
    1年ぶん取るのは、他の計器と同じ統計しきい値を作るため。
    2件だけだと「大きく動いたか」を判定できず、永久に通知されない計器になる。
    """
    try:
        req = urllib.request.Request("https://api.alternative.me/fng/?limit=365",
                                     headers={"User-Agent": "Mozilla/5.0"})
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        d = json.loads(urllib.request.urlopen(req, context=ctx, timeout=20).read())
        rows = d.get("data") or []
        if len(rows) < 2:
            return None
        # APIは新しい順で返すので、古い順に直してから統計を取る
        series = [float(r["value"]) for r in reversed(rows) if r.get("value")]
        cur, prev = series[-1], series[-2]
        st = _stats_from_series(series)
        pct = round((cur - prev) / prev * 100, 2) if prev else None
        return {
            "symbol": "CRYPTO_FNG", "name": "暗号資産 恐怖&強欲指数",
            "group": "misc", "unit": "", "up_is_bad": False,
            "value": cur, "prev": prev, "change": round(cur - prev, 1),
            "change_pct": pct,
            "label": rows[0].get("value_classification", ""),
            "threshold": st["threshold"], "typical": st["typical"],
            "big": bool(st["threshold"] and pct is not None
                        and abs(pct) >= st["threshold"]),
        }
    except Exception:
        logger.error("暗号資産F&Gを取得できませんでした", exc_info=True)
        return None


def _build_gauge(sym: str, name: str, group: str, unit: str, up_bad) -> dict | None:
    s = _fetch_series(sym)
    if not s or len(s) < 2:
        return None
    cur, prev = s[-1], s[-2]
    if not prev:
        return None
    chg_pct = (cur - prev) / prev * 100

    # 過去1年の1日変化率から、この計器にとっての「大きな動き」を求める
    daily = []
    for a, b in zip(s, s[1:]):
        if a:
            daily.append(abs((b - a) / a * 100))
    threshold = None
    if len(daily) >= _MIN_HISTORY:
        threshold = max(_pctl(daily, _PCTL), _MIN_MOVE_PCT)

    return {
        "symbol": sym, "name": name, "group": group, "unit": unit,
        "up_is_bad": up_bad,
        "value": round(cur, 2), "prev": round(prev, 2),
        "change": round(cur - prev, 2),
        "change_pct": round(chg_pct, 2),
        "threshold": round(threshold, 2) if threshold else None,
        "typical": round(statistics.median(daily), 2) if daily else None,
        "big": bool(threshold and abs(chg_pct) >= threshold),
    }


def run() -> dict:
    """全計器を取得して一覧にまとめる。"""
    logger.info("=== リスク計器盤 ===")
    gauges = []
    for sym, name, group, unit, up_bad in _GAUGES:
        try:
            g = _build_gauge(sym, name, group, unit, up_bad)
            if g:
                gauges.append(g)
            else:
                logger.info(f"取得できず（この計器は表示しません）: {name}")
        except Exception:
            logger.error(f"{name} の取得に失敗しました", exc_info=True)

    # VVIX/VIX レシオ（VIX自体の不安定さ。急騰は市場が先を読めていない合図）
    vix = next((g for g in gauges if g["symbol"] == "^VIX"), None)
    vvix = next((g for g in gauges if g["symbol"] == "^VVIX"), None)
    if vix and vvix and vix["value"]:
        r_now = vvix["value"] / vix["value"]
        r_prev = (vvix["prev"] / vix["prev"]) if vix["prev"] else None
        gauges.append({
            "symbol": "VVIX_VIX", "name": "VVIX/VIX レシオ", "group": "vol",
            "unit": "", "up_is_bad": True,
            "value": round(r_now, 2),
            "prev": round(r_prev, 2) if r_prev else None,
            "change": round(r_now - r_prev, 2) if r_prev else None,
            "change_pct": round((r_now - r_prev) / r_prev * 100, 2) if r_prev else None,
            "threshold": None, "big": False,
        })

    cf = _fetch_crypto_fng()
    if cf:
        gauges.append(cf)

    jgb = _fetch_jgb()
    if jgb.get("available"):
        gauges += jgb["gauges"]

    big = [g for g in gauges if g.get("big")]
    logger.info(f"✅ 計器 {len(gauges)}件 / 大きく動いた {len(big)}件")
    return {
        "available": bool(gauges),
        "generated_at": get_jst_now().strftime("%Y-%m-%d %H:%M"),
        "gauges": gauges,
        "big_moves": big,
        "jgb_date": jgb.get("date"),
    }


# ── 通知 ───────────────────────────────────────────────────────
def _session_key(now=None) -> str:
    n = now or get_jst_now()
    d = n.date()
    if n.hour < 6:
        from datetime import timedelta
        d = d - timedelta(days=1)
    return d.isoformat()


def _filter_new(big: list) -> list:
    """同じ計器の同じ方向は1セッション1回だけ。"""
    skey = _session_key()
    try:
        st = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        st = {}

    kept = []
    for g in big:
        direction = "up" if (g.get("change_pct") or 0) > 0 else "down"
        key = f"{g['symbol']}:{direction}"
        rec = st.get(key)
        if isinstance(rec, dict) and rec.get("session") == skey:
            continue
        kept.append(g)
        st[key] = {"session": skey, "ts": datetime.now().isoformat()}

    if kept:
        st = {k: v for k, v in st.items()
              if isinstance(v, dict) and v.get("session") == skey}
        try:
            _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            _STATE_FILE.write_text(json.dumps(st, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
        except Exception:
            logger.error("状態の保存に失敗しました", exc_info=True)
    return kept


def _arrow(g: dict) -> str:
    """
    上昇が危険な計器（VIX等）と、上昇が安心な計器（F&G等）で色を変える。
    金利や通貨は良し悪しが文脈依存なので中立の矢印にする。
    """
    up = (g.get("change_pct") or 0) > 0
    bad = g.get("up_is_bad")
    if bad is None:
        return "🔺" if up else "🔻"
    if bad:
        return "🔴↑" if up else "🟢↓"
    return "🟢↑" if up else "🔴↓"


# ── 意味づけ ───────────────────────────────────────────────────
# 数字だけ出しても「で、どういうこと？」で終わってしまう。
# 各指標が何を測っていて、上がった/下がったが何を意味するかを言葉にする。
# (指標: (何を測るか, 上がった時の意味, 下がった時の意味))
_MEANING = {
    "^VIX":   ("米国株の今後30日の荒れ具合の予想",
               "投資家の不安が増えた。株が下げやすい空気",
               "不安が和らいだ。落ち着きを取り戻しつつある"),
    "^VIX1D": ("今日1日のうちの急変への警戒度",
               "今日中に大きく動くと身構えている。指標発表や要人発言の直前に上がりやすい",
               "今日は大きな波乱を想定していない"),
    "^VIX9D": ("目先2週間ほどの荒れ具合の予想",
               "近いうちの波乱を警戒している",
               "目先の警戒が解けてきた"),
    "^VIX3M": ("3ヶ月先までの荒れ具合の予想",
               "もっと先まで不安が続くと見ている",
               "中期的な不安が薄れてきた"),
    "^VVIX":  ("恐怖指数そのものの不安定さ",
               "先行きが読めない状態。相場観が定まっていない",
               "見通しが落ち着いてきた"),
    "^VXN":   ("ハイテク株(NASDAQ)の荒れ具合",
               "ハイテク株中心に不安が強まった",
               "ハイテク株の不安が和らいだ"),
    "^VXD":   ("ダウ(大型株)の荒れ具合",
               "大型株にも不安が広がった",
               "大型株の不安が和らいだ"),
    "^SKEW":  ("暴落に備えた保険がどれだけ買われているか",
               "急落への備えが増えた。プロが万一に保険をかけている",
               "急落への警戒が薄れた"),
    "NIKKEI_VI": ("日本株の今後30日の荒れ具合の予想",
                  "日本株への不安が増えた",
                  "日本株の不安が和らいだ"),
    "^MOVE":  ("米国債市場の荒れ具合",
               "金融政策の見通しが揺れている。株にも波及しやすい",
               "金利の見通しが落ち着いてきた"),
    "^OVX":   ("原油価格の荒れ具合",
               "エネルギー情勢への警戒。地政学リスクが意識されやすい",
               "エネルギー面の警戒が和らいだ"),
    "^GVZ":   ("金価格の荒れ具合",
               "安全資産の金にも値動きの荒さが出てきた",
               "金相場が落ち着いてきた"),
    "^IRX":   ("米国の3ヶ月金利（政策金利に近い）",
               "利下げ観測が後退した", "利下げ観測が強まった"),
    "2YY=F":  ("米国の2年金利（政策金利の見通しを映す）",
               "利下げ観測が後退した", "利下げ観測が強まった"),
    "^FVX":   ("米国の5年金利", "金利上昇。株の重荷になりやすい", "金利低下。株の支えになりやすい"),
    "^TNX":   ("米国の10年金利（世界の金利の基準）",
               "金利上昇。ハイテク株や高PER銘柄には逆風。円安要因にもなる",
               "金利低下。株の支えになるが、景気後退懸念が理由なら注意"),
    "^TYX":   ("米国の30年金利（長期の期待を映す）",
               "長期の金利上昇。財政やインフレへの懸念が背景にあることも",
               "長期の金利低下"),
    "DX-Y.NYB": ("ドルの総合的な強さ",
                 "ドル高。新興国や商品市況には逆風、円安方向に効きやすい",
                 "ドル安。新興国や商品市況には追い風"),
    "USDJPY=X": ("ドル円の為替レート",
                 "円安。輸出企業の追い風で日経平均にはプラスになりやすい",
                 "円高。輸出企業には逆風で日経平均にはマイナスになりやすい"),
    "CRYPTO_FNG": ("暗号資産市場の投資家心理",
                   "強気に傾いた。リスクを取る動きが戻っている",
                   "弱気に傾いた。リスクを避ける動きが強い"),
}


def _meaning(g: dict) -> str:
    """その計器が動いたことの意味を1行で返す。"""
    sym = g.get("symbol", "")
    if sym.startswith("JGB"):
        up = (g.get("change_pct") or 0) > 0
        return ("日本の金利上昇。日銀の政策変更が意識されると円高・株安に効きやすい"
                if up else "日本の金利低下。円安方向に効きやすい")
    m = _MEANING.get(sym)
    if not m:
        return ""
    return m[1] if (g.get("change_pct") or 0) > 0 else m[2]


def _what_is(g: dict) -> str:
    sym = g.get("symbol", "")
    if sym.startswith("JGB"):
        return "日本国債の利回り"
    m = _MEANING.get(sym)
    return m[0] if m else ""


def _term_structure(gauges: list) -> str | None:
    """
    VIXの期間構造を読む。

    通常は先の方が不透明なので VIX9D < VIX < VIX3M と右肩上がりになる。
    これが逆転して目先(VIX9D)が3ヶ月先(VIX3M)を上回るのは、
    「今まさに何かが起きている」状態で、歴史的に相場の急変局面で現れる。
    数字を並べるだけでは見えない情報なので、明示的に判定する。
    """
    def val(sym):
        g = next((x for x in gauges if x["symbol"] == sym), None)
        return g["value"] if g else None

    s, m, l = val("^VIX9D"), val("^VIX"), val("^VIX3M")
    if s is None or m is None or l is None:
        return None
    if s > l:
        return ("⚠️ 目先の警戒が先々より強い状態（期間構造の逆転）。"
                "相場が荒れている時に現れる形で、当面は値動きが大きくなりやすい。")
    if s < m < l:
        return "✅ 恐怖指数は通常の並び（目先＜先々）。相場は平常運転の範囲。"
    return None


def _overall_read(gauges: list) -> list:
    """
    計器全体から今の相場の傾きを読む。

    1つの指標だけでは個別の材料かもしれないが、
    「不安↑ × 金利↓ × 円高」のように複数が同じ話をしているなら、
    市場全体の資金の向きが変わったと読める。
    ここでは数を数えて、どちらに傾いているかだけを述べる。
    断定を避けるのは、この判定が相関の観察であって予測ではないため。
    """
    def g(sym):
        return next((x for x in gauges if x["symbol"] == sym), None)

    risk_off, risk_on = [], []

    vix = g("^VIX")
    if vix and vix.get("change_pct") is not None:
        (risk_off if vix["change_pct"] > 0 else risk_on).append(
            f"恐怖指数{'上昇' if vix['change_pct'] > 0 else '低下'}")

    tnx = g("^TNX")
    if tnx and tnx.get("change_pct") is not None:
        # 金利低下は「安全資産の債券が買われた」＝リスクオフの目印になりやすい
        (risk_off if tnx["change_pct"] < 0 else risk_on).append(
            f"米長期金利{'低下' if tnx['change_pct'] < 0 else '上昇'}")

    fx = g("USDJPY=X")
    if fx and fx.get("change_pct") is not None:
        # 円は有事に買われやすい。円高＝リスクオフの目印
        (risk_off if fx["change_pct"] < 0 else risk_on).append(
            f"{'円高' if fx['change_pct'] < 0 else '円安'}")

    skew = g("^SKEW")
    if skew and skew.get("change_pct") is not None and abs(skew["change_pct"]) > 1:
        if skew["change_pct"] > 0:
            risk_off.append("暴落への備え増加")

    out = []
    if len(risk_off) >= 3:
        out.append(f"🔴 *全体としてはリスクを避ける動き*（{'・'.join(risk_off)}）")
    elif len(risk_on) >= 3:
        out.append(f"🟢 *全体としてはリスクを取る動き*（{'・'.join(risk_on)}）")
    elif risk_off or risk_on:
        parts = []
        if risk_off:
            parts.append("慎重: " + "・".join(risk_off))
        if risk_on:
            parts.append("前向き: " + "・".join(risk_on))
        out.append(f"⚖️ *方向感は割れています*（{' ／ '.join(parts)}）")

    ts = _term_structure(gauges)
    if ts:
        out.append(ts)
    return out


def _headline(big: list, gauges: list) -> str:
    """
    最初の1行で「今日は何が起きたのか」を言い切る。
    数字を読む前に結論が分かる形にしないと、通知を開いた瞬間に読む気が失せる。
    """
    if not big:
        return "⚡ *大きく動いた指標*"
    lead = max(big, key=lambda x: abs(x.get("change_pct") or 0))
    up = (lead.get("change_pct") or 0) > 0
    name = lead["name"].split("（")[0]
    verb = "急上昇" if up else "急低下"
    return f"⚡ *{name}が{verb}* — いつもより大きな動きが{len(big)}件"


def build_message(big: list, all_gauges: list = None) -> str:
    gauges = all_gauges or big
    lines = [_headline(big, gauges), "━━━━━━━━━━━━━━", ""]

    # ── ① まず全体像（個々の数字より先に結論を置く）──────────────
    read = _overall_read(gauges)
    if read:
        lines.append("📖 *ひとことで言うと*")
        lines += read
        lines.append("")

    # ── ② 動いた指標を、意味とセットで ────────────────────────
    lines.append("🔍 *大きく動いた指標*")
    lines.append("")
    for g in sorted(big, key=lambda x: -abs(x.get("change_pct") or 0)):
        pct = g.get("change_pct")
        typ = g.get("typical")
        th = g.get("threshold")
        lines.append(f"{_arrow(g)} *{g['name']}*　{g['value']}{g.get('unit','')}"
                     f"（{pct:+.2f}%）")

        what = _what_is(g)
        if what:
            lines.append(f"　📌 これは何？　{what}")
        mean = _meaning(g)
        if mean:
            lines.append(f"　💭 どういうこと？　{mean}")
        if th and typ is not None:
            lines.append(f"　📊 どれくらい大きい？　普段は{typ:.1f}%程度の動き"
                         f"（目安{th:.1f}%を超えました）")
        if g.get("change_bp") is not None:
            lines.append(f"　（{g['change_bp']:+.1f}ベーシスポイント）")
        lines.append("")

    # ── ③ 主要な指標の現在地（動いた指標だけでは状況が分からない）──
    if all_gauges:
        ref = [g for g in all_gauges
               if g["symbol"] in ("^VIX", "^TNX", "DX-Y.NYB", "USDJPY=X", "NIKKEI_VI")]
        if ref:
            lines.append("📊 *いまの主要指標*")
            for g in ref:
                pct = g.get("change_pct")
                lines.append(f"　{g['name'].split('（')[0]}: "
                             f"{g['value']}{g.get('unit','')}"
                             f"（{pct:+.2f}%）" if pct is not None
                             else f"　{g['name']}: {g['value']}")
            lines.append("")

    lines.append("ℹ️ 「大きく動いた」の基準は、各指標の過去1年の値動きから"
                 "自動計算しています（年に約25日しか起きない大きさ）。"
                 "指標ごとに普段の動き幅が違うため、同じ%では比べられません。")
    return "\n".join(lines).strip()[:4000]


def run_gauge_alert() -> bool:
    """monitor_run.py から呼ぶ。大きく動いた計器があれば1通にまとめて送る。"""
    try:
        r = run()
        big = r.get("big_moves") or []
        if not big:
            logger.info("リスク計器盤: 大きく動いた指標なし")
            return False

        big = _filter_new(big)
        if not big:
            return False

        from src.notify_telegram import send_message
        # 恐怖指数・金利・為替はマクロの話なのでFXグループへ。
        # 未設定ならメイン側に落として通知消失を防ぐ。
        chat_id = os.getenv("TELEGRAM_FX_CHAT_ID", "").strip() or None
        ok = send_message(build_message(big, r.get("gauges")), chat_id=chat_id)
        if ok:
            logger.info("✅ 大きく動いた指標を通知: "
                        + " / ".join(g["name"] for g in big))
        return bool(ok)
    except Exception:
        logger.error("リスク計器盤の処理に失敗しました", exc_info=True)
        return False


if __name__ == "__main__":
    import io, sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    r = run()
    for grp in ("vol", "vol2", "rate", "jgb", "fx", "misc"):
        gs = [g for g in r["gauges"] if g.get("group") == grp]
        if not gs:
            continue
        print(f"\n{_GROUP_JA.get(grp, grp)}")
        for g in gs:
            mark = " ⚡大きく動いた" if g.get("big") else ""
            th = f" (目安{g['threshold']}%)" if g.get("threshold") else ""
            print(f"  {g['name']:24} {g['value']:>10}  "
                  f"{g.get('change_pct', 0):+6.2f}%{th}{mark}")
    print(f"\n大きく動いた: {len(r['big_moves'])}件")
