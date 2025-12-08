#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eBay全商品同期スクリプト

eBay Inventory APIから全商品を取得してMaster DBに同期します。
- 在庫切れ（quantity=0）の商品も含む全商品を取得
- Master DBのlistingsテーブルを更新

使用例:
    # 全商品を同期
    python platforms/ebay/scripts/sync_all_inventory.py

    # dry-runモード（DB更新なし）
    python platforms/ebay/scripts/sync_all_inventory.py --dry-run

    # 最大100件まで取得（テスト用）
    python platforms/ebay/scripts/sync_all_inventory.py --max-items 100
"""

import sys
import logging
from pathlib import Path
from typing import Dict, Any, List
import argparse

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


class EbayInventorySync:
    """eBay全商品同期クラス"""

    def __init__(self, dry_run: bool = False):
        """
        初期化

        Args:
            dry_run: Trueの場合、実際の更新は行わない
        """
        self.master_db = MasterDB()
        self.account_manager = EbayAccountManager()
        self.dry_run = dry_run

        # 統計情報
        self.stats = {
            'total_items': 0,
            'new_items': 0,
            'updated_items': 0,
            'zero_stock_items': 0,
            'errors': 0,
            'errors_detail': [],
        }

    def sync_account_inventory(self, account_id: str, max_items: int = None):
        """
        1アカウントの全商品を同期

        Args:
            account_id: eBayアカウントID
            max_items: 最大取得件数（Noneの場合は全件）
        """
        account = self.account_manager.get_account(account_id)
        if not account:
            logger.error(f"アカウント {account_id} が見つかりません")
            return

        logger.info("")
        logger.info("=" * 70)
        logger.info(f"【eBay全商品同期】アカウント: {account.get('name', account_id)} ({account_id})")
        logger.info("=" * 70)

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

        # 全Inventory Itemsを取得
        logger.info("\neBay Inventory APIから全商品を取得中...")
        try:
            inventory_items = ebay_client.get_all_inventory_items_paginated(max_items=max_items)
            logger.info(f"取得完了: {len(inventory_items)}件")
        except Exception as e:
            logger.error(f"Inventory Items取得エラー: {e}")
            self.stats['errors'] += 1
            return

        if not inventory_items:
            logger.warning("商品が見つかりませんでした")
            return

        self.stats['total_items'] = len(inventory_items)

        # 各商品をMaster DBに同期
        logger.info("\nMaster DBに同期中...")
        for i, item in enumerate(inventory_items, 1):
            self._sync_inventory_item(item, account_id)

            if i % 10 == 0:
                logger.info(f"  進捗: {i}/{len(inventory_items)}件")

    def _sync_inventory_item(self, item: Dict[str, Any], account_id: str):
        """
        1つの商品をMaster DBに同期

        Args:
            item: eBay Inventory Item
            account_id: アカウントID
        """
        sku = item.get('sku')
        if not sku:
            logger.warning("SKUが見つかりません、スキップ")
            self.stats['errors'] += 1
            return

        # 在庫数を取得
        quantity = item.get('availability', {}).get('shipToLocationAvailability', {}).get('quantity', 0)

        # 在庫0の商品をカウント
        if quantity == 0:
            self.stats['zero_stock_items'] += 1

        # SKUからASINを抽出（s-ASIN-timestamp形式を想定）
        asin = self._extract_asin_from_sku(sku)
        if not asin:
            logger.warning(f"SKU {sku} からASINを抽出できません、スキップ")
            self.stats['errors'] += 1
            return

        # Master DBに既存レコードがあるか確認（SKUで検索）
        existing_listing = self._get_existing_listing(sku, account_id)

        if existing_listing:
            # 更新
            self._update_listing(existing_listing['id'], quantity)
            self.stats['updated_items'] += 1
        else:
            # 新規登録（同じASINで既にlistingがある場合はスキップ）
            if self._asin_already_listed(asin, account_id):
                logger.debug(f"  [SKIP] ASIN {asin} は既に別のSKUで登録済み、スキップ")
                self.stats['updated_items'] += 1  # 既存として扱う
            else:
                self._create_listing(asin, sku, account_id, quantity, item)
                self.stats['new_items'] += 1

    def _extract_asin_from_sku(self, sku: str) -> str:
        """
        SKUからASINを抽出

        Args:
            sku: SKU（例: s-B083M6K95X-20251027_0456）

        Returns:
            str: ASIN（例: B083M6K95X）
        """
        # s-ASIN-timestamp形式を想定
        parts = sku.split('-')
        if len(parts) >= 2:
            return parts[1]
        return None

    def _get_existing_listing(self, sku: str, account_id: str) -> Dict[str, Any]:
        """
        既存のlistingレコードを取得

        Args:
            sku: SKU
            account_id: アカウントID

        Returns:
            dict or None: 既存レコード
        """
        with self.master_db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT *
                FROM listings
                WHERE sku = ? AND platform = 'ebay' AND account_id = ?
            ''', (sku, account_id))

            row = cursor.fetchone()
            if row:
                return dict(row)
        return None

    def _asin_already_listed(self, asin: str, account_id: str) -> bool:
        """
        同じASINで既にlistingがあるかチェック

        Args:
            asin: ASIN
            account_id: アカウントID

        Returns:
            bool: 既にlistingがある場合True
        """
        with self.master_db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) as count
                FROM listings
                WHERE asin = ? AND platform = 'ebay' AND account_id = ?
            ''', (asin, account_id))

            row = cursor.fetchone()
            return row['count'] > 0 if row else False

    def _update_listing(self, listing_id: int, quantity: int):
        """
        listingレコードを更新

        Args:
            listing_id: ListingのID
            quantity: eBay在庫数
        """
        if self.dry_run:
            logger.debug(f"  [DRY RUN] Listing ID {listing_id} の在庫数を {quantity} に更新")
            return

        with self.master_db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE listings
                SET in_stock_quantity = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (quantity, listing_id))
            conn.commit()

    def _create_listing(self, asin: str, sku: str, account_id: str, quantity: int, item: Dict[str, Any]):
        """
        新規listingレコードを作成

        Args:
            asin: ASIN
            sku: SKU
            account_id: アカウントID
            quantity: eBay在庫数
            item: eBay Inventory Item
        """
        if self.dry_run:
            logger.debug(f"  [DRY RUN] 新規Listing作成: {asin} (SKU: {sku}, 在庫: {quantity})")
            return

        # 商品情報を取得
        product = self.master_db.get_product(asin)
        if not product:
            logger.warning(f"  [WARN] ASIN {asin} がMaster DBに存在しません、Listingのみ作成")

        # Listingを作成（価格情報がない場合は0で登録）
        with self.master_db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO listings (
                    asin, platform, account_id, sku,
                    selling_price, currency, in_stock_quantity,
                    status, visibility, listed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (
                asin,
                'ebay',
                account_id,
                sku,
                0.0,  # 価格は後で更新
                'USD',
                quantity,
                'listed',  # 在庫数に応じて後で調整可能
                'public'
            ))
            conn.commit()

    def print_summary(self):
        """統計情報を表示"""
        logger.info("\n" + "=" * 70)
        logger.info("処理結果サマリー")
        logger.info("=" * 70)
        logger.info(f"取得した商品数: {self.stats['total_items']}件")
        logger.info(f"新規登録: {self.stats['new_items']}件")
        logger.info(f"更新: {self.stats['updated_items']}件")
        logger.info(f"在庫0の商品: {self.stats['zero_stock_items']}件")
        logger.info(f"エラー: {self.stats['errors']}件")

        if self.stats['errors_detail']:
            logger.error("\nエラー詳細:")
            for error in self.stats['errors_detail'][:10]:
                logger.error(f"  - {error}")

        logger.info("=" * 70)

    def sync_all_accounts(self, max_items: int = None):
        """
        全アカウントの商品を同期

        Args:
            max_items: 最大取得件数（Noneの場合は全件）
        """
        logger.info("\n" + "=" * 70)
        logger.info("eBay全商品同期処理を開始")
        logger.info("=" * 70)
        logger.info(f"実行モード: {'DRY RUN（実際の更新なし）' if self.dry_run else '本番実行'}")
        if max_items:
            logger.info(f"最大取得件数: {max_items}件")

        # アクティブなアカウント取得
        accounts = self.account_manager.get_active_accounts()
        if not accounts:
            logger.error("エラー: アクティブなアカウントが見つかりません")
            return

        logger.info(f"アクティブアカウント数: {len(accounts)}件")

        # 各アカウントを処理
        for account in accounts:
            account_id = account['id']

            try:
                self.sync_account_inventory(account_id, max_items)
            except Exception as e:
                logger.error(f"エラー: アカウント {account_id} の処理中にエラー: {e}")
                self.stats['errors'] += 1
                self.stats['errors_detail'].append({
                    'account_id': account_id,
                    'error': str(e)
                })

        # 統計表示
        self.print_summary()


def main():
    """メイン処理"""
    parser = argparse.ArgumentParser(
        description='eBay全商品をMaster DBに同期'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='DRY RUNモード（実際の更新は行わない）'
    )
    parser.add_argument(
        '--account',
        help='特定のアカウントIDのみ処理（省略時は全アカウント）'
    )
    parser.add_argument(
        '--max-items',
        type=int,
        default=None,
        help='テスト用：最大取得件数（省略時は全件）'
    )

    args = parser.parse_args()

    # 同期処理実行
    sync = EbayInventorySync(dry_run=args.dry_run)

    if args.account:
        # 特定アカウントのみ
        sync.sync_account_inventory(
            account_id=args.account,
            max_items=args.max_items
        )
        sync.print_summary()
    else:
        # 全アカウント
        sync.sync_all_accounts(max_items=args.max_items)

    # 終了コード
    if sync.stats['errors'] > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
