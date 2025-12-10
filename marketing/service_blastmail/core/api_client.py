"""
Blastmail API Client

Blastmail APIを操作するクライアントクラス
API Documentation: https://blastmail.jp/api/recent_https.html
"""

import requests
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

# ロガー取得
logger = logging.getLogger(__name__)


class BlastmailAuthenticator:
    """
    Blastmail API認証クラス

    ログイン/ログアウト、トークン管理を担当
    """

    BASE_URL = "https://api.bme.jp/rest/1.0"
    TOKEN_VALIDITY_MINUTES = 50  # トークン有効期限（余裕を持って50分）

    def __init__(
        self,
        username: str,
        password: str,
        api_key: str
    ):
        """
        Args:
            username: ブラストメールID
            password: APIパスワード
            api_key: API利用キー
        """
        self.username = username
        self.password = password
        self.api_key = api_key
        self._access_token: Optional[str] = None
        self._token_acquired_at: Optional[datetime] = None

    def login(self) -> str:
        """
        ログインしてアクセストークンを取得

        Returns:
            str: アクセストークン

        Raises:
            requests.exceptions.HTTPError: 認証エラー
        """
        url = f"{self.BASE_URL}/authenticate/login"
        data = {
            'username': self.username,
            'password': self.password,
            'api_key': self.api_key,
            'format': 'json'
        }

        logger.debug(f"Blastmail ログイン試行: {self.username}")
        response = requests.post(url, data=data, timeout=30)

        if not response.ok:
            error_detail = f"Status: {response.status_code}"
            try:
                error_json = response.json()
                error_detail += f", Response: {error_json}"
            except Exception:
                error_detail += f", Text: {response.text[:500]}"
            logger.error(f"Blastmail ログインエラー: {error_detail}")
            response.raise_for_status()

        result = response.json()
        self._access_token = result.get('accessToken')
        self._token_acquired_at = datetime.now()

        logger.info(f"Blastmail ログイン成功: {self.username}")
        return self._access_token

    def logout(self) -> bool:
        """
        ログアウトしてトークンを無効化

        Returns:
            bool: ログアウト成功時True
        """
        if not self._access_token:
            return True

        url = f"{self.BASE_URL}/authenticate/logout"
        params = {
            'access_token': self._access_token,
            'f': 'json'
        }

        try:
            response = requests.get(url, params=params, timeout=30)
            if response.ok:
                logger.info(f"Blastmail ログアウト成功: {self.username}")
                self._access_token = None
                self._token_acquired_at = None
                return True
        except Exception as e:
            logger.warning(f"Blastmail ログアウトエラー: {e}")

        return False

    def get_valid_token(self) -> str:
        """
        有効なアクセストークンを取得（必要に応じて再認証）

        Returns:
            str: 有効なアクセストークン
        """
        if self._is_token_valid():
            return self._access_token

        # トークンが無効または期限切れの場合は再認証
        logger.info("トークン期限切れのため再認証")
        return self.login()

    def _is_token_valid(self) -> bool:
        """トークンが有効かどうかを判定"""
        if not self._access_token or not self._token_acquired_at:
            return False

        # トークン取得から指定時間以内か確認
        elapsed = datetime.now() - self._token_acquired_at
        return elapsed < timedelta(minutes=self.TOKEN_VALIDITY_MINUTES)

    @property
    def access_token(self) -> Optional[str]:
        """現在のアクセストークン（有効性チェックなし）"""
        return self._access_token


