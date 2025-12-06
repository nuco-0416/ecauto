"""
Setup BASE Account

BASEアカウントのセットアップを行うスクリプト
既存のトークンをコピーして設定
"""

import sys
import json
import shutil
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from platforms.base.accounts.manager import AccountManager


def copy_existing_token(source_path: str, account_id: str):
    """
    既存のトークンファイルをコピー

    Args:
        source_path: コピー元のトークンファイルパス
        account_id: コピー先のアカウントID
    """
    manager = AccountManager()
    source = Path(source_path)

    if not source.exists():
        print(f"[ERROR] ソースファイルが見つかりません: {source_path}")
        return False

    # トークンファイルを読み込み
    try:
        with open(source, 'r', encoding='utf-8') as f:
            token_data = json.load(f)

        # 保存
        success = manager.save_token(account_id, token_data)

        if success:
            print(f"[OK] トークンをコピーしました")
            print(f"  元: {source}")
            print(f"  先: {manager.tokens_dir / f'{account_id}_token.json'}")
            return True
        else:
            print(f"[ERROR] トークンの保存に失敗しました")
            return False

    except Exception as e:
        print(f"[ERROR] トークンのコピー中にエラーが発生しました: {e}")
        return False


def setup_from_old_base():
    """既存のBASEプロジェクトからトークンをコピー"""
    print("=" * 60)
    print("既存BASEプロジェクトからのセットアップ")
    print("=" * 60)

    # 既存のbase_token.jsonのパス
    old_token_path = Path("C:/Users/hiroo/Documents/ama-cari/base/base_token.json")

    if not old_token_path.exists():
        print(f"\n[WARNING] 既存のトークンファイルが見つかりません")
        print(f"パス: {old_token_path}")
        print("\n手動でトークンを設定してください")
        return

    print(f"\n既存トークン: {old_token_path}")

    # アカウント選択
    manager = AccountManager()
    accounts = manager.list_accounts()

    if not accounts:
        print("\n[ERROR] アカウント設定がありません")
        print("platforms/base/accounts/account_config.json を作成してください")
        return

    print("\n設定可能なアカウント:")
    for i, account_id in enumerate(accounts, 1):
        account = manager.get_account(account_id)
        print(f"  {i}. {account_id} - {account['name']}")

    # デフォルトは最初のアカウント
    print(f"\nデフォルトアカウント: {accounts[0]}")
    response = input("このアカウントにトークンをコピーしますか? (y/n): ")

    if response.lower() == 'y':
        success = copy_existing_token(str(old_token_path), accounts[0])
        if success:
            print("\n[SUCCESS] セットアップ完了")
        else:
            print("\n[ERROR] セットアップ失敗")
    else:
        print("\n[CANCELLED] キャンセルしました")


def main():
    """メイン処理"""
    setup_from_old_base()


if __name__ == '__main__':
    main()
