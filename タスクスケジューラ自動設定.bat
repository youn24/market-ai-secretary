@echo off
chcp 65001 > nul
echo ============================================
echo  タスクスケジューラ 自動設定
echo  毎朝7:30に自動実行されます
echo ============================================
echo.

set PROJ=C:\Users\中田　洋介\Desktop\tousijouhou\market-ai-secretary

:: 既存タスク削除（エラーは無視）
schtasks /delete /tn "市場AI秘書_朝" /f 2>nul
schtasks /delete /tn "市場レポート_朝" /f 2>nul
schtasks /delete /tn "市場AI秘書" /f 2>nul

:: 朝7:30 自動実行（平日）
echo [1/2] 朝レポート（平日 07:30）を登録中...
schtasks /create /tn "市場AI秘書_朝" /tr "\"%PROJ%\完全自動起動.bat\"" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 07:30 /ru "%USERNAME%" /rl HIGHEST /f

if %errorlevel%==0 (
    echo     OK! 毎朝7:30に自動実行されます
) else (
    echo     失敗。管理者として実行してください
)

:: 夕方17:30（オプション）
echo [2/2] 夕方レポート（平日 17:30）を登録中...
schtasks /create /tn "市場AI秘書_夕" /tr "\"%PROJ%\完全自動起動.bat\"" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 17:30 /ru "%USERNAME%" /rl HIGHEST /f

if %errorlevel%==0 (
    echo     OK! 毎日17:30にも自動実行されます
) else (
    echo     失敗（夕方は任意なのでスキップしてもOK）
)

echo.
echo ============================================
echo  設定完了！Telegramに毎日通知が届きます 📱
echo ============================================
echo.
pause
