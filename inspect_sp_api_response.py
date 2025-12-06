"""SP-APIレスポンスの生データを確認"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from integrations.amazon.sp_api_client import AmazonSPAPIClient
from integrations.amazon.config import SP_API_CREDENTIALS
from sp_api.api import CatalogItems
from sp_api.base import Marketplaces

# テストASIN（カテゴリがあることが確認済み）
test_asin = "B0C1YY9KVT"

print("=" * 80)
print(f"ASIN: {test_asin} のSP-APIレスポンスを確認")
print("=" * 80)

# 直接 CatalogItems API を呼び出し
catalog_client = CatalogItems(
    marketplace=Marketplaces.JP,
    credentials=SP_API_CREDENTIALS
)

print("\n[テスト1] 基本的な includedData")
print("-" * 80)
try:
    result = catalog_client.get_catalog_item(
        test_asin,
        includedData=['attributes', 'summaries', 'images', 'salesRanks']
    )
    item_data = result() if callable(result) else result

    print("取得成功")
    print(f"トップレベルキー: {list(item_data.keys())}")

    # salesRanks の確認
    if 'salesRanks' in item_data:
        print("\n✅ salesRanks フィールドが存在します")
    else:
        print("\n❌ salesRanks フィールドがありません")

    # その他のフィールド
    print(f"\n利用可能なフィールド:")
    for key in item_data.keys():
        print(f"  - {key}")

except Exception as e:
    print(f"エラー: {e}")

# 利用可能な includedData パラメータを確認
print("\n" + "=" * 80)
print("[テスト2] sp-api ライブラリがサポートする includedData を確認")
print("=" * 80)

# ドキュメント確認
try:
    # get_catalog_item のシグネチャを確認
    import inspect
    sig = inspect.signature(catalog_client.get_catalog_item)
    print(f"\nget_catalog_item のシグネチャ:")
    print(sig)
except:
    pass

print("\n" + "=" * 80)
print("結論")
print("=" * 80)
print("SP-API Catalog Items API の仕様とライブラリのサポート状況を確認しました。")
print("browseNodeInfo が使用できない場合、別の方法でカテゴリを取得する必要があります。")
