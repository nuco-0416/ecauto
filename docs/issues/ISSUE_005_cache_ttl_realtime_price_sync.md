# Issue #005: キャッシュTTL機構の未実装による価格・在庫更新の停止

**ステータス**: 🟡 実装中
**発生日**: 2025-11-23
**優先度**: 🔴 最高（ビジネスクリティカル）
**担当**: Claude Code
**影響範囲**: 全商品（10,772件）の価格・在庫同期

---

## 問題の詳細

### 症状

**現象:**
- 毎時間実行される価格・在庫同期デーモンが、**SP-APIから新データを取得していない**
- キャッシュファイルが数日間更新されていない（2025-11-21作成のキャッシュがそのまま使用）
- 価格変動・在庫切れを検知できず、ECプラットフォームに古いデータが反映され続ける

**深刻な影響:**
- ⚠️ **注文後に在庫がない**: 在庫切れ検知の遅延（最大数日）
- ⚠️ **原価割れで赤字**: Amazon価格上昇の検知遅延
- ⚠️ **価格競争力の低下**: Amazon価格下落の検知遅延

### 具体例

```bash
# キャッシュファイルの状態
-rw-r--r-- 1 hiroo 197609 11K 11月 21 05:50 B0006L0120.json

# ← 2日前のデータを使い続けている！
```

**キャッシュ内容:**
```json
{
  "price": 7560.0,
  "in_stock": true,
  "cached_at": "2025-11-23T01:15:38.317725"
}
```

**問題点:**
- `price_updated_at` フィールドが存在しない
- `stock_updated_at` フィールドが存在しない
- `basic_info_updated_at` フィールドが存在しない
- TTL判定ができない → 常に古いキャッシュを使用

---

## 問題が発覚した経緯

### タイムライン

1. **2025-11-23 17:43** - UTF-8エンコーディング修正後、サービス再起動
2. **2025-11-23 17:49** - 在庫同期処理で627件更新
3. **調査開始** - Productsテーブルは更新されているのに、どこから取得？
4. **発見** - キャッシュファイルは2日前のまま（SP-API呼び出しなし）
5. **原因特定** - sync_prices.pyがTTLを無視してキャッシュのみ使用

### 発見の経緯

```bash
# Productsテーブルは更新されている
SELECT updated_at FROM products ORDER BY updated_at DESC LIMIT 5;
# → 2025-11-23 17:49:31

# しかしキャッシュファイルは古い
ls -lh inventory/data/cache/amazon_products/ | head -10
# → 11月 21 05:50 B0006L0120.json

# sync_prices.pyのコードを確認
# → "キャッシュから取得（TTL無視で直接ファイルを読む）"
```

---

## 問題解決のために参照したコード・ドキュメント

### 関連ファイル

#### 1. platforms/base/scripts/sync_prices.py (行126)

**問題のコード:**
```python
# キャッシュから取得（TTL無視で直接ファイルを読む）
if use_cache and cache_file.exists():
    try:
        with open(cache_file, 'r', encoding='utf-8') as f:
            cached_product = json.load(f)

        if cached_product.get('price') is not None:
            self.stats['cache_hits'] += 1
            return {
                'price_jpy': int(cached_product['price']),
                'in_stock': cached_product.get('in_stock', False)
            }
```

**問題点:**
- ファイルが存在すれば**無条件で使用**
- TTLチェックが実装されていない
- SP-API呼び出しが発生しない

#### 2. inventory/scripts/validate_and_fill_cache.py (行121, 131)

**TTL判定の実装（未使用）:**
```python
# 価格TTLチェック（24時間）
elif self.is_expired(cache_data.get('price_updated_at', ''), self.TTL_PRICE):
    result['needs_update'] = True

# 在庫TTLチェック（1時間）
elif self.is_expired(cache_data.get('stock_updated_at', ''), self.TTL_STOCK):
    result['needs_update'] = True
```

**問題点:**
- `price_updated_at`, `stock_updated_at` フィールドが**キャッシュに存在しない**
- validate_and_fill_cache.pyは**手動実行のみ**（デーモンで使用されていない）
- TTL機構は設計されていたが、**実装が不完全**

