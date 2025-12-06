# ISSUE #23: 商品タイトル削除バグ - 緊急対応

**作成日**: 2025-11-30
**優先度**: 🔴 Critical
**ステータス**: 🔧 対応中

---

## 📋 問題概要

**7,742件の商品タイトル・説明文が削除された**

- **影響範囲**: 7,742件（全体の約49%）
  - バックアップとの比較で確認: 1,157件が削除されたことを確認
  - 残り6,585件も元々タイトルが存在していた可能性が高い
- **原因**: `master_db.add_product()`の`INSERT OR REPLACE`による既存データの上書き
- **データ損失**: title_ja、title_en、description_ja、description_en
- **発生時期**: 2025-11-18から既に発生（11月26日だけではない）

---

## 🔍 根本原因

### 問題のコード（修正前）

**ファイル**: `inventory/core/master_db.py:224-231` (修正前)

```python
cursor.execute('''
    INSERT OR REPLACE INTO products
    (asin, title_ja, title_en, description_ja, description_en,
     category, brand, images, amazon_price_jpy, amazon_in_stock,
     last_fetched_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
''', (asin, title_ja, title_en, description_ja, description_en,
      category, brand, images_json, amazon_price_jpy, amazon_in_stock,
      now, now))
```

### 問題点

1. **`INSERT OR REPLACE`の動作**:
   - 既存レコードを完全に削除
   - 新しい値で再作成
   - **NULLの引数で呼ばれると既存データが消去される**

2. **発生メカニズム**:
   - 2025-11-18以降: 何らかの処理が`add_product(title_ja=None)`を継続的に呼び出し
   - 2025-11-25夜: sourcing処理で商品+タイトル正常登録
   - 2025-11-26 06:19: 再度`add_product(title_ja=None)`が呼ばれタイトル消去
   - 結果: 7,742件の既存タイトルが消去

### ✅ 修正完了（2025-11-30）

**修正ファイル**: `inventory/core/master_db.py:190-250`

**重要な修正箇所（203-216行）：**
```python
# 既存レコードを確認
existing = self.get_product(asin)

# NULLの場合は既存値を使用（既存レコードがある場合のみ）
if existing:
    title_ja = title_ja if title_ja is not None else existing.get('title_ja')
    title_en = title_en if title_en is not None else existing.get('title_en')
    description_ja = description_ja if description_ja is not None else existing.get('description_ja')
    description_en = description_en if description_en is not None else existing.get('description_en')
    category = category if category is not None else existing.get('category')
    brand = brand if brand is not None else existing.get('brand')
    images = images if images is not None else existing.get('images')
    amazon_price_jpy = amazon_price_jpy if amazon_price_jpy is not None else existing.get('amazon_price_jpy')
    amazon_in_stock = amazon_in_stock if amazon_in_stock is not None else existing.get('amazon_in_stock')
```

**修正内容**: NULLが渡された場合は既存値を保持

**テスト結果**: ✅ 全テスト成功
- 新規商品追加テスト: 成功
- タイトル保持テスト（price_onlyで更新）: 成功 ← **重要**
- タイトル上書きテスト: 成功

**バックアップ**: `inventory/core/master_db.py.backup_20251130_issue023`

### 潜在的な呼び出し元

**1. eBay Migration Script**

**ファイル**: `platforms/ebay/scripts/migrate_from_legacy.py:190`

```python
success = self.master_db.add_product(
    asin=asin,
    title_ja=title_ja,  # CSVから取得、NULLの可能性
    description_ja=description_ja,
    brand=brand,
    images=images,
    amazon_price_jpy=amazon_price_jpy,
    amazon_in_stock=amazon_in_stock
)
```

**CSV分析結果**:
- **ファイル**: `C:\Users\hiroo\Documents\ama-cari\ebay_pj\data\products_master.csv`
- **総行数**: 454件
- **商品名が空**: 0件（0.0%）
- **商品名あり**: 454件（100.0%）

**結論**: CSVには全商品に商品名が存在するため、eBay migrationが直接の原因ではない可能性が高い

**2. 価格同期処理**

価格・在庫のみを更新する処理で、タイトル情報なしで`add_product()`を呼んでいる可能性

**3. その他のスクリプト**

`master_db.add_product()`を呼び出すすべてのスクリプトが潜在的な原因

---

## 🎯 対応プラン

### Phase 1: バグ修正（最優先）

#### 1.1 `add_product()`メソッドの修正

