"""
不要なlistingsレコードを削除するスクリプト（緊急時のメンテナンス用）

【重要】このスクリプトは通常実行不要です。
バグや不正データが混入した場合の緊急対応用として使用してください。

以下の条件に該当するレコードを削除：
- 販売価格未設定（selling_price IS NULL OR selling_price = 0）
- テストデータ（asin LIKE 'B0TEST%'）
- 商品マスタにAmazon価格情報がない

改善点（2025-11-22）:
- listingsを削除する際、対応するupload_queueも連鎖削除するようにしました
- これにより、データ整合性を保つことができます
"""

import sys
from pathlib import Path

# パスを追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from inventory.core.master_db import MasterDB


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='不要なlistingsレコードを削除'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='実際には削除せず、削除対象のみ表示'
    )
    parser.add_argument(
        '--yes', '-y',
        action='store_true',
        help='確認をスキップして自動実行'
    )

    args = parser.parse_args()

    print("=" * 70)
    print("不要なlistingsレコードの削除")
    print("=" * 70)

    db = MasterDB()

    with db.get_connection() as conn:
        cursor = conn.cursor()

        # 1. 販売価格未設定
        print("\n=== 1. 販売価格未設定のレコード ===")
        cursor.execute('''
            SELECT COUNT(*) as count
            FROM listings
            WHERE status = 'pending'
            AND (selling_price IS NULL OR selling_price = 0)
        ''')
        no_price_count = cursor.fetchone()['count']
        print(f"該当件数: {no_price_count}件")

        if no_price_count > 0:
            cursor.execute('''
                SELECT id, asin, platform, account_id, selling_price
                FROM listings
                WHERE status = 'pending'
                AND (selling_price IS NULL OR selling_price = 0)
                LIMIT 5
            ''')
            print("サンプル（最初の5件）:")
            for row in cursor.fetchall():
                print(f"  ID: {row['id']} | ASIN: {row['asin']} | Platform: {row['platform']} | "
                      f"Account: {row['account_id']} | Price: {row['selling_price']}")

        # 2. テストデータ
        print("\n=== 2. テストデータ（B0TEST*） ===")
        cursor.execute('''
            SELECT COUNT(*) as count
            FROM listings
            WHERE asin LIKE 'B0TEST%'
        ''')
        test_count = cursor.fetchone()['count']
        print(f"該当件数: {test_count}件")

        if test_count > 0:
            cursor.execute('''
                SELECT id, asin, platform, account_id, status
                FROM listings
                WHERE asin LIKE 'B0TEST%'
                LIMIT 10
            ''')
            print("サンプル（最初の10件）:")
            for row in cursor.fetchall():
                print(f"  ID: {row['id']} | ASIN: {row['asin']} | Platform: {row['platform']} | "
                      f"Account: {row['account_id']} | Status: {row['status']}")

        # 3. Amazon価格未取得（商品マスタにはあるが価格情報がない）
        print("\n=== 3. Amazon価格未取得のレコード ===")
        cursor.execute('''
            SELECT COUNT(*) as count
            FROM listings l
            INNER JOIN products p ON l.asin = p.asin
            WHERE l.status = 'pending'
            AND (p.amazon_price_jpy IS NULL OR p.amazon_price_jpy = 0)
        ''')
        no_amazon_price_count = cursor.fetchone()['count']
        print(f"該当件数: {no_amazon_price_count}件")

        if no_amazon_price_count > 0:
            cursor.execute('''
                SELECT l.id, l.asin, l.platform, l.account_id, l.selling_price, p.amazon_price_jpy
                FROM listings l
                INNER JOIN products p ON l.asin = p.asin
                WHERE l.status = 'pending'
                AND (p.amazon_price_jpy IS NULL OR p.amazon_price_jpy = 0)
                LIMIT 5
            ''')
            print("サンプル（最初の5件）:")
            for row in cursor.fetchall():
                print(f"  ID: {row['id']} | ASIN: {row['asin']} | Platform: {row['platform']} | "
                      f"Account: {row['account_id']} | Selling: {row['selling_price']} | "
                      f"Amazon: {row['amazon_price_jpy']}")

        # 合計
        total_to_delete = no_price_count + test_count + no_amazon_price_count
        print(f"\n削除対象の合計: {total_to_delete}件")
        print(f"  - 販売価格未設定: {no_price_count}件")
        print(f"  - テストデータ: {test_count}件")
        print(f"  - Amazon価格未取得: {no_amazon_price_count}件")

        if total_to_delete == 0:
            print("\n削除対象のレコードはありません")
            return

        # 確認
        if args.dry_run:
            print(f"\n[DRY RUN] 実際には削除しません")
            return

        if not args.yes:
            response = input(f"\n{total_to_delete}件のレコードを削除しますか？ (y/N): ")
            if response.lower() != 'y':
                print("キャンセルしました")
                return
        else:
            print(f"\n{total_to_delete}件のレコードを削除します（--yesオプション指定）")

        # 削除実行
        print("\n削除中...")
        print()

        # ===============================================================
        # フェーズ1: upload_queueから対応するレコードを削除（整合性維持）
        # ===============================================================
        print("=== フェーズ1: upload_queue から対応するレコードを削除 ===")
        print()

        # 1-1. 販売価格未設定のlistingsに対応するupload_queueを削除
        cursor.execute('''
            DELETE FROM upload_queue
            WHERE (asin, platform, account_id) IN (
                SELECT asin, platform, account_id
                FROM listings
                WHERE status = 'pending'
                AND (selling_price IS NULL OR selling_price = 0)
            )
        ''')
        deleted_queue_no_price = cursor.rowcount
        print(f"  販売価格未設定（upload_queue）: {deleted_queue_no_price}件削除")

        # 1-2. テストデータのupload_queueを削除（全プラットフォーム対象）
        cursor.execute('''
            DELETE FROM upload_queue
            WHERE asin LIKE 'B0TEST%'
        ''')
        deleted_queue_test = cursor.rowcount
        print(f"  テストデータ（upload_queue）: {deleted_queue_test}件削除")

        # 1-3. Amazon価格未取得のlistingsに対応するupload_queueを削除
        cursor.execute('''
            DELETE FROM upload_queue
            WHERE (asin, platform, account_id) IN (
                SELECT l.asin, l.platform, l.account_id
                FROM listings l
                INNER JOIN products p ON l.asin = p.asin
                WHERE l.status = 'pending'
                AND (p.amazon_price_jpy IS NULL OR p.amazon_price_jpy = 0)
            )
        ''')
        deleted_queue_no_amazon = cursor.rowcount
        print(f"  Amazon価格未取得（upload_queue）: {deleted_queue_no_amazon}件削除")

        total_queue_deleted = deleted_queue_no_price + deleted_queue_test + deleted_queue_no_amazon
        print()
        print(f"upload_queue 削除合計: {total_queue_deleted}件")
        print()

        # ===============================================================
        # フェーズ2: listingsから不要なレコードを削除
        # ===============================================================
        print("=== フェーズ2: listings から不要なレコードを削除 ===")
        print()

        # 2-1. 販売価格未設定
        cursor.execute('''
            DELETE FROM listings
            WHERE status = 'pending'
            AND (selling_price IS NULL OR selling_price = 0)
        ''')
        deleted_no_price = cursor.rowcount
        print(f"  販売価格未設定（listings）: {deleted_no_price}件削除")

        # 2-2. テストデータ
        cursor.execute('''
            DELETE FROM listings
            WHERE asin LIKE 'B0TEST%'
        ''')
        deleted_test = cursor.rowcount
        print(f"  テストデータ（listings）: {deleted_test}件削除")

        # 2-3. Amazon価格未取得
        cursor.execute('''
            DELETE FROM listings
            WHERE id IN (
                SELECT l.id
                FROM listings l
                INNER JOIN products p ON l.asin = p.asin
                WHERE l.status = 'pending'
                AND (p.amazon_price_jpy IS NULL OR p.amazon_price_jpy = 0)
            )
        ''')
        deleted_no_amazon = cursor.rowcount
        print(f"  Amazon価格未取得（listings）: {deleted_no_amazon}件削除")

        total_listings_deleted = deleted_no_price + deleted_test + deleted_no_amazon
        print()
        print(f"listings 削除合計: {total_listings_deleted}件")
        print()

        # ===============================================================
        # フェーズ3: テストデータの商品マスタも削除
        # ===============================================================
        print("=== フェーズ3: テストデータの商品マスタを削除 ===")
        print()

        cursor.execute('''
            DELETE FROM products
            WHERE asin LIKE 'B0TEST%'
        ''')
        deleted_test_products = cursor.rowcount
        print(f"  テストデータ（products）: {deleted_test_products}件削除")

        print("\n" + "=" * 70)
        print("削除完了")
        print("=" * 70)
        print(f"upload_queue 削除: {total_queue_deleted}件")
        print(f"listings 削除: {total_listings_deleted}件")
        print(f"products 削除: {deleted_test_products}件")
        print()
        print("[重要] upload_queueとlistingsの整合性を保つため、")
        print("listingsを削除する前にupload_queueからも対応するレコードを削除しました。")
        print("=" * 70)


if __name__ == '__main__':
    main()
