"""
禁止商品削除スクリプト

CSVファイルまたはASINリストから禁止商品を削除する
- プラットフォームAPIで出品削除
- listingsテーブルから削除
- productsテーブルから削除（デフォルト、--keep-productsで保持可）
- ブロックリストに追加（オプション）

重要な仕様:
- プラットフォーム削除が成功した場合のみDB削除を実行
- プラットフォーム削除が失敗した場合はDB削除をスキップ
- デフォルトでproductsテーブルも削除（再出品防止のため）

使い方:
    # CSVファイルから削除（deleteカラムが"YES"のもの）
    python inventory/scripts/remove_prohibited_items.py \
      --csv prohibited_items_scan_20251207.csv \
      --delete-from-platform \
      --add-to-blocklist \
      --yes

    # productsテーブルを保持したい場合
    python inventory/scripts/remove_prohibited_items.py \
      --csv prohibited_items_scan_20251207.csv \
      --delete-from-platform \
      --keep-products \
      --yes

    # ASINリストから削除
    python inventory/scripts/remove_prohibited_items.py \
      --asins "B076BNB41Q,B0D3PLVQNX" \
      --delete-from-platform \
      --add-to-blocklist

    # DRY RUNモード（確認のみ）
    python inventory/scripts/remove_prohibited_items.py \
      --csv prohibited_items_scan_20251207.csv \
      --dry-run
"""

import sys
import csv
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from inventory.core.master_db import MasterDB


def load_asins_from_csv(csv_path: str, delete_column: str = 'delete') -> tuple:
    """
    CSVファイルから削除対象のASINとホワイトリスト対象を読み込み

    Args:
        csv_path: CSVファイルパス
        delete_column: 削除フラグのカラム名

    Returns:
        tuple: (delete_asins_data, whitelist_asins_data)
            - delete_asins_data: 削除対象のASIN情報のリスト
            - whitelist_asins_data: ホワイトリスト対象のASIN情報のリスト
    """
    delete_asins_data = []
    whitelist_asins_data = []

    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)

        for row in reader:
            asin = row['asin']

            # deleteカラムが "YES" の場合は削除対象
            if row.get(delete_column, '').strip().upper() == 'YES':
                # platform_item_idsをパース（形式: "platform:item_id, platform:item_id, ..."）
                platform_item_ids_raw = row.get('platform_item_ids', '').strip()
                platform_item_ids = {}
                if platform_item_ids_raw:
                    for item in platform_item_ids_raw.split(', '):
                        if ':' in item:
                            platform, item_id = item.split(':', 1)
                            if platform not in platform_item_ids:
                                platform_item_ids[platform] = []
                            platform_item_ids[platform].append(item_id)

                delete_asins_data.append({
                    'asin': asin,
                    'title_ja': row.get('title_ja', ''),
                    'risk_score': int(row.get('risk_score', 0)),
                    'matched_keywords': row.get('matched_keywords', ''),
                    'platforms': row.get('platforms', '').split(', ') if row.get('platforms') else [],
                    'accounts': row.get('accounts', '').split(', ') if row.get('accounts') else [],
                    'platform_item_ids': platform_item_ids
                })

            # whitelist_asinカラムまたはwhitelist_keywordsカラムに値がある場合はホワイトリスト対象
            whitelist_asin_flag = row.get('whitelist_asin', '').strip().upper() == 'YES'
            whitelist_keywords_value = row.get('whitelist_keywords', '').strip()

            if whitelist_asin_flag or whitelist_keywords_value:
                whitelist_asins_data.append({
                    'asin': asin,
                    'title_ja': row.get('title_ja', ''),
                    'whitelist_asin': whitelist_asin_flag,
                    'whitelist_keywords': [kw.strip() for kw in whitelist_keywords_value.split(',') if kw.strip()] if whitelist_keywords_value else []
                })

    return delete_asins_data, whitelist_asins_data


def load_asins_from_list(asins: List[str]) -> List[Dict[str, Any]]:
    """
    ASINリストから削除対象データを作成

    Args:
        asins: ASINのリスト

    Returns:
        list: ASIN情報のリスト
    """
    return [{'asin': asin, 'title_ja': '', 'risk_score': 0, 'matched_keywords': '', 'platforms': [], 'accounts': [], 'platform_item_ids': {}} for asin in asins]


