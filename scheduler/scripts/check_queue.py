"""
キューステータス確認スクリプト

アップロードキューの状態を確認
"""

import sys
from pathlib import Path
from datetime import datetime

# パスを追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scheduler.queue_manager import UploadQueueManager


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='アップロードキューの状態を確認'
    )
    parser.add_argument(
        '--platform',
        type=str,
        default='base',
        help='プラットフォーム名（デフォルト: base）'
    )
    parser.add_argument(
        '--status',
        type=str,
        help='ステータスフィルタ（pending/uploading/success/failed）'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=10,
        help='表示件数（デフォルト: 10）'
    )
    parser.add_argument(
        '--show-due',
        action='store_true',
        help='scheduled_at が到来したアイテムのみ表示'
    )

    args = parser.parse_args()

    print("=" * 60)
    print(f"アップロードキュー状態確認 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    queue_manager = UploadQueueManager()

    # 統計情報を表示
    stats = queue_manager.get_queue_statistics(platform=args.platform)

    print(f"\nプラットフォーム: {args.platform}")
    print(f"\n統計情報:")
    print(f"  待機中 (pending): {stats['pending']}件")
    print(f"  処理中 (uploading): {stats['uploading']}件")
    print(f"  成功 (success): {stats['success']}件")
    print(f"  失敗 (failed): {stats['failed']}件")
    print(f"  合計: {stats['total']}件")

    # アカウント別の統計情報を表示
    print(f"\nアカウント別の統計:")
    with queue_manager.db.get_connection() as conn:
        cursor = conn.cursor()
        account_stats = cursor.execute("""
            SELECT
                account_id,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN status = 'uploading' THEN 1 ELSE 0 END) as uploading,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                COUNT(*) as total
            FROM upload_queue
            WHERE platform = ?
            GROUP BY account_id
            ORDER BY account_id
        """, (args.platform,)).fetchall()

        if account_stats:
            for row in account_stats:
                account_id, pending, uploading, success, failed, total = row
                print(f"  {account_id}:")
                print(f"    待機中: {pending}件 | 処理中: {uploading}件 | 成功: {success}件 | 失敗: {failed}件 | 合計: {total}件")
        else:
            print(f"  （データなし）")

    # アイテム一覧を表示
    print(f"\n{'='*60}")

    if args.show_due:
        print(f"scheduled_at が到来したアイテム（最大{args.limit}件）")
        items = queue_manager.get_scheduled_items_due(
            limit=args.limit,
            platform=args.platform
        )
    else:
        status_text = f"ステータス={args.status}" if args.status else "全ステータス"
        print(f"{status_text}（最大{args.limit}件）")
        items = queue_manager.get_pending_items(
            limit=args.limit,
            platform=args.platform
        )
        if args.status:
            items = queue_manager.db.get_upload_queue(
                status=args.status,
                platform=args.platform,
                limit=args.limit
            )

    print("=" * 60)

    if not items:
        print("\n該当するアイテムはありません")
        return

    print(f"\n{len(items)}件のアイテム:\n")

    for i, item in enumerate(items, 1):
        print(f"{i}. キューID: {item['id']}")
        print(f"   ASIN: {item['asin']}")
        print(f"   アカウント: {item['account_id']}")
        print(f"   ステータス: {item['status']}")
        print(f"   優先度: {item['priority']}")
        print(f"   予定時刻: {item['scheduled_time']}")

        if item.get('processed_at'):
            print(f"   処理時刻: {item['processed_at']}")

        if item.get('error_message'):
            print(f"   エラー: {item['error_message']}")

        if item.get('result_data'):
            result = item['result_data']
            if isinstance(result, dict) and result.get('item_id'):
                print(f"   BASE item_id: {result['item_id']}")

        print()

    print("=" * 60)


if __name__ == '__main__':
    main()
