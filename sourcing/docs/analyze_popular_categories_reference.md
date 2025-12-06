# analyze_popular_categories.py リファレンス

## 概要

SellerSpriteから人気カテゴリを分析し、nodeIdPathsを抽出するスクリプト（スタンドアロン版）。
ランキング上位商品のカテゴリを分析して、売れ筋カテゴリとそのnodeIdPathsを特定します。

**v2.0の特徴**:
- 共通モジュール（`category_extractor`）を使用したクリーンな実装
- ProductResearchExtractorの不具合を回避
- コード重複を排除し、保守性を向上

## スクリプトパス

```
C:\Users\hiroo\Documents\GitHub\ecauto\sourcing\scripts\analyze_popular_categories.py
```

## 実行環境

```bash
C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe
```

## 基本的な使用方法

### 最小限の実行（デフォルト設定）

```bash
"C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe" "C:\Users\hiroo\Documents\GitHub\ecauto\sourcing\scripts\analyze_popular_categories.py"
```

デフォルト設定:
- サンプルサイズ: 500件
- トップNカテゴリ: 10件
- 販売数下限: 300
- 価格下限: 2500
- 市場: JP
- 出力先: `C:\Users\hiroo\Documents\GitHub\ecauto\sourcing\sources\sellersprite\popular_categories.json`

### パラメータ付き実行

```bash
"C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe" "C:\Users\hiroo\Documents\GitHub\ecauto\sourcing\scripts\analyze_popular_categories.py" \
  --sample-size 50 \
  --top-n 5 \
  --sales-min 300 \
  --price-min 2500 \
  --market JP
```

## パラメータ詳細

| パラメータ | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| `--sample-size` | int | 500 | 分析するサンプル数（最大: 2000） |
| `--top-n` | int | 10 | 抽出する上位カテゴリ数 |
| `--sales-min` | int | 300 | 月間販売数の最小値 |
| `--price-min` | int | 2500 | 価格の最小値（円） |
| `--market` | str | JP | 市場（JP, US, UK等） |
| `--output` | str | sourcing/sources/sellersprite/popular_categories.json | 出力ファイルパス |

## 出力形式

### 出力ファイルパス

デフォルト:
```
C:\Users\hiroo\Documents\GitHub\ecauto\sourcing\sources\sellersprite\popular_categories.json
```

### JSON構造

```json
[
  {
    "rank": 1,
    "category": "ドラッグストア > 栄養補助食品 > サプリメント・ビタミン > プロテイン > ホエイプロテイン",
    "count": 3,
    "percentage": 6.0,
    "nodeIdPaths": "[\"160384011:169976011:344024011:3457068051:3457072051\"]"
  },
  {
    "rank": 2,
    "category": "ドラッグストア > 日用品 > 洗濯・仕上げ剤 > ジェルボール型洗剤",
    "count": 3,
    "percentage": 6.0,
    "nodeIdPaths": "[\"160384011:170563011:170664011:4811678051\"]"
  }
]
```

### フィールド説明

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `rank` | int | ランキング順位 |
| `category` | string | カテゴリ名（階層構造） |
| `count` | int | サンプル内での商品数 |
| `percentage` | float | サンプル内での割合（%） |
| `nodeIdPaths` | string | AmazonのnodeIdPaths（JSON文字列） |

## 使用例

### 例1: 小規模なテスト分析

```bash
"C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe" "C:\Users\hiroo\Documents\GitHub\ecauto\sourcing\scripts\analyze_popular_categories.py" \
  --sample-size 50 \
  --top-n 5 \
  --sales-min 300 \
  --price-min 2500
```

### 例2: 大規模な本格分析

```bash
"C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe" "C:\Users\hiroo\Documents\GitHub\ecauto\sourcing\scripts\analyze_popular_categories.py" \
  --sample-size 1000 \
  --top-n 20 \
  --sales-min 500 \
  --price-min 3000
```

### 例3: カスタム出力先を指定

