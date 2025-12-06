# LLM販売分析機能 - 実装計画

最終更新: 2025-11-26

## 📋 概要

SellerSpriteからのASIN抽出とLLMを活用した販売分析機能を段階的に実装する。

**最終目標:**
- 2000-3000件/日のASIN自動抽出
- 販売データに基づく完全自律的な商品発掘

**現在の進捗:**
- ✅ **Phase 0完了**（2025-11-25）: 認証システム統一・動作検証
- ✅ **Phase 1一部完了**（2025-11-26）: 2034件のASIN抽出成功、出品連携完了

---

## 🎯 段階的実装アプローチ

### 優先度1：手動パラメータでのASIN大量取得 🔥

**目標:** 人間が指定したパラメータでスクリプト実行 → 2000-3000件/日のASIN取得

**必要な実装:**
- Playwrightセッション管理
- SellerSprite操作の定型スクリプト化
- MCP（Model Context Protocol）による操作記録で開発効率化

**実行イメージ:**
```bash
# 手動でパラメータ指定
python sourcing/scripts/extract_asins.py \
  --pattern ranking \
  --category "おもちゃ・ホビー" \
  --min-rank 1 \
  --max-rank 1000 \
  --output data/asins_20250122.txt
```

---

### 優先度2：LLMがパラメータを決定（セミオート）⚡

**目標:** スクリプト内のプロンプトに基づいてLLMがカテゴリ・条件を決定

**必要な実装:**
- スクリプト内からのLLM呼び出し
- 抽出方針をプロンプトで記述
- LLMがパラメータ生成 → 優先度1のスクリプトを実行

**実行イメージ:**
```bash
# プロンプトで指示
python sourcing/scripts/extract_asins_smart.py \
  --prompt "直近で販売数が急増している冬物のおもちゃカテゴリからASINを3000件抽出"
```

**内部動作:**
1. LLMがプロンプトを解釈
2. 抽出パラメータを生成（カテゴリ: "おもちゃ・ホビー > 冬物", ソート: "販売数降順", 件数: 3000）
3. 優先度1のスクリプトを内部で実行

---

### 優先度3：完全自律的なASIN抽出（フルオート）🤖

**目標:** 販売データを分析してLLMが自律的に抽出戦略を立案・実行

**必要な実装:**
- 各種データ連携システム（BASE、メルカリ、eBay、Yahoo!オークション、Amazon Business）
- データ統合・トレンド分析
- LLMによる抽出戦略の自動生成

**実行イメージ:**
```bash
# パラメータ指定なし、完全自動
python sourcing/scripts/autonomous_extraction.py \
  --daily-target 3000
```

**内部動作:**
1. `analytics/`が過去30日の販売データを集計
2. LLMが「売れ筋カテゴリ」「利益率が高い商品」「在庫回転率」を分析
3. LLMが抽出戦略を生成（例：「スポーツ用品の売上が20%増、カテゴリXから2000件抽出すべき」）
4. 優先度2のスクリプトを自動実行

---

## 📁 ディレクトリ構造

