"""
キャッシュ完全欠損ASINのみを補完するスクリプト

期限切れは無視し、キャッシュファイルが存在しないASINのみを対象にします
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
        description='キャッシュ完全欠損ASINのみを補完'
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

    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("キャッシュ完全欠損ASINの補完")
    print("=" * 70)
    print(f"プラットフォーム: {args.platform}")
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

    if args.dry_run:
        print(f"[DRY RUN] {len(missing_asins)}件のASINをSP-APIで取得する予定です")
        print("\n最初の20件:")
        for asin in missing_asins[:20]:
            print(f"  {asin}")
        if len(missing_asins) > 20:
            print(f"  ... 他 {len(missing_asins) - 20}件")
        return

    # SP-APIで補完
    print(f"推定所要時間: {len(missing_asins) * 2.1 / 60:.1f}分")
    print()
    print("=" * 70)
    print("SP-API補完開始")
    print("=" * 70)
    print()

    success_count = 0
    error_count = 0
    errors = []

    for i, asin in enumerate(missing_asins, 1):
        try:
            # SP-APIで商品情報を取得
            product_data = sp_api_client.get_product_price(asin)

            if product_data:
                # キャッシュに保存
                now = datetime.now().isoformat()
                product_data['price_updated_at'] = now
                product_data['stock_updated_at'] = now

                cache.set_product(asin, product_data, update_types=['all'])

                # Master DBも更新
                master_db.update_amazon_info(
                    asin=asin,
                    price_jpy=product_data.get('price', 0),
                    in_stock=product_data.get('in_stock', False)
                )

                success_count += 1

                # 進捗表示（10件ごと）
                if i % 10 == 0:
                    print(f"[{i}/{len(missing_asins)}] {asin} - 成功 ({i/len(missing_asins)*100:.1f}%)")

            else:
                print(f"[{i}/{len(missing_asins)}] {asin} - データなし")
                error_count += 1

        except Exception as e:
            error_msg = f"{asin}: {str(e)}"
            print(f"[{i}/{len(missing_asins)}] {asin} - エラー: {e}")
            error_count += 1
            errors.append(error_msg)

        # レート制限（2.1秒待機）
        if i < len(missing_asins):
            time.sleep(2.1)

    # 結果サマリー
    print()
    print("=" * 70)
    print("補完結果サマリー")
    print("=" * 70)
    print(f"対象ASIN数: {len(missing_asins)}件")
    print(f"  - 成功: {success_count}件")
    print(f"  - 失敗: {error_count}件")

    if errors:
        print()
        print("エラー詳細（最大10件）:")
        for error in errors[:10]:
            print(f"  - {error}")

    print("=" * 70)
    print(f"終了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # 終了コード
    sys.exit(0 if error_count == 0 else 1)


if __name__ == '__main__':
    main()
