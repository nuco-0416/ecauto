"""
Yahoo Auction Session Verification Script

Yahoo!オークションのセッション状態を確認するスクリプト。
保存済みのプロファイルを使用してログイン状態を検証する。

使用例:
    python -m platforms.yahoo_auction.scripts.verify_session --account-id yahoo_01
    python -m platforms.yahoo_auction.scripts.verify_session --account-id yahoo_01 --proxy-id proxy_01
"""

import argparse
import logging
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from platforms.yahoo_auction.browser.session import YahooAuctionSession
from common.browser.profile_manager import ProfileManager

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(
        description='Yahoo!オークションのセッション状態を確認します',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
  # セッション状態を確認
  python -m platforms.yahoo_auction.scripts.verify_session --account-id yahoo_01

  # プロキシを指定して確認
  python -m platforms.yahoo_auction.scripts.verify_session --account-id yahoo_01 --proxy-id proxy_01

  # ブラウザを表示して確認
  python -m platforms.yahoo_auction.scripts.verify_session --account-id yahoo_01 --show-browser
        """
    )

    parser.add_argument(
        '--account-id',
        required=True,
        help='アカウントID（例: yahoo_01）'
    )
    parser.add_argument(
        '--proxy-id',
        default=None,
        help='プロキシID（config/proxies.json で定義）'
    )
    parser.add_argument(
        '--show-browser',
        action='store_true',
        help='ブラウザを表示する（デフォルト: ヘッドレス）'
    )
    parser.add_argument(
        '--screenshot',
        action='store_true',
        help='スクリーンショットを撮影する'
    )

    args = parser.parse_args()

    print("=" * 60)
    print("Yahoo!オークション セッション確認")
    print("=" * 60)
    print(f"アカウントID: {args.account_id}")
    if args.proxy_id:
        print(f"プロキシID: {args.proxy_id}")
    print(f"ヘッドレスモード: {'OFF' if args.show_browser else 'ON'}")
    print("=" * 60)
    print()

    # プロファイルの存在確認
    profile_manager = ProfileManager()
    if not profile_manager.profile_exists("yahoo_auction", args.account_id):
        print("[WARNING] プロファイルが存在しません")
        print("先に login.py でログインしてください")
        print()
        print("実行例:")
        print(f"  python -m platforms.yahoo_auction.scripts.login --account-id {args.account_id}")
        return 1

    profile_info = profile_manager.get_profile_info("yahoo_auction", args.account_id)
    print(f"プロファイル: {profile_info['profile_path']}")
    print(f"サイズ: {profile_info['size_mb']} MB")
    print()

    # セッション開始
    session = YahooAuctionSession(
        account_id=args.account_id,
        proxy_id=args.proxy_id,
        headless=not args.show_browser
    )

    try:
        print("セッションを開始中...")
        page = session.start()

        print("ログイン状態を確認中...")
        print()

        if session.is_logged_in():
            print("-" * 60)
            print("[OK] ログイン済みです")
            print("-" * 60)
            print()
            print(f"現在のURL: {page.url}")

            # スクリーンショット撮影
            if args.screenshot:
                screenshot_path = session.take_screenshot("verify_session.png")
                print(f"スクリーンショット: {screenshot_path}")

            # 追加情報の取得を試みる
            try:
                # ユーザー情報を取得（可能であれば）
                page.goto(session.URLS['mypage'], wait_until='domcontentloaded', timeout=10000)
                print(f"マイページURL: {page.url}")
            except Exception as e:
                logger.debug(f"マイページ情報取得スキップ: {e}")

            return 0

        else:
            print("-" * 60)
            print("[NG] ログインが必要です")
            print("-" * 60)
            print()
            print("セッションが無効か期限切れです")
            print("login.py で再ログインしてください")
            print()
            print("実行例:")
            print(f"  python -m platforms.yahoo_auction.scripts.login --account-id {args.account_id}")

            # スクリーンショット撮影
            if args.screenshot:
                screenshot_path = session.take_screenshot("verify_session_failed.png")
                print(f"スクリーンショット: {screenshot_path}")

            return 1

    except Exception as e:
        logger.error(f"エラー: {e}")
        return 1

    finally:
        print()
        session.stop()
        print("完了")


if __name__ == '__main__':
    sys.exit(main())
