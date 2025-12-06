# SP-API エラーハンドリング改善サマリー

**最終更新**: 2025-11-21

## 概要

SP-API のエラー時に在庫切れと誤判定されていた問題を修正しました。
エラー時は前回のキャッシュを保持することで、一時的なAPI エラーで商品が非公開にならないようになりました。

---

## 主な変更点

### 1. エラーと在庫切れの区別

| 状況 | 修正前 | 修正後 |
|-----|-------|-------|
| API 成功（在庫あり） | `{'in_stock': True}` | `{'in_stock': True}` |
| API 成功（在庫切れ） | `{'in_stock': False}` | `{'in_stock': False}` |
| **API エラー** | `{'in_stock': False}` ⚠️ | `None` ✅ |

### 2. リトライ機構の強化

```python
# 修正前：レート制限エラーのみリトライ
if "QuotaExceeded" in error_message:
    # リトライ
else:
    break  # すぐに終了

# 修正後：全てのエラーでリトライ
if "QuotaExceeded" in error_message:
    # リトライ
else:
    # リトライ（5秒待機、最大3回）
```

### 3. フォールバック処理の追加

```python
# API エラー時の動作

修正前:
API エラー → {'in_stock': False} を保存 → 商品が非公開に

修正後:
API エラー → None を返す → 既存キャッシュを使用 → 在庫状態を維持
```

---

## 修正ファイル

| ファイル | 変更内容 |
|---------|---------|
| `integrations/amazon/sp_api_client.py` | エラー時に `None` を返す、全エラーでリトライ |
| `platforms/base/scripts/sync_prices.py` | フォールバック処理、統計情報追加 |
| `inventory/scripts/sync_stock_visibility.py` | 統計情報追加、警告表示 |

詳細は [work_log_20251121_api_error_fix.md](./work_log_20251121_api_error_fix.md) を参照してください。

---

## 新しい統計情報

価格同期処理で以下の統計情報が追加されました：

```
SP-API エラー処理:
  - SP-APIエラー発生: 5件
  - キャッシュフォールバック成功: 5件
  - フォールバック成功率: 100.0%
```

在庫同期処理で以下の統計情報が追加されました：

```
キャッシュ状態:
  - キャッシュ欠損（Master DB使用）: 2件
  - キャッシュ不完全（スキップ）: 1件

⚠ 警告: 3件の商品でキャッシュに問題がありました。
  - 1件: キャッシュが不完全（SP-APIエラーの可能性）
```

---

## 使用方法

### 手動でエラー状況を確認する

```bash
# 価格同期を実行（ドライラン）
python platforms/base/scripts/sync_prices.py --dry-run

# 在庫同期を実行（ドライラン）
python inventory/scripts/sync_stock_visibility.py --dry-run

# 統合同期を実行（ドライラン）
python inventory/scripts/sync_inventory.py --dry-run
```

### 特定ASINのキャッシュを確認

```bash
cd /c/Users/hiroo/Documents/GitHub/ecauto

# キャッシュファイルを確認
cat inventory/data/cache/amazon_products/B08CDYX378.json

# 結果例
{
  "price": 1358.0,
  "in_stock": true,
  "is_prime": true,
  "is_fba": false,
  "is_buybox_winner": false,
  "currency": "JPY",
  "cached_at": "2025-11-21T14:46:56.703054"
}
```

### 特定ASINのキャッシュを手動更新

```bash
cd /c/Users/hiroo/Documents/GitHub/ecauto

python -c "
from integrations.amazon.sp_api_client import AmazonSPAPIClient
from integrations.amazon.config import SP_API_CREDENTIALS
from inventory.core.cache_manager import AmazonProductCache

client = AmazonSPAPIClient(SP_API_CREDENTIALS)
cache = AmazonProductCache()

# 最新情報を取得してキャッシュに保存
asin = 'B08CDYX378'
price_info = client.get_product_price(asin)

if price_info:
    cache.set_product(asin, price_info)
    print(f'Cache updated for {asin}')
else:
    print(f'Failed to update cache for {asin}')
"
```

---

## トラブルシューティング

### Q1. API エラーが頻発する

**原因**: レート制限に達している可能性があります。

**対処法**:
1. ログで `QuotaExceeded` エラーを確認
2. 同期間隔を延長（現在1時間 → 2時間など）
3. 処理対象を分散（アカウント別に時間をずらす）

### Q2. キャッシュフォールバックが失敗する

**原因**: キャッシュが存在しない、または不完全です。

**対処法**:
1. 新規商品の場合：初回取得を手動で実行
2. キャッシュ破損の場合：該当ASINのキャッシュを削除して再取得

```bash
# キャッシュを削除
rm inventory/data/cache/amazon_products/ASIN.json

# 再取得（価格同期を実行）
python platforms/base/scripts/sync_prices.py --account base_account_2
```

### Q3. 在庫情報が更新されない

**原因**: API エラーが続いており、フォールバックで古いキャッシュを使用しています。

**対処法**:
1. SP-API の認証情報を確認
2. ログでエラー内容を確認
3. 手動で該当ASINのキャッシュを更新（上記参照）

---

## リトライ設定

現在のリトライ設定：

| パラメータ | 値 | 説明 |
|-----------|---|------|
| `max_retries` | 3回 | 最大リトライ回数 |
| `retry_delay` | 5秒 | リトライ間隔 |
| `min_interval` | 2.1秒 | 通常のAPI呼び出し間隔 |

変更する場合は `integrations/amazon/sp_api_client.py` を編集してください。

---

## 監視推奨項目

1. **SP-API エラー発生率**
   - 目標: 5%以下
   - 確認方法: 価格同期ログの統計情報

2. **キャッシュフォールバック成功率**
   - 目標: 95%以上
   - 確認方法: 価格同期ログの統計情報

3. **在庫同期でのスキップ件数**
   - 目標: 1%以下
   - 確認方法: 在庫同期ログの統計情報

---

## 関連ドキュメント

- [詳細な作業ログ](./work_log_20251121_api_error_fix.md)
- [インベントリ同期戦略](./インベントリ同期戦略_設計書.md)
- [定期実行デーモン実装](./定期実行デーモン実装完了レポート_20251120.md)

---

**問い合わせ**: プロジェクト管理者まで
