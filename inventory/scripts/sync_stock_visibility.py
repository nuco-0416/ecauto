"""
在庫切れ時の自動非公開スクリプト

Amazon在庫切れ時に全プラットフォームで商品を非公開にし、
在庫復活時に再公開する
"""

import sys
import logging
import signal
from pathlib import Path
from datetime import datetime
import time

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
from platforms.base.accounts.manager import AccountManager
from platforms.base.core.api_client import BaseAPIClient


class StockVisibilitySync:
    """
    在庫切れ時の自動非公開処理クラス
    """

    def __init__(self, register_signal_handler: bool = False):
        """
        初期化

        Args:
            register_signal_handler: シグナルハンドラを登録するか（スタンドアロン実行時のみTrue）
                                      daemon経由で実行される場合はFalse（daemon_base.pyが管理）
        """
        # スタンドアロン実行時のみシグナルハンドラを登録
        # daemon経由の場合はdaemon_base.pyのシグナルハンドラが管理
        if register_signal_handler:
            signal.signal(signal.SIGINT, _signal_handler)
            signal.signal(signal.SIGTERM, _signal_handler)

        self.master_db = MasterDB()
        self.account_manager = AccountManager()

        # 統計情報
        self.stats = {
            'total_products': 0,
            'out_of_stock_count': 0,
            'in_stock_count': 0,
            'updated_to_hidden': 0,
            'updated_to_public': 0,
            'stock_restored': 0,  # 販売済商品の在庫を1に復活させた件数
            'no_stock_info': 0,
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

                    self._sync_listing(listing, base_client, dry_run)

            except Exception as e:
                logger.error(f"エラー: アカウント {account_id} の処理中にエラー: {e}")
                self.stats['errors'] += 1
                self.stats['errors_detail'].append({
                    'account_id': account_id,
                    'error': str(e)
                })

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

        # ログプレフィックス（プラットフォーム/アカウントID）
        log_prefix = f"[BASE/{base_client.account_id}]"

        self.stats['total_products'] += 1

        # 商品情報を取得（マスタDBから）
        product = self.master_db.get_product(asin)
        if not product:
            logger.info(f"  {log_prefix} [SKIP] {asin} - 商品情報が見つかりません")
            return

        # Amazon在庫状況をチェック（マスタDBから直接取得）
        amazon_in_stock = product.get('amazon_in_stock')
        if amazon_in_stock is None:
            logger.debug(f"  {log_prefix} [SKIP] {asin} - 在庫情報がありません")
            self.stats['no_stock_info'] += 1
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
            # visibility変更不要だが、Amazon在庫ありの場合は在庫数チェックを行う
            # （販売済みでBASE在庫0のまま放置されている商品への対応）
            if amazon_in_stock and current_visibility == 'public':
                self._restore_stock_if_needed(asin, listing_id, platform_item_id, base_client, dry_run, log_prefix)
            return

        # 変更が必要
        logger.info(f"  {log_prefix} [UPDATE] {asin} | {current_visibility} → {target_visibility}")

        if dry_run:
            logger.info(f"    {log_prefix} → DRY RUN: 実際の更新はスキップ")
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

            logger.info(f"    {log_prefix} → 更新成功")

            # BASE APIレート制限対策（実際にAPI呼び出しが行われた場合のみ）
            time.sleep(0.1)

            if target_visibility == 'hidden':
                self.stats['updated_to_hidden'] += 1
            else:
                self.stats['updated_to_public'] += 1

        except Exception as e:
            logger.error(f"    {log_prefix} → 更新エラー: {e}")
            self.stats['errors'] += 1
            self.stats['errors_detail'].append({
                'asin': asin,
                'listing_id': listing_id,
                'error': str(e)
            })
            return

        # Amazon在庫ありの場合、BASE側の在庫数もチェックして復活させる
        if amazon_in_stock and target_visibility == 'public':
            self._restore_stock_if_needed(asin, listing_id, platform_item_id, base_client, dry_run, log_prefix)

    def _restore_stock_if_needed(self, asin: str, listing_id: int, platform_item_id: str, base_client, dry_run: bool, log_prefix: str = ""):
        """
        BASE側の在庫数が0の場合、在庫を1に復活させる

        Args:
            asin: 商品ASIN
            listing_id: リスティングID
            platform_item_id: BASE商品ID
            base_client: BASE APIクライアント
            dry_run: Trueの場合、実際の更新は行わない
            log_prefix: ログプレフィックス（プラットフォーム/アカウントID）
        """
        try:
            # BASE側の現在の在庫数を取得
            item_detail = base_client.get_item(platform_item_id)
            if not item_detail:
                logger.warning(f"    {log_prefix} [STOCK] {asin} - 商品情報を取得できませんでした")
                return

            # レスポンス形式: {'item': {...}}
            item_info = item_detail.get('item', {})
            current_stock = item_info.get('stock', 0)

            if current_stock == 0:
                logger.info(f"    {log_prefix} [STOCK_RESTORE] {asin} - Amazon在庫あり、BASE在庫0→1に復活")

                if dry_run:
                    logger.info(f"      {log_prefix} → DRY RUN: 実際の更新はスキップ")
                    self.stats['stock_restored'] += 1
                    return

                # 在庫数を1に復活
                base_client.update_item(
                    item_id=platform_item_id,
                    updates={'stock': 1}
                )

                logger.info(f"      {log_prefix} → 在庫数1に復活成功")
                self.stats['stock_restored'] += 1

                # BASE APIレート制限対策
                time.sleep(0.1)

        except Exception as e:
            logger.error(f"    {log_prefix} [STOCK] {asin} - 在庫復活エラー: {e}")
            self.stats['errors'] += 1
            self.stats['errors_detail'].append({
                'asin': asin,
                'listing_id': listing_id,
                'error': f'在庫復活エラー: {str(e)}'
            })

    def _print_summary(self):
        """統計情報を表示"""
        logger.info("\n" + "=" * 70)
        logger.info("処理結果サマリー")
        logger.info("=" * 70)
        logger.info(f"処理した商品数: {self.stats['total_products']}件")
        logger.info(f"  - 在庫あり: {self.stats['in_stock_count']}件")
        logger.info(f"  - 在庫切れ: {self.stats['out_of_stock_count']}件")
        if self.stats['no_stock_info'] > 0:
            logger.info(f"  - 在庫情報なし（スキップ）: {self.stats['no_stock_info']}件")
        print()
        logger.info(f"更新した商品数:")
        logger.info(f"  - 非公開に変更: {self.stats['updated_to_hidden']}件")
        logger.info(f"  - 公開に変更: {self.stats['updated_to_public']}件")
        logger.info(f"  - 在庫1に復活: {self.stats['stock_restored']}件")
        print()
        logger.info(f"エラー: {self.stats['errors']}件")

        if self.stats['errors_detail']:
            logger.error("\nエラー詳細:")
            for error in self.stats['errors_detail'][:10]:  # 最大10件表示
                logger.error(f"  - {error}")

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

    # 同期処理実行（スタンドアロン実行時はシグナルハンドラを登録）
    sync = StockVisibilitySync(register_signal_handler=True)
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
