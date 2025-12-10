"""
既存商品を新しいアカウントに割り当てるスクリプト

productsテーブルに既に存在する商品を、指定したアカウントのlistingsに追加し、
upload_queueにスケジュールします。

SP-API呼び出しは行いません（既にproductsテーブルにデータがあるため）。

使い方:
    # 明示的にアカウントとカテゴリを指定
    python inventory/scripts/assign_products_to_account.py \
        --account-id base_account_3 \
        --category-filter "カメラ,三脚,レンズ" \
        --dry-run

    # カテゴリルーティング設定に基づいて自動振り分け
    python inventory/scripts/assign_products_to_account.py \
        --use-category-routing \
        --dry-run

    # 特定カテゴリのみを自動振り分け
    python inventory/scripts/assign_products_to_account.py \
        --category-filter "家電" \
        --use-category-routing \
        --dry-run
"""

import sys
import argparse
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from inventory.core.master_db import MasterDB
from inventory.core.listing_manager import ListingManager
from common.pricing import PriceCalculator
from common.category_router import CategoryRouter
from scheduler.queue_manager import UploadQueueManager
from shared.utils.sku_generator import generate_sku


def load_active_accounts() -> List[str]:
    """
    account_config.jsonからアクティブなアカウントIDを取得

    Returns:
        List[str]: アクティブなアカウントIDのリスト
    """
    config_path = project_root / 'platforms' / 'base' / 'accounts' / 'account_config.json'

    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    return [
        account['id']
        for account in config['accounts']
        if account.get('active', False)
    ]


def get_products_by_category(
    db: MasterDB,
    category_keywords: List[str] = None,
    limit: int = None
) -> List[Dict[str, Any]]:
    """
    カテゴリ条件で商品を取得

    Args:
        db: MasterDBインスタンス
        category_keywords: カテゴリに含まれるべきキーワード（OR条件）
        limit: 取得件数上限

    Returns:
        List[dict]: 商品情報のリスト
    """
    with db.get_connection() as conn:
        cursor = conn.cursor()

        if category_keywords:
            # キーワードでOR検索
            conditions = ' OR '.join(['category LIKE ?' for _ in category_keywords])
            params = [f'%{kw}%' for kw in category_keywords]

            query = f'''
                SELECT * FROM products
                WHERE {conditions}
                ORDER BY updated_at DESC
            '''

            if limit:
                query += f' LIMIT {limit}'

            cursor.execute(query, params)
        else:
            # 全商品
            query = 'SELECT * FROM products ORDER BY updated_at DESC'
            if limit:
                query += f' LIMIT {limit}'
            cursor.execute(query)

        rows = cursor.fetchall()
        products = []
        for row in rows:
            product = dict(row)
            # images をパース
            if product.get('images'):
                try:
                    product['images'] = json.loads(product['images'])
                except:
                    product['images'] = []
            products.append(product)

        return products


def check_existing_listing(
    listing_manager: ListingManager,
    asin: str,
    platform: str,
    account_id: str
) -> bool:
    """
    既に出品が存在するかチェック

    Returns:
        bool: 存在する場合True
    """
    return listing_manager.listing_exists(asin, platform, account_id)


