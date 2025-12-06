#!/usr/bin/env python3
"""
description_jaがNULLの商品をSP-APIで再取得して更新するスクリプト

使用方法:
    python inventory/scripts/refetch_missing_descriptions.py --dry-run  # 確認のみ
    python inventory/scripts/refetch_missing_descriptions.py            # 実際に更新
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


def fetch_missing_description_products(master_db, since_date=None):
    """description_jaがNULLのproductsレコードを取得"""
    with master_db.get_connection() as conn:
        cursor = conn.cursor()

        query = """
        SELECT asin, title_ja, created_at
        FROM products
        WHERE description_ja IS NULL
        """

        params = []
        if since_date:
            query += " AND created_at >= ?"
            params.append(since_date)

        query += " ORDER BY created_at DESC"

        cursor.execute(query, params)
        rows = cursor.fetchall()

        products = []
        for row in rows:
            products.append({
                'asin': row[0],
                'title_ja': row[1],
                'created_at': row[2]
            })

        cursor.close()
        return products


def update_description(master_db, asin, description_ja):
    """productsテーブルのdescription_jaを更新"""
    with master_db.get_connection() as conn:
        cursor = conn.cursor()

        query = """
        UPDATE products
        SET description_ja = ?, updated_at = ?
        WHERE asin = ?
        """

        cursor.execute(query, (
            description_ja,
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            asin
        ))

        cursor.close()
        return True


def main():
    parser = argparse.ArgumentParser(
        description='description_jaがNULLの商品をSP-APIで再取得して更新'
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
    parser.add_argument(
        '--since',
        type=str,
        default=None,
        help='指定した日付以降の商品のみ対象（例: 2025-11-27）'
    )

    args = parser.parse_args()

    print("="*80)
    print("商品説明（description_ja）再取得スクリプト")
    print("="*80)
    print()

    if args.dry_run:
        print("【DRY RUN モード】実際の更新は行いません")
        print()

    # MasterDBとSP-APIクライアントを初期化
    master_db = MasterDB()
    sp_client = AmazonSPAPIClient(SP_API_CREDENTIALS)

    # description_jaがNULLのproductsを取得
    print("description_jaがNULLのproductsレコードを検索中...")
    products = fetch_missing_description_products(master_db, since_date=args.since)

    print(f"description_jaがNULL: {len(products)}件")
    if args.since:
        print(f"  (対象期間: {args.since}以降)")
    print()

    if len(products) == 0:
        print("[OK] 対象データはありません")
        return

    # サンプル表示（最初の5件）
    print("サンプルASIN（最初の5件）:")
    for i, product in enumerate(products[:5]):
        title = product['title_ja'][:50] if product['title_ja'] else 'N/A'
        print(f"  {i+1}. {product['asin']} - title: {title}...")
    print()

    if args.dry_run:
        print("【DRY RUN】実際の更新をスキップします")
        return

    # 確認プロンプト
    response = input(f"{len(products)}件のASINを再取得しますか？ (yes/no): ")
    if response.lower() != 'yes':
        print("キャンセルしました")
        return

    print()
    print("="*80)
    print("再取得開始")
    print("="*80)

    # 処理するASIN数の制限
    process_limit = args.limit if args.limit else len(products)

    # 統計カウンター
    success_count = 0
    failed_count = 0
    already_fixed_count = 0

    for i, product in enumerate(products[:process_limit]):
        asin = product['asin']
        print(f"\n[{i+1}/{process_limit}] {asin}")

        try:
            # SP-APIで商品情報を再取得
            product_data = sp_client.get_product_info(asin)

            if not product_data:
                print(f"  [FAIL] 商品情報取得失敗")
                failed_count += 1
                continue

            # description_jaが取得できたかチェック
            description_ja = product_data.get('description_ja')

            if description_ja:
                # description_jaを更新
                update_description(master_db, asin, description_ja)
                print(f"  [OK] description_ja更新成功 ({len(description_ja)}文字)")
                success_count += 1
            else:
                print(f"  [SKIP] description_ja取得できず（bullet_pointsなし）")
                already_fixed_count += 1

        except Exception as e:
            print(f"  [ERROR] {e}")
            failed_count += 1

    # 最終結果
    print()
    print("="*80)
    print("再取得完了")
    print("="*80)
    print(f"成功: {success_count}件")
    print(f"失敗: {failed_count}件")
    print(f"取得できず: {already_fixed_count}件")
    print(f"合計: {success_count + failed_count + already_fixed_count}件")
    print()

    if already_fixed_count > 0:
        print("注意: 一部の商品はbullet_pointsがないため、description_jaを生成できませんでした。")
        print("      これらの商品は、修正済みのSP-APIクライアントではtitle_jaが商品説明として使用されます。")


if __name__ == '__main__':
    main()
