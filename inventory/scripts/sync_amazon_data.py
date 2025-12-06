"""
Amazon商品データ同期スクリプト

マスタDBの商品情報をAmazon SP-APIから最新データに更新
価格・在庫状況を同期
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime
import time

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from inventory.core.master_db import MasterDB
from inventory.core.cache_manager import AmazonProductCache
from integrations.amazon.config import SP_API_CREDENTIALS
from integrations.amazon.sp_api_client import AmazonSPAPIClient


def sync_products_from_amazon(
    db: MasterDB,
    sp_client: AmazonSPAPIClient,
    cache: AmazonProductCache,
    limit: int = None,
    batch_size: int = 20,
    category_missing_only: bool = False
) -> dict:
    """
    マスタDB内の全商品をAmazon SP-APIから同期

    Args:
        db: MasterDBインスタンス
        sp_client: SP-APIクライアント
        cache: キャッシュマネージャー
        limit: 同期する最大件数（Noneで全件）
        batch_size: 一括取得件数（最大20）
        category_missing_only: Trueの場合、カテゴリがNULLのASINのみ同期

    Returns:
        dict: 実行結果
    """
    print(f"\n{'='*60}")
    print(f"Amazon商品データ同期開始 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    # マスタDBから全ASINを取得
    with db.get_connection() as conn:
        cursor = conn.cursor()

        query = "SELECT DISTINCT asin FROM products"

        # カテゴリ欠損フィルタ
        if category_missing_only:
            query += " WHERE category IS NULL OR category = ''"

        if limit:
            query += f" LIMIT {limit}"

        cursor.execute(query)
        asins = [row['asin'] for row in cursor.fetchall()]

    if not asins:
        print("同期対象の商品がありません")
        return {'total': 0, 'success': 0, 'failed': 0}

    print(f"同期対象: {len(asins)}件\n")

    success_count = 0
    failed_count = 0
    price_updated_count = 0

    # バッチ処理（最適化版：商品情報は個別、価格情報はバッチ）
    for i in range(0, len(asins), batch_size):
        batch = asins[i:i+batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(asins) + batch_size - 1) // batch_size

        print(f"[バッチ {batch_num}/{total_batches}] {len(batch)}件処理中...")

        try:
            # ステップ1: 商品情報を個別取得（Catalog API - バッチAPIなし）
            products_info = {}
            for asin in batch:
                try:
                    product_info = sp_client.get_product_info(asin)
                    if product_info:
                        products_info[asin] = product_info
                except Exception as e:
                    print(f"  [ERROR] {asin}: 商品情報取得失敗 - {e}")

            # ステップ2: 価格情報をバッチで一括取得（Pricing API - バッチ対応）
            print(f"  → 価格情報をバッチ取得中（{len(batch)}件）...")
            prices_data = sp_client.get_prices_batch(batch, batch_size=batch_size)

            # ステップ3: マージして更新
            for asin in batch:
                product_info = products_info.get(asin)
                price_info = prices_data.get(asin)

                if product_info:
                    # 価格情報をマージ
                    if price_info and price_info.get('status') == 'success':
                        product_info['amazon_price_jpy'] = price_info.get('price')
                        product_info['amazon_in_stock'] = price_info.get('in_stock', False)
                    else:
                        # 価格取得失敗時はNone
                        product_info['amazon_price_jpy'] = None
                        product_info['amazon_in_stock'] = False

                    # productsテーブルを更新
                    old_price = None
                    existing = db.get_product(asin)
                    if existing:
                        old_price = existing.get('amazon_price_jpy')

                    db.add_product(
                        asin=asin,
                        title_ja=product_info.get('title_ja'),
                        description_ja=product_info.get('description_ja'),
                        category=product_info.get('category'),
                        brand=product_info.get('brand'),
                        images=product_info.get('images'),
                        amazon_price_jpy=product_info.get('amazon_price_jpy'),
                        amazon_in_stock=product_info.get('amazon_in_stock')
                    )

                    # キャッシュに保存
                    cache.set_product(asin, product_info)

                    # 価格変更をチェック
                    new_price = product_info.get('amazon_price_jpy')
                    if old_price and new_price and old_price != new_price:
                        price_diff = new_price - old_price
                        print(f"  [価格更新] {asin}: ¥{old_price:,} → ¥{new_price:,} ({price_diff:+,}円)")
                        price_updated_count += 1

                    success_count += 1
                else:
                    print(f"  [ERROR] {asin}: 取得失敗")
                    failed_count += 1

        except Exception as e:
            print(f"  [ERROR] バッチ処理エラー: {e}")
            failed_count += len(batch)

        # 進捗表示
        if (i + batch_size) % 100 == 0:
            print(f"進捗: {min(i + batch_size, len(asins))}/{len(asins)} ({min(i + batch_size, len(asins))/len(asins)*100:.1f}%)")

    # 結果表示
    print(f"\n{'='*60}")
    print("同期完了")
    print(f"{'='*60}")
    print(f"処理件数: {len(asins)}件")
    print(f"成功: {success_count}件")
    print(f"失敗: {failed_count}件")
    print(f"価格更新: {price_updated_count}件")
    print(f"成功率: {success_count/len(asins)*100:.1f}%")
    print(f"{'='*60}\n")

    return {
        'total': len(asins),
        'success': success_count,
        'failed': failed_count,
        'price_updated': price_updated_count
    }


def main():
    parser = argparse.ArgumentParser(
        description='Amazon SP-APIから商品データを同期'
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='同期する最大件数（未指定で全件）'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=20,
        help='一括取得件数（デフォルト: 20、最大: 20）'
    )
    parser.add_argument(
        '--category-missing',
        action='store_true',
        help='カテゴリがNULLのASINのみ同期'
    )

    args = parser.parse_args()

    # バッチサイズを制限
    batch_size = min(args.batch_size, 20)

    # 初期化
    db = MasterDB()
    cache = AmazonProductCache()
    sp_client = AmazonSPAPIClient(SP_API_CREDENTIALS)

    # 確認
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(DISTINCT asin) as count FROM products")
        total = cursor.fetchone()['count']

    limit_text = f"{args.limit}件" if args.limit else "全件"
    filter_text = "カテゴリ欠損のみ" if args.category_missing else "全商品"
    print(f"\nマスタDB商品数: {total}件")
    print(f"フィルタ: {filter_text}")
    print(f"同期対象: {limit_text}")
    print(f"バッチサイズ: {batch_size}件")
    print(f"最適化: 価格取得にバッチAPI使用（API呼び出し約50%削減）")

    response = input(f"\n同期を開始しますか？ (y/N): ")
    if response.lower() != 'y':
        print("キャンセルしました")
        return

    # 同期実行
    result = sync_products_from_amazon(
        db=db,
        sp_client=sp_client,
        cache=cache,
        limit=args.limit,
        batch_size=batch_size,
        category_missing_only=args.category_missing
    )

    # 終了
    if result['failed'] > 0:
        print("警告: 一部の商品で同期に失敗しました")


if __name__ == '__main__':
    main()
