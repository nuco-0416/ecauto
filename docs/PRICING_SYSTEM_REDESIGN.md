# 価格決定システム再設計 - 実装計画書

**作成日**: 2025-12-02
**ステータス**: 🎉 全Phase完了
**担当**: Claude Code

---

## 📋 目次

1. [背景と目的](#背景と目的)
2. [現状分析](#現状分析)
3. [提案アーキテクチャ](#提案アーキテクチャ)
4. [実装計画](#実装計画)
5. [移行戦略](#移行戦略)
6. [考慮すべき関連領域](#考慮すべき関連領域)

---

## 背景と目的

### 現状の課題

- 価格決定ロジックが4つのファイルに分散実装されている
- マークアップ率（1.3）と最小価格差（100円）がハードコードされている
- 価格戦略の変更時に複数ファイルの修正が必要
- カテゴリ別や価格帯別の柔軟な価格設定ができない

### 改善目標

✅ **集中管理**: 価格決定ロジックを一元化
✅ **柔軟性**: 設定ファイルで簡単に係数を調整可能
✅ **拡張性**: 新しい価格戦略を容易に追加可能
✅ **安全性**: 既存運用への影響を最小限に抑える
✅ **監視性**: 価格変更の履歴と監査機能を強化

---

## 現状分析

### 価格決定ロジックの実装場所

| ファイル | 行番号 | 用途 | ハードコード値 |
|---------|--------|------|---------------|
| `platforms/base/scripts/sync_prices.py` | 55 | 定期価格同期 | `DEFAULT_MARKUP_RATIO = 1.3`<br>`MIN_PRICE_DIFF = 100` |
| `inventory/scripts/add_new_products.py` | 191 | 新規商品追加 | `default=1.3` |
| `scheduler/platform_uploaders/base_uploader.py` | 239 | BASE出品実行 | `price = int(amazon_price * 1.3)` |
| `scheduler/upload_executor.py` | 104 | アップロード準備 | `selling_price = int(amazon_price * 1.3)` |

### 共通ロジック

すべてのファイルで同じ計算式を使用：

```python
販売価格 = Amazon価格 × 1.3
```

価格調整（10円単位への丸め）:
```python
if selling_price % 10 != 0:
    selling_price = ((selling_price + 5) // 10) * 10
```

### 価格決定のタイミング

```
┌─────────────────────────────────────────────┐
│ 1. 新規商品追加時                            │
│    → add_new_products.py                   │
│    → SP-APIから価格取得 → 販売価格計算        │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│ 2. 出品実行時                                │
│    → upload_executor.py / base_uploader.py │
│    → マスタDBから価格取得 → 販売価格計算       │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│ 3. 定期価格同期時                            │
│    → sync_prices.py                        │
│    → SP-API最新価格取得 → 販売価格再計算      │
└─────────────────────────────────────────────┘
```

---

## 提案アーキテクチャ

### ディレクトリ構造

```
C:\Users\hiroo\Documents\GitHub\ecauto\
├── config/
│   └── pricing_strategy.yaml          # 価格戦略の設定ファイル
│
├── common/
│   └── pricing/
│       ├── __init__.py                # パッケージ初期化
│       ├── strategy.py                # 抽象基底クラス
│       ├── calculator.py              # 価格計算エンジン
│       ├── config_loader.py           # 設定ファイルローダー
│       └── strategies/
│           ├── __init__.py
│           ├── simple_markup.py       # シンプルマークアップ（現行ロジック）
│           ├── tiered_markup.py       # 価格帯別マークアップ
│           └── category_based.py      # カテゴリ別マークアップ（将来）
│
└── tests/
    └── pricing/
        ├── test_simple_markup.py
        ├── test_tiered_markup.py
        └── test_calculator.py
```

### クラス図

```
┌─────────────────────────────┐
│   PricingStrategy (ABC)     │  ← 抽象基底クラス
├─────────────────────────────┤
│ + calculate(amazon_price)   │
│ + validate_price(price)     │
│ + get_strategy_name()       │
└─────────────────────────────┘
            ▲
            │ 継承
     ┌──────┴──────┬──────────────┐
     │             │              │
┌─────────┐  ┌─────────┐  ┌─────────────┐
│ Simple  │  │ Tiered  │  │  Category   │
│ Markup  │  │ Markup  │  │   Based     │
└─────────┘  └─────────┘  └─────────────┘

┌────────────────────────────────┐
│   PriceCalculator              │  ← 価格計算エンジン
├────────────────────────────────┤
│ - strategy: PricingStrategy    │
│ - config: dict                 │
├────────────────────────────────┤
│ + calculate_selling_price()    │
│ + validate_safety_limits()     │
│ + round_price()                │
└────────────────────────────────┘

┌────────────────────────────────┐
│   ConfigLoader                 │  ← 設定ファイルローダー
├────────────────────────────────┤
│ + load_config()                │
│ + get_strategy()               │
│ + reload_config()              │
└────────────────────────────────┘
```

---

## 設定ファイル構造

### config/pricing_strategy.yaml

```yaml
# ========================================
# 価格戦略設定ファイル
# ========================================

# デフォルト戦略
default_strategy: "simple_markup"

# 戦略別設定
strategies:
  # シンプルマークアップ（現行ロジック）
  simple_markup:
    markup_ratio: 1.3          # マークアップ率（30%利益）
    min_price_diff: 100        # 価格更新の最小差額（円）
    round_to: 10               # 価格の丸め単位（円）

  # 価格帯別マークアップ
  tiered_markup:
    tiers:
      - max_price: 1000
        markup_ratio: 1.4      # 1000円以下は40%
      - max_price: 5000
        markup_ratio: 1.3      # 1001-5000円は30%
      - max_price: 10000
        markup_ratio: 1.25     # 5001-10000円は25%
      - max_price: null
        markup_ratio: 1.2      # 10001円以上は20%
    min_price_diff: 100
    round_to: 10

  # カテゴリ別マークアップ（将来実装）
  category_based:
    default_markup_ratio: 1.3
    category_overrides:
      electronics: 1.25        # 家電は25%
      books: 1.4               # 本は40%
      toys: 1.35               # おもちゃは35%
    min_price_diff: 100
    round_to: 10

# プラットフォーム別オーバーライド（将来実装）
platform_overrides:
  base:
    strategy: "simple_markup"
  # mercari:
  #   strategy: "tiered_markup"

# 安全装置
safety:
  min_selling_price: 500       # 最低出品価格（円）
  max_selling_price: 100000    # 最高出品価格（円）
  max_markup_ratio: 2.0        # 最大マークアップ率（異常検知）
  min_markup_ratio: 1.05       # 最小マークアップ率（異常検知）

# ログ設定
logging:
  log_price_changes: true      # 価格変更をログに記録
  log_strategy_used: true      # 使用した戦略をログに記録
  alert_on_extreme_price: true # 極端な価格の場合に警告
```

---

## 実装計画

### Phase 1: 基盤構築（既存への影響なし）

**目標**: 新しい価格決定モジュールを構築し、テストする

#### タスク1: ディレクトリ構造の作成
```bash
common/pricing/
├── __init__.py
├── strategy.py
├── calculator.py
├── config_loader.py
└── strategies/
    ├── __init__.py
    ├── simple_markup.py
    └── tiered_markup.py
```

#### タスク2: 抽象基底クラスの実装
**ファイル**: `common/pricing/strategy.py`

```python
from abc import ABC, abstractmethod
from typing import Dict, Any

class PricingStrategy(ABC):
    """価格戦略の抽象基底クラス"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    @abstractmethod
    def calculate(self, amazon_price: int) -> int:
        """Amazon価格から販売価格を計算"""
        pass

    @abstractmethod
    def get_strategy_name(self) -> str:
        """戦略名を取得"""
        pass

    def validate_price(self, price: int, safety_config: Dict[str, Any]) -> bool:
        """価格が安全範囲内かチェック"""
        min_price = safety_config.get('min_selling_price', 0)
        max_price = safety_config.get('max_selling_price', float('inf'))
        return min_price <= price <= max_price
```

#### タスク3: SimpleMarkupStrategy の実装
**ファイル**: `common/pricing/strategies/simple_markup.py`

現行ロジック（Amazon価格 × 1.3）を実装

#### タスク4: TieredMarkupStrategy の実装
**ファイル**: `common/pricing/strategies/tiered_markup.py`

価格帯別のマークアップ率を適用

#### タスク5: 設定ファイルローダーの実装
**ファイル**: `common/pricing/config_loader.py`

YAMLファイルの読み込みと戦略インスタンスの生成

#### タスク6: 価格計算エンジンの実装
**ファイル**: `common/pricing/calculator.py`

統一的なインターフェースで価格計算を実行

#### タスク7: ユニットテストの作成
- `test_simple_markup.py`: SimpleMarkupStrategyのテスト
- `test_tiered_markup.py`: TieredMarkupStrategyのテスト
- `test_calculator.py`: PriceCalculatorのテスト

**実行**:
```bash
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' -m pytest tests/pricing/ -v"
```

---

### Phase 2: 既存コードとの統合 ✅ **完了**

**目標**: 既存の5ファイルに新しい価格決定モジュールを統合

#### 統合順序（リスクの低い順）

1. **add_new_products.py** (新規商品追加) ✅
   - バックアップ: `add_new_products.py.backup_pricing_integration`
   - 変更内容: `calculate_selling_price()` 関数を削除、PriceCalculatorを使用
   - 構文チェック: 成功

2. **import_candidates_to_master.py** (候補商品インポート) ✅
   - バックアップ: `import_candidates_to_master.py.backup_pricing_integration`
   - 変更内容: インライン価格計算を削除、PriceCalculatorを使用
   - 構文チェック: 成功

3. **sync_prices.py** (定期同期スクリプト) ✅
   - バックアップ: `sync_prices.py.backup_pricing_integration`
   - 変更内容: `calculate_selling_price()` メソッドを新モジュール経由に変更
   - 構文チェック: 成功
   - 実行テスト: PriceCalculatorの初期化成功を確認

4. **base_uploader.py** (BASE出品) ✅
   - バックアップ: `base_uploader.py.backup_pricing_integration`
   - 変更内容: `_prepare_item_data()` 内の価格計算を新モジュール経由に変更
   - 構文チェック: 成功

5. **upload_executor.py** (アップロード実行) ✅
   - バックアップ: `upload_executor.py.backup_pricing_integration`
   - 変更内容: BASE/eBay両方の価格計算を新モジュール経由に変更
   - 構文チェック: 成功

#### 統合パターン（例: sync_prices.py）

**Before**:
```python
def calculate_selling_price(self, amazon_price: int, markup_ratio: float = 1.3) -> int:
    selling_price = int(amazon_price * markup_ratio)
    if selling_price % 10 != 0:
        selling_price = ((selling_price + 5) // 10) * 10
    return selling_price
```

**After**:
```python
from common.pricing.calculator import PriceCalculator

def __init__(self):
    # ...
    self.price_calculator = PriceCalculator()

def calculate_selling_price(self, amazon_price: int, markup_ratio: float = None) -> int:
    # 新しい価格計算モジュールを使用
    return self.price_calculator.calculate_selling_price(
        amazon_price=amazon_price,
        override_markup_ratio=markup_ratio  # CLIオプションでのオーバーライドに対応
    )
```

---

### Phase 3: 監視と拡張機能

**目標**: 価格変更の監視と異常検知機能を追加

#### タスク1: 価格変更履歴テーブルの追加

```sql
CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asin TEXT NOT NULL,
    platform TEXT NOT NULL,
    account_id TEXT,
    old_price REAL,
    new_price REAL,
    amazon_price_jpy INTEGER,
    markup_ratio REAL,
    strategy_used TEXT,
    changed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    change_reason TEXT,
    FOREIGN KEY (asin) REFERENCES products(asin)
);

CREATE INDEX idx_price_history_asin ON price_history(asin);
CREATE INDEX idx_price_history_changed_at ON price_history(changed_at);
```

#### タスク2: 異常価格検知機能

```python
def detect_price_anomaly(self, amazon_price: int, selling_price: int) -> bool:
    """異常な価格設定を検知"""
    markup_ratio = selling_price / amazon_price if amazon_price > 0 else 0

    # 設定ファイルから閾値を取得
    max_markup = self.config['safety']['max_markup_ratio']
    min_markup = self.config['safety']['min_markup_ratio']

    if markup_ratio > max_markup or markup_ratio < min_markup:
        logging.warning(
            f"異常な価格設定を検知: Amazon価格={amazon_price}円, "
            f"販売価格={selling_price}円, マークアップ率={markup_ratio:.2f}"
        )
        return True
    return False
```

#### タスク3: 価格変更通知機能

`config/notifications.json` に価格関連の通知設定を追加

---

## 移行戦略

### ロールバック計画

各統合ステップで以下を実施：

1. **バックアップ作成**
   ```bash
   copy <元ファイル> <元ファイル>.backup
   ```

2. **動作確認テスト**
   - DRY RUNモードでテスト
   - 少数データでテスト
   - ログ出力を確認

3. **問題発生時のロールバック**
   ```bash
   copy <元ファイル>.backup <元ファイル>
   ```

### 並行運用期間

- **期間**: Phase 2 統合後 1週間
- **監視項目**:
  - 価格計算の正確性
  - エラー発生率
  - パフォーマンス（処理時間）
  - API呼び出し回数

### 完全移行の条件

✅ すべてのユニットテストが成功
✅ 4つの既存ファイルがすべて新モジュールを使用
✅ 並行運用期間中にエラーなし
✅ 価格計算結果が期待通り
✅ パフォーマンス劣化なし

---

## 考慮すべき関連領域

### 1. 在庫同期との連携

**ファイル**: `platforms/base/scripts/sync_inventory_status.py`

**考慮点**:
- 在庫切れ時の価格戦略（再入荷時に価格を再計算するか？）
- 在庫レベルに基づく動的価格設定（将来的に）

**推奨**: 価格同期と在庫同期を統合したスクリプトの検討

### 2. 販売実績との連携

**ディレクトリ**: `integrations/base_sales_webhook/`

**考慮点**:
- 販売後の価格更新トリガー（同じ商品の再出品時）
- 販売実績に基づく価格最適化（将来的に）

### 3. エラーハンドリングと通知

**ファイル**: `config/notifications.json`

**追加すべき通知項目**:
- 異常価格の検知（極端に高い/低い価格）
- 価格計算エラー
- 設定ファイルの読み込みエラー

### 4. データベーススキーマの拡張

**listingsテーブルへの追加カラム案**:
```sql
ALTER TABLE listings ADD COLUMN pricing_strategy TEXT;        -- 使用した価格戦略名
ALTER TABLE listings ADD COLUMN markup_ratio REAL;            -- 実際に適用したマークアップ率
ALTER TABLE listings ADD COLUMN price_updated_at DATETIME;    -- 価格最終更新日時
ALTER TABLE listings ADD COLUMN price_update_reason TEXT;     -- 更新理由
```

### 5. プラットフォーム間の価格一貫性

将来的に複数プラットフォーム展開時：
- プラットフォーム間での価格整合性
- プラットフォーム別の手数料を考慮した価格設定

### 6. パフォーマンスへの影響

**懸念点**:
- 設定ファイルの読み込みオーバーヘッド
- 戦略クラスのインスタンス化コスト

**対策**:
- 設定ファイルをメモリにキャッシュ
- 戦略インスタンスを再利用
- バッチ処理での最適化

---

## タイムライン

| フェーズ | 作業内容 | 所要時間（目安） |
|---------|---------|-----------------|
| **Phase 1** | 基盤構築とテスト | 実装中 |
| **Phase 2** | 既存コードとの統合 | 4ファイル × テスト |
| **Phase 3** | 監視機能の追加 | 追加実装 |

---

## 承認と変更履歴

| 日付 | 変更内容 | 承認者 |
|------|---------|--------|
| 2025-12-02 | 初版作成 | - |
| 2025-12-02 | Phase 1 実装開始 | ユーザー承認済 |
| 2025-12-02 | Phase 1 実装完了 | - |
| 2025-12-02 | Phase 2 実装開始 | - |
| 2025-12-02 | Phase 2 実装完了 | - |
| 2025-12-02 | Phase 3 実装開始 | - |
| 2025-12-02 | Phase 3 実装完了 | - |
| 2025-12-02 | 全Phase実装完了 🎉 | - |

---

## 参考資料

- [バッチ処理実装ドキュメント](BATCH_PROCESSING_IMPLEMENTATION.md)
- [SP-API レート制限対応](issues/ISSUE_006_sp_api_rate_limit_getpricing_migration.md)
- [プロジェクトガイドライン](.claude/CLAUDE.md)

---

## 📊 実装進捗サマリー

### ✅ Phase 1: 基盤構築 - 完了
- ディレクトリ構造作成
- 抽象基底クラス（PricingStrategy）実装
- SimpleMarkupStrategy 実装（現行ロジック）
- TieredMarkupStrategy 実装（価格帯別）
- 設定ファイルローダー（ConfigLoader）実装
- 価格計算エンジン（PriceCalculator）実装
- 設定ファイル（pricing_strategy.yaml）作成
- ユニットテスト作成

### ✅ Phase 2: 既存コードとの統合 - 完了
- add_new_products.py - 統合完了
- import_candidates_to_master.py - 統合完了
- sync_prices.py - 統合完了
- base_uploader.py - 統合完了
- upload_executor.py - 統合完了
- 全ファイルの構文チェック成功
- PriceCalculator初期化テスト成功

### ✅ Phase 3: 監視と拡張機能 - 完了
- ✅ 価格変更履歴テーブルの追加（price_history テーブル作成）
- ✅ MasterDB に価格履歴メソッド追加（add_price_history_record, get_price_history）
- ✅ 異常価格検知機能（PriceCalculator._alert_extreme_price メソッドで実装済み）
- ⏸️ 価格変更通知機能（将来的な拡張として保留）

---

## 🎉 実装完了サマリー

価格決定システムの再設計が完了しました！

### 主な成果

1. **価格ロジックの一元化**: 5つのファイルに分散していた価格計算ロジックを `common/pricing/` に統一
2. **柔軟な価格戦略**: 設定ファイル（YAML）で簡単に価格戦略を変更可能
3. **安全装置の強化**: 異常価格の検知と自動補正
4. **価格変更の追跡**: price_history テーブルで全ての価格変更を記録
5. **後方互換性**: 既存のCLIオプション（--markup-ratio）を維持

### 統合済みファイル（5ファイル）

| ファイル | 統合内容 | バックアップ |
|---------|---------|------------|
| add_new_products.py | PriceCalculator統合 | ✅ |
| import_candidates_to_master.py | PriceCalculator統合 | ✅ |
| sync_prices.py | PriceCalculator統合 | ✅ |
| base_uploader.py | PriceCalculator統合 | ✅ |
| upload_executor.py | PriceCalculator統合（BASE/eBay両対応） | ✅ |

### 新規追加ファイル

| ファイル | 説明 |
|---------|------|
| `common/pricing/strategy.py` | 価格戦略の抽象基底クラス |
| `common/pricing/calculator.py` | 価格計算エンジン |
| `common/pricing/config_loader.py` | 設定ファイルローダー |
| `common/pricing/strategies/simple_markup.py` | シンプルマークアップ戦略 |
| `common/pricing/strategies/tiered_markup.py` | 価格帯別マークアップ戦略 |
| `config/pricing_strategy.yaml` | 価格戦略設定ファイル |
| `tests/pricing/test_simple_markup.py` | SimpleMarkupStrategyテスト |
| `tests/pricing/test_tiered_markup.py` | TieredMarkupStrategyテスト |
| `tests/pricing/test_calculator.py` | PriceCalculatorテスト |

### データベース拡張

| テーブル | 説明 |
|---------|------|
| `price_history` | 価格変更履歴（ASIN、プラットフォーム、価格変動、戦略名など） |

### 今後の拡張案

1. **価格変更通知**: config/notifications.json に価格関連の通知設定を追加
2. **カテゴリ別価格戦略**: CategoryBasedStrategy の実装
3. **価格最適化**: 販売実績に基づく動的価格設定
4. **ダッシュボード**: 価格変更履歴の可視化

---

**🎯 次のアクション**: 本番環境での動作確認と、実際の価格同期処理での検証を推奨します。
