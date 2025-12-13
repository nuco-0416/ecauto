"""
BASE API Client

BASE APIを操作するクライアントクラス（プロキシ対応版）
"""

import requests
import time
import logging
from typing import Dict, Any, Optional, TYPE_CHECKING
from pathlib import Path
import sys

# 型ヒント用のインポート（循環インポートを回避）
if TYPE_CHECKING:
    from accounts.manager import AccountManager

# common/proxy をインポート可能にする
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
from common.proxy.proxy_manager import ProxyManager

# ロガー取得
logger = logging.getLogger(__name__)


class BaseAPIClient:
    """
    BASE APIクライアントクラス（自動トークン更新 + プロキシ対応）

    プロキシ設定は以下の優先順位で適用されます：
    1. コンストラクタの proxy_id パラメータ（明示的指定）
    2. account_config.json のアカウント直接指定 proxy_id（後方互換性）
    3. account_config.json のオーナー設定 proxy_id（マルチオーナー対応）
    4. 未設定の場合はプロキシなしで動作
    """

    BASE_URL = "https://api.thebase.in/1"

    def __init__(
        self,
        access_token: str = None,
        account_id: str = None,
        account_manager: Optional['AccountManager'] = None,
        proxy_id: str = None
    ):
        """
        Args:
            access_token: BASE APIのアクセストークン（直接指定の場合）
            account_id: アカウントID（AccountManager経由の場合）
            account_manager: AccountManagerインスタンス（自動更新機能を使う場合）
            proxy_id: プロキシID（config/proxies.json で定義、オプション）

        Note:
            - access_tokenを直接指定した場合、自動更新は行われません
            - account_idとaccount_managerを指定した場合、自動トークン更新が有効になります
            - proxy_id未指定でもアカウント設定にproxy_idがあれば自動適用されます
        """
        self.account_id = account_id
        self.account_manager = account_manager
        self.access_token = access_token

        # プロキシ設定の初期化
        self.proxies = None
        self._proxy_id = proxy_id

        # AccountManager経由の場合は初期トークンを取得
        if account_id and account_manager:
            token_data = account_manager.get_token_with_auto_refresh(account_id)
            if token_data:
                self.access_token = token_data['access_token']
            else:
                raise ValueError(f"アカウント {account_id} の有効なトークンを取得できませんでした")

            # プロキシIDを取得（オーナー経由で解決、明示的に指定されていない場合）
            # 解決順序: 1. コンストラクタ指定 → 2. アカウント直接指定 → 3. オーナー設定
            if not proxy_id:
                self._proxy_id = account_manager.get_proxy_id_for_account(account_id)

        # プロキシ設定を適用
        if self._proxy_id:
            try:
                proxy_manager = ProxyManager()
                self.proxies = proxy_manager.get_proxy(self._proxy_id)
                if self.proxies:
                    logger.info(f"プロキシを使用: {self._proxy_id}")
                else:
                    logger.warning(f"プロキシが見つかりません: {self._proxy_id}")
            except Exception as e:
                logger.warning(f"プロキシ設定の読み込みに失敗しました: {e}")

        if not self.access_token:
            raise ValueError("access_token または (account_id + account_manager) が必要です")

        self.headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }

    def _refresh_token_if_needed(self):
        """
        必要に応じてトークンを更新し、ヘッダーを更新

        Returns:
            bool: 更新成功時True
        """
        if not self.account_id or not self.account_manager:
            # 自動更新が無効の場合はスキップ
            return True

        # トークンを自動更新（必要な場合のみ）
        token_data = self.account_manager.get_token_with_auto_refresh(self.account_id)
        if not token_data:
            return False

        # アクセストークンとヘッダーを更新
        new_access_token = token_data['access_token']
        if new_access_token != self.access_token:
            self.access_token = new_access_token
            self.headers['Authorization'] = f'Bearer {new_access_token}'

        return True

    def _request(
        self,
        method: str,
        url: str,
        headers: Dict[str, str] = None,
        params: Dict[str, Any] = None,
        data: Dict[str, Any] = None,
        timeout: int = 30
    ) -> requests.Response:
        """
        共通HTTPリクエストメソッド（プロキシ対応）

        全てのAPIコールはこのメソッドを経由し、プロキシ設定を適用する。

        Args:
            method: HTTPメソッド（'GET', 'POST'等）
            url: リクエストURL
            headers: HTTPヘッダー（Noneの場合はself.headersを使用）
            params: クエリパラメータ
            data: リクエストボディ
            timeout: タイムアウト秒数

        Returns:
            requests.Response: レスポンスオブジェクト
        """
        kwargs = {
            'headers': headers or self.headers,
            'timeout': timeout
        }

        if params:
            kwargs['params'] = params
        if data:
            kwargs['data'] = data

        # プロキシ設定を適用
        if self.proxies:
            kwargs['proxies'] = self.proxies

        return requests.request(method, url, **kwargs)

    def create_item(self, item_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        商品を作成

        Args:
            item_data: 商品データ
                - title: 商品名（必須）
                - price: 価格（必須）
                - stock: 在庫数（必須）
                - detail: 商品説明
                - visible: 公開状態（1=公開, 0=非公開）
                - identifier: 商品コード
                等

        Returns:
            dict: API応答データ

        Raises:
            requests.exceptions.HTTPError: API呼び出しエラー
            RateLimitError: APIレート制限に達した場合
        """
        # トークン自動更新チェック
        self._refresh_token_if_needed()

        url = f"{self.BASE_URL}/items/add"
        response = self._request('POST', url, data=item_data)

        # エラー時に詳細なメッセージを取得してログ出力
        if not response.ok:
            error_detail = f"Status: {response.status_code}"
            error_type = None
            error_description = None

            try:
                error_json = response.json()
                error_type = error_json.get('error')
                error_description = error_json.get('error_description')
                error_detail += f", Response: {error_json}"
            except:
                error_detail += f", Text: {response.text[:200]}"

            # レート制限エラーの場合は特別に警告ログを出力
            if error_type == 'hour_api_limit':
                logger.warning(
                    f"[RATE_LIMIT] APIレート制限に到達しました: {error_description}"
                )
                logger.warning(
                    f"[RATE_LIMIT] Account: {self.account_id}, "
                    f"1時間後に自動リセットされます"
                )

            # 全てのAPIエラーをログに記録
            logger.error(
                f"商品登録エラー: {error_detail}, "
                f"Account: {self.account_id}"
            )

            # HTTPError例外を投げる（エラー詳細を含める）
            from requests.exceptions import HTTPError
            error_msg = f"{error_type}: {error_description}" if error_type else error_detail
            raise HTTPError(error_msg, response=response)

        return response.json()

    def update_item(self, item_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        商品を更新

        Args:
            item_id: BASE商品ID
            updates: 更新データ
                - price: 価格
                - stock: 在庫数
                - visible: 公開状態
                等

        Returns:
            dict: API応答データ

        Raises:
            requests.exceptions.HTTPError: API呼び出しエラー
        """
        # トークン自動更新チェック
        self._refresh_token_if_needed()

        url = f"{self.BASE_URL}/items/edit"

        data = {'item_id': item_id}
        data.update(updates)

        response = self._request('POST', url, data=data)

        # エラー時に詳細をログ出力
        if not response.ok:
            error_detail = f"Status: {response.status_code}"
            error_type = None
            error_description = None

            try:
                error_json = response.json()
                error_type = error_json.get('error')
                error_description = error_json.get('error_description')
                error_detail += f", Response: {error_json}"
            except:
                error_detail += f", Text: {response.text[:200]}"

            # レート制限エラーの場合は特別に警告ログを出力
            if error_type == 'hour_api_limit':
                logger.warning(
                    f"[RATE_LIMIT] 商品更新でAPIレート制限に到達: {error_description}"
                )
                logger.warning(
                    f"[RATE_LIMIT] Account: {self.account_id}, Item: {item_id}, "
                    f"1時間後に自動リセットされます"
                )

            logger.error(
                f"商品更新エラー (item_id={item_id}): {error_detail}"
            )

            from requests.exceptions import HTTPError
            error_msg = f"{error_type}: {error_description}" if error_type else error_detail
            raise HTTPError(error_msg, response=response)

        return response.json()

    def get_items(self, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """
        商品一覧を取得

        Args:
            limit: 取得件数（最大100）
            offset: オフセット

        Returns:
            dict: API応答データ

        Raises:
            requests.exceptions.HTTPError: API呼び出しエラー
        """
        # トークン自動更新チェック
        self._refresh_token_if_needed()

        url = f"{self.BASE_URL}/items"

        params = {'limit': limit, 'offset': offset}
        response = self._request('GET', url, params=params)
        response.raise_for_status()

        return response.json()

    def get_item(self, item_id: str) -> Dict[str, Any]:
        """
        商品情報を取得

        Args:
            item_id: BASE商品ID

        Returns:
            dict: API応答データ

        Raises:
            requests.exceptions.HTTPError: API呼び出しエラー
        """
        # トークン自動更新チェック
        self._refresh_token_if_needed()

        # 公式API仕様: GET /1/items/detail/:item_id
        url = f"{self.BASE_URL}/items/detail/{item_id}"

        response = self._request('GET', url)
        response.raise_for_status()

        return response.json()

    def delete_item(self, item_id: str) -> Dict[str, Any]:
        """
        商品を削除

        Args:
            item_id: BASE商品ID

        Returns:
            dict: API応答データ

        Raises:
            requests.exceptions.HTTPError: API呼び出しエラー
        """
        # トークン自動更新チェック
        self._refresh_token_if_needed()

        url = f"{self.BASE_URL}/items/delete"

        data = {'item_id': item_id}
        response = self._request('POST', url, data=data)

        # エラー時に詳細なメッセージを取得
        if not response.ok:
            error_detail = f"Status: {response.status_code}"
            try:
                error_json = response.json()
                error_detail += f", Response: {error_json}"
            except:
                error_detail += f", Text: {response.text[:200]}"

            logger.error(f"商品削除エラー (item_id={item_id}): {error_detail}")
            response.raise_for_status()  # これで詳細が上に伝わる

        return response.json()

    def add_image_from_url(self, item_id: str, image_no: int, image_url: str) -> Dict[str, Any]:
        """
        画像URLから商品画像を追加

        Args:
            item_id: BASE商品ID
            image_no: 画像番号（1-20）
            image_url: 画像URL

        Returns:
            dict: API応答データ

        Raises:
            requests.exceptions.HTTPError: API呼び出しエラー
        """
        # トークン自動更新チェック
        self._refresh_token_if_needed()

        url = f"{self.BASE_URL}/items/add_image"

        data = {
            'item_id': item_id,
            'image_no': image_no,
            'image_url': image_url
        }

        response = self._request('POST', url, data=data)

        # エラー時に詳細をログ出力
        if not response.ok:
            error_detail = f"Status: {response.status_code}"
            error_type = None
            error_description = None

            try:
                error_json = response.json()
                error_type = error_json.get('error')
                error_description = error_json.get('error_description')
                error_detail += f", Response: {error_json}"
            except:
                error_detail += f", Text: {response.text[:200]}"

            # レート制限エラーの場合は特別に警告ログを出力
            if error_type == 'hour_api_limit':
                logger.warning(
                    f"[RATE_LIMIT] 画像追加でAPIレート制限に到達: {error_description}"
                )
                logger.warning(
                    f"[RATE_LIMIT] Account: {self.account_id}, Item: {item_id}, "
                    f"1時間後に自動リセットされます"
                )

            logger.error(
                f"画像追加エラー (item_id={item_id}, image_no={image_no}): {error_detail}"
            )

            from requests.exceptions import HTTPError
            error_msg = f"{error_type}: {error_description}" if error_type else error_detail
            raise HTTPError(error_msg, response=response)

        return response.json()

    def add_images_bulk(self, item_id: str, image_urls: list, max_images: int = 20) -> Dict[str, Any]:
        """
        複数の画像URLを一括で商品に追加

        Args:
            item_id: BASE商品ID
            image_urls: 画像URLのリスト
            max_images: 最大画像数（デフォルト20、BASEの上限）

        Returns:
            dict: 処理結果
                {
                    'success_count': 成功件数,
                    'failed_count': 失敗件数,
                    'results': [{'image_no': 1, 'success': True/False, 'error': エラーメッセージ}, ...]
                }
        """
        results = []
        success_count = 0
        failed_count = 0

        # 最大画像数までループ
        for i, image_url in enumerate(image_urls[:max_images], start=1):
            if not image_url:
                continue

            try:
                self.add_image_from_url(item_id, i, image_url)
                results.append({
                    'image_no': i,
                    'image_url': image_url,
                    'success': True,
                    'error': None
                })
                success_count += 1

                # レート制限対策: 画像間で0.1秒待機（5000req/h制限対応）
                time.sleep(0.1)

            except requests.exceptions.HTTPError as e:
                error_msg = f"HTTP {e.response.status_code}: {e.response.text if e.response else str(e)}"
                results.append({
                    'image_no': i,
                    'image_url': image_url,
                    'success': False,
                    'error': error_msg
                })
                failed_count += 1

            except Exception as e:
                results.append({
                    'image_no': i,
                    'image_url': image_url,
                    'success': False,
                    'error': str(e)
                })
                failed_count += 1

        return {
            'item_id': item_id,
            'success_count': success_count,
            'failed_count': failed_count,
            'total': success_count + failed_count,
            'results': results
        }

    def get_all_items(self, max_items: int = None) -> list:
        """
        全商品を取得（ページネーション処理付き）

        Args:
            max_items: 最大取得件数（Noneの場合は全件）

        Returns:
            list: 商品リスト
        """
        all_items = []
        offset = 0
        limit = 100

        while True:
            response = self.get_items(limit=limit, offset=offset)
            items = response.get('items', [])

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
            time.sleep(0.1)  # レート制限対策（5000req/h制限対応）

        return all_items
