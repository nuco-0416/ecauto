# Windows 本番環境デプロイガイド

マルチプラットフォーム対応デーモン監視システムのセットアップガイドです。

## 📋 実装完了内容

### ✅ Phase 1: プラットフォーム抽象化層
- **scheduler/platform_uploaders/uploader_interface.py** - 共通インターフェース
- **scheduler/platform_uploaders/base_uploader.py** - BASE用実装
- **scheduler/platform_uploaders/ebay_uploader.py** - eBay用（スケルトン）
- **scheduler/platform_uploaders/yahoo_uploader.py** - Yahoo!用（スケルトン）
- **scheduler/platform_uploaders/uploader_factory.py** - ファクトリーパターン

### ✅ Phase 2: マルチプラットフォーム対応デーモン
- **scheduler/upload_daemon.py** - DaemonBase継承、通知統合

### ✅ Phase 3: 設定ファイル
- **config/platforms.json** - プラットフォーム別設定

---

## 🚀 クイックスタート（手動実行）

### 1. BASE アップロードデーモンを起動

```bash
cd C:\Users\hiroo\Documents\GitHub\ecauto

# 60秒ごとにチェック、バッチサイズ10
.\venv\Scripts\python.exe scheduler\upload_daemon.py --platform base --interval 60 --batch-size 10
```

### 2. ログ確認

```bash
# リアルタイムでログ確認（PowerShell）
Get-Content logs\upload_scheduler_base.log -Wait

# 最新100行を表示
Get-Content logs\upload_scheduler_base.log -Tail 100
```

---

## 🔧 Windowsサービス化（NSSM使用）

### 前提条件

1. **NSSMのインストール**
   - https://nssm.cc/download から最新版をダウンロード
   - **推奨配置先（以下のいずれか）：**
     - `C:\Windows\System32\nssm.exe` （システム全体で使用可能）
     - `deploy/windows/nssm.exe` （プロジェクト内）
   - ✅ スクリプトが自動検出するため、どちらでもOK
   - ℹ️ 既に `C:\Windows\System32\nssm.exe` に配置済みの場合は何もする必要なし

2. **管理者権限**
   - コマンドプロンプトを右クリック → 「管理者として実行」

### 🆕 自動セットアップ（推奨）

自動セットアップスクリプトを使用すると、サービスとヘルスチェックシステムを一括でインストールできます：

```batch
cd C:\Users\hiroo\Documents\GitHub\ecauto\deploy\windows

REM 1. サービスをインストール（管理者権限で実行）
setup_services.bat

REM 2. ヘルスチェックシステムをセットアップ
setup_health_check.bat
```

これで以下が自動的に設定されます：
- ✅ Windowsサービスとして登録（ECAutoUploadScheduler-BASE）
- ✅ 自動起動設定（遅延起動）
- ✅ 失敗時の自動再起動設定
- ✅ ヘルスチェック監視（5分ごと）
- ✅ 日次レポート（毎日9:00）

**設定内容をカスタマイズする場合:**

[config/platforms.json](../../config/platforms.json) を編集してから `setup_services.bat` を実行してください。

```json
{
  "platforms": {
    "base": {
      "enabled": true,
      "interval_seconds": 60,
      "batch_size": 10,
      "business_hours": {"start": 6, "end": 23}
    }
  }
}
```

---

### 📝 手動セットアップ（高度な設定）

自動セットアップで対応できない場合のみ、手動でセットアップします：

```batch
cd C:\Users\hiroo\Documents\GitHub\ecauto\deploy\windows

REM サービスをインストール
nssm install ECAutoUploadScheduler-BASE ^
    "C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe" ^
    "C:\Users\hiroo\Documents\GitHub\ecauto\scheduler\upload_daemon.py" ^
    --platform base ^
    --interval 60 ^
    --batch-size 10 ^
    --start-hour 6 ^
    --end-hour 23

REM 作業ディレクトリを設定
nssm set ECAutoUploadScheduler-BASE AppDirectory "C:\Users\hiroo\Documents\GitHub\ecauto"

REM 表示名を設定
nssm set ECAutoUploadScheduler-BASE DisplayName "EC Auto - BASE Upload"

REM ログファイルを設定
nssm set ECAutoUploadScheduler-BASE AppStdout "C:\Users\hiroo\Documents\GitHub\ecauto\logs\upload_scheduler_base_service.log"
nssm set ECAutoUploadScheduler-BASE AppStderr "C:\Users\hiroo\Documents\GitHub\ecauto\logs\upload_scheduler_base_service_error.log"

REM 自動起動を有効化（遅延起動）
nssm set ECAutoUploadScheduler-BASE Start SERVICE_DELAYED_AUTO_START

REM 失敗時の自動再起動を設定（1分/2分/5分で3回リトライ）
sc failure ECAutoUploadScheduler-BASE reset= 86400 actions= restart/60000/restart/120000/restart/300000

REM サービスを起動
nssm start ECAutoUploadScheduler-BASE

REM 状態確認
nssm status ECAutoUploadScheduler-BASE
```

