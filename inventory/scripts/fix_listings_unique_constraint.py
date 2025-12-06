"""
Issue #013: listingsのUNIQUE制約を修正するスクリプト

UNIQUE制約を(asin, platform)から(asin, platform, account_id)に変更します。

実行方法:
    python inventory/scripts/fix_listings_unique_constraint.py [--dry-run]
"""

import sys
import os
import sqlite3
from pathlib import Path
import io

# UTF-8出力を強制（Windows環境でのcp932エラー回避）
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from inventory.core.master_db import MasterDB


def fix_unique_constraint(dry_run=False):
    """
    listingsテーブルのUNIQUE制約を修正

    Args:
        dry_run: Trueの場合、変更を実行せずにログのみ出力
    """
    print("=" * 70)
    print("Issue #013: listingsのUNIQUE制約修正スクリプト")
    print("=" * 70)
    print()

    if dry_run:
        print("[DRY-RUN MODE] 変更は実行されません")
        print()

    db = MasterDB()

    with db.get_connection() as conn:
        # 現在のインデックス情報を取得
        print("[1/4] 現在のインデックス情報を確認中...")
        cursor = conn.execute("""
            SELECT name, sql
            FROM sqlite_master
            WHERE type='index'
              AND tbl_name='listings'
              AND name LIKE 'idx_listings%'
        """)
        indexes = cursor.fetchall()

        print(f"  現在のインデックス数: {len(indexes)}件")
        for name, sql in indexes:
            print(f"    - {name}")
            if sql:
                print(f"      {sql}")
        print()

        # 既存のUNIQUE制約に該当するレコード数を確認
        print("[2/4] UNIQUE制約の影響範囲を確認中...")

        # 既存の制約(asin, platform)で重複しているレコード数
        cursor = conn.execute("""
            SELECT asin, platform, COUNT(*) as count,
                   GROUP_CONCAT(account_id) as accounts
            FROM listings
            GROUP BY asin, platform
            HAVING COUNT(*) > 1
        """)
        duplicate_old_constraint = cursor.fetchall()

        print(f"  既存制約(asin, platform)で重複: {len(duplicate_old_constraint)}件")
        if len(duplicate_old_constraint) > 0 and len(duplicate_old_constraint) <= 10:
            for asin, platform, count, accounts in duplicate_old_constraint:
                print(f"    - {asin} ({platform}): {count}件 - accounts: {accounts}")
        elif len(duplicate_old_constraint) > 10:
            print(f"    ※ 重複が多いため、最初の10件のみ表示:")
            for asin, platform, count, accounts in duplicate_old_constraint[:10]:
                print(f"    - {asin} ({platform}): {count}件 - accounts: {accounts}")
        print()

        # 新しい制約(asin, platform, account_id)で重複しているレコード数
        cursor = conn.execute("""
            SELECT asin, platform, account_id, COUNT(*) as count
            FROM listings
            GROUP BY asin, platform, account_id
            HAVING COUNT(*) > 1
        """)
        duplicate_new_constraint = cursor.fetchall()

        print(f"  新制約(asin, platform, account_id)で重複: {len(duplicate_new_constraint)}件")
        if len(duplicate_new_constraint) > 0:
            print("  ⚠️  警告: 新しいUNIQUE制約でも重複があります！")
            for asin, platform, account_id, count in duplicate_new_constraint[:10]:
                print(f"    - {asin} ({platform}, {account_id}): {count}件")
            print()
            print("  新しいUNIQUE制約を追加する前に、重複を解消する必要があります。")
            return False
        else:
            print("  ✓ 新しいUNIQUE制約に対する重複はありません")
        print()

        if dry_run:
            print("[DRY-RUN] 以下の変更が実行されます:")
            print("  1. DROP INDEX idx_listings_asin_platform_unique")
            print("  2. CREATE UNIQUE INDEX idx_listings_asin_platform_account_unique")
            print("     ON listings(asin, platform, account_id)")
            print()
            print("[DRY-RUN] 実際の変更は行いませんでした")
            return True

        # 既存のUNIQUE INDEXを削除
        print("[3/4] 既存のUNIQUE INDEXを削除中...")
        try:
            conn.execute("DROP INDEX IF EXISTS idx_listings_asin_platform_unique")
            print("  ✓ idx_listings_asin_platform_unique を削除しました")
        except Exception as e:
            print(f"  ❌ エラー: {e}")
            return False
        print()

        # 新しいUNIQUE INDEXを作成
        print("[4/4] 新しいUNIQUE INDEXを作成中...")
        try:
            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_listings_asin_platform_account_unique
                ON listings(asin, platform, account_id)
            """)
            print("  ✓ idx_listings_asin_platform_account_unique を作成しました")
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
              AND tbl_name='listings'
              AND name LIKE 'idx_listings%'
        """)
        indexes = cursor.fetchall()

        print(f"  インデックス数: {len(indexes)}件")
        for name, sql in indexes:
            print(f"    - {name}")
            if sql:
                print(f"      {sql}")
        print()

        print("=" * 70)
        print("✓ UNIQUE制約の修正が完了しました")
        print("=" * 70)

        return True


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="listingsテーブルのUNIQUE制約を修正"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="変更を実行せずにログのみ出力"
    )

    args = parser.parse_args()

    success = fix_unique_constraint(dry_run=args.dry_run)

    if success:
        sys.exit(0)
    else:
        sys.exit(1)
