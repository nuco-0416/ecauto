# 商品登録ガイド

マスタDBへの新規商品登録方法

## 概要

### 重要なルール

1. ✅ **ASINはマスタDB全体でユニーク**
   - 同じASINは1回のみ登録可能

2. ✅ **プラットフォーム内で1 ASINは1出品のみ**
   - 同じASINを複数のBASEアカウントに出品不可
   - `(ASIN, platform)`の組み合わせがUNIQUE
   - 例: ASIN[B001]はBASEアカウント1またはBASEアカウント2のどちらか1つのみ

3. ✅ **異なるプラットフォーム間では出品OK**
   - ASIN[B001]をBASEとメルカリ両方に出品するのはOK

4. ✅ **出品状態の管理**
   - `status='pending'`: 未出品（キューに追加可能）
   - `status='listed'`: 既に出品済み

## 新規商品登録方法

### パターンA: ASINリストから新規登録（基本）

**用途:** 新規商品をASINリストから追加

**手順:**

1. **ASINリストファイルを作成**

`asins.txt`:
```
B0CB5G8NRV
B0C77CKKVR
B0DYSGGJJW
# コメント行（#で始まる行は無視される）
B0FKGSRGYK
```

2. **スクリプトを実行**

```bash
python inventory/scripts/add_new_products.py \
  --asin-file asins.txt \
  --platform base \
  --account-id base_account_1 \
  --markup-rate 1.3 \
  --skip-existing
```

**パラメータ:**
- `--asin-file`: ASINリストファイル（必須）
- `--platform`: プラットフォーム名（base/mercari/yahoo/ebay、必須）
- `--account-id`: アカウントID（必須）
- `--markup-rate`: Amazon価格に対する掛け率（デフォルト: 1.3）
- `--skip-existing`: 既存のASINをスキップ（推奨）
- `--rate-limit`: SP-API呼び出し間隔（秒、デフォルト: 1.0）

**動作:**
1. ASINリストを読み込み
2. 各ASINについて:
   - キャッシュからAmazon商品情報を取得（Phase 4でSP-API実装予定）
   - `products`テーブルに商品情報を追加
   - 売価を計算（Amazon価格 × 掛け率）
   - `listings`テーブルに出品情報を追加（`status='pending'`）

**次のステップ:**
```bash
# キューに追加（時間分散）
python scheduler/scripts/add_to_queue.py --platform base --distribute

# デーモン起動
python scheduler/daemon.py
```

### パターンB: レガシーCSVから移行登録

**用途:** 既存プロジェクトのCSVデータを移行

**手順:**

1. **既存CSVを確認**

`legacy_products.csv`:
```csv
ASIN,商品名,商品説明,想定売価,item_id,商品コード
B0CB5G8NRV,商品A,説明文A,2980,,base_001
B0C77CKKVR,商品B,説明文B,3980,12345,base_002
```

2. **スクリプトを実行**

```bash
python inventory/scripts/import_legacy_data.py \
  --csv legacy_products.csv \
  --platform base \
  --account-id base_account_1 \
  --asin-column ASIN \
  --status pending \
  --skip-existing
```

**パラメータ:**
- `--csv`: CSVファイルのパス（必須）
- `--platform`: プラットフォーム名（必須）
- `--account-id`: アカウントID（必須）
- `--asin-column`: CSVのASIN列名（デフォルト: ASIN）
- `--status`: 登録時のステータス（pending=未出品、listed=出品済み）
- `--skip-existing`: 既存のASINをスキップ（推奨）
- `--fetch-from-sp-api`: SP-APIから不足情報を取得（Phase 4で実装）
- `--rate-limit`: SP-API呼び出し間隔（秒、デフォルト: 1.0）

**認識されるCSV列:**
- `ASIN` (必須): 商品ASIN
- `商品名` / `title`: 商品名
- `商品説明` / `description`: 商品説明
- `想定売価` / `selling_price` / `price`: 売価
- `item_id`: プラットフォームのアイテムID（出品済みの場合）
- `商品コード` / `sku`: SKU

