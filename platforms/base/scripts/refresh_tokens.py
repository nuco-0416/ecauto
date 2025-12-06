"""
BASE トークン一括更新スクリプト

全アカウントのトークンを一括で更新
定期実行（cron/タスクスケジューラ）での使用を想定
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
    print(f"BASE トークン一括更新 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # AccountManagerを初期化
    manager = AccountManager()

    # アクティブなアカウント一覧を取得
    active_accounts = manager.get_active_accounts()

    if not active_accounts:
        print("\n警告: アクティブなアカウントが見つかりません")
        return

    print(f"\nアクティブアカウント: {len(active_accounts)}件")
    print()

    # 全アカウントのトークンを更新
    results = manager.refresh_all_tokens(active_only=True)

    # 結果サマリー
    success_count = sum(1 for success in results.values() if success)
    failure_count = len(results) - success_count

    print("\n" + "=" * 60)
    print("更新結果")
    print("=" * 60)

    for account_id, success in results.items():
        account = manager.get_account(account_id)
        status = "[OK]" if success else "[ERROR]"
        print(f"{status} {account['name']} ({account_id})")

        # トークン情報を表示
        if success:
            token = manager.get_token(account_id)
            if token:
                token_info = BaseOAuthClient.get_token_info(token)
                if 'remaining_hours' in token_info:
                    print(f"      有効期限: 残り {token_info['remaining_hours']} 時間")

    print()
    print(f"成功: {success_count}件 / 失敗: {failure_count}件")
    print("=" * 60)

    # 失敗があった場合は終了コード1
    if failure_count > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()
