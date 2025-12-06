# eBay自動化システム - クイックスタートガイド

## 📋 概要

EC Auto eBay統合モジュールは、eBay Inventory APIを使用した商品の自動出品、価格・在庫同期、レガシーデータ移行を提供します。

**主要機能**:
- ✅ 複数アカウント対応（Sandbox/Production）
- ✅ OAuth 2.0トークン自動管理
- ✅ SP-APIキャッシュによる高速価格同期
- ✅ 時間分散スケジューリング
- ✅ ビジネスポリシー自動適用
- ✅ レガシーシステムからのデータ移行

**実装状況**: Phase 1-5 完了 ✅

---

## 🔧 前提条件

### 必須環境
- Python 3.8以上
- SQLite3
- eBay Developer Account（App ID, Cert ID, Dev ID）
- SP-API認証情報（価格同期用）

### ディレクトリ構造
```
platforms/ebay/
├── accounts/
│   ├── manager.py              # アカウント管理
│   ├── account_config.json     # アカウント設定（要作成）
│   ├── account_config.json.example
│   └── tokens/                 # トークンファイル（自動作成）
├── core/
│   ├── auth.py                 # OAuth認証
│   ├── api_client.py           # eBay API クライアント
│   ├── category_mapper.py      # カテゴリマッピング
│   └── policies.py             # ビジネスポリシー管理
├── scripts/
│   ├── sync_listings.py         # eBay出品状態同期（★新規）
│   ├── sync_prices.py           # 価格同期
│   ├── migrate_from_legacy.py   # データ移行
│   └── test_integration.py      # 統合テスト
└── docs/
    └── implementation_plan_initial.md
```

---

## 🚀 セットアップ手順

### 1. アカウント設定

`platforms/ebay/accounts/account_config.json` を作成：

```json
{
  "accounts": [
    {
      "id": "ebay_account_1",
      "name": "eBay Main Account",
      "description": "メインアカウント",
      "active": true,
      "environment": "production",
      "credentials": {
        "app_id": "YOUR_APP_ID_HERE",
        "cert_id": "YOUR_CERT_ID_HERE",
        "dev_id": "YOUR_DEV_ID_HERE",
        "redirect_uri": "YOUR_REDIRECT_URI_HERE"
      },
      "settings": {
        "merchant_location_key": "JP_LOCATION",
        "default_currency": "USD",
        "rate_limit_per_day": 5000
      }
    }
  ]
}
```

**注意**: `account_config.json.example` を参考に作成してください。

### 2. OAuth認証

初回認証を実行：

```bash
python platforms/ebay/core/auth.py
```

1. ブラウザで認証URLが開きます
2. eBayにログインして認証を許可
3. リダイレクトURLから認証コードを取得
4. 認証コードを入力してトークンを取得

トークンは `platforms/ebay/accounts/tokens/` に保存され、自動更新されます。

### 3. データベース初期化

`ebay_listing_metadata` テーブルが自動作成されます（初回実行時）。

確認コマンド：
```bash
sqlite3 inventory/data/master.db "SELECT name FROM sqlite_master WHERE type='table' AND name='ebay_listing_metadata';"
```

### 4. ビジネスポリシー設定

eBay Seller Hubで以下を作成し、Policy IDを取得：
- Payment Policy（支払いポリシー）
- Return Policy（返品ポリシー）
- Fulfillment Policy（配送ポリシー）

Policy IDは `platforms/ebay/core/policies.py` で設定します。

---

## 📖 使用方法

### 商品出品

スケジューラーを通じて自動出品：

```python
from scheduler.upload_executor import UploadExecutor

executor = UploadExecutor()
# upload_queue テーブルにプラットフォーム='ebay'のタスクがあれば自動処理
```

デーモンで定期実行：
```bash
python scheduler/daemon.py
```

### eBay出品状態の同期 ⭐NEW

eBay本番環境の出品状態をローカルDBに同期します。

#### 基本的な使用方法
```bash
# 特定アカウントの出品状態を同期（最大200件）
python platforms/ebay/scripts/sync_listings.py --account ebay_account_1

# 処理件数を制限
python platforms/ebay/scripts/sync_listings.py --account ebay_account_1 --max-items 50

# デバッグモードで詳細ログを表示
python platforms/ebay/scripts/sync_listings.py --account ebay_account_1 --debug
```

#### 重要な仕様

**ASINベースの管理**:
- **ASIN** がプライマリな識別子として使用されます
- SKUはタイムスタンプを含むため変動しますが、ASINで既存レコードを検索・更新します
- 同じASINで異なるSKUの重複は自動的に解消されます

