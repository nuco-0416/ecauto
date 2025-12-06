@echo off
REM ============================================================
REM ヘルスチェック スケジュールタスク セットアップ
REM ============================================================
REM
REM このスクリプトは、サービスヘルスチェックを定期的に実行する
REM Windowsスケジュールタスクを登録します。
REM
REM 登録されるタスク:
REM   1. ヘルスチェック（5分ごと）
REM   2. 日次レポート（毎日9:00）
REM
REM 前提条件:
REM   - 管理者権限で実行
REM
REM ============================================================

REM 管理者権限チェック
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo.
    echo ============================================================
    echo エラー: このスクリプトは管理者権限で実行する必要があります
    echo ============================================================
    echo.
    echo 右クリック → 「管理者として実行」で実行してください
    echo.
    pause
    exit /b 1
)

echo ============================================================
echo ヘルスチェック スケジュールタスク セットアップ
echo ============================================================
echo.

REM パスを設定
set PYTHON_EXE=C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe
set HEALTH_CHECK_SCRIPT=C:\Users\hiroo\Documents\GitHub\ecauto\deploy\windows\health_check.py

REM スクリプトの存在を確認
if not exist "%PYTHON_EXE%" (
    echo ❌ Python実行ファイルが見つかりません: %PYTHON_EXE%
    pause
    exit /b 1
)

if not exist "%HEALTH_CHECK_SCRIPT%" (
    echo ❌ ヘルスチェックスクリプトが見つかりません: %HEALTH_CHECK_SCRIPT%
    pause
    exit /b 1
)

echo ✅ 前提条件チェック完了
echo.

REM ============================================================
REM タスク1: ヘルスチェック（5分ごと）
REM ============================================================

echo [1/2] ヘルスチェックタスクを登録中...

REM 既存のタスクを削除（エラーは無視）
schtasks /Delete /TN "ECAutoHealthCheck" /F >nul 2>&1

REM 新しいタスクを作成
schtasks /Create ^
    /TN "ECAutoHealthCheck" ^
    /TR "\"%PYTHON_EXE%\" \"%HEALTH_CHECK_SCRIPT%\"" ^
    /SC MINUTE ^
    /MO 5 ^
    /RU "SYSTEM" ^
    /RL HIGHEST ^
    /F

if %errorLevel% equ 0 (
    echo   ✅ ヘルスチェックタスクを登録しました（5分ごと）
) else (
    echo   ❌ ヘルスチェックタスクの登録に失敗しました
    pause
    exit /b 1
)

echo.

REM ============================================================
REM タスク2: 日次レポート（毎日9:00）
REM ============================================================

echo [2/2] 日次レポートタスクを登録中...

REM 既存のタスクを削除（エラーは無視）
schtasks /Delete /TN "ECAutoDailyReport" /F >nul 2>&1

REM 新しいタスクを作成
schtasks /Create ^
    /TN "ECAutoDailyReport" ^
    /TR "\"%PYTHON_EXE%\" \"%HEALTH_CHECK_SCRIPT%\" --daily-report" ^
    /SC DAILY ^
    /ST 09:00 ^
    /RU "SYSTEM" ^
    /RL HIGHEST ^
    /F

if %errorLevel% equ 0 (
    echo   ✅ 日次レポートタスクを登録しました（毎日9:00）
) else (
    echo   ❌ 日次レポートタスクの登録に失敗しました
    pause
    exit /b 1
)

echo.

REM ============================================================
REM 登録結果を確認
REM ============================================================

echo ============================================================
echo 登録されたタスク
echo ============================================================
echo.

schtasks /Query /TN "ECAutoHealthCheck" /FO LIST
echo.
schtasks /Query /TN "ECAutoDailyReport" /FO LIST

echo.
echo ============================================================
echo セットアップ完了
echo ============================================================
echo.
echo 以下のタスクが登録されました:
echo   1. ECAutoHealthCheck - サービスヘルスチェック（5分ごと）
echo   2. ECAutoDailyReport - 日次レポート送信（毎日9:00）
echo.
echo タスクの確認:
echo   - タスクスケジューラを開く
echo   - または「schtasks /Query /TN "ECAutoHealthCheck"」を実行
echo.
echo タスクの削除:
echo   schtasks /Delete /TN "ECAutoHealthCheck" /F
echo   schtasks /Delete /TN "ECAutoDailyReport" /F
echo.

pause
