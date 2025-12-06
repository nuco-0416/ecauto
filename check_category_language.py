#!/usr/bin/env python
"""カテゴリの言語を確認するスクリプト"""
import sqlite3
from pathlib import Path

project_root = Path(__file__).parent

# master.db のカテゴリを確認
print("=" * 60)
print("master.db のカテゴリ言語チェック")
print("=" * 60)

master_db_path = project_root / 'inventory' / 'data' / 'master.db'
conn = sqlite3.connect(master_db_path)
cursor = conn.cursor()

# カテゴリがあるレコード数
cursor.execute('''
    SELECT
        COUNT(*) as total,
        COUNT(CASE WHEN category IS NOT NULL AND category != '' THEN 1 END) as with_category
    FROM products
''')
row = cursor.fetchone()
print(f"\n総商品数: {row[0]}")
print(f"カテゴリあり: {row[1]}")
if row[0] > 0:
    print(f"割合: {row[1]/row[0]*100:.1f}%")

# サンプルを表示
print("\n【カテゴリのサンプル（5件）】")
cursor.execute('''
    SELECT asin, category
    FROM products
    WHERE category IS NOT NULL AND category != ''
    LIMIT 5
''')
rows = cursor.fetchall()
if rows:
    for asin, category in rows:
        print(f"{asin}: {category[:200]}")
else:
    print("（カテゴリ情報が保存されている商品が見つかりません）")

conn.close()

# sourcing.db のカテゴリを確認
print("\n" + "=" * 60)
print("sourcing.db のカテゴリ言語チェック")
print("=" * 60)

sourcing_db_path = project_root / 'sourcing' / 'data' / 'sourcing.db'
if sourcing_db_path.exists():
    conn = sqlite3.connect(sourcing_db_path)
    cursor = conn.cursor()

    # カテゴリがあるレコード数
    cursor.execute('''
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN category IS NOT NULL AND category != '' THEN 1 END) as with_category
        FROM sourcing_candidates
    ''')
    row = cursor.fetchone()
    print(f"\n総候補数: {row[0]}")
    print(f"カテゴリあり: {row[1]}")
    if row[0] > 0:
        print(f"割合: {row[1]/row[0]*100:.1f}%")

    # サンプルを表示
    print("\n【カテゴリのサンプル（5件）】")
    cursor.execute('''
        SELECT asin, category
        FROM sourcing_candidates
        WHERE category IS NOT NULL AND category != ''
        LIMIT 5
    ''')
    rows = cursor.fetchall()
    if rows:
        for asin, category in rows:
            print(f"{asin}: {category[:200]}")
    else:
        print("（カテゴリ情報が保存されている候補が見つかりません）")

    conn.close()
else:
    print("\nsourcing.db が見つかりません")

print("\n" + "=" * 60)
