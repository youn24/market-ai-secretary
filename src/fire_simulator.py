"""
FIREシミュレーター
Financial Independence, Retire Early の達成年数・達成年齢を計算し、
HTMLレポートを生成する。
"""

import json
import math
import os
from pathlib import Path

DEFAULT_CONFIG = {
    "current_assets": 3_000_000,
    "monthly_savings": 50_000,
    "annual_return_pct": 5.0,
    "annual_expense": 2_400_000,
    "current_age": 35,
    "safe_withdrawal_rate": 4.0,
}

_CONFIG_PATH = Path(__file__).parent.parent / "data" / "fire_config.json"


def _load_config(config: dict | None) -> dict:
    """設定を読み込む。引数 > ファイル > デフォルトの優先順。"""
    base = dict(DEFAULT_CONFIG)
    if _CONFIG_PATH.exists():
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                base.update(json.load(f))
        except Exception:
            pass
    if config:
        base.update(config)
    return base


def _months_to_fire(assets: float, monthly: float, annual_return: float, target: float) -> float:
    """複利月次ループで FIRE 達成までの月数を返す。達成不可なら inf。"""
    r = annual_return / 12 / 100
    if r == 0:
        if monthly <= 0:
            return float("inf")
        remaining = target - assets
        return remaining / monthly if remaining > 0 else 0
    n = 0
    current = assets
    while current < target and n < 12 * 100:
        current = current * (1 + r) + monthly
        n += 1
    return n if current >= target else float("inf")


def _assets_at_month(assets: float, monthly: float, annual_return: float, months: int) -> float:
    """n ヶ月後の資産額を返す。"""
    r = annual_return / 12 / 100
    if r == 0:
        return assets + monthly * months
    return assets * ((1 + r) ** months) + monthly * (((1 + r) ** months - 1) / r)


def _monthly_needed_for_fire(assets: float, annual_return: float, target: float, max_years: int = 50) -> float:
    """指定年数以内に FIRE するために必要な毎月積立額を二分探索で求める。"""
    lo, hi = 0.0, 10_000_000.0
    months_limit = max_years * 12
    r = annual_return / 12 / 100

    def _reach(monthly):
        return _months_to_fire(assets, monthly, annual_return, target) <= months_limit

    if _reach(0):
        return 0.0
    if not _reach(hi):
        return float("inf")

    for _ in range(60):
        mid = (lo + hi) / 2
        if _reach(mid):
            hi = mid
        else:
            lo = mid
    return math.ceil(hi / 1000) * 1000


def _build_milestones(
    assets: float,
    monthly: float,
    annual_return: float,
    current_age: int,
    fire_target: float,
) -> list[dict]:
    """資産マイルストーンを計算する。"""
    checkpoints = [5_000_000, 10_000_000, 20_000_000, 30_000_000, fire_target]
    seen = set()
    result = []
    for cp in checkpoints:
        if cp in seen or cp < assets:
            continue
        seen.add(cp)
        months = _months_to_fire(assets, monthly, annual_return, cp)
        if math.isinf(months):
            continue
        years = math.ceil(months / 12)
        age = current_age + years
        if cp == fire_target:
            label = "FIRE達成!"
        elif cp >= 100_000_000:
            label = f"{cp / 100_000_000:.0f}億円"
        elif cp >= 10_000_000:
            label = f"{cp / 10_000_000:.0f}千万円"
        else:
            label = f"{cp / 10_000:.0f}万円"
        result.append({"year": years, "age": age, "assets": cp, "label": label})
    result.sort(key=lambda x: x["year"])
    return result


