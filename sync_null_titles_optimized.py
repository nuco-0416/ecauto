#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
タイトルNULL商品のみをAmazon SP-APIから同期（最適化版）

最適化内容：
1. Catalog APIのレート制限を公式上限（0.5秒）に変更
2. 価格取得に get_prices_batch() を使用（20件/バッチ、12秒間隔）

予想速度改善：
- 現状: 約9.1時間（1ASINあたり5秒）
- 最適化後: 約2時間（商品情報54分 + 価格情報65分）
- 改善率: 4.5倍速
"""
import sys
import io
from pathlib import Path
from datetime import datetime
import time

# UTF-8出力を強制
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

from inventory.core.master_db import MasterDB
from inventory.core.cache_manager import AmazonProductCache
from integrations.amazon.config import SP_API_CREDENTIALS
from integrations.amazon.sp_api_client import AmazonSPAPIClient


def sync_null_title_products_optimized(
    limit: int = None,
    batch_size: int = 20,
    dry_run: bool = False,
    catalog_interval: float = 0.5  # 最適化: 公式上限（2 req/sec = 0.5秒間隔）
):
    """
    タイトルがNULLの商品のみをSP-APIから同期（最適化版）

    Args:
        limit: 同期する最大件数（Noneで全件）
        batch_size: 価格バッチ取得件数（最大20）
        dry_run: DRY RUNモード
        catalog_interval: Catalog APIのレート制限間隔（秒）

    Returns:
        dict: 実行結果
    """
    print("=" * 80)
    print("タイトルNULL商品の同期 - Amazon SP-API（最適化版）")
    print("=" * 80)
    print(f"\n開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"モード: {'DRY RUN（変更なし）' if dry_run else '本番実行'}")
    print(f"Catalog APIレート制限: {catalog_interval}秒/リクエスト")
    print(f"価格バッチサイズ: {batch_size}件\n")

    # 初期化
    db = MasterDB()
    cache = AmazonProductCache()
    sp_client = AmazonSPAPIClient(SP_API_CREDENTIALS)

    # Catalog APIのレート制限を最適化
    sp_client.min_interval_catalog = catalog_interval

    # タイトルがNULLの商品を取得
    print("タイトルNULL商品を検索中...")
    with db.get_connection() as conn:
        cursor = conn.cursor()

        query = """
            SELECT asin FROM products
            WHERE title_ja IS NULL OR title_ja = ''
            ORDER BY created_at DESC
        """
        if limit:
            query += f" LIMIT {limit}"

        cursor.execute(query)
        asins = [row['asin'] for row in cursor.fetchall()]

    if not asins:
        print("⚠️ タイトルNULL商品が見つかりませんでした")
        return {'total': 0, 'success': 0, 'failed': 0}

    print(f"対象商品: {len(asins)}件\n")

    # 速度予測
    estimated_catalog_time = len(asins) * catalog_interval
    estimated_price_time = (len(asins) + batch_size - 1) // batch_size * 12
    estimated_total_time = estimated_catalog_time + estimated_price_time

    print(f"【速度予測】")
    print(f"  商品情報取得: {estimated_catalog_time/60:.1f}分")
    print(f"  価格情報取得: {estimated_price_time/60:.1f}分")
    print(f"  合計予想時間: {estimated_total_time/60:.1f}分 ({estimated_total_time/3600:.1f}時間)\n")

    if not dry_run:
        response = input(f"SP-APIで{len(asins)}件の商品情報を取得します。続行しますか？ (y/N): ")
        if response.lower() != 'y':
            print("キャンセルしました")
            return {'total': 0, 'success': 0, 'failed': 0}
        print()

    # 統計情報
    success_count = 0
    failed_count = 0
    title_updated_count = 0
    sample_updates = []

    start_time = time.time()

    # Phase 1: 商品情報取得（個別、最適化されたレート制限）
    print("【Phase 1】商品情報取得中...")
    products_info = {}

    for i, asin in enumerate(asins, 1):
        try:
            product_info = sp_client.get_product_info(asin)

            if product_info:
                products_info[asin] = product_info
            else:
                print(f"  ⚠️ 商品情報取得失敗: {asin}")

            # 進捗表示
            if i % 50 == 0 or i == len(asins):
                elapsed = time.time() - start_time
                progress = i / len(asins) * 100
                remaining = (len(asins) - i) * catalog_interval
                print(f"  進捗: {i}/{len(asins)}件 ({progress:.1f}%) | "
                      f"経過: {elapsed/60:.1f}分 | 残り: {remaining/60:.1f}分")

        except Exception as e:
            print(f"  ❌ エラー: {asin} - {e}")

    phase1_time = time.time() - start_time
    print(f"\nPhase 1完了 - 商品情報取得: {len(products_info)}件 / {len(asins)}件")
    print(f"所要時間: {phase1_time:.1f}秒 ({phase1_time/60:.1f}分)\n")

    # Phase 2: 価格情報取得（バッチ処理）
    print("【Phase 2】価格情報取得中（バッチ処理）...")
    phase2_start = time.time()

    # バッチごとに処理
    total_batches = (len(asins) + batch_size - 1) // batch_size
    prices_info = {}

    for batch_idx in range(0, len(asins), batch_size):
        batch_asins = asins[batch_idx:batch_idx + batch_size]
        batch_num = (batch_idx // batch_size) + 1

        print(f"  [バッチ {batch_num}/{total_batches}] {len(batch_asins)}件処理中...")

        try:
            # バッチで価格取得
            batch_prices = sp_client.get_prices_batch(batch_asins, batch_size=batch_size)

            # 結果を格納
            prices_info.update(batch_prices)

        except Exception as e:
            print(f"    ❌ バッチエラー: {e}")

        # 進捗表示
        if batch_num % 10 == 0 or batch_num == total_batches:
            elapsed = time.time() - phase2_start
            progress = batch_num / total_batches * 100
            remaining = (total_batches - batch_num) * 12
            print(f"    進捗: {batch_num}/{total_batches}バッチ ({progress:.1f}%) | "
                  f"経過: {elapsed/60:.1f}分 | 残り: {remaining/60:.1f}分")

    phase2_time = time.time() - phase2_start
    print(f"\nPhase 2完了 - 価格情報取得: {len(prices_info)}件 / {len(asins)}件")
    print(f"所要時間: {phase2_time:.1f}秒 ({phase2_time/60:.1f}分)\n")

    # Phase 3: データベース更新
    print("【Phase 3】データベース更新中...")
    phase3_start = time.time()

    for asin in asins:
        product_info = products_info.get(asin)
        price_info = prices_info.get(asin)

        if product_info:
            new_title = product_info.get('title_ja')

            # 価格情報を統合
            if price_info and price_info.get('status') != 'api_error':
                product_info['amazon_price_jpy'] = price_info.get('price')
                product_info['amazon_in_stock'] = price_info.get('in_stock', False)

            if new_title:
                if not dry_run:
                    # productsテーブルを更新
                    db.add_product(
                        asin=asin,
                        title_ja=new_title,
                        title_en=product_info.get('title_en'),
                        description_ja=product_info.get('description_ja'),
                        description_en=product_info.get('description_en'),
                        brand=product_info.get('brand'),
                        images=product_info.get('images'),
                        amazon_price_jpy=product_info.get('amazon_price_jpy'),
                        amazon_in_stock=product_info.get('amazon_in_stock')
                    )

                    # キャッシュに保存
                    cache.set_product(asin, product_info)

                title_updated_count += 1

                # 最初の5件をサンプルとして記録
                if len(sample_updates) < 5:
                    title_preview = new_title[:60] + "..." if len(new_title) > 60 else new_title
                    sample_updates.append({
                        'asin': asin,
                        'title_ja': title_preview
                    })

                success_count += 1
            else:
                success_count += 1
        else:
            print(f"  ⚠️ データなし: {asin}")
            failed_count += 1

    phase3_time = time.time() - phase3_start
    duration = time.time() - start_time

    # 結果表示
    print("\n" + "=" * 80)
    print("同期完了")
    print("=" * 80)
    print(f"\n【処理結果】")
    print(f"  処理件数: {len(asins)}件")
    print(f"  成功: {success_count}件")
    print(f"  失敗: {failed_count}件")
    print(f"  タイトル更新: {title_updated_count}件")
    print(f"  成功率: {success_count/len(asins)*100:.1f}%")
    print(f"\n【処理時間】")
    print(f"  Phase 1 (商品情報): {phase1_time/60:.1f}分")
    print(f"  Phase 2 (価格情報): {phase2_time/60:.1f}分")
    print(f"  Phase 3 (DB更新): {phase3_time/60:.1f}分")
    print(f"  総時間: {duration:.1f}秒 ({duration/60:.1f}分 / {duration/3600:.1f}時間)")

    if sample_updates:
        print(f"\n【更新サンプル】最初の5件:")
        for i, sample in enumerate(sample_updates, 1):
            print(f"  {i}. {sample['asin']}: {sample['title_ja']}")

    if dry_run:
        print("\n⚠️ DRY RUNモード: 実際の更新は行われていません")

    print("=" * 80)

    return {
        'total': len(asins),
        'success': success_count,
        'failed': failed_count,
        'title_updated': title_updated_count,
        'phase1_time': phase1_time,
        'phase2_time': phase2_time,
        'phase3_time': phase3_time,
        'total_time': duration
    }


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description='タイトルNULL商品をAmazon SP-APIから同期（最適化版）'
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
        help='価格バッチ取得件数（デフォルト: 20、最大: 20）'
    )
    parser.add_argument(
        '--catalog-interval',
        type=float,
        default=0.5,
        help='Catalog APIレート制限間隔（秒、デフォルト: 0.5）'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='DRY RUNモード（実際の更新なし）'
    )

    args = parser.parse_args()

    # バッチサイズを制限
    batch_size = min(args.batch_size, 20)

    result = sync_null_title_products_optimized(
        limit=args.limit,
        batch_size=batch_size,
        dry_run=args.dry_run,
        catalog_interval=args.catalog_interval
    )

    # エラーがあれば終了コード1
    if result['failed'] > 0:
        sys.exit(1)
    else:
        sys.exit(0)
