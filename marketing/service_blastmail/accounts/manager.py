"""
Blastmail Account Manager

Blastmail複数アカウントの管理を行うマネージャークラス
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class AccountManager:
    """
    Blastmail複数アカウント管理クラス

    認証情報の管理とAPIクライアント作成機能を提供
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Args:
            config_path: アカウント設定ファイルのパス
                         指定しない場合は config/account_config.json を使用
        """
        if config_path is None:
            # デフォルトパス
            base_dir = Path(__file__).resolve().parent.parent
            config_path = base_dir / 'config' / 'account_config.json'

        self.config_path = Path(config_path)

        # 設定をロード
        self.accounts = self._load_config()

    def _load_config(self) -> List[Dict[str, Any]]:
        """アカウント設定をロード"""
        if not self.config_path.exists():
            logger.warning(f"アカウント設定ファイルが見つかりません: {self.config_path}")
            logger.warning("config/account_config.json.example を参考に作成してください")
            return []

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                return config.get('accounts', [])
        except Exception as e:
            logger.error(f"アカウント設定の読み込みに失敗しました: {e}")
            return []

    def get_account(self, account_id: str) -> Optional[Dict[str, Any]]:
        """
        アカウントIDで設定を取得

        Args:
            account_id: アカウントID（例: 'blastmail_account_1'）

        Returns:
            dict or None: アカウント設定
        """
        for account in self.accounts:
            if account['id'] == account_id:
                return account
        return None

    def get_active_accounts(self) -> List[Dict[str, Any]]:
        """
        アクティブなアカウント一覧を取得

        Returns:
            list: アクティブなアカウントのリスト
        """
        return [acc for acc in self.accounts if acc.get('active', False)]

    def get_all_accounts(self) -> List[Dict[str, Any]]:
        """
        全アカウント一覧を取得

        Returns:
            list: 全アカウントのリスト
        """
        return self.accounts

    def get_credentials(self, account_id: str) -> Optional[Dict[str, str]]:
        """
        アカウントの認証情報を取得

        Args:
            account_id: アカウントID

        Returns:
            dict or None: 認証情報（username, password, api_key）
        """
        account = self.get_account(account_id)
        if account:
            return account.get('credentials')
        return None

    def create_client(self, account_id: str):
        """
        アカウントIDからAPIクライアントを作成

        Args:
            account_id: アカウントID

        Returns:
            BlastmailAPIClient: 認証済みAPIクライアント

        Raises:
            ValueError: アカウントが見つからないか認証情報が不足している場合
        """
        # 循環インポートを避けるためにここでインポート
        from marketing.service_blastmail.core.api_client import BlastmailAPIClient

        account = self.get_account(account_id)
        if not account:
            raise ValueError(f"アカウント '{account_id}' が見つかりません")

        credentials = account.get('credentials')
        if not credentials:
            raise ValueError(f"アカウント '{account_id}' の認証情報が設定されていません")

        username = credentials.get('username')
        password = credentials.get('password')
        api_key = credentials.get('api_key')

        if not all([username, password, api_key]):
            raise ValueError(
                f"アカウント '{account_id}' の認証情報が不完全です。"
                "username, password, api_key をすべて設定してください"
            )

        return BlastmailAPIClient.from_credentials(
            username=username,
            password=password,
            api_key=api_key,
            account_id=account['id'],
            account_name=account.get('name', account['id'])
        )

    def create_all_clients(self, active_only: bool = True) -> List:
        """
        全アカウントのAPIクライアントを作成

        Args:
            active_only: Trueの場合、アクティブなアカウントのみ

        Returns:
            list: BlastmailAPIClientのリスト
        """
        clients = []
        accounts = self.get_active_accounts() if active_only else self.accounts

        for account in accounts:
            try:
                client = self.create_client(account['id'])
                clients.append(client)
            except Exception as e:
                logger.warning(f"アカウント '{account['id']}' のクライアント作成に失敗: {e}")

        return clients

    def list_accounts(self) -> None:
        """アカウント一覧を表示"""
        if not self.accounts:
            print("登録されているアカウントがありません")
            return

        print(f"\n{'='*60}")
        print("Blastmail アカウント一覧")
        print(f"{'='*60}")

        for acc in self.accounts:
            status = "有効" if acc.get('active', False) else "無効"
            credentials = acc.get('credentials', {})
            cred_status = "設定済" if credentials.get('username') else "未設定"
            print(f"  ID: {acc['id']}")
            print(f"  名前: {acc.get('name', 'N/A')}")
            print(f"  状態: {status}")
            print(f"  認証情報: {cred_status}")
            print(f"{'-'*60}")