#### 3. inventory/core/cache_manager.py (行97-126)

**キャッシュ保存処理:**
```python
def set_product(self, asin: str, data: Dict[str, Any]) -> bool:
    cache_file = self.cache_dir / f'{asin}.json'

    # タイムスタンプを追加
    data['cached_at'] = datetime.now().isoformat()  # ← これだけ

    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
```

**問題点:**
- `cached_at` のみ記録
- データ種別ごとの更新日時（price_updated_at等）が記録されない
- 部分更新に対応していない

#### 4. integrations/amazon/sp_api_client.py

**API使い分けの確認:**
- **Products API** (`get_item_offers_batch`): 価格・在庫を取得 (行426-580)
- **CatalogItems API** (`get_catalog_item`): 基本情報（説明・画像）を取得 (行140-256)

**重要な発見:**
- 価格と在庫は**同じAPIエンドポイント**から同時取得
- 1回のAPI呼び出しで両方のデータを取得できる
- 別々のTTLは不要だが、基本情報は別API → TTL機構が必要

---

## 根本原因の分析

### 原因1: キャッシュ構造の不整合

**設計上の意図:**
```json
{
  "price": 7560.0,
  "in_stock": true,
  "title_ja": "商品名",
  "description_ja": "説明",
  "price_updated_at": "2025-11-23T17:00:00",    // 価格の最終更新
  "stock_updated_at": "2025-11-23T17:00:00",    // 在庫の最終更新
  "basic_info_updated_at": "2025-11-20T00:00:00" // 基本情報の最終更新
}
```

**実際のキャッシュ:**
```json
{
  "price": 7560.0,
  "in_stock": true,
  "cached_at": "2025-11-23T01:15:38.317725"  // ← 全体の保存時刻のみ
}
```

### 原因2: 2系統の更新フローの混同

ユーザーからの指摘通り、以下の2系統を厳格に区別していなかった：

**①SP-API ⇔ ローカルキャッシュ:**
- 現状: **更新されていない**（毎時間のデーモンがキャッシュのみ使用）
- 期待: 1〜3時間ごとにSP-APIから最新データを取得

**②ローカルキャッシュ ⇔ ECプラットフォーム:**
- 現状: **正常に動作**（古いデータをBASEに反映）
- 期待: 最新データをBASEに反映

### 原因3: 3つの処理の役割が不明確

| 処理 | 本来の役割 | 実際の動作 |
|------|----------|-----------|
| **商品登録** | 初回のみ全情報取得 | ✅ 正常 |
| **価格・在庫定期更新** | 1〜3時間ごと | ❌ キャッシュのみ使用 |
| **基本情報定期更新** | 週1回 | ❌ 未実装 |

---

## 解決方法

### 設計方針

ユーザーの要件を満たす3階層のキャッシュ管理を実装：

```
【処理A】価格・在庫の定期更新（頻繁） ← 最重要
┌─────────────────────────────────────────┐
│ sync_prices.py（修正版）                 │
│ - Products API呼び出し（バッチ処理）     │
│ - price, in_stock のみ更新               │
│ - price_updated_at, stock_updated_at更新 │
│ - 実行頻度: 3時間ごと（デーモン自動実行）│
│ - 所要時間: 約19分（10,772件）           │
└─────────────────────────────────────────┘

【処理B】基本情報の定期更新（低頻度）
┌─────────────────────────────────────────┐
│ update_basic_info.py（新規または既存修正）│
│ - CatalogItems API呼び出し               │
│ - title, description, images のみ更新    │
│ - basic_info_updated_at更新              │
│ - 実行頻度: 週1回（cronまたは手動）       │
└─────────────────────────────────────────┘

【処理C】新規商品登録（初回のみ）
┌─────────────────────────────────────────┐
│ add_new_products.py（既存のまま）        │
│ - CatalogItems API + Products API       │
│ - 全情報を一度に取得                     │
│ - すべての*_updated_atを設定             │
└─────────────────────────────────────────┘
```

