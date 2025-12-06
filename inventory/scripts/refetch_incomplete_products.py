#!/usr/bin/env python3
"""
不完全な商品データ（title_ja or amazon_price_jpyがNULL）をSP-APIで再取得して更新するスクリプト

使用方法:
    python inventory/scripts/refetch_incomplete_products.py --dry-run  # 確認のみ
    python inventory/scripts/refetch_incomplete_products.py            # 実際に更新
"""

import sys
import os
import argparse
from datetime import datetime

# プロジェクトルートをパスに追加
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, project_root)

from inventory.core.master_db import MasterDB
from integrations.amazon.sp_api_client import AmazonSPAPIClient
from integrations.amazon.config import SP_API_CREDENTIALS


def fetch_incomplete_products(master_db):
    """不完全なproductsレコードを取得"""
    with master_db.get_connection() as conn:
        cursor = conn.cursor()

        # title_ja または amazon_price_jpy がNULLのレコードを取得
        query = """
        SELECT asin, title_ja, amazon_price_jpy, created_at
        FROM products
        WHERE title_ja IS NULL OR amazon_price_jpy IS NULL
        ORDER BY created_at DESC
        """

        cursor.execute(query)
        rows = cursor.fetchall()

        incomplete_products = []
        for row in rows:
            incomplete_products.append({
                'asin': row[0],
                'title_ja': row[1],
                'amazon_price_jpy': row[2],
                'created_at': row[3]
            })

        cursor.close()
        return incomplete_products


