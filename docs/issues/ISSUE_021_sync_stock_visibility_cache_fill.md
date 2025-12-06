# ISSUE #021: sync_stock_visibility大量WARNログ問題とキャッシュ補完機能実装

**日付:** 2025-11-29
**ステータス:** ✅ 解決済み（次回実行時に動作確認予定）
**優先度:** 高（ログの可読性、在庫同期の信頼性）
**関連ファイル:**
- `inventory/scripts/sync_stock_visibility.py`
- `scheduled_tasks/sync_inventory_daemon.py`

---

## 📋 問題の概要

### 症状

sync_inventory_daemon.py実行時に、大量のWARNログが出力される問題：

```
2025-11-28 21:14:25 [INFO] inventory.scripts.sync_stock_visibility:   [WARN] B09BHQZ98J - キャッシュが存在しません。Master DBから取得を試みます。
2025-11-28 21:14:27 [INFO] inventory.scripts.sync_stock_visibility:   [WARN] B0DPL7Q5WP - キャッシュが存在しません。Master DBから取得を試みます。
（580件の大量ログ...）
```

### ユーザーの想定

- これはREADMEのルート1（商品ソーシング）で登録された、まだ出品完了していないASIN
- 未出品ASINでもProduct/listingテーブル登録時点で商品情報が揃っているべき
- 商品情報が見つからないエラーが出るべきではない

---

## 🔍 調査結果

### 1. デバッグスクリプトによる実態確認

調査対象ASIN（B09BHQZ98J, B0DPL7Q5WP）の実際の状態：

```
■ ProductsテーブルとListingsテーブルの状態:
  - ✅ Productsテーブルに商品情報が存在
  - ✅ Listingsテーブルに登録済み（status='listed' = 既に出品済み）
  - ✅ amazon_in_stockの情報も正しく保存
  - ❌ キャッシュファイルが存在しない

■ 全体の状況:
  - Status別のListing数:
    - listed: 12,829件（出品済み）
    - pending: 3,803件（未出品）
  - status='listed'でキャッシュが存在しない商品数: 580/12,829件（約4.5%）
```

**結論:** 未出品ASINではなく、**既に出品済みだがキャッシュが存在しない商品**が原因。

---

## 💡 根本原因の分析

### ①キャッシュ欠損の原因

キャッシュファイルが存在しない理由：

1. **最近出品された商品**
   - 出品後、まだ一度も価格同期（sync_prices.py）が実行されていない

2. **SP-API取得時のエラー**
   - 価格同期時にSP-APIエラーが発生し、キャッシュ作成がスキップされた
   - sync_prices.pyの処理フロー:
     ```python
     if price_info is None or price_info.get('price') is None:
         # SP-APIエラーの場合はスキップ
         continue
     ```

### ②sync_stock_visibility.pyの設計意図と問題点

**設計意図:**
- キャッシュファイルを優先的に使用
- キャッシュが存在しない場合、フォールバックとしてMaster DBの値を使用
- この場合、`[WARN]`ログを出力

**問題点:**
- キャッシュが存在しないことを「例外的な状態」として扱っている
- 580件もの商品でキャッシュが欠損しているため、大量のWARNログが発生
- ログの可読性が低下し、本当に重要なエラーが埋もれる

### ③データの整合性は保たれている

✅ **重要:** 商品情報（Productsテーブル）には`amazon_in_stock`が正しく保存されており、sync_stock_visibility.pyはフォールバックとしてMaster DBの値を使用しているため、**機能的には正常に動作している。**

---

## 🎯 解決策: 提案E（処理完了時のキャッシュ一括補完）

### アーキテクチャの選択

複数の提案を検討した結果、**提案E**を採用：

| 提案 | 内容 | メリット | デメリット |
|------|------|----------|------------|
| A | 処理開始時に一括補完 | 確実性が高い | 処理開始時に時間がかかる |
| B | 処理完了時に補完 | 今回の処理が速い | 今回はMaster DBを使用 |
| C | 20件溜まったら補完 | リアルタイム性が高い | 実装が複雑 |
| D | リアルタイム個別補完 | タイムラグ最小 | 処理時間が長くなる |
| **E** | **処理完了時一括補完** | **バランスが良い** | 今回はMaster DB使用 |

### 提案Eの詳細

