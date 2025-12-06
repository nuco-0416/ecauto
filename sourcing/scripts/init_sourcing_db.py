"""
Sourcing Database 初期化スクリプト

sourcing.db のテーブルを作成する
"""

import sqlite3
from pathlib import Path
from datetime import datetime


def init_db():
    """sourcing.db を初期化"""

    # データベースファイルパス
    db_path = Path(__file__).parent.parent / 'data' / 'sourcing.db'
    db_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"データベースを初期化します: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 仕入候補商品テーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sourcing_candidates (
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
            )
        ''')
        print("[OK] sourcing_candidates テーブル作成")

        # SellerSprite抽出ログテーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS extraction_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                extraction_type TEXT,  -- 'ranking', 'category', 'seasonal'
                parameters TEXT,  -- JSON: {"category": "おもちゃ", "min_rank": 1, "max_rank": 1000}
                asins_found INTEGER,
                status TEXT DEFAULT 'running',  -- 'running', 'completed', 'failed'
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                error_message TEXT
            )
        ''')
        print("[OK] extraction_logs テーブル作成")

        # 抽出パターン定義テーブル（MCP録画結果）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS extraction_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_name TEXT UNIQUE,
                pattern_type TEXT,  -- 'ranking', 'category', 'seasonal'
                playwright_script TEXT,  -- Pythonコード（async def extract()）
                parameters_schema TEXT,  -- JSON Schema for validation
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used_at TIMESTAMP
            )
        ''')
        print("[OK] extraction_patterns テーブル作成")

        # インデックス作成
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_candidates_asin ON sourcing_candidates(asin)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_candidates_status ON sourcing_candidates(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_logs_type ON extraction_logs(extraction_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_logs_status ON extraction_logs(status)')
        print("[OK] インデックス作成")

        conn.commit()
        print(f"\n[SUCCESS] データベース初期化完了: {db_path}")

        # テーブル一覧を表示
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        print("\n作成されたテーブル:")
        for table in tables:
            print(f"  - {table[0]}")

    except Exception as e:
        print(f"\n[ERROR] エラー: {e}")
        conn.rollback()
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
