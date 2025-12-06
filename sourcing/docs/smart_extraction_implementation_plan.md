# スマート抽出システム実装プラン

**作成日**: 2025-11-26
**目的**: sourcing.dbとの重複を最小化し、効率的に新規ASINを大量取得するシステムの構築

---

## 📋 目次

1. [現状の問題点](#現状の問題点)
2. [根本原因の分析](#根本原因の分析)
3. [解決策の概要](#解決策の概要)
4. [実装プラン](#実装プラン)
5. [技術仕様](#技術仕様)
6. [期待される効果](#期待される効果)

---

## 現状の問題点

### 重複率100%の問題

**事象:**
- 2025-11-26に3,000ASIN取得を試みた結果、**重複率100%（新規ASIN 0件）**
- 取得したASINはすべて既存のsourcing.dbに存在

**影響:**
- 新規ASIN取得の効率が極めて低い
- 同じセグメントで何度実行しても同じ結果

### SellerSprite Web版の制約

**仕様上の制限:**
- 検索結果が20万ASINあっても、**WebUIでは上位20ページ（2,000ASIN）までしか取得不可**
- ページネーションの限界により、下位198,000ASINにアクセスできない

**具体例:**
```
条件: 販売数300以上 × 価格2,500円以上
結果: 200,000件ヒット
取得可能: 上位2,000件のみ ← 常に同じASIN
```

---

## 根本原因の分析

### extraction_logs の分析結果

既存の抽出パターンを分析した結果：

| ID | 販売数条件 | 価格帯 | 取得件数 | 実行日 |
|----|----------|--------|---------|--------|
| 31 | 300以上（上限なし） | 2,500-5,000 | 1,000 | 2025-11-26 |
| 32 | 300以上（上限なし） | 5,000-10,000 | 1,000 | 2025-11-26 |
| 33 | 300以上（上限なし） | 10,000-20,000 | 1,000 | 2025-11-26 |
| 28-30 | 300以上（上限なし） | 各種価格帯 | 600-600 | 2025-11-25 |

**共通パターン:**
- すべて `sales_min: 300, sales_max: null`（販売数300以上、上限なし）
- 価格帯のみで分割
- 販売数の上限を設定していない

**問題:**
→ 常に「販売数300以上」の**上位2,000ASINのみ**を取得している
→ 同じ条件 = 同じ結果 = 重複率100%

### 未開拓エリアの存在

**20万ASINのうち、下位198,000ASINが未開拓:**
- 販売数300-350件/月のASIN
- 販売数350-400件/月のASIN
- 販売数400-500件/月のASIN
- ...

これらは既存の抽出条件（300以上、上限なし）でも**検索結果には含まれる**が、**上位2,000件に入らない**ため取得できていない。

---

## 解決策の概要

### 戦略: 販売数セグメント分割で下位を掘り起こす

**コンセプト:**
1. **販売数に上限を設定**して細かくセグメント化
2. 各セグメントの結果を2,000件未満に抑える
3. 下位の販売数レンジを体系的にカバー

**具体例:**
```
従来: sales_min=300, sales_max=null → 上位2,000件のみ
改善:
  - sales_min=300, sales_max=350 → 異なる2,000件
  - sales_min=350, sales_max=400 → 異なる2,000件
  - sales_min=400, sales_max=500 → 異なる2,000件
```

### 2段階アプローチ

#### Phase 1: 即座の改善（手動セグメント指定）
- 販売数セグメント分割を手動で実行
- 既存の `extract_asins_bulk.py` を活用
- 迅速に新規ASINを取得

#### Phase 2: スマート抽出システム（自動化）
- 抽出履歴を自動分析
- 未開拓セグメントを自動提案
- 目標達成まで自動リトライ

---

## 実装プラン

### Phase 1: 販売数セグメント分割での即座の改善

**目標:** 3,000件の新規ASINを取得

**実行コマンド:**
```bash
python sourcing/scripts/extract_asins_bulk.py \
  --strategy segment \
  --segment-type sales \
  --segments "300-350,350-400,400-450,450-500,500-600,600-800" \
  --price-min 2500 \
  --count-per-segment 500 \
  --output base_asins_new_sales_segment_20251126.txt
```

**セグメント設計:**
| セグメント | 販売数範囲 | 価格条件 | 取得目標 |
|----------|----------|---------|---------|
| 1 | 300-350 | 2,500円以上 | 500件 |
| 2 | 350-400 | 2,500円以上 | 500件 |
| 3 | 400-450 | 2,500円以上 | 500件 |
| 4 | 450-500 | 2,500円以上 | 500件 |
| 5 | 500-600 | 2,500円以上 | 500件 |
| 6 | 600-800 | 2,500円以上 | 500件 |
| **合計** | - | - | **3,000件** |

**期待される結果:**
- 既存パターンと完全に異なるセグメント
- 新規ASIN率: 70-90%以上（推定）

**検証方法:**
```python
# 取得後、重複チェックスクリプトで検証
python sourcing/scripts/check_duplicates.py \
  --input base_asins_new_sales_segment_20251126.txt \
  --report
```

---

### Phase 2: スマート抽出システムの構築

**新規スクリプト:** `sourcing/scripts/smart_extract_asins.py`

**機能概要:**
1. **抽出履歴分析**
   - `extraction_logs`から過去のパターンを読み込み
   - 未使用セグメントを自動特定

2. **リアルタイム重複チェック**
   - 取得したASINを即座に`sourcing_candidates`と照合
   - 新規ASIN率を計算・表示

3. **自動セグメント選択**
   - 重複率の低いセグメントを優先
   - 目標新規件数に達するまで未開拓セグメントを自動試行

4. **インテリジェントリトライ**
   - 重複率が高い（例: >50%）場合は次のセグメントへ自動移行
   - 最大試行回数制限

5. **詳細レポート生成**
   - 取得結果の統計
   - 使用セグメント一覧
   - 重複率分析
   - 未開拓セグメント提案

---

## 技術仕様

### 新規スクリプト: `smart_extract_asins.py`

#### コマンドライン引数

```bash
python sourcing/scripts/smart_extract_asins.py \
  --target-new-asins 3000 \           # 目標新規ASIN数
  --price-min 2500 \                  # 価格最小値
  --max-duplicates-rate 0.3 \         # 重複率上限（30%）
  --max-attempts 20 \                 # 最大試行回数
  --segment-size 500 \                # 各セグメント取得数
  --output base_asins_smart_YYYYMMDD.txt \
  --report-output extraction_report_YYYYMMDD.md
```

#### 内部ロジック

**1. 初期化フェーズ**
```python
def initialize():
    # sourcing.dbから既存ASINをロード
    existing_asins = load_existing_asins()

    # extraction_logsから抽出履歴をロード
    extraction_history = load_extraction_logs()

    # 未開拓セグメントを特定
    unexplored_segments = identify_unexplored_segments(extraction_history)

    return existing_asins, unexplored_segments
```

**2. セグメント選択アルゴリズム**
```python
def select_next_segment(unexplored_segments, extraction_history):
    """
    優先順位:
    1. 過去に未使用のセグメント
    2. 重複率が低かったセグメント範囲
    3. ランダムな未開拓セグメント
    """
    # 販売数範囲のグリッドを生成
    sales_grid = generate_sales_grid(
        min=100, max=2000, step=50
    )

    # 既存パターンと重複しないセグメントを選択
    for segment in sales_grid:
        if not is_used(segment, extraction_history):
            return segment

    return None
```

**3. 抽出ループ**
```python
def smart_extraction_loop(target_new_asins, max_attempts):
    new_asins = set()
    attempts = 0

    while len(new_asins) < target_new_asins and attempts < max_attempts:
        # 次のセグメントを選択
        segment = select_next_segment(...)

        # 抽出実行
        extracted_asins = extract_from_segment(segment)

        # リアルタイム重複チェック
        truly_new = extracted_asins - existing_asins - new_asins
        duplicate_rate = 1 - (len(truly_new) / len(extracted_asins))

        # 結果を記録
        new_asins.update(truly_new)
        log_extraction(segment, len(truly_new), duplicate_rate)

        # 重複率が高い場合は警告
        if duplicate_rate > max_duplicates_rate:
            print(f"⚠️ 重複率高い ({duplicate_rate:.1%}), 次のセグメントへ")

        attempts += 1

    return new_asins
```

**4. レポート生成**
```python
def generate_report(new_asins, segments_used, total_attempts):
    """
    Markdown形式のレポートを生成:
    - 取得結果サマリー
    - セグメント別統計
    - 重複率分析
    - 未開拓エリア提案
    """
    pass
```

#### データ構造

**セグメント表現:**
```python
@dataclass
class ExtractionSegment:
    sales_min: int
    sales_max: int
    price_min: int
    price_max: Optional[int]
    market: str = "JP"

    def to_params(self) -> dict:
        """extract_asins_bulk.py に渡すパラメータ"""
        return {
            "sales_min": self.sales_min,
            "sales_max": self.sales_max,
            "price_min": self.price_min,
            "price_max": self.price_max,
            "market": self.market,
        }
```

**抽出結果:**
```python
@dataclass
class ExtractionResult:
    segment: ExtractionSegment
    asins_found: int
    new_asins: int
    duplicate_rate: float
    execution_time: float
    timestamp: datetime
```

#### データベース連携

**extraction_logsへの記録:**
```python
def log_to_database(segment: ExtractionSegment, result: ExtractionResult):
    conn = sqlite3.connect('sourcing/data/sourcing.db')
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO extraction_logs
        (extraction_type, parameters, asins_found, status, started_at, completed_at)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        'product_research',
        json.dumps(segment.to_params()),
        result.asins_found,
        'completed',
        result.timestamp,
        result.timestamp
    ))

    conn.commit()
    conn.close()
```

---

### 補助スクリプト: `analyze_extraction_history.py`

**目的:** 既存の抽出履歴を可視化し、未開拓セグメントを提案

**機能:**
1. extraction_logsの統計サマリー
2. 価格帯×販売数のヒートマップ生成
3. 未開拓セグメント一覧
4. 次回実行の推奨パラメータ

**実行例:**
```bash
python sourcing/scripts/analyze_extraction_history.py \
  --output-report sourcing/docs/extraction_history_analysis.md \
  --visualize
```

---

### 補助スクリプト: `check_duplicates.py`

**目的:** ASINファイルとsourcing.dbの重複をチェック

**機能:**
1. ファイル内ASINとDB内ASINの照合
2. 重複率の計算
3. 新規ASIN一覧の出力

**実行例:**
```bash
python sourcing/scripts/check_duplicates.py \
  --input base_asins_3000_20251126.txt \
  --output new_asins_only.txt \
  --report
```

**出力:**
```
【重複チェック結果】
ファイル内ASIN数: 2,999件
DB内既存ASIN数: 3,467件
重複ASIN数: 2,999件 (100.0%)
新規ASIN数: 0件 (0.0%)

新規ASINを new_asins_only.txt に保存しました。
```

---

## 期待される効果

### 定量的効果

| 指標 | 現状 | Phase 1実施後 | Phase 2実施後 |
|------|------|--------------|--------------|
| 新規ASIN率 | 0% | 70-90% | 85-95% |
| 3,000件取得の所要時間 | N/A（取得不可） | 約5-7分 | 約5-10分（自動） |
| 手動作業時間 | 30分/回 | 10分/回 | 0分（完全自動） |

### 定性的効果

**Phase 1実施後:**
- ✅ 新規ASINの安定取得が可能
- ✅ 重複率の大幅な低下
- ⚠️ セグメント選択は手動

**Phase 2実施後:**
- ✅ 完全自動化
- ✅ 抽出履歴の活用
- ✅ 未開拓エリアの自動探索
- ✅ 効率的なセグメント選択
- ✅ 詳細なレポート生成

---

## 実装スケジュール

### Phase 1: 即座の改善（目安: 10分）

- [x] 問題分析完了
- [ ] 販売数セグメント分割で実行
- [ ] 結果検証（重複率チェック）
- [ ] 有効性の確認

### Phase 2: スマート抽出システム（目安: 2-3時間）

#### ステップ1: 補助スクリプト作成（30分）
- [ ] `check_duplicates.py` 作成
- [ ] `analyze_extraction_history.py` 作成
- [ ] 動作確認

#### ステップ2: コア機能実装（1時間）
- [ ] `smart_extract_asins.py` スケルトン作成
- [ ] 抽出履歴分析機能
- [ ] セグメント選択アルゴリズム
- [ ] リアルタイム重複チェック

#### ステップ3: 統合とテスト（30分）
- [ ] extract_asins_bulk.py との連携
- [ ] DB読み書き機能
- [ ] エラーハンドリング
- [ ] ドライラン実行

#### ステップ4: 本番実行と検証（30分）
- [ ] 目標3,000件での実行
- [ ] 結果検証
- [ ] レポート生成
- [ ] ドキュメント更新

---

## 付録: セグメント設計のベストプラクティス

### 販売数レンジの設計指針

**基本原則:**
1. 各セグメントの検索結果が2,000件未満になるように設計
2. 下位レンジほど細かく分割（データ量が多いため）
3. 上位レンジは広めでOK（データ量が少ないため）

**推奨セグメント設計例:**

**パターンA: 細かい分割（新規ASIN重視）**
```
300-320, 320-340, 340-360, 360-380, 380-400,
400-420, 420-440, 440-460, 460-480, 480-500,
500-550, 550-600, 600-700, 700-800, 800-1000,
1000-1500, 1500-2000, 2000-3000
```

**パターンB: バランス型**
```
300-350, 350-400, 400-450, 450-500,
500-600, 600-700, 700-800, 800-1000,
1000-1500, 1500-2000
```

**パターンC: 粗い分割（速度重視）**
```
300-400, 400-500, 500-700, 700-1000, 1000-2000
```

### 価格帯との組み合わせ

より細かい制御が必要な場合は、価格帯も併用：

```
# 低価格帯（データ量多い）→ 販売数を細かく
価格: 2,500-5,000円
販売数: 300-320, 320-340, 340-360, ...

# 高価格帯（データ量少ない）→ 販売数を広く
価格: 20,000-50,000円
販売数: 300-500, 500-1000, 1000-2000
```

---

## まとめ

### 重要なポイント

1. **SellerSprite Web版の制約を理解する**
   - 上位2,000件しか取得できない
   - セグメント分割で下位データにアクセス

2. **販売数に上限を設定する**
   - `sales_max`を活用
   - 既存パターンと重複しないセグメントを選択

3. **抽出履歴を活用する**
   - extraction_logsで過去のパターンを確認
   - 未開拓セグメントを優先

4. **段階的にアプローチする**
   - Phase 1: 手動で迅速に改善
   - Phase 2: 自動化で長期的な効率化

### 次のアクション

1. **Phase 1実行**: 販売数セグメント分割で3,000件取得
2. **結果検証**: 新規ASIN率の確認
3. **Phase 2判断**: 自動化の必要性を評価
4. **継続的改善**: セグメント設計の最適化

---

**ドキュメント更新履歴:**
- 2025-11-26: 初版作成
