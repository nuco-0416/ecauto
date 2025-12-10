# 商品登録パイプライン

sourcing_candidates から master.db への商品登録処理に関するドキュメント。

## 設計思想

### 問題の背景

従来の `import_candidates_to_master.py` では、以下の問題があった：

1. **重複チェックのタイミング問題**
   - SP-API呼び出し（時間コスト大）の**後**に重複チェックが行われていた
   - 例: 2000件処理を指定 → 800件が重複 → 実際に新規登録されるのは1200件
   - SP-APIは1件あたり約12秒かかるため、重複分の時間が無駄になる

2. **オペレーター期待値とのギャップ**
   - 「2000件処理」と指定した場合、オペレーターは「2000件の新規登録完了」を期待する
   - しかし実際には「2000件を投入し、重複を除いた残りが登録される」という動作だった

### 解決方針

**フェーズ分割アプローチ**を採用：

```
フェーズ1: 重複チェック＋候補準備（SP-API不要、高速）
    ↓
フェーズ2: SP-API呼び出し＋商品登録（フィルタ済みASINのみ）
```

これにより：
- SP-API呼び出し前に「何件処理可能か」が確定
- 候補不足の場合、時間を消費する前にオペレーターが判断可能
- 上流のsourcingプロセスへのフィードバックが容易

### テーブル間の関係

```
sourcing.db                      master.db
┌─────────────────────┐         ┌─────────────────┐
│ sourcing_candidates │         │    products     │ ← 商品マスタ（ASIN = PK）
│ - status='candidate'│─────────│                 │
│ - status='duplicate'│         └────────┬────────┘
│ - status='imported' │                  │ FK
└─────────────────────┘         ┌────────┴────────┐
                                │    listings     │ ← 出品情報
                                │    upload_queue │ ← 出品キュー
                                └─────────────────┘
```

**重要**: listings/upload_queue は products の外部キー参照を持つ。
したがって、**productsテーブルでの重複チェックのみで十分**。
productsに存在しないASINがlistings/upload_queueに存在する場合は設計上のバグ。

---

## 現状の実装状況

### 実装済み

| スクリプト | 役割 | ステータス |
|-----------|------|-----------|
| `delete_exist_asin_candidate.py` | フェーズ1: 重複チェック＋候補準備 | **実装済み** |
| `import_candidates_to_master.py` | フェーズ2: SP-API呼び出し＋登録 | 既存（改修不要） |

### 処理フロー

```
[フェーズ1] delete_exist_asin_candidate.py
├─ sourcing_candidates から status='candidate' を取得
├─ products テーブルで重複チェック
├─ 重複ASIN → status='duplicate' に更新（論理削除）
├─ 要求件数に達するか確認
└─ 出力: 処理可能件数、不足件数

    ↓ （候補が十分な場合のみ次へ）

[フェーズ2] import_candidates_to_master.py
├─ sourcing_candidates から status='candidate' を取得
├─ products テーブルで既存確認（SP-APIスキップ判定）
├─ 新規ASINのみ SP-API で商品情報取得
├─ products / listings / upload_queue に登録
└─ status='imported' に更新
```

### ステータス遷移

```
sourcing_candidates.status:

  'candidate'  ─┬─→ 'duplicate'  （productsに既存、フェーズ1で更新）
                │
                └─→ 'imported'   （登録完了、フェーズ2で更新）
```

---

## スクリプトの使い方

### フェーズ1: 重複チェック

```bash
# dry-runで確認（実際の更新なし）
/home/nuc_o/github/ecauto/venv/bin/python \
  /home/nuc_o/github/ecauto/sourcing/scripts/delete_exist_asin_candidate.py \
  --count 2000 --dry-run

# 本番実行（重複ASINをstatus='duplicate'に更新）
/home/nuc_o/github/ecauto/venv/bin/python \
  /home/nuc_o/github/ecauto/sourcing/scripts/delete_exist_asin_candidate.py \
  --count 2000
```

**オプション**:
| オプション | 必須 | 説明 |
|-----------|------|------|
| `--count N` | Yes | 必要なASIN件数 |
| `--dry-run` | No | 確認のみ（更新しない） |

