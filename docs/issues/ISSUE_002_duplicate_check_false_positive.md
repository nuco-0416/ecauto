# Issue #002: 重複判定処理の誤検知

**ステータス**: 🟢 解決済み
**発生日**: 2025-11-22
**解決日**: 2025-11-22
**優先度**: 中
**担当**: Claude

---

## 問題の詳細

### 症状

upload_daemon.pyの重複チェック処理で、実際には重複していない商品が「重複」と判定される。

```
2025-11-22 17:33:45 [WARNING] upload_scheduler_base: 重複検出: B09KTYVX7Z - スキップします
2025-11-22 17:36:48 [WARNING] upload_scheduler_base: 重複検出: B01M342KAC - スキップします
```

### 詳細な状況

#### 検証で使用したASIN

1. **ASIN: B09KTYVX7Z**
   - listings status: `pending`
   - platform_item_id: NULL
   - **BASE側**: 存在しない（目視確認済み、base_account_2には存在しない）
   - **判定結果**: 重複と判定 ❌

2. **ASIN: B01M342KAC**
   - listings status: `pending`
   - platform_item_id: NULL
   - **BASE側**: 存在しない（目視確認済み、base_account_2には存在しない）
   - **判定結果**: 重複と判定 ❌

### 期待される動作

- `listings.status = 'pending'` かつ `platform_item_id IS NULL` の商品
- BASE側に実際に存在しない商品
- → **重複ではないと判定されるべき**

### 実際の動作

- 上記の条件を満たしているにも関わらず「重複」と判定
- アップロード処理がスキップされる
- status='failed' として記録される

---

## 問題が発覚した経緯

### 背景

Issue #001（upload_queueとlistingsの整合性問題）の解決後、修正が正しく機能しているかを検証するため、scheduled_timeを変更して即座にアップロード処理を実行。

### 検証手順

1. 未出品のASINを選択（`platform_item_id IS NULL`, `status='pending'`）
2. scheduled_timeを現在時刻に変更
3. デーモンがアップロード処理を実行
4. **期待**: アップロード成功
5. **実際**: 重複検出でスキップ

### 発見の経緯

```bash
# 検証スクリプト実行
./venv/Scripts/python.exe reschedule_for_test.py --yes

# ログ監視
tail -f logs/upload_scheduler_base.log
```

**ログ出力**:
```
[INFO] アップロード開始: ASIN=B01M342KAC, Account=base_account_2
[WARNING] 重複検出: B01M342KAC - スキップします
[INFO] バッチ完了: 成功=0, 失敗=1
```

**目視確認**:
- BASE管理画面で base_account_2 の商品一覧を確認
- 該当ASINは存在しない

---

## 問題解決のために参照するべきコード・ドキュメント

### 関連コード

#### 1. scheduler/upload_daemon.py (行274-282)

重複チェック処理の実装箇所：

```python
# 重複チェック
if uploader.check_duplicate(asin, item_data['sku']):
    self.logger.warning(f"重複検出: {asin} - スキップします")
    self.queue_manager.update_queue_status(
        queue_id=queue_id,
        status='failed',
        error_message='重複商品'
    )
    return {'status': 'failed', 'message': '重複商品'}
```

#### 2. scheduler/platform_uploaders/uploader_factory.py

プラットフォーム別アップローダーの生成：

```python
uploader = UploaderFactory.create(
    platform=self.platform,
    account_id=account_id,
    account_manager=self.account_manager
)
```

#### 3. platforms/base/uploader.py

**要確認**: `check_duplicate()` メソッドの実装
- BASE APIを呼び出して重複チェックを行っている可能性
- SKUやASINでの検索方法
- 削除済み商品の扱い

#### 4. platforms/base/core/api_client.py

**要確認**: BASE APIクライアントの実装
- 商品検索APIの呼び出し方法
- 削除済み・非公開商品のフィルタリング

### データベーススキーマ

**listings テーブル**:
- `platform_item_id`: BASEでの商品ID（出品成功後に設定される）
- `status`: 'pending'（未出品）/ 'listed'（出品済み）/ 'failed'（失敗）

### 関連ドキュメント

- [platforms/base/README.md](../../platforms/base/README.md) - BASE連携の仕様
- [scheduler/README.md](../../scheduler/README.md) - アップロードスケジューラーの仕様

---

## 推測される原因

以下のいずれかの可能性が考えられる：

### 仮説1: SKU重複チェックの問題

- SKUが過去に使用されていた
- BASE側で削除済みだが、SKUの履歴が残っている
- 削除済み商品を含めて重複チェックしている

