"""
Issue #014: upload_queueの重複レコードをクリーンアップするスクリプト

同じ(asin, platform, account_id)の組み合わせで複数のレコードが存在する場合、
最適なレコードを1つだけ残して他を削除します。

実行方法:
    python scheduler/scripts/cleanup_duplicate_queue.py [--dry-run]
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


def cleanup_duplicate_queue(dry_run=False):
    """
    upload_queueの重複レコードをクリーンアップ

    優先順位:
    1. statusの優先順位: uploading > pending > success > failed
    2. 同じstatusの場合: 最新のレコード（created_atが最新）を残す
    3. 異なるaccount_idの場合: listingsに存在するaccount_idを優先

    Args:
        dry_run: Trueの場合、変更を実行せずにログのみ出力

    Returns:
        dict: 結果の統計情報
    """
    print("=" * 70)
    print("Issue #014: upload_queueの重複レコードクリーンアップ")
    print("=" * 70)
    print()

    if dry_run:
        print("[DRY-RUN MODE] 変更は実行されません")
        print()

    db = MasterDB()

    stats = {
        'total_duplicates': 0,
        'unique_asins': 0,
        'records_to_delete': 0,
        'records_to_keep': 0,
        'deleted': 0,
        'errors': 0,
        'error_details': []
    }

    with db.get_connection() as conn:
        # 重複しているASINを取得
        print("[1/3] 重複しているASINを検索中...")
        cursor = conn.execute('''
            SELECT asin, platform, COUNT(*) as count
            FROM upload_queue
            GROUP BY asin, platform
            HAVING COUNT(*) > 1
            ORDER BY count DESC, asin
        ''')
        duplicates = cursor.fetchall()

        stats['unique_asins'] = len(duplicates)

        if stats['unique_asins'] == 0:
            print("  ✓ 重複レコードはありません")
            print()
            return stats

        # 重複しているレコード総数を計算
        cursor = conn.execute('''
            SELECT COUNT(*)
            FROM upload_queue
            WHERE (asin, platform) IN (
                SELECT asin, platform
                FROM upload_queue
                GROUP BY asin, platform
                HAVING COUNT(*) > 1
            )
        ''')
        stats['total_duplicates'] = cursor.fetchone()[0]

        print(f"  重複しているASIN: {stats['unique_asins']}件")
        print(f"  重複レコード総数: {stats['total_duplicates']}件")
        print()

        # サンプル表示（最初の10件）
        print("  重複パターン（上位10件）:")
        for i, (asin, platform, count) in enumerate(duplicates[:10], 1):
            print(f"    {i}. {asin} ({platform}): {count}件")
        if len(duplicates) > 10:
            print(f"    ... 他 {len(duplicates) - 10}件")
        print()

        if dry_run:
            print("[DRY-RUN] クリーンアップ対象の分析中...")
            print()

        # 各重複ASINについて処理
        print("[2/3] クリーンアップ対象を決定中...")
        print()

        delete_ids = []
        keep_count = 0

        for i, (asin, platform, count) in enumerate(duplicates, 1):
            # 進捗表示（100件ごと）
            if i % 100 == 0 or i == 1:
                print(f"  進捗: {i}/{stats['unique_asins']}件 処理中...")

            try:
                # このASINのすべてのレコードを取得
                cursor = conn.execute('''
                    SELECT id, account_id, status, created_at, scheduled_time
                    FROM upload_queue
                    WHERE asin = ? AND platform = ?
                    ORDER BY
                        CASE status
                            WHEN 'uploading' THEN 1
                            WHEN 'pending' THEN 2
                            WHEN 'success' THEN 3
                            WHEN 'failed' THEN 4
                            ELSE 5
                        END,
                        created_at DESC
                ''', (asin, platform))
                records = cursor.fetchall()

                # listingsに存在するaccount_idを確認
                cursor = conn.execute('''
                    SELECT DISTINCT account_id
                    FROM listings
                    WHERE asin = ? AND platform = ?
                ''', (asin, platform))
                listings_accounts = [row[0] for row in cursor.fetchall()]

                # 最適なレコードを選択
                keep_id = None

                # 優先1: listingsに存在するaccount_idで、最優先のstatus
                for record_id, account_id, status, created_at, scheduled_time in records:
                    if account_id in listings_accounts:
                        keep_id = record_id
                        break

                # 優先2: listingsになくても、最優先のstatus（最新）
                if keep_id is None and records:
                    keep_id = records[0][0]

                # 残すレコード以外を削除対象に追加
                for record_id, account_id, status, created_at, scheduled_time in records:
                    if record_id != keep_id:
                        delete_ids.append(record_id)
                    else:
                        keep_count += 1

                # サンプル表示（最初の10件）
                if i <= 10:
                    print(f"    {asin} ({platform}):")
                    for record_id, account_id, status, created_at, scheduled_time in records:
                        marker = "✓ 保持" if record_id == keep_id else "✗ 削除"
                        print(f"      {marker}: ID={record_id}, account={account_id}, status={status}")

            except Exception as e:
                stats['errors'] += 1
                error_msg = f"  {asin} ({platform}): {str(e)}"
                if len(stats['error_details']) < 10:
                    stats['error_details'].append(error_msg)
                if i <= 10:
                    print(f"    ❌ {error_msg}")

        print()

        stats['records_to_delete'] = len(delete_ids)
        stats['records_to_keep'] = keep_count

        print(f"  削除対象レコード: {stats['records_to_delete']}件")
        print(f"  保持するレコード: {stats['records_to_keep']}件")
        print()

        if dry_run:
            print("[DRY-RUN] 以下のクリーンアップが実行されます:")
            print(f"  - {stats['records_to_delete']}件のレコードを削除")
            print(f"  - {stats['records_to_keep']}件のレコードを保持")
            print()
            print("[DRY-RUN] 実際の変更は行いませんでした")
            return stats

        # 実際に削除を実行
        print("[3/3] 重複レコードを削除中...")

        if stats['records_to_delete'] > 0:
            # 一括削除（パフォーマンス向上のため）
            placeholders = ','.join('?' * len(delete_ids))
            conn.execute(f'''
                DELETE FROM upload_queue
                WHERE id IN ({placeholders})
            ''', delete_ids)

            conn.commit()

            stats['deleted'] = stats['records_to_delete']
            print(f"  ✓ {stats['deleted']}件のレコードを削除しました")
        else:
            print("  削除対象のレコードはありませんでした")

        print()

        # クリーンアップ後の統計
        cursor = conn.execute('''
            SELECT COUNT(*)
            FROM upload_queue
        ''')
        total_after = cursor.fetchone()[0]

        cursor = conn.execute('''
            SELECT asin, platform, COUNT(*) as count
            FROM upload_queue
            GROUP BY asin, platform
            HAVING COUNT(*) > 1
        ''')
        duplicates_after = cursor.fetchall()

        print("=" * 70)
        print("クリーンアップ結果:")
        print("=" * 70)
        print(f"  重複ASIN数: {stats['unique_asins']}件")
        print(f"  削除したレコード: {stats['deleted']}件")
        print(f"  エラー: {stats['errors']}件")
        print()
        print(f"  クリーンアップ後:")
        print(f"    - upload_queue総レコード数: {total_after}件")
        print(f"    - 残存する重複ASIN: {len(duplicates_after)}件")
        print()

        if stats['error_details']:
            print("エラー詳細（最大10件）:")
            for error in stats['error_details']:
                print(error)
            print()

        if len(duplicates_after) == 0:
            print("✓ すべての重複レコードがクリーンアップされました")
        else:
            print("⚠️  一部の重複が残っています")
            print("\n  残存する重複（最初の5件）:")
            for asin, platform, count in duplicates_after[:5]:
                print(f"    - {asin} ({platform}): {count}件")

        print("=" * 70)

        return stats


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="upload_queueの重複レコードをクリーンアップ"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="変更を実行せずにログのみ出力"
    )

    args = parser.parse_args()

    stats = cleanup_duplicate_queue(dry_run=args.dry_run)

    # 成功条件: エラーがないか、削除成功数がエラー数より多い
    if stats['errors'] == 0 or stats['deleted'] > stats['errors']:
        sys.exit(0)
    else:
        sys.exit(1)
