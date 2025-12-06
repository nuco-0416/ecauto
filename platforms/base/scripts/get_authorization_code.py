"""
BASE OAuth Authorization Code取得スクリプト

初回認証時に使用するスクリプト
認証URLを生成し、ブラウザで認証後に取得したコードからトークンを取得
"""

import sys
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from platforms.base.accounts.manager import AccountManager
from platforms.base.core.auth import BaseOAuthClient


def main():
    print("=" * 60)
    print("BASE OAuth 認証コード取得")
    print("=" * 60)

    # AccountManagerを初期化
    manager = AccountManager()

    # アカウント一覧を表示
    print("\n利用可能なアカウント:")
    for i, account in enumerate(manager.accounts, 1):
        status = "[Active]" if account.get('active') else "[Inactive]"
        print(f"{i}. {status} {account['id']} - {account['name']}")

    # アカウントを選択
    account_num = input("\n認証するアカウント番号を選択してください: ")
    try:
        account_index = int(account_num) - 1
        if account_index < 0 or account_index >= len(manager.accounts):
            print("エラー: 無効なアカウント番号です")
            return

        account = manager.accounts[account_index]
    except ValueError:
        print("エラー: 数字を入力してください")
        return

    account_id = account['id']
    credentials = account.get('credentials', {})

    print(f"\n選択されたアカウント: {account['name']} ({account_id})")

    # OAuth クライアントを作成
    oauth_client = BaseOAuthClient(
        client_id=credentials.get('client_id'),
        client_secret=credentials.get('client_secret'),
        redirect_uri=credentials.get('redirect_uri')
    )

    # 認証URLを生成
    auth_url = oauth_client.get_authorization_url()

    print("\n" + "=" * 60)
    print("ステップ1: ブラウザで以下のURLにアクセスして認証してください")
    print("=" * 60)
    print(auth_url)
    print()

    # 認証コードを入力
    print("=" * 60)
    print("ステップ2: 認証後、リダイレクトされたURLから 'code=' パラメータの値をコピーしてください")
    print("=" * 60)
    print("例: http://localhost:8000/callback?code=ABC123DEF456")
    print("    → 'ABC123DEF456' の部分をコピー")
    print()

    code = input("認証コードを入力してください: ").strip()

    if not code:
        print("エラー: 認証コードが入力されていません")
        return

    # トークンを取得
    try:
        print("\nトークンを取得中...")
        token_data = oauth_client.get_access_token_from_code(code)

        # トークンを保存
        if manager.save_token(account_id, token_data):
            print("\n[OK] トークン取得・保存成功!")
            print(f"保存先: {manager.tokens_dir / f'{account_id}_token.json'}")

            # トークン情報を表示
            token_info = BaseOAuthClient.get_token_info(token_data)
            print("\nトークン情報:")
            print(f"  アクセストークン: {'あり' if token_info['has_access_token'] else 'なし'}")
            print(f"  リフレッシュトークン: {'あり' if token_info['has_refresh_token'] else 'なし'}")
            if 'remaining_hours' in token_info:
                print(f"  有効期限: 残り {token_info['remaining_hours']} 時間")

        else:
            print("\n[ERROR] トークンの保存に失敗しました")

    except Exception as e:
        print(f"\n[ERROR] トークンの取得に失敗しました: {e}")


if __name__ == '__main__':
    main()
