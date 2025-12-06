"""
BASE出品済み商品の欠損している商品説明を補完するスクリプト

機能:
1. ローカルDBから description_ja が欠損している BASE出品済み商品を抽出
2. SP-APIで商品情報を再取得
3. ローカルDBを更新（products テーブル）
4. BASE APIで商品説明を更新（items/edit）

使用方法:
    # dry-run（確認のみ）
    python platforms/base/scripts/complement_missing_descriptions.py --dry-run --limit 5

    # 実際に更新
    python platforms/base/scripts/complement_missing_descriptions.py --limit 10

    # 特定アカウントのみ
    python platforms/base/scripts/complement_missing_descriptions.py --account base_account_1 --limit 10
"""

import sys
import sqlite3
import time
import argparse
from pathlib import Path
from typing import Dict, Any, Optional

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# 循環インポート回避のため、必要な場所でインポート
from integrations.amazon.sp_api_client import AmazonSPAPIClient
from integrations.amazon.config import SP_API_CREDENTIALS
from inventory.core.master_db import MasterDB


class DescriptionComplementer:
    """商品説明補完処理クラス"""

    def __init__(self, dry_run: bool = False):
        """
        Args:
            dry_run: Trueの場合、実際の更新は行わず処理内容のみ表示
        """
        self.dry_run = dry_run
        self.master_db = MasterDB()
        self.sp_api_client = AmazonSPAPIClient(SP_API_CREDENTIALS)

        # BASE アカウントマネージャー（遅延インポート）
        from platforms.base.accounts.manager import AccountManager
        self.account_manager = AccountManager()  # デフォルトパスを使用

        # 統計情報
        self.stats = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0,
            'sp_api_failed': 0,
            'base_api_failed': 0,
            'db_update_failed': 0
        }

    def get_missing_description_items(
        self,
        limit: Optional[int] = None,
        account_id: Optional[str] = None
    ) -> list:
        """
        BASE APIから detail が欠損している商品を取得

        Args:
            limit: 取得する最大件数
            account_id: 特定アカウントのみ取得する場合

        Returns:
            list: 商品情報のリスト（BASE API + ローカルDB情報）
        """
        from platforms.base.core.api_client import BaseAPIClient

        missing_items = []

        # アクティブなアカウントを取得
        accounts = self.account_manager.get_active_accounts()

        for account in accounts:
            acc_id = account['id']

            # 特定アカウントのみ処理する場合
            if account_id and acc_id != account_id:
                continue

            print(f"  [{acc_id}] 商品一覧を取得中...")

            try:
                # BASE APIクライアント作成
                base_client = BaseAPIClient(
                    account_id=acc_id,
                    account_manager=self.account_manager
                )

                # 全商品を取得
                items = base_client.get_all_items()

                # detail欠損商品を抽出
                for item in items:
                    detail = item.get('detail', '')
                    if not detail or detail.strip() == '':
                        # identifierからASINを抽出（形式: b-ASIN-timestamp）
                        identifier = item.get('identifier', '')
                        asin = None
                        if identifier and identifier.startswith('b-'):
                            parts = identifier.split('-')
                            if len(parts) >= 2:
                                asin = parts[1]

                        if not asin:
                            print(f"    [WARNING] ASIN抽出失敗: identifier={identifier}")
                            continue

                        # ローカルDBから商品情報を取得
                        conn = sqlite3.connect(self.master_db.db_path)
                        conn.row_factory = sqlite3.Row
                        cursor = conn.cursor()

                        cursor.execute("""
                            SELECT
                                p.asin,
                                p.title_ja,
                                p.description_ja,
                                p.brand
                            FROM products p
                            WHERE p.asin = ?
                        """, (asin,))

                        product = cursor.fetchone()
                        conn.close()

                        missing_items.append({
                            'asin': asin,
                            'platform_item_id': item['item_id'],
                            'account_id': acc_id,
                            'title_ja': product['title_ja'] if product else None,
                            'description_ja': product['description_ja'] if product else None,
                            'brand': product['brand'] if product else None,
                            'base_title': item.get('title')
                        })

                        # limitチェック
                        if limit and len(missing_items) >= limit:
                            break

                print(f"    detail欠損商品: {len([i for i in missing_items if i['account_id'] == acc_id])}件")

                # limitに達したら終了
                if limit and len(missing_items) >= limit:
                    break

            except Exception as e:
                print(f"    [エラー] {e}")
                continue

        return missing_items[:limit] if limit else missing_items

    def fetch_product_info_from_sp_api(self, asin: str) -> Optional[Dict[str, Any]]:
        """
        SP-APIから商品情報を取得

        Args:
            asin: ASIN

        Returns:
            dict: 商品情報、失敗時はNone
        """
        try:
            product_info = self.sp_api_client.get_product_info(asin)

            if not product_info:
                print(f"    [SP-API] 商品情報取得失敗（Noneが返却）")
                return None

            # 必須フィールドのバリデーション
            if not product_info.get('description_ja'):
                print(f"    [SP-API] description_ja が取得できませんでした")
                return None

            return product_info

        except Exception as e:
            print(f"    [SP-API] エラー: {e}")
            return None

    def update_local_db(
        self,
        asin: str,
        product_info: Dict[str, Any]
    ) -> bool:
        """
        ローカルDBを更新

        Args:
            asin: ASIN
            product_info: SP-APIから取得した商品情報

        Returns:
            bool: 成功時True
        """
        try:
            conn = sqlite3.connect(self.master_db.db_path)
            cursor = conn.cursor()

            # productsテーブルを更新
            cursor.execute("""
                UPDATE products
                SET
                    title_ja = COALESCE(?, title_ja),
                    description_ja = ?,
                    brand = COALESCE(?, brand),
                    images = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE asin = ?
            """, (
                product_info.get('title_ja'),
                product_info.get('description_ja'),
                product_info.get('brand'),
                '|'.join(product_info.get('images', [])),
                asin
            ))

            conn.commit()
            conn.close()

            return True

        except Exception as e:
            print(f"    [DB更新] エラー: {e}")
            return False

    def update_base_item_description(
        self,
        account_id: str,
        platform_item_id: str,
        description: str
    ) -> bool:
        """
        BASE APIで商品説明を更新

        Args:
            account_id: アカウントID
            platform_item_id: BASE商品ID
            description: 商品説明

        Returns:
            bool: 成功時True
        """
        try:
            # BASE APIクライアント作成（遅延インポート）
            from platforms.base.core.api_client import BaseAPIClient
            base_client = BaseAPIClient(
                account_id=account_id,
                account_manager=self.account_manager
            )

            # 商品説明を更新
            updates = {'detail': description}
            response = base_client.update_item(platform_item_id, updates)

            if response:
                print(f"    [BASE API] 商品説明を更新しました")
                return True
            else:
                print(f"    [BASE API] 更新失敗（レスポンスなし）")
                return False

        except Exception as e:
            print(f"    [BASE API] エラー: {e}")
            return False

    def complement_single_item(self, item: Dict[str, Any]) -> bool:
        """
        1つの商品の説明文を補完

        Args:
            item: 商品情報

        Returns:
            bool: 成功時True
        """
        asin = item['asin']
        platform_item_id = item['platform_item_id']
        account_id = item['account_id']

        print(f"\n[{self.stats['total'] + 1}] ASIN: {asin}")
        print(f"    BASE商品ID: {platform_item_id}")
        print(f"    アカウント: {account_id}")
        print(f"    BASEタイトル: {item.get('base_title', 'NULL')[:50]}...")

        # 1. まずローカルDBから description_ja を取得
        description = item.get('description_ja')

        if description:
            print(f"    [1/3] ローカルDBから説明文を取得")
            print(f"    [OK] description_ja: {description[:80]}...")
            product_info = None  # ローカルDBから取得した場合はSP-API不要
        else:
            # 2. ローカルDBになければSP-APIから取得
            print(f"    [1/3] ローカルDBに説明文なし、SP-APIから取得中...")
            product_info = self.fetch_product_info_from_sp_api(asin)

            if not product_info:
                print(f"    [FAILED] SP-API取得失敗")
                self.stats['sp_api_failed'] += 1
                return False

            description = product_info.get('description_ja')
            print(f"    [OK] description_ja: {description[:80] if description else 'NULL'}...")

        if self.dry_run:
            if product_info:
                print(f"    [DRY-RUN] ローカルDB更新をスキップ")
            print(f"    [DRY-RUN] BASE API更新をスキップ")
            return True

        # 2. ローカルDBを更新（SP-APIから取得した場合のみ）
        if product_info:
            print(f"    [2/3] ローカルDBを更新中...")
            if not self.update_local_db(asin, product_info):
                print(f"    [FAILED] DB更新失敗")
                self.stats['db_update_failed'] += 1
                return False

            print(f"    [OK] ローカルDB更新完了")
        else:
            print(f"    [2/3] ローカルDB更新をスキップ（既存データを使用）")

        # 3. BASE APIで商品説明を更新
        print(f"    [3/3] BASE APIで商品説明を更新中...")
        if not self.update_base_item_description(account_id, platform_item_id, description):
            print(f"    [FAILED] BASE API更新失敗")
            self.stats['base_api_failed'] += 1
            return False

        print(f"    [OK] 補完完了")
        return True

    def run(
        self,
        limit: Optional[int] = None,
        account_id: Optional[str] = None
    ):
        """
        補完処理を実行

        Args:
            limit: 処理する最大件数
            account_id: 特定アカウントのみ処理する場合
        """
        print("=" * 80)
        print("BASE出品済み商品の説明文補完処理")
        print("=" * 80)

        if self.dry_run:
            print("\n[DRY-RUN MODE] 実際の更新は行いません\n")

        # 欠損商品を取得
        print(f"\n欠損商品を検索中...")
        items = self.get_missing_description_items(limit=limit, account_id=account_id)

        if not items:
            print("\n補完が必要な商品は見つかりませんでした")
            return

        print(f"補完対象: {len(items)}件")

        if account_id:
            print(f"対象アカウント: {account_id}")

        # 処理開始
        self.stats['total'] = len(items)

        for i, item in enumerate(items, 1):
            try:
                success = self.complement_single_item(item)

                if success:
                    self.stats['success'] += 1
                else:
                    self.stats['failed'] += 1

                # レート制限対策: 0.5秒待機
                if not self.dry_run and i < len(items):
                    time.sleep(0.5)

            except KeyboardInterrupt:
                print("\n\n処理を中断しました")
                break

            except Exception as e:
                print(f"    [ERROR] 予期しないエラー: {e}")
                self.stats['failed'] += 1
                continue

        # 統計表示
        self.print_stats()

    def print_stats(self):
        """統計情報を表示"""
        print("\n" + "=" * 80)
        print("処理結果サマリー")
        print("=" * 80)
        print(f"処理総数:       {self.stats['total']:>6}件")
        print(f"成功:           {self.stats['success']:>6}件")
        print(f"失敗:           {self.stats['failed']:>6}件")

        if self.stats['sp_api_failed'] > 0:
            print(f"  - SP-API失敗: {self.stats['sp_api_failed']:>6}件")

        if self.stats['db_update_failed'] > 0:
            print(f"  - DB更新失敗: {self.stats['db_update_failed']:>6}件")

        if self.stats['base_api_failed'] > 0:
            print(f"  - BASE API失敗: {self.stats['base_api_failed']:>6}件")

        if self.stats['total'] > 0:
            success_rate = self.stats['success'] / self.stats['total'] * 100
            print(f"\n成功率: {success_rate:.1f}%")

        print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description='BASE出品済み商品の説明文補完')
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='dry-runモード（実際の更新は行わない）'
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='処理する最大件数'
    )
    parser.add_argument(
        '--account',
        type=str,
        help='特定アカウントのみ処理（例: base_account_1）'
    )

    args = parser.parse_args()

    complementer = DescriptionComplementer(dry_run=args.dry_run)
    complementer.run(limit=args.limit, account_id=args.account)


if __name__ == '__main__':
    main()