```
ecauto/
├── sourcing/                           # 仕入元管理モジュール
│   ├── core/
│   │   ├── __init__.py
│   │   ├── llm_client.py              # LLM APIクライアント（優先度2）
│   │   └── parameter_generator.py     # パラメータ生成（優先度2）
│   │
│   ├── sources/
│   │   ├── __init__.py
│   │   ├── sellersprite/              # SellerSprite連携
│   │   │   ├── __init__.py
│   │   │   ├── auth_manager.py        # Cookie認証管理
│   │   │   ├── browser_controller.py  # Playwright操作基盤
│   │   │   ├── extractors/            # 抽出パターン別スクリプト
│   │   │   │   ├── __init__.py
│   │   │   │   ├── base_extractor.py  # 抽出基底クラス
│   │   │   │   ├── ranking_extractor.py      # ランキング抽出
│   │   │   │   ├── category_extractor.py     # カテゴリ深掘り抽出
│   │   │   │   ├── seasonal_extractor.py     # 季節需要抽出
│   │   │   │   └── smart_extractor.py        # LLM連携抽出（優先度2）
│   │   │   ├── prompts/               # プロンプトテンプレート（優先度2）
│   │   │   │   ├── ranking_prompt.txt
│   │   │   │   ├── category_prompt.txt
│   │   │   │   └── seasonal_prompt.txt
│   │   │   └── mcp_recorder.py        # MCP操作録画ツール
│   │   └── amazon_business/           # Amazon Business仕入データ（優先度3）
│   │       ├── __init__.py
│   │       └── procurement_importer.py
│   │
│   ├── data/
│   │   ├── sourcing.db                # 仕入候補DB
│   │   ├── sellersprite_cookies.json  # SellerSprite Cookie
│   │   └── extraction_logs/           # 抽出ログ
│   │
│   └── scripts/
│       ├── extract_asins.py           # メイン実行スクリプト（優先度1）
│       ├── extract_asins_smart.py     # LLM連携スクリプト（優先度2）
│       ├── autonomous_extraction.py   # 自律実行エンジン（優先度3）
│       └── record_new_pattern.py      # MCP録画用スクリプト
│
├── analytics/                          # 販売分析モジュール（優先度3）
│   ├── core/
│   │   ├── __init__.py
│   │   ├── data_aggregator.py         # データ統合
│   │   ├── trend_analyzer.py          # トレンド分析
│   │   ├── strategy_generator.py      # 抽出戦略生成
│   │   └── report_generator.py        # レポート生成
│   │
│   ├── collectors/                     # データ収集モジュール
│   │   ├── __init__.py
│   │   ├── base_collector.py          # BASE売上データ取得
│   │   ├── mercari_collector.py       # メルカリ売上データ
│   │   ├── ebay_collector.py          # eBay売上データ
│   │   ├── yahoo_collector.py         # Yahoo!オークション売上データ
│   │   └── amazon_business_collector.py # Amazon Business発注データ
│   │
│   ├── data/
│   │   ├── analytics.db               # 分析用DB
│   │   └── llm_cache/                 # LLMレスポンスキャッシュ
│   │
│   └── scripts/
│       ├── collect_sales_data.py      # 全プラットフォームから売上収集
│       ├── analyze_performance.py     # 販売実績分析
│       └── auto_extract.py            # 完全自動抽出
│
└── shared/                             # 共通ライブラリ
    ├── llm/                            # LLM共通モジュール（優先度2）
    │   ├── __init__.py
    │   ├── base_client.py             # LLM基底クラス
    │   ├── openai_client.py           # GPT-5クライアント
    │   ├── claude_client.py           # Claudeクライアント
    │   ├── gemini_client.py           # Geminiクライアント
    │   └── cache_manager.py           # LLMレスポンスキャッシュ
    │
    └── (既存のamazon/, utils/, config/)
```

---

## 🗄️ データベース設計

### sourcing.db（仕入管理）

```sql
-- 仕入候補商品
CREATE TABLE sourcing_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asin TEXT UNIQUE,
    source TEXT,  -- 'sellersprite', 'amazon_business'
    source_item_id TEXT,

    -- SellerSpriteデータ
    sales_rank INTEGER,
    category TEXT,
    estimated_monthly_sales INTEGER,
    current_price_jpy INTEGER,

    -- LLM評価結果（優先度2以降）
    llm_evaluation_score REAL,  -- 0.0-1.0
    llm_reason TEXT,
    llm_tags TEXT,  -- JSON: ["seasonal", "trending", "high_profit"]

    -- ステータス
    status TEXT DEFAULT 'candidate',  -- 'candidate', 'approved', 'rejected', 'imported'
    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    evaluated_at TIMESTAMP,
    imported_at TIMESTAMP
);

-- SellerSprite抽出ログ
CREATE TABLE extraction_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    extraction_type TEXT,  -- 'ranking', 'category', 'seasonal'
    parameters TEXT,  -- JSON: {"category": "おもちゃ", "min_rank": 1, "max_rank": 1000}
    asins_found INTEGER,
    status TEXT DEFAULT 'running',  -- 'running', 'completed', 'failed'
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT
);

-- 抽出パターン定義（スクリプト録画結果）
CREATE TABLE extraction_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_name TEXT UNIQUE,
    pattern_type TEXT,  -- 'ranking', 'category', 'seasonal'
    playwright_script TEXT,  -- Pythonコード（async def extract()）
    parameters_schema TEXT,  -- JSON Schema for validation
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP
);
```

### analytics.db（販売分析 - 優先度3）

