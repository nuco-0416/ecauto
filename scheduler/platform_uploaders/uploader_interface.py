"""
プラットフォームアップローダー共通インターフェース

全プラットフォームが実装すべきメソッドを定義
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

class UploaderInterface(ABC):
    """アップローダー基底クラス"""

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """プラットフォーム名（例: 'base', 'ebay', 'yahoo'）"""
        pass

    @abstractmethod
    def upload_item(self, item_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        単一アイテムをアップロード

        Args:
            item_data: アップロード対象のアイテムデータ
                {
                    'asin': str,
                    'sku': str,
                    'title': str,
                    'description': str,
                    'price': int,
                    'stock': int,
                    'images': List[str],
                    'account_id': str,
                    ...
                }

        Returns:
            {
                'status': 'success' | 'failed',
                'platform_item_id': 'xxx',  # プラットフォーム側のID
                'message': 'エラーメッセージ（失敗時）'
            }
        """
        pass

    @abstractmethod
    def check_duplicate(self, asin: str, sku: str) -> bool:
        """
        重複チェック

        Args:
            asin: Amazon ASIN
            sku: SKU

        Returns:
            True: 既に出品済み、False: 未出品
        """
        pass

    @abstractmethod
    def upload_images(
        self,
        platform_item_id: str,
        image_urls: List[str]
    ) -> Dict[str, Any]:
        """
        画像をアップロード（商品登録後）

        Args:
            platform_item_id: プラットフォーム側のアイテムID
            image_urls: 画像URLのリスト

        Returns:
            {
                'status': 'success' | 'failed',
                'uploaded_count': int,
                'message': 'メッセージ'
            }
        """
        pass

    @abstractmethod
    def validate_item(self, item_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        アイテムデータの検証

        Args:
            item_data: アイテムデータ

        Returns:
            (is_valid, error_message)
                is_valid: True=有効, False=無効
                error_message: エラーメッセージ（無効時）
        """
        pass

    def get_business_hours(self) -> tuple[int, int]:
        """
        営業時間を取得（オーバーライド可能）

        Returns:
            (start_hour, end_hour)  # デフォルト: (6, 23)
        """
        return (6, 23)

    def get_rate_limit(self) -> float:
        """
        API レート制限（秒）を取得（オーバーライド可能）

        Returns:
            rate_limit_seconds  # デフォルト: 2.0秒
        """
        return 2.0