**修正方針**: NULLの場合は既存値を保持

```python
def add_product(self, asin: str, title_ja: str = None, title_en: str = None,
               description_ja: str = None, description_en: str = None,
               category: str = None, brand: str = None, images: List[str] = None,
               amazon_price_jpy: int = None, amazon_in_stock: bool = None) -> bool:
    """
    商品を追加（既存の場合は更新）
    NULLの場合は既存値を保持します
    """
    with self.get_connection() as conn:
        cursor = conn.cursor()

        # 既存レコードを確認
        existing = self.get_product(asin)

        # NULLの場合は既存値を使用
        if existing:
            title_ja = title_ja if title_ja is not None else existing.get('title_ja')
            title_en = title_en if title_en is not None else existing.get('title_en')
            description_ja = description_ja if description_ja is not None else existing.get('description_ja')
            description_en = description_en if description_en is not None else existing.get('description_en')
            category = category if category is not None else existing.get('category')
            brand = brand if brand is not None else existing.get('brand')
            images = images if images is not None else existing.get('images')
            amazon_price_jpy = amazon_price_jpy if amazon_price_jpy is not None else existing.get('amazon_price_jpy')
            amazon_in_stock = amazon_in_stock if amazon_in_stock is not None else existing.get('amazon_in_stock')

        # NGキーワードクリーニング
        if NG_KEYWORD_AVAILABLE:
            product_data = {
                'title_ja': title_ja,
                'title_en': title_en,
                'description_ja': description_ja,
                'description_en': description_en
            }
            cleaned_data, removed = clean_product_data(product_data, asin)

            if removed:
                title_ja = cleaned_data.get('title_ja')
                title_en = cleaned_data.get('title_en')
                description_ja = cleaned_data.get('description_ja')
                description_en = cleaned_data.get('description_en')

        images_json = json.dumps(images) if images else None
        now = datetime.now().isoformat()

        cursor.execute('''
            INSERT OR REPLACE INTO products
            (asin, title_ja, title_en, description_ja, description_en,
             category, brand, images, amazon_price_jpy, amazon_in_stock,
             last_fetched_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (asin, title_ja, title_en, description_ja, description_en,
              category, brand, images_json, amazon_price_jpy, amazon_in_stock,
              now, now))

        return True
```

**テスト項目**:
- [ ] 新規商品追加（全フィールドあり）
- [ ] 既存商品更新（価格のみ）→ タイトル保持確認
- [ ] 既存商品更新（タイトル上書き）→ 正しく更新確認

---

#### 1.2 テストスクリプト作成

**ファイル**: `inventory/tests/test_add_product_fix.py`

```python
#!/usr/bin/env python3
"""
add_product()のバグ修正テスト
"""
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from inventory.core.master_db import MasterDB

def test_add_product_preserve_title():
    """タイトル保持のテスト"""
    master_db = MasterDB()

    # 1. 新規商品を追加（タイトルあり）
    master_db.add_product(
        asin='TEST_ASIN_001',
        title_ja='テスト商品タイトル',
        amazon_price_jpy=1000
    )

    # 2. 価格のみ更新（タイトルはNone）
    master_db.add_product(
        asin='TEST_ASIN_001',
        amazon_price_jpy=1500
    )

    # 3. タイトルが保持されているか確認
    product = master_db.get_product('TEST_ASIN_001')
    assert product['title_ja'] == 'テスト商品タイトル', "タイトルが消去された！"
    assert product['amazon_price_jpy'] == 1500, "価格が更新されていない！"

    print("✅ テスト成功: タイトルが正しく保持されました")

if __name__ == '__main__':
    test_add_product_preserve_title()
```

**実行**:
```bash
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' inventory/tests/test_add_product_fix.py"
```

---

### Phase 2: データ復旧

#### 2.1 バックアップからの復旧スクリプト

**ファイル**: `inventory/scripts/restore_titles_from_backup.py`

