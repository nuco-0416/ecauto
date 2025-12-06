# ISSUE #024: BASE禁止商品によるアカウント規制対応

**作成日**: 2025-12-01
**優先度**: 🔴 最高
**ステータス**: 🚧 対応中
**関連**: BASE Account 1 規制

---

## 📋 概要

BASEアカウント1で禁止商品の出品によりアカウント規制を受けた。
現在の出品状況を分析し、問題商品を特定、および今後の再発防止策を実装する。

---

## 🔍 調査結果サマリー

### 出品状況
- **base_account_1**: 12,872件の出品
  - 掲載済み（listed）: 12,081件
  - ペンディング（pending）: 791件
- **base_account_2**: 3,694件の出品
  - 掲載済み（listed）: 25件
  - ペンディング（pending）: 3,669件

### 問題商品の検出結果

#### base_account_1
- **問題商品候補**: 2,517件（汚染率: 19.55%）
- **ステータス別**:
  - 掲載済み: 2,356件
  - ペンディング: 161件

**カテゴリ別内訳**:
| カテゴリ | 件数 | BASE利用規約該当項目 |
|---------|------|---------------------|
| vehicles（自動車・バイク関連） | 831件 | 項目35 |
| adult（アダルト関連） | 545件 | 項目4 |
| medical（医薬品・医療機器） | 513件 | 項目24 |
| child（児童関連） | 289件 | 項目5 |
| rmt（ゲームアカウント・RMT） | 278件 | 項目21 |
| weapons（武器関連） | 71件 | 項目3 |
| tobacco（タバコ関連） | 50件 | 項目10 |
| その他 | 40件 | - |

#### base_account_2
- **問題商品候補**: 238件（汚染率: 6.44%）
- **ステータス別**:
  - 掲載済み: 25件
  - ペンディング: 213件

**カテゴリ別内訳**:
| カテゴリ | 件数 |
|---------|------|
| medical | 103件 |
| adult | 49件 |
| child | 48件 |
| rmt | 19件 |
| vehicles | 18件 |
| その他 | 1件 |

#### クロスアカウント汚染
- **複数アカウントに出品されている問題商品**: 238件

---

## ⚠️ 重要な注意点

### 誤検出の可能性

キーワードマッチングによる検出のため、以下のような誤検出が多数含まれています：

| 検出キーワード | 誤検出例 | 理由 |
|--------------|---------|------|
| 「AV」 | ゲーミングモニター | 製品名に「AV」が含まれる |
| 「アダルト」 | キャットフード（アダルトチキン） | 成猫用フードの表記 |
| 「薬」 | ポカリスエット、アミノバイタル | スポーツ飲料・サプリメント |
| 「児童」 | 児童書、児童用商品 | 正規の児童向け商品 |
| 「バイク」 | バイク用タイヤ、グローブ | バイク部品・アクセサリー（問題なし） |

### 本当に注意が必要な商品

#### 🔴 高リスク（即時削除推奨）
1. **医療機器・検査キット**（BASE項目24）
   - 体温計、血圧計、PCR検査キット、妊娠検査薬など
2. **タバコ関連**（BASE項目10）
   - 電子タバコ、IQOS、Ploom、アイコスなど
3. **武器・刀剣類**（BASE項目3）
   - サバイバルナイフ、エアガン、スタンガンなど

#### 🟡 中リスク（手動確認推奨）
1. **電動キックボード・フル電動自転車**（BASE項目35）
2. **ゲームアカウント・RMT**（BASE項目21）
3. **現金・金券類**（BASE項目11, 13）

---

## 📊 生成されたレポートファイル

1. **base_account1_listings.csv**
   - base_account_1の全出品リスト（12,872件）

2. **prohibited_items_report.csv**
   - 問題商品候補の詳細レポート（2,517件）
   - カラム: asin, sku, platform_item_id, status, visibility, title_ja, category, brand, matched_categories, matched_keywords, selling_price

3. **cross_account_contamination_report.csv**
   - アカウント別汚染レポート

4. **multi_account_prohibited_items.csv**
   - 複数アカウントに出品されている問題商品（238件）

---

## 🎯 対応アクションプラン

### Phase 1: 緊急対応（即時）

#### ✅ 完了
- [x] 出品状況の調査
- [x] 問題商品の検出
- [x] クロスアカウント汚染の確認
- [x] レポート生成

