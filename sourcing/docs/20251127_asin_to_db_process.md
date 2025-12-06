# ASINの抽出からsourcing.dbへの登録プロセス調査レポート

**調査日時:** 2025-11-27
**調査対象:** C:\Users\hiroo\Documents\GitHub\ecauto\sourcing
**作成者:** Claude Code

---

## 目次

1. [システム概要](#システム概要)
2. [発見したスクリプトとその役割](#発見したスクリプトとその役割)
3. [データベーススキーマ](#データベーススキーマ)
4. [データフロー](#データフロー)
5. [認証システム](#認証システム)
6. [ASIN抽出の詳細プロセス](#asin抽出の詳細プロセス)
7. [データベース登録メカニズム](#データベース登録メカニズム)
8. [実装上の重要ポイント](#実装上の重要ポイント)
9. [ドキュメントとリソース](#ドキュメントとリソース)

---

## システム概要

### 目的と規模

sourcing.dbシステムは、SellerSpriteから大量のASIN（Amazon商品識別コード）を自動抽出し、仕入対象商品候補として蓄積・管理するシステムです。

**現在の状況（2025-11-27）:**
- 総ASIN数: **7,658件**
- うち候補状態: 5,624件
- うち出品済み: 2,034件
- 全てsellerspriteを情報源とする

### アーキテクチャの全体像

```
SellerSprite (Web)
      ↓ [Playwright自動操作]
認証 + ブラウザセッション
      ↓
ASIN抽出スクリプト（複数パターン）
      ↓
中間ファイル（.txt形式）
      ↓
データベース登録スクリプト
      ↓
sourcing.db (SQLite)
      ↓ [出品連携スクリプト]
inventory/master.db (商品マスタ)
      ↓
BASE API → 実出品
```

---

## 発見したスクリプトとその役割

### 1. **データベース初期化スクリプト**

**ファイルパス:** [sourcing/scripts/init_sourcing_db.py](sourcing/scripts/init_sourcing_db.py)

**機能:** sourcing.dbの初期化とテーブル作成

**テーブル作成内容:**
```python
# sourcing_candidates: 仕入候補商品テーブル
- id (INTEGER PRIMARY KEY)
- asin (TEXT UNIQUE)
- source (TEXT) - 'sellersprite', 'amazon_business' など
- category (TEXT) - 商品カテゴリ
- sales_rank (INTEGER) - セールスランク
- estimated_monthly_sales (INTEGER) - 推定月間販売数
- current_price_jpy (INTEGER) - 現在価格
- llm_evaluation_score (REAL) - LLM評価スコア（0.0-1.0）
- llm_reason (TEXT) - 評価理由
- llm_tags (TEXT) - JSONタグ
- status (TEXT) - 'candidate', 'approved', 'rejected', 'imported'
- discovered_at (TIMESTAMP) - 発見日時
- evaluated_at (TIMESTAMP) - 評価日時
- imported_at (TIMESTAMP) - 出品日時

# extraction_logs: 抽出ログテーブル
- 抽出処理のトレーサビリティを記録

# extraction_patterns: 抽出パターン定義テーブル
- 再利用可能な抽出パターンを保存
```

**実行方法:**
```bash
python sourcing/scripts/init_sourcing_db.py
```

### 2. **主要な抽出スクリプト - auto_extract_by_categories.py**

**ファイルパス:** [sourcing/scripts/auto_extract_by_categories.py](sourcing/scripts/auto_extract_by_categories.py)

**概要:** カテゴリベースのASIN自動抽出（最新・推奨）

**処理フロー:**
```
1. 初期サンプリング
   ↓
   500-1,000件のASINをカテゴリ情報付きで取得

2. カテゴリ統計分析
   ↓
   発見されたカテゴリを統計・ソート

3. 既存DB比較
   ↓
   既存DB内のカテゴリ分布を確認
   未開拓カテゴリを特定

4. 優先順位付け
   ↓
   未開拓カテゴリ → 既存カテゴリの順で処理

5. カテゴリ別抽出ループ
   ↓
   各カテゴリで2,000件ずつ抽出
   リアルタイム重複チェック
   目標件数達成まで継続

6. 結果保存
   ↓
   テキストファイル + Markdownレポート
```

**使用例（推奨構成）:**
```bash
python sourcing/scripts/auto_extract_by_categories.py \
  --target-new-asins 10000 \
  --sample-size 1000 \
  --asins-per-category 2000 \
  --max-categories 20 \
  --sales-min 300 \
  --price-min 2500 \
  --output base_asins_extracted.txt \
  --report extraction_report.md
```

**パラメータ詳細:**

| パラメータ | デフォルト | 説明 |
|-----------|---------|------|
| `--target-new-asins` | 10000 | 目標新規ASIN数 |
| `--sample-size` | 1000 | 初期サンプルサイズ（最大: 2000） |
| `--asins-per-category` | 2000 | 各カテゴリの取得数（最大: 2000） |
| `--max-categories` | 20 | 最大処理カテゴリ数 |
| `--sales-min` | 300 | 月間販売数の最小値 |
| `--price-min` | 2500 | 価格の最小値（円） |
| `--market` | JP | 市場（JP, US, UK等） |
| `--output` | なし | 出力ファイルパス（ASIN一覧） |
| `--report` | なし | レポートファイルパス（Markdown） |

### 3. **その他の抽出スクリプト**

#### **extract_asins.py**
- **用途:** 単一パターンでの基本的なASIN抽出
- **パターン:** ranking, category, seasonal, product_research
- **特徴:** コマンドラインパラメータによる柔軟な制御

**使用例:**
```bash
python sourcing/scripts/extract_asins.py \
  --pattern ranking \
  --category "おもちゃ・ホビー" \
  --min-rank 1 \
  --max-rank 1000 \
  --output data/asins_20250123.txt
```

#### **extract_asins_bulk.py**
- **用途:** セグメント分割による大量抽出（3000件/日目標）
- **戦略:** 価格帯や販売数範囲で分割して、SellerSpriteの2000件制限を回避
- **特徴:** 複数セグメントを1ブラウザセッションで処理

#### **analyze_popular_categories.py**
- **用途:** ランキング上位商品からカテゴリ分析
- **出力:** popular_categories.json（nodeIdPaths付き）
- **用途:** カテゴリ別抽出の事前準備

### 4. **データベース登録スクリプト**

#### **register_asins_from_file.py**

**ファイルパス:** [sourcing/scripts/register_asins_from_file.py](sourcing/scripts/register_asins_from_file.py)

**機能:** ASINテキストファイルをsourcing_candidatesテーブルに登録

**処理ロジック:**
```python
# 入力: ASINファイル（1行に1つのASIN）
# 処理:
for asin in asins:
    cursor.execute('SELECT id FROM sourcing_candidates WHERE asin = ?', (asin,))
    existing = cursor.fetchone()

    if existing:
        # 既存の場合: discovered_at を更新
        UPDATE sourcing_candidates
        SET discovered_at = ?
        WHERE asin = ?
    else:
        # 新規の場合: 挿入
        INSERT INTO sourcing_candidates (
            asin,
            source,
            status,
            discovered_at
        ) VALUES (?, 'sellersprite', 'candidate', ?)

# 出力: 実行結果（新規登録数、既存更新数）
```

**使用例:**
```bash
python sourcing/scripts/register_asins_from_file.py \
  --input base_asins_combined_20251127.txt
```

**結果例:**
```
================================================
登録完了
================================================
総ASIN数:     10000件
新規登録:     7658件
既存更新:     2342件
================================================
```

#### **import_candidates_to_master.py**

**ファイルパス:** [sourcing/scripts/import_candidates_to_master.py](sourcing/scripts/import_candidates_to_master.py)

**機能:** sourcing_candidates → master.db への出品連携

**処理フロー:**
```
1. 候補ASIN取得
   sourcing_candidates から status='candidate' を取得

2. SP-API で商品情報取得
   - 既存: productsテーブルから取得（高速）
   - 新規: SP-APIで取得（時間がかかる）

3. アカウント割り振り
   - ランダムにアカウント選択
   - base_account_1, base_account_2 に均等配分

4. products + listings 登録
   - ProductRegistrar で一括登録

5. upload_queue 追加
   - 出品実行キューに追加

6. status 更新
   - sourcing_candidates の status を 'imported' に更新
```

**使用例:**
```bash
# DRY RUN（確認のみ）
python sourcing/scripts/import_candidates_to_master.py --dry-run

# 本番実行（最大100件）
python sourcing/scripts/import_candidates_to_master.py --limit 100

# 全件実行
python sourcing/scripts/import_candidates_to_master.py

# アカウント別の件数指定（2025-11-28 追加機能）
python sourcing/scripts/import_candidates_to_master.py --account-limits "base_account_1:989,base_account_2:400"
```

**パラメータ詳細:**

| パラメータ | 説明 | 例 |
|-----------|------|-----|
| `--limit` | 処理する最大件数 | `--limit 100` |
| `--dry-run` | 確認のみ（実際の登録は行わない） | `--dry-run` |
| `--account-limits` | アカウント別の追加件数指定 | `--account-limits "base_account_1:989,base_account_2:400"` |

**`--account-limits` オプション（2025-11-28 追加）:**

このオプションを使用すると、各アカウントに追加する件数を個別に指定できます。

- **形式:** `アカウントID:件数,アカウントID:件数`
- **用途:** upload_queueのバランス調整
- **動作:**
  1. 指定された件数の合計が自動的に`--limit`として設定される
  2. ASINがランダムにシャッフルされ、指定された件数ずつ各アカウントに割り当てられる
  3. 既存の1000件ずつの均等割り振りを上書き

**実行例（2025-11-28）:**
```bash
# 実行前の状態
# - base_account_1: 11件（pending）
# - base_account_2: 600件（pending）

# 目標: 各アカウント1000件にする
python sourcing/scripts/import_candidates_to_master.py \
  --account-limits "base_account_1:989,base_account_2:400"

# 実行結果
# - base_account_1: 938件（pending） ← 927件追加
# - base_account_2: 977件（pending） ← 377件追加
# - 合計: 1,915件（達成率: 95.8%）
```

**不足が発生した理由:**
- SP-APIでの商品情報取得失敗（NOT_FOUND）
- SP-APIクォータ超過エラー
- 既にlistingsに登録済みでキューに追加されなかった商品

---

## データベーススキーマ

### テーブル構造

#### **sourcing_candidates** （メインテーブル）

```
┌─────────────────────────────────────────────────────────────┐
│ sourcing_candidates                                          │
├──────────┬──────────────┬──────┬─────────┬──────────────────┤
│ Column   │ Type         │ PK   │ NOT NULL│ Constraint       │
├──────────┼──────────────┼──────┼─────────┼──────────────────┤
│ id       │ INTEGER      │ ✓    │ ✓       │ AUTOINCREMENT    │
│ asin     │ TEXT         │      │ ✓       │ UNIQUE           │
│ source   │ TEXT         │      │         │ 'sellersprite'   │
│ source_  │ TEXT         │      │         │ 外部ID           │
│ item_id  │              │      │         │                  │
│ sales_   │ INTEGER      │      │         │ ランク           │
│ rank     │              │      │         │                  │
│ category │ TEXT         │      │         │ NULL OK         │
│ estimated│ INTEGER      │      │         │ 月販売数         │
│_monthly_ │              │      │         │                  │
│sales     │              │      │         │                  │
│ current_ │ INTEGER      │      │         │ 日本円           │
│ price_jpy│              │      │         │                  │
│ llm_eval │ REAL         │      │         │ 0.0-1.0          │
│uation_  │              │      │         │                  │
│ score    │              │      │         │                  │
│ llm_     │ TEXT         │      │         │ JSON形式         │
│ reason   │              │      │         │                  │
│ llm_tags │ TEXT         │      │         │ JSON: ["tag"...] │
│ status   │ TEXT         │      │ ✓       │ DEFAULT:         │
│          │              │      │         │ 'candidate'      │
│ discover │ TIMESTAMP    │      │ ✓       │ DEFAULT:         │
│ ed_at    │              │      │         │ CURRENT_         │
│          │              │      │         │ TIMESTAMP        │
│ evaluated│ TIMESTAMP    │      │         │ NULL OK          │
│ _at      │              │      │         │                  │
│ imported │ TIMESTAMP    │      │         │ NULL OK          │
│ _at      │              │      │         │                  │
└──────────┴──────────────┴──────┴─────────┴──────────────────┘

インデックス:
- idx_candidates_asin ON (asin)
- idx_candidates_status ON (status)
```

#### **extraction_logs** （処理ログテーブル）

```
処理トレーサビリティを記録：
- extraction_type: 'ranking', 'category', 'seasonal'
- parameters: JSON形式の抽出条件
- asins_found: 抽出件数
- status: 'running', 'completed', 'failed'
- started_at: 処理開始時刻
- completed_at: 処理完了時刻
- error_message: エラー内容
```

#### **extraction_patterns** （再利用可能なパターン）

```
Playwright操作パターンを保存・再利用するための定義テーブル：
- pattern_name: パターン識別子
- pattern_type: 'ranking', 'category', 'seasonal'
- playwright_script: Python async関数コード
- parameters_schema: JSON Schema
```

### インデックス戦略

```sql
CREATE INDEX idx_candidates_asin ON sourcing_candidates(asin);
CREATE INDEX idx_candidates_status ON sourcing_candidates(status);
CREATE INDEX idx_logs_type ON extraction_logs(extraction_type);
CREATE INDEX idx_logs_status ON extraction_logs(status);
```

**効果:**
- ASIN検索: 高速化（重複チェック時に使用）
- ステータス検索: 高速化（候補/出品済みの分類時に使用）

---

## データフロー

### 完全フロー図

```
┌────────────────────────────────────────────────────────────────────┐
│                       PHASE 0: ASIN抽出                            │
└────────────────────────────────────────────────────────────────────┘

1. SellerSprite へアクセス
   ↓
   認証 (auth_manager.py)
   - メールアドレス/パスワード入力
   - Google認証
   - Cookie保存

2. ASIN抽出（複数パターン）
   ├─ auto_extract_by_categories.py    ← 推奨（新規が多い）
   ├─ extract_asins.py                 ← 単純パターン
   ├─ extract_asins_bulk.py            ← 大量抽出用
   └─ analyze_popular_categories.py    ← カテゴリ分析

3. 中間ファイル作成
   テキストファイル (1行に1ASIN)
   例: base_asins_20251127.txt

┌────────────────────────────────────────────────────────────────────┐
│                   PHASE 1: DB登録 + キューイング                    │
└────────────────────────────────────────────────────────────────────┘

4. ASIN をDBに登録
   register_asins_from_file.py
   ├─ 重複チェック
   ├─ 新規: INSERT
   ├─ 既存: UPDATE discovered_at
   └─ sourcing_candidates に登録

5. 出品連携（オプション）
   import_candidates_to_master.py
   ├─ sourcing_candidates から取得
   ├─ SP-API で商品情報取得
   ├─ master.db (products) に登録
   ├─ upload_queue に追加
   └─ sourcing_candidates status → 'imported'

┌────────────────────────────────────────────────────────────────────┐
│                     PHASE 2: 出品実行（既存）                       │
└────────────────────────────────────────────────────────────────────┘

6. upload_executor（既存パイプライン）
   ↓
   BASE API → 出品完了
```

### 重要なデータ変換ポイント

#### **ASIN抽出時：**
```
SellerSprite WebUI (HTMLテーブル)
   ↓ [JavaScriptスクリプト実行]
JSオブジェクト { asin, category, nodeIdPaths }
   ↓ [Python側で受け取り]
テキストファイル (1行=1ASIN)
```

#### **DB登録時：**
```
テキストファイル (ASIN リスト)
   ↓ [重複チェック + 変換]
SQLクエリ (INSERT / UPDATE)
   ↓ [SQLite実行]
sourcing.db
   ├─ sourcing_candidates テーブル
   └─ extraction_logs テーブル
```

---

## 認証システム

### 認証マネージャー構成

**ファイルパス:** [sourcing/sources/sellersprite/auth_manager.py](sourcing/sources/sellersprite/auth_manager.py)

### 実装された3つの認証方法

#### **1. 手動ログイン** `manual_login()`
```python
async def manual_login():
    """ブラウザを開いて、ユーザーが手動でログイン"""
    # 1. ブラウザ起動
    # 2. https://www.sellersprite.com/jp/w/user/login に遷移
    # 3. ユーザーが手動でGoogle認証
    # 4. ログイン完了を自動検出
    # 5. Cookie保存
```

**特徴:**
- 最も確実
- 2段階認証対応
- Cookie永続化

#### **2. 自動ログイン** `auto_login()`
```python
async def auto_login():
    """Google認証情報を使用した自動ログイン"""
    # 環境変数から取得:
    # - GOOGLE_EMAIL
    # - GOOGLE_PASSWORD
```

**特徴:**
- 環境変数ベース
- スクリプト化可能
- 自動化に向く

#### **3. 直接ログイン** `direct_login()`
```python
async def direct_login():
    """SellerSprite直接認証（メール/パスワード）"""
    # 環境変数から取得:
    # - SELLERSPRITE_EMAIL
    # - SELLERSPRITE_PASSWORD
```

**特徴:**
- 最も簡単
- SellerSprite専用
- Googleアカウント不要

### 認証情報の保存場所

```
C:\Users\hiroo\Documents\GitHub\ecauto\sourcing\sources\sellersprite\.env
```

**設定例:**
```env
SELLERSPRITE_EMAIL=your-email@example.com
SELLERSPRITE_PASSWORD=your-password
GOOGLE_EMAIL=your-google@gmail.com
GOOGLE_PASSWORD=your-google-password
```

### セッション管理

**Cookie保存場所:**
```
C:\Users\hiroo\Documents\GitHub\ecauto\sourcing\data\sellersprite_cookies.json
```

**Chromeプロファイル保存場所:**
```
C:\Users\hiroo\Documents\GitHub\ecauto\sourcing\data\chrome_profile/
```

### 認証フロー

```
認証チェック (check_cookie_expiry)
   ↓
[Cookie有効かつプロファイル存在？]
   ├─ YES → プロファイル使用（セッション再利用）
   └─ NO → ログイン画面へ

[ログイン方法選択]
   ├─ SELLERSPRITE_EMAIL 環境変数あり → direct_login()
   ├─ GOOGLE_EMAIL 環境変数あり → auto_login()
   └─ いずれもなし → manual_login()
```

---

## ASIN抽出の詳細プロセス

### 共通ユーティリティ

**ファイルパス:** [sourcing/sources/sellersprite/utils/category_extractor.py](sourcing/sources/sellersprite/utils/category_extractor.py)

このモジュールはあらゆる抽出スクリプトの基盤となります。

### 主要な3つの関数

#### **1. build_product_research_url()**
```python
def build_product_research_url(
    market: str,              # "JP", "US", "UK", etc.
    sales_min: int,           # 月間販売数の最小値
    price_min: int,           # 価格の最小値
    amz: bool = True,         # Amazon販売のみ
    fba: bool = True,         # FBAのみ
    node_id_paths: str = "[]" # カテゴリフィルター
) -> str:
    """
    URLパラメータによるフィルター条件をすべて指定した完全なURLを構築
    UI操作は一切不要
    """
```

**生成URLの例:**
```
https://www.sellersprite.com/v3/product-research?
  market=JP&
  page=1&
  size=100&
  minSales=300&
  minPrice=2500&
  sellerTypes=["AMZ","FBA"]&
  nodeIdPaths=[]&
  ...
```

**利点:**
- フィルター実行ボタンのクリック不要
- 高速（UI操作のオーバーヘッドなし）
- 確実（HTMLパース不要）

#### **2. extract_asins_with_categories()**
```python
async def extract_asins_with_categories(
    page: Page,
    limit: int
) -> List[Dict[str, str]]:
    """
    テーブルからASINとカテゴリ情報を抽出

    返却値:
    [
        {
            "asin": "B00XXXXX",
            "category": "ホーム&キッチン > キッチン用品",
            "nodeIdPaths": "[\"...\":\"...\"]"
        },
        ...
    ]
    """
```

**処理ステップ:**
```
1. リスト表示に切り替え
   - 「リスト」ボタンをクリック（表示最適化）

2. 必要なページ数を計算
   - limit 件数から ⌈limit / 100⌉ ページを取得

3. 各ページを処理
   ├─ 全ての展開アイコンをクリック
   ├─ DOMの更新を待機（3秒）
   ├─ JavaScriptで行ごとにASIN/カテゴリ抽出
   └─ 次のページに移動

4. limit件数に制限
```

**JavaScript抽出ロジック:**
```javascript
// テーブルの各行をスキャン
rows.forEach((row, index) => {
    // ASIN正規表現で抽出
    const asinMatch = rowText.match(/ASIN:\s*([A-Z0-9]{10})/);

    if (asinMatch) {
        currentAsin = asinMatch[1];
    }

    // 展開詳細セクション (.table-expand) からカテゴリを抽出
    const tableExpand = row.querySelector('.table-expand');
    if (tableExpand && currentAsin) {
        // .product-type > a.type をすべて取得
        const categoryLinks = productType.querySelectorAll('a.type');

        // 最後のリンクからnodeIdPathsを抽出
        const lastLink = categoryLinks[categoryLinks.length - 1];
        const nodeIdPathsParam = new URL(lastLink.href).searchParams.get('nodeIdPaths');
    }
});
```

#### **3. create_browser_session()**
```python
@asynccontextmanager
async def create_browser_session(
    email: Optional[str] = None,
    password: Optional[str] = None,
    headless: bool = False
):
    """
    ログイン済みのブラウザセッションを作成

    yield: (browser, page)
    """
```

**特徴:**
- 環境変数から認証情報を自動取得
- with文でのリソース自動管理
- ブラウザ自動クローズ

### カテゴリベース抽出の詳細フロー

`auto_extract_by_categories.py` の実装詳細：

```python
class CategoryBasedExtractor:
    async def run(self):
        # ステップ1: 初期サンプリング
        sample_data = await self._initial_sampling(page)
        # 返却値: [{"asin": "B00X", "category": "カテゴリA", ...}, ...]

        # ステップ2: カテゴリ統計分析
        category_stats = self._analyze_categories(sample_data)
        # 返却値: {
        #     "Home & Kitchen": {"count": 50, "nodeIdPaths": "[...]"},
        #     "Beauty": {"count": 30, "nodeIdPaths": "[...]"},
        #     ...
        # }

        # ステップ3: 既存DBのカテゴリ分布確認
        existing_categories = self._get_existing_categories()
        # 返却値: {"Home & Kitchen": 1200, "Beauty": 800, ...}

        # ステップ4: 未開拓カテゴリ特定
        unexplored = self._identify_unexplored_categories(
            category_stats, existing_categories
        )
        # 返却値: {"Toys", "Electronics", ...}

        # ステップ5: 優先順位付け
        prioritized = self._prioritize_categories(
            category_stats, unexplored
        )
        # 返却値: [
        #     ("Toys", {...}),
        #     ("Electronics", {...}),
        #     ("Beauty", {...}),  # 既存カテゴリ
        # ]

        # ステップ6: カテゴリ別抽出ループ
        all_new_asins = set()
        for category_name, category_info in prioritized:
            if len(all_new_asins) >= self.args.target_new_asins:
                break  # 目標達成

            new_asins = await self._extract_by_category(
                page,
                category_name,
                category_info['nodeIdPaths'],
                all_new_asins
            )
            all_new_asins.update(new_asins)

        # ステップ7: 結果保存
        await self._save_results(all_new_asins, prioritized)
```

### 重複チェックの仕組み

```python
def _get_existing_asins(self) -> Set[str]:
    """既存DBのASINセットを取得（高速）"""
    conn = sqlite3.connect(self.db_path)
    cursor = conn.cursor()

    cursor.execute('SELECT asin FROM sourcing_candidates')
    rows = cursor.fetchall()
    return {row[0] for row in rows}  # O(n)から O(1) へ

async def _extract_by_category(
    self, page, category_name, node_id_paths, already_found_asins
) -> Set[str]:
    """カテゴリ別抽出（リアルタイム重複チェック）"""

    # 抽出
    asins = {item['asin'] for item in data if item.get('asin')}

    # 既存DBのASINを取得
    existing_asins = self._get_existing_asins()

    # 重複チェック
    new_asins = asins - existing_asins - already_found_asins
    #        ↑      ↑                 ↑
    #        抽出   既存DB          今回実行内
```

---

## データベース登録メカニズム

### register_asins_from_file.py の詳細

```python
def register_asins(input_file: Path, db_path: Path):
    """ASINファイルをDBに登録"""

    # 1. ASINファイル読み込み
    asins = []
    with input_file.open('r', encoding='utf-8') as f:
        for line in f:
            asin = line.strip()
            if asin:
                asins.append(asin)

    # 2. DB接続
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 3. 各ASINを処理
    saved_count = 0
    updated_count = 0

    for i, asin in enumerate(asins, 1):
        # 既存チェック
        cursor.execute(
            'SELECT id FROM sourcing_candidates WHERE asin = ?',
            (asin,)
        )
        existing = cursor.fetchone()

        if existing:
            # 更新パターン
            cursor.execute(
                '''UPDATE sourcing_candidates
                   SET discovered_at = ?
                   WHERE asin = ?''',
                (datetime.now().isoformat(), asin)
            )
            updated_count += 1
        else:
            # 挿入パターン
            cursor.execute(
                '''INSERT INTO sourcing_candidates (
                    asin,
                    source,
                    status,
                    discovered_at
                ) VALUES (?, 'sellersprite', 'candidate', ?)''',
                (asin, datetime.now().isoformat())
            )
            saved_count += 1

        # 進捗表示（100件ごと）
        if i % 100 == 0:
            print(f"処理中: {i}/{len(asins)}件")

    # 4. コミット
    conn.commit()
    conn.close()

    # 5. 統計表示
    print(f"新規登録: {saved_count}件")
    print(f"既存更新: {updated_count}件")
```

### 重要な設計決定

1. **UNIQUE制約による重複防止**
   ```sql
   CREATE TABLE sourcing_candidates (
       asin TEXT UNIQUE,  -- ← これにより重複ASINの挿入が自動防止
       ...
   )
   ```

2. **discovered_at の更新**
   ```
   既存ASINが再度見つかった場合、「発見日時」を更新することで
   同一ASINが複数回抽出される状況を トレース可能 にしている
   ```

3. **status = 'candidate' の意味**
   ```
   新規登録されたASINは必ず 'candidate' ステータスで開始
   → 後で LLM評価や出品処理で 'approved' や 'imported' に更新
   ```

---

## 実装上の重要ポイント

### 1. **認証とセッション管理**

**ポイント:**
- 複数回のログインを避けるために、1回のセッションで複数カテゴリを処理
- Cookie/Chromeプロファイルの永続化によるセッション再利用
- 2段階認証への対応

**実装箇所:**
```python
# auto_extract_by_categories.py の key part
async with create_browser_session(headless=False) as (browser, page):
    # ブラウザセッションは1つだけ作成
    # 全てのカテゴリ処理でこの page を再利用

    for category_name, category_info in prioritized_categories:
        new_asins = await self._extract_by_category(
            page,  # ← 同じページオブジェクト
            category_name,
            category_info['nodeIdPaths'],
            all_new_asins
        )
```

### 2. **重複排除の3段階防御**

```
第1防御: SQLの UNIQUE制約
         同じASINが2つ登録されることを物理的に防止

第2防御: register_asins_from_file.py の SELECT チェック
        既存ASIN の有無を確認して UPDATE/INSERT を分岐

第3防御: auto_extract_by_categories.py の リアルタイムチェック
        抽出時に existing_asins と already_found_asins を除外
```

### 3. **SellerSprite UIの変動への耐性**

```python
# category_extractor.py の工夫

# ❌ 脆弱な実装
await page.click('#filterButton')  # IDがコロコロ変わる

# ✅ 堅牢な実装
url = build_product_research_url(...)  # UIに依存しない
await page.goto(url)                   # URLパラメータを直接指定
# この方法なら UIの変更の影響を受けない
```

### 4. **JavaScriptでのデータ抽出**

```python
# page.evaluate() を使ってブラウザ内で直接JS実行
data_on_page = await page.evaluate('''() => {
    const data = [];
    const rows = Array.from(document.querySelectorAll('table tbody tr'));

    rows.forEach((row) => {
        // HTMLパース
        const asinMatch = row.textContent.match(/ASIN:\\s*([A-Z0-9]{10})/);

        if (asinMatch) {
            data.push({
                asin: asinMatch[1],
                category: extractCategory(row),
                nodeIdPaths: extractNodeIdPaths(row)
            });
        }
    });

    return data;  // Python側に返却
}''')
```

**利点:**
- HTMLフォーマット変更への耐性が強い（テキスト抽出が中心）
- ブラウザの実行環境で直接操作できる
- 複雑なDOM操作が可能

### 5. **エラーハンドリングと再試行**

```python
# base_extractor.py（全抽出器の基底クラス）の実装

async def extract(self) -> List[str]:
    """抽出を実行（エラーハンドリング付き）"""
    try:
        asins = await self._extract_impl(controller)
        return asins

    except Exception as e:
        self.log(f"[ERROR] 抽出処理エラー: {e}")

        # エラー時の処理
        try:
            if controller.page and not controller.page.is_closed():
                await controller.screenshot("error.png")
        except:
            pass

        raise
```

### 6. **ログとトレーサビリティ**

```python
# 全スクリプトに共通のロギング

self.log(f"【ステップ1】初期サンプリングを開始...")
# ↓
# [HH:MM:SS] 【ステップ1】初期サンプリングを開始...

# extraction_logs テーブルにも記録
cursor.execute('''
    INSERT INTO extraction_logs (
        extraction_type, parameters, asins_found,
        status, started_at, completed_at
    ) VALUES (?, ?, ?, ?, ?, ?)
''', (...))
```

---

## ドキュメントとリソース

### 関連ドキュメントファイル

| ファイル | 内容 |
|---------|------|
| [sourcing/docs/auto_extract_by_categories_reference.md](sourcing/docs/auto_extract_by_categories_reference.md) | auto_extract_by_categories.py の完全リファレンス |
| [sourcing/docs/analyze_popular_categories_reference.md](sourcing/docs/analyze_popular_categories_reference.md) | カテゴリ分析スクリプトの詳細 |
| [sourcing/docs/sellersprite_authentication_and_category_extraction.md](sourcing/docs/sellersprite_authentication_and_category_extraction.md) | 認証とカテゴリ抽出の技術詳細 |
| [sourcing/docs/category_based_extraction_plan.md](sourcing/docs/category_based_extraction_plan.md) | カテゴリベース抽出の実装計画 |
| [sourcing/docs/20251126_listing_integration_execution_report.md](sourcing/docs/20251126_listing_integration_execution_report.md) | 出品連携の実行結果レポート |
| [docs/sourcing_plan.md](docs/sourcing_plan.md) | プロジェクト全体の実装計画 |

### README ファイル

| ファイル | 内容 |
|---------|------|
| [sourcing/sources/sellersprite/README.md](sourcing/sources/sellersprite/README.md) | SellerSprite統合の概要 |
| [sourcing/sources/sellersprite/README_LOGIN.md](sourcing/sources/sellersprite/README_LOGIN.md) | ログイン方法の詳細 |
| [sourcing/sources/sellersprite/USAGE.md](sourcing/sources/sellersprite/USAGE.md) | 使用例とパラメータ |

### スクリプト使用時の推奨構成

**基本構成（Phase 0）:**
```bash
# ステップ1: DBの初期化
python sourcing/scripts/init_sourcing_db.py

# ステップ2: ASIN抽出（カテゴリベース推奨）
python sourcing/scripts/auto_extract_by_categories.py \
  --target-new-asins 10000 \
  --output base_asins.txt

# ステップ3: DB登録
python sourcing/scripts/register_asins_from_file.py \
  --input base_asins.txt
```

**発展構成（Phase 1）:**
```bash
# Phase 0の後で

# ステップ4: 出品連携
python sourcing/scripts/import_candidates_to_master.py
```

### 開発環境

**Python環境:**
```
C:\Users\hiroo\Documents\GitHub\ecauto\venv
```

**認証情報設定:**
```
C:\Users\hiroo\Documents\GitHub\ecauto\sourcing\sources\sellersprite\.env
```

**データベース:**
```
C:\Users\hiroo\Documents\GitHub\ecauto\sourcing\data\sourcing.db
```

---

## 現在の状況（2025-11-27 調査時点）

### sourcing.db の統計

```
総ASIN数: 7,658件
├─ 候補状態 (candidate): 5,624件
└─ 出品済み (imported): 2,034件

全て SellerSprite を情報源とする

抽出ログ: 89件の処理記録
```

### 処理フロー実績

1. **ASIN抽出済み**: 7,658件
2. **DB登録済み**: 7,658件（sourcing_candidates）
3. **出品連携済み**: 2,034件（inventory/master.db）

---

## 実行履歴

### 2025-11-28: upload_queueバランス調整

**目的:** 各アカウントのpending状態のキューを1,000件に調整

**実行前の状態:**
```
base_account_1: 11件（pending）
base_account_2: 600件（pending）
合計: 611件
```

**実行コマンド:**
```bash
python sourcing/scripts/import_candidates_to_master.py \
  --account-limits "base_account_1:989,base_account_2:400"
```

**実行結果:**
```
base_account_1: 938件（pending） ← 927件追加
base_account_2: 977件（pending） ← 377件追加
合計: 1,915件（達成率: 95.8%）
```

**追加されたデータ:**
- products: 新規商品情報をSP-APIから取得・登録
- listings: 各アカウントへの出品情報を登録
- upload_queue: 出品キューに追加（pending状態）

**発生したエラー:**
- NOT_FOUND: 一部のASINがAmazonで見つからない
- QuotaExceeded: SP-APIのクォータ超過（レート制限）

**カスタマイズ内容:**
- `--account-limits` オプションを追加
- アカウント別の件数指定機能を実装
- `_assign_accounts()` メソッドを拡張

---

## 推奨される運用フロー

### 日次運用（新規ASIN収集）

```bash
# 1. カテゴリベースで10,000件の新規ASINを抽出
python sourcing/scripts/auto_extract_by_categories.py \
  --target-new-asins 10000 \
  --sample-size 1000 \
  --asins-per-category 2000 \
  --max-categories 20 \
  --sales-min 300 \
  --price-min 2500 \
  --output "base_asins_$(date +%Y%m%d).txt" \
  --report "extraction_report_$(date +%Y%m%d).md"

# 2. DBに登録
python sourcing/scripts/register_asins_from_file.py \
  --input "base_asins_$(date +%Y%m%d).txt"

# 3. レポートを確認
cat "extraction_report_$(date +%Y%m%d).md"
```

### 週次運用（出品連携）

```bash
# 1. DRY RUNで確認
python sourcing/scripts/import_candidates_to_master.py --dry-run

# 2. 本番実行（1000件ずつ）
python sourcing/scripts/import_candidates_to_master.py --limit 1000

# 3. 出品キューの確認
# （既存の upload_executor で処理される）
```

---

このレポートは、C:\Users\hiroo\Documents\GitHub\ecauto\sourcing ディレクトリの完全な調査に基づいており、ASINの抽出からsourcing.dbへの登録までの全プロセスを網羅しています。
