"""
滞留商品をキューに追加するスクリプト

キューに未登録のpending商品を抽出し、
時間分散（6AM-11PM）でアップロードキューに追加します。
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
import math

# パスを追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from inventory.core.master_db import MasterDB


def get_next_business_start(now: datetime = None) -> datetime:
    """
    次の営業時間開始（翌日6時）を取得

    Args:
        now: 基準時刻（デフォルトは現在時刻）

    Returns:
        datetime: 次の営業時間開始
    """
    if now is None:
        now = datetime.now()

    # 明日の6時
    next_day = now.date() + timedelta(days=1)
    return datetime.combine(next_day, datetime.min.time()).replace(hour=6, minute=0, second=0, microsecond=0)


def calculate_time_slots(items_count: int, start_time: datetime,
                         business_hours_start: int = 6,
                         business_hours_end: int = 23,
                         daily_limit: int = 1000) -> list:
    """
    時間分散スロットを計算（1日の上限を最大限活用）

    Args:
        items_count: アイテム数
        start_time: 開始時刻
        business_hours_start: 営業時間開始（時）
        business_hours_end: 営業時間終了（時）
        daily_limit: 1日あたりの上限

    Returns:
        list: datetime のリスト
    """
    time_slots = []

    # 営業時間（分）を計算
    business_hours = business_hours_end - business_hours_start  # 17時間
    business_minutes = business_hours * 60  # 1020分

    # 現在の日付
    current_date = start_time.date()
    items_today = 0

    for i in range(items_count):
        # 1日の上限に達したら翌日に移動
        if items_today >= daily_limit:
            current_date += timedelta(days=1)
            items_today = 0

        # 今日の進捗率（0.0～1.0）
        progress = items_today / min(items_count - i + items_today, daily_limit)

        # 営業時間内で均等に分散
        minutes_from_start = int(progress * business_minutes)
        hours_from_start = minutes_from_start // 60
        minutes_in_hour = minutes_from_start % 60

        scheduled_time = datetime.combine(
            current_date,
            datetime.min.time()
        ).replace(
            hour=business_hours_start + hours_from_start,
            minute=minutes_in_hour,
            second=0,
            microsecond=0
        )

        time_slots.append(scheduled_time)
        items_today += 1

    return time_slots


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='滞留商品をキューに追加'
    )
    parser.add_argument(
        '--platform',
        type=str,
        default='base',
        help='プラットフォーム名（デフォルト: base）'
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='追加するアイテム数の上限（指定しない場合は全て）'
    )
    parser.add_argument(
        '--priority',
        type=int,
        default=5,
        help='優先度（1-20、デフォルト: 5）'
    )
    parser.add_argument(
        '--daily-limit',
        type=int,
        default=1000,
        help='1日あたりのアイテム上限（デフォルト: 1000）'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='実際には追加せず、シミュレーションのみ実行'
    )
    parser.add_argument(
        '--yes', '-y',
        action='store_true',
        help='確認をスキップして自動実行'
    )

    args = parser.parse_args()

    print("=" * 70)
    print("滞留商品のキューへの追加")
    print("=" * 70)

    db = MasterDB()

    # 滞留商品を取得（正常な商品のみ）
    print(f"\nプラットフォーム '{args.platform}' の滞留商品を取得中...")

    with db.get_connection() as conn:
        cursor = conn.cursor()

        # キューに未登録 かつ 正常な商品を取得
        query = '''
            SELECT
                l.asin,
                l.account_id,
                l.selling_price,
                p.title_ja
            FROM listings l
            INNER JOIN products p ON l.asin = p.asin
            WHERE l.platform = ?
            AND l.status = 'pending'
            AND NOT EXISTS (
                SELECT 1 FROM upload_queue uq
                WHERE uq.asin = l.asin AND uq.platform = l.platform
            )
            AND l.selling_price IS NOT NULL
            AND l.selling_price > 0
            AND l.asin NOT LIKE 'B0TEST%'
            ORDER BY l.account_id, l.id ASC
        '''

        if args.limit:
            query += f' LIMIT {args.limit}'

        cursor.execute(query, (args.platform,))
        items = cursor.fetchall()

    if not items:
        print(f"\n追加対象のアイテムがありません")
        return

    print(f"\n取得したアイテム: {len(items)}件")

    # アカウント別にグループ化
    account_items = {}
    for row in items:
        account_id = row['account_id']
        if account_id not in account_items:
            account_items[account_id] = []
        account_items[account_id].append(row)

    print(f"\nアカウント別内訳:")
    for account_id, account_item_list in account_items.items():
        print(f"  {account_id}: {len(account_item_list)}件")

    # 各アカウント別にスケジューリング（並列処理可能）
    start_time = get_next_business_start()
    account_schedules = {}

    print(f"\nスケジューリング（アカウント別・並列処理）:")
    for account_id, account_item_list in account_items.items():
        time_slots = calculate_time_slots(
            len(account_item_list),
            start_time,
            daily_limit=args.daily_limit
        )
        account_schedules[account_id] = time_slots

        days_needed = (time_slots[-1].date() - time_slots[0].date()).days + 1
        print(f"  {account_id}:")
        print(f"    開始時刻: {time_slots[0].strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"    終了時刻: {time_slots[-1].strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"    期間: {days_needed}日")
        print(f"    件数/日: {len(account_item_list) // days_needed if days_needed > 0 else len(account_item_list)}件")

    print(f"\n全体:")
    print(f"  優先度: {args.priority}")
    print(f"  1日あたりの上限（各アカウント）: {args.daily_limit}件")
    print(f"  並列処理: 各アカウント独立してスケジュール（同時実行可能）")

    # itemsの順序に合わせてtime_slotsを構築
    time_slots = []
    account_index = {account_id: 0 for account_id in account_items.keys()}

    for row in items:
        account_id = row['account_id']
        idx = account_index[account_id]
        time_slots.append(account_schedules[account_id][idx])
        account_index[account_id] += 1

    # サンプル表示
    print(f"\nサンプル（最初の5件）:")
    for i in range(min(5, len(items))):
        row = items[i]
        scheduled = time_slots[i]
        title = row['title_ja'][:40] if row['title_ja'] else 'N/A'
        print(f"  {i+1}. ASIN: {row['asin']} | Account: {row['account_id']} | "
              f"Price: JPY {row['selling_price']:,.0f} | "
              f"Time: {scheduled.strftime('%m/%d %H:%M')}")
        print(f"      Title: {title}...")

    # 確認
    if args.dry_run:
        print(f"\n[DRY RUN] 実際には追加しません")
    elif not args.yes:
        response = input(f"\n{len(items)}件のアイテムをキューに追加しますか？ (y/N): ")
        if response.lower() != 'y':
            print("キャンセルしました")
            return
    else:
        print(f"\n{len(items)}件のアイテムをキューに追加します（--yesオプション指定）")

    if args.dry_run:
        print("\n[DRY RUN] シミュレーション完了")
        return

    # キューに追加
    print("\nキューに追加中...")

    success_count = 0
    failed_count = 0

    with db.get_connection() as conn:
        cursor = conn.cursor()

        for i, row in enumerate(items):
            asin = row['asin']
            account_id = row['account_id']
            scheduled_time = time_slots[i].isoformat()

            try:
                cursor.execute('''
                    INSERT INTO upload_queue
                    (asin, platform, account_id, scheduled_time, priority, status)
                    VALUES (?, ?, ?, ?, ?, 'pending')
                ''', (asin, args.platform, account_id, scheduled_time, args.priority))
                success_count += 1

                if (i + 1) % 100 == 0:
                    print(f"  進捗: {i + 1}/{len(items)}")
            except Exception as e:
                print(f"  エラー (ASIN: {asin}): {e}")
                failed_count += 1

    # 結果表示
    print("\n" + "=" * 70)
    print("追加完了")
    print("=" * 70)
    print(f"成功: {success_count}件")
    print(f"失敗: {failed_count}件")
    print(f"開始時刻: {time_slots[0].strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"終了時刻: {time_slots[-1].strftime('%Y-%m-%d %H:%M:%S')}")

    if account_items:
        print(f"\nアカウント別割り当て:")
        for account_id, items_list in account_items.items():
            print(f"  {account_id}: {len(items_list)}件")

    print("=" * 70)


if __name__ == '__main__':
    main()
