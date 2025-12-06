# Upload Scheduler

BASE商品の時間分散アップロードとキュー管理システム

## 概要

Phase 3で実装した、出品アイテムのスケジュール管理と自動アップロード機能を提供します。

### 主な機能

- **マルチアカウント並列処理**: 各アカウントが独立したプロセスで並列動作（**推奨**）
- **時間分散アップロード**: 6AM-11PM（JST）に均等分散してアップロード
- **複数アカウント自動振り分け**: 日次上限1000件を考慮して自動割り当て
- **レート制限管理**: API呼び出し間隔を2秒確保
- **自動リトライ**: エラー時に最大3回リトライ
- **自動再起動**: プロセスが停止した場合、自動的に再起動
- **優先度管理**: 緊急アップロードの優先処理
- **デーモン実行**: バックグラウンドでの自動処理
- **マルチプラットフォーム対応**: BASE、eBay、Yahoo!等への拡張可能

## アーキテクチャ

### 🆕 推奨：マルチアカウント並列処理

```
multi_account_manager.py (親プロセス)
├── upload_daemon_account.py --platform base --account base_account_1
├── upload_daemon_account.py --platform base --account base_account_2
├── upload_daemon_account.py --platform ebay --account ebay_account_1
└── upload_daemon_account.py --platform yahoo --account yahoo_account_1
```

各プロセスは独立して動作し、キューから**自分のアカウントのアイテムのみ**を処理します。

**メリット:**
- ✅ アカウント間で完全に並列処理（2倍の処理速度）
- ✅ 一方のアカウントでエラーが発生しても他方は継続
- ✅ アカウント別ログで詳細な監視が可能
- ✅ プロセスが停止した場合、自動的に再起動

### 📌 後方互換：単一プラットフォームデーモン

```
upload_daemon.py (単一プロセス)
  └── scheduled_time順に全アカウントのアイテムを処理
```

**注意:** scheduled_time順に処理するため、アカウント間で偏りが発生する可能性があります。
新規環境では**マルチアカウントマネージャー**の使用を強く推奨します。

---

## セットアップ

### 前提条件

- Phase 1: マスタDB初期化完了
- Phase 2: BASE複数アカウント設定完了
- Phase 2.5: トークン自動管理設定完了

### アカウント構成の設定

`scheduler/config/accounts_config.py` を編集：

```python
UPLOAD_ACCOUNTS = {
    'base': [
        'base_account_1',
        'base_account_2',
    ],
    # 将来の拡張用
    # 'ebay': ['ebay_account_1'],
    # 'yahoo': ['yahoo_account_1'],
}

DAEMON_CONFIG = {
    'interval_seconds': 60,  # チェック間隔（秒）
    'batch_size': 10,  # 1回の処理件数
    'business_hours_start': 6,  # 営業開始時刻（時）
    'business_hours_end': 23,  # 営業終了時刻（時）
}
```

**アカウント別設定（オプション）:**

特定のアカウントで設定を変更したい場合：

```python
ACCOUNT_SPECIFIC_CONFIG = {
    'base_account_1': {
        'batch_size': 15,  # account_1は高速処理
        'interval_seconds': 30,
    },
    'base_account_2': {
        'business_hours_start': 9,  # account_2は営業時間制限
        'business_hours_end': 18,
    },
}
```

**⚠️ 重要:**
- マルチアカウントマネージャーは**コマンドライン引数での設定変更に対応していません**
- 設定を変更する場合は`accounts_config.py`を編集後、**マネージャーを再起動**してください

```bash
# 1. マネージャーを停止
python scheduler/multi_account_manager.py stop

# 2. accounts_config.py を編集

# 3. マネージャーを再起動
python scheduler/multi_account_manager.py start
```

**代替手段:**
一時的に特定のアカウントだけ設定を変更したい場合は、個別起動も可能です：

```bash
# base_account_1のみ、カスタム設定で起動
python scheduler/upload_daemon_account.py \
  --platform base \
  --account base_account_1 \
  --batch-size 20 \
  --interval 30
```

ただし、個別起動時はマネージャーの自動再起動機能は使えません。

---

## 使い方

### 1. キューへのアイテム追加

マスタDBから`status='pending'`のアイテムをキューに追加します。

