# ISSUE #029: キャッシュシステムの削除とワークフロー改善

**作成日**: 2025-12-07
**優先度**: 🔴 High
**ステータス**: 🚧 作業中
**完了日**: -

---

## 📋 概要

プロジェクト内に2つの商品情報管理システム（productsテーブルとキャッシュファイル）が共存しており、データの不整合やエラーが発生している。
また、アカウント間の商品展開ワークフローに非効率な部分があり、改善が必要。

### 問題の経緯

`upload_queueへの商品追加処理`において、以下の問題が発生：

1. **キャッシュ起因のエラー**: 1000件中996件が「商品情報の取得に失敗」
2. **非効率な商品展開**: アカウント1に12,000件の既存出品があるにもかかわらず、最初の1000件のみ取得し、不足分をsourcingから取得
3. **一時スクリプトの乱立**: 同じような処理のために一時スクリプトを都度作成

---

## 🔍 問題の詳細

### 問題1: キャッシュシステムとproductsテーブルの重複

#### 現状

- **productsテーブル** (SQLite DB)
  - 商品情報を完全に保持: ASIN、タイトル、説明、カテゴリ、ブランド、画像、価格、在庫状況
  - 登録数: 18,020件
  - ファイル: [inventory/core/master_db.py](../../inventory/core/master_db.py)

- **キャッシュシステム** (JSONファイル)
  - ディレクトリ: `inventory/data/cache/amazon_products/`
  - ファイル数: 17,544個
  - **productsテーブルと同じ情報を保持**（完全に重複）
  - ファイル: [inventory/core/cache_manager.py](../../inventory/core/cache_manager.py)

#### 問題のあるコード