```sql
-- 販売実績（全プラットフォーム統合）
CREATE TABLE sales_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asin TEXT,
    platform TEXT,  -- 'base', 'mercari', 'ebay', 'yahoo'
    account_id TEXT,
    order_id TEXT UNIQUE,

    sold_at TIMESTAMP,
    selling_price REAL,
    cost_price REAL,
    profit REAL,
    profit_margin REAL,  -- 利益率
    quantity INTEGER DEFAULT 1,

    FOREIGN KEY (asin) REFERENCES products(asin)
);

-- 仕入実績（複数仕入元対応）
CREATE TABLE procurement_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asin TEXT,
    source TEXT,  -- 'amazon_business', '1688', etc
    order_id TEXT,

    ordered_at TIMESTAMP,
    unit_cost REAL,
    quantity INTEGER,
    total_cost REAL,

    FOREIGN KEY (asin) REFERENCES products(asin)
);

-- エンゲージメントメトリクス
CREATE TABLE engagement_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asin TEXT,
    platform TEXT,
    account_id TEXT,
    date DATE,

    page_views INTEGER DEFAULT 0,
    likes INTEGER DEFAULT 0,
    favorites INTEGER DEFAULT 0,
    cart_adds INTEGER DEFAULT 0,

    UNIQUE(asin, platform, account_id, date),
    FOREIGN KEY (asin) REFERENCES products(asin)
);

-- LLM分析結果キャッシュ
CREATE TABLE llm_analysis_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_type TEXT,  -- 'sales_insights', 'category_trends', 'sourcing_advice'
    input_hash TEXT UNIQUE,  -- MD5(prompt + data)
    prompt TEXT,
    response TEXT,
    model TEXT,  -- 'gpt-5', 'claude-3.5-sonnet', 'gemini-2.0'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP
);
```

---

## 📅 実装フェーズ

### Phase 0: 認証システム統一・動作検証（完了）✅

**完了日**: 2025-11-25

**実施内容:**
1. ✅ シングルセッション方式の実装（TypeScript版と同様）
2. ✅ メールアドレス/PASSWORD認証の実装
3. ✅ extract_asins.py動作検証（10件のASIN抽出成功）
4. ✅ Chromeセッション管理問題の解決

**成果:**
- 認証システムが安定動作
- 基盤システムが完成

**参考:**
- [sourcing/docs/20251125_implementation_progress_report_v3.md](../sourcing/docs/20251125_implementation_progress_report_v3.md)

---

### Phase 1: 優先度1実装（一部完了）✅⏳

**完了日**: 2025-11-26（一部完了）

| Day | タスク | ステータス | 成果物 |
|-----|--------|----------|--------|
| 1 | ディレクトリ・DB構築、SellerSprite認証流用 | ✅ 完了 | `sourcing/data/sourcing.db`, `auth_manager.py` |
| 2 | Playwright基盤実装 | ✅ 完了 | `browser_controller.py` |
| 3-4 | 定型スクリプト実装（product_research） | ✅ 完了 | `product_research_extractor.py` |
| 5 | 大量抽出機能実装 | ✅ 完了 | `extract_asins_bulk.py`（2034件抽出成功） |
| 6 | 出品連携スクリプト実装 | ✅ 完了 | `import_candidates_to_master.py` |
| 7 | master.dbへの連携実行 | ✅ 完了 | 2034件をupload_queueに追加完了 |

**達成した成果:**
- ✅ 2034件のASIN候補を抽出（2025-11-25）
- ✅ sourcing_candidatesからmaster.dbへの自動連携パイプライン構築
- ✅ SP-APIレート制限の最適化（処理速度2.5倍向上）
- ✅ NGキーワード自動クリーニング機能

**未完了タスク:**
- ⏳ セグメント分割による3000件/日の継続抽出
- ⏳ MCP録画ツール実装（ranking, category抽出パターン）

**参考:**
- [sourcing/docs/20251126_listing_integration_execution_report.md](../sourcing/docs/20251126_listing_integration_execution_report.md)
- [sourcing/docs/20251126_listing_integration_plan.md](../sourcing/docs/20251126_listing_integration_plan.md)

---

### Phase 2: 優先度2実装（3-5日）

| Day | タスク | 成果物 |
|-----|--------|--------|
| 1 | LLMクライアント実装（GPT-5） | `shared/llm/openai_client.py` |
| 2 | パラメータ生成ロジック | `parameter_generator.py` |
| 3 | プロンプトテンプレート作成 | `prompts/*.txt` |
| 4 | LLM連携抽出クラス | `smart_extractor.py` |
| 5 | 統合スクリプト・テスト | `extract_asins_smart.py` |

**成果:** プロンプトでASIN抽出方針を指示できる

---

### Phase 3: 優先度3実装（1-2週間）

