"""
BASE API → ローカルDB マージプレビュースクリプト

BASE APIから既存商品を取得し、ローカルDBとの差分を分析します。
実際のデータ変更は行いません（プレビューのみ）。
"""

import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
import re
from datetime import datetime

# パスを追加
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / 'platforms' / 'base'))

from core.api_client import BaseAPIClient
from accounts.manager import AccountManager
from inventory.core.master_db import MasterDB


def extract_asin_from_identifier(identifier: str) -> Optional[str]:
    """
    SKU/identifierからASINを抽出

    Args:
        identifier: SKU文字列（例: "base-B0CB5G8NRV-20251113_1202"）

    Returns:
        str or None: 抽出されたASIN
    """
    if not identifier:
        return None

    # パターン1: base-{ASIN}-{timestamp}
    match = re.search(r'base-([A-Z0-9]{10})-\d+_\d+', identifier)
    if match:
        return match.group(1)

    # パターン2: {ASIN} が含まれている
    match = re.search(r'([A-Z0-9]{10})', identifier)
    if match:
        return match.group(1)

    return None


def fetch_all_base_items(api_client: BaseAPIClient) -> List[Dict[str, Any]]:
    """
    BASE APIから全商品を取得（ページネーション対応）

    Args:
        api_client: BaseAPIClientインスタンス

    Returns:
        list: 商品データのリスト
    """
    all_items = []
    offset = 0
    limit = 100  # BASE APIの最大値

    print("\nBASE APIから商品を取得中...")

    while True:
        try:
            response = api_client.get_items(limit=limit, offset=offset)
            items = response.get('items', [])

            if not items:
                break

            all_items.extend(items)
            offset += len(items)

            print(f"  取得済み: {len(all_items)}件", end='\r')

            # 次のページがない場合は終了
            if len(items) < limit:
                break

        except Exception as e:
            print(f"\n  エラー (offset={offset}): {e}")
            break

    print(f"\n  合計取得: {len(all_items)}件")
    return all_items


def analyze_merge_impact(base_items: List[Dict[str, Any]], db: MasterDB) -> Dict[str, Any]:
    """
    マージの影響を分析

    Args:
        base_items: BASE APIから取得した商品リスト
        db: MasterDBインスタンス

    Returns:
        dict: 分析結果
    """
    print("\n差分を分析中...")

    result = {
        'new_items': [],           # BASE APIにあり、ローカルDBにない
        'existing_sku_match': [],  # SKUが一致（更新対象）
        'existing_asin_match': [], # ASINは一致、SKUは異なる
        'no_asin': [],             # ASINが抽出できない
        'local_only': [],          # ローカルDBのみに存在
        'platform_normalize': [],  # プラットフォーム名正規化が必要
        'account_normalize': [],   # アカウントID正規化が必要
    }

    # BASE APIの商品をSKUとASINでインデックス化
    base_by_sku = {}
    base_by_asin = {}

    for item in base_items:
        identifier = item.get('identifier', '')
        item_id = item.get('item_id')

        # SKUでインデックス
        if identifier:
            base_by_sku[identifier] = item

        # ASINを抽出してインデックス
        asin = extract_asin_from_identifier(identifier)
        if asin:
            if asin not in base_by_asin:
                base_by_asin[asin] = []
            base_by_asin[asin].append(item)
            item['_extracted_asin'] = asin
        else:
            result['no_asin'].append(item)

    print(f"  BASE API商品: {len(base_items)}件")
    print(f"  ASIN抽出成功: {len(base_by_asin)}件")
    print(f"  ASIN抽出失敗: {len(result['no_asin'])}件")

    # ローカルDBのlistingsを取得
    with db.get_connection() as conn:
        cursor = conn.cursor()

        # すべてのlistingsを取得
        cursor.execute("""
            SELECT id, asin, platform, account_id, platform_item_id, sku, status, selling_price
            FROM listings
        """)
        local_listings = cursor.fetchall()

    print(f"  ローカルDB listings: {len(local_listings)}件")

    # ローカルDBのlistingsを分析
    local_by_sku = {}
    local_by_asin = {}

    for listing in local_listings:
        listing_dict = dict(listing)
        sku = listing_dict.get('sku')
        asin = listing_dict.get('asin')
        platform = listing_dict.get('platform')
        account_id = listing_dict.get('account_id')

        # プラットフォーム名正規化チェック
        if platform == 'BASE':
            result['platform_normalize'].append(listing_dict)

        # アカウントID正規化チェック
        if account_id == 'base_main':
            result['account_normalize'].append(listing_dict)

        # SKUでインデックス
        if sku:
            local_by_sku[sku] = listing_dict

        # ASINでインデックス
        if asin:
            if asin not in local_by_asin:
                local_by_asin[asin] = []
            local_by_asin[asin].append(listing_dict)

    # 差分分析
    for item in base_items:
        identifier = item.get('identifier', '')
        asin = item.get('_extracted_asin')

        # ケース1: SKU完全一致
        if identifier and identifier in local_by_sku:
            local_listing = local_by_sku[identifier]
            result['existing_sku_match'].append({
                'base_item': item,
                'local_listing': local_listing,
                'action': 'update_platform_item_id'
            })

        # ケース2: SKUは不一致だがASINが一致
        elif asin and asin in local_by_asin:
            # SKUが一致しないものだけ
            local_listings_for_asin = [
                l for l in local_by_asin[asin]
                if l.get('sku') != identifier
            ]
            if local_listings_for_asin:
                result['existing_asin_match'].append({
                    'base_item': item,
                    'local_listings': local_listings_for_asin,
                    'action': 'update_or_merge'
                })

        # ケース3: 新規（ローカルDBに存在しない）
        elif asin:  # ASINが抽出できる場合のみ
            result['new_items'].append({
                'base_item': item,
                'asin': asin,
                'action': 'insert'
            })

    # ローカルDBのみに存在する商品
    base_asins = set(base_by_asin.keys())
    for asin, local_listings in local_by_asin.items():
        if asin not in base_asins:
            for local_listing in local_listings:
                # platform_item_idがない = BASE APIに未登録
                if not local_listing.get('platform_item_id'):
                    result['local_only'].append(local_listing)

    return result


