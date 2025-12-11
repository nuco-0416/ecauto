"""
BASE既存出品 タイトルNGキーワードクリーンアップスクリプト

BASEに出品済みの商品のタイトルからNGキーワードを削除して更新する
※ デフォルトではBASE APIから直接タイトルを取得してチェックするため、
   マスターDBのクリーンアップ状況に依存しない

# スキャンのみ（BASE APIから直接取得 - 推奨）
/home/nuc_o/github/ecauto/venv/bin/python shared/utils/ng_keywords_cleanup_base_titles.py --scan-only

# dry-run（全アカウント）
/home/nuc_o/github/ecauto/venv/bin/python shared/utils/ng_keywords_cleanup_base_titles.py --dry-run

# 特定アカウントのみ実行
/home/nuc_o/github/ecauto/venv/bin/python shared/utils/ng_keywords_cleanup_base_titles.py --execute --account base_account_1

# DBベースでスキャン（旧方式）
/home/nuc_o/github/ecauto/venv/bin/python shared/utils/ng_keywords_cleanup_base_titles.py --scan-only --use-db
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


def fetch_all_items_from_base(client: BaseAPIClient, rate_limit: float = 1.0) -> list:
    """
    BASE APIから全商品を取得

    Args:
        client: BaseAPIClientインスタンス
        rate_limit: API呼び出し間隔（秒）

    Returns:
        list: 商品リスト
    """
    all_items = []
    offset = 0
    limit = 100

    while True:
        try:
            response = client.get_items(limit=limit, offset=offset)
            items = response.get('items', [])

            if not items:
                break

            all_items.extend(items)
            print(f"  取得中... {len(all_items)}件")

            if len(items) < limit:
                break

            offset += limit
            time.sleep(rate_limit)

        except Exception as e:
            print(f"  [ERROR] 商品一覧取得エラー (offset={offset}): {e}")
            break

    return all_items


def find_items_with_ng_titles_from_api(
    ng_filter: NGKeywordFilter,
    account_manager: AccountManager,
    account_id: str = None,
    rate_limit: float = 1.0
) -> dict:
    """
    BASE APIから直接商品を取得し、NGキーワードを含むタイトルを検索

    Args:
        ng_filter: NGKeywordFilterインスタンス
        account_manager: AccountManagerインスタンス
        account_id: アカウントIDでフィルタ（オプション）
        rate_limit: API呼び出し間隔（秒）

    Returns:
        dict: アカウントごとのNGキーワードを含む商品リスト
    """
    results = {}

    # 対象アカウントを取得
    if account_id:
        accounts = [account_id]
    else:
        accounts = account_manager.get_all_account_ids()

    for acc_id in accounts:
        print(f"\n[{acc_id}] BASE APIから商品を取得中...")

        try:
            client = BaseAPIClient(account_id=acc_id, account_manager=account_manager)
            items = fetch_all_items_from_base(client, rate_limit)
            print(f"  取得完了: {len(items)}件")

            items_with_ng = []
            for item in items:
                item_id = item.get('item_id')
                title = item.get('title', '')

                # NGキーワードフィルターを適用
                filtered_title = ng_filter.filter_title(title)

                # タイトルが変更される場合
                if title != filtered_title:
                    items_with_ng.append({
                        'item_id': item_id,
                        'original_title': title,
                        'cleaned_title': filtered_title,
                        'account_id': acc_id,
                        'identifier': item.get('identifier', ''),
                        'price': item.get('price', 0),
                        'stock': item.get('stock', 0)
                    })

            results[acc_id] = items_with_ng
            print(f"  NGキーワード検出: {len(items_with_ng)}件")

        except Exception as e:
            print(f"  [ERROR] APIクライアント初期化失敗: {e}")
            results[acc_id] = []

    return results


def find_listings_with_ng_titles(db: MasterDB, ng_filter: NGKeywordFilter, account_id: str = None) -> list:
    """
    【旧方式】DBベースでNGキーワードを含むタイトルの出品を検索
    ※ マスターDBがクリーンアップ済みの場合は0件になる可能性あり

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


