"""
価格取得失敗の詳細分析スクリプト

「価格情報が取得できません」の原因を詳細に分類します
"""
import sys
import os
from pathlib import Path
from collections import defaultdict

# パスを追加
sys.path.insert(0, str(Path(__file__).resolve().parent))

from inventory.core.master_db import MasterDB
from integrations.amazon.sp_api_client import AmazonSPAPIClient
from integrations.amazon.config import SP_API_CREDENTIALS

def main():
    print("=" * 70)
    print("価格取得失敗の詳細分析")
    print("=" * 70)
    print()

    # 1. 出品済み商品のASINを取得
    print("【1. 出品済み商品の取得】")
    master_db = MasterDB()

    listings = master_db.get_listings_by_account(
        platform='base',
        account_id='base_account_1',  # テスト用に1アカウントのみ
        status='listed'
    )

    print(f"  対象商品数: {len(listings)}件")

    # テスト用に最初の100件のみ
    test_asins = [listing['asin'] for listing in listings[:100]]
    print(f"  テスト対象: {len(test_asins)}件（最初の100件）")
    print()

    # 2. SP-APIで取得
    print("【2. SP-APIバッチ取得】")
    print("  詳細なデバッグ情報を収集します...")
    print()

    try:
        sp_api_client = AmazonSPAPIClient(SP_API_CREDENTIALS)

        # バッチで取得
        results = sp_api_client.get_prices_batch(test_asins, batch_size=20)

        # 3. 結果を分類
        print()
        print("【3. 結果の分類】")

        categories = {
            'success': [],  # 成功
            'api_error': [],  # APIエラー（None）
            'out_of_stock': [],  # 在庫切れ（price=None, in_stock=False）
            'unknown': []  # その他
        }

        for asin in test_asins:
            result = results.get(asin)

            if result is None:
                # APIエラー
                categories['api_error'].append(asin)
            elif isinstance(result, dict):
                if result.get('price') is not None:
                    # 成功
                    categories['success'].append(asin)
                elif result.get('in_stock') == False:
                    # 在庫切れ or フィルタリング不一致
                    categories['out_of_stock'].append(asin)
                else:
                    categories['unknown'].append(asin)
            else:
                categories['unknown'].append(asin)

        # 統計表示
        print()
        print(f"  成功: {len(categories['success'])}件")
        print(f"  APIエラー: {len(categories['api_error'])}件")
        print(f"  在庫切れ/フィルタリング不一致: {len(categories['out_of_stock'])}件")
        print(f"  その他: {len(categories['unknown'])}件")
        print()

        # 4. 在庫切れ/フィルタリング不一致の詳細確認
        if categories['out_of_stock']:
            print("【4. 在庫切れ/フィルタリング不一致の詳細分析】")
            print(f"  対象: {len(categories['out_of_stock'])}件")
            print()
            print("  サンプルASINで詳細確認...")

            # 最初の5件をDEBUG_ASINで詳細確認
            sample_asins = categories['out_of_stock'][:5]

            for idx, asin in enumerate(sample_asins, 1):
                print()
                print(f"  --- サンプル {idx}/{len(sample_asins)}: {asin} ---")

                # DEBUG_ASINを設定して再取得
                os.environ['DEBUG_ASIN'] = asin

                result = sp_api_client.get_prices_batch([asin], batch_size=1)

                # 環境変数をクリア
                del os.environ['DEBUG_ASIN']

        # 5. APIエラーの詳細確認
        if categories['api_error']:
            print()
            print("【5. APIエラーの詳細】")
            print(f"  対象: {len(categories['api_error'])}件")
            print()

            # サンプルを表示
            for idx, asin in enumerate(categories['api_error'][:10], 1):
                print(f"  {idx}. {asin}")

        # 6. 推奨事項
        print()
        print("=" * 70)
        print("【推奨事項】")
        print("=" * 70)

        if categories['api_error']:
            print(f"⚠️  APIエラー {len(categories['api_error'])}件")
            print("   → これらの商品はキャッシュ/Master DBからフォールバックすべき")

        if categories['out_of_stock']:
            print(f"⚠️  在庫切れ/フィルタリング不一致 {len(categories['out_of_stock'])}件")
            print("   → 「本当の在庫切れ」と「条件不一致」を区別する必要がある")
            print("   → 条件不一致の場合は、条件緩和を検討すべき")

        print()

    except Exception as e:
        print(f"  ❌ エラー: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