```bash
# 基本的な使い方（100件、時間分散あり）
python scheduler/scripts/add_to_queue.py --distribute --limit 100

# アカウント指定
python scheduler/scripts/add_to_queue.py --account-id base_account_1 --limit 50

# 優先度指定（1-20、デフォルト5）
python scheduler/scripts/add_to_queue.py --priority 10 --distribute --limit 100
```

**パラメータ:**
- `--platform`: プラットフォーム名（デフォルト: base）
- `--account-id`: アカウントID（未指定時は自動割り当て）
- `--limit`: 追加するアイテム数（デフォルト: 100）
- `--priority`: 優先度 1-20（デフォルト: 5）
- `--distribute`: 時間分散を行う（6AM-11PM）

**動作:**
1. マスタDBから`platform='base'`かつ`status='pending'`のアイテムを取得
2. 時間スロットを計算（翌日6時から17時間で均等分散）
3. アカウントを自動割り当て（各アカウントの日次上限1000件を考慮）
4. キューに追加（`scheduled_time`付き）

### 2. キューの状態確認

```bash
# 全体統計と最新10件を表示
python scheduler/scripts/check_queue.py

# scheduled_time が到来したアイテムを表示
python scheduler/scripts/check_queue.py --show-due --limit 20

# ステータス指定で表示
python scheduler/scripts/check_queue.py --status pending --limit 50
python scheduler/scripts/check_queue.py --status failed --limit 10
```

**パラメータ:**
- `--platform`: プラットフォーム名（デフォルト: base）
- `--status`: ステータスフィルタ（pending/uploading/success/failed）
- `--limit`: 表示件数（デフォルト: 10）
- `--show-due`: scheduled_time が到来したアイテムのみ表示

**表示内容:**
- 統計情報（pending/uploading/success/failed/合計）
- アイテム詳細（キューID、ASIN、アカウント、ステータス、予定時刻、エラーメッセージ等）

---

### 3. スケジューラーデーモンの実行

## 🆕 推奨：マルチアカウント並列処理マネージャー

複数のアカウントを並列処理する場合は、**マルチアカウントマネージャー**を使用します。

### 基本的な起動

```bash
# プロジェクトルートで実行
cd C:\Users\hiroo\Documents\GitHub\ecauto

# すべてのアカウントを並列起動
python scheduler/multi_account_manager.py start
```

### 起動時の出力例

```
============================================================
マルチアカウントアップロードマネージャー
============================================================

起動するプロセス数: 2

[START] base_base_account_1 (PID: 12345)
[START] base_base_account_2 (PID: 12346)

============================================================
[OK] 2個のプロセスを起動しました
============================================================

起動中のプロセス:

  [Running] base_base_account_1
    PID: 12345
    稼働時間: 0:00:05
    再起動回数: 0
    設定: batch_size=10, interval=60s

  [Running] base_base_account_2
    PID: 12346
    稼働時間: 0:00:05
    再起動回数: 0
    設定: batch_size=10, interval=60s

============================================================
プロセス監視を開始します
チェック間隔: 60秒
停止するには Ctrl+C を押してください
============================================================
```

### 管理コマンド

```bash
# ステータス確認
python scheduler/multi_account_manager.py status

# 全プロセスを停止
python scheduler/multi_account_manager.py stop

# 全プロセスを再起動
python scheduler/multi_account_manager.py restart
```

### 停止方法

**Ctrl + C** を押すと、すべてのプロセスが Graceful Shutdown されます。

```
シグナル 2 を受信しました。プロセスを停止します...

============================================================
すべてのプロセスを停止しています...
============================================================

[STOP] base_base_account_1 (PID: 12345) を停止します...
  [OK] 停止しました
[STOP] base_base_account_2 (PID: 12346) を停止します...
  [OK] 停止しました

============================================================
すべてのプロセスを停止しました
お疲れ様でした
============================================================
```

### ログファイル

アカウント別にログファイルが生成されます：

```
logs/
├── upload_scheduler_base_base_account_1.log
├── upload_scheduler_base_base_account_2.log
└── multi_account_manager.lock  # 重複起動防止用ロックファイル
```

### ログの監視

マルチアカウント環境では、複数のログファイルを同時に監視する専用スクリプトが用意されています。

#### リアルタイムログ監視

```bash
# すべてのアカウントのログをリアルタイムで監視
python scheduler/view_multi_logs.py

# 特定プラットフォームのログのみ監視
python scheduler/view_multi_logs.py --platform base

# 最新100行を表示してから監視開始
python scheduler/view_multi_logs.py --tail 100
```

