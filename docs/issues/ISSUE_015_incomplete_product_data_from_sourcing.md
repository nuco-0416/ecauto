# Issue #015: sourcing/での商品情報取得不完全の原因調査と対策

**ステータス**: ✅ 対策実装完了
**発生日**: 2025-11-26
**優先度**: 中
**担当**: Claude Code
**関連Issue**: Issue #013, Issue #014
**調査完了日**: 2025-11-26
**実装完了日**: 2025-11-26

---

## 問題の詳細

### 発見の経緯

Issue #014のupload_daemon.py動作確認中に、「価格情報が不正です」というバリデーションエラーが多発。調査の結果、商品情報取得処理に問題があることが判明。

### エラー内容

productsテーブルに登録されたASINの一部で、商品情報が不完全な状態になっている。

```
バリデーションエラー: 価格情報が不正です
```

### データ統計

**productsテーブル:**
```
総ASIN数: 12,777件
価格情報なし (amazon_price_jpy IS NULL): 1,038件 (8.1%)
```

**upload_queue (pending):**
```
総pending数: 1,786件
価格情報なし: 82件 (4.6%)
```

**日付別の不完全データ発生率:**
```
2025-11-26: 総数 1,168件, 価格なし 53件 (4.5%)
2025-11-25: 総数 841件, 価格なし 45件 (5.4%)
2025-11-21: 総数 1,880件, 価格なし 51件 (2.7%)
2025-11-20: 総数 1,924件, 価格なし 250件 (13.0%) ← 特に多い
2025-11-19: 総数 6件, 価格なし 4件 (66.7%)
```

### 症状

1. **価格情報の欠落**
   - `amazon_price_jpy` が NULL または 0
   - listingsの `selling_price` も NULL
   - upload_daemon.pyで「価格情報が不正です」エラー

2. **商品情報の欠落**
   - 一部のASINで `title_ja` も NULL
   - `category` が空
   - 商品データ自体が取得できていない

3. **不安定な発生パターン**
   - すべてのASINで失敗するわけではない（8.1%）
   - 日によって発生率が異なる（2.7%〜13.0%）
   - 特定の日（2025-11-20）で発生率が高い

### サンプルASIN

**価格情報なしのASIN例:**
```
B0C6ZXFFFG - MayReel クリスマスリボン
  title_ja: ✓ あり
  amazon_price_jpy: ✗ NULL
  brand: MAYREEL
  category: ✗ 空

B01AS83DCA - Peachy Clean 抗菌性シリコーンスクラバー
  title_ja: ✓ あり
  amazon_price_jpy: ✗ NULL
  brand: Peachy Clean
  category: ✗ 空

B0CQN6FYLN
  title_ja: ✗ NULL
  amazon_price_jpy: ✗ NULL
  brand: (不明)
  category: ✗ 空
```

---

## 根本原因（仮説）

### 仮説1: SP-API取得処理のタイムアウト・レート制限

sourcing/でのSP-API呼び出しが、以下の理由で失敗している可能性：
- APIレート制限に達している
- ネットワークタイムアウト
- 一部のASINでAPIレスポンスが遅延

### 仮説2: エラーハンドリングの不足

取得失敗時に、不完全なデータのままDBに登録してしまっている：
- 価格情報取得失敗 → `amazon_price_jpy` を NULL で登録
- 商品情報取得失敗 → `title_ja` を NULL で登録
- エラーログが不十分で原因が追跡できない

### 仮説3: データバリデーションの欠如

productsへの登録時に、必須項目のバリデーションが行われていない：
- `amazon_price_jpy` が NULL でも登録される
- `title_ja` が NULL でも登録される
- 不完全なproductsが後続処理でエラーを引き起こす

---

## 影響範囲

### 直接的な影響

1. **upload_daemon.pyの失敗**
   - pending 82件が「価格情報が不正です」で失敗予定
   - 現在failed 10件

2. **listings作成の失敗**
   - 価格情報なしでは正しい価格設定ができない
   - 商品情報なしでは出品情報が不完全

### 間接的な影響

1. **データ品質の低下**
   - 8.1%のASINで商品情報が不完全
   - データの信頼性が損なわれる

2. **運用効率の低下**
   - エラー調査に時間がかかる
   - 手動での価格設定が必要になる可能性

---

## 調査方針

