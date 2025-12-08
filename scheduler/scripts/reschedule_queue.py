"""
キューのスケジュールを再設定するスクリプト

既にキューに追加されたアイテムのscheduled_timeを現在時刻に更新
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

# パスを追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from inventory.core.master_db import MasterDB


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='キューのスケジュールを再設定'
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
        default='pending',
        help='対象ステータス（デフォルト: pending）'
    )
    parser.add_argument(
        '--now',
        action='store_true',
        help='すべて現在時刻に設定'
    )
    parser.add_argument(
        '--interval',
        type=int,
        default=60,
        help='アイテム間隔（秒、デフォルト: 60）'
    )
    parser.add_argument(
        '--yes', '-y',
        action='store_true',
        help='確認をスキップして自動実行'
    )
    parser.add_argument(
        '--account-id',
        type=str,
        help='アカウントIDでフィルタリング（例: base_account_2）'
    )
    parser.add_argument(
        '--end-time',
        type=str,
        help='終了時刻（例: "2025-12-07 23:00"）までに均等に分散'
    )
    parser.add_argument(
        '--start-time',
        type=str,
        help='開始時刻（例: "2025-12-07 07:00"）。デフォルトは現在時刻'
    )

    args = parser.parse_args()

    print("=" * 60)
    print("キューのスケジュール再設定")
    print("=" * 60)

    db = MasterDB()

    # 対象アイテムを取得
    with db.get_connection() as conn:
        cursor = conn.cursor()

        # アカウントIDフィルタリングの条件を追加
        if args.account_id:
            cursor.execute("""
                SELECT id, asin, account_id, scheduled_time
                FROM upload_queue
                WHERE platform = ? AND status = ? AND account_id = ?
                ORDER BY priority DESC, scheduled_time ASC
            """, (args.platform, args.status, args.account_id))
        else:
            cursor.execute("""
                SELECT id, asin, account_id, scheduled_time
                FROM upload_queue
                WHERE platform = ? AND status = ?
                ORDER BY priority DESC, scheduled_time ASC
            """, (args.platform, args.status))

        items = cursor.fetchall()

    if not items:
        print(f"\n対象アイテムがありません（platform={args.platform}, status={args.status}）")
        return

    print(f"\n対象アイテム: {len(items)}件")
    print(f"プラットフォーム: {args.platform}")
    print(f"ステータス: {args.status}")
    if args.account_id:
        print(f"アカウントID: {args.account_id}")

    # スケジュール計算
    if args.end_time:
        # 終了時刻までに均等に分散
        start_time = datetime.strptime(args.start_time, '%Y-%m-%d %H:%M') if args.start_time else datetime.now()
        end_time = datetime.strptime(args.end_time, '%Y-%m-%d %H:%M')

        # 利用可能な時間（秒）
        total_seconds = (end_time - start_time).total_seconds()

        if total_seconds <= 0:
            print(f"\nエラー: 終了時刻が開始時刻より前です")
            return

        if len(items) > 1:
            # アイテム間の間隔を計算
            interval = total_seconds / (len(items) - 1)
        else:
            interval = 0

        print(f"新しいスケジュール: {start_time.strftime('%Y-%m-%d %H:%M')} 〜 {end_time.strftime('%Y-%m-%d %H:%M')}")
        print(f"間隔: {interval:.1f}秒 ({interval/60:.1f}分)")
        base_time = start_time
    elif args.now:
        print(f"新しいスケジュール: 現在時刻から{args.interval}秒間隔")
        base_time = datetime.now()
        interval = args.interval
    else:
        print("新しいスケジュール: 変更なし（--nowまたは--end-timeオプションを指定してください）")
        return

    # サンプル表示
    if len(items) > 0:
        print(f"\n最初の3件のサンプル:")
        for i in range(min(3, len(items))):
            item = items[i]
            new_time = base_time + timedelta(seconds=interval * i)
            print(f"  ASIN: {item[1]}, 現在: {item[3]}, 新: {new_time.strftime('%Y-%m-%d %H:%M:%S')}")

    # 確認
    if not args.yes:
        response = input(f"\n{len(items)}件のスケジュールを変更しますか？ (y/N): ")
        if response.lower() != 'y':
            print("キャンセルしました")
            return
    else:
        print(f"\n{len(items)}件のスケジュールを変更します（--yesオプション指定）")

    # 更新実行
    print("\nスケジュールを更新中...")

    with db.get_connection() as conn:
        cursor = conn.cursor()

        for i, item in enumerate(items):
            queue_id = item[0]
            new_scheduled_at = base_time + timedelta(seconds=interval * i)

            cursor.execute("""
                UPDATE upload_queue
                SET scheduled_time = ?
                WHERE id = ?
            """, (new_scheduled_at, queue_id))

            if (i + 1) % 100 == 0:
                print(f"  {i + 1}/{len(items)}件 更新完了")

        conn.commit()

    print("\n" + "=" * 60)
    print("更新完了")
    print("=" * 60)
    print(f"更新件数: {len(items)}件")
    print(f"開始時刻: {base_time.strftime('%Y-%m-%d %H:%M:%S')}")
    if len(items) > 0:
        final_time = base_time + timedelta(seconds=interval * (len(items) - 1))
        print(f"終了予定: {final_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)


if __name__ == '__main__':
    main()
