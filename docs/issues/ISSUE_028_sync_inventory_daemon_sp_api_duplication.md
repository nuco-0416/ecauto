# ISSUE #028: sync_inventory_daemonのSP-API通信重複問題

**日付:** 2025-12-07
**ステータス:** 🔴 未解決（調査完了、実装待ち）
**優先度:** 高（SP-APIレート制限・処理効率）
**関連ファイル:**
- `scheduled_tasks/sync_inventory_daemon.py`
- `inventory/scripts/sync_inventory.py`
- `platforms/base/scripts/sync_prices.py`
- `platforms/ebay/scripts/sync_prices.py`

---

## 📋 問題の概要

### 症状

`sync_inventory_daemon.py`は設計意図と実装が乖離しており、SP-API通信が不必要に2回以上実行される可能性があります。

**設計意図（コメント・ドキュメントから）:**
```
Phase 1: SP-API → キャッシュ（全体の価格・在庫を一括更新、1回のみ）
Phase 2: キャッシュ → 各プラットフォーム（ローカルDBのみ参照）
```

**実際の実装:**
```
Phase 1: 何もしない（pass）
Phase 2:
  - BASE: 毎回SP-APIバッチで全商品取得
  - eBay: キャッシュミス時に個別SP-API呼び出し
```

### ユーザーの想定

- 最初にSP-APIで全商品の価格・在庫情報を一括取得してキャッシュに保存
- その直後のプラットフォームごとの価格・在庫確認では、ローカルにあるマスタDBで同期された価格在庫情報を参照
- SP-APIへの通信を不必要に2回実行することを避ける

---

## 🔍 調査結果

### 問題1: Phase 1でSP-API処理が実行されていない

**ファイル:** `scheduled_tasks/sync_inventory_daemon.py`
**行番号:** 174-185

```python
# Phase 1: SP-API → キャッシュ（シリアル処理、1回のみ）
# skip_cache_updateが有効な場合はスキップ
if self.skip_cache_update:
    # ... スキップのログ表示 ...
else:
    # このフェーズは全プラットフォーム共通のため、1回だけ実行
    # InventorySyncのrun_full_syncが内部でSP-APIからキャッシュへの同期を実施
    # ここでは明示的な処理は不要（各プラットフォームの同期処理内で実施される）
    pass  # ← 実際には何もしていない！
```

**問題点:**
- コメントでは「SP-APIからキャッシュへの同期を実施」とあるが、実際には`pass`で何も処理していない
- 全体のキャッシュ更新が行われていないため、Phase 2で各プラットフォームが個別にSP-APIを呼び出す必要がある

---

### 問題2: BASEプラットフォームで毎回SP-APIバッチを実行

**ファイル:** `platforms/base/scripts/sync_prices.py`
**行番号:** 374-395

```python
if not skip_cache_update:
    # ISSUE #005 & #006対応: キャッシュをスキップして、常に全件をSP-APIバッチで取得
    logger.info(f"\n[重要] SP-APIバッチで最新価格・在庫を取得中...")
    logger.info(f"  対象商品数: {len(listings)}件")
    logger.info(f"  バッチサイズ: 20件/リクエスト")
    # ...
    batch_results = self.sp_api_client.get_prices_batch(asins, batch_size=20)
```

**問題点:**
- `sync_account_prices()`が呼ばれるたびに、`skip_cache_update=False`（デフォルト）の場合、全商品をSP-APIバッチで取得
- Phase 1でキャッシュ全体の更新が行われていないため、やむを得ずSP-APIを呼び出している

**呼び出しフロー:**
```
sync_inventory_daemon.py:284
  ↓
InventorySync.run_full_sync()
  ↓
PriceSync.sync_all_accounts()
  ↓
sync_account_prices(account_id, skip_cache_update=False)
  ↓
毎回SP-APIバッチを実行
```

---

### 問題3: eBayプラットフォームでもSP-APIを個別呼び出し

**ファイル:** `platforms/ebay/scripts/sync_prices.py`
**行番号:** 154-172, 304-307

```python
def fill_cache_for_asin(self, asin: str) -> Optional[Dict[str, Any]]:
    """
    SP-APIから商品情報を取得してキャッシュと Master DBを更新
    """
    # ...
    logger.info(f"  [SP-API] {asin} - Amazon価格を取得中...")
    product_data = self.sp_api_client.get_product_price(asin)
    # ...

# Line 304-307
if not amazon_info or not amazon_info.get('price_jpy'):
    if self.auto_fetch_sp_api:  # デフォルト: True
        amazon_info = self.fill_cache_for_asin(asin)
```