### Phase 1: 取得処理の特定

1. sourcing/配下のコードを調査
   - SP-API呼び出しコードの特定
   - 商品情報取得フローの確認
   - エラーハンドリングの実装状況

2. ログの確認
   - 2025-11-20（発生率13.0%）のログを重点調査
   - API失敗ログの有無
   - タイムアウト・レート制限エラーの確認

### Phase 2: 失敗パターンの分析

1. 失敗ASINの共通点を調査
   - 特定のカテゴリ・ブランドに偏っているか
   - ASINの形式（B0で始まるか等）に関連性があるか
   - 取得時刻に規則性があるか

2. 成功ASINとの比較
   - 同じ日に取得されたASINで、成功と失敗の差は何か
   - APIレスポンスの違い

### Phase 3: 再現テスト

1. 失敗ASINの再取得テスト
   - 同じASINで再度SP-APIを呼び出す
   - 成功するか失敗するか
   - 失敗する場合のエラー内容

2. 大量取得時の動作確認
   - 連続でSP-APIを呼び出した際の挙動
   - レート制限に達するかどうか

---

## 対策案

### 短期対策（Issue #013/#014の完了を優先）

1. **不完全レコードのクリーンアップ**
   - pending 82件をupload_queueから削除
   - failed 10件をupload_queueから削除
   - 正常なASINのみで動作確認を完了させる

### 中期対策（データ品質の改善）

1. **取得処理の改善**
   - SP-API呼び出しのリトライ機能追加
   - タイムアウト時間の調整
   - レート制限への対応（待機処理）

2. **バリデーションの追加**
   - productsへの登録前に必須項目チェック
   - `amazon_price_jpy` が NULL の場合は登録しない
   - `title_ja` が NULL の場合は登録しない
   - 不完全データをエラーログに記録

3. **エラーハンドリングの強化**
   - API失敗時のログ記録
   - 失敗ASINのリトライキュー作成
   - 管理者への通知機能

### 長期対策（データ取得の安定化）

1. **取得処理のモニタリング**
   - 取得成功率のダッシュボード
   - 失敗パターンの可視化
   - アラート機能

2. **代替データソースの検討**
   - SP-API以外のデータソース
   - キャッシュ機構の導入

---

## 実装計画

### Step 1: 不完全レコードのクリーンアップ（優先）

**目的:** Issue #013/#014の動作確認を完了させる

**スクリプト:** `scheduler/scripts/cleanup_incomplete_queue.py`

```python
"""
価格情報が欠落しているASINをupload_queueから削除
"""
- pending 82件を削除
- failed 10件（「価格情報が不正です」エラー）を削除
- 削除前にASINリストをファイルに保存（後で再取得可能に）
```

### Step 2: sourcing/コードの調査

**調査対象:**
- `sourcing/` 配下のすべてのPythonファイル
- SP-API呼び出しコードの特定
- エラーハンドリングの実装状況

**成果物:**
- 取得フローの図解
- 問題箇所の特定
- 修正提案書

### Step 3: バリデーション機能の追加

**修正対象:**
- productsへの登録処理
- 必須項目のバリデーション追加
- 不完全データの登録防止

### Step 4: 再取得処理の実装

**機能:**
- 不完全データのASINリストを読み込み
- SP-APIで再取得
- 成功したら正常にproductsとlistingsを登録
- upload_queueに追加

---

## 期待される結果

### 短期（クリーンアップ後）

```
upload_queue (pending): 1,786件 → 1,704件 (-82件)
upload_daemon.py成功率: 「価格情報が不正です」エラーの排除
```

### 中期（バリデーション追加後）

```
productsの品質: 不完全データの登録を防止
新規登録ASINの成功率: 100%（API失敗時は登録しない）
```

### 長期（取得処理改善後）

```
SP-API取得成功率: 95%以上（現在91.9%）
データ品質: 安定した商品情報の取得
運用負荷: エラー調査の削減
```

---

## リスク評価

### リスク1: 削除したASINの再処理

**リスクレベル:** 低

- 削除前にASINリストをファイル保存
- 再取得スクリプトで復旧可能

### リスク2: sourcing/コードの複雑性

**リスクレベル:** 中

- コードが複雑で修正が困難な可能性
- 対策：段階的な改善、十分なテスト

### リスク3: SP-APIの制約

