"""
商品マスタ管理クラス

productsテーブルの操作を担当
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
import sys

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from inventory.core.master_db import MasterDB

# NGキーワードクリーニング（オプショナル）
try:
    from shared.utils.ng_keyword_cleaner import clean_product_data
    NG_KEYWORD_AVAILABLE = True
except ImportError:
    NG_KEYWORD_AVAILABLE = False


class ProductManager:
    """
    商品マスタ管理クラス

    productsテーブルの操作を担当（単一責任原則）
    """

    def __init__(self, master_db: Optional[MasterDB] = None):
        """
        Args:
            master_db: MasterDBインスタンス（Noneの場合は新規作成）
        """
        self.db = master_db or MasterDB()

    def add_product(
        self,
        asin: str,
        title_ja: str = None,
        title_en: str = None,
        description_ja: str = None,
        description_en: str = None,
        category: str = None,
        brand: str = None,
        images: List[str] = None,
        amazon_price_jpy: int = None,
        amazon_in_stock: bool = None
    ) -> bool:
        """
        商品をproductsテーブルに追加（既存の場合は更新）

        IMPORTANT: NULLの場合は既存値を保持します（ISSUE #23対策）

        Args:
            asin: ASIN
            title_ja: 日本語タイトル
            title_en: 英語タイトル
            description_ja: 日本語説明
            description_en: 英語説明
            category: カテゴリ
            brand: ブランド
            images: 画像URLリスト
            amazon_price_jpy: Amazon価格（円）
            amazon_in_stock: Amazon在庫有無

        Returns:
            bool: 成功時True
        """
        return self.db.add_product(
            asin=asin,
            title_ja=title_ja,
            title_en=title_en,
            description_ja=description_ja,
            description_en=description_en,
            category=category,
            brand=brand,
            images=images,
            amazon_price_jpy=amazon_price_jpy,
            amazon_in_stock=amazon_in_stock
        )

    def get_product(self, asin: str) -> Optional[Dict[str, Any]]:
        """
        ASINで商品情報を取得

        Args:
            asin: ASIN

        Returns:
            dict or None: 商品情報の辞書
        """
        return self.db.get_product(asin)

    def update_amazon_info(self, asin: str, price_jpy: int, in_stock: bool) -> bool:
        """
        Amazon価格・在庫情報を更新

        Args:
            asin: ASIN
            price_jpy: Amazon価格（円）
            in_stock: 在庫有無

        Returns:
            bool: 成功時True
        """
        return self.db.update_amazon_info(asin, price_jpy, in_stock)

    def product_exists(self, asin: str) -> bool:
        """
        商品が存在するかチェック

        Args:
            asin: ASIN

        Returns:
            bool: 存在する場合True
        """
        product = self.get_product(asin)
        return product is not None


# 使用例
if __name__ == '__main__':
    # テストデータ
    test_asin = "B0TEST001"
    test_product_data = {
        'title_ja': 'テスト商品',
        'title_en': 'Test Product',
        'description_ja': 'テスト説明',
        'description_en': 'Test Description',
        'category': 'Electronics',
        'brand': 'TestBrand',
        'images': ['https://example.com/image1.jpg'],
        'amazon_price_jpy': 2000,
        'amazon_in_stock': True
    }

    # ProductManagerを初期化
    manager = ProductManager()

    # 商品追加
    success = manager.add_product(
        asin=test_asin,
        **test_product_data
    )

    print("=" * 60)
    print("ProductManager テスト結果")
    print("=" * 60)
    print(f"ASIN: {test_asin}")
    print(f"商品追加: {'OK' if success else 'NG'}")

    # 商品取得
    product = manager.get_product(test_asin)
    if product:
        print(f"商品取得: OK")
        print(f"  タイトル: {product['title_ja']}")
        print(f"  価格: {product['amazon_price_jpy']}円")
    else:
        print(f"商品取得: NG")

    print("=" * 60)
