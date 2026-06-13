"""
TDnet 適時開示ウォッチャー
東証「適時開示情報閲覧サービス（TDnet）」から、ウォッチリスト銘柄の
開示（決算短信・自社株買い・上方修正・M&A 等）だけを抽出して通知する。

特徴：
  - 完全無料・APIキー不要（静的HTMLをスクレイピング）
  - ウォッチリスト26銘柄のみに絞るので通知が激減
  - 各開示に「時刻 + 種類アイコン + タイトル + PDFリンク」を付ける
  - 前営業日分のみ取得 → 同じ開示を翌日また通知しない

データ元：https://www.release.tdnet.info/inbs/I_list_001_YYYYMMDD.html
"""
import os
import re
import json
import time
from pathlib import Path
from datetime import datetime, timedelta

import requests

from src.utils import BASE_DIR, setup_logger, get_jst_now

logger = setup_logger("tdnet_watcher")

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ja,en;q=0.9",
}
_TDNET_BASE = "https://www.release.tdnet.info/inbs/"


# ── 開示種類の分類（重要度つき） ─────────────────────────────────
# 方向が曖昧な「業績予想の修正」は最後にニュートラル判定するため、
# まず明確にポジ/ネガと分かるキーワードを優先する。
_CATEGORY_RULES = [
    # (絵文字, ラベル, 重要度, キーワード群)
    ("📊", "決算",       "high",   ["決算短信", "四半期決算", "通期決算", "中間決算"]),
    ("💰", "自社株買い", "high",   ["自己株式取得", "自己株式の取得", "自社株買い"]),
    ("🗑", "自社株消却", "medium", ["自己株式の消却", "自己株式消却"]),
    ("🤝", "M&A・買収",  "high",   ["子会社化", "株式取得", "買収", "TOB", "公開買付", "経営統合", "合併"]),
    ("🤝", "資本業務提携", "medium", ["資本業務提携", "業務提携", "資本提携", "業務資本提携"]),
    ("✂️", "株式分割",   "medium", ["株式分割", "株式併合"]),
    ("📉", "希薄化注意", "medium", ["新株予約権", "第三者割当", "公募増資", "ストック・オプション", "ストックオプション"]),
    ("🚨", "要注意開示", "high",   ["特別調査委員会", "第三者委員会", "不適切", "上場廃止", "監理銘柄", "特設注意"]),
    ("📅", "月次速報",   "low",    ["月次", "月度"]),
    ("🏢", "IR・その他", "low",    ["説明会", "個人投資家", "Q&A", "補足説明", "動画"]),
]


def _classify(title: str) -> tuple[str, str, str]:
    """開示タイトルから (絵文字, ラベル, 重要度) を判定"""
    # 1) 明確にネガティブ（株価に下押し）
    if any(k in title for k in ["下方修正", "下振れ", "減額", "減配", "無配", "業績予想の下方"]):
        return ("⚠️", "下方修正・減配", "high")
    # 2) 明確にポジティブ（株価に上押し）
    if any(k in title for k in ["上方修正", "上振れ", "増額", "増配", "復配", "記念配当", "特別配当"]):
        return ("🚀", "上方修正・増配", "high")
    # 3) 方向不明の予想修正（タイトルだけでは判断できない → 中身を見るべき）
    if any(k in title for k in ["業績予想の修正", "配当予想の修正", "業績予想及び", "配当予想及び"]):
        return ("📈", "予想修正（要確認）", "high")
    # 3.5) 決算説明会（数字の決算短信とは別物。経営者の生の声・Q&A・動画）
    #      「決算短信」より先に判定する（"通期決算説明会資料"等が決算ルールに吸われるのを防ぐ）
    if any(k in title for k in ["説明会", "書き起こし", "カンファレンス・コール",
                                 "カンファレンスコール", "スモールミーティング",
                                 "ロードショー", "オンライン説明"]):
        return ("🎤", "決算説明会", "medium")
    # 4) その他カテゴリ
    for emoji, label, importance, keywords in _CATEGORY_RULES:
        if any(k in title for k in keywords):
            return (emoji, label, importance)
    return ("📄", "開示", "low")


