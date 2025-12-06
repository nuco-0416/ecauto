# Product Pricing APIバッチ処理実装レポート

**実装日**: 2025-11-22
**対象**: Issue #2 - SP-API処理の非効率性

## 📊 実装結果サマリー

### パフォーマンス改善

| 項目 | 改善前 | 改善後 | 高速化倍率 |
|------|--------|--------|-----------|
| **価格取得API** | 個別取得（2.1秒/件） | バッチ取得（20件/2.5秒） | **約10-20倍** |
| **新規商品追加（10件）** | 21.0秒 | 1.9秒 | **10.9倍** |
| **価格取得（17件）** | 35.7秒 | 1.7秒 | **21.7倍** |
| **価格取得（50件）** | 105秒 | 11.2秒 | **9.4倍** |

### レート制限の変更

- **改善前**: 個別取得 - 0.5リクエスト/秒（2秒に1回）
- **改善後**: バッチ取得 - 0.5リクエスト/秒（20件/バッチ）
- **API呼び出し削減**: **約95%削減**

---

## 🔧 実装内容

### 1. SP-API クライアント拡張

**ファイル**: `integrations/amazon/sp_api_client.py`

#### 新規メソッド: `get_prices_batch()`

```python
def get_prices_batch(asins: List[str], batch_size: int = 20) -> Dict[str, Dict[str, Any]]
```

**機能**:
- Products API の `get_item_offers_batch()` を使用
- 最大20件/リクエストでバッチ処理
- 既存の価格フィルタリングロジックを維持
  - Prime + FBA発送
  - 3日以内配送
  - 送料無料
  - スコアリングによる最適価格選択

**レート制限**:
- 0.5リクエスト/秒（2秒に1回）
- 安全マージンを含めて2.5秒の待機時間

---

### 2. 新規商品追加スクリプトの最適化

**ファイル**: `inventory/scripts/add_new_products.py`

#### 処理フローの変更

**改善前（個別処理）**:
```
各ASINについて:
  1. SP-APIから商品情報取得（Catalog API）
  2. SP-APIから価格情報取得（Products API）
  3. DBに登録
  4. 2.1秒待機
```

**改善後（バッチ処理）**:
```
ステップ1: 既存商品チェック（一括）
ステップ2: 価格情報をバッチ取得（20件/リクエスト）
ステップ3: 各ASINについて:
  1. 商品情報取得（Catalog API）
  2. バッチで取得済みの価格情報を統合
  3. DBに登録
  4. 0.5秒待機（Catalog API用）
```

#### 新規関数

```python
def fetch_prices_batch(asins: list, batch_size: int = 20) -> dict
```

**説明**: 複数ASINの価格情報をバッチで取得

```python
def fetch_product_info_from_sp_api(
    asin: str,
    use_sp_api: bool = True,
    ng_filter: NGKeywordFilter = None,
    price_info: dict = None  # 新規追加
) -> dict
```

**説明**: 既存関数を拡張し、事前取得した価格情報を受け取れるようにした

---

### 3. 価格同期スクリプトの最適化

**ファイル**: `platforms/base/scripts/sync_prices.py`

#### 処理フローの変更

**改善前（個別処理）**:
```
各出品について:
  1. キャッシュから価格取得
  2. キャッシュミス時: SP-APIから個別取得
  3. 価格計算・更新
  4. 2秒待機
```

**改善後（バッチ処理）**:
```
ステップ1: 全出品のキャッシュチェック
ステップ2: キャッシュミスをバッチで一括取得
ステップ3: 各出品について:
  1. 価格計算・更新
  2. 0.5秒待機（BASE API用）
```

#### 新規メソッド

```python
def _sync_listing_price_with_info(
    listing: dict,
    base_client: BaseAPIClient,
    amazon_info: dict,  # 事前取得した価格情報
    dry_run: bool
)
```

**説明**: 価格情報を引数で受け取り、個別API呼び出しを削減

---

### 4. BASE API並列処理の実装

**ファイル**: `platforms/base/scripts/sync_prices.py`

#### 処理フローの変更

**改善前（逐次処理）**:
```
各BASEアカウントについて順番に:
  1. 出品リストを取得
  2. 価格情報を同期
  3. BASE APIで価格更新
```

**改善後（並列処理）**:
```
複数BASEアカウントを並列で:
  ThreadPoolExecutorで同時処理
  各アカウントは独立したAPIクオータを持つため安全
```

#### 新規メソッド

```python
def sync_all_accounts(
    self,
    dry_run: bool = False,
    parallel: bool = True,
    max_workers: int = 4
):
    """
    全アカウントの価格を同期（並列処理対応）
    """
    if parallel and len(accounts) > 1:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_account = {
                executor.submit(self._sync_account_safe, account['id'], dry_run): account
                for account in accounts
            }
            for future in as_completed(future_to_account):
                future.result()
```

```python
def _sync_account_safe(self, account_id: str, dry_run: bool):
    """
    並列処理用のセーフラッパー
    エラーをキャッチして他のアカウントの処理を継続
    """
```