def _fmt_yen(amount: float) -> str:
    """金額を読みやすい形式に変換する。"""
    if amount >= 100_000_000:
        v = amount / 100_000_000
        return f"{v:.1f}億円" if v != int(v) else f"{int(v)}億円"
    if amount >= 10_000:
        man = int(amount // 10_000)
        return f"{man:,}万円"
    return f"{int(amount):,}円"


def _build_html(result: dict) -> str:
    """ダークテーマ・黄金色アクセントの HTML を生成する。"""
    fire_years = result["fire_years"]
    fire_age = result["fire_age"]
    fire_target = result["fire_target"]
    current_assets = result["current_assets"]
    progress_pct = min(result["progress_pct"], 100)
    monthly_needed = result["monthly_needed"]
    milestones = result["milestones"]
    boost = result["scenario_boost"]

    # プログレスバー幅
    bar_width = f"{progress_pct:.1f}%"

    # マイルストーンタイムライン HTML
    milestone_items = ""
    for m in milestones:
        is_fire = m["label"] == "FIRE達成!"
        dot_class = "milestone-dot fire" if is_fire else "milestone-dot"
        label_class = "milestone-label fire" if is_fire else "milestone-label"
        milestone_items += f"""
        <div class="milestone-item">
            <div class="{dot_class}"></div>
            <div class="{label_class}">{m['label']}</div>
            <div class="milestone-age">{m['age']}歳</div>
            <div class="milestone-year">+{m['year']}年後</div>
        </div>"""

    # シナリオブースト表示
    if boost.get("available"):
        boost_html = f"""
        <div class="boost-card">
            <div class="boost-title">毎月+1万円増やすと？</div>
            <div class="boost-row">
                <div class="boost-item">
                    <div class="boost-sub">現在のペース</div>
                    <div class="boost-value">{boost['base_years']}年後</div>
                    <div class="boost-age">({boost['base_age']}歳)</div>
                </div>
                <div class="boost-arrow">→</div>
                <div class="boost-item highlight">
                    <div class="boost-sub">+1万円/月</div>
                    <div class="boost-value">{boost['new_years']}年後</div>
                    <div class="boost-age">({boost['new_age']}歳)</div>
                </div>
            </div>
            <div class="boost-diff">
                <span class="diff-badge">▲ {boost['years_saved']}年早くFIREできます！</span>
            </div>
        </div>"""
    else:
        boost_html = ""

    # 必要月額表示
    if math.isinf(monthly_needed):
        needed_str = "計算範囲外"
    else:
        needed_str = _fmt_yen(monthly_needed) + "/月"

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FIREシミュレーター</title>
<style>
  :root {{
    --bg: #0d1117;
    --card: #161b22;
    --border: #30363d;
    --gold: #f0b429;
    --gold-light: #ffd166;
    --gold-dark: #c98a00;
    --text: #e6edf3;
    --text-muted: #8b949e;
    --green: #3fb950;
    --blue: #58a6ff;
    --red: #f85149;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: 'Segoe UI', 'Hiragino Sans', 'Noto Sans JP', sans-serif;
    padding: 24px 16px;
    max-width: 860px;
    margin: 0 auto;
  }}
  h1 {{
    font-size: 1.4rem;
    color: var(--gold);
    margin-bottom: 20px;
    display: flex;
    align-items: center;
    gap: 8px;
  }}
  /* バナー */
  .fire-banner {{
    background: linear-gradient(135deg, #1a1200 0%, #2a1f00 40%, #1a1200 100%);
    border: 2px solid var(--gold);
    border-radius: 16px;
    padding: 28px 24px;
    text-align: center;
    margin-bottom: 24px;
    position: relative;
    overflow: hidden;
  }}
  .fire-banner::before {{
    content: '';
    position: absolute;
    inset: 0;
    background: radial-gradient(ellipse at 50% 0%, rgba(240,180,41,0.12) 0%, transparent 70%);
    pointer-events: none;
  }}
  .fire-banner .fire-icon {{
    font-size: 2.8rem;
    margin-bottom: 8px;
    display: block;
  }}
  .fire-banner .fire-headline {{
    font-size: 2rem;
    font-weight: 800;
    color: var(--gold);
    line-height: 1.2;
    margin-bottom: 8px;
  }}
  .fire-banner .fire-sub {{
    font-size: 1rem;
    color: var(--text-muted);
  }}
  .fire-banner .fire-target-label {{
    margin-top: 14px;
    font-size: 0.9rem;
    color: var(--gold-light);
    opacity: 0.9;
  }}
  /* 進捗バー */
  .progress-card {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px 24px;
    margin-bottom: 20px;
  }}
  .progress-header {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 10px;
  }}
  .progress-title {{
    font-size: 0.85rem;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }}
  .progress-pct {{
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--gold);
  }}
  .progress-track {{
    background: #21262d;
    border-radius: 999px;
    height: 18px;
    overflow: hidden;
    margin-bottom: 10px;
  }}
  .progress-fill {{
    height: 100%;
    background: linear-gradient(90deg, var(--gold-dark), var(--gold), var(--gold-light));
    border-radius: 999px;
    width: {bar_width};
    transition: width 0.6s ease;
  }}
  .progress-amounts {{
    display: flex;
    justify-content: space-between;
    font-size: 0.82rem;
    color: var(--text-muted);
  }}
  .progress-amounts .current {{
    color: var(--gold-light);
    font-weight: 600;
  }}
  /* 指標グリッド */
  .metrics-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 14px;
    margin-bottom: 20px;
  }}
  .metric-card {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 16px 18px;
  }}
  .metric-label {{
    font-size: 0.78rem;
    color: var(--text-muted);
    margin-bottom: 6px;
    letter-spacing: 0.04em;
  }}
  .metric-value {{
    font-size: 1.25rem;
    font-weight: 700;
    color: var(--text);
  }}
  .metric-value.gold {{ color: var(--gold); }}
  .metric-value.green {{ color: var(--green); }}
  /* マイルストーンタイムライン */
  .milestone-section {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px 24px;
    margin-bottom: 20px;
  }}
  .section-title {{
    font-size: 0.85rem;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 18px;
  }}
  .milestone-timeline {{
    display: flex;
    gap: 0;
    overflow-x: auto;
    padding-bottom: 8px;
    position: relative;
    scrollbar-width: thin;
    scrollbar-color: var(--gold-dark) transparent;
  }}
  .milestone-timeline::before {{
    content: '';
    position: absolute;
    top: 14px;
    left: 14px;
    right: 14px;
    height: 2px;
    background: linear-gradient(90deg, var(--gold-dark), var(--gold));
    z-index: 0;
  }}
  .milestone-item {{
    display: flex;
    flex-direction: column;
    align-items: center;
    min-width: 110px;
    position: relative;
    z-index: 1;
  }}
  .milestone-dot {{
    width: 28px;
    height: 28px;
    border-radius: 50%;
    background: var(--card);
    border: 3px solid var(--gold-dark);
    margin-bottom: 10px;
    flex-shrink: 0;
  }}
  .milestone-dot.fire {{
    background: var(--gold);
    border-color: var(--gold-light);
    box-shadow: 0 0 12px rgba(240,180,41,0.6);
  }}
  .milestone-label {{
    font-size: 0.82rem;
    font-weight: 600;
    color: var(--text);
    text-align: center;
    margin-bottom: 3px;
  }}
  .milestone-label.fire {{
    color: var(--gold);
    font-size: 0.9rem;
  }}
  .milestone-age {{
    font-size: 0.95rem;
    font-weight: 700;
    color: var(--gold-light);
    margin-bottom: 2px;
  }}
  .milestone-year {{
    font-size: 0.75rem;
    color: var(--text-muted);
  }}
  /* ブーストカード */
  .boost-card {{
    background: linear-gradient(135deg, #0d1f0d 0%, #111f11 100%);
    border: 1px solid #2a4a2a;
    border-radius: 12px;
    padding: 20px 24px;
    margin-bottom: 20px;
  }}
  .boost-title {{
    font-size: 0.85rem;
    color: var(--green);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 14px;
  }}
  .boost-row {{
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 20px;
    margin-bottom: 14px;
  }}
  .boost-item {{
    text-align: center;
    flex: 1;
  }}
  .boost-item.highlight {{
    background: rgba(63,185,80,0.08);
    border-radius: 10px;
    padding: 12px;
    border: 1px solid rgba(63,185,80,0.25);
  }}
  .boost-sub {{
    font-size: 0.75rem;
    color: var(--text-muted);
    margin-bottom: 4px;
  }}
  .boost-value {{
    font-size: 1.4rem;
    font-weight: 700;
    color: var(--text);
  }}
  .boost-item.highlight .boost-value {{ color: var(--green); }}
  .boost-age {{
    font-size: 0.8rem;
    color: var(--text-muted);
    margin-top: 2px;
  }}
  .boost-arrow {{
    font-size: 1.4rem;
    color: var(--green);
    opacity: 0.7;
    flex-shrink: 0;
  }}
  .boost-diff {{
    text-align: center;
  }}
  .diff-badge {{
    display: inline-block;
    background: rgba(63,185,80,0.15);
    border: 1px solid rgba(63,185,80,0.4);
    border-radius: 999px;
    padding: 5px 16px;
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--green);
  }}
  /* 月額必要 */
  .needed-card {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 16px 24px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;
  }}
  .needed-label {{
    font-size: 0.85rem;
    color: var(--text-muted);
  }}
  .needed-value {{
    font-size: 1.2rem;
    font-weight: 700;
    color: var(--blue);
  }}
  footer {{
    font-size: 0.75rem;
    color: var(--text-muted);
    text-align: center;
    margin-top: 24px;
    line-height: 1.8;
  }}
