"""
eBay専用価格戦略

eBay輸出ビジネスの実際のコスト構造を考慮した価格計算ロジック
"""

from typing import Dict, Any
from ..strategy import PricingStrategy


class EbayCustomStrategy(PricingStrategy):
    """
    eBay専用の価格戦略

    実際のコスト構造に基づいた価格計算:
    - 固定コスト: 送料 + 梱包資材代
    - 売価に対する割合: eBay手数料(17%) + 関税(15%) + 利益率(20%)

    計算式:
    売価 = (原価 + 送料 + 梱包資材代) / (1 - 手数料率 - 関税率 - 利益率)
    """

    def __init__(self, config: Dict[str, Any]):
        """
        初期化

        Args:
            config: 戦略設定
                - shipping_cost: 送料（円、デフォルト: 4000）
                - packaging_cost: 梱包資材代（円、デフォルト: 500）
                - ebay_fee_rate: eBay手数料率（デフォルト: 0.17）
                - customs_duty_rate: 関税率（デフォルト: 0.15）
                - profit_margin: 目標利益率（デフォルト: 0.20）
                - round_to: 価格の丸め単位（デフォルト: 10）
                - min_price_diff: 最小価格差（デフォルト: 100）
        """
        super().__init__(config)

        # 固定コスト
        self.shipping_cost = config.get('shipping_cost', 4000)
        self.packaging_cost = config.get('packaging_cost', 500)

        # 売価に対する割合
        self.ebay_fee_rate = config.get('ebay_fee_rate', 0.17)
        self.customs_duty_rate = config.get('customs_duty_rate', 0.15)
        self.profit_margin = config.get('profit_margin', 0.20)

        # その他設定
        self.round_to = config.get('round_to', 10)
        self.min_price_diff = config.get('min_price_diff', 100)

        # 売価に対する割合の合計を事前計算
        self.total_rate = self.ebay_fee_rate + self.customs_duty_rate + self.profit_margin

    def calculate(self, amazon_price: int) -> int:
        """
        販売価格を計算（eBay輸出ビジネスの実コストを考慮）

        計算式:
        1. 固定コスト = 原価 + 送料 + 梱包資材代
        2. 売価に対する割合合計 = eBay手数料率 + 関税率 + 利益率
        3. 売価 = 固定コスト / (1 - 売価に対する割合合計)
        4. 10円単位への丸め

        例) 原価10,000円の場合:
           固定コスト = 10,000 + 4,000 + 500 = 14,500円
           売価 = 14,500 / (1 - 0.17 - 0.15 - 0.20) = 14,500 / 0.48 = 30,208円

           検証:
           - eBay手数料(17%): 30,208 × 0.17 = 5,135円
           - 関税(15%): 30,208 × 0.15 = 4,531円
           - 利益(20%): 30,208 × 0.20 = 6,042円
           - 固定コスト: 14,500円
           合計: 5,135 + 4,531 + 6,042 + 14,500 = 30,208円 ✓

        Args:
            amazon_price: Amazon価格（円）

        Returns:
            販売価格（円）
        """
        # 1. 固定コストの合計
        fixed_costs = amazon_price + self.shipping_cost + self.packaging_cost

        # 2. 売価の計算
        # 売価 = 固定コスト / (1 - 手数料率 - 関税率 - 利益率)
        selling_price = fixed_costs / (1 - self.total_rate)

        # 3. 10円単位への丸め（四捨五入）
        selling_price_rounded = int(selling_price)
        if selling_price_rounded % self.round_to != 0:
            selling_price_rounded = (
                (selling_price_rounded + self.round_to // 2) // self.round_to
            ) * self.round_to

        return selling_price_rounded

    def get_strategy_name(self) -> str:
        """戦略名を取得"""
        return "ebay_custom"

    def should_update_price(
        self,
        current_price: int,
        new_price: int,
        min_price_diff: int = None
    ) -> bool:
        """
        価格を更新すべきかどうかを判定

        Args:
            current_price: 現在の販売価格
            new_price: 新しい販売価格
            min_price_diff: 最小価格差（Noneの場合は設定値を使用）

        Returns:
            更新すべき場合True
        """
        if current_price is None:
            return True

        if min_price_diff is None:
            min_price_diff = self.min_price_diff

        price_diff = abs(new_price - current_price)
        return price_diff >= min_price_diff

    def get_markup_ratio(self, amazon_price: int, selling_price: int) -> float:
        """
        実際のマークアップ率を計算

        Args:
            amazon_price: Amazon価格
            selling_price: 販売価格

        Returns:
            マークアップ率
        """
        if amazon_price == 0:
            return 0.0

        return selling_price / amazon_price

    def get_cost_breakdown(self, amazon_price: int, selling_price: int) -> Dict[str, float]:
        """
        コスト内訳を取得（デバッグ・分析用）

        Args:
            amazon_price: Amazon価格
            selling_price: 販売価格

        Returns:
            コスト内訳の辞書
        """
        ebay_fee = selling_price * self.ebay_fee_rate
        customs_duty = selling_price * self.customs_duty_rate
        profit = selling_price * self.profit_margin

        return {
            'selling_price': selling_price,
            'amazon_price': amazon_price,
            'shipping_cost': self.shipping_cost,
            'packaging_cost': self.packaging_cost,
            'ebay_fee': ebay_fee,
            'customs_duty': customs_duty,
            'profit': profit,
            'total_costs': amazon_price + self.shipping_cost + self.packaging_cost,
            'total_fees_and_profit': ebay_fee + customs_duty + profit,
            'verification_sum': (
                amazon_price + self.shipping_cost + self.packaging_cost +
                ebay_fee + customs_duty + profit
            )
        }
