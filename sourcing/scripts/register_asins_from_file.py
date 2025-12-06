"""
ASINファイルからsourcing_candidatesテーブルに登録するスクリプト

使用例:
    python sourcing/scripts/register_asins_from_file.py \
      --input base_asins_combined_20251127.txt
"""

import argparse
import sqlite3
import sys
from pathlib import Path
from datetime import datetime


def register_asins(input_file: Path, db_path: Path):
    """
    ASINファイルからDBに登録

    Args:
        input_file: ASINファイルパス
        db_path: sourcing.dbのパス
    """
    # ASINファイルを読み込む
    print("=" * 60)
    print("ASINファイルからDB登録")
    print("=" * 60)
    print(f"入力ファイル: {input_file}")
    print(f"データベース: {db_path}")
    print()

    if not input_file.exists():
        print(f"[ERROR] ファイルが見つかりません: {input_file}")
        sys.exit(1)

    # ASINを読み込む
    asins = []
    with input_file.open('r', encoding='utf-8') as f:
        for line in f:
            asin = line.strip()
            if asin:  # 空行をスキップ
                asins.append(asin)

    print(f"[OK] {len(asins)}件のASINを読み込みました")
    print()

    # DBに登録
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        saved_count = 0
        updated_count = 0

        print("DBへの登録を開始...")

        for i, asin in enumerate(asins, 1):
            # 既存チェック
            cursor.execute('SELECT id FROM sourcing_candidates WHERE asin = ?', (asin,))
            existing = cursor.fetchone()

            if existing:
                # 既存の場合は更新（最終発見日時を更新）
                cursor.execute('''
                    UPDATE sourcing_candidates
                    SET discovered_at = ?
                    WHERE asin = ?
                ''', (datetime.now().isoformat(), asin))
                updated_count += 1
            else:
                # 新規の場合は挿入
                cursor.execute('''
                    INSERT INTO sourcing_candidates (
                        asin,
                        source,
                        status,
                        discovered_at
                    ) VALUES (?, 'sellersprite', 'candidate', ?)
                ''', (asin, datetime.now().isoformat()))
                saved_count += 1

            # 進捗表示（100件ごと）
            if i % 100 == 0:
                print(f"  処理中: {i}/{len(asins)}件 (新規={saved_count}, 更新={updated_count})")

        conn.commit()

        print()
        print("=" * 60)
        print("登録完了")
        print("=" * 60)
        print(f"総ASIN数:     {len(asins)}件")
        print(f"新規登録:     {saved_count}件")
        print(f"既存更新:     {updated_count}件")
        print("=" * 60)

        if saved_count == 0:
            print()
            print("[INFO] すべてのASINが既にDB内に存在していました")

    except Exception as e:
        print()
        print(f"[ERROR] エラーが発生しました: {e}")
        conn.rollback()
        sys.exit(1)

    finally:
        conn.close()


def main():
    """メイン処理"""
    parser = argparse.ArgumentParser(
        description='ASINファイルからsourcing_candidatesテーブルに登録',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # 基本的な使用方法
  python sourcing/scripts/register_asins_from_file.py \\
    --input base_asins_combined_20251127.txt

  # DBパスを指定
  python sourcing/scripts/register_asins_from_file.py \\
    --input base_asins_combined_20251127.txt \\
    --db sourcing/data/sourcing.db
        """
    )

    parser.add_argument(
        '--input',
        required=True,
        type=str,
        help='ASINファイルパス（1行に1つのASIN）'
    )
    parser.add_argument(
        '--db',
        type=str,
        help='sourcing.dbのパス（デフォルト: sourcing/data/sourcing.db）'
    )

    args = parser.parse_args()

    # パスを解決
    input_file = Path(args.input)

    if args.db:
        db_path = Path(args.db)
    else:
        # デフォルトのDBパス
        project_root = Path(__file__).parent.parent.parent
        db_path = project_root / 'sourcing' / 'data' / 'sourcing.db'

    if not db_path.exists():
        print(f"[ERROR] データベースが見つかりません: {db_path}")
        print(f"[INFO] 先に init_sourcing_db.py を実行してデータベースを作成してください")
        sys.exit(1)

    # 登録実行
    register_asins(input_file, db_path)


if __name__ == '__main__':
    main()