</style>
</head>
<body>

<h1>🔥 FIREシミュレーター</h1>

<div class="fire-banner">
  <span class="fire-icon">🔥</span>
  <div class="fire-headline">あと{fire_years}年でFIREできます！</div>
  <div class="fire-sub">{fire_age}歳でFINANCIAL INDEPENDENCEを達成</div>
  <div class="fire-target-label">FIRE目標額 {_fmt_yen(fire_target)}</div>
</div>

<div class="progress-card">
  <div class="progress-header">
    <div class="progress-title">FIRE達成度</div>
    <div class="progress-pct">{progress_pct:.1f}%</div>
  </div>
  <div class="progress-track">
    <div class="progress-fill"></div>
  </div>
  <div class="progress-amounts">
    <span class="current">現在 {_fmt_yen(current_assets)}</span>
    <span>目標 {_fmt_yen(fire_target)}</span>
  </div>
</div>

<div class="metrics-grid">
  <div class="metric-card">
    <div class="metric-label">FIRE目標額</div>
    <div class="metric-value gold">{_fmt_yen(fire_target)}</div>
  </div>
  <div class="metric-card">
    <div class="metric-label">達成年齢</div>
    <div class="metric-value gold">{fire_age}歳</div>
  </div>
  <div class="metric-card">
    <div class="metric-label">現在の資産</div>
    <div class="metric-value">{_fmt_yen(current_assets)}</div>
  </div>
  <div class="metric-card">
    <div class="metric-label">達成まで</div>
    <div class="metric-value green">{fire_years}年</div>
  </div>
