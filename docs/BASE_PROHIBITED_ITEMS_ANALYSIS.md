# BASE 禁止商品分析レポート

**作成日**: 2025-12-01
**対象**: BASEアカウント（base_account_1, base_account_2）

## 1. 調査概要

BASEアカウント1で規制を受けたため、現在の出品状況をBASEの利用規約（禁止商品リスト）と照らし合わせて分析しました。

### 調査対象
- **base_account_1**: 12,872件の出品
- **base_account_2**: 3,694件の出品
- **合計**: 16,566件の出品

## 2. 問題商品の検出結果

### 2.1 キーワードマッチによる検出

BASEの禁止商品リストに基づくキーワードマッチングを実施しました。

#### base_account_1
- **問題商品候補**: 2,517件（汚染率: 19.55%）
- **ステータス別**:
  - 掲載済み（listed）: 2,356件
  - ペンディング（pending）: 161件

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
| cash（現金） | 31件 | 項目11 |
| counterfeit（偽ブランド品） | 19件 | 項目14 |
| drugs（薬物） | 8件 | 項目1 |
| used_clothing（使用済み衣類） | 7件 | 項目6 |
| illegal_devices（違法機器） | 6件 | 項目17, 18 |
| cannabis（大麻関連） | 1件 | 項目2 |

#### base_account_2
- **問題商品候補**: 238件（汚染率: 6.44%）
- **ステータス別**:
  - 掲載済み（listed）: 25件
  - ペンディング（pending）: 213件

**カテゴリ別内訳**:
| カテゴリ | 件数 |
|---------|------|
| medical | 103件 |
| adult | 49件 |
| child | 48件 |
| rmt | 19件 |
| vehicles | 18件 |

### 2.2 クロスアカウント汚染

**複数アカウントに出品されている問題商品**: 238件

主な商品例（上位10件）:
1. ポカリスエット（「薬」でヒット）
2. アミノバイタル（「薬」「サプリメント」でヒット）
3. ゴールドジム マルチビタミン（「児童」「サプリメント」でヒット）
4. キャットフード（「アダルト」＝「アダルトチキン」でヒット）
5. ゲーミングモニター（「AV」でヒット）

## 3. 重要な発見

### 3.1 誤検出の可能性が高い商品

キーワードマッチングにより、以下のような誤検出が多数発生しています：

| 検出キーワード | 誤検出例 | 理由 |
|--------------|---------|------|
| 「AV」 | ゲーミングモニター | 製品名に「AV」が含まれる |
| 「アダルト」 | キャットフード（アダルトチキン） | 成猫用フードの表記 |
| 「薬」 | ポカリスエット、アミノバイタル | スポーツ飲料・サプリメント |
| 「児童」 | 児童書、児童用商品 | 正規の児童向け商品 |
| 「バイク」 | バイク用タイヤ、グローブ | バイク部品・アクセサリー |
| 「オートバイ」 | オートバイ用ベルト | バイク部品・アクセサリー |

### 3.2 本当に問題の可能性がある商品

以下のカテゴリは慎重な確認が必要です：

#### 高リスク
1. **医療機器・検査キット**（medical）
   - 体温計、血圧計、PCR検査キット、妊娠検査薬など
   - BASE項目24「医薬品、医療機器」に該当する可能性

2. **タバコ関連**（tobacco）
   - 電子タバコ、IQOS、Ploomなど
   - BASE項目10「たばこ」に該当する可能性

3. **武器・刀剣類**（weapons）
   - サバイバルナイフ、エアガンなど
   - BASE項目3「銃砲、刀剣類、武器」に該当する可能性

#### 中リスク
1. **自動車・オートバイ関連**（vehicles）
   - バイク部品は問題ないが、「電動キックボード」「フル電動自転車」は禁止
   - BASE項目35に該当する可能性

2. **ゲームアカウント・RMT**（rmt）
   - ゲームアカウント、フォロワー、いいねの販売
   - BASE項目21に該当する可能性