def update_product(master_db, asin, product_data):
    """productsテーブルを更新"""
    with master_db.get_connection() as conn:
        cursor = conn.cursor()

        # 更新するフィールドのみを抽出（Noneでないもの）
        update_fields = []
        update_values = []

        if product_data.get('title_ja'):
            update_fields.append('title_ja = ?')
            update_values.append(product_data['title_ja'])

        if product_data.get('title_en'):
            update_fields.append('title_en = ?')
            update_values.append(product_data['title_en'])

        if product_data.get('description_ja'):
            update_fields.append('description_ja = ?')
            update_values.append(product_data['description_ja'])

        if product_data.get('description_en'):
            update_fields.append('description_en = ?')
            update_values.append(product_data['description_en'])

        if product_data.get('category'):
            update_fields.append('category = ?')
            update_values.append(product_data['category'])

        if product_data.get('brand'):
            update_fields.append('brand = ?')
            update_values.append(product_data['brand'])

        if product_data.get('images'):
            update_fields.append('images = ?')
            update_values.append(str(product_data['images']))

        if product_data.get('amazon_price_jpy'):
            update_fields.append('amazon_price_jpy = ?')
            update_values.append(product_data['amazon_price_jpy'])

        if 'amazon_in_stock' in product_data:
            update_fields.append('amazon_in_stock = ?')
            update_values.append(product_data['amazon_in_stock'])

        if not update_fields:
            return False

        # 更新日時を追加
        update_fields.append('updated_at = ?')
        update_values.append(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

        # WHERE句用にASINを追加
        update_values.append(asin)

        query = f"""
        UPDATE products
        SET {', '.join(update_fields)}
        WHERE asin = ?
        """

        cursor.execute(query, update_values)
        cursor.close()

        return True


def update_listing_price(master_db, asin, amazon_price_jpy, markup_rate=1.3):
    """listingsテーブルの価格を更新"""
    with master_db.get_connection() as conn:
        cursor = conn.cursor()

        selling_price = int(amazon_price_jpy * markup_rate)

        query = """
        UPDATE listings
        SET selling_price = ?, updated_at = ?
        WHERE asin = ? AND selling_price IS NULL
        """

        cursor.execute(query, (
            selling_price,
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            asin
        ))

        updated_count = cursor.rowcount
        cursor.close()

        return updated_count


def main():
    parser = argparse.ArgumentParser(
        description='不完全な商品データをSP-APIで再取得して更新'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='実際には更新せず、確認のみ行う'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='処理するASIN数の上限（テスト用）'
    )

    args = parser.parse_args()

    print("="*80)
    print("不完全商品データ再取得スクリプト")
    print("="*80)
    print()

    if args.dry_run:
        print("【DRY RUN モード】実際の更新は行いません")
        print()

    # MasterDBとSP-APIクライアントを初期化
    master_db = MasterDB()
    sp_client = AmazonSPAPIClient(SP_API_CREDENTIALS)

    # 不完全なproductsを取得
    print("不完全なproductsレコードを検索中...")
    incomplete_products = fetch_incomplete_products(master_db)

    print(f"不完全なproductsレコード: {len(incomplete_products)}件")
    print()

    if len(incomplete_products) == 0:
        print("✓ 不完全なデータはありません")
        return

    # 統計情報
    stats = {
        'total': len(incomplete_products),
        'title_ja_null': sum(1 for p in incomplete_products if not p['title_ja']),
        'price_null': sum(1 for p in incomplete_products if not p['amazon_price_jpy']),
        'both_null': sum(1 for p in incomplete_products if not p['title_ja'] and not p['amazon_price_jpy'])
    }

    print("統計情報:")
    print(f"  - title_ja NULL: {stats['title_ja_null']}件")
    print(f"  - amazon_price_jpy NULL: {stats['price_null']}件")
    print(f"  - 両方 NULL: {stats['both_null']}件")
    print()

    # サンプル表示（最初の5件）
    print("サンプルASIN（最初の5件）:")
    for i, product in enumerate(incomplete_products[:5]):
        print(f"  {i+1}. {product['asin']} - title: {bool(product['title_ja'])}, price: {bool(product['amazon_price_jpy'])}")
    print()

    if args.dry_run:
        print("【DRY RUN】実際の更新をスキップします")
        return

    # 確認プロンプト
    response = input(f"{len(incomplete_products)}件のASINを再取得しますか？ (yes/no): ")
    if response.lower() != 'yes':
        print("キャンセルしました")
        return

    print()
    print("="*80)
    print("再取得開始")
    print("="*80)

    # 処理するASIN数の制限
    process_limit = args.limit if args.limit else len(incomplete_products)

    # 統計カウンター
    success_count = 0
    failed_count = 0
    skipped_count = 0

    for i, product in enumerate(incomplete_products[:process_limit]):
        asin = product['asin']
        print(f"\n[{i+1}/{process_limit}] {asin}")

        try:
            # SP-APIで商品情報を再取得
            product_data = sp_client.get_product_info(asin)

            if not product_data:
                print(f"  ✗ 商品情報取得失敗")
                failed_count += 1
                continue

            # 価格情報を追加
            price_data = sp_client.get_product_price(asin)
            if price_data:
                product_data.update({
                    'amazon_price_jpy': price_data.get('price'),
                    'amazon_in_stock': price_data.get('in_stock', False)
                })

            # バリデーション
            if not product_data.get('title_ja') or not product_data.get('amazon_price_jpy'):
                print(f"  ✗ データ不完全: title_ja={bool(product_data.get('title_ja'))}, price={bool(product_data.get('amazon_price_jpy'))}")
                failed_count += 1
                continue

            # productsテーブルを更新
            updated = update_product(master_db, asin, product_data)

            if updated:
                print(f"  ✓ products更新成功")

                # listingsテーブルの価格も更新
                if product_data.get('amazon_price_jpy'):
                    listings_updated = update_listing_price(
                        master_db,
                        asin,
                        product_data['amazon_price_jpy']
                    )
                    if listings_updated > 0:
                        print(f"  ✓ listings価格更新成功 ({listings_updated}件)")

                success_count += 1
            else:
                print(f"  - 更新スキップ（既に完全）")
                skipped_count += 1

        except Exception as e:
            print(f"  ✗ エラー: {e}")
            failed_count += 1

    # 最終結果
    print()
    print("="*80)
    print("再取得完了")
    print("="*80)
    print(f"成功: {success_count}件")
    print(f"失敗: {failed_count}件")
    print(f"スキップ: {skipped_count}件")
    print(f"合計: {success_count + failed_count + skipped_count}件")


if __name__ == '__main__':
    main()