**ファイル**: [inventory/scripts/add_new_products.py:94-104](../../inventory/scripts/add_new_products.py#L94-L104)

```python
def fetch_product_info_from_sp_api(...):
    # キャッシュから取得を試みる
    cache = AmazonProductCache()
    cached_data = cache.get_product(asin)

    # キャッシュに価格情報も含まれている場合はそれを返す
    if cached_data and cached_data.get('amazon_price_jpy') is not None:
        return cached_data

    # SP-APIから取得（キャッシュがないか、価格情報がない場合）
    if use_sp_api:
        # SP-APIから取得...
```

**問題点**:
1. まずキャッシュから取得を試みる
2. キャッシュに価格情報がない場合、SP-APIを使用しない限り失敗
3. **productsテーブルには価格情報があるのに、使用されていない**

#### エラーの実例

```
実行結果（account3向け）
成功: 0件
スキップ: 4件
失敗: 996件
総計: 1000件

エラー: ほぼすべてのASINで「商品情報の取得に失敗」
```

#### 根本原因

- キャッシュとproductsテーブルの役割が重複
- データの不整合（キャッシュに価格情報がない場合がある）
- 保守性の低下（2つのシステムを維持する必要がある）

---

### 問題2: アカウント間商品展開の非効率なロジック

#### 現状の動作

**ファイル**: 一時スクリプト `temp_extract_asins_for_account2.py`, `temp_extract_asins_for_account3.py`

```python
# アカウント1の商品から最初の1000件のみ取得
SELECT DISTINCT asin
FROM listings
WHERE platform = 'base'
  AND account_id = 'base_account_1'
LIMIT 1000
```

**問題点**:
1. アカウント1には12,000件の既存出品が存在
2. しかし、最初の1000件のみ取得
3. 不足分（account2: 522件、account3: 50件）をsourcingから取得しようとする
   - sourcingからの取得はSP-API使用で時間がかかる
   - 既存データを活用すれば即座に展開可能

#### 改善案

```python
# 改善後: アカウント1の全商品から取得
# 優先順位:
# 1. アカウント1の既存出品（12,000件）から取得
# 2. 不足分のみsourcingから取得
```

---

### 問題3: 一時スクリプトの乱立

#### 現状

以下のような一時スクリプトが都度作成されている：

- `temp_extract_asins_for_account2.py`
- `temp_extract_asins_for_account3.py`
- `temp_copy_listings_from_products.py`

**問題点**:
- 同じような処理のために毎回スクリプトを作成
- プロジェクトディレクトリが煩雑になる
- 保守性が低い

**改善案**:
- 汎用的なツールとして `shared/utils` に配置
- 再利用可能な形で実装

---

## 💡 解決策

### 解決策1: キャッシュシステムの削除

#### 実施内容

1. **キャッシュ依存の除去**
   - `add_new_products.py`: キャッシュではなくproductsテーブルから取得
   - `sync_prices.py`: 同様の修正
   - その他のスクリプト: キャッシュ使用箇所を特定して修正

2. **キャッシュシステムの削除**
   - `inventory/core/cache_manager.py` を削除（または非推奨化）
   - キャッシュディレクトリ `inventory/data/cache/amazon_products/` を削除
   - README.mdからキャッシュに関する記述を削除

#### 期待される効果

- ✅ データの一貫性が向上
- ✅ 保守性が向上（単一のデータソース）
- ✅ エラーが解消（価格情報の不整合がなくなる）
- ✅ ディスク容量の節約（17,544個のJSONファイルを削除）

---

### 解決策2: ASIN抽出ツールの作成

#### ツール仕様

**ファイル**: `shared/utils/extract_asins_for_account.py`

```python
#!/usr/bin/env python3
"""
アカウント間でASINリストを抽出するツール

使用例:
  # アカウント1からアカウント2向けにASINを抽出（1000件）
  python shared/utils/extract_asins_for_account.py \
    --source-account base_account_1 \
    --target-account base_account_2 \
    --limit 1000 \
    --output asins_for_account2.txt

  # 全件抽出
  python shared/utils/extract_asins_for_account.py \
    --source-account base_account_1 \
    --target-account base_account_3 \
    --output asins_for_account3.txt
"""
```

**機能**:
- ソースアカウントの既存出品からASINを抽出
- ターゲットアカウントに未登録のASINのみ抽出
- 件数制限、出力ファイル指定に対応

---

### 解決策3: アカウント間商品展開ロジックの改善

#### 改善内容

**現在の処理フロー**:
```
1. アカウント1の商品から最初の1000件のみ取得
2. 不足分をsourcingから取得（SP-API使用、時間がかかる）
```

**改善後の処理フロー**:
```
1. アカウント1の全商品（12,000件）から優先的に取得
2. それでも不足する場合のみsourcingから取得
```

#### 実装方法

**オプション1**: 既存スクリプトの修正
- `temp_extract_asins_for_account*.py` の `LIMIT 1000` を削除

**オプション2**: 新ツールの使用（解決策2）
- 汎用的な `extract_asins_for_account.py` を使用
- LIMITを指定せずに実行

---

## 📝 実装計画

### フェーズ1: バックアップと準備

- [ ] マスタDBのバックアップ作成
- [ ] 影響範囲の調査（キャッシュを使用しているスクリプト一覧）

### フェーズ2: キャッシュシステムの削除

- [ ] `add_new_products.py` の修正（キャッシュ → productsテーブル）
- [ ] `sync_prices.py` の修正（該当する場合）
- [ ] その他のスクリプトの修正
- [ ] テスト実行（本番スクリプトで直接テスト）

### フェーズ3: ASIN抽出ツールの作成

- [ ] `shared/utils/extract_asins_for_account.py` の実装
- [ ] テスト実行
- [ ] 一時スクリプトの削除

### フェーズ4: アカウント間商品展開ロジックの改善

- [ ] 抽出ロジックの修正（LIMIT削除、優先順位設定）
- [ ] テスト実行
- [ ] ドキュメント更新

### フェーズ5: クリーンアップ

- [ ] キャッシュディレクトリの削除
- [ ] `cache_manager.py` の削除または非推奨化
- [ ] README.md の更新
- [ ] ISSUE_029 の完了マーク

---

## ⚠️ リスクと注意事項

### リスク

1. **既存スクリプトの互換性**
   - キャッシュに依存しているスクリプトが他にも存在する可能性
   - 影響範囲の調査が重要

2. **パフォーマンス**
   - ファイルベースのキャッシュとSQLiteの性能差
   - ただし、SQLiteの方が一般的に高速（インデックス、クエリ最適化）

3. **データ整合性**
   - キャッシュとproductsテーブルで異なるデータが存在する場合
   - productsテーブルを信頼できる情報源（Single Source of Truth）とする

### 対策

- 各フェーズでバックアップを作成
- テスト実行（--dry-run, --max-items）で動作確認
- エラーが発生した場合の巻き戻し手順を準備

---

## 📊 影響範囲

### 修正が必要なファイル

1. **inventory/scripts/add_new_products.py**
   - `fetch_product_info_from_sp_api()` 関数
   - キャッシュ使用箇所の削除

2. **platforms/base/scripts/sync_prices.py**
   - キャッシュ使用の有無を確認
   - 該当する場合は修正

3. **その他のスクリプト**
   - `cache_manager` をインポートしているファイルをすべて確認

### 新規作成ファイル

1. **shared/utils/extract_asins_for_account.py**
   - アカウント間ASIN抽出ツール

### 削除予定ファイル

1. **inventory/core/cache_manager.py** (非推奨化または削除)
2. **inventory/data/cache/amazon_products/** (ディレクトリごと削除)
3. **一時スクリプト**
   - `temp_extract_asins_for_account2.py`
   - `temp_extract_asins_for_account3.py`
   - `temp_copy_listings_from_products.py`

---

## 📈 期待される改善効果

### 定量的効果

- **エラー率の改善**: 996/1000 → 0/1000
- **ディスク容量**: 17,544個のJSONファイルを削除（推定数十MB）
- **保守コスト**: 2つのシステム → 1つのシステム（-50%）

### 定性的効果

- ✅ データの一貫性が向上
- ✅ デバッグが容易に
- ✅ コードの可読性が向上
- ✅ 新規開発者のオンボーディングが簡単に

---

## 🔗 関連リンク

- [README.md - Amazon情報キャッシュ](../../README.md#L11)
- [inventory/core/master_db.py](../../inventory/core/master_db.py)
- [inventory/core/cache_manager.py](../../inventory/core/cache_manager.py)
- [playbooks/upload_queueへの商品追加処理.md](../../playbooks/upload_queueへの商品追加処理.md)

---

## 📅 進捗ログ

### 2025-12-07

- ✅ ISSUE_029 ドキュメント作成
- ✅ フェーズ1: バックアップと準備
  - マスタDBバックアップ作成 (`master_backup_20251207_063242.db`)
  - 影響範囲調査完了（2つの主要ファイルを特定）
- ✅ フェーズ2: キャッシュシステムの削除
  - `inventory/scripts/add_new_products.py` の修正完了
    - `AmazonProductCache` インポート削除
    - `fetch_product_info_from_sp_api()` 関数をproductsテーブル優先に変更
    - 禁止商品チェック部分も修正
    - バックアップ作成: `add_new_products.py.backup_20251207_issue029`
  - `platforms/base/scripts/sync_prices.py` の確認
    - キャッシュ使用を確認（マスタDBも更新している）
    - 今後の修正対象として記録
- ✅ フェーズ3: ASIN抽出ツールの作成
  - `shared/utils/extract_asins_for_account.py` を作成
  - 汎用的なツールとして実装
  - 一時スクリプトを削除
- ⏭️ フェーズ4: アカウント間商品展開ロジックの改善
  - 新しいツールを使用することで実現
  - プレイブックの更新が必要
- ⏭️ フェーズ5: クリーンアップ
  - キャッシュディレクトリの削除（将来的に実施）
  - `cache_manager.py` の非推奨化（将来的に実施）
  - README.md の更新（将来的に実施）

### 2025-12-08

- ✅ `inventory/scripts/sync_stock_visibility.py` の修正完了
  - **問題**: sync_inventory_daemon.py 実行時に以下のエラーが発生
    ```
    ERROR - [SKIP] B0F18FNLVD - キャッシュの在庫情報が欠損しています（API取得エラーの可能性）
    ```
  - **原因**: `_sync_listing()` メソッドがキャッシュファイルを優先的に参照しており、キャッシュに `in_stock` フィールドがない場合にスキップしていた
  - **修正内容**:
    | 変更箇所 | 内容 |
    |---------|------|
    | インポート削除 | `AmazonProductCache`, `AmazonSPAPIClient`, `os`, `load_dotenv` |
    | 初期化処理 | `self.cache`, SP-APIクライアント初期化を削除 |
    | `_sync_listing()` | キャッシュ参照ロジック（約30行）をマスタDB直接参照（5行）に簡略化 |
    | `sync_all_listings()` | キャッシュ欠損チェック、キャッシュ補完処理（約65行）を削除 |
    | `_print_summary()` | キャッシュ関連統計を `no_stock_info` に置換 |
  - **テスト結果** (DRY RUN):
    ```
    処理した商品数: 4866件
      - 在庫あり: 4801件
      - 在庫切れ: 65件
    エラー: 0件
    ```
  - バックアップ作成: `sync_stock_visibility.py.backup_20251208_issue029`

### 次のステップ

1. ~~**本番環境でのテスト**: 修正した`add_new_products.py`を実際のASINリストでテスト~~
2. **プレイブックの更新**: 新しいツールと手順を反映
3. **sync_prices.py の修正**: キャッシュをproductsテーブルに統一
4. **キャッシュシステムの完全削除**: テスト完了後に実施
5. **sync_inventory_daemon.py の本番テスト**: 修正した`sync_stock_visibility.py`の動作確認
