#!/usr/bin/env python3
"""
productsテーブルから直接listingsにコピーするツール

キャッシュファイル（JSON）のTTL期限切れ問題を回避し、
productsテーブルから直接商品情報を取得してlistingsとupload_queueに追加します。

使い方:
    python shared/utils/copy_products_to_listings.py \
        --asin-file asins_for_account3.txt \
        --platform base \
        --account-id base_account_3 \
        --dry-run
"""

import sys
import argparse
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path


def generate_sku(asin: str, account_id: str) -> str:
    """SKUを生成"""
    timestamp = datetime.now().strftime("%y%m%d%H%M")
    account_suffix = account_id.split('_')[-1] if '_' in account_id else account_id[:3]
    return f"{asin}-{account_suffix}-{timestamp}"


def calculate_selling_price(amazon_price: float, markup_rate: float = 1.3) -> int:
    """販売価格を計算"""
    if amazon_price is None or amazon_price <= 0:
        return 0
    return int(amazon_price * markup_rate)


def copy_products_to_listings(
    asin_file: str,
    platform: str,
    account_id: str,
    markup_rate: float = 1.3,
    dry_run: bool = False,
    db_path: str = "inventory/data/master.db",
    start_date: datetime = None,
    daily_limit: int = 1000,
    hourly_limit: int = 100
) -> dict:
    """
    productsテーブルからlistingsとupload_queueにコピー

    Args:
        asin_file: ASINリストファイルパス
        platform: プラットフォーム名
        account_id: アカウントID
        markup_rate: 掛け率（デフォルト: 1.3）
        dry_run: DRY RUNモード
        db_path: データベースファイルパス
        start_date: 開始日時（デフォルト: 翌日6:00）
        daily_limit: 1日あたりの上限（デフォルト: 1000）
        hourly_limit: 1時間あたりの上限（デフォルト: 100）

    Returns:
        dict: 処理結果（added_count, skipped_count, failed_count）
    """
    # ASINリストを読み込み
    asins = []
    with open(asin_file, 'r', encoding='utf-8') as f:
        for line in f:
            asin = line.strip()
            if asin and not asin.startswith('#'):
                asins.append(asin)

    print(f"[INFO] ASINリストから{len(asins)}件を読み込みました")

    # データベース接続
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    added_count = 0
    skipped_count = 0
    failed_count = 0

    # スケジューリング設定
    if start_date is None:
        start_date = datetime.now().replace(hour=6, minute=0, second=0, microsecond=0) + timedelta(days=1)

    end_time = start_date.replace(hour=23, minute=0)
    time_slots_per_day = min(daily_limit, int((end_time - start_date).total_seconds() / 60))

    print(f"\n[INFO] スケジュール設定:")
    print(f"  開始日時: {start_date.strftime('%Y-%m-%d %H:%M')}")
    print(f"  終了日時: {end_time.strftime('%Y-%m-%d %H:%M')}")
    print(f"  1日あたりの上限: {daily_limit}件")
    print(f"  1時間あたりの上限: {hourly_limit}件")

    for idx, asin in enumerate(asins, 1):
        try:
            # productsテーブルから商品情報を取得
            cursor.execute("""
                SELECT asin, title_ja, description_ja, category, brand,
                       images, amazon_price_jpy, amazon_in_stock
                FROM products
                WHERE asin = ?
            """, (asin,))
            product = cursor.fetchone()

            if not product:
                print(f"[{idx}/{len(asins)}] [SKIP] {asin}: productsテーブルに存在しません")
                skipped_count += 1
                continue

            # 既存のlistingsをチェック
            cursor.execute("""
                SELECT id FROM listings
                WHERE asin = ? AND platform = ? AND account_id = ?
            """, (asin, platform, account_id))
            existing_listing = cursor.fetchone()

            if existing_listing:
                print(f"[{idx}/{len(asins)}] [SKIP] {asin}: 既にlistingsに存在します")
                skipped_count += 1
                continue

            # 販売価格を計算
            selling_price = calculate_selling_price(
                product['amazon_price_jpy'],
                markup_rate
            )

            if selling_price <= 0:
                print(f"[{idx}/{len(asins)}] [SKIP] {asin}: 価格情報がありません")
                skipped_count += 1
                continue

            # SKUを生成
            sku = generate_sku(asin, account_id)

            # スケジュール時間を計算
            slot_index = added_count % time_slots_per_day
            scheduled_time = start_date + timedelta(minutes=slot_index)

            if not dry_run:
                # listingsテーブルに追加
                cursor.execute("""
                    INSERT INTO listings (
                        asin, platform, account_id, sku, status,
                        selling_price, in_stock_quantity
                    ) VALUES (?, ?, ?, ?, 'pending', ?, 1)
                """, (
                    asin, platform, account_id, sku,
                    selling_price
                ))

                # upload_queueに追加
                cursor.execute("""
                    INSERT INTO upload_queue (
                        asin, platform, account_id, scheduled_time, status,
                        priority
                    ) VALUES (?, ?, ?, ?, 'pending', 5)
                """, (
                    asin, platform, account_id,
                    scheduled_time.isoformat()
                ))

            print(f"[{idx}/{len(asins)}] [OK] {asin}: 追加しました（価格: {selling_price}円, 予定: {scheduled_time.strftime('%m/%d %H:%M')}）")
            added_count += 1

        except Exception as e:
            print(f"[{idx}/{len(asins)}] [ERROR] {asin}: {e}", file=sys.stderr)
            failed_count += 1

    if not dry_run:
        conn.commit()

    conn.close()

    return {
        'added_count': added_count,
        'skipped_count': skipped_count,
        'failed_count': failed_count,
        'total_count': len(asins)
    }


