"""
データベースバックアップスクリプト

master.dbと関連ファイルをバックアップします。
"""

import sys
from pathlib import Path
from datetime import datetime
import shutil

# パスを追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from inventory.core.master_db import MasterDB


def backup_database(db_path: Path, backup_dir: Path) -> Path:
    """
    データベースをバックアップ

    Args:
        db_path: データベースファイルのパス
        backup_dir: バックアップディレクトリ

    Returns:
        Path: バックアップファイルのパス
    """
    # バックアップディレクトリを作成
    backup_dir.mkdir(parents=True, exist_ok=True)

    # タイムスタンプ付きファイル名
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_file = backup_dir / f"{db_path.stem}_backup_{timestamp}{db_path.suffix}"

    # データベースファイルをコピー
    shutil.copy2(db_path, backup_file)

    # ファイルサイズ取得
    file_size = backup_file.stat().st_size / (1024 * 1024)  # MB

    print(f"バックアップ作成成功:")
    print(f"  元ファイル: {db_path}")
    print(f"  バックアップ: {backup_file}")
    print(f"  ファイルサイズ: {file_size:.2f} MB")

    return backup_file


def list_backups(backup_dir: Path, limit: int = 10) -> list:
    """
    バックアップファイル一覧を取得

    Args:
        backup_dir: バックアップディレクトリ
        limit: 表示件数

    Returns:
        list: バックアップファイルのリスト
    """
    if not backup_dir.exists():
        return []

    backups = sorted(
        backup_dir.glob("*_backup_*.db"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )

    return backups[:limit]


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='データベースバックアップ'
    )
    parser.add_argument(
        '--list',
        action='store_true',
        help='バックアップファイル一覧を表示'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=10,
        help='一覧表示件数（デフォルト: 10）'
    )

    args = parser.parse_args()

    # パス設定
    project_root = Path(__file__).resolve().parent.parent.parent
    db_path = project_root / 'inventory' / 'data' / 'master.db'
    backup_dir = project_root / 'inventory' / 'data' / 'backups'

    print("=" * 70)
    print("データベースバックアップ")
    print("=" * 70)

    if args.list:
        # バックアップ一覧を表示
        print(f"\nバックアップ一覧（最新{args.limit}件）:")
        backups = list_backups(backup_dir, limit=args.limit)

        if not backups:
            print("  バックアップファイルがありません")
        else:
            for i, backup_file in enumerate(backups, 1):
                file_size = backup_file.stat().st_size / (1024 * 1024)
                file_time = datetime.fromtimestamp(backup_file.stat().st_mtime)
                print(f"  {i}. {backup_file.name}")
                print(f"     サイズ: {file_size:.2f} MB")
                print(f"     作成日時: {file_time.strftime('%Y-%m-%d %H:%M:%S')}")
                print()
    else:
        # バックアップ作成
        if not db_path.exists():
            print(f"\nエラー: データベースファイルが見つかりません")
            print(f"  パス: {db_path}")
            sys.exit(1)

        print(f"\nデータベースファイル: {db_path}")
        print(f"バックアップ先: {backup_dir}")

        # バックアップ実行
        backup_file = backup_database(db_path, backup_dir)

        print("\n" + "=" * 70)
        print("バックアップ完了")
        print("=" * 70)

        # バックアップファイル数を確認
        all_backups = list_backups(backup_dir, limit=100)
        print(f"\n総バックアップ数: {len(all_backups)}件")

        if len(all_backups) > 10:
            print(f"\n注意: 古いバックアップが{len(all_backups)}件あります")
            print(f"ディスク容量を節約するため、不要なバックアップを削除することを推奨します")


if __name__ == '__main__':
    main()