**同期処理の動作**:
1. eBay Inventory APIから出品一覧を取得
2. 各SKUのOffer情報を取得
3. SKUからASINを抽出
4. **ASINで既存レコードを検索**（platform/account_idに関わらず）
5. 既存レコードがあれば、SKU・platform・account_id・status・priceをすべて更新
6. 新規の場合のみINSERT

**ステータスマッピング**:
- `PUBLISHED` → `listed`（eBayに公開済み）
- `UNPUBLISHED` → `pending`（下書き状態）

**レガシーデータの自動統合**:
- 旧システムのデータ（platform='eBay', account_id='ebay_main'）も自動的に検出
- 新しい命名規則（platform='ebay', account_id='ebay_account_1'）に統一
- UNIQUE制約エラーを回避しながら安全に統合

### 価格・在庫同期

#### 全アカウントの価格同期
```bash
python platforms/ebay/scripts/sync_prices.py --all
```

#### 特定アカウントのみ同期
```bash
python platforms/ebay/scripts/sync_prices.py --account ebay_account_1
```

#### カスタムマークアップ設定（オプション）
```bash
# 特定のマークアップ率を指定（カスタム戦略を上書き）
python platforms/ebay/scripts/sync_prices.py --all --markup 1.25
```

**価格計算ロジック**:

eBay専用カスタム戦略（`ebay_custom`）を使用：

```python
# 1. JPYでの売価計算（実際のコスト構造を考慮）
固定コスト = 原価（Amazon価格） + 送料 + 梱包資材代
売価（JPY） = 固定コスト / (1 - eBay手数料率 - 関税率 - 利益率)

# 2. USD換算（リアルタイム為替レート）
売価（USD） = 売価（JPY） / 為替レート
```

**デフォルト設定** (`config/pricing_strategy.yaml`):

固定コスト：
- 送料: 4,000円（将来的にサイズ別バリエーション対応予定）
- 梱包資材代: 500円

売価に対する割合：
- eBay手数料: 17%（売価から引かれる）
- 関税: 15%（売価に対して課税される）
- 目標利益率: 20%

為替レート：
- yfinance APIからリアルタイム取得（24時間キャッシュ）
- フォールバック: 150 JPY/USD

**計算例**（Amazon価格10,000円の場合）：
```
固定コスト = 10,000 + 4,000 + 500 = 14,500円
売価（JPY） = 14,500 / (1 - 0.17 - 0.15 - 0.20) = 30,210円
売価（USD） = 30,210 / 155.45 ≈ $194.34

コスト内訳：
- eBay手数料（17%）: 5,136円
- 関税（15%）: 4,532円
- 利益（20%）: 6,042円
- 固定コスト: 14,500円
合計: 30,209円 ≈ 30,210円 ✓
```

**設定のカスタマイズ**:

`config/pricing_strategy.yaml` の `ebay_custom` セクションを編集：
```yaml
ebay_custom:
  # 固定コスト
  shipping_cost: 4000        # 送料を変更
  packaging_cost: 500        # 梱包資材代を変更

  # 売価に対する割合
  ebay_fee_rate: 0.17        # eBay手数料率を変更
  customs_duty_rate: 0.15    # 関税率を変更
  profit_margin: 0.20        # 目標利益率を変更
```

### レガシーデータ移行

#### CSVからの移行
```bash
python platforms/ebay/scripts/migrate_from_legacy.py --csv C:\path\to\products_master.csv --account ebay_account_1
```

#### eBay APIから既存出品を同期（推奨）
```bash
python platforms/ebay/scripts/migrate_from_legacy.py --sync-existing --account ebay_account_1
```

**オプション**:
- `--dry-run`: 実際に登録せずシミュレーション
- `--limit N`: 処理する商品数を制限

**ASIN重複チェック**:
- ASIN + platform + account_id の組み合わせで重複を検出
- 同じASINは再登録されません（SKUに日付が含まれていても安全）

---

## 🧪 テスト

### 統合テスト（Phase 1-5）

全機能の動作確認：
```bash
python platforms/ebay/scripts/test_integration.py
```

テスト内容：
- Phase 1: 基盤構築（ディレクトリ、認証、DB）
- Phase 2: eBay API統合
- Phase 3: スケジューラー統合
- Phase 4: 価格・在庫同期
- Phase 5: レガシーデータ移行

**期待結果**:
```
[SUCCESS] 全統合テスト成功
```

