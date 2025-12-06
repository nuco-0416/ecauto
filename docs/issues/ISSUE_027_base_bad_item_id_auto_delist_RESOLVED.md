# Issue #027: BASE API 400エラー（bad_item_id）による価格同期エラー【解決済み】

**ステータス**: ✅ 解決済み
**発生日**: 2025-12-03
**解決日**: 2025-12-04
**担当**: Claude Code

---

## 問題の詳細

### エラー内容

`sync_inventory_daemon.py`実行時に以下のエラーが発生：

```
BASE API 400エラー:
{'asin': 'B0C1QZNKHY', 'listing_id': 12391, 'error': '400 Client Error: Bad Request for url: https://api.thebase.in/1/items/edit'}

SP-API取得失敗:
[WARN] B0FLJBT6C1 - SP-API取得失敗 (11件)
```

### 根本原因

1. **BASE API 400エラー（bad_item_id）**
   - BASE側で削除された商品が、データベースには`listed`ステータスで残っていた
   - 価格同期処理で該当商品を更新しようとすると、`bad_item_id`エラーが発生
   - 影響: 17件のリスティング（Listing 12391, 7646 など）

2. **SP-API取得失敗**
   - 調査の結果、これは**エラーではない**ことが判明
   - 8件: `status='out_of_stock'`（在庫切れ）
   - 3件: `status='filtered_out'`（フィルタリング条件不一致）
   - 正常な動作として処理される

### 影響範囲

- **base_account_2**: 17件の無効なリスティング
- 価格同期処理の遅延（エラーハンドリングに時間がかかる）
- ログに大量のエラーメッセージが記録される

---

## 問題が発覚した経緯

### タイムライン

1. **デーモン実行時にエラー発生**
   ```
   BASE API 400エラー: bad_item_id
   ```

2. **調査開始**
   - デバッグスクリプト作成で原因特定
   - Listing 12391 (ASIN: B0C1QZNKHY, item_id: 126494877)
   - Listing 7646 (ASIN: B0DRCNW4GZ, item_id: 125804955)

3. **BASE管理画面で確認**
   - 該当商品がBASE側で削除されていることを確認
   - 全17件が同様の状況

---

## 解決方法

### 実装内容

#### 1. ListingValidatorクラスの実装

**ファイル**: [platforms/base/core/listing_validator.py](../../platforms/base/core/listing_validator.py)

**機能**:
- BASE API側での商品存在確認（個別API呼び出し）
- 自動delisted処理（複数段階の検証）
- 復元可能な安全な実装

**主要メソッド**:

```python
def verify_item_exists(
    self,
    platform_item_id: str,
    listing: Dict[str, Any],
    use_cache: bool = True
) -> Tuple[bool, Optional[str]]:
    """
    BASE側で商品が存在するか検証（高速版：個別API呼び出し）

    - 400エラー（bad_item_id / no_item_id）= 商品が存在しない
    - 404エラー = 商品が存在しない
    - その他のエラー = 一時的なエラーの可能性（delisted対象外）
    """
```

**技術的な実装ポイント**:
- GETリクエスト用に`Content-Type`ヘッダーを除外（BASE API仕様に対応）
- `bad_item_id`と`no_item_id`の両方を「存在しない」と判定
- エラーレスポンスの詳細な解析とログ出力

#### 2. sync_prices.pyの拡張

**ファイル**: [platforms/base/scripts/sync_prices.py](../../platforms/base/scripts/sync_prices.py)

**変更内容**:
- `bad_item_id`エラー発生時の自動delisted処理を追加
- 環境変数`AUTO_DELIST_INVALID_ITEMS`で制御（デフォルト: 有効）
- 詳細ログ記録（`logs/auto_delisted.log`）
- 処理統計の追加（`auto_delisted_count`）

#### 3. ドキュメント作成

**ファイル**: [docs/auto_delist_invalid_items.md](../auto_delist_invalid_items.md)

**内容**:
- 機能説明
- 使用方法
- トラブルシューティング
- 開発者向け情報

### テスト結果

#### DRY RUNモードでのテスト

```bash
python test_auto_delist.py
```

**結果**:
```
テストした出品数: 2件
  - 存在しない: 2件
  - delisted処理: 2件
  - エラー: 0件
```

**検証内容**:
- Listing 12391 (ASIN: B0C1QZNKHY) → 正しく「存在しない」と判定
- Listing 7646 (ASIN: B0DRCNW4GZ) → 正しく「存在しない」と判定
- 自動delisted処理が正常に動作

### 安全装置

1. **複数段階の検証**
   - BASE APIの個別確認（`get_item`）
   - エラーレスポンスの詳細解析
   - 404/400エラーの厳密な判定

2. **詳細ログ記録**
   - `logs/auto_delisted.log`に全処理を記録
   - JSON形式で構造化されたログ

3. **復元可能**
   - ステータスを`delisted`に変更するのみ
   - 手動で`listed`に戻すことが可能

4. **環境変数で制御**
   - デフォルト: 有効
   - `.env`で無効化可能：`AUTO_DELIST_INVALID_ITEMS=false`

---

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
5. 400エラー（bad_item_id / no_item_id）または 404エラー?
   ↓ YES
6. delisted ステータスに変更
   ↓
7. ログ記録 & 統計更新
```

---

## パフォーマンス

### 最適化のポイント

1. **個別API呼び出し**
   - エラー発生時のみ個別確認
   - 全商品リストの取得は不要（高速）
   - 17件のエラーの場合、約1.7秒（17回 × 0.1秒/回）

2. **Content-Typeヘッダーの除外**
   - GETリクエストに最適化
   - BASE API仕様に準拠

3. **並列処理への影響**
   - 正常な商品には影響なし
   - エラー商品のみ追加検証

---

## 関連ファイル

### 新規作成

- `platforms/base/core/listing_validator.py` - 検証ロジック
- `docs/auto_delist_invalid_items.md` - ドキュメント

### 修正

- `platforms/base/scripts/sync_prices.py` - エラーハンドリング追加

### テスト（削除済み）

- `test_auto_delist.py` - テストスクリプト（プロジェクトルールに従い削除）

---

## ログファイル

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
    "platform_item_id": "126494877",
    "error": "bad_item_id",
    "error_description": "不正なitem_idです。"
  }
}
```

---

## 今後の対応

### 本番実行

```bash
# DRY RUNモードで確認
python platforms/base/scripts/sync_prices.py --dry-run --account base_account_2 --max-items 100

# 本番実行
python platforms/base/scripts/sync_prices.py --account base_account_2
```

### モニタリング

- `logs/auto_delisted.log`で処理状況を確認
- 誤delisted防止のため、定期的にログをレビュー

### 拡張可能性

他のプラットフォーム（eBay、Yahooなど）にも適用可能：
1. `listing_validator.py`を汎用化
2. 各プラットフォームのAPIクライアントに対応
3. エラーハンドリングを追加

---

## 参考

- BASE API仕様: https://docs.thebase.com/docs/api/
- 関連ISSUE: なし（新規機能実装）
