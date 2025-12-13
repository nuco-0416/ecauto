"""
Yahoo Auction Session Manager

Playwrightを使用したYahoo!オークションのセッション管理。
プロキシ経由での接続とプロファイル永続化をサポート。
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any
import sys

from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page, Playwright

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from common.proxy.proxy_manager import ProxyManager
from common.browser.profile_manager import ProfileManager

# ロガー設定
logger = logging.getLogger(__name__)


class YahooAuctionSession:
    """
    Yahoo!オークション セッション管理クラス

    Playwrightを使用してブラウザセッションを管理し、
    プロキシ経由での接続とプロファイル永続化を行う。

    使用例（コンテキストマネージャ）:
        with YahooAuctionSession(account_id="yahoo_01", proxy_id="proxy_01") as page:
            page.goto("https://auctions.yahoo.co.jp/")
            # ページ操作...

    使用例（明示的な開始/終了）:
        session = YahooAuctionSession(account_id="yahoo_01")
        page = session.start()
        try:
            page.goto("https://auctions.yahoo.co.jp/")
            # ページ操作...
        finally:
            session.stop()

    分離要素:
        - IPアドレス: プロキシ経由で分離
        - ブラウザフィンガープリント: プロファイル分離
        - Cookie/Session: プロファイル永続化
        - WebRTC: 無効化オプション
        - タイムゾーン: Asia/Tokyo固定
        - 言語設定: ja-JP固定
    """

    PLATFORM = "yahoo_auction"

    # Yahoo!オークション関連のURL
    URLS = {
        'top': 'https://auctions.yahoo.co.jp/',
        'login': 'https://login.yahoo.co.jp/',
        'mypage': 'https://auctions.yahoo.co.jp/user/jp/show/mystatus',
        'sell': 'https://auctions.yahoo.co.jp/sell/',
    }

    def __init__(
        self,
        account_id: str,
        proxy_id: Optional[str] = None,
        headless: bool = True,
        slow_mo: int = 0
    ):
        """
        Args:
            account_id: アカウントID（例: "yahoo_01"）
            proxy_id: プロキシID（config/proxies.json で定義、Noneの場合はプロキシなし）
            headless: ヘッドレスモード（True=バックグラウンド実行、False=ブラウザ表示）
            slow_mo: 操作間の遅延（ミリ秒、デバッグ用）
        """
        self.account_id = account_id
        self.proxy_id = proxy_id
        self.headless = headless
        self.slow_mo = slow_mo

        # マネージャー初期化
        self.profile_manager = ProfileManager()
        self.proxy_manager = ProxyManager() if proxy_id else None

        # Playwright関連（start()で初期化）
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

        logger.info(f"YahooAuctionSession 初期化: account_id={account_id}, proxy_id={proxy_id}")

    @property
    def profile_path(self) -> Path:
        """プロファイルパスを取得"""
        return self.profile_manager.get_profile_path(self.PLATFORM, self.account_id)

    @property
    def page(self) -> Optional[Page]:
        """現在のページオブジェクトを取得"""
        return self._page

    @property
    def is_active(self) -> bool:
        """セッションがアクティブかどうか"""
        return self._context is not None and self._page is not None

    def _get_browser_args(self) -> list:
        """
        ブラウザ起動引数を取得

        WebRTC無効化やオートメーション検知回避のオプションを含む。
        """
        return [
            # WebRTC無効化（ローカルIP漏洩防止）
            "--disable-webrtc",
            "--disable-features=WebRtcHideLocalIpsWithMdns",
            # オートメーション検知回避
            "--disable-blink-features=AutomationControlled",
            # その他の安定性向上オプション
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ]

    def _get_proxy_config(self) -> Optional[Dict[str, str]]:
        """
        Playwright用のプロキシ設定を取得

        Returns:
            dict: Playwright用のproxy設定
                  {
                      'server': 'http://hostname:port',
                      'username': 'user',
                      'password': 'pass'
                  }
                  プロキシ未設定の場合はNone
        """
        if not self.proxy_id or not self.proxy_manager:
            return None

        proxy_config = self.proxy_manager.get_proxy_for_playwright(self.proxy_id)
        if proxy_config:
            logger.info(f"プロキシを使用: {self.proxy_id} -> {proxy_config.get('server')}")
        else:
            logger.warning(f"プロキシが見つかりません: {self.proxy_id}")

        return proxy_config

    def start(self) -> Page:
        """
        ブラウザセッションを開始

        プロファイルディレクトリを作成し、Playwrightブラウザを起動する。
        launch_persistent_context を使用してセッション情報を永続化する。

        Returns:
            Page: Playwrightページオブジェクト

        Raises:
            RuntimeError: ブラウザの起動に失敗した場合
        """
        if self.is_active:
            logger.warning("セッションは既にアクティブです")
            return self._page

        try:
            # プロファイルディレクトリを作成
            self.profile_manager.create_profile(self.PLATFORM, self.account_id)
            logger.info(f"プロファイルパス: {self.profile_path}")

            # Playwright起動
            self._playwright = sync_playwright().start()

            # 起動オプション
            launch_options = {
                "headless": self.headless,
                "args": self._get_browser_args(),
                "slow_mo": self.slow_mo,
            }

            # プロキシ設定
            proxy_config = self._get_proxy_config()
            if proxy_config:
                launch_options["proxy"] = proxy_config

            # コンテキストオプション（ロケール、タイムゾーン等）
            context_options = {
                "locale": "ja-JP",
                "timezone_id": "Asia/Tokyo",
                "viewport": {"width": 1280, "height": 720},
                "user_agent": None,  # デフォルトを使用
            }

            # persistent_contextでプロファイルを永続化
            # これによりCookie、LocalStorage、セッション情報が保持される
            self._context = self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_path),
                **launch_options,
                **context_options,
            )

            # 既存のページがあれば使用、なければ新規作成
            if self._context.pages:
                self._page = self._context.pages[0]
                logger.info("既存のページを再利用")
            else:
                self._page = self._context.new_page()
                logger.info("新規ページを作成")

            logger.info(f"セッション開始成功: account_id={self.account_id}")
            return self._page

        except Exception as e:
            logger.error(f"セッション開始失敗: {e}")
            self.stop()
            raise RuntimeError(f"ブラウザセッションの開始に失敗しました: {e}")

    def stop(self):
        """
        ブラウザセッションを終了

        コンテキストを閉じ、Playwrightを停止する。
        プロファイルデータは自動的に保存される。
        """
        try:
            if self._context:
                self._context.close()
                logger.info("コンテキストを閉じました")
            if self._playwright:
                self._playwright.stop()
                logger.info("Playwrightを停止しました")
        except Exception as e:
            logger.error(f"セッション終了エラー: {e}")
        finally:
            self._context = None
            self._playwright = None
            self._page = None
            logger.info(f"セッション終了: account_id={self.account_id}")

    def __enter__(self) -> Page:
        """コンテキストマネージャのエントリー"""
        return self.start()

    def __exit__(self, exc_type, exc_val, exc_tb):
        """コンテキストマネージャのイグジット"""
        self.stop()
        return False  # 例外を再送出

    def is_logged_in(self) -> bool:
        """
        Yahoo!オークションへのログイン状態を確認

        マイページにアクセスし、ログインページにリダイレクトされるかどうかで判定。

        Returns:
            bool: ログイン済みの場合True
        """
        if not self._page:
            logger.warning("ページが初期化されていません")
            return False

        try:
            # マイページにアクセス
            self._page.goto(self.URLS['mypage'], wait_until='domcontentloaded', timeout=30000)

            # ログインページにリダイレクトされたかチェック
            current_url = self._page.url
            if "login.yahoo.co.jp" in current_url:
                logger.info("ログインが必要です")
                return False

            # マイページが表示されているかチェック
            if "auctions.yahoo.co.jp" in current_url and "mystatus" in current_url:
                logger.info("ログイン済みです")
                return True

            # その他の場合（エラーページなど）
            logger.warning(f"不明なページ: {current_url}")
            return False

        except Exception as e:
            logger.error(f"ログイン状態確認エラー: {e}")
            return False

    def goto_login_page(self) -> Page:
        """
        ログインページに移動

        Returns:
            Page: ページオブジェクト
        """
        if not self._page:
            raise RuntimeError("セッションが開始されていません")

        self._page.goto(self.URLS['login'], wait_until='domcontentloaded', timeout=30000)
        logger.info("ログインページに移動しました")
        return self._page

    def goto_top_page(self) -> Page:
        """
        Yahoo!オークショントップページに移動

        Returns:
            Page: ページオブジェクト
        """
        if not self._page:
            raise RuntimeError("セッションが開始されていません")

        self._page.goto(self.URLS['top'], wait_until='domcontentloaded', timeout=30000)
        logger.info("トップページに移動しました")
        return self._page

    def wait_for_manual_login(self, timeout: int = 300) -> bool:
        """
        手動ログインを待機

        ログインページを表示し、ユーザーが手動でログインするのを待つ。
        ログインが完了するとセッション情報がプロファイルに保存される。

        Args:
            timeout: タイムアウト秒数（デフォルト5分）

        Returns:
            bool: ログイン成功時True
        """
        if not self._page:
            raise RuntimeError("セッションが開始されていません")

        logger.info(f"手動ログインを待機中... (タイムアウト: {timeout}秒)")
        logger.info("ブラウザでYahoo! JAPAN IDでログインしてください")

        try:
            # ログインページに移動
            self.goto_login_page()

            # ログイン完了を待機（URLがauctions.yahoo.co.jpに変わるまで）
            self._page.wait_for_url(
                "**/auctions.yahoo.co.jp/**",
                timeout=timeout * 1000,
                wait_until='domcontentloaded'
            )

            logger.info("ログインが完了しました")
            return True

        except Exception as e:
            logger.error(f"手動ログイン待機エラー: {e}")
            return False

    def take_screenshot(self, filename: str = None) -> str:
        """
        スクリーンショットを撮影

        Args:
            filename: ファイル名（Noneの場合は自動生成）

        Returns:
            str: 保存先パス
        """
        if not self._page:
            raise RuntimeError("セッションが開始されていません")

        if filename is None:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{self.account_id}_{timestamp}.png"

        # スクリーンショット保存先
        screenshot_dir = self.profile_path / "screenshots"
        screenshot_dir.mkdir(exist_ok=True)
        filepath = screenshot_dir / filename

        self._page.screenshot(path=str(filepath))
        logger.info(f"スクリーンショット保存: {filepath}")

        return str(filepath)
