"""
バリデーションエラーで失敗したキューレコードを一括削除するスクリプト

特定のエラーメッセージを持つfailedステータスのレコードを削除します。

実行方法:
    python scheduler/scripts/cleanup_validation_error_queue.py [--error-pattern "タイトルが取得できません"] [--dry-run]
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


def cleanup_validation_error_queue(error_pattern: str, dry_run=False):
    """
    バリデーションエラーで失敗したキューレコードを削除

    Args:
        error_pattern: 削除対象とするエラーメッセージのパターン（LIKE句で使用）
        dry_run: Trueの場合、変更を実行せずにログのみ出力

    Returns:
        dict: 結果の統計情報
    """
    print("=" * 70)
    print("バリデーションエラーキューレコードのクリーンアップ")
    print("=" * 70)
    print()

    if dry_run:
        print("[DRY-RUN MODE] 変更は実行されません")
        print()

    db = MasterDB()

    stats = {
        'total_failed': 0,
        'matching_records': 0,
        'deleted': 0,
        'errors': 0
    }

    with db.get_connection() as conn:
        cursor = conn.cursor()

        # 全体のfailedレコード数を取得
        print("[1/3] キューの状態を確認中...")
        cursor.execute('''
            SELECT COUNT(*) as count
            FROM upload_queue
            WHERE status = 'failed'
        ''')
        stats['total_failed'] = cursor.fetchone()['count']

        # エラーパターンに一致するレコードを取得
        cursor.execute('''
            SELECT COUNT(*) as count
            FROM upload_queue
            WHERE status = 'failed'
            AND error_message LIKE ?
        ''', (f'%{error_pattern}%',))
        stats['matching_records'] = cursor.fetchone()['count']

        print(f"  失敗レコード総数: {stats['total_failed']}件")
        print(f"  削除対象レコード（エラーパターン: '{error_pattern}'）: {stats['matching_records']}件")
        print()

        if stats['matching_records'] == 0:
            print("  ✓ 削除対象のレコードはありません")
            print()
            return stats

        # サンプル表示（最初の10件）
        print("[2/3] 削除対象のサンプルを表示中...")
        cursor.execute('''
            SELECT id, asin, platform, account_id, error_message, created_at
            FROM upload_queue
            WHERE status = 'failed'
            AND error_message LIKE ?
            ORDER BY created_at DESC
            LIMIT 10
        ''', (f'%{error_pattern}%',))

        print("  削除対象レコード（最初の10件）:")
        for row in cursor.fetchall():
            print(f"    ID: {row['id']} | ASIN: {row['asin']} | Platform: {row['platform']} | "
                  f"Account: {row['account_id']}")
            print(f"      Error: {row['error_message']}")
            print(f"      Created: {row['created_at']}")
            print()

        if dry_run:
            print("[DRY-RUN] 以下のクリーンアップが実行されます:")
            print(f"  - {stats['matching_records']}件のレコードを削除")
            print()
            print("[DRY-RUN] 実際の変更は行いませんでした")
            return stats

        # 確認メッセージ
        print(f"警告: {stats['matching_records']}件のレコードを削除します")
        response = input("続行しますか？ (y/N): ")
        if response.lower() != 'y':
            print("キャンセルしました")
            return stats

        # 実際に削除を実行
        print()
        print("[3/3] レコードを削除中...")

        try:
            cursor.execute('''
                DELETE FROM upload_queue
                WHERE status = 'failed'
                AND error_message LIKE ?
            ''', (f'%{error_pattern}%',))

            stats['deleted'] = cursor.rowcount
            conn.commit()

            print(f"  ✓ {stats['deleted']}件のレコードを削除しました")

        except Exception as e:
            stats['errors'] += 1
            print(f"  ❌ エラーが発生しました: {str(e)}")
            conn.rollback()

        print()

        # クリーンアップ後の統計
        cursor.execute('''
            SELECT COUNT(*) as count
            FROM upload_queue
            WHERE status = 'failed'
        ''')
        failed_after = cursor.fetchone()['count']

        print("=" * 70)
        print("クリーンアップ結果:")
        print("=" * 70)
        print(f"  削除前の失敗レコード数: {stats['total_failed']}件")
        print(f"  削除したレコード: {stats['deleted']}件")
        print(f"  削除後の失敗レコード数: {failed_after}件")
        print(f"  エラー: {stats['errors']}件")
        print()

        if stats['errors'] == 0:
            print("✓ クリーンアップが正常に完了しました")
        else:
            print("⚠️  エラーが発生しました")

        print("=" * 70)

        return stats


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="バリデーションエラーで失敗したキューレコードを削除"
    )
    parser.add_argument(
        "--error-pattern",
        default="タイトルが取得できません",
        help="削除対象とするエラーメッセージのパターン（デフォルト: 'タイトルが取得できません'）"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="変更を実行せずにログのみ出力"
    )

    args = parser.parse_args()

    stats = cleanup_validation_error_queue(
        error_pattern=args.error_pattern,
        dry_run=args.dry_run
    )

    # 成功条件: エラーがない
    if stats['errors'] == 0:
        sys.exit(0)
    else:
        sys.exit(1)
