# auto_extract_by_categories.py リファレンス

## 概要

**ファイルパス**: `C:\Users\hiroo\Documents\GitHub\ecauto\sourcing\scripts\auto_extract_by_categories.py`

カテゴリベースでASINを自動抽出するスクリプト。SellerSpriteの商品リサーチデータから、既存データとの重複を最小化しながら新規ASINを効率的に取得します。

### 主な特徴

- カテゴリ軸での抽出により重複を最小化
- 未開拓カテゴリを優先的に処理
- ブラウザセッションの再利用による高速化（1回のログインで全処理完了）
- リアルタイムでの重複チェック
- 目標件数に達するまで自動的にカテゴリを巡回

---

## 実行環境

### 必須要件

1. **Python環境**: `C:\Users\hiroo\Documents\GitHub\ecauto\venv`
2. **認証情報**: `sourcing/sources/sellersprite/.env` に以下を設定
   - `SELLERSPRITE_EMAIL`
   - `SELLERSPRITE_PASSWORD`
3. **データベース**: `sourcing/data/sourcing.db` に `sourcing_candidates` テーブルが存在

### 依存モジュール

```python
from sourcing.sources.sellersprite.utils.category_extractor import (
    build_product_research_url,
    extract_asins_with_categories,
    create_browser_session
)
```

---

## 使用方法

### 基本コマンド

```bash
./venv/Scripts/python.exe sourcing/scripts/auto_extract_by_categories.py \
  --target-new-asins <目標数> \
  --sample-size <サンプルサイズ> \
  --asins-per-category <カテゴリあたりの取得数> \
  --max-categories <最大カテゴリ数> \
  --sales-min <最小販売数> \
  --price-min <最小価格> \
  --output <出力ファイル> \
  --report <レポートファイル>
```

### コマンドライン引数

| 引数 | デフォルト | 説明 |
|------|-----------|------|
| `--target-new-asins` | 10000 | 目標新規ASIN数 |
| `--sample-size` | 1000 | 初期サンプルサイズ（最大: 2000） |
| `--asins-per-category` | 2000 | 各カテゴリの取得数（最大: 2000） |
| `--max-categories` | 20 | 最大処理カテゴリ数 |
| `--sales-min` | 300 | 月間販売数の最小値 |
| `--price-min` | 2500 | 価格の最小値（円） |
| `--market` | JP | 市場（JP, US, UK等） |
| `--output` | なし | 出力ファイルパス（ASIN一覧） |
| `--report` | なし | レポートファイルパス（Markdown形式） |

---

## 実行例

### 小規模テスト（100件の新規ASIN）

```bash
./venv/Scripts/python.exe sourcing/scripts/auto_extract_by_categories.py \
  --target-new-asins 100 \
  --sample-size 50 \
  --asins-per-category 100 \
  --max-categories 3 \
  --sales-min 300 \
  --price-min 2500 \
  --output test_asins.txt \
  --report test_report.md
```

**実行時間**: 約58秒
**期待される結果**: 100件以上の新規ASIN

### 本番実行（10,000件の新規ASIN）

```bash
./venv/Scripts/python.exe sourcing/scripts/auto_extract_by_categories.py \
  --target-new-asins 10000 \
  --sample-size 1000 \
  --asins-per-category 2000 \
  --max-categories 20 \
  --sales-min 300 \
  --price-min 2500 \
  --output base_asins_category_$(date +%Y%m%d).txt \
  --report category_report_$(date +%Y%m%d).md
```

**実行時間**: 約15-20分（カテゴリ数による）
**期待される結果**: 10,000件以上の新規ASIN

### カスタムフィルター例

```bash
# 高価格帯・高売上の商品に絞る
./venv/Scripts/python.exe sourcing/scripts/auto_extract_by_categories.py \
  --target-new-asins 5000 \
  --sales-min 500 \
  --price-min 5000 \
  --output premium_asins.txt
```

---

## 処理フロー

### ステップ1: 初期サンプリング

1. ブラウザセッションを作成（SellerSpriteにログイン）
2. 指定されたフィルター条件でURLを構築
3. 商品リサーチページからサンプルデータを取得
4. カテゴリ情報（category, nodeIdPaths）を抽出

### ステップ2: カテゴリ統計分析

1. サンプルデータからカテゴリごとの商品数をカウント
2. カテゴリを商品数の多い順にソート
3. トップ5カテゴリをログ出力

### ステップ3: 既存DBとの比較

