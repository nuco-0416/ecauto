# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
レガシーシステムからのデータ移行スクリプト

レガシーシステム（C:/Users/hiroo/Documents/ama-cari/ebay_pj）の
products_master.csvを読み取り、新システムのmaster.dbに移行する

使用方法:
    # ドライラン（実際の書き込みなし）
    python platforms/ebay/scripts/migrate_from_legacy.py --dry-run

    # 本番実行
    python platforms/ebay/scripts/migrate_from_legacy.py

    # 特定のCSVファイルを指定
    python platforms/ebay/scripts/migrate_from_legacy.py --csv-path /path/to/products_master.csv
"""

import sys
import csv
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List

# Windows環境対応
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(project_root))

from inventory.core.master_db import MasterDB

# ロガー設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class LegacyDataMigrator:
    """
    レガシーデータ移行クラス
    """

    # デフォルトのレガシーCSVパス
    DEFAULT_LEGACY_CSV_PATH = r"C:\Users\hiroo\Documents\ama-cari\ebay_pj\data\products_master.csv"

    def __init__(self, platform: str = 'ebay', account_id: str = 'ebay_account_1'):
        """
        初期化

        Args:
            platform: プラットフォーム名（デフォルト: 'ebay'）
            account_id: アカウントID（デフォルト: 'ebay_account_1'）
        """
        self.platform = platform
        self.account_id = account_id
        self.master_db = MasterDB()

        # 統計情報
        self.stats = {
            'total_rows': 0,
            'products_added': 0,
            'products_updated': 0,
            'products_skipped': 0,
            'listings_added': 0,
            'listings_skipped': 0,
            'errors': 0,
            'errors_detail': [],
        }

    def migrate_products_master(self, csv_path: str, dry_run: bool = False) -> Dict[str, Any]:
        """
        products_master.csvを読み込み、master.dbに移行

        Args:
            csv_path: CSVファイルのパス
            dry_run: Trueの場合、実際の書き込みは行わない

        Returns:
            dict: 統計情報
        """
        logger.info("=" * 70)
        logger.info("レガシーデータ移行処理を開始")
        logger.info("=" * 70)
        logger.info(f"CSVパス: {csv_path}")
        logger.info(f"プラットフォーム: {self.platform}")
        logger.info(f"アカウントID: {self.account_id}")
        logger.info(f"実行モード: {'DRY RUN（実際の書き込みなし）' if dry_run else '本番実行'}")
        logger.info(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("")

        # CSVファイル存在確認
        csv_file = Path(csv_path)
        if not csv_file.exists():
            logger.error(f"CSVファイルが見つかりません: {csv_path}")
            return self.stats

        # CSV読み込み（UTF-8 BOM対応）
        logger.info("CSVファイルを読み込み中...")
        try:
            with open(csv_file, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)

                for row_num, row in enumerate(reader, start=2):  # ヘッダーが1行目なので2から
                    self.stats['total_rows'] += 1

                    try:
                        self._process_row(row, dry_run)
                    except Exception as e:
                        logger.error(f"行 {row_num} の処理中にエラー: {e}")
                        self.stats['errors'] += 1
                        self.stats['errors_detail'].append({
                            'row_num': row_num,
                            'asin': row.get('ASIN', 'N/A'),
                            'error': str(e)
                        })

                    # 進捗表示（100行ごと）
                    if self.stats['total_rows'] % 100 == 0:
                        logger.info(f"  処理済み: {self.stats['total_rows']}行")

        except Exception as e:
            logger.error(f"CSVファイルの読み込み中にエラー: {e}")
            import traceback
            traceback.print_exc()
            return self.stats

        # サマリー表示
        self._print_summary()

        return self.stats

    def _process_row(self, row: Dict[str, str], dry_run: bool):
        """
        1行分のデータを処理

        Args:
            row: CSV行データ（辞書）
            dry_run: Trueの場合、実際の書き込みは行わない
        """
        asin = row.get('ASIN', '').strip()
        if not asin:
            logger.warning(f"  [SKIP] ASINが空です")
            self.stats['products_skipped'] += 1
            return

        # 商品データを準備
        title_ja = row.get('商品名', '').strip()
        description_ja = row.get('商品説明', '').strip()
        brand = row.get('brand', '').strip()
        image_url = row.get('Image URL', '').strip()

        # 画像URLをJSON配列に変換
        images = []
        if image_url:
            images = [image_url]

        # Amazon価格（日本円）
        amazon_price_jpy = None
        price_str = row.get('価格（日本円）', '').strip()
        if price_str:
            try:
                amazon_price_jpy = int(float(price_str))
            except ValueError:
                logger.warning(f"  [WARN] {asin}: 価格の変換に失敗: {price_str}")

        # Amazon在庫状況
        amazon_in_stock = None
        stock_status = row.get('在庫状況', '').strip()
        if stock_status:
            # "在庫あり" → True, "在庫なし" → False
            amazon_in_stock = '在庫あり' in stock_status or 'In Stock' in stock_status

        # ドライランモードでない場合のみDB操作を実行
        if not dry_run:
            # 既存商品をチェック
            existing_product = self.master_db.get_product(asin)

            # 商品を追加/更新
            try:
                success = self.master_db.add_product(
                    asin=asin,
                    title_ja=title_ja,
                    description_ja=description_ja,
                    brand=brand,
                    images=images,
                    amazon_price_jpy=amazon_price_jpy,
                    amazon_in_stock=amazon_in_stock
                )

                if success:
                    if existing_product:
                        self.stats['products_updated'] += 1
                    else:
                        self.stats['products_added'] += 1
                else:
                    logger.warning(f"  [WARN] {asin}: 商品の追加/更新に失敗")
                    self.stats['errors'] += 1

            except Exception as e:
                logger.error(f"  [ERROR] {asin}: 商品の追加/更新中にエラー: {e}")
                self.stats['errors'] += 1
                self.stats['errors_detail'].append({
                    'asin': asin,
                    'error': f'商品追加/更新エラー: {str(e)}'
                })
                return
        else:
            # ドライランモードの場合は統計のみ更新
            logger.debug(f"  [DRY RUN] {asin}: {title_ja}")
            self.stats['products_added'] += 1

        # 出品情報を追加（dry_runチェックは_add_listing内で行う）
        self._add_listing(row, asin, dry_run)

    def _add_listing(self, row: Dict[str, str], asin: str, dry_run: bool):
        """
        出品情報を追加

        Args:
            row: CSV行データ
            asin: 商品ASIN
            dry_run: Trueの場合、実際の書き込みは行わない
        """
        sku = row.get('sku', '').strip()
        if not sku:
            # SKUが無い場合はスキップ
            logger.warning(f"  [SKIP] {asin}: SKUが空です")
            self.stats['listings_skipped'] += 1
            return

        # 販売価格（想定売価）
        selling_price = None
        price_str = row.get('想定売価', '').strip()
        if price_str:
            try:
                selling_price = float(price_str)
            except ValueError:
                logger.warning(f"  [WARN] {asin}: 想定売価の変換に失敗: {price_str}")

        # ドライランモードの場合は既存チェックをスキップ
        if dry_run:
            logger.debug(f"  [DRY RUN] {asin}: Listing追加 (SKU: {sku})")
            self.stats['listings_added'] += 1
            return

        # 既存の出品をチェック（ASIN優先、次にSKU）
        # データベース制約: ASIN + platform + account_id の組み合わせはUNIQUE
        existing_listing = None

        # 既存出品を検索
        all_listings = self.master_db.get_listings_by_account(
            platform=self.platform,
            account_id=self.account_id
        )

        for listing in all_listings:
            # 優先1: ASINが一致する場合（同じ商品の重複を防ぐ）
            if listing['asin'] == asin:
                existing_listing = listing
                logger.debug(f"  [SKIP] {asin}: 既に同じASINの出品が存在します (既存SKU: {listing['sku']}, 新SKU: {sku})")
                break
            # 優先2: SKUが一致する場合（念のため）
            elif listing['sku'] == sku:
                existing_listing = listing
                logger.debug(f"  [SKIP] {asin}: 同じSKUの出品が存在します (SKU: {sku})")
                break

        if existing_listing:
            self.stats['listings_skipped'] += 1
            return

        # 出品を追加
        try:
            # eBayの場合、通貨はUSD
            currency = 'USD' if self.platform == 'ebay' else 'JPY'

            listing_id = self.master_db.add_listing(
                asin=asin,
                platform=self.platform,
                account_id=self.account_id,
                sku=sku,
                selling_price=selling_price,
                currency=currency,
                status='pending'  # 初期状態はpending
            )

            if listing_id:
                self.stats['listings_added'] += 1
            else:
                logger.warning(f"  [WARN] {asin}: 出品の追加に失敗 (SKU: {sku})")
                self.stats['errors'] += 1

        except Exception as e:
            error_msg = str(e)

            # SKU UNIQUE制約違反の場合はスキップとして扱う（エラーとしてカウントしない）
            if 'UNIQUE constraint failed: listings.sku' in error_msg:
                logger.debug(f"  [SKIP] {asin}: SKU既に存在 (SKU: {sku})")
                self.stats['listings_skipped'] += 1
            else:
                # その他のエラー
                logger.error(f"  [ERROR] {asin}: 出品の追加中にエラー: {error_msg}")
                self.stats['errors'] += 1
                self.stats['errors_detail'].append({
                    'asin': asin,
                    'sku': sku,
                    'error': f'出品追加エラー: {error_msg}'
                })

    def _print_summary(self):
        """統計情報を表示"""
        logger.info("")
        logger.info("=" * 70)
        logger.info("移行結果サマリー")
        logger.info("=" * 70)
        logger.info(f"処理した行数: {self.stats['total_rows']}行")
        logger.info("")
        logger.info("商品 (products):")
        logger.info(f"  - 追加: {self.stats['products_added']}件")
        logger.info(f"  - 更新: {self.stats['products_updated']}件")
        logger.info(f"  - スキップ: {self.stats['products_skipped']}件")
        logger.info("")
        logger.info("出品 (listings):")
        logger.info(f"  - 追加: {self.stats['listings_added']}件")
        logger.info(f"  - スキップ: {self.stats['listings_skipped']}件")
        logger.info("")
        logger.info(f"エラー: {self.stats['errors']}件")

        if self.stats['errors_detail']:
            logger.error("")
            logger.error("エラー詳細（最大10件表示）:")
            for error in self.stats['errors_detail'][:10]:
                logger.error(f"  - {error}")

        logger.info("=" * 70)
        logger.info(f"終了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("")


def sync_existing_listings(account_id: str) -> Dict[str, Any]:
    """
    eBay APIから既存出品を取得し、master.dbと同期

    既存のeBay出品情報を取得して、master.dbのlistingsテーブルの
    platform_item_idフィールドを更新する

    Args:
        account_id: eBayアカウントID

    Returns:
        dict: 同期結果の統計情報
    """
    from platforms.ebay.accounts.manager import EbayAccountManager
    from platforms.ebay.core.api_client import EbayAPIClient

    logger.info("=" * 70)
    logger.info("既存eBay出品の同期処理を開始")
    logger.info("=" * 70)
    logger.info(f"アカウントID: {account_id}")
    logger.info(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("")

    # 統計情報
    stats = {
        'total_items': 0,
        'matched': 0,
        'updated': 0,
        'not_found_in_db': 0,
        'errors': 0,
        'errors_detail': [],
    }

    # アカウントマネージャー初期化
    account_manager = EbayAccountManager()
    master_db = MasterDB()

    # アカウント認証情報を取得
    credentials = account_manager.get_credentials(account_id)
    if not credentials:
        logger.error(f"eBayアカウント認証情報が見つかりません: {account_id}")
        return stats

    environment = account_manager.get_environment(account_id)

    # eBay APIクライアントを初期化
    try:
        ebay_client = EbayAPIClient(
            account_id=account_id,
            credentials=credentials,
            environment=environment
        )
    except Exception as e:
        logger.error(f"eBay APIクライアントの初期化に失敗: {e}")
        return stats

    # 全Inventory Itemsを取得
    logger.info("eBayから既存Inventory Itemsを取得中...")
    try:
        # eBay Inventory API: GET /sell/inventory/v1/inventory_item
        url = '/sell/inventory/v1/inventory_item'
        params = {'limit': 100}  # 1ページあたり100件

        all_inventory_items = []
        offset = 0

        while True:
            params['offset'] = offset
            response = ebay_client._make_request('GET', url, params=params)

            if not response:
                break

            # Inventory Itemsを取得
            items = response.get('inventoryItems', [])
            if not items:
                break

            all_inventory_items.extend(items)
            stats['total_items'] += len(items)

            # 次のページがあるかチェック
            total = response.get('total', 0)
            if offset + len(items) >= total:
                break

            offset += len(items)
            logger.info(f"  取得済み: {len(all_inventory_items)}件 / {total}件")

        logger.info(f"  合計取得数: {len(all_inventory_items)}件")

    except Exception as e:
        logger.error(f"Inventory Items取得エラー: {e}")
        import traceback
        traceback.print_exc()
        stats['errors'] += 1
        return stats

    # 各Inventory Itemについてmaster.dbと同期
    logger.info("\nmaster.dbと同期中...")
    for item in all_inventory_items:
        sku = item.get('sku')
        if not sku:
            continue

        try:
            # master.dbでSKUを検索
            listings = master_db.get_listings_by_account(
                platform='ebay',
                account_id=account_id
            )

            matching_listing = None
            for listing in listings:
                if listing['sku'] == sku:
                    matching_listing = listing
                    break

            if not matching_listing:
                # master.dbに存在しない（レガシーにない出品）
                logger.debug(f"  [NOT_IN_DB] SKU: {sku}")
                stats['not_found_in_db'] += 1
                continue

            # 一致するlistingが見つかった
            stats['matched'] += 1

            # eBay listing_idを取得（offersから）
            listing_id = None

            # Offerを取得してlisting_idを抽出
            offers_url = f'/sell/inventory/v1/offer'
            offers_params = {'sku': sku}
            offers_response = ebay_client._make_request('GET', offers_url, params=offers_params)

            if offers_response and offers_response.get('offers'):
                offers = offers_response['offers']
                if offers and len(offers) > 0:
                    # 最初のOfferのlisting_idを取得
                    first_offer = offers[0]
                    listing_id = first_offer.get('listingId')

            if not listing_id:
                logger.debug(f"  [NO_LISTING_ID] SKU: {sku}")
                continue

            # master.dbを更新
            master_db.update_listing(
                listing_id=matching_listing['id'],
                platform_item_id=listing_id,
                status='listed'  # 既存出品なのでstatusをlistedに
            )

            logger.info(f"  [UPDATED] SKU: {sku} → listing_id: {listing_id}")
            stats['updated'] += 1

        except Exception as e:
            logger.error(f"  [ERROR] SKU: {sku} - {e}")
            stats['errors'] += 1
            stats['errors_detail'].append({
                'sku': sku,
                'error': str(e)
            })

    # サマリー表示
    logger.info("")
    logger.info("=" * 70)
    logger.info("同期結果サマリー")
    logger.info("=" * 70)
    logger.info(f"eBayから取得したInventory Items: {stats['total_items']}件")
    logger.info(f"master.dbと一致: {stats['matched']}件")
    logger.info(f"platform_item_id更新: {stats['updated']}件")
    logger.info(f"master.dbに未登録: {stats['not_found_in_db']}件")
    logger.info(f"エラー: {stats['errors']}件")

    if stats['errors_detail']:
        logger.error("\nエラー詳細（最大10件表示）:")
        for error in stats['errors_detail'][:10]:
            logger.error(f"  - {error}")

    logger.info("=" * 70)
    logger.info(f"終了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("")

    return stats


def main():
    """メイン処理"""
    import argparse

    parser = argparse.ArgumentParser(
        description='レガシーシステムからのデータ移行'
    )
    parser.add_argument(
        '--csv-path',
        default=LegacyDataMigrator.DEFAULT_LEGACY_CSV_PATH,
        help=f'CSVファイルのパス（デフォルト: {LegacyDataMigrator.DEFAULT_LEGACY_CSV_PATH}）'
    )
    parser.add_argument(
        '--platform',
        default='ebay',
        help='プラットフォーム名（デフォルト: ebay）'
    )
    parser.add_argument(
        '--account-id',
        default='ebay_account_1',
        help='アカウントID（デフォルト: ebay_account_1）'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='DRY RUNモード（実際の書き込みは行わない）'
    )
    parser.add_argument(
        '--sync-existing',
        action='store_true',
        help='既存eBay出品の同期を実行（CSVインポートをスキップ）'
    )

    args = parser.parse_args()

    # 既存出品の同期モード
    if args.sync_existing:
        stats = sync_existing_listings(account_id=args.account_id)

        # 終了コード
        if stats['errors'] > 0:
            logger.warning(f"エラーが {stats['errors']}件 発生しました")
            sys.exit(1)
        else:
            logger.info("✅ 既存出品の同期が正常に完了しました")
            sys.exit(0)

    # データ移行処理実行（通常モード）
    migrator = LegacyDataMigrator(
        platform=args.platform,
        account_id=args.account_id
    )

    stats = migrator.migrate_products_master(
        csv_path=args.csv_path,
        dry_run=args.dry_run
    )

    # 終了コード
    if stats['errors'] > 0:
        logger.warning(f"エラーが {stats['errors']}件 発生しました")
        sys.exit(1)
    else:
        logger.info("✅ データ移行が正常に完了しました")
        sys.exit(0)


if __name__ == '__main__':
    main()