| Day | タスク | 成果物 |
|-----|--------|--------|
| 1-3 | データ収集モジュール実装 | `analytics/collectors/*.py` |
| 4-5 | データ統合・トレンド分析 | `data_aggregator.py`, `trend_analyzer.py` |
| 6-7 | LLM戦略生成エンジン | `strategy_generator.py` |
| 8-10 | 自律実行エンジン・テスト | `autonomous_extraction.py` |

**成果:** 完全自動でデータドリブンなASIN抽出

---

## 🔧 技術スタック

### コア技術
- **Python 3.10+**
- **Playwright**: ブラウザ自動操作
- **SQLite**: ローカルDB
- **AsyncIO**: 非同期処理

### LLM API
- **OpenAI GPT-5**: メインLLM（レガシーコード流用）
- **Claude 3.5**: 補助LLM
- **Gemini 2.0**: 補助LLM

### 参考レガシーコード
- **GPT-5呼び出し**: `C:\Users\hiroo\Documents\ama-cari\ebay_pj\scripts\create_en_ebay_listing_openai_csv.py`
- **Playwright認証**: `C:\Users\hiroo\Documents\ama-cari\sellersprite-playwright\sellersprite_auth.py`

---

## 🚀 セットアップ手順

### 1. 環境準備

```bash
cd C:\Users\hiroo\Documents\GitHub\ecauto

# 依存パッケージ追加
echo "playwright==1.41.0" >> requirements.txt
echo "openai>=1.0.0" >> requirements.txt
echo "python-dotenv>=1.0.0" >> requirements.txt

# インストール
.\venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

### 2. APIキー設定

`.env`ファイルに追加：
```env
# OpenAI API
OPENAI_API_KEY=sk-proj-xxxxx...

# (優先度2以降で使用)
CLAUDE_API_KEY=sk-ant-xxxxx...
GEMINI_API_KEY=xxxxx...
```

### 3. ディレクトリ作成

```bash
# sourcing/ディレクトリ構造作成
mkdir -p sourcing/core
mkdir -p sourcing/sources/sellersprite/extractors
mkdir -p sourcing/sources/sellersprite/prompts
mkdir -p sourcing/data/extraction_logs
mkdir -p sourcing/scripts

# analytics/（Phase 3で使用）
mkdir -p analytics/collectors
mkdir -p analytics/core
mkdir -p analytics/data
mkdir -p analytics/scripts

# shared/llm/
mkdir -p shared/llm
```

---

## 📝 実装時の注意事項

### レガシープロジェクトとの関係
- **完全独立**: `C:\Users\hiroo\Documents\ama-cari\` と `C:/Users/hiroo/Documents/GitHub/ecauto` は相互に依存関係を持たない
- **コード流用OK**: レガシーコードの完全複製・流用は推奨
- **パス調整必須**: Cookieファイルパス等は新プロジェクトのディレクトリ構造に合わせる

### データ仕入元
- **現在**: Amazon Business（ほぼすべての販売商品）
- **将来**: 複数仕入元対応（1688等）を前提に設計

### 販売プラットフォーム
- BASE
- メルカリ
- eBay
- Yahoo!オークション

### データ形式
- CSV（手動エクスポート）
- JSON（API取得可能な場合）

---

## ✅ 成功基準

### Phase 0（完了）
- ✅ 認証システムが安定動作
- ✅ 基盤システムの実装完了
- ✅ Chromeセッション管理問題の解決

### Phase 1（一部完了）
- ✅ 2034件のASIN抽出成功
- ✅ sourcing → master.db連携パイプライン構築
- ✅ エラーログが適切に記録される
- ⏳ 手動パラメータで2000-3000件/日のASIN抽出が安定動作（継続実行中）
- ⏳ MCP録画で新規パターンを30分以内に追加可能（未実装）

### Phase 2
- [ ] プロンプトからLLMがパラメータを正確に生成
- [ ] 人間の指示なしでカテゴリ・条件を決定できる
- [ ] 抽出精度が手動と同等以上

### Phase 3
- [ ] 完全自動で毎日3000件のASINを抽出
- [ ] 販売データに基づいた戦略的な商品発掘
- [ ] 利益率・在庫回転率が向上

---

## 🔗 関連ドキュメント

- [プロジェクトREADME](../README.md)
- [実装計画](implementation_plan.md)
- [残存課題リスト](REMAINING_ISSUES.md)

---

## 📞 サポート

実装中に質問や問題が発生した場合は、このドキュメントを参照してください。

**最終更新**: 2025-11-26
**ステータス**: Phase 0完了、Phase 1一部完了（2034件抽出・出品連携成功）
