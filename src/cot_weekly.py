"""
src/cot_weekly.py — CFTC 投機筋ポジション 週次レポート

CFTC（米商品先物取引委員会）が毎週金曜 15:30 ET に公表する
COT（Commitment of Traders）レポートから、投機筋（Leveraged Money）の
建玉を取得し、週に一度まとめて通知する。

  ・データ基準日は「火曜時点」、公表は「金曜」（＝3日遅れ）
  ・日本時間では土曜の早朝に出そろうので、土曜朝に配信する

読み方:
  ネット買い越し（+）… 投機筋がその資産の上昇に賭けている
  ネット売り越し（−）… 下落に賭けている
  ポジションが極端に偏ると「巻き戻し（反対売買）」が起きやすく、
  相場が急反転するきっかけになることがある ＝ 逆張りの目安として使われる

⚠️ 注意: 3日前の値であり、リアルタイムの需給ではない。
   「今どちらに偏っているか」を掴むための材料として扱う。
"""

import io
import zipfile
import traceback
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

from src.utils import setup_logger

logger = setup_logger("cot_weekly")

JST = timezone(timedelta(hours=9))
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
_URL = "https://www.cftc.gov/files/dea/history/fut_fin_txt_{year}.zip"

# (CFTC市場名の先頭一致, 表示名, 絵文字, 「買い越し」が意味する方向の説明)
MARKETS = [
    ("JAPANESE YEN",         "円",        "💴", "円高", "円安"),
    ("EURO FX",              "ユーロ",    "🇪🇺", "ユーロ高", "ユーロ安"),
    ("BRITISH POUND",        "ポンド",    "🇬🇧", "ポンド高", "ポンド安"),
    ("AUSTRALIAN DOLLAR",    "豪ドル",    "🇦🇺", "豪ドル高", "豪ドル安"),
    ("NIKKEI STOCK AVERAGE", "日経225",   "🗾", "上昇",   "下落"),
    ("E-MINI S&P 500",       "S&P500",    "🇺🇸", "上昇",   "下落"),
]

_WEEKS = 156          # 約3年ぶんを保持して「偏りの度合い」を測る


def _fetch_raw(weeks: int = _WEEKS) -> pd.DataFrame | None:
    """CFTCの金融先物COTを直近3年ぶん取得して結合する"""
    now = datetime.now(JST)
    dfs = []
    for year in (now.year, now.year - 1, now.year - 2):
        try:
            r = requests.get(_URL.format(year=year), timeout=60, headers=_HEADERS)
            if r.status_code != 200:
                continue
            with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
                with zf.open(zf.namelist()[0]) as f:
                    dfs.append(pd.read_csv(f, encoding="latin-1"))
        except Exception:
            logger.debug(traceback.format_exc())
    if not dfs:
        return None
    return pd.concat(dfs, ignore_index=True)


def _extract(df: pd.DataFrame, prefix: str) -> pd.DataFrame | None:
    """指定市場の投機筋（Leveraged Money）建玉を時系列で取り出す"""
    try:
        mask = df["Market_and_Exchange_Names"].str.upper().str.startswith(prefix.upper(), na=False)
        sub = df[mask][[
            "Report_Date_as_YYYY-MM-DD",
            "Lev_Money_Positions_Long_All",
            "Lev_Money_Positions_Short_All",
        ]].copy()
        if sub.empty:
            return None
        sub.columns = ["date", "long", "short"]
        for col in ("long", "short"):
            sub[col] = pd.to_numeric(sub[col], errors="coerce").fillna(0).astype(int)
        sub["net"] = sub["long"] - sub["short"]
        return (sub.drop_duplicates("date").sort_values("date")).tail(_WEEKS)
    except Exception:
        logger.debug(traceback.format_exc())
        return None


def _bias(pct: float) -> tuple:
    """
    「その市場自身の過去3年」と比べてどちらに傾いているかを返す。

    ※ 買い越し/売り越しの符号そのものではなく“相対的な傾き”を表す。
       S&P500のように投機筋が常に売り越し（ヘッジ）の市場もあるため、
       符号だけで強弱を語ると誤解を生む。
    """
    if pct >= 90:
        return "🔴", "過去3年で最も買い方向に傾斜（巻き戻し警戒）"
    if pct >= 75:
        return "🟠", "買い方向に強く傾斜"
    if pct >= 55:
        return "🔸", "やや買い方向"
    if pct > 45:
        return "⚪", "平常圏"
    if pct > 25:
        return "🔹", "やや売り方向"
    if pct > 10:
        return "🟢", "売り方向に強く傾斜"
    return "🟢", "過去3年で最も売り方向に傾斜（巻き戻し警戒）"


