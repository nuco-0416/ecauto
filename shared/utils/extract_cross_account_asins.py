#!/usr/bin/env python3
"""
クロスアカウントASIN抽出ツール

ソースアカウント（例: base_account_1）に存在するが、
対象アカウント（例: base_account_3）には存在しないASINを抽出します。

使い方:
    python shared/utils/extract_cross_account_asins.py \
        --source-account base_account_1 \
        --target-account base_account_3 \
        --platform base \
        --limit 1000 \
        --output asins_for_account3.txt
"""

import sys
import argparse
import sqlite3
from pathlib import Path


def extract_asins(
    source_account: str,
    target_account: str,
    platform: str,
    limit: int,
    output_file: str,
    db_path: str = "inventory/data/master.db"
) -> int:
    """
    ソースアカウントから対象アカウントに存在しないASINを抽出

    Args:
        source_account: ソースアカウントID（例: base_account_1）
        target_account: 対象アカウントID（例: base_account_3）
        platform: プラットフォーム名（base/mercari/yahoo/ebay）
        limit: 抽出する最大件数
        output_file: 出力ファイルパス
        db_path: データベースファイルパス

    Returns:
        int: 抽出されたASIN数
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # ソースアカウントにあって対象アカウントにないASINを抽出
    query = """
        SELECT DISTINCT l.asin
        FROM listings l
        WHERE l.platform = ?
          AND l.account_id = ?
          AND l.status = 'listed'
          AND l.asin NOT IN (
            SELECT asin
            FROM listings
            WHERE platform = ?
              AND account_id = ?
          )
        LIMIT ?
    """

    cursor.execute(query, (platform, source_account, platform, target_account, limit))
    results = cursor.fetchall()

    # ファイルに出力
    with open(output_file, 'w', encoding='utf-8') as f:
        for row in results:
            f.write(f"{row[0]}\n")

    conn.close()

    return len(results)


def main():
    parser = argparse.ArgumentParser(
        description='クロスアカウントASIN抽出ツール',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
  # base_account_1からbase_account_3に展開可能なASINを1000件抽出
  python shared/utils/extract_cross_account_asins.py \\
      --source-account base_account_1 \\
      --target-account base_account_3 \\
      --platform base \\
      --limit 1000 \\
      --output asins_for_account3.txt

  # 不足分を追加で抽出（2回目）
  python shared/utils/extract_cross_account_asins.py \\
      --source-account base_account_1 \\
      --target-account base_account_3 \\
      --platform base \\
      --limit 500 \\
      --offset 1000 \\
      --output asins_for_account3_additional.txt
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
        help='対象アカウントID（例: base_account_3）'
    )
    parser.add_argument(
        '--platform',
        type=str,
        required=True,
        choices=['base', 'mercari', 'yahoo', 'ebay'],
        help='プラットフォーム名'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=1000,
        help='抽出する最大件数（デフォルト: 1000）'
    )
    parser.add_argument(
        '--offset',
        type=int,
        default=0,
        help='スキップする件数（複数回実行時に使用、デフォルト: 0）'
    )
    parser.add_argument(
        '--output',
        type=str,
        required=True,
        help='出力ファイルパス（例: asins_for_account3.txt）'
    )
    parser.add_argument(
        '--db-path',
        type=str,
        default='inventory/data/master.db',
        help='データベースファイルパス（デフォルト: inventory/data/master.db）'
    )
    parser.add_argument(
        '--append',
        action='store_true',
        help='既存ファイルに追記（デフォルト: 上書き）'
    )

    args = parser.parse_args()

    print("=" * 80)
    print("クロスアカウントASIN抽出")
    print("=" * 80)
    print(f"\nソースアカウント: {args.source_account}")
    print(f"対象アカウント: {args.target_account}")
    print(f"プラットフォーム: {args.platform}")
    print(f"抽出件数: {args.limit}件")
    print(f"オフセット: {args.offset}件")
    print(f"出力ファイル: {args.output}")
    print(f"モード: {'追記' if args.append else '上書き'}")

    # offsetをサポートするためにクエリを修正
    if args.offset > 0:
        conn = sqlite3.connect(args.db_path)
        cursor = conn.cursor()

        query = """
            SELECT DISTINCT l.asin
            FROM listings l
            WHERE l.platform = ?
              AND l.account_id = ?
              AND l.status = 'listed'
              AND l.asin NOT IN (
                SELECT asin
                FROM listings
                WHERE platform = ?
                  AND account_id = ?
              )
            LIMIT ? OFFSET ?
        """

        cursor.execute(query, (
            args.platform, args.source_account,
            args.platform, args.target_account,
            args.limit, args.offset
        ))
        results = cursor.fetchall()

        # ファイルに出力
        mode = 'a' if args.append else 'w'
        with open(args.output, mode, encoding='utf-8') as f:
            for row in results:
                f.write(f"{row[0]}\n")

        conn.close()
        extracted_count = len(results)
    else:
        # offsetなしの場合は元の関数を使用
        extracted_count = extract_asins(
            source_account=args.source_account,
            target_account=args.target_account,
            platform=args.platform,
            limit=args.limit,
            output_file=args.output,
            db_path=args.db_path
        )

    print("\n" + "=" * 80)
    print("抽出完了")
    print("=" * 80)
    print(f"抽出されたASIN数: {extracted_count}件")
    print(f"出力ファイル: {args.output}")
    print("=" * 80)

    if extracted_count == 0:
        print("\n⚠️ 抽出可能なASINがありませんでした")
        print("   - ソースアカウントに出品済み商品がない")
        print("   - または、すべて対象アカウントに既に存在する")

    return 0


if __name__ == '__main__':
    sys.exit(main())
