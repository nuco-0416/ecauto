"""
BASE注文一覧取得スクリプト

BASE APIから注文情報を取得し、販売された商品の在庫状況を確認する
"""

import sys
import logging
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import requests
import time

# パスを追加
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from platforms.base.accounts.manager import AccountManager
from platforms.base.core.api_client import BaseAPIClient
from inventory.core.master_db import MasterDB

# ロガー設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class OrdersFetcher:
    """
    BASE注文取得クラス
    """

    BASE_URL = "https://api.thebase.in/1"

    def __init__(self):
        self.account_manager = AccountManager()
        self.master_db = MasterDB()

    def get_orders(
        self,
        account_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100,
        max_orders: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        注文一覧を取得

        Args:
            account_id: アカウントID
            start_date: 開始日（yyyy-mm-dd形式）
            end_date: 終了日（yyyy-mm-dd形式）
            limit: 1回のリクエストで取得する件数（最大100）
            max_orders: 最大取得件数（Noneの場合は全件）

        Returns:
            list: 注文リスト
        """
        # APIクライアント作成
        base_client = BaseAPIClient(
            account_id=account_id,
            account_manager=self.account_manager
        )

        all_orders = []
        offset = 0

        while True:
            params = {
                'limit': limit,
                'offset': offset
            }

            if start_date:
                params['start_ordered'] = start_date
            if end_date:
                params['end_ordered'] = end_date

            try:
                # トークン自動更新
                base_client._refresh_token_if_needed()

                url = f"{self.BASE_URL}/orders"
                response = requests.get(
                    url,
                    headers=base_client.headers,
                    params=params,
                    timeout=30
                )
                response.raise_for_status()

                data = response.json()
                orders = data.get('orders', [])

                if not orders:
                    break

                all_orders.extend(orders)

                # 最大件数チェック
                if max_orders and len(all_orders) >= max_orders:
                    all_orders = all_orders[:max_orders]
                    break

                # 取得件数がlimitより少ない場合は終了
                if len(orders) < limit:
                    break

                offset += limit
                time.sleep(0.1)  # レート制限対策

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 401:
                    logger.error(f"認証エラー: read_ordersスコープが必要です")
                else:
                    logger.error(f"注文取得エラー: {e}")
                break
            except Exception as e:
                logger.error(f"注文取得エラー: {e}")
                break

        return all_orders

    def get_order_detail(self, account_id: str, unique_key: str) -> Optional[Dict[str, Any]]:
        """
        注文詳細を取得

        Args:
            account_id: アカウントID
            unique_key: 注文のunique_key

        Returns:
            dict: 注文詳細
        """
        base_client = BaseAPIClient(
            account_id=account_id,
            account_manager=self.account_manager
        )

        try:
            base_client._refresh_token_if_needed()

            url = f"{self.BASE_URL}/orders/detail/{unique_key}"
            response = requests.get(
                url,
                headers=base_client.headers,
                timeout=30
            )
            response.raise_for_status()

            return response.json().get('order')

        except Exception as e:
            logger.error(f"注文詳細取得エラー ({unique_key}): {e}")
            return None

    def get_sold_items_with_zero_stock(
        self,
        account_id: str,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        販売済みで在庫0になっている商品を取得

        Args:
            account_id: アカウントID
            days: 遡る日数（デフォルト30日）

        Returns:
            list: 販売済みで在庫0の商品リスト
        """
        # 日付範囲を設定
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        logger.info(f"注文を取得中: {account_id} ({start_date} ~ {end_date})")

        # 注文一覧を取得
        orders = self.get_orders(
            account_id=account_id,
            start_date=start_date,
            end_date=end_date
        )

        logger.info(f"取得した注文数: {len(orders)}件")

        # 注文詳細から商品情報を収集
        sold_items = {}  # item_id -> 商品情報

        for order in orders:
            unique_key = order.get('unique_key')
            dispatch_status = order.get('dispatch_status')

            # キャンセル以外の注文を対象
            if dispatch_status == 'cancelled':
                continue

            # 注文詳細を取得
            detail = self.get_order_detail(account_id, unique_key)
            if not detail:
                continue

            # 注文商品を処理
            order_items = detail.get('order_items', [])
            for item in order_items:
                item_id = str(item.get('item_id'))
                if item_id not in sold_items:
                    sold_items[item_id] = {
                        'item_id': item_id,
                        'title': item.get('title', '')[:50],
                        'variation_id': item.get('variation_id'),
                        'price': item.get('price'),
                        'amount': item.get('amount', 1),
                        'order_count': 1,
                        'order_dates': [order.get('ordered')]
                    }
                else:
                    sold_items[item_id]['amount'] += item.get('amount', 1)
                    sold_items[item_id]['order_count'] += 1
                    sold_items[item_id]['order_dates'].append(order.get('ordered'))

            time.sleep(0.1)  # レート制限対策

        logger.info(f"販売された商品種類: {len(sold_items)}件")

        # 現在の在庫状況を確認
        base_client = BaseAPIClient(
            account_id=account_id,
            account_manager=self.account_manager
        )

        all_items = base_client.get_all_items(max_items=2000)
        items_map = {str(item.get('item_id')): item for item in all_items}

        # 在庫0の商品を抽出
        zero_stock_sold = []
        for item_id, sold_info in sold_items.items():
            current_item = items_map.get(item_id)
            if current_item and current_item.get('stock') == 0:
                sold_info['current_stock'] = 0
                sold_info['identifier'] = current_item.get('identifier', '')
                sold_info['visible'] = current_item.get('visible')

                # ASINを抽出
                identifier = sold_info['identifier']
                if identifier.startswith('b-') and '-' in identifier[2:]:
                    asin = identifier.split('-')[1]
                    sold_info['asin'] = asin

                    # Amazon在庫状況を確認
                    product = self.master_db.get_product(asin)
                    if product:
                        sold_info['amazon_in_stock'] = product.get('amazon_in_stock', False)
                        sold_info['amazon_price'] = product.get('amazon_price_jpy')

                zero_stock_sold.append(sold_info)

        return zero_stock_sold


def main():
    parser = argparse.ArgumentParser(
        description='BASE注文一覧取得・販売済み在庫0商品の特定'
    )
    parser.add_argument(
        '--account',
        help='アカウントID（省略時は全アカウント）'
    )
    parser.add_argument(
        '--days',
        type=int,
        default=30,
        help='遡る日数（デフォルト: 30）'
    )
    parser.add_argument(
        '--list-orders',
        action='store_true',
        help='注文一覧を表示'
    )
    parser.add_argument(
        '--sold-zero-stock',
        action='store_true',
        help='販売済みで在庫0の商品を表示'
    )
    parser.add_argument(
        '--restore-stock',
        action='store_true',
        help='Amazon在庫ありの商品の在庫を1に復活'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='DRY RUNモード（実際の更新なし）'
    )

    args = parser.parse_args()

    fetcher = OrdersFetcher()
    account_manager = AccountManager()

    # アカウント一覧を取得
    if args.account:
        accounts = [{'id': args.account}]
    else:
        accounts = account_manager.get_active_accounts()

    all_zero_stock_sold = []

    for account in accounts:
        account_id = account['id']

        print()
        print("=" * 70)
        print(f"アカウント: {account_id}")
        print("=" * 70)

        if args.list_orders:
            # 注文一覧を表示
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=args.days)).strftime('%Y-%m-%d')

            orders = fetcher.get_orders(
                account_id=account_id,
                start_date=start_date,
                end_date=end_date
            )

            print(f"\n注文一覧（過去{args.days}日間）: {len(orders)}件")
            print("-" * 70)

            for order in orders[:20]:  # 最大20件表示
                ordered_ts = order.get('ordered', 0)
                ordered_date = datetime.fromtimestamp(ordered_ts).strftime('%Y-%m-%d %H:%M') if ordered_ts else 'N/A'
                status = order.get('dispatch_status', 'N/A')
                total = order.get('total', 0)

                print(f"  {ordered_date} | {status:<12} | {total:>8}円 | {order.get('unique_key', '')[:20]}")

            if len(orders) > 20:
                print(f"  ... 他 {len(orders) - 20}件")

        if args.sold_zero_stock or args.restore_stock:
            # 販売済みで在庫0の商品を取得
            zero_stock_sold = fetcher.get_sold_items_with_zero_stock(
                account_id=account_id,
                days=args.days
            )

            for item in zero_stock_sold:
                item['account_id'] = account_id

            all_zero_stock_sold.extend(zero_stock_sold)

            print(f"\n販売済みで在庫0の商品: {len(zero_stock_sold)}件")
            print("-" * 100)
            print(f"{'No':>3} | {'ASIN':<12} | {'Item ID':<10} | {'販売数':>4} | {'Amazon在庫':>10} | 商品名")
            print("-" * 100)

            for i, item in enumerate(zero_stock_sold, 1):
                asin = item.get('asin', 'N/A')
                item_id = item.get('item_id', 'N/A')
                amount = item.get('amount', 0)
                amazon_stock = '在庫あり' if item.get('amazon_in_stock') else '在庫なし'
                title = item.get('title', '')[:40]

                print(f"{i:>3} | {asin:<12} | {item_id:<10} | {amount:>4} | {amazon_stock:>10} | {title}")

            print("-" * 100)

    # 在庫復活処理
    if args.restore_stock and all_zero_stock_sold:
        # Amazon在庫ありの商品のみ対象
        restore_targets = [item for item in all_zero_stock_sold if item.get('amazon_in_stock')]

        print()
        print("=" * 70)
        print(f"在庫復活対象: {len(restore_targets)}件（Amazon在庫あり）")
        print("=" * 70)

        if args.dry_run:
            print("[DRY RUN] 実際の更新は行いません")

        restored_count = 0
        error_count = 0

        for item in restore_targets:
            account_id = item['account_id']
            item_id = item['item_id']
            asin = item.get('asin', 'N/A')

            print(f"  [{account_id}] {asin} (item_id: {item_id})")

            if args.dry_run:
                print(f"    → DRY RUN: 在庫1に復活（スキップ）")
                restored_count += 1
                continue

            try:
                base_client = BaseAPIClient(
                    account_id=account_id,
                    account_manager=account_manager
                )

                base_client.update_item(
                    item_id=item_id,
                    updates={'stock': 1}
                )

                print(f"    → 在庫1に復活成功")
                restored_count += 1
                time.sleep(0.1)

            except Exception as e:
                print(f"    → エラー: {e}")
                error_count += 1

        print()
        print(f"復活完了: {restored_count}件")
        if error_count > 0:
            print(f"エラー: {error_count}件")


if __name__ == '__main__':
    main()
