#!/usr/bin/env python3
"""
バックアップとの詳細な比較分析
"""
import sqlite3

def compare_dbs():
    """2つのDBを比較して、タイトルが消失した商品を特定"""

    print("=" * 70)
    print("バックアップとの詳細比較分析")
    print("=" * 70)

    # 現在のDBからASINとtitle_jaのマッピングを取得
    current_conn = sqlite3.connect(r'C:\Users\hiroo\Documents\GitHub\ecauto\inventory\data\master.db')
    current_cur = current_conn.cursor()

    backup_conn = sqlite3.connect(r'C:\Users\hiroo\Documents\GitHub\ecauto\inventory\data\master.db.backup_20251126_issue013')
    backup_cur = backup_conn.cursor()

    # バックアップにあって現在は存在しない、またはタイトルが消えた商品を探す
    print("\n1. バックアップで有効なタイトルがあったが、現在はNULL/空になった商品:")
    print("-" * 70)

    backup_cur.execute('''
        SELECT asin, title_ja, description_ja
        FROM products
        WHERE title_ja IS NOT NULL AND title_ja != ""
        LIMIT 100
    ''')

    lost_title_count = 0
    for backup_row in backup_cur.fetchall():
        asin = backup_row[0]
        backup_title = backup_row[1]

        current_cur.execute('SELECT title_ja FROM products WHERE asin = ?', (asin,))
        current_row = current_cur.fetchone()

        if current_row:
            current_title = current_row[0]
            if not current_title or current_title == "":
                lost_title_count += 1
                if lost_title_count <= 10:  # 最初の10件のみ表示
                    print(f"  ASIN: {asin}")
                    print(f"    Backup title: {backup_title[:80]}")
                    print(f"    Current title: (NULL/empty)")
                    print()

    print(f"タイトルが消失した商品数: {lost_title_count}件（全件チェックが必要）")

    # 新規追加された商品を調べる
    print("\n2. 新規追加された商品の状況:")
    print("-" * 70)

    current_cur.execute('SELECT COUNT(*) FROM products')
    current_total = current_cur.fetchone()[0]

    backup_cur.execute('SELECT COUNT(*) FROM products')
    backup_total = backup_cur.fetchone()[0]

    print(f"現在の総商品数: {current_total}")
    print(f"バックアップ総商品数: {backup_total}")
    print(f"追加された商品数: {current_total - backup_total}")

    # 新規商品でタイトルがNULLのものを調べる
    current_cur.execute('''
        SELECT asin, title_ja, description_ja, created_at
        FROM products
        WHERE asin NOT IN (SELECT asin FROM products WHERE asin IN (
            SELECT asin FROM (SELECT * FROM products LIMIT 0)
        ))
        LIMIT 10
    ''')

    # より単純なクエリ: 最近作成された商品でタイトルがNULLのもの
    print("\n3. 最近追加されたタイトルNULL商品（サンプル）:")
    print("-" * 70)
    current_cur.execute('''
        SELECT asin, title_ja, description_ja, created_at, updated_at
        FROM products
        WHERE title_ja IS NULL OR title_ja = ""
        ORDER BY created_at DESC
        LIMIT 10
    ''')

    for row in current_cur.fetchall():
        print(f"  ASIN: {row[0]}")
        print(f"    Created: {row[3]}")
        print(f"    Updated: {row[4]}")
        print(f"    Title: {row[1]}")
        print(f"    Description: {row[2][:50] if row[2] else 'NULL'}...")
        print()

    # eBayプラットフォームの商品を調べる
    print("\n4. eBayプラットフォームに関連する出品数:")
    print("-" * 70)

    current_cur.execute('''
        SELECT COUNT(*) FROM listings WHERE platform = 'ebay'
    ''')
    ebay_listings = current_cur.fetchone()[0]
    print(f"eBayの出品数: {ebay_listings}")

    if ebay_listings > 0:
        current_cur.execute('''
            SELECT l.asin, p.title_ja, l.sku, l.status
            FROM listings l
            LEFT JOIN products p ON l.asin = p.asin
            WHERE l.platform = 'ebay'
            LIMIT 10
        ''')

        print("\neBay出品のサンプル:")
        for row in current_cur.fetchall():
            print(f"  ASIN: {row[0]}, Title: {row[1][:50] if row[1] else 'NULL'}..., SKU: {row[2]}, Status: {row[3]}")

    current_conn.close()
    backup_conn.close()

    print("\n" + "=" * 70)
    print("分析完了")
    print("=" * 70)

if __name__ == '__main__':
    compare_dbs()
