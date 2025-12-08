# 禁止商品管理システム - 完全ガイド

**最終更新**: 2025年12月7日
**ステータス**: ✅ 実装完了・運用中

---

## 📋 目次

1. [概要](#概要)
2. [背景と経緯](#背景と経緯)
3. [実装された機能](#実装された機能)
4. [使用方法](#使用方法)
5. [運用ガイドライン](#運用ガイドライン)
6. [技術仕様](#技術仕様)
7. [過去の調査結果](#過去の調査結果)

---

## 概要

BASEをはじめとするECプラットフォームの利用規約違反（禁止商品出品）を防止するための包括的な管理システムです。

### 主な機能

1. **事前チェック**: 新規商品追加時の自動禁止商品チェック
2. **既存DBスキャン**: 登録済み商品の一括チェック
3. **削除ワークフロー**: 目視確認→削除→ブロックリストへの自動登録
4. **再発防止**: ブロックリストによる自動ブロック

### システム構成

```
┌─────────────────────────────────────────────────────────┐
│ 1. 新規追加時の自動チェック                              │
│    - sourcing/scripts/import_candidates_to_master.py    │
│    - inventory/scripts/add_new_products.py              │
│    - ProhibitedItemChecker + BlocklistManager           │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│ 2. 既存DBの定期スキャン                                  │
│    - inventory/scripts/scan_prohibited_items.py         │
│    - CSVレポート生成                                     │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼ (目視確認)
                            │
┌─────────────────────────────────────────────────────────┐
│ 3. 禁止商品の削除                                        │
│    - inventory/scripts/remove_prohibited_items.py       │
│    - プラットフォーム削除 + DB削除 + ブロックリスト登録  │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│ 4. ブロックリストによる再発防止                         │
│    - config/blocked_asins.json                          │
│    - 新規追加時に自動ブロック                            │
└─────────────────────────────────────────────────────────┘
```

---

## 背景と経緯

### Phase 1: 問題の発生（2025年12月1日）

**事象**: BASEアカウント1で規制を受ける

**調査結果**:
- **base_account_1**: 12,872件の出品中、2,517件（19.55%）が問題商品候補
- **base_account_2**: 3,694件の出品中、238件（6.44%）が問題商品候補

**検出された主な問題商品カテゴリ**:
| カテゴリ | 件数 | BASE利用規約該当項目 |
|---------|------|---------------------|
| vehicles（自動車・バイク関連） | 831件 | 項目35 |
| adult（アダルト関連） | 545件 | 項目4 |
| medical（医薬品・医療機器） | 513件 | 項目24 |
| child（児童関連） | 289件 | 項目5 |
| rmt（ゲームアカウント・RMT） | 278件 | 項目21 |

**課題**:
- 誤検出が多数（「AV」「アダルト」「薬」「児童」「バイク」など）
- 手動確認が必須
- 再発防止策が不足

### Phase 2: 初期対応（2025年12月2日）

**実施内容**:
1. ✅ 禁止商品チェッカー（ProhibitedItemChecker）の実装
2. ✅ 設定ファイル（config/prohibited_items.json）の作成
3. ✅ ソーシングパイプラインへの統合（import_candidates_to_master.py）
4. ✅ 新規商品追加時のチェック機能（add_new_products.py）

**対応した具体的な違反**:
- **遺伝子検査キット**: GeneLife DIET（BASE利用規約項目24違反）
- **医薬品**: 育毛剤（医薬部外品）54件
- **検査キット**: DNA検査、遺伝子検査等

**設定ファイルの強化**:
- blockedカテゴリ追加（医薬品、検査キット、酒類、チケット、タバコ）
- strictキーワード追加（アルコール、チケット、占い等）
- ホワイトリスト拡充（誤検出防止）

### Phase 3: 包括的な管理システムの構築（2025年12月7日）

**実装内容**:
1. ✅ **既存DBスキャナー** - 登録済み商品の一括チェック
2. ✅ **削除スクリプト** - プラットフォーム削除 + DB削除の自動化
3. ✅ **ブロックリスト機能** - 削除済みASINの自動ブロック
4. ✅ **統合強化** - 既存スクリプトへのブロックリスト機能統合

**ワークフローの完成**:
既存DB監査 → 目視確認 → 一括削除 → ブロックリスト登録 → 新規追加時の自動ブロック

---

## 実装された機能

### 1. ProhibitedItemChecker（禁止商品チェッカー）

**ファイル**: `inventory/core/prohibited_item_checker.py`

**機能**:
- ✅ カテゴリベース判定（blocked/high_risk/medium_risk）
- ✅ キーワードベース判定（strict/moderate/low）
- ✅ ブランドベース判定
- ✅ ホワイトリスト機能（誤検出防止）
- ✅ リスクスコア算出（0-100）

**判定基準**:
- **80以上**: 自動ブロック（auto_block）
- **50-79**: 手動レビュー推奨（manual_review）
- **0-49**: 自動承認（auto_approve）

### 2. 設定ファイル

**ファイル**: `config/prohibited_items.json`（バージョン: 1.1）

**構成**:
```json
{
  "categories": {
    "blocked": [        // スコア100で即ブロック
      "Health & Personal Care > Medications",
      "ドラッグストア > 医薬品",
      "Tobacco Products"
    ],
    "high_risk": [      // +30点
      "Health & Personal Care > Medical Supplies"
    ],
    "medium_risk": [    // +20点
      "Video Games > Digital Games & DLC"
    ]
  },
  "keywords": {
    "strict": {         // weight: 100
      "medical_strict": ["医薬部外品", "第一類医薬品"],
      "tobacco_strict": ["たばこ", "加熱式たばこ"],
      "alcohol": ["アルコール", "ビール", "ワイン"]
    },
    "moderate": {       // weight: 60-100
      "medical": ["検査キット", "遺伝子検査"],
      "hair_growth": ["育毛剤", "発毛剤"]
    }
  },
  "whitelist": {        // 誤検出防止
    "adult": ["アダルトチキン", "成猫用"],
    "alcohol": ["ノンアルコール", "アルコール消毒"],
    "vehicles": ["バイク用", "バイクパーツ"]
  }
}
```

### 3. 既存DBスキャナー

**ファイル**: `inventory/scripts/scan_prohibited_items.py`

**機能**:
- ✅ マスタDBの全商品をスキャン
- ✅ リスクレベル別フィルタリング（high/medium/low）
- ✅ プラットフォーム・アカウント別フィルタ
- ✅ 出品状況（listed/pending）の確認
- ✅ 目視確認用CSVレポート生成

**出力例**:
```csv
asin,title_ja,risk_score,matched_keywords,listing_statuses,delete
B076BNB41Q,GeneLife DIET 遺伝子検査キット,100,"遺伝子検査,検査キット",listed,
```

### 4. 削除スクリプト

**ファイル**: `inventory/scripts/remove_prohibited_items.py`

**機能**:
- ✅ CSVファイルまたはASINリストから削除対象を読み込み
- ✅ 出品済の場合：プラットフォームAPIで削除
- ✅ listingsテーブルから削除
- ✅ productsテーブルから削除（オプション）
- ✅ ブロックリストに自動登録
- ✅ DRY RUNモード対応

**対応プラットフォーム**:
- ✅ BASE（完全対応）
- ⚠️ eBay、Yahoo!、メルカリ（未実装）

### 5. ブロックリスト機能

**ファイル**:
- `config/blocked_asins.json`（ブロックリストデータ）
- `inventory/core/blocklist_manager.py`（管理クラス）

**機能**:
- ✅ 削除済みASINの記録
- ✅ ブロック理由、削除日時、リスクスコアの保存
- ✅ 新規追加時の自動ブロック
- ✅ 統計情報の表示

**統合状況**:
- ✅ `sourcing/scripts/import_candidates_to_master.py`
- ✅ `inventory/scripts/add_new_products.py`

---

## 使用方法

### 【ワークフロー1】既存DBの禁止商品監査

#### ステップ1: 既存DBをスキャン

```bash
# 高リスク商品のみスキャン（リスクスコア80以上）
python inventory/scripts/scan_prohibited_items.py --risk-level high

# 全商品をスキャン（リスクスコア50以上）
python inventory/scripts/scan_prohibited_items.py --threshold 50

# 特定プラットフォーム・アカウントのみスキャン
python inventory/scripts/scan_prohibited_items.py \
  --platform base \
  --account-id base_account_2 \
  --risk-level high
```

**出力**:
- CSVファイル: `logs/prohibited_items_scan_YYYYMMDD_HHMMSS.csv`
- サマリー表示: 検出件数、リスクレベル別集計、出品状況

#### ステップ2: CSVファイルで目視確認

1. ExcelまたはGoogleスプレッドシートで生成されたCSVを開く
2. 各商品を確認し、削除対象のASINの `delete` カラムに `YES` を入力
3. ファイルを保存

**確認ポイント**:
- タイトル、カテゴリ、ブランドを確認
- matched_keywordsで検出理由を確認
- 誤検出の可能性がある場合はホワイトリストに追加を検討

#### ステップ3: 削除を実行

```bash
# DRY RUNモード（確認のみ、実際の削除は行わない）
python inventory/scripts/remove_prohibited_items.py \
  --csv logs/prohibited_items_scan_20251207_014812.csv \
  --delete-from-platform \
  --add-to-blocklist \
  --dry-run

# 本番実行
python inventory/scripts/remove_prohibited_items.py \
  --csv logs/prohibited_items_scan_20251207_014812.csv \
  --delete-from-platform \
  --add-to-blocklist \
  --yes

# productsテーブルからも削除する場合
python inventory/scripts/remove_prohibited_items.py \
  --csv logs/prohibited_items_scan_20251207_014812.csv \
  --delete-from-platform \
  --delete-products \
  --add-to-blocklist \
  --yes
```

**処理内容**:
1. CSVファイルから `delete=YES` のASINを抽出
2. 各ASINについて：
   - listingsテーブルで出品状況を確認
   - 出品済（listed）の場合：プラットフォームAPIで削除
   - listingsテーブルから削除
   - productsテーブルから削除（オプション）
   - `config/blocked_asins.json`に登録

#### ステップ4: 結果確認

```bash
# ブロックリストの確認
cat config/blocked_asins.json

# 統計表示
処理対象:               10件
プラットフォーム削除:    8件
listings削除:           10件
products削除:            0件
ブロックリスト追加:     10件
```

### 【ワークフロー2】新規商品追加時の自動チェック

#### ソーシングからの自動追加

```bash
# sourcing_candidatesから自動連携
python sourcing/scripts/import_candidates_to_master.py --limit 100

# 実行例（ブロックリスト機能が自動的に有効）
処理対象ASIN数:       100件
商品情報取得成功:      95件
商品情報取得失敗:       5件
ブロックリスト拒否:     2件  ← ブロックリストで自動ブロック
禁止商品ブロック:       3件  ← ProhibitedItemCheckerで自動ブロック
productsテーブル追加:  90件
```

#### 手動での商品追加

```bash
# ASINリストから追加（禁止商品チェック有効）
python inventory/scripts/add_new_products.py \
  --asin-file asins.txt \
  --platform base \
  --account-id base_account_1 \
  --use-sp-api \
  --check-prohibited \
  --yes

# 実行例
成功: 45件
スキップ: 5件
ブロックリスト拒否: 2件  ← ブロックリストで自動ブロック
禁止商品ブロック: 3件    ← ProhibitedItemCheckerで自動ブロック
```

### 【ワークフロー3】個別ASINの削除

```bash
# ASINリストを直接指定
python inventory/scripts/remove_prohibited_items.py \
  --asins "B076BNB41Q,B0D3PLVQNX" \
  --delete-from-platform \
  --add-to-blocklist \
  --yes

# ASINリストファイルから読み込み
python inventory/scripts/remove_prohibited_items.py \
  --asin-file prohibited_asins.txt \
  --delete-from-platform \
  --add-to-blocklist \
  --yes
```

---

## 運用ガイドライン

### 定期監査

**推奨頻度**: 月次または商品追加時

```bash
# 1. 既存DBをスキャン
python inventory/scripts/scan_prohibited_items.py --risk-level high

# 2. CSVファイルで目視確認
# logs/prohibited_items_scan_YYYYMMDD_HHMMSS.csv を確認

# 3. 削除実行（DRY RUN → 本番）
python inventory/scripts/remove_prohibited_items.py \
  --csv logs/prohibited_items_scan_YYYYMMDD_HHMMSS.csv \
  --delete-from-platform \
  --add-to-blocklist \
  --dry-run

python inventory/scripts/remove_prohibited_items.py \
  --csv logs/prohibited_items_scan_YYYYMMDD_HHMMSS.csv \
  --delete-from-platform \
  --add-to-blocklist \
  --yes
```

### 誤検出への対応

**問題**: 正規商品が誤って検出される場合

**対応**:
1. `config/prohibited_items.json`のホワイトリストに追加

```json
{
  "keywords": {
    "whitelist": {
      "adult": [
        "アダルトチキン",
        "成猫用",
        "新しい正規商品名"  // 追加
      ]
    }
  }
}
```

2. 設定ファイル更新後、再スキャン

```bash
python inventory/scripts/scan_prohibited_items.py --risk-level high
```

### プラットフォーム規約の更新対応

**BASE利用規約の変更時**:

1. `config/prohibited_items.json`を更新
   - 新規禁止商品カテゴリを追加
   - 新規禁止キーワードを追加

2. 既存DBを再スキャン

```bash
python inventory/scripts/scan_prohibited_items.py --threshold 50
```

3. 検出された商品を確認・削除

### ログの管理

**ログファイルの場所**:
- スキャン結果: `logs/prohibited_items_scan_YYYYMMDD_HHMMSS.csv`
- ブロックリスト: `config/blocked_asins.json`

**ログローテーション**:
- 古いCSVファイルは定期的にアーカイブ
- ブロックリストは累積型（削除不要）

---

## 技術仕様

### ファイル構成

```
ecauto/
├── inventory/
│   ├── core/
│   │   ├── prohibited_item_checker.py    # 禁止商品チェッカー
│   │   └── blocklist_manager.py          # ブロックリスト管理
│   └── scripts/
│       ├── scan_prohibited_items.py      # 既存DBスキャナー
│       └── remove_prohibited_items.py    # 削除スクリプト
├── config/
│   ├── prohibited_items.json             # 禁止商品設定
│   └── blocked_asins.json                # ブロックリスト
├── sourcing/scripts/
│   └── import_candidates_to_master.py    # ブロックリスト統合済み
└── logs/
    └── prohibited_items_scan_*.csv       # スキャン結果
```

### データベーススキーマ

**注**: 禁止商品チェック結果はデータベースには保存されません。

- リスクスコア、チェック履歴はログファイルとCSVで管理
- ブロックリストは `config/blocked_asins.json` で管理
- 削除後のASINは listings/products テーブルから削除

### リスクスコア計算

```python
total_score = keyword_score + category_score + brand_score

# 例
keyword_score = 100  # 「医薬部外品」でヒット（strict）
category_score = 30  # 「Health & Personal Care > Medical」（high_risk）
brand_score = 0
total_score = 130 → min(100, 130) = 100  # 上限は100

→ risk_level = 'block', recommendation = 'auto_block'
```

### ブロックリストのスキーマ

```json
{
  "version": "1.0",
  "last_updated": "2025-12-07T01:50:00+09:00",
  "blocked_asins": {
    "B0DS5X8JPV": {
      "reason": "加熱式タバコ（BASE利用規約項目10違反）",
      "risk_score": 100,
      "deleted_at": "2025-12-07T01:50:00+09:00",
      "deleted_by": "manual",
      "platforms": ["base"],
      "note": "手動削除"
    }
  }
}
```

### プラットフォーム削除API

**BASE**:
- ✅ 実装済み: `platforms/base/core/api_client.py` の `delete_item()`
- 認証: OAuth 2.0トークン
- レート制限: 考慮済み

**その他のプラットフォーム**:
- ⚠️ eBay、Yahoo!、メルカリは未実装
- 今後、各プラットフォームのAPI仕様に応じて実装予定

---

## 過去の調査結果

### 初回調査（2025年12月1日）

**対象アカウント**: base_account_1, base_account_2

**検出結果**:
- 合計: 16,566件の出品
- 問題商品候補: 2,755件（16.6%）

**誤検出の多いキーワード**:
| キーワード | 誤検出例 | 対応 |
|-----------|---------|------|
| 「AV」 | ゲーミングモニター | ホワイトリストに「AVケーブル」等を追加 |
| 「アダルト」 | キャットフード（アダルトチキン） | ホワイトリストに「アダルトチキン」等を追加 |
| 「薬」 | ポカリスエット、アミノバイタル | ホワイトリストに「スポーツ飲料」等を追加 |
| 「児童」 | 児童書、児童用商品 | ホワイトリストに「児童書」等を追加 |
| 「バイク」 | バイク用タイヤ、グローブ | ホワイトリストに「バイク用」等を追加 |

**本当に問題のある商品**:
1. **医療機器・検査キット**: 体温計、血圧計、PCR検査キット、遺伝子検査キット
2. **タバコ関連**: 電子タバコ、IQOS、加熱式タバコ
3. **医薬品**: 育毛剤（医薬部外品）、第1類〜第3類医薬品
4. **武器・刀剣類**: サバイバルナイフ、エアガン
5. **酒類**: ビール、ワイン、日本酒、焼酎

### 第2回対応（2025年12月2日）

**事象**: BASEアカウント2で遺伝子検査キット出品により警告

**対応内容**:
1. ✅ 禁止商品設定の強化（医薬品・検査キット関連）
2. ✅ ソーシングパイプラインへの統合
3. ✅ 自動ブロック機能の実装
4. ✅ 統計情報への反映

**検出された商品**:
- 遺伝子検査キット: 5件
- 医薬品関連商品: 54件

**効果**:
今後、ソーシング時に自動的にブロックされ、BASE利用規約違反のリスクが大幅に軽減

### 第3回強化（2025年12月7日）

**実施内容**:
1. ✅ 既存DBスキャナーの実装
2. ✅ 削除スクリプトの実装
3. ✅ ブロックリスト機能の実装
4. ✅ 既存スクリプトへの統合強化

**テスト結果**:
- スキャン: 100件中6件の高リスク商品を検出
- 削除: DRY RUNモードで正常動作確認
- ブロックリスト: 統合機能が正常動作

**検出例**:
1. ✅ Fasoul Q1 加熱式タバコ（正しい検出）
2. ✅ チャップアップ 育毛剤・医薬部外品（正しい検出）
3. ⚠️ アルコールウェットティッシュ（要確認）
4. ⚠️ パックご飯（誤検出の可能性）

---

## 関連ドキュメント

- [BASE禁止商品リスト（公式）](https://official.thebase.in/pages/prohibited-items)
- [プロジェクトREADME](../README.md)
- [禁止商品設定ファイル](../config/prohibited_items.json)
- [ブロックリスト](../config/blocked_asins.json)

---

## 改訂履歴

| 日付 | バージョン | 内容 |
|------|-----------|------|
| 2025-12-01 | 0.1 | 初回調査・分析レポート作成 |
| 2025-12-02 | 0.2 | ProhibitedItemChecker実装、ソーシング統合 |
| 2025-12-07 | 1.0 | 包括的な管理システム完成（スキャナー・削除・ブロックリスト）|

---

**作成者**: Claude Code
**最終更新**: 2025年12月7日
