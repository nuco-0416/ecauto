"""
BASE商品のSKU修正スクリプト

SKUが空欄のBASE商品に対して、ローカルDBから適切なSKUを割り当てて更新します。

処理フロー:
1. BASE APIから全商品を取得
2. SKU（identifier）が空欄の商品を抽出
3. 商品タイトルでローカルDBを検索してASINを特定
4. ASINとアカウントIDからlistingsテーブルのSKUを取得
5. SKUが見つかった場合、BASE APIで商品を更新
6. SKUが見つからない場合、新規SKU生成も可能

使用方法:
    # ドライラン（実際の更新なし）
    python platforms/base/scripts/fix_missing_sku.py --dry-run

    # 本番実行（特定アカウント）
    python platforms/base/scripts/fix_missing_sku.py --account-id base_account_1

    # 本番実行（全アカウント）
    python platforms/base/scripts/fix_missing_sku.py --all-accounts

    # 最大処理件数を指定
    python platforms/base/scripts/fix_missing_sku.py --max-items 10 --dry-run
"""

import sys
from pathlib import Path
import argparse
import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import time
import re

# パスを追加
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / 'platforms' / 'base'))

from platforms.base.accounts.manager import AccountManager
from platforms.base.core.api_client import BaseAPIClient
from inventory.core.master_db import MasterDB
from shared.utils.sku_generator import generate_sku

