"""
アップローダーファクトリー

プラットフォーム名からアップローダーインスタンスを生成
"""

from typing import Dict, Type
from scheduler.platform_uploaders.uploader_interface import UploaderInterface
from scheduler.platform_uploaders.base_uploader import BaseUploader
from scheduler.platform_uploaders.ebay_uploader import eBayUploader
from scheduler.platform_uploaders.yahoo_uploader import YahooUploader


class UploaderFactory:
    """アップローダーファクトリー"""

    # プラットフォーム名 → アップローダークラスのマッピング
    _uploaders: Dict[str, Type[UploaderInterface]] = {
        'base': BaseUploader,
        'ebay': eBayUploader,
        'yahoo': YahooUploader,
    }

    @classmethod
    def create(cls, platform: str, account_id: str, account_manager=None) -> UploaderInterface:
        """
        プラットフォーム名からアップローダーを生成

        Args:
            platform: プラットフォーム名（'base', 'ebay', 'yahoo'）
            account_id: アカウントID
            account_manager: AccountManagerインスタンス（オプション、指定しない場合は内部で作成）

        Returns:
            UploaderInterface実装クラスのインスタンス

        Raises:
            ValueError: 未対応のプラットフォーム

        Example:
            >>> uploader = UploaderFactory.create('base', 'base_account_1')
            >>> result = uploader.upload_item({'asin': 'B0TEST123', ...})
        """
        uploader_class = cls._uploaders.get(platform.lower())

        if uploader_class is None:
            raise ValueError(
                f"未対応のプラットフォーム: {platform}\n"
                f"対応プラットフォーム: {list(cls._uploaders.keys())}"
            )

        return uploader_class(account_id=account_id, account_manager=account_manager)

    @classmethod
    def get_supported_platforms(cls) -> list[str]:
        """
        対応プラットフォーム一覧を取得

        Returns:
            list[str]: プラットフォーム名のリスト

        Example:
            >>> UploaderFactory.get_supported_platforms()
            ['base', 'ebay', 'yahoo']
        """
        return list(cls._uploaders.keys())

    @classmethod
    def register_platform(
        cls,
        platform: str,
        uploader_class: Type[UploaderInterface]
    ):
        """
        新しいプラットフォームを登録（プラグイン機構）

        Args:
            platform: プラットフォーム名
            uploader_class: アップローダークラス

        Example:
            >>> class MercariUploader(UploaderInterface):
            ...     pass  # 実装
            >>> UploaderFactory.register_platform('mercari', MercariUploader)
        """
        cls._uploaders[platform.lower()] = uploader_class

    @classmethod
    def is_supported(cls, platform: str) -> bool:
        """
        プラットフォームが対応済みかチェック

        Args:
            platform: プラットフォーム名

        Returns:
            bool: 対応済みならTrue

        Example:
            >>> UploaderFactory.is_supported('base')
            True
            >>> UploaderFactory.is_supported('mercari')
            False
        """
        return platform.lower() in cls._uploaders
