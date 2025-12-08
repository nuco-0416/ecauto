# BASEへの商品追加（最適化版プロンプト）

## 📋 要件
- **対象アカウント**: BASE アカウント2（`base_account_2`）/ アカウント3（`base_account_3`）
- **追加件数**: 
　**upload_queue**テーブル（出品キュー）の登録件数が以下とする
　アカウント2 = 1000件、アカウント3 = 1000件

---

## 🗂️ システム構成（事前情報）

### データベーススキーマ

#### 1. **products**テーブル（商品マスタ）
- **主キー**: `asin`
- **重要フィールド**: `title_ja`, `amazon_price_jpy`, `amazon_in_stock`

#### 2. **listings**テーブル（出品情報）
- **主キー**: `id`
- **UNIQUE制約**: `(asin, platform, account_id)` - 同一アカウント内で同じASINは1つのみ
- **重要フィールド**:
  - `asin`, `platform`, `account_id`
  - `status`: `'pending'`（未出品）, `'queued'`（キュー待ち）, `'listed'`（出品済み）
  - `selling_price`, `in_stock_quantity`

#### 3. **upload_queue**テーブル（出品キュー）
- **主キー**: `id`
- **UNIQUE制約**: `(asin, platform, account_id)` - 同一アカウント内で同じASINは1つのみキューに追加可能
- **重要フィールド**: `asin`, `platform`, `account_id`, `scheduled_time`, `status`

#### 4. **sourcing_candidates**テーブル（ソーシング候補）
- **場所**: `sourcing/data/sourcing.db`
- **重要フィールド**: `asin`, `imported_at`（master.dbへの連携済み日時、NULLなら未連携）

---

## 🔧 使用するスクリプト（事前情報）

### ⚡ 処理フロー（重要：この順序で実行すること）

1. **【最優先】パターン1を実行** → `status='pending'`の未出品商品をキューに追加（最速）
2. **【パターン1で不足する場合】パターン1.5を実行** → 他アカウントの出品済み商品を展開（高速）
3. **【パターン1・1.5で不足する場合のみ】パターン2を実行** → Sourcing候補から新規追加（時間がかかる）

---

### パターン1: Master DB（productsテーブル）から既存の未出品商品を追加 ⭐ **【最優先・必ず最初に実行】**

**スクリプト**: `scheduler/scripts/add_pending_to_queue.py`

**対象**:
- **productsテーブルに既に登録済み**の商品
- **listingsテーブルで`status='pending'`**（未出品）の商品
- **upload_queueに未登録**の商品

**処理時間**: ⚡ **非常に高速**（数秒〜数十秒）

**主な機能**:
- ✅ Master DBから既存の未出品商品を抽出
- ✅ アカウント別に自動振り分け
- ✅ 時間分散スケジューリング（6:00〜23:00 JST）
- ✅ 1日1000件上限に対応
- ✅ upload_queueへの追加

**実行形式**:
```powershell
# DRY RUN（確認のみ）
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' scheduler/scripts/add_pending_to_queue.py --dry-run" 2>&1 | Select-Object -Last 100

# 本番実行
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' scheduler/scripts/add_pending_to_queue.py --yes" 2>&1 | Select-Object -Last 50
```

**重要なオプション**:
- `--dry-run`: DRY RUNモード（確認のみ、実際には追加しない）
- `--yes`: 確認をスキップして自動実行
- `--daily-limit`: 1日あたりの出品上限（デフォルト: 1000）
- `--start-date`: 開始日時（デフォルト: 翌日6:00）

**⚠️ 前提条件**:
- 商品が既に**productsテーブルに登録済み**であること
- listings テーブルで`status='pending'`（未出品）であること

**このパターンを使用すべき理由**:
- ✅ SP-API呼び出しが不要なため、**処理が非常に高速**
- ✅ 既存の商品情報を活用できる
- ✅ 禁止商品チェック済みの商品のみが対象

---

### パターン1.5: 他アカウントの出品済み商品を別アカウントに展開 🔄 **【パターン1で不足する場合に実行】**

**対象**:
- **他のアカウント（例: base_account_1）で既に出品済み**の商品
- **対象アカウント（例: base_account_3）には未出品**の商品
- **productsテーブルに登録済み**の商品

**処理時間**: ⚡ **高速**（数十秒〜数分）

**2つのアプローチ**:

#### 🔧 **アプローチA: 専用ツール使用（推奨）** ← **キャッシュTTL期限切れ問題を回避**

専用ツールを使ってproductsテーブルから直接listingsにコピーします。