#### 🚧 進行中
- [ ] **base_account_2の危険商品を即時削除**（最優先）
  - 対象: 238件の問題商品候補
  - 方法: BASE APIで一括削除
  - 目的: アカウント2の規制を防ぐ

- [ ] **base_account_1の規制理由の特定**
  - BASEからの通知を確認
  - 具体的な問題商品ASINを特定

### Phase 2: 短期対応（1週間以内）

- [ ] base_account_1の高リスク商品を削除
  - medical、tobacco、weaponsカテゴリの手動確認
  - 該当商品の非公開化・削除

- [ ] NGキーワード設定の強化
  - `config/ng_keywords.json`を拡張
  - ホワイトリストの追加

### Phase 3: 中期対応（1ヶ月以内）

- [ ] **禁止商品チェッカーの実装**
  - `inventory/core/prohibited_item_checker.py`
  - `config/prohibited_items.json`
  - カテゴリベース判定
  - キーワードベース判定（ホワイトリスト対応）
  - リスクスコアアルゴリズム

- [ ] 既存パイプラインへの統合
  - `sourcing/scripts/import_candidates_to_master.py`
  - `inventory/scripts/add_new_products.py`

- [ ] 既存出品の段階的クリーニング
  - Week 1: 高リスク商品
  - Week 2: 中リスク商品
  - Week 3: 低リスク商品の確認と誤検出の修正

---

## 🛠️ 技術仕様

### 禁止商品チェッカー仕様

**アーキテクチャ**:
```
┌─────────────────┐
│ ソーシング      │
│ (SellerSprite)  │
└────────┬────────┘
         │ ASIN候補
         ▼
┌─────────────────────────────┐
│ ProhibitedItemChecker        │
│  - カテゴリベース判定        │
│  - キーワードベース判定      │
│  - ブランドベース判定        │
│  - リスクスコア算出          │
└────────┬────────────────────┘
         │ リスクスコア 0-100
         ▼
  - 80以上: 自動ブロック
  - 50-79: 手動レビュー
  - 0-49: 自動承認
         │
         ▼
┌─────────────────┐
│ SP-API取得      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ master.db登録   │
│ upload_queue追加│
└─────────────────┘
```

**主要コンポーネント**:
1. `ProhibitedItemChecker`クラス
2. `config/prohibited_items.json`（設定ファイル）
3. ホワイトリスト機構
4. リスクスコアアルゴリズム

---

## 📈 期待される効果

1. **即時効果**
   - base_account_2の規制リスクを回避
   - 既存の問題商品を削除

2. **短期効果**
   - 新規出品時の問題商品を事前ブロック
   - ソーシング効率の向上（問題商品を事前除外）

3. **長期効果**
   - アカウント規制リスクの大幅低減
   - 出品品質の向上
   - 運用コストの削減

---

## 📎 関連ドキュメント

