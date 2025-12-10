"""
カテゴリルーティングモジュール

商品のカテゴリに基づいて出品先アカウントを自動振り分けする
"""

import yaml
from pathlib import Path
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)


class CategoryRouter:
    """
    カテゴリに基づいて出品先アカウントを決定するルーター
    """

    def __init__(self, config_path: str = None):
        """
        Args:
            config_path: 設定ファイルパス（デフォルト: config/category_routing.yaml）
        """
        if config_path is None:
            project_root = Path(__file__).resolve().parent.parent
            config_path = project_root / 'config' / 'category_routing.yaml'

        self.config_path = Path(config_path)
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """設定ファイルを読み込む"""
        if not self.config_path.exists():
            logger.warning(f"設定ファイルが見つかりません: {self.config_path}")
            return {
                'enabled': False,
                'default_account': None,
                'accounts': {}
            }

        with open(self.config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        return config

    def reload_config(self):
        """設定ファイルを再読み込み"""
        self.config = self._load_config()

    @property
    def is_enabled(self) -> bool:
        """ルーティングが有効かどうか"""
        return self.config.get('enabled', False)

    @property
    def default_account(self) -> Optional[str]:
        """デフォルトアカウント"""
        return self.config.get('default_account')

    def get_routing_rules(self) -> List[Dict[str, Any]]:
        """
        ルーティングルールを優先順位順で取得

        Returns:
            List[dict]: 優先順位順のルーティングルール
        """
        accounts = self.config.get('accounts', {})
        rules = []

        for account_id, rule in accounts.items():
            if rule is None:
                continue

            keywords = rule.get('keywords', [])
            if not keywords:  # キーワードが空の場合はスキップ（全ジャンル対応）
                continue

            rules.append({
                'account_id': account_id,
                'priority': rule.get('priority', 99),
                'keywords': keywords
            })

        # 優先順位でソート（小さい方が優先）
        rules.sort(key=lambda x: x['priority'])

        return rules

    def route(self, category: str, available_accounts: List[str] = None) -> Optional[str]:
        """
        カテゴリに基づいて出品先アカウントを決定

        Args:
            category: 商品カテゴリ（例: "家電＆カメラ > カメラ用三脚"）
            available_accounts: 利用可能なアカウントIDのリスト（Noneの場合はチェックしない）

        Returns:
            str or None: 振り分け先のアカウントID（決定できない場合はNone）
        """
        if not self.is_enabled:
            logger.debug("カテゴリルーティングは無効です")
            return None

        if not category:
            logger.debug("カテゴリが空のため、デフォルトアカウントを返します")
            return self._get_valid_default(available_accounts)

        # ルールを優先順位順にチェック
        rules = self.get_routing_rules()

        for rule in rules:
            account_id = rule['account_id']

            # 利用可能なアカウントかチェック
            if available_accounts and account_id not in available_accounts:
                logger.debug(f"アカウント {account_id} は利用不可のためスキップ")
                continue

            # キーワードマッチング
            for keyword in rule['keywords']:
                if keyword in category:
                    logger.info(f"カテゴリルーティング: '{category}' -> {account_id} (keyword: '{keyword}')")
                    return account_id

        # マッチしない場合はデフォルト
        default = self._get_valid_default(available_accounts)
        if default:
            logger.debug(f"マッチするルールなし: '{category}' -> デフォルト {default}")
        return default

    def _get_valid_default(self, available_accounts: List[str] = None) -> Optional[str]:
        """
        有効なデフォルトアカウントを取得

        Args:
            available_accounts: 利用可能なアカウントIDのリスト

        Returns:
            str or None: デフォルトアカウントID
        """
        default = self.default_account

        if default and available_accounts and default not in available_accounts:
            logger.warning(f"デフォルトアカウント {default} は利用不可です")
            return None

        return default

    def route_batch(self, products: List[Dict[str, Any]], available_accounts: List[str] = None) -> Dict[str, List[str]]:
        """
        複数商品をバッチでルーティング

        Args:
            products: 商品情報のリスト（各商品に 'asin' と 'category' が必要）
            available_accounts: 利用可能なアカウントIDのリスト

        Returns:
            Dict[str, List[str]]: アカウントID -> ASINリストのマッピング
        """
        result = {}

        for product in products:
            asin = product.get('asin')
            category = product.get('category', '')

            if not asin:
                continue

            account_id = self.route(category, available_accounts)

            if account_id:
                if account_id not in result:
                    result[account_id] = []
                result[account_id].append(asin)

        return result

    def get_account_for_category(self, category: str) -> Dict[str, Any]:
        """
        カテゴリに対するルーティング結果の詳細を取得

        Args:
            category: 商品カテゴリ

        Returns:
            dict: ルーティング結果の詳細
                {
                    'account_id': str or None,
                    'matched_keyword': str or None,
                    'is_default': bool
                }
        """
        if not self.is_enabled:
            return {
                'account_id': None,
                'matched_keyword': None,
                'is_default': False,
                'reason': 'routing_disabled'
            }

        if not category:
            return {
                'account_id': self.default_account,
                'matched_keyword': None,
                'is_default': True,
                'reason': 'empty_category'
            }

        # ルールを優先順位順にチェック
        rules = self.get_routing_rules()

        for rule in rules:
            for keyword in rule['keywords']:
                if keyword in category:
                    return {
                        'account_id': rule['account_id'],
                        'matched_keyword': keyword,
                        'is_default': False,
                        'reason': 'keyword_match'
                    }

        return {
            'account_id': self.default_account,
            'matched_keyword': None,
            'is_default': True,
            'reason': 'no_match'
        }

    def preview_routing(self, categories: List[str]) -> List[Dict[str, Any]]:
        """
        ルーティング結果をプレビュー（デバッグ・確認用）

        Args:
            categories: カテゴリのリスト

        Returns:
            List[dict]: 各カテゴリのルーティング結果
        """
        results = []

        for category in categories:
            result = self.get_account_for_category(category)
            result['category'] = category
            results.append(result)

        return results


# シングルトンインスタンス（必要に応じて使用）
_router_instance = None


def get_category_router(config_path: str = None) -> CategoryRouter:
    """
    CategoryRouterのシングルトンインスタンスを取得

    Args:
        config_path: 設定ファイルパス（初回呼び出し時のみ有効）

    Returns:
        CategoryRouter: ルーターインスタンス
    """
    global _router_instance

    if _router_instance is None:
        _router_instance = CategoryRouter(config_path)

    return _router_instance
