"""
Account Manager

BASE複数アカウントの管理を行うマネージャークラス
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional
import sys

# auth.pyをインポート
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.auth import BaseOAuthClient


class AccountManager:
    """
    BASE複数アカウント管理クラス
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
            account_id: アカウントID（例: 'base_account_1'）

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
        有効なトークンが存在するかチェック（期限切れも確認）

        Args:
            account_id: アカウントID

        Returns:
            bool: トークンが存在し、access_tokenがあり、有効期限内の場合True
        """
        token = self.get_token(account_id)
        if not token or not token.get('access_token'):
            return False

        # 期限切れチェック
        if BaseOAuthClient.is_token_expired(token):
            return False

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
            'name': account['name'],
            'description': account.get('description', ''),
            'active': account.get('active', False),
            'daily_upload_limit': account.get('daily_upload_limit', 1000),
            'rate_limit_per_hour': account.get('rate_limit_per_hour', 50),
            'has_token': self.has_valid_token(account_id)
        }

        return info

    def refresh_token_if_needed(self, account_id: str, force: bool = False) -> bool:
        """
        必要に応じてトークンを自動更新

        Args:
            account_id: アカウントID
            force: Trueの場合、期限に関わらず強制的に更新

        Returns:
            bool: 更新成功時True
        """
        account = self.get_account(account_id)
        if not account:
            print(f"エラー: アカウント {account_id} が見つかりません")
            return False

        token = self.get_token(account_id)
        if not token:
            print(f"エラー: アカウント {account_id} のトークンが見つかりません")
            return False

        # 強制更新でない場合は期限チェック
        if not force and not BaseOAuthClient.is_token_expired(token):
            return True  # 更新不要

        # リフレッシュトークンがない場合はエラー
        refresh_token = token.get('refresh_token')
        if not refresh_token:
            print(f"エラー: アカウント {account_id} にリフレッシュトークンがありません")
            return False

        # OAuth クライアントを作成
        credentials = account.get('credentials', {})
        oauth_client = BaseOAuthClient(
            client_id=credentials.get('client_id'),
            client_secret=credentials.get('client_secret'),
            redirect_uri=credentials.get('redirect_uri')
        )

        # トークン更新
        try:
            print(f"トークンを更新中: {account_id}")
            new_token = oauth_client.refresh_access_token(refresh_token)

            # 新しいトークンを保存
            if self.save_token(account_id, new_token):
                print(f"[OK] トークン更新成功: {account_id}")
                return True
            else:
                print(f"[ERROR] トークンの保存に失敗しました: {account_id}")
                return False

        except Exception as e:
            print(f"[ERROR] トークン更新失敗: {account_id} - {e}")
            return False

    def get_token_with_auto_refresh(self, account_id: str) -> Optional[Dict[str, Any]]:
        """
        トークンを取得（必要に応じて自動更新）

        Args:
            account_id: アカウントID

        Returns:
            dict or None: トークン情報（更新後）
        """
        # トークンを取得
        token = self.get_token(account_id)
        if not token:
            return None

        # 期限切れの場合は自動更新
        if BaseOAuthClient.is_token_expired(token):
            if self.refresh_token_if_needed(account_id):
                # 更新後のトークンを再取得
                return self.get_token(account_id)
            else:
                return None

        return token

    def refresh_all_tokens(self, active_only: bool = True) -> Dict[str, bool]:
        """
        全アカウントのトークンを一括更新

        Args:
            active_only: Trueの場合、アクティブなアカウントのみ更新

        Returns:
            dict: アカウントIDと更新結果のマップ
        """
        accounts = self.get_active_accounts() if active_only else self.accounts
        results = {}

        for account in accounts:
            account_id = account['id']
            results[account_id] = self.refresh_token_if_needed(account_id, force=True)

        return results

    def print_summary(self):
        """アカウント一覧のサマリーを表示"""
        print("\n" + "=" * 60)
        print("BASE アカウント一覧")
        print("=" * 60)

        active_accounts = self.get_active_accounts()
        print(f"アクティブ: {len(active_accounts)}件 / 全体: {len(self.accounts)}件\n")

        for account in self.accounts:
            account_id = account['id']
            name = account['name']
            active = "[Active]" if account.get('active') else "[Inactive]"
            has_token = "[Token OK]" if self.has_valid_token(account_id) else "[No Token]"

            print(f"{active} {has_token} {account_id}")
            print(f"  名前: {name}")
            print(f"  説明: {account.get('description', '')}")

            # トークン情報を表示
            token = self.get_token(account_id)
            if token:
                token_info = BaseOAuthClient.get_token_info(token)
                if 'remaining_hours' in token_info:
                    print(f"  トークン有効期限: 残り {token_info['remaining_hours']} 時間")

            print()

        print("=" * 60)
