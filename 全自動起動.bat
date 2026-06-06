@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo =============================================
echo  投資経済 AI 秘書 - 全自動起動
echo =============================================
echo.

:: Ollama モデルパス設定
set OLLAMA_MODELS=C:\ollama_models

:: Step 1: データ取得・分析・レポート生成
echo [1/2] データ取得・分析・レポート生成中...
echo （テクニカル・ファンダ・AI要約を含む。5〜10分かかります）
echo.
python run_daily.py --mode morning
echo.

:: Step 2: ダッシュボード起動
echo [2/2] ダッシュボード起動中...
echo ブラウザが自動で開きます。
echo このウィンドウは閉じないでください。
echo.
python -m streamlit run dashboard.py

pause
