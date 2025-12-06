"""
Upload Scheduler Daemon

定期的にアップロードキューをチェックし、scheduled_at が到来したアイテムをアップロード
"""

import sys
from pathlib import Path
import time
import signal
from datetime import datetime, time as dt_time
from typing import Optional

# パスを追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scheduler.upload_executor import UploadExecutor
from scheduler.queue_manager import UploadQueueManager


class UploadSchedulerDaemon:
    """
    アップロードスケジューラーデーモン

    機能:
    - 指定間隔でキューをチェック
    - 営業時間内（6AM-11PM JST）のみ処理
    - Graceful shutdown対応
    """

    def __init__(
        self,
        check_interval_seconds: int = 60,
        batch_size: int = 10,
        platform: str = 'base',
        business_hours_start: int = 6,
        business_hours_end: int = 23
    ):
        """
        Args:
            check_interval_seconds: チェック間隔（秒）
            batch_size: 1回の処理件数
            platform: プラットフォーム名
            business_hours_start: 営業開始時刻（時）
            business_hours_end: 営業終了時刻（時）
        """
        self.check_interval_seconds = check_interval_seconds
        self.batch_size = batch_size
        self.platform = platform
        self.business_hours_start = business_hours_start
        self.business_hours_end = business_hours_end

        self.executor = UploadExecutor()
        self.queue_manager = UploadQueueManager()

        self.running = False
        self.shutdown_requested = False

        # シグナルハンドラの設定
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """シグナルハンドラ（Ctrl+C等）"""
        print(f"\n受信したシグナル: {signum}")
        print("シャットダウンを開始します...")
        self.shutdown_requested = True

    def _is_business_hours(self) -> bool:
        """営業時間内かチェック"""
        now = datetime.now()
        current_hour = now.hour

        return self.business_hours_start <= current_hour < self.business_hours_end

    def _print_status(self):
        """現在の状態を表示"""
        print(f"\n{'='*60}")
        print(f"デーモン状態 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}")

        # キュー統計を取得
        stats = self.queue_manager.get_queue_statistics(platform=self.platform)

        print(f"プラットフォーム: {self.platform}")
        print(f"営業時間: {self.business_hours_start}:00 - {self.business_hours_end}:00")
        print(f"営業時間内: {'はい' if self._is_business_hours() else 'いいえ'}")
        print(f"\nキュー統計:")
        print(f"  待機中 (pending): {stats['pending']}件")
        print(f"  処理中 (uploading): {stats['uploading']}件")
        print(f"  成功 (success): {stats['success']}件")
        print(f"  失敗 (failed): {stats['failed']}件")
        print(f"  合計: {stats['total']}件")
        print(f"{'='*60}\n")

    def run(self):
        """デーモンを実行"""
        print(f"\n{'='*60}")
        print("Upload Scheduler Daemon 起動")
        print(f"{'='*60}")
        print(f"プラットフォーム: {self.platform}")
        print(f"チェック間隔: {self.check_interval_seconds}秒")
        print(f"バッチサイズ: {self.batch_size}件")
        print(f"営業時間: {self.business_hours_start}:00 - {self.business_hours_end}:00")
        print(f"{'='*60}\n")

        self.running = True
        iteration = 0

        while self.running and not self.shutdown_requested:
            iteration += 1

            try:
                # 営業時間チェック
                if not self._is_business_hours():
                    if iteration % 10 == 1:  # 10回に1回表示
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] 営業時間外のため待機中...")
                    time.sleep(self.check_interval_seconds)
                    continue

                # 処理対象アイテムをチェック
                due_items = self.queue_manager.get_scheduled_items_due(
                    limit=self.batch_size,
                    platform=self.platform
                )

                if due_items:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] 処理対象: {len(due_items)}件")

                    # アップロード実行
                    result = self.executor.process_due_items(
                        platform=self.platform,
                        batch_size=self.batch_size
                    )

                    # 結果を表示
                    if result['processed'] > 0:
                        print(f"処理完了: 成功={result['success']}, 失敗={result['failed']}")

                else:
                    if iteration % 10 == 1:  # 10回に1回表示
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] 処理対象なし")

                # 定期的にステータス表示
                if iteration % 60 == 0:  # 約60分ごと
                    self._print_status()

                # 待機
                time.sleep(self.check_interval_seconds)

            except KeyboardInterrupt:
                print("\nKeyboardInterrupt を受信しました")
                break

            except Exception as e:
                print(f"[ERROR] エラーが発生しました: {e}")
                import traceback
                traceback.print_exc()
                print(f"{self.check_interval_seconds}秒後にリトライします...")
                time.sleep(self.check_interval_seconds)

        # シャットダウン
        print("\n" + "="*60)
        print("デーモンをシャットダウンしています...")
        print("="*60)

        self.running = False
        print("シャットダウン完了")

    def stop(self):
        """デーモンを停止"""
        self.running = False
        self.shutdown_requested = True


def main():
    """メイン関数"""
    import argparse

    parser = argparse.ArgumentParser(
        description='Upload Scheduler Daemon - 定期的にアップロードキューを処理'
    )
    parser.add_argument(
        '--interval',
        type=int,
        default=60,
        help='チェック間隔（秒、デフォルト: 60）'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=10,
        help='1回の処理件数（デフォルト: 10）'
    )
    parser.add_argument(
        '--platform',
        type=str,
        default='base',
        help='プラットフォーム名（デフォルト: base）'
    )
    parser.add_argument(
        '--start-hour',
        type=int,
        default=6,
        help='営業開始時刻（デフォルト: 6）'
    )
    parser.add_argument(
        '--end-hour',
        type=int,
        default=23,
        help='営業終了時刻（デフォルト: 23）'
    )

    args = parser.parse_args()

    # デーモンを作成して実行
    daemon = UploadSchedulerDaemon(
        check_interval_seconds=args.interval,
        batch_size=args.batch_size,
        platform=args.platform,
        business_hours_start=args.start_hour,
        business_hours_end=args.end_hour
    )

    daemon.run()


if __name__ == '__main__':
    main()
