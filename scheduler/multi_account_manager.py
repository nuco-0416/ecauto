"""
マルチアカウント・マルチプラットフォーム並列アップロードマネージャー

複数のupload_daemon_account.pyプロセスを並列起動・管理

機能:
- プラットフォーム×アカウント別に独立プロセスを起動
- プロセス監視・自動再起動
- 統合ログ・統合レポート
- Graceful Shutdown
"""

import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import subprocess
import time
from datetime import datetime
import signal
import os
import platform as platform_module

# パスを追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scheduler.config.accounts_config import (
    get_all_accounts,
    get_daemon_config,
    UPLOAD_ACCOUNTS
)


def check_existing_daemon_process(platform: str, account_id: str) -> Optional[int]:
    """
    システム全体で既存のデーモンプロセスが実行中かチェック
    
    get_all_daemon_processes()を使用して同じロジックでチェック

    Args:
        platform: プラットフォーム名
        account_id: アカウントID

    Returns:
        int: 既存プロセスのPID（存在しない場合はNone）
    """
    processes = get_all_daemon_processes()
    for p, a, pid in processes:
        if p == platform and a == account_id:
            return pid
    return None


def get_all_daemon_processes() -> List[Tuple[str, str, int]]:
    """
    システム全体で実行中の全デーモンプロセスを取得

    Returns:
        list: [(platform, account_id, pid), ...] のリスト
    """
    processes = []

    try:
        if platform_module.system() == 'Windows':
            # Windowsの場合はwmicを使用
            cmd = 'wmic process where "commandline like \'%upload_daemon_account.py%\'" get commandline,processid'
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                for line in lines[1:]:  # 最初の行はヘッダー
                    if 'upload_daemon_account.py' in line:
                        # コマンドラインからプラットフォームとアカウントを抽出
                        parts = line.split()
                        platform = None
                        account_id = None
                        pid = None

                        for i, part in enumerate(parts):
                            if part == '--platform' and i + 1 < len(parts):
                                platform = parts[i + 1]
                            elif part == '--account' and i + 1 < len(parts):
                                account_id = parts[i + 1]
                            elif part.isdigit() and len(part) > 3:  # PIDは通常4桁以上
                                pid = int(part)

                        if platform and account_id and pid:
                            # 重複チェック：同じアカウントの最初のプロセスのみ追加
                            if not any(p == platform and a == account_id for p, a, _ in processes):
                                processes.append((platform, account_id, pid))

    except Exception as e:
        print(f"[WARNING] プロセス一覧取得中にエラーが発生しました: {e}")

    return processes


def stop_all_manager_processes():
    """
    システム全体で実行中の全multi_account_managerプロセスを停止（restartプロセスは除外）
    """
    manager_pids = []

    try:
        if platform_module.system() == 'Windows':
            cmd = 'wmic process where "commandline like \'%multi_account_manager.py%\' and not commandline like \'%stop%\' and not commandline like \'%restart%\'" get processid'
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                for line in lines[1:]:  # 最初の行はヘッダー
                    line = line.strip()
                    if line and line.isdigit():
                        manager_pids.append(int(line))

    except Exception as e:
        print(f"[WARNING] managerプロセスの検出中にエラーが発生しました: {e}")

    if manager_pids:
        print(f"[INFO] {len(manager_pids)}個のmanagerプロセスを停止します")
        for pid in manager_pids:
            print(f"[STOP] multi_account_manager (PID: {pid}) を停止中...")
            try:
                if platform_module.system() == 'Windows':
                    subprocess.run(
                        ['taskkill', '/F', '/PID', str(pid), '/T'],  # /Tで子プロセスも停止
                        capture_output=True,
                        timeout=10
                    )
                else:
                    subprocess.run(
                        ['kill', '-9', str(pid)],
                        capture_output=True,
                        timeout=10
                    )
                print(f"  [OK] 停止しました")
            except Exception as e:
                print(f"  [ERROR] 停止に失敗しました: {e}")
        print()


