"""アクティブアカウントフィルタリングの検証スクリプト"""
import sqlite3
from pathlib import Path

# データベースパス
project_root = Path(__file__).resolve().parent
db_path = project_root / 'inventory' / 'data' / 'master.db'

# テストしたASINs
test_asins = ['B0BXWF22P9', 'B09Q1MR3D2', 'B0BLV2CZ8M']

print("=" * 70)
print("アクティブアカウントフィルタリング検証")
print("=" * 70)
print(f"\nテスト対象ASIN: {', '.join(test_asins)}")
print(f"期待されるアカウント: base_account_2 のみ\n")

# データベース接続
with sqlite3.connect(db_path) as conn:
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # listingsテーブルを確認
    print("[1] listingsテーブルの確認")
    print("-" * 70)
    cursor.execute("""
        SELECT asin, account_id, sku, selling_price, status
        FROM listings
        WHERE asin IN (?, ?, ?)
        ORDER BY id DESC
    """, test_asins)

    listings = cursor.fetchall()

    if not listings:
        print("  [WARNING] 登録されたlistingが見つかりません")
    else:
        accounts_found = set()
        for listing in listings:
            print(f"  [OK] ASIN: {listing['asin']}")
            print(f"       アカウント: {listing['account_id']}")
            print(f"       SKU: {listing['sku']}")
            print(f"       売価: {listing['selling_price']}円")
            print(f"       ステータス: {listing['status']}")
            print()
            accounts_found.add(listing['account_id'])

        print(f"  検出されたアカウント: {', '.join(accounts_found)}")

        # base_account_1が含まれていないか確認
        if 'base_account_1' in accounts_found:
            print("  [ERROR] 非アクティブなbase_account_1が検出されました！")
        else:
            print("  [SUCCESS] 非アクティブなbase_account_1は除外されています")

    # upload_queueを確認
    print("\n[2] upload_queueの確認")
    print("-" * 70)
    cursor.execute("""
        SELECT asin, account_id, priority, status
        FROM upload_queue
        WHERE asin IN (?, ?, ?)
        ORDER BY id DESC
    """, test_asins)

    queue_items = cursor.fetchall()

    if not queue_items:
        print("  [WARNING] キューアイテムが見つかりません")
    else:
        queue_accounts = set()
        for item in queue_items:
            print(f"  [OK] ASIN: {item['asin']}")
            print(f"       アカウント: {item['account_id']}")
            print(f"       優先度: {item['priority']}")
            print(f"       ステータス: {item['status']}")
            print()
            queue_accounts.add(item['account_id'])

        print(f"  検出されたアカウント: {', '.join(queue_accounts)}")

        if 'base_account_1' in queue_accounts:
            print("  [ERROR] 非アクティブなbase_account_1が検出されました！")
        else:
            print("  [SUCCESS] 非アクティブなbase_account_1は除外されています")

print("\n" + "=" * 70)
print("検証完了")
print("=" * 70)
