"""
SKU生成ユーティリティ

プラットフォーム間で統一されたSKU（商品コード）を生成
"""

from datetime import datetime
from typing import Optional


# プラットフォームコード定義
PLATFORM_CODES = {
    'base': 'b',
    'mercari': 's',  # メルカリショップ
    'ebay': 'e',
    'yahoo': 'ya',   # ヤフオク
}


def generate_sku(
    platform: str,
    asin: str,
    timestamp: Optional[datetime] = None
) -> str:
    """
    統一されたSKUを生成

    命名規則: {platform_code}-{ASIN}-{timestamp}

    例:
        - base: b-B0FFN1RB6J-20251120230102
        - mercari: s-B0FFN1RB6J-20251120230102
        - ebay: e-B0FFN1RB6J-20251120230102
        - yahoo: ya-B0FFN1RB6J-20251120230102

    Args:
        platform: プラットフォーム名（base/mercari/ebay/yahoo）
        asin: 商品ASIN
        timestamp: タイムスタンプ（指定なしの場合は現在時刻）

    Returns:
        str: 生成されたSKU

    Raises:
        ValueError: 不明なプラットフォーム名
    """
    # プラットフォームコードを取得
    platform_lower = platform.lower()
    if platform_lower not in PLATFORM_CODES:
        raise ValueError(
            f"不明なプラットフォーム: {platform}. "
            f"有効な値: {', '.join(PLATFORM_CODES.keys())}"
        )

    platform_code = PLATFORM_CODES[platform_lower]

    # タイムスタンプを生成（YYYYMMDDHHmmSS形式）
    if timestamp is None:
        timestamp = datetime.now()

    timestamp_str = timestamp.strftime('%Y%m%d%H%M%S')

    # SKUを組み立て
    sku = f"{platform_code}-{asin}-{timestamp_str}"

    return sku


def parse_sku(sku: str) -> dict:
    """
    SKUを解析してplatform, ASIN, timestampを取得

    Args:
        sku: SKU文字列

    Returns:
        dict: {
            'platform_code': str,
            'platform': str,
            'asin': str,
            'timestamp_str': str,
            'timestamp': datetime
        }

    Raises:
        ValueError: SKU形式が不正
    """
    parts = sku.split('-')

    if len(parts) != 3:
        raise ValueError(f"不正なSKU形式: {sku}. 期待される形式: {platform_code}-{ASIN}-{timestamp}")

    platform_code, asin, timestamp_str = parts

    # プラットフォーム名を逆引き
    platform = None
    for p, code in PLATFORM_CODES.items():
        if code == platform_code:
            platform = p
            break

    if not platform:
        raise ValueError(f"不明なプラットフォームコード: {platform_code}")

    # タイムスタンプをパース
    try:
        timestamp = datetime.strptime(timestamp_str, '%Y%m%d%H%M%S')
    except ValueError:
        raise ValueError(f"不正なタイムスタンプ形式: {timestamp_str}")

    return {
        'platform_code': platform_code,
        'platform': platform,
        'asin': asin,
        'timestamp_str': timestamp_str,
        'timestamp': timestamp
    }


def add_platform(platform: str, code: str):
    """
    新しいプラットフォームを追加

    Args:
        platform: プラットフォーム名
        code: プラットフォームコード（1-2文字推奨）
    """
    PLATFORM_CODES[platform.lower()] = code


def get_supported_platforms() -> list:
    """
    サポートされているプラットフォーム一覧を取得

    Returns:
        list: プラットフォーム名のリスト
    """
    return list(PLATFORM_CODES.keys())


def get_platform_code(platform: str) -> str:
    """
    プラットフォームコードを取得

    Args:
        platform: プラットフォーム名

    Returns:
        str: プラットフォームコード

    Raises:
        ValueError: 不明なプラットフォーム名
    """
    platform_lower = platform.lower()
    if platform_lower not in PLATFORM_CODES:
        raise ValueError(
            f"不明なプラットフォーム: {platform}. "
            f"有効な値: {', '.join(PLATFORM_CODES.keys())}"
        )

    return PLATFORM_CODES[platform_lower]


# 使用例とテスト
if __name__ == '__main__':
    print("=== SKU生成テスト ===\n")

    # 各プラットフォームでSKUを生成
    test_asin = "B0FFN1RB6J"
    test_timestamp = datetime(2025, 11, 20, 23, 1, 2)

    for platform in get_supported_platforms():
        sku = generate_sku(platform, test_asin, test_timestamp)
        print(f"{platform:10s}: {sku}")

        # 解析テスト
        parsed = parse_sku(sku)
        assert parsed['platform'] == platform
        assert parsed['asin'] == test_asin
        assert parsed['timestamp'] == test_timestamp
        print(f"  -> 解析OK: {parsed}")

    print("\n=== エラーテスト ===\n")

    # 不明なプラットフォーム
    try:
        generate_sku('unknown', test_asin)
    except ValueError as e:
        print(f"✓ 期待通りのエラー: {e}")

    # 不正なSKU形式
    try:
        parse_sku('invalid-sku')
    except ValueError as e:
        print(f"✓ 期待通りのエラー: {e}")

    print("\n=== 新しいプラットフォーム追加テスト ===\n")

    # 新しいプラットフォームを追加
    add_platform('shopify', 'sh')
    sku = generate_sku('shopify', test_asin, test_timestamp)
    print(f"Shopify: {sku}")

    print("\nすべてのテストが成功しました！")
