"""
BASEにテスト登録した特定のアイテムのみを削除するスクリプト

使用方法:
    python scheduler/scripts/delete_test_items.py --dry-run  # 削除対象を確認
    python scheduler/scripts/delete_test_items.py  # 実際に削除
"""

import sys
import os
import time
import argparse
from pathlib import Path

# プロジェクトルートをPythonパスに追加
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from inventory.core.master_db import MasterDB
from platforms.base.accounts.manager import AccountManager
from platforms.base.core.api_client import BaseAPIClient


# 直近の登録でテスト削除対象となる17個のASINリスト
# （2025-11-19 15時台に登録されたもの）
TEST_ASINS = [
    'B0C6X64277',
    'B09JS7R48N',
    'B07CZKGD7X',
    'B0DX1BC3R8',
    'B00EOI6XVY',
    'B0DRCNW4GZ',
    'B071DF59C5',
    'B0D86FVG5R',
    'B00004RFRV',
    'B0FGQJ45HW',
    'B08HXN835J',
    'B00LUKK0IQ',
    'B006OHKDW8',
    'B06Y69FKT2',
    'B07YV55TNL',
    'B092DG9B3N',
    'B07JHV82ST',
]


def delete_test_items(dry_run: bool = False, skip_confirm: bool = False):
    """
    テスト用ASINのアイテムのみを削除

    Args:
        dry_run: Trueの場合は削除せずに表示のみ
    """
    print(f"\n{'='*60}")
    print(f"テストアイテム削除スクリプト")
    print(f"対象ASIN数: {len(TEST_ASINS)}")
    print(f"{'='*60}")

    # データベース接続
    db = MasterDB()

    # AccountManagerを初期化
    account_manager = AccountManager()

    # 削除対象アイテムを収集
    items_to_delete = []

    for asin in TEST_ASINS:
        # ASINに紐づくlistingを取得
        listings = db.get_listings_by_asin(asin)

        for listing in listings:
            platform = listing.get('platform')
            account_id = listing.get('account_id')
            platform_item_id = listing.get('platform_item_id')
            status = listing.get('status')

            # BASEプラットフォームで、platform_item_idが存在するもののみ
            if platform == 'base' and platform_item_id:
                items_to_delete.append({
                    'listing_id': listing['id'],
                    'platform_item_id': platform_item_id,
                    'account_id': account_id,
                    'asin': asin,
                    'sku': listing.get('sku', 'N/A'),
                    'status': status
                })

    if not items_to_delete:
        print(f"\n[INFO] 削除対象のアイテムがありません")
        return

    print(f"\n削除対象アイテム数: {len(items_to_delete)}")
    print(f"\nアイテム詳細:")
    for item in items_to_delete:
        print(f"  - ASIN: {item['asin']}, BASE ID: {item['platform_item_id']}, "
              f"Account: {item['account_id']}, Status: {item['status']}")

    if dry_run:
        print("\n[DRY RUN] 実際には削除されません")
        return

    # 削除確認
    if not skip_confirm:
        print(f"\n{'='*60}")
        print(f"警告: 上記 {len(items_to_delete)} 個のアイテムを削除します")
        print(f"{'='*60}")
        confirm = input("本当に削除しますか？ (yes/no): ")

        if confirm.lower() != 'yes':
            print("\n削除をキャンセルしました")
            return
    else:
        print(f"\n{'='*60}")
        print(f"削除を開始します: {len(items_to_delete)} 個のアイテム")
        print(f"{'='*60}")

    # アカウント別に削除処理
    items_by_account = {}
    for item in items_to_delete:
        account_id = item['account_id']
        if account_id not in items_by_account:
            items_by_account[account_id] = []
        items_by_account[account_id].append(item)

    success_count = 0
    failed_count = 0
    total_count = len(items_to_delete)

    for account_id, items in items_by_account.items():
        print(f"\n{'='*60}")
        print(f"アカウント: {account_id} ({len(items)}個)")
        print(f"{'='*60}")

        try:
            # BASE APIクライアントを作成（自動トークン更新付き）
            api_client = BaseAPIClient(
                account_id=account_id,
                account_manager=account_manager
            )
        except Exception as e:
            print(f"[ERROR] アカウント {account_id} のAPIクライアント作成失敗: {e}")
            failed_count += len(items)
            continue

        for i, item in enumerate(items, start=1):
            platform_item_id = item['platform_item_id']
            asin = item['asin']

            try:
                print(f"\n[{success_count + failed_count + 1}/{total_count}] "
                      f"削除中: ASIN={asin}, BASE ID={platform_item_id}")

                # BASE APIで削除
                result = api_client.delete_item(platform_item_id)
                print(f"  [OK] BASE APIから削除成功")

                # データベースのステータスを更新
                db.update_listing(
                    item['listing_id'],
                    status='deleted',
                    platform_item_id=None
                )
                print(f"  [OK] データベース更新完了")

                success_count += 1

                # レート制限対策
                time.sleep(0.5)

            except Exception as e:
                print(f"  [ERROR] 削除失敗: {e}")
                failed_count += 1

    # 結果サマリー
    print(f"\n{'='*60}")
    print(f"削除結果:")
    print(f"  成功: {success_count}")
    print(f"  失敗: {failed_count}")
    print(f"  合計: {total_count}")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description='テスト用にアップロードしたアイテムのみを削除')
    parser.add_argument('--dry-run', action='store_true', help='削除せずに対象アイテムを表示のみ')
    parser.add_argument('--yes', '-y', action='store_true', help='確認プロンプトをスキップ')

    args = parser.parse_args()

    if args.dry_run:
        print("\n" + "="*60)
        print("DRY RUN モード - 実際には削除されません")
        print("="*60)

    delete_test_items(dry_run=args.dry_run, skip_confirm=args.yes)

    if not args.dry_run:
        print("\n削除処理が完了しました")


if __name__ == '__main__':
    main()