**動作:**
1. CSVを読み込み
2. 各行について:
   - CSVから商品情報を取得
   - オプション: SP-APIから不足情報を補完
   - `products`テーブルに商品情報を追加
   - `listings`テーブルに出品情報を追加

**次のステップ:**

`--status pending`の場合:
```bash
# キューに追加
python scheduler/scripts/add_to_queue.py --platform base --distribute

# デーモン起動
python scheduler/daemon.py
```

`--status listed`の場合:
- 既に出品済みとして登録されるため、キューには追加不要
- 価格・在庫同期のみ（Phase 4で実装予定）

### パターンC: 既存BASEアカウントからインポート（移行時のみ）

**用途:** 運用中のBASEアカウントから既存商品を取り込み

**手順:**

現在の`import_from_csv.py`を使用:

```bash
python inventory/scripts/import_from_csv.py \
  --source C:\Users\hiroo\Documents\ama-cari\base\data\products_master_base.csv \
  --platform base \
  --account-id base_account_1 \
  --type base_master
```

**動作:**
- CSVから商品情報を読み込み
- `item_id`が存在する場合は`status='listed'`（出品済み）
- `item_id`が空の場合は`status='pending'`（未出品）

**注意:**
このパターンは移行時のみ使用。日常的な新規商品追加にはパターンAを使用してください。

## データフロー

### 新規商品登録から出品まで

```
1. ASINリスト作成
   asins.txt
   ↓
2. 商品登録
   add_new_products.py
   ↓
3. マスタDBに追加
   products テーブル: 商品情報
   listings テーブル: status='pending', account_id設定
   ↓
4. キューに追加
   add_to_queue.py
   ↓
5. upload_queue テーブル
   scheduled_at付きで追加
   ↓
6. デーモン実行
   daemon.py
   ↓
7. アップロード
   BASE APIで出品
   ↓
8. ステータス更新
   listings.status='listed'
   listings.platform_item_id更新
```

### レガシーデータ移行

```
1. 既存CSV
   legacy_products.csv
   ↓
2. データ移行
   import_legacy_data.py
   ↓
3. マスタDBに追加
   products テーブル
   listings テーブル: status='pending' or 'listed'
   ↓
4. status='pending'の場合のみ
   キューに追加 → アップロード
```

## トラブルシューティング

### UNIQUE制約エラー

**エラー:**
```
UNIQUE constraint failed: listings.asin, platform
```

**原因:**
同じASINを同じプラットフォーム内で重複登録しようとした

**対処:**
1. 既存の出品を確認:
```bash
python inventory/scripts/test_db.py
```

2. `--skip-existing`オプションを使用:
```bash
python inventory/scripts/add_new_products.py --skip-existing ...
```

3. または、既存データを削除してから再登録:
```python
# SQLiteで直接削除（注意して使用）
DELETE FROM listings WHERE asin = 'B001' AND platform = 'base';
```

### ASINが既に存在する

**症状:**
`products`テーブルにASINが既存

**対処:**
- `add_product()`は既存の場合は更新するため、エラーにならない
- 問題は`listings`テーブルでの重複のみ
- `--skip-existing`を使用すれば自動的にスキップ

### 商品情報が取得できない

**症状:**
「ASIN XXX の情報がキャッシュにありません」

**原因:**
- キャッシュにデータがない
- SP-APIがまだ実装されていない（Phase 4で実装予定）

**対処:**
- 現在はダミーデータで登録される
- Phase 4でSP-API実装後、再度情報を取得して更新

### プラットフォーム間での重複

**質問:**
同じASINをBASEとメルカリ両方に出品できる？

**回答:**
はい、できます。異なる`platform`であれば問題ありません。

```bash
# BASE用
python inventory/scripts/add_new_products.py \
  --asin-file asins.txt \
  --platform base \
  --account-id base_account_1

# メルカリ用（同じASINでもOK）
python inventory/scripts/add_new_products.py \
  --asin-file asins.txt \
  --platform mercari \
  --account-id mercari_1
```