```bash
"C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe" "C:\Users\hiroo\Documents\GitHub\ecauto\sourcing\scripts\analyze_popular_categories.py" \
  --sample-size 500 \
  --top-n 10 \
  --output "C:\Users\hiroo\Documents\GitHub\ecauto\custom_categories.json"
```

## 処理フロー

1. **パラメータ解析**: コマンドライン引数を解析
2. **ブラウザセッション作成**: `create_browser_session()`でログイン済みブラウザを起動
3. **URL構築**: `build_product_research_url()`でフィルター条件付きURLを生成
4. **ページ遷移**: 商品リサーチページに直接遷移（UI操作を最小化）
5. **データ抽出**: `extract_asins_with_categories()`でASINとカテゴリ情報を取得
   - リスト表示への切り替え
   - 全行の展開
   - カテゴリとnodeIdPathsの抽出
6. **集計処理**: `Counter`でカテゴリごとに商品数を集計
7. **ランキング作成**: `most_common()`で上位Nカテゴリをランキング
8. **JSON出力**: 結果をJSONファイルに保存
9. **クリーンアップ**: ブラウザセッションを自動終了

## 依存関係

### 必須モジュール

**共通ユーティリティモジュール** (`category_extractor`):
- パス: `sourcing.sources.sellersprite.utils.category_extractor`
- 提供機能:
  - `log()`: タイムスタンプ付きログ出力
  - `build_product_research_url()`: フィルター条件付きURL構築
  - `extract_asins_with_categories()`: ASINとカテゴリ情報の抽出
  - `create_browser_session()`: ログイン済みブラウザセッション作成

### 外部ライブラリ

- `playwright`: ブラウザ自動化
- `python-dotenv`: 環境変数管理
- `argparse`: コマンドライン引数解析（標準ライブラリ）
- `asyncio`: 非同期処理（標準ライブラリ）

### 環境変数

`.env`ファイルの場所: `C:\Users\hiroo\Documents\GitHub\ecauto\sourcing\sources\sellersprite\.env`

必要な環境変数:
- `SELLERSPRITE_EMAIL`: SellerSpriteのメールアドレス
- `SELLERSPRITE_PASSWORD`: SellerSpriteのパスワード

## 実行時間の目安

| サンプルサイズ | 実行時間（目安） |
|--------------|----------------|
| 50件 | 約30秒 |
| 100件 | 約1分 |
| 500件 | 約3-5分 |
| 1000件 | 約7-10分 |

※ネットワーク状況やSellerSpriteのサーバー負荷により変動します

## エラーハンドリング

### 一般的なエラー

1. **ログインエラー**: SellerSpriteへのログインに失敗
   - `.env`ファイルの設定を確認
   - SellerSpriteのアカウント状態を確認

2. **データ抽出エラー**: 商品データの抽出に失敗
   - ネットワーク接続を確認
   - SellerSpriteのページ構造変更の可能性

3. **ファイル保存エラー**: JSONファイルの保存に失敗
   - 出力先ディレクトリの書き込み権限を確認
   - ディスク容量を確認

### デバッグモード

スクリプトは自動的にデバッグ情報を出力します:
- 最初の3件のデータサンプル
- カテゴリとnodeIdPathsの抽出状況
- セル情報の詳細（最初の商品のみ）

## 注意事項

1. **実行環境**: 必ず`venv`環境で実行してください
2. **タイムゾーン**: JSTを想定しています
3. **API制限**: SellerSpriteのAPIレート制限に注意
4. **データ鮮度**: 抽出されるデータはリアルタイムのランキングに基づきます
5. **nodeIdPaths形式**: JSON文字列として保存されるため、パース処理が必要な場合があります

## AIエージェント向け使用ガイド

### 自動実行時の推奨設定

