"""
マスターDB NGキーワードクリーンアップスクリプト

productsテーブル内のタイトル・説明文からNGキーワードを削除する

# スキャンのみ（対象確認）
/home/nuc_o/github/ecauto/venv/bin/python shared/utils/ng_keywords_cleanup_master_db.py --scan-only

# dry-run（変更内容確認）
/home/nuc_o/github/ecauto/venv/bin/python shared/utils/ng_keywords_cleanup_master_db.py --dry-run

# 実行
/home/nuc_o/github/ecauto/venv/bin/python shared/utils/ng_keywords_cleanup_master_db.py --execute

"""

import sys
import argparse
from pathlib import Path
from datetime import datetime

# プロジェクトルートをパスに追加（shared/utils/ から3階層上）
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from inventory.core.master_db import MasterDB
from common.ng_keyword_filter import NGKeywordFilter


def find_products_with_ng_keywords(db: MasterDB, ng_filter: NGKeywordFilter) -> list:
    """
    NGキーワードを含む商品を検索

    Returns:
        list: NGキーワードを含む商品のリスト
    """
    products_with_ng = []

    # 検索対象のパターン
    search_patterns = [
        '【.co.jp限定】',
        '【.co.jp 限定】',
        '【Amazon.co.jp限定】',
        '【Amazon.co.jp 限定】',
        'Amazon',
        'アマゾン',
        'by Amazon',
        'プライム会員'
    ]

    with db.get_connection() as conn:
        cursor = conn.cursor()

        # 全商品を取得してチェック
        cursor.execute('''
            SELECT asin, title_ja, title_en, description_ja, description_en
            FROM products
        ''')

        for row in cursor.fetchall():
            product = dict(row)
            asin = product['asin']

            # 各フィールドをチェック
            fields_with_ng = []
            for field in ['title_ja', 'title_en', 'description_ja', 'description_en']:
                value = product.get(field)
                if value:
                    for pattern in search_patterns:
                        if pattern.lower() in value.lower():
                            fields_with_ng.append({
                                'field': field,
                                'pattern': pattern,
                                'value': value[:100] + '...' if len(value) > 100 else value
                            })
                            break

            if fields_with_ng:
                products_with_ng.append({
                    'asin': asin,
                    'fields': fields_with_ng
                })

    return products_with_ng


def cleanup_products(db: MasterDB, ng_filter: NGKeywordFilter, dry_run: bool = True) -> dict:
    """
    商品データからNGキーワードを削除

    Args:
        db: MasterDBインスタンス
        ng_filter: NGKeywordFilterインスタンス
        dry_run: Trueの場合は実際には更新しない

    Returns:
        dict: 処理結果の統計
    """
    stats = {
        'scanned': 0,
        'found': 0,
        'updated': 0,
        'errors': 0,
        'details': []
    }

    with db.get_connection() as conn:
        cursor = conn.cursor()

        # 全商品を取得
        cursor.execute('''
            SELECT asin, title_ja, title_en, description_ja, description_en
            FROM products
        ''')

        products = [dict(row) for row in cursor.fetchall()]
        stats['scanned'] = len(products)

        for product in products:
            asin = product['asin']

            # フィルターを適用
            original_data = {
                'title_ja': product.get('title_ja'),
                'title_en': product.get('title_en'),
                'description_ja': product.get('description_ja'),
                'description_en': product.get('description_en')
            }

            cleaned_data = {}
            any_changed = False

            for field in ['title_ja', 'title_en', 'description_ja', 'description_en']:
                original = original_data.get(field)
                if original:
                    if 'title' in field:
                        cleaned = ng_filter.filter_title(original)
                    else:
                        cleaned = ng_filter.filter_description(original)

                    cleaned_data[field] = cleaned
                    if original != cleaned:
                        any_changed = True
                else:
                    cleaned_data[field] = original

            if any_changed:
                stats['found'] += 1

                detail = {
                    'asin': asin,
                    'changes': []
                }

                for field in ['title_ja', 'title_en', 'description_ja', 'description_en']:
                    if original_data.get(field) != cleaned_data.get(field):
                        original_preview = original_data[field][:80] + '...' if original_data[field] and len(original_data[field]) > 80 else original_data.get(field)
                        cleaned_preview = cleaned_data[field][:80] + '...' if cleaned_data[field] and len(cleaned_data[field]) > 80 else cleaned_data.get(field)
                        detail['changes'].append({
                            'field': field,
                            'original': original_preview,
                            'cleaned': cleaned_preview
                        })

                stats['details'].append(detail)

                if not dry_run:
                    try:
                        now = datetime.now().isoformat()
                        cursor.execute('''
                            UPDATE products
                            SET title_ja = ?,
                                title_en = ?,
                                description_ja = ?,
                                description_en = ?,
                                updated_at = ?
                            WHERE asin = ?
                        ''', (
                            cleaned_data['title_ja'],
                            cleaned_data['title_en'],
                            cleaned_data['description_ja'],
                            cleaned_data['description_en'],
                            now,
                            asin
                        ))
                        stats['updated'] += 1
                    except Exception as e:
                        stats['errors'] += 1
                        print(f"  [ERROR] {asin}: {e}")

    return stats


