"""
Issue #013: 欠損したlistingsを補完するスクリプト

upload_queueに存在するが、対応するlistingsが存在しないASINについて、
listingsレコードを作成します。

実行方法:
    python inventory/scripts/backfill_missing_listings.py [--dry-run]
"""

import sys
import os
from pathlib import Path
from datetime import datetime
import io

# UTF-8出力を強制（Windows環境でのcp932エラー回避）
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from inventory.core.master_db import MasterDB
from inventory.core.product_registrar import ProductRegistrar


def backfill_missing_listings(dry_run=False):
    """
    欠損したlistingsを補完

    Args:
        dry_run: Trueの場合、変更を実行せずにログのみ出力

    Returns:
        dict: 結果の統計情報
    """
    print("=" * 70)
    print("Issue #013: 欠損したlistingsの補完スクリプト")
    print("=" * 70)
    print()

    if dry_run:
        print("[DRY-RUN MODE] 変更は実行されません")
        print()

    db = MasterDB()
    registrar = ProductRegistrar(master_db=db)

    stats = {
        'total_missing': 0,
        'account_1_missing': 0,
        'account_2_missing': 0,
        'created': 0,
        'skipped_no_product': 0,
        'errors': 0,
        'error_details': []
    }

    with db.get_connection() as conn:
        # パターン1: account_1でlistingsが欠損しているASIN
        print("[1/3] account_1で欠損しているlistingsを検索中...")
        cursor = conn.execute("""
            SELECT DISTINCT q.asin, q.account_id, q.platform
            FROM upload_queue q
            LEFT JOIN listings l ON q.asin = l.asin
                AND q.account_id = l.account_id
                AND q.platform = l.platform
            WHERE q.platform = 'base'
              AND q.account_id = 'base_account_1'
              AND l.asin IS NULL
            ORDER BY q.asin
        """)
        missing_account_1 = cursor.fetchall()
        stats['account_1_missing'] = len(missing_account_1)
        print(f"  account_1で欠損: {len(missing_account_1)}件")
        print()

        # パターン2: account_2でlistingsが欠損しているASIN
        print("[2/3] account_2で欠損しているlistingsを検索中...")
        cursor = conn.execute("""
            SELECT DISTINCT q.asin, q.account_id, q.platform
            FROM upload_queue q
            LEFT JOIN listings l ON q.asin = l.asin
                AND q.account_id = l.account_id
                AND q.platform = l.platform
            WHERE q.platform = 'base'
              AND q.account_id = 'base_account_2'
              AND l.asin IS NULL
            ORDER BY q.asin
        """)
        missing_account_2 = cursor.fetchall()
        stats['account_2_missing'] = len(missing_account_2)
        print(f"  account_2で欠損: {len(missing_account_2)}件")
        print()

        # 全ての欠損ASINを統合
        all_missing = missing_account_1 + missing_account_2
        stats['total_missing'] = len(all_missing)

        print(f"合計欠損: {stats['total_missing']}件")
        print()

        if dry_run:
            print("[DRY-RUN] 以下のlistingsが作成されます:")
            print(f"  account_1: {stats['account_1_missing']}件")
            print(f"  account_2: {stats['account_2_missing']}件")
            print()

            # サンプル表示（最初の10件）
            print("サンプル（最初の10件）:")
            for i, (asin, account_id, platform) in enumerate(all_missing[:10]):
                # productsから商品情報を取得
                product = db.get_product(asin)
                if product:
                    print(f"  {i+1}. {asin} ({account_id})")
                    print(f"     Amazon価格: {product.get('amazon_price_jpy', 'N/A')}円")
                else:
                    print(f"  {i+1}. {asin} ({account_id}) - ⚠️ productsに存在しません")
            print()

            print("[DRY-RUN] 実際の変更は行いませんでした")
            return stats

        # 補完処理
        print("[3/3] listingsを補完中...")
        print()

        for i, (asin, account_id, platform) in enumerate(all_missing, 1):
            # 進捗表示（100件ごと）
            if i % 100 == 0 or i == 1:
                print(f"  進捗: {i}/{stats['total_missing']}件 処理中...")

            try:
                # productsから商品情報を取得
                product = db.get_product(asin)

                if not product:
                    stats['skipped_no_product'] += 1
                    if len(stats['error_details']) < 10:
                        stats['error_details'].append(
                            f"  {asin} ({account_id}): productsに存在しません"
                        )
                    continue

                # listingsを作成（queueには追加しない）
                result = registrar.register_product(
                    asin=asin,
                    platform=platform,
                    account_id=account_id,
                    product_data={
                        'amazon_price_jpy': product.get('amazon_price_jpy'),
                        'amazon_url': product.get('amazon_url'),
                        'title': product.get('title'),
                        'image_url': product.get('image_url'),
                        'category': product.get('category'),
                        'brand': product.get('brand'),
                    },
                    add_to_queue=False  # queueには追加しない（既に存在するため）
                )

                if result.get('listing_created'):
                    stats['created'] += 1
                    if i <= 10:  # 最初の10件は詳細を表示
                        print(f"    ✓ {asin} ({account_id}): SKU={result.get('sku')}")

            except Exception as e:
                stats['errors'] += 1
                error_msg = f"  {asin} ({account_id}): {str(e)}"
                if len(stats['error_details']) < 10:
                    stats['error_details'].append(error_msg)
                if i <= 10:  # 最初の10件はエラーも表示
                    print(f"    ❌ {error_msg}")

        print()
        print("=" * 70)
        print("補完結果:")
        print("=" * 70)
        print(f"  合計欠損: {stats['total_missing']}件")
        print(f"    - account_1: {stats['account_1_missing']}件")
        print(f"    - account_2: {stats['account_2_missing']}件")
        print()
        print(f"  作成成功: {stats['created']}件")
        print(f"  スキップ（productsなし）: {stats['skipped_no_product']}件")
        print(f"  エラー: {stats['errors']}件")
        print()

        if stats['error_details']:
            print("エラー詳細（最大10件）:")
            for error in stats['error_details']:
                print(error)
            print()

        if stats['created'] > 0:
            print("✓ listingsの補完が完了しました")
        elif stats['total_missing'] == 0:
            print("✓ 欠損しているlistingsはありません")
        else:
            print("⚠️ listingsを作成できませんでした")

        print("=" * 70)

        return stats


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="欠損したlistingsを補完"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="変更を実行せずにログのみ出力"
    )

    args = parser.parse_args()

    stats = backfill_missing_listings(dry_run=args.dry_run)

    # 成功条件: エラーがないか、作成成功数がエラー数より多い
    if stats['errors'] == 0 or stats['created'] > stats['errors']:
        sys.exit(0)
    else:
        sys.exit(1)
