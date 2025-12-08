"""
新規商品追加スクリプト

ASINリストからSP-API経由で商品情報を取得してマスタDBに追加

使い方:
    python inventory/scripts/add_new_products.py --asin-file asins.txt --platform base --account-id base_account_1
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime
import time
import json

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from inventory.core.master_db import MasterDB
from inventory.core.product_manager import ProductManager
from inventory.core.listing_manager import ListingManager
from inventory.core.prohibited_item_checker import ProhibitedItemChecker
from inventory.core.blocklist_manager import BlocklistManager
from common.ng_keyword_filter import NGKeywordFilter
from common.pricing import PriceCalculator
from shared.utils.sku_generator import generate_sku


def read_asin_list(file_path: str) -> list:
    """
    ASINリストファイルを読み込み

    Args:
        file_path: ASINリストファイルのパス（改行区切り）

    Returns:
        list: ASINのリスト
    """
    asins = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            asin = line.strip()
            if asin and not asin.startswith('#'):  # コメント行を除外
                asins.append(asin)
    return asins


def fetch_prices_batch(asins: list, batch_size: int = 20) -> dict:
    """
    複数ASINの価格情報をバッチで取得

    Args:
        asins: ASINのリスト
        batch_size: バッチサイズ（デフォルト: 20）

    Returns:
        dict: ASIN別の価格情報 {asin: {'price': xxx, 'in_stock': True, ...}}
    """
    try:
        from integrations.amazon.config import SP_API_CREDENTIALS
        from integrations.amazon.sp_api_client import AmazonSPAPIClient

        sp_client = AmazonSPAPIClient(SP_API_CREDENTIALS)
        results = sp_client.get_prices_batch(asins, batch_size=batch_size)
        return results
    except Exception as e:
        print(f"  エラー: バッチ価格取得失敗 - {e}")
        return {}


def fetch_product_info_from_sp_api(asin: str, use_sp_api: bool = True, ng_filter: NGKeywordFilter = None, price_info: dict = None, master_db: MasterDB = None) -> dict:
    """
    商品情報を取得（productsテーブル優先、必要に応じてSP-API）

    Args:
        asin: 商品ASIN
        use_sp_api: SP-APIを使用するか（Falseの場合はproductsテーブルのみ）
        ng_filter: NGキーワードフィルター（Noneの場合はフィルター無効）
        price_info: 事前に取得した価格情報（バッチ処理用、オプション）
        master_db: MasterDBインスタンス（Noneの場合は新規作成）

    Returns:
        dict: 商品情報
            - title_ja: 商品名
            - description_ja: 商品説明
            - category: カテゴリ
            - brand: ブランド
            - images: 画像URLリスト
            - amazon_price_jpy: Amazon価格
            - amazon_in_stock: 在庫状況
    """
    # MasterDBインスタンスを取得
    if master_db is None:
        master_db = MasterDB()

    # productsテーブルから取得を試みる
    existing_product = master_db.get_product(asin)

    # productsテーブルに価格情報も含まれている場合はそれを返す
    if existing_product and existing_product.get('amazon_price_jpy') is not None:
        # NGキーワードフィルターを適用
        if ng_filter:
            existing_product['title_ja'] = ng_filter.filter_title(existing_product.get('title_ja', ''))
            existing_product['description_ja'] = ng_filter.filter_description(existing_product.get('description_ja', ''))
        return existing_product

    # SP-APIから取得（productsテーブルにないか、価格情報がない場合）
    if use_sp_api:
        try:
            from integrations.amazon.config import SP_API_CREDENTIALS
            from integrations.amazon.sp_api_client import AmazonSPAPIClient

            sp_client = AmazonSPAPIClient(SP_API_CREDENTIALS)

            # 商品情報を取得（価格情報は除く）
            product_info = sp_client.get_product_info(asin)

            if product_info:
                # 価格情報を統合
                if price_info and price_info is not None:
                    # バッチで取得した価格情報を使用
                    product_info['amazon_price_jpy'] = price_info.get('price')
                    product_info['amazon_in_stock'] = price_info.get('in_stock', False)
                else:
                    # 価格情報を個別に取得（従来の方式）
                    price_data = sp_client.get_product_price(asin)
                    if price_data:
                        product_info['amazon_price_jpy'] = price_data.get('price')
                        product_info['amazon_in_stock'] = price_data.get('in_stock', False)

                # NGキーワードフィルターを適用
                if ng_filter:
                    product_info['title_ja'] = ng_filter.filter_title(product_info.get('title_ja', ''))
                    product_info['description_ja'] = ng_filter.filter_description(product_info.get('description_ja', ''))

                # productsテーブルに保存（キャッシュは使用しない）
                master_db.add_product(
                    asin=asin,
                    title_ja=product_info.get('title_ja'),
                    description_ja=product_info.get('description_ja'),
                    category=product_info.get('category'),
                    brand=product_info.get('brand'),
                    images=product_info.get('images'),
                    amazon_price_jpy=product_info.get('amazon_price_jpy'),
                    amazon_in_stock=product_info.get('amazon_in_stock')
                )
                print(f"  [SP-API] 商品情報取得成功")
                return product_info

        except Exception as e:
            print(f"  警告: SP-API取得エラー - {e}")

    # productsテーブルにもSP-APIにもない場合はNoneを返す（ダミーデータは登録しない）
    print(f"  エラー: ASIN {asin} の情報が取得できません。このASINはスキップされます")
    return None


def main():
    parser = argparse.ArgumentParser(
        description='ASINリストから新規商品をマスタDBに追加'
    )
    parser.add_argument(
        '--asin-file',
        type=str,
        required=True,
        help='ASINリストファイル（改行区切り）'
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
        '--markup-rate',
        type=float,
        default=1.3,
        help='Amazon価格に対する掛け率（デフォルト: 1.3）'
    )
    parser.add_argument(
        '--skip-existing',
        action='store_true',
        default=True,
        help='既存のASINをスキップ（デフォルト: 有効）'
    )
    parser.add_argument(
        '--no-skip-existing',
        action='store_false',
        dest='skip_existing',
        help='既存のASINもスキップせずに処理'
    )
    parser.add_argument(
        '--use-sp-api',
        action='store_true',
        help='SP-APIから商品情報を取得（デフォルトはキャッシュのみ）'
    )
    parser.add_argument(
        '--rate-limit',
        type=float,
        default=1.0,
        help='SP-API呼び出し間隔（秒、デフォルト: 1.0）'
    )
    parser.add_argument(
        '--yes', '-y',
        action='store_true',
        help='確認をスキップして自動実行'
    )
    parser.add_argument(
        '--no-auto-queue',
        action='store_true',
        help='自動的にキューへ追加しない（デフォルト: 自動追加する）'
    )
    parser.add_argument(
        '--queue-priority',
        type=int,
        default=5,
        help='キューへ追加する際の優先度（1-20、デフォルト: 5）'
    )
    parser.add_argument(
        '--auto-distribute-accounts',
        action='store_true',
        help='複数アカウントへ自動分散（デフォルト: 指定アカウントのみ使用）'
    )
    parser.add_argument(
        '--hourly-limit',
        type=int,
        default=100,
        help='1時間あたりの最大アップロード件数（デフォルト: 100）'
    )
    parser.add_argument(
        '--check-prohibited',
        action='store_true',
        help='禁止商品チェックを有効にする（推奨）'
    )
    parser.add_argument(
        '--prohibited-threshold',
        type=int,
        default=80,
        help='禁止商品の自動ブロック閾値（デフォルト: 80）'
    )

    args = parser.parse_args()

    print("=" * 60)
    print("新規商品追加")
    print("=" * 60)

    # ASINリストを読み込み
    print(f"\nASINリストを読み込み中: {args.asin_file}")
    asins = read_asin_list(args.asin_file)
    print(f"読み込み完了: {len(asins)}件")

    # マスタDBに接続
    db = MasterDB()

    # マネージャー初期化（リファクタリング後）
    product_manager = ProductManager(master_db=db)
    listing_manager = ListingManager(master_db=db)
    price_calculator = PriceCalculator()  # 価格計算エンジン

    # NGキーワードフィルターを初期化
    ng_keywords_file = project_root / 'config' / 'NG_keywords.txt'
    ng_filter = NGKeywordFilter(str(ng_keywords_file))

    # 設定を表示
    print(f"\nプラットフォーム: {args.platform}")
    print(f"アカウントID: {args.account_id}")
    print(f"掛け率: {args.markup_rate}")
    print(f"既存スキップ: {'あり' if args.skip_existing else 'なし'}")
    print(f"SP-API使用: {'あり' if args.use_sp_api else 'なし（キャッシュのみ）'}")
    print(f"NGキーワードフィルター: {'有効' if ng_filter.ng_keywords else '無効'}")

    # 確認
    if not args.yes:
        response = input(f"\n{len(asins)}件の商品をマスタDBに追加しますか？ (y/N): ")
        if response.lower() != 'y':
            print("キャンセルしました")
            return
    else:
        print(f"\n{len(asins)}件の商品をマスタDBに追加します（--yesオプション指定）")

    # 商品を追加
    print("\n商品を追加中...")

    success_count = 0
    skip_count = 0
    error_count = 0
    successfully_added_asins = []  # 成功したASINのリスト（キュー追加用）

    # ステップ1: 既存チェックを最初に実行
    print("\nステップ1: 既存商品をチェック中...")
    asins_to_process = []  # 処理が必要なASINのリスト

    for i, asin in enumerate(asins, 1):
        # 既存チェック（同じプラットフォーム・同じアカウントでの重複をチェック）
        if args.skip_existing:
            # プラットフォーム＆アカウント内での重複チェック
            existing_listings = db.get_listings_by_asin(asin)
            platform_account_exists = any(
                listing['platform'] == args.platform and listing['account_id'] == args.account_id
                for listing in existing_listings
            )
            if platform_account_exists:
                print(f"[{i}/{len(asins)}] スキップ: {asin} ({args.platform}/{args.account_id}に既存)")
                skip_count += 1
                continue

        asins_to_process.append(asin)

    print(f"処理対象: {len(asins_to_process)}件（スキップ: {skip_count}件）")

    # ステップ1.2: ブロックリストチェック
    blocklist_blocked_count = 0
    if asins_to_process:
        print(f"\nステップ1.2: ブロックリストチェック中... ({len(asins_to_process)}件)")
        blocklist_manager = BlocklistManager()
        asins_after_blocklist = []

        for i, asin in enumerate(asins_to_process, 1):
            if blocklist_manager.is_blocked(asin):
                block_info = blocklist_manager.get_block_info(asin)
                print(f"[{i}/{len(asins_to_process)}] ブロック: {asin} (ブロックリスト登録済み)")
                print(f"  理由: {block_info.get('reason', '不明')}")
                print(f"  削除日: {block_info.get('deleted_at', '不明')}")
                blocklist_blocked_count += 1
                continue

            asins_after_blocklist.append(asin)

        asins_to_process = asins_after_blocklist
        print(f"ブロックリストチェック完了: {blocklist_blocked_count}件をブロック")
        print(f"処理対象: {len(asins_to_process)}件")

    # ステップ1.5: 禁止商品チェック（オプション）
    blocked_count = 0
    blocked_items = []  # ブロックされたアイテムの詳細情報

    if args.check_prohibited and asins_to_process:
        print(f"\nステップ1.5: 禁止商品チェック中... ({len(asins_to_process)}件)")
        checker = ProhibitedItemChecker()
        asins_after_check = []

        for i, asin in enumerate(asins_to_process, 1):
            # productsテーブルから商品情報を取得
            product_data = db.get_product(asin)

            if product_data:
                # 商品データでチェック
                result = checker.check_product(product_data)

                if result['risk_score'] >= args.prohibited_threshold:
                    print(f"[{i}/{len(asins_to_process)}] ブロック: {asin} (リスクスコア: {result['risk_score']})")
                    print(f"  理由: {', '.join([kw['keyword'] for kw in result['matched_keywords'][:3]])}")

                    # ブロック詳細を保存
                    blocked_items.append({
                        'asin': asin,
                        'title_ja': cached_data.get('title_ja', ''),
                        'category': cached_data.get('category', ''),
                        'brand': cached_data.get('brand', ''),
                        'risk_score': result['risk_score'],
                        'risk_level': result['risk_level'],
                        'recommendation': result['recommendation'],
                        'matched_keywords': result['matched_keywords'],
                        'matched_categories': result['matched_categories'],
                        'details': result['details']
                    })

                    blocked_count += 1
                    continue

            asins_after_check.append(asin)

        asins_to_process = asins_after_check
        print(f"禁止商品チェック完了: {blocked_count}件をブロック")
        print(f"処理対象: {len(asins_to_process)}件")

        # ブロックされたアイテムをファイルに出力
        if blocked_items:
            # logs/ ディレクトリを作成
            logs_dir = project_root / 'logs'
            logs_dir.mkdir(exist_ok=True)

            # タイムスタンプを生成
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

            # JSONファイルに出力
            json_file = logs_dir / f'blocked_items_{timestamp}.json'
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'timestamp': datetime.now().isoformat(),
                    'platform': args.platform,
                    'account_id': args.account_id,
                    'threshold': args.prohibited_threshold,
                    'total_blocked': len(blocked_items),
                    'blocked_items': blocked_items
                }, f, ensure_ascii=False, indent=2)

            # ログファイルに出力（人間可読形式）
            log_file = logs_dir / f'blocked_items_{timestamp}.log'
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write("=" * 80 + "\n")
                f.write("禁止商品チェック - ブロックされたアイテム\n")
                f.write("=" * 80 + "\n")
                f.write(f"日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"プラットフォーム: {args.platform}\n")
                f.write(f"アカウント: {args.account_id}\n")
                f.write(f"ブロック閾値: {args.prohibited_threshold}\n")
                f.write(f"ブロック件数: {len(blocked_items)}\n")
                f.write("=" * 80 + "\n\n")

                for idx, item in enumerate(blocked_items, 1):
                    f.write(f"[{idx}] ASIN: {item['asin']}\n")
                    f.write(f"    タイトル: {item['title_ja'][:60]}...\n" if len(item['title_ja']) > 60 else f"    タイトル: {item['title_ja']}\n")
                    f.write(f"    カテゴリ: {item['category']}\n")
                    f.write(f"    ブランド: {item['brand']}\n")
                    f.write(f"    リスクスコア: {item['risk_score']}\n")
                    f.write(f"    リスクレベル: {item['risk_level']}\n")
                    f.write(f"    推奨アクション: {item['recommendation']}\n")

                    if item['matched_keywords']:
                        f.write(f"    マッチしたキーワード:\n")
                        for kw in item['matched_keywords'][:5]:  # 最大5個表示
                            f.write(f"      - {kw['keyword']} (weight: {kw['weight']}, group: {kw['group']})\n")

                    if item['matched_categories']:
                        f.write(f"    マッチしたカテゴリ:\n")
                        for cat in item['matched_categories']:
                            f.write(f"      - {cat}\n")

                    f.write("\n")

                f.write("=" * 80 + "\n")

            print(f"\nブロックされたアイテムの詳細を出力しました:")
            print(f"  JSON: {json_file}")
            print(f"  LOG:  {log_file}")

    # ステップ2: 価格情報をバッチで取得（SP-API使用時のみ）
    price_data_map = {}  # ASIN -> 価格情報のマップ
    if args.use_sp_api and asins_to_process:
        print(f"\nステップ2: 価格情報をバッチ取得中... ({len(asins_to_process)}件)")
        print(f"  バッチサイズ: 20件/リクエスト")
        print(f"  予想リクエスト数: {(len(asins_to_process) + 19) // 20}回")
        print(f"  予想処理時間: {((len(asins_to_process) + 19) // 20) * 2.5:.1f}秒")

        import time
        batch_start = time.time()
        price_data_map = fetch_prices_batch(asins_to_process, batch_size=20)
        batch_elapsed = time.time() - batch_start

        print(f"  完了: {len(price_data_map)}件の価格情報を取得（{batch_elapsed:.1f}秒）")

        # 比較情報を表示
        individual_estimated = len(asins_to_process) * 2.1
        if batch_elapsed > 0:
            speedup = individual_estimated / batch_elapsed
            print(f"  個別取得との比較: {individual_estimated:.1f}秒 → {batch_elapsed:.1f}秒（{speedup:.1f}倍高速化）")
    else:
        print("\nステップ2: バッチ価格取得をスキップ（キャッシュのみモード）")

    # ステップ3: 商品情報を取得してDBに登録
    print(f"\nステップ3: 商品情報を取得してDBに登録中...")

    for i, asin in enumerate(asins_to_process, 1):
        try:
            # 価格情報を取得（バッチで取得済みの場合はそれを使用）
            price_info = price_data_map.get(asin) if price_data_map else None

            # SP-APIから商品情報を取得
            print(f"[{i}/{len(asins_to_process)}] 取得中: {asin}")
            product_info = fetch_product_info_from_sp_api(
                asin,
                use_sp_api=args.use_sp_api,
                ng_filter=ng_filter,
                price_info=price_info,
                master_db=db
            )

            # 商品情報が取得できなかった場合はスキップ（ダミーデータは登録しない）
            if product_info is None:
                print(f"  [SKIP] {asin}: 商品情報の取得に失敗したためスキップします")
                error_count += 1
                continue

            # productsテーブルに追加（ProductManager使用）
            product_manager.add_product(
                asin=asin,
                title_ja=product_info.get('title_ja'),
                title_en=product_info.get('title_en'),
                description_ja=product_info.get('description_ja'),
                description_en=product_info.get('description_en'),
                category=product_info.get('category'),
                brand=product_info.get('brand'),
                images=product_info.get('images'),
                amazon_price_jpy=product_info.get('amazon_price_jpy'),
                amazon_in_stock=product_info.get('amazon_in_stock')
            )

            # 売価を計算（新しい価格決定モジュールを使用）
            amazon_price = product_info.get('amazon_price_jpy')
            if amazon_price:
                selling_price = price_calculator.calculate_selling_price(
                    amazon_price=amazon_price,
                    platform=args.platform,
                    override_markup_ratio=args.markup_rate  # CLIオプションでのオーバーライドに対応
                )
            else:
                selling_price = None

            # listingsテーブルに追加（ListingManager使用）
            # 統一されたSKU生成（案A: 登録時生成）
            sku = generate_sku(
                platform=args.platform,
                asin=asin,
                timestamp=datetime.now()
            )

            listing_manager.add_listing(
                asin=asin,
                platform=args.platform,
                account_id=args.account_id,
                sku=sku,
                selling_price=selling_price,
                currency='JPY',
                in_stock_quantity=1,
                status='pending',  # 未出品
                visibility='public'
            )

            print(f"  [OK] 追加完了: {product_info.get('title_ja', asin)[:40]}")
            success_count += 1
            successfully_added_asins.append(asin)  # 成功したASINをリストに追加

            # レート制限（Catalog API用）
            # 価格取得はバッチで完了済みのため、商品情報取得のみのレート制限
            if i < len(asins_to_process) and args.use_sp_api:
                time.sleep(0.5)  # Catalog APIのレート制限（5リクエスト/秒 = 0.2秒/リクエスト、安全マージン込み）

        except Exception as e:
            error_count += 1
            print(f"  [ERROR] {asin}: {e}")

            # 最初の5件のエラーはトレースバックを表示
            if error_count <= 5:
                import traceback
                traceback.print_exc()

    # 結果表示
    print("\n" + "=" * 60)
    print("追加完了")
    print("=" * 60)
    print(f"成功: {success_count}件")
    print(f"スキップ: {skip_count}件")
    if blocklist_blocked_count > 0:
        print(f"ブロックリスト拒否: {blocklist_blocked_count}件")
    if blocked_count > 0:
        print(f"禁止商品ブロック: {blocked_count}件")
    print(f"失敗: {error_count}件")
    print(f"合計: {len(asins)}件")
    print("=" * 60)

    # 自動的にキューに追加
    if success_count > 0 and not args.no_auto_queue:
        print("\n" + "=" * 60)
        print("アップロードキューへの自動追加")
        print("=" * 60)

        try:
            from scheduler.queue_manager import UploadQueueManager

            queue_manager = UploadQueueManager()

            print(f"\n{success_count}件の商品をキューに追加中...")
            print(f"プラットフォーム: {args.platform}")
            print(f"アカウント: {args.account_id}")
            print(f"優先度: {args.queue_priority}")

            if args.auto_distribute_accounts:
                print(f"アカウント分散: あり（複数アカウントへ自動分散）")
            else:
                print(f"アカウント分散: なし（{args.account_id}のみ使用）")

            print(f"時間分散: あり（翌日6AM-11PM、1時間あたり最大{args.hourly_limit}件）")

            # ASINを一括でキューに追加（時間分散あり）
            result = queue_manager.add_batch_to_queue(
                asins=successfully_added_asins,
                platform=args.platform,
                account_id=args.account_id if not args.auto_distribute_accounts else None,
                priority=args.queue_priority,
                distribute_time=True,
                auto_distribute_accounts=args.auto_distribute_accounts,
                hourly_limit=args.hourly_limit
            )

            print("\n" + "=" * 60)
            print("キュー追加完了")
            print("=" * 60)
            print(f"成功: {result['success']}件")
            print(f"失敗: {result['failed']}件")
            print(f"開始時刻: {result.get('start_time', '不明')}")
            print(f"終了時刻: {result.get('end_time', '不明')}")

            if result.get('account_distribution'):
                print(f"\nアカウント別割り当て:")
                for account_id, count in result['account_distribution'].items():
                    print(f"  {account_id}: {count}件")

            print("=" * 60)

            print("\n次のステップ:")
            print("デーモンが自動的にアップロードを実行します（6AM-11PM営業時間内）")
            print("進捗確認:")
            print(f"  python scheduler/scripts/check_queue.py --platform {args.platform}")

        except Exception as e:
            print(f"\nエラー: キューへの自動追加に失敗しました - {e}")
            import traceback
            traceback.print_exc()
            print("\n手動でキューに追加してください:")
            print(f"  python scheduler/scripts/add_to_queue.py --platform {args.platform} --distribute --limit {success_count}")

    elif success_count > 0 and args.no_auto_queue:
        print("\n次のステップ:")
        print("1. キューに追加:")
        print(f"   python scheduler/scripts/add_to_queue.py --platform {args.platform} --distribute --limit {success_count}")
        print("2. デーモン起動:")
        print("   python scheduler/daemon.py")

    else:
        print("\n追加された商品がないため、キューへの追加はスキップされました")


if __name__ == '__main__':
    main()
