# ASIN抽出からDB登録までのワークフロー

**作成日**: 2025-11-27
**対象**: CLIエージェント（今後の作業用プロンプト）
**目的**: SellerSpriteから新規ASINを抽出し、sourcing.dbに登録する一連のプロセス

---

## 📋 概要

このドキュメントは、SellerSpriteからASINを抽出し、`sourcing_candidates`テーブルに登録する一連のワークフローを記載しています。重複を最小化しながら、効率的に新規ASINを取得する方法を説明します。

---

## 🎯 目標

- SellerSpriteから指定件数（例: 2,000件）の新規ASINを取得
- 既存DB（`sourcing.db`）との重複を最小化
- カテゴリベースの抽出により、多様なASINを取得

---

## 📂 関連ファイル

### スクリプト
- **抽出スクリプト**: `sourcing/scripts/auto_extract_by_categories.py`
- **DB登録スクリプト**: `sourcing/scripts/register_asins_from_file.py`

### データベース
- **DB**: `sourcing/data/sourcing.db`
- **対象テーブル**: `sourcing_candidates`

### 環境変数
- **認証情報**: `sourcing/sources/sellersprite/.env`
  - `SELLERSPRITE_EMAIL`
  - `SELLERSPRITE_PASSWORD`

---

## 🔄 ワークフロー

### ステップ1: 初回ASIN抽出

#### 目的
- 初回の大量ASIN抽出（目標件数に対して少し少なめに設定）

#### コマンド例
```bash
./venv/Scripts/python.exe sourcing/scripts/auto_extract_by_categories.py \
  --target-new-asins 2000 \
  --sample-size 500 \
  --asins-per-category 1000 \
  --max-categories 5 \
  --sales-min 300 \
  --price-min 2500 \
  --output "base_asins_2000_20251127.txt" \
  --report "category_report_20251127.md"
```

#### パラメータ説明
- `--target-new-asins`: 目標新規ASIN数
- `--sample-size`: 初期サンプルサイズ（最大2,000）
- `--asins-per-category`: 各カテゴリでの取得数（最大2,000）
- `--max-categories`: 処理する最大カテゴリ数
- `--sales-min`: 月間販売数の最小値
- `--price-min`: 価格の最小値（円）
- `--output`: 出力ファイルパス
- `--report`: レポートファイルパス（Markdown形式）

#### 期待される結果
- 目標に近い件数のASINファイルが生成される
- 一部のカテゴリで取得可能数が限られている場合があるため、目標に届かない可能性がある

#### 注意点
- **文字エンコーディングエラー**: 絵文字使用時に`cp932`エラーが発生する場合がある
  - 修正済み: `auto_extract_by_categories.py:142`で絵文字を削除

---

### ステップ2: 追加ASIN抽出（目標未達の場合）

#### 目的
- 初回で目標に届かなかった場合、追加でASINを取得

#### コマンド例
```bash
./venv/Scripts/python.exe sourcing/scripts/auto_extract_by_categories.py \
  --target-new-asins 500 \
  --sample-size 500 \
  --asins-per-category 1000 \
  --max-categories 10 \
  --sales-min 300 \
  --price-min 2500 \
  --output "base_asins_additional_500_20251127.txt" \
  --report "category_report_additional_20251127.md"
```

#### 注意点
- **重複の発生**: 同じカテゴリから抽出すると、前回と重複する
- **解決策**: DB登録後に再実行することで重複を回避（次のステップで説明）

---

### ステップ3: ASINファイルの統合

#### 目的
- 複数回の抽出結果を統合し、重複を排除

#### コマンド例
```bash
cat base_asins_2000_20251127.txt base_asins_additional_500_20251127.txt | sort -u > base_asins_combined_20251127.txt
wc -l base_asins_combined_20251127.txt
```

#### 重要な発見
- **重複の実態**: 同じカテゴリから抽出した場合、ほぼすべてが重複する可能性がある
  - 例: 1回目1,546件 + 2回目670件 = 統合後1,547件（669件が重複）

#### 教訓
- **DB登録を先に行う**: 統合ではなく、DB登録後に再実行する方が効率的

---

### ステップ4: DBへの登録

#### 目的
- 抽出したASINを`sourcing_candidates`テーブルに登録
- 以降の抽出で重複を自動的に回避

#### コマンド例
```bash
./venv/Scripts/python.exe sourcing/scripts/register_asins_from_file.py \
  --input base_asins_combined_20251127.txt
```

