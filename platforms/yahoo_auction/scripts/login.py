"""
Yahoo Auction Login Script

Yahoo!オークションへの初回ログインを行うスクリプト。
ブラウザを表示して手動でログインし、セッション情報をプロファイルに保存する。

使用例:
    python -m platforms.yahoo_auction.scripts.login --account-id yahoo_01
    python -m platforms.yahoo_auction.scripts.login --account-id yahoo_01 --proxy-id proxy_01
"""

import argparse
import logging
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from platforms.yahoo_auction.browser.session import YahooAuctionSession

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(
        description='Yahoo!オークションへのログインを行います',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
  # アカウント yahoo_01 でログイン
  python -m platforms.yahoo_auction.scripts.login --account-id yahoo_01

  # プロキシを指定してログイン
  python -m platforms.yahoo_auction.scripts.login --account-id yahoo_01 --proxy-id proxy_01

  # タイムアウトを10分に設定
  python -m platforms.yahoo_auction.scripts.login --account-id yahoo_01 --timeout 600
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
        '--timeout',
        type=int,
        default=300,
        help='ログイン待機タイムアウト秒数（デフォルト: 300秒=5分）'
    )

    args = parser.parse_args()

    print("=" * 60)
    print("Yahoo!オークション ログインスクリプト")
    print("=" * 60)
    print(f"アカウントID: {args.account_id}")
    if args.proxy_id:
        print(f"プロキシID: {args.proxy_id}")
    print(f"タイムアウト: {args.timeout}秒")
    print("=" * 60)
    print()

    # セッション開始（headless=False でブラウザを表示）
    session = YahooAuctionSession(
        account_id=args.account_id,
        proxy_id=args.proxy_id,
        headless=False  # ブラウザを表示
    )

    try:
        print("ブラウザを起動中...")
        page = session.start()

        # 既存のログイン状態を確認
        print("ログイン状態を確認中...")
        if session.is_logged_in():
            print()
            print("[OK] 既にログイン済みです")
            print("プロファイルにセッション情報が保存されています")
            return 0

        print()
        print("-" * 60)
        print("手動でログインしてください")
        print("-" * 60)
        print()
        print("1. ブラウザが開きます")
        print("2. Yahoo! JAPAN IDとパスワードでログインしてください")
        print("3. ログインが完了すると自動的に検出されます")
        print()
        print(f"（タイムアウト: {args.timeout}秒）")
        print()

        # 手動ログインを待機
        if session.wait_for_manual_login(timeout=args.timeout):
            print()
            print("[OK] ログインに成功しました")
            print(f"プロファイル保存先: {session.profile_path}")

            # スクリーンショットを撮影
            screenshot_path = session.take_screenshot("login_success.png")
            print(f"スクリーンショット: {screenshot_path}")

            return 0
        else:
            print()
            print("[ERROR] ログインに失敗しました（タイムアウト）")
            return 1

    except KeyboardInterrupt:
        print()
        print("中断されました")
        return 1

    except Exception as e:
        logger.error(f"エラー: {e}")
        return 1

    finally:
        print()
        print("ブラウザを閉じています...")
        session.stop()
        print("完了")


if __name__ == '__main__':
    sys.exit(main())
