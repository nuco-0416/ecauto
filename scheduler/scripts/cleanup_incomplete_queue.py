"""
Issue #015: 価格情報が欠落しているASINをupload_queueから削除するスクリプト

価格情報（amazon_price_jpy）が欠落しているASINは、upload_daemon.pyで
「価格情報が不正です」エラーになるため、キューから削除する。

削除対象:
1. status='pending' かつ productsのamazon_price_jpyがNULL: 82件
2. status='failed' かつ error_messageが「価格情報が不正」: 10件

削除前にASINリストをファイルに保存し、後で再取得可能にする。

実行方法:
    python scheduler/scripts/cleanup_incomplete_queue.py [--dry-run]
"""

import sys
import os
from pathlib import Path
from datetime import datetime
import io

# UTF-8出力を強制（Windows環境でのcp932エラー回避）
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from inventory.core.master_db import MasterDB


def cleanup_incomplete_queue(dry_run=False):
    """
    価格情報が欠落しているASINをupload_queueから削除

    Args:
        dry_run: Trueの場合、変更を実行せずにログのみ出力

    Returns:
        dict: 削除統計
    """
    print("=" * 80)
    print("Issue #015: 不完全レコードのクリーンアップ")
    print("=" * 80)
    print()

    if dry_run:
        print("[DRY-RUN MODE] 変更は実行されません")
        print()

    db = MasterDB()

    stats = {
        'pending_no_price': 0,
        'failed_price_error': 0,
        'total_deleted': 0,
        'saved_asins': []
    }

    with db.get_connection() as conn:
        # 削除対象1: pending かつ 価格情報なし
        print("[1/4] 削除対象の特定: pending & 価格情報なし")
        print("-" * 80)

        cursor = conn.execute("""
            SELECT
                q.id,
                q.asin,
                q.account_id,
                p.amazon_price_jpy,
                p.title_ja
            FROM upload_queue q
            INNER JOIN products p ON q.asin = p.asin
            WHERE q.status = 'pending'
              AND (p.amazon_price_jpy IS NULL OR p.amazon_price_jpy = 0)
        """)
        pending_no_price = cursor.fetchall()

        stats['pending_no_price'] = len(pending_no_price)

        print(f"  pending & 価格情報なし: {stats['pending_no_price']}件")

        if stats['pending_no_price'] > 0:
            print("\n  サンプル（最初の5件）:")
            for i, (queue_id, asin, account_id, price, title) in enumerate(pending_no_price[:5], 1):
                title_short = (title[:40] + '...') if title and len(title) > 40 else (title or '<NULL>')
                print(f"    {i}. {asin} ({account_id})")
                print(f"       title: {title_short}")
                print(f"       price: {price}")

        # 削除対象2: failed かつ 「価格情報が不正です」エラー
        print("\n[2/4] 削除対象の特定: failed & 価格情報エラー")
        print("-" * 80)

        cursor = conn.execute("""
            SELECT
                q.id,
                q.asin,
                q.account_id,
                q.error_message
            FROM upload_queue q
            WHERE q.status = 'failed'
              AND q.error_message LIKE '%価格情報が不正%'
        """)
        failed_price_error = cursor.fetchall()

        stats['failed_price_error'] = len(failed_price_error)

        print(f"  failed & 価格情報エラー: {stats['failed_price_error']}件")

        if stats['failed_price_error'] > 0:
            print("\n  サンプル（最初の5件）:")
            for i, (queue_id, asin, account_id, error_msg) in enumerate(failed_price_error[:5], 1):
                print(f"    {i}. {asin} ({account_id})")
                print(f"       error: {error_msg}")

        stats['total_deleted'] = stats['pending_no_price'] + stats['failed_price_error']

        print(f"\n  合計削除対象: {stats['total_deleted']}件")
        print()

        # ASINリストを保存
        print("[3/4] ASINリストの保存")
        print("-" * 80)

        # pending ASINs
        pending_asins = [
            {
                'asin': asin,
                'account_id': account_id,
                'reason': 'no_price',
                'title': title
            }
            for _, asin, account_id, _, title in pending_no_price
        ]

        # failed ASINs
        failed_asins = [
            {
                'asin': asin,
                'account_id': account_id,
                'reason': 'price_validation_error',
                'error': error_msg
            }
            for _, asin, account_id, error_msg in failed_price_error
        ]

        stats['saved_asins'] = pending_asins + failed_asins

        # ファイルに保存
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = project_root / f'price_missing_asins_{timestamp}.txt'

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"# Issue #015: 価格情報欠落ASINリスト\n")
            f.write(f"# 削除日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# 合計: {stats['total_deleted']}件\n")
            f.write("\n")
            f.write("# pending & 価格情報なし\n")
            for item in pending_asins:
                title_short = (item['title'][:40] + '...') if item['title'] and len(item['title']) > 40 else (item['title'] or '<NULL>')
                f.write(f"{item['asin']}\t{item['account_id']}\t{item['reason']}\t{title_short}\n")
            f.write("\n")
            f.write("# failed & 価格情報エラー\n")
            for item in failed_asins:
                f.write(f"{item['asin']}\t{item['account_id']}\t{item['reason']}\t{item['error']}\n")

        print(f"  ✓ ASINリストを保存しました: {output_file}")
        print()

        if dry_run:
            print("[DRY-RUN] 以下の削除が実行されます:")
            print(f"  - pending & 価格情報なし: {stats['pending_no_price']}件")
            print(f"  - failed & 価格情報エラー: {stats['failed_price_error']}件")
            print(f"  - 合計: {stats['total_deleted']}件")
            print()
            print("[DRY-RUN] 実際の変更は行いませんでした")
            return stats

        # 削除実行
        print("[4/4] upload_queueからの削除")
        print("-" * 80)

        # pending削除
        if stats['pending_no_price'] > 0:
            pending_ids = [queue_id for queue_id, _, _, _, _ in pending_no_price]
            placeholders = ','.join('?' * len(pending_ids))
            conn.execute(f"""
                DELETE FROM upload_queue
                WHERE id IN ({placeholders})
            """, pending_ids)
            print(f"  ✓ pending & 価格情報なし: {stats['pending_no_price']}件を削除")

        # failed削除
        if stats['failed_price_error'] > 0:
            failed_ids = [queue_id for queue_id, _, _, _ in failed_price_error]
            placeholders = ','.join('?' * len(failed_ids))
            conn.execute(f"""
                DELETE FROM upload_queue
                WHERE id IN ({placeholders})
            """, failed_ids)
            print(f"  ✓ failed & 価格情報エラー: {stats['failed_price_error']}件を削除")

        conn.commit()
        print()

        # 削除後の統計
        cursor = conn.execute("""
            SELECT COUNT(*)
            FROM upload_queue
            WHERE status = 'pending'
        """)
        pending_after = cursor.fetchone()[0]

        cursor = conn.execute("""
            SELECT COUNT(*)
            FROM upload_queue
            WHERE status = 'failed'
        """)
        failed_after = cursor.fetchone()[0]

        print("=" * 80)
        print("クリーンアップ結果")
        print("=" * 80)
        print(f"  削除したレコード: {stats['total_deleted']}件")
        print(f"    - pending & 価格情報なし: {stats['pending_no_price']}件")
        print(f"    - failed & 価格情報エラー: {stats['failed_price_error']}件")
        print()
        print(f"  削除後のキュー状態:")
        print(f"    - pending: {pending_after}件")
        print(f"    - failed: {failed_after}件")
        print()
        print(f"  保存ファイル: {output_file}")
        print("=" * 80)

        return stats


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="価格情報が欠落しているASINをupload_queueから削除"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="変更を実行せずにログのみ出力"
    )

    args = parser.parse_args()

    stats = cleanup_incomplete_queue(dry_run=args.dry_run)

    if stats['total_deleted'] > 0:
        sys.exit(0)
    else:
        print("削除対象のレコードはありませんでした")
        sys.exit(0)
