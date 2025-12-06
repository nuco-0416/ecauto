"""
キューへのアイテム追加スクリプト

マスタDBからBASE出品対象のアイテムをキューに追加
"""

import sys
from pathlib import Path
from datetime import datetime

# パスを追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scheduler.queue_manager import UploadQueueManager
from inventory.core.master_db import MasterDB


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='アップロードキューにアイテムを追加'
    )
    parser.add_argument(
        '--platform',
        type=str,
        default='base',
        help='プラットフォーム名（デフォルト: base）'
    )
    parser.add_argument(
        '--account-id',
        type=str,
        help='アカウントID（指定しない場合は自動割り当て）'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=100,
        help='追加するアイテム数（デフォルト: 100）'
    )
    parser.add_argument(
        '--priority',
        type=int,
        default=5,
        help='優先度（1-20、デフォルト: 5）'
    )
    parser.add_argument(
        '--distribute',
        action='store_true',
        help='時間分散を行う（6AM-11PM）'
    )
    parser.add_argument(
        '--yes', '-y',
        action='store_true',
        help='確認をスキップして自動実行'
    )

    args = parser.parse_args()

    print("=" * 60)
    print("アップロードキューへのアイテム追加")
    print("=" * 60)

    # MasterDBとQueueManagerを初期化
    db = MasterDB()
    queue_manager = UploadQueueManager()

    # platform='base' かつ status='pending' の出品情報を取得
    print(f"\nプラットフォーム '{args.platform}' の pending 状態のアイテムを取得中...")

    with db.get_connection() as conn:
        cursor = conn.cursor()

        # account_idも一緒に取得（listingsテーブルのaccount_idを尊重）
        cursor.execute('''
            SELECT asin, account_id
            FROM listings
            WHERE platform = ?
            AND status = 'pending'
            LIMIT ?
        ''', (args.platform, args.limit))

        items = [(row['asin'], row['account_id']) for row in cursor.fetchall()]

    if not items:
        print(f"\n追加対象のアイテムがありません")
        return

    print(f"取得したアイテム: {len(items)}件")
    print(f"プラットフォーム: {args.platform}")
    print(f"優先度: {args.priority}")
    print(f"時間分散: {'あり' if args.distribute else 'なし'}")

    # アカウント別の内訳を表示
    account_counts = {}
    for asin, account_id in items:
        account_counts[account_id] = account_counts.get(account_id, 0) + 1

    print(f"\nアカウント別内訳:")
    for account_id, count in account_counts.items():
        print(f"  {account_id}: {count}件")

    # 確認
    if not args.yes:
        response = input(f"\n{len(items)}件のアイテムをキューに追加しますか？ (y/N): ")
        if response.lower() != 'y':
            print("キャンセルしました")
            return
    else:
        print(f"\n{len(items)}件のアイテムをキューに追加します（--yesオプション指定）")

    # 個別に追加（listingsテーブルのaccount_idを尊重）
    print("\nキューに追加中...")

    # 時間スロットを計算
    if args.distribute:
        start_time = queue_manager._get_next_upload_start_time()
        time_slots = queue_manager._calculate_time_slots(len(items), start_time)
    else:
        time_slots = [datetime.now()] * len(items)

    success_count = 0
    failed_count = 0

    for i, (asin, account_id) in enumerate(items):
        scheduled_at = time_slots[i]

        if queue_manager.add_to_queue(
            asin=asin,
            platform=args.platform,
            account_id=account_id,  # listingsテーブルのaccount_idを使用
            priority=args.priority,
            scheduled_at=scheduled_at
        ):
            success_count += 1
        else:
            failed_count += 1

        if (i + 1) % 100 == 0:
            print(f"  進捗: {i + 1}/{len(items)}")

    result = {
        'success': success_count,
        'failed': failed_count,
        'start_time': time_slots[0].isoformat() if time_slots else None,
        'end_time': time_slots[-1].isoformat() if time_slots else None,
        'account_distribution': account_counts
    }

    # 結果表示
    print("\n" + "=" * 60)
    print("追加完了")
    print("=" * 60)
    print(f"成功: {result['success']}件")
    print(f"失敗: {result['failed']}件")
    print(f"開始時刻: {result.get('start_time', '不明')}")
    print(f"終了時刻: {result.get('end_time', '不明')}")

    if result.get('account_distribution'):
        print(f"\nアカウント別割り当て:")
        for account_id, count in result['account_distribution'].items():
            print(f"  {account_id}: {count}件")

    print("=" * 60)


if __name__ == '__main__':
    main()
