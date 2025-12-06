"""
価格決定モジュール

このモジュールは商品の出品価格を計算するための
戦略パターンベースの価格決定システムを提供します。

主要コンポーネント:
- PricingStrategy: 価格戦略の抽象基底クラス
- PriceCalculator: 価格計算エンジン
- ConfigLoader: 設定ファイルローダー

使用例:
    from common.pricing import PriceCalculator

    calculator = PriceCalculator()
    selling_price = calculator.calculate_selling_price(
        amazon_price=1500,
        platform='base',
        account_id='base_account_1'
    )
"""

from .strategy import PricingStrategy
from .calculator import PriceCalculator
from .config_loader import ConfigLoader

__all__ = [
    'PricingStrategy',
    'PriceCalculator',
    'ConfigLoader',
]

__version__ = '1.0.0'