**問題点:**
- キャッシュがない場合、各ASINに対して個別にSP-APIを呼び出す
- `auto_fetch_sp_api=True`がデフォルトのため、キャッシュミス時にSP-APIを呼び出す
- BASEで既に取得済みのASINに対しても、eBayで再度SP-APIを呼び出す可能性がある

---

## 💡 根本原因の分析

### 原因1: Phase 1の実装が未完成

**設計上の意図:**
- Phase 1で全プラットフォームの全ASINを収集
- SP-APIバッチで一括取得してキャッシュに保存（1回のみ）

**実際の実装:**
- Phase 1では何もしていない（`pass`）
- 各プラットフォームがそれぞれSP-APIを呼び出す必要がある

### 原因2: Phase 2でのSP-API呼び出しを防ぐ仕組みがない

**設計上の意図:**
- Phase 2では`skip_cache_update=True`でキャッシュのみを参照
- または`allow_sp_api=False`でSP-API呼び出しを禁止

**実際の実装:**
- `skip_cache_update=False`（デフォルト）でSP-APIを毎回呼び出す
- `allow_sp_api=True`（デフォルト）でキャッシュミス時にSP-APIを呼び出す

### 原因3: アーキテクチャの乖離

**ドキュメント（README.md:258）:**
```
SP-APIレート制限対策: 並列処理を無効化してQuotaExceededエラーを回避
```

**問題点:**
- 並列処理を無効化しても、SP-API通信の重複は解決しない
- 根本的な解決にはPhase 1での一括更新が必要

---

## 🎯 解決策（提案）

### 案1: Phase 1で全ASINのキャッシュ更新を実装（推奨）

**目的:** 設計意図通りの実装を完成させる

**実装イメージ:**

#### sync_inventory_daemon.py の修正

```python
# Phase 1: SP-API → キャッシュ（シリアル処理、1回のみ）
if self.skip_cache_update:
    # スキップのログ表示
    pass
else:
    self.logger.info("\n" + "=" * 70)
    self.logger.info("【Phase 1】SP-API → キャッシュ同期")
    self.logger.info("=" * 70)

    # ステップ1: 全プラットフォームの全ASINを収集
    all_asins = self._collect_all_asins()
    self.logger.info(f"対象商品数: {len(all_asins)}件")

    # ステップ2: SP-APIバッチで一括取得してキャッシュに保存
    self._update_cache_for_asins(all_asins)

    self.logger.info("Phase 1完了: 全商品のキャッシュ更新完了")
```

#### 新規メソッドの実装

```python
def _collect_all_asins(self) -> List[str]:
    """
    全プラットフォームの全ASINを収集

    Returns:
        list: 重複なしのASINリスト
    """
    all_asins = set()

    for platform in self.platforms:
        if platform == 'base':
            # BASEの全出品からASINを収集
            listings = self.master_db.get_listings_by_platform('base', status='listed')
            for listing in listings:
                all_asins.add(listing['asin'])

        elif platform == 'ebay':
            # eBayの全出品からASINを収集
            listings = self.master_db.get_listings_by_platform('ebay', status='listed')
            for listing in listings:
                all_asins.add(listing['asin'])

    return list(all_asins)

def _update_cache_for_asins(self, asins: List[str]):
    """
    SP-APIバッチで全ASINの価格・在庫を取得してキャッシュに保存

    Args:
        asins: ASINリスト
    """
    from integrations.amazon.sp_api_client import AmazonSPAPIClient
    from integrations.amazon.config import SP_API_CREDENTIALS

    # SP-APIクライアント
    sp_api_client = AmazonSPAPIClient(SP_API_CREDENTIALS)

    # バッチサイズ20でSP-APIから取得
    batch_results = sp_api_client.get_prices_batch(asins, batch_size=20)

    # キャッシュとMaster DBを更新
    cache = AmazonProductCache()
    master_db = MasterDB()

    for asin, price_info in batch_results.items():
        if price_info and price_info.get('status') == 'success':
            # キャッシュに保存
            cache.set_product(asin, {
                'price': price_info['price'],
                'in_stock': price_info.get('in_stock', False)
            }, update_types=['price', 'stock'])

            # Master DBも更新
            master_db.update_amazon_info(
                asin=asin,
                price_jpy=int(price_info['price']),
                in_stock=price_info.get('in_stock', False)
            )

    self.logger.info(f"キャッシュ更新完了: {len(batch_results)}件")
```

#### Phase 2の修正

```python
# BASEの場合
stats = self.sync_instances[platform].run_full_sync(
    platform=platform,
    skip_cache_update=True,  # ← Trueに変更（SP-APIをスキップ）
    max_items=self.max_items
)

# eBayの場合
# EbayPriceSync.__init__() に auto_fetch_sp_api=False を渡す
self.sync_instances[platform] = EbayPriceSync(
    markup_ratio=None,
    auto_fetch_sp_api=False  # ← SP-API自動取得を無効化
)
```

