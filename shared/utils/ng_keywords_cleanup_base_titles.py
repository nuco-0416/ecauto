"""
BASE既存出品 タイトルNGキーワードクリーンアップスクリプト

BASEに出品済みの商品のタイトルからNGキーワードを削除して更新する

# スキャンのみ
/home/nuc_o/github/ecauto/venv/bin/python shared/utils/ng_keywords_cleanup_base_titles.py --scan-only

# dry-run（全アカウント）
/home/nuc_o/github/ecauto/venv/bin/python shared/utils/ng_keywords_cleanup_base_titles.py --dry-run

# 特定アカウントのみ実行
/home/nuc_o/github/ecauto/venv/bin/python shared/utils/ng_keywords_cleanup_base_titles.py --execute --account base_account_1
"""

import sys
import argparse
import time
from pathlib import Path
from datetime import datetime

# プロジェクトルートをパスに追加（shared/utils/ から3階層上）
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from inventory.core.master_db import MasterDB
from common.ng_keyword_filter import NGKeywordFilter
from platforms.base.core.api_client import BaseAPIClient
from platforms.base.accounts.manager import AccountManager


def find_listings_with_ng_titles(db: MasterDB, ng_filter: NGKeywordFilter, account_id: str = None) -> list:
    """
    NGキーワードを含むタイトルの出品を検索

    Args:
        db: MasterDBインスタンス
        ng_filter: NGKeywordFilterインスタンス
        account_id: アカウントIDでフィルタ（オプション）

    Returns:
        list: NGキーワードを含む出品のリスト
    """
    listings_with_ng = []

    with db.get_connection() as conn:
        cursor = conn.cursor()

        # BASEの出品済み商品を取得
        query = '''
            SELECT l.id, l.asin, l.platform_item_id, l.account_id, l.sku,
                   p.title_ja, p.title_en, p.description_ja
            FROM listings l
            JOIN products p ON l.asin = p.asin
            WHERE l.platform = 'base'
              AND l.status = 'listed'
              AND l.platform_item_id IS NOT NULL
        '''
        params = []

        if account_id:
            query += ' AND l.account_id = ?'
            params.append(account_id)

        query += ' ORDER BY l.updated_at DESC'

        cursor.execute(query, params)

        for row in cursor.fetchall():
            listing = dict(row)
            asin = listing['asin']
            title_ja = listing.get('title_ja') or ''

            # NGキーワードフィルターを適用
            filtered_title = ng_filter.filter_title(title_ja)

            # タイトルが変更される場合
            if title_ja != filtered_title:
                listings_with_ng.append({
                    'listing_id': listing['id'],
                    'asin': asin,
                    'platform_item_id': listing['platform_item_id'],
                    'account_id': listing['account_id'],
                    'sku': listing['sku'],
                    'original_title': title_ja,
                    'cleaned_title': filtered_title
                })

    return listings_with_ng


def update_base_titles(
    db: MasterDB,
    ng_filter: NGKeywordFilter,
    account_manager: AccountManager,
    account_id: str = None,
    dry_run: bool = True,
    rate_limit: float = 2.0,
    max_items: int = None
) -> dict:
    """
    BASE商品のタイトルを更新

    Args:
        db: MasterDBインスタンス
        ng_filter: NGKeywordFilterインスタンス
        account_manager: AccountManagerインスタンス
        account_id: アカウントIDでフィルタ（オプション）
        dry_run: Trueの場合は実際には更新しない
        rate_limit: API呼び出し間隔（秒）
        max_items: 処理件数上限（オプション）

    Returns:
        dict: 処理結果の統計
    """
    stats = {
        'scanned': 0,
        'found': 0,
        'updated': 0,
        'skipped': 0,
        'errors': 0,
        'details': []
    }

    # NGキーワードを含む出品を検索
    listings = find_listings_with_ng_titles(db, ng_filter, account_id)
    stats['scanned'] = len(listings)
    stats['found'] = len(listings)

    if max_items:
        listings = listings[:max_items]

    # アカウント別にグループ化
    by_account = {}
    for listing in listings:
        acc_id = listing['account_id']
        if acc_id not in by_account:
            by_account[acc_id] = []
        by_account[acc_id].append(listing)

    # 各アカウントの商品を更新
    for acc_id, account_listings in by_account.items():
        print(f"\n{'='*60}")
        print(f"アカウント: {acc_id} ({len(account_listings)}件)")
        print(f"{'='*60}")

        if not dry_run:
            try:
                client = BaseAPIClient(account_id=acc_id, account_manager=account_manager)
            except Exception as e:
                print(f"  [ERROR] APIクライアント初期化失敗: {e}")
                stats['errors'] += len(account_listings)
                continue

        for i, listing in enumerate(account_listings):
            asin = listing['asin']
            item_id = listing['platform_item_id']
            original = listing['original_title']
            cleaned = listing['cleaned_title']

            print(f"\n[{i+1}/{len(account_listings)}] ASIN: {asin}, Item ID: {item_id}")
            print(f"  変更前: {original[:60]}{'...' if len(original) > 60 else ''}")
            print(f"  変更後: {cleaned[:60]}{'...' if len(cleaned) > 60 else ''}")

            detail = {
                'asin': asin,
                'item_id': item_id,
                'account_id': acc_id,
                'original': original,
                'cleaned': cleaned,
                'status': 'pending'
            }

            if dry_run:
                detail['status'] = 'dry_run'
                stats['skipped'] += 1
            else:
                try:
                    # BASE APIで更新
                    result = client.update_item(item_id, {'title': cleaned})
                    detail['status'] = 'success'
                    stats['updated'] += 1
                    print(f"  → 更新成功")

                    # レート制限
                    time.sleep(rate_limit)

                except Exception as e:
                    detail['status'] = 'error'
                    detail['error'] = str(e)
                    stats['errors'] += 1
                    print(f"  → エラー: {e}")

            stats['details'].append(detail)

    return stats


