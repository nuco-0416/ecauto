"""
既存DB禁止商品スキャナー

マスタDBに登録済みの商品を禁止商品チェッカーでスキャンし、
リスクの高い商品をレポート出力する

使い方:
    # 全商品をスキャン（リスクスコア50以上のみ出力）
    python inventory/scripts/scan_prohibited_items.py

    # 高リスク商品のみスキャン（スコア80以上）
    python inventory/scripts/scan_prohibited_items.py --risk-level high

    # 特定プラットフォーム・アカウントのみスキャン
    python inventory/scripts/scan_prohibited_items.py --platform base --account-id base_account_2
"""

import sys
import csv
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from inventory.core.master_db import MasterDB
from inventory.core.prohibited_item_checker import ProhibitedItemChecker


def scan_products(
    db: MasterDB,
    checker: ProhibitedItemChecker,
    risk_level: str = 'all',
    threshold: int = 50,
    platform: Optional[str] = None,
    account_id: Optional[str] = None,
    limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    商品をスキャンして禁止商品をチェック

    Args:
        db: MasterDB instance
        checker: ProhibitedItemChecker instance
        risk_level: リスクレベルフィルタ ('all', 'high', 'medium', 'low')
        threshold: リスクスコア閾値（この値以上の商品のみ返す）
        platform: プラットフォームフィルタ（オプション）
        account_id: アカウントIDフィルタ（オプション）
        limit: 処理する最大件数（オプション）

    Returns:
        list: スキャン結果のリスト
    """
    results = []

    # リスクレベルに応じた閾値
    risk_thresholds = {
        'high': 80,
        'medium': 50,
        'low': 30,
        'all': threshold
    }

    min_score = risk_thresholds.get(risk_level, threshold)

    # productsテーブルから全商品を取得
    with db.get_connection() as conn:
        cursor = conn.cursor()

        # クエリ構築
        query = """
            SELECT DISTINCT
                p.asin,
                p.title_ja,
                p.title_en,
                p.description_ja,
                p.description_en,
                p.category,
                p.brand,
                p.images,
                p.amazon_price_jpy
            FROM products p
        """

        # プラットフォーム/アカウントフィルタがある場合はlistingsと結合
        if platform or account_id:
            query += " LEFT JOIN listings l ON p.asin = l.asin"
            conditions = []
            if platform:
                conditions.append(f"l.platform = '{platform}'")
            if account_id:
                conditions.append(f"l.account_id = '{account_id}'")
            if conditions:
                query += " WHERE " + " AND ".join(conditions)

        if limit:
            query += f" LIMIT {limit}"

        cursor.execute(query)
        products = cursor.fetchall()

        print(f"\n[INFO] スキャン対象: {len(products)}件の商品")
        print(f"[INFO] 最小リスクスコア: {min_score}")
        print()

        # 各商品をチェック
        for i, product in enumerate(products, 1):
            asin = product['asin']

            # 進捗表示
            if i % 100 == 0:
                print(f"  処理中... {i}/{len(products)} ({i/len(products)*100:.1f}%)")

            # 禁止商品チェック
            check_result = checker.check_product({
                'asin': asin,
                'title_ja': product['title_ja'] or '',
                'title_en': product['title_en'] or '',
                'description_ja': product['description_ja'] or '',
                'description_en': product['description_en'] or '',
                'category': product['category'] or '',
                'brand': product['brand'] or '',
                'images': product['images'] or []
            })

            # 閾値以上の場合のみ結果に追加
            if check_result['risk_score'] >= min_score:
                # 出品状況を取得
                cursor.execute("""
                    SELECT
                        platform,
                        account_id,
                        status,
                        visibility,
                        platform_item_id,
                        sku
                    FROM listings
                    WHERE asin = ?
                """, (asin,))
                listings = cursor.fetchall()

                # 出品状況のサマリー
                listing_statuses = []
                platforms = []
                accounts = []
                platform_item_ids = []

                for listing in listings:
                    listing_statuses.append(listing['status'])
                    platforms.append(listing['platform'])
                    accounts.append(listing['account_id'])
                    if listing['platform_item_id']:
                        platform_item_ids.append(f"{listing['platform']}:{listing['platform_item_id']}")

                # 結果に追加
                results.append({
                    'asin': asin,
                    'title_ja': product['title_ja'] or '',
                    'description_ja': product['description_ja'] or '',
                    'description_en': product['description_en'] or '',
                    'category': product['category'] or '',
                    'brand': product['brand'] or '',
                    'amazon_price_jpy': product['amazon_price_jpy'],
                    'risk_score': check_result['risk_score'],
                    'risk_level': check_result['risk_level'],
                    'recommendation': check_result['recommendation'],
                    'matched_keywords': ', '.join([kw['keyword'] for kw in check_result['matched_keywords']]),
                    'matched_categories': ', '.join(check_result['matched_categories']),
                    'is_whitelisted': check_result['is_whitelisted'],
                    'listing_count': len(listings),
                    'listing_statuses': ', '.join(set(listing_statuses)),
                    'platforms': ', '.join(set(platforms)),
                    'accounts': ', '.join(set(accounts)),
                    'platform_item_ids': ', '.join(platform_item_ids),
                    'details': check_result['details']
                })

    print(f"\n[INFO] スキャン完了: {len(results)}件の問題商品候補を検出")
    return results


def export_to_csv(results: List[Dict[str, Any]], output_path: str):
    """
    結果をCSVファイルに出力

    Args:
        results: スキャン結果
        output_path: 出力ファイルパス
    """
    if not results:
        print("[WARN] 出力する結果がありません")
        return

    # CSVヘッダー
    fieldnames = [
        'asin',
        'title_ja',
        'description_ja',
        'description_en',
        'category',
        'brand',
        'amazon_price_jpy',
        'risk_score',
        'risk_level',
        'recommendation',
        'matched_keywords',
        'matched_categories',
        'is_whitelisted',
        'listing_count',
        'listing_statuses',
        'platforms',
        'accounts',
        'platform_item_ids',  # プラットフォーム削除用のID（形式: platform:item_id）
        'delete',  # 目視確認用の空カラム（YESで削除対象）
        'whitelist_asin',  # YESでASINホワイトリストに追加
        'whitelist_keywords'  # カンマ区切りでキーワードホワイトリストに追加
    ]

    with open(output_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for result in results:
            # delete, whitelist_asin, whitelist_keywordsカラムを追加（空）
            row = {k: result.get(k, '') for k in fieldnames if k not in ['delete', 'whitelist_asin', 'whitelist_keywords']}
            row['delete'] = ''  # 目視確認で "YES" を入力する用
            row['whitelist_asin'] = ''  # YESでASINホワイトリストに追加
            row['whitelist_keywords'] = ''  # カンマ区切りでキーワード追加
            writer.writerow(row)

    print(f"\n[SUCCESS] CSVファイルを出力しました: {output_path}")
    print(f"[INFO] Excel等で開いて、以下のカラムを編集してください:")
    print(f"  - 'delete': 削除対象のASINに 'YES' を入力")
    print(f"  - 'whitelist_asin': ホワイトリスト登録するASINに 'YES' を入力")
    print(f"  - 'whitelist_keywords': ホワイトリスト登録するキーワードをカンマ区切りで入力")


def main():
    parser = argparse.ArgumentParser(
        description='既存DB禁止商品スキャナー'
    )
    parser.add_argument(
        '--risk-level',
        type=str,
        choices=['all', 'high', 'medium', 'low'],
        default='all',
        help='リスクレベルフィルタ (high: 80+, medium: 50+, low: 30+, all: 閾値指定)'
    )
    parser.add_argument(
        '--threshold',
        type=int,
        default=50,
        help='リスクスコア閾値（デフォルト: 50）'
    )
    parser.add_argument(
        '--platform',
        type=str,
        help='プラットフォームフィルタ（例: base）'
    )
    parser.add_argument(
        '--account-id',
        type=str,
        help='アカウントIDフィルタ（例: base_account_2）'
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='処理する最大件数（テスト用）'
    )
    parser.add_argument(
        '--output',
        type=str,
        help='出力ファイル名（デフォルト: prohibited_items_scan_YYYYMMDD_HHMMSS.csv）'
    )

    args = parser.parse_args()

    print("=" * 70)
    print("既存DB禁止商品スキャナー")
    print("=" * 70)

    # MasterDB初期化
    db = MasterDB()

    # ProhibitedItemChecker初期化
    checker = ProhibitedItemChecker()

    # スキャン実行
    results = scan_products(
        db=db,
        checker=checker,
        risk_level=args.risk_level,
        threshold=args.threshold,
        platform=args.platform,
        account_id=args.account_id,
        limit=args.limit
    )

    # 結果サマリー
    print("\n" + "=" * 70)
    print("スキャン結果サマリー")
    print("=" * 70)

    if results:
        # リスクレベル別の集計
        high_risk = sum(1 for r in results if r['risk_score'] >= 80)
        medium_risk = sum(1 for r in results if 50 <= r['risk_score'] < 80)
        low_risk = sum(1 for r in results if r['risk_score'] < 50)

        print(f"検出件数: {len(results)}件")
        print(f"  - 高リスク (80+):  {high_risk}件")
        print(f"  - 中リスク (50-79): {medium_risk}件")
        print(f"  - 低リスク (30-49): {low_risk}件")

        # 出品状況別の集計
        listed_count = sum(1 for r in results if 'listed' in r['listing_statuses'])
        pending_count = sum(1 for r in results if 'pending' in r['listing_statuses'] and 'listed' not in r['listing_statuses'])
        no_listing = sum(1 for r in results if r['listing_count'] == 0)

        print(f"\n出品状況:")
        print(f"  - 出品済み (listed):    {listed_count}件")
        print(f"  - 未出品 (pending):      {pending_count}件")
        print(f"  - 出品なし:              {no_listing}件")

        # トップ10表示
        print(f"\n高リスク商品トップ10:")
        sorted_results = sorted(results, key=lambda x: x['risk_score'], reverse=True)
        for i, result in enumerate(sorted_results[:10], 1):
            print(f"  {i}. [{result['risk_score']:3d}] {result['asin']} - {result['title_ja'][:50]}")
            if result['matched_keywords']:
                print(f"      キーワード: {result['matched_keywords'][:80]}")

    else:
        print("問題商品は検出されませんでした")

    print("=" * 70)

    # CSV出力
    if results:
        if not args.output:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_path = project_root / 'logs' / f'prohibited_items_scan_{timestamp}.csv'
        else:
            output_path = Path(args.output)

        # ディレクトリを作成
        output_path.parent.mkdir(parents=True, exist_ok=True)

        export_to_csv(results, str(output_path))

        print("\n次のステップ:")
        print(f"1. CSVファイルを開く: {output_path}")
        print("2. 削除対象のASINの 'delete' カラムに 'YES' を入力")
        print("3. 削除を実行:")
        print(f"   python inventory/scripts/remove_prohibited_items.py --csv {output_path} --delete-from-platform --add-to-blocklist --yes")


if __name__ == '__main__':
    main()
