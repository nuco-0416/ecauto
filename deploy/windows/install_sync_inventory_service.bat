@echo off
chcp 65001 >nul
REM ================================================================
REM EC Auto - 在庫同期デーモン Windowsサービスインストールスクリプト
REM
REM 前提条件:
REM - NSSMがインストールされていること
REM   ダウンロード: https://nssm.cc/download
REM
REM 使用方法:
REM   1. 管理者権限でコマンドプロンプトを開く
REM   2. このスクリプトを実行
REM      > install_sync_inventory_service.bat
REM ================================================================

echo ================================================================
echo EC Auto - 在庫同期デーモン サービスインストール
echo ================================================================
echo.

REM --- 設定項目 ---
set SERVICE_NAME=ECAutoSyncInventory
set DISPLAY_NAME=EC Auto - Inventory Sync
set PROJECT_DIR=C:\Users\hiroo\Documents\GitHub\ecauto
set PYTHON_EXE=%PROJECT_DIR%\venv\Scripts\python.exe
set SCRIPT_PATH=%PROJECT_DIR%\scheduled_tasks\sync_inventory_daemon.py
set INTERVAL=3600

REM --- NSSMの確認 ---
where nssm >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] NSSMが見つかりません。
    echo.
    echo NSSMをインストールしてください:
    echo   1. https://nssm.cc/download からダウンロード
    echo   2. nssm.exe をPATHの通った場所に配置
    echo      （例: C:\Windows\System32）
    echo.
    pause
    exit /b 1
)

echo [OK] NSSMが見つかりました
echo.

REM --- プロジェクトディレクトリの確認 ---
if not exist "%PROJECT_DIR%" (
    echo [ERROR] プロジェクトディレクトリが見つかりません: %PROJECT_DIR%
    pause
    exit /b 1
)

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Python実行ファイルが見つかりません: %PYTHON_EXE%
    pause
    exit /b 1
)

if not exist "%SCRIPT_PATH%" (
    echo [ERROR] スクリプトファイルが見つかりません: %SCRIPT_PATH%
    pause
    exit /b 1
)

echo [OK] プロジェクトファイルが見つかりました
echo.

REM --- 既存サービスの確認 ---
sc query "%SERVICE_NAME%" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [警告] サービス "%SERVICE_NAME%" は既に存在します。
    echo.
    choice /C YN /M "既存のサービスを削除して再インストールしますか？"
    if errorlevel 2 (
        echo インストールをキャンセルしました。
        pause
        exit /b 0
    )

    echo.
    echo サービスを停止中...
    nssm stop "%SERVICE_NAME%"
    timeout /t 2 /nobreak >nul

    echo サービスを削除中...
    nssm remove "%SERVICE_NAME%" confirm
    timeout /t 2 /nobreak >nul
    echo.
)

REM --- サービスのインストール ---
echo サービスをインストール中...
echo.
echo   サービス名: %SERVICE_NAME%
echo   表示名: %DISPLAY_NAME%
echo   Python: %PYTHON_EXE%
echo   スクリプト: %SCRIPT_PATH%
echo   実行間隔: %INTERVAL%秒
echo.

nssm install "%SERVICE_NAME%" "%PYTHON_EXE%" "%SCRIPT_PATH%" --interval %INTERVAL%

if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] サービスのインストールに失敗しました。
    pause
    exit /b 1
)

REM --- サービス設定 ---
echo サービスを設定中...

REM 作業ディレクトリ
nssm set "%SERVICE_NAME%" AppDirectory "%PROJECT_DIR%"

REM 表示名
nssm set "%SERVICE_NAME%" DisplayName "%DISPLAY_NAME%"

REM 説明
nssm set "%SERVICE_NAME%" Description "EC Auto - Inventory Sync Daemon"

REM スタートアップタイプ（自動）
nssm set "%SERVICE_NAME%" Start SERVICE_AUTO_START

REM ログ設定
nssm set "%SERVICE_NAME%" AppStdout "%PROJECT_DIR%\logs\sync_inventory_stdout.log"
nssm set "%SERVICE_NAME%" AppStderr "%PROJECT_DIR%\logs\sync_inventory_stderr.log"

REM 再起動設定（失敗時に自動再起動）
nssm set "%SERVICE_NAME%" AppExit Default Restart
nssm set "%SERVICE_NAME%" AppRestartDelay 60000

echo [OK] サービスの設定が完了しました
echo.

REM --- サービスの開始 ---
choice /C YN /M "サービスを今すぐ開始しますか？"
if errorlevel 2 goto skip_start
if errorlevel 1 (
    echo.
    echo サービスを開始中...
    nssm start "%SERVICE_NAME%"

    REM 少し待機してから状態確認
    timeout /t 2 /nobreak >nul

    nssm status "%SERVICE_NAME%" | find "SERVICE_RUNNING" >nul
    if errorlevel 1 (
        echo [ERROR] サービスの開始に失敗しました
    ) else (
        echo [OK] サービスが開始しました
    )
)

:skip_start
echo.
echo ================================================================
echo インストール完了
echo ================================================================
echo.
echo サービス管理コマンド:
echo   状態確認: nssm status %SERVICE_NAME%
echo   開始:     nssm start %SERVICE_NAME%
echo   停止:     nssm stop %SERVICE_NAME%
echo   再起動:   nssm restart %SERVICE_NAME%
echo   削除:     nssm remove %SERVICE_NAME% confirm
echo.
echo ログファイル:
echo   アプリ:   %PROJECT_DIR%\logs\sync_inventory.log
echo   標準出力: %PROJECT_DIR%\logs\sync_inventory_stdout.log
echo   標準エラー: %PROJECT_DIR%\logs\sync_inventory_stderr.log
echo.
pause
