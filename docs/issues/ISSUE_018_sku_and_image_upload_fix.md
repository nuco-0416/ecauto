# ISSUE_018: 商品コード（SKU）登録と画像アップロード問題

**日付**: 2025-11-27
**ステータス**: ✅ 解決済み
**優先度**: 高
**カテゴリ**: バグ修正 / リファクタリング後の不具合
**関連ISSUE**: ISSUE_016, ISSUE_017

---

## 📋 問題の概要

BASEへの商品アップロード時に、以下2つの問題が発生していることが発覚：

### 問題1: 商品コード（SKU）が登録されない

**症状**:
- BASEに商品はアップロードされる
- しかし、商品コード（identifier）フィールドが空欄になる
- 以前は正常に登録されていたが、リファクタリング後に発生

**影響**:
- 商品管理が困難になる
- 在庫管理システムとの連携に支障

### 問題2: 画像がアップロードされない（特定条件下）

**症状**:
- `scheduler/scripts/run_upload.py`（UploadExecutor）を使用した場合、画像がアップロードされない
- `scheduler/upload_daemon.py`を使用した場合は、画像が正常にアップロードされる

**影響**:
- ワンショット実行で画像なしの商品が登録される
- 不完全な商品ページが公開される

---

## 🔍 原因分析

### 問題1の原因: 商品コード（SKU）登録

#### リファクタリング時の削除

**ファイル**: `scheduler/platform_uploaders/base_uploader.py`
**メソッド**: `_prepare_item_data()` (Line 222-267)

**問題箇所**:
```python
# BASE API用データを構築
prepared = {
    'title': title,
    'detail': description,
    'price': int(price),
    'stock': int(item_data.get('stock') or 1),
    'visible': 1  # 公開状態
}
# ❌ identifier フィールドが含まれていない！

return prepared
```

**本来あるべき実装**:
- `listings`テーブルから該当ASINのSKUを取得
- `prepared`ディクショナリに`identifier`フィールドとしてSKUを追加

#### データベース構造

**テーブル**: `listings`
- `sku` フィールド: UNIQUE制約あり
- フォーマット: `b-{ASIN}-{タイムスタンプ}`
- 例: `b-B0D31FK2W6-20251126084623`

### 問題2の原因: 画像アップロード

#### コードパスの違い

**upload_daemon.py経由（正常動作）**:
```python
# Line 300-308
if item_data.get('images'):
    img_result = uploader.upload_images(
        platform_item_id,
        item_data['images']
    )
    self.logger.info(
        f"画像アップロード: {img_result.get('uploaded_count', 0)}件"
    )
```
→ ✅ 画像アップロード処理が実行される

**UploadExecutor経由（画像なし）**:
```python
# scheduler/upload_executor.py: upload_item() メソッド (Line 122-282)
response = api_client.create_item(item_data)
# ...
# ❌ 画像アップロード処理が存在しない！
```
→ ❌ 商品登録のみで、画像アップロード処理がない

#### 背景

- ISSUE_016で画像アップロード処理が一旦削除された（パフォーマンス問題）
- ISSUE_017で画像アップロード処理が復元された（文字コード問題を解決）
- しかし、`UploadExecutor`には画像アップロード処理が追加されなかった

---

## 🛠️ 解決策

### 問題1の修正: 商品コード（SKU）登録

#### 修正内容

**ファイル**: `scheduler/platform_uploaders/base_uploader.py`
**メソッド**: `_prepare_item_data()` (Line 240-283)

**追加コード**:
```python
# 出品情報を取得（SKUを取得するため）
listing = None
with self.db.get_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM listings
        WHERE asin = ? AND platform = 'base' AND account_id = ?
        LIMIT 1
    """, (asin, self.account_id))
    row = cursor.fetchone()
    if row:
        listing = dict(row)

# ... (商品データ構築)

# SKU（商品コード）を追加
if listing and listing.get('sku'):
    prepared['identifier'] = listing['sku']
    logger.debug(f"商品コード設定: {listing['sku']}")

return prepared
```

**修正行**: Line 240-251（SKU取得）、Line 280-283（identifier設定）

### 問題2の現状: 画像アップロード

#### 確認結果

**upload_daemon経由のテスト**:
- ✅ Item ID: 126609393（ASIN: B0D4M2ZBWC）→ 画像7枚アップロード成功
- ✅ Item ID: 126609422（ASIN: B08L38B7DP）→ 画像7枚アップロード成功

**デバッグログ**:
```
2025-11-27 22:54:07 [INFO] アップロード成功: Item ID=126609393
  [DEBUG] upload_images 開始: Item ID=126609393, 画像数=7
  [DEBUG] add_images_bulk 結果: {'success_count': 7, 'failed_count': 0}
2025-11-27 22:54:16 [INFO] 画像アップロード: 7件
```

#### 対応方針

**短期的な対応**:
- `upload_daemon`を使用する限り、画像アップロードは正常に動作
- ワンショット実行（`run_upload.py`）は、緊急時やテスト用途のみに限定

**長期的な対応**（今後の課題）:
- `UploadExecutor`に画像アップロード処理を追加
- または、`base_uploader.upload_item()`メソッド内で画像アップロードを呼び出すように統一

---

## ✅ 検証結果

### 商品コード（SKU）登録のテスト

**テスト実行日**: 2025-11-27

#### データベース確認
```sql
SELECT asin, sku, status, platform_item_id
FROM listings
WHERE platform_item_id IN ('126607448', '126607453')
```

**結果**:
- ✅ Item ID: 126607448 → SKU: `b-B08XWRWGNR-20251127193842`
- ✅ Item ID: 126607453 → SKU: `b-B0FGGZWTYX-20251127193842`
- ✅ ステータス: `listed`

