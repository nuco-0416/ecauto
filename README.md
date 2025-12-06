# EC Auto - 複数ECプラットフォーム統合管理システム

BASE、eBay、Yahoo!オークション、メルカリなど、複数のECプラットフォームを統合管理するシステムです。

## 特徴

- 🆕 **商品ソーシング自動化**: SellerSpriteから2000+件/日のASIN自動抽出・出品連携
- 🆕 **ブラウザ自動化**: PlaywrightによるAPIなしプラットフォーム対応（Amazon Business住所管理等）
- **中央集権型在庫管理**: SQLiteベースのマスタDBで全商品・出品を統一管理
- **Amazon情報キャッシュ**: SP-APIの情報をローカルキャッシュしてレート制限を回避
- **効率的な処理**: SP-APIバッチ取得（最大20倍高速化） + 複数ECアカウント並列同期
- **スケジュール出品**: 時間帯分散（6時〜23時JST）で露出を最大化
- **複数アカウント対応**: カテゴリ別の自動振り分けで1日の出品制限を回避
- **プラットフォーム横断**: 統一インターフェースで複数ECを管理

## プロジェクト構成

```
ecauto/
├── sourcing/              # 🆕 商品ソーシング（Phase 0/1完了）
│   ├── sources/          # ソース別実装（SellerSprite）
│   ├── scripts/          # 抽出・連携スクリプト
│   ├── data/             # sourcing.db、抽出ログ
│   └── docs/             # 実装レポート
│
├── inventory/             # 在庫・商品情報の中央管理
│   ├── core/             # コアロジック（DB、キャッシュ）
│   ├── models/           # データモデル
│   ├── data/             # SQLite DB、キャッシュデータ
│   └── scripts/          # 管理スクリプト
│
├── platforms/            # プラットフォーム別実装
│   ├── base/            # BASE EC
│   ├── ebay/            # eBay
│   ├── amazon_business/ # 🆕 Amazon Business（ブラウザ自動化）
│   ├── yahoo_auction/   # Yahoo!オークション
│   └── mercari/         # メルカリ
│
├── scheduler/           # 出品スケジューラー
│   ├── scripts/        # キュー管理スクリプト
│   └── upload_daemon.py # デーモンプロセス
│
├── scheduled_tasks/     # 🆕 定期実行デーモン
│   ├── daemon_base.py   # デーモン基底クラス
│   ├── sync_inventory_daemon.py # 在庫・価格同期デーモン
│   └── config/          # デーモン設定
│
├── shared/              # 共通ライブラリ
│   ├── amazon/          # Amazon SP-API関連
│   ├── utils/           # 汎用ユーティリティ
│   └── config/          # グローバル設定
│
└── docs/                # ドキュメント
```

## セットアップ

### 1. 仮想環境の作成・有効化

```bash
cd C:\Users\hiroo\Documents\GitHub\ecauto
python -m venv venv
.\venv\Scripts\activate
```

### 2. 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

### 3. マスタDBの初期化

```bash
python inventory/scripts/init_master_db.py
```

### 4. 環境変数の設定

`.env` ファイルを作成して必要な認証情報を設定:

```env
# Amazon SP-API
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
SP_API_REFRESH_TOKEN=your_refresh_token

# BASE API
BASE_CLIENT_ID=your_client_id
BASE_CLIENT_SECRET=your_client_secret
```

### 5. アカウント設定

**重要**: `platforms/base/accounts/account_config.json` が**唯一の信頼できる情報源（Single Source of Truth）**です。

すべてのコンポーネント（AccountManager、Scheduler、価格・在庫同期デーモン等）がこのファイルを参照します。

```bash
cd platforms/base/accounts
cp account_config.json.example account_config.json
# account_config.json を編集してアカウント情報を設定
```

**設定例:**
```json
{
  "accounts": [
    {
      "id": "base_account_1",
      "name": "在庫BAZAAR",
      "active": true,
      "credentials": { ... }
    },
    {
      "id": "base_account_2",
      "name": "バイヤー倉庫",
      "active": true,
      "credentials": { ... }
    }
  ]
}
```

**注意事項:**
- アカウントの有効/無効は `active` フラグで制御
- 設定変更後は**デーモンプロセスの再起動が必須**
- 詳細は [platforms/base/README.md](platforms/base/README.md) を参照

## 使用方法

### 🆕 ルート1: 商品ソーシングからの自動追加（推奨）

SellerSpriteから自動的にASIN候補を抽出し、出品キューまで一気通貫で追加：

