"""
整合性回復スクリプト

upload_queueから、対応するlistingsが存在しないレコードを削除します。

背景:
cleanup_invalid_listings.py などでlistingsが削除された場合、
対応するupload_queueレコードが残ってしまい、デーモン実行時にエラーが発生します。
このスクリプトで整合性を回復します。

使用方法:
    # DRY RUNモードで影響範囲を確認
    python scheduler/scripts/fix_queue_listings_mismatch.py --dry-run

    # 実際に削除を実行
    python scheduler/scripts/fix_queue_listings_mismatch.py --yes
"""

import sys
from pathlib import Path
from datetime import datetime

# パスを追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from inventory.core.master_db import MasterDB


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='upload_queueとlistingsの整合性を回復'
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
    parser.add_argument(
        '--platform',
        type=str,
        help='特定のプラットフォームのみ対象（未指定の場合は全プラットフォーム）'
    )

    args = parser.parse_args()

    print("=" * 80)
    print("upload_queue と listings の整合性回復")
    print("=" * 80)
    print()
    print("対象: upload_queueに存在するが、対応するlistingsが存在しないレコード")
    print()

    db = MasterDB()

    # 不整合なレコードを特定
    with db.get_connection() as conn:
        cursor = conn.cursor()

        # プラットフォーム指定がある場合
        platform_filter = ""
        params = []
        if args.platform:
            platform_filter = "AND uq.platform = ?"
            params.append(args.platform)
            print(f"対象プラットフォーム: {args.platform}")
        else:
            print("対象プラットフォーム: 全て")

        print()

        # 不整合レコードを取得
        query = f'''
            SELECT
                uq.id,
                uq.asin,
                uq.platform,
                uq.account_id,
                uq.status as queue_status,
                uq.scheduled_time,
                uq.error_message,
                uq.created_at
            FROM upload_queue uq
            WHERE NOT EXISTS (
                SELECT 1 FROM listings l
                WHERE l.asin = uq.asin
                AND l.platform = uq.platform
                AND l.account_id = uq.account_id
            )
            {platform_filter}
            ORDER BY uq.platform, uq.account_id, uq.created_at
        '''

        cursor.execute(query, params)
        mismatched_records = cursor.fetchall()

    if not mismatched_records:
        print("✓ 整合性の問題は見つかりませんでした")
        print("=" * 80)
        return

    print(f"[警告] 不整合なレコードが見つかりました: {len(mismatched_records)}件")
    print()

    # プラットフォーム・アカウント・ステータス別の統計
    stats = {}
    for record in mismatched_records:
        platform = record['platform']
        account_id = record['account_id']
        status = record['queue_status']
        key = (platform, account_id, status)

        if key not in stats:
            stats[key] = []
        stats[key].append(record)

    print("=== 統計情報 ===")
    print()
    for (platform, account_id, status), records in sorted(stats.items()):
        print(f"Platform: {platform}, Account: {account_id}, Status: {status}")
        print(f"  件数: {len(records)}件")

        # ASINのサンプル表示（最大5件）
        sample_asins = [r['asin'] for r in records[:5]]
        print(f"  サンプルASIN: {', '.join(sample_asins)}")

        # エラーメッセージの例（あれば）
        error_samples = [r['error_message'] for r in records if r['error_message']]
        if error_samples:
            print(f"  エラー例: {error_samples[0][:100]}...")
        print()

    # 詳細表示（最初の10件）
    print("=== 詳細（最初の10件）===")
    print()
    for i, record in enumerate(mismatched_records[:10], 1):
        print(f"[{i}] ID: {record['id']}")
        print(f"    ASIN: {record['asin']}")
        print(f"    Platform: {record['platform']}")
        print(f"    Account: {record['account_id']}")
        print(f"    Queue Status: {record['queue_status']}")
        print(f"    Scheduled: {record['scheduled_time']}")
        if record['error_message']:
            error_msg = record['error_message'][:100]
            print(f"    Error: {error_msg}{'...' if len(record['error_message']) > 100 else ''}")
        print(f"    Created: {record['created_at']}")

        # このASINのlistingsを確認
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT account_id, platform, status
                FROM listings
                WHERE asin = ?
            ''', (record['asin'],))
            existing_listings = cursor.fetchall()

        if existing_listings:
            print(f"    [INFO] このASINは別のアカウント/プラットフォームでlistingsに存在:")
            for listing in existing_listings:
                print(f"           - Platform: {listing['platform']}, "
                      f"Account: {listing['account_id']}, "
                      f"Status: {listing['status']}")
        else:
            print(f"    [INFO] このASINはlistingsに全く存在しません")

        print()

    if len(mismatched_records) > 10:
        print(f"... 他 {len(mismatched_records) - 10}件")
        print()

    # サマリー
    print("=" * 80)
    print(f"削除対象の合計: {len(mismatched_records)}件")
    print("=" * 80)
    print()

    # DRY RUNチェック
    if args.dry_run:
        print("[DRY RUN] 実際には削除しません")
        print()
        print("実際に削除するには --dry-run フラグを外して再実行してください:")
        if args.platform:
            print(f"  python scheduler/scripts/fix_queue_listings_mismatch.py --platform {args.platform} --yes")
        else:
            print(f"  python scheduler/scripts/fix_queue_listings_mismatch.py --yes")
        print()
        print("=" * 80)
        return

    # 確認
    if not args.yes:
        print("[警告] この操作は元に戻せません。")
        print()
        response = input(f"{len(mismatched_records)}件のレコードをupload_queueから削除しますか？ (y/N): ")
        if response.lower() != 'y':
            print()
            print("キャンセルしました")
            print("=" * 80)
            return
    else:
        print(f"[INFO] {len(mismatched_records)}件のレコードを削除します（--yesオプション指定）")

    print()
    print("削除を実行中...")
    print()

    # 削除実行
    with db.get_connection() as conn:
        cursor = conn.cursor()

        # ログファイルを作成
        log_dir = Path(__file__).resolve().parent.parent.parent / 'logs'
        log_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = log_dir / f'queue_cleanup_{timestamp}.log'

        with open(log_file, 'w', encoding='utf-8') as f:
            f.write(f"upload_queue 整合性回復ログ\n")
            f.write(f"実行日時: {datetime.now().isoformat()}\n")
            f.write(f"削除件数: {len(mismatched_records)}件\n")
            f.write("=" * 80 + "\n\n")

            deleted_count = 0
            for record in mismatched_records:
                queue_id = record['id']
                asin = record['asin']
                platform = record['platform']
                account_id = record['account_id']

                # 削除
                cursor.execute('DELETE FROM upload_queue WHERE id = ?', (queue_id,))

                if cursor.rowcount > 0:
                    deleted_count += 1
                    log_msg = (f"[{deleted_count}] ID: {queue_id} | "
                              f"ASIN: {asin} | "
                              f"Platform: {platform} | "
                              f"Account: {account_id}")
                    f.write(log_msg + "\n")

                    if deleted_count % 100 == 0:
                        print(f"  進捗: {deleted_count}/{len(mismatched_records)}")

            f.write("\n" + "=" * 80 + "\n")
            f.write(f"削除完了: {deleted_count}件\n")

    print()
    print("=" * 80)
    print("整合性回復完了")
    print("=" * 80)
    print(f"削除件数: {deleted_count}件")
    print(f"ログファイル: {log_file}")
    print()
    print("次のステップ:")
    print("1. デーモンを再起動して動作確認")
    print("2. cleanup_invalid_listings.py の改善（upload_queueも連鎖削除）")
    print("=" * 80)


if __name__ == '__main__':
    main()
