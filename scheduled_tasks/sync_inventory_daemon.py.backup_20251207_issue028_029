"""
在庫同期デーモン

定期的にAmazon在庫・価格を取得し、複数プラットフォームと同期します。

機能:
- キャッシュ検証と差分補完（SP-API → キャッシュ、1回のみ実行）
- 価格同期（キャッシュ → 各プラットフォーム、並列実行）
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

    # 既存キャッシュを使用（SP-API処理をスキップ、テスト用）
    python scheduled_tasks/sync_inventory_daemon.py --skip-cache-update --dry-run

    # 少量テスト（5件のみ処理）
    python scheduled_tasks/sync_inventory_daemon.py --skip-cache-update --dry-run --max-items 5
"""

import sys
from pathlib import Path
import argparse
import os
import msvcrt  # Windows用ファイルロック
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any
import time

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


class SyncInventoryDaemon(DaemonBase):
    """
    在庫同期デーモン（マルチプラットフォーム並列処理対応）

    定期的に以下の処理を実行します:
    1. Amazon SP-APIから最新の価格・在庫情報を取得（キャッシュベース、1回のみ実行）
    2. 各プラットフォームの価格を並列同期（BASE、eBay等）
    3. 各プラットフォームの在庫状況（visibility）を並列同期

    アーキテクチャ:
        Phase 1: SP-API → キャッシュ（シリアル処理、レート制限対策）
        Phase 2: キャッシュ → 各プラットフォーム（並列処理、ThreadPoolExecutor）
    """

    def __init__(
        self,
        interval_seconds: int = 10800,
        platforms: List[str] = None,
        dry_run: bool = False,
        skip_cache_update: bool = False,
        max_items: int = None
    ):
        """
        Args:
            interval_seconds: 実行間隔（秒）デフォルト: 10800（3時間 - ISSUE #005対応）
            platforms: プラットフォーム名のリスト（デフォルト: ['base', 'ebay']）
            dry_run: DRY RUNモード（デフォルト: False）
            skip_cache_update: キャッシュ更新をスキップ（既存キャッシュを使用、テスト用）
            max_items: テスト用：処理する最大商品数（省略時は全件）
        """
        # ロックファイルで単一インスタンスを保証
        lock_dir = Path(__file__).parent.parent / 'logs'
        lock_dir.mkdir(exist_ok=True)
        self.lock_file_path = lock_dir / 'sync_inventory_daemon.lock'

        print(f"[LOCK] ロックファイル取得試行: {self.lock_file_path} - PID: {os.getpid()}", flush=True)

        try:
            # ロックファイルを開く（存在しない場合は作成）
            self.lock_file = open(self.lock_file_path, 'w')
            # Windows用ファイルロック取得（非ブロッキング）
            msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            # ロック成功 - PIDを書き込む
            self.lock_file.write(f"{os.getpid()}\n")
            self.lock_file.flush()
            print(f"[LOCK] ロック取得成功 - PID: {os.getpid()}", flush=True)
        except (IOError, OSError) as e:
            print(f"[LOCK] エラー: 別のインスタンスが既に実行中です", flush=True)
            print(f"[LOCK] ロックファイル: {self.lock_file_path}", flush=True)
            print(f"[LOCK] 詳細: {e}", flush=True)
            print(f"[LOCK] このプロセスを終了します - PID: {os.getpid()}", flush=True)
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
            if self.max_items:
                self.logger.info(f"処理件数制限: {self.max_items}件（テストモード）")
            self.logger.info("=" * 70)

            # 各プラットフォームのアカウント情報を表示
            for platform in self.platforms:
                self._log_platform_accounts(platform)

            # Phase 1: SP-API → キャッシュ（シリアル処理、1回のみ）
            # skip_cache_updateが有効な場合はスキップ
            if self.skip_cache_update:
                self.logger.info("\n" + "=" * 70)
                self.logger.info("【Phase 1】SP-API → キャッシュ同期: スキップ")
                self.logger.info("既存のキャッシュデータを使用します")
                self.logger.info("=" * 70)
            else:
                # このフェーズは全プラットフォーム共通のため、1回だけ実行
                # InventorySyncのrun_full_syncが内部でSP-APIからキャッシュへの同期を実施
                # ここでは明示的な処理は不要（各プラットフォームの同期処理内で実施される）
                pass

            # Phase 2: キャッシュ → 各プラットフォーム（並列処理）
            self.logger.info("\n" + "=" * 70)
            self.logger.info("【Phase 2】キャッシュ → 各プラットフォーム同期（並列処理）")
            self.logger.info("=" * 70)

            # ThreadPoolExecutorで並列実行
            platform_stats = {}
            with ThreadPoolExecutor(max_workers=len(self.platforms)) as executor:
                # 各プラットフォームの同期タスクを投入
                future_to_platform = {
                    executor.submit(self._sync_platform, platform): platform
                    for platform in self.platforms
                }

                # 結果を収集
                for future in as_completed(future_to_platform):
                    platform = future_to_platform[future]
                    try:
                        stats = future.result()
                        platform_stats[platform] = stats
                        self.logger.info(f"✓ {platform.upper()} 同期完了")
                    except Exception as e:
                        self.logger.error(f"✗ {platform.upper()} 同期エラー: {e}", exc_info=True)
                        platform_stats[platform] = {'error': str(e)}

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
                # skip_cache_updateが有効な場合は、キャッシュ更新をスキップ
                stats = self.sync_instances[platform].run_full_sync(
                    platform=platform,
                    skip_cache_update=self.skip_cache_update,
                    max_items=self.max_items
                )
            elif platform == 'ebay':
                # eBay: 価格同期のみ（既にキャッシュベース）
                price_stats = self.sync_instances[platform].sync_all_accounts(
                    dry_run=self.dry_run,
                    max_items=self.max_items
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
                print(f"[LOCK] ロックファイル解放 - PID: {os.getpid()}", flush=True)
                self.lock_file.close()
            if hasattr(self, 'lock_file_path') and self.lock_file_path.exists():
                self.lock_file_path.unlink()
                print(f"[LOCK] ロックファイル削除: {self.lock_file_path}", flush=True)
        except Exception as e:
            print(f"[LOCK] クリーンアップ中にエラー: {e}", flush=True)


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

    args = parser.parse_args()

    # デーモンを作成して実行
    daemon = SyncInventoryDaemon(
        interval_seconds=args.interval,
        platforms=args.platforms,
        dry_run=args.dry_run,
        skip_cache_update=args.skip_cache_update,
        max_items=args.max_items
    )

    daemon.run()


if __name__ == '__main__':
    main()