def main():
    parser = argparse.ArgumentParser(
        description='productsテーブルから直接listingsにコピー',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
  # DRY RUNモードで確認
  python shared/utils/copy_products_to_listings.py \\
      --asin-file asins_for_account3.txt \\
      --platform base \\
      --account-id base_account_3 \\
      --dry-run

  # 本番実行
  python shared/utils/copy_products_to_listings.py \\
      --asin-file asins_for_account3.txt \\
      --platform base \\
      --account-id base_account_3

  # 掛け率を変更して実行
  python shared/utils/copy_products_to_listings.py \\
      --asin-file asins_for_account3.txt \\
      --platform base \\
      --account-id base_account_3 \\
      --markup-rate 1.5
        """
    )

    parser.add_argument(
        '--asin-file',
        type=str,
        required=True,
        help='ASINリストファイル'
    )
    parser.add_argument(
        '--platform',
        type=str,
        required=True,
        choices=['base', 'mercari', 'yahoo', 'ebay'],
        help='プラットフォーム名'
    )
    parser.add_argument(
        '--account-id',
        type=str,
        required=True,
        help='アカウントID（例: base_account_3）'
    )
    parser.add_argument(
        '--markup-rate',
        type=float,
        default=1.3,
        help='Amazon価格に対する掛け率（デフォルト: 1.3）'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='DRY RUNモード（確認のみ、実際には追加しない）'
    )
    parser.add_argument(
        '--db-path',
        type=str,
        default='inventory/data/master.db',
        help='データベースファイルパス（デフォルト: inventory/data/master.db）'
    )
    parser.add_argument(
        '--daily-limit',
        type=int,
        default=1000,
        help='1日あたりの上限（デフォルト: 1000）'
    )
    parser.add_argument(
        '--hourly-limit',
        type=int,
        default=100,
        help='1時間あたりの上限（デフォルト: 100）'
    )

    args = parser.parse_args()

    print("=" * 80)
    print("productsテーブル → listings/upload_queue コピー")
    print("=" * 80)
    print(f"\nASINファイル: {args.asin_file}")
    print(f"プラットフォーム: {args.platform}")
    print(f"アカウントID: {args.account_id}")
    print(f"掛け率: {args.markup_rate}")
    print(f"モード: {'DRY RUN' if args.dry_run else '本番実行'}")

    # 処理実行
    result = copy_products_to_listings(
        asin_file=args.asin_file,
        platform=args.platform,
        account_id=args.account_id,
        markup_rate=args.markup_rate,
        dry_run=args.dry_run,
        db_path=args.db_path,
        daily_limit=args.daily_limit,
        hourly_limit=args.hourly_limit
    )

    # サマリー
    print("\n" + "=" * 80)
    print("処理結果")
    print("=" * 80)
    print(f"追加: {result['added_count']}件")
    print(f"スキップ: {result['skipped_count']}件")
    print(f"失敗: {result['failed_count']}件")
    print(f"総計: {result['total_count']}件")
    print("=" * 80)

    if args.dry_run:
        print("\n[DRY RUN] 実際には追加していません")
    else:
        print(f"\n✅ {result['added_count']}件の商品をlistingsとupload_queueに追加しました")

    return 0


if __name__ == "__main__":
    sys.exit(main())