def print_analysis_report(analysis: Dict[str, Any]):
    """
    分析結果をレポート形式で出力

    Args:
        analysis: analyze_merge_impact()の結果
    """
    print("\n" + "=" * 80)
    print("BASE API → ローカルDB マージプレビューレポート")
    print("=" * 80)

    print(f"\n生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    print("\n【サマリー】")
    print(f"  新規追加が必要: {len(analysis['new_items'])}件")
    print(f"  既存商品（SKU一致）: {len(analysis['existing_sku_match'])}件")
    print(f"  既存商品（ASIN一致、SKU不一致）: {len(analysis['existing_asin_match'])}件")
    print(f"  ローカルDBのみ（BASE APIに未登録）: {len(analysis['local_only'])}件")
    print(f"  ASIN抽出失敗（SKIPされる）: {len(analysis['no_asin'])}件")

    print("\n【正規化が必要】")
    print(f"  プラットフォーム名（BASE → base）: {len(analysis['platform_normalize'])}件")
    print(f"  アカウントID（base_main → base_account_1）: {len(analysis['account_normalize'])}件")

    # 詳細レポート
    print("\n" + "-" * 80)
    print("【ケース1: 新規追加が必要な商品】")
    print("-" * 80)
    print(f"件数: {len(analysis['new_items'])}件")
    if analysis['new_items']:
        print("\nサンプル（最初の5件）:")
        for i, item_data in enumerate(analysis['new_items'][:5], 1):
            item = item_data['base_item']
            asin = item_data['asin']
            print(f"  {i}. ASIN: {asin}")
            print(f"     BASE item_id: {item.get('item_id')}")
            print(f"     Title: {item.get('title', '')[:50]}...")
            print(f"     Price: {item.get('price')} JPY")
            print(f"     Stock: {item.get('stock')}")
            print()

    print("-" * 80)
    print("【ケース2: 既存商品（SKU一致）- platform_item_idを更新】")
    print("-" * 80)
    print(f"件数: {len(analysis['existing_sku_match'])}件")
    if analysis['existing_sku_match']:
        print("\nサンプル（最初の5件）:")
        for i, match_data in enumerate(analysis['existing_sku_match'][:5], 1):
            base_item = match_data['base_item']
            local_listing = match_data['local_listing']
            print(f"  {i}. ASIN: {local_listing['asin']}")
            print(f"     SKU: {local_listing['sku']}")
            print(f"     現在のplatform_item_id: {local_listing.get('platform_item_id')}")
            print(f"     BASE item_id: {base_item.get('item_id')}")
            print(f"     Status: {local_listing['status']} → listed")
            print()

    print("-" * 80)
    print("【ケース3: 既存商品（ASIN一致、SKU不一致）】")
    print("-" * 80)
    print(f"件数: {len(analysis['existing_asin_match'])}件")
    if analysis['existing_asin_match']:
        print("\nサンプル（最初の3件）:")
        for i, match_data in enumerate(analysis['existing_asin_match'][:3], 1):
            base_item = match_data['base_item']
            local_listings = match_data['local_listings']
            asin = base_item.get('_extracted_asin')
            print(f"  {i}. ASIN: {asin}")
            print(f"     BASE SKU: {base_item.get('identifier')}")
            print(f"     BASE item_id: {base_item.get('item_id')}")
            print(f"     ローカルDB（{len(local_listings)}件）:")
            for listing in local_listings[:2]:
                print(f"       - SKU: {listing['sku']}, Status: {listing['status']}")
            print()

    print("-" * 80)
    print("【ケース4: ローカルDBのみ（BASE APIに未登録）】")
    print("-" * 80)
    print(f"件数: {len(analysis['local_only'])}件")
    if analysis['local_only']:
        print("\nサンプル（最初の5件）:")
        for i, listing in enumerate(analysis['local_only'][:5], 1):
            print(f"  {i}. ASIN: {listing['asin']}")
            print(f"     SKU: {listing.get('sku')}")
            print(f"     Status: {listing['status']}")
            print(f"     Platform: {listing['platform']}")
            print()

    print("=" * 80)
    print("プレビュー完了")
    print("=" * 80)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='BASE API → ローカルDB マージプレビュー'
    )
    parser.add_argument(
        '--account-id',
        type=str,
        default='base_account_1',
        help='BASE アカウントID（デフォルト: base_account_1）'
    )

    args = parser.parse_args()

    print("=" * 80)
    print("BASE API → ローカルDB マージプレビュー")
    print("=" * 80)

    # AccountManagerとAPIクライアントを初期化
    account_manager = AccountManager()
    api_client = BaseAPIClient(
        account_id=args.account_id,
        account_manager=account_manager
    )

    # MasterDBを初期化
    db = MasterDB()

    # BASE APIから全商品を取得
    base_items = fetch_all_base_items(api_client)

    if not base_items:
        print("\nBASE APIから商品を取得できませんでした")
        return

    # マージの影響を分析
    analysis = analyze_merge_impact(base_items, db)

    # レポート出力
    print_analysis_report(analysis)


if __name__ == '__main__':
    main()
