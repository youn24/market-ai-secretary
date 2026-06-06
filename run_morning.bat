@echo off
chcp 65001 > nul
cd /d "%~dp0"
set OLLAMA_MODELS=C:\ollama_models
echo [朝の市場レポート] データ取得・分析開始...
python run_daily.py --mode morning
echo.
echo 完了！ダッシュボードを開くには「全自動起動.bat」を実行してください。
