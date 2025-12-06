"""
全アカウントの価格取得状況を分析
"""
import sys
from pathlib import Path
from collections import defaultdict

# パスを追加
sys.path.insert(0, str(Path(__file__).resolve().parent))

from inventory.core.master_db import MasterDB
from platforms.base.accounts.manager import AccountManager

def main():
    print("=" * 70)
    print("全アカウントの価格取得状況分析")
    print("=" * 70)
    print()

    master_db = MasterDB()
    account_manager = AccountManager()

    # アクティブなアカウントを取得
    accounts = account_manager.get_active_accounts()

    print(f"アクティブアカウント数: {len(accounts)}件")
    print()

    total_stats = {
        'total_listings': 0,
        'with_cache': 0,
        'without_cache': 0,
        'with_price': 0,
        'without_price': 0
    }

    for account in accounts:
        account_id = account['id']
        account_name = account['name']

        print(f"【{account_name}】({account_id})")

        # 出品一覧を取得
        listings = master_db.get_listings_by_account(
            platform='base',
            account_id=account_id,
            status='listed'
        )

        print(f"  出品数: {len(listings)}件")

        if not listings:
            print()
            continue

        # キャッシュの有無を確認
        from inventory.core.cache_manager import AmazonProductCache
        cache = AmazonProductCache()

        cache_exists = 0
        cache_missing = 0
        price_exists = 0
        price_missing = 0

        for listing in listings:
            asin = listing['asin']
            cache_file = cache.cache_dir / f'{asin}.json'

            # キャッシュの有無
            if cache_file.exists():
                cache_exists += 1

                # キャッシュの中身を確認
                import json
                try:
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        cached_data = json.load(f)

                    if cached_data.get('price') is not None:
                        price_exists += 1
                    else:
                        price_missing += 1
                except:
                    cache_missing += 1
                    price_missing += 1
            else:
                cache_missing += 1
                price_missing += 1

        print(f"  キャッシュ:")
        print(f"    - あり: {cache_exists}件 ({cache_exists/len(listings)*100:.1f}%)")
        print(f"    - なし: {cache_missing}件 ({cache_missing/len(listings)*100:.1f}%)")
        print(f"  価格情報:")
        print(f"    - あり: {price_exists}件 ({price_exists/len(listings)*100:.1f}%)")
        print(f"    - なし: {price_missing}件 ({price_missing/len(listings)*100:.1f}%)")

        # 統計を集計
        total_stats['total_listings'] += len(listings)
        total_stats['with_cache'] += cache_exists
        total_stats['without_cache'] += cache_missing
        total_stats['with_price'] += price_exists
        total_stats['without_price'] += price_missing

        print()

    # 全体統計
    print("=" * 70)
    print("【全体統計】")
    print("=" * 70)
    print(f"総出品数: {total_stats['total_listings']:,}件")
    print()
    print("キャッシュ状況:")
    print(f"  - あり: {total_stats['with_cache']:,}件 ({total_stats['with_cache']/total_stats['total_listings']*100:.1f}%)")
    print(f"  - なし: {total_stats['without_cache']:,}件 ({total_stats['without_cache']/total_stats['total_listings']*100:.1f}%)")
    print()
    print("価格情報:")
    print(f"  - あり: {total_stats['with_price']:,}件 ({total_stats['with_price']/total_stats['total_listings']*100:.1f}%)")
    print(f"  - なし: {total_stats['without_price']:,}件 ({total_stats['without_price']/total_stats['total_listings']*100:.1f}%)")
    print()

    if total_stats['without_price'] > 0:
        print("⚠️  価格情報がない商品が存在します")
        print(f"   → これらの商品で「価格情報が取得できません」が出力される可能性があります")
        print()

if __name__ == '__main__':
    main()