### Phase 1: キャッシュ管理機能の拡張

**修正ファイル:** `inventory/core/cache_manager.py`

**追加機能:**
- 部分更新対応（価格のみ、基本情報のみ等）
- データ種別ごとの更新日時記録
- TTL判定機能

**実装内容:**
```python
def set_product(self, asin: str, data: Dict[str, Any],
                update_types: List[str] = ['all']) -> bool:
    """
    商品情報をキャッシュに保存（部分更新対応）

    Args:
        asin: ASIN
        data: 更新データ
        update_types: 更新タイプ ['price', 'stock', 'basic_info', 'all']

    Returns:
        bool: 成功時True
    """
    cache_file = self.cache_dir / f'{asin}.json'
    now = datetime.now().isoformat()

    # 既存データを読み込み（部分更新の場合）
    existing_data = {}
    if cache_file.exists() and 'all' not in update_types:
        with open(cache_file, 'r', encoding='utf-8') as f:
            existing_data = json.load(f)

    # データをマージ
    merged_data = {**existing_data, **data}

    # 更新日時を設定
    if 'price' in update_types or 'all' in update_types:
        merged_data['price_updated_at'] = now
    if 'stock' in update_types or 'all' in update_types:
        merged_data['stock_updated_at'] = now
    if 'basic_info' in update_types or 'all' in update_types:
        merged_data['basic_info_updated_at'] = now

    merged_data['cached_at'] = now

    # 保存
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(merged_data, f, ensure_ascii=False, indent=2)

    return True
```

### Phase 2: 価格・在庫更新の修正

**修正ファイル:** `platforms/base/scripts/sync_prices.py`

**主な変更点:**
1. キャッシュチェックを**スキップ**（または最小限に）
2. **SP-APIバッチで全商品を取得**（20件/リクエスト）
3. キャッシュとProductsテーブルを更新（①SP-API ⇔ キャッシュ）
4. 価格変動検知 → BASE更新（②キャッシュ ⇔ ECプラットフォーム）
5. Chatwork通知

**実装概要:**
```python
def sync_account_prices(self, account_id: str, dry_run: bool = False):
    """1アカウントの価格を同期（SP-APIバッチ使用）"""

    # 出品一覧を取得
    listings = self.master_db.get_listings_by_account(
        platform='base',
        account_id=account_id,
        status='listed'
    )
    asins = [listing['asin'] for listing in listings]

    print(f"[重要] SP-APIバッチで最新価格・在庫を取得: {len(asins)}件")

    # ①SP-API → キャッシュ（バッチ処理で効率化）
    batch_results = self.sp_api_client.get_prices_batch(
        asins,
        batch_size=20
    )

    price_changed = []
    stock_changed = []

    for asin, price_info in batch_results.items():
        if not price_info or price_info.get('price') is None:
            continue

        # 旧データを取得
        old_product = self.master_db.get_product(asin)
        old_price = old_product.get('amazon_price_jpy') if old_product else None
        old_stock = old_product.get('amazon_in_stock') if old_product else None

        new_price = int(price_info['price'])
        new_stock = price_info.get('in_stock', False)

        # ①-a: SP-API → キャッシュ（価格・在庫のみ更新）
        self.cache.set_product(
            asin,
            price_info,
            update_types=['price', 'stock']  # 部分更新
        )

        # ①-b: SP-API → Productsテーブル
        self.master_db.update_amazon_info(
            asin=asin,
            price_jpy=new_price,
            in_stock=new_stock
        )

        # 変動検知
        if old_price and abs(new_price - old_price) >= 100:
            price_changed.append({
                'asin': asin,
                'old': old_price,
                'new': new_price,
                'diff': new_price - old_price
            })

        if old_stock is not None and old_stock != new_stock:
            stock_changed.append({
                'asin': asin,
                'old': '在庫あり' if old_stock else '在庫切れ',
                'new': '在庫あり' if new_stock else '在庫切れ'
            })

    # ②キャッシュ → BASE更新（既存のロジック）
    for listing in listings:
        self._sync_listing_price_with_info(listing, base_client, ...)

    # Chatwork通知（既存のnotifier使用）
    if price_changed or stock_changed:
        self.notifier.notify(
            event_type='task_completion',
            title='価格・在庫更新完了',
            message=self._format_notification_message(
                total=len(batch_results),
                price_changed=price_changed,
                stock_changed=stock_changed
            )
        )
```

