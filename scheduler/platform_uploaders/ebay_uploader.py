"""
eBay用アップローダー（将来実装）

eBay API統合時にこのクラスを実装します
"""

import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

# パスを追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scheduler.platform_uploaders.uploader_interface import UploaderInterface


class eBayUploader(UploaderInterface):
    """eBay専用アップローダー（スケルトン）"""

    def __init__(self, account_id: str):
        """
        Args:
            account_id: eBayアカウントID（例: 'ebay_account_1'）
        """
        self.account_id = account_id
        # TODO: eBay APIクライアントの初期化

    @property
    def platform_name(self) -> str:
        return 'ebay'

    def upload_item(self, item_data: Dict[str, Any]) -> Dict[str, Any]:
        """eBayにアイテムをアップロード"""
        # TODO: eBay API実装
        raise NotImplementedError(
            "eBay uploader is not yet implemented. "
            "Please implement eBay API integration in this method."
        )

    def check_duplicate(self, asin: str, sku: str) -> bool:
        """eBay重複チェック"""
        # TODO: eBay APIで重複チェック
        # 暫定: 常にFalse（重複なし）を返す
        return False

    def upload_images(
        self,
        platform_item_id: str,
        image_urls: List[str]
    ) -> Dict[str, Any]:
        """eBay画像アップロード"""
        # TODO: eBay API実装
        raise NotImplementedError(
            "eBay image upload is not yet implemented."
        )

    def validate_item(self, item_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """eBayアイテム検証"""
        # TODO: eBay固有のバリデーション
        # 暫定: 常にOK
        return True, None

    def get_business_hours(self) -> tuple[int, int]:
        """eBay営業時間: 24時間稼働"""
        return (0, 24)

    def get_rate_limit(self) -> float:
        """eBay API制限: 1秒（仮）"""
        # TODO: eBay APIの実際のレート制限に合わせて調整
        return 1.0
