# BASE禁止商品対応レポート（2025-12-02）

**対応日**: 2025年12月2日
**対応者**: Claude Code
**対象アカウント**: base_account_2

---

## 1. 対応の概要

BASEのアカウント2において、身体機能検査キット商品の出品により利用規約違反の警告を受けました。
これに伴い、該当商品の削除と今後の再発防止策を実施しました。

### 警告内容

- **商品名**: GeneLife DIET 肥満遺伝子検査キット(Web版) ダイエット法はDNA検査で変わる
- **違反項目**: BASE利用規約 項目24「医薬品、身体機能検査キット、医療機器」
- **理由**: 身体機能検査キットに該当

---

## 2. 検出された禁止商品

### 2.1 検査キット商品（5件）

| ASIN | 商品名 | アカウント | 対応状況 |
|------|--------|-----------|---------|
| B076BNB41Q | GeneLife DIET 肥満遺伝子検査キット | base_account_2 | 🔴 手動削除が必要 |
| B0DKT7TKC4 | chatGENE Pro 500項目 遺伝子検査キット | base_account_1 | ⚠️ 非アクティブ |
| B0D3PLVQNX | chatGENE 400項目 遺伝子検査キット | base_account_2 | 🔴 手動削除が必要 |
| B01HYTP1F8 | ダイエット遺伝子検査キット【遺伝子博士】 | base_account_1 | ⚠️ 非アクティブ |
| B009QSJ46I | エクオール検査「ソイチェック」 | base_account_1 | ⚠️ 非アクティブ |

### 2.2 医薬品関連商品（54件）

**第1類医薬品**: 発毛剤（リアップ、メディカルミノキ5など）
**第2類医薬品**: 漢方薬、胃腸薬、ビタミン剤など
**第3類医薬品**: ビタミン剤、整腸剤など

詳細は`search_pharmaceutical_products.py`の実行結果を参照。

---

## 3. アカウント状況

### base_account_1
- **ステータス**: 非アクティブ
- **APIアクセス**: 不可
- **対応**: 非アクティブのため対応不要

### base_account_2
- **ステータス**: 🔴 **利用制限中**
- **APIアクセス**: 不可（400 Error: access_denied）
- **対応**: **手動削除が必要**

### base_account_3
- **ステータス**: ✅ 正常
- **APIアクセス**: 可能

---

## 4. 実施した対応

### 4.1 設定ファイルの更新

#### `config/prohibited_items.json`の更新（v1.1）

**追加したblockedカテゴリ**:
```json
"blocked": [
  // 医薬品・検査キット
  "Health & Personal Care > Medications",
  "Health & Personal Care > Over-the-Counter Medication",
  "ドラッグストア > 医薬品",
  "ドラッグストア > 医薬部外品",
  "ドラッグストア > 第一類医薬品",
  "ドラッグストア > 第二類医薬品",
  "ドラッグストア > 第三類医薬品",
  "ドラッグストア > 遺伝子検査",
  "Health & Personal Care > Health Tests",
  "Health & Personal Care > Medical Tests",

  // 酒類
  "Grocery & Gourmet Food > Beverages > Alcoholic Beverages",
  "ドラッグストア > お酒",
  "食品・飲料 > アルコール飲料",

  // チケット・デジタルコンテンツ
  "Entertainment Collectibles > Event Tickets",
  "Apps & Games > Digital Content",

  // タバコ
  "Tobacco Products"
]
```

**追加したstrictキーワード（weight: 100）**:
- `alcohol`: 「アルコール」「お酒」「ビール」「ワイン」「日本酒」「焼酎」「ウイスキー」「リキュール」
- `tickets`: 「チケット」「入場券」「観覧券」「招待券」「整理券」
- `fortune_telling`: 「占い」「占いサービス」「鑑定サービス」「スピリチュアル鑑定」

**追加したmoderateキーワード**:
- `hair_growth`: 「育毛剤」「増毛」「発毛剤」「植毛」など（weight: 70）
- `used_goods`: 「古着」「中古衣類」「トレーディングカード」「トレカ」「古物」など（weight: 60）
- `luxury_brands`: 「シャネル」「エルメス」「ルイヴィトン」「グッチ」「プラダ」など（weight: 50）
- `digital_content`: 「デジタルコンテンツ」「ダウンロード販売」「電子書籍」など（weight: 60）

**強化したキーワード**:
- `medical_strict`: 「第一類医薬品」「第二類医薬品」「第三類医薬品」を追加（weight: 100）
- `medical`: 「遺伝子検査」「DNA検査」を追加（weight: 100）

