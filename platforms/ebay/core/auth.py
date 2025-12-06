# -*- coding: utf-8 -*-
"""
eBay OAuth認証・トークン管理モジュール

レガシーシステムのauth.pyを移植・改良
"""

import base64
import requests
from urllib.parse import urlencode
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List
import sys

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(project_root))


class EbayAuthClient:
    """
    eBay OAuth 認証クライアント

    機能:
    - Application Token取得（公開API用）
    - User Token取得（OAuth認証フロー）
    - Token更新（Refresh Token）
    - Token有効期限管理
    """

    # OAuth スコープ定義
    SCOPES_SELL = [
        "https://api.ebay.com/oauth/api_scope/sell.inventory",
        "https://api.ebay.com/oauth/api_scope/sell.marketing",
        "https://api.ebay.com/oauth/api_scope/sell.account",
        "https://api.ebay.com/oauth/api_scope/sell.fulfillment",
    ]

    SCOPES_COMMERCE = [
        "https://api.ebay.com/oauth/api_scope/commerce.taxonomy.readonly",
    ]

    def __init__(self, app_id: str, cert_id: str, redirect_uri: str, environment: str = 'production'):
        """
        Args:
            app_id: eBay App ID (Client ID)
            cert_id: eBay Cert ID (Client Secret)
            redirect_uri: OAuth Redirect URI
            environment: 'sandbox' or 'production'
        """
        self.app_id = app_id
        self.cert_id = cert_id
        self.redirect_uri = redirect_uri
        self.environment = environment
        self.is_sandbox = (environment == 'sandbox')

        # API URL設定
        if self.is_sandbox:
            self.base_url = "https://api.sandbox.ebay.com"
            self.auth_base_url = "https://auth.sandbox.ebay.com"
        else:
            self.base_url = "https://api.ebay.com"
            self.auth_base_url = "https://auth.ebay.com"

        # トークンキャッシュ
        self.token_cache = {}

    def get_application_token(self) -> Optional[Dict[str, Any]]:
        """
        Application Token取得（Client Credentials Grant）

        公開データへのアクセスに使用（カテゴリ検索、Taxonomy API等）

        Returns:
            {
                'access_token': str,
                'token_type': 'Application Access Token',
                'expires_in': int,
                'expires_at': datetime
            }
        """
        # キャッシュチェック
        if 'app_token' in self.token_cache:
            cached = self.token_cache['app_token']
            if cached.get('expires_at') and cached['expires_at'] > datetime.now():
                return cached

        url = f"{self.base_url}/identity/v1/oauth2/token"

        # Basic認証ヘッダー作成
        credentials = f"{self.app_id}:{self.cert_id}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {encoded_credentials}"
        }

        data = {
            "grant_type": "client_credentials",
            "scope": "https://api.ebay.com/oauth/api_scope"
        }

        try:
            response = requests.post(url, headers=headers, data=data)
            response.raise_for_status()

            token_data = response.json()

            # 有効期限を計算してキャッシュ（5分前に期限切れとする）
            expires_in = token_data.get('expires_in', 7200)
            token_data['expires_at'] = datetime.now() + timedelta(seconds=expires_in - 300)

            # キャッシュに保存
            self.token_cache['app_token'] = token_data

            return token_data

        except requests.exceptions.RequestException as e:
            print(f"Application Token取得エラー: {e}")
            if hasattr(e.response, 'text'):
                print(f"  Response: {e.response.text}")
            return None

    def get_user_consent_url(self, scopes: List[str] = None) -> str:
        """
        ユーザー認証URL生成（Authorization Code Grant）

        Args:
            scopes: OAuthスコープリスト（Noneの場合はデフォルトスコープ使用）

        Returns:
            str: ユーザー認証URL
        """
        if scopes is None:
            # デフォルトスコープ: 出品・管理に必要な権限
            scopes = self.SCOPES_SELL

        params = {
            "client_id": self.app_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes)
        }

        return f"{self.auth_base_url}/oauth2/authorize?{urlencode(params)}"

    def get_user_token(self, auth_code: str) -> Optional[Dict[str, Any]]:
        """
        認証コードからUser Token取得

        Args:
            auth_code: eBayから返される認証コード

        Returns:
            {
                'access_token': str,
                'refresh_token': str,
                'token_type': 'User Access Token',
                'expires_in': int,
                'refresh_token_expires_in': int,
                'expires_at': datetime,
                'token_saved_at': str (ISO format)
            }
        """
        url = f"{self.base_url}/identity/v1/oauth2/token"

        # Basic認証ヘッダー作成
        credentials = f"{self.app_id}:{self.cert_id}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {encoded_credentials}"
        }

        data = {
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": self.redirect_uri
        }

        try:
            response = requests.post(url, headers=headers, data=data)
            response.raise_for_status()

            token_data = response.json()

            # メタ情報追加（レガシーシステムと同じ形式）
            token_data['token_saved_at'] = datetime.now().isoformat()

            return token_data

        except requests.exceptions.RequestException as e:
            print(f"User Token取得エラー: {e}")
            if hasattr(e.response, 'text'):
                print(f"  Response: {e.response.text}")
            return None

    def refresh_user_token(self, refresh_token: str) -> Optional[Dict[str, Any]]:
        """
        Refresh TokenからUser Token更新

        Args:
            refresh_token: リフレッシュトークン

        Returns:
            {
                'access_token': str,
                'token_type': 'User Access Token',
                'expires_in': int,
                'expires_at': datetime,
                'token_saved_at': str (ISO format)
            }

        Note:
            新しいRefresh Tokenは返されない場合があるため、
            元のRefresh Tokenを保持する必要がある
        """
        url = f"{self.base_url}/identity/v1/oauth2/token"

        # Basic認証ヘッダー作成
        credentials = f"{self.app_id}:{self.cert_id}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {encoded_credentials}"
        }

        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": " ".join(self.SCOPES_SELL)
        }

        try:
            response = requests.post(url, headers=headers, data=data)
            response.raise_for_status()

            token_data = response.json()

            # メタ情報追加（レガシーシステムと同じ形式）
            token_data['token_saved_at'] = datetime.now().isoformat()

            # 新しいRefresh Tokenが返されない場合は元のものを保持
            if 'refresh_token' not in token_data:
                token_data['refresh_token'] = refresh_token

            return token_data

        except requests.exceptions.RequestException as e:
            print(f"Token更新エラー: {e}")
            if hasattr(e.response, 'text'):
                print(f"  Response: {e.response.text}")
            return None

    @staticmethod
    def is_token_expired(token_data: Dict[str, Any]) -> bool:
        """
        トークンの有効期限切れチェック

        Args:
            token_data: トークン情報

        Returns:
            bool: 期限切れの場合True
        """
        if 'token_saved_at' not in token_data:
            return True

        try:
            saved_time = datetime.fromisoformat(token_data['token_saved_at'])
            # 1時間以上経過している場合は期限切れとみなす
            return datetime.now() - saved_time > timedelta(hours=1)
        except (ValueError, KeyError):
            return True

    @staticmethod
    def get_token_info(token_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        トークン情報のサマリー取得

        Args:
            token_data: トークン情報

        Returns:
            {
                'has_access_token': bool,
                'has_refresh_token': bool,
                'token_type': str,
                'saved_at': str,
                'remaining_hours': float
            }
        """
        info = {
            'has_access_token': bool(token_data.get('access_token')),
            'has_refresh_token': bool(token_data.get('refresh_token')),
            'token_type': token_data.get('token_type', 'Unknown'),
        }

        if 'token_saved_at' in token_data:
            info['saved_at'] = token_data['token_saved_at']

            try:
                saved_time = datetime.fromisoformat(token_data['token_saved_at'])
                elapsed = datetime.now() - saved_time
                remaining = timedelta(hours=1) - elapsed
                info['remaining_hours'] = round(remaining.total_seconds() / 3600, 2)
            except (ValueError, KeyError):
                pass

        return info


class EbayTokenManager:
    """
    eBay Token Manager（高レベルAPI）

    AccountManagerと連携してトークンの取得・更新を管理
    """

    def __init__(self, account_id: str, credentials: Dict[str, str], environment: str = 'production'):
        """
        Args:
            account_id: アカウントID
            credentials: 認証情報 {'app_id', 'cert_id', 'redirect_uri'}
            environment: 'sandbox' or 'production'
        """
        self.account_id = account_id
        self.environment = environment

        # OAuth クライアント初期化
        self.auth_client = EbayAuthClient(
            app_id=credentials['app_id'],
            cert_id=credentials['cert_id'],
            redirect_uri=credentials['redirect_uri'],
            environment=environment
        )

        # トークンファイルパス
        tokens_dir = Path(__file__).parent.parent / 'accounts' / 'tokens'
        tokens_dir.mkdir(parents=True, exist_ok=True)
        self.token_file = tokens_dir / f'{account_id}_token.json'

    def get_valid_token(self) -> Optional[str]:
        """
        有効なアクセストークンを取得（必要に応じて自動更新）

        Returns:
            str or None: アクセストークン
        """
        # トークンファイル読み込み
        if not self.token_file.exists():
            print(f"トークンが見つかりません: {self.token_file}")
            print(f"  python platforms/ebay/scripts/setup_account.py --account-id {self.account_id} を実行してください")
            return None

        try:
            with open(self.token_file, 'r', encoding='utf-8') as f:
                token_data = json.load(f)
        except Exception as e:
            print(f"トークン読み込みエラー: {e}")
            return None

        # 有効期限チェック
        if EbayAuthClient.is_token_expired(token_data):
            print("トークンを更新中...")

            # リフレッシュトークンで更新
            refresh_token = token_data.get('refresh_token')
            if not refresh_token:
                print("リフレッシュトークンがありません")
                return None

            new_token = self.auth_client.refresh_user_token(refresh_token)

            if new_token:
                # トークンを保存
                try:
                    with open(self.token_file, 'w', encoding='utf-8') as f:
                        json.dump(new_token, f, ensure_ascii=False, indent=2)
                    print("トークン更新成功")
                    return new_token['access_token']
                except Exception as e:
                    print(f"トークン保存エラー: {e}")
                    return None
            else:
                print("トークン更新失敗")
                return None

        return token_data.get('access_token')


# テスト実行
def main():
    """テスト実行"""
    print("eBay認証モジュール - テスト")
    print("=" * 60)

    # ダミー認証情報でインスタンス作成
    client = EbayAuthClient(
        app_id="dummy_app_id",
        cert_id="dummy_cert_id",
        redirect_uri="https://localhost:8000/callback",
        environment="sandbox"
    )

    # ユーザー認証URL生成テスト
    consent_url = client.get_user_consent_url()
    print(f"\nユーザー認証URL:\n{consent_url}\n")

    print("=" * 60)
    print("モジュールのロードに成功しました")


if __name__ == '__main__':
    main()