**メリット:**
- ✅ 設計意図通りの実装
- ✅ SP-API通信の重複を完全に解消
- ✅ レート制限のリスク低減
- ✅ 処理時間の短縮（重複呼び出しの削減）

**デメリット:**
- 実装が必要（約2-3時間）
- テストが必要

---

### 案2: Phase 2でSP-API呼び出しを禁止（部分対応）

**目的:** 最小限の修正で重複を防ぐ

**実装イメージ:**

#### sync_inventory_daemon.py の修正

```python
# BASEの場合
stats = self.sync_instances[platform].run_full_sync(
    platform=platform,
    skip_cache_update=True,  # ← キャッシュのみ使用
    max_items=self.max_items
)

# eBayの場合
self.sync_instances[platform] = EbayPriceSync(
    markup_ratio=None,
    auto_fetch_sp_api=False  # ← SP-API自動取得を無効化
)
```

**メリット:**
- ✅ 実装が簡単（30分程度）
- ✅ SP-API通信の重複を防ぐ

**デメリット:**
- ❌ Phase 1でキャッシュ更新が行われないため、価格情報が古くなる可能性
- ❌ 初回実行時にキャッシュがない場合、価格情報が取得できない
- ❌ 設計意図と乖離したままの実装

---

### 案3: 現状維持（非推奨）

**理由:**
- SP-API通信の重複によるレート制限リスク
- 処理時間の増加
- 設計意図との乖離

**採用しない方が良い理由:**
- ISSUE #006でQuotaExceededエラーを経験済み
- 同じ問題が再発するリスクが高い

---

## 📊 期待される効果

### 案1実装後の効果

**実装前:**
```
┌─────────────────────────────────────────┐
│ Phase 1: 何もしない（pass）              │
│ Phase 2: 各プラットフォームがSP-API呼び出し│
│   - BASE: 全商品バッチ取得               │
│   - eBay: キャッシュミス時に個別取得     │
│                                          │
│ 問題:                                    │
│ - SP-API通信の重複                       │
│ - レート制限のリスク                     │
│ - 処理時間の増加                         │
└─────────────────────────────────────────┘
```

**実装後:**
```
┌─────────────────────────────────────────┐
│ Phase 1: SP-API → キャッシュ（1回のみ）  │
│   - 全プラットフォームの全ASIN収集       │
│   - SP-APIバッチで一括取得               │
│   - キャッシュ・Master DB更新            │
│                                          │
│ Phase 2: キャッシュ → 各プラットフォーム │
│   - BASE: キャッシュのみ参照             │
│   - eBay: キャッシュのみ参照             │
│                                          │
│ 改善:                                    │
│ ✅ SP-API通信は1回のみ                   │
│ ✅ レート制限リスクの低減                │
│ ✅ 処理時間の短縮                        │
└─────────────────────────────────────────┘
```

### 処理時間の改善（推定）

| 項目 | 実装前 | 実装後 | 改善率 |
|------|--------|--------|--------|
| SP-API呼び出し回数 | 2-3回（BASE + eBay） | 1回（Phase 1のみ） | 🟢 50-66%削減 |
| レート制限違反リスク | 中 | 低 | 🟢 大幅改善 |
| 処理時間（10,000件） | 約98分 + α | 約98分 | ➖ 同程度 |

**注記:**
- 処理時間は同程度だが、SP-API通信の重複が解消されるため、レート制限のリスクが大幅に低減
- eBayでのキャッシュミス時の個別SP-API呼び出しが不要になる

---

## 🛠️ 実装計画（提案）

### タイムライン

| Phase | 作業内容 | 所要時間 | 優先度 |
|-------|---------|---------|-------|
| 1 | Phase 1のキャッシュ更新実装 | 2時間 | 🔴 高 |
| 2 | Phase 2のSP-API呼び出し禁止 | 30分 | 🔴 高 |
| 3 | テスト実行（dry-run） | 1時間 | 必須 |
| 4 | 本番デプロイ | 30分 | 必須 |
| **合計** | **4時間** | |

### Phase 1: キャッシュ更新実装

**作業内容:**

1. `_collect_all_asins()` メソッドの実装
   - 全プラットフォームの全ASINを収集
   - 重複を除去

2. `_update_cache_for_asins()` メソッドの実装
   - SP-APIバッチで一括取得
   - キャッシュ・Master DB更新

3. Phase 1での呼び出し
   - `skip_cache_update=False`の場合に実行

**テスト:**
```bash
# DRY RUN
venv\Scripts\python.exe scheduled_tasks\sync_inventory_daemon.py --dry-run --max-items 100
```

