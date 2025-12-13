"""
在庫同期デーモン

定期的にAmazon在庫・価格を取得し、複数プラットフォームと同期します。

機能 (ISSUE_028 & ISSUE_029対応):
- Phase 1: SP-API → Master DB（全ASINの価格・在庫を一括更新、1回のみ実行）
- Phase 2: Master DB → 各プラットフォーム（並列実行）
- 在庫同期（visibility更新）

使用例:
    # 3時間ごとに同期（デフォルト - ISSUE #005対応、BASE + eBay並列処理）
    python scheduled_tasks/sync_inventory_daemon.py

    # 1時間ごとに同期（短い間隔）
    python scheduled_tasks/sync_inventory_daemon.py --interval 3600

    # 特定プラットフォームのみ（複数指定可能）
    python scheduled_tasks/sync_inventory_daemon.py --platforms base ebay

    # BASEのみ
    python scheduled_tasks/sync_inventory_daemon.py --platforms base

    # 既存Master DBを使用（SP-API処理をスキップ、テスト用）
    python scheduled_tasks/sync_inventory_daemon.py --skip-cache-update --dry-run

    # 少量テスト（5件のみ処理）
    python scheduled_tasks/sync_inventory_daemon.py --skip-cache-update --dry-run --max-items 5
"""

import sys
from pathlib import Path
import argparse
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any
import time

# プラットフォーム別のファイルロックモジュールをインポート
if sys.platform == 'win32':
    import msvcrt  # Windows用ファイルロック
else:
    import fcntl  # Linux/Unix用ファイルロック

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
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scheduled_tasks.daemon_base import DaemonBase
from inventory.scripts.sync_inventory import InventorySync
from platforms.ebay.scripts.sync_prices import EbayPriceSync
from integrations.amazon.sp_api_client import AmazonSPAPIClient
from integrations.amazon.config import SP_API_CREDENTIALS
from inventory.core.master_db import MasterDB