1. `sourcing_candidates` テーブルからカテゴリ分布を取得
2. サンプルカテゴリと既存カテゴリを比較
3. 未開拓カテゴリを特定

### ステップ4: カテゴリの優先順位付け

1. 未開拓カテゴリを最優先
2. 既存カテゴリを次点として配置
3. `max-categories` まで制限

### ステップ5: カテゴリ別抽出ループ

各カテゴリについて:
1. nodeIdPathsでフィルターしたURLを構築
2. カテゴリ内の商品データを取得
3. 既存DBおよび今回抽出済みのASINと重複チェック
4. 新規ASINのみを追加
5. 目標件数に達したら終了

### ステップ6: 結果保存

1. 新規ASINをテキストファイルに保存（`--output`指定時）
2. 実行レポートをMarkdown形式で保存（`--report`指定時）

---

## 出力形式

### ASINファイル（`--output`）

```
B08XXXXX01
B08XXXXX02
B08XXXXX03
...
```

- 1行に1つのASIN
- 重複なし
- アルファベット順にソート

### レポートファイル（`--report`）

Markdown形式で以下の情報を含む:

```markdown
# カテゴリベースASIN自動抽出レポート

**実行日時**: 2025-11-27 15:36:55

## 📊 抽出結果サマリー

| 指標 | 値 |
|------|------|
| 新規ASIN数 | 115件 |
| 総抽出ASIN数 | 254件 |
| 重複ASIN数 | 139件 |
| 新規率 | 45.3% |
| 処理カテゴリ数 | 3件 |

## 📂 処理カテゴリ一覧

1. **ドラッグストア > 健康食品 > サプリメント・ビタミン > プロテイン > ホエイプロテイン**
   - サンプル内商品数: 3件
   - nodeIdPaths: `["160384011:169976011:344024011:3457068051:3457072051"]`

...

## ⚙️ 実行パラメータ

```
目標新規ASIN数: 100件
初期サンプルサイズ: 50件
...
```
```

---

## パフォーマンス情報

### 最適化の詳細

**改善前**（v1.0）:
- ログイン回数: カテゴリ数 + 1回
- 実行時間（3カテゴリ）: 約88秒

**改善後**（v2.0 - 現在）:
- ログイン回数: 1回のみ（ブラウザセッション再利用）
- 実行時間（3カテゴリ）: 約58秒
- **改善率**: 34%高速化

### 実行時間の目安

| カテゴリ数 | 目標ASIN数 | 実行時間（目安） |
|----------|----------|--------------|
| 3 | 100 | 約1分 |
| 5 | 1,000 | 約3-5分 |
| 10 | 5,000 | 約10-15分 |
| 20 | 10,000 | 約15-25分 |

※ネットワーク状況やSellerSpriteのレスポンス速度により変動

---

## エラーハンドリング

### よくあるエラーと対処法

#### 1. 認証エラー

```
ValueError: 環境変数 SELLERSPRITE_EMAIL と SELLERSPRITE_PASSWORD が設定されていません
```

**対処法**:
- `sourcing/sources/sellersprite/.env` ファイルを確認
- 認証情報が正しく設定されているか確認

#### 2. データベースエラー

```
[ERROR] サンプリングでデータが取得できませんでした
```

**対処法**:
- `sourcing/data/sourcing.db` が存在するか確認
- `sourcing_candidates` テーブルが作成されているか確認

#### 3. タイムアウトエラー

```
TimeoutError: page.goto: Timeout 30000ms exceeded
```

**対処法**:
- ネットワーク接続を確認
- SellerSpriteのサイトが正常に動作しているか確認
- タイムアウト値を増やす（スクリプト内の `timeout=30000` を変更）

#### 4. カテゴリ情報が取得できない

```
[ERROR] カテゴリ情報が取得できませんでした
```

**対処法**:
- フィルター条件を緩和（`sales_min`, `price_min` を下げる）
- `sample_size` を増やす
- SellerSpriteの画面レイアウトが変更されていないか確認

---

## データベーススキーマ

### sourcing_candidates テーブル

スクリプトが参照するテーブル:

```sql
CREATE TABLE sourcing_candidates (
    asin TEXT PRIMARY KEY,
    category TEXT,
    -- その他のカラム
);
```

**重要**: `category` カラムは既存カテゴリの分析に使用されます。

---

## AIエージェント使用時の注意事項

### 推奨される使用シナリオ

1. **新規ASIN収集**: 既存データとの重複を最小化したい場合
2. **カテゴリ多様化**: 特定カテゴリに偏らないデータ収集
3. **定期実行**: 週次・月次での新規ASIN追加

