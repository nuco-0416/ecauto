"""
価格情報が欠損している商品の詳細分析
"""
import sys
import os
from pathlib import Path
import json

# パスを追加
sys.path.insert(0, str(Path(__file__).resolve().parent))

from inventory.core.master_db import MasterDB
from inventory.core.cache_manager import AmazonProductCache
from integrations.amazon.sp_api_client import AmazonSPAPIClient
from integrations.amazon.config import SP_API_CREDENTIALS

def main():
    print("=" * 70)
    print("価格情報が欠損している商品の詳細分析")
    print("=" * 70)
    print()

    master_db = MasterDB()
    cache = AmazonProductCache()

    # 1. 価格情報がない商品を抽出
    print("【1. 価格情報がない商品を抽出】")

    # 全出品を取得
    all_listings = []
    for account_id in ['base_account_1', 'base_account_2']:
        listings = master_db.get_listings_by_account(
            platform='base',
            account_id=account_id,
            status='listed'
        )
        all_listings.extend(listings)

    print(f"  総出品数: {len(all_listings)}件")

    # 価格情報がない商品をフィルタ
    missing_price_asins = []

    for listing in all_listings:
        asin = listing['asin']
        cache_file = cache.cache_dir / f'{asin}.json'

        has_price = False

        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)

                if cached_data.get('price') is not None:
                    has_price = True
            except:
                pass

        if not has_price:
            missing_price_asins.append(asin)

    print(f"  価格情報なし: {len(missing_price_asins)}件")
    print()

    if not missing_price_asins:
        print("価格情報がない商品はありません。")
        return

    # 2. サンプル商品でSP-APIリクエスト
    print("【2. サンプル商品でSP-API詳細確認】")
    print(f"  サンプル数: 10件（全{len(missing_price_asins)}件中）")
    print()

    sp_api_client = AmazonSPAPIClient(SP_API_CREDENTIALS)

    failure_reasons = {
        'no_offers': [],  # オファー0件
        'filtered_out': [],  # フィルタリング条件不一致
        'api_error': [],  # APIエラー
        'unknown': []  # その他
    }

    sample_asins = missing_price_asins[:10]

    for idx, asin in enumerate(sample_asins, 1):
        print(f"  [{idx}/10] {asin}")

        # DEBUG_ASINを設定
        os.environ['DEBUG_ASIN'] = asin

        try:
            result = sp_api_client.get_prices_batch([asin], batch_size=1)

            price_info = result.get(asin)

            if price_info is None:
                print(f"    → APIエラー")
                failure_reasons['api_error'].append(asin)
            elif price_info.get('price') is None:
                # デバッグ出力から判断（オファー件数が0なら在庫切れ）
                # TODO: 実際のデバッグ出力を見て判断
                print(f"    → 在庫切れ または フィルタリング不一致")
                failure_reasons['no_offers'].append(asin)
            else:
                print(f"    → 成功（価格: {price_info.get('price')}円）")
        except Exception as e:
            print(f"    → 例外: {e}")
            failure_reasons['unknown'].append(asin)
        finally:
            if 'DEBUG_ASIN' in os.environ:
                del os.environ['DEBUG_ASIN']

        print()

    # 3. 統計表示
    print("=" * 70)
    print("【分析結果】")
    print("=" * 70)
    print(f"サンプル数: {len(sample_asins)}件")
    print()
    print("失敗理由:")
    print(f"  - オファー0件（在庫切れ）: {len(failure_reasons['no_offers'])}件")
    print(f"  - フィルタリング不一致: {len(failure_reasons['filtered_out'])}件")
    print(f"  - APIエラー: {len(failure_reasons['api_error'])}件")
    print(f"  - その他: {len(failure_reasons['unknown'])}件")
    print()

    print("推定（全体）:")
    if len(sample_asins) > 0:
        total = len(missing_price_asins)
        ratio_no_offers = len(failure_reasons['no_offers']) / len(sample_asins)
        ratio_api_error = len(failure_reasons['api_error']) / len(sample_asins)

        print(f"  - オファー0件: 約{int(total * ratio_no_offers)}件")
        print(f"  - APIエラー: 約{int(total * ratio_api_error)}件")
    print()

    # 4. 推奨事項
    print("=" * 70)
    print("【推奨事項】")
    print("=" * 70)

    if failure_reasons['api_error']:
        print("1. APIエラーの商品")
        print("   → キャッシュ/Master DBからフォールバックする実装が必要")
        print()

    if failure_reasons['no_offers']:
        print("2. オファー0件（在庫切れ）の商品")
        print("   → 在庫同期で非公開にする（既存の仕組みで対応可能）")
        print()

    print("3. エラー原因の詳細記録")
    print("   → 統計情報として記録し、ビジネス判断に活用")
    print()

if __name__ == '__main__':
    main()
