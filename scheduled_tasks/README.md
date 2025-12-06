# Scheduled Tasks - 定期実行デーモン

EC Autoの定期実行タスクを管理するディレクトリです。

## 📁 構成

```
scheduled_tasks/
├── daemon_base.py              # デーモン基底クラス
├── sync_inventory_daemon.py    # 在庫同期デーモン
├── config/
│   └── daemons.json           # デーモン設定ファイル
└── README.md
```

## 🚀 使い方

### 在庫同期デーモン

Amazon在庫・価格を定期的に取得し、BASEと同期します。

#### 基本的な実行

```bash
cd C:\Users\hiroo\Documents\GitHub\ecauto

# 1時間ごとに同期（デフォルト）
python scheduled_tasks/sync_inventory_daemon.py

# 30分ごとに同期
python scheduled_tasks/sync_inventory_daemon.py --interval 1800

# DRY RUNモード（テスト用）
python scheduled_tasks/sync_inventory_daemon.py --dry-run
```

#### オプション

| オプション | 説明 | デフォルト |
|-----------|------|-----------|
| `--interval` | 実行間隔（秒） | 3600（1時間） |
| `--platform` | プラットフォーム名 | base |
| `--dry-run` | DRY RUNモード | False |

#### ログ確認

ログは `logs/sync_inventory.log` に出力されます。

**基本的なログ確認:**

```bash
# ログをリアルタイムで確認（Linux/macOS）
tail -f logs/sync_inventory.log

# ログをリアルタイムで確認（Windows PowerShell）
Get-Content logs/sync_inventory.log -Wait

# 最後の50行から表示してリアルタイム確認（Windows PowerShell）
Get-Content logs/sync_inventory.log -Tail 50 -Wait
```

**ログのフィルタリング:**

```powershell
# SP-APIのバッチ処理ログだけ表示
Get-Content logs/sync_inventory.log -Wait | Select-String "バッチ"

# DEBUGログだけ表示（初期化処理の進捗確認）
Get-Content logs/sync_inventory.log -Wait | Select-String "\[DEBUG\]"

# エラーログだけ表示
Get-Content logs/sync_inventory.log -Wait | Select-String "ERROR"

# 特定のコンポーネントのログだけ表示
Get-Content logs/sync_inventory.log -Wait | Select-String "sp_api_client"
```

**ログの出力内容:**

- **初期化ログ**: 各コンポーネント（PriceSync、SP-APIクライアントなど）の初期化状況
- **バッチ処理ログ**: SP-APIリクエストの開始/完了、所要時間、成功/失敗件数
- **価格同期ログ**: 価格更新の処理状況と統計
- **在庫同期ログ**: 在庫状態の更新状況
- **エラーログ**: QuotaExceeded、接続エラー等の詳細

> **Tip**: デーモンが正常に動作しているかを確認するには、`Get-Content logs/sync_inventory.log -Tail 20 -Wait` で最新の20行を表示しながら監視するのがおすすめです。

## 🔔 通知機能

デーモンの起動・停止、エラー発生時などに通知を受け取ることができます。

> **注意:** LINE Notifyは2025年3月31日にサービス終了予定です。

### 対応通知方法

- **Chatwork** (推奨 - 日本で広く使われるビジネスチャット)
- Discord Webhook
- Slack Webhook
- Email (SMTP)
- Windows Event Log

### クイックスタート

1. **設定ファイルを作成**
   ```bash
   copy config\notifications.json.example config\notifications.json
   ```

2. **Chatwork APIトークンとルームIDを取得**
   - https://www.chatwork.com/ にログイン
   - 右上のアイコン > サービス連携 > API Token > 新しいトークンを発行
   - 通知したいルームのURLから `#!rid` の後の数字（ルームID）をコピー

3. **通知を有効化**
   ```json
   {
     "enabled": true,
     "method": "chatwork",
     "chatwork": {
       "api_token": "YOUR_API_TOKEN_HERE",
       "room_id": "YOUR_ROOM_ID_HERE"
     }
   }
   ```

詳細は [通知機能ガイド](../docs/notifications.md) を参照してください。

### 通知イベント

以下のイベントで通知を送信できます（config で個別に ON/OFF 可能）:

- `daemon_start`: デーモン起動時
- `daemon_stop`: デーモン停止時
- `task_success`: タスク成功時（基本的なタスク成功通知）
- `task_completion`: **タスク完了時に詳細レポートを通知**（処理件数、更新件数、次回実行予定時刻など）
- `task_failure`: タスク失敗時
- `retry_exhausted`: リトライ回数上限到達時
- `service_restart`: サービス再起動時

### 完了レポート通知（新機能）

`task_completion` イベントを有効にすると、各処理の完了時に詳細なレポートをChatworkに送信します。

#### 在庫同期デーモン (`sync_inventory_daemon.py`)

**送信される情報:**
- 所要時間
- 価格同期: 処理件数、更新件数、エラー件数
- 在庫同期: 処理件数、非公開化件数、公開化件数、エラー件数
- 次回実行予定時刻

#### アップロードスケジューラー (`upload_daemon.py`)

**送信される情報:**
- 処理件数
- 登録成功数
- 登録失敗数
- 残り件数（キュー内）
- 次回実行予定時刻

#### 設定例

```json
{
  "enabled": true,
  "method": "chatwork",
  "events": {
    "task_completion": true
  }
}
```

### アップロードスケジューラー

🆕 **新しいマルチプラットフォーム対応デーモン（推奨）:**

```bash
# 60秒ごとにキューをチェック（BASE）
python scheduler/upload_daemon.py --platform base --interval 60

# eBay用（将来）
python scheduler/upload_daemon.py --platform ebay --interval 60
```