---

## 📊 サービス管理コマンド

### 状態確認

```batch
REM サービスの実行状態を確認
nssm status ECAutoUploadScheduler-BASE

REM 詳細な設定を確認
sc qc ECAutoUploadScheduler-BASE

REM 失敗時の再起動設定を確認
sc qfailure ECAutoUploadScheduler-BASE
```

### サービスの停止

```batch
nssm stop ECAutoUploadScheduler-BASE
```

### サービスの再起動

**重要**: コード修正後は必ず再起動してください

```batch
nssm restart ECAutoUploadScheduler-BASE
```

### サービスの削除

```batch
nssm stop ECAutoUploadScheduler-BASE
nssm remove ECAutoUploadScheduler-BASE confirm
```

### ログ確認

```batch
REM リアルタイムでログを確認（PowerShell）
Get-Content C:\Users\hiroo\Documents\GitHub\ecauto\logs\upload_scheduler_base.log -Wait

REM 最新50行を表示
Get-Content C:\Users\hiroo\Documents\GitHub\ecauto\logs\upload_scheduler_base.log -Tail 50
```

---

## 🏥 ヘルスチェックシステム

### 概要

ヘルスチェックシステムは、Windowsサービスの状態を定期的に監視し、異常時に自動復旧を試みます。

### セットアップ

```batch
cd C:\Users\hiroo\Documents\GitHub\ecauto\deploy\windows

REM 管理者権限で実行
setup_health_check.bat
```

これで以下のタスクが登録されます：
- **ECAutoHealthCheck**: 5分ごとにサービス状態をチェック
- **ECAutoDailyReport**: 毎日9:00にChatworkへレポート送信

### ヘルスチェックの動作

1. **サービス状態確認**: 5分ごとに全サービスの状態をチェック
2. **自動再起動**: 停止しているサービスを自動的に再起動
3. **Chatwork通知**: 異常検出時に通知送信
4. **ログ記録**: `logs/health_check.log` に結果を記録

### タスクスケジューラー管理

```batch
REM タスク状態を確認
schtasks /Query /TN "ECAutoHealthCheck" /FO LIST
schtasks /Query /TN "ECAutoDailyReport" /FO LIST

REM タスクを無効化
schtasks /Change /TN "ECAutoHealthCheck" /DISABLE

REM タスクを有効化
schtasks /Change /TN "ECAutoHealthCheck" /ENABLE

REM タスクを削除
schtasks /Delete /TN "ECAutoHealthCheck" /F
schtasks /Delete /TN "ECAutoDailyReport" /F
```

---

## 🔔 Chatwork通知の設定

### 1. notifications.jsonを作成

```bash
cd C:\Users\hiroo\Documents\GitHub\ecauto
copy config\notifications.json.example config\notifications.json
```

### 2. APIトークンとルームIDを設定

[config/notifications.json](../../config/notifications.json) を編集：

```json
{
  "enabled": true,
  "method": "chatwork",
  "chatwork": {
    "api_token": "YOUR_API_TOKEN_HERE",
    "room_id": "YOUR_ROOM_ID_HERE"
  },
  "events": {
    "daemon_start": true,
    "daemon_stop": true,
    "task_failure": true
  }
}
```

### 通知イベント

以下のタイミングで通知が送信されます：
- デーモン起動時
- デーモン停止時
- タスク失敗時
- 失敗率が高い時（失敗 > 成功）

---

## 🌐 新規プラットフォーム追加手順

### 例：Mercariを追加する場合

#### 1. アップローダークラスを実装

[scheduler/platform_uploaders/mercari_uploader.py](../../scheduler/platform_uploaders/mercari_uploader.py) を作成：

```python
from scheduler.platform_uploaders.uploader_interface import UploaderInterface

class MercariUploader(UploaderInterface):
    def __init__(self, account_id: str):
        self.account_id = account_id
        # Mercari APIクライアントを初期化

    @property
    def platform_name(self) -> str:
        return 'mercari'

    def upload_item(self, item_data):
        # Mercari API実装
        pass

    # その他のメソッドを実装...
```

#### 2. ファクトリーに登録

[scheduler/platform_uploaders/uploader_factory.py](../../scheduler/platform_uploaders/uploader_factory.py) を編集：

```python
from scheduler.platform_uploaders.mercari_uploader import MercariUploader

class UploaderFactory:
    _uploaders = {
        'base': BaseUploader,
        'ebay': eBayUploader,
        'yahoo': YahooUploader,
        'mercari': MercariUploader,  # ← 追加
    }
```

