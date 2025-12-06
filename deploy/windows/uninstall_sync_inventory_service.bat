@echo off
chcp 65001 >nul
REM ================================================================
REM EC Auto - 在庫同期デーモン Windowsサービスアンインストールスクリプト
REM ================================================================

echo ================================================================
echo EC Auto - 在庫同期デーモン サービスアンインストール
echo ================================================================
echo.

set SERVICE_NAME=ECAutoSyncInventory

REM --- NSSMの確認 ---
where nssm >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] NSSMが見つかりません。
    pause
    exit /b 1
)

REM --- サービスの確認 ---
sc query "%SERVICE_NAME%" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [情報] サービス "%SERVICE_NAME%" は存在しません。
    pause
    exit /b 0
)

echo サービス "%SERVICE_NAME%" を削除します。
echo.
choice /C YN /M "本当に削除しますか？"
if errorlevel 2 (
    echo キャンセルしました。
    pause
    exit /b 0
)

echo.
echo サービスを停止中...
nssm stop "%SERVICE_NAME%"
timeout /t 2 /nobreak >nul

echo サービスを削除中...
nssm remove "%SERVICE_NAME%" confirm

if %ERRORLEVEL% EQU 0 (
    echo [OK] サービスが削除されました
) else (
    echo [ERROR] サービスの削除に失敗しました
)

echo.
pause