def delete_from_platform(asin: str, platform: str, account_id: str, platform_item_id: Optional[str] = None, dry_run: bool = False) -> bool:
    """
    プラットフォームAPIで商品を削除

    Args:
        asin: ASIN
        platform: プラットフォーム名
        account_id: アカウントID
        platform_item_id: プラットフォーム側のitem_id（オプション）
        dry_run: DRY RUNモード

    Returns:
        bool: 成功した場合True
    """
    if dry_run:
        print(f"  [DRY RUN] プラットフォーム削除: {platform}/{account_id}/{asin}")
        return True

    try:
        if platform == 'base':
            # BASE APIで削除
            from platforms.base.core.api_client import BaseAPIClient
            from platforms.base.accounts.manager import AccountManager

            # アカウント情報取得
            account_manager = AccountManager()
            account = account_manager.get_account(account_id)

            if not account:
                print(f"  [ERROR] アカウントが見つかりません: {account_id}")
                return False

            # APIクライアント初期化
            api_client = BaseAPIClient(
                access_token=account['credentials']['access_token'],
                refresh_token=account['credentials']['refresh_token'],
                account_id=account_id
            )

            # platform_item_idが指定されていない場合はlistingsテーブルから取得
            if not platform_item_id:
                db = MasterDB()
                with db.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT platform_item_id
                        FROM listings
                        WHERE asin = ? AND platform = ? AND account_id = ?
                    """, (asin, platform, account_id))
                    result = cursor.fetchone()

                    if not result or not result['platform_item_id']:
                        print(f"  [WARN] platform_item_idが見つかりません: {asin}")
                        return False

                    platform_item_id = result['platform_item_id']

            # BASE APIで削除
            success = api_client.delete_item(platform_item_id)

            if success:
                print(f"  [SUCCESS] BASE APIで削除完了: {platform_item_id}")
                return True
            else:
                print(f"  [ERROR] BASE API削除失敗: {platform_item_id}")
                return False

        elif platform == 'ebay':
            # eBay APIで削除（未実装）
            print(f"  [WARN] eBay削除は未実装です: {asin}")
            return False

        elif platform == 'yahoo':
            # Yahoo!オークションAPIで削除（未実装）
            print(f"  [WARN] Yahoo!削除は未実装です: {asin}")
            return False

        elif platform == 'mercari':
            # メルカリAPIで削除（未実装）
            print(f"  [WARN] メルカリ削除は未実装です: {asin}")
            return False

        else:
            print(f"  [ERROR] 未知のプラットフォーム: {platform}")
            return False

    except Exception as e:
        print(f"  [ERROR] プラットフォーム削除エラー ({platform}/{account_id}/{asin}): {e}")
        import traceback
        traceback.print_exc()
        return False


def delete_from_db(
    asin: str,
    db: MasterDB,
    delete_from_listings: bool = True,
    delete_from_products: bool = False,
    dry_run: bool = False
) -> Dict[str, bool]:
    """
    データベースから商品を削除

    Args:
        asin: ASIN
        db: MasterDB instance
        delete_from_listings: listingsテーブルから削除
        delete_from_products: productsテーブルから削除
        dry_run: DRY RUNモード

    Returns:
        dict: {'listings': bool, 'products': bool}
    """
    result = {'listings': False, 'products': False}

    if dry_run:
        print(f"  [DRY RUN] DB削除: listings={delete_from_listings}, products={delete_from_products}")
        return {'listings': True, 'products': True}

    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()

            # listingsテーブルから削除
            if delete_from_listings:
                cursor.execute("DELETE FROM listings WHERE asin = ?", (asin,))
                deleted_count = cursor.rowcount
                result['listings'] = deleted_count > 0
                if deleted_count > 0:
                    print(f"  [SUCCESS] listings削除完了: {deleted_count}件")

            # productsテーブルから削除
            if delete_from_products:
                cursor.execute("DELETE FROM products WHERE asin = ?", (asin,))
                deleted_count = cursor.rowcount
                result['products'] = deleted_count > 0
                if deleted_count > 0:
                    print(f"  [SUCCESS] products削除完了")

    except Exception as e:
        print(f"  [ERROR] DB削除エラー ({asin}): {e}")
        import traceback
        traceback.print_exc()

    return result


def add_to_blocklist(
    asin: str,
    reason: str,
    risk_score: int,
    platforms: List[str],
    dry_run: bool = False
):
    """
    ブロックリストに追加

    Args:
        asin: ASIN
        reason: ブロック理由
        risk_score: リスクスコア
        platforms: プラットフォームリスト
        dry_run: DRY RUNモード
    """
    blocklist_path = project_root / 'config' / 'blocked_asins.json'

    if dry_run:
        print(f"  [DRY RUN] ブロックリスト追加: {asin}")
        return

    try:
        # 既存のブロックリストを読み込み
        if blocklist_path.exists():
            with open(blocklist_path, 'r', encoding='utf-8') as f:
                blocklist = json.load(f)
        else:
            blocklist = {
                "version": "1.0",
                "last_updated": datetime.now().isoformat(),
                "blocked_asins": {}
            }

        # ブロックリストに追加
        blocklist['blocked_asins'][asin] = {
            "reason": reason,
            "risk_score": risk_score,
            "deleted_at": datetime.now().isoformat(),
            "deleted_by": "manual",
            "platforms": platforms
        }

        blocklist['last_updated'] = datetime.now().isoformat()

        # 保存
        with open(blocklist_path, 'w', encoding='utf-8') as f:
            json.dump(blocklist, f, ensure_ascii=False, indent=2)

        print(f"  [SUCCESS] ブロックリスト追加完了: {blocklist_path}")

    except Exception as e:
        print(f"  [ERROR] ブロックリスト追加エラー ({asin}): {e}")
        import traceback
        traceback.print_exc()


def add_to_whitelist(
    asin: str = None,
    keywords: List[str] = None,
    dry_run: bool = False
):
    """
    ホワイトリストに追加

    Args:
        asin: ASINホワイトリストに追加するASIN（オプション）
        keywords: キーワードホワイトリストに追加するキーワードリスト（オプション）
        dry_run: DRY RUNモード
    """
    config_path = project_root / 'config' / 'prohibited_items.json'

    if dry_run:
        if asin:
            print(f"  [DRY RUN] ASINホワイトリスト追加: {asin}")
        if keywords:
            print(f"  [DRY RUN] キーワードホワイトリスト追加: {', '.join(keywords)}")
        return

    try:
        # 既存の設定を読み込み
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        # ASINホワイトリストに追加
        if asin:
            asin_whitelist = config['keywords'].get('asin_whitelist', [])
            if asin not in asin_whitelist:
                asin_whitelist.append(asin)
                config['keywords']['asin_whitelist'] = asin_whitelist
                print(f"  [SUCCESS] ASINホワイトリスト追加: {asin}")
            else:
                print(f"  [INFO] ASINホワイトリスト登録済み: {asin}")

        # キーワードホワイトリストに追加（customカテゴリに追加）
        if keywords:
            whitelist = config['keywords'].get('whitelist', {})
            custom_whitelist = whitelist.get('custom', [])

            added_keywords = []
            for keyword in keywords:
                if keyword not in custom_whitelist:
                    custom_whitelist.append(keyword)
                    added_keywords.append(keyword)

            if added_keywords:
                whitelist['custom'] = custom_whitelist
                config['keywords']['whitelist'] = whitelist
                print(f"  [SUCCESS] キーワードホワイトリスト追加: {', '.join(added_keywords)}")
            else:
                print(f"  [INFO] キーワードホワイトリスト登録済み")

        # 保存
        config['last_updated'] = datetime.now().strftime('%Y-%m-%d')
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

    except Exception as e:
        print(f"  [ERROR] ホワイトリスト追加エラー: {e}")
        import traceback
        traceback.print_exc()


def remove_prohibited_items(
    asins_data: List[Dict[str, Any]],
    db: MasterDB,
    delete_from_platform_flag: bool = False,
    delete_from_products_flag: bool = False,
    add_to_blocklist_flag: bool = False,
    dry_run: bool = False
) -> Dict[str, int]:
    """
    禁止商品を削除

    Args:
        asins_data: ASIN情報のリスト
        db: MasterDB instance
        delete_from_platform_flag: プラットフォームAPIで削除
        delete_from_products_flag: productsテーブルから削除
        add_to_blocklist_flag: ブロックリストに追加
        dry_run: DRY RUNモード

    Returns:
        dict: 統計情報
    """
    stats = {
        'total': len(asins_data),
        'platform_deleted': 0,
        'listings_deleted': 0,
        'products_deleted': 0,
        'blocklist_added': 0,
        'errors': 0
    }

    for i, asin_data in enumerate(asins_data, 1):
        asin = asin_data['asin']
        title = asin_data.get('title_ja', '')
        risk_score = asin_data.get('risk_score', 0)
        matched_keywords = asin_data.get('matched_keywords', '')
        csv_platform_item_ids = asin_data.get('platform_item_ids', {})

        print(f"\n[{i}/{len(asins_data)}] 処理中: {asin}")
        if title:
            print(f"  タイトル: {title[:60]}")
        if matched_keywords:
            print(f"  キーワード: {matched_keywords[:60]}")

        try:
            # 出品状況を確認
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT platform, account_id, status, platform_item_id
                    FROM listings
                    WHERE asin = ?
                """, (asin,))
                listings = cursor.fetchall()

            # プラットフォーム削除の成功フラグ
            platform_deletion_success = True
            platform_deletion_attempted = False

            # CSVからplatform_item_idsが指定されている場合の削除処理
            if csv_platform_item_ids and delete_from_platform_flag:
                print(f"  [INFO] CSVのplatform_item_idsを使用して削除")
                platform_deletion_attempted = True
                platform_deletion_success = False  # 一旦Falseにして、成功したらTrueに

                for platform, item_ids in csv_platform_item_ids.items():
                    # アカウントIDを取得（listingsから、または最初のアカウントを使用）
                    account_id = None
                    if listings:
                        for listing in listings:
                            if listing['platform'] == platform:
                                account_id = listing['account_id']
                                break

                    # アカウントIDが見つからない場合はスキップ
                    if not account_id:
                        print(f"  [WARN] アカウントIDが見つかりません（platform={platform}）")
                        continue

                    # 各item_idを削除
                    all_items_deleted = True
                    for item_id in item_ids:
                        success = delete_from_platform(asin, platform, account_id, platform_item_id=item_id, dry_run=dry_run)
                        if success:
                            stats['platform_deleted'] += 1
                        else:
                            all_items_deleted = False

                    # すべてのitem_idの削除に成功した場合のみTrueに
                    if all_items_deleted:
                        platform_deletion_success = True

            # listingsテーブルから取得した情報での削除処理
            elif listings:
                print(f"  [INFO] 出品状況: {len(listings)}件")

                # プラットフォームから削除
                if delete_from_platform_flag:
                    platform_deletion_attempted = True
                    platform_deletion_success = True  # 一旦Trueにして、失敗したらFalseに

                    for listing in listings:
                        platform = listing['platform']
                        account_id = listing['account_id']
                        status = listing['status']
                        platform_item_id = listing['platform_item_id']

                        # listedの場合のみプラットフォームAPIで削除
                        if status == 'listed':
                            success = delete_from_platform(asin, platform, account_id, platform_item_id=platform_item_id, dry_run=dry_run)
                            if success:
                                stats['platform_deleted'] += 1
                            else:
                                platform_deletion_success = False
                        else:
                            print(f"  [INFO] スキップ: {platform}/{account_id}（status={status}）")
            else:
                print(f"  [INFO] 出品なし（listingsに存在しません）")

            # プラットフォーム削除が試みられた場合、成功を確認してからDB削除を実行
            if delete_from_platform_flag and platform_deletion_attempted:
                if not platform_deletion_success:
                    print(f"  [ERROR] プラットフォーム削除が失敗したため、DB削除をスキップします")
                    stats['errors'] += 1
                    continue

                print(f"  [SUCCESS] プラットフォーム削除が完了しました。DB削除を実行します")

            # DBから削除（listingsとproductsの両方）
            db_result = delete_from_db(
                asin=asin,
                db=db,
                delete_from_listings=True,
                delete_from_products=delete_from_products_flag,
                dry_run=dry_run
            )

            if db_result['listings']:
                stats['listings_deleted'] += 1
            if db_result['products']:
                stats['products_deleted'] += 1

            # ブロックリストに追加
            if add_to_blocklist_flag:
                platforms = list(set([l['platform'] for l in listings])) if listings else []
                add_to_blocklist(
                    asin=asin,
                    reason=matched_keywords or "禁止商品",
                    risk_score=risk_score,
                    platforms=platforms,
                    dry_run=dry_run
                )
                stats['blocklist_added'] += 1

        except Exception as e:
            print(f"  [ERROR] 処理エラー: {e}")
            stats['errors'] += 1
            import traceback
            traceback.print_exc()

    return stats