### アカウント間での振り分け

**質問:**
BASEアカウント1とBASEアカウント2に商品を振り分けるには？

**回答:**
ASINリストを分けて登録してください。

```bash
# アカウント1用
python inventory/scripts/add_new_products.py \
  --asin-file asins_account1.txt \
  --platform base \
  --account-id base_account_1

# アカウント2用
python inventory/scripts/add_new_products.py \
  --asin-file asins_account2.txt \
  --platform base \
  --account-id base_account_2
```

または、レガシーCSVでaccount_id列を分けて登録。

## API リファレンス

### add_new_products.py

```bash
python inventory/scripts/add_new_products.py \
  --asin-file asins.txt \
  --platform base \
  --account-id base_account_1 \
  [--markup-rate 1.3] \
  [--skip-existing] \
  [--rate-limit 1.0]
```

### import_legacy_data.py

```bash
python inventory/scripts/import_legacy_data.py \
  --csv legacy.csv \
  --platform base \
  --account-id base_account_1 \
  [--asin-column ASIN] \
  [--status pending|listed] \
  [--skip-existing] \
  [--fetch-from-sp-api] \
  [--rate-limit 1.0]
```

## Phase 4: SP-API統合完了

### 実装済み機能

- ✅ SP-API統合（商品情報自動取得）
- ✅ Amazon価格・在庫の自動同期
- ✅ 商品画像の自動取得
- ✅ 商品説明・特徴（Bullet Points）の自動取得
- ✅ バッチ処理とレート制限対応

### SP-API機能の使い方

#### 新規商品追加時にSP-APIを使用

```bash
python inventory/scripts/add_new_products.py \
  --asin-file asins.txt \
  --platform base \
  --account-id base_account_1 \
  --use-sp-api \
  --skip-existing
```

**`--use-sp-api` フラグを追加すると:**
- キャッシュに商品情報がない場合、SP-APIから自動取得
- 商品名、説明、ブランド、画像、在庫状況を取得
- 取得したデータはキャッシュに保存（再利用可能）
- ダミーデータの代わりに実データで登録

**取得される情報:**
- `title_ja`: 商品名（日本語）
- `description_ja`: 商品説明（日本語）
- `brand`: ブランド名
- `images`: 商品画像URL（最大6枚）
- `bullet_points`: 商品の特徴
- `amazon_in_stock`: 在庫状況（True/False）
- `amazon_price_jpy`: Amazon価格（取得可能な場合）

#### 既存商品の価格・在庫同期

```bash
# マスタDB内の全商品をAmazonと同期
python inventory/scripts/sync_amazon_data.py

# テスト（最新10件のみ）
python inventory/scripts/sync_amazon_data.py --limit 10

# バッチサイズ調整
python inventory/scripts/sync_amazon_data.py --batch-size 10
```

**動作:**
1. マスタDB内の全ASINを取得
2. 20件ずつバッチでSP-API呼び出し
3. 商品情報と価格を更新
4. 価格変更があった場合は差分を表示
5. マスタDBとキャッシュの両方を更新

**レート制限:**
- SP-APIは1秒あたり0.5リクエストの制限があります
- バッチ処理で2.1秒間隔を空けて呼び出し
- 大量同期には時間がかかることに注意

### SP-API認証情報

システムは既存プロジェクトの認証情報を自動的に読み込みます:

**参照パス:**
```
C:\Users\hiroo\Documents\ama-cari\am_sp-api\sp_api_credentials.py
```

**必要な認証情報:**
- `refresh_token`: SP-APIリフレッシュトークン
- `lwa_app_id`: LWA App ID
- `lwa_client_secret`: LWA Client Secret

認証情報が見つからない場合、警告が表示されますがエラーにはなりません（キャッシュのみ使用）。

### 価格取得の仕組み

**使用API:** Products API (`get_item_offers`)
- すべての商品の価格情報が取得可能（自分が販売登録していない商品もOK）
- Pricing API（Competitive Pricing）とは異なり、すべての出品者のオファーを取得