### 実行前の確認事項

```bash
# 1. 環境変数の確認
./venv/Scripts/python.exe -c "import os; from pathlib import Path; from dotenv import load_dotenv; env_path = Path('sourcing/sources/sellersprite/.env'); load_dotenv(dotenv_path=env_path); email = os.getenv('SELLERSPRITE_EMAIL'); password = os.getenv('SELLERSPRITE_PASSWORD'); print('OK: Email and Password are set' if (email and password) else 'ERROR: Missing credentials')"

# 2. データベースの確認
./venv/Scripts/python.exe -c "import sqlite3; conn = sqlite3.connect('sourcing/data/sourcing.db'); cursor = conn.cursor(); cursor.execute('SELECT name FROM sqlite_master WHERE type=\"table\" AND name=\"sourcing_candidates\"'); result = cursor.fetchone(); conn.close(); print('OK: sourcing_candidates table exists' if result else 'ERROR: table not found')"
```

### パラメータ選択のガイドライン

#### 初回実行（データベースが空）

```bash
--target-new-asins 10000
--sample-size 1000
--asins-per-category 2000
--max-categories 20
```

#### 追加実行（既存データあり）

```bash
--target-new-asins 5000
--sample-size 500
--asins-per-category 1000
--max-categories 10
```

#### テスト実行

```bash
--target-new-asins 100
--sample-size 50
--asins-per-category 100
--max-categories 3
```

---

## 連携スクリプト

### 前処理スクリプト

なし（単独で実行可能）

### 後処理スクリプト

抽出されたASINは以下のスクリプトで利用可能:

1. **価格データ取得**: `sourcing/scripts/get_pricing_data.py`
2. **詳細データ取得**: `sourcing/scripts/fetch_asin_details.py`
3. **登録処理**: `sourcing/scripts/register_candidates.py`

### 実行例（連携）

```bash
# 1. ASIN抽出
./venv/Scripts/python.exe sourcing/scripts/auto_extract_by_categories.py \
  --target-new-asins 1000 \
  --output new_asins.txt

# 2. 価格データ取得
./venv/Scripts/python.exe sourcing/scripts/get_pricing_data.py \
  --input new_asins.txt

# 3. 登録処理
./venv/Scripts/python.exe sourcing/scripts/register_candidates.py \
  --input new_asins.txt
```

---

## トラブルシューティング

### デバッグモード

スクリプト内のログ出力を確認:

```python
# スクリプト内で自動的にタイムスタンプ付きログが出力される
[15:36:55] 【ステップ1】初期サンプリングを開始...
[15:36:55]   サンプルサイズ: 50件
[15:36:55]   → 50件のデータを取得
[15:36:55]   → カテゴリ情報あり: 50件 / 50件
```

### ブラウザの目視確認

ヘッドレスモードを無効化（デフォルト）:

```python
# スクリプト内: create_browser_session(headless=False)
```

ブラウザの動作を目視で確認できます。

### 統計情報の確認

実行後の統計情報をチェック:

```
============================================================
抽出完了
============================================================
新規ASIN数: 115件
処理カテゴリ数: 3件
総抽出ASIN数: 254件
重複ASIN数: 139件
新規率: 45.3%
```

**新規率が低い（<30%）場合**:
- フィルター条件を調整（`sales_min`, `price_min`を変更）
- 異なるカテゴリを選択（`max_categories`を増やす）

---

## バージョン履歴

### v2.0（現在）- 2025-11-27

- ブラウザセッション再利用による高速化（34%改善）
- ログイン回数を1回に削減
- パフォーマンス最適化

### v1.0 - 2025-11-27

- 初期リリース
- カテゴリベース抽出機能
- 未開拓カテゴリの優先処理

---

## 関連ドキュメント

- [analyze_popular_categories_reference.md](./analyze_popular_categories_reference.md) - カテゴリ分析スクリプト
- [category_based_extraction_plan.md](./category_based_extraction_plan.md) - カテゴリベース抽出の計画書
- [sellersprite_authentication_and_category_extraction.md](./sellersprite_authentication_and_category_extraction.md) - SellerSprite認証とカテゴリ抽出の詳細

---

## サポート

問題が発生した場合:

1. ログ出力を確認
2. 関連ドキュメントを参照
3. デバッグモード（ブラウザ目視）で実行
4. 小規模パラメータでテスト実行

---

**最終更新**: 2025-11-27
**メンテナ**: ecauto プロジェクトチーム
