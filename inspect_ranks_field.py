"""ranks フィールドの中身を確認"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from integrations.amazon.sp_api_client import AmazonSPAPIClient
from integrations.amazon.config import SP_API_CREDENTIALS
from sp_api.api import CatalogItems
from sp_api.base import Marketplaces

# テストASIN
test_asins = [
    ("B0C1YY9KVT", "カテゴリあり（掃除機用バッテリー）"),
    ("B004WPOOP6", "カテゴリなし（salesRanksで取得失敗）"),
]

# 直接 CatalogItems API を呼び出し
catalog_client = CatalogItems(
    marketplace=Marketplaces.JP,
    credentials=SP_API_CREDENTIALS
)

for asin, description in test_asins:
    print("=" * 80)
    print(f"ASIN: {asin} - {description}")
    print("=" * 80)

    try:
        result = catalog_client.get_catalog_item(
            asin,
            includedData=['attributes', 'summaries', 'images', 'salesRanks']
        )
        item_data = result() if callable(result) else result

        print("\n[ranks フィールド]")
        if 'ranks' in item_data:
            ranks = item_data['ranks']
            print(json.dumps(ranks, indent=2, ensure_ascii=False))
        else:
            print("存在しません")

        print("\n[salesRanks フィールド]")
        if 'salesRanks' in item_data:
            sales_ranks = item_data['salesRanks']
            print(json.dumps(sales_ranks, indent=2, ensure_ascii=False))
        else:
            print("存在しません")

        print("\n[その他のフィールド]")
        for key in item_data.keys():
            if key not in ['ranks', 'salesRanks', 'attributes', 'images', 'summaries']:
                print(f"  - {key}: {type(item_data[key])}")

    except Exception as e:
        print(f"エラー: {e}")

    print()
