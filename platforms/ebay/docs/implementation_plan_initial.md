# eBay自動化システム移行 実装計画書

**作成日**: 2025-11-28
**プロジェクト**: EC Auto - eBay統合
**対象**: レガシーebayシステム → 新規統合システム移行

---

## 📋 目次

1. [現状分析](#現状分析)
2. [移行方針](#移行方針)
3. [設計仕様](#設計仕様)
4. [実装プラン](#実装プラン)
5. [マイルストーン](#マイルストーン)
6. [留意事項](#留意事項)

---

## 🔍 現状分析

### レガシーebayシステムの特徴

**場所**: `C:\Users\hiroo\Documents\ama-cari\ebay_pj`

**主要コンポーネント**:
- **`core/listing.py`**: 出品管理（Offer作成、公開）
- **`core/inventory.py`**: 在庫管理（Inventory Item作成）
- **`core/token_manager.py`**: OAuth トークン管理
- **`core/config.py`**: 環境設定（Sandbox/Production）
- **`scripts/upload_to_ebay.py`**: 一括出品スクリプト

**データ管理方式**:
- CSVベース（`products_master.csv`）
- ASINリストファイル（`ASIN.txt`等）
- eBay出品CSVの生成（日本語版・英語版）

**主要機能**:
1. Amazon商品情報スクレイピング
2. OpenAI APIによる商品説明翻訳・最適化
3. eBayカテゴリ自動推薦（Taxonomy API）
4. 動的なItem Specifics（Aspects）生成
5. ビジネスポリシー適用（payment, return, fulfillment）

**ワークフロー**:
```
Amazonスクレイピング
  ↓
CSVに保存（JP版、EN版）
  ↓
eBay API出品
  ├─ Inventory Item作成
  ├─ Offer作成
  └─ Publish実行
```

---

### 新規システム（ecauto）の強み

**主要特徴**:
- ✅ **SQLiteベースの統一商品管理**（`inventory/data/master.db`）
- ✅ **SP-APIキャッシュ**による高速化・コスト削減
- ✅ **スケジューラー**による時間分散自動出品
- ✅ **複数プラットフォーム対応**アーキテクチャ
- ✅ **定期実行デーモン**による価格・在庫自動同期

**データフロー**:
```
SellerSprite/ASINファイル
  ↓
SP-API商品情報取得
  ↓
master.db登録（products + listings）
  ↓
upload_queueに自動追加
  ↓
デーモンが自動出品
```

**BASE移行の実績**:
- 複数アカウント対応済み
- トークン自動更新実装済み
- SP-APIバッチ処理実装済み（価格取得20倍高速化）
- 時間分散スケジューリング実装済み

---

## 🎯 移行方針

### 基本方針

新規システムの統一フローを**最大限活用**しつつ、eBay固有の機能を実装します：

1. ✅ **商品取得・運用**: 新システムのフローを使用
   - SellerSprite自動抽出 or ASINファイル
   - SP-API商品情報取得
   - master.db統一管理

2. ✅ **価格・在庫同期**: 新システムの同期システムを利用
   - `scheduled_tasks/sync_inventory_daemon.py`
   - SP-APIバッチ処理（高速化済み）
   - プラットフォーム別更新処理

3. ✅ **eBay固有機能**: `platforms/ebay/` ディレクトリに実装
   - カテゴリ自動推薦（Taxonomy API）
   - Item Specifics動的生成
   - ビジネスポリシー管理

### 設計原則

- **DRY原則**: 既存の共通機能を再利用（重複実装を避ける）
- **プラットフォーム抽象化**: BASEと同様のインターフェース
- **段階的移行**: まず新規出品、次に既存データ移行
- **後方互換性**: レガシーシステムと並行運用可能

---

## 📐 設計仕様

### 1. ディレクトリ構造

```
platforms/ebay/
├── accounts/                    # アカウント管理（BASEと同様）
│   ├── __init__.py
│   ├── manager.py              # アカウントマネージャー
│   ├── account_config.json     # アカウント設定
│   ├── account_config.json.example
│   └── tokens/                 # トークンファイル（自動生成）
│       └── ebay_account_1_token.json
│
├── core/                       # eBay API クライアント
│   ├── __init__.py
│   ├── api_client.py          # eBay Inventory API統合クライアント
│   ├── auth.py                # OAuth認証・トークン管理
│   ├── policies.py            # ビジネスポリシー管理
│   └── category_mapper.py     # カテゴリ自動推薦
│
├── data/                       # eBay固有データ
│   ├── policies/              # ポリシーID設定
│   │   └── default_policies.json
│   └── category_cache/        # カテゴリキャッシュ
│
├── scripts/                    # 管理スクリプト
│   ├── __init__.py
│   ├── setup_account.py       # アカウントセットアップ
│   ├── setup_policies.py      # ポリシー初期設定
│   ├── sync_prices.py         # 価格同期（BASE同様）
│   ├── test_listing.py        # 出品テスト
│   └── migrate_from_legacy.py # レガシーデータ移行
│
├── docs/                       # ドキュメント
│   ├── implementation_plan_initial.md  # 本ドキュメント
│   └── README.md              # eBay統合ドキュメント
│
└── README.md                   # クイックスタートガイド
```

---

### 2. データベース拡張

既存の `inventory/data/master.db` を拡張します。

#### 既存テーブル活用

**`listings` テーブル**（既存）:
- `platform='ebay'` で識別
- `account_id`: eBayアカウントID
- `platform_item_id`: eBay Listing ID
- `sku`: eBay SKU（ASIN-ebay-account形式）
- その他は共通フィールドを使用

#### 新規テーブル作成

**`ebay_listing_metadata` テーブル**（新規）:
```sql
CREATE TABLE ebay_listing_metadata (
    listing_id INTEGER PRIMARY KEY,
    offer_id TEXT,              -- eBay Offer ID
    category_id TEXT,           -- eBay Category ID
    policy_payment_id TEXT,     -- Payment Policy ID
    policy_return_id TEXT,      -- Return Policy ID
    policy_fulfillment_id TEXT, -- Fulfillment Policy ID
    item_specifics JSON,        -- eBay Item Specifics（Aspects）
    merchant_location_key TEXT DEFAULT 'JP_LOCATION',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (listing_id) REFERENCES listings(id)
);
```

**マイグレーションスクリプト**: `inventory/scripts/migrations/add_ebay_metadata.py`

---

### 3. 主要コンポーネント設計

#### A. eBay APIクライアント

**ファイル**: `platforms/ebay/core/api_client.py`

```python
class EbayAPIClient:
    """
    eBay Inventory API統合クライアント
    レガシーの listing.py と inventory.py の機能を統合
    """

    def __init__(self, access_token: str, environment: str = 'production'):
        """
        Args:
            access_token: eBay OAuth access token
            environment: 'sandbox' or 'production'
        """
        self.access_token = access_token
        self.environment = environment
        self.base_url = self._get_base_url()

    def create_or_update_inventory_item(self, sku: str, product_data: Dict) -> Dict:
        """
        Inventory Item作成/更新

        Args:
            sku: 商品SKU
            product_data: 商品データ（title, description, images, aspects等）

        Returns:
            {'success': True/False, 'sku': str, 'error': str}
        """
        pass

    def create_offer(self, sku: str, price: float, category_id: str,
                    policies: Dict, quantity: int = 1) -> Optional[str]:
        """
        Offer作成

        Args:
            sku: 商品SKU
            price: 販売価格（USD）
            category_id: eBayカテゴリID
            policies: ポリシーID辞書 {'payment': str, 'return': str, 'fulfillment': str}
            quantity: 在庫数

        Returns:
            offer_id: 作成されたOffer ID（失敗時はNone）
        """
        pass

    def publish_offer(self, offer_id: str) -> Optional[str]:
        """
        Offer公開（リスティング作成）

        Args:
            offer_id: Offer ID

        Returns:
            listing_id: eBay Listing ID（失敗時はNone）
        """
        pass

    def get_offers_by_sku(self, sku: str) -> List[Dict]:
        """SKUに紐づくOffer一覧取得"""
        pass

    def update_offer_price(self, offer_id: str, new_price: float) -> bool:
        """Offer価格更新"""
        pass

    def update_inventory_quantity(self, sku: str, quantity: int) -> bool:
        """在庫数更新"""
        pass

    def delete_offer(self, offer_id: str) -> bool:
        """Offer削除"""
        pass
```

**レガシーからの移植内容**:
- `core/listing.py` の全メソッド
- `core/inventory.py` の全メソッド
- `scripts/upload_to_ebay.py` の主要ロジック

---

#### B. カテゴリマッパー

**ファイル**: `platforms/ebay/core/category_mapper.py`

```python
class CategoryMapper:
    """
    eBayカテゴリ自動推薦
    レガシーの get_ebay_category_id() を改良
    """

    def __init__(self, app_token: str):
        """
        Args:
            app_token: eBay Application Token（Taxonomy API用）
        """
        self.app_token = app_token
        self.cache_dir = Path(__file__).parent.parent / 'data' / 'category_cache'
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_recommended_category(self, title: str, description: str = None,
                                use_cache: bool = True) -> Optional[Dict]:
        """
        Taxonomy APIでカテゴリ推薦

        Args:
            title: 商品タイトル
            description: 商品説明（オプション）
            use_cache: キャッシュを使用するか

        Returns:
            {
                'category_id': str,
                'category_name': str,
                'confidence': float
            }
        """
        pass

    def get_category_specifics(self, category_id: str) -> List[Dict]:
        """
        カテゴリ必須Item Specificsを取得

        Args:
            category_id: eBayカテゴリID

        Returns:
            [
                {
                    'name': 'Brand',
                    'required': True,
                    'values': ['Sony', 'Canon', ...]
                },
                ...
            ]
        """
        pass
```

---

#### C. ポリシー管理

**ファイル**: `platforms/ebay/core/policies.py`

```python
class PolicyManager:
    """
    eBayビジネスポリシー管理
    レガシーの POLICY_IDS を統合管理
    """

    def __init__(self, config_path: str = None):
        """
        Args:
            config_path: ポリシー設定ファイルパス
        """
        self.config_path = config_path or self._get_default_config_path()
        self.policies = self._load_policies()

    def get_default_policies(self, account_id: str) -> Dict[str, str]:
        """
        アカウントのデフォルトポリシーID取得

        Args:
            account_id: eBayアカウントID

        Returns:
            {
                'payment': 'policy_id',
                'return': 'policy_id',
                'fulfillment': 'policy_id'
            }
        """
        pass

    def validate_policies(self, policy_ids: Dict[str, str],
                         api_client: 'EbayAPIClient') -> Dict[str, bool]:
        """
        ポリシーIDの有効性確認（eBay APIで検証）

        Args:
            policy_ids: ポリシーID辞書
            api_client: EbayAPIClient インスタンス

        Returns:
            {
                'payment': True/False,
                'return': True/False,
                'fulfillment': True/False
            }
        """
        pass
```

**設定ファイル**: `platforms/ebay/data/policies/default_policies.json`

```json
{
  "accounts": {
    "ebay_account_1": {
      "payment": "374677267023",
      "return": "374677266023",
      "fulfillment": "374676887023"
    }
  }
}
```

---

#### D. 認証管理

**ファイル**: `platforms/ebay/core/auth.py`

```python
class EbayAuthManager:
    """
    eBay OAuth認証・トークン管理
    レガシーの token_manager.py を改良
    """

    def __init__(self, account_id: str, environment: str = 'production'):
        """
        Args:
            account_id: eBayアカウントID
            environment: 'sandbox' or 'production'
        """
        self.account_id = account_id
        self.environment = environment
        self.token_path = self._get_token_path()
        self.credentials = self._load_credentials()

    def get_valid_token(self) -> Optional[str]:
        """
        有効なアクセストークンを取得（必要に応じて自動更新）

        Returns:
            access_token: 有効なアクセストークン（取得失敗時はNone）
        """
        pass

    def refresh_token(self) -> bool:
        """
        リフレッシュトークンを使用してアクセストークン更新

        Returns:
            成功: True, 失敗: False
        """
        pass

    def get_application_token(self) -> Optional[str]:
        """
        Application Token取得（Taxonomy API用）

        Returns:
            application_token: アプリケーショントークン
        """
        pass
```

---

### 4. 出品ワークフロー（新規システム統合版）

```
┌─────────────────────────────────────────────┐
│ 1. 商品ソーシング（既存フローそのまま）      │
│    ・SellerSprite自動抽出                    │
│      python sourcing/scripts/extract_asins_bulk.py
│    ・または ASINファイル                     │
│      asins.txt                               │
└─────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────┐
│ 2. SP-API取得・マスタDB登録（既存フロー）    │
│    python inventory/scripts/add_new_products.py
│      --asin-file asins.txt                   │
│      --platform ebay                         │
│      --account-id ebay_account_1             │
│      --use-sp-api                            │
│      --yes                                   │
│                                              │
│    処理内容:                                 │
│    ・SP-API商品情報取得                      │
│    ・products テーブルに登録                 │
│    ・listings テーブルに登録（platform='ebay'）
│    ・✅ 自動的にupload_queueに追加           │
└─────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────┐
│ 3. eBay出品準備（upload_executor内で実行）  │
│    ・カテゴリ自動推薦（Taxonomy API）        │
│    ・Item Specifics動的生成                  │
│    ・ポリシーID適用                          │
│    ・価格計算（JPY → USD変換 + マークアップ）│
└─────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────┐
│ 4. eBay出品実行（upload_daemon）             │
│    python scheduler/upload_daemon.py         │
│      --platform ebay                         │
│                                              │
│    処理内容:                                 │
│    ・Inventory Item作成                      │
│    ・Offer作成                               │
│    ・Publish実行                             │
│    ・listings.status更新（listed）           │
│    ・platform_item_id設定（Listing ID）      │
└─────────────────────────────────────────────┘
```

---

### 5. 価格・在庫同期フロー

```
┌─────────────────────────────────────────────┐
│ 定期実行デーモン（scheduled_tasks/）         │
│ python scheduled_tasks/sync_inventory_daemon.py
│   --interval 3600  # 1時間ごと             │
└─────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────┐
│ 1. SP-API価格・在庫取得（共通処理）          │
│    ・バッチ処理（20件/req）で高速化          │
│    ・キャッシュ活用（TTL: 1時間）            │
│    ・レート制限遵守                          │
└─────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────┐
│ 2. プラットフォーム別更新                    │
│    ├─ BASE: BaseAPIClient.update_item()     │
│    │   ・価格更新                            │
│    │   ・在庫数更新                          │
│    │   ・在庫切れ時に非公開                  │
│    │                                         │
│    └─ eBay: EbayAPIClient.update_offer()    │
│        ・Offer価格更新                       │
│        ・Inventory数量更新                   │
│        ・在庫切れ時にOffer削除（検討中）     │
└─────────────────────────────────────────────┘
```

**実装箇所**:
- `platforms/ebay/scripts/sync_prices.py`: eBay価格同期スクリプト
- `scheduled_tasks/sync_inventory_daemon.py`: プラットフォーム判定処理を追加

---

## 🚀 実装プラン

### Phase 1: 基盤構築（2-3日）

#### タスク一覧

1. **ディレクトリ構造作成**
   - `platforms/ebay/` 以下の全ディレクトリ作成
   - `__init__.py` ファイル配置

2. **データベーススキーマ拡張**
   - マイグレーションスクリプト作成
     - `inventory/scripts/migrations/add_ebay_metadata.py`
   - `ebay_listing_metadata` テーブル作成
   - 動作確認スクリプト作成

3. **アカウント管理機能**
   - `platforms/ebay/accounts/manager.py` 実装
     - BASEの `platforms/base/accounts/manager.py` をベースに作成
   - 設定ファイルテンプレート作成
     - `account_config.json.example`

4. **認証機能**
   - `platforms/ebay/core/auth.py` 実装
     - レガシーの `core/token_manager.py` を移植・改良
     - トークン自動更新機能
     - Application Token取得機能

5. **設定ファイル作成**
   - `platforms/ebay/accounts/account_config.json.example`
   - `platforms/ebay/data/policies/default_policies.json`
   - `.gitignore` 更新（トークンファイル除外）

#### 成果物

- ✅ `platforms/ebay/` ディレクトリ一式
- ✅ データベーススキーマ拡張完了
- ✅ アカウント設定完了
- ✅ トークン取得・更新機能実装完了

#### テスト項目

- [ ] アカウント設定ファイルの読み込み確認
- [ ] トークン取得・更新の動作確認
- [ ] データベーステーブル作成確認

---

### Phase 2: eBay API統合（3-4日）

#### タスク一覧

1. **`EbayAPIClient`実装**
   - `platforms/ebay/core/api_client.py`
   - レガシーから以下を移植：
     - `core/listing.py` の全メソッド
     - `core/inventory.py` の全メソッド
   - 新規実装：
     - 価格更新メソッド
     - 在庫更新メソッド
     - エラーハンドリング強化

2. **`CategoryMapper`実装**
   - `platforms/ebay/core/category_mapper.py`
   - Taxonomy API連携
   - カテゴリキャッシュ機能
   - レガシーの `get_ebay_category_id()` を改良

3. **`PolicyManager`実装**
   - `platforms/ebay/core/policies.py`
   - ポリシーID管理
   - ポリシーバリデーション
   - 設定ファイル読み込み

4. **テストスクリプト作成**
   - `platforms/ebay/scripts/test_listing.py`
   - Sandbox環境での動作確認用

#### レガシーからの移植マッピング

| レガシー | 新規 | 備考 |
|---------|------|------|
| `core/listing.py::create_offer()` | `api_client.py::create_offer()` | ほぼそのまま移植 |
| `core/listing.py::publish_offer()` | `api_client.py::publish_offer()` | ほぼそのまま移植 |
| `core/listing.py::get_offers()` | `api_client.py::get_offers_by_sku()` | メソッド名変更 |
| `core/inventory.py::create_or_update_item()` | `api_client.py::create_or_update_inventory_item()` | ほぼそのまま移植 |
| `scripts/upload_to_ebay.py::get_ebay_category_id()` | `category_mapper.py::get_recommended_category()` | クラス化・改良 |
| `scripts/upload_to_ebay.py::POLICY_IDS` | `policies.py::PolicyManager` | 設定ファイル化 |

#### 成果物

- ✅ eBay API統合クライアント完成
- ✅ カテゴリ自動推薦機能実装
- ✅ ポリシー管理機能実装
- ✅ テストスクリプト作成

#### テスト項目

- [ ] Inventory Item作成テスト（Sandbox）
- [ ] Offer作成テスト（Sandbox）
- [ ] Publish実行テスト（Sandbox）
- [ ] カテゴリ推薦APIテスト
- [ ] ポリシーID検証テスト

---

### Phase 3: 出品スケジューラー統合（2-3日）

#### タスク一覧

1. **`upload_executor.py` にeBay対応追加**
   - `scheduler/upload_executor.py` 修正
   - プラットフォーム振り分けロジック追加
   - `_upload_to_ebay()` メソッド実装

2. **eBay出品処理実装**
   - カテゴリ推薦処理
   - Item Specifics動的生成
   - 価格計算（JPY→USD変換 + マークアップ）
   - 出品実行（Inventory Item → Offer → Publish）
   - ステータス更新

3. **エラーハンドリング**
   - eBay固有のエラー処理
   - リトライロジック
   - エラーログ記録

4. **デーモン起動確認**
   - 動作確認スクリプト作成
   - ログ出力確認

#### 実装箇所

**ファイル**: `scheduler/upload_executor.py`

```python
def upload_item(self, queue_item: Dict[str, Any]) -> Dict[str, Any]:
    """キューアイテムを出品"""
    platform = queue_item['platform']

    if platform == 'base':
        return self._upload_to_base(queue_item)
    elif platform == 'ebay':
        return self._upload_to_ebay(queue_item)  # 新規追加
    else:
        raise ValueError(f"Unsupported platform: {platform}")

def _upload_to_ebay(self, queue_item: Dict[str, Any]) -> Dict[str, Any]:
    """
    eBay出品処理

    処理フロー:
    1. master.dbから商品情報取得
    2. カテゴリ推薦
    3. Item Specifics生成
    4. 価格計算（JPY→USD）
    5. Inventory Item作成
    6. Offer作成
    7. Publish実行
    8. ステータス更新
    """
    # 実装内容は省略
    pass
```

#### 成果物

- ✅ スケジューラーのeBay対応完了
- ✅ 出品フロー全体の動作確認完了
- ✅ エラーハンドリング実装完了

#### テスト項目

- [ ] ASINファイルからの出品テスト（Sandbox）
- [ ] 時間分散スケジューリング確認
- [ ] エラー発生時のリトライ確認
- [ ] ステータス更新確認

---

### Phase 4: 価格・在庫同期（2日）

#### タスク一覧

1. **`platforms/ebay/scripts/sync_prices.py` 作成**
   - BASEの `platforms/base/scripts/sync_prices.py` をベースに実装
   - eBay API対応
   - 価格差分検知・更新

2. **`sync_inventory_daemon.py` にeBay対応追加**
   - `scheduled_tasks/sync_inventory_daemon.py` 修正
   - プラットフォーム判定処理追加
   - eBay価格・在庫同期呼び出し

3. **在庫切れ時の処理実装**
   - 在庫切れ検知
   - Offer削除 or 数量0更新（要検討）

#### 実装例

**ファイル**: `platforms/ebay/scripts/sync_prices.py`

```python
def sync_ebay_prices(account_id: str, markup_ratio: float = 1.3, dry_run: bool = False):
    """
    eBay出品価格同期

    処理フロー:
    1. master.dbから出品済み商品取得（platform='ebay', status='listed'）
    2. SP-APIキャッシュから価格取得
    3. 価格計算（JPY → USD変換 + マークアップ）
    4. eBay Offer価格更新（差分があるもののみ）

    Args:
        account_id: eBayアカウントID
        markup_ratio: マークアップ率（例: 1.3 = 30%上乗せ）
        dry_run: True の場合は更新せずにログ出力のみ
    """
    pass
```

**ファイル**: `scheduled_tasks/sync_inventory_daemon.py`（修正）

```python
def sync_platform(platform: str, account_id: str):
    """プラットフォーム別同期処理"""
    if platform == 'base':
        sync_base_inventory(account_id)
    elif platform == 'ebay':
        sync_ebay_inventory(account_id)  # 新規追加
```

#### 成果物

- ✅ eBay価格同期スクリプト実装完了
- ✅ 定期実行デーモンのeBay対応完了
- ✅ 在庫切れ時の処理実装完了

#### テスト項目

- [ ] 価格同期テスト（差分更新確認）
- [ ] 在庫切れ時の処理確認
- [ ] デーモンの定期実行確認

---

### Phase 5: レガシーデータ移行（1-2日）

#### タスク一覧

1. **移行スクリプト作成**
   - `platforms/ebay/scripts/migrate_from_legacy.py`
   - `products_master.csv` 読み込み
   - master.dbへインポート

2. **既存eBay出品の同期**
   - eBay APIから既存出品取得
   - master.dbと同期
   - `platform_item_id` 設定

#### 実装例

**ファイル**: `platforms/ebay/scripts/migrate_from_legacy.py`

```python
def migrate_products_master(csv_path: str, platform: str = 'ebay', account_id: str = 'ebay_account_1'):
    """
    レガシーのproducts_master.csvを読み込み
    master.dbのproducts/listingsテーブルに移行

    Args:
        csv_path: products_master.csvのパス
        platform: プラットフォーム名
        account_id: アカウントID
    """
    pass

def sync_existing_listings(account_id: str):
    """
    eBay APIから既存出品を取得
    master.dbと同期

    Args:
        account_id: eBayアカウントID
    """
    pass
```

#### 成果物

- ✅ レガシーデータ移行スクリプト実装完了
- ✅ 既存出品の同期完了

#### テスト項目

- [ ] CSVインポート確認
- [ ] 既存出品の取得・同期確認
- [ ] データ整合性確認

---

### Phase 6: テスト・本番展開（2-3日）

#### タスク一覧

1. **単体テスト**
   - 各コンポーネントの動作確認
   - エラーケースのテスト

2. **統合テスト**
   - 出品フロー全体のテスト（Sandbox）
   - 価格・在庫同期テスト（Sandbox）

3. **本番環境スモールバッチテスト**
   - 10-20件の少量出品テスト
   - 結果確認・問題修正

4. **デーモン稼働確認**
   - Windowsサービス登録
   - 自動起動確認
   - ログ監視

5. **ドキュメント作成**
   - `platforms/ebay/README.md`: クイックスタートガイド
   - セットアップ手順
   - トラブルシューティング

#### テスト項目

- [ ] 全単体テストパス
- [ ] 全統合テストパス
- [ ] 本番環境テスト成功
- [ ] デーモン安定稼働確認
- [ ] ドキュメント完成

---

## 📅 マイルストーン

| Phase | 期間 | 主要成果物 | 依存関係 |
|-------|------|-----------|---------|
| **Phase 1** | 2-3日 | ディレクトリ構造、認証機能、DB拡張 | なし |
| **Phase 2** | 3-4日 | eBay API統合クライアント | Phase 1 |
| **Phase 3** | 2-3日 | スケジューラー統合、出品フロー | Phase 2 |
| **Phase 4** | 2日 | 価格・在庫同期 | Phase 3 |
| **Phase 5** | 1-2日 | レガシーデータ移行 | Phase 2 |
| **Phase 6** | 2-3日 | テスト・本番展開、ドキュメント | All |

**合計所要期間**: **12-17日**（作業日ベース）

---

## ⚠️ 留意事項

### 1. ポリシーID

**課題**:
- レガシーのポリシーID（payment, return, fulfillment）が新規システムでも有効か確認が必要
- 無効な場合は再作成が必要

**対応**:
- Phase 1でポリシーIDバリデーション機能を実装
- 無効な場合は `scripts/setup_policies.py` でポリシー再作成

---

### 2. カテゴリID

**課題**:
- Taxonomy APIの推薦結果の精度
- カテゴリ変更時のItem Specifics要件の差分対応

**対応**:
- カテゴリ推薦結果をキャッシュして効率化
- 推薦失敗時のフォールバックカテゴリ設定（例: Action Figures）
- カテゴリ別必須Item Specificsの自動取得・適用

---

### 3. 画像URL

**課題**:
- レガシーではAmazon画像URLを直接使用
- 新規システムではSP-APIから取得した画像URLを使用

**対応**:
- SP-APIから取得した画像URLをそのまま使用
- 画像URLが取得できない場合のエラーハンドリング

---

### 4. レート制限

**課題**:
- eBay Inventory API: **5,000リクエスト/日**（アプリケーション単位）
- Taxonomy API: **5,000リクエスト/日**（アプリケーション単位）
- 大量出品時は分散処理が必要

**対応**:
- スケジューラーで時間分散（6AM-11PM JST）
- レート制限遵守のウェイト処理実装
- カテゴリ推薦結果のキャッシュ活用

---

### 5. テスト環境

**推奨**:
- Sandbox環境での動作確認を推奨
- 本番環境への移行は段階的に
- 初回は少量（10-20件）でテスト

**Sandbox設定**:
- `environment='sandbox'` で動作
- Sandboxアカウント・トークンが必要

---

### 6. 価格計算

**課題**:
- JPY → USD 変換レート
- マークアップ率

**対応**:
- レガシーの `scripts/currency_manager.py` を参考に為替レート取得
- マークアップ率は設定ファイルで管理（デフォルト: 1.3 = 30%上乗せ）

---

### 7. Item Specifics（Aspects）

**課題**:
- カテゴリごとに必須Item Specificsが異なる
- レガシーでは動的に生成していた

**対応**:
- `CategoryMapper.get_category_specifics()` でカテゴリ必須項目を取得
- SP-APIから取得した商品情報をマッピング
- 不足項目は「Does not apply」等で補完

---

### 8. 在庫切れ時の処理

**課題**:
- BASEは「非公開」に変更
- eBayは「Offer削除」または「数量0更新」

**対応**:
- Phase 4で要件確認
- 暫定案: Offer削除（再出品時に再作成）

---

## 🔄 レガシーシステムとの並行運用

### 移行期間中の運用

**推奨**:
- レガシーシステムは当面停止せず、並行運用
- 新規出品は新システムで実施
- 既存出品の価格・在庫同期はレガシーで継続

**完全移行後**:
- 全出品を新システムで管理
- レガシーシステムは参照用に保持

---

## 📚 参考資料

### レガシーシステム

- **場所**: `C:\Users\hiroo\Documents\ama-cari\ebay_pj`
- **主要ファイル**:
  - `core/listing.py`
  - `core/inventory.py`
  - `core/token_manager.py`
  - `scripts/upload_to_ebay.py`

### 新規システム（ecauto）

- **README.md**: プロジェクト全体概要
- **platforms/base/README.md**: BASE統合の参考実装
- **scheduler/README.md**: スケジューラー仕様
- **docs/WORKFLOW_IMPROVEMENT_2025-11-21.md**: ワークフロー自動化の実装例

### eBay API ドキュメント

- [eBay Inventory API](https://developer.ebay.com/api-docs/sell/inventory/overview.html)
- [eBay Taxonomy API](https://developer.ebay.com/api-docs/commerce/taxonomy/overview.html)
- [eBay OAuth](https://developer.ebay.com/api-docs/static/oauth-tokens.html)

---

## 📝 変更履歴

| 日付 | バージョン | 変更内容 | 担当 |
|------|-----------|---------|------|
| 2025-11-28 | 1.0 | 初版作成 | Claude |

---

**Document Version**: 1.0
**Last Updated**: 2025-11-28
**Author**: Claude (AI Assistant)
**Status**: 実装開始準備完了
