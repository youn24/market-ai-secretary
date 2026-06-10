"""
銘柄を指定してその場で財務分析するスクリプト
使い方:
  python analyze_stock.py 9984       # ソフトバンクGを分析
  python analyze_stock.py 5803 6981  # フジクラ・村田を同時分析
  python analyze_stock.py            # ウォッチリスト全銘柄を分析
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.financial_analyzer import analyze_company, run_watchlist_analysis


KNOWN = {
    "5803": ("5803.T", "フジクラ"),
    "9984": ("9984.T", "ソフトバンクグループ"),
    "6981": ("6981.T", "村田製作所"),
    "7203": ("7203.T", "トヨタ自動車"),
    "9432": ("9432.T", "NTT"),
    "6758": ("6758.T", "ソニーグループ"),
    "6861": ("6861.T", "キーエンス"),
    "4063": ("4063.T", "信越化学工業"),
    "8035": ("8035.T", "東京エレクトロン"),
    "2914": ("2914.T", "日本たばこ産業"),
    "6762": ("6762.T", "TDK"),
    "6501": ("6501.T", "日立製作所"),
    "7012": ("7012.T", "川崎重工業"),
    "285A": ("285A.T", "キオクシア"),
    "4063": ("4063.T", "信越化学工業"),
}


def resolve(code: str):
    if code in KNOWN:
        return KNOWN[code]
    if "." not in code:
        code = code + ".T"
    return (code, code)


def print_result(r: dict):
    sep = "─" * 50
    print(f"\n{sep}")
    print(f"  {r.get('verdict_emoji','⚪')} {r.get('name','')}  ({r.get('symbol','')})")
    print(sep)

    raw = r.get("raw", {})
    per = f"{raw['per']:.1f}倍"  if raw.get("per")  else "N/A"
    pbr = f"{raw['pbr']:.2f}倍" if raw.get("pbr")  else "N/A"
    roe = f"{raw['roe']*100:.1f}%" if raw.get("roe") else "N/A"
    opm = f"{raw['op_margin']*100:.1f}%" if raw.get("op_margin") else "N/A"
    rg  = f"{raw['revenue_growth']*100:+.1f}%" if raw.get("revenue_growth") else "N/A"
    eg  = f"{raw['earnings_growth']*100:+.1f}%" if raw.get("earnings_growth") else "N/A"
    div = f"{raw['dividend_yield']*100:.1f}%" if raw.get("dividend_yield") else "N/A"
    cp  = f"{raw['current_price']:,.0f}円" if raw.get("current_price") else "N/A"

    print(f"  現在値      : {cp}")
    print(f"  PER         : {per}  （15倍以下が割安目安）")
    print(f"  PBR         : {pbr}  （1倍以下は資産より安い）")
    print(f"  ROE         : {roe}  （10%以上が優秀）")
    print(f"  営業利益率  : {opm}")
    print(f"  売上成長率  : {rg}")
    print(f"  利益成長率  : {eg}")
    print(f"  配当利回り  : {div}")
    print(f"\n  AI総合判定 : 【{r.get('verdict','---')}】")
    print(sep)
    print("\n【AI詳細分析】")
    print(r.get("ai_analysis", "分析なし"))
    print()


def main():
    args = sys.argv[1:]

    if not args:
        print("ウォッチリスト全銘柄を分析します...\n")
        result = run_watchlist_analysis()
        for r in result.get("results", []):
            print_result(r)
    else:
        for code in args:
            sym, name = resolve(code)
            print(f"\n{name}({sym}) を分析中...")
            r = analyze_company(sym, name)
            print_result(r)


if __name__ == "__main__":
    main()
