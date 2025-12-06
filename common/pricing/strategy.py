"""
価格戦略の抽象基底クラス

すべての価格戦略はこのクラスを継承して実装します。
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging


class PricingStrategy(ABC):
    """価格戦略の抽象基底クラス"""

    def __init__(self, config: Dict[str, Any]):
        """
        初期化

        Args:
            config: 戦略固有の設定辞書
        """
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    def calculate(self, amazon_price: int) -> int:
        """
        Amazon価格から販売価格を計算

        Args:
            amazon_price: Amazon.co.jpでの商品価格（日本円）

        Returns:
            計算された販売価格（日本円）

        Raises:
            ValueError: 無効な価格が渡された場合
        """
        pass

    @abstractmethod
    def get_strategy_name(self) -> str:
        """
        戦略名を取得

        Returns:
            戦略の識別名（例: "simple_markup", "tiered_markup"）
        """
        pass

    def validate_price(self, price: int, safety_config: Dict[str, Any]) -> bool:
        """
        価格が安全範囲内かチェック

        Args:
            price: チェック対象の価格
            safety_config: 安全装置の設定

        Returns:
            価格が安全範囲内の場合True、そうでない場合False
        """
        min_price = safety_config.get('min_selling_price', 0)
        max_price = safety_config.get('max_selling_price', float('inf'))

        if price < min_price:
            self.logger.warning(
                f"価格が最低出品価格を下回っています: {price}円 < {min_price}円"
            )
            return False

        if price > max_price:
            self.logger.warning(
                f"価格が最高出品価格を上回っています: {price}円 > {max_price}円"
            )
            return False

        return True

    def round_price(self, price: int, round_to: int = 10) -> int:
        """
        価格を指定単位に丸める

        Args:
            price: 元の価格
            round_to: 丸め単位（デフォルト: 10円）

        Returns:
            丸められた価格

        例:
            round_price(1984, 10) -> 1990
            round_price(1234, 100) -> 1200
        """
        if round_to <= 0:
            return price

        # 四捨五入して指定単位に丸める
        return ((price + round_to // 2) // round_to) * round_to

    def get_markup_ratio(self, amazon_price: int, selling_price: int) -> float:
        """
        実際に適用されたマークアップ率を計算

        Args:
            amazon_price: Amazon価格
            selling_price: 販売価格

        Returns:
            マークアップ率（例: 1.3）

        Raises:
            ValueError: Amazon価格が0以下の場合
        """
        if amazon_price <= 0:
            raise ValueError(f"無効なAmazon価格: {amazon_price}")

        return selling_price / amazon_price

    def validate_amazon_price(self, amazon_price: int) -> None:
        """
        Amazon価格の妥当性をチェック

        Args:
            amazon_price: チェック対象のAmazon価格

        Raises:
            ValueError: 無効な価格の場合
        """
        if not isinstance(amazon_price, (int, float)):
            raise ValueError(
                f"Amazon価格は数値である必要があります: {type(amazon_price)}"
            )

        if amazon_price <= 0:
            raise ValueError(
                f"Amazon価格は正の値である必要があります: {amazon_price}"
            )

    def should_update_price(
        self,
        current_price: Optional[int],
        new_price: int,
        min_price_diff: int = 100
    ) -> bool:
        """
        価格を更新すべきかどうかを判定

        Args:
            current_price: 現在の販売価格（Noneの場合は新規出品）
            new_price: 新しい販売価格
            min_price_diff: 更新判定の最小価格差（デフォルト: 100円）

        Returns:
            更新すべき場合True、そうでない場合False
        """
        # 新規出品の場合は常に更新
        if current_price is None:
            return True

        # 価格差が閾値以上の場合のみ更新
        price_diff = abs(new_price - current_price)
        should_update = price_diff >= min_price_diff

        if not should_update:
            self.logger.debug(
                f"価格差が閾値未満のため更新をスキップ: "
                f"差額={price_diff}円 < 閾値={min_price_diff}円"
            )

        return should_update
