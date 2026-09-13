@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo =============================================
echo  投資経済 AI 秘書 ダッシュボード起動
echo  ブラウザで自動的に開きます
echo  終了するには このウィンドウを閉じてください
echo =============================================
echo.
streamlit run dashboard.py --server.headless false
pause
