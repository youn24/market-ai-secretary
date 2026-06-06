@echo off
chcp 65001 > nul
echo =============================================
echo  Market AI Secretary - セットアップ
echo =============================================
echo.

:: Pythonの確認
python --version > nul 2>&1
if %errorlevel% neq 0 (
    echo [エラー] Python が見つかりません。
    echo.
    echo 以下の手順でPythonをインストールしてください：
    echo  1. https://www.python.org/downloads/ を開く
    echo  2. "Download Python 3.x.x" をクリック
    echo  3. インストーラを実行
    echo  4. 必ず "Add Python to PATH" にチェックを入れる
    echo  5. インストール後、このファイルを再度実行
    echo.
    pause
    exit /b 1
)

python --version
echo.

:: ライブラリのインストール
echo [1/3] ライブラリをインストール中...
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [エラー] ライブラリのインストールに失敗しました。
    pause
    exit /b 1
)
echo.

:: .envのコピー（まだない場合）
if not exist .env (
    echo [2/3] .env.example を .env にコピー中...
    copy .env.example .env
    echo .env を作成しました。
    echo Telegram通知を使う場合は .env ファイルを編集してください。
) else (
    echo [2/3] .env は既に存在します。スキップ。
)
echo.

:: テスト実行
echo [3/3] テスト実行中...
python run_daily.py --mode test
echo.

echo =============================================
echo  セットアップ完了！
echo  レポートは reports\ フォルダに保存されました。
echo  毎日実行するには: python run_daily.py --mode morning
echo =============================================
pause
