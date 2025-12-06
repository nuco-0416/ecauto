"""
価格帯別マークアップ戦略

Amazon価格の価格帯に応じて異なるマークアップ率を適用する戦略。
低価格商品には高めのマージン、高価格商品には低めのマージンを設定することで、
利益率を最適化します。

設定例:
    tiers:
      - max_price: 1000
        markup_ratio: 1.4      # 1000円以下は40%
      - max_price: 5000
        markup_ratio: 1.3      # 1001-5000円は30%
      - max_price: null
        markup_ratio: 1.2      # 5001円以上は20%

計算例:
    Amazon価格 = 800円 → マークアップ率 1.4 → 販売価格 1120円
    Amazon価格 = 3000円 → マークアップ率 1.3 → 販売価格 3900円
    Amazon価格 = 15000円 → マークアップ率 1.2 → 販売価格 18000円
"""

from typing import Dict, Any, List, Optional
from ..strategy import PricingStrategy


class TieredMarkupStrategy(PricingStrategy):
    """価格帯別マークアップ戦略"""

    def __init__(self, config: Dict[str, Any]):
        """
        初期化

        Args:
            config: 戦略設定
                - tiers: 価格帯のリスト
                    - max_price: 価格帯の上限（null = 無制限）
                    - markup_ratio: 適用するマークアップ率
                - round_to: 価格の丸め単位
                - min_price_diff: 更新判定の最小価格差
        """
        super().__init__(config)

        # 設定値の取得
        self.tiers = config.get('tiers', [])
        self.round_to = config.get('round_to', 10)
        self.min_price_diff = config.get('min_price_diff', 100)

        # Tiersの検証とソート
        if not self.tiers:
            raise ValueError("価格帯（tiers）が設定されていません")

        self._validate_and_sort_tiers()

        self.logger.info(
            f"TieredMarkupStrategy初期化完了: "
            f"{len(self.tiers)}個の価格帯を設定"
        )

    def _validate_and_sort_tiers(self) -> None:
        """
        価格帯の設定を検証し、価格順にソート
        """
        # 価格順にソート（None/nullは最後）
        self.tiers.sort(key=lambda t: t['max_price'] if t['max_price'] is not None else float('inf'))

        # 各tierの検証
        for i, tier in enumerate(self.tiers):
            # 必須フィールドのチェック
            if 'markup_ratio' not in tier:
                raise ValueError(f"Tier {i}: markup_ratioが設定されていません")

            markup_ratio = tier['markup_ratio']
            if markup_ratio <= 1.0:
                raise ValueError(
                    f"Tier {i}: マークアップ率は1.0より大きい必要があります: {markup_ratio}"
                )

            # 価格帯の重複チェック
            if i > 0:
                prev_max = self.tiers[i-1]['max_price']
                curr_max = tier['max_price']

                if prev_max is not None and curr_max is not None:
                    if curr_max <= prev_max:
                        raise ValueError(
                            f"Tier {i}: 価格帯が重複または逆順です: "
                            f"{prev_max} >= {curr_max}"
                        )

    def _get_tier_for_price(self, amazon_price: int) -> Dict[str, Any]:
        """
        指定されたAmazon価格に適用すべき価格帯を取得

        Args:
            amazon_price: Amazon価格

        Returns:
            適用する価格帯の設定

        Raises:
            ValueError: 該当する価格帯が見つからない場合
        """
        for tier in self.tiers:
            max_price = tier['max_price']

            # max_priceがNoneの場合は無制限
            if max_price is None:
                return tier

            # Amazon価格がmax_price以下の場合、このtierを適用
            if amazon_price <= max_price:
                return tier

        # どの価格帯にも該当しない場合（通常は発生しないはず）
        raise ValueError(
            f"Amazon価格 {amazon_price}円 に該当する価格帯が見つかりません"
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

        # 適用する価格帯を取得
        tier = self._get_tier_for_price(amazon_price)
        markup_ratio = tier['markup_ratio']

        # マークアップを適用
        raw_price = amazon_price * markup_ratio

        # 整数に変換
        selling_price = int(raw_price)

        # 指定単位に丸める
        selling_price = self.round_price(selling_price, self.round_to)

        self.logger.debug(
            f"価格計算完了: Amazon価格={amazon_price}円 "
            f"→ 販売価格={selling_price}円 "
            f"(マークアップ率={markup_ratio}, 価格帯上限={tier['max_price']}円)"
        )

        return selling_price

    def get_strategy_name(self) -> str:
        """
        戦略名を取得

        Returns:
            戦略の識別名
        """
        return "tiered_markup"

    def get_config_summary(self) -> Dict[str, Any]:
        """
        現在の設定のサマリーを取得

        Returns:
            設定情報の辞書
        """
        return {
            'strategy': self.get_strategy_name(),
            'tiers': self.tiers,
            'round_to': self.round_to,
            'min_price_diff': self.min_price_diff,
        }

    def get_tier_info(self, amazon_price: int) -> Dict[str, Any]:
        """
        指定価格に適用される価格帯情報を取得

        Args:
            amazon_price: Amazon価格

        Returns:
            価格帯情報（デバッグ用）
        """
        tier = self._get_tier_for_price(amazon_price)
        return {
            'amazon_price': amazon_price,
            'max_price': tier['max_price'],
            'markup_ratio': tier['markup_ratio'],
            'estimated_selling_price': self.calculate(amazon_price),
        }
