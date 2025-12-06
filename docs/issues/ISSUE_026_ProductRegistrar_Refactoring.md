# ISSUE #026: ProductRegistrar リファクタリング - 単一責任原則違反の修正

**作成日**: 2025-12-02
**優先度**: 🟡 Medium
**ステータス**: ✅ 完了
**完了日**: 2025-12-02

---

## 📋 概要

`ProductRegistrar`クラスが複数の責務を持ちすぎており、単一責任原則（Single Responsibility Principle）に違反している。
また、プロジェクト内で一貫性のない登録方法が混在しており、コードの保守性・テスト性・デバッグ性が低下している。

### 現在の問題点

1. **ProductRegistrarの責務過多**
   - `register_product()`メソッドが3つの異なるテーブルを操作:
     - `products`テーブルへの登録
     - `listings`テーブルへの登録
     - `upload_queue`への追加
   - 1つのメソッドが複数の関心事を持つため、変更が困難

2. **コードの一貫性の欠如**
   - 異なるスクリプトで異なるアプローチを使用:
     - `sourcing/scripts/import_candidates_to_master.py`: ProductRegistrarを使用
     - `inventory/scripts/add_new_products.py`: 直接UploadQueueManagerを呼び出し
   - 同じ処理を実現するための複数の実装パスが存在

3. **保守性の低下**
   - テーブル操作が分離されていないため、個別のテストが困難
   - エラーハンドリングが複雑化
   - デバッグ時にどの処理で問題が発生したか特定しづらい

---

## 🔍 現在の実装

### ProductRegistrar.register_product()

