@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo [テスト] 動作確認を開始します...
python run_daily.py --mode test
echo.
pause