#### 処理内容
- 各ASINについて既存チェックを実施
- 新規の場合: `INSERT INTO sourcing_candidates`
- 既存の場合: `discovered_at`を更新

#### 登録されるデータ
```sql
INSERT INTO sourcing_candidates (
    asin,
    source,
    status,
    discovered_at
) VALUES (?, 'sellersprite', 'candidate', ?)
```

#### 結果例
```
総ASIN数:     1547件
新規登録:     1547件
既存更新:     0件
```

---

### ステップ5: DB登録後の追加抽出

#### 目的
- DB登録後、既存ASINとの重複を避けて新規ASINのみを取得

#### コマンド例
```bash
./venv/Scripts/python.exe sourcing/scripts/auto_extract_by_categories.py \
  --target-new-asins 500 \
  --sample-size 500 \
  --asins-per-category 1000 \
  --max-categories 10 \
  --sales-min 300 \
  --price-min 2500 \
  --output "base_asins_additional_round2_20251127.txt" \
  --report "category_report_round2_20251127.md"
```

#### 重要な違い
- **新規率の変化**: DB登録前は87.5% → DB登録後は25.2%
- **これは正常**: 既存ASINとの重複チェックが正しく機能している証拠

#### 期待される結果
- 最初の数カテゴリは100%重複（新規0件）
- 新しいカテゴリに到達すると新規ASINが取得できる

#### 実例（20251127）
```
カテゴリ1〜5: 新規0件（既にDB登録済み）
カテゴリ6: ペット用品 > 猫 > キャットフード > ドライ（249件の新規）
カテゴリ7: 食品・飲料・お酒 > 飲料 > お茶（81件の新規）
カテゴリ8: 家電＆カメラ > 携帯電話 > モバイルバッテリー（323件の新規）
```

---

### ステップ6: 追加ASINのDB登録

#### 目的
- 2回目以降の抽出結果もDBに登録

#### コマンド例
```bash
./venv/Scripts/python.exe sourcing/scripts/register_asins_from_file.py \
  --input base_asins_additional_round2_20251127.txt
```

#### 結果例
```
総ASIN数:     653件
新規登録:     653件
既存更新:     0件
```

---

### ステップ7: クリーンアップ

#### 目的
- プロジェクトディレクトリを整理し、不要な中間ファイルを削除

#### 削除すべきファイル
- 統合前の個別ファイル（統合版があるため不要）

#### コマンド例
```bash
rm base_asins_2000_20251127.txt base_asins_additional_500_20251127.txt
```

#### 保持すべきファイル
- 統合版ASINファイル: `base_asins_combined_20251127.txt`
- 2回目のASINファイル: `base_asins_additional_round2_20251127.txt`
- レポートファイル: `category_report_*.md`（すべて）

---

## ⚠️ 重要な注意点

### 1. 重複の最小化戦略

**❌ 非効率な方法**:
```
1. 抽出 → 2. 抽出 → 3. 統合 → 4. DB登録
```
→ 同じカテゴリから取得すると、ほぼ全て重複

**✅ 効率的な方法**:
```
1. 抽出 → 2. DB登録 → 3. 抽出 → 4. DB登録
```
→ DBが既存ASINとの重複を自動チェック

### 2. 文字エンコーディング

**問題**: Windows環境で絵文字を含むログ出力がエラーになる
```python
UnicodeEncodeError: 'cp932' codec can't encode character '\u2705'
```

**解決策**: スクリプト内の絵文字を通常文字に置換
```python
# 修正前
self.log(f"✅ 目標達成: {len(all_new_asins)}件の新規ASIN")

# 修正後
self.log(f"[OK] 目標達成: {len(all_new_asins)}件の新規ASIN")
```

### 3. カテゴリの枯渇

**現象**: 一部のカテゴリでは数百件しか取得できない
```
カテゴリ2: 食品・飲料・お酒 > ビール（211件で終了）
カテゴリ3: ノンアルコール飲料（106件で終了）
```

**対処法**:
- `--max-categories`を増やして、より多くのカテゴリを処理
- フィルター条件（`--sales-min`, `--price-min`）を調整

### 4. 新規率の変化

**DB登録前**:
- 新規率: 80-90%
- 理由: 初回抽出のため、ほとんどが新規

**DB登録後**:
- 新規率: 20-30%
- 理由: 既存ASINとの重複チェックが働いている（正常な動作）

---

## 📊 実績データ（20251127セッション）