**リスクレベル:** 中

- APIレート制限は変更できない
- 対策：待機処理、リトライ間隔の調整

---

## 関連ファイル（今後調査予定）

### 調査対象

1. **sourcing/配下のすべてのファイル**
   - SP-API呼び出しコード
   - 商品情報取得処理
   - エラーハンドリング

### 新規作成（予定）

1. **scheduler/scripts/cleanup_incomplete_queue.py**
   - 不完全レコードのクリーンアップ

2. **sourcing/scripts/refetch_missing_data.py**
   - 不完全ASINの再取得

3. **docs/sourcing_data_flow.md**
   - データ取得フローの図解

---

## 関連Issue

- **Issue #013**: listingsのUNIQUE制約設計ミスとaccount_id別出品の不整合（解決済み）
  - listings補完時にproductsなしASIN 26件を発見

- **Issue #014**: upload_queueのUNIQUE制約欠如と重複レコード問題（解決済み）
  - upload_daemon.py動作確認時に価格情報エラーを発見

---

---

## 🔍 調査結果（2025-11-26 完了）

### データベース分析結果

**全体統計:**
```
総ASIN数: 12,777件
価格NULL: 1,029件（8.1%）
タイトルNULL: 8,129件（63.6%）← 異常に高い

価格NULLの内訳:
  - 価格NULL & タイトルOK: 352件（34.2%）
  - 価格NULL & タイトルNULL: 677件（65.8%）
```

**不完全データのパターン:**
1. **パターンA: brandあり、title_ja NULL、images NULL、price あり**
   - 商品情報（Catalog API）が不完全
   - 価格情報（Products API）は成功
   - 例: B09DP1ZJV2, B0D93NFXVL

2. **パターンB: title_ja NULL、brand あり、price NULL**
   - 商品情報も価格情報も不完全
   - 例: B0FLTW11NS

### SP-API再取得テスト結果

**重要な発見:**
- **DBで不完全データとして記録されているASINでも、現在のSP-APIでは正常にデータが取得できている**
- 例: B09DP1ZJV2
  - DB: title_ja = NULL, images = NULL
  - 再取得: title_ja = "チャップアップ...", images = 6枚 ✓

**結論:**
- **現在のSP-APIとコードでは、データは正常に取得できている**
- **過去に登録されたデータが不完全**

### 根本原因の特定

#### 原因1: SP-APIからの不完全なレスポンス（過去）

**コード箇所:** `integrations/amazon/sp_api_client.py:294`

```python
product_info['title_ja'] = summary.get('itemName')
```

**問題:**
- SP-APIが`itemName`フィールドを含まないレスポンスを返した場合、`title_ja`はNoneとなる
- `get_product_info()`は部分的なデータでも`None`ではなく辞書を返す
- その不完全なデータがそのまま`MasterDB.add_product()`に渡される
- バリデーションがないため、NULLのままDBに登録される

**原因:**
- 過去のある時期に、SP-APIが不完全なレスポンスを返していた可能性
- または、API一時エラー時に部分的なデータが返された

#### 原因2: エラーハンドリングのバグ

**コード箇所:** `integrations/amazon/sp_api_client.py:963-969`

```python
price_data = self.get_product_price(asin)
product_info.update({
    'amazon_price_jpy': price_data.get('price'),  # ← price_dataがNoneの場合にAttributeError!
    'amazon_in_stock': price_data.get('in_stock', False),
    ...
})
```

**問題:**
- `get_product_price()`はAPIエラー時に`None`を返す（L532-535）
- しかし、`price_data.get()`を呼び出すため、AttributeErrorが発生
- 例外が`import_candidates_to_master.py:244-246`で捕捉されるため、そのASINは登録されない

**影響:**
- このバグ自体は不完全データの登録を引き起こさない
- しかし、コードの堅牢性に問題がある

#### 原因3: バリデーションの欠如

**コード箇所:** `inventory/core/product_registrar.py:87-98`

```python
self.master_db.add_product(
    asin=asin,
    title_ja=product_data.get('title_ja'),  # Noneでも登録される
    ...
    amazon_price_jpy=product_data.get('amazon_price_jpy'),  # Noneでも登録される
)
```

**問題:**
- 必須項目のバリデーションが行われていない
- `title_ja`や`amazon_price_jpy`がNoneでも登録される

