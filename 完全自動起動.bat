@echo off
chcp 65001 > nul
title 市場AI秘書 - 完全自動実行

echo ============================================
echo   市場AI秘書 完全自動実行システム
echo ============================================
echo.

:: 作業フォルダへ移動
cd /d "C:\Users\中田　洋介\Desktop\tousijouhou\market-ai-secretary"

:: Ollama環境変数設定（日本語パス対策）
set OLLAMA_MODELS=C:\ollama_models

:: Ollamaがすでに起動しているか確認
tasklist /fi "imagename eq ollama.exe" 2>nul | find /i "ollama.exe" >nul
if %errorlevel% neq 0 (
    echo [1/3] Ollama起動中...
    start /min "" ollama serve
    timeout /t 5 /nobreak > nul
) else (
    echo [1/3] Ollama: すでに起動済み
)

:: Pythonパス
set PYTHON="C:\Users\中田　洋介\AppData\Local\Python\pythoncore-3.14-64\python.exe"

echo [2/3] 市場データ取得・AI分析・レポート生成・Telegram通知...
%PYTHON% run_daily.py --mode morning

echo.
echo [3/3] 完了！Telegramを確認してください 📱
echo ============================================
echo.
pause