# ロガー設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class SKUFixer:
    """SKU修正処理クラス"""

    def __init__(self, account_manager: AccountManager, db: MasterDB, dry_run: bool = True):
        """
        Args:
            account_manager: AccountManagerインスタンス
            db: MasterDBインスタンス
            dry_run: Trueの場合は実際の更新を行わない
        """
        self.account_manager = account_manager
        self.db = db
        self.dry_run = dry_run

        # 統計情報
        self.stats = {
            'total_checked': 0,
            'missing_sku': 0,
            'asin_found': 0,
            'asin_not_found': 0,
            'sku_found': 0,
            'sku_generated': 0,
            'updated': 0,
            'failed': 0,
            'skipped': 0
        }

    def find_sku_by_item_id(self, item_id: str, account_id: str) -> Optional[Tuple[str, str]]:
        """
        BASE商品IDからSKUとASINを検索

        Args:
            item_id: BASE商品ID
            account_id: アカウントID

        Returns:
            Tuple[str, str]: (SKU, ASIN) のタプル、見つからない場合はNone
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT sku, asin FROM listings
                WHERE platform = 'base'
                  AND account_id = ?
                  AND platform_item_id = ?
                  AND sku IS NOT NULL
                LIMIT 1
            """, (account_id, item_id))
            row = cursor.fetchone()
            if row:
                return (row['sku'], row['asin'])

        return None

    def find_asin_by_title(self, title: str) -> Optional[str]:
        """
        商品タイトルからASINを検索

        Args:
            title: 商品タイトル

        Returns:
            str: 見つかったASIN、見つからない場合はNone
        """
        if not title:
            return None

        # タイトルから検索（完全一致優先、次にLIKE検索）
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # 1. 完全一致
            cursor.execute("""
                SELECT asin FROM products
                WHERE title_ja = ? OR title_en = ?
                LIMIT 1
            """, (title, title))
            row = cursor.fetchone()
            if row:
                logger.debug(f"完全一致でASIN発見: {row['asin']}")
                return row['asin']

            # 2. LIKE検索（前方一致）
            # タイトルの最初の30文字で検索
            title_prefix = title[:30]
            cursor.execute("""
                SELECT asin, title_ja FROM products
                WHERE title_ja LIKE ? OR title_en LIKE ?
                LIMIT 1
            """, (f"{title_prefix}%", f"{title_prefix}%"))
            row = cursor.fetchone()
            if row:
                logger.debug(f"LIKE検索でASIN発見: {row['asin']} (DB: {row['title_ja'][:40]}...)")
                return row['asin']

        return None

    def get_sku_for_asin(self, asin: str, account_id: str) -> Optional[str]:
        """
        ASINとアカウントIDからSKUを取得

        Args:
            asin: ASIN
            account_id: アカウントID

        Returns:
            str: 見つかったSKU、見つからない場合はNone
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT sku FROM listings
                WHERE asin = ? AND platform = 'base' AND account_id = ?
                LIMIT 1
            """, (asin, account_id))
            row = cursor.fetchone()
            if row and row['sku']:
                return row['sku']

        return None

    def generate_new_sku(self, asin: str) -> str:
        """
        新規SKUを生成

        Args:
            asin: ASIN

        Returns:
            str: 生成されたSKU
        """
        return generate_sku('base', asin)

    def update_base_item_sku(
        self,
        api_client: BaseAPIClient,
        item_id: str,
        sku: str
    ) -> Tuple[bool, Optional[str]]:
        """
        BASE商品のSKUを更新

        Args:
            api_client: BaseAPIClientインスタンス
            item_id: BASE商品ID
            sku: 設定するSKU

        Returns:
            Tuple[bool, Optional[str]]: (成功フラグ, エラーメッセージ)
        """
        if self.dry_run:
            logger.info(f"  [DRY-RUN] Item {item_id} に SKU '{sku}' を設定")
            return True, None

        try:
            # BASE APIの仕様: /items/editは部分更新をサポート
            # identifierのみを指定すれば、他のフィールド（画像含む）は保持される
            api_client.update_item(item_id, {'identifier': sku})
            logger.info(f"  ✓ Item {item_id} に SKU '{sku}' を設定しました")
            logger.debug(f"    ※ BASE APIの仕様により、画像などの他のフィールドは保持されます")
            return True, None

        except Exception as e:
            error_msg = f"Item {item_id} の更新に失敗: {e}"
            logger.error(f"  ✗ {error_msg}")
            return False, error_msg

    def process_account(
        self,
        account_id: str,
        max_items: Optional[int] = None
    ) -> Dict[str, int]:
        """
        1つのアカウントの商品を処理

        Args:
            account_id: アカウントID
            max_items: 最大処理件数（Noneの場合は全件）

        Returns:
            dict: 処理統計
        """
        logger.info(f"\n{'='*70}")
        logger.info(f"アカウント: {account_id}")
        logger.info(f"{'='*70}")

        account_stats = {
            'checked': 0,
            'missing_sku': 0,
            'updated': 0,
            'failed': 0,
            'skipped': 0
        }

        try:
            # API クライアント初期化
            api_client = BaseAPIClient(
                account_id=account_id,
                account_manager=self.account_manager
            )

            # 全商品を取得
            logger.info("BASE APIから全商品を取得中...")
            all_items = api_client.get_all_items()
            logger.info(f"取得完了: {len(all_items)}件")

            # SKU空欄の商品を抽出
            missing_sku_items = [
                item for item in all_items
                if not item.get('identifier')
            ]

            account_stats['checked'] = len(all_items)
            account_stats['missing_sku'] = len(missing_sku_items)

            logger.info(f"SKU空欄: {len(missing_sku_items)}件")

            if not missing_sku_items:
                logger.info("処理対象の商品がありません")
                return account_stats

            # 最大処理件数を適用
            if max_items:
                missing_sku_items = missing_sku_items[:max_items]
                logger.info(f"最大処理件数制限: {len(missing_sku_items)}件を処理")

            # 各商品を処理
            logger.info(f"\n処理開始...")
            for i, item in enumerate(missing_sku_items, 1):
                item_id = item.get('item_id')
                title = item.get('title', '')

                logger.info(f"\n[{i}/{len(missing_sku_items)}] Item ID: {item_id}")
                logger.info(f"  タイトル: {title[:60]}...")

                # 1. BASE商品IDからSKUとASINを検索（最優先）
                result = self.find_sku_by_item_id(item_id, account_id)

                if result:
                    sku, asin = result
                    logger.info(f"  ASIN: {asin} （platform_item_idから取得）")
                    logger.info(f"  SKU: {sku} （platform_item_idから取得）")
                    self.stats['asin_found'] += 1
                    self.stats['sku_found'] += 1
                else:
                    # 2. フォールバック: タイトルからASINを検索
                    logger.debug(f"  platform_item_idで見つからず、タイトルマッチを試行")
                    asin = self.find_asin_by_title(title)

                    if not asin:
                        logger.warning(f"  ⚠ ASINが見つかりませんでした（platform_item_idもタイトルマッチもなし）")
                        account_stats['skipped'] += 1
                        self.stats['asin_not_found'] += 1
                        continue

                    logger.info(f"  ASIN: {asin} （タイトルマッチ）")
                    self.stats['asin_found'] += 1

                    # 3. ASINからSKUを取得
                    sku = self.get_sku_for_asin(asin, account_id)

                    if sku:
                        logger.info(f"  SKU: {sku} （既存）")
                        self.stats['sku_found'] += 1
                    else:
                        # SKUが見つからない場合は新規生成
                        sku = self.generate_new_sku(asin)
                        logger.info(f"  SKU: {sku} （新規生成）")
                        self.stats['sku_generated'] += 1

                # 4. BASE APIで商品を更新
                success, error = self.update_base_item_sku(api_client, item_id, sku)

                if success:
                    account_stats['updated'] += 1
                    self.stats['updated'] += 1
                else:
                    account_stats['failed'] += 1
                    self.stats['failed'] += 1

                # レート制限対策
                if not self.dry_run:
                    time.sleep(0.5)

        except Exception as e:
            logger.error(f"アカウント {account_id} の処理でエラー: {e}")
            import traceback
            traceback.print_exc()

        # アカウント別統計を表示
        logger.info(f"\n--- アカウント {account_id} の処理結果 ---")
        logger.info(f"確認: {account_stats['checked']}件")
        logger.info(f"SKU空欄: {account_stats['missing_sku']}件")
        logger.info(f"更新成功: {account_stats['updated']}件")
        logger.info(f"更新失敗: {account_stats['failed']}件")
        logger.info(f"スキップ: {account_stats['skipped']}件")

        # 全体統計を更新
        self.stats['total_checked'] += account_stats['checked']
        self.stats['missing_sku'] += account_stats['missing_sku']

        return account_stats

    def run(
        self,
        account_ids: List[str],
        max_items: Optional[int] = None
    ):
        """
        複数アカウントの処理を実行

        Args:
            account_ids: アカウントIDのリスト
            max_items: 最大処理件数（各アカウントごと）
        """
        logger.info(f"\n{'='*70}")
        logger.info(f"SKU修正処理開始")
        logger.info(f"モード: {'ドライラン（更新なし）' if self.dry_run else '本番実行'}")
        logger.info(f"対象アカウント: {', '.join(account_ids)}")
        logger.info(f"{'='*70}")

        start_time = datetime.now()

        for account_id in account_ids:
            self.process_account(account_id, max_items)

        end_time = datetime.now()
        elapsed = end_time - start_time

        # 最終結果を表示
        logger.info(f"\n{'='*70}")
        logger.info(f"処理完了")
        logger.info(f"{'='*70}")
        logger.info(f"実行時間: {elapsed}")
        logger.info(f"\n【全体統計】")
        logger.info(f"確認商品数: {self.stats['total_checked']}件")
        logger.info(f"SKU空欄: {self.stats['missing_sku']}件")
        logger.info(f"  - ASIN発見: {self.stats['asin_found']}件")
        logger.info(f"  - ASIN未発見: {self.stats['asin_not_found']}件")
        logger.info(f"  - SKU取得: {self.stats['sku_found']}件")
        logger.info(f"  - SKU新規生成: {self.stats['sku_generated']}件")
        logger.info(f"更新成功: {self.stats['updated']}件")
        logger.info(f"更新失敗: {self.stats['failed']}件")
        logger.info(f"スキップ: {self.stats['skipped']}件")
        logger.info(f"{'='*70}")


