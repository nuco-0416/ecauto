"""
出品情報管理クラス

listingsテーブルの操作を担当
"""

from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
import sys

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from inventory.core.master_db import MasterDB


class ListingManager:
    """
    出品情報管理クラス

    listingsテーブルの操作を担当（単一責任原則）
    """

    def __init__(self, master_db: Optional[MasterDB] = None):
        """
        Args:
            master_db: MasterDBインスタンス（Noneの場合は新規作成）
        """
        self.db = master_db or MasterDB()

    def add_listing(
        self,
        asin: str,
        platform: str,
        account_id: str,
        platform_item_id: str = None,
        sku: str = None,
        selling_price: float = None,
        currency: str = 'JPY',
        in_stock_quantity: int = 0,
        status: str = 'pending',
        visibility: str = 'public'
    ) -> Optional[int]:
        """
        出品情報をlistingsテーブルに追加

        Args:
            asin: ASIN
            platform: プラットフォーム名（base/mercari/yahoo/ebay）
            account_id: アカウントID
            platform_item_id: プラットフォーム側のアイテムID
            sku: SKU
            selling_price: 売価
            currency: 通貨（デフォルト: JPY）
            in_stock_quantity: 在庫数
            status: ステータス（pending/listed/delisted）
            visibility: 公開設定（public/private）

        Returns:
            int or None: 追加されたlisting ID
        """
        return self.db.add_listing(
            asin=asin,
            platform=platform,
            account_id=account_id,
            platform_item_id=platform_item_id,
            sku=sku,
            selling_price=selling_price,
            currency=currency,
            in_stock_quantity=in_stock_quantity,
            status=status,
            visibility=visibility
        )

    def upsert_listing(
        self,
        asin: str,
        platform: str,
        account_id: str,
        platform_item_id: str = None,
        sku: str = None,
        selling_price: float = None,
        currency: str = 'JPY',
        in_stock_quantity: int = 0,
        status: str = 'pending',
        visibility: str = 'public'
    ) -> Optional[int]:
        """
        出品情報を追加または更新（UPSERT）

        SKUが既に存在する場合は更新、存在しない場合は追加

        Args:
            asin: ASIN
            platform: プラットフォーム名
            account_id: アカウントID
            platform_item_id: プラットフォーム側のアイテムID
            sku: SKU
            selling_price: 売価
            currency: 通貨
            in_stock_quantity: 在庫数
            status: ステータス
            visibility: 公開設定

        Returns:
            int or None: listing ID
        """
        return self.db.upsert_listing(
            asin=asin,
            platform=platform,
            account_id=account_id,
            platform_item_id=platform_item_id,
            sku=sku,
            selling_price=selling_price,
            currency=currency,
            in_stock_quantity=in_stock_quantity,
            status=status,
            visibility=visibility
        )

    def get_listing_by_sku(self, sku: str) -> Optional[Dict[str, Any]]:
        """
        SKUで出品情報を取得

        Args:
            sku: SKU

        Returns:
            dict or None: 出品情報の辞書
        """
        return self.db.get_listing_by_sku(sku)

    def get_listings_by_asin(self, asin: str) -> List[Dict[str, Any]]:
        """
        ASINで出品情報を取得（複数プラットフォームの可能性あり）

        Args:
            asin: ASIN

        Returns:
            list: 出品情報のリスト
        """
        return self.db.get_listings_by_asin(asin)

    def get_listings_by_account(
        self,
        platform: str,
        account_id: str,
        status: str = None
    ) -> List[Dict[str, Any]]:
        """
        アカウント別に出品一覧を取得

        Args:
            platform: プラットフォーム名
            account_id: アカウントID
            status: ステータスでフィルタ（オプショナル）

        Returns:
            list: 出品情報のリスト
        """
        return self.db.get_listings_by_account(platform, account_id, status)

    def update_listing(self, listing_id: int, **kwargs) -> bool:
        """
        出品情報を更新

        Args:
            listing_id: Listing ID
            **kwargs: 更新するフィールド（selling_price, status, visibility等）

        Returns:
            bool: 成功時True
        """
        return self.db.update_listing(listing_id, **kwargs)

    def listing_exists(self, asin: str, platform: str, account_id: str) -> bool:
        """
        出品が存在するかチェック

        Args:
            asin: ASIN
            platform: プラットフォーム名
            account_id: アカウントID

        Returns:
            bool: 存在する場合True
        """
        listings = self.get_listings_by_asin(asin)
        for listing in listings:
            if listing['platform'] == platform and listing['account_id'] == account_id:
                return True
        return False


# 使用例
if __name__ == '__main__':
    # テストデータ
    test_asin = "B0TEST001"
    test_platform = "base"
    test_account_id = "base_account_1"
    test_sku = "BASE-B0TEST001-20251202"

    # ListingManagerを初期化
    manager = ListingManager()

    # 出品追加
    listing_id = manager.add_listing(
        asin=test_asin,
        platform=test_platform,
        account_id=test_account_id,
        sku=test_sku,
        selling_price=2600,
        currency='JPY',
        in_stock_quantity=1,
        status='pending',
        visibility='public'
    )

    print("=" * 60)
    print("ListingManager テスト結果")
    print("=" * 60)
    print(f"ASIN: {test_asin}")
    print(f"SKU: {test_sku}")
    print(f"出品追加: {'OK' if listing_id else 'NG'}")
    if listing_id:
        print(f"  Listing ID: {listing_id}")

    # 出品取得
    listing = manager.get_listing_by_sku(test_sku)
    if listing:
        print(f"出品取得: OK")
        print(f"  売価: {listing['selling_price']}円")
        print(f"  ステータス: {listing['status']}")
    else:
        print(f"出品取得: NG")

    print("=" * 60)
