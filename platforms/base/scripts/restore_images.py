"""
BASE商品の画像復元スクリプト

SKU更新処理で消失した画像をローカルDBから復元します。

使用方法:
    # ドライラン
    python platforms/base/scripts/restore_images.py --dry-run

    # 本番実行
    python platforms/base/scripts/restore_images.py --yes

    # 特定の商品IDのみ
    python platforms/base/scripts/restore_images.py --item-ids 126131788,126131974 --yes
"""

import sys
from pathlib import Path
import argparse
import logging
import json
import sqlite3
from typing import List, Dict, Any, Optional
import time

# パスを追加
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / 'platforms' / 'base'))

from platforms.base.accounts.manager import AccountManager
from platforms.base.core.api_client import BaseAPIClient

# ロガー設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class ImageRestorer:
    """画像復元クラス"""

    def __init__(
        self,
        account_manager: AccountManager,
        db_path: str,
        dry_run: bool = True
    ):
        self.account_manager = account_manager
        self.db_path = db_path
        self.dry_run = dry_run

        # 統計情報
        self.stats = {
            'checked': 0,
            'has_images_in_db': 0,
            'no_images_in_db': 0,
            'restored': 0,
            'failed': 0,
            'skipped': 0
        }

    def get_images_from_db(self, asin: str) -> Optional[List[str]]:
        """
        DBからASINの画像URLリストを取得

        Args:
            asin: ASIN

        Returns:
            List[str]: 画像URLリスト、見つからない場合はNone
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute(
                'SELECT images FROM products WHERE asin = ?',
                (asin,)
            )
            row = cursor.fetchone()

            if row and row['images']:
                try:
                    images = json.loads(row['images'])
                    if isinstance(images, list) and images:
                        return images
                except json.JSONDecodeError:
                    logger.error(f"ASIN {asin}: 画像データのJSON解析に失敗")
                    return None

        finally:
            conn.close()

        return None

    def restore_item_images(
        self,
        api_client: BaseAPIClient,
        item_id: str,
        asin: str,
        account_id: str
    ) -> bool:
        """
        1商品の画像を復元

        Args:
            api_client: BaseAPIClientインスタンス
            item_id: BASE商品ID
            asin: ASIN
            account_id: アカウントID

        Returns:
            bool: 成功フラグ
        """
        self.stats['checked'] += 1

        # DBから画像を取得
        images = self.get_images_from_db(asin)

        if not images:
            logger.warning(f"Item {item_id} (ASIN: {asin}): DBに画像データがありません")
            self.stats['no_images_in_db'] += 1
            self.stats['skipped'] += 1
            return False

        logger.info(f"Item {item_id} (ASIN: {asin}): DBから{len(images)}枚の画像を取得")
        self.stats['has_images_in_db'] += 1

        if self.dry_run:
            logger.info(f"  [DRY-RUN] {len(images)}枚の画像を復元")
            for i, img_url in enumerate(images[:5], 1):  # 最初の5枚のみ表示
                logger.info(f"    {i}. {img_url}")
            if len(images) > 5:
                logger.info(f"    ... 他{len(images)-5}枚")
            self.stats['restored'] += 1
            return True

        # 画像を復元
        try:
            result = api_client.add_images_bulk(item_id, images)

            if result['success_count'] > 0:
                logger.info(
                    f"  ✓ {result['success_count']}枚の画像を復元しました "
                    f"(失敗: {result['failed_count']}枚)"
                )
                self.stats['restored'] += 1
                return True
            else:
                logger.error(
                    f"  ✗ 画像の復元に失敗しました "
                    f"(失敗: {result['failed_count']}枚)"
                )
                self.stats['failed'] += 1
                return False

        except Exception as e:
            logger.error(f"  ✗ 画像復元エラー: {e}")
            self.stats['failed'] += 1
            return False

    def run(
        self,
        account_id: str,
        item_id_asin_pairs: List[tuple]
    ):
        """
        画像復元処理を実行

        Args:
            account_id: アカウントID
            item_id_asin_pairs: [(item_id, asin), ...] のリスト
        """
        logger.info(f"\n{'='*70}")
        logger.info(f"画像復元処理開始")
        logger.info(f"モード: {'ドライラン（更新なし）' if self.dry_run else '本番実行'}")
        logger.info(f"アカウント: {account_id}")
        logger.info(f"対象商品数: {len(item_id_asin_pairs)}件")
        logger.info(f"{'='*70}\n")

        # API クライアント初期化
        api_client = BaseAPIClient(
            account_id=account_id,
            account_manager=self.account_manager
        )

        # 各商品を処理
        for i, (item_id, asin) in enumerate(item_id_asin_pairs, 1):
            logger.info(f"\n[{i}/{len(item_id_asin_pairs)}] Item ID: {item_id}")

            self.restore_item_images(api_client, item_id, asin, account_id)

            # レート制限対策
            if not self.dry_run and i < len(item_id_asin_pairs):
                time.sleep(1)

        # 最終結果
        logger.info(f"\n{'='*70}")
        logger.info(f"処理完了")
        logger.info(f"{'='*70}")
        logger.info(f"\n【統計】")
        logger.info(f"確認: {self.stats['checked']}件")
        logger.info(f"  - DBに画像あり: {self.stats['has_images_in_db']}件")
        logger.info(f"  - DBに画像なし: {self.stats['no_images_in_db']}件")
        logger.info(f"復元成功: {self.stats['restored']}件")
        logger.info(f"復元失敗: {self.stats['failed']}件")
        logger.info(f"スキップ: {self.stats['skipped']}件")
        logger.info(f"{'='*70}")


def main():
    parser = argparse.ArgumentParser(
        description='BASE商品の画像復元スクリプト',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        '--account-id',
        type=str,
        default='base_account_2',
        help='アカウントID（デフォルト: base_account_2）'
    )

    parser.add_argument(
        '--item-ids',
        type=str,
        help='復元する商品IDのカンマ区切りリスト（指定しない場合は全更新済み商品）'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='ドライラン（実際の復元を行わない）'
    )

    parser.add_argument(
        '--yes',
        action='store_true',
        help='確認プロンプトをスキップして自動実行'
    )

    args = parser.parse_args()

    # デフォルトの商品リスト（更新した10件）
    default_items = [
        ('126131788', 'B09KTYVX7Z'),  # 画像: 6枚
        ('126131812', 'B09KTYVX7Z'),  # 画像: 6枚（重複）
        ('126131974', 'B01M342KAC'),  # 画像: 2枚
        ('126132978', 'B0CP6JJYYX'),  # 画像: 9枚
        ('126133016', 'B0DKW8RYD3'),  # 画像: 0枚（スキップ）
        ('126133715', 'B09GTV616T'),  # 画像: 0枚（スキップ）
        ('126133723', 'B00LKE1Q44'),  # 画像: 7枚
        ('126133743', 'B08G19CTTG'),  # 画像: 9枚
        ('126133756', 'B08HHZ3KCC'),  # 画像: 8枚
        ('126133765', 'B089K1ZYD3'),  # 画像: 7枚
    ]

    # 商品IDのフィルタリング
    if args.item_ids:
        specified_ids = set(args.item_ids.split(','))
        items = [
            (item_id, asin) for item_id, asin in default_items
            if item_id in specified_ids
        ]
        if not items:
            print(f"エラー: 指定された商品IDが見つかりません")
            sys.exit(1)
    else:
        items = default_items

    # 本番実行の確認
    if not args.dry_run and not args.yes:
        print("\n" + "!"*70)
        print("警告: 本番実行モードです。BASE APIの商品に画像が追加されます。")
        print("!"*70)
        print(f"\n対象商品数: {len(items)}件")
        response = input("\n続行しますか？ (yes/no): ")
        if response.lower() != 'yes':
            print("中止しました")
            sys.exit(0)

    # 初期化
    account_manager = AccountManager()
    db_path = project_root / 'inventory' / 'data' / 'master.db'

    # 画像復元処理を実行
    restorer = ImageRestorer(account_manager, str(db_path), dry_run=args.dry_run)
    restorer.run(args.account_id, items)


if __name__ == '__main__':
    main()
