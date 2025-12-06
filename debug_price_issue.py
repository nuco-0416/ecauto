"""
価格取得問題のデバッグスクリプト
"""
import sys
import os
from pathlib import Path

# パスを追加
sys.path.insert(0, str(Path(__file__).resolve().parent))

from integrations.amazon.sp_api_client import AmazonSPAPIClient
from integrations.amazon.config import SP_API_CREDENTIALS
from inventory.core.master_db import MasterDB
from inventory.core.cache_manager import AmazonProductCache

def main():
    # テスト対象のASIN
    test_asin = 'B0DT8B18T6'

    print(f"=== デバッグ: {test_asin} ===\n")

    # 1. マスタDBの状態確認
    print("【1. マスタDB の状態】")
    master_db = MasterDB()
    product = master_db.get_product(test_asin)

    if product:
        print(f"  ASIN: {product.get('asin')}")
        print(f"  価格: {product.get('amazon_price_jpy')}")
        print(f"  在庫: {product.get('amazon_in_stock')}")
        print(f"  更新日時: {product.get('updated_at')}")
    else:
        print(f"  マスタDBに登録なし")

    # 2. キャッシュの状態確認
    print(f"\n【2. キャッシュの状態】")
    cache = AmazonProductCache()
    cache_file = cache.cache_dir / f'{test_asin}.json'

    if cache_file.exists():
        import json
        with open(cache_file, 'r', encoding='utf-8') as f:
            cached_data = json.load(f)

        print(f"  キャッシュファイル: 存在")
        print(f"  価格: {cached_data.get('price')}")
        print(f"  在庫: {cached_data.get('in_stock')}")
        print(f"  タイムスタンプ: {cached_data.get('timestamp')}")
    else:
        print(f"  キャッシュファイル: 存在しない")

    # 3. SP-API で直接取得テスト（DEBUG_ASINを設定）
    print(f"\n【3. SP-API バッチリクエストテスト】")
    print(f"  デバッグ情報を出力します...\n")

    # DEBUG_ASIN環境変数を設定
    os.environ['DEBUG_ASIN'] = test_asin

    try:
        sp_api_client = AmazonSPAPIClient(SP_API_CREDENTIALS)

        # バッチリクエストで取得
        result = sp_api_client.get_prices_batch([test_asin], batch_size=1)

        print(f"\n【結果】")
        if test_asin in result:
            price_info = result[test_asin]
            if price_info:
                print(f"  価格: {price_info.get('price')} 円")
                print(f"  在庫: {price_info.get('in_stock')}")
                print(f"  Prime: {price_info.get('is_prime')}")
                print(f"  FBA: {price_info.get('is_fba')}")
            else:
                print(f"  ❌ 価格情報が None （APIエラー or フィルタリング条件不一致）")
        else:
            print(f"  ❌ 結果に含まれていない")

    except Exception as e:
        print(f"  ❌ エラー: {e}")
    finally:
        # 環境変数をクリア
        if 'DEBUG_ASIN' in os.environ:
            del os.environ['DEBUG_ASIN']

if __name__ == '__main__':
    main()
