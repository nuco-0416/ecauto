# カテゴリ別ASIN抽出ツール v2 - クイックスタート

## 🚀 3,000件追加取得の手順

### 前提条件
- 過去に `auto_extract_by_categories.py` (v1) で抽出済み
- 各カテゴリで10ページ（1,000件）まで取得済み

### ステップ1: 履歴ファイルを生成（初回のみ）

過去のレポートから履歴を生成：

```bash
python sourcing/scripts/generate_history_from_reports.py \
  --reports sourcing/sources/sellersprite/logs_and_reports/category_report_20251128.md \
            sourcing/sources/sellersprite/logs_and_reports/category_report_additional_20251128.md \
            sourcing/sources/sellersprite/logs_and_reports/category_report_round3_20251128.md \
  --output sourcing/sources/sellersprite/logs_and_reports/category_history.json \
  --pages-extracted 10
```

**実行結果**:
```
処理中: category_report_20251128.md
  → 10カテゴリを抽出
処理中: category_report_additional_20251128.md
  → 20カテゴリを抽出
処理中: category_report_round3_20251128.md
  → 25カテゴリを抽出

合計 25 カテゴリを履歴に追加
✅ 履歴ファイルを生成しました: sourcing/sources/sellersprite/logs_and_reports/category_history.json
```

### ステップ2: 11-20ページ目を抽出

```bash
python sourcing/scripts/auto_extract_by_categories_v2.py \
  --target-new-asins 3000 \
  --resume \
  --history-file sourcing/sources/sellersprite/logs_and_reports/category_history.json \
  --pages-per-category 20 \
  --output sourcing/sources/sellersprite/logs_and_reports/asins_round4_20251130.txt \
  --report sourcing/sources/sellersprite/logs_and_reports/category_report_round4_20251130.md
```

**実行時間**: 約30-40分（25カテゴリ × 10ページ × 約1.5分/ページ）

**期待される結果**:
- 新規ASIN数: 1,000-2,000件（重複除く）
- 処理カテゴリ数: 15-25件（目標達成次第）

### ステップ3: DB登録

```bash
python sourcing/scripts/register_asins_from_file.py \
  --input sourcing/sources/sellersprite/logs_and_reports/asins_round4_20251130.txt
```

## 📁 生成されるファイル

```
C:\Users\hiroo\Documents\GitHub\ecauto\sourcing\sources\sellersprite\logs_and_reports\
├── category_history.json                    # 履歴ファイル（進捗管理）
├── asins_round4_20251130.txt                # 抽出ASIN一覧
└── category_report_round4_20251130.md       # 抽出レポート
```

## ⚙️ パラメータ解説

| パラメータ | 説明 | デフォルト |
|-----------|------|----------|
| `--target-new-asins` | 目標新規ASIN数 | 3000 |
| `--resume` | 再開モード（履歴から続きを処理） | - |
| `--pages-per-category` | 各カテゴリの最大ページ数（1-20） | 10 |
| `--history-file` | 履歴ファイルのパス | 必須 |

## 🔍 履歴ファイルの確認

```bash
# 現在の進捗を確認
python -c "import json; print(json.dumps(json.load(open('sourcing/sources/sellersprite/logs_and_reports/category_history.json')), indent=2, ensure_ascii=False))"
```

## 💡 Tips

### さらに追加で取得したい場合

履歴ファイルは自動更新されるため、再度実行すれば新しいカテゴリから取得します：

```bash
# ステップ2を再実行（新しいカテゴリを自動探索）
python sourcing/scripts/auto_extract_by_categories_v2.py \
  --target-new-asins 3000 \
  --resume \
  --history-file sourcing/sources/sellersprite/logs_and_reports/category_history.json \
  --pages-per-category 20 \
  --output sourcing/sources/sellersprite/logs_and_reports/asins_round5_20251130.txt \
  --report sourcing/sources/sellersprite/logs_and_reports/category_report_round5_20251130.md
```

### 通常モード（履歴なし）で実行

```bash
# 新規にカテゴリを探索（履歴ファイルを新規作成）
python sourcing/scripts/auto_extract_by_categories_v2.py \
  --target-new-asins 3000 \
  --pages-per-category 10 \
  --history-file sourcing/sources/sellersprite/logs_and_reports/category_history.json \
  --output sourcing/sources/sellersprite/logs_and_reports/asins_new_batch.txt \
  --report sourcing/sources/sellersprite/logs_and_reports/report_new_batch.md
```

## 📖 詳細ドキュメント

- [使用ガイド](../docs/20251130_category_extractor_v2_guide.md) - 詳細な使い方とトラブルシューティング
- [ASIN抽出とDB登録フロー](../docs/20251127_asin_to_db_process.md) - 基本的なワークフロー

## 🎯 次回以降の実行

このツールは**永続的に使用可能**です。次回も同じ手順で実行できます：

1. 履歴ファイル（`sourcing/sources/sellersprite/logs_and_reports/category_history.json`）を保持
2. ステップ2から実行（履歴ファイルを指定）
3. 自動的に未処理のカテゴリから続きを抽出

---

**作成日**: 2025-11-30
**バージョン**: v2.0
**保存場所**: `C:\Users\hiroo\Documents\GitHub\ecauto\sourcing\scripts\`