**特徴**:
- ✅ キャッシュファイル（JSON）のTTL期限切れ問題を完全に回避
- ✅ productsテーブルから直接取得するため確実
- ✅ SP-API呼び出しなし
- ✅ 禁止商品チェック済みの商品のみが対象

**ステップ1: ASIN抽出ツールで対象ASINリストを作成**

```powershell
# base_account_1からbase_account_3に展開可能なASINを1000件抽出
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' shared/utils/extract_cross_account_asins.py --source-account base_account_1 --target-account base_account_3 --platform base --limit 1000 --output asins_for_account3.txt"
```

**⚠️ 不足した場合の追加抽出**:

最初の1000件で不足する場合、**ソースアカウントの残りの出品から追加で抽出**できます：

```powershell
# 追加で500件抽出（offset=1000で2回目の抽出）
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' shared/utils/extract_cross_account_asins.py --source-account base_account_1 --target-account base_account_3 --platform base --limit 500 --offset 1000 --output asins_for_account3_additional.txt"

# または、最初から多めに抽出
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' shared/utils/extract_cross_account_asins.py --source-account base_account_1 --target-account base_account_3 --platform base --limit 5000 --output asins_for_account3.txt"
```

**重要**: ソースアカウント（例: base_account_1）に12,000件の出品がある場合、最初の1000件で不足しても、**残り11,000件から追加で充当できます**。Sourcing候補から取得する前に、まずソースアカウントの残りの出品を活用してください。

**ステップ2: productsテーブルから直接listingsにコピー**

```powershell
# DRY RUNで確認
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' shared/utils/copy_products_to_listings.py --asin-file asins_for_account3.txt --platform base --account-id base_account_3 --dry-run"

# 本番実行
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' shared/utils/copy_products_to_listings.py --asin-file asins_for_account3.txt --platform base --account-id base_account_3"
```

**オプション**:
- `--asin-file`: ASINリストファイルパス
- `--platform`: プラットフォーム名（base/mercari/yahoo/ebay）
- `--account-id`: 対象アカウントID
- `--markup-rate`: 掛け率（デフォルト: 1.3）
- `--dry-run`: DRY RUNモード
- `--daily-limit`: 1日あたりの上限（デフォルト: 1000）
- `--hourly-limit`: 1時間あたりの上限（デフォルト: 100）

---

#### 🔄 **アプローチB: add_new_products.py使用** ← **キャッシュTTL期限切れに注意**

既存のadd_new_products.pyスクリプトを使用します。

**⚠️ キャッシュTTL期限切れ問題**:
- キャッシュファイル（`inventory/data/cache/amazon_products/{ASIN}.json`）のTTLはデフォルト24時間
- 期限切れの場合、商品情報の取得に失敗します
- **失敗が多発する場合は、アプローチAを使用してください**

**ステップ1: ASIN抽出ツールで対象ASINリストを作成**

（アプローチAと同じ）

**ステップ2: add_new_products.pyでキャッシュから取得**

```powershell
# 本番実行（キャッシュから高速取得、自動的にキューにも追加）
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' inventory/scripts/add_new_products.py --asin-file asins_for_account3.txt --platform base --account-id base_account_3 --skip-existing --yes" 2>&1 | Select-Object -Last 50
```

**重要なオプション**:
- `--asin-file`: ASINリストファイルパス
- `--platform`: 常に `base`
- `--account-id`: 対象アカウントID（例: `base_account_3`）
- `--skip-existing`: 既に対象アカウントに登録済みのASINをスキップ
- `--yes`: 確認をスキップして自動実行
- `--use-sp-api`は**指定しない**（キャッシュから取得）

---

**このパターンを使用すべき理由**:
- ✅ 他アカウントの出品済み商品を再利用できる
- ✅ SP-API呼び出し不要で高速
- ✅ 既に禁止商品チェック済みの商品を活用できる
- ✅ パターン2（Sourcing候補）よりも圧倒的に高速
- ✅ ソースアカウントに大量の出品がある場合、複数回実行して追加充当可能

---

### パターン2: Sourcing候補から新規商品を追加 ⚠️ **【パターン1で不足する場合のみ実行】**

**スクリプト**: `sourcing/scripts/import_candidates_to_master.py`

**対象**:
- **sourcing_candidatesテーブル**の未連携候補
- **productsテーブルに未登録**の新規商品

**処理時間**: ⏱️ **時間がかかる**（1000件あたり約30分〜1時間、SP-API呼び出しのため）

