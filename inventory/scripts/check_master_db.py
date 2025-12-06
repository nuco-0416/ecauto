"""
Master DBの登録状況を確認するスクリプト
"""

import sys
from pathlib import Path

# パスを追加
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from inventory.core.master_db import MasterDB
from inventory.core.cache_manager import AmazonProductCache


def check_master_db():
    """Master DBの登録状況を確認"""
    print("\n" + "=" * 70)
    print("Master DB 登録状況")
    print("=" * 70)

    db = MasterDB()
    cache = AmazonProductCache()

    with db.get_connection() as conn:
        cursor = conn.cursor()

        # 1. 商品マスタ（products）
        cursor.execute("SELECT COUNT(*) as count FROM products")
        products_count = cursor.fetchone()['count']
        print(f"\n【商品マスタ（products）】")
        print(f"  登録商品数: {products_count:,}件")

        # Amazon価格・在庫情報がある商品
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN amazon_price_jpy IS NOT NULL THEN 1 ELSE 0 END) as with_price,
                SUM(CASE WHEN amazon_in_stock = 1 THEN 1 ELSE 0 END) as in_stock,
                SUM(CASE WHEN amazon_in_stock = 0 THEN 1 ELSE 0 END) as out_of_stock
            FROM products
        """)
        row = cursor.fetchone()
        print(f"  Amazon価格情報あり: {row['with_price']:,}件")
        print(f"  在庫あり: {row['in_stock']:,}件")
        print(f"  在庫切れ: {row['out_of_stock']:,}件")

        # 2. 出品情報（listings）
        print(f"\n【出品情報（listings）】")
        cursor.execute("SELECT COUNT(*) as count FROM listings")
        listings_count = cursor.fetchone()['count']
        print(f"  総出品数: {listings_count:,}件")

        # ステータス別
        cursor.execute("""
            SELECT status, COUNT(*) as count
            FROM listings
            GROUP BY status
            ORDER BY count DESC
        """)
        print(f"\n  ステータス別:")
        for row in cursor.fetchall():
            print(f"    {row['status']}: {row['count']:,}件")

        # プラットフォーム別
        cursor.execute("""
            SELECT platform, COUNT(*) as count
            FROM listings
            GROUP BY platform
            ORDER BY count DESC
        """)
        print(f"\n  プラットフォーム別:")
        for row in cursor.fetchall():
            print(f"    {row['platform']}: {row['count']:,}件")

        # Visibility別（出品済みのみ）
        cursor.execute("""
            SELECT visibility, COUNT(*) as count
            FROM listings
            WHERE status = 'listed'
            GROUP BY visibility
        """)
        print(f"\n  公開状態（出品済みのみ）:")
        for row in cursor.fetchall():
            print(f"    {row['visibility']}: {row['count']:,}件")

        # 3. 出品キュー（upload_queue）
        print(f"\n【出品キュー（upload_queue）】")
        cursor.execute("SELECT COUNT(*) as count FROM upload_queue")
        queue_count = cursor.fetchone()['count']
        print(f"  総キュー数: {queue_count:,}件")

        # ステータス別
        cursor.execute("""
            SELECT status, COUNT(*) as count
            FROM upload_queue
            GROUP BY status
            ORDER BY count DESC
        """)
        print(f"\n  ステータス別:")
        for row in cursor.fetchall():
            print(f"    {row['status']}: {row['count']:,}件")

        # 4. キャッシュ状況
        print(f"\n【キャッシュ状況】")
        cached_asins = cache.list_cached_asins()
        print(f"  キャッシュ済みASIN数: {len(cached_asins):,}件")

        # キャッシュが欠損しているASINを確認（出品済みのみ）
        cursor.execute("""
            SELECT DISTINCT asin
            FROM listings
            WHERE status = 'listed'
        """)
        listed_asins = [row['asin'] for row in cursor.fetchall()]

        missing_cache = [asin for asin in listed_asins if asin not in cached_asins]
        print(f"  キャッシュ欠損（出品済み）: {len(missing_cache):,}件")

        # キャッシュ統計
        cache_stats = cache.get_stats()
        print(f"\n  キャッシュヒット率: {cache_stats['hit_rate']}")
        print(f"  最終一括更新: {cache_stats['last_bulk_update'] or 'なし'}")

        # 5. アカウント設定
        print(f"\n【アカウント設定（account_configs）】")
        cursor.execute("SELECT COUNT(*) as count FROM account_configs")
        accounts_count = cursor.fetchone()['count']
        print(f"  登録アカウント数: {accounts_count}件")

        cursor.execute("""
            SELECT id, platform, name, active, daily_upload_limit
            FROM account_configs
            ORDER BY platform, id
        """)
        print(f"\n  アカウント一覧:")
        for row in cursor.fetchall():
            status = "有効" if row['active'] else "無効"
            print(f"    {row['id']} ({row['platform']}) - {row['name']} [{status}]")

        # 6. キャッシュ欠損の詳細（最大20件表示）
        if missing_cache:
            print(f"\n【キャッシュ欠損ASIN（最大20件表示）】")
            for asin in missing_cache[:20]:
                print(f"  {asin}")
            if len(missing_cache) > 20:
                print(f"  ... 他 {len(missing_cache) - 20}件")

    print("\n" + "=" * 70)
    print()


if __name__ == '__main__':
    check_master_db()