**特徴:**
- 複数ログファイルを同時監視（tail -f のマルチファイル版）
- アカウント別に色分けして表示
- ログレベル（INFO/WARNING/ERROR）も色分け
- リアルタイム更新

**出力例:**
```
[base_account_1] 2025-11-28 13:39:15 INFO アップロード成功: ASIN B0TEST123
[base_account_2] 2025-11-28 13:39:17 INFO アップロード成功: ASIN B0TEST456
[base_account_1] 2025-11-28 13:39:20 ERROR アップロード失敗: ASIN B0TEST789
```

#### 個別ログファイルの確認

```bash
# Windows
type logs\upload_scheduler_base_base_account_1.log

# Linux/Mac
tail -f logs/upload_scheduler_base_base_account_1.log
```

---

### 単一アカウントでの起動（テスト用）

マネージャーを使わず、単一アカウントのみを起動することもできます：

```bash
# base_account_1のみ起動
python scheduler/upload_daemon_account.py --platform base --account base_account_1

# オプション指定
python scheduler/upload_daemon_account.py \
  --platform base \
  --account base_account_1 \
  --batch-size 15 \
  --interval 30 \
  --start-hour 8 \
  --end-hour 22
```

**パラメータ:**
- `--platform`: プラットフォーム名（**必須**: base/ebay/yahoo）
- `--account`: アカウントID（**必須**）
- `--interval`: チェック間隔（秒、デフォルト: 60）
- `--batch-size`: 1回の処理件数（デフォルト: 10）
- `--start-hour`: 営業開始時刻（デフォルト: 6）
- `--end-hour`: 営業終了時刻（デフォルト: 23）

---

## 📌 後方互換：従来の単一プラットフォームデーモン

**重要:** 以下のデーモンは後方互換性のために残されていますが、新規環境では**マルチアカウントマネージャー**の使用を強く推奨します。

### upload_daemon.py（プラットフォーム単位）

```bash
# デフォルト設定（60秒ごとチェック、バッチサイズ10）
python scheduler/upload_daemon.py --platform base

# カスタム設定
python scheduler/upload_daemon.py --platform base --interval 30 --batch-size 20
```

**パラメータ:**
- `--platform`: プラットフォーム名（**必須**: base/ebay/yahoo）
- `--interval`: チェック間隔（秒、デフォルト: 60）
- `--batch-size`: 1回の処理件数（デフォルト: 10）
- `--start-hour`: 営業開始時刻（デフォルト: 6）
- `--end-hour`: 営業終了時刻（デフォルト: 23）

**動作:**
1. 60秒ごとにキューをチェック
2. scheduled_timeが現在時刻を過ぎたアイテムを取得（最大10件）
3. **scheduled_time順**に処理（アカウントフィルタなし）
4. 営業時間内（6AM-11PM）のみ処理
5. 各アイテムをアップロード実行
   - レート制限（2秒間隔）
   - エラー時はリトライ（最大3回）
   - ステータス更新
   - Chatwork通知（設定時）
6. Ctrl+C でGraceful shutdown

**⚠️ 注意:**
- アカウントフィルタがないため、scheduled_time順に処理されます
- 特定のアカウントに処理が偏る可能性があります
- マルチアカウント環境では**マルチアカウントマネージャーの使用を推奨**します

### daemon.py（旧版）

```bash
python scheduler/daemon.py --interval 30 --batch-size 20
```

> **非推奨**: 最も古いバージョンです。`upload_daemon.py`または`multi_account_manager.py`を使用してください。

---

## ワークフロー例

### 日次アップロードの例（推奨）

```bash
# 1. キューに500件追加（翌日6AM-11PMに分散）
python scheduler/scripts/add_to_queue.py --distribute --limit 500

# 2. キュー状態を確認
python scheduler/scripts/check_queue.py

# 3. マルチアカウントマネージャーを起動（バックグラウンドで自動処理）
python scheduler/multi_account_manager.py start

# 4. 定期的に進捗確認
python scheduler/scripts/check_queue.py --status success
python scheduler/scripts/check_queue.py --status failed

# 5. ステータス確認
python scheduler/multi_account_manager.py status
```

### 緊急アップロードの例

```bash
# 優先度を高く設定（20）してすぐにアップロード
python scheduler/scripts/add_to_queue.py --priority 20 --limit 10

# scheduled_time が現在時刻になるため、デーモンが次のチェックで処理
# （営業時間内の場合、最大60秒以内に処理開始）
```