def stop_all_daemon_processes():
    """
    システム全体で実行中の全デーモンプロセスとmanagerプロセスを停止
    """
    # まずmanagerプロセスを停止（これにより自動再起動が止まる）
    stop_all_manager_processes()

    # 少し待機
    time.sleep(2)

    # daemonプロセスを停止
    processes = get_all_daemon_processes()

    if not processes:
        print("[INFO] 実行中のデーモンプロセスはありません")
        # ロックファイルも削除
        remove_manager_lock()
        return

    print(f"[INFO] {len(processes)}個のデーモンプロセスを停止します")
    print()

    for platform, account_id, pid in processes:
        key = f"{platform}_{account_id}"
        print(f"[STOP] {key} (PID: {pid}) を停止中...")

        try:
            if platform_module.system() == 'Windows':
                subprocess.run(
                    ['taskkill', '/F', '/PID', str(pid)],
                    capture_output=True,
                    timeout=10
                )
            else:
                subprocess.run(
                    ['kill', '-9', str(pid)],
                    capture_output=True,
                    timeout=10
                )
            print(f"  [OK] 停止しました")

        except Exception as e:
            print(f"  [ERROR] 停止に失敗しました: {e}")

    print()
    print("[INFO] すべてのプロセスを停止しました")

    # ロックファイルを削除
    remove_manager_lock()


