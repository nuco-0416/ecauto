# クイックスタートガイド

新規リポジトリ `ecauto` のセットアップから基本的な使い方まで。

## 1. 初期セットアップ

### 仮想環境の有効化

```bash
cd C:\Users\hiroo\Documents\GitHub\ecauto
.\venv\Scripts\activate
```

### 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

### 環境変数の設定

`.env` ファイルを作成（`.env.example` をコピー）:

```bash
cp .env.example .env
```

`.env` ファイルを編集して、必要な認証情報を設定してください。

## 2. マスタDBの初期化

```bash
python inventory/scripts/init_master_db.py
```

成功すると、`inventory/data/master.db` が作成されます。

## 3. マスタDBの動作確認

テストスクリプトを実行:

```bash
python inventory/scripts/test_db.py
```

以下の機能がテストされます:
- 商品マスタの追加・取得・更新
- 出品情報の追加・取得・更新
- 出品キューの追加・取得
- アカウント設定の追加・取得

## 4. 既存データのインポート（初回移行時のみ）

**注意:** 初回移行時のみ使用。日常的な新規商品追加は「4.5. 新規商品登録」を参照してください。

### BASEマスタCSVをインポート

```bash
python inventory/scripts/import_from_csv.py \
  --source "C:\Users\hiroo\Documents\ama-cari\base\data\products_master_base.csv" \
  --platform base \
  --account-id base_account_1 \
  --type base_master
```

### 統合マスタCSVをインポート

```bash
python inventory/scripts/import_from_csv.py \
  --source "C:\Users\hiroo\Documents\ama-cari\data\product_master_integrated.csv" \
  --type integrated
```

## 4.5. 新規商品登録