---

## キューステータス

### ステータス遷移

```
pending → uploading → success
                   → failed (retry後も失敗)
```

**ステータス詳細:**
- `pending`: キューに追加済み、scheduled_time 待ち
- `uploading`: アップロード処理中
- `success`: アップロード成功
- `failed`: 全リトライ失敗

### 優先度

- `1` (PRIORITY_LOW): 低優先度
- `5` (PRIORITY_NORMAL): 通常（デフォルト）
- `10` (PRIORITY_HIGH): 高優先度
- `20` (PRIORITY_URGENT): 緊急

同じ`scheduled_at`の場合、優先度が高いものから処理されます。

---

## 時間分散アルゴリズム

### 計算方法

```python
# 6AM-11PM = 17時間 = 1020分
total_minutes = 17 * 60

# アイテム数に応じて均等間隔を計算
interval_minutes = total_minutes / (count - 1)

# 各アイテムのscheduled_timeを計算
for i in range(count):
    offset_minutes = int(i * interval_minutes)
    scheduled_time = start_time + timedelta(minutes=offset_minutes)
```

**例:**
- 100件の場合: 約10.2分間隔
- 500件の場合: 約2分間隔
- 1020件の場合: 1分間隔

### アカウント自動割り当て

```python
# 1. 各アカウントの日次上限と使用状況を取得
# 2. 残り枠をプールに追加
# 3. ランダムシャッフルで均等分散
```

**例:**
- account_1: 上限1000、使用済み200 → 残り800枠
- account_2: 上限1000、使用済み500 → 残り500枠
- 合計: 1300枠利用可能

500件追加の場合、account_1とaccount_2にランダム分散（概ね均等）

---

## レート制限とリトライ

### レート制限

- API呼び出し間隔: **2秒**
- 前回のAPI呼び出しから2秒経過していない場合は自動的に待機

### リトライロジック

```python
# 最大3回リトライ
# エラー発生時は5秒待機後にリトライ
for retry in range(3):
    try:
        response = api_client.create_item(item_data)
        # 成功 → break
    except Exception as e:
        if retry < 2:
            time.sleep(5)  # 5秒待機
        else:
            # 全リトライ失敗 → status='failed'
```

---

## パフォーマンス

### 処理速度

- レート制限: 2秒/アイテム
- 理論値: 1800アイテム/時間
- リトライ込み実測値: 約1500アイテム/時間

### 並列処理の効果

**従来版（順次処理）:**
```
account_1: 113件 → 約2時間
account_2: 286件 → 約5時間
合計: 約7時間
```

**並列版（2プロセス）:**
```
account_1: 113件 → 約2時間 }
account_2: 286件 → 約5時間 } 並列実行
合計: 約5時間（最も遅いプロセスの時間）
```

**約2時間（28%）の短縮！**

### 日次上限

- 1アカウント: 1000アイテム/日
- 2アカウント: 2000アイテム/日
- 営業時間（17時間）で2000件 → 約118件/時間 → 十分に処理可能

### 推奨設定

- チェック間隔: 60秒（営業時間内で十分）
- バッチサイズ: 10-20件（レート制限考慮）
- トークン更新: 1日1回（Phase 2.5で自動化済み）

---

## トラブルシューティング

### キューにアイテムが追加されない

**原因:**
- マスタDBに`status='pending'`のアイテムがない
- アカウントの日次上限に達している

**対処:**
```bash
# マスタDBを確認
python inventory/scripts/test_db.py

# アカウント状態を確認
python platforms/base/scripts/check_token_status.py
```

### アップロードが失敗する

**原因:**
- トークンの期限切れ
- BASE APIエラー
- 商品データ不足

**対処:**
```bash
# 失敗したアイテムを確認
python scheduler/scripts/check_queue.py --status failed --limit 20

# トークンを更新
python platforms/base/scripts/refresh_tokens.py

# エラーメッセージを確認してデータ修正
```

### プロセスが起動しない（マルチアカウントマネージャー）

**原因:** Pythonのパスが正しくない

**解決策:** `multi_account_manager.py` でPythonの実行パスを確認

```python
python_exe = sys.executable  # 現在のPythonインタープリタを使用
```

### プロセスが自動再起動を繰り返す

**原因:** デーモン内でエラーが発生している

**解決策:** アカウント別ログファイルを確認

