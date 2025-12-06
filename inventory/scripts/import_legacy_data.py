"""
レガシーデータインポートスクリプト

既存プロジェクトのCSVデータをSP-API経由で不足情報を補完しながらマスタDBに追加

使い方:
    python inventory/scripts/import_legacy_data.py --csv legacy_data.csv --platform base --account-id base_account_1
"""

import sys
import argparse
import pandas as pd
from pathlib import Path
from datetime import datetime
import time

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from inventory.core.master_db import MasterDB
from inventory.core.cache_manager import AmazonProductCache
from shared.utils.sku_generator import generate_sku


def fetch_product_info_from_sp_api(asin: str) -> dict:
    """
    SP-APIから商品情報を取得（不足情報を補完）

    Args:
        asin: 商品ASIN

    Returns:
        dict: 商品情報
    """
    cache = AmazonProductCache()
    cached_data = cache.get_product(asin)

    if cached_data:
        return cached_data

    # TODO: Phase 4でSP-API実装
    print(f"  警告: ASIN {asin} の情報がキャッシュにありません")
    return {
        'asin': asin,
        'title_ja': None,
        'description_ja': None,
        'category': None,
        'brand': None,
        'images': [],
        'amazon_price_jpy': None,
        'amazon_in_stock': None
    }


def main():
    parser = argparse.ArgumentParser(
        description='レガシーCSVデータをマスタDBに追加'
    )
    parser.add_argument(
        '--csv',
        type=str,
        required=True,
        help='レガシーCSVファイルのパス'
    )
    parser.add_argument(
        '--platform',
        type=str,
        required=True,
        help='プラットフォーム名（base/mercari/yahoo/ebay）'
    )
    parser.add_argument(
        '--account-id',
        type=str,
        required=True,
        help='アカウントID（例: base_account_1）'
    )
    parser.add_argument(
        '--asin-column',
        type=str,
        default='ASIN',
        help='CSVのASIN列名（デフォルト: ASIN）'
    )
    parser.add_argument(
        '--status',
        type=str,
        default='pending',
        choices=['pending', 'listed'],
        help='登録時のステータス（pending=未出品、listed=出品済み）'
    )
    parser.add_argument(
        '--skip-existing',
        action='store_true',
        help='既存のASINをスキップ'
    )
    parser.add_argument(
        '--fetch-from-sp-api',
        action='store_true',
        help='SP-APIから不足情報を取得（レート制限注意）'
    )
    parser.add_argument(
        '--rate-limit',
        type=float,
        default=1.0,
        help='SP-API呼び出し間隔（秒、デフォルト: 1.0）'
    )

    args = parser.parse_args()

    print("=" * 60)
    print("レガシーデータインポート")
    print("=" * 60)

    # CSVを読み込み
    print(f"\nCSVファイルを読み込み中: {args.csv}")
    try:
        df = pd.read_csv(args.csv, encoding='utf-8-sig')
        print(f"読み込み完了: {len(df)}件")
    except Exception as e:
        print(f"エラー: CSVファイルの読み込みに失敗しました - {e}")
        return

    # ASIN列の確認
    if args.asin_column not in df.columns:
        print(f"エラー: 列 '{args.asin_column}' が見つかりません")
        print(f"利用可能な列: {', '.join(df.columns)}")
        return

    # マスタDBに接続
    db = MasterDB()

    # 設定を表示
    print(f"\nプラットフォーム: {args.platform}")
    print(f"アカウントID: {args.account_id}")
    print(f"ステータス: {args.status}")
    print(f"ASIN列: {args.asin_column}")
    print(f"SP-API取得: {'あり' if args.fetch_from_sp_api else 'なし'}")
    print(f"既存スキップ: {'あり' if args.skip_existing else 'なし'}")

    # 確認
    response = input(f"\n{len(df)}件の商品をマスタDBに追加しますか？ (y/N): ")
    if response.lower() != 'y':
        print("キャンセルしました")
        return

    # 商品を追加
    print("\n商品を追加中...")

    success_count = 0
    skip_count = 0
    error_count = 0

    for idx, row in df.iterrows():
        try:
            asin = str(row[args.asin_column]).strip()

            if not asin or asin == 'nan':
                print(f"[{idx + 1}/{len(df)}] スキップ: ASINが空")
                skip_count += 1
                continue

            # 既存チェック
            if args.skip_existing:
                existing_listings = db.get_listings_by_asin(asin)
                platform_exists = any(
                    listing['platform'] == args.platform
                    for listing in existing_listings
                )
                if platform_exists:
                    print(f"[{idx + 1}/{len(df)}] スキップ: {asin} ({args.platform}に既存)")
                    skip_count += 1
                    continue

            print(f"[{idx + 1}/{len(df)}] 処理中: {asin}")

            # CSVから取得できる情報
            title_ja = row.get('商品名') or row.get('title') or None
            description_ja = row.get('商品説明') or row.get('description') or None
            selling_price = row.get('想定売価') or row.get('selling_price') or row.get('price') or None
            item_id = row.get('item_id') or None
            sku = row.get('商品コード') or row.get('sku') or None

            # SP-APIから不足情報を取得
            sp_api_info = {}
            if args.fetch_from_sp_api:
                sp_api_info = fetch_product_info_from_sp_api(asin)
                time.sleep(args.rate_limit)

            # productsテーブルに追加（CSVとSP-APIの情報をマージ）
            db.add_product(
                asin=asin,
                title_ja=title_ja or sp_api_info.get('title_ja'),
                description_ja=description_ja or sp_api_info.get('description_ja'),
                category=sp_api_info.get('category'),
                brand=sp_api_info.get('brand'),
                images=sp_api_info.get('images'),
                amazon_price_jpy=sp_api_info.get('amazon_price_jpy'),
                amazon_in_stock=sp_api_info.get('amazon_in_stock')
            )

            # listingsテーブルに追加
            if not sku:
                # 統一されたSKU生成
                sku = generate_sku(
                    platform=args.platform,
                    asin=asin,
                    timestamp=datetime.now()
                )

            # selling_priceの型変換
            if selling_price and pd.notna(selling_price):
                selling_price = float(selling_price)
            else:
                selling_price = None

            # platform_item_idの設定
            platform_item_id = None
            if item_id and pd.notna(item_id):
                platform_item_id = str(item_id)

            db.add_listing(
                asin=asin,
                platform=args.platform,
                account_id=args.account_id,
                platform_item_id=platform_item_id,
                sku=sku,
                selling_price=selling_price,
                currency='JPY',
                in_stock_quantity=1,
                status=args.status,
                visibility='public'
            )

            print(f"  [OK] 追加完了: {title_ja or asin}")
            success_count += 1

            if (idx + 1) % 100 == 0:
                print(f"進捗: {idx + 1}/{len(df)} ({(idx + 1)/len(df)*100:.1f}%)")

        except Exception as e:
            error_count += 1
            print(f"  [ERROR] {asin if 'asin' in locals() else '不明'}: {e}")

            # 最初の5件のエラーはトレースバックを表示
            if error_count <= 5:
                import traceback
                traceback.print_exc()

    # 結果表示
    print("\n" + "=" * 60)
    print("インポート完了")
    print("=" * 60)
    print(f"成功: {success_count}件")
    print(f"スキップ: {skip_count}件")
    print(f"失敗: {error_count}件")
    print(f"合計: {len(df)}件")
    print(f"成功率: {success_count/len(df)*100:.1f}%")
    print("=" * 60)

    if args.status == 'pending':
        print("\n次のステップ:")
        print("1. キューに追加:")
        print(f"   python scheduler/scripts/add_to_queue.py --platform {args.platform} --distribute")
        print("2. デーモン起動:")
        print("   python scheduler/daemon.py")


if __name__ == '__main__':
    main()
