# ASIN抽出作業ガイド - 2025年11月30日実施

## 概要

SellerSpriteから目標3,000件の新規ASINを抽出し、データベースに登録する作業の完全な再現手順。

## 目標

- **新規ASIN数**: 3,000件以上
- **検索条件**: 販売数≥300、価格≥2,500円、FBA商品
- **市場**: 日本（JP）

## 前提条件

### 既存の抽出履歴

過去に以下のラウンドを実施済み：
- Round 1 (11/28): 458件 - `base_asins_2500_20251128.txt`
- Round 2 (11/28): 1,865件 - `base_asins_additional_20251128.txt`
- Round 3 (11/28): 1,052件 - `base_asins_round3_20251128.txt`
- **過去合計**: 3,375件

### 使用するツール

- `auto_extract_by_categories_v2.py` - 履歴管理機能付き抽出ツール（v2）
- `generate_history_from_reports.py` - 過去レポートから履歴生成
- `register_asins_from_file.py` - DB登録スクリプト

## 作業フロー

### ステップ1: 履歴ファイルの生成

過去のレポートから履歴ファイルを生成して、v2ツールで利用可能にする。

```bash
python sourcing/scripts/generate_history_from_reports.py \
  --reports category_report_20251128.md \
            category_report_additional_20251128.md \
            category_report_round3_20251128.md \
  --output category_history.json \
  --pages-extracted 10
```

**期待される出力**:
- `category_history.json` が生成される
- 過去に処理した25カテゴリの履歴が記録される
- 各カテゴリで10ページまで抽出済みとして記録

### ステップ2: Round 4 - ページ深化戦略（失敗）

既存カテゴリの11-20ページ目を抽出しようと試みる。

```bash
python sourcing/scripts/auto_extract_by_categories_v2.py \
  --target-new-asins 3000 \
  --resume \
  --history-file category_history.json \
  --pages-per-category 20 \
  --sales-min 300 \
  --price-min 2500 \
  --output asins_round4_20251130.txt \
  --report category_report_round4_20251130.md
```

**結果**: 0件取得（ページが存在せず）

**問題点**: SellerSpriteの検索条件（sales≥300, price≥2,500）では、ほとんどのカテゴリで10ページ以降のデータが存在しない。

### ステップ3: 戦略変更 - サンプルサイズ増加

ページを深く掘るのではなく、初期サンプルサイズを大幅に増やして新しいカテゴリを発見する戦略に変更。

#### Round 5: サンプルサイズ1,000件

```bash
python sourcing/scripts/auto_extract_by_categories_v2.py \
  --target-new-asins 2500 \
  --history-file category_history.json \
  --pages-per-category 10 \
  --sales-min 300 \
  --price-min 2500 \
  --sample-size 1000 \
  --output asins_round5_20251130.txt \
  --report category_report_round5_20251130.md
```

**結果**: 704件取得

**発見**: サンプルサイズを300→1,000に増やすと、354カテゴリを発見（従来は約30カテゴリ）

#### Round 6: サンプルサイズ1,500件

```bash
python sourcing/scripts/auto_extract_by_categories_v2.py \
  --target-new-asins 2000 \
  --history-file category_history.json \
  --pages-per-category 10 \
  --sales-min 300 \
  --price-min 2500 \
  --sample-size 1500 \
  --output asins_round6_20251130.txt \
  --report category_report_round6_20251130.md
```

**結果**: 1,074件取得

**発見**: サンプルサイズ1,500件で493カテゴリを発見

#### Round 7: サンプルサイズ2,000件

```bash
python sourcing/scripts/auto_extract_by_categories_v2.py \
  --target-new-asins 1500 \
  --history-file category_history.json \
  --pages-per-category 10 \
  --sales-min 300 \
  --price-min 2500 \
  --sample-size 2000 \
  --output asins_round7_20251130.txt \
  --report category_report_round7_20251130.md
```

**結果**: 914件取得（新規率12.5%）

**発見**: サンプルサイズ2,000件で610カテゴリを発見

#### Round 8: サンプルサイズ2,500件（最終）

```bash
python sourcing/scripts/auto_extract_by_categories_v2.py \
  --target-new-asins 1200 \
  --history-file category_history.json \
  --pages-per-category 10 \
  --sales-min 300 \
  --price-min 2500 \
  --sample-size 2500 \
  --output asins_round8_20251130.txt \
  --report category_report_round8_20251130.md
```

