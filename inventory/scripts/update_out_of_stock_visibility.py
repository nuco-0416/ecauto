"""
在庫切れ商品を非公開設定にする専用スクリプト

キャッシュ補完レポートから特定された在庫切れ商品を
効率的に非公開（hidden）設定に更新します
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
from platforms.base.accounts.manager import AccountManager
from platforms.base.core.api_client import BaseAPIClient


def update_visibility_for_asins(asins: list, platform: str = 'base', dry_run: bool = False):
    """
    指定されたASINのvisibilityをhiddenに更新

    Args:
        asins: 更新対象のASINリスト
        platform: プラットフォーム名（デフォルト: base）
        dry_run: Trueの場合、実際の更新は行わない
    """
    print("\n" + "=" * 70)
    print("在庫切れ商品の非公開設定")
    print("=" * 70)
    print(f"プラットフォーム: {platform}")
    print(f"実行モード: {'DRY RUN（実際の更新なし）' if dry_run else '本番実行'}")
    print(f"対象ASIN数: {len(asins)}件")
    print(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # 初期化
    master_db = MasterDB()
    cache = AmazonProductCache()
    account_manager = AccountManager()

    # 統計情報
    stats = {
        'total': len(asins),
        'updated': 0,
        'skipped': 0,
        'errors': 0,
        'details': []
    }

    # アクティブなアカウント取得
    accounts = account_manager.get_active_accounts()
    if not accounts:
        print("[ERROR] アクティブなアカウントが見つかりません")
        return stats

    print(f"アクティブアカウント数: {len(accounts)}件\n")

    # アカウント別にBASE APIクライアントを準備
    clients = {}
    for account in accounts:
        account_id = account['id']
        clients[account_id] = BaseAPIClient(
            account_id=account_id,
            account_manager=account_manager
        )

    # 各ASINを処理
    for i, asin in enumerate(asins, 1):
        print(f"\n[{i}/{len(asins)}] {asin}")

        # 商品情報を取得
        product = master_db.get_product(asin)
        if not product:
            print(f"  [SKIP] 商品情報が見つかりません")
            stats['skipped'] += 1
            continue

        # キャッシュから在庫状況を確認
        cache_data = cache.get_product(asin)
        if not cache_data:
            print(f"  [WARN] キャッシュが存在しません")
        else:
            in_stock = cache_data.get('in_stock', False)
            if in_stock:
                print(f"  [WARN] キャッシュでは在庫ありと表示されています（スキップ）")
                stats['skipped'] += 1
                continue

        # 出品情報を取得
        with master_db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, account_id, platform_item_id, visibility
                FROM listings
                WHERE platform = ? AND asin = ? AND status = 'listed'
            ''', (platform, asin))
            listings = cursor.fetchall()

        if not listings:
            print(f"  [SKIP] 出品情報が見つかりません")
            stats['skipped'] += 1
            continue

        # 各出品を更新
        for listing in listings:
            listing_id = listing['id']
            account_id = listing['account_id']
            platform_item_id = listing['platform_item_id']
            current_visibility = listing['visibility']

            print(f"  出品ID: {platform_item_id} (アカウント: {account_id})")
            print(f"    現在の状態: {current_visibility}")

            if current_visibility == 'hidden':
                print(f"    → すでに非公開です（スキップ）")
                stats['skipped'] += 1
                continue

            # 変更が必要
            print(f"    → {current_visibility} → hidden に変更")

            if dry_run:
                print(f"    → DRY RUN: 実際の更新はスキップ")
                stats['updated'] += 1
                continue

            # BASE APIで更新（レート制限なし）
            try:
                client = clients.get(account_id)
                if not client:
                    print(f"    → [ERROR] アカウント {account_id} のAPIクライアントが見つかりません")
                    stats['errors'] += 1
                    stats['details'].append({
                        'asin': asin,
                        'listing_id': listing_id,
                        'error': f'APIクライアントなし（アカウント: {account_id}）'
                    })
                    continue

                # BASE APIで更新
                client.update_item(
                    item_id=platform_item_id,
                    updates={'visible': 0}
                )

                # マスタDBも更新
                master_db.update_listing(
                    listing_id=listing_id,
                    visibility='hidden'
                )

                print(f"    → 更新成功")
                stats['updated'] += 1

            except Exception as e:
                print(f"    → [ERROR] 更新エラー: {e}")
                stats['errors'] += 1
                stats['details'].append({
                    'asin': asin,
                    'listing_id': listing_id,
                    'error': str(e)
                })

    # 結果サマリー
    print("\n" + "=" * 70)
    print("処理結果サマリー")
    print("=" * 70)
    print(f"対象ASIN数: {stats['total']}件")
    print(f"  - 更新成功: {stats['updated']}件")
    print(f"  - スキップ: {stats['skipped']}件")
    print(f"  - エラー: {stats['errors']}件")

    if stats['details']:
        print("\nエラー詳細:")
        for detail in stats['details']:
            print(f"  - ASIN: {detail['asin']}, 出品ID: {detail['listing_id']}")
            print(f"    エラー: {detail['error']}")

    print("=" * 70)
    print(f"終了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    return stats


def main():
    """メイン処理"""
    import argparse

    parser = argparse.ArgumentParser(
        description='在庫切れ商品を非公開設定にする'
    )
    parser.add_argument(
        '--platform',
        default='base',
        help='プラットフォーム名（デフォルト: base）'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='DRY RUNモード（実際の更新は行わない）'
    )
    parser.add_argument(
        '--report-file',
        type=str,
        help='キャッシュ補完レポートファイルのパス'
    )
    parser.add_argument(
        '--asins',
        type=str,
        nargs='+',
        help='対象ASINを直接指定（スペース区切り）'
    )

    args = parser.parse_args()

    # ASINリストを取得
    asins = []

    if args.asins:
        # コマンドライン引数から取得
        asins = args.asins
        print(f"[INFO] コマンドライン引数からASINを取得: {len(asins)}件")

    elif args.report_file:
        # レポートファイルから取得
        report_path = Path(args.report_file)
        if not report_path.exists():
            print(f"[ERROR] レポートファイルが見つかりません: {report_path}")
            sys.exit(1)

        with open(report_path, 'r', encoding='utf-8') as f:
            report = json.load(f)
            asins = report.get('out_of_stock', {}).get('asins', [])
            print(f"[INFO] レポートファイルからASINを取得: {len(asins)}件")

    else:
        # デフォルト: 最新のレポートファイルから取得
        logs_dir = Path(__file__).parent.parent.parent / 'logs'
        report_files = sorted(logs_dir.glob('cache_fill_report_*.json'), reverse=True)

        if report_files:
            latest_report = report_files[0]
            with open(latest_report, 'r', encoding='utf-8') as f:
                report = json.load(f)
                asins = report.get('out_of_stock', {}).get('asins', [])
                print(f"[INFO] 最新レポートからASINを取得: {latest_report.name}")
                print(f"[INFO] 対象ASIN数: {len(asins)}件")
        else:
            print("[ERROR] レポートファイルが見つかりません")
            print("--asins または --report-file でASINを指定してください")
            sys.exit(1)

    if not asins:
        print("[INFO] 更新対象のASINはありません")
        sys.exit(0)

    # 更新実行
    stats = update_visibility_for_asins(asins, platform=args.platform, dry_run=args.dry_run)

    # 終了コード
    if stats['errors'] > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
