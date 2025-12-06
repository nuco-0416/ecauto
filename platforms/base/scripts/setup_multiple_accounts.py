"""
Setup Multiple BASE Accounts

複数BASEアカウントのトークンを一括設定するスクリプト
"""

import sys
import json
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from platforms.base.accounts.manager import AccountManager


def setup_token_manually(account_id: str):
    """
    手動でトークン情報を入力して保存

    Args:
        account_id: アカウントID
    """
    print(f"\n--- {account_id} のトークン設定 ---")

    access_token = input("Access Token: ").strip()
    if not access_token:
        print("[SKIP] Access Tokenが空のためスキップします")
        return False

    refresh_token = input("Refresh Token (Enterでスキップ): ").strip()

    token_data = {
        "access_token": access_token,
        "refresh_token": refresh_token if refresh_token else "",
        "token_type": "Bearer",
        "expires_in": 3600
    }

    manager = AccountManager()
    success = manager.save_token(account_id, token_data)

    if success:
        print(f"[OK] {account_id} のトークンを保存しました")
        return True
    else:
        print(f"[ERROR] {account_id} のトークン保存に失敗しました")
        return False


def import_from_file(account_id: str, token_file_path: str):
    """
    ファイルからトークンをインポート

    Args:
        account_id: アカウントID
        token_file_path: トークンファイルのパス
    """
    token_file = Path(token_file_path)

    if not token_file.exists():
        print(f"[ERROR] ファイルが見つかりません: {token_file_path}")
        return False

    try:
        with open(token_file, 'r', encoding='utf-8') as f:
            token_data = json.load(f)

        manager = AccountManager()
        success = manager.save_token(account_id, token_data)

        if success:
            print(f"[OK] {account_id} のトークンをインポートしました")
            print(f"  ソース: {token_file_path}")
            return True
        else:
            print(f"[ERROR] {account_id} のトークン保存に失敗しました")
            return False

    except Exception as e:
        print(f"[ERROR] トークンのインポート中にエラーが発生しました: {e}")
        return False


def setup_all_accounts():
    """全アカウントのトークンを設定"""
    print("=" * 60)
    print("複数BASEアカウントのトークン設定")
    print("=" * 60)

    manager = AccountManager()
    accounts = manager.list_accounts()

    if not accounts:
        print("\n[ERROR] アカウント設定がありません")
        print("platforms/base/accounts/account_config.json を作成してください")
        return

    print(f"\n設定対象アカウント: {len(accounts)}件")
    for i, account_id in enumerate(accounts, 1):
        account = manager.get_account(account_id)
        active = "[Active]" if account.get('active') else "[Inactive]"
        has_token = "[Token OK]" if manager.has_valid_token(account_id) else "[No Token]"
        print(f"  {i}. {active} {has_token} {account_id} - {account['name']}")

    print("\n設定方法を選択してください:")
    print("  1. 手動入力（各アカウントごとにトークンを入力）")
    print("  2. ファイルからインポート（各アカウントごとにファイルを指定）")
    print("  3. キャンセル")

    choice = input("\n選択 (1-3): ").strip()

    if choice == '1':
        # 手動入力モード
        success_count = 0
        for account_id in accounts:
            account = manager.get_account(account_id)
            print(f"\n[{account_id}] {account['name']}")

            if manager.has_valid_token(account_id):
                response = input("既にトークンがあります。上書きしますか? (y/n): ")
                if response.lower() != 'y':
                    print("[SKIP] スキップしました")
                    continue

            if setup_token_manually(account_id):
                success_count += 1

        print(f"\n[完了] {success_count}/{len(accounts)} アカウントのトークンを設定しました")

    elif choice == '2':
        # ファイルインポートモード
        success_count = 0
        for account_id in accounts:
            account = manager.get_account(account_id)
            print(f"\n[{account_id}] {account['name']}")

            if manager.has_valid_token(account_id):
                response = input("既にトークンがあります。上書きしますか? (y/n): ")
                if response.lower() != 'y':
                    print("[SKIP] スキップしました")
                    continue

            token_file = input("トークンファイルのパス (Enterでスキップ): ").strip()
            if not token_file:
                print("[SKIP] スキップしました")
                continue

            if import_from_file(account_id, token_file):
                success_count += 1

        print(f"\n[完了] {success_count}/{len(accounts)} アカウントのトークンを設定しました")

    else:
        print("\n[CANCELLED] キャンセルしました")


def quick_setup_two_accounts():
    """2アカウントのクイックセットアップ"""
    print("=" * 60)
    print("2アカウント クイックセットアップ")
    print("=" * 60)

    manager = AccountManager()
    accounts = manager.list_accounts()

    if len(accounts) < 2:
        print("\n[ERROR] アカウント設定が2件未満です")
        return

    print("\n既存のトークンファイルから設定します")
    print("\n例: C:/Users/hiroo/Documents/ama-cari/base/base_token_account1.json")

    # アカウント1
    print(f"\n[1] {accounts[0]}")
    token_file_1 = input("トークンファイル1のパス: ").strip()
    if token_file_1:
        import_from_file(accounts[0], token_file_1)

    # アカウント2
    print(f"\n[2] {accounts[1]}")
    token_file_2 = input("トークンファイル2のパス: ").strip()
    if token_file_2:
        import_from_file(accounts[1], token_file_2)

    print("\n[完了] セットアップ完了")


def main():
    """メイン処理"""
    print("\n複数アカウントのトークン設定")
    print("\nモードを選択してください:")
    print("  1. 全アカウント設定（推奨）")
    print("  2. 2アカウント クイックセットアップ")
    print("  3. キャンセル")

    mode = input("\n選択 (1-3): ").strip()

    if mode == '1':
        setup_all_accounts()
    elif mode == '2':
        quick_setup_two_accounts()
    else:
        print("\n[CANCELLED] キャンセルしました")


if __name__ == '__main__':
    main()