**所要時間:** 2時間

### Phase 2: SP-API呼び出し禁止

**作業内容:**

1. `sync_inventory_daemon.py` の修正
   - BASEの場合: `skip_cache_update=True`
   - eBayの場合: `auto_fetch_sp_api=False`

2. エラーハンドリング
   - キャッシュがない場合の警告ログ

**テスト:**
```bash
# DRY RUN
venv\Scripts\python.exe scheduled_tasks\sync_inventory_daemon.py --dry-run --max-items 100
```

**所要時間:** 30分

### Phase 3: テスト実行

**dry-runテスト:**
```bash
# 少量データでテスト
venv\Scripts\python.exe scheduled_tasks\sync_inventory_daemon.py --dry-run --max-items 100

# 全件テスト
venv\Scripts\python.exe scheduled_tasks\sync_inventory_daemon.py --dry-run
```

**確認事項:**
- [ ] Phase 1でキャッシュが全件更新される
- [ ] Phase 2でSP-API呼び出しが発生しない
- [ ] 価格・在庫情報が正しく取得できる
- [ ] エラーが発生しない

**所要時間:** 1時間

### Phase 4: 本番デプロイ

**手順:**
1. サービス停止
2. コード更新
3. サービス起動
4. ログ監視（最初の1サイクル）

**所要時間:** 30分

---

## ⚠️ リスクと対策

### リスク1: Phase 1でのSP-API呼び出し失敗

**懸念:**
- Phase 1でSP-API呼び出しが失敗すると、全プラットフォームの価格情報が取得できない

**対策:**
- ✅ エラーハンドリングを実装
- ✅ 失敗時は既存のキャッシュを使用（フォールバック）
- ✅ 失敗したASINのみPhase 2で個別取得

### リスク2: キャッシュ更新の遅延

**懸念:**
- Phase 1での一括更新により、処理開始が遅れる可能性

**対策:**
- ✅ Phase 1とPhase 2を並列化しない（設計通り）
- ✅ 処理時間は同程度に保つ

### リスク3: レート制限の問題

**懸念:**
- Phase 1での一括更新でレート制限に抵触する可能性

**対策:**
- ✅ 既存のレート制限設定（12秒/バッチ）を使用
- ✅ ISSUE #006で検証済みの安全な設定

---

## 📝 関連Issue

- **ISSUE #005**: キャッシュTTL機構の未実装による価格・在庫更新の停止
  - 関連: ISSUE #005でバッチ処理を実装したが、Phase 1での一括更新が未実装だった

- **ISSUE #006**: SP-APIレート制限違反とgetPricing APIへの移行
  - 関連: レート制限の問題を解決したが、SP-API通信の重複は残存

- **ISSUE #022**: 価格同期の詳細なエラー分類とフォールバック機能実装
  - 関連: APIエラー時のフォールバック機能を実装したが、Phase 1での一括更新が未実装

---

## 🔄 次回実装時の確認事項

- [ ] Phase 1で全ASINが収集される
- [ ] Phase 1でSP-APIバッチが正しく実行される
- [ ] キャッシュ・Master DBが正しく更新される
- [ ] Phase 2でSP-API呼び出しが発生しない
- [ ] 価格・在庫情報が正しく取得できる
- [ ] エラーハンドリングが正しく機能する
- [ ] 処理時間が許容範囲内

---

## 📚 セッション用プロンプト

次回この問題または類似問題が発生した場合、以下のプロンプトで問題解決を再開：

```
sync_inventory_daemonのSP-API通信重複問題について対応します。

症状:
- Phase 1でSP-API処理が実行されていない（pass）
- Phase 2で各プラットフォームが個別にSP-APIを呼び出している
- SP-API通信の重複によるレート制限リスク

確認すべき点:
1. Phase 1の実装状況（scheduled_tasks/sync_inventory_daemon.py:174-185）
2. Phase 2でのSP-API呼び出し（platforms/base/scripts/sync_prices.py:374-395）
3. eBayでのSP-API呼び出し（platforms/ebay/scripts/sync_prices.py:154-172）

参照ドキュメント:
- docs/issues/ISSUE_028_sync_inventory_daemon_sp_api_duplication.md
- README.md（アーキテクチャセクション）

対応手順:
1. Phase 1のキャッシュ更新実装（_collect_all_asins、_update_cache_for_asins）
2. Phase 2のSP-API呼び出し禁止（skip_cache_update=True、auto_fetch_sp_api=False）
3. テスト実行（dry-run）
4. 本番デプロイ
```

---

**作成日:** 2025-12-07
**最終更新:** 2025-12-07
**ステータス:** 🔴 未解決（調査完了、実装待ち）
