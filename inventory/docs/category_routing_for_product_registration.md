# カテゴリルーティング機能

商品のカテゴリに基づいて、出品先アカウント（ショップ）を自動振り分けする機能。

**実装日**: 2025-12-11

---

## 概要

### 背景・目的

BASEで複数のショップ（アカウント）を運営する場合、カテゴリ特化ショップ（例: カメラ専門店、ガジェット専門店）を追加したいケースがある。

この機能により、商品のカテゴリ情報に基づいて自動的に適切なショップへ振り分けることが可能になる。

### 処理フロー

```
1. sourcing / ASINリスト
   ↓
2. products テーブル（SP-APIでcategory取得）
   ↓
3. listings テーブル ← ★ここでカテゴリルーティング実行
   ↓
4. upload_queue
```

**重要**: SP-API呼び出しタイミングは従来通りで変更なし。
ルーティングは `products.category` の値を参照するだけ。

---

## ファイル構成

| ファイル | 種別 | 役割 |
|----------|------|------|
| `config/category_routing.yaml` | 設定 | ルーティングルールの定義 |
| `common/category_router.py` | モジュール | 共通ルーティングロジック |
| `inventory/scripts/assign_products_to_account.py` | スクリプト | 既存商品を新ショップに追加 |
| `sourcing/scripts/import_candidates_to_master.py` | スクリプト | 新規商品インポート（`--use-category-routing` オプション追加） |

---

## 設定ファイル

### config/category_routing.yaml

```yaml
# ルーティング機能の有効/無効
enabled: true

# デフォルトアカウント（どのルールにもマッチしない場合）
default_account: "base_account_2"

# アカウント別ルーティングルール
accounts:
  # カメラ専門店
  base_account_3:
    priority: 1           # 優先度（小さい方が優先）
    keywords:             # カテゴリに含まれるキーワード（OR条件）
      - "カメラ"
      - "三脚"
      - "レンズ"
      - "フィルター"
      - "ストロボ"
      - "撮影"

  # ガジェット専門店
  base_account_gadget:
    priority: 2
    keywords:
      - "ヘッドホン"
      - "イヤホン"
      - "スピーカー"
      - "充電"
      - "モバイル"
      - "スマホ"
      - "タブレット"
```

### ルーティングの優先順位

1. `priority` が小さいアカウントから順にマッチング判定
2. `keywords` のいずれかがカテゴリパスに含まれればマッチ
3. どれにもマッチしない場合は `default_account` へ

### 全ジャンル対応ショップ

`keywords` を空にするか、設定を省略すると「全ジャンル受け入れ」となる。
この場合、`default_account` として機能する。

---

## 使い方

### 1. 既存商品を新ショップに追加

`assign_products_to_account.py` を使用。

```bash
# カテゴリルーティングで自動振り分け（dry-run）
python inventory/scripts/assign_products_to_account.py \
  --use-category-routing \
  --dry-run

# 手動でアカウントとカテゴリを指定
python inventory/scripts/assign_products_to_account.py \
  --account-id base_account_3 \
  --category-filter "カメラ,三脚,レンズ" \
  --dry-run

# 本番実行
python inventory/scripts/assign_products_to_account.py \
  --use-category-routing \
  --yes
```

**オプション**:

| オプション | 説明 |
|-----------|------|
| `--account-id` | 振り分け先アカウントID（`--use-category-routing` 使用時は不要） |
| `--category-filter` | カテゴリフィルター（カンマ区切り） |
| `--use-category-routing` | 設定ファイルに基づいて自動振り分け |
| `--platform` | プラットフォーム（デフォルト: base） |
| `--limit` | 処理する最大件数 |
| `--dry-run` | 実際の登録は行わず確認のみ |
| `--skip-queue` | upload_queueへの追加をスキップ |
| `--yes, -y` | 確認プロンプトをスキップ |

### 2. 新規商品インポート時のルーティング

`import_candidates_to_master.py` に `--use-category-routing` オプションを追加。