# ── ウォッチリスト読み込み ───────────────────────────────────────
def _load_watchlist() -> dict:
    """{4桁コード or 英数コード: 銘柄名} の辞書を返す"""
    path = BASE_DIR / "data" / "watchlist.json"
    mapping = {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for s in data.get("stocks", []):
            sym = s.get("symbol", "")
            # "5803.T" -> "5803", "285A.T" -> "285A"
            code = sym.split(".")[0].strip().upper()
            if code:
                mapping[code] = s.get("name", code)
    except Exception as e:
        logger.warning(f"watchlist 読み込み失敗: {e}")
    return mapping


# ── 1日分のTDnet開示を取得 ───────────────────────────────────────
def _fetch_date(date_str: str, max_pages: int = 8) -> list[dict]:
    """指定日(YYYYMMDD)の全開示をページ送りで取得"""
    all_items = []
    for page in range(1, max_pages + 1):
        url = f"{_TDNET_BASE}I_list_{page:03d}_{date_str}.html"
        try:
            r = requests.get(url, headers=_HEADERS, timeout=12)
            if r.status_code != 200:
                break
            text = r.content.decode("utf-8", errors="replace")
        except Exception as e:
            logger.warning(f"TDnet取得失敗 [{date_str} p{page}]: {e}")
            break

        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.DOTALL)
        page_count = 0
        for row in rows:
            t  = re.search(r'class="[^"]*kjTime[^"]*"[^>]*>(.*?)</td>',  row, re.DOTALL)
            c  = re.search(r'class="[^"]*kjCode[^"]*"[^>]*>(.*?)</td>',  row, re.DOTALL)
            n  = re.search(r'class="[^"]*kjName[^"]*"[^>]*>(.*?)</td>',  row, re.DOTALL)
            ti = re.search(r'class="[^"]*kjTitle[^"]*"[^>]*>(.*?)</td>', row, re.DOTALL)
            if not (t and c and ti):
                continue
            time_str = re.sub(r"<[^>]+>", "", t.group(1)).strip()
            code     = re.sub(r"<[^>]+>", "", c.group(1)).strip()
            name     = re.sub(r"<[^>]+>", "", n.group(1)).replace("&nbsp;", " ").strip() if n else ""
            title    = re.sub(r"<[^>]+>", "", ti.group(1)).replace("&nbsp;", " ").strip()
            # PDFリンク
            pdf_m = re.search(r'href="([^"]+\.pdf)"', ti.group(1))
            pdf_url = _TDNET_BASE + pdf_m.group(1) if pdf_m else ""
            if not (re.match(r"\d{1,2}:\d{2}", time_str) and code and title):
                continue
            all_items.append({
                "time":  time_str,
                "code":  code,
                "name":  name,
                "title": title,
                "pdf":   pdf_url,
                "date":  date_str,
            })
            page_count += 1
        if page_count < 100:   # 100件未満なら最終ページ
            break
        time.sleep(0.4)
    return all_items


def _prev_business_day(now: datetime) -> datetime:
    """前営業日を返す（土日をスキップ）"""
    d = now - timedelta(days=1)
    while d.weekday() >= 5:   # 5=土, 6=日
        d -= timedelta(days=1)
    return d


# ── メイン処理 ───────────────────────────────────────────────────
def fetch_watchlist_disclosures(date_str: str = None,
                                days_back: int = None) -> dict:
    """
    ウォッチリスト銘柄の開示を抽出。
      date_str  : "YYYYMMDD" を直接指定（CLI用）
      days_back : 今日から何営業日分さかのぼるか（未指定なら前営業日1日分）
    """
    watch = _load_watchlist()
    if not watch:
        return {"available": False, "reason": "watchlist空"}

    now = get_jst_now()
    # 対象日リストを決める
    dates = []
    if date_str:
        dates = [date_str]
    else:
        # 前営業日1日分（重複通知を避けるためデフォルト1日）
        target = _prev_business_day(now)
        dates = [target.strftime("%Y%m%d")]
        # days_back 指定時は追加でさかのぼる
        if days_back and days_back > 1:
            d = target
            for _ in range(days_back - 1):
                d = _prev_business_day(d + timedelta(days=0))
                d = _prev_business_day(d)
                dates.append(d.strftime("%Y%m%d"))

    # 全開示取得 → ウォッチリストで絞る
    hits = []
    seen = set()
    for ds in dates:
        items = _fetch_date(ds)
        logger.info(f"TDnet {ds}: 全{len(items)}件取得")
        for it in items:
            code4 = it["code"][:4].upper()   # 5桁コードの先頭4桁
            if code4 in watch:
                key = (it["code"], it["title"])
                if key in seen:
                    continue
                seen.add(key)
                emoji, label, importance = _classify(it["title"])
                it["watch_name"] = watch[code4]
                it["emoji"]      = emoji
                it["category"]   = label
                it["importance"] = importance
                hits.append(it)

    # 重要度順 → 時刻順でソート
    imp_order = {"high": 0, "medium": 1, "low": 2}
    hits.sort(key=lambda x: (imp_order.get(x["importance"], 3), x["time"]), reverse=False)

    return {
        "available":   len(hits) > 0,
        "count":       len(hits),
        "disclosures": hits,
        "dates":       dates,
        "high_count":  sum(1 for h in hits if h["importance"] == "high"),
    }


