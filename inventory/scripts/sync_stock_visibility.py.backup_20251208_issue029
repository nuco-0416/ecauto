"""
在庫切れ時の自動非公開スクリプト

Amazon在庫切れ時に全プラットフォームで商品を非公開にし、
在庫復活時に再公開する
"""

import sys
import logging
import os
import signal
from pathlib import Path
from datetime import datetime
import time
from dotenv import load_dotenv

# ロガーの設定
logger = logging.getLogger(__name__)

# グローバルシャットダウンフラグ
_shutdown_requested = False

def _signal_handler(signum, frame):
    """シグナルハンドラ（Ctrl+C対応）"""
    global _shutdown_requested
    signal_name = signal.Signals(signum).name
    logger.info(f"シグナル {signal_name} ({signum}) を受信しました")
    _shutdown_requested = True

# Windows環境でのUTF-8エンコーディング強制設定
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        # Python 3.7未満の場合のフォールバック
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# パスを追加
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from inventory.core.master_db import MasterDB
from inventory.core.cache_manager import AmazonProductCache
from platforms.base.accounts.manager import AccountManager
from platforms.base.core.api_client import BaseAPIClient
from integrations.amazon.sp_api_client import AmazonSPAPIClient


class StockVisibilitySync:
    """
    在庫切れ時の自動非公開処理クラス
    """

    def __init__(self):
        """初期化"""
        # シグナルハンドラを登録
        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)

        self.master_db = MasterDB()
        self.cache = AmazonProductCache()
        self.account_manager = AccountManager()

        # SP-APIクライアント初期化（キャッシュ補完用）
        load_dotenv(project_root / '.env')
        try:
            sp_api_credentials = {
                'refresh_token': os.getenv('REFRESH_TOKEN'),
                'lwa_app_id': os.getenv('LWA_APP_ID'),
                'lwa_client_secret': os.getenv('LWA_CLIENT_SECRET')
            }
            self.sp_api_client = AmazonSPAPIClient(sp_api_credentials)
            self.sp_api_available = True
            logger.info("SP-APIクライアント初期化成功（キャッシュ補完機能有効）")
        except Exception as e:
            logger.warning(f"SP-APIクライアント初期化失敗: {e}")
            logger.warning("キャッシュ補完機能は無効化されます")
            self.sp_api_client = None
            self.sp_api_available = False

        # 統計情報
        self.stats = {
            'total_products': 0,
            'out_of_stock_count': 0,
            'in_stock_count': 0,
            'updated_to_hidden': 0,
            'updated_to_public': 0,
            'cache_missing': 0,
            'cache_incomplete': 0,
            'cache_fill_success': 0,
            'cache_fill_failed': 0,
            'errors': 0,
            'errors_detail': []
        }

    def sync_all_listings(self, platform: str = 'base', dry_run: bool = False):
        """
        全出品の在庫状況を同期

        Args:
            platform: プラットフォーム名（デフォルト: 'base'）
            dry_run: Trueの場合、実際の更新は行わず、ログのみ出力
        """
        logger.info("\n" + "=" * 70)
        logger.info("在庫切れ時の自動非公開処理を開始")
        logger.info("=" * 70)
        logger.info(f"プラットフォーム: {platform}")
        logger.info(f"実行モード: {'DRY RUN（実際の更新なし）' if dry_run else '本番実行'}")
        logger.info(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()

        # キャッシュ欠損ASINを収集するリスト
        missing_cache_asins = []

        # アクティブなアカウント取得
        accounts = self.account_manager.get_active_accounts()
        if not accounts:
            logger.error("エラー: アクティブなアカウントが見つかりません")
            return self.stats

        logger.info(f"アクティブアカウント数: {len(accounts)}件\n")

        # 各アカウントの出品をループ
        for account in accounts:
            # シャットダウン要求チェック
            global _shutdown_requested
            if _shutdown_requested:
                logger.info("シャットダウン要求を検出しました（アカウントループ中断）")
                break

            account_id = account['id']
            account_name = account['name']

            logger.info(f"\n--- アカウント: {account_name} ({account_id}) ---")

            try:
                # アカウント別の出品一覧を取得
                listings = self.master_db.get_listings_by_account(
                    platform=platform,
                    account_id=account_id,
                    status='listed'  # 出品済みのみ
                )

                logger.info(f"出品数: {len(listings)}件")

                if not listings:
                    logger.info("  → 出品なし、スキップ")
                    continue

                # BASE APIクライアント作成
                base_client = BaseAPIClient(
                    account_id=account_id,
                    account_manager=self.account_manager
                )

                # 各出品をチェック
                for listing in listings:
                    # シャットダウン要求チェック
                    if _shutdown_requested:
                        logger.info("シャットダウン要求を検出しました（出品ループ中断）")
                        break

                    asin = listing['asin']

                    # キャッシュ欠損をチェック
                    cache_file = self.cache.cache_dir / f'{asin}.json'
                    if not cache_file.exists():
                        missing_cache_asins.append(asin)
                        logger.debug(f"  [CACHE MISS] {asin} - Master DBフォールバック")

                    self._sync_listing(listing, base_client, dry_run)

            except Exception as e:
                logger.error(f"エラー: アカウント {account_id} の処理中にエラー: {e}")
                self.stats['errors'] += 1
                self.stats['errors_detail'].append({
                    'account_id': account_id,
                    'error': str(e)
                })

        # ━━━ キャッシュ補完処理（処理完了後） ━━━
        if missing_cache_asins and not dry_run and self.sp_api_available:
            # 重複を削除
            missing_cache_asins = list(set(missing_cache_asins))

            logger.info("")
            logger.info("━" * 70)
            logger.info("キャッシュ補完処理（次回の処理高速化のため）")
            logger.info("━" * 70)
            logger.info(f"欠損キャッシュ: {len(missing_cache_asins)}件")
            logger.info(f"SP-APIバッチで一括取得中...")

            # 推定時間を表示
            batch_count = (len(missing_cache_asins) + 19) // 20
            estimated_minutes = (batch_count * 12) / 60
            logger.info(f"推定時間: 約{estimated_minutes:.1f}分 ({batch_count}バッチ)")
            print()

            try:
                # SP-APIバッチで一括取得
                batch_results = self.sp_api_client.get_prices_batch(
                    missing_cache_asins,
                    batch_size=20
                )

                # キャッシュに保存 + Master DB更新
                success_count = 0
                failed_count = 0

                for asin, price_info in batch_results.items():
                    if price_info and price_info.get('price') is not None:
                        # キャッシュに保存
                        self.cache.set_product(asin, price_info)

                        # Master DBも更新（最新情報で同期）
                        try:
                            self.master_db.update_amazon_info(
                                asin=asin,
                                price_jpy=int(price_info['price']),
                                in_stock=price_info.get('in_stock', False)
                            )
                        except Exception as e:
                            logger.warning(f"  [WARN] {asin} - Master DB更新失敗: {e}")

                        success_count += 1
                    else:
                        failed_count += 1
                        logger.warning(f"  [WARN] {asin} - SP-API取得失敗")

                logger.info("")
                logger.info(f"補完完了: 成功 {success_count}件 / 失敗 {failed_count}件")
                logger.info("━" * 70)
                print()

                self.stats['cache_fill_success'] = success_count
                self.stats['cache_fill_failed'] = failed_count

            except Exception as e:
                logger.error(f"キャッシュ補完中にエラー: {e}")
                self.stats['cache_fill_failed'] = len(missing_cache_asins)
        elif missing_cache_asins and dry_run:
            logger.info(f"\n[DRY RUN] キャッシュ補完をスキップ（{len(missing_cache_asins)}件）\n")
        elif missing_cache_asins and not self.sp_api_available:
            logger.warning(f"\n[警告] SP-API未初期化のため、キャッシュ補完をスキップ（{len(missing_cache_asins)}件）\n")

        # 統計表示
        self._print_summary()

        return self.stats

    def _sync_listing(self, listing: dict, base_client: BaseAPIClient, dry_run: bool):
        """
        1つの出品の在庫状況を同期

        Args:
            listing: 出品情報
            base_client: BASE APIクライアント
            dry_run: Trueの場合、実際の更新は行わない
        """
        asin = listing['asin']
        listing_id = listing['id']
        platform_item_id = listing['platform_item_id']
        current_visibility = listing['visibility']

        self.stats['total_products'] += 1

        # 商品情報を取得（マスタDBから）
        product = self.master_db.get_product(asin)
        if not product:
            logger.info(f"  [SKIP] {asin} - 商品情報が見つかりません")
            return

        # Amazon在庫状況をチェック（キャッシュ優先、TTL無視）
        amazon_in_stock = None

        # まずキャッシュから取得を試みる（TTL無視）
        if True:
            import json
            cache_file = self.cache.cache_dir / f'{asin}.json'

            if cache_file.exists():
                try:
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        cached_product = json.load(f)

                    # in_stockフィールドが存在するかチェック（欠損チェック）
                    if cached_product.get('in_stock') is not None:
                        amazon_in_stock = cached_product.get('in_stock', False)
                    else:
                        logger.error(f"  [SKIP] {asin} - キャッシュの在庫情報が欠損しています（API取得エラーの可能性）")
                        self.stats['cache_incomplete'] += 1
                        return
                except Exception as e:
                    logger.error(f"  [SKIP] {asin} - キャッシュ読み込みエラー: {e}")
                    self.stats['errors'] += 1
                    return
            else:
                # キャッシュがない場合、Master DBの値を使用（処理完了後にキャッシュ補完される）
                logger.debug(f"  [FALLBACK] {asin} - Master DBから在庫情報を使用")
                self.stats['cache_missing'] += 1

                amazon_in_stock = product.get('amazon_in_stock')
                if amazon_in_stock is None:
                    logger.info(f"  [SKIP] {asin} - Master DBにも在庫情報がありません")
                    return

        # 目標のvisibilityを決定
        if amazon_in_stock:
            target_visibility = 'public'
            self.stats['in_stock_count'] += 1
        else:
            target_visibility = 'hidden'
            self.stats['out_of_stock_count'] += 1

        # 変更が必要かチェック
        if current_visibility == target_visibility:
            # 変更不要
            return

        # 変更が必要
        logger.info(f"  [UPDATE] {asin} | {current_visibility} → {target_visibility}")

        if dry_run:
            logger.info(f"    → DRY RUN: 実際の更新はスキップ")
            if target_visibility == 'hidden':
                self.stats['updated_to_hidden'] += 1
            else:
                self.stats['updated_to_public'] += 1
            return

        # BASE APIで更新
        try:
            visible_flag = 1 if target_visibility == 'public' else 0

            base_client.update_item(
                item_id=platform_item_id,
                updates={'visible': visible_flag}
            )

            # マスタDBも更新
            self.master_db.update_listing(
                listing_id=listing_id,
                visibility=target_visibility
            )

            logger.info(f"    → 更新成功")

            # BASE APIレート制限対策（実際にAPI呼び出しが行われた場合のみ）
            time.sleep(0.1)

            if target_visibility == 'hidden':
                self.stats['updated_to_hidden'] += 1
            else:
                self.stats['updated_to_public'] += 1

        except Exception as e:
            logger.error(f"    → 更新エラー: {e}")
            self.stats['errors'] += 1
            self.stats['errors_detail'].append({
                'asin': asin,
                'listing_id': listing_id,
                'error': str(e)
            })

    def _print_summary(self):
        """統計情報を表示"""
        logger.info("\n" + "=" * 70)
        logger.info("処理結果サマリー")
        logger.info("=" * 70)
        logger.info(f"処理した商品数: {self.stats['total_products']}件")
        logger.info(f"  - 在庫あり: {self.stats['in_stock_count']}件")
        logger.info(f"  - 在庫切れ: {self.stats['out_of_stock_count']}件")
        print()
        logger.info(f"キャッシュ状態:")
        logger.info(f"  - キャッシュ欠損（Master DB使用）: {self.stats['cache_missing']}件")
        logger.info(f"  - キャッシュ不完全（スキップ）: {self.stats['cache_incomplete']}件")
        if self.stats['cache_fill_success'] > 0 or self.stats['cache_fill_failed'] > 0:
            logger.info(f"  - キャッシュ補完（成功/失敗）: {self.stats['cache_fill_success']}/{self.stats['cache_fill_failed']}件")
        print()
        logger.info(f"更新した商品数:")
        logger.info(f"  - 非公開に変更: {self.stats['updated_to_hidden']}件")
        logger.info(f"  - 公開に変更: {self.stats['updated_to_public']}件")
        print()
        logger.error(f"エラー: {self.stats['errors']}件")

        if self.stats['errors_detail']:
            logger.error("\nエラー詳細:")
            for error in self.stats['errors_detail'][:10]:  # 最大10件表示
                logger.error(f"  - {error}")

        # 重要な警告を表示
        if self.stats['cache_incomplete'] > 0:
            print()
            logger.warning(f"警告: {self.stats['cache_incomplete']}件の商品でキャッシュが不完全でした。")
            logger.warning("  → SP-APIエラーの可能性があります。")

        logger.info("=" * 70)
        logger.info(f"終了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()


def main():
    """メイン処理"""
    import argparse

    parser = argparse.ArgumentParser(
        description='Amazon在庫切れ時に全プラットフォームで商品を非公開にする'
    )
    parser.add_argument(
        '--platform',
        default='base',
        help='プラットフォーム名（デフォルト: base）'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='DRY RUNモード（実際の更新は行わない）'
    )

    args = parser.parse_args()

    # 同期処理実行
    sync = StockVisibilitySync()
    stats = sync.sync_all_listings(
        platform=args.platform,
        dry_run=args.dry_run
    )

    # 終了コード
    if stats['errors'] > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
