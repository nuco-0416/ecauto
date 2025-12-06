# ISSUE_017: 画像アップロード処理が実行されない問題

**日付**: 2025-11-26
**ステータス**: ✅ 解決済み
**優先度**: 最高
**カテゴリ**: バグ / 画像アップロード / 文字コード
**関連ISSUE**: ISSUE_016
**解決日**: 2025-11-27

---

## 📋 問題の概要

ISSUE_016で画像アップロード処理を削除したが、実際には画像が表示されなくなったため、コードを復元した。しかし、復元後も**画像アップロード処理が実行されていない**問題が発生している。

### 症状

1. **商品はアップロードされる**: BASE APIへの商品登録は成功（Item IDが取得できる）
2. **画像が表示されない**: アップロードされた商品ページで画像が表示されない
3. **ログに出力されない**: 画像アップロードのログ（「画像アップロード: X件」）が出力されない
4. **デバッグログも出力されない**: 追加したデバッグログ（[DEBUG]）も出力されない

### 確認された事例

- **商品ID 126495790** (ASIN: B09C1PM23V): 画像なし
- **商品ID 126496792** (ASIN: B0DYJSQ5K5): 画像なし（テスト用、画像9件がDBに存在）

---

## 🔍 原因調査

### 1. ISSUE_016の経緯

**誤った判断**: 画像アップロード処理は不要と判断し、以下のコードを削除：
- `uploader.upload_images()` の呼び出し
- `BaseAPIClient.add_image_from_url()` メソッド
- `BaseAPIClient.add_images_bulk()` メソッド

**結果**: 商品登録は成功するが、画像が表示されない状態に

### 2. コード復元作業

以下の7ファイルに画像アップロード処理を復元：

1. **scheduler/upload_daemon_account.py** (Line 312-320)
2. **scheduler/upload_daemon.py** (Line 300-308)
3. **scheduler/platform_uploaders/uploader_interface.py** (Line 62-81)
4. **scheduler/platform_uploaders/base_uploader.py** (Line 129-171)
5. **scheduler/platform_uploaders/ebay_uploader.py** (Line 46-55)
6. **scheduler/platform_uploaders/yahoo_uploader.py** (Line 46-55)
7. **platforms/base/core/api_client.py** (Line 224-319)

### 3. デバッグログの追加

**追加した箇所**:

#### scheduler/upload_daemon_account.py (Line 312-327)
```python
# デバッグ: item_dataの画像情報を確認
images_data = item_data.get('images')
self.logger.info(f"[DEBUG] item_data['images']: type={type(images_data)}, len={len(images_data) if images_data else 0}, data={images_data}")

# 画像アップロード
if item_data.get('images'):
    self.logger.info(f"[DEBUG] 画像アップロード処理を開始します")
    img_result = uploader.upload_images(
        platform_item_id,
        item_data['images']
    )
    self.logger.info(
        f"画像アップロード: {img_result.get('uploaded_count', 0)}件"
    )
else:
    self.logger.warning(f"[DEBUG] item_data['images']が空のため、画像アップロードをスキップしました")
```

#### scheduler/platform_uploaders/base_uploader.py (Line 76-88, 166-174)
```python
# upload_item メソッド内
print(f"  [DEBUG] create_item 送信データ: {prepared_data}")
print(f"  [DEBUG] create_item レスポンス: {result}")
print(f"  [DEBUG] 取得したItem ID: {item_id}")

# upload_images メソッド内
print(f"  [DEBUG] upload_images 開始: Item ID={platform_item_id}, 画像数={len(image_urls)}")
print(f"  [DEBUG] 画像URL: {image_urls[:3]}...")
print(f"  [DEBUG] add_images_bulk 結果: {result}")
```

### 4. 現在の問題

**デバッグログが出力されない**:
- 2025-11-26 21:32:06にテストASIN（B0DYJSQ5K5）がアップロードされた
- 「アップロード成功: Item ID=126496792」のログは出力
- **しかし、その後のデバッグログや画像アップロードのログが一切出力されていない**

**考えられる原因**:
1. Pythonキャッシュ（`__pycache__`）が残っており、古いコードが実行されている
2. プロセスの再起動が完全に行われていない
3. コードの復元に問題がある（構文エラーやインポートエラー）

---

## 🛠️ 試したこと

### 1. Pythonキャッシュのクリア

```python
# 実行回数: 3回以上
for pycache in root.rglob('__pycache__'):
    shutil.rmtree(pycache)
```

結果: 20-79個の`__pycache__`ディレクトリを削除したが、問題は解決せず

### 2. プロセスの完全停止・再起動

```bash
# 実行方法
1. wmicコマンドでプロセスを停止
2. taskkillで強制終了
3. Pythonキャッシュクリア
4. multi_account_managerを再起動
```

結果: プロセスは正常に再起動したが、デバッグログは出力されず

### 3. テスト用ASINの準備

- キューの249件のpendingアイテムを`on_hold`に変更
- テスト用ASIN（B0DYJSQ5K5、画像9件）を1件だけpendingに戻す
- Queue ID: 5038

結果: アップロードは実行されたが、画像アップロード処理は呼び出されず

---

## 📊 データ確認

### DBの画像データ

**ASIN: B0DYJSQ5K5の画像データ**:
```python
画像数: 9
画像データ型: <class 'list'>
画像URL[0]: https://m.media-amazon.com/images/I/...
```

→ **画像データは正しくDBに保存されている**

### アップロード履歴

**Item ID: 126496792**:
- ASIN: B0DYJSQ5K5
- Account: base_account_1
- アップロード時刻: 2025-11-26 21:32:06
- ステータス: success
- **画像: なし（表示されない）**

---