### Phase 3: デーモン実行間隔の変更

**修正ファイル:** `scheduled_tasks/sync_inventory_daemon.py`

**変更内容:**
```python
# デフォルト実行間隔を3時間に変更
DEFAULT_INTERVAL = 3 * 3600  # 10,800秒
```

**またはサービスインストールスクリプト修正:**
```batch
# deploy/windows/install_sync_inventory_service.bat (行27)
set INTERVAL=10800
REM 3時間ごとに実行（1時間 = 3600秒）
```

---

## 実装計画

### タイムライン

| Phase | 作業内容 | 所要時間 | 担当 |
|-------|---------|---------|------|
| 1 | cache_manager.py拡張 | 30分 | Claude Code |
| 2 | sync_prices.py修正 | 60分 | Claude Code |
| 3 | デーモン間隔変更 | 15分 | Claude Code |
| 4 | テスト実行（dry-run） | 30分 | Claude Code |
| 5 | 本番デプロイ | 10分 | Claude Code |
| **合計** | **2時間25分** | | |

### Phase別詳細

#### Phase 1: cache_manager.py拡張

**追加メソッド:**
- `set_product()`: 部分更新対応に改修
- `get_product_with_ttl()`: TTL判定付き取得（オプション）

**テスト:**
```bash
# ユニットテスト
python -m pytest tests/test_cache_manager.py -v
```

#### Phase 2: sync_prices.py修正

**変更箇所:**
1. `get_amazon_price()`: キャッシュチェックを最小化
2. `sync_account_prices()`: バッチAPI使用に変更
3. 通知メッセージのフォーマット追加

**テスト:**
```bash
# DRY RUN
python platforms/base/scripts/sync_prices.py --dry-run --account-id base_account_1
```

#### Phase 3: デーモン間隔変更

**サービス再インストール:**
```bash
# 管理者権限で実行
cd C:\Users\hiroo\Documents\GitHub\ecauto\deploy\windows
uninstall_sync_inventory_service.bat
install_sync_inventory_service.bat
```

#### Phase 4: テスト実行

**dry-runでの確認事項:**
- SP-API呼び出し回数（539回、約19分）
- キャッシュ更新の確認
- Productsテーブル更新の確認
- 価格変動検知の動作
- 通知メッセージの内容

#### Phase 5: 本番デプロイ

**手順:**
1. サービス停止
2. コード更新
3. サービス起動
4. ログ監視（最初の1サイクル）
5. 動作確認

---

## 期待される効果

### 修正前

```
┌─────────────────────────────────────────┐
│ 毎時間実行                               │
│ - キャッシュのみ使用（古いデータ）       │
│ - SP-API呼び出し: 0回                    │
│ - 価格変動検知: なし                     │
│ - 在庫切れ検知: なし                     │
│ - 遅延: 最大数日                         │
└─────────────────────────────────────────┘
```

### 修正後

```
┌─────────────────────────────────────────┐
│ 3時間ごとに実行                          │
│ - SP-APIバッチ取得（最新データ）         │
│ - SP-API呼び出し: 539回（約19分）        │
│ - 価格変動検知: リアルタイム             │
│ - 在庫切れ検知: リアルタイム             │
│ - 遅延: 最大3時間                        │
│ - Chatwork通知: 変動時のみ               │
└─────────────────────────────────────────┘

日次実行回数: 8回（0:00, 3:00, 6:00, ...）
```

### ビジネスインパクト