```bash
# 1. SellerSpriteからASIN候補を大量抽出（2000+件/日）
python sourcing/scripts/extract_asins_bulk.py \
  --strategy segment \
  --segments "2500-5000,5000-10000,10000-20000" \
  --sales-min 300

# 2. master.dbへ自動連携（SP-APIで商品情報取得 + upload_queueに自動追加）
python sourcing/scripts/import_candidates_to_master.py
```

**パイプライン:**
```
SellerSprite → sourcing_candidates → master.db → upload_queue → BASE出品
            (extract)           (import)      (scheduler)
```

詳細は [sourcing/sources/sellersprite/USAGE.md](sourcing/sources/sellersprite/USAGE.md) を参照

---

### ルート2: ASINリストファイルからの追加

手動で用意したASINリストから追加：

```bash
# ASINリストファイル（asins.txt）を作成
# B0CB5G8NRV
# B0C77CKKVR
# ...

# SP-APIで商品情報取得してmaster.dbとupload_queueに追加
python inventory/scripts/add_new_products.py \
  --asin-file asins.txt \
  --platform base \
  --account-id base_account_1 \
  --use-sp-api \
  --yes
```

詳細は [QUICKSTART.md](QUICKSTART.md#45-新規商品登録) を参照

---

### ルート3: 既存データのインポート（初回移行時のみ）

```bash
# 既存のBASEマスタCSVをインポート
python inventory/scripts/import_from_csv.py \
  --source C:\Users\hiroo\Documents\ama-cari\base\data\products_master_base.csv \
  --platform base

# 既存のeBay出品をインポート
python inventory/scripts/import_existing_listings.py \
  --platform ebay
```

---

### スケジュール出品の実行

キューに追加されたアイテムを自動的に出品：

#### 🆕 推奨：マルチアカウント並列処理

複数のアカウントを並列処理する場合は、**マルチアカウントマネージャー**を使用します：

```bash
# すべてのアカウントを並列起動
python scheduler/multi_account_manager.py start

# ステータス確認
python scheduler/multi_account_manager.py status

# 停止
python scheduler/multi_account_manager.py stop
```

**メリット:**
- ✅ アカウント間で完全に並列処理（2倍の処理速度）
- ✅ 一方のアカウントでエラーが発生しても他方は継続
- ✅ プロセスが停止した場合、自動的に再起動

---

#### 📌 後方互換：従来のデーモン

**注意:** `upload_daemon.py`は後方互換性のために残されていますが、新規環境では**マルチアカウントマネージャー**の使用を推奨します。

```bash
# フォアグラウンド実行（テスト用）
python scheduler/upload_daemon.py --platform base
```

**⚠️ 制限事項:**
- scheduled_time順に処理するため、アカウント間で偏りが発生する可能性があります

---

詳細は [scheduler/README.md](scheduler/README.md) を参照

### 価格・在庫の同期

#### 🆕 推奨：定期実行デーモン（本番運用）

Amazon価格・在庫を定期的に取得し、BASEと自動同期します（**価格同期 + 在庫同期**の統合処理）：

```bash
# デフォルト（3時間ごとに自動同期）
python scheduled_tasks/sync_inventory_daemon.py

# 1時間ごとに同期
python scheduled_tasks/sync_inventory_daemon.py --interval 3600

# DRY RUNモード（テスト用）
python scheduled_tasks/sync_inventory_daemon.py --dry-run
```

**メリット**:
- ✅ **完全な同期**: 価格同期 + 在庫同期を自動実行
- ✅ **定期自動実行**: 手動実行不要、常に最新状態を維持
- ✅ **ログ管理**: `logs/sync_inventory.log` に実行履歴を記録（10MB×5世代ローテーション）
- ✅ **SP-APIレート制限対策**: 並列処理を無効化してQuotaExceededエラーを回避
- ✅ **エラーハンドリング**: リトライ機能、通知機能（Chatwork等）

**ログ確認**:
```powershell
# リアルタイムでログを確認（Windows PowerShell）
Get-Content logs/sync_inventory.log -Tail 50 -Wait

# エラーのみ表示
Get-Content logs/sync_inventory.log -Wait | Select-String "ERROR"
```

詳細は [scheduled_tasks/README.md](scheduled_tasks/README.md) を参照してください。

---

#### 📌 個別スクリプト実行（開発・テスト用）

価格同期のみを手動で実行する場合：

```bash
# 全アカウントの価格を同期
python platforms/base/scripts/sync_prices.py \
  --markup-ratio 1.3

# 特定アカウントのみ同期
python platforms/base/scripts/sync_prices.py \
  --markup-ratio 1.3 \
  --account base_account_1

# DRYRUNモード（実際の更新なし）
python platforms/base/scripts/sync_prices.py \
  --markup-ratio 1.3 \
  --dry-run
```

**注意**:
- ターミナル出力のみ（ログファイルなし）
- 価格同期のみ（在庫同期は含まれません）
- 本番運用では**定期実行デーモン**の使用を推奨

### 価格決定システム

🆕 **柔軟な価格戦略システム**を実装しました（2025-12-02完了）

価格計算ロジックを一元化し、設定ファイルで簡単に価格戦略を変更できるようになりました。

**主な機能**:
- ✅ **価格ロジックの一元化**: 複数ファイルに分散していた価格計算を統一モジュールに集約
- ✅ **柔軟な価格戦略**: YAMLファイルで簡単に戦略を切り替え（シンプルマークアップ、価格帯別など）
- ✅ **安全装置**: 異常価格の自動検知と補正機能
- ✅ **価格変更履歴**: すべての価格変更をデータベースに記録
- ✅ **後方互換性**: 既存のCLIオプション（`--markup-ratio`）を維持

**設定ファイル**: `config/pricing_strategy.yaml`

```yaml
# デフォルト戦略
default_strategy: "simple_markup"

strategies:
  simple_markup:
    markup_ratio: 1.3          # マークアップ率（30%利益）
    min_price_diff: 100        # 価格更新の最小差額
    round_to: 10               # 10円単位に丸める

  tiered_markup:               # 価格帯別マークアップ
    tiers:
      - max_price: 1000
        markup_ratio: 1.4      # 1000円以下は40%
      - max_price: 5000
        markup_ratio: 1.3      # 5000円以下は30%
```

**詳細**: [docs/PRICING_SYSTEM_REDESIGN.md](docs/PRICING_SYSTEM_REDESIGN.md) - 価格決定システムの完全なドキュメント

### ブラウザ自動化（Amazon Business）

🆕 **Playwrightベースのブラウザ自動化**を実装しました（2025-12-02完了）

APIが提供されていないプラットフォームに対して、ブラウザ自動化で操作を実現します。

**主な機能**:
- ✅ **セッション管理**: Chrome profileベースのログイン状態永続化（手動ログイン不要）
- ✅ **住所録クリーンアップ**: 指定した住所以外を自動削除（設定ファイルで保護リスト管理）
- ✅ **マルチアカウント対応**: アカウント別にプロファイルを分離管理

**使用例**:

```bash
# 初回ログイン（セッション作成）
python platforms/amazon_business/scripts/login.py

# セッション確認
python platforms/amazon_business/scripts/verify_session.py

# 住所録クリーンアップ（保護リストは config/address_cleanup.json で設定）
python platforms/amazon_business/scripts/cleanup_addresses.py

# ヘッドレスモードで実行
python platforms/amazon_business/scripts/cleanup_addresses.py --headless
```

**設定ファイル**: `platforms/amazon_business/config/address_cleanup.json`

```json
{
  "address_cleanup": {
    "exclude_names": [
      "ハディエント公式",
      "小口博朗"
    ]
  }
}
```

**詳細**: [platforms/amazon_business/README.md](platforms/amazon_business/README.md) - Amazon Business自動化の完全なドキュメント

## 開発状況

- [x] **Sourcing Phase 0/1: 商品ソーシング自動化（完了）** 🆕
  - [x] SellerSprite連携（Playwright）
  - [x] 2034件のASIN候補抽出
  - [x] sourcing → master.db 自動連携パイプライン
  - [x] SP-APIレート制限最適化（2.5倍高速化）
- [x] Phase 1: 基盤構築（完了）
  - [x] ディレクトリ構造
  - [x] SQLiteマスタDB
  - [x] キャッシュマネージャー
- [x] Phase 2: BASE複数アカウント対応（完了）
  - [x] 複数アカウント管理
  - [x] トークン自動更新
  - [x] アカウント別スケジューリング
- [x] Phase 3: 出品キュー・スケジューラー（完了）
  - [x] 時間分散スケジューリング
  - [x] Windowsサービス化
  - [x] 滞留商品の自動検出・キュー追加
- [x] Phase 4: 価格・在庫同期リファクタ（完了）
  - [x] SP-APIバッチ処理実装（10-20倍高速化）
  - [x] BASE API並列処理（20%高速化）
  - [x] BASE API → ローカルDB同期
- [ ] Phase 5: 他プラットフォーム統合（進行中）
  - [x] eBay基本機能
  - [ ] Yahoo!オークション
  - [ ] メルカリ
- [ ] Phase 6: モニタリング・最適化
  - [x] **ProductRegistrar リファクタリング** ([ISSUE_026](docs/issues/ISSUE_026_ProductRegistrar_Refactoring.md)) ✅ 完了（2025-12-02）
    - 単一責任原則に従った設計への移行
    - ProductManager、ListingManager、QueueManagerへの責務分離
    - コードの一貫性・テスト性・保守性の向上
  - [x] **価格決定システム再設計** ([docs/PRICING_SYSTEM_REDESIGN.md](docs/PRICING_SYSTEM_REDESIGN.md)) ✅ 完了（2025-12-02）
    - 価格ロジックの一元化（5ファイルから共通モジュールへ）
    - 柔軟な価格戦略（YAML設定ファイル）
    - 価格変更履歴の記録と異常検知機能

## 🔧 開発ガイドライン

### SP-API通信の集約化

**基本原則**: すべてのSP-API通信は `integrations/amazon/sp_api_client.py` を経由すること。

#### アーキテクチャ

```
各種スクリプト
    ↓
integrations/amazon/sp_api_client.py (唯一のSP-API通信レイヤー)
    ↓
Amazon SP-API
```

#### メリット
- ✅ メンテナンス性の向上（修正が1箇所で完了）
- ✅ デバッグの容易化（SP-API関連のバグは1ファイルのみ調査）
- ✅ レート制限管理の一元化（0.7秒/リクエスト、自動リトライ機能）
- ✅ エラーハンドリングの統一（QuotaExceeded自動対応）

#### 変更時のチェックリスト

**SP-APIから取得する情報を追加する場合**:

1. **`integrations/amazon/sp_api_client.py` に新フィールドを追加**
   - `get_product_info()` または `get_products_batch()` メソッドを修正
   - 戻り値の辞書に新しいフィールドを追加
   - 例：カテゴリ情報の追加（[実装例](docs/CATEGORY_IMPLEMENTATION_SUMMARY.md)）

2. **各スクリプトの `db.add_product()` 呼び出しを更新**
   - 以下のスクリプトを確認し、新しいパラメータを追加：
     - `inventory/scripts/sync_amazon_data.py`
     - `sourcing/scripts/import_candidates_to_master.py`
     - `inventory/scripts/add_new_products.py`
     - その他、SP-APIを使用するスクリプト

3. **テスト実行**
   - 本番スクリプトを直接実行してテスト（`--dry-run` や `--limit` オプションを活用）
   - データベースへの保存を確認
   - 詳細は [テストルール](#testing-rules) を参照

**参考資料**:
- [BATCH_PROCESSING_IMPLEMENTATION_V2.md](docs/BATCH_PROCESSING_IMPLEMENTATION_V2.md) - SP-APIバッチ処理の最適化実装
- [CATEGORY_IMPLEMENTATION_SUMMARY.md](docs/CATEGORY_IMPLEMENTATION_SUMMARY.md) - カテゴリ取得実装の事例

## 📝 最近の更新・改修履歴

### 🆕 2025-11-26: 商品ソーシング機能 Phase 1完了

SellerSpriteからの自動ASIN抽出と出品パイプラインへの自動連携を実現しました。

**主な成果**:
1. **SellerSprite ASIN抽出**
   - Playwrightによる自動ブラウザ操作
   - 2034件のASIN候補を抽出成功（2025-11-25）
   - sourcing.dbで候補を管理

2. **自動出品連携パイプライン**
   - sourcing_candidates → master.db → upload_queue の完全自動化
   - SP-APIで商品情報取得（約2.7時間で1920件処理）
   - NGキーワード自動クリーニング機能
   - アカウント自動割り振り（base_account_1: 1110件、base_account_2: 924件）

3. **SP-APIレート制限の最適化**
   - Catalog APIのレート制限を12秒→2.5秒に最適化
   - 処理速度2.5倍向上（6.7時間 → 2.7時間）

**使用例**:
```bash
# SellerSpriteからASIN抽出
python sourcing/scripts/extract_asins_bulk.py \
  --strategy segment \
  --segments "2500-5000,5000-10000,10000-20000" \
  --sales-min 300

# master.dbへの連携（出品キューに自動追加）
python sourcing/scripts/import_candidates_to_master.py
```

**詳細**:
- [sourcing/docs/20251126_listing_integration_execution_report.md](sourcing/docs/20251126_listing_integration_execution_report.md)
- [sourcing/docs/20251125_implementation_progress_report_v3.md](sourcing/docs/20251125_implementation_progress_report_v3.md)
- [docs/sourcing_plan.md](docs/sourcing_plan.md)

---

### 2025-11-22: 滞留商品の出品キュー追加とBASE API同期

既存のBASE API商品（約9,000件）をローカルDBに統合し、滞留商品をキューに追加しました。

**主な変更点**:
1. **BASE API → ローカルDB マージ機能**
   - BASE APIから既存商品9,082件を取得
   - ローカルDBに1,829件の新規商品を追加
   - 既存商品7,123件のSKU・価格・在庫情報を更新
   - プラットフォーム名・アカウントID・ステータスの正規化（約7,000件）

2. **滞留商品の出品キュー追加**
   - キューに未登録のpending商品1,626件を自動検出
   - 1日1000件上限に対応した時間分散スケジューリング
   - アカウント別並列処理対応（base_account_1: 831件、base_account_2: 795件）
   - 営業時間（6:00～23:00）内で均等分散、1日で完了

3. **新規スクリプト追加**
   - `inventory/scripts/backup_db.py`: データベースバックアップ
   - `inventory/scripts/preview_base_sync.py`: マージプレビュー
   - `inventory/scripts/sync_from_base_api.py`: BASE API同期・マージ
   - `scheduler/scripts/add_pending_to_queue.py`: 滞留商品キュー追加（改善版）
   - `scheduler/scripts/cleanup_invalid_listings.py`: 不要レコード削除

**使用例**:
```bash
# DBバックアップ
python inventory/scripts/backup_db.py

# BASE APIとの同期プレビュー
python inventory/scripts/preview_base_sync.py --account-id base_account_1

# BASE APIから商品をマージ（本番）
python inventory/scripts/sync_from_base_api.py --account-id base_account_1

# 滞留商品をキューに追加
python scheduler/scripts/add_pending_to_queue.py --yes
```

**結果**:
- 商品マスタ: 11,468件（+1,829件）
- BASE listings: 10,805件（+約2,000件）
- platform_item_id設定済み: 9,137件
- 正規化完了: プラットフォーム名・アカウントID・ステータスすべて統一

---

### 2025-11-22: SP-APIバッチ処理とBASE API並列処理の実装

SP-APIのバッチ処理とBASE API並列処理を実装し、処理時間を大幅に短縮しました。

**主な改善点**:
1. **SP-API Product Pricing APIバッチ処理**
   - 最大20件/リクエストでバッチ取得
   - API呼び出しを95%削減
   - 処理時間を80-90%削減（10-20倍高速化）
   - 1日あたり4時間以上の時間削減

2. **BASE API並列処理**
   - ThreadPoolExecutorで複数アカウントを同時処理
   - 2アカウント処理で20%高速化（117秒 → 93秒）
   - コマンドライン引数で制御可能（`--parallel`, `--max-workers`）

3. **SP-API呼び出しの誤り修正**
   - `get_amazon_price()`メソッドに`allow_sp_api`フラグを追加
   - BASE API同期時のSP-API誤呼び出しを解消
   - レート制限エラー（QuotaExceeded）を完全に解消

**使用例**:
```bash
# 価格同期（現在は定期実行デーモン推奨）
python platforms/base/scripts/sync_prices.py --markup-ratio 1.3

# 新規商品追加（自動的にSP-APIバッチ処理を使用）
python inventory/scripts/add_new_products.py \
  --asin-file asins.txt \
  --platform base \
  --account-id base_account_1 \
  --use-sp-api
```

**注意**: このセクションは2025-11-22時点の情報です。現在は**定期実行デーモン**（scheduled_tasks/sync_inventory_daemon.py）の使用を推奨します。

**詳細**: [docs/BATCH_PROCESSING_IMPLEMENTATION.md](docs/BATCH_PROCESSING_IMPLEMENTATION.md)

---

### 2025-11-21: アカウント分散・時間分散の最適化

商品アップロードの動作を最適化し、より柔軟な制御が可能になりました。

**主な変更点**:
1. **アカウント分散のデフォルト動作変更**
   - デフォルト: 指定された`--account-id`のみを使用
   - `--auto-distribute-accounts`フラグで複数アカウントへの自動分散を有効化

2. **時間分散アルゴリズムの最適化**
   - 1日のクォータ（1000件）を最大限使用
   - 1時間あたりの制限（デフォルト100件）を考慮した効率的な詰め込み
   - `--hourly-limit`オプションで調整可能

3. **キュー動作の明確化**
   - 既存スケジュールのチェック機能を追加
   - 重複する場合は警告を表示

**使用例**:
```bash
# デフォルト: 指定アカウントのみ使用、効率的な時間分散
python inventory/scripts/add_new_products.py \
  --asin-file asins.txt \
  --platform base \
  --account-id base_account_1 \
  --use-sp-api

# 複数アカウントへ自動分散を有効化
python inventory/scripts/add_new_products.py \
  --asin-file asins.txt \
  --platform base \
  --account-id base_account_1 \
  --use-sp-api \
  --auto-distribute-accounts
```

**詳細**: [docs/REMAINING_ISSUES.md](docs/REMAINING_ISSUES.md#issue-4-アカウント分散時間分散の最適化-)

---

### 2025-11-21: ワークフロー自動化（Phase 1完了）

商品登録からアップロードまでのワークフローを自動化しました。

**主な変更点**:
- `add_new_products.py`に自動キュー追加機能を実装
- 手動操作が不要になり、データ整合性が向上

**詳細**:
- [ワークフロー改善レポート](docs/WORKFLOW_IMPROVEMENT_2025-11-21.md) - 詳細な改修内容と技術仕様
- [残存課題リスト](docs/REMAINING_ISSUES.md) - Phase 2-3の未着手課題

**使用方法**:
```bash
# 新規商品登録（自動的にキューに追加される）
python inventory/scripts/add_new_products.py \
  --asin-file asins.txt \
  --platform base \
  --account-id base_account_1 \
  --use-sp-api \
  --yes
```

## ライセンス

Private

## 関連ドキュメント

### セットアップ・基本
- [QUICKSTART.md](QUICKSTART.md) - クイックスタートガイド
- [docs/REMAINING_ISSUES.md](docs/REMAINING_ISSUES.md) - 残存課題リスト

### 🆕 共通基盤
- [common/browser/README.md](common/browser/README.md) - Playwrightブラウザオートメーション基盤

### 🆕 商品ソーシング
- [docs/sourcing_plan.md](docs/sourcing_plan.md) - ソーシング機能実装計画
- [sourcing/docs/20251126_listing_integration_execution_report.md](sourcing/docs/20251126_listing_integration_execution_report.md) - 出品連携実行レポート
- [sourcing/docs/20251125_implementation_progress_report_v3.md](sourcing/docs/20251125_implementation_progress_report_v3.md) - Phase 1完了レポート
- [sourcing/sources/sellersprite/USAGE.md](sourcing/sources/sellersprite/USAGE.md) - SellerSprite使い方

### BASE統合
- [platforms/base/README.md](platforms/base/README.md) - BASE統合ドキュメント
- [platforms/base/TOKEN_MANAGEMENT.md](platforms/base/TOKEN_MANAGEMENT.md) - トークン管理ガイド

### 🆕 Amazon Business（ブラウザ自動化）
- [platforms/amazon_business/README.md](platforms/amazon_business/README.md) - Amazon Business自動化ドキュメント

### スケジューラー・最適化
- [scheduler/README.md](scheduler/README.md) - スケジューラー使用ガイド
- [scheduled_tasks/README.md](scheduled_tasks/README.md) - 🆕 定期実行デーモン（価格・在庫同期）
- [deploy/windows/README.md](deploy/windows/README.md) - Windowsサービス化ガイド
- [docs/BATCH_PROCESSING_IMPLEMENTATION.md](docs/BATCH_PROCESSING_IMPLEMENTATION.md) - バッチ処理実装レポート

### アーキテクチャ・管理
- [docs/認証情報管理アーキテクチャ.md](docs/認証情報管理アーキテクチャ.md) - 認証情報管理の全体像
- [docs/高優先度機能_使い方ガイド.md](docs/高優先度機能_使い方ガイド.md) - 在庫切れ自動非公開・価格同期
- [docs/PRICING_SYSTEM_REDESIGN.md](docs/PRICING_SYSTEM_REDESIGN.md) - 🆕 価格決定システム（2025-12-02完了）

## 関連リンク

- [BASE API ドキュメント](https://developers.thebase.in/)
- [Amazon SP-API](https://developer-docs.amazon.com/sp-api/)
- [eBay API](https://developer.ebay.com/)
