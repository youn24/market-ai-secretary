"""
空売り残高アナライザー（踏み上げ候補の発見）
karauri.net（空売り残高情報・無料）から機関投資家の空売りポジションを取得する。

金融庁ルールで発行済株式の0.5%以上の空売りは報告義務がある。
karauri.net はこの報告データを銘柄別・機関別に集計している。

需給分析での意味：
  - 空売り残高が多い  → いずれ買い戻す必要がある＝将来の買い圧力（踏み上げ候補）
  - 空売り残が減少中  → 今まさに買い戻しが進行＝上昇の燃料
  - 空売り残が増加中  → 機関が弱気＝下押し圧力

⚠️ 空売り残高は需給材料のひとつ。多いから必ず上がるわけではない
   （業績悪化で売られ続けることもある）。
"""
import re
import time

import requests

from src.utils import setup_logger, BASE_DIR

logger = setup_logger("short_selling")

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ja",
}


def _load_watchlist():
    import json
    path = BASE_DIR / "data" / "watchlist.json"
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for s in data.get("stocks", []):
            if s.get("symbol"):
                out.append((s["symbol"].split(".")[0], s.get("name", "")))
    except Exception as e:
        logger.warning(f"watchlist読み込み失敗: {e}")
    return out


def fetch_short_interest(code: str) -> dict:
    """
    1銘柄の空売り残高を取得・集計。
    karauri.net のテーブルは [日付, 機関名, 残高比率, 前回比, 残株数, 株数増減] の時系列。
    各機関の最新エントリを採り、比率>0を「現在の空売り」として集計する。
    """
    code = str(code).split(".")[0]
    url = f"https://karauri.net/{code}/"
    try:
        r = requests.get(url, headers=_HEADERS, timeout=12)
        if r.status_code != 200:
            return {"available": False}
        txt = r.content.decode("utf-8", errors="replace")
    except Exception as e:
        logger.debug(f"karauri取得失敗[{code}]: {e}")
        return {"available": False}

    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", txt, re.DOTALL)
    # 機関ごとに最新エントリを保持
    latest: dict[str, dict] = {}
    for row in rows:
        cells = [re.sub(r"<[^>]+>", "", c).strip()
                 for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)]
        cells = [c for c in cells if c]
        if len(cells) < 4:
            continue
        date = cells[0]
        # 日付形式 YYYY/MM/DD の行のみ
        if not re.match(r"\d{4}/\d{1,2}/\d{1,2}", date):
            continue
        inst = cells[1]
        ratio_m = re.search(r"(\d+\.\d+)", cells[2])
        diff_m  = re.search(r"([+\-]?\d+\.\d+)", cells[3])
        if not ratio_m:
            continue
        ratio = float(ratio_m.group(1))
        diff  = float(diff_m.group(1)) if diff_m else 0.0
        # 機関ごとに最も新しい日付を採用
        if inst not in latest or date > latest[inst]["date"]:
            latest[inst] = {"date": date, "ratio": ratio, "diff": diff}

    # 現在アクティブな空売り（比率>0）を集計
    active = {k: v for k, v in latest.items() if v["ratio"] > 0}
    total_ratio = round(sum(v["ratio"] for v in active.values()), 2)
    n_inst = len(active)
    # トレンド：アクティブ機関の前回比合計（プラス=売り増し, マイナス=買い戻し）
    net_diff = round(sum(v["diff"] for v in active.values()), 2)
    if net_diff <= -0.15:
        trend = "decreasing"   # 買い戻し進行（はっきり減少）
    elif net_diff >= 0.15:
        trend = "increasing"   # 売り増し（はっきり増加）
    else:
        trend = "flat"         # 横ばい

    # 上位機関（比率順）
    top = sorted(active.items(), key=lambda x: x[1]["ratio"], reverse=True)[:3]
    top_inst = [{"name": k, "ratio": v["ratio"], "diff": v["diff"]} for k, v in top]

    return {
        "available": True,
        "code": code,
        "total_ratio": total_ratio,
        "n_institutions": n_inst,
        "net_diff": net_diff,
        "trend": trend,
        "top_institutions": top_inst,
    }


def judge_squeeze(si: dict) -> dict:
    """空売り残高から踏み上げ/下押しを判定"""
    if not si.get("available") or si["total_ratio"] <= 0:
        return {"sig": "none", "emoji": "", "name": "", "desc": "空売り残高なし"}
    tr = si["total_ratio"]
    trend = si["trend"]

    if tr >= 1.5 and trend == "decreasing":
        return {"sig": "bull", "emoji": "🔥", "name": "踏み上げ進行中",
                "desc": f"空売り残{tr}%が買い戻され中。急騰（踏み上げ）の燃料が点火"}
    if tr >= 1.5 and trend == "increasing":
        return {"sig": "warn", "emoji": "🐻", "name": "機関が売り増し",
                "desc": f"空売り残{tr}%が増加中。大口が弱気で下押し圧力"}
    if tr >= 1.5:
        return {"sig": "bull", "emoji": "🎯", "name": "踏み上げ候補",
                "desc": f"空売り残{tr}%と高水準。将来の買い戻し圧力が蓄積（踏み上げ余地）"}
    if tr >= 0.5:
        return {"sig": "neutral", "emoji": "📍", "name": "空売りあり",
                "desc": f"空売り残{tr}%。中程度の買い戻し余地"}
    return {"sig": "neutral", "emoji": "", "name": "", "desc": f"空売り残{tr}%（少ない）"}


def analyze_watchlist() -> dict:
    """ウォッチリスト全銘柄の空売り残高を分析"""
    results = []
    for code, name in _load_watchlist():
        si = fetch_short_interest(code)
        if si.get("available") and si["total_ratio"] > 0:
            si["name"] = name
            si["squeeze"] = judge_squeeze(si)
            results.append(si)
        time.sleep(0.3)
    # 空売り残高の多い順
    results.sort(key=lambda x: x["total_ratio"], reverse=True)
    return {"available": len(results) > 0, "results": results, "count": len(results)}


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        si = fetch_short_interest(sys.argv[1])
        si["squeeze"] = judge_squeeze(si)
        lines = [f"=== {sys.argv[1]} 空売り残高 ==="]
        if si.get("available"):
            lines.append(f"合計残高比率: {si['total_ratio']}% / 機関数: {si['n_institutions']} / トレンド: {si['trend']}")
            lines.append(f"判定: {si['squeeze']['emoji']} {si['squeeze']['name']} - {si['squeeze']['desc']}")
            for t in si["top_institutions"]:
                lines.append(f"  {t['name']}: {t['ratio']}% ({t['diff']:+.2f})")
        else:
            lines.append("データなし")
        text = "\n".join(lines)
    else:
        res = analyze_watchlist()
        lines = [f"=== ウォッチリスト空売り残高ランキング（{res.get('count',0)}銘柄）==="]
        for r in res.get("results", []):
            sq = r["squeeze"]
            lines.append(f"[{r['code']}] {r['name']}: {r['total_ratio']}% {sq['emoji']}{sq['name']} (機関{r['n_institutions']})")
        text = "\n".join(lines)
    try:
        print(text)
    except UnicodeEncodeError:
        with open("ss_output.txt", "w", encoding="utf-8") as f:
            f.write(text)
        print("ss_output.txt に保存しました")
