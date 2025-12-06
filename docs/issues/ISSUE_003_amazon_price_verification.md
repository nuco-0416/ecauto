# Issue #003: amazon_price_jpy未設定商品の扱いと同期処理の検証

**ステータス**: 🔵 検証待ち
**発生日**: 2025-11-22（検証の必要性を認識）
**優先度**: 中
**担当**: 未割り当て

---

## 問題の詳細

### 概要

BASE APIから取得した商品で、`selling_price` は設定されているが `amazon_price_jpy` が未設定のケースが存在する。この状態の商品について、以下の検証が必要：

1. 価格・在庫同期処理で `amazon_price_jpy` が適切に保管されるか
2. amazon_price_jpy が未設定の商品をどう扱うべきか
3. cleanup_invalid_listings.py の削除条件が適切か

### 現在の状況

#### データの状態

**BASE APIから取得した商品**:
- `selling_price`: 設定済み（例: 5,230円）
- `amazon_price_jpy`: 未設定（NULL）
- `status`: 'pending' または 'listed'

#### 現在の処理

**cleanup_invalid_listings.py** (改善後):
```python
# Amazon価格未取得のレコードを削除対象とする
WHERE l.status = 'pending'
  AND (p.amazon_price_jpy IS NULL OR p.amazon_price_jpy = 0)
```

この条件により、amazon_price_jpy が未設定の商品は削除される。

### 想定される設計

システムの本来の想定：

1. **BASE APIから商品を取得** → `selling_price` のみ設定
2. **定期的な価格・在庫同期処理を実行** → `amazon_price_jpy` を保管
3. **以降は amazon_price_jpy を正として価格計算**

```
selling_price = amazon_price_jpy × markup_ratio
```

### 問題点

**現状の不明点**:
- 価格・在庫同期処理が実際に `amazon_price_jpy` を保管しているか **未検証**
- amazon_price_jpy が未設定のまま残り続ける可能性
- cleanup_invalid_listings.py が誤って必要な商品を削除する可能性

---

## 問題が発覚した経緯

### 背景

Issue #001（upload_queueとlistingsの整合性問題）の調査中に発見。

### 発見の流れ

1. BASE API → ローカルDB マージ処理を実行
   - sync_from_base_api.py で BASE APIから既存商品を取得
   - 約9,000件の商品データをマージ

2. cleanup_invalid_listings.py を実行
   - Amazon価格未取得の商品を削除対象に含める
   - **amazon_price_jpy IS NULL** の条件でフィルタリング

3. 問題提起
   - 「amazon_price_jpy は定期的な価格・在庫同期処理で保管される想定」
   - しかし、実際にそのように挙動するかは **未検証**

### ユーザーコメント

> 現状で「selling_price」は「amazon_price_jpy」を元に一定の計算を行い割り当てており、常に「amazon_price_jpy」を正とする必要があり、安易にダミー値や割り戻しを行うことがあってはいけない値です。
>
> ただし、今回の事例において、base_account1から商品リストを取得→直後に出品キューのテストであり、「base_account1から商品リストを取得」と「出品キューのテスト」はたまたまその順で開発作業を行っただけ、であり、実運用ではそのような順番になることはまずありません。
>
> つまり、一時的にプラットフォーム側の出品を読み込んだ場合でも、「amazon_price_jpy」は定期的な価格・在庫の同期処理の実行時に保管される想定（これは本当にそのように挙動するかは未検証）です。

---

## 検証が必要な理由

### 1. データ整合性の原則

システムの設計原則として：
- `amazon_price_jpy` を正（マスタ）とする
- `selling_price` は `amazon_price_jpy × markup_ratio` で計算
- ダミー値や割り戻しは行わない

この原則が守られているか検証が必要。

### 2. cleanup_invalid_listings.py の妥当性

**現在の削除条件**:
```python
# Amazon価格未取得のレコードを削除
WHERE (p.amazon_price_jpy IS NULL OR p.amazon_price_jpy = 0)
```

この条件が適切かどうかは、価格同期処理の挙動次第：
- ✅ 価格同期で amazon_price_jpy が保管される → 削除条件は適切
- ❌ 価格同期で amazon_price_jpy が保管されない → 削除条件は不適切（必要な商品を削除してしまう）

### 3. 運用上の影響

**シナリオ1: BASE APIから新規商品を取得した直後**
- amazon_price_jpy が未設定のまま
- cleanup_invalid_listings.py を実行すると削除される
- 価格同期を実行する前に削除されてしまう可能性

**シナリオ2: 価格同期が正常に動作する場合**
- 定期的な価格同期で amazon_price_jpy が設定される
- cleanup_invalid_listings.py を実行しても問題なし

どちらのシナリオが実際に起こるかを検証する必要がある。

---

## 調査すべき項目

### 優先度: 高

#### 1. 価格・在庫同期処理の挙動を確認

**対象スクリプト**:
- `platforms/base/scripts/sync_prices.py`
- `inventory/scripts/sync_amazon_data.py`