## 🔗 関連コード

### upload_daemon_account.py の画像準備部分

```python
# 画像URLをパース（JSON文字列の場合）
import json
images = product.get('images', [])
if isinstance(images, str):
    try:
        images = json.loads(images)
    except (json.JSONDecodeError, TypeError):
        images = []

# アイテムデータを準備
item_data = {
    'asin': asin,
    'sku': listing.get('sku', ''),
    'title': product.get('title_ja') or product.get('title_en'),
    'description': product.get('description_ja') or product.get('description_en'),
    'price': listing.get('selling_price'),
    'stock': listing.get('in_stock_quantity', 1),
    'images': images,  # ← 画像データを設定
    'account_id': account_id
}
```

→ **画像データは正しく`item_data`に設定されているはず**

### 画像アップロード呼び出し部分

```python
if result['status'] == 'success':
    platform_item_id = result.get('platform_item_id')
    self.logger.info(f"アップロード成功: Item ID={platform_item_id}")

    # デバッグ: item_dataの画像情報を確認
    images_data = item_data.get('images')
    self.logger.info(f"[DEBUG] item_data['images']: type={type(images_data)}, len={len(images_data) if images_data else 0}, data={images_data}")

    # 画像アップロード
    if item_data.get('images'):
        self.logger.info(f"[DEBUG] 画像アップロード処理を開始します")
        img_result = uploader.upload_images(
            platform_item_id,
            item_data['images']
        )
```

→ **`if item_data.get('images'):`の条件が False になっている可能性**

---

## 💡 次のステップ

### 優先度: 最高

1. **手動テストスクリプトの作成**
   - デーモンを使わず、直接アップロード処理を実行
   - デバッグ情報を標準出力に出力
   - `item_data['images']`の内容を確認

2. **コードの再確認**
   - 復元したコードに構文エラーがないか確認
   - インポートエラーがないか確認

3. **ログファイルの直接確認**
   - `logs/upload_scheduler_base_base_account_1.log`を直接確認
   - デバッグログが本当に出力されていないか確認

4. **プロセスのコード確認**
   - 実行中のプロセスが使用しているPythonファイルを確認
   - `ps`コマンドでコマンドライン引数を確認

---

## 🚨 影響範囲

### プロダクション環境への影響

- **不完全な商品が多数アップロードされている**: 画像なしの商品が本番環境に出品されている
- **推定影響数**: 数十件～数百件（pending: 249件のうち、既にアップロードされた分）
- **緊急度**: 高（顧客に不完全な商品ページが表示されている）

### 対応方針

1. **まず原因を特定**: 手動テストで問題を特定
2. **修正と検証**: 正しく動作することを確認
3. **既存商品の修正**: 画像なしでアップロードされた商品に画像を追加する処理を実行

---

## 📝 備考

### BASE APIの仕様（確認済み）

**商品登録API（/items/add）**:
- `image_url`: メイン画像URL（オプション）
- `image_url_2`～`image_url_20`: 追加画像URL（オプション）

**画像追加API（/items/add_image）**:
- 商品登録後に画像を追加可能
- `item_id`, `image_no`, `image_url`を指定

→ **両方のアプローチが可能。現在の実装は後者（商品登録後に画像追加）**

### デバッグログの設計

- `print()`文: base_uploader.py内で使用（標準出力）
- `self.logger.info()`: upload_daemon_account.py内で使用（ログファイル）

→ **両方が出力されない場合、コード自体が実行されていない可能性が高い**

---

## 👤 担当者

- **発見**: ユーザー確認により発覚
- **調査**: Claude Code（進行中）
- **対応**: 未定

---

---

## ✅ 解決策

### 根本原因: Windows環境での文字コード問題

**原因**: subprocess経由で起動されたPythonプロセスのstdout/stderrがShift-JISになっており、日本語を含むログ出力時にハングアップしていた。

**症状の詳細**:
- ログ出力で日本語（商品タイトル、説明文）を含む変数を評価しようとすると、プロセスが無限にハングアップ
- タイムアウトも発生せず、エラーも出力されない
- ログファイルには特定の箇所までしか出力されない

### 修正内容

#### 1. upload_daemon_account.py にUTF-8設定を追加

**ファイル**: `scheduler/upload_daemon_account.py`
**変更箇所**: Line 13-19

```python
import sys
import io

# Windows環境での文字コード問題対策: stdout/stderrをUTF-8でラップ
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
```

#### 2. デバッグログの削減

過剰なデバッグログを削除し、必要最小限のログ出力に変更：
- `base_uploader.py`: デバッグログを削除
- `api_client.py`: デバッグログを削除
- `upload_daemon_account.py`: シンプルなログに変更

### 検証結果

**テストASIN**: B0DYJSQ5K5
**Queue ID**: 5038
**結果**: ✅ 成功

```
2025-11-27 01:26:15 [INFO] 商品登録成功: ASIN=B0DYJSQ5K5, Item ID=126517522
2025-11-27 01:26:15 [INFO] アップロード成功: Item ID=126517522
2025-11-27 01:26:15 [INFO] 画像アップロード開始: 9枚
2025-11-27 01:26:27 [INFO] 画像アップロード: 9枚
```

画像アップロードが正常に実行され、9枚の画像がすべてアップロードされました。

---

## 📅 変更履歴

| 日付 | 変更内容 | 担当者 |
|------|---------|--------|
| 2025-11-26 | Issue作成・原因調査開始 | Claude Code |
| 2025-11-26 | デバッグログ追加・テスト実行 | Claude Code |
| 2025-11-27 | **文字コード問題を特定・修正完了** | Claude Code |
| 2025-11-27 | **テスト成功・Issue解決** | Claude Code |
