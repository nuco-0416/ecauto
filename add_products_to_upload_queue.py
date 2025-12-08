"""
既存商品をlistingsとupload_queueに追加するスクリプト

既にproductsテーブルに存在する商品を、指定したアカウントのlistingsとupload_queueに追加します。
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime
import time

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

from inventory.core.master_db import MasterDB
from inventory.core.listing_manager import ListingManager
from common.pricing import PriceCalculator
from scheduler.queue_manager import UploadQueueManager
from shared.utils.sku_generator import generate_sku


def read_asin_list(file_path: str) -> list:
    """
    ASINリストファイルを読み込み

    Args:
        file_path: ASINリストファイルのパス（改行区切り）

    Returns:
        list: ASINのリスト
    """
    asins = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            asin = line.strip()
            if asin and not asin.startswith('#'):  # コメント行を除外
                asins.append(asin)
    return asins


def main():
    parser = argparse.ArgumentParser(
        description='既存商品をlistingsとupload_queueに追加'
    )
    parser.add_argument(
        '--asin-file',
        type=str,
        required=True,
        help='ASINリストファイル（改行区切り）'
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
        required=True,
        help='アカウントID（例: base_account_2）'
    )
    parser.add_argument(
        '--yes', '-y',
        action='store_true',
        help='確認をスキップして自動実行'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='DRY RUNモード（実際の追加は行わない）'
    )

    args = parser.parse_args()

    print("=" * 70)
    print("既存商品をlistings + upload_queueに追加")
    print("=" * 70)

    # ASINリストを読み込み
    print(f"\nASINリストを読み込み中: {args.asin_file}")
    asins = read_asin_list(args.asin_file)
    print(f"読み込み完了: {len(asins)}件")

    # マスタDBに接続
    db = MasterDB()
    listing_manager = ListingManager(master_db=db)
    price_calculator = PriceCalculator()
    queue_manager = UploadQueueManager()

    # 設定を表示
    print(f"\nプラットフォーム: {args.platform}")
    print(f"アカウントID: {args.account_id}")
    print(f"モード: {'DRY RUN' if args.dry_run else '本番実行'}")

    # 確認
    if not args.yes and not args.dry_run:
        response = input(f"\n{len(asins)}件の商品をlistings + upload_queueに追加しますか？ (y/N): ")
        if response.lower() != 'y':
            print("キャンセルしました")
            return
    else:
        print(f"\n{len(asins)}件の商品を処理します")

    # 統計情報
    success_listings = 0
    success_queue = 0
    skip_count = 0
    error_count = 0

    print("\n処理中...")

    for i, asin in enumerate(asins, 1):
        try:
            # productsテーブルから商品情報を取得
            product = db.get_product(asin)
            if not product:
                print(f"[{i}/{len(asins)}] スキップ: {asin} (productsテーブルに存在しない)")
                skip_count += 1
                continue

            # 既にlistingsに存在するかチェック
            existing_listings = db.get_listings_by_asin(asin)
            already_listed = any(
                listing['platform'] == args.platform and listing['account_id'] == args.account_id
                for listing in existing_listings
            )

            if already_listed:
                print(f"[{i}/{len(asins)}] スキップ: {asin} (既にlistingsに存在)")
                skip_count += 1
                continue

            # DRY RUNモードの場合はここでスキップ
            if args.dry_run:
                print(f"[{i}/{len(asins)}] [DRY RUN] 追加対象: {asin} - {product.get('title_ja', '')[:40]}")
                success_listings += 1
                success_queue += 1
                continue

            # 売価を計算
            amazon_price = product.get('amazon_price_jpy')
            if amazon_price:
                selling_price = price_calculator.calculate_selling_price(
                    amazon_price=amazon_price,
                    platform=args.platform
                )
            else:
                selling_price = None

            # SKU生成
            sku = generate_sku(
                platform=args.platform,
                asin=asin,
                timestamp=datetime.now()
            )

            # listingsテーブルに追加
            listing_id = listing_manager.add_listing(
                asin=asin,
                platform=args.platform,
                account_id=args.account_id,
                sku=sku,
                selling_price=selling_price,
                currency='JPY',
                in_stock_quantity=1,
                status='pending',
                visibility='public'
            )

            if listing_id:
                success_listings += 1

                # upload_queueに追加
                queue_added = queue_manager.add_to_queue(
                    asin=asin,
                    platform=args.platform,
                    account_id=args.account_id,
                    priority=UploadQueueManager.PRIORITY_NORMAL
                )

                if queue_added:
                    success_queue += 1
                    print(f"[{i}/{len(asins)}] 追加成功: {asin} - {product.get('title_ja', '')[:40]}")
                else:
                    print(f"[{i}/{len(asins)}] 部分成功: {asin} (listingsのみ、queue追加失敗)")

        except Exception as e:
            error_count += 1
            print(f"[{i}/{len(asins)}] エラー: {asin} - {e}")

    # 結果表示
    print("\n" + "=" * 70)
    print("処理完了")
    print("=" * 70)
    print(f"listings追加成功: {success_listings}件")
    print(f"queue追加成功: {success_queue}件")
    print(f"スキップ: {skip_count}件")
    print(f"エラー: {error_count}件")
    print(f"合計: {len(asins)}件")
    print("=" * 70)

    if not args.dry_run:
        print("\n次のステップ:")
        print("デーモンが自動的にアップロードを実行します（6AM-11PM営業時間内）")
        print("進捗確認:")
        print(f"  python scheduler/scripts/check_queue.py --platform {args.platform}")


if __name__ == '__main__':
    main()
