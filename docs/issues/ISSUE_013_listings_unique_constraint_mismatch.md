# Issue #013: listingsのUNIQUE制約設計ミスとaccount_id別出品の不整合

**ステータス**: ✅ 解決済み
**発生日**: 2025-11-26
**優先度**: 高
**担当**: Claude Code

---

## 問題の詳細

### エラー内容

upload_daemon.py実行時に、以下のエラーが多発：

```
ValueError: 出品情報が見つかりません: B0CVXF4N37, account=base_account_1
ValueError: 出品情報が見つかりません: B007OP23DQ, account=base_account_1
ValueError: 出品情報が見つかりません: B0DDL8WGH5, account=base_account_1
...
```

**成功率**: 約20%（成功2件、失敗8件のパターンが多発）

### データ統計

```
listingsテーブル:
  base_account_1: 10,431件（listed: 9,922件、pending: 509件）
  base_account_2:  1,686件（listed: 1,005件、pending: 681件）

upload_queueとlistingsの不一致:
  パターン1: upload_queue (account_1) あり、listings (account_1) なし → 465件
  パターン2: upload_queue (account_2) あり、listings (account_2) なし → 729件
  合計: 1,194件のASINでlistingsが欠損
```

### 症状

1. **account_id別にlistingsを作成できない**
   - base_account_1とbase_account_2で同じASINを別々に出品したい
   - しかし、UNIQUE制約エラーにより、2つ目のlistingsを作成できない

2. **SKUプレフィックスの不一致**
   - 既存のlistings: `s-B0CB5G8NRV-20251009`（`s-`プレフィックス）
   - 新規のlistings: `b-B0CVXF4N37-20251126`（`b-`プレフィックス）
   - ProductRegistrarは既存のlistingsを検出できず、新規作成を試みてUNIQUE制約エラー

---

## 根本原因

### データベーススキーマの設計ミス

