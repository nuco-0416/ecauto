#!/usr/bin/env python3
"""
upload_queueから既に出品済み（listings.status='listed'）の商品を削除するスクリプト

ISSUE #015関連: BASE API同期で登録された商品が無駄にキューに追加されている問題を解決
"""

import sys
import os
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from inventory.core.master_db import MasterDB


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='upload_queueから既に出品済みの商品を削除'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='実際には削除せず、確認のみ行う'
    )

    args = parser.parse_args()

    print("="*80)
    print("upload_queueクリーンアップ: 既出品済み商品の削除")
    print("="*80)
    print()

    if args.dry_run:
        print("【DRY RUN モード】実際の削除は行いません")
        print()

    master_db = MasterDB()

    with master_db.get_connection() as conn:
        cursor = conn.cursor()

        # 1. 削除対象を特定（既にlisted状態の商品）
        query_select = """
        SELECT q.id, q.asin, q.platform, q.account_id, q.status as queue_status,
               l.status as listing_status, l.platform_item_id,
               p.title_ja
        FROM upload_queue q
        INNER JOIN listings l ON q.asin = l.asin AND q.platform = l.platform AND q.account_id = l.account_id
        LEFT JOIN products p ON q.asin = p.asin
        WHERE l.status = 'listed'
          AND q.status IN ('pending', 'failed')
        ORDER BY q.id
        """

        cursor.execute(query_select)
        to_delete = cursor.fetchall()

        if not to_delete:
            print("✓ 削除対象の商品はありません")
            return

        print(f"削除対象: {len(to_delete)}件")
        print()

        # 統計
        stats = {
            'pending': 0,
            'failed': 0,
            'title_ja_null': 0
        }

        for row in to_delete:
            if row['queue_status'] == 'pending':
                stats['pending'] += 1
            elif row['queue_status'] == 'failed':
                stats['failed'] += 1

            if not row['title_ja']:
                stats['title_ja_null'] += 1

        print("統計情報:")
        print(f"  - pending: {stats['pending']}件（これから処理される予定だったもの）")
        print(f"  - failed: {stats['failed']}件（既に失敗したもの）")
        print(f"  - title_ja NULL: {stats['title_ja_null']}件（バリデーションエラーの原因）")
        print()

        # サンプル表示（最初の5件）
        print("サンプル（最初の5件）:")
        for i, row in enumerate(to_delete[:5], 1):
            print(f"  {i}. Queue ID: {row['id']}")
            print(f"     ASIN: {row['asin']}")
            print(f"     Queue Status: {row['queue_status']}")
            print(f"     Listing: {row['listing_status']} (platform_item_id: {row['platform_item_id']})")
            print(f"     title_ja: {'あり' if row['title_ja'] else 'NULL'}")
            print()

        if args.dry_run:
            print("【DRY RUN】実際の削除をスキップします")
            return

        # 確認プロンプト
        response = input(f"{len(to_delete)}件のレコードを削除しますか？ (yes/no): ")
        if response.lower() != 'yes':
            print("キャンセルしました")
            return

        print()
        print("="*80)
        print("削除開始")
        print("="*80)

        # 削除実行
        queue_ids = [row['id'] for row in to_delete]

        cursor.execute(f"""
            DELETE FROM upload_queue
            WHERE id IN ({','.join('?' * len(queue_ids))})
        """, queue_ids)

        deleted_count = cursor.rowcount

        print()
        print("="*80)
        print("削除完了")
        print("="*80)
        print(f"削除件数: {deleted_count}件")
        print()
        print("効果:")
        print(f"  - pending {stats['pending']}件の無駄な処理を回避")
        print(f"  - failed {stats['failed']}件のエラーレコードをクリーンアップ")
        print(f"  - title_ja NULL {stats['title_ja_null']}件のバリデーションエラーを予防")


if __name__ == '__main__':
    main()
