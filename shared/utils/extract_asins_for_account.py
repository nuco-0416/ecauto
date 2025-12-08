#!/usr/bin/env python3
"""
アカウント間でASINリストを抽出するツール

使用例:
  # アカウント1からアカウント2向けにASINを抽出（1000件）
  python shared/utils/extract_asins_for_account.py \\
    --source-account base_account_1 \\
    --target-account base_account_2 \\
    --limit 1000 \\
    --output asins_for_account2.txt

  # 全件抽出
  python shared/utils/extract_asins_for_account.py \\
    --source-account base_account_1 \\
    --target-account base_account_3 \\
    --output asins_for_account3.txt

  # プラットフォーム指定
  python shared/utils/extract_asins_for_account.py \\
    --source-account base_account_1 \\
    --target-account base_account_2 \\
    --platform base \\
    --limit 500 \\
    --output asins.txt
"""

import sys
import argparse
import sqlite3
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))


def extract_asins_for_account(
    source_account: str,
    target_account: str,
    platform: str = 'base',
    limit: int = None,
    output_file: str = None,
    db_path: str = None
) -> list:
    """
    ソースアカウントの既存出品からターゲットアカウント向けにASINを抽出

    Args:
        source_account: ソースアカウントID
        target_account: ターゲットアカウントID
        platform: プラットフォーム名（デフォルト: 'base'）
        limit: 抽出する最大件数（Noneの場合は全件）
        output_file: 出力ファイルパス（Noneの場合は標準出力）
        db_path: データベースファイルパス（Noneの場合はデフォルト）

    Returns:
        list: 抽出したASINのリスト
    """
    # デフォルトのデータベースパス
    if db_path is None:
        db_path = project_root / 'inventory' / 'data' / 'master.db'

    # データベースに接続
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # クエリを構築
    query = """
        SELECT DISTINCT l1.asin
        FROM listings l1
        WHERE l1.platform = ?
          AND l1.account_id = ?
          AND NOT EXISTS (
              SELECT 1
              FROM listings l2
              WHERE l2.asin = l1.asin
                AND l2.platform = ?
                AND l2.account_id = ?
          )
        ORDER BY l1.created_at DESC
    """

    params = [platform, source_account, platform, target_account]

    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)

    # クエリを実行
    cursor.execute(query, params)
    asins = [row[0] for row in cursor.fetchall()]

    conn.close()

    # 結果を出力
    if output_file:
        output_path = Path(output_file)
        with open(output_path, 'w', encoding='utf-8') as f:
            for asin in asins:
                f.write(f"{asin}\\n")
        print(f"[INFO] {len(asins)}件のASINを {output_file} に出力しました")
    else:
        for asin in asins:
            print(asin)

    return asins


def main():
    parser = argparse.ArgumentParser(
        description='アカウント間でASINリストを抽出するツール',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # アカウント1からアカウント2向けにASINを抽出（1000件）
  python shared/utils/extract_asins_for_account.py \\
    --source-account base_account_1 \\
    --target-account base_account_2 \\
    --limit 1000 \\
    --output asins_for_account2.txt

  # 全件抽出
  python shared/utils/extract_asins_for_account.py \\
    --source-account base_account_1 \\
    --target-account base_account_3 \\
    --output asins_for_account3.txt
        """
    )

    parser.add_argument(
        '--source-account',
        type=str,
        required=True,
        help='ソースアカウントID（例: base_account_1）'
    )
    parser.add_argument(
        '--target-account',
        type=str,
        required=True,
        help='ターゲットアカウントID（例: base_account_2）'
    )
    parser.add_argument(
        '--platform',
        type=str,
        default='base',
        help='プラットフォーム名（デフォルト: base）'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='抽出する最大件数（指定しない場合は全件）'
    )
    parser.add_argument(
        '--output',
        type=str,
        default=None,
        help='出力ファイルパス（指定しない場合は標準出力）'
    )
    parser.add_argument(
        '--db-path',
        type=str,
        default=None,
        help='データベースファイルパス（指定しない場合はデフォルト）'
    )

    args = parser.parse_args()

    print("=" * 60)
    print("ASIN抽出ツール")
    print("=" * 60)
    print(f"ソースアカウント: {args.source_account}")
    print(f"ターゲットアカウント: {args.target_account}")
    print(f"プラットフォーム: {args.platform}")
    print(f"最大件数: {args.limit if args.limit else '全件'}")
    print("=" * 60)

    # ASIN抽出を実行
    asins = extract_asins_for_account(
        source_account=args.source_account,
        target_account=args.target_account,
        platform=args.platform,
        limit=args.limit,
        output_file=args.output,
        db_path=args.db_path
    )

    print("=" * 60)
    print(f"抽出完了: {len(asins)}件")
    print("=" * 60)


if __name__ == "__main__":
    main()