### 最終結果
| 実行回 | 新規ASIN数 | 新規率 | 累計 |
|--------|-----------|--------|------|
| 1回目 | 1,547件 | - | 1,547件 |
| 2回目（DB登録後） | 653件 | 25.2% | 2,200件 |

### 目標達成
- **目標**: 2,000件
- **実績**: 2,200件
- **達成率**: 110%

---

## 🔧 トラブルシューティング

### エラー1: 文字エンコーディングエラー

**症状**:
```
UnicodeEncodeError: 'cp932' codec can't encode character '\u2705'
```

**原因**: Windowsコンソールが絵文字をサポートしていない

**解決策**: `auto_extract_by_categories.py`の絵文字を削除（142行目）

---

### エラー2: 認証エラー

**症状**:
```
ValueError: 環境変数 SELLERSPRITE_EMAIL と SELLERSPRITE_PASSWORD が設定されていません
```

**原因**: 環境変数が未設定

**解決策**:
1. `sourcing/sources/sellersprite/.env`ファイルを確認
2. 認証情報が正しく設定されているか確認

---

### エラー3: データベースが見つからない

**症状**:
```
[ERROR] データベースが見つかりません
```

**原因**: `sourcing.db`が未作成

**解決策**:
```bash
./venv/Scripts/python.exe sourcing/scripts/init_sourcing_db.py
```

---

### 問題4: 目標件数に届かない

**症状**: 指定した目標件数より少ないASINしか取得できない

**原因**: カテゴリごとの商品数が限られている

**解決策**:
1. `--max-categories`を増やす（例: 5 → 10 → 20）
2. フィルター条件を緩和（`--sales-min`や`--price-min`を下げる）
3. 複数回に分けて実行し、DB登録を挟む

---

### 問題5: 重複が多すぎる

**症状**: 新規率が極端に低い（5%以下）

**原因**: 同じカテゴリから繰り返し抽出している

**解決策**:
1. DB登録を先に行う
2. `--max-categories`を増やして、より多様なカテゴリを処理
3. サンプルサイズを増やして、より多くのカテゴリを発見

---

## 📝 ベストプラクティス

### 1. DB登録を優先
- **理由**: 重複チェックが自動化される
- **方法**: 抽出 → DB登録 → 抽出 → DB登録（繰り返し）

### 2. パラメータの調整
- **初回実行**: `--max-categories 5-10`（主要カテゴリを優先）
- **2回目以降**: `--max-categories 10-20`（多様性を重視）

### 3. 目標設定
- **推奨**: 目標の70-80%を初回で取得
- **例**: 目標2,000件 → 初回1,500件、2回目500件

### 4. ファイル管理
- **統合版を保持**: 中間ファイルは削除してOK
- **レポート保持**: 後で分析できるよう保存

### 5. 定期実行
- **頻度**: 週次または月次
- **方法**: 同じパラメータで実行し、DB登録
- **結果**: 自動的に新規ASINのみが追加される

---

## 🎯 今後の使い方

### さらにASINを追加する場合

1. **スクリプト実行**:
```bash
./venv/Scripts/python.exe sourcing/scripts/auto_extract_by_categories.py \
  --target-new-asins 500 \
  --sample-size 500 \
  --asins-per-category 1000 \
  --max-categories 10 \
  --sales-min 300 \
  --price-min 2500 \
  --output "base_asins_$(date +%Y%m%d).txt" \
  --report "category_report_$(date +%Y%m%d).md"
```

2. **DB登録**:
```bash
./venv/Scripts/python.exe sourcing/scripts/register_asins_from_file.py \
  --input "base_asins_$(date +%Y%m%d).txt"
```

3. **繰り返し**: 目標件数に達するまで1-2を繰り返す

---

## 📚 関連ドキュメント

- [auto_extract_by_categories_reference.md](./auto_extract_by_categories_reference.md) - スクリプトの詳細リファレンス
- [category_based_extraction_plan.md](./category_based_extraction_plan.md) - カテゴリベース抽出の設計書
- [init_sourcing_db.py](../scripts/init_sourcing_db.py) - DB初期化スクリプト

---

## 📞 サポート

問題が発生した場合:
1. ログ出力を確認
2. 関連ドキュメントを参照
3. デバッグモード（`--keep-browser`）で実行
4. 小規模パラメータでテスト実行

---

**最終更新**: 2025-11-27
**作成者**: Claude Code エージェント
**目的**: 今後のCLIエージェントが同様の作業を効率的に実行できるようにする
