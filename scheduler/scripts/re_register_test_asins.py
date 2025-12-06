"""
テスト用20 ASINを再登録してアップロードするスクリプト

使用方法:
    python scheduler/scripts/re_register_test_asins.py
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

# プロジェクトルートをPythonパスに追加
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from inventory.scripts.add_new_products import fetch_product_info_from_sp_api, calculate_selling_price
from scheduler.queue_manager import UploadQueueManager
from inventory.core.master_db import MasterDB
from common.ng_keyword_filter import NGKeywordFilter
from shared.utils.sku_generator import generate_sku

# 実際にBASEにアップロード成功した17 ASIN（改善版テスト用）
TEST_ASINS = [
    'B09YY6NZ7N',
    'B0D86FVG5R',
    'B092DG9B3N',
    'B071DF59C5',
    'B07YV55TNL',
    'B0DRCNW4GZ',
    'B06Y69FKT2',
    'B00EOI6XVY',
    'B006OHKDW8',
    'B0DX1BC3R8',
    'B00LUKK0IQ',
    'B07CZKGD7X',
    'B08HXN835J',
    'B09JS7R48N',
    'B0FGQJ45HW',
    'B0C6X64277',
    'B00004RFRV',
]


def main():
    print("="*60)
    print("テスト用ASIN再登録スクリプト")
    print(f"対象ASIN数: {len(TEST_ASINS)}")
    print("="*60)

    db = MasterDB()
    queue_manager = UploadQueueManager()

    # NGキーワードフィルター初期化
    ng_keywords_file = project_root / 'config' / 'NG_keywords.txt'
    ng_filter = NGKeywordFilter(str(ng_keywords_file))

    # アカウントを交互に割り当て
    accounts = ['base_account_1', 'base_account_2']

    registered_count = 0
    failed_count = 0
    skipped_count = 0

    for i, asin in enumerate(TEST_ASINS):
        account_id = accounts[i % 2]  # 交互に割り当て

        print(f"\n[{i+1}/{len(TEST_ASINS)}] ASIN: {asin}, Account: {account_id}")

        try:
            # 商品情報を取得（価格取得含む）
            product = fetch_product_info_from_sp_api(asin, use_sp_api=True, ng_filter=ng_filter)

            if not product:
                print(f"  [SKIP] 商品登録失敗（除外条件に該当）")
                skipped_count += 1
                continue

            # 価格情報を確認
            amazon_price = product.get('amazon_price_jpy')
            if not amazon_price:
                print(f"  [SKIP] 価格情報なし")
                skipped_count += 1
                continue

            # 商品をDBに保存
            db.add_product(product)

            # 販売価格を計算
            selling_price = calculate_selling_price(amazon_price)

            # 統一されたSKU生成
            sku = generate_sku(
                platform='base',
                asin=asin,
                timestamp=datetime.now()
            )

            # listingを作成
            listing_id = db.create_listing(
                asin=asin,
                platform='base',
                account_id=account_id,
                sku=sku,
                selling_price=selling_price,
                in_stock_quantity=1
            )

            # upload_queueに登録
            scheduled_time = datetime.now()  # 即時アップロード

            queue_manager.add_to_queue(
                asin=asin,
                platform='base',
                account_id=account_id,
                scheduled_time=scheduled_time,
                priority=5
            )

            print(f"  [OK] 登録完了 - 価格: ¥{amazon_price}, 販売価格: ¥{selling_price}")
            registered_count += 1

        except Exception as e:
            print(f"  [ERROR] 登録失敗: {e}")
            import traceback
            traceback.print_exc()
            failed_count += 1

    # サマリー
    print(f"\n{'='*60}")
    print(f"登録結果:")
    print(f"  成功: {registered_count}")
    print(f"  スキップ: {skipped_count}")
    print(f"  失敗: {failed_count}")
    print(f"  合計: {len(TEST_ASINS)}")
    print(f"{'='*60}")

    if registered_count > 0:
        print(f"\n次のステップ:")
        print(f"  ./venv/Scripts/python.exe scheduler/scripts/run_upload.py --batch-size {registered_count}")


if __name__ == '__main__':
    main()