def main():
    parser = argparse.ArgumentParser(
        description='BASE商品のSKU修正スクリプト',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        '--account-id',
        type=str,
        help='処理対象のアカウントID（例: base_account_1）'
    )

    parser.add_argument(
        '--all-accounts',
        action='store_true',
        help='全アカウントを処理'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='ドライラン（実際の更新を行わない）'
    )

    parser.add_argument(
        '--max-items',
        type=int,
        help='最大処理件数（各アカウントごと、テスト用）'
    )

    parser.add_argument(
        '--debug',
        action='store_true',
        help='デバッグログを有効化'
    )

    parser.add_argument(
        '--yes',
        action='store_true',
        help='確認プロンプトをスキップして自動実行'
    )

    args = parser.parse_args()

    # デバッグログ
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # アカウントIDの決定
    if args.all_accounts:
        account_ids = ['base_account_1', 'base_account_2']
    elif args.account_id:
        account_ids = [args.account_id]
    else:
        print("エラー: --account-id または --all-accounts を指定してください")
        parser.print_help()
        sys.exit(1)

    # ドライランの確認
    if not args.dry_run and not args.yes:
        print("\n" + "!"*70)
        print("警告: 本番実行モードです。BASE APIの商品が実際に更新されます。")
        print("!"*70)
        response = input("\n続行しますか？ (yes/no): ")
        if response.lower() != 'yes':
            print("中止しました")
            sys.exit(0)

    # 初期化
    account_manager = AccountManager()
    db = MasterDB()

    # SKU修正処理を実行
    fixer = SKUFixer(account_manager, db, dry_run=args.dry_run)
    fixer.run(account_ids, max_items=args.max_items)


if __name__ == '__main__':
    main()
