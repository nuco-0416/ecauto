"""
マルチアカウントログビューアー

複数のアカウント別ログファイルを統合表示
アカウント別にカラー表示

使い方:
    python scheduler/view_multi_logs.py
    python scheduler/view_multi_logs.py --platform base
    python scheduler/view_multi_logs.py --tail 50  # 最新50行のみ
"""

import sys
from pathlib import Path
import time
import re
from typing import List, Dict
from datetime import datetime
import argparse

# パスを追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ANSIカラーコード（Windowsターミナル対応）
class Colors:
    RESET = '\033[0m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    GRAY = '\033[90m'

    # アカウント別カラー
    ACCOUNT_COLORS = {
        'base_account_1': CYAN,
        'base_account_2': MAGENTA,
        'ebay_account_1': GREEN,
        'yahoo_account_1': YELLOW,
    }


def get_account_color(log_file: str) -> str:
    """
    ログファイル名からアカウント別カラーを取得

    Args:
        log_file: ログファイル名

    Returns:
        str: ANSIカラーコード
    """
    for account, color in Colors.ACCOUNT_COLORS.items():
        if account in log_file:
            return color
    return Colors.WHITE


def parse_log_line(line: str, log_file: str) -> Dict:
    """
    ログ行をパースして情報を抽出

    Args:
        line: ログ行
        log_file: ログファイル名

    Returns:
        dict: パース結果
    """
    # ログレベルを検出
    level = 'INFO'
    if '[ERROR]' in line:
        level = 'ERROR'
    elif '[WARNING]' in line:
        level = 'WARNING'
    elif '[DEBUG]' in line:
        level = 'DEBUG'

    # アカウント名を抽出
    account_match = re.search(r'base_account_\d+|ebay_account_\d+|yahoo_account_\d+', log_file)
    account_name = account_match.group(0) if account_match else 'unknown'

    return {
        'line': line.rstrip(),
        'level': level,
        'account': account_name,
        'file': log_file
    }


def colorize_log_line(parsed: Dict) -> str:
    """
    ログ行をカラー表示用に整形

    Args:
        parsed: パース結果

    Returns:
        str: カラー表示されたログ行
    """
    account_color = get_account_color(parsed['file'])
    level_color = Colors.WHITE

    if parsed['level'] == 'ERROR':
        level_color = Colors.RED
    elif parsed['level'] == 'WARNING':
        level_color = Colors.YELLOW
    elif parsed['level'] == 'DEBUG':
        level_color = Colors.GRAY

    # アカウント名を先頭に追加
    account_tag = f"{account_color}[{parsed['account']}]{Colors.RESET}"
    colored_line = f"{account_tag} {level_color}{parsed['line']}{Colors.RESET}"

    return colored_line


def follow_logs(log_files: List[Path], tail_lines: int = 0):
    """
    複数のログファイルをリアルタイム監視

    Args:
        log_files: ログファイルのリスト
        tail_lines: 初期表示行数（0の場合は全て）
    """
    # ファイルハンドルを開く
    file_handles = {}
    file_positions = {}

    for log_file in log_files:
        if log_file.exists():
            fh = open(log_file, 'r', encoding='utf-8', errors='ignore')

            # tail_linesが指定されている場合は最後のN行を表示
            if tail_lines > 0:
                lines = fh.readlines()
                for line in lines[-tail_lines:]:
                    parsed = parse_log_line(line, str(log_file))
                    print(colorize_log_line(parsed))
            else:
                # ファイルの最後に移動（既存ログをスキップ）
                fh.seek(0, 2)

            file_handles[str(log_file)] = fh
            file_positions[str(log_file)] = fh.tell()

    print()
    print("=" * 80)
    print(f"{Colors.GREEN}ログを監視中... (Ctrl+C で停止){Colors.RESET}")
    print("=" * 80)
    print()

    try:
        while True:
            has_new_data = False

            for log_file_str, fh in file_handles.items():
                # 新しい行を読み取る
                where = fh.tell()
                lines = fh.readlines()

                if lines:
                    has_new_data = True
                    for line in lines:
                        parsed = parse_log_line(line, log_file_str)
                        print(colorize_log_line(parsed))
                    file_positions[log_file_str] = fh.tell()
                else:
                    # ファイルが切り詰められたかチェック
                    fh.seek(0, 2)
                    if fh.tell() < where:
                        # ファイルがローテーションされた
                        fh.seek(0)
                        file_positions[log_file_str] = 0

            if not has_new_data:
                time.sleep(0.5)  # 0.5秒待機

    except KeyboardInterrupt:
        print()
        print("=" * 80)
        print(f"{Colors.YELLOW}監視を停止しました{Colors.RESET}")
        print("=" * 80)

    finally:
        # ファイルハンドルを閉じる
        for fh in file_handles.values():
            fh.close()


def main():
    """
    メイン処理
    """
    parser = argparse.ArgumentParser(
        description='マルチアカウントログビューアー'
    )
    parser.add_argument(
        '--platform',
        default='base',
        help='プラットフォーム名（デフォルト: base）'
    )
    parser.add_argument(
        '--tail',
        type=int,
        default=0,
        help='初期表示行数（0の場合はリアルタイム監視のみ）'
    )

    args = parser.parse_args()

    # ログディレクトリ
    logs_dir = Path(__file__).resolve().parent.parent / 'logs'

    # ログファイルを検索
    pattern = f'upload_scheduler_{args.platform}_*.log'
    log_files = list(logs_dir.glob(pattern))

    if not log_files:
        print(f"[ERROR] ログファイルが見つかりません: {logs_dir / pattern}")
        print()
        print("以下のコマンドでマルチアカウントマネージャーを起動してください:")
        print("  python scheduler/multi_account_manager.py")
        return

    print("=" * 80)
    print(f"{Colors.CYAN}マルチアカウントログビューアー{Colors.RESET}")
    print("=" * 80)
    print()
    print(f"監視中のログファイル: {len(log_files)}件")
    for log_file in log_files:
        account_color = get_account_color(str(log_file))
        print(f"  {account_color}- {log_file.name}{Colors.RESET}")
    print()

    # ログを監視
    follow_logs(log_files, tail_lines=args.tail)


if __name__ == '__main__':
    main()
