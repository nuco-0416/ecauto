"""
Issue #013: listingsのデータ整合性を検証するスクリプト

以下の項目をチェックします:
1. upload_queueとlistingsの整合性（欠損チェック）
2. UNIQUE制約の有効性（重複チェック）
3. listingsとproductsの整合性（孤立レコードチェック）

実行方法:
    python inventory/scripts/verify_listings_integrity.py
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


def verify_listings_integrity():
    """
    listingsのデータ整合性を検証

    Returns:
        bool: 全てのチェックが成功した場合True
    """
    print("=" * 70)
    print("Issue #013: listingsデータ整合性検証")
    print("=" * 70)
    print()

    db = MasterDB()
    all_checks_passed = True

    with db.get_connection() as conn:
        # チェック1: UNIQUE制約の確認
        print("[チェック1/5] UNIQUE制約の確認")
        print("-" * 70)

        cursor = conn.execute("""
            SELECT name, sql
            FROM sqlite_master
            WHERE type='index'
              AND tbl_name='listings'
              AND name LIKE 'idx_listings%unique%'
        """)
        unique_indexes = cursor.fetchall()

        print(f"  UNIQUEインデックス数: {len(unique_indexes)}件")

        expected_index = 'idx_listings_asin_platform_account_unique'
        has_expected_index = False

        for name, sql in unique_indexes:
            print(f"    - {name}")
            if sql:
                print(f"      {sql}")
            if name == expected_index:
                has_expected_index = True

        if has_expected_index:
            print(f"  ✓ 期待されるUNIQUE制約が存在します: {expected_index}")
        else:
            print(f"  ❌ 期待されるUNIQUE制約が見つかりません: {expected_index}")
            all_checks_passed = False

        # 旧制約の確認
        old_index = 'idx_listings_asin_platform_unique'
        cursor = conn.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type='index'
              AND tbl_name='listings'
              AND name = ?
        """, (old_index,))
        old_index_exists = cursor.fetchone()

        if old_index_exists:
            print(f"  ⚠️  警告: 古いUNIQUE制約がまだ存在します: {old_index}")
            all_checks_passed = False
        else:
            print(f"  ✓ 古いUNIQUE制約は削除されています: {old_index}")

        print()

        # チェック2: listingsの重複チェック
        print("[チェック2/5] listingsの重複チェック")
        print("-" * 70)

        cursor = conn.execute("""
            SELECT asin, platform, account_id, COUNT(*) as count
            FROM listings
            GROUP BY asin, platform, account_id
            HAVING COUNT(*) > 1
        """)
        duplicates = cursor.fetchall()

        print(f"  重複レコード数: {len(duplicates)}件")

        if len(duplicates) == 0:
            print("  ✓ 重複レコードはありません")
        else:
            print("  ❌ 重複レコードが見つかりました:")
            for asin, platform, account_id, count in duplicates[:10]:
                print(f"    - {asin} ({platform}, {account_id}): {count}件")
            if len(duplicates) > 10:
                print(f"    ... 他 {len(duplicates) - 10}件")
            all_checks_passed = False

        print()

        # チェック3: upload_queueとlistingsの整合性チェック
        print("[チェック3/5] upload_queueとlistingsの整合性チェック")
        print("-" * 70)

        # account_1で欠損しているASIN
        cursor = conn.execute("""
            SELECT COUNT(DISTINCT q.asin)
            FROM upload_queue q
            LEFT JOIN listings l ON q.asin = l.asin
                AND q.account_id = l.account_id
                AND q.platform = l.platform
            WHERE q.platform = 'base'
              AND q.account_id = 'base_account_1'
              AND l.asin IS NULL
        """)
        missing_account_1 = cursor.fetchone()[0]

        # account_2で欠損しているASIN
        cursor = conn.execute("""
            SELECT COUNT(DISTINCT q.asin)
            FROM upload_queue q
            LEFT JOIN listings l ON q.asin = l.asin
                AND q.account_id = l.account_id
                AND q.platform = l.platform
            WHERE q.platform = 'base'
              AND q.account_id = 'base_account_2'
              AND l.asin IS NULL
        """)
        missing_account_2 = cursor.fetchone()[0]

        total_missing = missing_account_1 + missing_account_2

        print(f"  欠損しているlistings:")
        print(f"    - account_1: {missing_account_1}件")
        print(f"    - account_2: {missing_account_2}件")
        print(f"    - 合計: {total_missing}件")

        if total_missing == 0:
            print("  ✓ upload_queueとlistingsは整合しています")
        else:
            print("  ❌ listingsが欠損しています")
            all_checks_passed = False

            # サンプル表示
            if total_missing > 0:
                print("\n  サンプル（最初の5件）:")
                cursor = conn.execute("""
                    SELECT DISTINCT q.asin, q.account_id
                    FROM upload_queue q
                    LEFT JOIN listings l ON q.asin = l.asin
                        AND q.account_id = l.account_id
                        AND q.platform = l.platform
                    WHERE q.platform = 'base'
                      AND l.asin IS NULL
                    LIMIT 5
                """)
                for asin, account_id in cursor.fetchall():
                    print(f"    - {asin} ({account_id})")

        print()

        # チェック4: listingsとproductsの整合性チェック
        print("[チェック4/5] listingsとproductsの整合性チェック")
        print("-" * 70)

        cursor = conn.execute("""
            SELECT COUNT(*)
            FROM listings l
            LEFT JOIN products p ON l.asin = p.asin
            WHERE p.asin IS NULL
        """)
        orphaned_listings = cursor.fetchone()[0]

        print(f"  孤立したlistings（productsに対応するレコードがない）: {orphaned_listings}件")

        if orphaned_listings == 0:
            print("  ✓ すべてのlistingsに対応するproductsが存在します")
        else:
            print("  ⚠️  警告: 一部のlistingsに対応するproductsがありません")
            # これは警告のみで、エラーとはしない（productsが削除された可能性があるため）

            # サンプル表示
            print("\n  サンプル（最初の5件）:")
            cursor = conn.execute("""
                SELECT l.asin, l.account_id
                FROM listings l
                LEFT JOIN products p ON l.asin = p.asin
                WHERE p.asin IS NULL
                LIMIT 5
            """)
            for asin, account_id in cursor.fetchall():
                print(f"    - {asin} ({account_id})")

        print()

        # チェック5: listingsの統計情報
        print("[チェック5/5] listingsの統計情報")
        print("-" * 70)

        # 全体のレコード数
        cursor = conn.execute("SELECT COUNT(*) FROM listings")
        total_listings = cursor.fetchone()[0]

        # account_id別のレコード数
        cursor = conn.execute("""
            SELECT account_id, status, COUNT(*) as count
            FROM listings
            GROUP BY account_id, status
            ORDER BY account_id, status
        """)
        account_stats = cursor.fetchall()

        print(f"  総レコード数: {total_listings}件")
        print()
        print("  アカウント別統計:")

        current_account = None
        account_total = 0

        for account_id, status, count in account_stats:
            if current_account != account_id:
                if current_account is not None:
                    print(f"      小計: {account_total}件")
                current_account = account_id
                account_total = 0
                print(f"    {account_id}:")

            print(f"      - {status}: {count}件")
            account_total += count

        if current_account is not None:
            print(f"      小計: {account_total}件")

        print()

        # まとめ
        print("=" * 70)
        print("検証結果まとめ")
        print("=" * 70)

        if all_checks_passed:
            print("✓ すべてのチェックが成功しました")
            print()
            print("Issue #013の修正は正常に完了しています。")
        else:
            print("❌ 一部のチェックが失敗しました")
            print()
            print("以下の項目を確認してください:")
            if not has_expected_index:
                print("  - UNIQUE制約が正しく設定されていません")
            if old_index_exists:
                print("  - 古いUNIQUE制約が削除されていません")
            if len(duplicates) > 0:
                print("  - listingsに重複レコードが存在します")
            if total_missing > 0:
                print("  - upload_queueとlistingsの整合性が取れていません")

        print("=" * 70)

        return all_checks_passed


if __name__ == "__main__":
    success = verify_listings_integrity()

    if success:
        sys.exit(0)
    else:
        sys.exit(1)
