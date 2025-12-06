"""
価格計算エンジン

価格戦略を使用して実際の販売価格を計算するメインエンジン。
すべての価格計算リクエストはこのクラスを通じて処理されます。

使用例:
    from common.pricing import PriceCalculator

    calculator = PriceCalculator()

    # 基本的な使用方法
    selling_price = calculator.calculate_selling_price(amazon_price=1500)

    # プラットフォーム指定
    selling_price = calculator.calculate_selling_price(
        amazon_price=1500,
        platform='base'
    )

    # マークアップ率のオーバーライド（CLIオプション対応）
    selling_price = calculator.calculate_selling_price(
        amazon_price=1500,
        override_markup_ratio=1.4
    )
"""

import logging
from typing import Dict, Any, Optional, Union

from .config_loader import ConfigLoader
from .strategy import PricingStrategy
from .strategies import SimpleMarkupStrategy
from common.currency import CurrencyManager


class PriceCalculator:
    """価格計算エンジン"""

    def __init__(
        self,
        config_path: Optional[str] = None,
        default_strategy_name: Optional[str] = None
    ):
        """
        初期化

        Args:
            config_path: 設定ファイルのパス（Noneの場合はデフォルト）
            default_strategy_name: デフォルト戦略名（Noneの場合は設定ファイルから取得）
        """
        self.logger = logging.getLogger(self.__class__.__name__)

        # 設定ローダーの初期化
        try:
            self.config_loader = ConfigLoader(config_path)
            self.logger.info("価格計算エンジンを初期化しました")
        except Exception as e:
            self.logger.error(f"設定ローダーの初期化に失敗: {e}")
            raise

        # デフォルト戦略名
        self.default_strategy_name = default_strategy_name

        # 安全装置とログ設定を取得
        self.safety_config = self.config_loader.get_safety_config()
        self.logging_config = self.config_loader.get_logging_config()

        # 通貨換算マネージャーは遅延初期化（実際に必要になるまで初期化しない）
        # eBayなどで通貨換算が必要な場合のみ、_convert_currency()で初期化される
        self.currency_manager = None

    def calculate_selling_price(
        self,
        amazon_price: int,
        platform: Optional[str] = None,
        strategy_name: Optional[str] = None,
        override_markup_ratio: Optional[float] = None,
        current_price: Optional[Union[int, float]] = None,
        target_currency: Optional[str] = None
    ) -> Union[int, float]:
        """
        販売価格を計算

        Args:
            amazon_price: Amazon.co.jpでの商品価格（日本円）
            platform: プラットフォーム名（例: 'base'）
            strategy_name: 使用する戦略名（Noneの場合はデフォルト）
            override_markup_ratio: マークアップ率のオーバーライド（CLIオプション用）
            current_price: 現在の販売価格（価格更新判定用）
            target_currency: 変換先通貨（例: 'USD'）。Noneの場合はJPY

        Returns:
            計算された販売価格（JPYの場合はint、その他の通貨の場合はfloat）

        Raises:
            ValueError: 無効なパラメータが渡された場合
        """
        # マークアップ率がオーバーライドされている場合
        if override_markup_ratio is not None:
            selling_price_jpy = self._calculate_with_override(
                amazon_price=amazon_price,
                markup_ratio=override_markup_ratio
            )
        else:
            # 戦略名の決定
            if strategy_name is None:
                strategy_name = self.default_strategy_name

            # 戦略インスタンスを取得
            strategy = self.config_loader.get_strategy(
                strategy_name=strategy_name,
                platform=platform
            )

            # 販売価格を計算（JPY）
            selling_price_jpy = strategy.calculate(amazon_price)

            # 安全装置のチェック
            if not strategy.validate_price(selling_price_jpy, self.safety_config):
                # 安全範囲外の価格
                self.logger.warning(
                    f"計算された価格が安全範囲外です: "
                    f"Amazon価格={amazon_price}円, 販売価格={selling_price_jpy}円"
                )

                # 異常価格の警告
                if self.logging_config.get('alert_on_extreme_price', True):
                    self._alert_extreme_price(amazon_price, selling_price_jpy, strategy)

                # 安全範囲に収める
                selling_price_jpy = self._clamp_price(selling_price_jpy)

        # 通貨の決定（プラットフォーム設定から自動取得）
        if target_currency is None and platform:
            target_currency = self.config_loader.get_target_currency(platform)

        # 通貨換算（必要な場合）
        if target_currency and target_currency != 'JPY':
            selling_price = self._convert_currency(
                amount_jpy=selling_price_jpy,
                target_currency=target_currency
            )
        else:
            selling_price = selling_price_jpy

        # ログ出力
        if self.logging_config.get('log_price_changes', True):
            self._log_price_calculation(
                amazon_price=amazon_price,
                selling_price=selling_price,
                strategy=strategy if override_markup_ratio is None else None,
                current_price=current_price,
                target_currency=target_currency
            )

        return selling_price

    def _calculate_with_override(
        self,
        amazon_price: int,
        markup_ratio: float
    ) -> int:
        """
        マークアップ率のオーバーライドで価格を計算

        Args:
            amazon_price: Amazon価格
            markup_ratio: マークアップ率

        Returns:
            販売価格
        """
        # 一時的なSimpleMarkupStrategyを作成
        temp_config = {
            'markup_ratio': markup_ratio,
            'round_to': 10,
            'min_price_diff': 100,
        }

        strategy = SimpleMarkupStrategy(temp_config)
        selling_price = strategy.calculate(amazon_price)

        self.logger.info(
            f"マークアップ率をオーバーライド: {markup_ratio} "
            f"(Amazon価格={amazon_price}円 → 販売価格={selling_price}円)"
        )

        return selling_price

    def _clamp_price(self, price: int) -> int:
        """
        価格を安全範囲内に収める

        Args:
            price: 元の価格

        Returns:
            安全範囲内に収められた価格
        """
        min_price = self.safety_config.get('min_selling_price', 0)
        max_price = self.safety_config.get('max_selling_price', float('inf'))

        clamped_price = max(min_price, min(price, max_price))

        if clamped_price != price:
            self.logger.warning(
                f"価格を安全範囲内に調整: {price}円 → {clamped_price}円"
            )

        return clamped_price

    def _alert_extreme_price(
        self,
        amazon_price: int,
        selling_price: int,
        strategy: PricingStrategy
    ) -> None:
        """
        極端な価格の警告

        Args:
            amazon_price: Amazon価格
            selling_price: 販売価格
            strategy: 使用した戦略
        """
        markup_ratio = strategy.get_markup_ratio(amazon_price, selling_price)

        max_markup = self.safety_config.get('max_markup_ratio', 2.0)
        min_markup = self.safety_config.get('min_markup_ratio', 1.05)

        if markup_ratio > max_markup:
            self.logger.warning(
                f"⚠️ 異常に高いマークアップ率: {markup_ratio:.2f} "
                f"(最大: {max_markup}) - "
                f"Amazon価格={amazon_price}円, 販売価格={selling_price}円"
            )

        if markup_ratio < min_markup:
            self.logger.warning(
                f"⚠️ 異常に低いマークアップ率: {markup_ratio:.2f} "
                f"(最小: {min_markup}) - "
                f"Amazon価格={amazon_price}円, 販売価格={selling_price}円"
            )

    def _log_price_calculation(
        self,
        amazon_price: int,
        selling_price: Union[int, float],
        strategy: Optional[PricingStrategy],
        current_price: Optional[Union[int, float]],
        target_currency: Optional[str] = None
    ) -> None:
        """
        価格計算のログ出力

        Args:
            amazon_price: Amazon価格
            selling_price: 販売価格
            strategy: 使用した戦略
            current_price: 現在の価格
            target_currency: 変換先通貨
        """
        if strategy:
            markup_ratio = strategy.get_markup_ratio(amazon_price, int(selling_price) if target_currency != 'JPY' else selling_price)
            strategy_name = strategy.get_strategy_name()
        else:
            markup_ratio = 0
            strategy_name = "override"

        # 通貨フォーマット
        if target_currency == 'USD':
            price_str = f"${selling_price:.2f}"
            current_price_str = f"${current_price:.2f}" if current_price else None
        else:
            price_str = f"{int(selling_price):,}円"
            current_price_str = f"{int(current_price):,}円" if current_price else None

        log_message = (
            f"価格計算: Amazon={amazon_price:,}円 → 販売={price_str} "
            f"(マークアップ={markup_ratio:.2f}, 戦略={strategy_name}"
        )

        if target_currency and target_currency != 'JPY':
            log_message += f", 通貨={target_currency}"

        log_message += ")"

        if current_price is not None:
            if target_currency == 'USD':
                price_diff = selling_price - current_price
                log_message += f" [現在価格={current_price_str}, 差額=${price_diff:+.2f}]"
            else:
                price_diff = int(selling_price) - int(current_price)
                log_message += f" [現在価格={current_price_str}, 差額={price_diff:+d}円]"

        if self.logging_config.get('log_strategy_used', True):
            self.logger.info(log_message)
        else:
            self.logger.debug(log_message)

    def should_update_price(
        self,
        current_price: Optional[int],
        new_price: int,
        strategy_name: Optional[str] = None,
        platform: Optional[str] = None
    ) -> bool:
        """
        価格を更新すべきかどうかを判定

        Args:
            current_price: 現在の販売価格
            new_price: 新しい販売価格
            strategy_name: 使用する戦略名
            platform: プラットフォーム名

        Returns:
            更新すべき場合True
        """
        # 戦略を取得
        strategy = self.config_loader.get_strategy(
            strategy_name=strategy_name,
            platform=platform
        )

        # 戦略の最小価格差を取得
        min_price_diff = strategy.config.get('min_price_diff', 100)

        return strategy.should_update_price(
            current_price=current_price,
            new_price=new_price,
            min_price_diff=min_price_diff
        )

    def get_strategy_info(
        self,
        strategy_name: Optional[str] = None,
        platform: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        戦略の情報を取得（デバッグ用）

        Args:
            strategy_name: 戦略名
            platform: プラットフォーム名

        Returns:
            戦略情報の辞書
        """
        strategy = self.config_loader.get_strategy(
            strategy_name=strategy_name,
            platform=platform
        )

        return {
            'strategy_name': strategy.get_strategy_name(),
            'config': strategy.config,
            'safety_config': self.safety_config,
            'logging_config': self.logging_config,
        }

    def _convert_currency(
        self,
        amount_jpy: int,
        target_currency: str
    ) -> float:
        """
        通貨換算（遅延初期化対応）

        Args:
            amount_jpy: 日本円の金額
            target_currency: 変換先通貨（例: 'USD'）

        Returns:
            換算後の金額

        Raises:
            ValueError: 通貨換算に失敗した場合
        """
        # 遅延初期化: 初めて通貨換算が必要になった時に初期化
        if self.currency_manager is None:
            try:
                self.currency_manager = CurrencyManager()
                self.logger.info("通貨換算マネージャーを初期化しました（遅延初期化）")
            except Exception as e:
                self.logger.error(f"通貨換算マネージャーの初期化に失敗: {e}")
                raise ValueError(f"通貨換算マネージャーの初期化に失敗しました: {e}")

        try:
            # JPY → target_currency に換算
            amount_converted = self.currency_manager.convert(
                amount=amount_jpy,
                from_currency='JPY',
                to_currency=target_currency
            )

            # 通貨ごとの丸め処理
            if target_currency == 'USD':
                # USDは小数点2桁（セント単位）
                amount_converted = round(amount_converted, 2)
            else:
                # その他の通貨も小数点2桁
                amount_converted = round(amount_converted, 2)

            self.logger.debug(
                f"通貨換算: {amount_jpy:,}円 → {amount_converted:.2f} {target_currency}"
            )

            return amount_converted

        except Exception as e:
            self.logger.error(f"通貨換算に失敗: {e}")
            raise ValueError(f"通貨換算に失敗しました: {e}")

    def reload_config(self) -> None:
        """設定ファイルを再読み込み"""
        self.config_loader.reload_config()
        self.safety_config = self.config_loader.get_safety_config()
        self.logging_config = self.config_loader.get_logging_config()
        self.logger.info("設定ファイルを再読み込みしました")
