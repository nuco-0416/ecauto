@echo off
chcp 65001 >nul
REM ================================================================
REM EC Auto - 在庫同期デーモン 手動起動スクリプト
REM
REM サービス化せずに、手動でデーモンを起動します。
REM 停止するには Ctrl+C を押してください。
REM ================================================================

echo ================================================================
echo EC Auto - 在庫同期デーモン 手動起動
echo ================================================================
echo.

set PROJECT_DIR=C:\Users\hiroo\Documents\GitHub\ecauto
set PYTHON_EXE=%PROJECT_DIR%\venv\Scripts\python.exe
set SCRIPT_PATH=%PROJECT_DIR%\scheduled_tasks\sync_inventory_daemon.py

REM デフォルト設定
set INTERVAL=3600
set DRY_RUN=

REM --- 引数処理 ---
if "%1"=="--dry-run" set DRY_RUN=--dry-run
if "%1"=="--test" set INTERVAL=60

echo プロジェクト: %PROJECT_DIR%
echo 実行間隔: %INTERVAL%秒
if defined DRY_RUN (
    echo モード: DRY RUN（テスト）
) else (
    echo モード: 本番実行
)
echo.
echo 停止するには Ctrl+C を押してください
echo.
echo ================================================================
echo.

cd /d "%PROJECT_DIR%"
"%PYTHON_EXE%" "%SCRIPT_PATH%" --interval %INTERVAL% %DRY_RUN%

pause
