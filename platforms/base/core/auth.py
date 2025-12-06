"""
BASE OAuth Authentication

BASE APIのOAuth認証とトークン管理を行うモジュール
"""

import requests
import time
from typing import Dict, Any, Optional
from datetime import datetime, timedelta


class BaseOAuthClient:
    """
    BASE OAuth認証クライアントクラス
    """

    # BASE OAuth エンドポイント
    AUTH_URL = "https://api.thebase.in/1/oauth/authorize"
    TOKEN_URL = "https://api.thebase.in/1/oauth/token"

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        """
        Args:
            client_id: BASE APIのクライアントID
            client_secret: BASE APIのクライアントシークレット
            redirect_uri: リダイレクトURI
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    def get_authorization_url(self, state: str = None) -> str:
        """
        認証URLを生成

        Args:
            state: CSRF対策用のstate値（オプション）

        Returns:
            str: 認証URL
        """
        from urllib.parse import urlencode

        params = {
            'response_type': 'code',
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'scope': 'read_items write_items'  # 必要なスコープ
        }

        if state:
            params['state'] = state

        # URLエンコードを正しく行う（スペースが%20になる）
        param_str = urlencode(params)
        return f"{self.AUTH_URL}?{param_str}"

    def get_access_token_from_code(self, code: str) -> Dict[str, Any]:
        """
        認証コードからアクセストークンを取得

        Args:
            code: 認証コード

        Returns:
            dict: トークン情報
                - access_token: アクセストークン
                - refresh_token: リフレッシュトークン
                - expires_in: 有効期限（秒）
                - token_type: トークンタイプ

        Raises:
            requests.exceptions.HTTPError: API呼び出しエラー
        """
        data = {
            'grant_type': 'authorization_code',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'code': code,
            'redirect_uri': self.redirect_uri
        }

        response = requests.post(self.TOKEN_URL, data=data, timeout=30)
        response.raise_for_status()

        token_data = response.json()

        # トークン取得時刻とexpires_atを追加
        token_data['obtained_at'] = datetime.now().isoformat()
        if 'expires_in' in token_data:
            expires_at = datetime.now() + timedelta(seconds=token_data['expires_in'])
            token_data['expires_at'] = expires_at.isoformat()

        # BASEのAPIレスポンスにはscopeが含まれないため、明示的に追加
        # 認証時に要求したスコープを保存
        if 'scope' not in token_data:
            token_data['scope'] = 'read_items write_items'

        return token_data

    def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """
        リフレッシュトークンを使ってアクセストークンを更新

        Args:
            refresh_token: リフレッシュトークン

        Returns:
            dict: 新しいトークン情報
                - access_token: 新しいアクセストークン
                - refresh_token: 新しいリフレッシュトークン
                - expires_in: 有効期限（秒）
                - token_type: トークンタイプ

        Raises:
            requests.exceptions.HTTPError: API呼び出しエラー
        """
        data = {
            'grant_type': 'refresh_token',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'refresh_token': refresh_token
        }

        try:
            response = requests.post(self.TOKEN_URL, data=data, timeout=30)
            response.raise_for_status()

            token_data = response.json()

            # トークン取得時刻とexpires_atを追加
            token_data['obtained_at'] = datetime.now().isoformat()
            if 'expires_in' in token_data:
                expires_at = datetime.now() + timedelta(seconds=token_data['expires_in'])
                token_data['expires_at'] = expires_at.isoformat()

            # BASEのAPIレスポンスにはscopeが含まれないため、明示的に追加
            # 認証時に要求したスコープを保存
            if 'scope' not in token_data:
                token_data['scope'] = 'read_items write_items'

            return token_data

        except requests.exceptions.HTTPError as e:
            print(f"エラー: トークンのリフレッシュに失敗しました: {e}")
            if e.response is not None:
                print(f"レスポンス: {e.response.text}")
            raise

    @staticmethod
    def is_token_expired(token_data: Dict[str, Any], buffer_seconds: int = 300) -> bool:
        """
        トークンが期限切れかチェック

        Args:
            token_data: トークン情報
            buffer_seconds: 有効期限の何秒前を期限切れとみなすか（デフォルト5分）

        Returns:
            bool: 期限切れの場合True
        """
        if 'expires_at' not in token_data:
            # expires_atがない場合、expires_inから計算
            if 'expires_in' in token_data and 'obtained_at' in token_data:
                obtained_at = datetime.fromisoformat(token_data['obtained_at'])
                expires_at = obtained_at + timedelta(seconds=token_data['expires_in'])
            else:
                # 情報が不足している場合は期限切れとみなす
                return True
        else:
            expires_at = datetime.fromisoformat(token_data['expires_at'])

        # バッファを考慮した期限切れチェック
        expiry_with_buffer = expires_at - timedelta(seconds=buffer_seconds)
        return datetime.now() >= expiry_with_buffer

    @staticmethod
    def get_token_info(token_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        トークン情報のサマリーを取得

        Args:
            token_data: トークン情報

        Returns:
            dict: トークン情報サマリー
        """
        info = {
            'has_access_token': bool(token_data.get('access_token')),
            'has_refresh_token': bool(token_data.get('refresh_token')),
            'token_type': token_data.get('token_type', 'unknown'),
            'obtained_at': token_data.get('obtained_at', 'unknown'),
            'expires_at': token_data.get('expires_at', 'unknown'),
            'is_expired': BaseOAuthClient.is_token_expired(token_data)
        }

        if 'expires_at' in token_data:
            expires_at = datetime.fromisoformat(token_data['expires_at'])
            remaining = expires_at - datetime.now()
            info['remaining_seconds'] = int(remaining.total_seconds())
            info['remaining_hours'] = round(remaining.total_seconds() / 3600, 1)

        return info