#### コード確認
- ✅ `base_uploader.py:280-283` でidentifierフィールドが設定されている
- ✅ `_prepare_item_data`メソッドでlistingsテーブルからSKUを取得

#### BASE管理画面での確認
- ✅ 2件とも商品コード（identifier）が正しく登録されていることをユーザーが確認

### 画像アップロードのテスト

**テスト実行日**: 2025-11-27

#### upload_daemon経由のテスト（推奨方法）

**テスト条件**:
- プラットフォーム: BASE
- バッチサイズ: 1件
- 実行間隔: 5秒

**結果**:
| Item ID | ASIN | 画像数 | 結果 |
|---------|------|--------|------|
| 126609393 | B0D4M2ZBWC | 7枚 | ✅ 全て成功 |
| 126609422 | B08L38B7DP | 7枚 | ✅ 全て成功 |

**処理時間**:
- 商品登録 + 画像アップロード: 約10-12秒/件
- 画像1枚あたり: 約0.5秒（API間隔）

#### UploadExecutor経由のテスト（問題あり）

**結果**:
- ✅ 商品登録: 成功
- ❌ 画像アップロード: 実行されず

**原因**: `UploadExecutor.upload_item()`に画像アップロード処理がない

---

## 📊 影響範囲

### 修正前の状態

**商品コード（SKU）**:
- ❌ 新規アップロード時にidentifierフィールドが空欄
- 影響: リファクタリング後の全アップロード（具体的な件数は不明）

**画像アップロード**:
- ❌ `run_upload.py`経由のアップロードで画像なし
- ✅ `upload_daemon.py`経由では正常（本番運用では問題なし）

### 修正後の状態

**商品コード（SKU）**:
- ✅ 全アップロード方法でidentifierが正しく設定される
- ✅ データベースのSKUが正しくBASE APIに送信される

**画像アップロード**:
- ✅ `upload_daemon.py`経由: 正常動作（変更なし）
- ⚠️ `run_upload.py`経由: 未対応（今後の課題）

---

## 🔧 今後の課題

### 優先度: 中

**UploadExecutorへの画像アップロード処理追加**:
1. `UploadExecutor.upload_item()`メソッドに画像アップロード処理を追加
2. または、`BaseUploader.upload_item()`から画像アップロードを呼び出すように統一
3. テストの実施

**実装方針**:
```python
# scheduler/upload_executor.py: upload_item() メソッド内
# 商品登録成功後に追加
if item_id:
    # 画像データを取得
    images = product.get('images', [])
    if isinstance(images, str):
        import json
        try:
            images = json.loads(images)
        except:
            images = []

    # 画像アップロード
    if images:
        # BaseUploaderのupload_imagesメソッドを使用するか、
        # または直接BaseAPIClient.add_images_bulkを呼び出す
        pass
```

---

## 📝 教訓と改善点

### リファクタリング時の注意点

1. **機能の完全性を確認**
   - 削除・追加した機能が全てのコードパスで反映されているか確認
   - 複数の実装パス（daemon、executor）がある場合は全てを確認

2. **テストの重要性**
   - リファクタリング後は必ず全機能をテスト
   - 異なる実行方法（daemon、ワンショット）で動作確認

3. **ドキュメント化**
   - 機能削除・追加の理由と影響範囲を文書化（ISSUE_016、ISSUE_017の良い例）

### コードレビューの改善

- **統一性**: 同じ機能を複数の場所で実装している場合、全てを同期して修正
- **抽象化**: 共通処理（画像アップロード）は共通メソッドに集約すべき

---

## 🔗 関連ファイル

### 修正ファイル
- `scheduler/platform_uploaders/base_uploader.py` (Line 240-251, 280-283)

### 未修正ファイル（今後の課題）
- `scheduler/upload_executor.py` (Line 122-282)

### 正常動作ファイル
- `scheduler/upload_daemon.py` (Line 300-308)
- `platforms/base/core/api_client.py` (add_images_bulk メソッド)

---

## 👤 担当者

- **発見**: ユーザー（BASE管理画面での確認）
- **分析・修正**: Claude Code
- **検証**: Claude Code + ユーザー確認

---

## 📅 変更履歴

| 日付 | 変更内容 | 担当者 |
|------|---------|--------|
| 2025-11-27 | Issue作成・原因分析 | Claude Code |
| 2025-11-27 | SKU登録問題の修正完了 | Claude Code |
| 2025-11-27 | 画像アップロード動作確認（upload_daemon） | Claude Code |
| 2025-11-27 | UploadExecutorの問題特定（未修正） | Claude Code |
| 2025-11-27 | **SKU登録問題の解決確認・Issue完了** | ユーザー確認 |

---

## 📌 補足情報

### 正しいアップロード方法（推奨）

**本番運用**:
```bash
# upload_daemonを起動（バックグラウンド）
python scheduler/upload_daemon.py --platform base
```

**テスト・デバッグ**:
```bash
# キューのscheduled_timeを変更してdaemonが処理するのを待つ
# または、緊急時のみrun_upload.pyを使用（画像なしになることを理解した上で）
```

### データベース状態の確認方法

```sql
-- 商品コード（SKU）の確認
SELECT asin, sku, platform_item_id, status
FROM listings
WHERE platform = 'base' AND sku IS NOT NULL
LIMIT 10;

-- 画像データの確認
SELECT asin, title_ja, images
FROM products
WHERE images IS NOT NULL AND images != ''
LIMIT 10;
```

### BASE API仕様

**商品登録API（/items/add）**:
- `identifier`: 商品コード（SKU）- オプションだが、管理上重要

**画像追加API（/items/add_image）**:
- 商品登録後に個別に画像を追加
- 1枚ごとにAPI呼び出し（レート制限: 0.5秒間隔）