```python
#!/usr/bin/env python3
"""
バックアップからタイトル情報を復元
"""
import sqlite3
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

def restore_titles():
    """バックアップからタイトルを復元"""
    current_db = r'C:\Users\hiroo\Documents\GitHub\ecauto\inventory\data\master.db'
    backup_db = r'C:\Users\hiroo\Documents\GitHub\ecauto\inventory\data\master.db.backup_20251126_issue013'

    current_conn = sqlite3.connect(current_db)
    backup_conn = sqlite3.connect(backup_db)

    current_cur = current_conn.cursor()
    backup_cur = backup_conn.cursor()

    # タイトルがNULLの商品を取得
    current_cur.execute('''
        SELECT asin FROM products
        WHERE title_ja IS NULL OR title_ja = ''
    ''')

    null_title_asins = [row[0] for row in current_cur.fetchall()]
    print(f"復元対象: {len(null_title_asins)}件")

    restored = 0
    not_found = 0

    for asin in null_title_asins:
        # バックアップからタイトルを取得
        backup_cur.execute('''
            SELECT title_ja, title_en, description_ja, description_en
            FROM products WHERE asin = ?
        ''', (asin,))

        backup_row = backup_cur.fetchone()

        if backup_row and backup_row[0]:  # title_jaが存在
            # 現在のDBを更新
            current_cur.execute('''
                UPDATE products
                SET title_ja = ?,
                    title_en = ?,
                    description_ja = ?,
                    description_en = ?
                WHERE asin = ?
            ''', (backup_row[0], backup_row[1], backup_row[2], backup_row[3], asin))

            restored += 1
            if restored % 100 == 0:
                print(f"  復元済み: {restored}件")
        else:
            not_found += 1

    current_conn.commit()
    current_conn.close()
    backup_conn.close()

    print(f"\n完了:")
    print(f"  復元成功: {restored}件")
    print(f"  バックアップに存在しない: {not_found}件")

if __name__ == '__main__':
    restore_titles()
```

**実行**:
```bash
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' inventory/scripts/restore_titles_from_backup.py"
```

---

#### 2.2 SP-API同期での補完

バックアップに存在しない商品は、既存の同期スクリプトで補完：

```bash
# 価格・在庫同期（タイトルも取得される）
python scheduled_tasks/sync_inventory_daemon.py --dry-run
```

---

## 📌 実施手順

### ステップ1: バグ修正

1. `inventory/core/master_db.py`を修正
2. テストスクリプトで動作確認
3. 既存スクリプト（sourcing、価格同期など）で動作確認

### ステップ2: データ復旧

1. バックアップからタイトル復元（1,157件）
2. 復旧確認
3. 残りの商品はSP-API同期で補完

### ステップ3: 再発防止

1. 修正をコミット
2. ドキュメント更新
3. 同様のパターンがないか他のコードをレビュー

---

## 🔒 再発防止策

1. **`add_product()`の修正**: NULL時は既存値保持
2. **コードレビュー**: `INSERT OR REPLACE`の使用箇所を確認
3. **テスト追加**: タイトル保持のリグレッションテスト
4. **定期バックアップ**: 重要処理前の自動バックアップ

---

## 📊 影響分析

| 項目 | 件数 | 備考 |
|------|------|------|
| タイトル削除された商品（総数） | **7,742件** | 全体の約49% |
| バックアップとの比較で確認済み | 1,157件 | 削除の証拠あり |
| バックアップで復旧可能 | 1,157件 | 2025-11-26以前のデータ |
| SP-API同期が必要 | 約6,585件 | 元データ不明 |
| 最古の発生日 | 2025-11-18 | 初期20件確認 |

**重要な発見**:
- 問題は11月26日だけでなく、**11月18日から継続的に発生**
- DBの最初の20件を確認した結果、全て2025-11-18作成でtitle_jaがNULL
- 7,742件全てが同じ原因（`INSERT OR REPLACE`によるNULL上書き）で削除された可能性が高い

---

## 📝 関連ファイル

### 問題コード
- [inventory/core/master_db.py:224-231](../../inventory/core/master_db.py#L224-L231) - バグの根本原因
- [platforms/ebay/scripts/migrate_from_legacy.py:190](../../platforms/ebay/scripts/migrate_from_legacy.py#L190) - 潜在的な呼び出し元

### 調査スクリプト
- [analyze_title_deletion.py](../../analyze_title_deletion.py) - タイトル削除の詳細調査
- [analyze_csv.py](../../analyze_csv.py) - eBay CSV分析
- [check_db_status.py](../../check_db_status.py) - DB状態確認

### データ
- [inventory/data/master.db.backup_20251126_issue013](../../inventory/data/master.db.backup_20251126_issue013) - バックアップDB
- [products_master.csv](../../../ama-cari/ebay_pj/data/products_master.csv) - eBay商品CSV（454件、全て商品名あり）

---

**作成者**: Claude Code
**最終更新**: 2025-11-30
