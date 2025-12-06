"""
価格戦略設定ファイルのローダー

YAMLファイルから価格戦略の設定を読み込み、
適切な戦略インスタンスを生成します。
"""

import os
import yaml
import logging
from typing import Dict, Any, Optional
from pathlib import Path

from .strategy import PricingStrategy
from .strategies import SimpleMarkupStrategy, TieredMarkupStrategy, EbayCustomStrategy


class ConfigLoader:
    """価格戦略設定ローダー"""

    # 戦略名と実装クラスのマッピング
    STRATEGY_MAP = {
        'simple_markup': SimpleMarkupStrategy,
        'tiered_markup': TieredMarkupStrategy,
        'ebay_custom': EbayCustomStrategy,
        # 将来的に追加
        # 'category_based': CategoryBasedStrategy,
    }

    def __init__(self, config_path: Optional[str] = None):
        """
        初期化

        Args:
            config_path: 設定ファイルのパス（Noneの場合はデフォルトパス）
        """
        self.logger = logging.getLogger(self.__class__.__name__)

        # 設定ファイルのパス決定
        if config_path is None:
            # プロジェクトルートからの相対パス
            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / 'config' / 'pricing_strategy.yaml'

        self.config_path = Path(config_path)
        self.config: Optional[Dict[str, Any]] = None
        self._cached_strategies: Dict[str, PricingStrategy] = {}

        # 設定ファイルの存在確認
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"設定ファイルが見つかりません: {self.config_path}"
            )

        # 初回ロード
        self.load_config()

    def load_config(self) -> Dict[str, Any]:
        """
        設定ファイルを読み込む

        Returns:
            読み込んだ設定の辞書

        Raises:
            FileNotFoundError: 設定ファイルが見つからない場合
            yaml.YAMLError: YAMLの解析に失敗した場合
        """
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f)

            # キャッシュをクリア（設定が変更された可能性があるため）
            self._cached_strategies.clear()

            self.logger.info(f"設定ファイルを読み込みました: {self.config_path}")
            return self.config

        except FileNotFoundError:
            self.logger.error(f"設定ファイルが見つかりません: {self.config_path}")
            raise

        except yaml.YAMLError as e:
            self.logger.error(f"YAML解析エラー: {e}")
            raise

        except Exception as e:
            self.logger.error(f"設定ファイルの読み込みに失敗: {e}")
            raise

    def reload_config(self) -> Dict[str, Any]:
        """
        設定ファイルを再読み込み

        Returns:
            読み込んだ設定の辞書
        """
        self.logger.info("設定ファイルを再読み込みします")
        return self.load_config()

    def get_strategy(
        self,
        strategy_name: Optional[str] = None,
        platform: Optional[str] = None
    ) -> PricingStrategy:
        """
        価格戦略のインスタンスを取得

        Args:
            strategy_name: 戦略名（Noneの場合はデフォルト戦略）
            platform: プラットフォーム名（オーバーライド設定用）

        Returns:
            価格戦略インスタンス

        Raises:
            ValueError: 無効な戦略名が指定された場合
        """
        if self.config is None:
            raise RuntimeError("設定ファイルが読み込まれていません")

        # プラットフォーム固有の設定をチェック
        if platform:
            platform_config = self.config.get('platform_overrides', {}).get(platform)
            if platform_config and 'strategy' in platform_config:
                strategy_name = platform_config['strategy']
                self.logger.debug(
                    f"プラットフォーム {platform} の設定を適用: {strategy_name}"
                )

        # 戦略名の決定（デフォルトまたは指定）
        if strategy_name is None:
            strategy_name = self.config.get('default_strategy', 'simple_markup')

        # キャッシュをチェック
        cache_key = f"{strategy_name}_{platform or 'default'}"
        if cache_key in self._cached_strategies:
            return self._cached_strategies[cache_key]

        # 戦略クラスの取得
        strategy_class = self.STRATEGY_MAP.get(strategy_name)
        if strategy_class is None:
            available_strategies = ', '.join(self.STRATEGY_MAP.keys())
            raise ValueError(
                f"無効な戦略名: {strategy_name}\n"
                f"利用可能な戦略: {available_strategies}"
            )

        # 戦略固有の設定を取得
        strategy_config = self.config.get('strategies', {}).get(strategy_name)
        if strategy_config is None:
            raise ValueError(
                f"戦略 '{strategy_name}' の設定が見つかりません"
            )

        # 戦略インスタンスを生成
        try:
            strategy = strategy_class(strategy_config)
            self._cached_strategies[cache_key] = strategy

            self.logger.info(
                f"価格戦略を初期化しました: {strategy_name} "
                f"(プラットフォーム: {platform or 'default'})"
            )

            return strategy

        except Exception as e:
            self.logger.error(f"戦略の初期化に失敗: {strategy_name}, エラー: {e}")
            raise

    def get_safety_config(self) -> Dict[str, Any]:
        """
        安全装置の設定を取得

        Returns:
            安全装置の設定辞書
        """
        if self.config is None:
            raise RuntimeError("設定ファイルが読み込まれていません")

        return self.config.get('safety', {})

    def get_logging_config(self) -> Dict[str, Any]:
        """
        ログ設定を取得

        Returns:
            ログ設定の辞書
        """
        if self.config is None:
            raise RuntimeError("設定ファイルが読み込まれていません")

        return self.config.get('logging', {})

    def get_currency_config(self) -> Dict[str, Any]:
        """
        通貨換算設定を取得

        Returns:
            通貨換算設定の辞書
        """
        if self.config is None:
            raise RuntimeError("設定ファイルが読み込まれていません")

        return self.config.get('currency_conversion', {})

    def get_target_currency(self, platform: Optional[str] = None) -> str:
        """
        プラットフォームの通貨を取得

        Args:
            platform: プラットフォーム名

        Returns:
            通貨コード（例: 'JPY', 'USD'）
        """
        if self.config is None:
            raise RuntimeError("設定ファイルが読み込まれていません")

        # プラットフォーム固有の設定をチェック
        if platform:
            platform_config = self.config.get('platform_overrides', {}).get(platform)
            if platform_config and 'target_currency' in platform_config:
                return platform_config['target_currency']

        # デフォルト通貨を取得
        currency_config = self.get_currency_config()
        return currency_config.get('default_source', 'JPY')

    def get_available_strategies(self) -> list:
        """
        利用可能な戦略のリストを取得

        Returns:
            戦略名のリスト
        """
        if self.config is None:
            raise RuntimeError("設定ファイルが読み込まれていません")

        return list(self.config.get('strategies', {}).keys())

    def validate_config(self) -> bool:
        """
        設定ファイルの妥当性をチェック

        Returns:
            設定が妥当な場合True

        Raises:
            ValueError: 設定に問題がある場合
        """
        if self.config is None:
            raise RuntimeError("設定ファイルが読み込まれていません")

        # 必須フィールドのチェック
        required_fields = ['default_strategy', 'strategies', 'safety']
        for field in required_fields:
            if field not in self.config:
                raise ValueError(f"必須フィールドが見つかりません: {field}")

        # デフォルト戦略が存在するかチェック
        default_strategy = self.config['default_strategy']
        if default_strategy not in self.config['strategies']:
            raise ValueError(
                f"デフォルト戦略 '{default_strategy}' の設定が見つかりません"
            )

        # 各戦略の設定を検証（インスタンス化できるかテスト）
        for strategy_name in self.config['strategies'].keys():
            if strategy_name in self.STRATEGY_MAP:
                try:
                    self.get_strategy(strategy_name)
                except Exception as e:
                    raise ValueError(
                        f"戦略 '{strategy_name}' の検証に失敗: {e}"
                    )

        self.logger.info("設定ファイルの検証が完了しました")
        return True