**出力例（成功）**:
```
=== 重複チェック完了 ===
要求件数:       2000件
候補総数:       7501件
重複除外:        503件（status='duplicate'に更新）
処理可能:       6998件

  要求件数を満たしています
  次のステップ: import_candidates_to_master.py --limit 2000
```

**出力例（候補不足）**:
```
=== 重複チェック完了 ===
要求件数:       8000件
候補総数:       7501件
重複除外:        503件
処理可能:       6998件

  候補が 1002件 不足しています
  sourcingの追加実行を検討してください
```

**終了コード**:
- `0`: 要求件数を満たした
- `1`: 候補不足

### フェーズ2: 商品登録

```bash
# dry-runで確認
/home/nuc_o/github/ecauto/venv/bin/python \
  /home/nuc_o/github/ecauto/sourcing/scripts/import_candidates_to_master.py \
  --limit 2000 --dry-run

# 本番実行
/home/nuc_o/github/ecauto/venv/bin/python \
  /home/nuc_o/github/ecauto/sourcing/scripts/import_candidates_to_master.py \
  --limit 2000
```

**主要オプション**:
| オプション | 説明 |
|-----------|------|
| `--limit N` | 処理する最大件数 |
| `--dry-run` | 確認のみ |
| `--account-limits` | アカウント別件数指定（例: `base_account_1:1000,base_account_2:1000`） |
| `--products-only` | productsテーブルのみ登録（listings/queueスキップ） |
| `--no-queue` | upload_queueへの追加をスキップ |
| `--use-category-routing` | カテゴリ別アカウント振り分け（[詳細](../../inventory/docs/category_routing_for_product_registration.md)） |

---

## 推奨ワークフロー

### 通常の商品登録（2000件の場合）

```bash
# Step 1: 重複チェック（dry-run）
venv/bin/python sourcing/scripts/delete_exist_asin_candidate.py --count 2000 --dry-run

# Step 2: 重複チェック（本番）
venv/bin/python sourcing/scripts/delete_exist_asin_candidate.py --count 2000

# Step 3: 商品登録（dry-run）
venv/bin/python sourcing/scripts/import_candidates_to_master.py --limit 2000 --dry-run

# Step 4: 商品登録（本番）
venv/bin/python sourcing/scripts/import_candidates_to_master.py --limit 2000
```

### 候補不足時の対応

```bash
# 重複チェックで不足が判明した場合
venv/bin/python sourcing/scripts/delete_exist_asin_candidate.py --count 2000
# → "候補が 500件 不足しています" と表示

# 対応1: 処理可能件数で進める
venv/bin/python sourcing/scripts/import_candidates_to_master.py --limit 1500

# 対応2: sourcingを追加実行してから再度チェック
# （sourcingの追加実行後）
venv/bin/python sourcing/scripts/delete_exist_asin_candidate.py --count 2000
```

---

## 将来的な改善計画

1. **ラッパースクリプトの作成**
   - フェーズ1 → フェーズ2 を連続実行
   - 候補不足時の自動判断

2. **自動化パイプラインへの組み込み**
   - cronやschedule連携
   - 候補不足時のアラート通知

3. **パフォーマンス最適化**
   - 重複チェックのバッチクエリ化（現状は1件ずつ確認）

---

## 関連ファイル

- `sourcing/scripts/delete_exist_asin_candidate.py` - 重複チェックスクリプト
- `sourcing/scripts/import_candidates_to_master.py` - 商品登録スクリプト
- `inventory/scripts/assign_products_to_account.py` - 既存商品を新ショップに追加
- `inventory/core/master_db.py` - master.dbのスキーマ定義
- `sourcing/data/sourcing.db` - sourcing_candidatesテーブル
- `inventory/data/master.db` - products/listings/upload_queueテーブル
- `config/category_routing.yaml` - カテゴリルーティング設定
- [カテゴリルーティング詳細](../../inventory/docs/category_routing_for_product_registration.md) - カテゴリ特化ショップへの自動振り分け機能

---

## 更新履歴

| 日付 | 内容 |
|------|------|
| 2025-12-11 | 初版作成。delete_exist_asin_candidate.py 実装 |
| 2025-12-11 | カテゴリルーティング機能追加（`--use-category-routing` オプション） |