def update_base_titles_from_api(
    ng_filter: NGKeywordFilter,
    account_manager: AccountManager,
    account_id: str = None,
    dry_run: bool = True,
    rate_limit: float = 2.0,
    max_items: int = None
) -> dict:
    """
    BASE APIから取得した商品のタイトルを更新

    Args:
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

    # BASE APIから直接NGキーワードを含む商品を検索
    items_by_account = find_items_with_ng_titles_from_api(
        ng_filter, account_manager, account_id, rate_limit
    )

    # 統計を集計
    for acc_id, items in items_by_account.items():
        stats['scanned'] += len(items)
        stats['found'] += len(items)

    # max_items制限を適用
    total_processed = 0

    # 各アカウントの商品を更新
    for acc_id, items in items_by_account.items():
        if not items:
            continue

        print(f"\n{'='*60}")
        print(f"アカウント: {acc_id} ({len(items)}件)")
        print(f"{'='*60}")

        if not dry_run:
            try:
                client = BaseAPIClient(account_id=acc_id, account_manager=account_manager)
            except Exception as e:
                print(f"  [ERROR] APIクライアント初期化失敗: {e}")
                stats['errors'] += len(items)
                continue

        for i, item in enumerate(items):
            if max_items and total_processed >= max_items:
                print(f"\n処理件数上限 ({max_items}) に達しました")
                break

            item_id = item['item_id']
            original = item['original_title']
            cleaned = item['cleaned_title']
            identifier = item.get('identifier', '')

            print(f"\n[{i+1}/{len(items)}] Item ID: {item_id}")
            if identifier:
                print(f"  SKU: {identifier}")
            print(f"  変更前: {original[:60]}{'...' if len(original) > 60 else ''}")
            print(f"  変更後: {cleaned[:60]}{'...' if len(cleaned) > 60 else ''}")

            detail = {
                'item_id': item_id,
                'account_id': acc_id,
                'identifier': identifier,
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
            total_processed += 1

    return stats


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
    【旧方式】DBベースでBASE商品のタイトルを更新
    ※ マスターDBがクリーンアップ済みの場合は0件になる可能性あり

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
                       help='NGキーワードを含む出品のスキャンのみ（BASE APIから直接取得）')
    parser.add_argument('--use-db', action='store_true',
                       help='DBベースでスキャン（旧方式、マスターDBがクリーンアップ済みだと0件になる可能性あり）')

    args = parser.parse_args()

    # dry_runフラグの決定
    dry_run = not args.execute

    print("=" * 70)
    print("BASE既存出品 タイトルNGキーワードクリーンアップ")
    print("=" * 70)
    print(f"実行モード: {'DRY RUN（実際には更新しません）' if dry_run else '実行モード（BASEを更新します）'}")
    print(f"スキャン方式: {'DBベース（旧方式）' if args.use_db else 'BASE APIから直接取得（推奨）'}")
    if args.account:
        print(f"対象アカウント: {args.account}")
    if args.max_items:
        print(f"処理件数上限: {args.max_items}")
    print()

    # 初期化
    ng_file = project_root / 'config' / 'ng_keywords.json'
    ng_filter = NGKeywordFilter(str(ng_file))
    account_manager = AccountManager()

    if args.use_db:
        # 旧方式: DBベース
        db = MasterDB()

        if args.scan_only:
            # スキャンのみ
            print("NGキーワードを含む出品をスキャン中（DBベース）...")
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

    else:
        # 新方式: BASE APIから直接取得（デフォルト）
        if args.scan_only:
            # スキャンのみ
            print("BASE APIからNGキーワードを含む商品をスキャン中...")
            items_by_account = find_items_with_ng_titles_from_api(
                ng_filter, account_manager, args.account, args.rate_limit
            )

            # 集計
            total = sum(len(items) for items in items_by_account.values())
            print(f"\n{'='*70}")
            print(f"検出件数合計: {total}件")
            print(f"{'='*70}")

            print("\nアカウント別内訳:")
            for acc_id, items in items_by_account.items():
                print(f"  {acc_id}: {len(items)}件")

            # 詳細表示
            all_items = []
            for acc_id, items in items_by_account.items():
                for item in items:
                    item['account_id'] = acc_id
                    all_items.append(item)

            print("\n詳細（最初の20件）:")
            for i, item in enumerate(all_items[:20]):
                print(f"\n[{i+1}] Item ID: {item['item_id']}")
                print(f"    Account: {item['account_id']}")
                if item.get('identifier'):
                    print(f"    SKU: {item['identifier']}")
                orig = item['original_title']
                clean = item['cleaned_title']
                print(f"    変更前: {orig[:60]}{'...' if len(orig) > 60 else ''}")
                print(f"    変更後: {clean[:60]}{'...' if len(clean) > 60 else ''}")

            if len(all_items) > 20:
                print(f"\n... 他 {len(all_items) - 20}件")

        else:
            # 更新実行
            stats = update_base_titles_from_api(
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
