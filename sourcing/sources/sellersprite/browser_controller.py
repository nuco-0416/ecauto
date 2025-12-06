"""
SellerSprite Browser Controller

Playwright操作の共通基盤を提供。
ページ遷移、エラーハンドリング、スクリーンショット保存などの共通処理を統一。
"""

import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, Callable
from datetime import datetime
from playwright.async_api import Page, Browser, BrowserContext, ElementHandle


class BrowserController:
    """
    Playwrightブラウザ操作の共通コントローラー
    """

    def __init__(
        self,
        page: Page,
        screenshot_dir: Optional[Path] = None,
        verbose: bool = True
    ):
        """
        Args:
            page: Playwrightページオブジェクト
            screenshot_dir: スクリーンショット保存ディレクトリ（デフォルト: sourcing/data/screenshots/）
            verbose: 詳細ログ出力の有効化
        """
        self.page = page
        self.verbose = verbose

        if screenshot_dir is None:
            base_dir = Path(__file__).parent.parent.parent
            screenshot_dir = base_dir / 'data' / 'screenshots'

        self.screenshot_dir = screenshot_dir
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    def log(self, message: str):
        """ログ出力"""
        if self.verbose:
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"[{timestamp}] {message}")

    async def goto(
        self,
        url: str,
        wait_until: str = "domcontentloaded",
        timeout: int = 30000,
        retry: int = 3
    ) -> bool:
        """
        ページ遷移（リトライ機能付き）

        Args:
            url: 遷移先URL
            wait_until: 待機条件（'load', 'domcontentloaded', 'networkidle'）
            timeout: タイムアウト（ミリ秒）
            retry: リトライ回数

        Returns:
            bool: 成功時 True
        """
        for attempt in range(retry):
            try:
                self.log(f"ページ遷移: {url} (試行 {attempt + 1}/{retry})")
                await self.page.goto(url, wait_until=wait_until, timeout=timeout)
                self.log(f"[OK] ページ遷移完了")
                return True

            except Exception as e:
                self.log(f"[WARN] ページ遷移失敗: {e}")
                if attempt < retry - 1:
                    wait_time = 2 ** attempt
                    self.log(f"  {wait_time}秒後にリトライします...")
                    await asyncio.sleep(wait_time)
                else:
                    self.log(f"[ERROR] ページ遷移に失敗しました: {url}")
                    return False

        return False

    async def wait_for_selector(
        self,
        selector: str,
        timeout: int = 10000,
        state: str = "visible"
    ) -> Optional[ElementHandle]:
        """
        セレクタの待機

        Args:
            selector: CSSセレクタ
            timeout: タイムアウト（ミリ秒）
            state: 待機状態（'attached', 'detached', 'visible', 'hidden'）

        Returns:
            ElementHandle または None
        """
        try:
            self.log(f"要素待機: {selector}")
            element = await self.page.wait_for_selector(
                selector,
                timeout=timeout,
                state=state
            )
            self.log(f"[OK] 要素検出")
            return element

        except Exception as e:
            self.log(f"[WARN] 要素が見つかりません: {selector} ({e})")
            return None

    async def click(
        self,
        selector: str,
        timeout: int = 10000,
        wait_after: int = 1000
    ) -> bool:
        """
        要素をクリック

        Args:
            selector: CSSセレクタ
            timeout: タイムアウト（ミリ秒）
            wait_after: クリック後の待機時間（ミリ秒）

        Returns:
            bool: 成功時 True
        """
        try:
            self.log(f"クリック: {selector}")
            await self.page.click(selector, timeout=timeout)
            await asyncio.sleep(wait_after / 1000)
            self.log(f"[OK] クリック完了")
            return True

        except Exception as e:
            self.log(f"[ERROR] クリック失敗: {selector} ({e})")
            return False

    async def fill(
        self,
        selector: str,
        text: str,
        timeout: int = 10000,
        clear_first: bool = True
    ) -> bool:
        """
        テキスト入力

        Args:
            selector: CSSセレクタ
            text: 入力テキスト
            timeout: タイムアウト（ミリ秒）
            clear_first: 入力前にクリア

        Returns:
            bool: 成功時 True
        """
        try:
            self.log(f"テキスト入力: {selector} = '{text}'")

            if clear_first:
                await self.page.fill(selector, "", timeout=timeout)

            await self.page.fill(selector, text, timeout=timeout)
            self.log(f"[OK] 入力完了")
            return True

        except Exception as e:
            self.log(f"[ERROR] 入力失敗: {selector} ({e})")
            return False

    async def select_option(
        self,
        selector: str,
        value: Optional[str] = None,
        label: Optional[str] = None,
        index: Optional[int] = None,
        timeout: int = 10000
    ) -> bool:
        """
        セレクトボックスの選択

        Args:
            selector: CSSセレクタ
            value: option の value 属性
            label: option のテキスト
            index: option のインデックス
            timeout: タイムアウト（ミリ秒）

        Returns:
            bool: 成功時 True
        """
        try:
            option_str = value or label or str(index)
            self.log(f"セレクト選択: {selector} = '{option_str}'")

            if value:
                await self.page.select_option(selector, value=value, timeout=timeout)
            elif label:
                await self.page.select_option(selector, label=label, timeout=timeout)
            elif index is not None:
                await self.page.select_option(selector, index=index, timeout=timeout)
            else:
                raise ValueError("value, label, index のいずれかを指定してください")

            self.log(f"[OK] 選択完了")
            return True

        except Exception as e:
            self.log(f"[ERROR] 選択失敗: {selector} ({e})")
            return False

    async def scroll_to_bottom(self, wait_time: int = 2000):
        """
        ページの最下部までスクロール

        Args:
            wait_time: スクロール後の待機時間（ミリ秒）
        """
        self.log("ページ最下部までスクロール")
        await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(wait_time / 1000)
        self.log("[OK] スクロール完了")

    async def scroll_into_view(self, selector: str):
        """
        要素が表示されるまでスクロール

        Args:
            selector: CSSセレクタ
        """
        try:
            self.log(f"要素までスクロール: {selector}")
            await self.page.evaluate(f"document.querySelector('{selector}').scrollIntoView()")
            await asyncio.sleep(0.5)
            self.log("[OK] スクロール完了")

        except Exception as e:
            self.log(f"[WARN] スクロール失敗: {selector} ({e})")

    async def screenshot(
        self,
        filename: Optional[str] = None,
        full_page: bool = True
    ) -> Path:
        """
        スクリーンショット保存

        Args:
            filename: ファイル名（Noneの場合は自動生成）
            full_page: ページ全体をキャプチャ

        Returns:
            Path: 保存先パス
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp}.png"

        filepath = self.screenshot_dir / filename
        self.log(f"スクリーンショット保存: {filepath}")

        await self.page.screenshot(path=str(filepath), full_page=full_page)
        self.log(f"[OK] 保存完了")

        return filepath

    async def get_text(self, selector: str) -> Optional[str]:
        """
        要素のテキストを取得

        Args:
            selector: CSSセレクタ

        Returns:
            str または None
        """
        try:
            element = await self.page.query_selector(selector)
            if element:
                text = await element.text_content()
                return text.strip() if text else None
            return None

        except Exception as e:
            self.log(f"[WARN] テキスト取得失敗: {selector} ({e})")
            return None

    async def get_attribute(self, selector: str, attribute: str) -> Optional[str]:
        """
        要素の属性を取得

        Args:
            selector: CSSセレクタ
            attribute: 属性名

        Returns:
            str または None
        """
        try:
            element = await self.page.query_selector(selector)
            if element:
                value = await element.get_attribute(attribute)
                return value
            return None

        except Exception as e:
            self.log(f"[WARN] 属性取得失敗: {selector}.{attribute} ({e})")
            return None

    async def extract_table_data(
        self,
        table_selector: str,
        headers: Optional[list] = None
    ) -> list[dict]:
        """
        テーブルデータを抽出

        Args:
            table_selector: テーブルのCSSセレクタ
            headers: カラムヘッダー（Noneの場合は自動検出）

        Returns:
            list[dict]: テーブルデータ
        """
        try:
            self.log(f"テーブルデータ抽出: {table_selector}")

            # ヘッダー自動検出
            if headers is None:
                header_elements = await self.page.query_selector_all(
                    f"{table_selector} thead th"
                )
                headers = []
                for element in header_elements:
                    text = await element.text_content()
                    headers.append(text.strip() if text else "")

            # 行データ抽出
            rows = await self.page.query_selector_all(f"{table_selector} tbody tr")
            data = []

            for row in rows:
                cells = await row.query_selector_all("td")
                row_data = {}

                for i, cell in enumerate(cells):
                    if i < len(headers):
                        text = await cell.text_content()
                        row_data[headers[i]] = text.strip() if text else ""

                if row_data:
                    data.append(row_data)

            self.log(f"[OK] {len(data)}行を抽出")
            return data

        except Exception as e:
            self.log(f"[ERROR] テーブル抽出失敗: {table_selector} ({e})")
            return []

    async def execute_with_retry(
        self,
        func: Callable,
        *args,
        retry: int = 3,
        wait_between: int = 2,
        **kwargs
    ) -> Any:
        """
        関数をリトライ機能付きで実行

        Args:
            func: 実行する非同期関数
            retry: リトライ回数
            wait_between: リトライ間の待機時間（秒）
            *args, **kwargs: 関数の引数

        Returns:
            関数の戻り値
        """
        for attempt in range(retry):
            try:
                result = await func(*args, **kwargs)
                return result

            except Exception as e:
                self.log(f"[WARN] 実行失敗 (試行 {attempt + 1}/{retry}): {e}")
                if attempt < retry - 1:
                    self.log(f"  {wait_between}秒後にリトライします...")
                    await asyncio.sleep(wait_between)
                else:
                    self.log(f"[ERROR] 実行失敗: {func.__name__}")
                    raise

    async def wait_for_navigation(
        self,
        timeout: int = 30000,
        wait_until: str = "domcontentloaded"
    ):
        """
        ナビゲーション完了を待機

        Args:
            timeout: タイムアウト（ミリ秒）
            wait_until: 待機条件
        """
        try:
            self.log("ナビゲーション待機")
            await self.page.wait_for_load_state(wait_until, timeout=timeout)
            self.log("[OK] ナビゲーション完了")

        except Exception as e:
            self.log(f"[WARN] ナビゲーション待機タイムアウト: {e}")
