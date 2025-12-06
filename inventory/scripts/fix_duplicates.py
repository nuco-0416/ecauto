"""
重複データ修正スクリプト

(asin, platform)の重複を解消
古いレコードを削除し、最新のレコードのみを保持
"""

import sys
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from inventory.core.master_db import MasterDB
import sqlite3


def fix_duplicates():
    """重複を修正"""

    # DBに直接接続（_init_tablesを呼ばない）
    db = MasterDB.__new__(MasterDB)
    db.db_path = Path(__file__).resolve().parent.parent / 'data' / 'master.db'

    print("=" * 60)
    print("重複データ修正")
    print("=" * 60)

    conn = sqlite3.connect(db.db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 重複を確認
    cursor.execute('''
        SELECT asin, platform, COUNT(*) as count
        FROM listings
        GROUP BY asin, platform
        HAVING count > 1
    ''')

    duplicates = cursor.fetchall()

    if not duplicates:
        print("\n重複データはありません")
        conn.close()
        return

    print(f"\n重複件数: {len(duplicates)}件")
    print("\n重複例（最大10件）:")
    for i, row in enumerate(duplicates[:10], 1):
        print(f"{i}. ASIN: {row['asin']}, Platform: {row['platform']}, 重複数: {row['count']}")

    # 確認
    response = input(f"\n{len(duplicates)}件の重複を修正しますか？古いレコードを削除し、最新のみ保持します。(y/N): ")
    if response.lower() != 'y':
        print("キャンセルしました")
        conn.close()
        return

    print("\n重複を修正中...")

    deleted_count = 0

    for dup in duplicates:
        asin = dup['asin']
        platform = dup['platform']

        # 同じ(asin, platform)のレコードを取得（IDの降順 = 最新優先）
        cursor.execute('''
            SELECT id FROM listings
            WHERE asin = ? AND platform = ?
            ORDER BY id DESC
        ''', (asin, platform))

        ids = [row['id'] for row in cursor.fetchall()]

        # 最初（最新）以外を削除
        ids_to_delete = ids[1:]

        for id_to_delete in ids_to_delete:
            cursor.execute('DELETE FROM listings WHERE id = ?', (id_to_delete,))
            deleted_count += 1

        if len(duplicates) <= 20:  # 20件以下なら詳細表示
            print(f"  [OK] {asin} ({platform}): {len(ids_to_delete)}件削除")

    conn.commit()

    print(f"\n削除完了: {deleted_count}件")

    # 再度重複チェック
    cursor.execute('''
        SELECT COUNT(*) as count
        FROM (
            SELECT asin, platform, COUNT(*) as c
            FROM listings
            GROUP BY asin, platform
            HAVING c > 1
        )
    ''')

    remaining = cursor.fetchone()['count']

    if remaining == 0:
        print("[OK] 重複は完全に解消されました")
    else:
        print(f"[WARNING] まだ{remaining}件の重複が残っています")

    conn.close()

    print("\n次のステップ:")
    print("1. マスタDBを再初期化してUNIQUE制約を適用:")
    print("   python inventory/scripts/init_master_db.py")
    print("\n2. または、Pythonから再初期化:")
    print("   from inventory.core.master_db import MasterDB")
    print("   db = MasterDB()  # UNIQUE制約が自動適用されます")


if __name__ == '__main__':
    fix_duplicates()
