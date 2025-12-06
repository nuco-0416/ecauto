# Issue #009: sync_stock_visibility.py の不要なレート制限による処理時間の肥大化

**ステータス**: 🟡 未対応
**発生日**: 2025-11-24
**優先度**: 🟡 中（パフォーマンス改善）
**担当**: 未定
**影響範囲**: 在庫切れ商品の自動非公開処理

---

## 問題の詳細

### 症状

**現象:**
- `sync_stock_visibility.py` の実行が非常に遅い（10,772件で約6時間）
- 30秒でタイムアウトする
- 各出品の処理後に2秒待機している

**具体例:**
```bash
# 30秒でタイムアウト
$ timeout 30 venv/Scripts/python.exe inventory/scripts/sync_stock_visibility.py --platform base --dry-run
Exit code 124  # タイムアウト
```

**処理時間の内訳:**
```
対象出品数: 10,772件
待機時間: 2秒/件
総処理時間: 10,772 × 2秒 = 21,544秒 = 約6時間
```

### 根本原因

**問題のコード（[sync_stock_visibility.py:112](C:\Users\hiroo\Documents\GitHub\ecauto\inventory\scripts\sync_stock_visibility.py#L112)）:**
```python
# 各出品をチェック
for listing in listings:
    self._sync_listing(listing, base_client, dry_run)
    time.sleep(2)  # レート制限対策 ← 問題箇所
```

**誤解されている点:**
1. `sync_stock_visibility.py` は **BASE API** を呼び出している
2. BASE APIにはレート制限が存在しない（またはSP-APIよりも緩い）
3. 2秒待機は **SP-API** のレート制限対策として実装された可能性
4. しかし、このスクリプトはSP-APIを呼び出していない

### 実際の処理フロー

```
1. Master DBから出品一覧を取得（SQLite、ローカル、高速）
   ↓
2. キャッシュから在庫情報を取得（JSONファイル、ローカル、高速）
   ↓
3. BASE APIで商品を更新（BASE API、外部API、レート制限対象？）
   ↓
4. Master DBのlistingsテーブルを更新（SQLite、ローカル、高速）
```

**SP-API呼び出し箇所**: なし

---

## 問題が発覚した経緯

### タイムライン

1. **2025-11-24 19:23** - `fill_missing_cache_detailed.py` で10件の在庫切れASINを検出
2. **推奨アクション** - `sync_stock_visibility.py --platform base` の実行を推奨
3. **実行開始** - DRY RUNモードで実行
4. **30秒後** - タイムアウト、処理が完了しない
5. **原因調査** - コードレビューで2秒待機を発見
6. **処理時間試算** - 10,772件 × 2秒 = 約6時間
7. **BASE API確認** - SP-API呼び出しがないことを確認

### 発見の経緯

```bash
# タイムアウトで実行が完了しない
$ timeout 30 venv/Scripts/python.exe inventory/scripts/sync_stock_visibility.py --platform base --dry-run
Exit code 124

# コードを確認
$ grep -n "time.sleep" inventory/scripts/sync_stock_visibility.py
112:                    time.sleep(2)  # レート制限対策
```

---

## 問題解決のために参照したコード・ドキュメント

### 関連ファイル

#### 1. inventory/scripts/sync_stock_visibility.py (行82-125)

**問題のコード:**
```python
# 各アカウントの出品をループ
for account in accounts:
    account_id = account['id']
    account_name = account['name']

    print(f"\n--- アカウント: {account_name} ({account_id}) ---")

    try:
        # アカウント別の出品一覧を取得
        listings = self.master_db.get_listings_by_account(
            platform=platform,
            account_id=account_id,
            status='listed'  # 出品済みのみ
        )

        print(f"出品数: {len(listings)}件")

        if not listings:
            print("  → 出品なし、スキップ")
            continue

        # BASE APIクライアント作成
        base_client = BaseAPIClient(
            account_id=account_id,
            account_manager=self.account_manager
        )

        # 各出品をチェック
        for listing in listings:
            self._sync_listing(listing, base_client, dry_run)
            time.sleep(2)  # レート制限対策 ← 問題箇所

    except Exception as e:
        print(f"エラー: アカウント {account_id} の処理中にエラー: {e}")
        self.stats['errors'] += 1
```

**問題点:**
- SP-APIを呼び出していないのに2秒待機
- BASE APIのレート制限は不明（調査必要）
- 10,772件で約6時間という非現実的な処理時間

#### 2. platforms/base/core/api_client.py

BASE APIクライアントの実装を確認する必要があります。

**確認すべき点:**
- BASE APIのレート制限の有無
- レート制限がある場合、推奨待機時間
- 実際に待機が必要かどうか

---

## 解決方法

### 設計方針

**段階的アプローチ:**

1. **短期対応（緊急）**: 専用スクリプトの作成
   - 在庫切れ10件だけを処理する専用スクリプト
   - レート制限なし（または最小限）
   - 処理時間: 10件 × 1秒 = 約10秒

2. **中長期対応（推奨）**: sync_stock_visibility.py の改善
   - BASE APIのレート制限を調査
   - 不要な待機を削除、または短縮
   - オプション: `--no-rate-limit` フラグの追加

### Phase 1: 専用スクリプトの作成（短期対応）

**目的**: 在庫切れ10件を即座に処理

**新規ファイル:** `inventory/scripts/update_out_of_stock_visibility.py`

**実装内容:**
```python
def update_visibility_for_asins(asins: list, platform: str = 'base', dry_run: bool = False):
    """
    指定されたASINのvisibilityをhiddenに更新

    レート制限なし（BASE APIは高速処理可能と仮定）
    """
    # 初期化
    master_db = MasterDB()
    cache = AmazonProductCache()
    account_manager = AccountManager()

    # 各ASINを処理
    for asin in asins:
        # 出品情報を取得
        listings = master_db.get_listings_by_asin(asin)

        for listing in listings:
            # BASE APIで更新
            base_client = BaseAPIClient(account_id=listing['account_id'])
            base_client.update_item(
                item_id=listing['platform_item_id'],
                updates={'visible': 0}
            )

            # Master DBも更新
            master_db.update_listing(
                listing_id=listing['id'],
                visibility='hidden'
            )

            # レート制限なし（BASE APIは高速と仮定）
            # time.sleep() なし
```

**使用方法:**
```bash
# レポートファイルから自動取得
python inventory/scripts/update_out_of_stock_visibility.py --platform base --dry-run

# ASINを直接指定
python inventory/scripts/update_out_of_stock_visibility.py \
  --asins B0D3LCSXPG B0FH6746V2 B0CC1F2VSN \
  --platform base \
  --dry-run
```

**処理時間:**
- 10件 × 1秒 = 約10秒（レート制限なし）
- 10件 × 0.5秒 = 約5秒（BASE APIが高速な場合）

### Phase 2: sync_stock_visibility.py の改善（中長期対応）

**目的**: 全件処理でも現実的な処理時間にする

**調査項目:**

1. **BASE APIのレート制限を調査**
   - 公式ドキュメント確認
   - 実測テスト（100件を連続実行）
   - エラーログの確認

2. **レート制限の結果に応じて対応**

   **ケースA: レート制限なし**
   ```python
   # time.sleep(2) を削除
   for listing in listings:
       self._sync_listing(listing, base_client, dry_run)
       # time.sleep(2)  # 削除
   ```
   処理時間: 10,772件 × 0.1秒 = 約18分

   **ケースB: レート制限あり（1秒/件）**
   ```python
   # time.sleep(2) → time.sleep(1) に変更
   for listing in listings:
       self._sync_listing(listing, base_client, dry_run)
       time.sleep(1)  # 2秒 → 1秒
   ```
   処理時間: 10,772件 × 1秒 = 約3時間

   **ケースC: レート制限あり（0.5秒/件）**
   ```python
   # time.sleep(2) → time.sleep(0.5) に変更
   for listing in listings:
       self._sync_listing(listing, base_client, dry_run)
       time.sleep(0.5)  # 2秒 → 0.5秒
   ```
   処理時間: 10,772件 × 0.5秒 = 約1.5時間

3. **オプション機能の追加**
   ```python
   parser.add_argument(
       '--no-rate-limit',
       action='store_true',
       help='レート制限を無視（テスト用）'
   )

   # 使用例
   if not args.no_rate_limit:
       time.sleep(2)
   ```

---

## 期待される効果

### Phase 1（専用スクリプト）の効果

**修正前:**
```
┌─────────────────────────────────────────┐
│ sync_stock_visibility.py使用            │
│ - 処理時間: 約6時間（10,772件）         │
│ - 10件だけでも: 約20秒                  │
│ - タイムアウト: 30秒で停止              │
└─────────────────────────────────────────┘
```

**修正後:**
```
┌─────────────────────────────────────────┐
│ update_out_of_stock_visibility.py使用   │
│ - 処理時間: 約10秒（10件）              │
│ - レート制限: なし                      │
│ - タイムアウト: なし                    │
└─────────────────────────────────────────┘
```

### Phase 2（sync_stock_visibility改善）の効果

**修正前:**
```
┌─────────────────────────────────────────┐
│ 現行                                    │
│ - 処理時間: 約6時間（10,772件 × 2秒）   │
│ - レート制限: 2秒/件（過剰？）          │
└─────────────────────────────────────────┘
```

**修正後（レート制限なし）:**
```
┌─────────────────────────────────────────┐
│ 改善版                                  │
│ - 処理時間: 約18分（10,772件 × 0.1秒）  │
│ - レート制限: なし                      │
│ - 改善率: 🟢 95%短縮                    │
└─────────────────────────────────────────┘
```

**修正後（レート制限1秒）:**
```
┌─────────────────────────────────────────┐
│ 改善版                                  │
│ - 処理時間: 約3時間（10,772件 × 1秒）   │
│ - レート制限: 1秒/件                    │
│ - 改善率: 🟡 50%短縮                    │
└─────────────────────────────────────────┘
```

---

## リスクと対策

### リスク1: BASE APIのレート制限超過

**懸念:**
- レート制限を削除した結果、BASE APIから429エラーが返る
- 処理が失敗する

**対策:**
- ✅ Phase 1で少数件（10件）をテスト実行
- ✅ エラーログを監視
- ✅ 429エラーが発生した場合は待機時間を追加

### リスク2: 処理の信頼性低下

**懸念:**
- 高速処理でエラーハンドリングが追いつかない
- データ不整合が発生

**対策:**
- ✅ DRY RUNで動作確認
- ✅ エラー時は詳細ログを出力
- ✅ トランザクション処理の実装

---

## 実装計画

### タイムライン

| Phase | 作業内容 | 所要時間 | 優先度 |
|-------|---------|---------|-------|
| 1 | 専用スクリプト作成 | 1時間 | 🔴 緊急 |
| 2 | BASE APIレート制限調査 | 2時間 | 🟡 推奨 |
| 3 | sync_stock_visibility改善 | 2時間 | 🟡 推奨 |
| 4 | テスト実行 | 1時間 | 必須 |
| **合計** | **6時間** | |

### Phase別詳細

#### Phase 1: 専用スクリプト作成（最優先）

**目的:** 在庫切れ10件を即座に処理

**作業内容:**
1. `update_out_of_stock_visibility.py` の作成
2. レポートファイル自動読み込み機能
3. DRY RUNテスト
4. 本番実行

**テスト:**
```bash
# DRY RUN
python inventory/scripts/update_out_of_stock_visibility.py --dry-run

# 本番実行
python inventory/scripts/update_out_of_stock_visibility.py --platform base
```

**成功基準:**
- 10件全てが更新される
- 処理時間が30秒以内
- エラーが発生しない

**所要時間:** 1時間

#### Phase 2: BASE APIレート制限調査

**作業内容:**

1. **公式ドキュメント確認**
   - BASE APIの公式ドキュメントを検索
   - レート制限の記載を確認

2. **実測テスト**
   ```python
   # 100件を連続実行してレート制限を調査
   for i in range(100):
       try:
           base_client.update_item(item_id=test_item_id, updates={'visible': 0})
           print(f"[{i+1}/100] 成功")
       except Exception as e:
           print(f"[{i+1}/100] エラー: {e}")
           break
   ```

3. **結果分析**
   - 429エラーが発生した場合: レート制限あり
   - 全件成功した場合: レート制限なし（または十分緩い）

**所要時間:** 2時間

#### Phase 3: sync_stock_visibility改善

**作業内容:**

1. **Phase 2の結果に応じて修正**
   - レート制限なし → `time.sleep(2)` 削除
   - レート制限あり → 適切な待機時間に変更

2. **オプション機能追加**
   ```python
   parser.add_argument(
       '--rate-limit',
       type=float,
       default=None,
       help='レート制限（秒/件）。デフォルトは自動判定'
   )
   ```

3. **エラーハンドリング強化**
   - 429エラー時のリトライ処理
   - バックオフアルゴリズムの実装

**所要時間:** 2時間

#### Phase 4: テスト実行

**テストケース:**

1. **TC-1: 少数件テスト（10件）**
   ```bash
   python inventory/scripts/sync_stock_visibility.py --dry-run --max-items 10
   ```
   - 処理時間: 10秒以内
   - エラー: なし

2. **TC-2: 中規模テスト（100件）**
   ```bash
   python inventory/scripts/sync_stock_visibility.py --dry-run --max-items 100
   ```
   - 処理時間: 2分以内
   - エラー: なし

3. **TC-3: 全件テスト（10,772件）**
   ```bash
   python inventory/scripts/sync_stock_visibility.py --dry-run
   ```
   - 処理時間: 30分以内（レート制限なしの場合）
   - エラー: なし

**所要時間:** 1時間

---

## 関連Issue

なし

---

## 次回の改善提案

1. **BASE API統合レート制限管理**
   - 全スクリプトで共通のレート制限管理クラスを実装
   - 設定ファイルで一元管理

2. **並列処理の検討**
   - 複数アカウントを並列処理
   - 処理時間をさらに短縮

3. **リアルタイム監視**
   - 在庫切れ検知時に自動で非公開設定
   - `sync_inventory_daemon.py` に統合

---

**作成日**: 2025-11-24
**最終更新**: 2025-11-24
**作成者**: Claude Code
**ステータス**: 🟡 未対応
**優先度**: 🟡 中（パフォーマンス改善）