def main():
    parser = argparse.ArgumentParser(description='BASE既存出品タイトルNGキーワードクリーンアップ')
    parser.add_argument('--dry-run', action='store_true', default=True,
                       help='実際には更新せず、変更内容のみ表示（デフォルト）')
    parser.add_argument('--execute', action='store_true',
                       help='実際に更新を実行')
    parser.add_argument('--account', type=str,
                       help='特定のアカウントのみ処理')
    parser.add_argument('--max-items', type=int,
                       help='処理件数上限')
    parser.add_argument('--rate-limit', type=float, default=2.0,
                       help='API呼び出し間隔（秒）（デフォルト: 2.0）')
    parser.add_argument('--scan-only', action='store_true',
                       help='NGキーワードを含む出品のスキャンのみ')

    args = parser.parse_args()

    # dry_runフラグの決定
    dry_run = not args.execute

    print("=" * 70)
    print("BASE既存出品 タイトルNGキーワードクリーンアップ")
    print("=" * 70)
    print(f"実行モード: {'DRY RUN（実際には更新しません）' if dry_run else '実行モード（BASEを更新します）'}")
    if args.account:
        print(f"対象アカウント: {args.account}")
    if args.max_items:
        print(f"処理件数上限: {args.max_items}")
    print()

    # 初期化
    db = MasterDB()
    ng_file = project_root / 'config' / 'ng_keywords.json'
    ng_filter = NGKeywordFilter(str(ng_file))
    account_manager = AccountManager()

    if args.scan_only:
        # スキャンのみ
        print("NGキーワードを含む出品をスキャン中...")
        listings = find_listings_with_ng_titles(db, ng_filter, args.account)

        print(f"\n検出件数: {len(listings)}件")

        # アカウント別にカウント
        by_account = {}
        for listing in listings:
            acc_id = listing['account_id']
            if acc_id not in by_account:
                by_account[acc_id] = 0
            by_account[acc_id] += 1

        print("\nアカウント別内訳:")
        for acc_id, count in by_account.items():
            print(f"  {acc_id}: {count}件")

        print("\n詳細（最初の20件）:")
        for i, listing in enumerate(listings[:20]):
            print(f"\n[{i+1}] ASIN: {listing['asin']}")
            print(f"    Account: {listing['account_id']}")
            print(f"    Item ID: {listing['platform_item_id']}")
            print(f"    変更前: {listing['original_title'][:60]}...")
            print(f"    変更後: {listing['cleaned_title'][:60]}...")

        if len(listings) > 20:
            print(f"\n... 他 {len(listings) - 20}件")

    else:
        # 更新実行
        stats = update_base_titles(
            db=db,
            ng_filter=ng_filter,
            account_manager=account_manager,
            account_id=args.account,
            dry_run=dry_run,
            rate_limit=args.rate_limit,
            max_items=args.max_items
        )

        print(f"\n{'='*70}")
        print("処理結果サマリー")
        print(f"{'='*70}")
        print(f"スキャン件数: {stats['scanned']}")
        print(f"NGキーワード検出: {stats['found']}")
        if dry_run:
            print(f"スキップ（dry run）: {stats['skipped']}")
        else:
            print(f"更新成功: {stats['updated']}")
            print(f"エラー: {stats['errors']}")

        if dry_run and stats['found'] > 0:
            print(f"\n{'='*70}")
            print("実行するには --execute オプションを使用してください")
            print(f"{'='*70}")


if __name__ == '__main__':
    main()