#### 3. 設定ファイルを更新

[config/platforms.json](../../config/platforms.json) に追加：

```json
{
  "platforms": {
    "mercari": {
      "enabled": true,
      "service_name": "ECAutoUploadScheduler-Mercari",
      "display_name": "EC Auto - Mercari Upload",
      "interval_seconds": 60,
      "batch_size": 10,
      "business_hours": {
        "start": 6,
        "end": 23
      }
    }
  }
}
```

#### 4. サービスをインストール

```batch
nssm install ECAutoUploadScheduler-Mercari ^
    "C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe" ^
    "C:\Users\hiroo\Documents\GitHub\ecauto\scheduler\upload_daemon.py" ^
    --platform mercari ^
    --interval 60 ^
    --batch-size 10

nssm start ECAutoUploadScheduler-Mercari
```

これで完了！新規プラットフォームが追加されました。

---

## 🐛 トラブルシューティング

### サービスが起動しない

1. **ログファイルを確認**
   ```batch
   REM デーモンのログ
   type C:\Users\hiroo\Documents\GitHub\ecauto\logs\upload_scheduler_base.log

   REM ヘルスチェックのログ
   type C:\Users\hiroo\Documents\GitHub\ecauto\logs\health_check.log
   ```

2. **Pythonパスを確認**
   ```batch
   C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe --version
   ```

3. **手動実行でテスト**
   ```batch
   cd C:\Users\hiroo\Documents\GitHub\ecauto
   .\venv\Scripts\python.exe scheduler\upload_daemon.py --platform base --interval 60
   ```

4. **NSSMの設定を確認**
   ```batch
   nssm get ECAutoUploadScheduler-BASE Application
   nssm get ECAutoUploadScheduler-BASE AppParameters
   nssm get ECAutoUploadScheduler-BASE AppDirectory
   ```

### scheduled_at / scheduled_time エラーが出る

**症状**: `sqlite3.OperationalError: no such column: scheduled_at`

**原因**: データベース列名は `scheduled_time` ですが、一部のコードで誤って `scheduled_at` を使用

**対処**:
1. コードが最新版か確認
2. サービスを再起動して修正を反映
   ```batch
   nssm restart ECAutoUploadScheduler-BASE
   ```

### 通知が届かない

1. **設定ファイルを確認**
   ```batch
   type config\notifications.json
   ```

2. **APIトークンをテスト**
   ```batch
   .\venv\Scripts\python.exe -c "from shared.utils.notifier import Notifier; n = Notifier(); n.send('テスト', 'テストメッセージ')"
   ```

### アップロードが失敗する

1. **キュー状態を確認**
   ```batch
   .\venv\Scripts\python.exe scheduler\scripts\check_queue.py --status failed --limit 20
   ```

2. **DBを確認**
   ```batch
   .\venv\Scripts\python.exe -c "from inventory.core.master_db import MasterDB; db = MasterDB(); print(db.get_product('B0TEST123'))"
   ```

### ヘルスチェックが動作しない

1. **タスクスケジューラーの状態を確認**
   ```batch
   schtasks /Query /TN "ECAutoHealthCheck" /V /FO LIST
   ```

2. **手動でヘルスチェックを実行**
   ```batch
   cd C:\Users\hiroo\Documents\GitHub\ecauto\deploy\windows
   python health_check.py
   ```

---

## 📚 関連ドキュメント

- [scheduled_tasks/README.md](../../scheduled_tasks/README.md) - デーモン基底クラスの詳細
- [config/platforms.json](../../config/platforms.json) - プラットフォーム設定
- [docs/work_log_20251121.md](../../docs/work_log_20251121.md) - 実証実験レポート

---

## 🎯 実装状況

| プラットフォーム | 状態 | 説明 |
|----------------|------|------|
| BASE | ✅ 完成 | 本番運用可能 |
| eBay | 🚧 スケルトン | API実装が必要 |
| Yahoo! | 🚧 スケルトン | API実装が必要 |

---

## 💡 次のステップ

### 即座に実行可能
1. BASEサービスを手動実行してテスト
2. NSSMでサービス化
3. Chatwork通知を設定

### 将来の拡張
1. eBay API統合
2. Yahoo!オークション API統合
3. ヘルスチェック監視スクリプト
4. 日次レポート自動送信

---

## 📝 備考

- **既存のdaemon.py**: 後方互換性のため残していますが、新しい`upload_daemon.py`の使用を推奨
- **プラットフォーム拡張**: `UploaderInterface`を実装するだけで簡単に追加可能
- **障害影響範囲**: プラットフォーム別サービスなので、BASE障害時もeBayは稼働継続

この設計により、将来的にどのプラットフォームが追加されても柔軟に対応できます！