```bash
# カテゴリルーティングで自動振り分け
python sourcing/scripts/import_candidates_to_master.py \
  --use-category-routing \
  --dry-run

# 従来通りの動作（ランダム or account-limits指定）
python sourcing/scripts/import_candidates_to_master.py \
  --account-limits "base_account_2:1000,base_account_3:1000" \
  --dry-run
```

---

## 動作例

### 入力（products.category）

| ASIN | category |
|------|----------|
| B076LWRJK8 | 家電＆カメラ > フラッシュ・ストロボ |
| B0B3MTMZCC | ビューティー > 保湿ミスト・スプレー |
| B09LXWJ3TV | ビューティー > オールインワンスキンケア > フェイスケアセット |

### 設定（category_routing.yaml）

```yaml
accounts:
  base_account_3:
    priority: 1
    keywords: ["カメラ", "ストロボ"]
```

### 出力（振り分け結果）

| ASIN | マッチキーワード | 振り分け先 |
|------|------------------|------------|
| B076LWRJK8 | "カメラ" | base_account_3 |
| B0B3MTMZCC | (なし) | base_account_2（デフォルト） |
| B09LXWJ3TV | (なし) | base_account_2（デフォルト） |

---

## CategoryRouter API

### 基本的な使い方

```python
from common.category_router import CategoryRouter

# ルーターを初期化
router = CategoryRouter()

# ルーティングが有効か確認
if router.is_enabled:
    # カテゴリからアカウントを決定
    account_id = router.route("家電＆カメラ > カメラ用三脚")
    print(account_id)  # => "base_account_3"
```

### 主要メソッド

| メソッド | 説明 |
|---------|------|
| `route(category, available_accounts)` | カテゴリからアカウントを決定 |
| `route_batch(products, available_accounts)` | 複数商品を一括ルーティング |
| `get_account_for_category(category)` | ルーティング結果の詳細を取得 |
| `preview_routing(categories)` | ルーティング結果をプレビュー |
| `reload_config()` | 設定ファイルを再読み込み |

### プロパティ

| プロパティ | 説明 |
|-----------|------|
| `is_enabled` | ルーティングが有効かどうか |
| `default_account` | デフォルトアカウント |

---

## 注意事項

### SP-API呼び出しへの影響

- **影響なし**: ルーティングは `products.category` を参照するだけ
- SP-API呼び出しタイミングは従来通り（products登録時）

### account_config.json との関係

- ルーティング設定は `config/category_routing.yaml` で管理
- アカウントの有効/無効は `platforms/base/accounts/account_config.json` の `active` フラグで制御
- ルーティング先に指定したアカウントが `active: false` の場合、そのアカウントへの振り分けはスキップされる

### カテゴリ情報の取得元

- `products.category` カラムに保存されている日本語カテゴリパス
- 形式: `"カテゴリ1 > カテゴリ2 > カテゴリ3"`
- SP-API の `salesRanks` から取得（`integrations/amazon/sp_api_client.py`）

---

## トラブルシューティング

### ルーティングが動作しない

1. `config/category_routing.yaml` の `enabled: true` を確認
2. `keywords` が正しく設定されているか確認
3. 対象アカウントが `account_config.json` で `active: true` になっているか確認

### 期待通りに振り分けられない

1. `--dry-run` でルーティングプレビューを確認
2. `products.category` の値を確認（SQLiteで直接確認）
3. キーワードの部分一致になっているか確認（完全一致ではない）

```bash
# カテゴリ値の確認
sqlite3 inventory/data/master.db "SELECT asin, category FROM products WHERE asin='B076LWRJK8'"
```

---

## 関連ファイル

- `config/category_routing.yaml` - ルーティング設定
- `common/category_router.py` - ルーティングロジック
- `inventory/scripts/assign_products_to_account.py` - 既存商品振り分けスクリプト
- `sourcing/scripts/import_candidates_to_master.py` - 商品インポートスクリプト
- `platforms/base/accounts/account_config.json` - アカウント設定
- `integrations/amazon/sp_api_client.py` - SP-APIクライアント（category取得）

---

## 更新履歴

| 日付 | 内容 |
|------|------|
| 2025-12-11 | 初版作成。カテゴリルーティング機能実装 |
