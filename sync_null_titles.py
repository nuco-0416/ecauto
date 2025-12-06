#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
タイトルNULL商品のみをAmazon SP-APIから同期

ISSUE #23対応: バックアップから復元できなかった残り6,585件を更新
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


def sync_null_title_products(limit: int = None, batch_size: int = 20, dry_run: bool = False):
    """
    タイトルがNULLの商品のみをSP-APIから同期

    Args:
        limit: 同期する最大件数（Noneで全件）
        batch_size: 一括取得件数（最大20）
        dry_run: DRY RUNモード

    Returns:
        dict: 実行結果
    """
    print("=" * 80)
    print("タイトルNULL商品の同期 - Amazon SP-API")
    print("=" * 80)
    print(f"\n開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"モード: {'DRY RUN（変更なし）' if dry_run else '本番実行'}")
    print(f"バッチサイズ: {batch_size}件\n")

    # 初期化
    db = MasterDB()
    cache = AmazonProductCache()
    sp_client = AmazonSPAPIClient(SP_API_CREDENTIALS)

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
    already_has_title = 0
    sample_updates = []

    # バッチ処理
    start_time = time.time()

    for i in range(0, len(asins), batch_size):
        batch = asins[i:i+batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(asins) + batch_size - 1) // batch_size

        print(f"[バッチ {batch_num}/{total_batches}] {len(batch)}件処理中...")

        try:
            # SP-APIから一括取得
            products_data = sp_client.get_products_batch(batch)

            # 各商品を更新
            for asin in batch:
                product_data = products_data.get(asin)

                if product_data:
                    # タイトルが取得できたか確認
                    new_title = product_data.get('title_ja')

                    if new_title:
                        if not dry_run:
                            # productsテーブルを更新
                            db.add_product(
                                asin=asin,
                                title_ja=new_title,
                                title_en=product_data.get('title_en'),
                                description_ja=product_data.get('description_ja'),
                                description_en=product_data.get('description_en'),
                                brand=product_data.get('brand'),
                                images=product_data.get('images'),
                                amazon_price_jpy=product_data.get('amazon_price_jpy'),
                                amazon_in_stock=product_data.get('amazon_in_stock')
                            )

                            # キャッシュに保存
                            cache.set_product(asin, product_data)

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
                        # タイトルが取得できなかった
                        already_has_title += 1
                        success_count += 1
                else:
                    print(f"  ⚠️ 取得失敗: {asin}")
                    failed_count += 1

        except Exception as e:
            print(f"  ❌ バッチ処理エラー: {e}")
            failed_count += len(batch)

        # 進捗表示
        if (i + batch_size) % 100 == 0 or (i + batch_size) >= len(asins):
            processed = min(i + batch_size, len(asins))
            print(f"  進捗: {processed}/{len(asins)}件 ({processed/len(asins)*100:.1f}%)")

        # SP-APIレート制限対応（2秒待機）
        if batch_num < total_batches:
            time.sleep(2.1)

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
    print(f"  所要時間: {duration:.1f}秒 ({duration/60:.1f}分)")

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
        'title_updated': title_updated_count
    }


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description='タイトルNULL商品をAmazon SP-APIから同期'
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
        '--dry-run',
        action='store_true',
        help='DRY RUNモード（実際の更新なし）'
    )

    args = parser.parse_args()

    # バッチサイズを制限
    batch_size = min(args.batch_size, 20)

    result = sync_null_title_products(
        limit=args.limit,
        batch_size=batch_size,
        dry_run=args.dry_run
    )

    # エラーがあれば終了コード1
    if result['failed'] > 0:
        sys.exit(1)
    else:
        sys.exit(0)
