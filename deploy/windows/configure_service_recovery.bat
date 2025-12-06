@echo off
chcp 65001 >nul
REM ================================================================
REM EC Auto - サービス回復設定スクリプト
REM
REM 機能:
REM - 失敗時の自動再起動設定
REM - 遅延起動設定（ネットワーク起動後）
REM - 依存関係の設定
REM ================================================================

echo ================================================================
echo EC Auto - サービス回復設定
echo ================================================================
echo.

set SERVICE_NAME=ECAutoSyncInventory

REM --- サービスの存在確認 ---
sc query "%SERVICE_NAME%" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] サービス "%SERVICE_NAME%" が見つかりません。
    echo 先にサービスをインストールしてください。
    pause
    exit /b 1
)

echo [OK] サービスが見つかりました
echo.

REM --- 遅延起動の設定 ---
echo 遅延起動を設定中...
sc config "%SERVICE_NAME%" start= delayed-auto
if %ERRORLEVEL% EQU 0 (
    echo [OK] 遅延起動を設定しました（ネットワーク起動後に開始）
) else (
    echo [WARNING] 遅延起動の設定に失敗しました
)
echo.

REM --- 失敗時の回復設定 ---
echo 失敗時の回復アクションを設定中...

REM 1回目の失敗: 1分後に再起動
REM 2回目の失敗: 2分後に再起動
REM 3回目以降: 5分後に再起動
sc failure "%SERVICE_NAME%" reset= 86400 actions= restart/60000/restart/120000/restart/300000

if %ERRORLEVEL% EQU 0 (
    echo [OK] 失敗時の回復アクションを設定しました
    echo   - 1回目の失敗: 1分後に再起動
    echo   - 2回目の失敗: 2分後に再起動
    echo   - 3回目以降: 5分後に再起動
    echo   - リセット期間: 24時間
) else (
    echo [WARNING] 回復アクションの設定に失敗しました
)
echo.

REM --- 依存関係の設定 ---
echo ネットワーク依存関係を設定中...
nssm set "%SERVICE_NAME%" DependOnService Tcpip Dnscache

if %ERRORLEVEL% EQU 0 (
    echo [OK] ネットワーク依存関係を設定しました
    echo   - TCP/IP
    echo   - DNS Client
) else (
    echo [WARNING] 依存関係の設定に失敗しました（既に設定済みの可能性）
)
echo.

REM --- 設定確認 ---
echo ================================================================
echo 現在の設定
echo ================================================================
sc qc "%SERVICE_NAME%"
echo.
sc qfailure "%SERVICE_NAME%"
echo.

echo ================================================================
echo 設定完了
echo ================================================================
echo.
echo Windows再起動後の挙動:
echo   1. Windowsが起動
echo   2. ネットワークサービス（TCP/IP、DNS）が起動
echo   3. 遅延起動タイマー（約2分）
echo   4. ECAutoSyncInventory サービスが自動起動
echo.
echo サービス異常終了時の挙動:
echo   - 自動的に再起動を試みます
echo   - 1回目: 1分後
echo   - 2回目: 2分後
echo   - 3回目以降: 5分後
echo.
pause