```python
def sync_all_listings(self, platform: str = 'base', dry_run: bool = False):
    # キャッシュ欠損ASINを収集するリスト
    missing_cache_asins = []

    # 各出品をチェック
    for listing in listings:
        asin = listing['asin']

        # キャッシュ欠損をチェック
        cache_file = self.cache.cache_dir / f'{asin}.json'
        if not cache_file.exists():
            missing_cache_asins.append(asin)
            logger.debug(f"  [CACHE MISS] {asin} - Master DBフォールバック")

        # 処理を継続（Master DBフォールバック）
        self._sync_listing(listing, base_client, dry_run)

    # ━━━ 処理完了後、欠損キャッシュを一括補完 ━━━
    if missing_cache_asins and not dry_run and self.sp_api_available:
        # 重複を削除
        missing_cache_asins = list(set(missing_cache_asins))

        logger.info("━" * 70)
        logger.info("キャッシュ補完処理（次回の処理高速化のため）")
        logger.info("━" * 70)
        logger.info(f"欠損キャッシュ: {len(missing_cache_asins)}件")

        # SP-APIバッチで一括取得
        batch_results = self.sp_api_client.get_prices_batch(
            missing_cache_asins,
            batch_size=20
        )

        # キャッシュに保存 + Master DB更新
        for asin, price_info in batch_results.items():
            if price_info and price_info.get('price') is not None:
                self.cache.set_product(asin, price_info)
                self.master_db.update_amazon_info(
                    asin=asin,
                    amazon_price_jpy=int(price_info['price']),
                    amazon_in_stock=price_info.get('in_stock', False)
                )
```

---

## 🛠️ 実装内容

### 1. SP-APIクライアントの初期化

`sync_stock_visibility.py:50-65`

```python
# SP-APIクライアント初期化（キャッシュ補完用）
load_dotenv(project_root / '.env')
try:
    sp_api_credentials = {
        'refresh_token': os.getenv('REFRESH_TOKEN'),
        'lwa_app_id': os.getenv('LWA_APP_ID'),
        'lwa_client_secret': os.getenv('LWA_CLIENT_SECRET')
    }
    self.sp_api_client = AmazonSPAPIClient(sp_api_credentials)
    self.sp_api_available = True
except Exception as e:
    logger.warning(f"SP-APIクライアント初期化失敗: {e}")
    self.sp_api_client = None
    self.sp_api_available = False
```

### 2. キャッシュ欠損ASINの収集

`sync_stock_visibility.py:114-121`

```python
# 各出品をチェック
for listing in listings:
    asin = listing['asin']

    # キャッシュ欠損をチェック
    cache_file = self.cache.cache_dir / f'{asin}.json'
    if not cache_file.exists():
        missing_cache_asins.append(asin)
        logger.debug(f"  [CACHE MISS] {asin} - Master DBフォールバック")

    self._sync_listing(listing, base_client, dry_run)
```

### 3. 処理完了後のキャッシュ一括補完

`sync_stock_visibility.py:134-197`

- SP-APIバッチで20件ずつ取得
- キャッシュに保存
- Master DBも最新情報で更新
- 成功/失敗の統計を記録

### 4. ログレベルの調整

`sync_stock_visibility.py:179`

```python
# 変更前:
logger.info(f"  [WARN] {asin} - キャッシュが存在しません。Master DBから取得を試みます。")

# 変更後:
logger.debug(f"  [FALLBACK] {asin} - Master DBから在庫情報を使用")
```

### 5. 統計情報の拡張

`sync_stock_visibility.py:254-255`

```python
if self.stats['cache_fill_success'] > 0 or self.stats['cache_fill_failed'] > 0:
    logger.info(f"  - キャッシュ補完（成功/失敗）: {self.stats['cache_fill_success']}/{self.stats['cache_fill_failed']}件")
```

---

## 📊 期待される効果

### Before（実装前）
```
2025-11-28 21:14:25 [INFO] inventory.scripts.sync_stock_visibility:   [WARN] B09BHQZ98J - キャッシュが存在しません。
2025-11-28 21:14:27 [INFO] inventory.scripts.sync_stock_visibility:   [WARN] B0DPL7Q5WP - キャッシュが存在しません。
（580件の大量WARNログ...）
```