def main():
    parser = argparse.ArgumentParser(
        description='既存商品を新しいアカウントに割り当て',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
例:
  # カメラ関連商品をbase_account_3に追加
  python assign_products_to_account.py --account-id base_account_3 --category-filter "カメラ,三脚" --dry-run

  # カテゴリルーティングで自動振り分け
  python assign_products_to_account.py --use-category-routing --dry-run
        '''
    )

    parser.add_argument('--account-id', type=str,
                        help='割り当て先アカウントID（--use-category-routing使用時は不要）')
    parser.add_argument('--category-filter', type=str,
                        help='カテゴリフィルター（カンマ区切り、例: "カメラ,三脚,レンズ"）')
    parser.add_argument('--use-category-routing', action='store_true',
                        help='config/category_routing.yaml に基づいて自動振り分け')
    parser.add_argument('--platform', type=str, default='base',
                        help='プラットフォーム（デフォルト: base）')
    parser.add_argument('--limit', type=int,
                        help='処理する最大件数')
    parser.add_argument('--dry-run', action='store_true',
                        help='実際の登録は行わず確認のみ')
    parser.add_argument('--skip-queue', action='store_true',
                        help='upload_queueへの追加をスキップ（listingsのみ追加）')
    parser.add_argument('--yes', '-y', action='store_true',
                        help='確認プロンプトをスキップ')

    args = parser.parse_args()

    # 引数のバリデーション
    if not args.use_category_routing and not args.account_id:
        parser.error('--account-id または --use-category-routing のいずれかを指定してください')

    print('=' * 70)
    print('既存商品のアカウント割り当てスクリプト')
    print('=' * 70)
    print(f"実行モード: {'DRY RUN（確認のみ）' if args.dry_run else '本番実行'}")
    print(f"プラットフォーム: {args.platform}")

    if args.use_category_routing:
        print("振り分け方法: カテゴリルーティング（自動）")
    else:
        print(f"振り分け先: {args.account_id}")

    if args.category_filter:
        print(f"カテゴリフィルター: {args.category_filter}")

    print()

    # 初期化
    db = MasterDB()
    listing_manager = ListingManager(master_db=db)
    price_calculator = PriceCalculator()
    queue_manager = UploadQueueManager()

    # アクティブなアカウントを取得
    active_accounts = load_active_accounts()
    print(f"アクティブなアカウント: {active_accounts}")

    # カテゴリルーター初期化（必要な場合）
    category_router = None
    if args.use_category_routing:
        category_router = CategoryRouter()
        if not category_router.is_enabled:
            print("\n警告: カテゴリルーティングが無効です（config/category_routing.yaml の enabled: true を確認）")
            return
        print(f"デフォルトアカウント: {category_router.default_account}")
        print(f"ルーティングルール: {len(category_router.get_routing_rules())}件")

    # カテゴリフィルターをパース
    category_keywords = None
    if args.category_filter:
        category_keywords = [kw.strip() for kw in args.category_filter.split(',')]

    # 商品を取得
    print(f"\n商品を取得中...")
    products = get_products_by_category(db, category_keywords, args.limit)
    print(f"対象商品: {len(products)}件")

    if not products:
        print("対象商品がありません。終了します。")
        return

    # 統計情報
    stats = {
        'total': len(products),
        'added_to_listings': 0,
        'added_to_queue': 0,
        'skipped_existing': 0,
        'skipped_no_price': 0,
        'skipped_no_account': 0,
        'by_account': {}
    }

    # ルーティング結果をプレビュー（カテゴリルーティング使用時）
    if args.use_category_routing:
        print("\n--- ルーティングプレビュー ---")
        routing_preview = {}
        for product in products[:min(10, len(products))]:  # 最初の10件をプレビュー
            category = product.get('category', '')
            result = category_router.get_account_for_category(category)
            account = result['account_id'] or '(振り分け不可)'
            if account not in routing_preview:
                routing_preview[account] = []
            routing_preview[account].append({
                'asin': product['asin'],
                'category': category[:50] + '...' if len(category) > 50 else category,
                'keyword': result.get('matched_keyword')
            })

        for account, items in routing_preview.items():
            print(f"\n{account}:")
            for item in items[:3]:
                keyword_info = f" (keyword: {item['keyword']})" if item['keyword'] else " (default)"
                print(f"  - {item['asin']}: {item['category']}{keyword_info}")
            if len(items) > 3:
                print(f"  ... 他 {len(items) - 3}件")

        # 全体の振り分け予測
        print("\n--- 振り分け予測（全件） ---")
        account_counts = {}
        for product in products:
            category = product.get('category', '')
            result = category_router.get_account_for_category(category)
            account = result['account_id'] or '(振り分け不可)'
            account_counts[account] = account_counts.get(account, 0) + 1

        for account, count in sorted(account_counts.items()):
            print(f"  {account}: {count}件")

    # 確認プロンプト
    if not args.dry_run and not args.yes:
        print()
        confirm = input("処理を開始しますか？ (y/N): ")
        if confirm.lower() != 'y':
            print("キャンセルしました。")
            return

    print("\n処理を開始します...")

    # 商品を処理
    for i, product in enumerate(products, 1):
        asin = product['asin']
        category = product.get('category', '')
        amazon_price = product.get('amazon_price_jpy')

        # 進捗表示
        if i % 100 == 0 or i == len(products):
            print(f"進捗: {i}/{len(products)}")

        # 価格がない場合はスキップ
        if not amazon_price:
            stats['skipped_no_price'] += 1
            continue

        # アカウント決定
        if args.use_category_routing:
            account_id = category_router.route(category, active_accounts)
            if not account_id:
                stats['skipped_no_account'] += 1
                continue
        else:
            account_id = args.account_id
            if account_id not in active_accounts:
                print(f"警告: {account_id} はアクティブではありません")
                stats['skipped_no_account'] += 1
                continue

        # 既存チェック
        if check_existing_listing(listing_manager, asin, args.platform, account_id):
            stats['skipped_existing'] += 1
            continue

        # 売価を計算
        selling_price = price_calculator.calculate_selling_price(amazon_price)

        # SKU生成
        sku = generate_sku(args.platform, asin)

        # DRY RUNの場合はここで終了
        if args.dry_run:
            stats['added_to_listings'] += 1
            if not args.skip_queue:
                stats['added_to_queue'] += 1
            stats['by_account'][account_id] = stats['by_account'].get(account_id, 0) + 1
            continue

        # listings に追加
        try:
            listing_id = listing_manager.add_listing(
                asin=asin,
                platform=args.platform,
                account_id=account_id,
                sku=sku,
                selling_price=selling_price,
                currency='JPY',
                in_stock_quantity=1 if product.get('amazon_in_stock') else 0,
                status='pending',
                visibility='public'
            )

            if listing_id:
                stats['added_to_listings'] += 1
                stats['by_account'][account_id] = stats['by_account'].get(account_id, 0) + 1

                # upload_queue に追加
                if not args.skip_queue:
                    success = queue_manager.add_to_queue(
                        asin=asin,
                        platform=args.platform,
                        account_id=account_id,
                        priority=5
                    )
                    if success:
                        stats['added_to_queue'] += 1

        except Exception as e:
            print(f"エラー ({asin}): {e}")

    # 結果表示
    print('\n' + '=' * 70)
    print('実行結果')
    print('=' * 70)
    print(f"対象商品: {stats['total']}件")
    print(f"listings追加: {stats['added_to_listings']}件")
    print(f"queue追加: {stats['added_to_queue']}件")
    print(f"スキップ（既存）: {stats['skipped_existing']}件")
    print(f"スキップ（価格なし）: {stats['skipped_no_price']}件")
    print(f"スキップ（アカウント不明）: {stats['skipped_no_account']}件")

    if stats['by_account']:
        print('\nアカウント別内訳:')
        for account, count in sorted(stats['by_account'].items()):
            print(f"  {account}: {count}件")

    if args.dry_run:
        print('\n※ DRY RUNモードのため、実際の登録は行われていません')


if __name__ == '__main__':
    main()
