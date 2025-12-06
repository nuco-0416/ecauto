"""
Amazon Business Session Manager

Chromeプロファイルを使用してセッション情報を永続化します。
Playwrightの launch_persistent_context を使用した確実な実装です。
"""

import asyncio
from pathlib import Path
from typing import Optional, Tuple
from playwright.async_api import (
    async_playwright,
    Playwright,
    BrowserContext,
    Page
)
import json

# プロジェクトルートからの相対インポート
import sys
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from common.browser import ProfileManager


class AmazonBusinessSession:
    """
    Amazonビジネスセッション管理

    Chromeプロファイルを使用してログイン状態を永続化します。
    """

    def __init__(self, account_id: str = "amazon_business_main"):
        """
        Args:
            account_id: アカウントID（デフォルト: "amazon_business_main"）
        """
        self.account_id = account_id
        self.platform = "amazon_business"
        self.profile_manager = ProfileManager()

        # アカウント設定を読み込む
        self.config = self._load_account_config()

    def _load_account_config(self) -> dict:
        """アカウント設定を読み込む"""
        config_path = (
            self.profile_manager.base_dir
            / "platforms"
            / self.platform
            / "accounts"
            / "account_config.json"
        )

        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 指定されたアカウントIDを検索
        for account in data["accounts"]:
            if account["id"] == self.account_id:
                return account

        raise ValueError(f"アカウントID '{self.account_id}' が見つかりません")

    def get_profile_path(self) -> Path:
        """プロファイルパスを取得"""
        return self.profile_manager.get_profile_path(
            self.platform,
            self.account_id
        )

    def profile_exists(self) -> bool:
        """プロファイルが存在するかチェック"""
        return self.profile_manager.profile_exists(
            self.platform,
            self.account_id
        )

    async def launch_browser(
        self,
        headless: bool = False,
        viewport: Optional[dict] = None
    ) -> Tuple[Playwright, BrowserContext, Page]:
        """
        ブラウザを起動

        Args:
            headless: ヘッドレスモード（デフォルト: False）
            viewport: ビューポートサイズ（デフォルト: 1920x1080）

        Returns:
            tuple: (playwright, context, page)
        """
        if viewport is None:
            viewport = {"width": 1920, "height": 1080}

        # プロファイルディレクトリを作成（存在しない場合）
        profile_path = self.profile_manager.create_profile(
            self.platform,
            self.account_id
        )

        print(f"プロファイルパス: {profile_path}")
        print(f"プロファイル存在: {self.profile_exists()}")
        print()

        # Playwrightを起動
        playwright = await async_playwright().start()

        # launch_persistent_context でChromeプロファイルを永続化
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_path),
            headless=headless,
            viewport=viewport,
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-automation",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
            ignore_default_args=["--enable-automation"],
        )

        # 保存されたCookieを読み込む（プロファイルが既存の場合）
        if self.profile_exists():
            await self._load_cookies(context, profile_path)

        # ページを取得（既存ページがあればそれを使用）
        page = context.pages[0] if context.pages else await context.new_page()

        return playwright, context, page

    async def check_login_status(self, page: Page) -> bool:
        """
        ログイン状態を確認

        Args:
            page: Playwrightページオブジェクト

        Returns:
            bool: ログイン済みの場合 True
        """
        try:
            current_url = page.url
            print(f"[DEBUG] 現在のURL: {current_url}")

            # ブランクページの場合のみAmazonにアクセス
            if not current_url or current_url == "about:blank":
                print("[DEBUG] ブランクページです。Amazonにアクセスします...")
                await page.goto(
                    "https://www.amazon.co.jp/",
                    wait_until="domcontentloaded",
                    timeout=30000
                )
                await asyncio.sleep(3)
                current_url = page.url
                print(f"[DEBUG] 遷移後のURL: {current_url}")

            # ログインページにいるかチェック（パス部分のみ）
            from urllib.parse import urlparse
            parsed_url = urlparse(current_url)
            url_path = parsed_url.path.lower()

            if "/ap/signin" in url_path or "/signin" in url_path or "/ap-portal" in url_path or "ap/signin" in url_path:
                print("[INFO] ログインページにいます")
                return False

            # business.amazon.co.jp または amazon.co.jp にいることを確認
            if "business.amazon.co.jp" in current_url or "amazon.co.jp" in current_url:
                print("[DEBUG] Amazonのページにいます")

                # 複数のセレクタでログイン状態を確認
                login_indicators = [
                    "#nav-link-accountList",
                    "a[data-csa-c-content-id='nav_youraccount_btn']",
                    "#nav-your-amazon",
                    "a[href*='nav_youraccount']",
                    ".nav-a[href*='account']",
                    "[aria-label*='アカウント']",
                ]

                for selector in login_indicators:
                    try:
                        element = await page.query_selector(selector)
                        if element:
                            text = await element.text_content()
                            if text and text.strip():
                                text = text.strip()
                                print(f"[DEBUG] セレクタ {selector} のテキスト: {text[:50]}")

                                # 「ログイン」という文字が含まれている場合はログインしていない
                                if "ログイン" in text:
                                    print(f"[DEBUG] 「ログイン」という文字が含まれているため、ログインしていないと判定")
                                    continue

                                # 「こんにちは」という文字が含まれていて、かつ「ログイン」が含まれていない場合はログイン済み
                                # または、アカウント系のセレクタが存在する場合
                                if len(text) > 5:  # 「こんにちは」だけでない実質的なテキスト
                                    print(f"[OK] ログイン済みです（検出: {selector}）")
                                    return True
                    except Exception:
                        continue

                # セレクタが見つからない場合はログイン未完了
                print("[INFO] アカウント要素が見つかりません（ログイン未完了）")
                return False

            print("[INFO] ログイン状態を確認できませんでした")
            return False

        except Exception as e:
            print(f"[ERROR] ログイン確認エラー: {e}")
            return False

    async def _save_cookies(self, context, profile_path: Path):
        """Cookieを明示的に保存"""
        try:
            cookies = await context.cookies()
            cookie_file = profile_path / "cookies.json"
            with open(cookie_file, "w", encoding="utf-8") as f:
                json.dump(cookies, f, indent=2)
            print(f"[DEBUG] Cookieを保存しました: {len(cookies)}件")
        except Exception as e:
            print(f"[WARN] Cookie保存エラー: {e}")

    async def _load_cookies(self, context, profile_path: Path):
        """Cookieを明示的に読み込む"""
        try:
            cookie_file = profile_path / "cookies.json"
            if cookie_file.exists():
                with open(cookie_file, "r", encoding="utf-8") as f:
                    cookies = json.load(f)
                await context.add_cookies(cookies)
                print(f"[DEBUG] Cookieを読み込みました: {len(cookies)}件")
                return True
        except Exception as e:
            print(f"[WARN] Cookie読み込みエラー: {e}")
        return False

    async def manual_login(
        self,
        headless: bool = False,
        max_wait_seconds: int = 300
    ) -> bool:
        """
        手動ログイン

        ブラウザを起動してログインページを開き、ユーザーの手動ログインを待ちます。
        ログイン完了後、プロファイルにセッション情報が自動保存されます。

        Args:
            headless: ヘッドレスモード（手動ログインの場合は False）
            max_wait_seconds: 最大待機時間（秒）

        Returns:
            bool: ログイン成功時 True
        """
        print("=" * 60)
        print("Amazonビジネス - 手動ログイン")
        print("=" * 60)
        print()
        print(f"アカウントID: {self.account_id}")
        print(f"アカウント名: {self.config['name']}")
        print()

        playwright, context, page = await self.launch_browser(headless=headless)

        try:
            # ログインページにアクセス
            login_url = self.config.get(
                "login_url",
                "https://business.amazon.co.jp/"
            )

            print(f"ログインページにアクセス中: {login_url}")
            await page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)

            print()
            print("【手順】")
            print("1. メールアドレス/パスワードでログイン")
            print("2. 2段階認証（必要な場合）を完了")
            print("3. ログインが完了するまで待機します...")
            print()
            print(f"最大 {max_wait_seconds} 秒間待機します")
            print()

            # ログイン完了を監視
            check_interval = 5
            elapsed = 0

            while elapsed < max_wait_seconds:
                await asyncio.sleep(check_interval)
                elapsed += check_interval

                # 全てのページを取得（新しいタブ/ポップアップを含む）
                all_pages = context.pages
                print(f"[DEBUG] 開いているタブ数: {len(all_pages)}")

                # 全てのページでログイン状態を確認
                for i, current_page in enumerate(all_pages):
                    try:
                        current_url = current_page.url
                        print(f"[DEBUG] タブ {i+1} URL: {current_url}")

                        # このページでログイン状態を確認
                        is_logged_in = await self.check_login_status(current_page)

                        if is_logged_in:
                            print()
                            print(f"[OK] ログイン完了を検知しました！（タブ {i+1}）")
                            print()

                            # 追加の待機（セッション情報が完全に保存されるまで）
                            print("セッション情報を保存中...")
                            await asyncio.sleep(5)

                            # Cookieを明示的に保存
                            await self._save_cookies(context, self.get_profile_path())

                            # スクリーンショット保存（最初のページ）
                            screenshot_path = (
                                self.get_profile_path().parent.parent / "login_success.png"
                            )
                            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
                            await all_pages[0].screenshot(path=str(screenshot_path), full_page=True)
                            print(f"[OK] スクリーンショット保存: {screenshot_path}")

                            print(f"[OK] プロファイル保存完了: {self.get_profile_path()}")
                            print()
                            print("次回以降は自動的にログイン状態が復元されます。")

                            return True
                    except Exception as e:
                        print(f"[DEBUG] タブ {i+1} チェック中にエラー: {e}")
                        continue

                # 定期的に進捗を表示
                if elapsed % 30 == 0:
                    print(f"  [{elapsed}秒] ログイン待機中...")

            print()
            print(f"[WARN] タイムアウト: {max_wait_seconds}秒経過しました")
            return False

        except Exception as e:
            print(f"[ERROR] エラー: {e}")
            import traceback
            traceback.print_exc()
            return False

        finally:
            await context.close()
            await playwright.stop()

    async def get_authenticated_context(
        self,
        headless: bool = False
    ) -> Optional[Tuple[Playwright, BrowserContext, Page]]:
        """
        認証済みコンテキストを取得

        プロファイルが存在する場合は自動的にセッションを復元します。
        存在しない場合、またはセッションが無効な場合はNoneを返します。

        Args:
            headless: ヘッドレスモード

        Returns:
            tuple: (playwright, context, page) または None
        """
        print("=" * 60)
        print("Amazonビジネス - セッション確認")
        print("=" * 60)
        print()

        # プロファイルの存在確認
        if not self.profile_exists():
            print("[INFO] プロファイルが見つかりません")
            print("初回ログインが必要です")
            print()
            return None

        print("[OK] プロファイルが見つかりました")
        print()

        # ブラウザを起動（プロファイルから自動復元）
        playwright, context, page = await self.launch_browser(headless=headless)

        # ログイン状態を確認
        print("ログイン状態を確認中...")
        is_logged_in = await self.check_login_status(page)

        if is_logged_in:
            print("[OK] セッションが有効です")
            print()
            return playwright, context, page
        else:
            print("[WARN] セッションが無効です")
            print("再ログインが必要です")
            print()

            # クリーンアップ
            await context.close()
            await playwright.stop()

            return None
