"""
出品連携スクリプト

sourcing_candidatesから商品情報を取得し、master.dbに登録して出品キューに追加する

Phase 1: 手動実行版
- daemon停止確認が必要
- SP-API使用のため、約20分/2000件（バッチ処理想定）の処理時間
"""

import sys
import os
import sqlite3
import random
import argparse
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from integrations.amazon.sp_api_client import AmazonSPAPIClient
from inventory.core.master_db import MasterDB
from inventory.core.product_manager import ProductManager
from inventory.core.listing_manager import ListingManager
from inventory.core.prohibited_item_checker import ProhibitedItemChecker
from inventory.core.blocklist_manager import BlocklistManager
from common.pricing import PriceCalculator
from scheduler.queue_manager import UploadQueueManager
from shared.utils.sku_generator import generate_sku
from shared.utils.logger import setup_logger


class CandidateImporter:
    """
    sourcing_candidatesからmaster.dbへの連携クラス
    """

    def __init__(self, limit: Optional[int] = None, dry_run: bool = False, account_limits: Optional[Dict[str, int]] = None, check_prohibited: bool = True, add_to_listings: bool = True, add_to_queue: bool = True):
        """
        Args:
            limit: 処理する最大件数（Noneの場合は全件）
            dry_run: Trueの場合、実際の登録は行わず確認のみ
            account_limits: アカウント別の追加件数指定（例: {'base_account_1': 989, 'base_account_2': 400}）
            check_prohibited: 禁止商品チェックを有効にする（デフォルト: True）
            add_to_listings: Trueの場合、listingsテーブルに追加（デフォルト: True）
            add_to_queue: Trueの場合、upload_queueに追加（デフォルト: True）
        """
        self.limit = limit
        self.dry_run = dry_run
        self.account_limits = account_limits
        self.check_prohibited = check_prohibited
        self.add_to_listings = add_to_listings
        self.add_to_queue = add_to_queue

        # ロガーを設定（ファイルとコンソール両方に出力）
        self.logger = setup_logger('import_candidates_to_master', console_output=True)

        # データベースパス
        self.sourcing_db_path = project_root / 'sourcing' / 'data' / 'sourcing.db'

        # MasterDB初期化
        self.master_db = MasterDB()

        # ProductManager初期化
        self.product_manager = ProductManager(master_db=self.master_db)

        # ListingManager初期化
        self.listing_manager = ListingManager(master_db=self.master_db)

        # PriceCalculator初期化（価格決定モジュール）
        self.price_calculator = PriceCalculator()

        # UploadQueueManager初期化
        self.queue_manager = UploadQueueManager()

        # 禁止商品チェッカー初期化
        if self.check_prohibited:
            self.prohibited_checker = ProhibitedItemChecker()
        else:
            self.prohibited_checker = None

        # ブロックリストマネージャー初期化
        self.blocklist_manager = BlocklistManager()

        # SP-API認証情報を環境変数から取得
        load_dotenv(project_root / '.env')
        sp_api_credentials = {
            'refresh_token': os.getenv('REFRESH_TOKEN'),
            'lwa_app_id': os.getenv('LWA_APP_ID'),
            'lwa_client_secret': os.getenv('LWA_CLIENT_SECRET')
        }

        # SP-APIClient初期化
        self.sp_api_client = AmazonSPAPIClient(sp_api_credentials)

        # アカウント情報をaccount_config.jsonから取得（アクティブなアカウントのみ）
        self.accounts = self._load_active_accounts()

        # 統計情報
        self.stats = {
            'total_asins': 0,
            'fetched_count': 0,
            'failed_fetch_count': 0,
            'added_to_products': 0,
            'added_to_listings': 0,
            'added_to_queue': 0,
            'failed_queue_count': 0,
            'updated_status_count': 0
        }

    def _load_active_accounts(self) -> List[str]:
        """
        account_config.jsonからアクティブなアカウントのみを読み込む

        Returns:
            List[str]: アクティブなアカウントIDのリスト
        """
        config_path = project_root / 'platforms' / 'base' / 'accounts' / 'account_config.json'

        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        active_accounts = [
            account['id']
            for account in config['accounts']
            if account.get('active', False)
        ]

        if not active_accounts:
            self.logger.warning("アクティブなアカウントが見つかりません")
            return []

        return active_accounts

    def run(self):
        """メイン処理"""
        self.logger.info("=" * 70)
        self.logger.info("出品連携スクリプト - sourcing_candidates → master.db")
        self.logger.info("=" * 70)
        self.logger.info(f"実行モード: {'DRY RUN（確認のみ）' if self.dry_run else '本番実行'}")

        # account_limitsが指定されている場合、limitを自動計算
        if self.account_limits:
            calculated_limit = sum(self.account_limits.values())
            if self.limit is None or self.limit > calculated_limit:
                self.limit = calculated_limit
            self.logger.info(f"処理件数制限: {self.limit}件（アカウント別指定: {self.account_limits}）")
        else:
            self.logger.info(f"処理件数制限: {self.limit if self.limit else '全件'}")

        self.logger.info(f"対象アカウント: {', '.join(self.accounts)}")

        # 登録対象テーブルの表示
        tables_to_register = []
        if self.add_to_listings:
            tables_to_register.extend(['products', 'listings'])
            if self.add_to_queue:
                tables_to_register.append('upload_queue')
        else:
            tables_to_register.append('products')
        self.logger.info(f"登録対象テーブル: {' + '.join(tables_to_register)}")

        self.logger.info("=" * 70)

        # 1. sourcing_candidatesから未処理ASIN取得
        asins = self._get_candidate_asins()
        if not asins:
            self.logger.info("処理対象のASINがありません")
            return

        self.stats['total_asins'] = len(asins)
        self.logger.info(f"[1/6] 候補ASIN取得完了: {len(asins)}件")

        if self.dry_run:
            self.logger.info("[DRY RUN] 最初の10件を表示:")
            for i, asin in enumerate(asins[:10], 1):
                self.logger.info(f"  {i}. {asin}")
            if len(asins) > 10:
                self.logger.info(f"  ... 他 {len(asins) - 10}件")

        # 2. SP-APIで商品情報取得
        self.logger.info("[2/6] SP-APIで商品情報を取得中...")
        self.logger.info("      注意: SP-APIレート制限により、処理に時間がかかります")
        self.logger.info(f"      推定時間: 約{len(asins) * 12 / 60:.1f}分")

        if not self.dry_run:
            products_data = self._fetch_products_data(asins)
            self.logger.info(f"商品情報取得完了: 成功 {self.stats['fetched_count']}件 / 失敗 {self.stats['failed_fetch_count']}件")
        else:
            self.logger.info("[DRY RUN] SP-API呼び出しをスキップ")
            products_data = {}

        # 3. アカウント割り振り（1000件ずつランダム）
        self.logger.info("[3/6] アカウント割り振り中...")
        account_assignments = self._assign_accounts(asins)
        for account_id, assigned_asins in account_assignments.items():
            self.logger.info(f"      {account_id}: {len(assigned_asins)}件")

        # 4. テーブル登録
        tables_desc = ' + '.join(tables_to_register)
        self.logger.info(f"[4/6] {tables_desc}への登録中...")
        if not self.dry_run and products_data:
            self._register_products_and_listings(products_data, account_assignments)
            self.logger.info("      登録完了:")
            self.logger.info(f"        - products:     {self.stats['added_to_products']}件")
            if self.add_to_listings:
                self.logger.info(f"        - listings:     {self.stats['added_to_listings']}件")
            if self.add_to_queue:
                self.logger.info(f"        - upload_queue: {self.stats['added_to_queue']}件")
                if self.stats['failed_queue_count'] > 0:
                    self.logger.info(f"        - 失敗:         {self.stats['failed_queue_count']}件")
        else:
            self.logger.info("[DRY RUN] 登録をスキップ")

        # 6. sourcing_candidatesのstatus更新
        self.logger.info("[6/6] sourcing_candidatesのstatus更新中...")
        if not self.dry_run:
            self._update_candidate_status(asins, 'imported')
            self.logger.info(f"      更新完了: {self.stats['updated_status_count']}件")
        else:
            self.logger.info("[DRY RUN] status更新をスキップ")

        # サマリー表示
        self._print_summary()

    def _get_candidate_asins(self) -> List[str]:
        """
        sourcing_candidatesから未処理ASINを取得

        Returns:
            list: ASINのリスト
        """
        conn = sqlite3.connect(self.sourcing_db_path)
        cursor = conn.cursor()

        try:
            query = "SELECT DISTINCT asin FROM sourcing_candidates WHERE status='candidate'"
            if self.limit:
                query += f" LIMIT {self.limit}"

            cursor.execute(query)
            asins = [row[0] for row in cursor.fetchall()]
            return asins

        finally:
            conn.close()

    def _fetch_products_data(self, asins: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        商品情報を取得
        - 既存のASIN: productsテーブルから取得（SP-API不要）
        - 新規のASIN: SP-APIで取得

        Args:
            asins: ASINのリスト

        Returns:
            dict: ASIN別の商品情報
        """
        products_data = {}
        existing_asins = []
        missing_asins = []

        # 1. まず、productsテーブルから既存情報を確認
        self.logger.info("  productsテーブルから既存情報を確認中...")
        for asin in asins:
            product = self.master_db.get_product(asin)
            if product:
                # 既存のproductsから情報を取得
                products_data[asin] = {
                    'title_ja': product.get('title_ja'),
                    'title_en': product.get('title_en'),
                    'description_ja': product.get('description_ja'),
                    'description_en': product.get('description_en'),
                    'category': product.get('category'),
                    'brand': product.get('brand'),
                    'images': product.get('images'),
                    'amazon_price_jpy': product.get('amazon_price_jpy'),
                    'amazon_in_stock': product.get('amazon_in_stock')
                }
                existing_asins.append(asin)
                self.stats['fetched_count'] += 1
            else:
                missing_asins.append(asin)

        self.logger.info("  既存情報確認完了")
        self.logger.info(f"    → 既存: {len(existing_asins)}件（DB取得）")

        # 2. productsに存在しないASINのみSP-APIで取得
        if missing_asins:
            self.logger.info(f"    → 新規: {len(missing_asins)}件（SP-API取得）")
            self.logger.info(f"        推定時間: 約{len(missing_asins) * 2.5 / 60:.1f}分")

            # 個別に処理
            for i, asin in enumerate(missing_asins, 1):
                try:
                    self.logger.info(f"  [{i}/{len(missing_asins)}] {asin} を取得中...")

                    # 商品情報取得
                    batch_data = self.sp_api_client.get_products_batch([asin])

                    if asin in batch_data:
                        products_data[asin] = batch_data[asin]
                        self.stats['fetched_count'] += 1
                        self.logger.info(f"  [{i}/{len(missing_asins)}] {asin} 取得成功")
                    else:
                        self.stats['failed_fetch_count'] += 1
                        self.logger.warning(f"  [{i}/{len(missing_asins)}] {asin} 取得失敗 (データなし)")

                except Exception as e:
                    self.stats['failed_fetch_count'] += 1
                    self.logger.error(f"  [{i}/{len(missing_asins)}] {asin} エラー: {e}")
        else:
            self.logger.info("    → 新規: 0件（SP-API呼び出しなし）")

        return products_data

    def _register_products_and_listings(
        self,
        products_data: Dict[str, Dict[str, Any]],
        account_assignments: Dict[str, List[str]]
    ):
        """
        products + listings + queueに一括登録

        Args:
            products_data: ASIN別の商品情報
            account_assignments: アカウントID別のASINリスト
        """
        # アカウント別に登録
        for account_id, asins in account_assignments.items():
            for asin in asins:
                # 商品情報が取得できている場合のみ登録
                if asin not in products_data:
                    continue

                product_data = products_data[asin]

                # ブロックリストチェック
                if self.blocklist_manager.is_blocked(asin):
                    block_info = self.blocklist_manager.get_block_info(asin)
                    self.logger.warning(f"  [BLOCKLIST] {asin}: ブロックリスト登録済み")
                    self.logger.warning(f"              理由: {block_info.get('reason', '不明')}")
                    self.logger.warning(f"              削除日: {block_info.get('deleted_at', '不明')}")
                    self.stats['blocklist_blocked_count'] = self.stats.get('blocklist_blocked_count', 0) + 1
                    continue

                # 禁止商品チェック
                if self.prohibited_checker:
                    check_result = self.prohibited_checker.check_product({
                        'asin': asin,
                        'title_ja': product_data.get('title_ja', ''),
                        'title_en': product_data.get('title_en', ''),
                        'description_ja': product_data.get('description_ja', ''),
                        'description_en': product_data.get('description_en', ''),
                        'category': product_data.get('category', ''),
                        'brand': product_data.get('brand', ''),
                        'images': product_data.get('images', [])
                    })

                    if check_result['recommendation'] == 'auto_block':
                        self.logger.warning(f"  [BLOCKED] {asin}: {check_result['risk_level']} (スコア: {check_result['risk_score']})")
                        if check_result['matched_keywords']:
                            self.logger.warning(f"            キーワード: {[k['keyword'] for k in check_result['matched_keywords']]}")
                        if check_result['matched_categories']:
                            self.logger.warning(f"            カテゴリ: {check_result['matched_categories']}")
                        self.stats['blocked_count'] = self.stats.get('blocked_count', 0) + 1
                        continue

                # 個別のマネージャーで登録（リファクタリング後）
                # Step 1: productsテーブルに登録
                try:
                    product_added = self.product_manager.add_product(
                        asin=asin,
                        title_ja=product_data.get('title_ja'),
                        title_en=product_data.get('title_en'),
                        description_ja=product_data.get('description_ja'),
                        description_en=product_data.get('description_en'),
                        category=product_data.get('category'),
                        brand=product_data.get('brand'),
                        images=product_data.get('images'),
                        amazon_price_jpy=product_data.get('amazon_price_jpy'),
                        amazon_in_stock=product_data.get('amazon_in_stock')
                    )
                    if product_added:
                        self.stats['added_to_products'] += 1
                except Exception as e:
                    self.logger.error(f"  [ERROR] products登録失敗 ({asin}): {e}")
                    continue

                # Step 2: listingsテーブルに登録（オプショナル）
                if self.add_to_listings:
                    try:
                        # SKU生成
                        sku = generate_sku(
                            platform='base',
                            asin=asin,
                            timestamp=datetime.now()
                        )

                        # 売価計算（新しい価格決定モジュールを使用）
                        amazon_price = product_data.get('amazon_price_jpy')
                        selling_price = None
                        if amazon_price:
                            selling_price = self.price_calculator.calculate_selling_price(
                                amazon_price=amazon_price,
                                platform='base'
                            )

                        listing_id = self.listing_manager.add_listing(
                            asin=asin,
                            platform='base',
                            account_id=account_id,
                            sku=sku,
                            selling_price=selling_price,
                            currency='JPY',
                            in_stock_quantity=1,
                            status='pending',
                            visibility='public'
                        )
                        if listing_id:
                            self.stats['added_to_listings'] += 1
                    except Exception as e:
                        # UNIQUE制約違反の場合はスキップ
                        if 'UNIQUE constraint failed' in str(e) or 'already exists' in str(e).lower():
                            self.logger.info(f"  listings既存スキップ ({asin})")
                        else:
                            self.logger.error(f"  [ERROR] listings登録失敗 ({asin}): {e}")
                            continue
                else:
                    self.logger.info(f"  listings登録スキップ ({asin}) - --products-only指定")

                # Step 3: upload_queueに追加（オプショナル）
                if self.add_to_queue:
                    try:
                        queue_added = self.queue_manager.add_to_queue(
                            asin=asin,
                            platform='base',
                            account_id=account_id,
                            priority=UploadQueueManager.PRIORITY_NORMAL
                        )
                        if queue_added:
                            self.stats['added_to_queue'] += 1
                        else:
                            self.stats['failed_queue_count'] += 1
                            self.logger.warning(f"  キュー追加失敗 ({asin})")
                    except Exception as e:
                        self.stats['failed_queue_count'] += 1
                        self.logger.error(f"  [ERROR] キュー追加失敗 ({asin}): {e}")
                else:
                    self.logger.info(f"  キュー追加スキップ ({asin}) - --no-queue指定")

    def _assign_accounts(self, asins: List[str]) -> Dict[str, List[str]]:
        """
        アカウント割り振り

        account_limitsが指定されている場合は指定された件数ずつ、
        指定されていない場合は1000件ずつランダム割り振り

        Args:
            asins: ASINのリスト

        Returns:
            dict: アカウントID別のASINリスト
        """
        # ASINをシャッフル
        shuffled_asins = asins.copy()
        random.shuffle(shuffled_asins)

        account_assignments = {}

        if self.account_limits:
            # アカウント別の件数指定がある場合
            current_idx = 0
            for account_id in self.accounts:
                limit = self.account_limits.get(account_id, 0)
                if limit > 0:
                    end_idx = min(current_idx + limit, len(shuffled_asins))
                    account_assignments[account_id] = shuffled_asins[current_idx:end_idx]
                    current_idx = end_idx
                else:
                    account_assignments[account_id] = []
        else:
            # デフォルト: 1000件ずつ割り振り
            for i, account_id in enumerate(self.accounts):
                start_idx = i * 1000
                end_idx = min(start_idx + 1000, len(shuffled_asins))
                account_assignments[account_id] = shuffled_asins[start_idx:end_idx]

        return account_assignments


    def _update_candidate_status(self, asins: List[str], new_status: str):
        """
        sourcing_candidatesのstatusを更新

        Args:
            asins: ASINのリスト
            new_status: 新しいステータス
        """
        conn = sqlite3.connect(self.sourcing_db_path)
        cursor = conn.cursor()

        try:
            for asin in asins:
                cursor.execute(
                    "UPDATE sourcing_candidates SET status=?, imported_at=? WHERE asin=?",
                    (new_status, datetime.now().isoformat(), asin)
                )
                self.stats['updated_status_count'] += 1

            conn.commit()

        finally:
            conn.close()

    def _print_summary(self):
        """サマリーを表示"""
        self.logger.info("=" * 70)
        self.logger.info("実行結果サマリー")
        self.logger.info("=" * 70)
        self.logger.info(f"処理対象ASIN数:       {self.stats['total_asins']:>6}件")
        self.logger.info(f"商品情報取得成功:     {self.stats['fetched_count']:>6}件")
        self.logger.info(f"商品情報取得失敗:     {self.stats['failed_fetch_count']:>6}件")
        if 'blocklist_blocked_count' in self.stats:
            self.logger.info(f"ブロックリスト拒否:   {self.stats['blocklist_blocked_count']:>6}件")
        if self.check_prohibited and 'blocked_count' in self.stats:
            self.logger.info(f"禁止商品ブロック:     {self.stats['blocked_count']:>6}件")
        self.logger.info(f"productsテーブル追加: {self.stats['added_to_products']:>6}件")
        self.logger.info(f"listingsテーブル追加: {self.stats['added_to_listings']:>6}件")
        self.logger.info(f"upload_queue追加:     {self.stats['added_to_queue']:>6}件")
        self.logger.info(f"upload_queue失敗:     {self.stats['failed_queue_count']:>6}件")
        self.logger.info(f"status更新:           {self.stats['updated_status_count']:>6}件")
        self.logger.info("=" * 70)

        if self.dry_run:
            self.logger.info("[DRY RUN完了] 実際の登録は行われていません")
        else:
            self.logger.info("[実行完了] 出品連携が正常に完了しました")

        self.logger.info("=" * 70)


def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(
        description='出品連携スクリプト - sourcing_candidates → master.db'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='処理する最大件数（デフォルト: 全件）'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='DRY RUNモード（確認のみ、実際の登録は行わない）'
    )
    parser.add_argument(
        '--account-limits',
        type=str,
        default=None,
        help='アカウント別の追加件数指定（例: base_account_1:989,base_account_2:400）'
    )
    parser.add_argument(
        '--no-queue',
        action='store_true',
        help='upload_queueへの追加をスキップ（productsとlistingsのみ登録）'
    )
    parser.add_argument(
        '--products-only',
        action='store_true',
        help='productsテーブルのみに登録（listingsとqueueはスキップ）'
    )

    args = parser.parse_args()

    # account_limitsをパース
    account_limits = None
    if args.account_limits:
        account_limits = {}
        for pair in args.account_limits.split(','):
            account_id, count = pair.split(':')
            account_limits[account_id.strip()] = int(count.strip())

    # CandidateImporterを初期化して実行
    # --products-onlyが指定された場合、listingsもqueueもスキップ
    add_to_listings = not args.products_only
    add_to_queue = not args.no_queue and not args.products_only

    importer = CandidateImporter(
        limit=args.limit,
        dry_run=args.dry_run,
        account_limits=account_limits,
        add_to_listings=add_to_listings,
        add_to_queue=add_to_queue
    )
    importer.run()


if __name__ == '__main__':
    main()
