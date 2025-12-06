# eBay統合 - トラブルシューティングガイド

このドキュメントでは、eBay統合で発生する可能性のある問題と解決方法をまとめています。

---

## 📋 目次

1. [セットアップ関連](#セットアップ関連)
2. [認証・トークン関連](#認証トークン関連)
3. [出品関連](#出品関連)
4. [価格・在庫同期関連](#価格在庫同期関連)
5. [データ移行関連](#データ移行関連)
6. [Windows環境特有の問題](#windows環境特有の問題)
7. [API制限・エラー](#api制限エラー)
8. [デバッグ方法](#デバッグ方法)

---

## セットアップ関連

### アカウント設定ファイルが見つからない

**エラーメッセージ**:
```
警告: アカウント設定ファイルが見つかりません: C:\Users\hiroo\Documents\GitHub\ecauto\platforms\ebay\accounts\account_config.json
account_config.json.example を参考に作成してください
```

**原因**: `account_config.json` が未作成

**解決方法**:
1. `platforms/ebay/accounts/` ディレクトリに移動
2. `account_config.json.example` をコピーして `account_config.json` を作成
3. eBay開発者アカウント情報を設定

```bash
cd platforms/ebay/accounts
cp account_config.json.example account_config.json
# エディタで account_config.json を編集
```

---

### データベーステーブルが存在しない

**エラーメッセージ**:
```
[NG] ebay_listing_metadata テーブルが存在しません
```

**原因**: データベースの初期化が未完了

**解決方法**:

```bash
# データベーススキーマを確認
sqlite3 inventory/data/master.db ".schema ebay_listing_metadata"

# テーブルが存在しない場合、マイグレーションスクリプトを実行
python inventory/scripts/migrations/add_ebay_metadata.py
```

---

## 認証・トークン関連

### トークンが無効・期限切れ

**エラーメッセージ**:
```
[No Token] ebay_account_1
```
または
```
Error: Access token expired
```

**原因**: OAuthトークンが未取得、または有効期限切れ

**解決方法**:

```bash
# OAuth認証を再実行
python platforms/ebay/core/auth.py
```

**手順**:
1. ブラウザが開き、eBayログインページが表示される
2. eBayにログインして認証を許可
3. リダイレクトURLから認証コードをコピー
4. ターミナルに認証コードを入力
5. トークンが `platforms/ebay/accounts/tokens/` に保存される

**注意**: トークンは自動更新されますが、初回は手動で取得が必要です。

---

### リダイレクトURIが一致しない

**エラーメッセージ**:
```
Error: redirect_uri_mismatch
```

**原因**: `account_config.json` の `redirect_uri` と eBay Developer Portal の設定が一致しない

**解決方法**:
1. [eBay Developer Portal](https://developer.ebay.com/) にログイン
2. Application設定を確認
3. Redirect URIを `account_config.json` と一致させる

---

## 出品関連

### ビジネスポリシーIDが無効

**エラーメッセージ**:
```
eBay API Error: Invalid policy ID
```
または
```
Error: Business policy not found
```

**原因**: ビジネスポリシーIDが正しく設定されていない

**解決方法**:
1. [eBay Seller Hub](https://www.ebay.com/sh/ovw) にログイン
2. Account → Business Policies に移動
3. 各ポリシーのIDを確認
4. `platforms/ebay/core/policies.py` のポリシーIDを更新

```python
# platforms/ebay/core/policies.py
PAYMENT_POLICY_ID = "YOUR_PAYMENT_POLICY_ID"
RETURN_POLICY_ID = "YOUR_RETURN_POLICY_ID"
FULFILLMENT_POLICY_ID = "YOUR_FULFILLMENT_POLICY_ID"
```

---

### カテゴリIDが無効

**エラーメッセージ**:
```
Error: Invalid category ID
```

**原因**: 指定したカテゴリIDが存在しない、または選択不可

**解決方法**:
1. eBay Category API で有効なカテゴリを検索
2. `CategoryMapper` でカテゴリマッピングを確認

```python
from platforms.ebay.core.category_mapper import CategoryMapper

mapper = CategoryMapper()
# カテゴリ推薦を取得
recommendations = mapper.get_category_suggestions(
    title="商品名",
    description="商品説明"
)
```

---

### SKU重複エラー

**エラーメッセージ**:
```
UNIQUE constraint failed: listings.sku
```

**原因**: 同じSKUが既に登録されている

**解決方法**:

**パターン1: 意図しない重複**
```bash
# データベースで既存SKUを確認
sqlite3 inventory/data/master.db "SELECT sku, asin, platform FROM listings WHERE sku='問題のSKU';"

# 必要に応じて削除
sqlite3 inventory/data/master.db "DELETE FROM listings WHERE id=削除対象のID;"
```

**パターン2: ASIN重複（正常な動作）**
- `migrate_from_legacy.py` はASIN優先で重複チェックを実行
- 同じASINは再登録されない（ログに `[SKIP]` と表示）
- これは正常な動作です

---

## 価格・在庫同期関連

### Amazon価格が見つからない

**エラーメッセージ**:
```
[SKIP] B0002YM3QI - キャッシュに価格情報がありません
```

**原因**: SP-APIキャッシュに価格データが存在しない

**解決方法**:

```bash
# SP-APIから最新の商品情報を取得
python inventory/scripts/update_product_info.py --asin B0002YM3QI
```

または、Amazon Product Cacheを再構築：
```python
from inventory.core.cache_manager import AmazonProductCache

cache = AmazonProductCache()
# ASINの価格情報を再取得
cache.update_product('B0002YM3QI')
```

---

### 価格が更新されない

**症状**: `sync_prices.py` 実行後も価格が変わらない

**原因**: 価格差が `MIN_PRICE_DIFF_USD` 未満

**解決方法**:

`platforms/ebay/scripts/sync_prices.py` で価格差の閾値を確認：
```python
MIN_PRICE_DIFF_USD = 0.50  # $0.50未満の差は更新しない
```

強制的に価格を更新する場合：
```bash
# dry-runで確認
python platforms/ebay/scripts/sync_prices.py --account ebay_account_1 --dry-run

# 本番実行（MIN_PRICE_DIFF_USDを一時的に0にする）
```

---

### 在庫数が0にならない

**症状**: Amazon在庫切れなのに、eBayで在庫数が0にならない

**原因**: Amazon在庫ステータスがキャッシュに反映されていない

**解決方法**:

```bash
# キャッシュを更新
python inventory/scripts/update_product_info.py --asin B0002YM3QI

# 在庫同期を実行
python platforms/ebay/scripts/sync_prices.py --account ebay_account_1
```

**ログ確認**:
```
[OUT_OF_STOCK] B0002YM3QI - Amazon在庫切れ、数量を0に更新
  → 在庫数0に更新成功
```

---

## データ移行関連

### CSVファイルが見つからない

**エラーメッセージ**:
```
FileNotFoundError: [Errno 2] No such file or directory: 'C:\\path\\to\\products_master.csv'
```

**原因**: CSVファイルのパスが間違っている

**解決方法**:

```bash
# パスを確認
dir C:\Users\hiroo\Documents\ama-cari\ebay_pj\data\products_master.csv

# 正しいパスで実行
python platforms/ebay/scripts/migrate_from_legacy.py --csv "C:\Users\hiroo\Documents\ama-cari\ebay_pj\data\products_master.csv"
```

---

### CSV文字コードエラー

**エラーメッセージ**:
```
UnicodeDecodeError: 'utf-8' codec can't decode byte
```

**原因**: CSVファイルの文字コードがUTF-8ではない

**解決方法**:

```python
# encoding='utf-8-sig' を試す（BOM付きUTF-8の場合）
# または encoding='shift-jis'

# migrate_from_legacy.py で文字コードを指定
```

---

### 大量データ移行時のタイムアウト

**症状**: 数千件のCSVインポート中にタイムアウト

**解決方法**:

```bash
# バッチ処理で少しずつ移行
python platforms/ebay/scripts/migrate_from_legacy.py --csv products_master.csv --limit 100

# limit を調整して繰り返し実行
```

---

## Windows環境特有の問題

### UnicodeEncodeError（絵文字）

**エラーメッセージ**:
```
UnicodeEncodeError: 'cp932' codec can't encode character '\u2705'
```

**原因**: Windowsコンソール（cp932）でUTF-8絵文字が表示できない

**解決方法**:

**方法1**: PowerShellで UTF-8を有効化
```powershell
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
```

**方法2**: コード内で絵文字を使用しない
- `test_integration.py` では既に対応済み（絵文字を `[OK]/[NG]` に置換）

---

### I/O operation on closed file

**エラーメッセージ**:
```
ValueError: I/O operation on closed file.
```

**原因**: モジュールインポート時にstdoutが閉じられる問題（Windows特有）

**解決方法**:

`test_integration.py` では既に対応済み：
```python
# stdoutを再作成
if hasattr(sys.stdout, 'closed') and sys.stdout.closed:
    sys.stdout = open(1, 'w', encoding='utf-8', closefd=False)
```

**回避策**: テストを再実行（通常は2回目以降は成功）

---

### パス区切り文字の問題

**症状**: Linuxスタイルのパス（`/`）でファイルが見つからない

**解決方法**:

```python
from pathlib import Path

# OS非依存のパス処理
csv_path = Path("C:/Users/hiroo/Documents/ama-cari/ebay_pj/data/products_master.csv")
```

---

## API制限・エラー

### Rate Limit Exceeded

**エラーメッセージ**:
```
Error: Rate limit exceeded
```

**原因**: eBay APIのレート制限に到達

**解決方法**:

1. **レート制限を確認**:
   - 1日あたりの上限: 通常5,000リクエスト
   - account_config.json で設定: `"rate_limit_per_day": 5000`

2. **時間分散処理**:
   ```python
   import time

   # リクエスト間に遅延を追加
   time.sleep(1)  # 1秒待機
   ```

3. **バッチ処理を減らす**:
   ```bash
   # 一度に処理する件数を減らす
   python platforms/ebay/scripts/sync_prices.py --account ebay_account_1 --limit 100
   ```

---

### 500 Internal Server Error

**エラーメッセージ**:
```
eBay API Error: 500 Internal Server Error
```

**原因**: eBay側の一時的な障害

**解決方法**:

1. **リトライ**: 数分後に再実行
2. **eBayステータス確認**: [eBay Developer Status](https://developer.ebay.com/support/api-status) をチェック
3. **Sandbox環境で確認**: 本番環境のみの問題か確認

---

### 401 Unauthorized

**エラーメッセージ**:
```
Error: 401 Unauthorized
```

**原因**: トークンが無効、または期限切れ

**解決方法**:

```bash
# トークンを再取得
python platforms/ebay/core/auth.py

# トークンファイルを確認
dir platforms\ebay\accounts\tokens\
```

---

## デバッグ方法

### ログレベルの変更

詳細なログを出力：

```python
import logging

# platforms/ebay/scripts/sync_prices.py などで
logging.basicConfig(level=logging.DEBUG)
```

---

### dry-runモードの活用

実際の変更なしで動作確認：

```bash
# 価格同期のdry-run
python platforms/ebay/scripts/sync_prices.py --account ebay_account_1 --dry-run

# データ移行のdry-run
python platforms/ebay/scripts/migrate_from_legacy.py --csv products_master.csv --dry-run
```

---

### データベースの直接確認

```bash
# listingsテーブルを確認
sqlite3 inventory/data/master.db "SELECT * FROM listings WHERE platform='ebay' LIMIT 10;"

# ebay_listing_metadataを確認
sqlite3 inventory/data/master.db "SELECT * FROM ebay_listing_metadata LIMIT 10;"

# 統計情報
sqlite3 inventory/data/master.db "SELECT platform, COUNT(*) FROM listings GROUP BY platform;"
```

---

### API レスポンスの確認

`platforms/ebay/core/api_client.py` でレスポンスをログ出力：

```python
def _make_request(self, method, url, **kwargs):
    response = self.session.request(method, url, **kwargs)

    # デバッグ用
    logger.debug(f"Response: {response.status_code}")
    logger.debug(f"Body: {response.text}")

    return response.json()
```

---

## よくある質問 (FAQ)

### Q1: Sandboxと本番環境の切り替え方法は？

**A**: `account_config.json` の `environment` を変更：

```json
{
  "environment": "sandbox"  // または "production"
}
```

---

### Q2: 複数アカウントの同時運用は可能？

**A**: 可能です。`account_config.json` に複数アカウントを登録：

```json
{
  "accounts": [
    {"id": "ebay_account_1", ...},
    {"id": "ebay_account_2", ...}
  ]
}
```

全アカウント同期：
```bash
python platforms/ebay/scripts/sync_prices.py --all
```

---

### Q3: 出品の削除方法は？

**A**: eBay Seller Hubから手動削除、またはAPI経由：

```python
from platforms.ebay.core.api_client import EbayAPIClient

client = EbayAPIClient(account_id='ebay_account_1', ...)
client.delete_listing(listing_id='listing_id_here')
```

---

### Q4: 画像が表示されない

**A**: 画像URLが有効か確認：

```bash
# データベースで画像URLを確認
sqlite3 inventory/data/master.db "SELECT asin, images FROM products WHERE asin='B0002YM3QI';"
```

画像URLは公開アクセス可能である必要があります。

---

## サポート情報

### ドキュメント
- [実装計画書](implementation_plan_initial.md)
- [README.md](../README.md)

### ログファイル
- 価格同期ログ: `logs/ebay_price_sync.log`（作成される場合）
- デーモンログ: `logs/daemon.log`

### 問い合わせ
問題が解決しない場合は、以下の情報とともに報告してください：
- エラーメッセージ全文
- 実行したコマンド
- Python バージョン
- OS バージョン
- ログファイルの関連部分

---

**最終更新**: 2025-11-28