## 4. 推奨対応

### 4.1 緊急対応（即時）

1. **高リスク商品の確認**
   - medical、tobacco、weaponsカテゴリの商品を手動確認
   - 該当する場合は即座に出品停止

2. **規制を受けた商品の特定**
   - BASEから通知された規制理由を確認
   - 該当商品のASINを特定し、すべてのアカウントから削除

### 4.2 短期対応（1週間以内）

1. **禁止商品フィルタの強化**
   - 現在のNG_keywords.jsonを拡張
   - より精度の高いキーワードフィルタを実装

2. **手動レビュー**
   - prohibited_items_report.csvを手動確認
   - 本当に問題のある商品をマークし、削除リストを作成

### 4.3 中期対応（1ヶ月以内）

1. **カテゴリベースのフィルタリング**
   - Amazonカテゴリを利用した自動判定
   - 高リスクカテゴリを事前にブロック

2. **出品前チェック機構の実装**（後述）

## 5. 出品前チェック機構の実装案

### 5.1 アーキテクチャ

```
┌─────────────────┐
│ ソーシング      │
│ (SellerSprite)  │
└────────┬────────┘
         │ ASIN候補
         ▼
┌─────────────────────────────┐
│ 1. 禁止商品チェッカー         │
│    - カテゴリベース判定       │
│    - キーワードベース判定     │
│    - ブランドベース判定       │
│    - リスクスコア算出         │
└────────┬────────────────────┘
         │ 合格したASIN
         ▼
┌─────────────────┐
│ 2. SP-API取得   │
│    - 商品情報   │
│    - 価格情報   │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────┐
│ 3. 再チェック（詳細情報）     │
│    - タイトル・説明文チェック │
│    - 画像チェック（将来実装） │
└────────┬────────────────────┘
         │ 合格したASIN
         ▼
┌─────────────────┐
│ master.db登録   │
│ upload_queue追加│
└─────────────────┘
```

### 5.2 実装コンポーネント

#### 5.2.1 禁止商品チェッカー（`ProhibitedItemChecker`）

**配置場所**: `inventory/core/prohibited_item_checker.py`

**機能**:
1. **カテゴリベース判定**
   - Amazonカテゴリを元に高リスクカテゴリを検出
   - 例: 「Health & Personal Care」「Automotive」「Sports」など

2. **キーワードベース判定**
   - タイトル・説明文からBASE禁止キーワードを検出
   - NGキーワード辞書を階層化（厳密レベル、中レベル、低レベル）

3. **ブランドベース判定**
   - 禁止ブランド・メーカーのブラックリスト
   - 例: タバコメーカー、アダルトブランドなど

4. **リスクスコア算出**
   - 各チェックの結果を総合評価
   - スコア0-100で算出（100が最もリスク高）
   - 閾値を超えた場合は自動ブロック

#### 5.2.2 禁止商品設定ファイル（`config/prohibited_items.json`）

**構造**:
```json
{
  "version": "1.0",
  "last_updated": "2025-12-01",
  "categories": {
    "high_risk": [
      "Health & Personal Care > Medications",
      "Sports & Outdoors > Hunting & Fishing > Knives",
      "Automotive > Motorcycles & Powersports > Motorcycles"
    ],
    "medium_risk": [
      "Sports & Outdoors > Outdoor Recreation > Cycling > Electric Bikes"
    ]
  },
  "keywords": {
    "strict": {
      "drugs": ["覚せい剤", "麻薬", "大麻"],
      "weapons": ["銃", "拳銃"],
      "adult": ["AV女優", "アダルトビデオ", "18禁DVD"]
    },
    "moderate": {
      "medical": ["医療機器", "血圧計", "体温計", "検査キット"],
      "tobacco": ["電子タバコ", "IQOS", "Ploom", "アイコス"],
      "vehicles": ["電動キックボード", "フル電動自転車"]
    },
    "whitelist": {
      "adult": ["アダルトチキン", "アダルト猫用", "成猫用"],
      "av": ["AVケーブル", "AVアンプ", "AV機器"]
    }
  },
  "brands": {
    "blacklist": [
      "タバコメーカー例"
    ]
  },
  "risk_thresholds": {
    "auto_block": 80,
    "manual_review": 50,
    "auto_approve": 20
  }
}
```