**バックグラウンド実行（本番運用）:**

現在はフォアグラウンドでの手動テスト運用を実施中です。
将来的にWindowsタスクスケジューラーを使用した自動実行を計画しています。

> **注意**: 過去にNSSMを使用したサービス化を検討しましたが、現在は放棄しています。
> NSSM関連の問題が発生した場合は [deploy/windows/README_NSSM_deprecated.md](../deploy/windows/README_NSSM_deprecated.md) を参照してください。

詳細は [scheduler/README.md](../scheduler/README.md) を参照してください。

---

📌 **旧デーモン（後方互換性のため残存）:**

```bash
# 60秒ごとにキューをチェック
python scheduler/daemon.py --interval 60
```

> **注意**: 新規環境では `scheduler/upload_daemon.py` の使用を推奨します。

## 🔧 開発者向け

### 新しいデーモンを作成する

`daemon_base.py` を継承して、`execute_task()` メソッドを実装します。

```python
from scheduled_tasks.daemon_base import DaemonBase

class MyDaemon(DaemonBase):
    def __init__(self, interval_seconds: int = 3600):
        super().__init__(
            name='my_daemon',
            interval_seconds=interval_seconds
        )

    def execute_task(self) -> bool:
        """実行すべきタスク"""
        try:
            # タスク実装
            self.logger.info("タスク実行中...")
            return True
        except Exception as e:
            self.logger.error(f"エラー: {e}", exc_info=True)
            return False

# 実行
daemon = MyDaemon(interval_seconds=1800)
daemon.run()
```

### 設定ファイルの編集

`config/daemons.json` でデーモンの設定を管理できます。

```json
{
  "daemons": {
    "sync_inventory": {
      "enabled": true,
      "interval_seconds": 3600,
      "platform": "base"
    }
  }
}
```

## 📊 ログ

### ログファイル

- 場所: `logs/{daemon_name}.log`
- ローテーション: 10MB × 5ファイル
- フォーマット: `YYYY-MM-DD HH:MM:SS [LEVEL] name: message`

### ログレベル

- `INFO`: 通常の実行ログ
- `WARNING`: 警告（リトライ等）
- `ERROR`: エラー（スタックトレース付き）

## ⚙️ デプロイ

### Windows（手動起動）

コマンドプロンプトまたはPowerShellで実行します。

```batch
cd C:\Users\hiroo\Documents\GitHub\ecauto
.\venv\Scripts\python.exe scheduled_tasks\sync_inventory_daemon.py
```

停止するには `Ctrl+C` を押します。

### Windows（タスクスケジューラ化 - 計画中）

現在はフォアグラウンドでの手動テスト運用を実施中です。
将来的にWindowsタスクスケジューラーを使用した自動実行を計画しています。

> **注意**: 過去にNSSMを使用したサービス化を検討しましたが、現在は放棄しています。
> NSSM関連の問題が発生した場合は [../deploy/windows/README_NSSM_deprecated.md](../deploy/windows/README_NSSM_deprecated.md) を参照してください。

### Linux（systemd）

systemdでサービスとして登録できます（将来対応）。

```ini
# /etc/systemd/system/ecauto-sync.service
[Unit]
Description=EC Auto - Inventory Sync Daemon
After=network.target

[Service]
Type=simple
User=hiroo
WorkingDirectory=/home/hiroo/ecauto
ExecStart=/home/hiroo/ecauto/venv/bin/python \
    scheduled_tasks/sync_inventory_daemon.py --interval 3600
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# サービス有効化
sudo systemctl enable ecauto-sync.service

# サービス開始
sudo systemctl start ecauto-sync.service

# ステータス確認
sudo systemctl status ecauto-sync.service

# ログ確認
journalctl -u ecauto-sync.service -f
```

### Docker

Docker Composeで実行できます（将来対応）。

```yaml
# docker-compose.yml
version: '3.8'

services:
  sync-inventory:
    build: .
    command: python scheduled_tasks/sync_inventory_daemon.py --interval 3600
    volumes:
      - ./logs:/app/logs
      - ./inventory/data:/app/inventory/data
    env_file:
      - .env
    restart: unless-stopped
```

```bash
# 起動
docker-compose up -d sync-inventory

# ログ確認
docker-compose logs -f sync-inventory

# 停止
docker-compose down
```

## 🐛 トラブルシューティング

### デーモンが起動しない

1. Pythonパスを確認
   ```bash
   which python  # Linux/macOS
   where python  # Windows
   ```

2. 依存パッケージを確認
   ```bash
   pip list | grep -E "(requests|pandas)"
   ```

3. ログファイルを確認
   ```bash
   cat logs/sync_inventory.log
   ```

### エラーが頻発する

1. リトライ設定を調整
   - `max_retries`: リトライ回数（デフォルト: 3）
   - `retry_delay_seconds`: リトライ間隔（デフォルト: 60秒）

2. 実行間隔を調整
   ```bash
   # 2時間ごとに変更
   python scheduled_tasks/sync_inventory_daemon.py --interval 7200
   ```

### ログファイルが肥大化

ログローテーション設定を確認:
- 最大ファイルサイズ: 10MB
- 保持ファイル数: 5

古いログを削除:
```bash
rm logs/sync_inventory.log.*
```

## 📚 関連ドキュメント

- [高優先度機能_使い方ガイド.md](../高優先度機能_使い方ガイド.md) - 在庫同期・価格同期の詳細
- [QUICKSTART.md](../QUICKSTART.md) - 全体のセットアップガイド
- [進捗確認レポート_20251120.md](../進捗確認レポート_20251120.md) - 実装状況