def run(*_args, **_kwargs) -> dict:
    """
    投機筋ポジションを取得して週次レポートを組み立てる。
    返り値: {available, report_date, items: [...], telegram_message}
    """
    result = {"available": False, "items": []}
    try:
        raw = _fetch_raw()
        if raw is None:
            logger.warning("CFTC: データ取得できず")
            return result

        items, report_date = [], ""
        for prefix, name, emoji, up_word, down_word in MARKETS:
            s = _extract(raw, prefix)
            if s is None or len(s) < 5:
                continue

            net   = s["net"].tolist()
            now_n = net[-1] / 1000.0                     # 千枚
            prev  = net[-2] / 1000.0 if len(net) > 1 else now_n
            chg   = now_n - prev

            lo, hi = min(net), max(net)
            pct = 50.0 if hi == lo else (net[-1] - lo) / (hi - lo) * 100
            mark, bias = _bias(pct)

            report_date = report_date or str(s["date"].iloc[-1])
            items.append({
                "name": name, "emoji": emoji, "mark": mark, "bias": bias,
                "net_k": now_n, "chg_k": chg, "pct": pct,
                "up_word": up_word, "down_word": down_word,
                "long_k": s["long"].iloc[-1] / 1000.0,
                "short_k": s["short"].iloc[-1] / 1000.0,
            })

        if not items:
            logger.warning("CFTC: 対象市場を抽出できず")
            return result

        result["items"]            = items
        result["report_date"]      = report_date
        result["available"]        = True
        result["telegram_message"] = build_message(items, report_date)
        logger.info(f"✅ 投機筋ポジション {len(items)}市場（基準日 {report_date}）")
        return result
    except Exception:
        logger.error("投機筋ポジション取得エラー")
        logger.debug(traceback.format_exc())
        return result


def build_message(items: list, report_date: str = "") -> str:
    """週次通知の本文（1行目＝スマホの通知バー）"""
    # 最も偏っている市場をタイトルに出す
    top = max(items, key=lambda x: abs(x["pct"] - 50))
    extreme = abs(top["pct"] - 50) >= 40
    if extreme:
        title = (f"📡 *投機筋ポジション週報* — "
                 f"{top['name']}が{top['bias']}")
    else:
        title = "📡 *投機筋ポジション週報*（CFTC建玉）"

    lines = [title,
             f"基準日 {report_date}（火曜時点・金曜公表）",
             "━━━━━━━━━━━━━━"]

    for it in items:
        arrow = "▲" if it["chg_k"] >= 0 else "▼"
        side  = "買い越し" if it["net_k"] >= 0 else "売り越し"
        lines += [
            "",
            f"{it['emoji']} *{it['name']}*　{it['mark']} {it['bias']}",
            f"　ネット{side} `{abs(it['net_k']):,.1f}千枚`"
            f"（前週比 {arrow}{abs(it['chg_k']):,.1f}）",
        ]
        # 極端なときだけ「巻き戻し」の含意を添える
        # （符号ではなく“過去3年と比べた傾き”で語る＝常時売り越しの市場でも正しくなる）
        if it["pct"] >= 90:
            lines.append(f"　→ 買い方向への傾きが過去3年で最大。"
                         f"利益確定が出ると{it['down_word']}に振れやすい。")
        elif it["pct"] <= 10:
            lines.append(f"　→ 売り方向への傾きが過去3年で最大。"
                         f"買い戻しが入ると{it['up_word']}に振れやすい。")

    lines.append("\n※投機筋＝ヘッジファンド等（Leveraged Money）の建玉。"
                 "火曜時点の値で3日遅れのため、今の需給そのものではありません。")
    return "\n".join(lines)


def run_weekly_report() -> bool:
    """週次ワークフローから呼ぶ。取得できたらTelegramへ1通送る。"""
    try:
        res = run()
        if not res.get("available"):
            logger.info("投機筋ポジション: 送信スキップ（データなし）")
            return False
        from src.notify_telegram import send_message
        ok = send_message(res["telegram_message"])
        if ok:
            logger.info("✅ 投機筋ポジション週報を送信")
        return bool(ok)
    except Exception:
        logger.error("投機筋ポジション週報エラー")
        logger.debug(traceback.format_exc())
        return False


if __name__ == "__main__":
    run_weekly_report()