**ファイル**: [inventory/core/product_registrar.py:39-184](../../inventory/core/product_registrar.py#L39-L184)

```python
def register_product(
    self,
    asin: str,
    platform: str,
    account_id: str,
    product_data: Dict[str, Any],
    markup_rate: float = 1.3,
    priority: int = UploadQueueManager.PRIORITY_NORMAL,
    add_to_queue: bool = True
) -> Dict[str, bool]:
    """
    商品を一括登録（products + listings + upload_queue）
    """
    # 1. productsテーブルに登録 (lines 99-123)
    self.master_db.add_product(...)

    # 2. listingsテーブルに登録 (lines 124-166)
    self.master_db.add_listing(...)

    # 3. upload_queueに追加 (lines 167-183)
    self.queue_manager.add_to_queue(...)
```

**問題**:
- 3つの異なる操作が1つのメソッドに密結合
- 個別の操作をテストすることが困難
- エラー時のリカバリーが複雑

### 一貫性のない使用例

#### パターン1: ProductRegistrarを使用

**ファイル**: [sourcing/scripts/import_candidates_to_master.py:294-302](../../sourcing/scripts/import_candidates_to_master.py#L294-L302)

```python
result = self.product_registrar.register_product(
    asin=asin,
    platform='base',
    account_id=account_id,
    product_data=product_data,
    markup_rate=1.3,
    priority=UploadQueueManager.PRIORITY_NORMAL,
    add_to_queue=True
)
```

#### パターン2: 直接UploadQueueManagerを使用

**ファイル**: [inventory/scripts/add_new_products.py:566-574](../../inventory/scripts/add_new_products.py#L566-L574)

```python
result = queue_manager.add_batch_to_queue(
    asins=successfully_added_asins,
    platform=args.platform,
    account_id=args.account_id,
    priority=args.queue_priority,
    distribute_time=True,
    ...
)
```

---

## 🎯 推奨対応

### アーキテクチャ設計

#### 1. 責務の分離

各テーブル操作を個別のマネージャークラスに分離:

```
┌─────────────────────┐
│  ProductManager     │ ← productsテーブル専用
│  - add_product()    │
│  - get_product()    │
│  - update_product() │
└─────────────────────┘

┌─────────────────────┐
│  ListingManager     │ ← listingsテーブル専用
│  - add_listing()    │
│  - get_listing()    │
│  - update_listing() │
└─────────────────────┘

┌─────────────────────┐
│  QueueManager       │ ← upload_queue専用（既存）
│  - add_to_queue()   │
│  - get_queue_item() │
└─────────────────────┘
```

#### 2. オプショナル: バッチ操作用ラッパー

必要に応じて、バッチ操作用のラッパークラスを提供:

```python
class ProductRegistrationPipeline:
    """
    複数のマネージャーを組み合わせたバッチ操作用パイプライン
    （オプショナル）
    """
    def __init__(self):
        self.product_manager = ProductManager()
        self.listing_manager = ListingManager()
        self.queue_manager = QueueManager()

    def register_and_queue(
        self,
        asin: str,
        platform: str,
        account_id: str,
        product_data: Dict[str, Any],
        **kwargs
    ) -> Dict[str, bool]:
        """
        products → listings → queue の順で登録
        """
        # Step 1: Product registration
        product_result = self.product_manager.add_product(asin, product_data)

        # Step 2: Listing registration
        listing_result = self.listing_manager.add_listing(
            asin, platform, account_id, **kwargs
        )

        # Step 3: Queue addition
        queue_result = self.queue_manager.add_to_queue(
            asin, platform, account_id, **kwargs
        )

        return {
            'product_added': product_result,
            'listing_added': listing_result,
            'queue_added': queue_result
        }
```

### メリット

1. **テスト性の向上**
   - 各マネージャーを個別にユニットテスト可能
   - モックを使った統合テストが容易

2. **デバッグ性の向上**
   - どのテーブル操作でエラーが発生したか明確
   - ログ出力が整理される

3. **保守性の向上**
   - 各マネージャーの責務が明確
   - コード変更時の影響範囲が限定的

4. **再利用性の向上**
   - 個別のマネージャーを異なる組み合わせで使用可能
   - プロジェクト全体で統一されたインターフェース

---

## 📋 実施プラン

### Phase 1: 設計と実装（推定: 2-3日）

1. **ProductManagerの実装**
   - `inventory/core/product_manager.py`を作成
   - `MasterDB.add_product()`のロジックを移行
   - ユニットテストを作成

2. **ListingManagerの実装**
   - `inventory/core/listing_manager.py`を作成
   - `MasterDB.add_listing()`のロジックを移行
   - ユニットテストを作成

3. **QueueManagerの確認**
   - 既存の`scheduler/queue_manager.py`を確認
   - 必要に応じてリファクタリング

### Phase 2: 既存コードの移行（推定: 1-2日）

1. **ProductRegistrarの非推奨化**
   - Deprecation warningを追加
   - ドキュメントに移行ガイドを記載

2. **主要スクリプトの更新**
   - `sourcing/scripts/import_candidates_to_master.py`
   - `inventory/scripts/add_new_products.py`
   - その他のProductRegistrar使用箇所

3. **統合テスト**
   - エンドツーエンドのテストを実施
   - 既存の動作が維持されていることを確認

### Phase 3: クリーンアップ（推定: 1日）

1. **ProductRegistrarの削除**
   - Deprecation期間後に削除
   - 関連ドキュメントの更新

2. **ドキュメント更新**
   - `QUICKSTART.md`
   - `README.md`
   - アーキテクチャドキュメント

---

## 🔒 注意事項

1. **既存の動作を破壊しない**
   - 段階的に移行を進める
   - 十分なテストを実施

2. **後方互換性**
   - 必要に応じてProductRegistrarをラッパーとして残す
   - Deprecation warningで段階的に移行を促す

3. **パフォーマンス**
   - データベースアクセスの最適化を維持
   - トランザクション管理を適切に行う

---

## 📊 期待される効果

| 項目 | 改善前 | 改善後 |
|------|--------|--------|
| テスト性 | 🔴 困難（複数の処理が密結合） | 🟢 容易（個別にテスト可能） |
| デバッグ性 | 🟡 中程度（エラー箇所の特定が困難） | 🟢 良好（エラー箇所が明確） |
| 保守性 | 🔴 低い（変更の影響範囲が広い） | 🟢 高い（変更の影響が限定的） |
| コードの一貫性 | 🔴 低い（複数の実装パス） | 🟢 高い（統一されたインターフェース） |
| 再利用性 | 🟡 中程度 | 🟢 高い（柔軟な組み合わせ） |

---

## 📝 関連ファイル

### 現在の実装
- [inventory/core/product_registrar.py](../../inventory/core/product_registrar.py) - リファクタリング対象
- [inventory/core/master_db.py](../../inventory/core/master_db.py) - 既存のDB操作
- [scheduler/queue_manager.py](../../scheduler/queue_manager.py) - 既存のキュー管理

### 使用箇所
- [sourcing/scripts/import_candidates_to_master.py](../../sourcing/scripts/import_candidates_to_master.py) - ProductRegistrarを使用
- [inventory/scripts/add_new_products.py](../../inventory/scripts/add_new_products.py) - 直接UploadQueueManagerを使用

### 関連ドキュメント
- [QUICKSTART.md](../../QUICKSTART.md) - 使用方法ガイド
- [CHEATSHEET.md](../../CHEATSHEET.md) - 運用コマンド集

---

## 💬 議論メモ

### ユーザーフィードバック（2025-12-02）

> 基本的に複数のテーブルの更新をひとつのスクリプトにまとめるべきではないと考えます。
>
> - プロダクトマスタの更新をするマネージャ
> - リスティングの更新をするマネージャ
> - アップロードキューへの追加をするマネージャ
>
> これら3つは独立していて、必要な処理に応じて順番に実行するべきではないでしょうか？
>
> まとめて実行したい場合はそのためのwrapperを用意すればいいと思います。そうすればデバッグもしやすいし、コードの再利用性も高まります。

### 同意事項

1. 単一責任原則に従った設計への移行
2. 個別のマネージャーによる責務の分離
3. 必要に応じたラッパーの提供
4. テスト性・デバッグ性・再利用性の向上

---

## 🎉 実施完了（2025-12-02）

### ✅ 実装内容

#### 1. 新しいマネージャークラスの実装

**ProductManager** ([inventory/core/product_manager.py](../../inventory/core/product_manager.py))
- productsテーブル専用の操作を担当
- 主要メソッド:
  - `add_product()`: 商品追加（既存値保持機能付き）
  - `get_product()`: 商品取得
  - `update_amazon_info()`: Amazon情報更新
  - `product_exists()`: 存在確認

**ListingManager** ([inventory/core/listing_manager.py](../../inventory/core/listing_manager.py))
- listingsテーブル専用の操作を担当
- 主要メソッド:
  - `add_listing()`: 出品追加
  - `upsert_listing()`: 出品追加または更新
  - `get_listing_by_sku()`: SKUで取得
  - `get_listings_by_asin()`: ASINで取得
  - `get_listings_by_account()`: アカウント別取得
  - `update_listing()`: 出品更新
  - `listing_exists()`: 存在確認

#### 2. 既存スクリプトの移行

**sourcing/scripts/import_candidates_to_master.py**
- ProductRegistrarの使用を廃止
- ProductManager、ListingManager、QueueManagerを個別に使用
- 処理の流れを明確化:
  1. ProductManager → productsテーブル登録
  2. ListingManager → listingsテーブル登録（SKU生成、売価計算含む）
  3. QueueManager → upload_queue登録
- エラーハンドリングを各ステップで個別に実施

**inventory/scripts/add_new_products.py**
- MasterDB直接呼び出しをマネージャー経由に変更
- ProductManager、ListingManagerを使用
- コードの一貫性を確保

#### 3. バックアップ

以下のファイルのバックアップを作成:
- `inventory/core/product_registrar.py.backup_20251202_issue026`
- `sourcing/scripts/import_candidates_to_master.py.backup_20251202_issue026`
- `inventory/scripts/add_new_products.py.backup_20251202_issue026`

#### 4. テスト結果

**ProductManager単体テスト**: ✅ 成功
```
ASIN: B0TEST001
商品追加: OK
商品取得: OK
  タイトル: テスト商品
  価格: 2000円
```

**ListingManager単体テスト**: ✅ 成功
```
ASIN: B0TEST001
SKU: BASE-B0TEST001-20251202
出品追加: OK
  Listing ID: 17554
出品取得: OK
  売価: 2600.0円
  ステータス: pending
```

**import_candidates_to_master.py (dry-run)**: ✅ 成功
- 3件のASINで正常動作確認
- 新しいマネージャーが正しく呼び出されることを確認

**add_new_products.py**: ✅ 成功
- 2件のASINで正常動作確認
- ProductManager、ListingManagerが正しく動作

### 🎯 達成された改善効果

| 項目 | 改善前 | 改善後 |
|------|--------|--------|
| テスト性 | 🔴 困難（複数の処理が密結合） | 🟢 容易（個別にテスト可能） |
| デバッグ性 | 🟡 中程度（エラー箇所の特定が困難） | 🟢 良好（エラー箇所が明確） |
| 保守性 | 🔴 低い（変更の影響範囲が広い） | 🟢 高い（変更の影響が限定的） |
| コードの一貫性 | 🔴 低い（複数の実装パス） | 🟢 高い（統一されたインターフェース） |
| 再利用性 | 🟡 中程度 | 🟢 高い（柔軟な組み合わせ） |

### 📝 備考

- ProductRegistrarは後方互換性のため残しているが、新規開発では使用非推奨
- 既存のすべての主要スクリプトを新しいマネージャーに移行完了
- 実装は単一責任原則に従い、テスト性・保守性が大幅に向上

### 🔧 追加機能: アクティブアカウントフィルタリング（2025-12-02）

**問題**:
`import_candidates_to_master.py` が、`account_config.json` の `active` フラグを無視して、非アクティブなアカウントにも商品を割り当てていた。

**実装内容**:
1. `_load_active_accounts()` メソッドを追加
2. `account_config.json` から `"active": true` のアカウントのみを読み込む
3. ハードコードされた `self.accounts = ['base_account_1', 'base_account_2']` を動的読み込みに変更

**コード**:
```python
def _load_active_accounts(self) -> List[str]:
    """
    account_config.jsonからアクティブなアカウントのみを読み込む

    Returns:
        List[str]: アクティブなアカウントIDのリスト
    """
    config_path = project_root / 'platforms' / 'base' / 'accounts' / 'account_config.json'

    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    active_accounts = [
        account['id']
        for account in config['accounts']
        if account.get('active', False)
    ]

    if not active_accounts:
        print("[WARNING] アクティブなアカウントが見つかりません")
        return []

    return active_accounts
```

**テスト結果**: ✅ 成功
- base_account_1 (active=false) が自動的に除外される
- base_account_2 (active=true) のみに商品が割り当てられる
- listingsテーブル、upload_queueともに正常動作を確認

**効果**:
- アカウントの有効/無効を `account_config.json` で一元管理可能
- 非アクティブアカウントへの誤割り当てを防止
- コードの保守性が向上（アカウントリストのハードコードを削除）

### 🔧 追加機能: 段階的な処理フロー - --products-only オプション（2025-12-02）

**背景**:
将来的に多数の出品先プラットフォーム（BASE、eBay、Yahoo!オークション、メルカリなど）への展開を予定しており、「ASIN情報収集」→「プラットフォーム/アカウント選択」→「出品」という段階的な処理が必要。

**実装内容**:
1. `--products-only` オプションを追加
2. このオプションが指定された場合、productsテーブルのみに登録（listingsとqueueはスキップ）
3. `add_to_listings` パラメータを追加して、listingsテーブルへの登録を制御

**コマンド例**:
```bash
# productsテーブルのみに登録（出品先未決定）
python sourcing\scripts\import_candidates_to_master.py --limit 1000 --products-only
```

**処理内容**:
- ✅ productsテーブルに登録（商品情報・価格情報を取得）
- ❌ listingsテーブルには登録しない（出品先未決定）
- ❌ upload_queueには追加しない

**テスト結果**: ✅ 成功
```
処理対象ASIN: 3件
商品情報取得成功: 3件
- products: 3件登録 ✅
- listings: 0件 ✅
- upload_queue: 0件 ✅
```

**効果**:
- **柔軟な処理フロー**: 商品情報収集と出品処理を完全に分離
- **マルチプラットフォーム対応**: 後で最適なプラットフォーム/アカウントを選択可能
- **段階的な運用**: ASIN収集 → 分析 → プラットフォーム選択 → 出品
- **リファクタリングの成果**: 単一責任原則に従った設計により、容易に実装可能

**ドキュメント**:
- [CHEATSHEET.md - 2.5 ASIN情報収集のみ](../../CHEATSHEET.md#25-asin情報収集のみproductsテーブルのみ)

---

**作成者**: Claude Code
**最終更新**: 2025-12-02
