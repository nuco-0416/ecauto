# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
eBay出品状態同期スクリプト

eBayプロダクション環境の出品一覧を取得し、ローカルDBと同期する
"""

import sys
import logging
from pathlib import Path
from typing import Dict, Any, List

# Windows環境対応
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(project_root))

from inventory.core.master_db import MasterDB
from platforms.ebay.accounts.manager import EbayAccountManager
from platforms.ebay.core.api_client import EbayAPIClient

# ロガー設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class EbayListingSync:
    """
    eBay出品状態同期クラス
    """

    def __init__(self):
        """初期化"""
        logger.info("eBay出品状態同期処理を初期化中...")

        self.master_db = MasterDB()
        self.account_manager = EbayAccountManager()

        # 統計情報
        self.stats = {
            'total_offers': 0,
            'updated': 0,
            'new': 0,
            'errors': 0,
        }

    def sync_account_listings(self, account_id: str, max_items: int = None):
        """
        1アカウントの出品状態を同期

        Args:
            account_id: eBayアカウントID
            max_items: 取得する最大アイテム数（Noneの場合は全件取得）
        """
        account = self.account_manager.get_account(account_id)
        if not account:
            logger.error(f"アカウント {account_id} が見つかりません")
            return

        logger.info("")
        logger.info("┌" + "─" * 68 + "┐")
        logger.info(f"│ 【eBay出品同期】アカウント: {account.get('name', account_id)} ({account_id})" + " " * (68 - len(f" 【eBay出品同期】アカウント: {account.get('name', account_id)} ({account_id})") - 2) + "│")
        logger.info("└" + "─" * 68 + "┘")

        # eBay APIクライアント作成
        credentials = self.account_manager.get_credentials(account_id)
        if not credentials:
            logger.error(f"eBayアカウント認証情報が見つかりません: {account_id}")
            self.stats['errors'] += 1
            return

        environment = self.account_manager.get_environment(account_id)

        try:
            ebay_client = EbayAPIClient(
                account_id=account_id,
                credentials=credentials,
                environment=environment
            )
        except Exception as e:
            logger.error(f"eBay APIクライアントの初期化に失敗: {e}")
            self.stats['errors'] += 1
            return

        # eBayから全inventory item一覧を取得
        if max_items:
            logger.info(f"eBayからInventory Item一覧を取得中（最大{max_items}件）...")
        else:
            logger.info(f"eBayからInventory Item一覧を取得中（全件）...")

        try:
            inventory_items = ebay_client.get_all_inventory_items(limit=200)

            # max_itemsが指定されている場合は件数を制限
            if max_items and len(inventory_items) > max_items:
                logger.info(f"取得件数を{len(inventory_items)}件から{max_items}件に制限します")
                inventory_items = inventory_items[:max_items]

            logger.info(f"Inventory Items取得件数: {len(inventory_items)}件")
        except Exception as e:
            logger.error(f"Inventory Item一覧の取得に失敗: {e}")
            self.stats['errors'] += 1
            return

        # 各SKUのOfferを取得してDBに同期
        logger.info("\n各SKUのOffer情報を取得中...")
        for item in inventory_items:
            sku = item.get('sku')
            if not sku:
                logger.warning("  [SKIP] SKUが見つかりません")
                continue

            try:
                # SKUに紐づくOfferを取得
                offers = ebay_client.get_offers_by_sku(sku)

                if offers:
                    # 複数のOfferがある場合は最初のもののみを使用
                    offer = offers[0]
                    if len(offers) > 1:
                        logger.warning(f"  [WARNING] {sku} - 複数のOffer({len(offers)}件)が見つかりました。最初のOfferのみを使用します")

                    self._sync_offer(offer, account_id)
                    self.stats['total_offers'] += 1
                else:
                    logger.info(f"  [NO OFFER] {sku} - Offerなし")

            except Exception as e:
                logger.error(f"  [ERROR] {sku} - Offer取得エラー: {e}")
                self.stats['errors'] += 1

    def _sync_offer(self, offer: Dict[str, Any], account_id: str):
        """
        1つのofferをDBに同期

        Args:
            offer: eBay offer情報
            account_id: アカウントID
        """
        try:
            sku = offer.get('sku')
            offer_id = offer.get('offerId')
            listing_id = offer.get('listingId')  # eBay listing ID

            # 価格情報
            pricing_summary = offer.get('pricingSummary', {})
            price_value = pricing_summary.get('price', {}).get('value')
            price_currency = pricing_summary.get('price', {}).get('currency')

            # ステータス
            status_str = offer.get('status', 'UNPUBLISHED')

            # ステータスをマッピング
            # PUBLISHED -> listed, UNPUBLISHED -> pending
            if status_str == 'PUBLISHED':
                status = 'listed'
            else:
                status = 'pending'

            # デバッグ用：eBay APIから取得した実際のstatus値をログ出力
            logger.debug(f"  [DEBUG] {sku} - eBay API status: {status_str} -> DB status: {status}")

            # 数量
            available_quantity = offer.get('availableQuantity', 0)

            if not sku:
                logger.warning(f"  [SKIP] SKUが見つかりません: offer_id={offer_id}")
                return

            # SKUからASINを抽出（SKU形式: s-{asin}-{timestamp}）
            parts = sku.split('-')
            if len(parts) >= 2:
                asin = parts[1]
            else:
                asin = sku

            # ASINベースで既存レコードを検索
            # 同じASIN + platform='ebay' + account_idのレコードを探す
            # レガシーデータ（eBay, ebay_main）も含めて検索
            with self.master_db.get_connection() as conn:
                cursor = conn.execute("""
                    SELECT id, sku, platform, account_id FROM listings
                    WHERE asin = ?
                    ORDER BY
                        CASE
                            WHEN platform = 'ebay' AND account_id = ? THEN 1
                            ELSE 2
                        END
                    LIMIT 1
                """, (asin, account_id))

                existing = cursor.fetchone()

                if existing:
                    # 既存レコードを更新（SKU、platform、account_idも含めてすべて更新）
                    listing_id_db = existing[0]
                    old_sku = existing[1]
                    old_platform = existing[2]
                    old_account = existing[3]

                    conn.execute("""
                        UPDATE listings
                        SET sku = ?,
                            platform = 'ebay',
                            account_id = ?,
                            status = ?,
                            selling_price = ?,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (sku, account_id, status, float(price_value) if price_value else 0.0, listing_id_db))

                    # eBayメタデータ：古いSKUのレコードを削除
                    conn.execute("""
                        DELETE FROM ebay_listing_metadata
                        WHERE sku = ?
                    """, (old_sku,))

                    # 新しいSKUでメタデータを作成
                    conn.execute("""
                        INSERT OR REPLACE INTO ebay_listing_metadata (
                            sku, offer_id, listing_id
                        ) VALUES (?, ?, ?)
                    """, (sku, offer_id, listing_id))

                    # ログ出力（レガシーデータ統合の場合は明示）
                    if old_platform != 'ebay' or old_account != account_id:
                        logger.info(f"  [UPDATE+統合] {sku} -> {status} (${price_value}) [旧:{old_platform}/{old_account}]")
                    elif old_sku != sku:
                        logger.info(f"  [UPDATE+SKU更新] {sku} -> {status} (${price_value}) [旧SKU:{old_sku}]")
                    else:
                        logger.info(f"  [UPDATE] {sku} -> {status} (${price_value})")

                    self.stats['updated'] += 1
                else:
                    # 新規作成
                    conn.execute("""
                        INSERT INTO listings (
                            asin, sku, platform, account_id, status, selling_price
                        ) VALUES (?, ?, 'ebay', ?, ?, ?)
                    """, (asin, sku, account_id, status, float(price_value) if price_value else 0.0))

                    # eBayメタデータも作成
                    conn.execute("""
                        INSERT OR REPLACE INTO ebay_listing_metadata (
                            sku, offer_id, listing_id
                        ) VALUES (?, ?, ?)
                    """, (sku, offer_id, listing_id))

                    logger.info(f"  [NEW] {sku} -> {status} (${price_value})")
                    self.stats['new'] += 1

        except Exception as e:
            sku_info = offer.get('sku', 'UNKNOWN') if offer else 'UNKNOWN'
            logger.error(f"  [ERROR] {sku_info} - offer同期エラー: {e}")
            self.stats['errors'] += 1

    def sync_all_accounts(self):
        """
        全アカウントの出品状態を同期
        """
        logger.info("\n" + "=" * 70)
        logger.info("eBay出品状態同期処理を開始")
        logger.info("=" * 70)

        # アクティブなアカウント取得
        accounts = self.account_manager.get_active_accounts()
        if not accounts:
            logger.error("エラー: アクティブなアカウントが見つかりません")
            return self.stats

        logger.info(f"アクティブアカウント数: {len(accounts)}件\n")

        # 各アカウントを処理
        for account in accounts:
            account_id = account['id']

            try:
                self.sync_account_listings(account_id)
            except Exception as e:
                logger.error(f"エラー: アカウント {account_id} の処理中にエラー: {e}")
                self.stats['errors'] += 1

        # 統計表示
        self._print_summary()

        return self.stats

    def _print_summary(self):
        """統計情報を表示"""
        logger.info("\n" + "=" * 70)
        logger.info("処理結果サマリー")
        logger.info("=" * 70)
        logger.info(f"eBay出品数: {self.stats['total_offers']}件")
        logger.info(f"  - 更新: {self.stats['updated']}件")
        logger.info(f"  - 新規: {self.stats['new']}件")
        logger.info(f"エラー: {self.stats['errors']}件")
        logger.info("=" * 70)
        logger.info("")


def main():
    """メイン処理"""
    import argparse

    parser = argparse.ArgumentParser(
        description='eBay出品状態をローカルDBと同期'
    )
    parser.add_argument(
        '--account',
        help='特定のアカウントIDのみ処理（省略時は全アカウント）'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='デバッグログを有効化'
    )
    parser.add_argument(
        '--max-items',
        type=int,
        default=None,
        help='取得する最大アイテム数（デフォルト: 全件取得）'
    )

    args = parser.parse_args()

    # デバッグモードの場合、ログレベルを変更
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)

    # 同期処理実行
    sync = EbayListingSync()

    if args.account:
        # 特定アカウントのみ
        sync.sync_account_listings(account_id=args.account, max_items=args.max_items)
        sync._print_summary()
    else:
        # 全アカウント（全アカウント処理時もmax_items適用）
        sync.sync_all_accounts()

    # 終了コード
    if sync.stats['errors'] > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
