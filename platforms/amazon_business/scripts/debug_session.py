#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Amazon Business - セッションデバッグ

現在のブラウザ状態を確認するデバッグスクリプト
"""

import asyncio
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from platforms.amazon_business.browser import AmazonBusinessSession


async def main():
    """メイン処理"""
    print()
    print("=" * 60)
    print("Amazon Business - セッションデバッグ")
    print("=" * 60)
    print()

    session = AmazonBusinessSession(account_id="amazon_business_main")

    # ブラウザを起動
    playwright, context, page = await session.launch_browser(headless=False)

    try:
        print("現在のページ情報:")
        print(f"  URL: {page.url}")
        print(f"  タイトル: {await page.title()}")
        print()

        # Amazon Business のホームページにアクセスせずに現在のURLをチェック
        current_url = page.url

        if not current_url or current_url == "about:blank":
            print("ブランクページです。Amazonビジネスにアクセスします...")
            await page.goto("https://business.amazon.co.jp/", wait_until="domcontentloaded")
            await asyncio.sleep(3)
            current_url = page.url

        print()
        print(f"現在のURL: {current_url}")
        print()

        # URLベースでログイン状態を判定
        if "signin" in current_url or "ap/signin" in current_url:
            print("❌ ログインページにいます")
        else:
            print("✅ ログインページではありません")

        # いくつかの要素をチェック
        print()
        print("要素のチェック:")

        selectors = [
            "#nav-link-accountList",
            "a[data-csa-c-content-id='nav_youraccount_btn']",
            "#nav-your-amazon",
            "[data-nav-role='signin']",
            "a[href*='nav_youraccount']",
            ".nav-a[href*='account']",
        ]

        for selector in selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    text = await element.text_content()
                    print(f"  ✅ {selector}: 存在 (テキスト: {text.strip()[:50]})")
                else:
                    print(f"  ❌ {selector}: 存在しない")
            except Exception as e:
                print(f"  ❌ {selector}: エラー ({e})")

        print()
        print("30秒間ブラウザを開いたままにします...")
        print("手動で要素を確認できます")
        await asyncio.sleep(30)

    finally:
        await context.close()
        await playwright.stop()


if __name__ == "__main__":
    asyncio.run(main())
