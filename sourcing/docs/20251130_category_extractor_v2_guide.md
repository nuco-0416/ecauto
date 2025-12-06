# カテゴリ別ASIN抽出ツール v2 使用ガイド

## 概要

`auto_extract_by_categories_v2.py` は、カテゴリごとのページ取得履歴を管理し、前回の続きから抽出を再開できる拡張版スクリプトです。

## v1からの主な改善点

| 機能 | v1 | v2 |
|------|----|----|
| **ページ取得履歴** | なし | JSON形式で保存 |
| **再開機能** | なし | 前回の続きから実行可能 |
| **最大ページ数** | 10ページ（固定） | 1-20ページ（可変） |
| **進捗の永続化** | なし | カテゴリごとに記録 |

## ファイル構成

```
sourcing/
├── scripts/
│   ├── auto_extract_by_categories.py         # v1（従来版）
│   ├── auto_extract_by_categories_v2.py      # v2（拡張版）★
│   └── generate_history_from_reports.py      # 履歴生成ツール★
├── docs/
│   └── 20251130_category_extractor_v2_guide.md  # このガイド★
└── sources/
    └── sellersprite/
        └── logs_and_reports/
            └── category_history.json           # 履歴ファイル（永続保存）★
```

## 使用フロー

### ステップ1: 過去のレポートから履歴ファイルを生成

過去に実行したレポート（`category_report_*.md`）から、カテゴリごとの取得履歴を生成します。

```bash
python sourcing/scripts/generate_history_from_reports.py \
  --reports sourcing/sources/sellersprite/logs_and_reports/category_report_20251128.md \
            sourcing/sources/sellersprite/logs_and_reports/category_report_additional_20251128.md \
            sourcing/sources/sellersprite/logs_and_reports/category_report_round3_20251128.md \
  --output sourcing/sources/sellersprite/logs_and_reports/category_history.json \
  --pages-extracted 10
```

**パラメータ説明**:
- `--reports`: 過去のレポートファイル（複数指定可能）
- `--output`: 出力先の履歴ファイル
- `--pages-extracted`: 各カテゴリで既に取得したページ数（デフォルト: 10）

**出力例**:
```json
{
  "categories": {
    "ドラッグストア > 栄養補助食品 > プロテイン > ホエイプロテイン": {
      "nodeIdPaths": "[\"160384011:169976011:344024011:3457068051:3457072051\"]",
      "pages_extracted": 10,
      "last_updated": "2025-11-30T10:00:00",
      "asins_count": 0,
      "sample_count": 36
    },
    ...
  },
  "metadata": {
    "total_asins": 0,
    "last_run": null,
    "generated_from_reports": ["category_report_20251128.md", ...],
    "generated_at": "2025-11-30T10:00:00"
  }
}
```

### ステップ2: 前回の続きから抽出を実行

履歴ファイルを使って、各カテゴリの11ページ目から20ページ目まで抽出します。

```bash
python sourcing/scripts/auto_extract_by_categories_v2.py \
  --target-new-asins 3000 \
  --resume \
  --history-file sourcing/sources/sellersprite/logs_and_reports/category_history.json \
  --pages-per-category 20 \
  --output sourcing/sources/sellersprite/logs_and_reports/asins_round4_20251130.txt \
  --report sourcing/sources/sellersprite/logs_and_reports/category_report_round4_20251130.md
```

**パラメータ説明**:
- `--target-new-asins`: 目標新規ASIN数（デフォルト: 3000）
- `--resume`: 再開モード（履歴から続きを処理）
- `--history-file`: 履歴ファイルのパス（必須）
- `--pages-per-category`: 各カテゴリの最大ページ数（1-20）
  - 例: 10 → 1-10ページ目まで
  - 例: 20 → 1-20ページ目まで（履歴で10ページ済みなら11-20ページ目を処理）
- `--output`: 出力ASIN一覧ファイル
- `--report`: 出力レポートファイル

### ステップ3: DB登録

抽出したASINをデータベースに登録します。

```bash
python sourcing/scripts/register_asins_from_file.py \
  --input sourcing/sources/sellersprite/logs_and_reports/asins_round4_20251130.txt
```

## 実行例

### 例1: 初回実行（履歴ファイルなし）

履歴ファイルが存在しない場合は、通常モードで新規にカテゴリを探索します。

