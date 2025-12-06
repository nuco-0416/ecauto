"""
ソーシング候補確認スクリプト

sourcing_candidatesテーブルの状態を確認
"""

import sys
import sqlite3
from pathlib import Path
from datetime import datetime


def main():
    # データベースパス
    db_path = Path(__file__).parent.parent / 'data' / 'sourcing.db'

    if not db_path.exists():
        print(f"[ERROR] データベースが見つかりません: {db_path}")
        return

    print("=" * 60)
    print(f"ソーシング候補確認 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # 統計情報を表示
        print("\n統計情報:")

        # ステータス別件数
        cursor.execute("""
            SELECT
                SUM(CASE WHEN status = 'candidate' THEN 1 ELSE 0 END) as candidate,
                SUM(CASE WHEN status = 'imported' THEN 1 ELSE 0 END) as imported,
                COUNT(*) as total
            FROM sourcing_candidates
        """)

        row = cursor.fetchone()

        if row and row['total'] > 0:
            print(f"  未登録ASIN: {row['candidate']}件")
            print(f"  登録済みASIN: {row['imported']}件")
            print(f"  合計: {row['total']}件")
        else:
            print("  （データなし）")

        print("\n" + "=" * 60)

    except Exception as e:
        print(f"[ERROR] エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()


if __name__ == '__main__':
    main()