```python
import subprocess
import json
from pathlib import Path

# 推奨パラメータ
params = {
    "sample_size": 500,
    "top_n": 10,
    "sales_min": 300,
    "price_min": 2500,
    "market": "JP"
}

# コマンド構築
cmd = [
    r"C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe",
    r"C:\Users\hiroo\Documents\GitHub\ecauto\sourcing\scripts\analyze_popular_categories.py",
    "--sample-size", str(params["sample_size"]),
    "--top-n", str(params["top_n"]),
    "--sales-min", str(params["sales_min"]),
    "--price-min", str(params["price_min"]),
    "--market", params["market"]
]

# 実行
result = subprocess.run(cmd, capture_output=True, text=True)

# 結果読み込み
output_path = Path(r"C:\Users\hiroo\Documents\GitHub\ecauto\sourcing\sources\sellersprite\popular_categories.json")
if output_path.exists():
    with open(output_path, "r", encoding="utf-8") as f:
        categories = json.load(f)
    print(f"取得カテゴリ数: {len(categories)}")
```

### nodeIdPathsの利用方法

```python
import json

# JSONからnodeIdPathsを抽出
def extract_node_id_paths(category_data):
    """カテゴリデータからnodeIdPathsを抽出"""
    node_paths = json.loads(category_data["nodeIdPaths"])
    return node_paths[0] if node_paths else None

# 使用例
with open(r"C:\Users\hiroo\Documents\GitHub\ecauto\sourcing\sources\sellersprite\popular_categories.json", "r", encoding="utf-8") as f:
    categories = json.load(f)

for category in categories:
    node_id_path = extract_node_id_paths(category)
    print(f"{category['category']}: {node_id_path}")
```

## バージョン履歴

- **v2.0** (2025-01-27): 共通モジュール化
  - `category_extractor`モジュールを使用したクリーンな実装に変更
  - ProductResearchExtractorの不具合を回避
  - コード重複を排除（約250行削減）
  - `create_browser_session()`による簡潔なブラウザ管理
  - 安定性と保守性の向上

- **v1.0** (2025-01-27): 初版作成
  - デフォルト出力先を`sourcing/sources/sellersprite/`に設定
  - カテゴリ情報とnodeIdPathsの同時抽出機能
  - ProductResearchExtractorに依存（非推奨）

## 関連ドキュメント

- **category_extractor.py**: 共通ユーティリティモジュール
  - パス: `C:\Users\hiroo\Documents\GitHub\ecauto\sourcing\sources\sellersprite\utils\category_extractor.py`
- **auto_extract_by_categories.py**: カテゴリ別ASIN自動抽出スクリプト
  - 同じ`category_extractor`モジュールを使用
  - パス: `C:\Users\hiroo\Documents\GitHub\ecauto\sourcing\scripts\auto_extract_by_categories.py`
- ecautoプロジェクト全体設計書

## アーキテクチャの改善点（v2.0）

### 共通モジュール化のメリット

1. **コード重複の排除**
   - `analyze_popular_categories.py`と`auto_extract_by_categories.py`で同じ処理を共有
   - 修正が1箇所で済むため、保守性が向上

2. **バグ回避**
   - ProductResearchExtractorの既知の不具合を回避
   - 実績のあるクリーンな実装を使用

3. **再利用性**
   - 他のスクリプトでも同じモジュールを利用可能
   - 一貫したコーディングスタイル

4. **テスタビリティ**
   - 各関数が独立しているため、単体テストが容易
   - モジュール単位でのテストが可能

### 実装の詳細

**create_browser_session()の利点**:
- コンテキストマネージャーによる自動クリーンアップ
- ログイン処理の共通化
- エラー時のブラウザ終了を保証

**build_product_research_url()の利点**:
- URLパラメータで全フィルター条件を指定
- UI操作（ボタンクリック等）を回避
- より安定した動作

**extract_asins_with_categories()の利点**:
- DOM操作を最小化
- ページネーション対応
- エラーハンドリングが充実

## サポート

問題が発生した場合は、以下を確認してください:
1. 実行ログの確認
2. `.env`ファイルの設定確認
3. SellerSpriteへの手動ログイン可否の確認
4. ネットワーク接続の確認
5. `category_extractor`モジュールのインポートエラーがないか確認