**確認すべき点**:
- amazon_price_jpy が未設定の商品を SP-API から取得しているか
- 取得した価格を products テーブルに保存しているか
- どのタイミングで実行されるか（手動 / 自動）

**検証手順**:
1. amazon_price_jpy が NULL の商品を特定
2. 価格同期処理を実行
3. 実行後に amazon_price_jpy が設定されたか確認

#### 2. BASE API同期とSP-API同期の関係

**確認すべき点**:
- BASE APIから取得した商品に対して、SP-API価格取得が自動実行されるか
- 手動で実行する必要があるか
- どのようなフローで運用することを想定しているか

### 優先度: 中

#### 3. amazon_price_jpy 未設定商品の件数を確認

現在のデータベースで、amazon_price_jpy が未設定の商品がどれだけ存在するか：

```sql
SELECT COUNT(*)
FROM products
WHERE amazon_price_jpy IS NULL OR amazon_price_jpy = 0
```

```sql
SELECT COUNT(*)
FROM listings l
INNER JOIN products p ON l.asin = p.asin
WHERE l.status = 'pending'
  AND (p.amazon_price_jpy IS NULL OR p.amazon_price_jpy = 0)
```

#### 4. selling_price の設定方法を確認

BASE APIから取得した商品の selling_price がどのように設定されているか：
- BASE API側に保存されている値をそのまま使用？
- ローカルで計算して設定？
- 手動で設定？

---

## 問題解決のために参照するべきコード・ドキュメント

### 関連コード

#### 1. platforms/base/scripts/sync_prices.py

BASE APIとの価格同期処理：

**確認すべき点**:
- SP-APIから価格を取得しているか
- amazon_price_jpy を更新しているか
- どのような条件で実行されるか

#### 2. inventory/scripts/sync_amazon_data.py

Amazon商品情報の同期処理：

**確認すべき点**:
- SP-API Product Pricing API を使用しているか
- バッチ処理で価格を取得しているか
- products テーブルの amazon_price_jpy を更新しているか

#### 3. inventory/scripts/sync_from_base_api.py

BASE API → ローカルDB マージ処理：

**確認すべき点** (行155-209):
```python
def merge_existing_items():
    # BASE APIから取得した商品をローカルDBに反映
    base_price = base_item.get('price')
    updates = {
        'selling_price': float(base_price) if base_price else None,
        # amazon_price_jpy は更新していない？
    }
```

amazon_price_jpy をどう扱っているか確認。

#### 4. inventory/scripts/add_new_products.py

新規商品追加処理（SP-API使用）：

**確認すべき点**:
- `--use-sp-api` フラグで SP-API から価格を取得
- amazon_price_jpy を設定
- selling_price を計算

```python
# SP-APIから価格取得（推定）
product = fetch_product_info_from_sp_api(asin, use_sp_api=True)
selling_price = calculate_selling_price(amazon_price)
```

#### 5. scheduler/scripts/cleanup_invalid_listings.py

不要レコード削除処理（改善後）：

**該当箇所** (行94-103, 183-194):
```python
# Amazon価格未取得のレコードを削除対象とする
cursor.execute('''
    SELECT COUNT(*) as count
    FROM listings l
    INNER JOIN products p ON l.asin = p.asin
    WHERE l.status = 'pending'
    AND (p.amazon_price_jpy IS NULL OR p.amazon_price_jpy = 0)
''')
```

### データベーススキーマ

**products テーブル**:
- `asin`: 商品ASIN
- `amazon_price_jpy`: Amazon価格（日本円）← 検証対象
- `selling_price`: 販売価格（計算値）
- `title_ja`, `title_en`: 商品名
- `updated_at`: 更新日時

**listings テーブル**:
- `asin`: 商品ASIN
- `platform`: プラットフォーム名
- `account_id`: アカウントID
- `selling_price`: 販売価格 ← BASE APIから取得した値
- `status`: 'pending' / 'listed' / 'failed'

### 関連ドキュメント

- [README.md](../../README.md) - 2025-11-22 の作業履歴
  - 「BASE API → ローカルDB マージ機能」の記載
  - 「SP-API処理の高速化」の記載

- [docs/BATCH_PROCESSING_IMPLEMENTATION.md](../BATCH_PROCESSING_IMPLEMENTATION.md)
  - SP-API Product Pricing API バッチ処理の実装

- [platforms/base/README.md](../../platforms/base/README.md)
  - BASE連携の仕様

---

## 検証手順（推奨）

### ステップ1: 現状確認

1. **amazon_price_jpy 未設定商品の件数を確認**

```bash
cd /c/Users/hiroo/Documents/GitHub/ecauto
./venv/Scripts/python.exe -c "
from inventory.core.master_db import MasterDB
db = MasterDB()
with db.get_connection() as conn:
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) as count FROM products WHERE amazon_price_jpy IS NULL OR amazon_price_jpy = 0')
    print(f'amazon_price_jpy 未設定: {cursor.fetchone()[\"count\"]}件')
"
```

2. **サンプル商品を特定**

