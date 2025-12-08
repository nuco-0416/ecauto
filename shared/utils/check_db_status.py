"""
データベース状態確認スクリプト

商品追加作業前にDBの現在状態を確認するためのツールスクリプト
playbooks専用のヘルパースクリプトとして permanent に配置
"""

import sys
import sqlite3
from pathlib import Path
from datetime import datetime

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

def main():
    # データベースパス
    master_db_path = project_root / 'inventory' / 'data' / 'master.db'
    sourcing_db_path = project_root / 'sourcing' / 'data' / 'sourcing.db'

    print("=" * 80)
    print(f"データベース状態確認レポート - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print()

    # Master DB の確認
    print("[1] Master DB (inventory/data/master.db)")
    print("-" * 80)

    with sqlite3.connect(master_db_path) as conn:
        cursor = conn.cursor()

        # products テーブルの総件数
        cursor.execute("SELECT COUNT(*) FROM products")
        products_count = cursor.fetchone()[0]
        print(f"[OK] products テーブルの総件数: {products_count:,} 件")
        print()

        # listings テーブルの内訳
        print("[OK] listings テーブルの内訳:")
        cursor.execute("""
            SELECT platform, account_id, COUNT(*) as count
            FROM listings
            GROUP BY platform, account_id
            ORDER BY platform, account_id
        """)
        listings_breakdown = cursor.fetchall()
        total_listings = 0
        for platform, account_id, count in listings_breakdown:
            print(f"  - {platform} / {account_id}: {count:,} 件")
            total_listings += count
        print(f"  合計: {total_listings:,} 件")
        print()

        # BASE アカウント2・3の既存出品数
        print("[OK] BASE アカウント2・3の既存出品数:")
        cursor.execute("""
            SELECT account_id, COUNT(*) as count
            FROM listings
            WHERE platform = 'base' AND account_id IN ('base_account_2', 'base_account_3')
            GROUP BY account_id
        """)
        base_accounts = cursor.fetchall()
        for account_id, count in base_accounts:
            print(f"  - {account_id}: {count:,} 件")
        print()

        # upload_queue のステータス別件数
        print("[OK] upload_queue のステータス別件数:")
        cursor.execute("""
            SELECT status, COUNT(*) as count
            FROM upload_queue
            GROUP BY status
            ORDER BY status
        """)
        queue_status = cursor.fetchall()
        total_queue = 0
        for status, count in queue_status:
            print(f"  - {status}: {count:,} 件")
            total_queue += count
        print(f"  合計: {total_queue:,} 件")
        print()

    # Sourcing DB の確認
    print("[2] Sourcing DB (sourcing/data/sourcing.db)")
    print("-" * 80)

    if sourcing_db_path.exists():
        with sqlite3.connect(sourcing_db_path) as conn:
            cursor = conn.cursor()

            # sourcing_candidates の総件数と未連携件数
            cursor.execute("SELECT COUNT(*) FROM sourcing_candidates")
            total_candidates = cursor.fetchone()[0]
            print(f"[OK] sourcing_candidates の総件数: {total_candidates:,} 件")

            cursor.execute("SELECT COUNT(*) FROM sourcing_candidates WHERE imported_at IS NULL")
            unexported_candidates = cursor.fetchone()[0]
            print(f"[OK] sourcing_candidates の未連携件数: {unexported_candidates:,} 件")

            exported_candidates = total_candidates - unexported_candidates
            print(f"[OK] 連携済み件数: {exported_candidates:,} 件")
            print()
    else:
        print("[NG] Sourcing DB が見つかりません")
        print()

    # 利用可能な候補商品の確認（master.dbに未登録の候補）
    print("[3] 利用可能な候補商品（master.dbに未登録）")
    print("-" * 80)

    if sourcing_db_path.exists():
        with sqlite3.connect(sourcing_db_path) as sourcing_conn, \
             sqlite3.connect(master_db_path) as master_conn:

            sourcing_cursor = sourcing_conn.cursor()
            master_cursor = master_conn.cursor()

            # master.dbに登録済みのASINリストを取得
            master_cursor.execute("SELECT asin FROM products")
            registered_asins = set(row[0] for row in master_cursor.fetchall())

            # sourcing_candidatesの全ASINを取得
            sourcing_cursor.execute("SELECT asin FROM sourcing_candidates WHERE imported_at IS NULL")
            candidate_asins = [row[0] for row in sourcing_cursor.fetchall()]

            # 未登録の候補数をカウント
            available_candidates = [asin for asin in candidate_asins if asin not in registered_asins]

            print(f"[OK] Sourcing候補から利用可能な商品数: {len(available_candidates):,} 件")
            print()
    else:
        print("[NG] Sourcing DB が見つからないため、スキップします")
        print()

    print("=" * 80)
    print("確認完了")
    print("=" * 80)

if __name__ == '__main__':
    main()
