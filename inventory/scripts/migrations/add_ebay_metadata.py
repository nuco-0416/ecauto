#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eBayメタデータテーブル追加マイグレーション

master.dbに ebay_listing_metadata テーブルを追加します。

使用方法:
    python inventory/scripts/migrations/add_ebay_metadata.py
"""

import sqlite3
import sys
from pathlib import Path

# 標準出力のエンコーディングをUTF-8に設定（Windows対応）
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(project_root))


def migrate():
    """マイグレーション実行"""
    db_path = project_root / 'inventory' / 'data' / 'master.db'

    if not db_path.exists():
        print(f"❌ エラー: データベースが見つかりません: {db_path}")
        print("   まず inventory/scripts/init_master_db.py を実行してください")
        return False

    print(f"データベース: {db_path}")
    print("マイグレーション開始...")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # ebay_listing_metadataテーブルが既に存在するか確認
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='ebay_listing_metadata'
        """)

        if cursor.fetchone():
            print("⚠️  ebay_listing_metadata テーブルは既に存在します")
            print("   マイグレーションをスキップします")
            return True

        # テーブル作成
        cursor.execute("""
            CREATE TABLE ebay_listing_metadata (
                listing_id INTEGER PRIMARY KEY,
                offer_id TEXT,
                category_id TEXT,
                policy_payment_id TEXT,
                policy_return_id TEXT,
                policy_fulfillment_id TEXT,
                item_specifics TEXT,
                merchant_location_key TEXT DEFAULT 'JP_LOCATION',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (listing_id) REFERENCES listings(id)
            )
        """)

        # インデックス作成
        cursor.execute("""
            CREATE INDEX idx_ebay_metadata_offer_id
            ON ebay_listing_metadata(offer_id)
        """)

        cursor.execute("""
            CREATE INDEX idx_ebay_metadata_category_id
            ON ebay_listing_metadata(category_id)
        """)

        conn.commit()
        print("✅ ebay_listing_metadata テーブルを作成しました")
        print("✅ インデックスを作成しました")

        # 作成されたテーブルを確認
        cursor.execute("PRAGMA table_info(ebay_listing_metadata)")
        columns = cursor.fetchall()

        print("\n作成されたカラム:")
        for col in columns:
            print(f"  - {col[1]} ({col[2]})")

        return True

    except sqlite3.Error as e:
        print(f"❌ エラー: {e}")
        conn.rollback()
        return False

    finally:
        conn.close()


def verify():
    """マイグレーション結果を確認"""
    db_path = project_root / 'inventory' / 'data' / 'master.db'

    if not db_path.exists():
        return False

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # テーブル存在確認
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='ebay_listing_metadata'
        """)

        if not cursor.fetchone():
            print("❌ 検証失敗: ebay_listing_metadata テーブルが見つかりません")
            return False

        # カラム数確認
        cursor.execute("PRAGMA table_info(ebay_listing_metadata)")
        columns = cursor.fetchall()

        expected_columns = [
            'listing_id', 'offer_id', 'category_id',
            'policy_payment_id', 'policy_return_id', 'policy_fulfillment_id',
            'item_specifics', 'merchant_location_key',
            'created_at', 'updated_at'
        ]

        actual_columns = [col[1] for col in columns]

        if set(expected_columns) != set(actual_columns):
            print("❌ 検証失敗: カラム構成が異なります")
            print(f"   期待: {expected_columns}")
            print(f"   実際: {actual_columns}")
            return False

        print("\n✅ 検証成功: テーブルが正しく作成されています")
        return True

    except sqlite3.Error as e:
        print(f"❌ 検証エラー: {e}")
        return False

    finally:
        conn.close()


def main():
    """メイン処理"""
    print("=" * 60)
    print("eBayメタデータテーブル追加マイグレーション")
    print("=" * 60)
    print()

    # マイグレーション実行
    if not migrate():
        sys.exit(1)

    print()

    # 検証
    if not verify():
        sys.exit(1)

    print()
    print("=" * 60)
    print("✅ マイグレーション完了")
    print("=" * 60)


if __name__ == '__main__':
    main()