**注意**: 本番運用では**「ルート1: 商品ソーシング」（[README.md](README.md#L88-L110) 参照）を推奨**します。
このセクションは以下の場合のみ使用してください：
- 初回セットアップ時のテスト
- ソーシング機能が利用できない場合
- 特定のASINのみを手動で追加したい場合

### パターンA: ASINリストから新規登録

ASINリストファイル（`asins.txt`）を作成:

```
B0CB5G8NRV
B0C77CKKVR
B0DYSGGJJW
```

スクリプトを実行:

```bash
python inventory/scripts/add_new_products.py \
  --asin-file asins.txt \
  --platform base \
  --account-id base_account_1 \
  --markup-rate 1.3 \
  --skip-existing
```

**パラメータ:**
- `--asin-file`: ASINリストファイル
- `--platform`: プラットフォーム名（base/mercari/yahoo/ebay）
- `--account-id`: アカウントID
- `--markup-rate`: Amazon価格に対する掛け率（デフォルト: 1.3）
- `--skip-existing`: 既存のASINをスキップ（推奨）

### パターンB: レガシーCSVから移行

既存プロジェクトのCSVデータを移行:

```bash
python inventory/scripts/import_legacy_data.py \
  --csv legacy_products.csv \
  --platform base \
  --account-id base_account_1 \
  --status pending \
  --skip-existing
```

**パラメータ:**
- `--csv`: CSVファイルのパス
- `--platform`: プラットフォーム名
- `--account-id`: アカウントID
- `--status`: pending（未出品）またはlisted（出品済み）
- `--skip-existing`: 既存のASINをスキップ（推奨）

詳細は [inventory/PRODUCT_REGISTRATION.md](inventory/PRODUCT_REGISTRATION.md) を参照してください。

## 4.7. BASE API同期（既存データの統合）

既存のBASE APIに登録済みの商品データをローカルマスタDBに統合します。

### ステップ1: データベースバックアップ

重要なDB操作の前に必ずバックアップを作成:

```bash
python inventory/scripts/backup_db.py
```

バックアップは `inventory/data/backups/` に保存されます。

### ステップ2: マージプレビュー

実際のデータ変更前に影響範囲を確認:

```bash
python inventory/scripts/preview_base_sync.py --account-id base_account_1
```

**確認内容:**
- 新規追加が必要な商品数
- 既存商品の更新数
- プラットフォーム名・アカウントID・ステータスの正規化が必要な件数
- ASIN重複の有無

### ステップ3: 本番マージ実行

プレビュー結果を確認後、本番マージを実行:

```bash
python inventory/scripts/sync_from_base_api.py --account-id base_account_1
```

**処理内容:**
1. プラットフォーム名の正規化（BASE → base）
2. アカウントIDの正規化（base_main → base_account_1）
3. ステータスの正規化（active → listed）
4. 既存商品のSKU・価格・在庫・公開状態を更新
5. 新規商品をマスタDBに追加

**DRYRUNモード（テスト用）:**

```bash
python inventory/scripts/sync_from_base_api.py --account-id base_account_1 --dry-run
```

### ステップ4: 不要レコードの削除（任意）

マージ後、以下の不要レコードを削除できます:
- 販売価格未設定のレコード
- Amazon価格未取得のレコード
- テストデータ（B0TEST*）

```bash
# プレビュー
python scheduler/scripts/cleanup_invalid_listings.py --dry-run

# 実行
python scheduler/scripts/cleanup_invalid_listings.py --yes
```

## 5. キャッシュマネージャーのテスト

Python対話モードでテスト:

```python
from inventory.core.cache_manager import AmazonProductCache

# キャッシュマネージャーを初期化
cache = AmazonProductCache()

# テストデータを保存
cache.set_product('B0TEST12345', {
    'asin': 'B0TEST12345',
    'title': 'テスト商品',
    'price': 5000,
    'in_stock': True
})

# データを取得
product = cache.get_product('B0TEST12345')
print(product)

# 統計情報を表示
stats = cache.get_stats()
print(stats)
```

## 6. BASE複数アカウント設定（Phase 2）

### アカウント設定ファイルの作成

**重要**: `platforms/base/accounts/account_config.json` は**唯一の信頼できる情報源（Single Source of Truth）**です。

すべてのコンポーネント（AccountManager、Scheduler、価格・在庫同期デーモン等）がこのファイルを参照します。

```bash
cd platforms/base/accounts
cp account_config.json.example account_config.json
```

`account_config.json` を編集して、使用するBASEアカウント情報を設定します。

**設定変更時の注意:**
- アカウントの有効/無効は `active` フラグで制御できます
- 設定を変更した場合は、**実行中のデーモンプロセスを必ず再起動**してください
- 設定はモジュールロード時に一度だけ評価されます

### 既存トークンのコピー

既存の `C:\Users\hiroo\Documents\ama-cari\base\base_token.json` から自動コピー:

```bash
python platforms/base/scripts/setup_account.py
```

### アカウント管理の動作確認

```bash
python platforms/base/scripts/test_accounts.py
```

成功すると、以下のような出力が表示されます:
- アカウント一覧
- トークン有無の確認
- アクティブアカウント数

詳細は [platforms/base/README.md](platforms/base/README.md) を参照してください。

## 6.5. トークン自動管理設定（Phase 2.5）

### 初回認証

各アカウントで初回OAuth認証を実行:

```bash
python platforms/base/scripts/get_authorization_code.py
```

**手順:**
1. アカウント番号を選択
2. 表示された認証URLをブラウザで開く
3. BASE アカウントで認証
4. リダイレクト先URLから `code=` パラメータの値をコピー
5. スクリプトに認証コードを入力

トークンは `platforms/base/accounts/tokens/` に自動保存されます。

### トークン状態確認

全アカウントのトークン状態を確認:

```bash
python platforms/base/scripts/check_token_status.py
```

期限切れや未設定のトークンがあれば警告が表示されます。

### トークン一括更新

全アカウントのトークンを一括更新:

```bash
python platforms/base/scripts/refresh_tokens.py
```

**推奨:** このスクリプトをタスクスケジューラ/cronで毎日実行してください。

### 自動更新機能のテスト

BaseAPIClientの自動トークン更新機能をテスト:

```bash
python platforms/base/scripts/test_auto_refresh.py
```

詳細は [platforms/base/TOKEN_MANAGEMENT.md](platforms/base/TOKEN_MANAGEMENT.md) を参照してください。

## 7. アップロードキュー・スケジューラー（Phase 3）

### 滞留商品のキュー追加（推奨）

マスタDBから`status='pending'`でキューに未登録のアイテムを自動検出してキューに追加:

```bash
# 滞留商品を自動検出してキューに追加（アカウント別並列スケジューリング）
python scheduler/scripts/add_pending_to_queue.py --yes
```

**主な機能:**
- `status='pending'`かつキューに未登録のアイテムを自動検出
- アカウント別に独立したスケジュールを作成（並列処理対応）
- 1日1000件上限に対応した時間分散スケジューリング
- 営業時間（6:00～23:00）内で均等分散

**オプション:**
- `--daily-limit`: 1日あたりの出品上限（デフォルト: 1000）
- `--start-date`: 開始日時（デフォルト: 翌日6:00）
- `--yes`: 確認をスキップして自動実行
- `--dry-run`: 実際には追加せず、プレビューのみ

**使用例:**

```bash
# プレビュー（DRY RUN）
python scheduler/scripts/add_pending_to_queue.py --dry-run

# カスタム設定で実行
python scheduler/scripts/add_pending_to_queue.py \
  --daily-limit 800 \
  --start-date "2025-11-25 06:00" \
  --yes
```

### キューへのアイテム追加（旧方式）

マスタDBから`status='pending'`のアイテムをキューに追加:

```bash
# 100件を時間分散（翌日6AM-11PM）でキューに追加
python scheduler/scripts/add_to_queue.py --distribute --limit 100
```

**オプション:**
- `--account-id`: アカウント指定（未指定時は自動割り当て）
- `--priority`: 優先度 1-20（デフォルト: 5）
- `--distribute`: 時間分散を行う

### キュー状態の確認

```bash
# 統計情報とアイテム一覧を表示
python scheduler/scripts/check_queue.py

# scheduled_time が到来したアイテムを表示
python scheduler/scripts/check_queue.py --show-due

# ステータス指定で表示
python scheduler/scripts/check_queue.py --status failed --limit 10
```

### スケジューラーデーモンの実行

キューを定期的にチェックして自動アップロード:

## 🆕 推奨：マルチアカウント並列処理マネージャー

複数のアカウントを並列処理する場合は、**マルチアカウントマネージャー**を使用します。

### 基本的な起動

```bash
# プロジェクトルートで実行
cd C:\Users\hiroo\Documents\GitHub\ecauto

# すべてのアカウントを並列起動
python scheduler/multi_account_manager.py start
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

**動作:**
- 各アカウント専用のプロセスを起動（並列処理）
- 60秒ごとにキューをチェック
- scheduled_timeが到来したアイテムを検出
- 営業時間内（6AM-11PM）のみ処理
- レート制限（2秒間隔）とリトライ（最大3回）
- プロセスが停止した場合、自動的に再起動
- Chatwork通知（設定時）
- Ctrl+Cで停止

**メリット:**
- ✅ アカウント間で完全に並列処理（2倍の処理速度）
- ✅ 一方のアカウントでエラーが発生しても他方は継続
- ✅ プロセスが停止した場合、自動的に再起動
- ✅ アカウント別ログで詳細な監視が可能

**ログファイル:**
```
logs/
├── upload_scheduler_base_base_account_1.log
├── upload_scheduler_base_base_account_2.log
└── multi_account_manager.lock
```

---

## 📌 後方互換：従来のデーモン

**重要:** 以下のデーモンは後方互換性のために残されていますが、新規環境では**マルチアカウントマネージャー**の使用を強く推奨します。

### upload_daemon.py（プラットフォーム単位）

```bash
# デフォルト設定（60秒ごとチェック、営業時間6AM-11PM）
python scheduler/upload_daemon.py --platform base

# カスタム設定
python scheduler/upload_daemon.py --platform base --interval 30 --batch-size 20
```

**⚠️ 注意:**
- アカウントフィルタがないため、scheduled_time順に処理されます
- 特定のアカウントに処理が偏る可能性があります
- マルチアカウント環境では**マルチアカウントマネージャーの使用を推奨**します

### daemon.py（旧版）

```bash
python scheduler/daemon.py --interval 30 --batch-size 20
```

> **非推奨**: 最も古いバージョンです。`multi_account_manager.py`を使用してください。

---

詳細は [scheduler/README.md](scheduler/README.md) を参照してください。

## 8. 🆕 定期実行デーモン（価格・在庫同期）

### 推奨：本番運用での自動同期

Amazon価格・在庫を定期的に取得し、BASEと自動同期するデーモンを実行します（**価格同期 + 在庫同期**の統合処理）：

```bash
# デフォルト（3時間ごとに自動同期）
python scheduled_tasks/sync_inventory_daemon.py

# 1時間ごとに同期
python scheduled_tasks/sync_inventory_daemon.py --interval 3600

# DRY RUNモード（テスト用）
python scheduled_tasks/sync_inventory_daemon.py --dry-run
```

### 処理内容

1. **価格同期**: Amazon価格を取得し、BASE出品価格を更新（掛け率1.3倍）
2. **在庫同期**: Amazon在庫状況に応じてBASE出品の公開/非公開を切り替え

### メリット

- ✅ **完全な同期**: 価格 + 在庫を一括で自動処理
- ✅ **定期自動実行**: 手動実行不要、常に最新状態を維持
- ✅ **ログ管理**: `logs/sync_inventory.log` に実行履歴を記録（10MB×5世代ローテーション）
- ✅ **SP-APIレート制限対策**: 並列処理を無効化してQuotaExceededエラーを回避
- ✅ **エラーハンドリング**: リトライ機能、通知機能（Chatwork等）

### ログ確認

```powershell
# リアルタイムでログを確認（Windows PowerShell）
Get-Content logs/sync_inventory.log -Tail 50 -Wait

# エラーのみ表示
Get-Content logs/sync_inventory.log -Wait | Select-String "ERROR"
```

### 詳細情報

詳細は [scheduled_tasks/README.md](scheduled_tasks/README.md) を参照してください。

## 9. その他の商品追加方法（代替手段）

### 手動でのASIN追加（SP-API）

**注意**: この方法は以下の場合のみ使用してください。**通常は「ルート1: 商品ソーシング」（README.md参照）を推奨します。**

- ソーシング機能が利用できない場合
- 特定のASINのみを追加したい場合
- 既存システム (`C:\Users\hiroo\Documents\ama-cari\am_sp-api\sp_api_credentials.py`) にSP-API認証情報が必要です

#### 手順

ASINリストファイル (`new_products.txt`) を作成:

```
B0CB5G8NRV
B0C77CKKVR
B0DYSGGJJW
```

SP-APIから商品情報を取得してマスタDBに追加（自動的にキューにも追加されます）:

```bash
python inventory/scripts/add_new_products.py \
  --asin-file new_products.txt \
  --platform base \
  --account-id base_account_1 \
  --markup-rate 1.3 \
  --use-sp-api \
  --skip-existing \
  --yes
```

**取得される情報:**
- 商品名（日本語・英語）
- 商品説明（日本語・英語）
- ブランド名
- 商品画像（最大6枚）
- 特徴（bullet points）
- 在庫状況
- Amazon価格（利用可能な場合）

**自動キュー追加機能:**
- 商品登録後、自動的にアップロードキューに追加されます
- `--yes`オプションで確認をスキップして自動実行
- `--no-queue`オプションでキュー追加をスキップ可能

## 次のステップ

- [x] Phase 1: 基盤構築完了
- [x] Phase 2: BASE複数アカウント対応完了
- [x] Phase 2.5: トークン自動管理完了
- [x] Phase 3: 出品キュー・スケジューラー完了
- [x] Phase 4: 価格・在庫同期リファクタ（SP-APIバッチ処理、並列処理）
- [ ] Phase 5: 他プラットフォーム統合
  - [x] eBay基本機能
  - [ ] Yahoo!オークション
  - [ ] メルカリ
- [ ] Phase 6: モニタリング・最適化

## トラブルシューティング

### ImportError: No module named 'inventory'

プロジェクトルートから実行していることを確認してください:

```bash
cd C:\Users\hiroo\Documents\GitHub\ecauto
python inventory/scripts/init_master_db.py
```

### データベースが見つからない

`inventory/data/` ディレクトリが存在することを確認:

```bash
mkdir -p inventory/data
python inventory/scripts/init_master_db.py
```

### SP-API認証エラー

`.env` ファイルに正しい認証情報が設定されているか確認:

```bash
cat .env
```

必要な認証情報:
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `SP_API_REFRESH_TOKEN`
- `SP_API_LWA_APP_ID`
- `SP_API_LWA_CLIENT_SECRET`

## ヘルプ

各スクリプトのヘルプを表示:

```bash
python inventory/scripts/import_from_csv.py --help
```