def main():
    parser = argparse.ArgumentParser(description='マスターDB NGキーワードクリーンアップ')
    parser.add_argument('--dry-run', action='store_true', default=True,
                       help='実際には更新せず、変更内容のみ表示（デフォルト）')
    parser.add_argument('--execute', action='store_true',
                       help='実際に更新を実行')
    parser.add_argument('--scan-only', action='store_true',
                       help='NGキーワードを含む商品のスキャンのみ')
    parser.add_argument('--max-display', type=int, default=20,
                       help='表示する詳細の最大件数（デフォルト: 20）')

    args = parser.parse_args()

    # dry_runフラグの決定
    dry_run = not args.execute

    print("=" * 70)
    print("マスターDB NGキーワードクリーンアップ")
    print("=" * 70)
    print(f"実行モード: {'DRY RUN（実際には更新しません）' if dry_run else '実行モード（DBを更新します）'}")
    print()

    # 初期化
    db = MasterDB()
    ng_file = project_root / 'config' / 'ng_keywords.json'
    ng_filter = NGKeywordFilter(str(ng_file))

    if args.scan_only:
        # スキャンのみ
        print("NGキーワードを含む商品をスキャン中...")
        products_with_ng = find_products_with_ng_keywords(db, ng_filter)

        print(f"\n検出件数: {len(products_with_ng)}件")

        for i, product in enumerate(products_with_ng[:args.max_display]):
            print(f"\n[{i+1}] ASIN: {product['asin']}")
            for field_info in product['fields']:
                print(f"    {field_info['field']}: {field_info['pattern']} を含む")
                print(f"    値: {field_info['value']}")

        if len(products_with_ng) > args.max_display:
            print(f"\n... 他 {len(products_with_ng) - args.max_display}件")

    else:
        # クリーンアップ実行
        print("クリーンアップ処理を実行中...")
        stats = cleanup_products(db, ng_filter, dry_run=dry_run)

        print(f"\n{'='*70}")
        print("処理結果")
        print(f"{'='*70}")
        print(f"スキャン件数: {stats['scanned']}")
        print(f"NGキーワード検出: {stats['found']}")
        if not dry_run:
            print(f"更新成功: {stats['updated']}")
            print(f"エラー: {stats['errors']}")

        if stats['details']:
            print(f"\n{'='*70}")
            print("変更詳細")
            print(f"{'='*70}")

            for i, detail in enumerate(stats['details'][:args.max_display]):
                print(f"\n[{i+1}] ASIN: {detail['asin']}")
                for change in detail['changes']:
                    print(f"    {change['field']}:")
                    print(f"      変更前: {change['original']}")
                    print(f"      変更後: {change['cleaned']}")

            if len(stats['details']) > args.max_display:
                print(f"\n... 他 {len(stats['details']) - args.max_display}件")

        if dry_run and stats['found'] > 0:
            print(f"\n{'='*70}")
            print("実行するには --execute オプションを使用してください")
            print(f"{'='*70}")


if __name__ == '__main__':
    main()