def main():
    parser = argparse.ArgumentParser(
        description='禁止商品削除スクリプト'
    )

    # 入力ソース
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        '--csv',
        type=str,
        help='CSVファイルパス（deleteカラムが"YES"のもの）'
    )
    input_group.add_argument(
        '--asins',
        type=str,
        help='ASINリスト（カンマ区切り）'
    )
    input_group.add_argument(
        '--asin-file',
        type=str,
        help='ASINリストファイル（改行区切り）'
    )

    # 削除オプション
    parser.add_argument(
        '--delete-from-platform',
        action='store_true',
        help='プラットフォームAPIで削除（listed商品のみ）'
    )
    parser.add_argument(
        '--keep-products',
        action='store_true',
        help='productsテーブルは保持（デフォルト: listingsとproductsの両方を削除）'
    )
    parser.add_argument(
        '--delete-products',
        action='store_true',
        help='【非推奨】--keep-productsと競合するため使用しないでください'
    )
    parser.add_argument(
        '--add-to-blocklist',
        action='store_true',
        help='ブロックリストに追加（今後の新規追加を防止）'
    )
    parser.add_argument(
        '--add-to-whitelist',
        action='store_true',
        help='ホワイトリストに追加（CSVのwhitelist_asin/whitelist_keywordsカラムに基づく）'
    )

    # 実行モード
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='DRY RUNモード（確認のみ、実際の削除は行わない）'
    )
    parser.add_argument(
        '--yes', '-y',
        action='store_true',
        help='確認をスキップして自動実行'
    )

    args = parser.parse_args()

    print("=" * 70)
    print("禁止商品削除スクリプト")
    print("=" * 70)

    # ASINデータを読み込み
    whitelist_asins_data = []

    if args.csv:
        print(f"\n[INFO] CSVファイルから読み込み: {args.csv}")
        asins_data, whitelist_asins_data = load_asins_from_csv(args.csv)
    elif args.asins:
        print(f"\n[INFO] ASINリストから読み込み")
        asins_data = load_asins_from_list(args.asins.split(','))
    elif args.asin_file:
        print(f"\n[INFO] ASINファイルから読み込み: {args.asin_file}")
        with open(args.asin_file, 'r', encoding='utf-8') as f:
            asins = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        asins_data = load_asins_from_list(asins)
    else:
        print("[ERROR] 入力ソースを指定してください")
        return

    if not asins_data and not whitelist_asins_data:
        print("[INFO] 処理対象のASINがありません")
        return

    if asins_data:
        print(f"[INFO] 削除対象: {len(asins_data)}件")
    if whitelist_asins_data:
        print(f"[INFO] ホワイトリスト追加対象: {len(whitelist_asins_data)}件")

    # 削除オプションの表示
    print("\n処理オプション:")
    if asins_data:
        print(f"  - プラットフォーム削除: {'あり' if args.delete_from_platform else 'なし'}")
        print(f"  - productsテーブル削除: {'なし（--keep-products指定）' if args.keep_products else 'あり（デフォルト）'}")
        print(f"  - ブロックリスト追加: {'あり' if args.add_to_blocklist else 'なし'}")
    if whitelist_asins_data:
        print(f"  - ホワイトリスト追加: {'あり' if args.add_to_whitelist else 'なし'}")
    print(f"  - 実行モード: {'DRY RUN（確認のみ）' if args.dry_run else '本番実行'}")

    # 確認
    if not args.yes and not args.dry_run:
        print("\n" + "=" * 70)
        print("⚠️  警告: この操作は取り消せません")
        print("=" * 70)
        if asins_data:
            response = input(f"\n{len(asins_data)}件の商品を削除しますか？ (yes/NO): ")
        else:
            response = input(f"\n{len(whitelist_asins_data)}件のホワイトリスト登録を実行しますか？ (yes/NO): ")
        if response.lower() != 'yes':
            print("キャンセルしました")
            return

    # MasterDB初期化
    db = MasterDB()

    # 削除実行
    stats = {}
    if asins_data:
        # デフォルトでproductsも削除（--keep-productsが指定されている場合のみ保持）
        should_delete_products = not args.keep_products

        stats = remove_prohibited_items(
            asins_data=asins_data,
            db=db,
            delete_from_platform_flag=args.delete_from_platform,
            delete_from_products_flag=should_delete_products,
            add_to_blocklist_flag=args.add_to_blocklist,
            dry_run=args.dry_run
        )

    # ホワイトリスト追加実行
    whitelist_stats = {'asin_whitelist_added': 0, 'keyword_whitelist_added': 0}
    if whitelist_asins_data and args.add_to_whitelist:
        print("\n" + "=" * 70)
        print("ホワイトリスト追加処理")
        print("=" * 70)

        for i, whitelist_data in enumerate(whitelist_asins_data, 1):
            asin = whitelist_data['asin']
            title = whitelist_data.get('title_ja', '')
            whitelist_asin_flag = whitelist_data.get('whitelist_asin', False)
            whitelist_keywords = whitelist_data.get('whitelist_keywords', [])

            print(f"\n[{i}/{len(whitelist_asins_data)}] 処理中: {asin}")
            if title:
                print(f"  タイトル: {title[:60]}")

            # ホワイトリストに追加
            if whitelist_asin_flag:
                add_to_whitelist(asin=asin, dry_run=args.dry_run)
                whitelist_stats['asin_whitelist_added'] += 1

            if whitelist_keywords:
                add_to_whitelist(keywords=whitelist_keywords, dry_run=args.dry_run)
                whitelist_stats['keyword_whitelist_added'] += len(whitelist_keywords)

    # 結果表示
    print("\n" + "=" * 70)
    print("処理完了サマリー")
    print("=" * 70)

    if stats:
        print(f"処理対象:               {stats['total']:>6}件")
        print(f"プラットフォーム削除:   {stats['platform_deleted']:>6}件")
        print(f"listings削除:           {stats['listings_deleted']:>6}件")
        print(f"products削除:           {stats['products_deleted']:>6}件")
        print(f"ブロックリスト追加:     {stats['blocklist_added']:>6}件")
        print(f"エラー:                 {stats['errors']:>6}件")

    if whitelist_stats['asin_whitelist_added'] > 0 or whitelist_stats['keyword_whitelist_added'] > 0:
        print(f"ASINホワイトリスト追加: {whitelist_stats['asin_whitelist_added']:>6}件")
        print(f"キーワードホワイトリスト追加: {whitelist_stats['keyword_whitelist_added']:>6}件")

    print("=" * 70)

    if args.dry_run:
        print("\n[DRY RUN完了] 実際の削除は行われていません")
        print("\n本番実行する場合:")
        if args.csv:
            cmd_parts = [f"python inventory/scripts/remove_prohibited_items.py --csv {args.csv}"]
            if args.delete_from_platform:
                cmd_parts.append("--delete-from-platform")
            if args.keep_products:
                cmd_parts.append("--keep-products")
            if args.add_to_blocklist:
                cmd_parts.append("--add-to-blocklist")
            if args.add_to_whitelist:
                cmd_parts.append("--add-to-whitelist")
            cmd_parts.append("--yes")
            print(f"  {' '.join(cmd_parts)}")
    else:
        print("\n[実行完了] 禁止商品の削除が完了しました")


if __name__ == '__main__':
    main()
