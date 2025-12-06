#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
メルカリショップス - セッション確認

保存されたChromeプロファイルからセッションを復元し、
ログイン状態を確認します。

使用方法:
    python platforms/mercari_shops/scripts/verify_session.py

    # ヘッドレスモードで確認
    python platforms/mercari_shops/scripts/verify_session.py --headless

動作:
    1. 保存されたChromeプロファイルからブラウザを起動
    2. セッション情報を自動復元
    3. メルカリショップスにアクセスしてログイン状態を確認
    4. ログイン済みの場合は成功メッセージを表示
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
        description="メルカリショップス セッション確認"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="ヘッドレスモードで実行"
    )
    parser.add_argument(
        "--account",
        default="mercari_shops_main",
        help="アカウントID（デフォルト: mercari_shops_main）"
    )
    args = parser.parse_args()

    print()
    print("=" * 60)
    print("メルカリショップス - セッション確認")
    print("=" * 60)
    print()

    # セッションマネージャーを初期化
    session = MercariShopsSession(account_id=args.account)

    # プロファイル情報を表示
    profile_info = session.profile_manager.get_profile_info(
        session.platform,
        session.account_id
    )

    print("【プロファイル情報】")
    print(f"  プラットフォーム: {profile_info['platform']}")
    print(f"  アカウントID: {profile_info['account_id']}")
    print(f"  プロファイルパス: {profile_info['profile_path']}")
    print(f"  存在: {profile_info['exists']}")

    if profile_info['exists']:
        print(f"  サイズ: {profile_info['size_mb']} MB")

    print()

    if not profile_info['exists']:
        print("[ERROR] プロファイルが見つかりません")
        print()
        print("初回ログインを実行してください:")
        print("  python platforms/mercari_shops/scripts/login.py")
        print()
        return

    # 認証済みコンテキストを取得
    result = await session.get_authenticated_context(headless=args.headless)

    if result is None:
        print()
        print("=" * 60)
        print("[FAILED] セッションが無効です")
        print("=" * 60)
        print()
        print("再ログインが必要です:")
        print("  python platforms/mercari_shops/scripts/login.py")
        print()
        return

    playwright, context, page = result

    try:
        print()
        print("=" * 60)
        print("[SUCCESS] セッションが有効です！")
        print("=" * 60)
        print()
        print(f"現在のURL: {page.url}")
        print()

        # ページタイトルを取得
        title = await page.title()
        print(f"ページタイトル: {title}")
        print()

        # ヘッドレスモードでない場合は、ブラウザを10秒間表示
        if not args.headless:
            print("ブラウザを10秒間表示します...")
            await asyncio.sleep(10)
            print()

        print("セッション確認が完了しました")
        print()

    except Exception as e:
        print(f"[ERROR] エラー: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # クリーンアップ
        await context.close()
        await playwright.stop()


if __name__ == "__main__":
    asyncio.run(main())