class BlastmailAPIClient:
    """
    Blastmail APIクライアントクラス

    メルマガ配信履歴の取得・管理機能を提供
    """

    BASE_URL = "https://api.bme.jp/rest/1.0"

    def __init__(
        self,
        access_token: Optional[str] = None,
        authenticator: Optional[BlastmailAuthenticator] = None,
        account_id: Optional[str] = None,
        account_name: Optional[str] = None
    ):
        """
        Args:
            access_token: Blastmail API利用許可トークン（直接指定）
            authenticator: BlastmailAuthenticatorインスタンス（自動認証用）
            account_id: アカウントID（マルチアカウント利用時）
            account_name: アカウント名（表示用）

        Note:
            access_token と authenticator のいずれかが必要です。
            authenticator を指定すると、トークン期限切れ時に自動再認証されます。
        """
        self.authenticator = authenticator
        self._access_token = access_token
        self.account_id = account_id
        self.account_name = account_name

        if not access_token and not authenticator:
            raise ValueError("access_token または authenticator が必要です")

    @classmethod
    def from_credentials(
        cls,
        username: str,
        password: str,
        api_key: str,
        account_id: Optional[str] = None,
        account_name: Optional[str] = None
    ) -> 'BlastmailAPIClient':
        """
        認証情報からクライアントを作成（ファクトリメソッド）

        Args:
            username: ブラストメールID
            password: APIパスワード
            api_key: API利用キー
            account_id: アカウントID
            account_name: アカウント名

        Returns:
            BlastmailAPIClient: 認証済みクライアント
        """
        authenticator = BlastmailAuthenticator(username, password, api_key)
        authenticator.login()  # 初回ログイン
        return cls(
            authenticator=authenticator,
            account_id=account_id,
            account_name=account_name
        )

    @property
    def access_token(self) -> str:
        """有効なアクセストークンを取得"""
        if self.authenticator:
            return self.authenticator.get_valid_token()
        return self._access_token

    def _build_params(self, **kwargs) -> Dict[str, Any]:
        """
        共通パラメータを構築

        Args:
            **kwargs: 追加パラメータ

        Returns:
            dict: access_tokenを含むパラメータ辞書
        """
        params = {'access_token': self.access_token}
        # Noneでない値のみ追加
        for key, value in kwargs.items():
            if value is not None:
                params[key] = value
        return params

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
        response_format: str = 'json',
        timeout: int = 30
    ) -> Any:
        """
        APIリクエストを実行

        Args:
            method: HTTP メソッド ('GET' or 'POST')
            endpoint: エンドポイントパス（先頭の/不要）
            params: クエリパラメータ
            data: POSTデータ
            response_format: レスポンス形式 ('json', 'xml', 'csv')
            timeout: タイムアウト秒数

        Returns:
            APIレスポンス（json/xmlの場合はdict、csvの場合はstr）

        Raises:
            requests.exceptions.HTTPError: API呼び出しエラー
        """
        url = f"{self.BASE_URL}/{endpoint}"

        # レスポンス形式をパラメータに追加
        if params is None:
            params = {}
        if response_format in ('json', 'xml'):
            params['f'] = response_format

        logger.debug(f"API Request: {method} {url}")

        if method.upper() == 'GET':
            response = requests.get(url, params=params, timeout=timeout)
        elif method.upper() == 'POST':
            response = requests.post(url, params=params, data=data, timeout=timeout)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

        # エラーハンドリング
        if not response.ok:
            error_detail = f"Status: {response.status_code}"
            try:
                error_json = response.json()
                error_detail += f", Response: {error_json}"
            except Exception:
                error_detail += f", Text: {response.text[:500]}"

            logger.error(f"Blastmail API Error: {error_detail}")
            response.raise_for_status()

        # レスポンス形式に応じてパース
        if response_format == 'json':
            return response.json()
        elif response_format == 'csv':
            return response.text
        else:
            return response.text

    def search_delivery_history(
        self,
        offset: int = 0,
        limit: int = 25,
        message_ids: Optional[List[str]] = None,
        subjects: Optional[List[str]] = None,
        groups: Optional[List[str]] = None,
        begin_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        配信履歴を検索

        Args:
            offset: 取得開始位置（デフォルト: 0）
            limit: 取得件数制限（デフォルト: 25）
            message_ids: 識別IDリストでフィルタ
            subjects: 件名リストでフィルタ
            groups: 宛先リストでフィルタ
            begin_date: 配信開始日時（この日時以降）
            end_date: 配信終了日時（この日時以前）

        Returns:
            dict: 配信履歴データ

        Example:
            >>> client = BlastmailAPIClient.from_credentials(
            ...     username='your_id', password='your_pass', api_key='your_key'
            ... )
            >>> history = client.search_delivery_history(limit=10)
            >>> for item in history.get('items', []):
            ...     print(f"{item['subject']} - {item['deliveryDate']}")
        """
        params = self._build_params(
            offset=offset,
            limit=limit
        )

        # リスト型パラメータはカンマ区切りで追加
        if message_ids:
            params['messageIDs'] = ','.join(message_ids)
        if subjects:
            params['subjects'] = ','.join(subjects)
        if groups:
            params['groups'] = ','.join(groups)

        # 日時パラメータはISO 8601形式
        if begin_date:
            params['beginDate'] = begin_date.strftime('%Y-%m-%dT%H:%M:%S')
        if end_date:
            params['endDate'] = end_date.strftime('%Y-%m-%dT%H:%M:%S')

        return self._request('GET', 'message/history/search', params=params)

    def get_message_detail(self, message_id: str) -> Dict[str, Any]:
        """
        メッセージ詳細を取得

        Args:
            message_id: メッセージ識別ID

        Returns:
            dict: メッセージ詳細データ
        """
        params = self._build_params(messageID=message_id)
        return self._request('GET', 'message/detail/search', params=params)

    def export_delivery_addresses(
        self,
        message_id: str,
        status: int = 0
    ) -> str:
        """
        配信成功/失敗アドレスをCSV形式でエクスポート

        Args:
            message_id: メッセージ識別ID
            status: 0=成功アドレス, 1=失敗アドレス

        Returns:
            str: CSV形式のアドレスリスト
        """
        params = self._build_params(
            messageID=message_id,
            status=status
        )
        return self._request(
            'GET',
            'history/list/export',
            params=params,
            response_format='csv'
        )

    def export_open_log(self, message_id: str) -> str:
        """
        開封ログをCSV形式でエクスポート

        Args:
            message_id: メッセージ識別ID

        Returns:
            str: CSV形式の開封ログ
        """
        params = self._build_params(messageID=message_id)
        return self._request(
            'GET',
            'mailopenlog/list/export',
            params=params,
            response_format='csv'
        )

    def delete_messages(self, message_ids: List[str]) -> Dict[str, Any]:
        """
        配信履歴を削除

        Args:
            message_ids: 削除するメッセージIDのリスト

        Returns:
            dict: 削除結果（成功/失敗のID情報）
        """
        params = self._build_params()
        data = {'messageIDs': ','.join(message_ids)}
        return self._request('POST', 'message/list/delete', params=params, data=data)

    def get_all_delivery_history(
        self,
        max_items: Optional[int] = None,
        begin_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        全配信履歴を取得（ページネーション処理付き）

        Args:
            max_items: 最大取得件数（Noneの場合は全件）
            begin_date: 配信開始日時でフィルタ
            end_date: 配信終了日時でフィルタ

        Returns:
            list: 配信履歴リスト
        """
        all_items = []
        offset = 0
        limit = 100  # 一度に取得する最大件数

        while True:
            response = self.search_delivery_history(
                offset=offset,
                limit=limit,
                begin_date=begin_date,
                end_date=end_date
            )

            # APIレスポンスは 'message' キーを使用
            items = response.get('message', response.get('items', []))
            if not items:
                break

            all_items.extend(items)

            # 最大件数チェック
            if max_items and len(all_items) >= max_items:
                all_items = all_items[:max_items]
                break

            # 取得件数がlimitより少ない場合は終了
            if len(items) < limit:
                break

            offset += limit
            logger.debug(f"配信履歴取得中... {len(all_items)} 件取得済み")

        logger.info(f"配信履歴取得完了: 合計 {len(all_items)} 件")
        return all_items