amazon_price_jpy が未設定だが selling_price が設定されている商品を1件選ぶ。

### ステップ2: 価格同期処理の実行

1. **sync_amazon_data.py を実行**

```bash
# 全商品を同期
./venv/Scripts/python.exe inventory/scripts/sync_amazon_data.py

# または特定ASINのみ
./venv/Scripts/python.exe inventory/scripts/sync_amazon_data.py --asin B01M342KAC
```

2. **sync_prices.py を実行**

```bash
# 全アカウントの価格・在庫を同期
./venv/Scripts/python.exe platforms/base/scripts/sync_prices.py --markup-ratio 1.3
```

### ステップ3: 結果確認

1. **amazon_price_jpy が設定されたか確認**

```bash
./venv/Scripts/python.exe -c "
from inventory.core.master_db import MasterDB
db = MasterDB()
product = db.get_product('B01M342KAC')
print(f'amazon_price_jpy: {product.get(\"amazon_price_jpy\")}')
print(f'selling_price: {product.get(\"selling_price\")}')
"
```

2. **ログを確認**

- SP-API呼び出しログ
- 価格更新ログ

### ステップ4: 結論

検証結果に基づいて判断：

**ケースA: amazon_price_jpy が設定された**
- ✅ 価格同期処理は正常に動作している
- cleanup_invalid_listings.py の削除条件は適切
- 運用フローを明確にする（BASE API同期 → 価格同期 → cleanup）

**ケースB: amazon_price_jpy が設定されなかった**
- ❌ 価格同期処理に問題がある
- cleanup_invalid_listings.py の削除条件を見直す必要がある
- 価格同期処理を修正する

---

## 想定される解決策

### パターン1: 価格同期処理が正常（推奨）

**前提**: 価格同期で amazon_price_jpy が適切に設定される

**運用フロー**:
```
1. BASE API同期（sync_from_base_api.py）
   → selling_price のみ設定

2. 価格同期処理（sync_amazon_data.py）
   → amazon_price_jpy を設定

3. cleanup実行（必要に応じて）
   → amazon_price_jpy 未設定の商品を削除
```

**cleanup_invalid_listings.py の改善**:
- 削除条件に注意書きを追加
- 実行前に価格同期を促す警告を表示

### パターン2: 価格同期処理に問題がある場合

**対応1: 価格同期処理を修正**
- sync_amazon_data.py を修正して amazon_price_jpy を確実に設定

**対応2: cleanup の削除条件を変更**
```python
# amazon_price_jpy 未設定でも selling_price があればOK
WHERE l.status = 'pending'
  AND l.selling_price IS NULL  # amazon_price_jpy の条件を削除
```

**対応3: BASE API同期時に SP-API も呼び出す**
- sync_from_base_api.py を拡張
- BASE APIで商品を取得した直後に SP-API で価格を取得

---

## 今後のアクション

### 1. 検証の実施（優先度: 高）

- [ ] 現状のデータ確認（amazon_price_jpy 未設定商品の件数）
- [ ] 価格同期処理の実行
- [ ] 結果確認（amazon_price_jpy が設定されたか）
- [ ] ログ分析

### 2. ドキュメント更新（優先度: 中）

検証結果に基づいて：
- [ ] 運用フローを明確化
- [ ] README.md に記載
- [ ] cleanup_invalid_listings.py にコメント追加

### 3. コード改善（優先度: 中）

必要に応じて：
- [ ] 価格同期処理の修正
- [ ] cleanup の削除条件の見直し
- [ ] エラーハンドリングの追加

---

## セッション用プロンプト

次回この問題を検証する際、以下のプロンプトで開始：

```
amazon_price_jpy 未設定商品の扱いと、価格同期処理の挙動を検証します。

背景:
- BASE APIから取得した商品で selling_price は設定されているが amazon_price_jpy が未設定
- システムの設計では「amazon_price_jpy を正とする」原則がある
- 定期的な価格同期処理で amazon_price_jpy が保管される想定だが、未検証

検証すべき点:
1. sync_amazon_data.py が amazon_price_jpy を適切に設定するか
2. sync_prices.py が amazon_price_jpy を更新するか
3. amazon_price_jpy 未設定商品の件数
4. cleanup_invalid_listings.py の削除条件が適切か

参照ドキュメント:
- docs/issues/ISSUE_003_amazon_price_verification.md
- inventory/scripts/sync_amazon_data.py
- platforms/base/scripts/sync_prices.py
- scheduler/scripts/cleanup_invalid_listings.py

検証手順:
1. amazon_price_jpy 未設定商品を特定
2. 価格同期処理を実行（sync_amazon_data.py, sync_prices.py）
3. 実行後に amazon_price_jpy が設定されたか確認
4. 結果に基づいて運用フローを明確化 or コード修正
```

---

## 関連Issue

- **Issue #001**: upload_queueとlistingsの整合性問題（解決済み）
  - 本Issueは #001 の調査中に発見

- **Issue #002**: 重複判定処理の誤検知（未解決）
  - 本Issueと直接の関連はないが、データ整合性という観点で関連
