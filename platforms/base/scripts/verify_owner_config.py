#!/usr/bin/env python
"""
オーナー設定検証スクリプト

account_config.json のオーナー設定を検証し、以下をチェック:
1. 全アカウントがowner_idを持っているか
2. 全owner_idが存在するオーナーを参照しているか
3. 全オーナーがproxy_idを持っているか
4. 全proxy_idが存在するプロキシを参照しているか

使用方法:
    venv/bin/python -m platforms.base.scripts.verify_owner_config
    venv/bin/python -m platforms.base.scripts.verify_owner_config --verbose
"""

import argparse
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from platforms.base.accounts.manager import AccountManager
from common.proxy.proxy_manager import ProxyManager


def verify_owner_config(verbose: bool = False) -> bool:
    """
    オーナー設定を検証

    Args:
        verbose: 詳細な情報を表示するか

    Returns:
        bool: 全てのチェックが通った場合True
    """
    print("=" * 60)
    print("オーナー設定検証")
    print("=" * 60)

    errors = []
    warnings = []

    # AccountManagerとProxyManagerを初期化
    try:
        am = AccountManager()
        pm = ProxyManager()
    except Exception as e:
        print(f"[ERROR] 設定ファイルの読み込みに失敗: {e}")
        return False

    # 1. オーナー設定の存在チェック
    print("\n[1] オーナー設定の存在チェック")
    if not am.owners:
        warnings.append("オーナー設定が空です（owners配列が未設定）")
        print("  [WARN] オーナー設定が空です")
    else:
        print(f"  [OK] オーナー数: {len(am.owners)}件")
        if verbose:
            for owner_id in am.owners:
                print(f"       - {owner_id}")

    # 2. アカウントのowner_idチェック
    print("\n[2] アカウントのowner_idチェック")
    accounts_without_owner = []
    accounts_with_invalid_owner = []

    for account in am.accounts:
        account_id = account['id']
        owner_id = account.get('owner_id')

        if not owner_id:
            accounts_without_owner.append(account_id)
        elif owner_id not in am.owners:
            accounts_with_invalid_owner.append((account_id, owner_id))

    if accounts_without_owner:
        warnings.append(f"owner_id未設定のアカウント: {accounts_without_owner}")
        print(f"  [WARN] owner_id未設定: {len(accounts_without_owner)}件")
        for acc_id in accounts_without_owner:
            print(f"         - {acc_id}")
    else:
        print("  [OK] 全アカウントにowner_idが設定されています")

    if accounts_with_invalid_owner:
        errors.append(f"無効なowner_id参照: {accounts_with_invalid_owner}")
        print(f"  [ERROR] 無効なowner_id参照: {len(accounts_with_invalid_owner)}件")
        for acc_id, owner_id in accounts_with_invalid_owner:
            print(f"          - {acc_id} → {owner_id} (存在しません)")
    else:
        print("  [OK] 全てのowner_id参照が有効です")

    # 3. オーナーのproxy_idチェック
    print("\n[3] オーナーのproxy_idチェック")
    owners_without_proxy = []
    owners_with_invalid_proxy = []
    proxy_ids = pm.list_proxies()

    for owner_id, owner in am.owners.items():
        proxy_id = owner.get('proxy_id')

        if not proxy_id:
            owners_without_proxy.append(owner_id)
        elif proxy_id not in proxy_ids:
            owners_with_invalid_proxy.append((owner_id, proxy_id))

    if owners_without_proxy:
        warnings.append(f"proxy_id未設定のオーナー: {owners_without_proxy}")
        print(f"  [WARN] proxy_id未設定: {len(owners_without_proxy)}件")
        for owner_id in owners_without_proxy:
            print(f"         - {owner_id}")
    else:
        print("  [OK] 全オーナーにproxy_idが設定されています")

    if owners_with_invalid_proxy:
        errors.append(f"無効なproxy_id参照: {owners_with_invalid_proxy}")
        print(f"  [ERROR] 無効なproxy_id参照: {len(owners_with_invalid_proxy)}件")
        for owner_id, proxy_id in owners_with_invalid_proxy:
            print(f"          - {owner_id} → {proxy_id} (存在しません)")
    else:
        print("  [OK] 全てのproxy_id参照が有効です")

    # 4. プロキシ解決テスト
    print("\n[4] プロキシ解決テスト")
    for account in am.accounts:
        account_id = account['id']
        proxy_id = am.get_proxy_id_for_account(account_id)
        proxy_type = "direct" if not proxy_id else pm.get_proxy_info(proxy_id).get('type', 'unknown') if pm.get_proxy_info(proxy_id) else "unknown"

        if verbose:
            print(f"  {account_id} → proxy: {proxy_id or 'なし'} ({proxy_type})")

    if not verbose:
        print("  [INFO] 詳細は --verbose オプションで確認できます")

    # 5. サマリー表示
    print("\n" + "=" * 60)
    print("検証結果サマリー")
    print("=" * 60)

    if errors:
        print(f"\n[ERROR] {len(errors)}件のエラーがあります:")
        for err in errors:
            print(f"  - {err}")

    if warnings:
        print(f"\n[WARN] {len(warnings)}件の警告があります:")
        for warn in warnings:
            print(f"  - {warn}")

    if not errors and not warnings:
        print("\n[OK] 全てのチェックに合格しました")

    # オーナーごとのアカウント一覧
    if verbose:
        print("\n" + "-" * 40)
        print("オーナーごとのアカウント一覧")
        print("-" * 40)
        for owner_id in am.list_owners():
            owner_info = am.get_owner_info(owner_id)
            print(f"\n[{owner_id}] {owner_info['name']}")
            print(f"  プロキシ: {owner_info['proxy_id']}")
            print(f"  アカウント ({owner_info['account_count']}件):")
            for acc_id in owner_info['accounts']:
                print(f"    - {acc_id}")

    return len(errors) == 0


def main():
    parser = argparse.ArgumentParser(
        description='オーナー設定を検証します',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  venv/bin/python -m platforms.base.scripts.verify_owner_config
  venv/bin/python -m platforms.base.scripts.verify_owner_config --verbose
        """
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='詳細な情報を表示'
    )

    args = parser.parse_args()

    success = verify_owner_config(verbose=args.verbose)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
