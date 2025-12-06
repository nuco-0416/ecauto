"""
シンプルマークアップ戦略

Amazon価格に固定のマークアップ率を適用する最も基本的な価格戦略。
これは現行システムで使用されているロジックと同じです。

計算式:
    販売価格 = Amazon価格 × マークアップ率

例:
    Amazon価格 = 1500円
    マークアップ率 = 1.3
    → 販売価格 = 1500 × 1.3 = 1950円
    → 10円単位に丸めて 1950円
"""

from typing import Dict, Any
from ..strategy import PricingStrategy


class SimpleMarkupStrategy(PricingStrategy):
    """シンプルマークアップ戦略"""

    def __init__(self, config: Dict[str, Any]):
        """
        初期化

        Args:
            config: 戦略設定
                - markup_ratio: マークアップ率（例: 1.3 = 30%利益）
                - round_to: 価格の丸め単位（例: 10 = 10円単位）
                - min_price_diff: 更新判定の最小価格差（例: 100円）
        """
        super().__init__(config)

        # 設定値の取得
        self.markup_ratio = config.get('markup_ratio', 1.3)
        self.round_to = config.get('round_to', 10)
        self.min_price_diff = config.get('min_price_diff', 100)

        # 設定値の検証
        if self.markup_ratio <= 1.0:
            raise ValueError(
                f"マークアップ率は1.0より大きい必要があります: {self.markup_ratio}"
            )

        self.logger.info(
            f"SimpleMarkupStrategy初期化完了: "
            f"マークアップ率={self.markup_ratio}, "
            f"丸め単位={self.round_to}円, "
            f"最小価格差={self.min_price_diff}円"
        )

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
        # Amazon価格の妥当性チェック
        self.validate_amazon_price(amazon_price)

        # マークアップを適用
        raw_price = amazon_price * self.markup_ratio

        # 整数に変換
        selling_price = int(raw_price)

        # 指定単位に丸める
        selling_price = self.round_price(selling_price, self.round_to)

        self.logger.debug(
            f"価格計算完了: Amazon価格={amazon_price}円 "
            f"→ 販売価格={selling_price}円 "
            f"(マークアップ率={self.markup_ratio})"
        )

        return selling_price

    def get_strategy_name(self) -> str:
        """
        戦略名を取得

        Returns:
            戦略の識別名
        """
        return "simple_markup"

    def get_config_summary(self) -> Dict[str, Any]:
        """
        現在の設定のサマリーを取得

        Returns:
            設定情報の辞書
        """
        return {
            'strategy': self.get_strategy_name(),
            'markup_ratio': self.markup_ratio,
            'round_to': self.round_to,
            'min_price_diff': self.min_price_diff,
        }