**主な機能**:
- SP-API経由で商品情報を取得（時間がかかる）
- **デフォルトで自動的に以下を実行**:
  - ✅ 禁止商品チェック
  - ✅ ブロックリストチェック
  - ✅ 重複チェック
  - ✅ productsテーブルへの追加
  - ✅ listingsテーブルへの追加
  - ✅ upload_queueへの追加

**実行形式**:
```powershell
# DRY RUN（テスト実行）
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' sourcing/scripts/import_candidates_to_master.py --account-limits 'base_account_2:1000,base_account_3:1000' --dry-run" 2>&1 | Select-Object -Last 50

# 本番実行
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' sourcing/scripts/import_candidates_to_master.py --account-limits 'base_account_2:1000,base_account_3:1000'" 2>&1 | Select-Object -Last 50
```

**重要なオプション**:
- `--account-limits`: アカウント別の追加件数を**カンマ区切り形式**で指定（例: `base_account_2:1000,base_account_3:1000`）
- `--limit`: 処理する最大件数（デフォルト: 全件）
- `--dry-run`: DRY RUNモード（確認のみ、実際の登録は行わない）
- `--no-queue`: upload_queueへの追加をスキップ（productsとlistingsのみ登録）
- `--products-only`: productsテーブルのみに登録（listingsとqueueはスキップ）

**注意**:
- デフォルトで products → listings → upload_queue の全てに追加されます
- スキップしたい場合のみ `--no-queue` や `--products-only` を使用します
- ⚠️ **SP-API呼び出しのため処理に時間がかかります**（1000件あたり約30分〜1時間）

---

## 🛡️ 安全装置（自動実行される）

### 1. 禁止商品チェック
- **設定ファイル**: `config/prohibited_items.json`
- **チェック内容**:
  - カテゴリベース: 医薬品、酒類、タバコ、チケット、占いなど
  - キーワードベース: 育毛剤、検査キット、デジタルコンテンツなど
  - リスクスコア: 80以上で自動ブロック

### 2. ブロックリスト
- **設定ファイル**: `config/blocked_asins.json`
- **内容**: 過去に削除した禁止商品のASINリスト
- **動作**: リストに含まれるASINは自動的にスキップ

### 3. 重複チェック
- **UNIQUE制約による自動防止**:
  - 同一アカウント内での同じASINの重複登録を防止
  - `(asin, platform, account_id)` のUNIQUE制約で保証

### 4. 同一日付内の複数アカウント重複防止
- **仕様**: 同じASINを同じ日付内に複数のアカウントに出品しない
- **実装**: スクリプト内で`scheduled_time`をチェック

---

## 📊 アカウント情報（事前情報）

**設定ファイル**: `platforms/base/accounts/account_config.json`

| アカウントID | 名前 | ステータス | 1日の出品上限 |
|------------|------|----------|------------|
| `base_account_1` | 在庫BAZAAR | ❌ Inactive | 1000件 |
| `base_account_2` | バイヤー倉庫【送料無料】 | ✅ Active | 1000件 |
| `base_account_3` | イイ値！SHOP | ✅ Active | 1000件 |

---

## ✅ 実行前の確認事項（毎回実行が必要）

### 🔧 専用確認スクリプトの実行（推奨）

**スクリプト**: `shared/utils/check_db_status.py`

データベースの現在状態を一括で確認できる専用ツールです。

**実行方法**:
```powershell
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' shared/utils/check_db_status.py"
```

**確認内容**:
- ✅ products テーブルの総件数
- ✅ listings テーブルのプラットフォーム・アカウント別内訳
- ✅ BASE アカウント2・3の既存出品数
- ✅ upload_queue のステータス別件数
- ✅ sourcing_candidates の総件数・未連携件数
- ✅ Sourcing候補から利用可能な商品数（master.dbに未登録）

**利点**:
- 一度の実行で全ての必要な情報を取得
- 毎回一時スクリプトを作成・削除する手間が不要
- 見やすいレポート形式で出力

---

### 📊 個別にSQLで確認する場合（オプション）

専用スクリプトが使えない場合や、特定の情報のみ確認したい場合：

```sql
-- products テーブルの総件数
SELECT COUNT(*) FROM products;

-- listings テーブルの総件数とアカウント別内訳
SELECT platform, account_id, COUNT(*)
FROM listings
GROUP BY platform, account_id;

-- upload_queue のステータス別件数
SELECT status, COUNT(*)
FROM upload_queue
GROUP BY status;

-- sourcing_candidates の未連携件数
SELECT COUNT(*)
FROM sourcing_candidates
WHERE imported_at IS NULL;

-- アカウント別の既存出品数
SELECT account_id, COUNT(*) as listing_count
FROM listings
WHERE platform = 'base' AND account_id IN ('base_account_2', 'base_account_3')
GROUP BY account_id;

-- Sourcing候補から利用可能な商品数
SELECT COUNT(*)
FROM sourcing_candidates sc
WHERE sc.imported_at IS NULL
  AND sc.asin NOT IN (SELECT asin FROM products);
```

