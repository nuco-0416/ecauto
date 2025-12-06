"""
キャッシュ完全欠損ASINをバッチ処理で補完するスクリプト

get_prices_batch() を使用して20件ずつ効率的に処理します
"""

import sys
from pathlib import Path
from datetime import datetime
import time

# Windows環境でのUTF-8エンコーディング強制設定
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# パスを追加
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from inventory.core.master_db import MasterDB
from inventory.core.cache_manager import AmazonProductCache
from integrations.amazon.config import SP_API_CREDENTIALS
from integrations.amazon.sp_api_client import AmazonSPAPIClient


def main():
    """メイン処理"""
    import argparse

    parser = argparse.ArgumentParser(
        description='キャッシュ完全欠損ASINをバッチ処理で補完'
    )
    parser.add_argument(
        '--platform',
        default='base',
        help='プラットフォーム名（デフォルト: base）'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='DRY RUNモード（SP-API呼び出しなし）'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=20,
        help='バッチサイズ（デフォルト: 20）'
    )

    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("キャッシュ完全欠損ASINの補完（バッチ処理版）")
    print("=" * 70)
    print(f"プラットフォーム: {args.platform}")
    print(f"バッチサイズ: {args.batch_size}件")
    print(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # 初期化
    master_db = MasterDB()
    cache = AmazonProductCache()

    # SP-APIクライアント
    if args.dry_run:
        sp_api_client = None
        print("[DRY RUN] SP-API呼び出しはスキップします")
    else:
        if all(SP_API_CREDENTIALS.values()):
            sp_api_client = AmazonSPAPIClient(SP_API_CREDENTIALS)
            print(f"[INFO] SP-APIクライアント初期化完了")
        else:
            print("[ERROR] SP-API認証情報が不足しています")
            sys.exit(1)

    # 出品済みのASINを取得
    with master_db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT DISTINCT asin
            FROM listings
            WHERE platform = ? AND status = 'listed'
        ''', (args.platform,))
        all_asins = [row[0] for row in cursor.fetchall()]

    print(f"対象ASIN数: {len(all_asins)}件")
    print()

    # キャッシュが存在しないASINのみを抽出
    missing_asins = []
    for asin in all_asins:
        cache_file = cache.cache_dir / f'{asin}.json'
        if not cache_file.exists():
            missing_asins.append(asin)

    print(f"キャッシュ完全欠損: {len(missing_asins)}件")
    print()

    if not missing_asins:
        print("補完が必要なASINはありません。")
        return

    # バッチ数を計算
    num_batches = (len(missing_asins) + args.batch_size - 1) // args.batch_size
    estimated_time = num_batches * 12  # 12秒/バッチ

    print(f"バッチ数: {num_batches}バッチ")
    print(f"推定所要時間: {estimated_time / 60:.1f}分 ({estimated_time}秒)")
    print()

    if args.dry_run:
        print(f"[DRY RUN] {len(missing_asins)}件のASINを{num_batches}バッチで取得する予定です")
        print("\n最初の20件:")
        for asin in missing_asins[:20]:
            print(f"  {asin}")
        if len(missing_asins) > 20:
            print(f"  ... 他 {len(missing_asins) - 20}件")
        return

    # バッチ処理で補完
    print("=" * 70)
    print("SP-API バッチ補完開始")
    print("=" * 70)
    print()

    # バッチ処理を実行
    results = sp_api_client.get_prices_batch(missing_asins, batch_size=args.batch_size)

    # 結果を処理
    success_count = 0
    error_count = 0
    no_data_count = 0

    print()
    print("=" * 70)
    print("キャッシュ保存処理")
    print("=" * 70)
    print()

    for i, asin in enumerate(missing_asins, 1):
        product_data = results.get(asin)

        if product_data:
            try:
                # キャッシュに保存
                now = datetime.now().isoformat()
                product_data['price_updated_at'] = now
                product_data['stock_updated_at'] = now

                cache.set_product(asin, product_data, update_types=['all'])

                # Master DBも更新
                price_jpy = product_data.get('price')
                in_stock = product_data.get('in_stock', False)

                if price_jpy is not None:
                    master_db.update_amazon_info(
                        asin=asin,
                        price_jpy=int(price_jpy),
                        in_stock=in_stock
                    )

                success_count += 1

                # 進捗表示（50件ごと）
                if i % 50 == 0:
                    print(f"[{i}/{len(missing_asins)}] キャッシュ保存中... ({i/len(missing_asins)*100:.1f}%)")

            except Exception as e:
                print(f"[{i}/{len(missing_asins)}] {asin} - 保存エラー: {e}")
                error_count += 1
        else:
            # データが取得できなかった
            no_data_count += 1
            if no_data_count <= 10:  # 最初の10件のみ表示
                print(f"[{i}/{len(missing_asins)}] {asin} - データなし")

    # 結果サマリー
    print()
    print("=" * 70)
    print("補完結果サマリー")
    print("=" * 70)
    print(f"対象ASIN数: {len(missing_asins)}件")
    print(f"  - 成功: {success_count}件")
    print(f"  - データなし: {no_data_count}件")
    print(f"  - 保存エラー: {error_count}件")
    print("=" * 70)
    print(f"終了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # 終了コード
    sys.exit(0 if error_count == 0 else 1)


if __name__ == '__main__':
    main()
