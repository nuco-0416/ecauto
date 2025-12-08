"""
デーモン基底クラス

レガシーシステムのシンプルさと、堅牢性を兼ね備えた基底クラス

特徴:
- シンプルな while True ループ（レガシーeBayシステム準拠）
- クロスプラットフォーム対応（Windows/Linux/Docker）
- Graceful shutdown（SIGINT/SIGTERM対応）
- 構造化ログ（ファイル出力 + ローテーション）
- エラーリトライ機能
"""

import sys
from pathlib import Path
import time
import signal
import threading
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import traceback
import os

# パスを追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.utils.logger import setup_logger

# 通知機能（オプショナル）
try:
    from shared.utils.notifier import Notifier
    NOTIFIER_AVAILABLE = True
except ImportError:
    NOTIFIER_AVAILABLE = False


class DaemonBase(ABC):
    """
    デーモン基底クラス

    サブクラスで execute_task() を実装することで、
    定期実行デーモンを簡単に作成できます。

    使用例:
        class MyDaemon(DaemonBase):
            def execute_task(self) -> bool:
                # タスク実装
                print("タスク実行")
                return True

        daemon = MyDaemon('my_daemon', interval_seconds=3600)
        daemon.run()
    """

    def __init__(
        self,
        name: str,
        interval_seconds: int = 3600,
        log_file: Optional[Path] = None,
        max_retries: int = 3,
        retry_delay_seconds: int = 60,
        enable_notifications: bool = True
    ):
        """
        Args:
            name: デーモン名（ログファイル名にも使用）
            interval_seconds: 実行間隔（秒）デフォルト: 3600（1時間）
            log_file: ログファイルのパス（指定しない場合は logs/{name}.log）
            max_retries: タスク失敗時の最大リトライ回数（デフォルト: 3）
            retry_delay_seconds: リトライ時の待機時間（秒、デフォルト: 60）
            enable_notifications: 通知機能を有効にするか（デフォルト: True）
        """
        self.name = name
        self.interval_seconds = interval_seconds
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds

        # フラグ
        self.running = False
        self.shutdown_requested = False
        self._shutdown_event = threading.Event()  # シグナル受信時に即座に待機を中断するため

        # ロガーセットアップ
        self.logger = setup_logger(
            name=name,
            log_file=log_file,
            console_output=True
        )

        # 通知機能のセットアップ
        self.notifier = None
        if enable_notifications and NOTIFIER_AVAILABLE:
            try:
                self.notifier = Notifier()
                if self.notifier.config.get('enabled', False):
                    self.logger.info(f"通知機能が有効です（方法: {self.notifier.config.get('method', 'unknown')}）")
            except Exception as e:
                self.logger.warning(f"通知機能の初期化に失敗: {e}")
                self.notifier = None

        # シグナルハンドラの設定
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """
        シグナルハンドラ（Ctrl+C、kill等）

        シグナルハンドラ内ではスレッドセーフでない操作（ロギング等）は
        避け、単純なフラグ操作のみを行う。

        Args:
            signum: シグナル番号
            frame: フレーム情報
        """
        # シグナルハンドラ内では最小限の処理のみ行う
        # （ロギングはスレッドセーフでない可能性があるため避ける）
        self.shutdown_requested = True
        self._shutdown_event.set()  # 待機中のスレッドを即座に起こす

        # 安全なwrite（シグナル安全）
        try:
            import sys
            sys.stderr.write(f"\n[SIGNAL] シグナル {signum} を受信しました。シャットダウン開始...\n")
            sys.stderr.flush()
        except:
            pass  # シグナルハンドラ内ではエラーを無視

    def _interruptible_sleep(self, total_seconds: float) -> bool:
        """
        割り込み可能なsleep（シグナル応答性を向上）

        短いポーリング間隔（1秒）でEvent.wait()を繰り返し、
        shutdown_requestedフラグをチェックすることで、
        シグナル受信時に最大1秒以内に応答します。

        Args:
            total_seconds: 待機時間（秒）

        Returns:
            bool: 正常に待機完了した場合True、シグナルで中断された場合False
        """
        POLL_INTERVAL = 1.0  # 1秒ごとにシャットダウン要求をチェック
        elapsed = 0.0

        while elapsed < total_seconds:
            # シャットダウン要求をチェック（フラグベース）
            if self.shutdown_requested:
                self.logger.info("待機中に停止シグナルを受け取りました（フラグ）")
                return False

            # 残り時間とポーリング間隔の小さい方を待機
            remaining = total_seconds - elapsed
            wait_time = min(POLL_INTERVAL, remaining)

            # Event.wait()で短時間待機
            interrupted = self._shutdown_event.wait(timeout=wait_time)
            if interrupted:
                self.logger.info("待機中に停止シグナルを受け取りました（Event）")
                return False

            elapsed += wait_time

        return True

    @abstractmethod
    def execute_task(self) -> bool:
        """
        実行すべきタスク（サブクラスで実装）

        Returns:
            bool: 成功時True、失敗時False

        例:
            def execute_task(self) -> bool:
                try:
                    sync_inventory(dry_run=False)
                    return True
                except Exception as e:
                    self.logger.error(f"エラー: {e}")
                    return False
        """
        pass

    def _execute_with_retry(self) -> bool:
        """
        リトライ機能付きでタスクを実行

        Returns:
            bool: 最終的な成功/失敗
        """
        for attempt in range(1, self.max_retries + 1):
            # シャットダウン要求チェック（リトライループ内）
            if self.shutdown_requested:
                self.logger.info("シャットダウン要求を検出（リトライループ中断）")
                return False

            try:
                if attempt > 1:
                    self.logger.info(f"リトライ {attempt}/{self.max_retries}")

                success = self.execute_task()

                if success:
                    return True
                else:
                    if attempt < self.max_retries:
                        self.logger.warning(
                            f"タスク失敗（{attempt}/{self.max_retries}）"
                            f"{self.retry_delay_seconds}秒後にリトライします..."
                        )
                        if not self._interruptible_sleep(self.retry_delay_seconds):
                            # シグナルで中断された場合
                            return False
                    else:
                        self.logger.error(
                            f"タスク失敗（最大リトライ回数 {self.max_retries} に到達）"
                        )
                        # 通知: リトライ回数上限
                        if self.notifier:
                            self.notifier.notify(
                                'retry_exhausted',
                                f'{self.name} - リトライ回数上限',
                                f'タスクが{self.max_retries}回失敗しました。\n手動での確認が必要です。',
                                'ERROR'
                            )
                        return False

            except Exception as e:
                self.logger.error(
                    f"タスク実行中に例外が発生しました（{attempt}/{self.max_retries}）: {e}",
                    exc_info=True
                )

                # 通知: タスク失敗（初回のみ）
                if attempt == 1 and self.notifier:
                    self.notifier.notify(
                        'task_failure',
                        f'{self.name} - タスク失敗',
                        f'エラーが発生しました: {str(e)}\n\nリトライします...',
                        'WARNING'
                    )

                if attempt < self.max_retries:
                    self.logger.info(f"{self.retry_delay_seconds}秒後にリトライします...")
                    if not self._interruptible_sleep(self.retry_delay_seconds):
                        # シグナルで中断された場合
                        return False
                else:
                    self.logger.error(f"最大リトライ回数に到達しました")
                    return False

        return False

    def run(self):
        """
        メインループ（レガシーシステムの while True パターン）

        この関数は無限ループを実行し、定期的に execute_task() を呼び出します。
        Ctrl+C または kill シグナルで停止できます。
        """
        self.logger.info("="*60)
        self.logger.info(f"{self.name} デーモン起動")
        self.logger.info("="*60)
        self.logger.info(f"実行間隔: {self.interval_seconds}秒 ({self.interval_seconds / 3600:.1f}時間)")
        self.logger.info(f"最大リトライ回数: {self.max_retries}")
        self.logger.info("停止するには Ctrl+C を押してください")
        self.logger.info("="*60)

        # 通知: デーモン起動
        if self.notifier:
            self.notifier.notify(
                'daemon_start',
                f'{self.name} - デーモン起動',
                f'デーモンが起動しました。\n実行間隔: {self.interval_seconds}秒',
                'INFO'
            )

        self.running = True

        # レガシーシステムと同じ while True パターン
        while True:
            try:
                # シャットダウン要求チェック
                if self.shutdown_requested:
                    self.logger.info("シャットダウン要求を検出しました")
                    break

                # タスク実行
                self.logger.info("")
                self.logger.info(f"--- タスク実行開始 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")
                start_time = datetime.now()

                success = self._execute_with_retry()

                elapsed_seconds = (datetime.now() - start_time).total_seconds()

                if success:
                    self.logger.info(
                        f"--- タスク成功 （所要時間: {elapsed_seconds:.1f}秒） ---"
                    )
                else:
                    self.logger.warning(
                        f"--- タスク失敗 （所要時間: {elapsed_seconds:.1f}秒） ---"
                    )

                # 次回実行時刻を計算
                next_run_time = datetime.now() + timedelta(seconds=self.interval_seconds)

                self.logger.info(
                    f"次回実行: {next_run_time.strftime('%Y-%m-%d %H:%M:%S')} ごろ"
                )
                self.logger.info(
                    f"({self.interval_seconds}秒待機...)"
                )

                # 待機（短い間隔で分割してシグナル応答性を向上）
                if not self._interruptible_sleep(self.interval_seconds):
                    # シグナルで中断された場合
                    break

            except KeyboardInterrupt:
                # レガシーシステムと同じエラー処理
                self.logger.info("KeyboardInterrupt を受け取りました")
                break

            except Exception as e:
                # レガシーシステムと同じ: ループは継続
                self.logger.error(
                    f"!!! 重大なエラーが発生しました（ループ継続）: {e}"
                )
                self.logger.error(traceback.format_exc())

                self.logger.info(
                    f"{self.interval_seconds}秒後にタスクを再実行します..."
                )

                if not self._interruptible_sleep(self.interval_seconds):
                    # シグナルで中断された場合
                    break

        # シャットダウン処理
        self.logger.info("")
        self.logger.info("="*60)
        self.logger.info("デーモンをシャットダウンしています...")
        self.logger.info("="*60)

        self.running = False

        # 通知: デーモン停止
        if self.notifier:
            self.notifier.notify(
                'daemon_stop',
                f'{self.name} - デーモン停止',
                f'デーモンが正常に停止しました。',
                'INFO'
            )

        self.logger.info(f"{self.name} デーモンを停止しました")
        self.logger.info("お疲れ様でした")

    def send_completion_report(
        self,
        task_name: str,
        stats: Dict[str, Any],
        next_run_time: Optional[datetime] = None
    ):
        """
        タスク完了時に詳細レポートを通知

        Args:
            task_name: タスク名
            stats: 統計情報（辞書）
            next_run_time: 次回実行予定時刻（オプション）
        """
        if not self.notifier or not self.notifier.is_enabled('task_completion'):
            return

        # 次回実行時刻の計算（引数で渡されていない場合）
        if next_run_time is None:
            next_run_time = datetime.now() + timedelta(seconds=self.interval_seconds)

        # レポートメッセージを作成
        message_lines = []

        # 統計情報をフォーマット
        if stats:
            for key, value in stats.items():
                if isinstance(value, dict):
                    # ネストされた辞書の場合
                    message_lines.append(f"【{key}】")
                    for sub_key, sub_value in value.items():
                        if isinstance(sub_value, (int, float)):
                            message_lines.append(f"  {sub_key}: {sub_value:,}")
                        else:
                            message_lines.append(f"  {sub_key}: {sub_value}")
                elif isinstance(value, (int, float)) and key != 'duration_seconds':
                    message_lines.append(f"{key}: {value:,}")

        # 次回実行時刻
        message_lines.append(f"\n次回実行予定: {next_run_time.strftime('%Y-%m-%d %H:%M:%S')}")

        report_message = "\n".join(message_lines)

        # 通知送信
        self.notifier.notify(
            event_type='task_completion',
            title=f'{task_name} - 処理完了',
            message=report_message,
            level='INFO'
        )

    def stop(self):
        """
        デーモンを停止（外部から呼び出す場合）

        通常は Ctrl+C や kill シグナルで停止しますが、
        プログラム内から停止する場合にこのメソッドを使用します。
        """
        self.logger.info("stop() が呼び出されました")
        self.shutdown_requested = True
        self.running = False