# ── Telegram メッセージ生成 ─────────────────────────────────────
def build_telegram_message(result: dict) -> str:
    if not result.get("available"):
        return ""
    hits = result["disclosures"]
    # 日付表示（YYYYMMDD -> M/D）
    ds = result["dates"][0]
    md = f"{int(ds[4:6])}/{int(ds[6:8])}"

    lines = [f"📋 *適時開示アラート（{md}）*"]
    high = result.get("high_count", 0)
    lines.append(f"ウォッチリスト {result['count']}件" + (f"（重要 {high}件）" if high else ""))
    lines.append("")

    # 銘柄ごとにまとめる
    by_code = {}
    for h in hits:
        by_code.setdefault((h["code"][:4], h["watch_name"]), []).append(h)

    for (code4, name), items in by_code.items():
        lines.append(f"*[{code4}] {name}*")
        for it in items:
            lines.append(f"  {it['emoji']} {it['time']}  {it['category']}")
            # タイトルは長いので60字まで
            title = it["title"][:60] + ("…" if len(it["title"]) > 60 else "")
            lines.append(f"     {title}")
        lines.append("")

    return "\n".join(lines).strip()


# ── HTML セクション生成 ─────────────────────────────────────────
def get_html(result: dict) -> str:
    if not result or not result.get("available"):
        return ""
    hits = result["disclosures"]
    ds = result["dates"][0]
    md = f"{int(ds[4:6])}/{int(ds[6:8])}"

    rows = ""
    imp_color = {"high": "#f44336", "medium": "#ffa726", "low": "#7a8fa8"}
    for h in hits:
        col = imp_color.get(h["importance"], "#7a8fa8")
        title_html = h["title"]
        if h["pdf"]:
            title_html = f'<a href="{h["pdf"]}" target="_blank" style="color:#7ec8ff;text-decoration:none;">{h["title"]} 📄</a>'
        rows += f'''
<div style="display:flex;gap:10px;padding:10px 0;border-bottom:1px solid #1e2d42;">
  <div style="font-size:1.2em;">{h["emoji"]}</div>
  <div style="flex:1;">
    <div style="font-size:0.78em;color:#7a8fa8;">
      <span style="color:{col};font-weight:700;">{h["category"]}</span>
      ・{h["time"]}・<b>[{h["code"][:4]}] {h["watch_name"]}</b>
    </div>
    <div style="font-size:0.86em;line-height:1.5;margin-top:2px;">{title_html}</div>
  </div>
</div>'''

    return f'''
<div style="background:#0f1623;border:1px solid #1e2d42;border-radius:14px;padding:16px;margin-bottom:16px;">
  <div style="font-weight:700;font-size:1.0em;margin-bottom:4px;">📋 適時開示アラート（{md}）</div>
  <div style="font-size:0.75em;color:#7a8fa8;margin-bottom:10px;">
    保有・注目銘柄の決算・自社株買い・M&Aなどの開示を東証TDnetから自動抽出（{result["count"]}件）
  </div>
  {rows}
</div>'''


# ── cloud_run.py 標準インターフェース ───────────────────────────
def run(prices: dict = None, risk: dict = None, fear_greed: dict = None) -> dict:
    """cloud_run.py から呼ばれる標準形式"""
    try:
        result = fetch_watchlist_disclosures()
        if result.get("available"):
            result["telegram_message"] = build_telegram_message(result)
            result["html"] = get_html(result)
        return result
    except Exception as e:
        logger.error(f"TDnetウォッチャーエラー: {e}")
        return {"available": False, "reason": str(e)}


# ── CLI（オンデマンド実行） ─────────────────────────────────────
if __name__ == "__main__":
    import sys
    # 引数: 日付(YYYYMMDD) or 営業日数
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    if arg and re.match(r"^\d{8}$", arg):
        res = fetch_watchlist_disclosures(date_str=arg)
    elif arg and arg.isdigit():
        res = fetch_watchlist_disclosures(days_back=int(arg))
    else:
        res = fetch_watchlist_disclosures()

    out = []
    if res.get("available"):
        out.append(f"=== ウォッチリスト適時開示 {res['count']}件（重要{res.get('high_count',0)}件）===\n")
        for h in res["disclosures"]:
            out.append(f"{h['emoji']} {h['time']} [{h['code'][:4]}] {h['watch_name']} | {h['category']}")
            out.append(f"   {h['title']}")
            if h["pdf"]:
                out.append(f"   {h['pdf']}")
            out.append("")
    else:
        out.append(f"開示なし（{res.get('reason','対象日にウォッチリスト銘柄の開示なし')}）")

    text = "\n".join(out)
    # Windows CP932対策：ファイルにも書き出す
    try:
        print(text)
    except UnicodeEncodeError:
        with open("tdnet_output.txt", "w", encoding="utf-8") as f:
            f.write(text)
        print("出力を tdnet_output.txt に保存しました")