---

## 📁 ファイル・DB構成

### データベーステーブル

#### `ebay_listing_metadata`
eBay固有の出品メタデータを保存：

| カラム | 型 | 説明 |
|--------|-----|------|
| listing_id | INTEGER | listings.idへの外部キー |
| listing_id_ebay | TEXT | eBay Listing ID |
| offer_id | TEXT | eBay Offer ID |
| sku | TEXT | eBay SKU（ユニーク） |
| category_id | TEXT | eBay Category ID |
| aspects | TEXT (JSON) | Item Specifics |
| policy_ids | TEXT (JSON) | ビジネスポリシーID |
| created_at | TIMESTAMP | 作成日時 |
| updated_at | TIMESTAMP | 更新日時 |

### SKUフォーマット
```
s-{ASIN}-{YYYYMMDD_HHMM}
```
例: `s-B0002YM3QI-20251128_1030`

---

## ⚠️ トラブルシューティング

### アカウント設定が見つからない
```
警告: アカウント設定ファイルが見つかりません: account_config.json
```
**解決**: `account_config.json.example` を参考に `account_config.json` を作成

### トークン期限切れ
```
Error: Access token expired
```
**解決**: OAuth認証を再実行
```bash
python platforms/ebay/core/auth.py
```

### 価格同期でAmazon価格が見つからない
```
警告: Amazon価格が見つかりません: ASIN=B0002YM3QI
```
**原因**: SP-APIキャッシュに価格データがない
**解決**: 商品情報を再取得してキャッシュを更新

### 統合テストでPhase 5が失敗（Windows環境）
```
ValueError: I/O operation on closed file
```
**原因**: Windows環境でのstdoutエンコーディング問題（既知の問題）
**解決**: コード内でstdout復元処理を実装済み。再実行してください。

### UNIQUE制約エラー（sync_listings.py実行時）
```
UNIQUE constraint failed: listings.sku
```
**原因**: 同じSKUまたはASINが既に登録されている
**解決**:
1. **ASINベースの検索に修正済み**（最新版では自動解決）
2. レガシーデータがある場合、ASINで検索して既存レコードを更新

### platform/account_idの不一致
```
UNIQUE constraint failed: listings.asin, listings.platform, listings.account_id
```
**原因**: レガシーデータ（platform='eBay', account_id='ebay_main'）と新データ（platform='ebay', account_id='ebay_account_1'）が混在
**解決**:
1. sync_listings.pyは自動的にレガシーデータを検出・統合します
2. platformやaccount_idに関わらず、ASINで既存レコードを検索
3. 既存レコードを新しい命名規則で更新

### SKU vs ASINの重複問題
```
同じASINで異なるタイムスタンプのSKUが複数存在
```
**原因**: SKU形式が `s-{ASIN}-{YYYYMMDD_HHMM}` のため、同じASINでも異なる日時で複数作成される
**解決**:
- **ASINをプライマリキーとして使用**（最新版で実装済み）
- 同じASINの場合、SKUを最新のものに更新
- SKU単体でのUNIQUE制約は維持しつつ、ASINベースで管理

詳細なトラブルシューティングは `platforms/ebay/docs/TROUBLESHOOTING.md` を参照。

---

## 📚 次のステップ

1. **本番環境での少量テスト**
   - 10-20件の商品で動作確認
   - 価格・説明・画像の表示確認

2. **デーモンのセットアップ**
   - Windowsサービスとして登録
   - 自動起動設定
   - ログ監視

3. **定期実行の設定**
   - 価格同期: 1日2回（朝・夕）
   - 在庫同期: 1時間ごと
   - 新規出品: 営業時間に時間分散

4. **モニタリング**
   - ログファイル監視
   - エラーレート確認
   - API利用状況確認

---

## 📞 サポート

- 実装計画: [implementation_plan_initial.md](docs/implementation_plan_initial.md)
- トラブルシューティング: [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)（作成予定）
- プロジェクトルート: `C:\Users\hiroo\Documents\GitHub\ecauto`

---

**最終更新**: 2025-12-03
**バージョン**: Phase 1-5 完了 + eBay専用価格戦略実装 + ASINベース出品同期実装 ✅

**主な変更点（2025-12-03）**:
- ✅ sync_listings.py追加（eBay出品状態の完全同期）
- ✅ ASINベースの検索・更新ロジック実装
- ✅ SKU重複問題の完全解決
- ✅ レガシーデータ自動統合機能
- ✅ 471件の完全同期達成
