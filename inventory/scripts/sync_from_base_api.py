"""
BASE API → ローカルDB マージスクリプト

BASE APIから既存商品を取得し、ローカルDBに統合します。
- 正規化処理（platform, account_id）
- 既存商品の更新（platform_item_id, SKU, status, price, stock, visibility）
- 新規商品の追加
"""

import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
import re
from datetime import datetime
import json

# パスを追加
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / 'platforms' / 'base'))

from core.api_client import BaseAPIClient
from accounts.manager import AccountManager
from inventory.core.master_db import MasterDB


def extract_asin_from_identifier(identifier: str) -> Optional[str]:
    """SKU/identifierからASINを抽出"""
    if not identifier:
        return None

    # パターン1: base-{ASIN}-{timestamp} または s-{ASIN}-{timestamp}
    match = re.search(r'(?:base|s)-([A-Z0-9]{10})-\d+(?:_\d+)?', identifier)
    if match:
        return match.group(1)

    # パターン2: {ASIN} が含まれている
    match = re.search(r'([A-Z0-9]{10})', identifier)
    if match:
        return match.group(1)

    return None


def normalize_listings(db: MasterDB, dry_run: bool = True) -> Dict[str, int]:
    """
    listingsテーブルの正規化

    Args:
        db: MasterDBインスタンス
        dry_run: Trueの場合は実際には更新しない

    Returns:
        dict: 正規化結果の統計
    """
    print("\n" + "=" * 70)
    print("フェーズ1: 正規化処理")
    print("=" * 70)

    stats = {
        'platform_normalized': 0,
        'account_normalized': 0,
        'status_normalized': 0,
        'duplicates_removed': 0
    }

    with db.get_connection() as conn:
        cursor = conn.cursor()

        # 0. 重複ASINの処理（BASE/base間の重複を解消）
        cursor.execute("""
            SELECT asin
            FROM listings
            WHERE platform IN ('BASE', 'base')
            GROUP BY asin
            HAVING COUNT(*) > 1
        """)
        duplicate_asins = [row['asin'] for row in cursor.fetchall()]

        if duplicate_asins:
            print(f"\n重複ASIN処理: {len(duplicate_asins)}件")
            print("  新しいシステム（platform='base'）のデータを優先し、")
            print("  古いデータ（platform='BASE'）を削除します")

            if not dry_run:
                # 重複するBASEレコードを削除
                for asin in duplicate_asins:
                    cursor.execute("""
                        DELETE FROM listings
                        WHERE asin = ? AND platform = 'BASE'
                    """, (asin,))
                    stats['duplicates_removed'] += cursor.rowcount

                print(f"  削除完了: {stats['duplicates_removed']}件")

        # 1. platform: BASE → base
        cursor.execute("SELECT COUNT(*) as count FROM listings WHERE platform = 'BASE'")
        platform_count = cursor.fetchone()['count']
        print(f"\nプラットフォーム名正規化: {platform_count}件（BASE → base）")

        if not dry_run and platform_count > 0:
            cursor.execute("UPDATE listings SET platform = 'base' WHERE platform = 'BASE'")
            stats['platform_normalized'] = cursor.rowcount
            print(f"  更新完了: {stats['platform_normalized']}件")

        # 2. account_id: base_main → base_account_1
        cursor.execute("SELECT COUNT(*) as count FROM listings WHERE account_id = 'base_main'")
        account_count = cursor.fetchone()['count']
        print(f"\nアカウントID正規化: {account_count}件（base_main → base_account_1）")

        if not dry_run and account_count > 0:
            cursor.execute("UPDATE listings SET account_id = 'base_account_1' WHERE account_id = 'base_main'")
            stats['account_normalized'] = cursor.rowcount
            print(f"  更新完了: {stats['account_normalized']}件")

        # 3. status: active → listed
        cursor.execute("SELECT COUNT(*) as count FROM listings WHERE status = 'active'")
        status_count = cursor.fetchone()['count']
        print(f"\nステータス正規化: {status_count}件（active → listed）")

        if not dry_run and status_count > 0:
            cursor.execute("UPDATE listings SET status = 'listed' WHERE status = 'active'")
            stats['status_normalized'] = cursor.rowcount
            print(f"  更新完了: {stats['status_normalized']}件")

    return stats