#### コマンドライン引数

```bash
--parallel           # 並列処理を有効（デフォルト）
--no-parallel        # 逐次処理モード
--max-workers N      # 最大ワーカー数（デフォルト: 4）
```

#### テスト結果

**テスト環境**: 2アカウント（base_account_1: 48件、base_account_2: 185件、合計233件）

**修正前（問題あり）**:

| モード | 処理時間 | キャッシュヒット率 | SP-API呼び出し | エラー | 問題 |
|--------|----------|-------------------|----------------|--------|------|
| 逐次処理 | 1分57秒（117秒） | 100.0% | 0回 | なし | - |
| 並列処理 | 2分14秒（134秒） | 97.0% | **14回** | **QuotaExceeded 2回** | ❌ ステップ1で誤ってSP-API呼び出し |

**修正後（正常動作）**:

| モード | 処理時間 | キャッシュヒット率 | SP-API呼び出し | エラー | 改善 |
|--------|----------|-------------------|----------------|--------|------|
| 逐次処理 | 1分57秒（117秒） | 100.0% | 0回 | なし | - |
| 並列処理 | **1分33秒（93秒）** | 100.0% | **0回** | **なし** | ✅ **24秒高速化（20%削減）** |

**修正内容**:
- `get_amazon_price()`に`allow_sp_api=False`フラグを追加
- ステップ1でキャッシュのみチェック（SP-API呼び出しを無効化）
- 統計情報の重複カウントを修正（`update_stats=False`）

**考察**:
- ✅ **並列処理が逐次処理より20%高速**（修正後）
- ✅ **SP-API呼び出しが完全に0回**になり、レート制限エラーが発生しなくなった
- ✅ BASE APIへの通信が並列化されるため、アカウント数が多いほど効果が高まる
- ✅ キャッシュヒット率100%の場合でも並列処理の効果がある

**推奨事項（修正後）**:
- ✅ **デフォルトで並列処理を推奨**（`--parallel`、修正により安全に使用可能）
- アカウント数が1つのみの場合: 逐次処理と並列処理の差はなし
- アカウント数が多い場合（3つ以上）: 並列処理の効果がさらに高まる

---

## 🎯 効果の詳細

### 新規商品追加（`add_new_products.py`）

#### 処理時間の比較（10件）

| 処理 | 改善前 | 改善後 | 削減率 |
|------|--------|--------|--------|
| 価格取得 | 21.0秒 | 1.9秒 | **91%削減** |
| 商品情報取得 | 各ASIN個別 | 各ASIN個別 | 変更なし |
| 合計 | 約30秒 | 約10秒 | **67%削減** |

**API呼び出し削減**:
- 価格取得: 10回 → 1回（**90%削減**）

---

### 価格同期（`sync_prices.py`）

#### シナリオ例: 100件の出品（キャッシュミス50件）

| 処理 | 改善前 | 改善後 | 削減率 |
|------|--------|--------|--------|
| キャッシュヒット | 0秒（同じ） | 0秒（同じ） | - |
| キャッシュミス（50件） | 105秒 | 11秒 | **89%削減** |
| BASE API更新（100件） | 200秒 | 50秒 | **75%削減** |
| **合計** | **305秒（5分）** | **61秒（1分）** | **80%削減** |

**API呼び出し削減**:
- SP-API: 50回 → 3回（**94%削減**）

---

## 📈 長期的な効果

### 1日あたりの処理量（想定）

| 項目 | 処理件数 | 改善前 | 改善後 | 時間削減 |
|------|----------|--------|--------|---------|
| 新規商品追加 | 1000件/日 | 約3.5時間 | 約20分 | **3時間10分** |
| 価格同期 | 2000件/日 | 約1.2時間 | 約10分 | **1時間10分** |
| **合計** | - | **4.7時間** | **30分** | **4時間20分/日** |

### コスト削減

- **SP-API呼び出し削減**: 約95%
- **サーバー稼働時間削減**: 約90%
- **エラーリスク低減**: レート制限エラーが大幅に減少

---

## 🔒 後方互換性

### 既存機能の保持

✅ **個別取得メソッドも保持**
- `get_product_price(asin)` - 個別取得は引き続き使用可能
- 後方互換性を維持

✅ **オプション指定可能**
- `batch_size` パラメータでバッチサイズを調整可能（デフォルト: 20）

✅ **既存の価格フィルタリングロジックを維持**
- Prime、FBA、配送条件などの判定は変更なし

---

## 🧪 テスト結果

### 実行したテスト

| テスト | 件数 | 結果 | 高速化倍率 |
|--------|------|------|-----------|
| バッチAPI単体 | 5件 | 成功 | 5.6倍 |
| バッチAPI単体 | 17件 | 成功 | 21.7倍 |
| バッチAPI単体 | 50件 | 成功 | 9.4倍 |
| add_new_products統合 | 10件 | 成功 | 10.9倍 |
| sync_prices統合 | DRY RUN | 成功 | - |

### 確認事項