#### 5.2.3 統合ポイント

**既存のソーシングパイプラインへの統合**:

1. **`sourcing/scripts/import_candidates_to_master.py`への統合**
   ```python
   from inventory.core.prohibited_item_checker import ProhibitedItemChecker

   checker = ProhibitedItemChecker()

   # 各ASIN候補に対して
   for candidate in candidates:
       asin = candidate['asin']

       # SP-API取得前の事前チェック
       risk_score = checker.check_asin_basic(asin, category=candidate.get('category'))

       if risk_score >= 80:
           logger.warning(f"[BLOCKED] {asin}: リスクスコア {risk_score}")
           continue

       # SP-API取得
       product_info = fetch_from_sp_api(asin)

       # 詳細チェック
       detailed_risk = checker.check_product_detailed(product_info)

       if detailed_risk >= 50:
           logger.warning(f"[REVIEW REQUIRED] {asin}: リスクスコア {detailed_risk}")
           # manual_review_queueに追加（将来実装）
           continue

       # 問題なければmaster.dbに登録
       db.add_product(...)
   ```

2. **`inventory/scripts/add_new_products.py`への統合**
   - 手動でASINを追加する場合も同様のチェックを実施

### 5.3 実装スケジュール

#### Phase 1: 基本実装（1週間）
- [ ] `ProhibitedItemChecker`クラスの実装
- [ ] `config/prohibited_items.json`の作成
- [ ] 既存パイプラインへの統合
- [ ] 単体テスト

#### Phase 2: 精度向上（2週間）
- [ ] ホワイトリストの充実
- [ ] カテゴリベース判定の強化
- [ ] リスクスコアアルゴリズムの最適化
- [ ] 実データでの検証

#### Phase 3: 追加機能（1ヶ月）
- [ ] 画像解析による判定（AI/ML）
- [ ] 手動レビューキュー機能
- [ ] ダッシュボード（問題商品の可視化）
- [ ] 自動通知機能（Chatwork連携）

## 6. 既存出品の対応

### 6.1 即時対応が必要な商品

以下のスクリプトを実行して、高リスク商品を特定してください：

```bash
# 1. 高リスク商品のみを抽出
python analyze_prohibited_items.py --risk-level high

# 2. 該当商品を非公開化（DRY RUNモード）
python platforms/base/scripts/bulk_hide_items.py \
  --asin-file high_risk_asins.txt \
  --dry-run

# 3. 問題がなければ本番実行
python platforms/base/scripts/bulk_hide_items.py \
  --asin-file high_risk_asins.txt
```

### 6.2 段階的な対応

1. **Week 1**: 高リスク商品（medical、tobacco、weapons）の手動確認と削除
2. **Week 2**: 中リスク商品（vehicles、rmt）の確認
3. **Week 3**: 低リスク商品の確認と誤検出の修正

## 7. まとめ

### 現状
- **base_account_1**: 2,517件の問題商品候補（汚染率19.55%）
- **base_account_2**: 238件の問題商品候補（汚染率6.44%）
- **複数アカウント出品**: 238件

### 次のアクション
1. ✅ 調査完了
2. ⏳ 規制を受けた商品の特定（BASEからの通知待ち）
3. ⏳ 高リスク商品の手動確認と削除
4. ⏳ 禁止商品チェッカーの実装
5. ⏳ 既存出品の段階的クリーニング

### 参考ファイル
- `base_account1_listings.csv`: base_account_1の全出品リスト
- `prohibited_items_report.csv`: 問題商品候補の詳細レポート
- `cross_account_contamination_report.csv`: アカウント別汚染レポート
- `multi_account_prohibited_items.csv`: 複数アカウント出品リスト
