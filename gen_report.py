"""実データでHTMLレポートを再生成"""
from src.fetch_prices import run as fp
from src.indicators import calc_risk_score
from src.fetch_news import run as fn
from src.design_ai import generate
import os

prices, fg = fp()
risk = calc_risk_score(prices)
news = fn()
path = generate(prices=prices, fear_greed=fg, risk=risk, news=news)
print("SUCCESS:", path)
print("SIZE:", os.path.getsize(str(path)) // 1024, "KB")

# プロセクションが入っているか確認
with open(str(path), encoding="utf-8") as f:
    html = f.read()
for kw in ["プロの目", "日米 恐怖スプレッド", "CME先物ギャップ", "NT倍率", "グロース体温計", "半導体動脈", "市場天気図"]:
    print(("OK  " if kw in html else "MISSING  ") + kw)
