"""
uploadingステータスで停止しているレコードをpendingに戻すスクリプト

デーモンが途中で停止し、uploadingステータスのまま放置されているレコードを
pendingに戻して再処理できるようにします。

実行方法:
    python scheduler/scripts/reset_uploading_to_pending.py [--dry-run]
"""

import sys
import os
from pathlib import Path
import io
from datetime import datetime

# UTF-8出力を強制（Windows環境でのcp932エラー回避）
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from inventory.core.master_db import MasterDB


def reset_uploading_to_pending(dry_run=False):
    """
    uploadingステータスのレコードをpendingに戻す

    Args:
        dry_run: Trueの場合、変更を実行せずにログのみ出力

    Returns:
        dict: 結果の統計情報
    """
    print("=" * 70)
    print("uploadingステータスのレコードをpendingに戻す")
    print("=" * 70)
    print()

    if dry_run:
        print("[DRY-RUN MODE] 変更は実行されません")
        print()

    db = MasterDB()

    stats = {
        'uploading_records': 0,
        'reset': 0,
        'errors': 0
    }

    with db.get_connection() as conn:
        cursor = conn.cursor()

        # uploadingステータスのレコードを取得
        print("[1/2] uploadingステータスのレコードを確認中...")
        cursor.execute('''
            SELECT COUNT(*) as count
            FROM upload_queue
            WHERE status = 'uploading'
        ''')
        stats['uploading_records'] = cursor.fetchone()['count']

        print(f"  uploadingステータスのレコード: {stats['uploading_records']}件")
        print()

        if stats['uploading_records'] == 0:
            print("  ✓ uploadingステータスのレコードはありません")
            print()
            return stats

        # サンプル表示（最初の10件）
        cursor.execute('''
            SELECT id, asin, platform, account_id, created_at, scheduled_time
            FROM upload_queue
            WHERE status = 'uploading'
            ORDER BY created_at DESC
            LIMIT 10
        ''')

        now = datetime.now()
        print("  uploadingステータスのレコード（最初の10件）:")
        for row in cursor.fetchall():
            print(f"    ID: {row['id']} | ASIN: {row['asin']} | Platform: {row['platform']} | "
                  f"Account: {row['account_id']}")
            print(f"      Created: {row['created_at']} | Scheduled: {row['scheduled_time']}")

            # 経過時間を計算
            if row['created_at']:
                try:
                    created = datetime.fromisoformat(row['created_at'])
                    elapsed = now - created
                    hours = elapsed.total_seconds() / 3600
                    print(f"      経過時間: {hours:.1f}時間前")
                except:
                    pass
            print()

        if dry_run:
            print("[DRY-RUN] 以下の処理が実行されます:")
            print(f"  - {stats['uploading_records']}件のレコードを 'uploading' → 'pending' に変更")
            print()
            print("[DRY-RUN] 実際の変更は行いませんでした")
            return stats

        # 確認メッセージ
        print(f"警告: {stats['uploading_records']}件のレコードを 'pending' に戻します")
        response = input("続行しますか？ (y/N): ")
        if response.lower() != 'y':
            print("キャンセルしました")
            return stats

        # 実際に更新を実行
        print()
        print("[2/2] レコードを更新中...")

        try:
            cursor.execute('''
                UPDATE upload_queue
                SET status = 'pending'
                WHERE status = 'uploading'
            ''')

            stats['reset'] = cursor.rowcount
            conn.commit()

            print(f"  ✓ {stats['reset']}件のレコードを 'pending' に戻しました")

        except Exception as e:
            stats['errors'] += 1
            print(f"  ❌ エラーが発生しました: {str(e)}")
            conn.rollback()

        print()

        # 更新後の統計
        cursor.execute('''
            SELECT COUNT(*) as count
            FROM upload_queue
            WHERE status = 'uploading'
        ''')
        uploading_after = cursor.fetchone()['count']

        cursor.execute('''
            SELECT COUNT(*) as count
            FROM upload_queue
            WHERE status = 'pending'
        ''')
        pending_after = cursor.fetchone()['count']

        print("=" * 70)
        print("更新結果:")
        print("=" * 70)
        print(f"  更新前のuploadingレコード数: {stats['uploading_records']}件")
        print(f"  pendingに戻したレコード: {stats['reset']}件")
        print(f"  更新後のuploadingレコード数: {uploading_after}件")
        print(f"  更新後のpendingレコード数: {pending_after}件")
        print(f"  エラー: {stats['errors']}件")
        print()

        if stats['errors'] == 0:
            print("✓ 更新が正常に完了しました")
            print()
            print("[次のステップ]")
            print("upload_daemonを起動すると、これらのレコードが再処理されます。")
        else:
            print("⚠️  エラーが発生しました")

        print("=" * 70)

        return stats


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="uploadingステータスのレコードをpendingに戻す"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="変更を実行せずにログのみ出力"
    )

    args = parser.parse_args()

    stats = reset_uploading_to_pending(dry_run=args.dry_run)

    # 成功条件: エラーがない
    if stats['errors'] == 0:
        sys.exit(0)
    else:
        sys.exit(1)
