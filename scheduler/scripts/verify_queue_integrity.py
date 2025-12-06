"""
Issue #014: upload_queueのデータ整合性を検証するスクリプト

以下の項目をチェックします:
1. UNIQUE制約の有効性（重複チェック）
2. upload_queueとlistingsの整合性
3. upload_queueとproductsの整合性

実行方法:
    python scheduler/scripts/verify_queue_integrity.py
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


def verify_queue_integrity():
    """
    upload_queueのデータ整合性を検証

    Returns:
        bool: 全てのチェックが成功した場合True
    """
    print("=" * 70)
    print("Issue #014: upload_queueデータ整合性検証")
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
              AND tbl_name='upload_queue'
              AND name LIKE '%unique%'
        """)
        unique_indexes = cursor.fetchall()

        print(f"  UNIQUEインデックス数: {len(unique_indexes)}件")

        expected_index = 'idx_queue_asin_platform_account_unique'
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

        print()

        # チェック2: upload_queueの重複チェック
        print("[チェック2/5] upload_queueの重複チェック")
        print("-" * 70)

        cursor = conn.execute("""
            SELECT asin, platform, account_id, COUNT(*) as count
            FROM upload_queue
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

        # チェック3: statusごとの統計
        print("[チェック3/5] upload_queueのstatus統計")
        print("-" * 70)

        cursor = conn.execute("""
            SELECT status, COUNT(*) as count
            FROM upload_queue
            GROUP BY status
            ORDER BY count DESC
        """)
        status_stats = cursor.fetchall()

        total_records = sum(count for _, count in status_stats)
        print(f"  総レコード数: {total_records}件")
        print()
        print("  status別統計:")
        for status, count in status_stats:
            percentage = (count / total_records * 100) if total_records > 0 else 0
            print(f"    - {status}: {count}件 ({percentage:.1f}%)")

        print()

        # チェック4: upload_queueとlistingsの整合性
        print("[チェック4/5] upload_queueとlistingsの整合性チェック")
        print("-" * 70)

        # pendingまたはuploadingのレコードについて、listingsが存在するか確認
        cursor = conn.execute("""
            SELECT COUNT(*)
            FROM upload_queue q
            LEFT JOIN listings l ON q.asin = l.asin
                AND q.account_id = l.account_id
                AND q.platform = l.platform
            WHERE q.status IN ('pending', 'uploading')
              AND l.asin IS NULL
        """)
        missing_listings = cursor.fetchone()[0]

        print(f"  pending/uploadingでlistingsが欠損: {missing_listings}件")

        if missing_listings == 0:
            print("  ✓ すべてのpending/uploadingレコードにlistingsが存在します")
        else:
            print("  ⚠️  警告: 一部のレコードでlistingsが欠損しています")
            # サンプル表示
            print("\n  サンプル（最初の5件）:")
            cursor = conn.execute("""
                SELECT q.asin, q.account_id, q.status
                FROM upload_queue q
                LEFT JOIN listings l ON q.asin = l.asin
                    AND q.account_id = l.account_id
                    AND q.platform = l.platform
                WHERE q.status IN ('pending', 'uploading')
                  AND l.asin IS NULL
                LIMIT 5
            """)
            for asin, account_id, status in cursor.fetchall():
                print(f"    - {asin} ({account_id}, status={status})")

        print()

        # チェック5: upload_queueとproductsの整合性
        print("[チェック5/5] upload_queueとproductsの整合性チェック")
        print("-" * 70)

        cursor = conn.execute("""
            SELECT COUNT(*)
            FROM upload_queue q
            LEFT JOIN products p ON q.asin = p.asin
            WHERE p.asin IS NULL
        """)
        orphaned_queue = cursor.fetchone()[0]

        print(f"  孤立したqueue（productsに対応するレコードがない）: {orphaned_queue}件")

        if orphaned_queue == 0:
            print("  ✓ すべてのqueueに対応するproductsが存在します")
        else:
            print("  ⚠️  警告: 一部のqueueに対応するproductsがありません")

            # サンプル表示
            print("\n  サンプル（最初の5件）:")
            cursor = conn.execute("""
                SELECT q.asin, q.account_id, q.status
                FROM upload_queue q
                LEFT JOIN products p ON q.asin = p.asin
                WHERE p.asin IS NULL
                LIMIT 5
            """)
            for asin, account_id, status in cursor.fetchall():
                print(f"    - {asin} ({account_id}, status={status})")

        print()

        # まとめ
        print("=" * 70)
        print("検証結果まとめ")
        print("=" * 70)

        if all_checks_passed and missing_listings == 0 and orphaned_queue == 0:
            print("✓ すべてのチェックが成功しました")
            print()
            print("Issue #014の修正は正常に完了しています。")
        else:
            issues = []
            if not has_expected_index:
                issues.append("  - UNIQUE制約が正しく設定されていません")
            if len(duplicates) > 0:
                issues.append("  - upload_queueに重複レコードが存在します")
            if missing_listings > 0:
                issues.append(f"  - {missing_listings}件のレコードでlistingsが欠損しています")
            if orphaned_queue > 0:
                issues.append(f"  - {orphaned_queue}件のレコードでproductsが欠損しています")

            if issues:
                print("⚠️  一部のチェックで警告またはエラーが見つかりました")
                print()
                print("以下の項目を確認してください:")
                for issue in issues:
                    print(issue)
            else:
                print("✓ データ整合性は概ね良好です")
                print()
                print("警告がありますが、これらは正常な状態である可能性があります。")

        print("=" * 70)

        return all_checks_passed


if __name__ == "__main__":
    success = verify_queue_integrity()

    if success:
        sys.exit(0)
    else:
        sys.exit(1)
