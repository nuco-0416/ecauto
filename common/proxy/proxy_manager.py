"""
Proxy Manager

プロキシ設定の読み込みと管理を行う共通モジュール。
config/proxies.json からプロキシ設定を読み込み、
環境変数を展開して使用可能な形式で提供する。
"""

import os
import json
import re
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

# ロガー設定
logger = logging.getLogger(__name__)


class ProxyManager:
    """
    プロキシ管理クラス

    config/proxies.json からプロキシ設定を読み込み、
    環境変数を展開して使用可能な形式で提供する。

    使用例:
        pm = ProxyManager()

        # requests用
        proxies = pm.get_proxy('proxy_01')
        response = requests.get(url, proxies=proxies)

        # Playwright用
        proxy_config = pm.get_proxy_for_playwright('proxy_01')
        browser.launch(proxy=proxy_config)
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Args:
            config_path: プロキシ設定ファイルのパス（Noneの場合はデフォルト）
        """
        # 環境変数をロード
        load_dotenv()

        if config_path is None:
            # プロジェクトルートからの相対パス
            base_dir = Path(__file__).parent.parent.parent
            config_path = base_dir / "config" / "proxies.json"

        self.config_path = Path(config_path)
        self.proxies = self._load_config()

    def _load_config(self) -> Dict[str, Dict[str, Any]]:
        """
        プロキシ設定をロード

        Returns:
            dict: プロキシIDをキーとした設定辞書
        """
        if not self.config_path.exists():
            logger.warning(f"プロキシ設定ファイルが見つかりません: {self.config_path}")
            return {}

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            # id をキーとした辞書に変換
            return {p['id']: p for p in config.get('proxies', [])}
        except json.JSONDecodeError as e:
            logger.error(f"プロキシ設定の解析に失敗しました: {e}")
            return {}
        except Exception as e:
            logger.error(f"プロキシ設定の読み込みに失敗しました: {e}")
            return {}

    def _expand_env_vars(self, text: str) -> str:
        """
        テキスト内の環境変数を展開

        ${VAR_NAME} 形式の環境変数を実際の値に置換する。

        Args:
            text: 環境変数を含む可能性のあるテキスト

        Returns:
            str: 環境変数が展開されたテキスト
        """
        pattern = r'\$\{([^}]+)\}'

        def replace(match):
            var_name = match.group(1)
            value = os.environ.get(var_name, '')
            if not value:
                logger.warning(f"環境変数が未設定です: {var_name}")
            return value

        return re.sub(pattern, replace, text)

    def get_proxy(self, proxy_id: str) -> Optional[Dict[str, str]]:
        """
        指定したIDのプロキシ設定を取得（requests用）

        Args:
            proxy_id: プロキシID（config/proxies.json で定義）

        Returns:
            dict: requests用のproxies辞書 {'http': url, 'https': url}
                  存在しない場合はNone
        """
        if proxy_id not in self.proxies:
            logger.warning(f"プロキシが見つかりません: {proxy_id}")
            return None

        proxy = self.proxies[proxy_id]
        url = self._expand_env_vars(proxy['url'])

        return {
            'http': url,
            'https': url
        }

    def get_proxy_for_playwright(self, proxy_id: str) -> Optional[Dict[str, str]]:
        """
        Playwright用のプロキシ設定を取得

        Playwrightは認証情報をURL埋め込みではなく、
        別キー（username, password）で指定する必要がある。

        Args:
            proxy_id: プロキシID

        Returns:
            dict: Playwright用のproxy設定
                  {
                      'server': 'http://hostname:port',
                      'username': 'user',  # 認証が必要な場合
                      'password': 'pass'   # 認証が必要な場合
                  }
                  存在しない場合はNone
        """
        if proxy_id not in self.proxies:
            logger.warning(f"プロキシが見つかりません: {proxy_id}")
            return None

        proxy = self.proxies[proxy_id]
        url = self._expand_env_vars(proxy['url'])

        # URLをパース
        parsed = urlparse(url)

        result = {
            'server': f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"
        }

        # 認証情報があれば追加
        if parsed.username:
            result['username'] = parsed.username
        if parsed.password:
            result['password'] = parsed.password

        return result

    def get_proxy_url(self, proxy_id: str) -> Optional[str]:
        """
        プロキシURLを直接取得（環境変数展開済み）

        Args:
            proxy_id: プロキシID

        Returns:
            str: プロキシURL、存在しない場合はNone
        """
        if proxy_id not in self.proxies:
            return None

        proxy = self.proxies[proxy_id]
        return self._expand_env_vars(proxy['url'])

    def verify_proxy(self, proxy_id: str, timeout: int = 10) -> bool:
        """
        プロキシの接続を検証

        Args:
            proxy_id: プロキシID
            timeout: タイムアウト秒数

        Returns:
            bool: 接続成功時True
        """
        proxies = self.get_proxy(proxy_id)
        if not proxies:
            return False

        try:
            # IPアドレス確認サービスに接続
            response = requests.get(
                'https://api.ipify.org?format=json',
                proxies=proxies,
                timeout=timeout
            )
            if response.ok:
                ip_info = response.json()
                logger.info(f"プロキシ {proxy_id} 接続成功: IP={ip_info.get('ip')}")
                return True
            return False
        except requests.exceptions.ProxyError as e:
            logger.error(f"プロキシ接続エラー ({proxy_id}): {e}")
            return False
        except requests.exceptions.Timeout:
            logger.error(f"プロキシ接続タイムアウト ({proxy_id})")
            return False
        except Exception as e:
            logger.error(f"プロキシ検証エラー ({proxy_id}): {e}")
            return False

    def get_proxy_ip(self, proxy_id: str, timeout: int = 10) -> Optional[str]:
        """
        プロキシ経由での外部IPアドレスを取得

        Args:
            proxy_id: プロキシID
            timeout: タイムアウト秒数

        Returns:
            str: 外部IPアドレス、取得失敗時はNone
        """
        proxies = self.get_proxy(proxy_id)
        if not proxies:
            return None

        try:
            response = requests.get(
                'https://api.ipify.org?format=json',
                proxies=proxies,
                timeout=timeout
            )
            if response.ok:
                return response.json().get('ip')
            return None
        except Exception as e:
            logger.error(f"IP取得エラー ({proxy_id}): {e}")
            return None

    def list_proxies(self) -> List[str]:
        """
        全プロキシIDのリストを取得

        Returns:
            list: プロキシIDのリスト
        """
        return list(self.proxies.keys())

    def get_proxy_info(self, proxy_id: str) -> Optional[Dict[str, Any]]:
        """
        プロキシの詳細情報を取得（認証情報を除く）

        Args:
            proxy_id: プロキシID

        Returns:
            dict: プロキシ情報（id, region, type, description）
        """
        if proxy_id not in self.proxies:
            return None

        proxy = self.proxies[proxy_id]
        return {
            'id': proxy.get('id'),
            'region': proxy.get('region'),
            'type': proxy.get('type'),
            'description': proxy.get('description', '')
        }

    def print_summary(self):
        """プロキシ一覧のサマリーを表示"""
        print("\n" + "=" * 60)
        print("プロキシ一覧")
        print("=" * 60)
        print(f"設定数: {len(self.proxies)}件\n")

        for proxy_id, proxy in self.proxies.items():
            region = proxy.get('region', 'N/A')
            proxy_type = proxy.get('type', 'N/A')
            description = proxy.get('description', '')

            print(f"[{proxy_id}]")
            print(f"  リージョン: {region}")
            print(f"  タイプ: {proxy_type}")
            if description:
                print(f"  説明: {description}")
            print()

        print("=" * 60)


# スクリプトとして実行された場合のテスト
if __name__ == '__main__':
    import sys

    logging.basicConfig(level=logging.INFO)

    pm = ProxyManager()
    pm.print_summary()

    # コマンドライン引数でプロキシIDが指定されていれば検証
    if len(sys.argv) > 1:
        proxy_id = sys.argv[1]
        print(f"\nプロキシ {proxy_id} を検証中...")
        if pm.verify_proxy(proxy_id):
            print(f"接続成功: IP = {pm.get_proxy_ip(proxy_id)}")
        else:
            print("接続失敗")