---

## 🚀 実行手順

### ステップ1: データベース状態の確認
専用スクリプトを実行して、現在の状態を把握する

```powershell
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' shared/utils/check_db_status.py"
```

**確認項目**:
- 利用可能な候補商品が十分にあるか（要求件数以上）
- 対象アカウントの既存出品数
- upload_queueの状態（pending/failedの件数）

---

### ステップ2: 実行方法の選択（優先順位）

#### 🎯 **【必須】まずパターン1を実行**

既に`status='pending'`の未出品商品をキューに追加します（最速）。

**判断基準**: DB状態確認で`status='pending'`の商品が要求件数を満たす場合はこれだけで完了

---

#### 🔄 **【パターン1で不足する場合】パターン1.5を実行**

他アカウント（例: base_account_1）の出品済み商品を対象アカウント（例: base_account_3）に展開します（高速）。

**判断基準**: パターン1で不足する場合、かつ他アカウントに出品済み商品が存在する場合に実行

---

#### ⚠️ **【パターン1・1.5で不足する場合のみ】パターン2を実行**

Sourcing候補から新規商品を追加します（時間がかかる）。

**判断基準**: パターン1・1.5を実行しても要求件数に満たない場合のみ実行

---

### ステップ3: 【最優先】パターン1のDRY RUNでテスト

**Master DB（`status='pending'`の未出品商品）からの追加**:
```powershell
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' scheduler/scripts/add_pending_to_queue.py --dry-run" 2>&1 | Select-Object -Last 100
```

**DRY RUNの確認内容**:
- ✅ 追加可能な商品数（`status='pending'`でキュー未登録の件数）
- ✅ アカウント別の振り分け
- ✅ スケジュール時間帯
- ✅ 処理時間の見積もり（数秒〜数十秒）

**この段階で要求件数を満たせる場合**:
→ パターン1の本番実行に進む（ステップ4-1へ）

**この段階で要求件数に満たない場合**:
→ パターン1.5のDRY RUNを実行（ステップ3-2へ）

---

### ステップ3-2: 【パターン1で不足する場合】パターン1.5のDRY RUNでテスト

**他アカウントの出品済み商品を別アカウントに展開**:

#### サブステップ1: ASIN抽出ツールで対象ASINリストを作成

**推奨**: 専用のASIN抽出ツールを使用（一時スクリプト不要）

```powershell
# base_account_1からbase_account_3に展開可能なASINを1000件抽出
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' shared/utils/extract_cross_account_asins.py --source-account base_account_1 --target-account base_account_3 --platform base --limit 1000 --output asins_for_account3.txt"
```

**⚠️ 重要**: 最初の1000件で不足する場合、**ソースアカウントの残りの出品から追加で充当**してください：

```powershell
# 追加で500件抽出（2回目の実行）
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' shared/utils/extract_cross_account_asins.py --source-account base_account_1 --target-account base_account_3 --platform base --limit 500 --offset 1000 --output asins_for_account3_additional.txt"
```

ソースアカウント（base_account_1）に12,000件の出品がある場合、**残り11,000件から追加で充当できます**。Sourcing候補から取得する前に、まずソースアカウントの残りを活用してください。

#### サブステップ2: productsテーブルから直接コピー（推奨）

**アプローチA: 専用ツール使用**（キャッシュTTL期限切れ問題を回避）

```powershell
# DRY RUNで確認
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' shared/utils/copy_products_to_listings.py --asin-file asins_for_account3.txt --platform base --account-id base_account_3 --dry-run"

# 本番実行
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' shared/utils/copy_products_to_listings.py --asin-file asins_for_account3.txt --platform base --account-id base_account_3"
```

**アプローチB: add_new_products.py使用**（キャッシュTTL期限切れに注意）

```powershell
# 本番実行（キャッシュから取得）
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' inventory/scripts/add_new_products.py --asin-file asins_for_account3.txt --platform base --account-id base_account_3 --skip-existing --yes" 2>&1 | Select-Object -Last 50
```

⚠️ アプローチBで失敗が多発する場合は、アプローチAを使用してください。

---

**この段階で要求件数を満たせる場合**:
→ 完了（パターン2は不要）

