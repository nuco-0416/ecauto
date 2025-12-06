"""
BASE商品削除スクリプト

指定されたitem_idまたはASINの商品をBASEから削除
"""

import sys
from pathlib import Path
from typing import List

# パスを追加
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from inventory.core.master_db import MasterDB


def delete_by_item_ids(item_ids: List[str], account_id: str) -> dict:
    """
    item_idで商品を削除

    Args:
        item_ids: BASEのitem_idリスト
        account_id: アカウントID

    Returns:
        dict: 削除結果
    """
    # 遅延インポート（循環インポート回避）
    from platforms.base.accounts.manager import AccountManager
    from platforms.base.core.api_client import BaseAPIClient

    account_manager = AccountManager()
    account = account_manager.get_account(account_id)

    if not account:
        raise ValueError(f"アカウントが見つかりません: {account_id}")

    # BaseAPIClientを正しく初期化（自動トークン更新機能を有効化）
    client = BaseAPIClient(
        account_id=account_id,
        account_manager=account_manager
    )
    db = MasterDB()

    success_count = 0
    failed_count = 0
    results = []

    for item_id in item_ids:
        try:
            print(f"[削除中] item_id={item_id}")

            # BASE APIで削除
            response = client.delete_item(item_id)
            print(f"  [OK] BASEから削除完了")

            # マスタDBのステータスを更新
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE listings
                    SET status = 'deleted',
                        platform_item_id = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE platform = 'base'
                      AND platform_item_id = ?
                """, (item_id,))
                conn.commit()
                print(f"  [OK] マスタDB更新完了")

            success_count += 1
            results.append({'item_id': item_id, 'status': 'success'})

        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"

            # HTTPエラーの場合は詳細を表示
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_json = e.response.json()
                    error_msg += f" | Response: {error_json}"
                except:
                    error_msg += f" | Status: {e.response.status_code}"

            print(f"  [ERROR] 削除失敗: {error_msg}")
            failed_count += 1
            results.append({'item_id': item_id, 'status': 'failed', 'error': error_msg})

    return {
        'success': success_count,
        'failed': failed_count,
        'results': results
    }


def delete_by_asins(asins: List[str], account_id: str, platform: str = 'base') -> dict:
    """
    ASINで商品を削除（マスタDBから item_id を取得）

    Args:
        asins: ASINリスト
        account_id: アカウントID
        platform: プラットフォーム名

    Returns:
        dict: 削除結果
    """
    db = MasterDB()

    # ASINからitem_idを取得
    item_ids = []
    not_found = []

    with db.get_connection() as conn:
        cursor = conn.cursor()

        for asin in asins:
            cursor.execute("""
                SELECT platform_item_id
                FROM listings
                WHERE asin = ?
                  AND platform = ?
                  AND account_id = ?
                  AND platform_item_id IS NOT NULL
            """, (asin, platform, account_id))

            result = cursor.fetchone()
            if result and result[0]:
                item_ids.append(result[0])
                print(f"ASIN {asin} -> item_id {result[0]}")
            else:
                not_found.append(asin)
                print(f"ASIN {asin} -> item_id not found (未アップロードまたは削除済み)")

    if not item_ids:
        print("\n削除対象の商品がありません")
        return {'success': 0, 'failed': 0, 'not_found': not_found}

    # item_idで削除実行
    result = delete_by_item_ids(item_ids, account_id)
    result['not_found'] = not_found

    return result


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='BASE商品削除スクリプト'
    )
    parser.add_argument(
        '--item-ids',
        type=str,
        help='削除するitem_id（カンマ区切り）'
    )
    parser.add_argument(
        '--asins',
        type=str,
        help='削除するASIN（カンマ区切り）'
    )
    parser.add_argument(
        '--account-id',
        type=str,
        required=True,
        help='アカウントID'
    )
    parser.add_argument(
        '--platform',
        type=str,
        default='base',
        help='プラットフォーム名（デフォルト: base）'
    )
    parser.add_argument(
        '--yes', '-y',
        action='store_true',
        help='確認をスキップ'
    )

    args = parser.parse_args()

    if not args.item_ids and not args.asins:
        print("エラー: --item-ids または --asins を指定してください")
        return

    print("=" * 60)
    print("BASE商品削除")
    print("=" * 60)

    # item_idsまたはASINsをリストに変換
    if args.item_ids:
        item_ids = [x.strip() for x in args.item_ids.split(',')]
        print(f"\n削除対象item_id: {len(item_ids)}件")
        for item_id in item_ids:
            print(f"  - {item_id}")
    else:
        item_ids = None

    if args.asins:
        asins = [x.strip() for x in args.asins.split(',')]
        print(f"\n削除対象ASIN: {len(asins)}件")
        for asin in asins:
            print(f"  - {asin}")
    else:
        asins = None

    print(f"\nアカウント: {args.account_id}")

    # 確認
    if not args.yes:
        response = input(f"\n削除を実行しますか？ (y/N): ")
        if response.lower() != 'y':
            print("キャンセルしました")
            return
    else:
        print("\n削除を実行します（--yesオプション指定）")

    # 削除実行
    print("\n削除中...")

    if item_ids:
        result = delete_by_item_ids(item_ids, args.account_id)
    else:
        result = delete_by_asins(asins, args.account_id, args.platform)

    # 結果表示
    print("\n" + "=" * 60)
    print("削除完了")
    print("=" * 60)
    print(f"成功: {result['success']}件")
    print(f"失敗: {result['failed']}件")
    if 'not_found' in result and result['not_found']:
        print(f"未発見: {len(result['not_found'])}件")
        for asin in result['not_found']:
            print(f"  - {asin}")
    print("=" * 60)


if __name__ == '__main__':
    main()