[inventory/core/master_db.py:82-120](../../inventory/core/master_db.py#L82-L120)

```python
# listings テーブル（出品情報）
CREATE TABLE IF NOT EXISTS listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asin TEXT,
    platform TEXT,
    account_id TEXT,
    sku TEXT UNIQUE,  # ← 問題1: SKUがUNIQUE制約
    ...
)

# 問題2: (asin, platform)のUNIQUE制約
# コメント: 「同じASINは1つのplatform内で1つのみ出品可能」
CREATE UNIQUE INDEX IF NOT EXISTS idx_listings_asin_platform_unique
ON listings(asin, platform)  # ← account_idが含まれていない！
```

**設計の矛盾:**

| 実際のUNIQUE制約 | 実際の要件 | 結果 |
|-----------------|-----------|------|
| (asin, platform) | account_id別に同じASINを出品したい | ❌ 2つ目のlistingsを作成できない |

### なぜ既存のlistingsが存在するのか？

現在のデータベースには、base_account_1に10,431件、base_account_2に1,686件のlistingsが存在しています。これは、以下の理由が考えられます：

1. **UNIQUE INDEXが後から追加された**
   - 既存のデータには制約が適用されていない
   - 新規データのみ制約が適用される

2. **異なるASINでaccount_idが分かれている**
   - 同じASINでaccount_idが異なるケースは少数
   - 大部分のASINは1つのaccount_idでのみ出品されている

### ProductRegistrarの動作

[inventory/core/product_registrar.py:232-243](../../inventory/core/product_registrar.py#L232-L243)

```python
except Exception as e:
    if 'UNIQUE constraint failed' in str(e):
        print(f"  [INFO] listings既存スキップ ({asin})")
        # 既存のlistingからSKUを取得
        existing_listings = self.master_db.get_listings_by_asin(asin)
        existing_listing = next((l for l in existing_listings
                                if l['platform'] == platform
                                and l['account_id'] == account_id), None)
        if existing_listing:
            result['sku'] = existing_listing['sku']
        # ← account_idが一致しない場合、SKUを取得できない
```

**問題点:**
- UNIQUE制約エラーが発生
- `account_id`が一致するlistingsを検索
- しかし、既存のlistingsは異なる`account_id`（例: base_account_2）のため、見つからない
- 結果：`sku`がNoneのまま、queue登録は成功するが、listingsは欠損

---

## 解決方法

### アプローチ: UNIQUE制約の修正とlistings補完

```
Step 1: UNIQUE制約の修正
  (asin, platform) → (asin, platform, account_id)

Step 2: 欠損したlistingsの補完
  1,194件のASINについてlistingsを作成

Step 3: upload_daemon.pyの互換性確認
  修正後のデータで正常に動作することを確認
```

---

## 実装計画

### Phase 1: UNIQUE制約の修正

**ステップ1: 既存のUNIQUE INDEXを削除**

```sql
DROP INDEX IF EXISTS idx_listings_asin_platform_unique;
```

**ステップ2: 新しいUNIQUE INDEXを作成**

```sql
-- (asin, platform, account_id)の組み合わせでUNIQUE
CREATE UNIQUE INDEX IF NOT EXISTS idx_listings_asin_platform_account_unique
ON listings(asin, platform, account_id);
```

**ステップ3: master_db.pyのスキーマを更新**

[inventory/core/master_db.py:116-120](../../inventory/core/master_db.py#L116-L120) を修正：

```python
# 修正前
# UNIQUE制約: 同じASINは1つのplatform内で1つのみ出品可能
CREATE UNIQUE INDEX IF NOT EXISTS idx_listings_asin_platform_unique
ON listings(asin, platform)

# 修正後
# UNIQUE制約: 同じASINは1つのplatformの同じアカウント内で1つのみ出品可能
CREATE UNIQUE INDEX IF NOT EXISTS idx_listings_asin_platform_account_unique
ON listings(asin, platform, account_id)
```

### Phase 2: 欠損したlistingsの補完

**対象:**
- パターン1: upload_queue (account_1) あり、listings (account_1) なし → 465件
- パターン2: upload_queue (account_2) あり、listings (account_2) なし → 729件
- 合計: 1,194件

**補完スクリプト:** `inventory/scripts/補完_missing_listings.py`

```python
"""
欠損したlistingsを補完するスクリプト
"""
from inventory.core.master_db import MasterDB
from inventory.core.product_registrar import ProductRegistrar

def補完_missing_listings():
    db = MasterDB()
    registrar = ProductRegistrar(master_db=db)

    # パターン1: account_1でlistingsが欠損しているASIN
    with db.get_connection() as conn:
        cursor = conn.execute('''
            SELECT DISTINCT q.asin, q.account_id
            FROM upload_queue q
            LEFT JOIN listings l ON q.asin = l.asin
                AND q.account_id = l.account_id
                AND q.platform = l.platform
            WHERE q.platform = 'base'
              AND q.account_id = 'base_account_1'
              AND l.asin IS NULL
        ''')
        missing_account_1 = cursor.fetchall()

    # パターン2: account_2でlistingsが欠損しているASIN
    with db.get_connection() as conn:
        cursor = conn.execute('''
            SELECT DISTINCT q.asin, q.account_id
            FROM upload_queue q
            LEFT JOIN listings l ON q.asin = l.asin
                AND q.account_id = l.account_id
                AND q.platform = l.platform
            WHERE q.platform = 'base'
              AND q.account_id = 'base_account_2'
              AND l.asin IS NULL
        ''')
        missing_account_2 = cursor.fetchall()

    # 補完処理
    for asin, account_id in missing_account_1 + missing_account_2:
        # productsから商品情報を取得
        product = db.get_product(asin)
        if not product:
            continue

        # listingsを作成
        result = registrar.register_product(
            asin=asin,
            platform='base',
            account_id=account_id,
            product_data={
                'amazon_price_jpy': product.get('amazon_price_jpy'),
                ...
            },
            add_to_queue=False  # queueには追加しない
        )
```

---

## 実装手順

### 1. バックアップの作成

```bash
# データベースのバックアップ
cp inventory/data/master.db inventory/data/master.db.backup_20251126
```

### 2. UNIQUE制約の修正

```bash
# スキーマ修正スクリプトを実行
python inventory/scripts/fix_listings_unique_constraint.py
```

### 3. 欠損したlistingsの補完

```bash
# 補完スクリプトを実行
python inventory/scripts/補完_missing_listings.py
```

### 4. 検証

```bash
# データ整合性チェック
python inventory/scripts/verify_listings_integrity.py
```

### 5. upload_daemon.pyで動作確認

```bash
# デーモンを起動してテスト
python scheduler/upload_daemon.py --platform base
```

---

## 期待される結果

### 修正前

```
upload_queueとlistingsの不一致: 1,194件
upload_daemon.py成功率: 約20%
```

### 修正後

```
upload_queueとlistingsの不一致: 0件
upload_daemon.py成功率: 100%（エラーがある場合は個別のエラー）
```

---

## リスク評価

### リスク1: 既存データへの影響

**リスクレベル:** 低

- UNIQUE INDEXの削除と再作成は、既存データには影響しない
- 新しいUNIQUE制約（asin, platform, account_id）は、既存データと矛盾しない

### リスク2: 補完処理の失敗

**リスクレベル:** 中

- 1,194件のlistingsを作成する際、エラーが発生する可能性がある
- 対策：バッチ処理でエラーをログに記録し、成功した件数を追跡

### リスク3: upload_daemon.pyとの互換性

**リスクレベル:** 低

- upload_daemon.pyは(asin, account_id, platform)でlistingsを検索している
- UNIQUE制約の変更は検索ロジックに影響しない

---

## 関連ファイル

### 修正ファイル

1. **inventory/core/master_db.py** (Lines 116-120)
   - UNIQUE制約の定義を変更

### 新規作成

1. **inventory/scripts/fix_listings_unique_constraint.py**
   - UNIQUE制約を修正するスクリプト

2. **inventory/scripts/補完_missing_listings.py**
   - 欠損したlistingsを補完するスクリプト

3. **inventory/scripts/verify_listings_integrity.py**
   - データ整合性を検証するスクリプト

### バックアップ

1. **inventory/data/master.db.backup_20251126**
   - 修正前のデータベースバックアップ

---

## 関連Issue

- **Issue #001**: upload_queueとlistingsの整合性不整合（解決済み）
  - データ整合性の原則を定義

- **Issue #012**: import_candidates_to_master.pyのlistings登録欠落とコード重複（解決済み）
  - ProductRegistrarの実装

- **Issue #014**: upload_queueのUNIQUE制約欠如と重複レコード問題（次のIssue）
  - upload_queueの重複レコードのクリーンアップ

---

## 次のステップ

1. ✅ 問題の特定と分析（完了）
2. ✅ UNIQUE制約の修正スクリプト作成（完了）
3. ✅ 欠損したlistingsの補完スクリプト作成（完了）
4. ✅ テスト実行（完了）
5. ✅ 本番適用（完了）
6. ✅ upload_daemon.pyで動作確認（完了）

---

## 実施結果

**実施日**: 2025-11-26

### Phase 1: UNIQUE制約の修正

**実施内容:**
1. [master_db.py](../../inventory/core/master_db.py#L116-L121) のスキーマ定義を更新
   - 旧: `(asin, platform)` → 新: `(asin, platform, account_id)`
2. [fix_listings_unique_constraint.py](../../inventory/scripts/fix_listings_unique_constraint.py) を実行
   - 旧制約 `idx_listings_asin_platform_unique` を削除
   - 新制約 `idx_listings_asin_platform_account_unique` を作成

**結果:**
- ✅ UNIQUE制約の修正完了
- ✅ 重複レコード: 0件
- ✅ 旧制約の削除確認

### Phase 2: 欠損したlistingsの補完

**実施内容:**
1. [backfill_missing_listings.py](../../inventory/scripts/backfill_missing_listings.py) を実行
   - 修正前の欠損: 1,191件（account_1: 462件、account_2: 729件）

**結果:**
- ✅ 補完成功: 1,165件
- ⚠️  スキップ（productsなし）: 26件
- listings総数: 12,505件 → 13,670件（+1,165件）

**補完後の統計:**
```
欠損しているlistings:
  - account_1: 16件（462件から改善）
  - account_2: 10件（729件から改善）
  - 合計: 26件（1,191件から改善）

listings総数: 13,670件
  - base_account_1: 10,880件（pending: 958件、listed: 9,922件）
  - base_account_2: 2,405件（pending: 1,400件、listed: 1,005件）
  - ebay_main: 385件
```

### Phase 3: データ整合性検証

**実施内容:**
1. [verify_listings_integrity.py](../../inventory/scripts/verify_listings_integrity.py) を実行

**結果:**
- ✅ UNIQUE制約: 正しく設定されている
- ✅ 重複レコード: 0件
- ✅ productsとの整合性: 問題なし
- ⚠️  残り26件の欠損: productsに商品情報が存在しないため、正当な欠損

### 成果

**修正前:**
```
upload_queueとlistingsの不一致: 1,191件
upload_daemon.py成功率: 約20%
```

**修正後:**
```
upload_queueとlistingsの不一致: 26件（productsなしのため正当）
期待されるupload_daemon.py成功率: 98%以上（26件/総数を除く）
```

### Phase 4: upload_daemon.py動作確認

**実施日**: 2025-11-26 16:21

**実施内容:**
1. Issue #015で価格情報欠落92件をクリーンアップ後、upload_daemon.pyを再起動
2. 2バッチ分の処理結果を確認

**結果:**
- ✅ 「価格情報が不正です」エラー: 完全に解消
- ✅ 正常なASINは正しく処理される（2件成功）
- ✅ 重複出品の検出: 正常に動作
- ✅ UNIQUE制約とlistings補完: 正常に機能

**バッチ処理結果:**
```
第1バッチ: 成功1件、失敗2件（タイトルなし※）、スキップ7件（重複出品済み）
第2バッチ: 成功1件、失敗1件（タイトルなし※）、スキップ1件（重複出品済み）

※「タイトルが取得できません」エラーはIssue #015の範疇
```

**最終確認:**
- listings補完: 1,165件成功
- UNIQUE制約: 正しく設定され、重複なし
- upload_daemon.py: 正常なASINを正しく処理可能

### 残課題

**26件のproductsなしASIN:**
- これらのASINはproductsテーブルに商品情報が存在しないため、listingsを作成できない
- 対応方法:
  1. upload_queueから削除する
  2. productsに商品情報を追加する（SP-APIから取得など）
  3. そのままにしておく（upload_daemon.pyがエラーをログに記録する）

**商品情報不完全の問題:**
- Issue #015として切り分け
- 価格情報・タイトル情報が欠落しているASINの調査と修正

---

**最終更新**: 2025-11-26 16:30
**ドキュメント作成者**: Claude Code
