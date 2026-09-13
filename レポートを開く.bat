@echo off
chcp 65001 > nul
cd /d "%~dp0"

:: Pythonで今日の日付(JST)を取得して開く
python -c "
import sys, os
from datetime import datetime, timezone, timedelta
from pathlib import Path

JST = timezone(timedelta(hours=9))
today = datetime.now(JST).strftime('%Y-%m-%d')
base = Path(r'C:\Users\中田　洋介\Desktop\tousijouhou\market-ai-secretary\reports')

# 優先順位: morning > evening > noon > test
for mode in ['morning', 'evening', 'noon', 'test']:
    p = base / f'{today}_{mode}.html'
    if p.exists():
        print(f'開くファイル: {p}')
        os.startfile(str(p))
        sys.exit(0)

print(f'今日({today})のレポートがまだありません。')
print('run_morning.bat を実行してからもう一度試してください。')
input('Enterで閉じます...')
"
