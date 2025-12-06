# カテゴリベース抽出システム実装プラン

**作成日**: 2025-11-26
**目的**: カテゴリ軸でのASIN取得により、既存データとの重複を最小化

---

## 📋 目次

1. [背景と目的](#背景と目的)
2. [実装アプローチ](#実装アプローチ)
3. [技術仕様](#技術仕様)
4. [実装ステップ](#実装ステップ)
5. [期待される効果](#期待される効果)

---

## 背景と目的

### Phase 1の結果と課題

**Phase 1（販売数セグメント分割）の結果:**
- 6セグメントから合計3,000件を取得
- 重複率: **100%** （新規ASIN 0件）

**根本原因:**
- SellerSpriteのランキングアルゴリズムが安定しており、異なる販売数レンジでも同じASINプールから取得される
- 各セグメントで「上位500件」しか取得していないため、常に既知のASINが返ってくる

### カテゴリベース抽出の利点

**戦略:**
カテゴリ軸で分割することで、異なる商品群にアクセスできる。

**具体例:**
```
従来: 販売数300-350（全カテゴリ混在）→ 上位500件
改善:
  - カテゴリA × 販売数300以上 → 2,000件
  - カテゴリB × 販売数300以上 → 2,000件
  - カテゴリC × 販売数300以上 → 2,000件
```

**メリット:**
1. 各カテゴリで**2,000件の上限**をフル活用できる
2. カテゴリごとに異なる商品群をカバー
3. 既存データのカテゴリ分布を分析して、未開拓カテゴリを優先できる

---

## 実装アプローチ

### 2段階アプローチ

#### フェーズ1: カテゴリ情報の取得とサンプリング
1. 初期サンプル（500-1,000件）を取得
2. 各ASINのカテゴリ情報を抽出
3. ユニークなカテゴリリストを作成
4. 既存DBのカテゴリ分布と比較

#### フェーズ2: カテゴリ別の体系的抽出
1. 未開拓カテゴリを優先順位付け
2. 各カテゴリで2,000件ずつ取得
3. リアルタイムで重複チェック
4. 目標件数に達するまで継続

---

## 技術仕様

### 1. カテゴリ情報の取得

#### SellerSprite WebUIの構造調査

**テーブル構造:**
```html
<table>
  <thead>
    <tr>
      <th>商品画像</th>
      <th>ASIN</th>
      <th>タイトル</th>
      <th>カテゴリ</th>  ← ここから抽出
      <th>価格</th>
      <th>月間販売数</th>
      ...
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>...</td>
      <td>B001TRIKI2</td>
      <td>商品タイトル</td>
      <td>ホーム&キッチン > キッチン用品</td>  ← カテゴリパス
      ...
    </tr>
  </tbody>
</table>
```

**実装:**
```python
async def extract_asins_with_categories(page, limit=500):
    """ASINとカテゴリ情報を同時取得"""
    results = []

    # テーブルの各行をループ
    rows = await page.locator('table tbody tr').all()

    for row in rows[:limit]:
        # ASIN列
        asin_cell = row.locator('td:nth-child(2)')  # 仮のインデックス
        asin = await asin_cell.text_content()

        # カテゴリ列
        category_cell = row.locator('td:nth-child(4)')  # 仮のインデックス
        category = await category_cell.text_content()

        results.append({
            'asin': asin.strip(),
            'category': category.strip()
        })

    return results
```

---

### 2. カテゴリフィルターの操作

#### WebUIの調査が必要な項目

1. **カテゴリフィルターの位置**
   - セレクタ: `?`（調査が必要）
   - UI形式: ドロップダウン、ツリー構造、検索ボックス？

2. **カテゴリの階層構造**
   - 例: "ホーム&キッチン > キッチン用品 > 調理器具"
   - 階層レベル: 1階層？2階層？3階層？

3. **カテゴリ選択の方法**
   - クリック操作の回数
   - 選択確認の方法
   - フィルター適用のタイミング

#### 実装方針

**ステップA: 手動でWebUIを調査**
```bash
# ブラウザを開いてカテゴリメニューを調査
python sourcing/sources/sellersprite/auth_manager.py login
# → ブラウザで商品リサーチページを開く
# → カテゴリフィルターを手動で操作
# → DevToolsでセレクタを特定
```

**ステップB: Playwright操作を実装**
```python
async def apply_category_filter(page, category_path: str):
    """
    カテゴリフィルターを適用

    Args:
        page: Playwrightのページオブジェクト
        category_path: "ホーム&キッチン > キッチン用品" 形式
    """
    # カテゴリメニューを開く
    category_button = page.locator('[data-testid="category-filter"]')  # 仮
    await category_button.click()

    # 階層をたどって選択
    categories = category_path.split(' > ')
    for category in categories:
        category_option = page.locator(f'text="{category}"').first
        await category_option.click()
        await page.wait_for_timeout(500)  # UIの更新を待つ

    # フィルター適用
    apply_button = page.locator('button:has-text("適用")')  # 仮
    await apply_button.click()

    # 結果の読み込みを待つ
    await page.wait_for_load_state('networkidle')
```

---

### 3. データベーススキーマの拡張

#### sourcing_candidates テーブルに列を追加

```sql
-- カテゴリ情報を保存（すでに存在）
ALTER TABLE sourcing_candidates
ADD COLUMN IF NOT EXISTS category TEXT;

-- カテゴリの階層レベルを保存（オプション）
ALTER TABLE sourcing_candidates
ADD COLUMN IF NOT EXISTS category_level_1 TEXT;

ALTER TABLE sourcing_candidates
ADD COLUMN IF NOT EXISTS category_level_2 TEXT;

ALTER TABLE sourcing_candidates
ADD COLUMN IF NOT EXISTS category_level_3 TEXT;
```

#### インデックスの追加

```sql
-- カテゴリでの検索を高速化
CREATE INDEX IF NOT EXISTS idx_category
ON sourcing_candidates(category);

CREATE INDEX IF NOT EXISTS idx_category_level_1
ON sourcing_candidates(category_level_1);
```

---

### 4. カテゴリ別抽出スクリプト

#### 新規スクリプト: `extract_by_categories.py`

**全体フロー:**
```
1. 初期サンプリング（500件）
   ↓
2. カテゴリリストを抽出
   ↓
3. 既存DBのカテゴリ分布と比較
   ↓
4. 未開拓カテゴリを優先順位付け
   ↓
5. 各カテゴリで2,000件ずつ取得
   ↓
6. 重複チェック → 新規ASINのみ保存
   ↓
7. 目標達成まで繰り返し
```

**コマンドライン:**
```bash
python sourcing/scripts/extract_by_categories.py \
  --target-new-asins 10000 \           # 目標新規ASIN数
  --sample-size 1000 \                 # 初期サンプルサイズ
  --asins-per-category 2000 \          # 各カテゴリの取得数
  --sales-min 300 \                    # 販売数の最小値
  --price-min 2500 \                   # 価格の最小値
  --max-categories 20 \                # 最大カテゴリ数
  --output category_asins_YYYYMMDD.txt \
  --report category_report_YYYYMMDD.md
```

**スクリプト構造:**
```python
async def main():
    # 1. 初期サンプリング
    print("初期サンプリングを開始...")
    sample_data = await extract_sample_with_categories(
        limit=args.sample_size,
        sales_min=args.sales_min,
        price_min=args.price_min
    )

    # 2. カテゴリ統計
    category_stats = analyze_categories(sample_data)
    print(f"発見されたカテゴリ数: {len(category_stats)}件")

    # 3. 既存DBと比較
    existing_categories = get_existing_categories_from_db()
    unexplored_categories = identify_unexplored_categories(
        category_stats,
        existing_categories
    )

    # 4. 優先順位付け
    prioritized_categories = prioritize_categories(
        unexplored_categories,
        max_count=args.max_categories
    )

    # 5. カテゴリ別抽出ループ
    all_new_asins = set()

    for i, category in enumerate(prioritized_categories):
        print(f"\n[カテゴリ {i+1}/{len(prioritized_categories)}]")
        print(f"  カテゴリ: {category['name']}")
        print(f"  推定ASIN数: {category['estimated_count']}件")

        # カテゴリフィルターを適用して抽出
        asins = await extract_by_category(
            category=category['name'],
            limit=args.asins_per_category,
            sales_min=args.sales_min,
            price_min=args.price_min
        )

        # 重複チェック
        existing_asins = load_existing_asins_from_db()
        new_asins = set(asins) - existing_asins - all_new_asins

        print(f"  取得: {len(asins)}件")
        print(f"  新規: {len(new_asins)}件 ({len(new_asins)/len(asins)*100:.1f}%)")

        all_new_asins.update(new_asins)

        # 目標達成チェック
        if len(all_new_asins) >= args.target_new_asins:
            print(f"\n✅ 目標達成: {len(all_new_asins)}件の新規ASIN")
            break

    # 6. 結果保存
    save_asins_to_file(all_new_asins, args.output)
    generate_report(all_new_asins, prioritized_categories, args.report)
```

---

## 実装ステップ

### ステップ1: カテゴリ情報取得機能の実装（1時間）

**タスク:**
1. `product_research_extractor.py` を拡張
2. テーブルからカテゴリ列を抽出するロジックを追加
3. カテゴリ情報をDBに保存

**成果物:**
- `ProductResearchExtractor.extract_with_categories()` メソッド
- カテゴリ情報を含むデータ取得の確認

**検証:**
```bash
# テスト実行
python -c "
from sourcing.sources.sellersprite.extractors.product_research_extractor import ProductResearchExtractor
import asyncio

async def test():
    extractor = ProductResearchExtractor({
        'sales_min': 300,
        'price_min': 2500,
        'limit': 100
    })

    # カテゴリ情報付きで取得
    results = await extractor.extract_with_categories()

    print(f'取得件数: {len(results)}')
    print('サンプル:')
    for r in results[:5]:
        print(f'  ASIN: {r[\"asin\"]}, カテゴリ: {r[\"category\"]}')

asyncio.run(test())
"
```

---

### ステップ2: WebUIのカテゴリメニュー調査（30分）

**タスク:**
1. SellerSpriteにログインしてWebUIを調査
2. カテゴリフィルターの位置とセレクタを特定
3. カテゴリ選択の操作手順を記録
4. スクリーンショットを保存

**調査項目:**
- カテゴリメニューの開き方
- カテゴリ階層の構造（1階層？複数階層？）
- カテゴリ選択後のフィルター適用方法
- 選択解除の方法

**ドキュメント化:**
`sourcing/sources/sellersprite/docs/category_filter_ui.md` に記録

---

### ステップ3: カテゴリ選択機能の実装（1-1.5時間）

**タスク:**
1. `ProductResearchExtractor` にカテゴリフィルター適用機能を追加
2. Playwrightでカテゴリメニューを操作
3. エラーハンドリングとリトライロジック

**実装:**
```python
# product_research_extractor.py

async def apply_category_filter(self, page, category_path: str):
    """カテゴリフィルターを適用"""
    self.log(f"カテゴリフィルターを適用: {category_path}")

    try:
        # 実装内容はステップ2の調査結果に基づく
        # ...

        self.log("[OK] カテゴリフィルター適用完了")
        return True

    except Exception as e:
        self.log(f"[ERROR] カテゴリフィルター適用失敗: {e}")
        return False
```

**検証:**
```bash
# 手動テスト
python -c "
from sourcing.sources.sellersprite.extractors.product_research_extractor import ProductResearchExtractor
import asyncio

async def test():
    extractor = ProductResearchExtractor({
        'sales_min': 300,
        'price_min': 2500,
        'limit': 100,
        'category': 'ホーム&キッチン > キッチン用品'  # 新パラメータ
    })

    asins = await extractor.extract()
    print(f'カテゴリ指定で取得: {len(asins)}件')

asyncio.run(test())
"
```

---

### ステップ4: カテゴリ別抽出スクリプトの作成（1時間）

**タスク:**
1. `sourcing/scripts/extract_by_categories.py` を新規作成
2. 初期サンプリング → カテゴリ分析 → カテゴリ別抽出のフローを実装
3. 進捗表示とレポート生成

**成果物:**
- `extract_by_categories.py` スクリプト
- 使用例ドキュメント

**実行例:**
```bash
python sourcing/scripts/extract_by_categories.py \
  --target-new-asins 10000 \
  --sample-size 1000 \
  --asins-per-category 2000 \
  --sales-min 300 \
  --price-min 2500 \
  --output category_asins_20251126.txt
```

---

### ステップ5: 統合テスト（30分）

**テストシナリオ:**
1. 初期サンプリングが正常に動作するか
2. カテゴリ情報が正しく抽出されるか
3. カテゴリフィルターが正常に適用されるか
4. 重複チェックが機能するか
5. 目標件数に達したら停止するか

**テスト実行:**
```bash
# 小規模テスト（500件目標）
python sourcing/scripts/extract_by_categories.py \
  --target-new-asins 500 \
  --sample-size 200 \
  --asins-per-category 500 \
  --max-categories 3 \
  --sales-min 300 \
  --price-min 2500 \
  --output test_category_asins.txt

# 結果検証
python sourcing/scripts/check_duplicates.py \
  --input test_category_asins.txt \
  --report
```

---

## 期待される効果

### 定量的効果

| 指標 | Phase 1（販売数セグメント） | Phase 2-A（カテゴリベース） |
|------|---------------------------|---------------------------|
| 新規ASIN率 | 0% | **70-90%**（推定） |
| 1回の実行で取得可能な新規ASIN数 | 0件 | **5,000-15,000件**（推定） |
| カバーできるカテゴリ数 | 全カテゴリ混在 | **20-50カテゴリ**を体系的に |

### 定性的効果

**メリット:**
1. ✅ 各カテゴリで2,000件の上限をフル活用
2. ✅ カテゴリごとに異なる商品群をカバー
3. ✅ 未開拓カテゴリを優先して攻略
4. ✅ 既存データのカテゴリ分布を分析可能
5. ✅ 長期的に安定した新規ASIN取得が可能

**デメリット:**
1. ⚠️ 実装工数がやや大きい（初回のみ）
2. ⚠️ WebUIの変更に影響を受ける可能性
3. ⚠️ カテゴリメニューの操作が複雑な場合、実装が困難

---

## リスクと対策

### リスク1: カテゴリメニューのUI構造が複雑

**対策:**
- ステップ2で十分に調査
- シンプルな操作方法を優先
- 複雑な場合は、カテゴリ名での検索機能を活用

### リスク2: カテゴリ情報の取得に失敗

**対策:**
- テーブルの列インデックスをハードコードせず、列名で特定
- エラーハンドリングを充実
- フォールバック: カテゴリなしでも動作するようにする

### リスク3: 既存データとの重複率が依然として高い

**対策:**
- 初期サンプリングで重複率を確認してから本格実行
- カテゴリの粒度を調整（より細かいカテゴリを選択）
- 他のフィルター条件（レビュー数、発売日など）も併用

---

## 次のステップ

**即座に開始:**
1. ステップ1: カテゴリ情報取得機能の実装
2. ステップ2: WebUIのカテゴリメニュー調査

**その後:**
3. ステップ3: カテゴリ選択機能の実装
4. ステップ4: カテゴリ別抽出スクリプトの作成
5. ステップ5: 統合テスト

**完成後:**
- 10,000件の新規ASIN取得を目標に本格実行
- 結果をレポート化
- 定期実行の自動化を検討

---

**ドキュメント更新履歴:**
- 2025-11-26: 初版作成（Phase 2-A実装プラン）