</div>

<div class="milestone-section">
  <div class="section-title">マイルストーンタイムライン</div>
  <div class="milestone-timeline">{milestone_items}
  </div>
</div>

{boost_html}

<div class="needed-card">
  <div class="needed-label">今の利回りでFIREするのに必要な毎月積立額</div>
  <div class="needed-value">{needed_str}</div>
</div>

<footer>
  ※ このシミュレーションは概算です。実際の投資成果を保証するものではありません。<br>
  安全引出率 {result['safe_withdrawal_rate']:.1f}% / 年間想定利回り {result['annual_return_pct']:.1f}% を使用
</footer>

</body>
</html>"""
    return html


def calc_fire_years(config: dict = None) -> dict:
    """
    FIRE 達成年数・年齢・マイルストーンを計算し、HTML レポートを生成する。

    Parameters
    ----------
    config : dict, optional
        設定の上書き。省略時は data/fire_config.json またはデフォルト値を使用。

    Returns
    -------
    dict
        available, fire_target, fire_years, fire_age, current_assets,
        progress_pct, monthly_needed, milestones, scenario_boost, html
    """
    cfg = _load_config(config)

    current_assets: float = float(cfg["current_assets"])
    monthly_savings: float = float(cfg["monthly_savings"])
    annual_return_pct: float = float(cfg["annual_return_pct"])
    annual_expense: float = float(cfg["annual_expense"])
    current_age: int = int(cfg["current_age"])
    safe_withdrawal_rate: float = float(cfg["safe_withdrawal_rate"])

    # FIRE 目標額 = 年間支出 / 安全引出率
    fire_target = annual_expense / (safe_withdrawal_rate / 100)

    # 達成月数
    months = _months_to_fire(current_assets, monthly_savings, annual_return_pct, fire_target)
    available = not math.isinf(months)

    if available:
        fire_years = math.ceil(months / 12)
        fire_age = current_age + fire_years
    else:
        fire_years = 9999
        fire_age = 9999

    # 達成率
    progress_pct = (current_assets / fire_target) * 100

    # 今の利回りで FIRE するのに必要な毎月積立額
    monthly_needed = _monthly_needed_for_fire(current_assets, annual_return_pct, fire_target)

    # マイルストーン
    milestones = _build_milestones(
        current_assets, monthly_savings, annual_return_pct, current_age, fire_target
    )

    # シナリオブースト: 毎月+1万円
    boost_monthly = monthly_savings + 10_000
    boost_months = _months_to_fire(current_assets, boost_monthly, annual_return_pct, fire_target)
    if available and not math.isinf(boost_months):
        boost_years = math.ceil(boost_months / 12)
        boost_age = current_age + boost_years
        years_saved = fire_years - boost_years
        scenario_boost = {
            "available": True,
            "base_years": fire_years,
            "base_age": fire_age,
            "new_years": boost_years,
            "new_age": boost_age,
            "years_saved": max(years_saved, 0),
        }
    else:
        scenario_boost = {"available": False}

    result = {
        "available": available,
        "fire_target": fire_target,
        "fire_years": fire_years,
        "fire_age": fire_age,
        "current_assets": current_assets,
        "progress_pct": round(progress_pct, 2),
        "monthly_needed": monthly_needed,
        "milestones": milestones,
        "scenario_boost": scenario_boost,
        "annual_return_pct": annual_return_pct,
        "safe_withdrawal_rate": safe_withdrawal_rate,
        "html": "",
    }

    # HTML 生成
    result["html"] = _build_html(result)

    return result


# --- CLI 実行 ---
if __name__ == "__main__":
    result = calc_fire_years()
    print(f"FIRE目標額    : {_fmt_yen(result['fire_target'])}")
    print(f"現在の資産    : {_fmt_yen(result['current_assets'])}")
    print(f"達成率        : {result['progress_pct']:.1f}%")
    print(f"FIRE達成まで  : {result['fire_years']}年後 ({result['fire_age']}歳)")
    print(f"必要月額      : {_fmt_yen(result['monthly_needed'])}/月")
    print("マイルストーン:")
    for m in result["milestones"]:
        print(f"  {m['label']:12s}  +{m['year']:3d}年後  {m['age']}歳")
    boost = result["scenario_boost"]
    if boost.get("available"):
        print(f"+1万円/月で  : {boost['years_saved']}年早くなる ({boost['new_age']}歳でFIRE)")

    # HTML 出力
    out_path = Path(__file__).parent.parent / "reports" / "fire_simulator.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(result["html"], encoding="utf-8")
    print(f"\nHTML出力: {out_path}")