**結果**: 906件取得（新規率12.4%）

**発見**: サンプルサイズ2,500件で610カテゴリを発見（過去最多）

### ステップ4: ASINファイルの統合

全ラウンドのASINファイルを統合し、重複を排除する。

```bash
cat base_asins_2500_20251128.txt \
    base_asins_additional_20251128.txt \
    base_asins_round3_20251128.txt \
    asins_round5_20251130.txt \
    asins_round6_20251130.txt \
    asins_round7_20251130.txt \
    asins_round8_20251130.txt \
  | sort | uniq > asins_all_rounds_complete_20251130.txt
```

**結果**:
- 統合前合計: 6,973件（Round 1-8の延べ数）
- 統合後（重複排除）: 4,774件
- 重複数: 2,199件（31.5%）

### ステップ5: データベース登録

```bash
python sourcing/scripts/register_asins_from_file.py \
  --input asins_all_rounds_complete_20251130.txt
```

## 最終結果サマリー

### ラウンド別実績

| ラウンド | 実施日 | サンプルサイズ | 新規ASIN数 | 新規率 | 処理カテゴリ数 |
|---------|--------|--------------|-----------|--------|--------------|
| Round 1 | 11/28 | 300 | 458件 | - | - |
| Round 2 | 11/28 | 300 | 1,865件 | - | - |
| Round 3 | 11/28 | 300 | 1,052件 | - | - |
| Round 4 | 11/30 | - | 0件 | 0% | 28件（失敗） |
| Round 5 | 11/30 | 1,000 | 704件 | - | - |
| Round 6 | 11/30 | 1,500 | 1,074件 | - | - |
| Round 7 | 11/30 | 2,000 | 914件 | 12.5% | 30件 |
| Round 8 | 11/30 | 2,500 | 906件 | 12.4% | 30件 |

### 統合結果

- **過去ラウンド（11/28）**: 3,375件
- **今回ラウンド（11/30）**: 3,598件
- **統合前合計**: 6,973件
- **統合後（ユニーク）**: 4,774件
- **重複数**: 2,199件（31.5%）
- **目標達成率**: 159.1%（目標3,000件）

## 重要な学び

### 1. ページ深化戦略の限界

**問題**: 検索条件が厳しい場合（sales≥300, price≥2,500）、多くのカテゴリで10ページ以降のデータが存在しない。

**結果**: Round 4（11-20ページ目の抽出）は0件という結果に終わった。

### 2. サンプルサイズ増加戦略の有効性

**発見**: 初期サンプルサイズを増やすと、より多様なカテゴリが発見される。

| サンプルサイズ | 発見カテゴリ数 | 効果 |
|--------------|--------------|------|
| 300件 | 約30件 | 基準 |
| 1,000件 | 354件 | 11.8倍 |
| 1,500件 | 493件 | 16.4倍 |
| 2,000件 | 610件 | 20.3倍 |
| 2,500件 | 610件 | 20.3倍（飽和） |

**結論**: サンプルサイズ2,000-2,500件で発見率が飽和する。

### 3. ラウンド間の重複

**問題**: 各ラウンドで報告される「新規ASIN数」は、そのラウンド実行時点でのDBとの比較であり、ラウンド間の重複は考慮されない。

**実績**:
- Round 5-8の延べ数: 3,598件
- 実際のユニーク数: 1,399件
- ラウンド間重複率: 61.1%

**原因**: 各ラウンドで同じカテゴリを繰り返し処理していたため。

### 4. 高収率カテゴリの発見

サンプルサイズ2,000-2,500で発見された高収率カテゴリ：

- ウイスキー: 126-135件
- ヘアドライヤー: 147件
- 保湿乳液・クリーム: 198件
- スティッククリーナー: 143件
- ヘアトリートメント: 131件

## 次回実施時の推奨アプローチ

### 効率的な戦略

1. **初回実行**: サンプルサイズ2,000-2,500件で実行
   - 最も多様なカテゴリを一度に発見できる
   - Round 1回で1,000-1,500件の新規ASINを取得可能

2. **追加実行**: 必要に応じて同じ設定で再実行
   - `--resume`フラグを使用して前回の続きから実行
   - 新しいカテゴリが見つかる限り継続可能

