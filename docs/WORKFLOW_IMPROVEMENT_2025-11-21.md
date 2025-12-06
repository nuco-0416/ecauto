# ワークフロー改善レポート

**作成日**: 2025-11-21
**対象**: 商品登録からアップロードまでの自動化
**ステータス**: Phase 1完了、Phase 2-3未着手

---

## 📋 目次

1. [発見された問題](#発見された問題)
2. [根本原因分析](#根本原因分析)
3. [Phase 1: 実施済み改修](#phase-1-実施済み改修)
4. [Phase 2-3: 残存課題](#phase-2-3-残存課題)
5. [推奨アクション](#推奨アクション)
6. [技術的な詳細](#技術的な詳細)

---

## 🔍 発見された問題

### 問題1: データフローの断絶（最優先課題）

**症状**:
- 2,087件がlistingsテーブルに登録されている
- しかし、upload_queueには277件しか追加されていない
- **1,885件が「宙に浮いている」状態**

**影響**:
- 商品登録したのにアップロードされない
- 手動でキュー追加を忘れると永久に処理されない
- データの整合性が保たれない

**データ**:
```
listingsテーブル (BASE):
  - pending: 1,896件 ← ❌ ほとんどがキューに入っていない
  - listed:    191件

upload_queue:
  - success:   229件
  - failed:     47件
  - uploading:   1件
  - Total:     277件

差分: 1,885件が未処理
```

### 問題2: SP-API処理の非効率性

**症状**:
- 1ASINあたり約4.2秒かかる（2回のAPI呼び出し × 2.1秒待機）
- 2,000件の処理に約2.3時間かかる

**原因**:
- 1件ずつシリアルに処理している
- Catalog APIのバッチ処理（20件/リクエスト）が実装されていない

### 問題3: ステータス更新の不整合

**症状**:
- アップロード成功したのに、listingsテーブルがpendingのまま残っているケースが8件

---

## 🎯 根本原因分析

### 原因1: 3ステップワークフローの分離

現在のワークフロー:

```
┌─────────────────────────────────────────┐
│ STEP 1: add_new_products.py            │
│ SP-API → products + listings           │
└─────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│ ❌ 手動操作が必要（ここで処理が止まる）   │
└─────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│ STEP 2: add_to_queue.py                │
│ listings → upload_queue                │
└─────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│ STEP 3: upload_daemon.py               │
│ upload_queue → BASE API                │
└─────────────────────────────────────────┘
```

**問題点**: STEP 1とSTEP 2の間に**手動操作が必要**

### 原因2: SP-APIのレート制限

| API | レート制限 | 実装状況 | 問題点 |
|---|---|---|---|
| Catalog API | 5リクエスト/秒<br>200リクエスト/時 | ✅ バッチメソッド定義済み | ❌ 使用されていない |
| Products API | 0.5リクエスト/秒<br>※価格取得 | ✅ 正しく実装 | ⚠️ 1件ずつのみ対応 |

**計算**:
- 1 ASIN = Catalog API (2.1秒) + Products API (2.1秒) = **4.2秒**
- 2,000 ASINs = 4.2秒 × 2,000 = 8,400秒 = **約2.3時間**

### 原因3: エラーハンドリングの不足

upload_executor.pyでのステータス更新処理に、一部例外ケースでの更新漏れがある可能性。

---

## ✅ Phase 1: 実施済み改修

### 改修内容

**ファイル**: `inventory/scripts/add_new_products.py`

#### 1. 自動キュー追加機能の実装

**変更点**:
- 商品追加成功後、自動的に`upload_queue`に追加
- 成功したASINのみを追跡する`successfully_added_asins`リストを導入
- 時間分散（6AM-11PM）を自動適用
- アカウント自動割り当て

**コード変更**:
```python
# 新しい変数
successfully_added_asins = []  # 成功したASINのリスト

# 商品追加成功時
successfully_added_asins.append(asin)

# 処理完了後、自動的にキューに追加
if success_count > 0 and not args.no_auto_queue:
    queue_manager = UploadQueueManager()
    result = queue_manager.add_batch_to_queue(
        asins=successfully_added_asins,
        platform=args.platform,
        priority=args.queue_priority,
        distribute_time=True
    )
```

#### 2. 新しいコマンドラインオプション

| オプション | 説明 | デフォルト |
|---|---|---|
| `--no-auto-queue` | 自動キュー追加を無効化 | False（有効） |
| `--queue-priority` | キュー優先度 (1-20) | 5（通常） |

#### 3. エラーハンドリングの強化

- キュー追加失敗時の例外処理
- 失敗時に手動コマンドを表示

### 新しいワークフロー

```
add_new_products.py 実行
  ↓
SP-APIから商品情報取得
  ↓
productsテーブルに追加
  ↓
listingsテーブルに追加
  ↓
✨ 自動的にupload_queueに追加（NEW）
  ↓
デーモンが自動アップロード（既存）
```

### 使用方法

#### 基本的な使い方（自動キュー追加あり）

```bash
python inventory/scripts/add_new_products.py \
  --asin-file asins.txt \
  --platform base \
  --account-id base_account_1 \
  --use-sp-api \
  --yes
```

#### 自動キュー追加を無効化

```bash
python inventory/scripts/add_new_products.py \
  --asin-file asins.txt \
  --platform base \
  --account-id base_account_1 \
  --use-sp-api \
  --no-auto-queue \
  --yes
```

#### 優先度を指定

```bash
# 緊急登録（優先度20）
python inventory/scripts/add_new_products.py \
  --asin-file urgent_asins.txt \
  --platform base \
  --account-id base_account_1 \
  --use-sp-api \
  --queue-priority 20 \
  --yes
```

### 期待される効果

| 項目 | 改善前 | 改善後 |
|---|---|---|
| **手動操作** | 2ステップ必要 | 自動化（0ステップ） |
| **処理漏れリスク** | 高い（手動忘れ） | ほぼゼロ |
| **運用負荷** | 毎回手動実行 | 完全自動 |
| **データ整合性** | 不安定 | 安定 |

---

## 🔧 Phase 2-3: 残存課題

### Phase 2: SP-API処理の効率化（優先度: 高）

#### 課題

**現状**:
- 1ASINあたり4.2秒（2回のAPI × 2.1秒待機）
- 2,000件で約2.3時間

**目標**:
- Catalog APIのバッチ処理実装（20件/リクエスト）
- 処理時間を約30分に短縮（約4.6倍高速化）

#### 提案する改修

**ファイル**: `integrations/amazon/sp_api_client.py`

1. **新しいバッチ取得メソッドの実装**

```python
def get_catalog_items_batch_optimized(self, asins: List[str], batch_size: int = 20):
    """
    Catalog APIで最大20件ずつ効率的に取得

    注意: Products API（価格）は依然として1件ずつ取得する必要がある
    """
    results = {}

    # 20件ずつバッチ処理
    for i in range(0, len(asins), batch_size):
        batch = asins[i:i + batch_size]

        # レート制限待機（1回のみ）
        self._wait_for_rate_limit()

        # バッチリクエスト
        catalog_client = CatalogItems(
            marketplace=self.marketplace,
            credentials=self.credentials
        )

        batch_result = catalog_client.search_catalog_items(
            identifiers=batch,
            identifiersType='ASIN',
            includedData=['attributes', 'summaries', 'images']
        )

        # 結果を統合
        results.update(batch_result)

    return results
```

2. **add_new_products.pyでのバッチ処理適用**

```python
# 現在の1件ずつ処理を変更
# Before:
for asin in asins:
    product_info = fetch_product_info_from_sp_api(asin, ...)

# After:
# まずCatalog APIでバッチ取得
catalog_results = sp_client.get_catalog_items_batch_optimized(asins, batch_size=20)

# 次に価格情報を1件ずつ取得（これは避けられない）
for asin in asins:
    product_info = catalog_results.get(asin)
    if product_info:
        price_info = sp_client.get_product_price(asin)
        product_info.update(price_info)
```

#### 期待される効果

| 項目 | 現状 | 改善後 | 効果 |
|---|---:|---:|---|
| Catalog API呼び出し | 2,000回 | 100回 | 95%削減 |
| 処理時間（2,000件） | 約2.3時間 | 約30分 | 約4.6倍高速化 |

#### 制約事項

- **Products API（価格取得）は1件ずつ処理が必須**
  - API仕様上、バッチ処理に対応していない
  - これは避けられない制約
- 並列処理は**実装すべきではない**
  - 1アプリケーション登録のため、並列化するとレート制限に引っかかる

### Phase 3: データ整合性の向上（優先度: 中）

#### 課題1: listingsステータス更新の不整合

**症状**:
- アップロード成功したのに`status='pending'`のまま残るケースが8件

**原因**:
- `upload_executor.py`のエラーハンドリング不足
- トランザクション処理の欠如

#### 提案する改修

**ファイル**: `scheduler/upload_executor.py`

1. **ステータス更新の確実化**

```python
def upload_item(self, queue_item: Dict[str, Any]) -> Dict[str, Any]:
    # ... アップロード処理 ...

    # 成功時のステータス更新を確実に行う
    try:
        # キューステータス更新
        self.queue_manager.update_queue_status(
            queue_id=queue_id,
            status=UploadQueueManager.STATUS_SUCCESS,
            result_data={...}
        )

        # listingsステータス更新（トランザクション内で）
        with self.db.get_connection() as conn:
            self.db.update_listing(
                listing['id'],
                platform_item_id=item_id,
                status='listed'
            )
            # 両方成功した場合のみcommit

    except Exception as e:
        # 更新失敗時のロールバック処理
        logger.error(f"Status update failed: {e}")
        # リトライまたはアラート
```

2. **定期的な整合性チェックスクリプト**

新規ファイル: `scheduler/scripts/check_consistency.py`

```python
"""
データ整合性チェックスクリプト

upload_queueとlistingsの不整合を検出・修正
"""

def check_and_fix_consistency():
    """
    1. upload_queue.status='success' だが listings.status='pending'
    2. listings.platform_item_id != NULL だが status='pending'
    などの不整合を検出して修正
    """
    pass
```

---

## 🎯 推奨アクション

### 即座に実行すべき事項

#### 1. 宙に浮いている1,885件の処理

```bash
cd C:\Users\hiroo\Documents\GitHub\ecauto

# pendingステータスの全てをキューに追加
python scheduler/scripts/add_to_queue.py \
  --platform base \
  --distribute \
  --limit 2000 \
  --yes

# 結果を確認
python scheduler/scripts/check_queue.py --platform base
```

#### 2. デーモンの稼働確認

```bash
# サービス状態確認
nssm status ECAutoUploadScheduler-BASE

# ログ確認（最新100行）
Get-Content "C:\Users\hiroo\Documents\GitHub\ecauto\logs\upload_scheduler_base.log" -Tail 100
```

#### 3. 今後の新規登録

```bash
# 今後はこのコマンドだけでOK（自動的にキューに追加される）
python inventory/scripts/add_new_products.py \
  --asin-file new_asins.txt \
  --platform base \
  --account-id base_account_1 \
  --use-sp-api \
  --yes
```

### 短期的な改善（1-2週間以内）

#### Phase 2の実装

**タスク**:
1. `sp_api_client.py`にバッチ処理メソッドを追加
2. `add_new_products.py`でバッチ処理を使用
3. テストと検証

**期待効果**:
- 処理時間が約4.6倍高速化
- API呼び出し回数が95%削減

### 中期的な改善（1ヶ月以内）

#### Phase 3の実装

**タスク**:
1. `upload_executor.py`のトランザクション処理強化
2. 整合性チェックスクリプトの作成
3. 定期実行の設定（cron/タスクスケジューラ）

**期待効果**:
- データ整合性の向上
- 不整合の自動検出・修復

---

## 📚 技術的な詳細

### データベーススキーマ

#### products テーブル
```sql
CREATE TABLE products (
    asin TEXT PRIMARY KEY,
    title_ja TEXT,
    title_en TEXT,
    description_ja TEXT,
    description_en TEXT,
    category TEXT,
    brand TEXT,
    images TEXT,  -- JSON
    amazon_price_jpy INTEGER,
    amazon_in_stock BOOLEAN,
    last_fetched_at TIMESTAMP,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

#### listings テーブル
```sql
CREATE TABLE listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asin TEXT,
    platform TEXT,  -- 'base', 'ebay', etc.
    account_id TEXT,
    platform_item_id TEXT,  -- BASE item_id等
    sku TEXT UNIQUE,
    selling_price REAL,
    currency TEXT DEFAULT 'JPY',
    in_stock_quantity INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending',  -- 'pending', 'listed', 'sold'
    visibility TEXT DEFAULT 'public',
    listed_at TIMESTAMP,
    updated_at TIMESTAMP,
    FOREIGN KEY (asin) REFERENCES products(asin),
    UNIQUE(asin, platform)  -- 同じASINは1プラットフォーム1回のみ
);
```

#### upload_queue テーブル
```sql
CREATE TABLE upload_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asin TEXT,
    platform TEXT,
    account_id TEXT,
    scheduled_time TIMESTAMP,
    priority INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending',  -- 'pending', 'uploading', 'success', 'failed'
    retry_count INTEGER DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMP,
    processed_at TIMESTAMP,
    FOREIGN KEY (asin) REFERENCES products(asin)
);
```

### SP-API レート制限

| API | レート制限 | 実装状況 |
|---|---|---|
| Catalog Items API | 5 req/sec<br>200 req/hour | バッチ20件/req可能 |
| Products API (Offers) | 0.5 req/sec<br>18 req/hour | 1件/reqのみ |

### 処理フローダイアグラム

```
┌─────────────────────────────────────────────────────┐
│ 1. ASINリスト読み込み                                │
│    - ファイルから読み込み                             │
│    - 重複除外                                        │
└─────────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────┐
│ 2. SP-API 商品情報取得                               │
│    - Catalog API: 商品基本情報                       │
│    - Products API: 価格・在庫情報                    │
│    - キャッシュチェック                               │
└─────────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────┐
│ 3. マスタDB登録                                      │
│    - productsテーブル: 商品マスタ                     │
│    - listingsテーブル: 出品情報 (status='pending')   │
└─────────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────┐
│ 4. アップロードキュー追加 ✨NEW                       │
│    - upload_queueテーブル                            │
│    - 時間分散（6AM-11PM）                            │
│    - アカウント自動割り当て                           │
└─────────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────┐
│ 5. デーモンによる自動アップロード                     │
│    - scheduled_time到来時に実行                      │
│    - BASE APIでアップロード                          │
│    - ステータス更新 (success/failed)                 │
└─────────────────────────────────────────────────────┘
```

---

## 📝 変更履歴

| 日付 | Phase | 変更内容 | 担当 |
|---|---|---|---|
| 2025-11-21 | Phase 1 | ワークフロー自動化実装 | Claude |
| - | Phase 2 | 未着手 | - |
| - | Phase 3 | 未着手 | - |

---

## 🔗 関連ドキュメント

- [scheduler/README.md](../scheduler/README.md) - スケジューラー全体の説明
- [platforms/base/README.md](../platforms/base/README.md) - BASE API連携の詳細
- [QUICKSTART.md](../QUICKSTART.md) - 全体のセットアップガイド

---

## ❓ FAQ

### Q1: 自動キュー追加を無効化したい

**A**: `--no-auto-queue`オプションを使用してください。

```bash
python inventory/scripts/add_new_products.py \
  --asin-file asins.txt \
  --platform base \
  --account-id base_account_1 \
  --no-auto-queue \
  --yes
```

### Q2: 既存の1,885件はどうなる？

**A**: 手動でキューに追加する必要があります。

```bash
python scheduler/scripts/add_to_queue.py \
  --platform base \
  --distribute \
  --limit 2000 \
  --yes
```

### Q3: Phase 2はいつ実装すべき？

**A**: 以下の状況で実装を推奨：
- 定期的に数百件以上のASINを登録する場合
- SP-API呼び出し回数を削減したい場合
- 処理時間を短縮したい場合

現在の処理速度で問題なければ、Phase 2は優先度を下げても良いでしょう。

### Q4: デーモンが止まっているか確認したい

**A**: 以下のコマンドで確認できます。

```bash
# サービス状態
nssm status ECAutoUploadScheduler-BASE

# ログ確認
Get-Content "C:\Users\hiroo\Documents\GitHub\ecauto\logs\upload_scheduler_base.log" -Tail 50
```

---

**Document Version**: 1.0
**Last Updated**: 2025-11-21
**Author**: Claude (AI Assistant)
**Reviewed By**: -