**追加したホワイトリスト**（誤検出防止）:
- `tickets`: 「チケットホルダー」「チケットケース」など
- `alcohol`: 「ノンアルコール」「アルコール消毒」など
- `hair`: 「育毛シャンプー」「ファッションウィッグ」など

### 4.2 禁止商品チェッカーの統合

#### `sourcing/scripts/import_candidates_to_master.py`への統合

商品登録前に`ProhibitedItemChecker`でチェックを実行し、以下の条件で自動ブロック：
- blockedカテゴリに該当 → スコア100（即座にブロック）
- キーワード+カテゴリのスコアが80以上 → 自動ブロック

**ブロック時の動作**:
```
[BLOCKED] B076BNB41Q: block (スコア: 100)
          キーワード: ['遺伝子検査', '検査キット']
          カテゴリ: ['blocked: ドラッグストア > 遺伝子検査']
```

### 4.3 統計情報の追加

import_candidates_to_master.pyの実行結果サマリーに「禁止商品ブロック」件数を追加：
```
処理対象ASIN数:       1000件
商品情報取得成功:      950件
商品情報取得失敗:       50件
禁止商品ブロック:       15件  ← 追加
productsテーブル追加:  935件
```

---

## 5. 手動対応が必要な商品

### base_account_2の手動削除対象

以下の商品はBASE管理画面から手動で削除してください：

1. **B076BNB41Q** - GeneLife DIET 肥満遺伝子検査キット
2. **B0D3PLVQNX** - chatGENE 400項目 遺伝子検査キット

### 医薬品商品（54件）

医薬品関連商品54件も利用規約違反のため、出品停止または削除を検討してください。
詳細リストは`search_pharmaceutical_products.py`を実行して確認できます。

---

## 6. 今後の運用

### 6.1 ソーシング時の自動チェック

`sourcing/scripts/import_candidates_to_master.py`を実行する際、自動的に禁止商品がブロックされます。

**実行例**:
```bash
venv\Scripts\python.exe sourcing\scripts\import_candidates_to_master.py --limit 100
```

禁止商品チェックを無効化する場合（非推奨）:
```bash
venv\Scripts\python.exe sourcing\scripts\import_candidates_to_master.py --limit 100 --no-check-prohibited
```

### 6.2 定期的な確認

月次で以下のスクリプトを実行し、禁止商品が混入していないかを確認してください：

```bash
# 検査キット商品の確認
venv\Scripts\python.exe search_medical_products.py

# 医薬品商品の確認
venv\Scripts\python.exe search_pharmaceutical_products.py
```

---

## 7. 参考情報

### BASE利用規約（禁止商品）

https://help.thebase.in/hc/ja/articles/115000047621

**項目24**: 医薬品（国内で販売が禁止されていない医薬品を含む）、身体機能検査キット、医療機器

→ **合法的に販売されている医薬品でもBASEでは禁止**

### 関連ファイル

- 設定ファイル: [config/prohibited_items.json](../config/prohibited_items.json)
- チェッカー実装: [inventory/core/prohibited_item_checker.py](../inventory/core/prohibited_item_checker.py)
- ソーシング連携: [sourcing/scripts/import_candidates_to_master.py](../sourcing/scripts/import_candidates_to_master.py)
- 前回の分析: [docs/BASE_PROHIBITED_ITEMS_ANALYSIS.md](./BASE_PROHIBITED_ITEMS_ANALYSIS.md)

---

## 8. まとめ

### 実施した対策

✅ 禁止商品設定の強化（医薬品・検査キット関連カテゴリ/キーワード）
✅ ソーシングパイプラインへの禁止商品チェッカー統合
✅ 自動ブロック機能の実装（スコア80以上）
✅ 統計情報への反映

### 残タスク

🔴 base_account_2の手動削除（利用制限中のため）
⚠️ 医薬品関連商品54件の対応検討
📋 定期的な禁止商品チェックの運用開始

### 効果

今後、ソーシング時に以下の商品が自動的にブロックされ、BASE利用規約違反のリスクが大幅に軽減されます：

- ✅ 医薬品（第1類〜第3類）
- ✅ 医薬部外品
- ✅ 検査キット（遺伝子検査、DNA検査など）
- ✅ 医療機器・コンタクトレンズ
- ✅ 酒類（ビール、ワイン、日本酒、焼酎など）
- ✅ チケット類（入場券、観覧券など）
- ✅ 占い・鑑定サービス
- ✅ 育毛剤・発毛剤・増毛サービス
- ✅ 古物（古着、トレカなど）
- ✅ ハイブランド商品（偽造品リスク対策）
- ✅ デジタルコンテンツ

---

**作成日**: 2025年12月2日
**更新日**: 2025年12月2日
