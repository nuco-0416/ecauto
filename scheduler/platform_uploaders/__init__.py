"""
プラットフォーム抽象化層

各ECプラットフォーム（BASE、eBay、Yahoo!等）へのアップロード機能を
統一されたインターフェースで提供します。
"""

from .uploader_interface import UploaderInterface
from .uploader_factory import UploaderFactory

__all__ = ['UploaderInterface', 'UploaderFactory']
