"""
ブロックリストマネージャー

削除済み禁止商品のブロックリストを管理する
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional


class BlocklistManager:
    """
    ブロックリストマネージャー

    config/blocked_asins.jsonを管理し、ASINがブロックリストに含まれるかをチェックする
    """

    def __init__(self, blocklist_path: Optional[str] = None):
        """
        Args:
            blocklist_path: ブロックリストファイルのパス（デフォルト: config/blocked_asins.json）
        """
        if blocklist_path is None:
            project_root = Path(__file__).resolve().parent.parent.parent
            blocklist_path = project_root / 'config' / 'blocked_asins.json'

        self.blocklist_path = Path(blocklist_path)
        self.blocklist = self._load_blocklist()

    def _load_blocklist(self) -> Dict[str, Any]:
        """
        ブロックリストを読み込み

        Returns:
            dict: ブロックリストデータ
        """
        if not self.blocklist_path.exists():
            # ファイルが存在しない場合は空のブロックリストを返す
            return {
                "version": "1.0",
                "last_updated": "",
                "blocked_asins": {}
            }

        try:
            with open(self.blocklist_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[WARN] ブロックリスト読み込みエラー: {e}")
            return {
                "version": "1.0",
                "last_updated": "",
                "blocked_asins": {}
            }

    def is_blocked(self, asin: str) -> bool:
        """
        ASINがブロックリストに含まれるかをチェック

        Args:
            asin: ASIN

        Returns:
            bool: ブロックリストに含まれる場合True
        """
        return asin in self.blocklist.get('blocked_asins', {})

    def get_block_info(self, asin: str) -> Optional[Dict[str, Any]]:
        """
        ASINのブロック情報を取得

        Args:
            asin: ASIN

        Returns:
            dict: ブロック情報（存在しない場合はNone）
        """
        return self.blocklist.get('blocked_asins', {}).get(asin)

    def get_blocked_count(self) -> int:
        """
        ブロックリストに含まれるASIN数を取得

        Returns:
            int: ブロックリストに含まれるASIN数
        """
        return len(self.blocklist.get('blocked_asins', {}))

    def reload(self):
        """ブロックリストを再読み込み"""
        self.blocklist = self._load_blocklist()
