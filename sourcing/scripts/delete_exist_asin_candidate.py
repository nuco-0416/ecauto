"""
重複ASIN除外スクリプト

sourcing_candidatesから、既にproductsテーブルに存在するASINを除外する。
import_candidates_to_master.py の前処理として使用。

処理内容:
1. sourcing_candidates から status='candidate' のASINを取得
2. products テーブルで重複チェック
3. 重複ASIN → status='duplicate' に更新（論理削除）
4. 要求件数に達するまで確認
5. 候補不足の場合 → 状況報告して終了
"""

import sys
import argparse
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import List, Set, Tuple

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from inventory.core.master_db import MasterDB
from shared.utils.logger import setup_logger


class DuplicateASINRemover:
    """
    sourcing_candidatesから重複ASINを除外するクラス
    """

    def __init__(self, required_count: int, dry_run: bool = False):
        """
        Args:
            required_count: 必要なASIN件数
            dry_run: Trueの場合、実際の更新は行わず確認のみ
        """
        self.required_count = required_count
        self.dry_run = dry_run

        # ロガーを設定
        self.logger = setup_logger('delete_exist_asin_candidate', console_output=True)

        # データベースパス
        self.sourcing_db_path = project_root / 'sourcing' / 'data' / 'sourcing.db'

        # MasterDB初期化
        self.master_db = MasterDB()

        # 統計情報
        self.stats = {
            'total_candidates': 0,      # 候補総数
            'duplicates_found': 0,      # 重複として検出された件数
            'duplicates_updated': 0,    # status='duplicate'に更新した件数
            'available_count': 0,       # 処理可能件数
            'shortage': 0               # 不足件数
        }

    def run(self) -> bool:
        """
        メイン処理

        Returns:
            bool: 要求件数を満たせた場合True
        """
        self.logger.info("=" * 70)
        self.logger.info("重複ASIN除外スクリプト")
        self.logger.info("=" * 70)
        self.logger.info(f"実行モード: {'DRY RUN（確認のみ）' if self.dry_run else '本番実行'}")
        self.logger.info(f"要求件数: {self.required_count}件")
        self.logger.info("=" * 70)

        # 1. 候補ASINを取得
        self.logger.info("[1/3] sourcing_candidates から候補を取得中...")
        candidate_asins = self._get_candidate_asins()
        self.stats['total_candidates'] = len(candidate_asins)
        self.logger.info(f"      候補総数: {len(candidate_asins)}件")

        if not candidate_asins:
            self.logger.warning("処理対象の候補がありません")
            self._print_summary()
            return False

        # 2. productsテーブルで重複チェック
        self.logger.info("[2/3] products テーブルで重複チェック中...")
        duplicate_asins, new_asins = self._check_duplicates(candidate_asins)
        self.stats['duplicates_found'] = len(duplicate_asins)
        self.stats['available_count'] = len(new_asins)

        self.logger.info(f"      重複ASIN: {len(duplicate_asins)}件")
        self.logger.info(f"      新規ASIN: {len(new_asins)}件")

        # 3. 重複ASINのstatus更新
        self.logger.info("[3/3] 重複ASINのstatus更新中...")
        if duplicate_asins:
            if not self.dry_run:
                updated_count = self._update_duplicate_status(duplicate_asins)
                self.stats['duplicates_updated'] = updated_count
                self.logger.info(f"      更新完了: {updated_count}件 → status='duplicate'")
            else:
                self.logger.info(f"      [DRY RUN] {len(duplicate_asins)}件を更新予定")
                self.stats['duplicates_updated'] = len(duplicate_asins)

                # DRY RUN時は最初の10件を表示
                if len(duplicate_asins) > 0:
                    self.logger.info("      重複ASINの例（最初の10件）:")
                    for asin in list(duplicate_asins)[:10]:
                        self.logger.info(f"        - {asin}")
                    if len(duplicate_asins) > 10:
                        self.logger.info(f"        ... 他 {len(duplicate_asins) - 10}件")
        else:
            self.logger.info("      重複ASINなし（更新不要）")

        # 不足件数の計算
        if self.stats['available_count'] < self.required_count:
            self.stats['shortage'] = self.required_count - self.stats['available_count']

        # サマリー表示
        self._print_summary()

        return self.stats['shortage'] == 0

    def _get_candidate_asins(self) -> List[str]:
        """
        sourcing_candidatesから status='candidate' のASINを取得

        Returns:
            list: ASINのリスト
        """
        conn = sqlite3.connect(self.sourcing_db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT DISTINCT asin
                FROM sourcing_candidates
                WHERE status = 'candidate'
                ORDER BY discovered_at DESC
            """)
            asins = [row[0] for row in cursor.fetchall()]
            return asins

        finally:
            conn.close()

    def _check_duplicates(self, asins: List[str]) -> Tuple[Set[str], Set[str]]:
        """
        productsテーブルで重複チェック

        Args:
            asins: チェック対象のASINリスト

        Returns:
            Tuple[Set[str], Set[str]]: (重複ASIN集合, 新規ASIN集合)
        """
        duplicate_asins = set()
        new_asins = set()

        # バッチ処理で効率化
        batch_size = 500
        total = len(asins)

        for i in range(0, total, batch_size):
            batch = asins[i:i + batch_size]

            for asin in batch:
                product = self.master_db.get_product(asin)
                if product:
                    duplicate_asins.add(asin)
                else:
                    new_asins.add(asin)

            # 進捗表示
            processed = min(i + batch_size, total)
            self.logger.info(f"      チェック進捗: {processed}/{total}件")

        return duplicate_asins, new_asins

    def _update_duplicate_status(self, asins: Set[str]) -> int:
        """
        重複ASINのstatusを 'duplicate' に更新

        Args:
            asins: 更新対象のASIN集合

        Returns:
            int: 更新した件数
        """
        conn = sqlite3.connect(self.sourcing_db_path)
        cursor = conn.cursor()
        updated_count = 0

        try:
            now = datetime.now().isoformat()

            for asin in asins:
                cursor.execute("""
                    UPDATE sourcing_candidates
                    SET status = 'duplicate',
                        imported_at = ?
                    WHERE asin = ? AND status = 'candidate'
                """, (now, asin))
                updated_count += cursor.rowcount

            conn.commit()
            return updated_count

        finally:
            conn.close()

    def _print_summary(self):
        """サマリーを表示"""
        self.logger.info("")
        self.logger.info("=" * 70)
        self.logger.info("=== 重複チェック完了 ===")
        self.logger.info("=" * 70)
        self.logger.info(f"要求件数:       {self.required_count:>6}件")
        self.logger.info(f"候補総数:       {self.stats['total_candidates']:>6}件")
        self.logger.info(f"重複除外:       {self.stats['duplicates_found']:>6}件（status='duplicate'に更新）")
        self.logger.info(f"処理可能:       {self.stats['available_count']:>6}件")
        self.logger.info("=" * 70)

        if self.stats['shortage'] > 0:
            self.logger.warning("")
            self.logger.warning(f"  候補が {self.stats['shortage']}件 不足しています")
            self.logger.warning("  sourcingの追加実行を検討してください")
            self.logger.warning("")
        else:
            self.logger.info("")
            self.logger.info("  要求件数を満たしています")
            self.logger.info(f"  次のステップ: import_candidates_to_master.py --limit {self.required_count}")
            self.logger.info("")

        if self.dry_run:
            self.logger.info("[DRY RUN完了] 実際の更新は行われていません")

        self.logger.info("=" * 70)


def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(
        description='重複ASIN除外スクリプト - sourcing_candidatesから既存ASINを除外'
    )
    parser.add_argument(
        '--count',
        type=int,
        required=True,
        help='必要なASIN件数（必須）'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='DRY RUNモード（確認のみ、実際の更新は行わない）'
    )

    args = parser.parse_args()

    if args.count <= 0:
        print("エラー: --count は1以上の値を指定してください")
        sys.exit(1)

    remover = DuplicateASINRemover(
        required_count=args.count,
        dry_run=args.dry_run
    )

    success = remover.run()

    # 終了コード: 0=成功（要求件数を満たした）、1=不足
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