- [詳細分析レポート](../BASE_PROHIBITED_ITEMS_ANALYSIS.md)
- [BASEの出品禁止商品リスト](https://official.thebase.in/pages/prohibited-items)
- [プロジェクトREADME](../../README.md)

---

## 📝 メモ

- 誤検出が多いため、手動確認が必須
- 特に「AV」「アダルト」「薬」「児童」「バイク」は誤検出率が高い
- ホワイトリストの充実が重要
- 目視確認と並行してチェッカーを実装
- 本日23:59までに新規商品の出品を完了させる必要あり

---

## 🔄 実施内容の追記（2025-12-01 更新）

### ✅ 完了した作業

#### 1. base_account_2の危険商品削除
- **未掲載商品（213件）**: データベースから削除完了 ✅
- **掲載済み商品（25件）**: BASE API削除エラーのため手動対応が必要

#### 2. 禁止商品チェッカーの実装
- **設定ファイル**: `config/prohibited_items.json` 作成完了 ✅
- **チェッカークラス**: `inventory/core/prohibited_item_checker.py` 実装完了 ✅
- **統合**: `inventory/scripts/add_new_products.py` に統合完了 ✅

#### 3. 目視確認フィードバックに基づく改善

**誤検出の削減**:
- ホワイトリストに以下を追加：
  - 「ロリータ」「ロリータファッション」（ファッションカテゴリ）
  - 「バイク」「オートバイ」「車」「乗り物」「ワッペン」（バイク用品・玩具）
  - 「子供」「幼稚園」「保育園」「男の子」「女の子」「入学」（児童用品）
  - 「サプリメント」「ビタミン」（栄養補助食品）

**有効なキーワードの追加**:
- 厳格キーワードに「医薬部外品」「医薬品」「薬事法」を追加（weight: 90）
- 厳格キーワードに「加熱式たばこ」を追加（weight: 100）

**カテゴリベースの禁止強化**:
- `blocked`カテゴリを新設（即座にスコア100で自動ブロック）:
  - `Health & Personal Care > Medications`
  - `Health & Personal Care > Over-the-Counter Medication`
  - `Tobacco Products`
- high_riskカテゴリを拡充:
  - `Health & Personal Care > Health Care`
  - `Health & Personal Care > Household Supplies > Household Medical Supplies`
  - `Health & Personal Care > Over-the-Counter Medication`
  - `Tobacco Products`

#### 4. sourcing/ への統合準備
- `sourcing/scripts/import_candidates_to_master.py` に禁止商品チェッカーを統合 ✅
- ソーシング時にもカテゴリベースで自動ブロック可能に

#### 5. ブロックされたアイテムの可視化機能
- **JSON出力**: `logs/blocked_items_YYYYMMDD_HHMMSS.json` ✅
  - 機械可読形式で構造化データを保存
  - プラットフォーム、アカウント、閾値などのメタ情報も含む
- **ログ出力**: `logs/blocked_items_YYYYMMDD_HHMMSS.log` ✅
  - ターミナルで読みやすい人間可読形式
  - 各アイテムの詳細情報を整形して表示
- **自動出力**: `--check-prohibited` オプション使用時、ブロックされたアイテムがあれば自動的にファイル出力

### 📊 改善効果の予想

**誤検出の削減**:
- 「バイク」関連: 831件 → **大幅減少**（バイク用品はホワイトリスト化）
- 「児童」関連: 289件 → **大幅減少**（児童用品はホワイトリスト化）
- 「ロリ」関連: → **削減**（ロリータファッションはホワイトリスト化）

**真の問題商品の検出強化**:
- 「医薬部外品」: **新規追加**（育毛剤などを検出）
- 「加熱式たばこ」: **新規追加**（IQOS互換機などを検出）
- カテゴリベース: **即座にブロック**（医薬品・タバコカテゴリ）

### 🚀 使い方（更新版）

#### 禁止商品チェッカー付きで新規商品を追加

```bash
# 推奨: 禁止商品チェックを有効化
python inventory/scripts/add_new_products.py \
  --asin-file asins.txt \
  --platform base \
  --account-id base_account_1 \
  --use-sp-api \
  --check-prohibited \
  --yes
```

#### ソーシング時も自動的に禁止商品をブロック

```bash
# sourcing → master.db の連携時に自動チェック
python sourcing/scripts/import_candidates_to_master.py
```

### ⚠️ 残存課題

#### ~~BASE API削除エラー~~ ✅ 解決済み
- **問題ファイル**:
  - `platforms/base/scripts/delete_items.py`
  - `platforms/base/core/api_client.py` (delete_itemメソッド)
- **エラー**: 400 Bad Request（アクセストークンが不正）
- **対応**: ✅ **修正完了** - [ISSUE_025](./ISSUE_025_base_delete_items_api_fix_RESOLVED.md)で解決
  - 原因1: トークンファイルにスコープ情報が欠落
  - 原因2: BaseAPIClientの初期化方法が誤っていた
  - 両方の問題を修正し、商品削除が正常に動作することを確認

#### ~~掲載済み商品の削除~~ ✅ 削除完了
- **対象**: 25件
- **リスト**: `base_account2_listed_prohibited_asins.txt`
- **実施日**: 2025-12-01
- **結果**:
  - 成功: 23件（BASE APIで削除完了、マスタDBも更新）
  - 失敗: 0件
  - 未発見: 2件（B09JS7R48N, B0BPKYK8SM - すでに削除済みまたは未アップロード）
- **方法**: BASE API経由で削除（ISSUE_025で修正完了）
- **実行コマンド**:
  ```bash
  # ASINリストから削除
  python platforms/base/scripts/delete_items.py \
    --asins 'B09JS7R48N,B0BPKYK8SM,...' \
    --account-id base_account_2 \
    --yes
  ```

### 🎉 Phase 1完了（緊急対応）

**base_account_2の保護完了**:
- 未掲載商品（213件）: データベースから削除 ✅
- 掲載済み商品（23件）: BASE APIで削除完了 ✅
- **合計**: 236件の禁止商品候補を削除
- **結果**: base_account_2のアカウント規制リスクを大幅に低減