---

## ✅ 対策案（優先度順）

### 【最優先】対策1: SP-APIエラーハンドリングのバグ修正

**ファイル:** `integrations/amazon/sp_api_client.py`

**修正箇所:** L963-969（`get_products_batch()`メソッド）

**修正内容:**
```python
# 修正前
price_data = self.get_product_price(asin)
product_info.update({
    'amazon_price_jpy': price_data.get('price'),  # ← AttributeError!
    ...
})

# 修正後
price_data = self.get_product_price(asin)
if price_data:  # Noneチェックを追加
    product_info.update({
        'amazon_price_jpy': price_data.get('price'),
        'amazon_in_stock': price_data.get('in_stock', False),
        'is_prime': price_data.get('is_prime', False),
        'is_fba': price_data.get('is_fba', False)
    })
else:
    # API失敗時はNoneを設定
    product_info.update({
        'amazon_price_jpy': None,
        'amazon_in_stock': False,
        'is_prime': False,
        'is_fba': False
    })
```

### 【優先】対策2: バリデーション機能の追加

**ファイル:** `inventory/core/product_registrar.py`

**修正箇所:** L39-77（`register_product()`メソッド）

**修正内容:**
```python
def register_product(self, asin, platform, account_id, product_data, ...):
    # バリデーション追加
    validation_errors = []

    if not product_data.get('title_ja'):
        validation_errors.append('title_ja is required')

    if not product_data.get('amazon_price_jpy'):
        validation_errors.append('amazon_price_jpy is required')

    if validation_errors:
        print(f"  [VALIDATION ERROR] {asin}: {', '.join(validation_errors)}")
        return {
            'product_added': False,
            'listing_added': False,
            'queue_added': False,
            'sku': None,
            'validation_errors': validation_errors
        }

    # 既存の登録処理...
```

### 【推奨】対策3: 不完全データの再取得スクリプト

**ファイル:** `inventory/scripts/refetch_incomplete_products.py`（新規作成）

**機能:**
1. productsテーブルから不完全データを抽出
   - `title_ja IS NULL`
   - `amazon_price_jpy IS NULL`
2. SP-APIで再取得
3. 成功したらDBを更新
4. listingsとupload_queueも更新

**実行方法:**
```bash
python inventory/scripts/refetch_incomplete_products.py --dry-run
python inventory/scripts/refetch_incomplete_products.py  # 本番実行
```

### 【推奨】対策4: 定期的なデータ整合性チェック

**ファイル:** `inventory/scripts/check_data_integrity.py`（新規作成）

**機能:**
- 不完全データの統計を出力
- アラート機能（不完全データが閾値を超えた場合）
- 日次実行を推奨

---

## 次のステップ

1. ✅ sourcing/コードの調査
2. ✅ 失敗パターンの分析
3. ✅ 根本原因の特定
4. ✅ SP-APIエラーハンドリングのバグ修正
5. ✅ バリデーション機能の追加
6. ✅ 不完全データ再取得スクリプトの作成
7. ⬜ データ整合性チェックスクリプトの作成（オプション）

---

## 📝 実装完了（2025-11-26）

### 実装した対策

#### 1. SP-APIエラーハンドリングのバグ修正 ✅