class SyncInventoryDaemon(DaemonBase):
    """
    在庫同期デーモン（マルチプラットフォーム並列処理対応）

    定期的に以下の処理を実行します (ISSUE_028 & ISSUE_029対応):
    1. Amazon SP-APIから最新の価格・在庫情報を取得（Master DBベース、1回のみ実行）
    2. 各プラットフォームの価格を並列同期（BASE、eBay等）
    3. 各プラットフォームの在庫状況（visibility）を並列同期

    アーキテクチャ:
        Phase 1: SP-API → Master DB（シリアル処理、全ASINの価格・在庫を一括更新）
        Phase 2: Master DB → 各プラットフォーム（並列処理、ThreadPoolExecutor）
    """

    def __init__(
        self,
        interval_seconds: int = 10800,
        platforms: List[str] = None,
        dry_run: bool = False,
        skip_cache_update: bool = False,
        max_items: int = None,
        stock_check_only: bool = False
    ):
        """
        Args:
            interval_seconds: 実行間隔（秒）デフォルト: 10800（3時間 - ISSUE #005対応）
            platforms: プラットフォーム名のリスト（デフォルト: ['base', 'ebay']）
            dry_run: DRY RUNモード（デフォルト: False）
            skip_cache_update: キャッシュ更新をスキップ（既存キャッシュを使用、テスト用）
            max_items: テスト用：処理する最大商品数（省略時は全件）
            stock_check_only: 在庫チェックのみ実行（SP-API同期・価格計算をスキップ）
        """
        # ロックファイルで単一インスタンスを保証
        lock_dir = Path(__file__).parent.parent / 'logs'
        lock_dir.mkdir(exist_ok=True)
        self.lock_file_path = lock_dir / 'sync_inventory_daemon.lock'

        try:
            # ロックファイルを開く（存在しない場合は作成）
            self.lock_file = open(self.lock_file_path, 'w')

            # プラットフォーム別のファイルロック取得（非ブロッキング）
            if sys.platform == 'win32':
                # Windows用ファイルロック
                msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                # Linux/Unix用ファイルロック（排他ロック、非ブロッキング）
                fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

            # ロック成功 - PIDを書き込む
            self.lock_file.write(f"{os.getpid()}\n")
            self.lock_file.flush()
        except (IOError, OSError, BlockingIOError) as e:
            print(f"エラー: 別のインスタンスが既に実行中です（ロックファイル: {self.lock_file_path}）", flush=True)
            sys.exit(1)

        super().__init__(
            name='sync_inventory',
            interval_seconds=interval_seconds,
            max_retries=3,
            retry_delay_seconds=60,
            enable_notifications=False  # デバッグ: 通知を完全に無効化
        )

        # プラットフォームリストの設定
        if platforms is None:
            self.platforms = ['base', 'ebay']  # デフォルト: BASE + eBay
        else:
            self.platforms = platforms

        self.dry_run = dry_run
        self.skip_cache_update = skip_cache_update
        self.max_items = max_items
        self.stock_check_only = stock_check_only

        # SP-APIクライアントの初期化（Phase 1用）
        try:
            if all(SP_API_CREDENTIALS.values()):
                # _shutdown_event を渡して、Ctrl+Cで即座に終了できるようにする
                # threading.Event はシグナル処理に対応しており、Event.wait() は即座に中断可能
                self.sp_api_client = AmazonSPAPIClient(
                    SP_API_CREDENTIALS,
                    shutdown_event=self._shutdown_event
                )
                self.sp_api_available = True
                self.logger.info("SP-APIクライアント初期化完了（Phase 1用、シャットダウン対応）")
            else:
                self.logger.warning("SP-API認証情報が不足しています")
                self.sp_api_client = None
                self.sp_api_available = False
        except Exception as e:
            self.logger.error(f"SP-APIクライアント初期化失敗: {e}")
            self.sp_api_client = None
            self.sp_api_available = False

        # Master DBの初期化（Phase 1用）
        self.master_db = MasterDB()

        # プラットフォーム別のSyncインスタンスを事前作成
        self.sync_instances = {}

        for platform in self.platforms:
            if platform == 'base':
                self.sync_instances[platform] = InventorySync(dry_run=dry_run)
            elif platform == 'ebay':
                self.sync_instances[platform] = EbayPriceSync(markup_ratio=None)
            else:
                raise ValueError(f"未対応のプラットフォーム: {platform}")

        self.logger.info(f"プラットフォーム: {', '.join(self.platforms)}")
        self.logger.info(f"並列処理: {len(self.platforms)}プラットフォーム")
        self.logger.info(f"DRY RUN: {dry_run}")
        if skip_cache_update:
            self.logger.info(f"キャッシュ更新: スキップ（既存キャッシュを使用）")
        if stock_check_only:
            self.logger.info(f"【在庫チェックモード】SP-API同期・価格計算をスキップ、在庫同期のみ実行")
        if max_items:
            self.logger.info(f"処理件数制限: {max_items}件（テストモード）")

    def execute_task(self) -> bool:
        """
        在庫同期タスクを実行（マルチプラットフォーム並列処理）

        Returns:
            bool: 成功時True、失敗時False
        """
        start_time = time.time()

        try:
            # ヘッダー表示
            self.logger.info("=" * 70)
            self.logger.info(f"【在庫・価格同期開始】マルチプラットフォーム並列処理")
            self.logger.info(f"プラットフォーム: {', '.join([p.upper() for p in self.platforms])}")
            self.logger.info(f"実行モード: {'DRY RUN' if self.dry_run else '本番実行'}")
            if self.skip_cache_update:
                self.logger.info(f"キャッシュ更新: スキップ（既存キャッシュを使用、テスト用）")
            if self.stock_check_only:
                self.logger.info(f"【在庫チェックモード】SP-API同期・価格計算をスキップ、在庫同期のみ実行")
            if self.max_items:
                self.logger.info(f"処理件数制限: {self.max_items}件（テストモード）")
            self.logger.info("=" * 70)

            # 各プラットフォームのアカウント情報を表示
            for platform in self.platforms:
                self._log_platform_accounts(platform)

            # Phase 1: SP-API → Master DB（シリアル処理、1回のみ）
            # skip_cache_update または stock_check_only が有効な場合はスキップ
            if self.skip_cache_update or self.stock_check_only:
                self.logger.info("\n" + "=" * 70)
                self.logger.info("【Phase 1】SP-API → Master DB同期: スキップ")
                if self.stock_check_only:
                    self.logger.info("在庫チェックモードのため、SP-API同期をスキップします")
                else:
                    self.logger.info("既存のMaster DBデータを使用します")
                self.logger.info("=" * 70)
            else:
                # ISSUE_028対応: 全ASINの価格・在庫を一括更新
                self.logger.info("\n" + "=" * 70)
                self.logger.info("【Phase 1】SP-API → Master DB同期（全プラットフォーム共通）")
                self.logger.info("=" * 70)
                self._run_phase1_sp_api_sync()

            # シャットダウン要求チェック（Phase 1後、Phase 2前）
            if self.shutdown_requested:
                self.logger.info("シャットダウン要求を検出（Phase 2をスキップ）")
                return False

            # Phase 2: Master DB → 各プラットフォーム（並列処理）
            self.logger.info("\n" + "=" * 70)
            self.logger.info("【Phase 2】Master DB → 各プラットフォーム同期（並列処理）")
            self.logger.info("=" * 70)

            # ThreadPoolExecutorで並列実行
            platform_stats = {}
            with ThreadPoolExecutor(max_workers=len(self.platforms)) as executor:
                # 各プラットフォームの同期タスクを投入
                future_to_platform = {
                    executor.submit(self._sync_platform, platform): platform
                    for platform in self.platforms
                }

                # 結果を収集（シグナル応答性を向上するため、短いタイムアウトでポーリング）
                remaining_futures = set(future_to_platform.keys())
                while remaining_futures:
                    # シャットダウン要求チェック
                    if self.shutdown_requested:
                        self.logger.info("シャットダウン要求を検出（並列処理中断）")
                        executor.shutdown(wait=False, cancel_futures=True)
                        return False

                    # 短いタイムアウトで完了済みタスクをチェック
                    done_futures = set()
                    for future in remaining_futures:
                        if future.done():
                            done_futures.add(future)

                    # 完了したタスクの結果を処理
                    for future in done_futures:
                        platform = future_to_platform[future]
                        try:
                            stats = future.result()
                            platform_stats[platform] = stats
                            self.logger.info(f"✓ {platform.upper()} 同期完了")
                        except Exception as e:
                            self.logger.error(f"✗ {platform.upper()} 同期エラー: {e}", exc_info=True)
                            platform_stats[platform] = {'error': str(e)}

                    # 完了したタスクを削除
                    remaining_futures -= done_futures

                    # 短い待機（CPU使用率を抑える、割り込み可能）
                    if remaining_futures:
                        try:
                            time.sleep(0.1)
                        except KeyboardInterrupt:
                            self.logger.info("並列処理中にKeyboardInterruptを受け取りました")
                            self.shutdown_requested = True
                            executor.shutdown(wait=False, cancel_futures=True)
                            return False

            # 統計情報の集計と表示
            duration = time.time() - start_time
            self.logger.info("")
            self.logger.info("=" * 70)
            self.logger.info("【実行結果サマリー】")
            self.logger.info("=" * 70)
            self.logger.info(f"所要時間: {duration:.1f}秒")
            self.logger.info(f"処理プラットフォーム: {len(platform_stats)}件")

            total_errors = 0
            for platform, stats in platform_stats.items():
                if 'error' in stats:
                    self.logger.error(f"\n[{platform.upper()}] エラー: {stats['error']}")
                    total_errors += 1
                    continue

                self.logger.info(f"\n[{platform.upper()}]")

                # 価格同期の統計
                price_stats = stats.get('price_sync', {})
                if price_stats:
                    self.logger.info(
                        f"  価格同期: 処理={price_stats.get('total_listings', 0)}件, "
                        f"更新={price_stats.get('price_updated', 0)}件, "
                        f"エラー={price_stats.get('errors', 0)}件"
                    )
                    total_errors += price_stats.get('errors', 0)

                # 在庫同期の統計
                stock_stats = stats.get('stock_sync', {})
                if stock_stats:
                    self.logger.info(
                        f"  在庫同期: 処理={stock_stats.get('total_products', 0)}件, "
                        f"非公開={stock_stats.get('updated_to_hidden', 0)}件, "
                        f"公開={stock_stats.get('updated_to_public', 0)}件, "
                        f"エラー={stock_stats.get('errors', 0)}件"
                    )
                    total_errors += stock_stats.get('errors', 0)

            # 完了通知
            self.logger.info("=" * 70)
            if total_errors > 0:
                self.logger.warning(f"⚠ 警告: {total_errors}件のエラーが発生しました")
                # エラーがあっても通知は送信
                self._send_multi_platform_completion_notification(platform_stats, duration, has_errors=True)
                return False
            else:
                self.logger.info("✓ 全プラットフォームの在庫同期が正常に完了しました")
                # 完了通知を送信
                self._send_multi_platform_completion_notification(platform_stats, duration, has_errors=False)
                return True

        except Exception as e:
            self.logger.error(f"在庫同期中にエラーが発生しました: {e}", exc_info=True)
            return False

    def _sync_platform(self, platform: str) -> Dict[str, Any]:
        """
        1つのプラットフォームの同期を実行（並列処理用）

        Args:
            platform: プラットフォーム名

        Returns:
            dict: 統計情報
        """
        start_time = time.time()

        try:
            if platform == 'base':
                # BASE: 統合同期を実行
                # Phase 2では常にskip_cache_update=Trueを渡す
                # （Phase 1で既にMaster DBを更新済み、またはユーザーが明示的にスキップを指定）
                # これにより、InventorySyncの内部SP-APIクライアントによる重複呼び出しを防ぐ
                stats = self.sync_instances[platform].run_full_sync(
                    platform=platform,
                    skip_cache_update=True,  # ISSUE_028: 常にTrue（Phase 1で更新済み）
                    max_items=self.max_items,
                    stock_check_only=self.stock_check_only  # 在庫チェックモード対応
                )
            elif platform == 'ebay':
                # eBay: 価格同期（stock_check_onlyの場合は在庫復活・再公開のみ）
                price_stats = self.sync_instances[platform].sync_all_accounts(
                    dry_run=self.dry_run,
                    max_items=self.max_items,
                    stock_check_only=self.stock_check_only  # 在庫チェックモード対応
                )
                duration = time.time() - start_time
                stats = {
                    'duration_seconds': duration,
                    'price_sync': price_stats,
                    'stock_sync': {}  # eBayは価格同期のみ
                }
            else:
                raise ValueError(f"未対応のプラットフォーム: {platform}")

            return stats

        except Exception as e:
            self.logger.error(f"[{platform.upper()}] 同期処理でエラー: {e}", exc_info=True)
            raise

    def _run_phase1_sp_api_sync(self) -> None:
        """
        Phase 1: SP-API → Master DB同期（全ASINの価格・在庫を一括更新）

        ISSUE_028対応: SP-API通信の重複を解消するため、Phase 1で全ASINを一括更新します。
        - 全プラットフォームの全ASINを収集
        - SP-APIバッチで価格・在庫を一括取得
        - Master DBに保存
        """
        if not self.sp_api_available:
            self.logger.error("SP-APIクライアントが利用できません")
            return

        try:
            # 1. 全プラットフォームの全ASINを収集（status='listed'）
            self.logger.info("全プラットフォームの出品中商品のASINを収集中...")
            all_asins = set()

            # listingsテーブルから直接取得
            with self.master_db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT DISTINCT asin
                    FROM listings
                    WHERE status = 'listed'
                """)
                rows = cursor.fetchall()
                for row in rows:
                    all_asins.add(row[0])

            if not all_asins:
                self.logger.warning("出品中商品が見つかりませんでした")
                return

            asins_list = list(all_asins)
            if self.max_items:
                asins_list = asins_list[:self.max_items]

            self.logger.info(f"収集完了: {len(asins_list)}件のASIN")

            # 2. SP-APIバッチで価格・在庫を一括取得
            self.logger.info(f"\nSP-APIバッチで価格・在庫を取得中...")
            self.logger.info(f"  バッチサイズ: 20件/リクエスト")
            batch_count = (len(asins_list) + 19) // 20
            self.logger.info(f"  予想リクエスト数: {batch_count}回")
            estimated_seconds = batch_count * 12
            self.logger.info(f"  予想処理時間: {estimated_seconds:.0f}秒 ({estimated_seconds/60:.1f}分)")

            price_results = self.sp_api_client.get_prices_batch(asins_list, batch_size=20)

            # シャットダウン要求チェック（SP-API処理後）
            if self.shutdown_requested:
                self.logger.info("シャットダウン要求を検出（Phase 1中断 - SP-API処理後）")
                return  # Phase 1を早期終了

            # 3. Master DBに保存
            self.logger.info(f"\nMaster DBに価格・在庫情報を保存中...")
            success_count = 0
            error_count = 0

            for asin, price_info in price_results.items():
                # シャットダウン要求チェック（DB保存ループ内）
                if self.shutdown_requested:
                    self.logger.info(f"シャットダウン要求を検出（Master DB保存中断 - {success_count}件保存済み）")
                    break

                try:
                    if price_info and price_info.get('price') is not None:
                        self.master_db.update_amazon_info(
                            asin=asin,
                            price_jpy=int(price_info['price']),
                            in_stock=price_info.get('in_stock', False)
                        )
                        success_count += 1
                    else:
                        error_count += 1
                except Exception as e:
                    self.logger.error(f"Master DB更新エラー ({asin}): {e}")
                    error_count += 1

            self.logger.info(f"\n【Phase 1完了】")
            self.logger.info(f"  成功: {success_count}件")
            self.logger.info(f"  失敗: {error_count}件")
            self.logger.info(f"  合計: {len(price_results)}件")

        except Exception as e:
            self.logger.error(f"Phase 1処理でエラー: {e}", exc_info=True)
            raise

    def _log_platform_accounts(self, platform: str) -> None:
        """
        プラットフォームのアカウント情報をログ出力

        Args:
            platform: プラットフォーム名
        """
        self.logger.info(f"\n[{platform.upper()}]")

        if platform == 'base':
            from platforms.base.accounts.manager import AccountManager
            account_manager = AccountManager()
            accounts = account_manager.get_active_accounts()
            if accounts:
                self.logger.info(f"  処理対象アカウント: {len(accounts)}件")
                for account in accounts:
                    self.logger.info(f"    - {account['name']} ({account['id']})")
            else:
                self.logger.warning("  アクティブなアカウントが見つかりません")

        elif platform == 'ebay':
            from platforms.ebay.accounts.manager import EbayAccountManager
            account_manager = EbayAccountManager()
            accounts = account_manager.get_active_accounts()
            if accounts:
                self.logger.info(f"  処理対象アカウント: {len(accounts)}件")
                for account in accounts:
                    self.logger.info(f"    - {account['name']} ({account['id']})")
            else:
                self.logger.warning("  アクティブなアカウントが見つかりません")

    def _send_multi_platform_completion_notification(
        self,
        platform_stats: Dict[str, Dict[str, Any]],
        duration: float,
        has_errors: bool
    ):
        """
        マルチプラットフォーム対応の完了通知を送信

        Args:
            platform_stats: プラットフォーム別の統計情報
            duration: 総所要時間（秒）
            has_errors: エラーがあったかどうか
        """
        # 全プラットフォームの統計情報を集計
        report_stats = {
            '所要時間(秒)': duration,
            '処理プラットフォーム数': len(platform_stats),
        }

        # プラットフォームごとの統計を追加
        for platform, stats in platform_stats.items():
            if 'error' in stats:
                report_stats[f'{platform.upper()}_エラー'] = stats['error']
                continue

            price_stats = stats.get('price_sync', {})
            stock_stats = stats.get('stock_sync', {})

            # 価格同期統計
            if price_stats:
                report_stats[f'{platform.upper()}_価格同期_処理件数'] = price_stats.get('total_listings', 0)
                report_stats[f'{platform.upper()}_価格同期_更新件数'] = price_stats.get('price_updated', 0)
                report_stats[f'{platform.upper()}_価格同期_エラー件数'] = price_stats.get('errors', 0)

            # 在庫同期統計
            if stock_stats:
                report_stats[f'{platform.upper()}_在庫同期_処理件数'] = stock_stats.get('total_products', 0)
                report_stats[f'{platform.upper()}_在庫同期_非公開化'] = stock_stats.get('updated_to_hidden', 0)
                report_stats[f'{platform.upper()}_在庫同期_公開化'] = stock_stats.get('updated_to_public', 0)
                report_stats[f'{platform.upper()}_在庫同期_エラー件数'] = stock_stats.get('errors', 0)

        # 完了レポートを送信
        self.send_completion_report(
            task_name='マルチプラットフォーム在庫・価格同期',
            stats=report_stats
        )

    def __del__(self):
        """デストラクタ: ロックファイルをクリーンアップ"""
        try:
            if hasattr(self, 'lock_file'):
                self.lock_file.close()
            if hasattr(self, 'lock_file_path') and self.lock_file_path.exists():
                self.lock_file_path.unlink()
        except Exception:
            pass  # デストラクタ内ではエラーを無視


def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(
        description='在庫同期デーモン - 定期的にAmazon在庫・価格を複数プラットフォームと並列同期'
    )
    parser.add_argument(
        '--interval',
        type=int,
        default=10800,
        help='実行間隔（秒）デフォルト: 10800（3時間 - ISSUE #005対応）'
    )
    parser.add_argument(
        '--platforms',
        nargs='+',
        default=None,
        help='プラットフォーム名のリスト（デフォルト: base ebay）複数指定可能'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='DRY RUNモード（実際の更新は行わない）'
    )
    parser.add_argument(
        '--skip-cache-update',
        action='store_true',
        help='キャッシュ更新をスキップ（既存キャッシュを使用、テスト用）'
    )
    parser.add_argument(
        '--max-items',
        type=int,
        default=None,
        help='テスト用：処理する最大商品数（省略時は全件）'
    )
    parser.add_argument(
        '--stock-check-only',
        action='store_true',
        help='在庫チェックのみ実行（SP-API同期・価格計算をスキップ）'
    )

    args = parser.parse_args()

    # デーモンを作成して実行
    daemon = SyncInventoryDaemon(
        interval_seconds=args.interval,
        platforms=args.platforms,
        dry_run=args.dry_run,
        skip_cache_update=args.skip_cache_update,
        max_items=args.max_items,
        stock_check_only=args.stock_check_only
    )

    daemon.run()


if __name__ == '__main__':
    main()