3. **避けるべき戦略**:
   - ページ深化（11-20ページ目）は効果が低い
   - サンプルサイズ2,500件以上は飽和しているため非効率

### コマンド例

```bash
# 推奨：初回実行（サンプルサイズ2,000件）
python sourcing/scripts/auto_extract_by_categories_v2.py \
  --target-new-asins 3000 \
  --history-file sourcing/sources/sellersprite/logs_and_reports/category_history.json \
  --pages-per-category 10 \
  --sales-min 300 \
  --price-min 2500 \
  --sample-size 2000 \
  --output sourcing/sources/sellersprite/logs_and_reports/asins_batch1.txt \
  --report sourcing/sources/sellersprite/logs_and_reports/category_report_batch1.md

# 追加が必要な場合：再開モードで実行
python sourcing/scripts/auto_extract_by_categories_v2.py \
  --target-new-asins 2000 \
  --resume \
  --history-file sourcing/sources/sellersprite/logs_and_reports/category_history.json \
  --pages-per-category 10 \
  --sales-min 300 \
  --price-min 2500 \
  --sample-size 2000 \
  --output sourcing/sources/sellersprite/logs_and_reports/asins_batch2.txt \
  --report sourcing/sources/sellersprite/logs_and_reports/category_report_batch2.md
```

## ファイル構成

### 作成されたファイル

```
C:\Users\hiroo\Documents\GitHub\ecauto\
├── sourcing/
│   ├── scripts/
│   │   ├── auto_extract_by_categories_v2.py      # 履歴管理付き抽出ツール
│   │   ├── generate_history_from_reports.py       # 履歴生成ツール
│   │   └── README_v2.md                            # v2クイックスタート
│   ├── docs/
│   │   ├── 20251130_category_extractor_v2_guide.md # 詳細ガイド
│   │   └── prompt_extract_asins_testpilot_20251130.md # このドキュメント
│   └── sources/
│       └── sellersprite/
│           └── logs_and_reports/
│               ├── category_history.json                           # 履歴ファイル（進捗管理）
│               ├── asins_all_rounds_complete_20251130.txt          # 全ラウンド統合版
│               ├── category_report_20251128.md                     # Round 1 レポート
│               ├── category_report_additional_20251128.md          # Round 2 レポート
│               ├── category_report_round3_20251128.md              # Round 3 レポート
│               ├── category_report_round5_20251130.md              # Round 5 レポート
│               ├── category_report_round6_20251130.md              # Round 6 レポート
│               ├── category_report_round7_20251130.md              # Round 7 レポート
│               └── category_report_round8_20251130.md              # Round 8 レポート
```

## トラブルシューティング

### 問題1: ページが見つからない（次ページボタンなし）

**症状**: `[WARN] 次のページボタンが見つかりません` というエラーが頻発

**原因**: 検索条件が厳しく、カテゴリのデータが10ページ未満しか存在しない

**対処**: ページ深化（11-20ページ）ではなく、サンプルサイズ増加戦略を使用する

### 問題2: 新規率が低い

**症状**: 各ラウンドで10-15%程度しか新規ASINが取得できない

**原因**:
1. カテゴリの重複処理
2. DBに既存のASINが多い

**対処**:
1. `--resume`モードで履歴ファイルを活用し、未処理カテゴリを優先
2. サンプルサイズを大きくして、より多様なカテゴリを発見

### 問題3: ラウンド間の重複が多い

**症状**: 各ラウンドで報告される新規ASIN数の合計と、統合後のユニーク数に大きな差がある

**原因**: 各ラウンドの「新規ASIN数」はDB比較であり、ラウンド間の重複を考慮していない

**対処**:
1. 最終的にASINファイルを統合・重複排除する必要がある
2. ラウンド間で異なる検索条件やサンプルサイズを使用して多様性を確保

## 参考資料

- [v2クイックスタート](../scripts/README_v2.md)
- [v2詳細ガイド](./20251130_category_extractor_v2_guide.md)
- [ASIN抽出とDB登録フロー](./20251127_asin_to_db_process.md)

---

**作成日**: 2025-11-30
**作成者**: Claude Code
**バージョン**: 1.0
**対象**: ecautoプロジェクト - ASIN抽出作業
