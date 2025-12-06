#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
メルカリショップス - 初回ログイン

Chromeプロファイルへの手動ログイン→セッション保存を行います。

使用方法:
    python platforms/mercari_shops/scripts/login.py

実行後:
    1. ブラウザが自動的に開きます
    2. メルカリショップスのログインページが表示されます
    3. 手動でログイン（メール/パスワード + 2段階認証）
    4. ログイン完了を自動検知してセッション保存
    5. 次回以降は自動的にログイン状態が復元されます
"""

import asyncio
import sys
import argparse
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from platforms.mercari_shops.browser.session import MercariShopsSession


async def main():
    """メイン処理"""
    # コマンドライン引数の解析
    parser = argparse.ArgumentParser(
        description="メルカリショップス - 初回ログイン"
    )
    parser.add_argument(
        "--account",
        default="mercari_shops_main",
        help="アカウントID（デフォルト: mercari_shops_main）"
    )
    args = parser.parse_args()

    print()
    print("=" * 60)
    print("メルカリショップス - 初回ログイン")
    print("=" * 60)
    print()
    print("このスクリプトは以下を行います:")
    print("  1. Chromeブラウザを起動")
    print("  2. メルカリショップスのログインページを開く")
    print("  3. 手動ログイン（メール/パスワード + 2段階認証）")
    print("  4. ログイン完了を自動検知してプロファイルに保存")
    print()
    print("準備ができたら Enter キーを押してください...")
    input()

    # セッションマネージャーを初期化
    session = MercariShopsSession(account_id=args.account)

    # プロファイル情報を表示
    profile_info = session.profile_manager.get_profile_info(
        session.platform,
        session.account_id
    )

    print()
    print("【プロファイル情報】")
    print(f"  プラットフォーム: {profile_info['platform']}")
    print(f"  アカウントID: {profile_info['account_id']}")
    print(f"  プロファイルパス: {profile_info['profile_path']}")
    print(f"  存在: {profile_info['exists']}")

    if profile_info['exists']:
        print(f"  サイズ: {profile_info['size_mb']} MB")
        print()
        print("[WARN] プロファイルが既に存在します")
        print("既存のセッション情報は上書きされます")
        print()

        response = input("続行しますか？ (y/n): ").strip().lower()
        if response != 'y':
            print("キャンセルしました")
            return

    print()

    # 手動ログイン実行
    success = await session.manual_login(
        headless=False,
        max_wait_seconds=300  # 5分間待機
    )

    if success:
        print()
        print("=" * 60)
        print("[SUCCESS] ログインとセッション保存が完了しました！")
        print("=" * 60)
        print()
        print("次回以降は以下のコマンドでセッションを確認できます:")
        print("  python platforms/mercari_shops/scripts/verify_session.py")
        print()
    else:
        print()
        print("=" * 60)
        print("[FAILED] ログインに失敗しました")
        print("=" * 60)
        print()
        print("もう一度実行してください")
        print()


if __name__ == "__main__":
    asyncio.run(main())
