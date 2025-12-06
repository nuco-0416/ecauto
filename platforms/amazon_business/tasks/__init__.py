"""
Amazon Business タスク

各種自動化タスクを格納するモジュール
"""

from .address_cleanup import cleanup_addresses

__all__ = ['cleanup_addresses']
