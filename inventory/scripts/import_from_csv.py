"""
Import Data from CSV

既存のBASEマスタCSVなどからデータをインポートするスクリプト
"""

import sys
import argparse
import pandas as pd
from pathlib import Path
from datetime import datetime

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from inventory.core.master_db import MasterDB


def import_base_master_csv(csv_path: str, account_id: str = 'base_account_1'):
    """
    BASEマスタCSVをインポート

    Args:
        csv_path: CSVファイルのパス
        account_id: インポート先のアカウントID
    """
    print(f"\n=== BASEマスタCSVインポート ===")
    print(f"ファイル: {csv_path}")
    print(f"アカウント: {account_id}\n")

    # CSVを読み込み
    try:
        df = pd.read_csv(csv_path, encoding='utf-8-sig')
        print(f"読み込み完了: {len(df)}件")
    except Exception as e:
        print(f"エラー: CSVファイルの読み込みに失敗しました - {e}")
        return

    # マスタDBに接続
    db = MasterDB()

    success_count = 0
    update_count = 0
    error_count = 0

    for idx, row in df.iterrows():
        try:
            asin = str(row['ASIN']).strip()
            item_id = str(row['item_id']).strip() if pd.notna(row['item_id']) else None

            # 商品マスタに追加（既存の場合は更新）
            db.add_product(
                asin=asin,
                title_ja=row.get('商品名'),
                description_ja=row.get('商品説明'),
                amazon_price_jpy=int(row['価格（日本円）']) if pd.notna(row['価格（日本円）']) else None,
                amazon_in_stock=bool(row['在庫状況']) if pd.notna(row['在庫状況']) else None,
                images=[row['Image URL']] if pd.notna(row.get('Image URL')) else None
            )

            # item_idがある場合は出品情報も追加または更新
            if item_id and item_id != 'nan':
                sku = row.get('商品コード')
                selling_price = float(row['想定売価']) if pd.notna(row['想定売価']) else None
                in_stock = int(row['在庫状況']) if pd.notna(row['在庫状況']) else 0
                visibility = 'public' if row.get('公開状態') == 1 else 'hidden'

                # 既存の出品をチェック
                existing = db.get_listing_by_sku(sku) if sku else None

                # upsert_listing を使用（既存の場合は更新、新規の場合は追加）
                db.upsert_listing(
                    asin=asin,
                    platform='base',
                    account_id=account_id,
                    platform_item_id=item_id,
                    sku=sku,
                    selling_price=selling_price,
                    currency='JPY',
                    in_stock_quantity=in_stock,
                    status='listed',
                    visibility=visibility
                )

                if existing:
                    update_count += 1

            success_count += 1

            if (idx + 1) % 100 == 0:
                print(f"進捗: {idx + 1}/{len(df)} ({(idx + 1)/len(df)*100:.1f}%)")

        except Exception as e:
            error_count += 1
            # 最初の10件のみエラー詳細を表示
            if error_count <= 10:
                print(f"エラー: ASIN {asin} - {e}")

    print(f"\n=== インポート完了 ===")
    print(f"成功: {success_count}件")
    print(f"  - 新規: {success_count - update_count}件")
    print(f"  - 更新: {update_count}件")
    print(f"失敗: {error_count}件")
    print(f"成功率: {success_count/len(df)*100:.1f}%")


def import_integrated_master_csv(csv_path: str):
    """
    統合マスタCSV (product_master_integrated.csv) をインポート

    Args:
        csv_path: CSVファイルのパス
    """
    print(f"\n=== 統合マスタCSVインポート ===")
    print(f"ファイル: {csv_path}\n")

    # CSVを読み込み
    try:
        df = pd.read_csv(csv_path, encoding='utf-8-sig')
        print(f"読み込み完了: {len(df)}件")
    except Exception as e:
        print(f"エラー: CSVファイルの読み込みに失敗しました - {e}")
        return

    # マスタDBに接続
    db = MasterDB()

    success_count = 0
    update_count = 0
    error_count = 0

    for idx, row in df.iterrows():
        try:
            asin = str(row['asin']).strip()
            platform = row['platform']
            account_id = row['account_id']
            sku = row.get('sku')

            # 商品マスタに追加（既存データは上書き）
            db.add_product(
                asin=asin,
                amazon_price_jpy=None,  # 後でキャッシュから取得
                amazon_in_stock=bool(row['in_stock']) if pd.notna(row['in_stock']) else None
            )

            # 既存の出品をチェック
            existing = db.get_listing_by_sku(sku) if sku else None

            # 出品情報を追加または更新
            db.upsert_listing(
                asin=asin,
                platform=platform,
                account_id=account_id,
                sku=sku,
                selling_price=float(row['selling_price']) if pd.notna(row['selling_price']) else None,
                currency=row.get('currency', 'JPY'),
                in_stock_quantity=int(row['in_stock_quantity']) if pd.notna(row['in_stock_quantity']) else 0,
                status=row.get('status', 'listed')
            )

            if existing:
                update_count += 1

            success_count += 1

            if (idx + 1) % 100 == 0:
                print(f"進捗: {idx + 1}/{len(df)} ({(idx + 1)/len(df)*100:.1f}%)")

        except Exception as e:
            error_count += 1
            # 最初の10件のみエラー詳細を表示
            if error_count <= 10:
                print(f"エラー: ASIN {asin} - {e}")

    print(f"\n=== インポート完了 ===")
    print(f"成功: {success_count}件")
    print(f"  - 新規: {success_count - update_count}件")
    print(f"  - 更新: {update_count}件")
    print(f"失敗: {error_count}件")
    print(f"成功率: {success_count/len(df)*100:.1f}%")


def main():
    parser = argparse.ArgumentParser(description='既存CSVからデータをインポート')
    parser.add_argument('--source', required=True, help='インポート元CSVファイルのパス')
    parser.add_argument('--platform', default='base', help='プラットフォーム名（base, ebay, yahoo等）')
    parser.add_argument('--account-id', help='アカウントID（BASEマスタCSVの場合のみ必要）')
    parser.add_argument('--type', choices=['base_master', 'integrated'], default='base_master',
                       help='CSVの種類')

    args = parser.parse_args()

    csv_path = Path(args.source)

    if not csv_path.exists():
        print(f"エラー: ファイルが見つかりません: {csv_path}")
        sys.exit(1)

    if args.type == 'base_master':
        account_id = args.account_id or 'base_account_1'
        import_base_master_csv(str(csv_path), account_id)
    elif args.type == 'integrated':
        import_integrated_master_csv(str(csv_path))


if __name__ == '__main__':
    main()