**この段階で要求件数に満たない場合**:
1. **まず、ソースアカウントの残りの出品から追加抽出**（サブステップ1を再実行、offsetを指定）
2. それでも不足する場合のみ、パターン2のDRY RUNを実行（ステップ3-3へ）

---

### ステップ3-3: 【パターン1・1.5で不足する場合のみ】パターン2のDRY RUNでテスト

**Sourcing候補（新規商品）からの追加**:
```powershell
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' sourcing/scripts/import_candidates_to_master.py --account-limits 'base_account_2:1000,base_account_3:1000' --dry-run" 2>&1 | Select-Object -Last 100
```

**DRY RUNの確認内容**:
- ✅ 追加される商品数
- ✅ スキップされる商品（禁止商品、重複など）
- ✅ エラーの有無
- ✅ 処理時間の見積もり（⚠️ 1000件あたり約30分〜1時間）

---

### ステップ4: 本番実行

#### 【パターン1】Master DB（`status='pending'`の未出品商品）からの追加

DRY RUNの結果を確認後、`--dry-run`を削除して実行：

```powershell
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' scheduler/scripts/add_pending_to_queue.py --yes" 2>&1 | Select-Object -Last 50
```

**処理完了後**: ステップ5で結果を確認し、要求件数に満たない場合のみパターン1.5またはパターン2を実行

---

#### 【パターン1.5】他アカウントの出品済み商品を別アカウントに展開（パターン1で不足する場合）

ステップ3-2で作成したASINリストを使用して実行（既に実行済みの場合はスキップ）

---

#### 【パターン2】Sourcing候補（新規商品）からの追加（パターン1・1.5で不足する場合のみ）

DRY RUNの結果を確認後、`--dry-run`を削除して実行：

```powershell
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' sourcing/scripts/import_candidates_to_master.py --account-limits 'base_account_2:1000,base_account_3:1000'" 2>&1 | Select-Object -Last 50
```

**⚠️ 注意**: 処理に時間がかかります（1000件あたり約30分〜1時間）

---

### ステップ5: 実行結果の確認

再度、専用スクリプトを実行して結果を確認：
```powershell
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' shared/utils/check_db_status.py"
```

または、個別にSQLで確認：
```sql
-- 追加された商品数を確認
SELECT COUNT(*) FROM products WHERE created_at > datetime('now', '-1 hour');

-- キューに追加された件数を確認
SELECT account_id, COUNT(*)
FROM upload_queue
WHERE created_at > datetime('now', '-1 hour')
GROUP BY account_id;
```

---

## ⚠️ 注意事項

1. **既存スクリプトを必ず使用する**
   - 重複防止、禁止商品チェックなどの重要な処理が実装されています
   - 独自スクリプトの作成は禁止

2. **処理中にエラーが発生した場合**
   - 処理を停止してユーザーに報告
   - エラー内容、発生箇所、影響範囲を明確に伝える

3. **同一日付内の重複出品防止**
   - スクリプトが自動的にチェック
   - 異なる日付であれば、別のアカウントへの出品は可能

4. **禁止商品の自動検出**
   - リスクスコア80以上の商品は自動的にスキップ
   - スキップされた商品はログに記録される

---

## 📝 参考ドキュメント

- **README.md**: プロジェクト全体の概要
- **QUICKSTART.md**: セットアップと基本的な使い方
- **docs/PROHIBITED_ITEMS_MANAGEMENT.md**: 禁止商品管理システムの詳細
- **sourcing/sources/sellersprite/USAGE.md**: ソーシング機能の使い方

---

## 💡 よくある質問

**Q: products テーブルに既に存在する商品を別のアカウントに追加できますか？**
A: はい、可能です。listingsテーブルのUNIQUE制約は`(asin, platform, account_id)`なので、同じASINでも異なるアカウントに出品できます。

**Q: 同じASINを複数のアカウントに同時に出品できますか？**
A: 同一日付内での複数アカウントへの出品は禁止です。異なる日付であれば可能です。

**Q: ブロックリストに含まれるASINを再度追加できますか？**
A: いいえ。`blocked_asins.json`に含まれるASINは自動的にスキップされます。リストから手動で削除する必要があります。

**Q: DRY RUNモードで何が確認できますか？**
A: 追加される商品数、スキップされる商品（禁止商品、重複など）、エラーの有無を確認できます。実際のDB変更は行われません。

---

**このプロンプトを使用することで、毎回READMEやスクリプトを確認する手間が省け、動的なDB状態の確認からすぐに作業を開始できます。**
