"""
キャッシュ完全欠損ASINをバッチ処理で補完（詳細ログ版）

補完失敗の原因を詳細に記録し、適切な対応を提案します
"""

import sys
from pathlib import Path
from datetime import datetime
import json

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
        description='キャッシュ完全欠損ASINをバッチ処理で補完（詳細ログ版）'
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
    print("キャッシュ完全欠損ASINの補完（詳細ログ版）")
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
        return

    # バッチ処理で補完
    print("=" * 70)
    print("SP-API バッチ補完開始")
    print("=" * 70)
    print()

    # バッチ処理を実行
    results = sp_api_client.get_prices_batch(missing_asins, batch_size=args.batch_size)

    # 結果を分類
    success_asins = []       # 価格・在庫情報を取得できたASIN
    out_of_stock_asins = []  # 在庫切れASIN（price=None, in_stock=False）
    no_data_asins = []       # データなし（None）
    error_asins = []         # 保存エラー

    print()
    print("=" * 70)
    print("結果分類と処理")
    print("=" * 70)
    print()

    for i, asin in enumerate(missing_asins, 1):
        product_data = results.get(asin)

        if product_data is None:
            # データなし（SP-APIエラー、無効なASINなど）
            no_data_asins.append(asin)
            print(f"[{i}/{len(missing_asins)}] {asin} - データなし（無効なASINの可能性）")
            continue

        # データあり（在庫切れも含む）
        try:
            now = datetime.now().isoformat()
            product_data['price_updated_at'] = now
            product_data['stock_updated_at'] = now

            # キャッシュに保存
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
                success_asins.append(asin)

                # 進捗表示（50件ごと）
                if len(success_asins) % 50 == 0:
                    print(f"[進捗] 成功: {len(success_asins)}件、在庫切れ: {len(out_of_stock_asins)}件、データなし: {len(no_data_asins)}件")
            else:
                # 在庫切れ（price=None）
                master_db.update_amazon_info(
                    asin=asin,
                    price_jpy=0,
                    in_stock=False
                )
                out_of_stock_asins.append(asin)
                print(f"[{i}/{len(missing_asins)}] {asin} - 在庫切れ（キャッシュに保存済み）")

        except Exception as e:
            print(f"[{i}/{len(missing_asins)}] {asin} - 保存エラー: {e}")
            error_asins.append({'asin': asin, 'error': str(e)})

    # 詳細レポートを保存
    report = {
        'timestamp': datetime.now().isoformat(),
        'platform': args.platform,
        'total_asins': len(missing_asins),
        'success': {
            'count': len(success_asins),
            'asins': success_asins
        },
        'out_of_stock': {
            'count': len(out_of_stock_asins),
            'asins': out_of_stock_asins
        },
        'no_data': {
            'count': len(no_data_asins),
            'asins': no_data_asins
        },
        'errors': {
            'count': len(error_asins),
            'details': error_asins
        }
    }

    report_file = Path(__file__).parent.parent.parent / 'logs' / f'cache_fill_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    report_file.parent.mkdir(exist_ok=True)
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # 結果サマリー
    print()
    print("=" * 70)
    print("補完結果サマリー")
    print("=" * 70)
    print(f"対象ASIN数: {len(missing_asins)}件")
    print()
    print(f"✅ 成功（価格・在庫取得）: {len(success_asins)}件")
    print(f"⚠️  在庫切れ（キャッシュ保存済み）: {len(out_of_stock_asins)}件")
    print(f"❌ データなし（無効なASIN）: {len(no_data_asins)}件")
    print(f"❌ 保存エラー: {len(error_asins)}件")
    print()

    if no_data_asins:
        print("--- 無効なASIN（最大20件表示）---")
        for asin in no_data_asins[:20]:
            print(f"  {asin}")
        if len(no_data_asins) > 20:
            print(f"  ... 他 {len(no_data_asins) - 20}件")
        print()

    if out_of_stock_asins:
        print("--- 在庫切れASIN（最大20件表示）---")
        for asin in out_of_stock_asins[:20]:
            print(f"  {asin}")
        if len(out_of_stock_asins) > 20:
            print(f"  ... 他 {len(out_of_stock_asins) - 20}件")
        print()

    print(f"詳細レポート: {report_file}")
    print("=" * 70)
    print(f"終了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # 次のアクション提案
    print("=" * 70)
    print("推奨アクション")
    print("=" * 70)

    if out_of_stock_asins:
        print(f"\n【在庫切れASIN: {len(out_of_stock_asins)}件】")
        print("→ ECプラットフォーム側をhiddenに設定することを推奨")
        print("   コマンド: python inventory/scripts/sync_stock_visibility.py --platform base")

    if no_data_asins:
        print(f"\n【無効なASIN: {len(no_data_asins)}件】")
        print("→ Master DBから削除することを推奨")
        print("   ※削除前に、手動で確認することを推奨")

    print("\n" + "=" * 70)
    print()

    # 終了コード
    sys.exit(0 if len(error_asins) == 0 else 1)


if __name__ == '__main__':
    main()