### 仮説2: ASIN重複チェックの問題

- ASINで商品を検索している
- 削除済み商品も検索結果に含まれる
- 適切にフィルタリングされていない

### 仮説3: キャッシュの問題

- BASE APIの検索結果がキャッシュされている
- 古いデータが返されている

### 仮説4: 別アカウントとの混同

- base_account_1 と base_account_2 のデータが混在
- アカウント指定が正しく機能していない

---

## 調査すべき項目

### 優先度: 高

1. **`check_duplicate()` メソッドの実装を確認**
   - platforms/base/uploader.py
   - どのような条件で重複と判定しているか
   - BASE APIの呼び出し方法

2. **BASE APIの検索結果を確認**
   - 削除済み商品が含まれるか
   - フィルタリング条件（visible, status等）

3. **実際のBASE APIレスポンスをログ出力**
   - デバッグモードで詳細なログを記録
   - APIレスポンスの内容を確認

### 優先度: 中

4. **SKUの使用履歴を確認**
   - 過去に同じSKUが使用されていたか
   - SKU生成ロジックの確認

5. **アカウント指定の動作確認**
   - account_id が正しく渡されているか
   - API呼び出し時のアカウント切り替え

---

## 暫定対応（Workaround）

現時点では根本原因が不明のため、以下の暫定対応を検討：

### オプション1: 重複チェックを一時的に無効化

**リスク**: 実際に重複した商品を登録してしまう可能性

```python
# upload_daemon.py の274-282行をコメントアウト
# if uploader.check_duplicate(asin, item_data['sku']):
#     ...
```

### オプション2: 手動で個別にアップロード

- 重複と判定された商品を手動で登録
- BASE管理画面から直接登録

### オプション3: 問題の切り分け

1. 新しいASIN（過去に一度も登録していない）で検証
2. SKUを変更して検証
3. 別のアカウントで検証

---

## 次のステップ

### 1. コードレビュー

以下のファイルを詳細にレビュー：

```bash
# BASE uploader の実装
platforms/base/uploader.py

# BASE APIクライアント
platforms/base/core/api_client.py
```

特に `check_duplicate()` メソッドの実装を確認。

### 2. デバッグログの追加

重複チェック処理に詳細なログを追加：

```python
self.logger.debug(f"重複チェック開始: ASIN={asin}, SKU={sku}")
# API呼び出し
self.logger.debug(f"BASE API レスポンス: {response}")
self.logger.debug(f"重複判定結果: {is_duplicate}")
```

### 3. テストケースの作成

- 新規ASIN（過去に登録していない）
- 削除済みASIN（過去に登録して削除した）
- 複数アカウントでの動作確認

---

## セッション用プロンプト

次回この問題を調査する際、以下のプロンプトで問題解決を開始：

```
BASE出品時の重複判定処理で誤検知が発生しています。

症状:
- upload_daemon.py実行時に「重複検出」の警告が出力される
- listingsの status='pending', platform_item_id IS NULL なのに重複と判定
- BASE管理画面で目視確認したところ、該当商品は存在しない

確認すべき点:
1. platforms/base/uploader.py の check_duplicate() メソッドの実装
2. BASE API呼び出し時のフィルタリング条件（削除済み商品の扱い）
3. SKUの使用履歴（過去に同じSKUが使用されていたか）
4. アカウント指定が正しく機能しているか

参照ドキュメント:
- docs/issues/ISSUE_002_duplicate_check_false_positive.md
- platforms/base/uploader.py
- platforms/base/core/api_client.py

調査手順:
1. check_duplicate() メソッドの実装を確認
2. デバッグログを追加してBASE APIのレスポンスを記録
3. 新規ASIN（過去に未登録）で検証
4. SKU変更で検証
5. 根本原因を特定して修正
```

---

## 解決策

### 根本原因

複数の問題が発見されました：

#### 1. 重複判定ロジックの不備