**フィルタリング条件（すべて必須）:**

1. **新品のみ** (`item_condition="New"` + `SubCondition="new"`)
   - 中古商品は自動的に除外

2. **Prime対象** (`IsPrime = True`)
   - Prime配送対象の商品のみ

3. **Amazon FBA発送** (`IsFulfilledByAmazon = True`)
   - Amazonが発送する商品のみ

4. **カート獲得商品** (`IsBuyBoxWinner = True`) ⭐ NEW
   - カートボタンを獲得している商品のみ
   - **招待制商品を自動除外**（招待制は `IsBuyBoxWinner=False`）

5. **3日以内配送** (`maximumHours <= 72`) ⭐ NEW
   - 配送に3日（72時間）以上かかる商品は除外
   - 発注から3日以内に届く商品のみ

6. **即時発送可能** (`availabilityType = "NOW"`) - デフォルト
   - `require_immediate=True`（デフォルト）: NOW のみ
   - `require_immediate=False`: NOW + 3日以内の FUTURE_WITH_DATE も許可

**除外される商品:**
- 中古商品
- Prime非対象商品
- マーケットプレイス出品（FBA以外）
- **招待制商品**（例: B0DP4586RV）
- **配送に3日以上かかる商品** ⭐ NEW
- 予約商品（require_immediate=True の場合）
- 発売日が3日以上先の商品（require_immediate=False でも除外）

**設定例:**
```python
# デフォルト: 即時発送のみ（予約商品除外）、3日以内配送
price_data = client.get_product_price(asin)  # require_immediate=True

# 3日以内に届く発売予定商品も含む
price_data = client.get_product_price(asin, require_immediate=False)
```

**価格計算:**
```python
# Amazon価格 7,560円、掛け率 1.3 の場合
selling_price = 7560 * 1.3 = 9,828円
```

### トラブルシューティング

#### SP-API取得エラー: No module named 'sp_api'

**原因:** `python-amazon-sp-api` パッケージがインストールされていない

**対処:**
```bash
# venvを使用している場合
./venv/Scripts/pip install python-amazon-sp-api

# グローバルにインストール
pip install python-amazon-sp-api
```

#### Amazon価格が取得できない（None）

**原因:** 全ての商品で価格情報が取得できるわけではありません

**理由:**
- Prime + FBA発送の商品がない（マーケットプレイス出品のみ、またはPrime非対象）
- 在庫切れ（オファーが0件）
- 予約商品（`require_immediate=True`を指定した場合）
- API制限

**対処:** これは正常な動作です。価格が取得できない場合は手動設定してください。

**デバッグ方法:**
```bash
# SP-APIクライアントで直接テスト
cd C:\Users\hiroo\Documents\GitHub\ecauto
./venv/Scripts/python.exe -c "
from integrations.amazon.sp_api_client import AmazonSPAPIClient
from integrations.amazon.config import SP_API_CREDENTIALS

client = AmazonSPAPIClient(SP_API_CREDENTIALS)
price_data = client.get_product_price('YOUR_ASIN_HERE')
print(price_data)
"
```

#### レート制限エラー

**原因:** SP-APIの呼び出し頻度が高すぎる

**対処:**
```bash
# レート制限間隔を長くする
python inventory/scripts/add_new_products.py \
  --rate-limit 3.0 \
  --use-sp-api ...
```

### カテゴリ情報について

Phase 4ではカテゴリ情報の自動取得は実装していません。

**理由:**
- BASEのカテゴリ管理にはアドオンアプリが必要
- Amazonカテゴリとの整合性調整が必要
- Phase 5以降で追加モジュールとして実装予定

## 関連ドキュメント

- [QUICKSTART.md](../QUICKSTART.md) - 全体のセットアップガイド
- [scheduler/README.md](../scheduler/README.md) - アップロードスケジューラー詳細
- [inventory/README.md](README.md) - マスタDB詳細
