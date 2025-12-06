"""
BASE トークン状態確認スクリプト

全アカウントのトークン状態を確認
"""

import sys
from pathlib import Path
from datetime import datetime

# パスを追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from accounts.manager import AccountManager
from core.auth import BaseOAuthClient


def main():
    print("=" * 60)
    print(f"BASE トークン状態確認 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # AccountManagerを初期化
    manager = AccountManager()

    if not manager.accounts:
        print("\n警告: アカウントが登録されていません")
        return

    print(f"\n登録アカウント: {len(manager.accounts)}件")
    print()

    # 各アカウントの状態を確認
    expired_accounts = []
    no_token_accounts = []
    valid_accounts = []

    for account in manager.accounts:
        account_id = account['id']
        name = account['name']
        active = account.get('active', False)

        print("-" * 60)
        print(f"アカウント: {name} ({account_id})")
        print(f"  状態: {'アクティブ' if active else '非アクティブ'}")

        # トークンを取得
        token = manager.get_token(account_id)

        if not token:
            print("  トークン: [なし]")
            if active:
                no_token_accounts.append(account_id)
            continue

        # トークン情報を取得
        token_info = BaseOAuthClient.get_token_info(token)

        print(f"  トークン: [あり]")
        print(f"    アクセストークン: {'あり' if token_info['has_access_token'] else 'なし'}")
        print(f"    リフレッシュトークン: {'あり' if token_info['has_refresh_token'] else 'なし'}")
        print(f"    取得日時: {token_info.get('obtained_at', '不明')}")

        if 'remaining_hours' in token_info:
            remaining_hours = token_info['remaining_hours']
            print(f"    有効期限: 残り {remaining_hours} 時間")

            # 期限切れチェック
            if token_info['is_expired']:
                print("    状態: [期限切れ]")
                if active:
                    expired_accounts.append(account_id)
            elif remaining_hours < 24:
                print("    状態: [要注意] 24時間以内に期限切れ")
            else:
                print("    状態: [正常]")
                if active:
                    valid_accounts.append(account_id)
        else:
            print("    有効期限: 不明")

    # サマリー
    print("\n" + "=" * 60)
    print("サマリー")
    print("=" * 60)
    print(f"有効なトークン: {len(valid_accounts)}件")
    print(f"期限切れトークン: {len(expired_accounts)}件")
    print(f"トークンなし: {len(no_token_accounts)}件")

    if expired_accounts:
        print("\n[要対応] 期限切れトークンのアカウント:")
        for account_id in expired_accounts:
            account = manager.get_account(account_id)
            print(f"  - {account['name']} ({account_id})")
        print("\n以下のコマンドで更新してください:")
        print("  python platforms/base/scripts/refresh_tokens.py")

    if no_token_accounts:
        print("\n[要対応] トークンが設定されていないアカウント:")
        for account_id in no_token_accounts:
            account = manager.get_account(account_id)
            print(f"  - {account['name']} ({account_id})")
        print("\n以下のコマンドで初回認証してください:")
        print("  python platforms/base/scripts/get_authorization_code.py")

    print("=" * 60)


if __name__ == '__main__':
    main()