[scheduler/platform_uploaders/base_uploader.py:100-133](../../scheduler/platform_uploaders/base_uploader.py#L100-L133) の `check_duplicate()` メソッドに問題がありました。

**問題のあったコード**:
```python
SELECT COUNT(*) as count
FROM listings
WHERE asin = ? AND platform = 'base' AND account_id = ?
```

このSQLは、`listings`テーブルに **レコードが存在するかどうかだけ** をチェックしていました。つまり：
- `status='pending'` かつ `platform_item_id IS NULL` （未出品）の商品も
- レコードが存在すれば「重複」と判定されていました

#### 2. API呼び出しの不備

[scheduler/platform_uploaders/base_uploader.py:76-77](../../scheduler/platform_uploaders/base_uploader.py#L76-L77) で `create_item()` をキーワード引数で呼び出していました。

**問題のあったコード**:
```python
result = self.client.create_item(
    title=prepared_data['title'],
    detail=prepared_data['detail'],
    ...
)
```

BASE APIクライアントは辞書を受け取る形式なので、この呼び出し方法はエラーになります。

#### 3. listings更新処理の欠落

[inventory/core/master_db.py:697-766](../../inventory/core/master_db.py#L697-L766) の `update_upload_queue_status()` が `upload_queue` テーブルのみを更新し、`listings` テーブルを更新していませんでした。

### 修正内容

#### 1. 重複判定ロジック修正

WHERE句に以下の条件を追加しました：

```python
SELECT id, status, platform_item_id
FROM listings
WHERE asin = ? AND platform = 'base' AND account_id = ?
  AND (status = 'listed' OR platform_item_id IS NOT NULL)
```

これにより、**実際にBASEに出品済みの商品のみ** が重複と判定されるようになりました。

#### 2. API呼び出し修正

辞書形式で呼び出すように修正：

```python
result = self.client.create_item(prepared_data)
```

#### 3. listings更新処理追加

`update_upload_queue_status()` にlistings更新処理を追加：

```python
# 成功時はlistingsテーブルも更新
if status == 'success' and queue_info and result_data:
    platform_item_id = result_data.get('platform_item_id')
    if platform_item_id:
        cursor.execute('''
            UPDATE listings
            SET status = 'listed',
                platform_item_id = ?,
                listed_at = ?
            WHERE asin = ? AND platform = ? AND account_id = ?
        ''', ...)
```

### デバッグログの追加

重複チェック時に詳細なログを出力するようにしました：
- 重複検出時: listing_id、status、platform_item_idを表示
- 重複なし時: 「BASEに未出品」と表示
- エラー時: エラー内容を表示

### テスト結果

**ASIN B01M342KAC での統合テスト**:

```
[DEBUG] 重複なし: ASIN=B01M342KAC (BASEに未出品)
[INFO] アップロード成功: Item ID=126131974
[INFO] バッチ完了: 成功=1, 失敗=0
```

**データベース確認**:
```
Listings:
  Status: pending → listed ✓
  Platform Item ID: None → 126131974 ✓
  Listed At: 2025-11-22T18:25:34 ✓
```

### 影響範囲

- **修正ファイル**:
  - [scheduler/platform_uploaders/base_uploader.py](../../scheduler/platform_uploaders/base_uploader.py) - 重複判定・API呼び出し
  - [inventory/core/master_db.py](../../inventory/core/master_db.py) - listings更新処理
  - [scheduler/upload_daemon.py](../../scheduler/upload_daemon.py) - 画像アップロード処理削除
- **影響するプラットフォーム**: BASEのみ（eBay、Yahooは未実装）

### 追加対応

#### 画像アップロード処理の削除

画像はBASE API登録時にURL文字列で指定されるため、別途画像アップロード処理は不要でした。
将来の混乱を避けるため、以下の画像アップロード関連コードを削除：

- [scheduler/upload_daemon.py](../../scheduler/upload_daemon.py) - 画像アップロード呼び出し
- [scheduler/upload_executor.py](../../scheduler/upload_executor.py) - `_upload_images()` メソッド
- [scheduler/platform_uploaders/base_uploader.py](../../scheduler/platform_uploaders/base_uploader.py) - `upload_images()` メソッド
- [scheduler/platform_uploaders/uploader_interface.py](../../scheduler/platform_uploaders/uploader_interface.py) - `upload_images()` 抽象メソッド定義
- [scheduler/platform_uploaders/yahoo_uploader.py](../../scheduler/platform_uploaders/yahoo_uploader.py) - `upload_images()` スケルトン
- [scheduler/platform_uploaders/ebay_uploader.py](../../scheduler/platform_uploaders/ebay_uploader.py) - `upload_images()` スケルトン

#### ディレクトリ整理

テスト・デバッグスクリプトを整理し、以下のディレクトリに移動：
- `scheduler/obsolete_scripts/` - scheduler内のテストスクリプト
- `obsolete_scripts/` - ルートディレクトリのデバッグスクリプト

---

## 関連Issue

- **Issue #001**: upload_queueとlistingsの整合性問題（解決済み）
  - 本Issueは #001 の検証中に発見
