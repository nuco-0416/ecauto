"""
Issue #014: upload_queueにUNIQUE制約を追加するスクリプト

(asin, platform, account_id)の組み合わせでUNIQUE制約を追加します。

実行方法:
    python scheduler/scripts/add_queue_unique_constraint.py [--dry-run]
"""

import sys
import os
from pathlib import Path
import io

# UTF-8出力を強制（Windows環境でのcp932エラー回避）
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from inventory.core.master_db import MasterDB


def add_queue_unique_constraint(dry_run=False):
    """
    upload_queueテーブルにUNIQUE制約を追加

    Args:
        dry_run: Trueの場合、変更を実行せずにログのみ出力
    """
    print("=" * 70)
    print("Issue #014: upload_queueにUNIQUE制約を追加")
    print("=" * 70)
    print()

    if dry_run:
        print("[DRY-RUN MODE] 変更は実行されません")
        print()

    db = MasterDB()

    with db.get_connection() as conn:
        # 現在のインデックス情報を取得
        print("[1/3] 現在のインデックス情報を確認中...")
        cursor = conn.execute("""
            SELECT name, sql
            FROM sqlite_master
            WHERE type='index'
              AND tbl_name='upload_queue'
              AND name LIKE 'idx_queue%'
        """)
        indexes = cursor.fetchall()

        print(f"  現在のインデックス数: {len(indexes)}件")
        for name, sql in indexes:
            print(f"    - {name}")
            if sql:
                print(f"      {sql}")
        print()

        # 新しいUNIQUE制約に該当する重複レコード数を確認
        print("[2/3] UNIQUE制約の影響範囲を確認中...")

        cursor = conn.execute("""
            SELECT asin, platform, account_id, COUNT(*) as count
            FROM upload_queue
            GROUP BY asin, platform, account_id
            HAVING COUNT(*) > 1
        """)
        duplicates = cursor.fetchall()

        print(f"  新制約(asin, platform, account_id)で重複: {len(duplicates)}件")
        if len(duplicates) > 0:
            print("  ⚠️  警告: UNIQUE制約に対する重複があります！")
            print("  最初の5件:")
            for asin, platform, account_id, count in duplicates[:5]:
                print(f"    - {asin} ({platform}, {account_id}): {count}件")
            print()
            print("  UNIQUE制約を追加する前に、重複を解消する必要があります。")
            print("  cleanup_duplicate_queue.pyを実行してください。")
            return False
        else:
            print("  ✓ 新しいUNIQUE制約に対する重複はありません")
        print()

        if dry_run:
            print("[DRY-RUN] 以下の変更が実行されます:")
            print("  1. CREATE UNIQUE INDEX idx_queue_asin_platform_account_unique")
            print("     ON upload_queue(asin, platform, account_id)")
            print()
            print("[DRY-RUN] 実際の変更は行いませんでした")
            return True

        # 新しいUNIQUE INDEXを作成
        print("[3/3] 新しいUNIQUE INDEXを作成中...")
        try:
            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_queue_asin_platform_account_unique
                ON upload_queue(asin, platform, account_id)
            """)
            print("  ✓ idx_queue_asin_platform_account_unique を作成しました")
            print("    制約: (asin, platform, account_id)の組み合わせでUNIQUE")
        except Exception as e:
            print(f"  ❌ エラー: {e}")
            return False
        print()

        # 変更を確定
        conn.commit()

        # 変更後のインデックス情報を確認
        print("変更後のインデックス情報:")
        cursor = conn.execute("""
            SELECT name, sql
            FROM sqlite_master
            WHERE type='index'
              AND tbl_name='upload_queue'
              AND name LIKE 'idx_queue%'
        """)
        indexes = cursor.fetchall()

        print(f"  インデックス数: {len(indexes)}件")
        for name, sql in indexes:
            print(f"    - {name}")
            if sql:
                print(f"      {sql}")
        print()

        print("=" * 70)
        print("✓ UNIQUE制約の追加が完了しました")
        print("=" * 70)

        return True


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="upload_queueにUNIQUE制約を追加"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="変更を実行せずにログのみ出力"
    )

    args = parser.parse_args()

    success = add_queue_unique_constraint(dry_run=args.dry_run)

    if success:
        sys.exit(0)
    else:
        sys.exit(1)
