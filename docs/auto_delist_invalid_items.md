# 自動delisted処理機能

## 概要

BASE API 400エラー（`bad_item_id`）が発生した場合に、自動的に出品を`delisted`ステータスに変更する機能です。

## 背景

BASE側で商品が削除されているにもかかわらず、データベースには出品情報が残っている場合、価格同期処理で`bad_item_id`エラーが発生します。このエラーが継続すると、同期処理全体が遅延し、正常な商品の更新にも影響します。

## 機能

### 1. **厳密なエラー判定**

- BASE APIの`error="bad_item_id"`のみを対象
- 他のエラー（認証エラー、サーバーエラーなど）は対象外

### 2. **高速な個別検証**

1. **BASE API個別呼び出し**
   - `get_item(item_id)`でエラーが発生した商品のみを個別確認
   - 全商品リストの取得は不要（高速）

2. **404エラーで判定**
   - 404エラー = 商品が存在しない
   - その他のエラー = 一時的なエラーの可能性（delisted対象外）

### 3. **安全装置**

- **詳細ログ記録**: `logs/auto_delisted.log`に記録
- **復元可能**: 後で手動で`listed`に戻すことが可能
- **統計情報**: 処理結果サマリーに表示

### 4. **設定で制御**

- デフォルトは**有効**
- 環境変数で無効化可能

## 使用方法

### 1. 同期処理の実行

**デフォルトで有効**なので、そのまま実行できます：

通常通り、価格同期処理を実行します：

```bash
# デーモン経由
python scheduled_tasks/sync_inventory_daemon.py

# 直接実行
python platforms/base/scripts/sync_prices.py
```

### 2. 無効化（必要な場合のみ）

自動delisted処理を無効化したい場合、`.env`ファイルに追加：

```bash
# 自動delisted処理を無効化
AUTO_DELIST_INVALID_ITEMS=false
```

### 3. ログの確認

処理後、以下のログを確認：

```bash
# 自動delistedログ
logs/auto_delisted.log

# 統計情報（標準出力）
自動delisted処理:
  - 自動delisted: 17件
  - item_id更新: 0件
    → 詳細: logs/auto_delisted.log を確認してください
```

## ログ形式

### auto_delisted.log

```json
{
  "listing_id": 12391,
  "auto_delisted": true,
  "reason": "bad_item_id",
  "timestamp": "2025-12-03T15:30:45",
  "error_details": {
    "asin": "B0C1QZNKHY",
    "listing_id": 12391,
    "status_code": 400,
    "error": "bad_item_id",
    "error_description": "不正なitem_idです。"
  }
}
```

## 動作フロー

```
1. BASE API更新時にエラー発生
   ↓
2. エラーコードが400 & error="bad_item_id" ?
   ↓ YES
3. 環境変数で無効化されている?
   ↓ NO（デフォルト有効）
4. BASE APIで個別確認（get_item）
   ↓
5. 404エラー?
   ↓ YES
6. delisted ステータスに変更
   ↓
7. ログ記録 & 統計更新
```

## 注意事項

### 1. **誤delisted防止**

- 複数段階の検証により、実際に存在する商品を誤って`delisted`にする可能性を最小化
- 検証エラー時は、安全のため「存在する」と判定

### 2. **復元方法**

誤って`delisted`になった場合：

```sql
-- Listingsテーブルで確認
SELECT * FROM Listings WHERE id = 12391;

-- 手動で復元
UPDATE Listings SET status = 'listed' WHERE id = 12391;
```

### 3. **BASE側で再出品した場合**

新しい`item_id`で出品された場合は、自動的に検出して更新されます。

## トラブルシューティング

### Q1: 自動delisted処理が動作しない

**確認事項**:
1. 環境変数で無効化されていないか
   ```bash
   cat .env | grep AUTO_DELIST_INVALID_ITEMS
   # "false"になっている場合は無効
   ```

2. エラーが`bad_item_id`であるか
   - ログで確認

### Q2: 誤ってdelistedになった

**対処方法**:
1. `logs/auto_delisted.log`で詳細を確認
2. 手動でstatusを`listed`に戻す
3. BASE管理画面で商品が存在するか確認

### Q3: パフォーマンスへの影響

**確認事項**:
- エラー発生時のみ個別API呼び出しを行うため、正常な商品には影響なし
- 17件のエラーの場合、17回のAPI呼び出し（約1.7秒）

## 開発者向け情報

### 関連ファイル

- `platforms/base/core/listing_validator.py`: 検証ロジック
- `platforms/base/scripts/sync_prices.py`: エラーハンドリング
- `logs/auto_delisted.log`: 自動delistedログ

### テスト方法

```bash
# DRY RUNモードでテスト（実際の変更なし）
python platforms/base/scripts/sync_prices.py --dry-run --account base_account_2 --max-items 100

# 無効化してテスト
AUTO_DELIST_INVALID_ITEMS=false python platforms/base/scripts/sync_prices.py --dry-run --account base_account_2
```

### 拡張方法

他のプラットフォーム（eBay、Yahooなど）にも適用する場合：

1. `listing_validator.py`を汎用化
2. 各プラットフォームのAPIクライアントに対応
3. エラーハンドリングを追加

## 参考

- ISSUE #XXX: BASE API 400エラー対策
- BASE API仕様: https://docs.thebase.com/docs/api/