| 指標 | 修正前 | 修正後 | 改善 |
|------|-------|-------|------|
| 価格変動検知 | 数日遅延 | 最大3時間 | 🟢 95%改善 |
| 在庫切れ検知 | 数日遅延 | 最大3時間 | 🟢 95%改善 |
| 注文後在庫切れリスク | 高 | 低 | 🟢 リスク大幅減 |
| 原価割れリスク | 高 | 低 | 🟢 リスク大幅減 |
| API呼び出し | 0回/日 | 4,312回/日 | ✅ 適正レベル |

---

## リスクと対策

### リスク1: API呼び出し増加

**懸念:**
- SP-API呼び出し: 0回/日 → 4,312回/日
- レート制限: 0.5リクエスト/秒（2秒に1回）

**対策:**
- ✅ バッチAPI使用（20件/リクエスト）
- ✅ レート制限遵守（2.1秒間隔）
- ✅ リトライ機構（最大3回）
- ✅ SP-APIは無料（金銭コストなし）

### リスク2: 処理時間の増加

**懸念:**
- 1サイクル: 約19分（10,772件）

**対策:**
- ✅ 3時間間隔で十分余裕あり
- ✅ バッチ処理で効率化
- ✅ 営業時間外は処理スキップ（オプション）

### リスク3: デーモン停止時の影響

**懸念:**
- デーモン停止中は更新されない

**対策:**
- ✅ 再起動時に即座に実行
- ✅ Chatwork通知で異常検知
- ✅ サービス自動再起動設定（NSSM）

---

## テスト計画

### テストケース

#### TC-1: 価格変動検知

**前提条件:**
- Amazon価格: 1,000円
- BASE価格: 1,300円

**操作:**
1. Amazon価格を1,200円に変更（外部）
2. sync_prices.py実行（dry-run）

**期待結果:**
- 価格変動検知: 1,000円 → 1,200円
- Productsテーブル更新: amazon_price_jpy = 1200
- キャッシュ更新: price_updated_at = 現在時刻
- Chatwork通知: 価格変動1件

#### TC-2: 在庫切れ検知

**前提条件:**
- Amazon在庫: あり
- BASE: 公開中

**操作:**
1. Amazon在庫を切らす（外部）
2. sync_prices.py実行

**期待結果:**
- 在庫変動検知: あり → なし
- Productsテーブル更新: amazon_in_stock = false
- BASE: 非公開に変更
- Chatwork通知: 在庫変動1件

#### TC-3: バッチAPI処理

**前提条件:**
- 対象商品: 100件

**操作:**
1. sync_prices.py実行（バッチサイズ20）

**期待結果:**
- SP-API呼び出し: 5回（100÷20）
- 所要時間: 約10秒（5回 × 2.1秒）
- 全100件のキャッシュ更新

---

## 関連Issue

- なし（新規の問題）

---

## セッション用プロンプト

次回この問題または類似問題が発生した場合、以下のプロンプトで問題解決を再開：

```
価格・在庫更新が停止している可能性があります。

症状:
- Productsテーブルは更新されているが、キャッシュファイルが古い
- sync_prices.pyがSP-APIを呼び出していない
- 価格変動・在庫切れを検知できていない

確認すべき点:
1. キャッシュファイルの更新日時（inventory/data/cache/amazon_products/）
2. キャッシュ構造に price_updated_at, stock_updated_at が存在するか
3. sync_prices.py がキャッシュのみ使用していないか
4. デーモンのログ（logs/sync_inventory.log）

参照ドキュメント:
- docs/issues/ISSUE_005_cache_ttl_realtime_price_sync.md
- inventory/core/cache_manager.py
- platforms/base/scripts/sync_prices.py

対応手順:
1. キャッシュ構造の確認
2. cache_manager.py の部分更新機能を確認
3. sync_prices.py のバッチAPI使用を確認
4. デーモン実行間隔を確認（3時間ごと）
5. テスト実行（dry-run）
6. 本番デプロイ
```

---

**作成日**: 2025-11-23
**最終更新**: 2025-11-23
**作成者**: Claude Code
**ステータス**: 🟡 実装中
**優先度**: 🔴 最高（ビジネスクリティカル）