**ファイル**: [integrations/amazon/sp_api_client.py:963-979](../../integrations/amazon/sp_api_client.py#L963-L979)

**修正内容**:
- `get_product_price()`がNoneを返した場合のチェックを追加
- AttributeErrorを防止し、価格情報がNULLでも処理を継続

```python
price_data = self.get_product_price(asin)
if price_data:  # Noneチェックを追加
    product_info.update({
        'amazon_price_jpy': price_data.get('price'),
        'amazon_in_stock': price_data.get('in_stock', False),
        'is_prime': price_data.get('is_prime', False),
        'is_fba': price_data.get('is_fba', False)
    })
else:
    # API失敗時はNoneを設定
    product_info.update({
        'amazon_price_jpy': None,
        'amazon_in_stock': False,
        'is_prime': False,
        'is_fba': False
    })
```

#### 2. バリデーション機能の追加 ✅

**ファイル**: [inventory/core/product_registrar.py:85-97](../../inventory/core/product_registrar.py#L85-L97)

**修正内容**:
- `register_product()`メソッドに必須項目のバリデーションを追加
- `title_ja`と`amazon_price_jpy`がNULLの場合は登録を拒否
- バリデーションエラーをログに記録

```python
# バリデーション: 必須項目のチェック
validation_errors = []

if not product_data.get('title_ja'):
    validation_errors.append('title_ja is required')

if not product_data.get('amazon_price_jpy'):
    validation_errors.append('amazon_price_jpy is required')

if validation_errors:
    print(f"  [VALIDATION ERROR] {asin}: {', '.join(validation_errors)}")
    result['validation_errors'] = validation_errors
    return result
```

#### 3. 不完全データ再取得スクリプトの作成 ✅

**ファイル**: [inventory/scripts/refetch_incomplete_products.py](../../inventory/scripts/refetch_incomplete_products.py)

**機能**:
- productsテーブルから不完全データ（title_ja or amazon_price_jpyがNULL）を検索
- SP-APIで商品情報を再取得
- productsテーブルとlistingsテーブルを更新
- dry-runモードで事前確認が可能

**使用方法**:
```bash
# 確認のみ（dry-run）
python inventory/scripts/refetch_incomplete_products.py --dry-run

# 実際に更新
python inventory/scripts/refetch_incomplete_products.py

# 処理するASIN数を制限（テスト用）
python inventory/scripts/refetch_incomplete_products.py --limit 10
```

**実行結果（dry-run）**:
```
不完全なproductsレコード: 8,481件
  - title_ja NULL: 8,129件
  - amazon_price_jpy NULL: 1,038件
  - 両方 NULL: 686件
```

### 期待される効果

1. **新規登録時のデータ品質向上**
   - バリデーションにより、不完全データの登録を防止
   - エラーログで問題を早期発見

2. **既存の不完全データの修正**
   - 再取得スクリプトで8,481件の不完全データを修正可能
   - upload_daemon.pyの「価格情報が不正です」エラーを解消

3. **システムの堅牢性向上**
   - SP-APIエラー時のクラッシュを防止
   - 部分的なデータでも適切に処理

### 運用方法

1. **即座に実行すべきこと**
   - 不完全データ再取得スクリプトを実行して、既存データを修正

2. **今後の対応**
   - 新規商品登録時、バリデーションエラーが発生した場合はログを確認
   - SP-APIエラーが多発する場合は、レート制限や認証情報を確認

---

## 🔍 追加調査結果（2025-11-26 21:00）

### 不完全データの真の原因を特定

**title_ja NULL: 8,129件**の内訳を詳細調査した結果、**95.3%（7,745件）がBASE API同期で登録された商品**であることが判明しました。

#### 調査結果

```
title_ja NULL & BASEレコードあり: 7,745件 (95.3%)
title_ja NULL & listingsレコードなし: 0件
title_ja NULL 総数: 8,129件

すべて 2025-11-18 16:56:01 に一括作成
```

#### 根本原因

**ファイル**: [inventory/scripts/sync_from_base_api.py:334-337](../../inventory/scripts/sync_from_base_api.py#L334-L337)

```python
# productsテーブルに追加
cursor.execute("""
    INSERT OR IGNORE INTO products (asin, title_ja)
    VALUES (?, ?)
""", (asin, title))
```

**問題点**:
1. BASE APIの`title`フィールドが空の場合、`title_ja`がNULLで登録される
2. 最小限の情報（ASIN + title_ja）しか登録されない
3. `brand`、`images`、`category`、`description`、**`amazon_price_jpy`**などは一切設定されない
4. BASE APIにはAmazon商品の詳細情報がないため、SP-API呼び出しが必要だが実装されていない

#### 対策（長期）

**Issue #016として新規登録推奨**: `sync_from_base_api.py`の改善

**修正方針**:
1. BASE APIから商品をマージ後、ASINリストを抽出
2. SP-APIで完全な商品情報（title_ja、brand、images、amazon_price_jpy等）を取得
3. productsテーブルを更新

**実装例**:
```python
# 新規追加したASINをリスト化
new_asins = [item['_extracted_asin'] for item in new_items]

# SP-APIで商品情報を一括取得
sp_api_client = AmazonSPAPIClient(SP_API_CREDENTIALS)
for asin in new_asins:
    product_info = sp_api_client.get_product_info(asin)
    if product_info:
        # productsテーブルを完全な情報で更新
        db.update_product(asin, product_info)
```

#### 対策（短期）

現時点では、作成済みの`refetch_incomplete_products.py`スクリプトで7,745件の不完全データを補完することを推奨します：

```bash
# テスト実行
python inventory/scripts/refetch_incomplete_products.py --limit 10

# 全件実行（約21時間かかる見込み: 7,745件 × 2.5秒/ASIN = 5.4時間）
python inventory/scripts/refetch_incomplete_products.py
```

---

---

## 🔍 追加調査結果2: キュー登録の問題（2025-11-26 21:30）

### upload_queueへの不適切な登録

**重大な問題**: すでに出品済み（listings.status='listed'）の商品が2,292件もupload_queueに登録されていることを発見。

#### 調査結果

```
upload_queueで重複登録（すでにlisted）: 2,292件
  - pending: 1,614件（これから処理される予定）
  - failed: 286件（既に失敗）
  - title_ja NULL: 175件（バリデーションエラーの原因）
```

#### 根本原因

**ファイル**: [inventory/core/master_db.py:465-469](../../inventory/core/master_db.py#L465-L469)（修正前）

```python
def add_to_upload_queue(self, asin, platform, account_id, priority, scheduled_at, metadata=None):
    cursor.execute('''
        INSERT INTO upload_queue
        (asin, platform, account_id, scheduled_time, priority, status)
        VALUES (?, ?, ?, ?, ?, 'pending')
    ''', (asin, platform, account_id, scheduled_at_str, priority))
```

**問題点**:
- 既にlistings.status='listed'（出品済み）の商品をチェックする処理が一切ない
- BASE APIから同期された商品（すでに出品済み）でも、無条件にキューに追加される
- 無駄な処理でキューが詰まり、バリデーションエラーを引き起こす

#### 実装した対策

##### 1. add_to_upload_queue()メソッドの修正 ✅

**ファイル**: [inventory/core/master_db.py:462-474](../../inventory/core/master_db.py#L462-L474)

**修正内容**:
- キュー追加前に、既にlistings.status='listed'の商品をチェック
- 既に出品済みの場合はスキップして、Falseを返す

```python
# 既に出品済み（listings.status='listed'）の商品をチェック
cursor.execute('''
    SELECT status, platform_item_id
    FROM listings
    WHERE asin = ? AND platform = ? AND account_id = ?
''', (asin, platform, account_id))

existing_listing = cursor.fetchone()

if existing_listing and existing_listing['status'] == 'listed':
    # 既に出品済みの場合はスキップ
    print(f"  [SKIP] {asin}: 既に出品済み (platform_item_id: {existing_listing['platform_item_id']})")
    return False
```

##### 2. 既存キューのクリーンアップスクリプト作成 ✅

**ファイル**: [scheduler/scripts/cleanup_already_listed_queue.py](../../scheduler/scripts/cleanup_already_listed_queue.py)

**機能**:
- upload_queueから既に出品済みの商品を削除
- pending/failedステータスの重複レコードをクリーンアップ
- dry-runモードで事前確認が可能

**使用方法**:
```bash
# 確認のみ（dry-run）
python scheduler/scripts/cleanup_already_listed_queue.py --dry-run

# 実際に削除
python scheduler/scripts/cleanup_already_listed_queue.py
```

**期待される効果**:
- pending 368件の無駄な処理を回避（既に出品済みの商品）
- failed 140件のエラーレコードをクリーンアップ（既に出品済みの商品）
- 合計 508件のクリーンアップ

**注意**: 残りのpending約1,246件（1,614 - 368）は未出品の正常なキューです。ただし、その中にtitle_ja NULL商品が約592件含まれている可能性があり、これらは別途対応が必要です。

#### ISSUE15との関連性

この問題は**完全にISSUE15の範囲内**です：

1. **直接的な関連**: title_ja NULLの商品175件がキューに登録され、バリデーションエラーを引き起こしている
2. **根本原因は同じ**: BASE API同期時のデータ不完全問題
3. **連鎖的な問題**: 不完全データ → キューに追加 → バリデーションエラー → upload_daemon.py失敗

---

**最終更新**: 2025-11-26 21:30（キュー登録問題を特定・対策実装完了）
**ドキュメント作成者**: Claude Code
