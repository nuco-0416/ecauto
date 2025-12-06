@echo off
REM ============================================================
REM Windows服務自動セットアップスクリプト
REM ============================================================
REM
REM 使用方法:
REM   setup_services.bat install     # サービスをインストール
REM   setup_services.bat uninstall   # サービスをアンインストール
REM   setup_services.bat restart     # サービスを再起動
REM
REM 前提条件:
REM   - 管理者権限で実行
REM   - nssm.exeがこのディレクトリに配置されている
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

REM スクリプトのディレクトリに移動
cd /d "%~dp0"

REM Pythonスクリプトを実行
C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe setup_services.py --%1

if %errorLevel% neq 0 (
    echo.
    echo ============================================================
    echo エラーが発生しました
    echo ============================================================
    pause
    exit /b 1
)

echo.
echo ============================================================
echo 処理が完了しました
echo ============================================================
pause