```bash
python sourcing/scripts/auto_extract_by_categories_v2.py \
  --target-new-asins 3000 \
  --pages-per-category 10 \
  --history-file sourcing/sources/sellersprite/logs_and_reports/category_history.json \
  --output sourcing/sources/sellersprite/logs_and_reports/asins_batch1.txt \
  --report sourcing/sources/sellersprite/logs_and_reports/report_batch1.md
```

### 例2: 再開実行（前回の続き）

既存の履歴ファイルを使って、前回の続きから実行します。

```bash
python sourcing/scripts/auto_extract_by_categories_v2.py \
  --target-new-asins 3000 \
  --resume \
  --history-file sourcing/sources/sellersprite/logs_and_reports/category_history.json \
  --pages-per-category 20 \
  --output sourcing/sources/sellersprite/logs_and_reports/asins_batch2.txt \
  --report sourcing/sources/sellersprite/logs_and_reports/report_batch2.md
```

### 例3: さらに深く掘る（20ページ超）

SellerSpriteの制限により、20ページが最大です。それ以上は取得できません。

## 履歴ファイルの構造

```json
{
  "categories": {
    "カテゴリ名": {
      "nodeIdPaths": "[\"カテゴリID\"]",
      "pages_extracted": 10,          // 取得済みページ数
      "last_updated": "2025-11-30T10:00:00",
      "asins_count": 458,              // 取得したASIN数
      "sample_count": 36               // サンプル内の商品数
    }
  },
  "metadata": {
    "total_asins": 3375,               // 累計新規ASIN数
    "last_run": "2025-11-30T10:00:00", // 最終実行日時
    "generated_from_reports": [...],   // 元レポート（生成時のみ）
    "generated_at": "2025-11-30T10:00:00"  // 生成日時（生成時のみ）
  }
}
```

## トラブルシューティング

### Q1: 履歴ファイルが見つからない

**エラー**: `FileNotFoundError: category_history.json`

**解決策**:
- `generate_history_from_reports.py` で履歴ファイルを生成してください
- または、`--resume` フラグを外して通常モードで実行してください

### Q2: 取得済みページ数がわからない

**回答**:
- v1で `--asins-per-category 1000` を指定した場合: **10ページ取得済み**
  - 1ページ = 100件
  - 1000件 = 10ページ
- v1で `--asins-per-category 2000` を指定した場合: **20ページ取得済み**（最大）

### Q3: 新規率が低い

**回答**:
- カテゴリの深いページ（11-20ページ目）は、人気商品が少なく重複率が高くなる傾向があります
- より多様なカテゴリを探索するには、`--max-categories` を増やしてください

### Q4: ページ移動でエラーが出る

**エラー**: `[ERROR] ページ移動エラー`

**解決策**:
- SellerSpriteの制限により、特定カテゴリで20ページ未満しかない場合があります
- エラーが出ても、取得できたデータは保存されます
- 別のカテゴリで再試行してください

## ページ深さと取得数の目安

| ページ範囲 | 件数 | 新規率（推定） | 用途 |
|-----------|------|---------------|------|
| 1-10ページ | 1,000件 | 15-35% | 初回抽出 |
| 11-20ページ | 1,000件 | 5-15% | 追加抽出 |

## 推奨ワークフロー

1. **初回実行**: v1またはv2で10ページまで抽出
2. **DB登録**: 取得したASINを登録
3. **履歴生成**: レポートから履歴ファイルを作成
4. **追加実行**: v2で11-20ページ目を抽出
5. **DB登録**: 追加ASINを登録
6. **必要に応じて繰り返し**: 新規カテゴリを探索

## まとめ

- **v2の主な利点**: ページ取得履歴の管理、再開機能、深いページまで抽出可能
- **推奨**: 既存のv1実行履歴がある場合は、履歴ファイルを生成してv2で続きを実行
- **制限**: SellerSpriteの仕様上、1カテゴリあたり最大20ページ（2,000件）まで

## 関連ドキュメント

- [20251127_asin_to_db_process.md](./20251127_asin_to_db_process.md) - ASIN抽出とDB登録の基本フロー
- [prompt_extract_asins_testpilot_20251127.md](./prompt_extract_asins_testpilot_20251127.md) - 過去の作業履歴
