#!/usr/bin/env python3
"""
11月26日に追加された商品を調査
"""
import sqlite3
import json
from pathlib import Path

def investigate():
    conn = sqlite3.connect(r'C:\Users\hiroo\Documents\GitHub\ecauto\inventory\data\master.db')
    cur = conn.cursor()

    print("=" * 70)
    print("11月26日追加商品の調査")
    print("=" * 70)

    # 11月26日に作成された商品を調べる
    cur.execute('''
        SELECT COUNT(*) FROM products
        WHERE created_at LIKE '2025-11-26%'
    ''')
    count_nov26 = cur.fetchone()[0]
    print(f"\n2025-11-26に作成された商品数: {count_nov26}")

    # 11月26日作成でタイトルがNULLの商品
    cur.execute('''
        SELECT COUNT(*) FROM products
        WHERE created_at LIKE '2025-11-26%'
        AND (title_ja IS NULL OR title_ja = '')
    ''')
    null_title_nov26 = cur.fetchone()[0]
    print(f"  うちタイトルがNULLの商品: {null_title_nov26}")

    # サンプル表示
    print("\n11月26日追加商品のサンプル（タイトルNULL）:")
    print("-" * 70)
    cur.execute('''
        SELECT asin, title_ja, description_ja, amazon_price_jpy, created_at
        FROM products
        WHERE created_at LIKE '2025-11-26%'
        AND (title_ja IS NULL OR title_ja = '')
        LIMIT 10
    ''')

    for row in cur.fetchall():
        asin = row[0]
        # キャッシュファイルが存在するかチェック
        cache_path = Path(rf'C:\Users\hiroo\Documents\GitHub\ecauto\inventory\data\cache\amazon_products\{asin}.json')
        cache_exists = "YES" if cache_path.exists() else "NO"

        print(f"  ASIN: {asin} [Cache: {cache_exists}]")
        print(f"    Created: {row[4]}")
        print(f"    Title: {row[1]}")
        print(f"    Price: {row[3]}")

        # キャッシュファイルを確認
        if cache_path.exists():
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                    # タイトル情報の有無を確認
                    item_name = cache_data.get('ItemName')
                    print(f"    Cache ItemName: {item_name[:50] if item_name else 'NULL'}...")
            except:
                print(f"    Cache: (読み込みエラー)")

    # どこから追加されたか（listingsテーブルを確認）
    print("\n\n11月26日追加商品の出品情報:")
    print("-" * 70)
    cur.execute('''
        SELECT p.asin, l.platform, l.account_id, l.sku, l.status, p.created_at
        FROM products p
        LEFT JOIN listings l ON p.asin = l.asin
        WHERE p.created_at LIKE '2025-11-26%'
        LIMIT 20
    ''')

    platform_counts = {}
    for row in cur.fetchall():
        platform = row[1] if row[1] else '(no listing)'
        platform_counts[platform] = platform_counts.get(platform, 0) + 1

        if len(platform_counts) <= 20:  # 最初の20件のみ表示
            print(f"  ASIN: {row[0]}, Platform: {platform}, Account: {row[2]}, Status: {row[4]}")

    print("\n\nプラットフォーム別集計:")
    print("-" * 70)
    for platform, count in platform_counts.items():
        print(f"  {platform}: {count}件")

    conn.close()

if __name__ == '__main__':
    investigate()