def merge_existing_items(base_items: List[Dict[str, Any]], db: MasterDB,
                         target_account_id: str, dry_run: bool = True) -> Dict[str, int]:
    """
    既存商品の更新（ケース2, 3）

    Args:
        base_items: BASE APIから取得した商品リスト
        db: MasterDBインスタンス
        target_account_id: ターゲットアカウントID
        dry_run: Trueの場合は実際には更新しない

    Returns:
        dict: 更新結果の統計
    """
    print("\n" + "=" * 70)
    print("フェーズ2: 既存商品の更新")
    print("=" * 70)

    stats = {
        'sku_match_updated': 0,
        'asin_match_updated': 0,
        'skipped': 0,
        'errors': 0
    }

    # BASE APIの商品をASINでインデックス化
    base_by_asin = {}
    for item in base_items:
        asin = extract_asin_from_identifier(item.get('identifier', ''))
        if asin:
            base_by_asin[asin] = item

    print(f"\nBASE API商品（ASIN抽出成功）: {len(base_by_asin)}件")

    # ローカルDBのlistingsを取得（platform=base, account_id=target）
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, asin, sku, platform_item_id, selling_price,
                   in_stock_quantity, visibility, status
            FROM listings
            WHERE platform = 'base' AND account_id = ?
        """, (target_account_id,))
        local_listings = cursor.fetchall()

    print(f"ローカルDB listings: {len(local_listings)}件")

    # 既存商品を更新
    update_count = 0
    with db.get_connection() as conn:
        cursor = conn.cursor()

        for listing in local_listings:
            listing_id = listing['id']
            asin = listing['asin']
            current_sku = listing['sku']

            # BASE APIに該当商品があるか確認
            if asin not in base_by_asin:
                stats['skipped'] += 1
                continue

            base_item = base_by_asin[asin]
            base_sku = base_item.get('identifier', '')
            base_item_id = base_item.get('item_id')
            base_price = base_item.get('price')
            base_stock = base_item.get('stock', 0)
            base_visible = base_item.get('visible', 1)

            # visibility変換
            visibility = 'public' if base_visible == 1 else 'hidden'

            # 更新内容
            updates = {
                'platform_item_id': str(base_item_id) if base_item_id else None,
                'sku': base_sku,
                'selling_price': float(base_price) if base_price else None,
                'in_stock_quantity': int(base_stock),
                'visibility': visibility,
                'status': 'listed'
            }

            if dry_run:
                update_count += 1
                if update_count <= 5:
                    print(f"\n  [{update_count}] ASIN: {asin}")
                    print(f"      SKU: {current_sku} → {base_sku}")
                    print(f"      platform_item_id: {listing['platform_item_id']} → {base_item_id}")
                    print(f"      price: {listing['selling_price']} → {base_price}")
                    print(f"      stock: {listing['in_stock_quantity']} → {base_stock}")
                    print(f"      visibility: {listing['visibility']} → {visibility}")
            else:
                try:
                    # SKU変更による重複チェック
                    if base_sku != current_sku:
                        cursor.execute("SELECT id FROM listings WHERE sku = ?", (base_sku,))
                        conflict = cursor.fetchone()
                        if conflict and conflict['id'] != listing_id:
                            print(f"  [WARN] SKU重複スキップ: {asin} ({base_sku})")
                            stats['skipped'] += 1
                            continue

                    # 更新実行
                    fields = ', '.join([f'{k} = ?' for k in updates.keys()])
                    values = list(updates.values())
                    values.append(listing_id)

                    cursor.execute(f"""
                        UPDATE listings
                        SET {fields}
                        WHERE id = ?
                    """, values)

                    if cursor.rowcount > 0:
                        update_count += 1
                        stats['asin_match_updated'] += 1

                except Exception as e:
                    print(f"  [ERROR] ASIN: {asin} - {e}")
                    stats['errors'] += 1

    print(f"\n更新対象: {update_count}件")
    if not dry_run:
        print(f"更新完了: {stats['asin_match_updated']}件")
        print(f"スキップ: {stats['skipped']}件")
        print(f"エラー: {stats['errors']}件")

    return stats


def add_new_items(base_items: List[Dict[str, Any]], db: MasterDB,
                  target_account_id: str, dry_run: bool = True) -> Dict[str, int]:
    """
    新規商品の追加（ケース1）

    Args:
        base_items: BASE APIから取得した商品リスト
        db: MasterDBインスタンス
        target_account_id: ターゲットアカウントID
        dry_run: Trueの場合は実際には追加しない

    Returns:
        dict: 追加結果の統計
    """
    print("\n" + "=" * 70)
    print("フェーズ3: 新規商品の追加")
    print("=" * 70)

    stats = {
        'products_added': 0,
        'listings_added': 0,
        'skipped': 0,
        'errors': 0
    }

    # ローカルDBの既存ASINを取得
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT asin FROM products")
        existing_asins = {row['asin'] for row in cursor.fetchall()}

    print(f"\n既存商品マスタ: {len(existing_asins)}件")

    # 新規商品を抽出
    new_items = []
    for item in base_items:
        asin = extract_asin_from_identifier(item.get('identifier', ''))
        if asin and asin not in existing_asins:
            item['_extracted_asin'] = asin
            new_items.append(item)

    print(f"新規追加対象: {len(new_items)}件")

    if not new_items:
        print("追加する商品はありません")
        return stats

    # サンプル表示
    print("\nサンプル（最初の3件）:")
    for i, item in enumerate(new_items[:3], 1):
        print(f"  {i}. ASIN: {item['_extracted_asin']}")
        print(f"     Title: {item.get('title', '')[:50]}...")
        print(f"     Price: {item.get('price')} JPY")
        print()

    if dry_run:
        stats['products_added'] = len(new_items)
        stats['listings_added'] = len(new_items)
        return stats

    # 実際に追加
    with db.get_connection() as conn:
        cursor = conn.cursor()

        for item in new_items:
            asin = item['_extracted_asin']
            title = item.get('title', '')
            price = item.get('price')
            stock = item.get('stock', 0)
            visible = item.get('visible', 1)
            sku = item.get('identifier', '')
            item_id = item.get('item_id')

            try:
                # productsテーブルに追加
                cursor.execute("""
                    INSERT OR IGNORE INTO products (asin, title_ja)
                    VALUES (?, ?)
                """, (asin, title))

                if cursor.rowcount > 0:
                    stats['products_added'] += 1

                # listingsテーブルに追加
                visibility = 'public' if visible == 1 else 'hidden'

                cursor.execute("""
                    INSERT INTO listings
                    (asin, platform, account_id, platform_item_id, sku,
                     selling_price, in_stock_quantity, visibility, status)
                    VALUES (?, 'base', ?, ?, ?, ?, ?, ?, 'listed')
                """, (asin, target_account_id, str(item_id), sku,
                      float(price) if price else None, int(stock), visibility))

                if cursor.rowcount > 0:
                    stats['listings_added'] += 1

            except Exception as e:
                print(f"  [ERROR] ASIN: {asin} - {e}")
                stats['errors'] += 1

    print(f"\n追加完了:")
    print(f"  商品マスタ: {stats['products_added']}件")
    print(f"  listings: {stats['listings_added']}件")
    print(f"  エラー: {stats['errors']}件")

    return stats


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='BASE API → ローカルDB マージ'
    )
    parser.add_argument(
        '--account-id',
        type=str,
        default='base_account_1',
        help='BASE アカウントID（デフォルト: base_account_1）'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='実際には更新せず、プレビューのみ'
    )
    parser.add_argument(
        '--skip-normalize',
        action='store_true',
        help='正規化処理をスキップ'
    )
    parser.add_argument(
        '--skip-update',
        action='store_true',
        help='既存商品の更新をスキップ'
    )
    parser.add_argument(
        '--skip-add',
        action='store_true',
        help='新規商品の追加をスキップ'
    )

    args = parser.parse_args()

    print("=" * 80)
    print("BASE API → ローカルDB マージ")
    print("=" * 80)

    if args.dry_run:
        print("\n[DRY RUN モード] 実際には更新しません")

    # バックアップチェック
    backup_dir = project_root / 'inventory' / 'data' / 'backups'
    if not args.dry_run and backup_dir.exists():
        backups = sorted(backup_dir.glob("master_backup_*.db"),
                        key=lambda p: p.stat().st_mtime, reverse=True)
        if backups:
            latest_backup = backups[0]
            backup_time = datetime.fromtimestamp(latest_backup.stat().st_mtime)
            print(f"\n最新バックアップ: {latest_backup.name}")
            print(f"作成日時: {backup_time.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            print("\n[警告] バックアップが見つかりません")
            print("実行前にバックアップを作成することを推奨します:")
            print("  python inventory/scripts/backup_db.py")
            response = input("\nバックアップなしで続行しますか？ (y/N): ")
            if response.lower() != 'y':
                print("キャンセルしました")
                return

    # AccountManagerとAPIクライアントを初期化
    account_manager = AccountManager()
    api_client = BaseAPIClient(
        account_id=args.account_id,
        account_manager=account_manager
    )

    # MasterDBを初期化
    db = MasterDB()

    # BASE APIから全商品を取得
    print("\nBASE APIから商品を取得中...")
    all_items = []
    offset = 0
    limit = 100

    while True:
        try:
            response = api_client.get_items(limit=limit, offset=offset)
            items = response.get('items', [])

            if not items:
                break

            all_items.extend(items)
            offset += len(items)
            print(f"  取得済み: {len(all_items)}件", end='\r')

            if len(items) < limit:
                break

        except Exception as e:
            print(f"\n  エラー (offset={offset}): {e}")
            break

    print(f"\n  合計取得: {len(all_items)}件")

    if not all_items:
        print("\nBASE APIから商品を取得できませんでした")
        return

    # 統計情報
    total_stats = {
        'normalize': {},
        'update': {},
        'add': {}
    }

    # フェーズ1: 正規化
    if not args.skip_normalize:
        total_stats['normalize'] = normalize_listings(db, dry_run=args.dry_run)

    # フェーズ2: 既存商品の更新
    if not args.skip_update:
        total_stats['update'] = merge_existing_items(
            all_items, db, args.account_id, dry_run=args.dry_run
        )

    # フェーズ3: 新規商品の追加
    if not args.skip_add:
        total_stats['add'] = add_new_items(
            all_items, db, args.account_id, dry_run=args.dry_run
        )

    # サマリー表示
    print("\n" + "=" * 80)
    print("マージ完了サマリー")
    print("=" * 80)

    if total_stats['normalize']:
        print("\n【正規化】")
        print(f"  重複削除: {total_stats['normalize'].get('duplicates_removed', 0)}件")
        print(f"  プラットフォーム名: {total_stats['normalize'].get('platform_normalized', 0)}件")
        print(f"  アカウントID: {total_stats['normalize'].get('account_normalized', 0)}件")
        print(f"  ステータス: {total_stats['normalize'].get('status_normalized', 0)}件")

    if total_stats['update']:
        print("\n【既存商品の更新】")
        print(f"  更新: {total_stats['update'].get('asin_match_updated', 0)}件")
        print(f"  スキップ: {total_stats['update'].get('skipped', 0)}件")
        print(f"  エラー: {total_stats['update'].get('errors', 0)}件")

    if total_stats['add']:
        print("\n【新規商品の追加】")
        print(f"  商品マスタ: {total_stats['add'].get('products_added', 0)}件")
        print(f"  listings: {total_stats['add'].get('listings_added', 0)}件")
        print(f"  エラー: {total_stats['add'].get('errors', 0)}件")

    print("\n" + "=" * 80)

    if args.dry_run:
        print("[DRY RUN] プレビューのみ実行しました")
        print("実際に実行するには --dry-run フラグを外してください")
    else:
        print("マージ完了")

    print("=" * 80)


if __name__ == '__main__':
    main()