def check_manager_lock() -> bool:
    """
    multi_account_managerの重複起動をチェック

    Returns:
        bool: 既に起動中の場合True
    """
    lock_file = Path(__file__).parent.parent / 'logs' / 'multi_account_manager.lock'

    if lock_file.exists():
        # ロックファイルが存在する場合、PIDを読み取ってプロセスが実行中か確認
        try:
            with open(lock_file, 'r') as f:
                pid = int(f.read().strip())

            # プロセスが実行中かチェック
            if platform_module.system() == 'Windows':
                result = subprocess.run(
                    ['tasklist', '/FI', f'PID eq {pid}', '/NH'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if str(pid) in result.stdout:
                    return True  # プロセスが実行中
            else:
                try:
                    os.kill(pid, 0)  # シグナル0でプロセスの存在確認
                    return True  # プロセスが実行中
                except OSError:
                    pass  # プロセスは存在しない

            # ロックファイルは存在するがプロセスは実行中ではない（古いロック）
            print(f"[INFO] 古いロックファイルを削除します (PID: {pid})")
            lock_file.unlink()

        except Exception as e:
            print(f"[WARNING] ロックファイルのチェック中にエラーが発生しました: {e}")
            # エラーの場合は古いロックファイルとして削除
            try:
                lock_file.unlink()
            except:
                pass

    return False


def create_manager_lock():
    """
    multi_account_managerのロックファイルを作成
    """
    lock_file = Path(__file__).parent.parent / 'logs' / 'multi_account_manager.lock'
    lock_file.parent.mkdir(parents=True, exist_ok=True)

    with open(lock_file, 'w') as f:
        f.write(str(os.getpid()))


def remove_manager_lock():
    """
    multi_account_managerのロックファイルを削除
    """
    lock_file = Path(__file__).parent.parent / 'logs' / 'multi_account_manager.lock'

    try:
        if lock_file.exists():
            lock_file.unlink()
    except Exception as e:
        print(f"[WARNING] ロックファイルの削除に失敗しました: {e}")


class MultiAccountUploadManager:
    """
    マルチアカウントアップロードマネージャー

    複数のデーモンプロセスを並列起動し、死活監視・自動再起動を行う
    """

    def __init__(self):
        """
        初期化
        """
        self.processes: Dict[str, Dict] = {}
        self.shutdown_requested = False

        # シグナルハンドラを設定
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        print("=" * 60)
        print("マルチアカウントアップロードマネージャー")
        print("=" * 60)
        print()

    def _signal_handler(self, signum, frame):
        """
        シグナル受信時の処理（Ctrl+C等）

        Args:
            signum: シグナル番号
            frame: フレーム
        """
        print(f"\n\nシグナル {signum} を受信しました。プロセスを停止します...")
        self.shutdown_requested = True

    def start_all(self):
        """
        すべてのアカウントのデーモンを並列起動
        """
        accounts = get_all_accounts()

        if not accounts:
            print("[ERROR] アカウント構成が定義されていません")
            print("scheduler/config/accounts_config.py を確認してください")
            return

        print(f"起動するプロセス数: {len(accounts)}")
        print()

        for platform, account_id in accounts:
            self._start_daemon(platform, account_id)
            time.sleep(1)  # 起動間隔を少し開ける

        print()
        print("=" * 60)
        print(f"[OK] {len(self.processes)}個のプロセスを起動しました")
        print("=" * 60)
        print()

        self._show_process_list()

    def _start_daemon(self, platform: str, account_id: str):
        """
        個別デーモンを起動

        Args:
            platform: プラットフォーム名
            account_id: アカウントID
        """
        key = f'{platform}_{account_id}'

        # システム全体で既存プロセスをチェック
        existing_pid = check_existing_daemon_process(platform, account_id)
        if existing_pid:
            print(f"[SKIP] {key} は既にシステムで実行中です (PID: {existing_pid})")
            return

        # 既に起動している場合はスキップ（このインスタンス内での管理）
        if key in self.processes:
            existing = self.processes[key]
            if existing['process'].poll() is None:  # まだ実行中
                print(f"[SKIP] {key} は既に起動しています (PID: {existing['process'].pid})")
                return

        # 設定を取得
        config = get_daemon_config(account_id)

        # Pythonの実行パス
        python_exe = sys.executable

        # コマンドライン引数
        cmd = [
            python_exe,
            'scheduler/upload_daemon_account.py',
            '--platform', platform,
            '--account', account_id,
            '--interval', str(config['interval_seconds']),
            '--batch-size', str(config['batch_size']),
            '--start-hour', str(config['business_hours_start']),
            '--end-hour', str(config['business_hours_end']),
        ]

        # プロセスを起動
        try:
            # 環境変数を設定
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'

            # stdout/stderrをDEVNULLにリダイレクト（デーモンは既にログファイルに出力している）
            # パイプバッファの詰まりによるデッドロックを防ぐため
            process = subprocess.Popen(
                cmd,
                cwd=Path(__file__).resolve().parent.parent,  # プロジェクトルート
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if platform_module.system() == "Windows" else 0
            )

            self.processes[key] = {
                'process': process,
                'platform': platform,
                'account': account_id,
                'start_time': datetime.now(),
                'restart_count': 0,
                'config': config
            }

            print(f"[START] {key} (PID: {process.pid})")

        except Exception as e:
            print(f"[ERROR] {key} の起動に失敗しました: {e}")

    def monitor(self, check_interval: int = 60):
        """
        プロセスを監視し、停止したら再起動

        Args:
            check_interval: チェック間隔（秒）
        """
        print()
        print("=" * 60)
        print("プロセス監視を開始します")
        print(f"チェック間隔: {check_interval}秒")
        print("停止するには Ctrl+C を押してください")
        print("=" * 60)
        print()

        while not self.shutdown_requested:
            try:
                time.sleep(check_interval)

                if self.shutdown_requested:
                    break

                # 各プロセスの状態をチェック
                for key, info in list(self.processes.items()):
                    if self.shutdown_requested:
                        break

                    process = info['process']
                    returncode = process.poll()

                    if returncode is not None:  # プロセスが停止
                        # stdout/stderrはDEVNULLにリダイレクト済みのため読み取り不要
                        print()
                        print("=" * 60)
                        print(f"[STOPPED] {key} が停止しました（終了コード: {returncode}）")
                        print("ログファイルを確認してください: logs/upload_scheduler_{key}.log")
                        print("=" * 60)

                        # 自動再起動
                        if not self.shutdown_requested:
                            info['restart_count'] += 1
                            print(f"[RESTART] {key} を再起動します（再起動回数: {info['restart_count']}）")
                            self._start_daemon(info['platform'], info['account'])

            except KeyboardInterrupt:
                # Ctrl+Cが押された場合
                self.shutdown_requested = True
                break

        # シャットダウン処理
        self.shutdown_all()

    def _show_process_list(self):
        """
        プロセス一覧を表示
        """
        print("起動中のプロセス:")
        print()

        for key, info in self.processes.items():
            status = "Running" if info['process'].poll() is None else "Stopped"
            uptime = datetime.now() - info['start_time']
            uptime_str = str(uptime).split('.')[0]  # マイクロ秒を除外

            print(f"  [{status}] {key}")
            print(f"    PID: {info['process'].pid}")
            print(f"    稼働時間: {uptime_str}")
            print(f"    再起動回数: {info['restart_count']}")
            print(f"    設定: batch_size={info['config']['batch_size']}, "
                  f"interval={info['config']['interval_seconds']}s")
            print()

    def shutdown_all(self):
        """
        すべてのプロセスを停止
        """
        print()
        print("=" * 60)
        print("すべてのプロセスを停止しています...")
        print("=" * 60)
        print()

        for key, info in self.processes.items():
            process = info['process']

            if process.poll() is None:  # まだ実行中
                print(f"[STOP] {key} (PID: {process.pid}) を停止します...")

                try:
                    # Graceful Shutdown（SIGTERMを送信）
                    process.terminate()

                    # 最大10秒待機
                    for _ in range(10):
                        if process.poll() is not None:
                            break
                        time.sleep(1)

                    # まだ停止していない場合は強制終了
                    if process.poll() is None:
                        print(f"  [KILL] 強制終了します...")
                        process.kill()
                        process.wait()

                    print(f"  [OK] 停止しました")

                except Exception as e:
                    print(f"  [ERROR] 停止に失敗しました: {e}")

        print()
        print("=" * 60)
        print("すべてのプロセスを停止しました")
        print("お疲れ様でした")
        print("=" * 60)

    def get_status(self):
        """
        全プロセスのステータスを取得

        Returns:
            dict: ステータス情報
        """
        running = 0
        stopped = 0

        for info in self.processes.values():
            if info['process'].poll() is None:
                running += 1
            else:
                stopped += 1

        return {
            'total': len(self.processes),
            'running': running,
            'stopped': stopped,
            'processes': self.processes
        }


def main():
    """
    メイン処理
    """
    import argparse

    parser = argparse.ArgumentParser(
        description='マルチアカウントアップロードマネージャー',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
使用例:
  # プロセスを起動（デフォルト）
  python scheduler/multi_account_manager.py
  python scheduler/multi_account_manager.py start

  # 全プロセスを停止
  python scheduler/multi_account_manager.py stop

  # プロセス状態を確認
  python scheduler/multi_account_manager.py status

  # 全プロセスを再起動
  python scheduler/multi_account_manager.py restart
        '''
    )

    parser.add_argument(
        'action',
        nargs='?',
        default='start',
        choices=['start', 'stop', 'status', 'restart'],
        help='実行するアクション（デフォルト: start）'
    )

    args = parser.parse_args()

    if args.action == 'stop':
        # 全プロセスを停止
        print("=" * 60)
        print("全デーモンプロセスを停止します")
        print("=" * 60)
        print()
        stop_all_daemon_processes()

    elif args.action == 'status':
        # プロセス状態を表示
        print("=" * 60)
        print("デーモンプロセスの状態")
        print("=" * 60)
        print()
        processes = get_all_daemon_processes()
        if not processes:
            print("[INFO] 実行中のデーモンプロセスはありません")
        else:
            print(f"[INFO] {len(processes)}個のデーモンプロセスが実行中です")
            print()
            for platform, account_id, pid in processes:
                key = f"{platform}_{account_id}"
                print(f"  [{key}] PID: {pid}")
        print()

    elif args.action == 'restart':
        # 全プロセスを再起動
        print("=" * 60)
        print("全デーモンプロセスを再起動します")
        print("=" * 60)
        print()
        stop_all_daemon_processes()

        # ロックファイルを削除
        remove_manager_lock()

        print()
        print("3秒後に再起動します...")
        time.sleep(3)
        print()

        # 重複起動チェック
        if check_manager_lock():
            print("[ERROR] multi_account_managerは既に起動しています")
            print("       既存のプロセスを停止してから再起動してください")
            print("       停止するには: python scheduler/multi_account_manager.py stop")
            return

        # バックグラウンドで新しいmanagerプロセスを起動
        python_exe = sys.executable
        script_path = Path(__file__).resolve()
        
        print("バックグラウンドでmanagerプロセスを起動します...")
        
        if platform_module.system() == 'Windows':
            # Windowsの場合はSTARTINFOを使ってバックグラウンド起動
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE
            
            process = subprocess.Popen(
                [python_exe, str(script_path), 'start'],
                cwd=script_path.parent.parent,
                startupinfo=startupinfo,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        else:
            # Linux/Macの場合
            process = subprocess.Popen(
                [python_exe, str(script_path), 'start'],
                cwd=script_path.parent.parent,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
        
        print(f"[OK] バックグラウンドでmanagerプロセスを起動しました (PID: {process.pid})")
        print()
        print("プロセス状態を確認するには:")
        print("  python scheduler/multi_account_manager.py status")
        print()

    else:  # start
        # 重複起動チェック
        if check_manager_lock():
            print("=" * 60)
            print("[ERROR] multi_account_managerは既に起動しています")
            print("=" * 60)
            print()
            print("既存のプロセスを停止してから再起動してください")
            print()
            print("状態確認: python scheduler/multi_account_manager.py status")
            print("停止: python scheduler/multi_account_manager.py stop")
            print()
            return

        # ロックファイルを作成
        create_manager_lock()

        try:
            # プロセスを起動
            manager = MultiAccountUploadManager()
            manager.start_all()
            manager.monitor(check_interval=60)
        finally:
            # 終了時にロックファイルを削除
            remove_manager_lock()


if __name__ == '__main__':
    main()
