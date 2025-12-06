# -*- coding: utf-8 -*-
"""
eBay Account Manager

eBay複数アカウントの管理を行うマネージャークラス
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional
import sys

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(project_root))


class EbayAccountManager:
    """
    eBay複数アカウント管理クラス
    """

    def __init__(self, config_path: str = None):
        """
        Args:
            config_path: アカウント設定ファイルのパス
        """
        if config_path is None:
            # デフォルトパス
            base_dir = Path(__file__).resolve().parent
            config_path = base_dir / 'account_config.json'

        self.config_path = Path(config_path)
        self.tokens_dir = self.config_path.parent / 'tokens'
        self.tokens_dir.mkdir(parents=True, exist_ok=True)

        # 設定をロード
        self.accounts = self._load_config()

    def _load_config(self) -> List[Dict[str, Any]]:
        """アカウント設定をロード"""
        if not self.config_path.exists():
            print(f"警告: アカウント設定ファイルが見つかりません: {self.config_path}")
            print("account_config.json.example を参考に作成してください")
            return []

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                return config.get('accounts', [])
        except Exception as e:
            print(f"エラー: アカウント設定の読み込みに失敗しました: {e}")
            return []

    def get_account(self, account_id: str) -> Optional[Dict[str, Any]]:
        """
        アカウントIDで設定を取得

        Args:
            account_id: アカウントID（例: 'ebay_account_1'）

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

    def get_token(self, account_id: str) -> Optional[Dict[str, Any]]:
        """
        アカウントのトークン情報を取得

        Args:
            account_id: アカウントID

        Returns:
            dict or None: トークン情報（access_token, refresh_token等）
        """
        token_file = self.tokens_dir / f'{account_id}_token.json'

        if not token_file.exists():
            return None

        try:
            with open(token_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"エラー: トークンの読み込みに失敗しました: {e}")
            return None

    def save_token(self, account_id: str, token_data: Dict[str, Any]) -> bool:
        """
        トークン情報を保存

        Args:
            account_id: アカウントID
            token_data: トークン情報（access_token, refresh_token等）

        Returns:
            bool: 成功時True
        """
        token_file = self.tokens_dir / f'{account_id}_token.json'

        try:
            with open(token_file, 'w', encoding='utf-8') as f:
                json.dump(token_data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"エラー: トークンの保存に失敗しました: {e}")
            return False

    def has_valid_token(self, account_id: str) -> bool:
        """
        有効なトークンが存在するかチェック

        Args:
            account_id: アカウントID

        Returns:
            bool: トークンが存在し、access_tokenがある場合True
        """
        token = self.get_token(account_id)
        if not token or not token.get('access_token'):
            return False

        # eBayトークンの期限切れチェックは auth.py で実装
        # ここでは簡易的に access_token の存在のみチェック
        return True

    def list_accounts(self) -> List[str]:
        """
        全アカウントIDのリストを取得

        Returns:
            list: アカウントIDのリスト
        """
        return [acc['id'] for acc in self.accounts]

    def get_account_info(self, account_id: str) -> Dict[str, Any]:
        """
        アカウントの詳細情報を取得（認証情報を除く）

        Args:
            account_id: アカウントID

        Returns:
            dict: アカウント情報
        """
        account = self.get_account(account_id)
        if not account:
            return {}

        # 認証情報を除いた情報を返す
        info = {
            'id': account['id'],
            'name': account.get('name', ''),
            'description': account.get('description', ''),
            'active': account.get('active', False),
            'environment': account.get('environment', 'production'),
            'has_token': self.has_valid_token(account_id)
        }

        # 設定情報を追加
        settings = account.get('settings', {})
        info['merchant_location_key'] = settings.get('merchant_location_key', 'JP_LOCATION')
        info['default_currency'] = settings.get('default_currency', 'USD')
        info['rate_limit_per_day'] = settings.get('rate_limit_per_day', 5000)

        return info

    def get_credentials(self, account_id: str) -> Optional[Dict[str, str]]:
        """
        アカウントの認証情報を取得

        Args:
            account_id: アカウントID

        Returns:
            dict or None: 認証情報（app_id, cert_id, dev_id, redirect_uri）
        """
        account = self.get_account(account_id)
        if not account:
            return None

        return account.get('credentials', {})

    def get_environment(self, account_id: str) -> str:
        """
        アカウントの環境（sandbox/production）を取得

        Args:
            account_id: アカウントID

        Returns:
            str: 'sandbox' or 'production'（デフォルト: 'production'）
        """
        account = self.get_account(account_id)
        if not account:
            return 'production'

        return account.get('environment', 'production')

    def print_summary(self):
        """アカウント一覧のサマリーを表示"""
        print("\n" + "=" * 60)
        print("eBay アカウント一覧")
        print("=" * 60)

        active_accounts = self.get_active_accounts()
        print(f"アクティブ: {len(active_accounts)}件 / 全体: {len(self.accounts)}件\n")

        for account in self.accounts:
            account_id = account['id']
            name = account.get('name', '')
            active = "[Active]" if account.get('active') else "[Inactive]"
            has_token = "[Token OK]" if self.has_valid_token(account_id) else "[No Token]"
            env = account.get('environment', 'production')

            print(f"{active} {has_token} {account_id}")
            print(f"  名前: {name}")
            print(f"  説明: {account.get('description', '')}")
            print(f"  環境: {env}")
            print()

        print("=" * 60)


def main():
    """テスト実行"""
    manager = EbayAccountManager()
    manager.print_summary()


if __name__ == '__main__':
    main()