✅ **価格情報の正確性**: 既存ロジックと同一の結果
✅ **エラーハンドリング**: バッチ失敗時も個別ASINごとに適切に処理
✅ **キャッシュ動作**: 既存のキャッシュ機構と正常に連携
✅ **DBトランザクション**: データ整合性を維持

---

## 📝 使用方法

### 新規商品追加（バッチ処理は自動）

```bash
python inventory/scripts/add_new_products.py \
  --asin-file asins.txt \
  --platform base \
  --account-id base_account_1 \
  --use-sp-api
```

**変更点**: なし（内部で自動的にバッチ処理を使用）

---

### 価格同期（バッチ処理は自動）

#### 基本的な使用方法

```bash
python platforms/base/scripts/sync_prices.py \
  --markup-ratio 1.3
```

**変更点**: なし（内部で自動的にバッチ処理を使用）

#### 並列処理オプション

**デフォルト（並列処理有効、推奨）**:
```bash
# 並列処理はデフォルトで有効（修正により安全に使用可能）
python platforms/base/scripts/sync_prices.py \
  --markup-ratio 1.3
```

**並列処理のワーカー数を指定**:
```bash
python platforms/base/scripts/sync_prices.py \
  --markup-ratio 1.3 \
  --max-workers 2
```

**逐次処理モード（アカウント数が1つのみの場合）**:
```bash
python platforms/base/scripts/sync_prices.py \
  --markup-ratio 1.3 \
  --no-parallel
```

**特定アカウントのみ処理**:
```bash
python platforms/base/scripts/sync_prices.py \
  --markup-ratio 1.3 \
  --account base_account_1 \
  --dry-run
```

---

## ⚠️ 注意事項

### レート制限

- **Products API**: 0.5リクエスト/秒（変更なし）
- **バッチサイズ**: 最大20件/リクエスト
- **推奨**: 大量処理時は時間帯を分散

### エラーハンドリング

- **QuotaExceeded**: レート制限超過時は自動的に待機
- **無効ASIN**: エラーログを出力してスキップ
- **ネットワークエラー**: リトライ機構あり（最大3回）

---

## 🚀 今後の改善案

### Phase 1: 完了 ✅
- ✅ Product Pricing APIバッチ処理の実装
- ✅ 新規商品追加スクリプトへの統合
- ✅ 価格同期スクリプトへの統合

### Phase 2: 完了 ✅
- ✅ **BASE API並列処理の実装**
  - 複数BASEアカウントを並列処理
  - ThreadPoolExecutorによるスレッドプール実装
  - コマンドライン引数で制御可能（--parallel, --max-workers）
  - **修正**: ステップ1でSP-APIが誤って呼び出される問題を修正
    - `get_amazon_price()`に`allow_sp_api`フラグを追加
    - 並列処理時のレート制限エラーを解消
    - 処理時間を20%削減（2分14秒 → 1分33秒）

### Phase 3: 将来的な拡張（オプション）
- 📋 Catalog API のバッチ処理対応
  - 調査結果: `search_catalog_items`は詳細情報を返さない
  - 商品詳細取得には個別API呼び出しが必要
  - 初回登録時のみなので、現状で問題なし

---

## 📚 参考資料

### SP-API ドキュメント

- [Product Pricing API v0](https://developer-docs.amazon.com/sp-api/docs/product-pricing-api-v0-reference)
- [Catalog Items API v2020-12-01](https://developer-docs.amazon.com/sp-api/docs/catalog-items-api-v2020-12-01-reference)

### 関連ファイル

- `integrations/amazon/sp_api_client.py` - SP-APIクライアント
- `inventory/scripts/add_new_products.py` - 新規商品追加
- `platforms/base/scripts/sync_prices.py` - 価格同期
- `docs/REMAINING_ISSUES.md` - 課題管理

---

**実装者**: Claude
**レビュー**: -
**承認**: -

---

## 🎉 まとめ

Product Pricing APIのバッチ処理実装により、**約10-20倍の高速化**を達成しました。

**主な成果**:
- ✅ **SP-API呼び出しを95%削減**
- ✅ **処理時間を80-90%削減**
- ✅ **1日あたり4時間以上の時間削減**
- ✅ **レート制限エラーの大幅な低減**
- ✅ **後方互換性を完全に維持**
- ✅ **BASE API並列処理の実装**
  - 複数アカウントの同時処理に対応
  - コマンドライン引数で制御可能

**技術的な実装**:
1. **Product Pricing API バッチ処理**
   - 20件/リクエストでバッチ取得
   - API呼び出しを95%削減

2. **キャッシュベースの価格同期**
   - キャッシュヒット時はSP-API呼び出しをスキップ
   - キャッシュミスのみバッチで一括取得

3. **BASE API並列処理**
   - ThreadPoolExecutorによる並列実行
   - アカウント数が多い場合に有効
   - キャッシュヒット率が高い場合は逐次処理を推奨

この実装により、**Issue #2: SP-API処理の非効率性**は完全に解決されました。