### After（実装後）
```
2025-11-29 00:00:00 [DEBUG] inventory.scripts.sync_stock_visibility:   [CACHE MISS] B09BHQZ98J - Master DBフォールバック
2025-11-29 00:00:02 [DEBUG] inventory.scripts.sync_stock_visibility:   [CACHE MISS] B0DPL7Q5WP - Master DBフォールバック

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
キャッシュ補完処理（次回の処理高速化のため）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
欠損キャッシュ: 580件
SP-APIバッチで一括取得中...
推定時間: 約6.0分 (29バッチ)

補完完了: 成功 580件 / 失敗 0件
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

======================================================================
処理結果サマリー
======================================================================
処理した商品数: 12829件
  - 在庫あり: 12249件
  - 在庫切れ: 580件

キャッシュ状態:
  - キャッシュ欠損（Master DB使用）: 580件
  - キャッシュ不完全（スキップ）: 0件
  - キャッシュ補完（成功/失敗）: 580/0件    ← ★追加

更新した商品数:
  - 非公開に変更: 580件
  - 公開に変更: 0件
```

---

## ✅ 動作確認方法

### 手動テスト

```bash
# 在庫同期を手動実行（本番モード）
venv\Scripts\python.exe inventory\scripts\sync_inventory.py --platform base
```

### ログ確認（PowerShell）

```powershell
# キャッシュ補完のログを検索
Select-String -Path logs\sync_inventory.log -Pattern "キャッシュ補完"

# 処理結果サマリーを表示
$lines = Get-Content logs\sync_inventory.log
$index = -1
for ($i = $lines.Count - 1; $i -ge 0; $i--) {
    if ($lines[$i] -match "処理結果サマリー") {
        $index = $i
        break
    }
}
if ($index -ge 0) {
    $lines[$index..([Math]::Min($index + 30, $lines.Count - 1))]
}
```

### 確認ポイント

1. ✅ 「キャッシュ補完処理」のログが出力される
2. ✅ 「補完完了: 成功 XXX件 / 失敗 XXX件」が表示される
3. ✅ 処理結果サマリーに「キャッシュ補完（成功/失敗）: XXX/XXX件」が表示される
4. ✅ 次回実行時に、キャッシュ欠損件数が0件になる

---

## 📈 運用シナリオ

### ケース1: 通常運用（キャッシュ完備）
```
在庫同期: 12,829件 → 約4時間（キャッシュヒット100%）
キャッシュ補完: スキップ（欠損0件）
```

### ケース2: 初回実行（キャッシュ欠損580件）
```
在庫同期: 12,829件 → 約4時間（Master DBフォールバック580件）
キャッシュ補完: 580件 → 約6分
総所要時間: 約4.1時間

次回以降: キャッシュヒット100%
```

### ケース3: SP-APIエラーで一部キャッシュ欠損（50件）
```
価格同期: SP-APIエラーで50件のキャッシュ作成失敗
↓
在庫同期: 12,829件 → Master DBフォールバック50件
キャッシュ補完: 50件 → 約30秒
↓
次回の価格同期: キャッシュ完備
```

---

## 🔄 次回実行時の確認事項

- [ ] sync_inventory_daemon.pyが自動実行される（3時間ごと）
- [ ] 「キャッシュ補完処理」のログが出力される
- [ ] 580件のキャッシュが正常に作成される
- [ ] 次回実行時にWARNログが消滅する
- [ ] キャッシュヒット率が100%になる

---

## 📝 備考

### タイムラグについて

- 今回の在庫同期: Master DBの情報を使用（最後にSP-APIで取得した情報）
- 処理完了後: SP-APIで最新情報を取得してキャッシュ作成
- 次回以降: 最新のキャッシュを使用

このアーキテクチャにより、ビジネス上のリスクを最小化しつつ、効率的なキャッシュ補完を実現。

### ビジネス要件との整合性

✅ 在庫状況の更新はビジネス上クリティカル
✅ 例外が発生してもスルーしない（Master DBフォールバック + 補完）
✅ タイムラグを最小化（処理完了直後に補完）
✅ エラー時も処理を継続（堅牢性）

---

**作成日:** 2025-11-29
**最終更新:** 2025-11-29
**ステータス:** ✅ 実装完了（次回実行時に動作確認予定）
