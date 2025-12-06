"""
Initialize Master Database

マスタデータベースを初期化するスクリプト
"""

import sys
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from inventory.core.master_db import MasterDB


def main():
    """マスタDBを初期化"""
    print("=" * 60)
    print("マスタデータベース初期化")
    print("=" * 60)

    # デフォルトパスで初期化
    db = MasterDB()

    print(f"\nデータベースパス: {db.db_path}")
    print("\n以下のテーブルが作成されました:")
    print("  - products (商品マスタ)")
    print("  - listings (出品情報)")
    print("  - upload_queue (出品キュー)")
    print("  - account_configs (アカウント設定)")
    print()

    # データベース接続テスト
    with db.get_connection() as conn:
        cursor = conn.cursor()

        # テーブル一覧を取得
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table'
            ORDER BY name
        """)
        tables = cursor.fetchall()

        print("作成されたテーブル:")
        for table in tables:
            print(f"  [OK] {table[0]}")

    print()
    print("=" * 60)
    print("初期化が完了しました")
    print("=" * 60)


if __name__ == '__main__':
    main()
