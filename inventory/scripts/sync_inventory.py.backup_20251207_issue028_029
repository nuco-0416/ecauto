"""
統合インベントリ同期スクリプト

キャッシュ検証 → 差分補完 → 価格・在庫同期を一括実行
本番環境（数万件規模）を想定した統合ワークフロー
"""

import sys
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

# ロガーの設定
logger = logging.getLogger(__name__)

# Windows環境でのUTF-8エンコーディング強制設定 + バッファリング無効化
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except AttributeError:
        # Python 3.7未満の場合のフォールバック
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
else:
    # UTF-8だがバッファリングを無効化
    try:
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except AttributeError:
        pass

# パスを追加
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from inventory.scripts.validate_and_fill_cache import CacheValidator
from platforms.base.scripts.sync_prices import PriceSync
from inventory.scripts.sync_stock_visibility import StockVisibilitySync


class InventorySync:
    """
    統合インベントリ同期クラス
    """

    def __init__(self, dry_run: bool = False):
        """
        初期化

        Args:
            dry_run: Trueの場合、実際の更新は行わない
        """
        logger.info(f"[DEBUG] InventorySync.__init__ 開始 (dry_run={dry_run})")
        self.dry_run = dry_run

        # 各コンポーネント
        logger.info("[DEBUG] CacheValidator初期化中...")
        self.cache_validator = CacheValidator(dry_run=dry_run)
        logger.info("[DEBUG] CacheValidator初期化完了")

        logger.info("[DEBUG] PriceSync初期化中...")
        self.price_sync = PriceSync()
        logger.info("[DEBUG] PriceSync初期化完了")

        logger.info("[DEBUG] StockVisibilitySync初期化中...")
        self.stock_sync = StockVisibilitySync()
        logger.info("[DEBUG] StockVisibilitySync初期化完了")

        # 統計情報
        self.stats = {
            'start_time': None,
            'end_time': None,
            'duration_seconds': 0,
            'cache_validation': {},
            'price_sync': {},
            'stock_sync': {},
            'total_errors': 0
        }
        logger.info("[DEBUG] InventorySync.__init__ 完了")

    def run_full_sync(self, platform: str = 'base', skip_cache_update: bool = False, max_items: int = None) -> Dict[str, Any]:
        """
        完全同期を実行（キャッシュ検証 → 価格同期 → 在庫同期）

        Args:
            platform: プラットフォーム名
            skip_cache_update: Trueの場合、SP-API処理をスキップして既存キャッシュを使用（テスト用）
            max_items: テスト用：処理する最大商品数（省略時は全件）

        Returns:
            dict: 実行結果
        """
        logger.info(f"[DEBUG] run_full_sync 開始 (platform={platform})")
        self.stats['start_time'] = datetime.now()
        logger.info(f"[DEBUG] start_time設定完了: {self.stats['start_time']}")

        logger.info("[DEBUG] ログ出力開始...")
        logger.info("=" * 70)
        logger.info("統合インベントリ同期を開始")
        logger.info("=" * 70)
        logger.info(f"プラットフォーム: {platform}")
        logger.info(f"実行モード: {'DRY RUN（実際の更新なし）' if self.dry_run else '本番実行'}")
        logger.info(f"開始時刻: {self.stats['start_time'].strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 70)

        try:
            # Step 1: 価格同期
            logger.info("")
            logger.info("┌─────────────────────────────────────────────────────┐")
            logger.info("│ Step 1: 価格同期                                     │")
            logger.info("└─────────────────────────────────────────────────────┘")
            logger.info("")

            # ISSUE #006対応: SP-APIレート制限のため並列処理を無効化
            # 並列処理により複数アカウントが同時にリクエストを送信し、レート制限を超える問題を回避
            price_stats = self.price_sync.sync_all_accounts(dry_run=self.dry_run, parallel=False, skip_cache_update=skip_cache_update, max_items=max_items)
            self.stats['price_sync'] = price_stats

            # Step 2: 在庫同期（visibility更新）
            logger.info("")
            logger.info("┌─────────────────────────────────────────────────────┐")
            logger.info("│ Step 2: 在庫同期（visibility更新）                   │")
            logger.info("└─────────────────────────────────────────────────────┘")
            logger.info("")

            stock_stats = self.stock_sync.sync_all_listings(
                platform=platform,
                dry_run=self.dry_run
            )
            self.stats['stock_sync'] = stock_stats

        except Exception as e:
            logger.error(f"統合同期中にエラーが発生しました: {e}", exc_info=True)
            self.stats['total_errors'] += 1
            raise

        finally:
            self.stats['end_time'] = datetime.now()
            self.stats['duration_seconds'] = (
                self.stats['end_time'] - self.stats['start_time']
            ).total_seconds()

        # 統合サマリー表示
        self._print_summary()

        return self.stats

    def run_price_only(self, platform: str = 'base') -> Dict[str, Any]:
        """
        価格同期のみ実行（キャッシュ検証 → 価格同期）

        Args:
            platform: プラットフォーム名

        Returns:
            dict: 実行結果
        """
        self.stats['start_time'] = datetime.now()

        logger.info("=" * 70)
        logger.info("価格同期を開始")
        logger.info("=" * 70)
        logger.info(f"プラットフォーム: {platform}")
        logger.info(f"実行モード: {'DRY RUN（実際の更新なし）' if self.dry_run else '本番実行'}")
        logger.info(f"開始時刻: {self.stats['start_time'].strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 70)

        try:
            # Step 1: 価格同期
            logger.info("┌─────────────────────────────────────────────────────┐")
            logger.info("│ Step 1: 価格同期                                     │")
            logger.info("└─────────────────────────────────────────────────────┘")

            # ISSUE #006対応: SP-APIレート制限のため並列処理を無効化
            price_stats = self.price_sync.sync_all_accounts(dry_run=self.dry_run, parallel=False)
            self.stats['price_sync'] = price_stats

        except Exception as e:
            logger.error(f"価格同期中にエラーが発生しました: {e}", exc_info=True)
            self.stats['total_errors'] += 1
            raise

        finally:
            self.stats['end_time'] = datetime.now()
            self.stats['duration_seconds'] = (
                self.stats['end_time'] - self.stats['start_time']
            ).total_seconds()

        # サマリー表示
        self._print_summary()

        return self.stats

    def run_stock_only(self, platform: str = 'base') -> Dict[str, Any]:
        """
        在庫同期のみ実行（キャッシュ検証 → 在庫同期）

        Args:
            platform: プラットフォーム名

        Returns:
            dict: 実行結果
        """
        self.stats['start_time'] = datetime.now()

        logger.info("=" * 70)
        logger.info("在庫同期を開始")
        logger.info("=" * 70)
        logger.info(f"プラットフォーム: {platform}")
        logger.info(f"実行モード: {'DRY RUN（実際の更新なし）' if self.dry_run else '本番実行'}")
        logger.info(f"開始時刻: {self.stats['start_time'].strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 70)

        try:
            # Step 1: 在庫同期
            logger.info("┌─────────────────────────────────────────────────────┐")
            logger.info("│ Step 1: 在庫同期（visibility更新）                   │")
            logger.info("└─────────────────────────────────────────────────────┘")

            stock_stats = self.stock_sync.sync_all_listings(
                platform=platform,
                dry_run=self.dry_run
            )
            self.stats['stock_sync'] = stock_stats

        except Exception as e:
            logger.error(f"在庫同期中にエラーが発生しました: {e}", exc_info=True)
            self.stats['total_errors'] += 1
            raise

        finally:
            self.stats['end_time'] = datetime.now()
            self.stats['duration_seconds'] = (
                self.stats['end_time'] - self.stats['start_time']
            ).total_seconds()

        # サマリー表示
        self._print_summary()

        return self.stats

    def _print_summary(self):
        """統合サマリーを表示"""
        logger.info("")
        logger.info("=" * 70)
        logger.info("統合同期結果サマリー")
        logger.info("=" * 70)

        # 価格同期結果
        if self.stats['price_sync']:
            ps = self.stats['price_sync']
            logger.info("")
            logger.info("【価格同期】")
            logger.info(f"  処理した出品: {ps.get('total_listings', 0)}件")
            logger.info(f"  価格更新: {ps.get('price_updated', 0)}件")
            logger.info(f"  更新不要: {ps.get('no_update_needed', 0)}件")
            logger.info(f"  キャッシュヒット率: {ps.get('cache_hits', 0) / max(ps.get('total_listings', 1), 1) * 100:.1f}%")
            logger.info(f"  エラー: {ps.get('errors', 0)}件")

        # 在庫同期結果
        if self.stats['stock_sync']:
            ss = self.stats['stock_sync']
            logger.info("")
            logger.info("【在庫同期】")
            logger.info(f"  処理した商品: {ss.get('total_products', 0)}件")
            logger.info(f"  在庫あり: {ss.get('in_stock_count', 0)}件")
            logger.info(f"  在庫切れ: {ss.get('out_of_stock_count', 0)}件")
            logger.info(f"  非公開に変更: {ss.get('updated_to_hidden', 0)}件")
            logger.info(f"  公開に変更: {ss.get('updated_to_public', 0)}件")
            logger.info(f"  エラー: {ss.get('errors', 0)}件")

        # 全体統計
        total_errors = (
            self.stats.get('price_sync', {}).get('errors', 0) +
            self.stats.get('stock_sync', {}).get('errors', 0)
        )

        logger.info("")
        logger.info("【全体統計】")
        logger.info(f"  実行時間: {self.stats['duration_seconds']:.1f}秒 ({self.stats['duration_seconds']/60:.1f}分)")
        logger.info(f"  総エラー数: {total_errors}件")
        logger.info(f"  ステータス: {'完了' if total_errors == 0 else '一部エラーあり'}")

        logger.info("=" * 70)
        logger.info(f"終了時刻: {self.stats['end_time'].strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("")


def main():
    """メイン処理"""
    import argparse

    parser = argparse.ArgumentParser(
        description='統合インベントリ同期スクリプト'
    )
    parser.add_argument(
        '--platform',
        default='base',
        help='プラットフォーム名（デフォルト: base）'
    )
    parser.add_argument(
        '--price-only',
        action='store_true',
        help='価格同期のみ実行'
    )
    parser.add_argument(
        '--stock-only',
        action='store_true',
        help='在庫同期のみ実行'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='DRY RUNモード（実際の更新なし）'
    )

    args = parser.parse_args()

    # ロギング設定（統計サマリーを表示するため）
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[logging.StreamHandler(sys.stdout)]
    )

    # 統合同期実行
    sync = InventorySync(dry_run=args.dry_run)

    try:
        if args.price_only:
            stats = sync.run_price_only(platform=args.platform)
        elif args.stock_only:
            stats = sync.run_stock_only(platform=args.platform)
        else:
            stats = sync.run_full_sync(platform=args.platform)

        # エラーがあれば終了コード1
        total_errors = (
            stats.get('price_sync', {}).get('errors', 0) +
            stats.get('stock_sync', {}).get('errors', 0)
        )

        if total_errors > 0:
            sys.exit(1)
        else:
            sys.exit(0)

    except Exception as e:
        logger.error(f"統合同期に失敗しました: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