```bash
# Windows
type logs\upload_scheduler_base_base_account_1.log

# Linux/Mac
tail -f logs/upload_scheduler_base_base_account_1.log
```

### アカウント1が処理されない

**原因:**
- scheduled_time順に処理されるため、特定のアカウントに偏っている（`upload_daemon.py`使用時）
- アカウント構成が正しくない

**解決策:**
1. **マルチアカウントマネージャーを使用**（推奨）
2. `accounts_config.py` でアカウントIDが正しいか確認

```python
UPLOAD_ACCOUNTS = {
    'base': [
        'base_account_1',  # <- これがDBのaccount_idと一致するか確認
        'base_account_2',
    ],
}
```

### デーモンが営業時間外に処理してしまう

**原因:**
- `--start-hour`/`--end-hour`の設定ミス

**対処:**
```bash
# 営業時間を明示的に指定
python scheduler/upload_daemon.py --platform base --start-hour 6 --end-hour 23

# またはaccounts_config.pyで設定
```

### scheduled_timeが過去のアイテムが大量にある

**原因:**
- デーモンが停止していた
- 処理速度がアイテム追加速度に追いついていない

**対処:**
```bash
# マルチアカウントマネージャーで並列処理
python scheduler/multi_account_manager.py start

# またはバッチサイズを増やして高速処理（従来版）
python scheduler/upload_daemon.py --platform base --batch-size 50 --interval 30
```

---

## API リファレンス

### UploadQueueManager

```python
from scheduler.queue_manager import UploadQueueManager

manager = UploadQueueManager()

# 単一アイテムをキューに追加
manager.add_to_queue(
    asin='B0TEST12345',
    platform='base',
    account_id='base_account_1',  # Noneで自動割り当て
    priority=5,
    scheduled_time=datetime.now()  # Noneで自動計算
)

# バッチ追加（時間分散あり）
result = manager.add_batch_to_queue(
    asins=['B0TEST1', 'B0TEST2', ...],
    platform='base',
    priority=5,
    distribute_time=True
)

# キュー統計取得
stats = manager.get_queue_statistics(platform='base')

# scheduled_time到来アイテム取得
due_items = manager.get_scheduled_items_due(limit=10, platform='base')

# scheduled_time到来アイテム取得（アカウント指定）
due_items = manager.get_scheduled_items_due(
    limit=10,
    platform='base',
    account_id='base_account_1'  # アカウントフィルタ
)

# ステータス更新
manager.update_queue_status(
    queue_id=123,
    status='success',
    result_data={'platform_item_id': '456789'}
)
```

### MultiAccountUploadManager

```python
from scheduler.multi_account_manager import MultiAccountUploadManager

# マネージャー初期化
manager = MultiAccountUploadManager()

# 全アカウントを起動
manager.start_all()

# プロセス監視（自動再起動）
manager.monitor(check_interval=60)

# 全プロセスを停止
manager.shutdown_all()

# ステータス取得
status = manager.get_status()
# {
#   'total': 2,
#   'running': 2,
#   'stopped': 0,
#   'processes': {...}
# }
```

### UploadSchedulerAccountDaemon（アカウント別デーモン）

```python
from scheduler.upload_daemon_account import UploadSchedulerAccountDaemon

daemon = UploadSchedulerAccountDaemon(
    platform='base',
    account_id='base_account_1',  # アカウント指定（必須）
    interval_seconds=60,
    batch_size=10,
    business_hours_start=6,
    business_hours_end=23
)

# デーモン実行
daemon.run()  # Ctrl+Cで停止

# 停止
daemon.stop()
```

---

## 次のステップ

Phase 3完了後の拡張案:

- **Phase 4**: Amazon SP-API統合（価格・在庫自動同期） ✅ 完了
- **Phase 5**: 他プラットフォーム対応（eBay、Yahoo、Mercari）
- **Phase 6**: ダッシュボード・モニタリング機能

---

## 関連ドキュメント

- [QUICKSTART.md](../QUICKSTART.md) - 全体のセットアップガイド
- [platforms/base/TOKEN_MANAGEMENT.md](../platforms/base/TOKEN_MANAGEMENT.md) - トークン管理詳細
- [platforms/base/README.md](../platforms/base/README.md) - BASE API連携詳細
- ~~[MULTI_ACCOUNT_README.md](MULTI_ACCOUNT_README.md)~~ - **このファイルに統合されました**
