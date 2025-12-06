#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SellerSprite 認証管理

レガシーコード（sellersprite_auth.py）を流用して、
ecautoプロジェクト用に調整したバージョン。

Cookie ベースの自動ログイン機能を提供。

使用例:
    from sourcing.sources.sellersprite.auth_manager import get_authenticated_browser

    async def your_task():
        result = await get_authenticated_browser()
        if result is None:
            print("認証失敗")
            return

        browser, context, page, p = result

        try:
            await page.goto("https://www.sellersprite.com/...")
            # 作業実行
        finally:
            await browser.close()
            await p.stop()
"""

import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from playwright.async_api import async_playwright

# Windows環境での文字コード問題を解決
if sys.platform == 'win32':
    import codecs
    if sys.stdout.encoding != 'utf-8':
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    if sys.stderr.encoding != 'utf-8':
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# 環境変数サポート
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenvがインストールされていない場合はスキップ


# ecautoプロジェクト用のCookieパスとChromeプロファイルディレクトリ
COOKIE_FILE = Path(__file__).parent.parent.parent / 'data' / 'sellersprite_cookies.json'
USER_DATA_DIR = Path(__file__).parent.parent.parent / 'data' / 'chrome_profile'


def check_cookie_expiry():
    """
    保存された Cookie の有効期限をチェック

    Returns:
        dict: {
            'exists': bool,
            'valid': bool,
            'expired_count': int,
            'total_count': int,
            'expires_soon': list,
            'message': str
        }
    """
    if not COOKIE_FILE.exists():
        return {
            'exists': False,
            'valid': False,
            'expired_count': 0,
            'total_count': 0,
            'expires_soon': [],
            'message': 'Cookie ファイルが見つかりません'
        }

    with open(COOKIE_FILE, 'r', encoding='utf-8') as f:
        cookies = json.load(f)

    now = datetime.now(timezone.utc).timestamp()
    one_day_later = now + (24 * 60 * 60)

    expired_count = 0
    expires_soon = []

    for cookie in cookies:
        if 'expires' in cookie and cookie['expires'] != -1:
            expires = cookie['expires']
            if expires < now:
                expired_count += 1
            elif expires < one_day_later:
                hours_left = (expires - now) / 3600
                expires_soon.append({
                    'name': cookie['name'],
                    'hours_left': round(hours_left, 1)
                })

    total_count = len(cookies)
    valid = expired_count == 0

    if expired_count > 0:
        message = f'{expired_count}/{total_count} 件の Cookie が期限切れです'
    elif expires_soon:
        message = f'{len(expires_soon)} 件の Cookie が24時間以内に期限切れになります'
    else:
        message = 'すべての Cookie が有効です'

    return {
        'exists': True,
        'valid': valid,
        'expired_count': expired_count,
        'total_count': total_count,
        'expires_soon': expires_soon,
        'message': message
    }


async def manual_login():
    """
    手動ログインして Cookie を保存
    Chromeプロファイルを永続化してセッション情報を保持

    Returns:
        bool: ログイン成功時 True
    """
    print("=" * 60)
    print("手動ログイン")
    print("=" * 60)
    print()

    # Chromeプロファイルディレクトリを作成
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        # launch_persistent_context を使用してChromeプロファイルを永続化
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,
            viewport={"width": 1920, "height": 1080},
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-automation',
                '--disable-dev-shm-usage',
                '--no-sandbox',
            ],
            ignore_default_args=['--enable-automation'],
        )

        page = context.pages[0] if context.pages else await context.new_page()

        try:
            print("ログインページにアクセス中...")
            await page.goto("https://www.sellersprite.com/jp/w/user/login",
                           wait_until="domcontentloaded",
                           timeout=30000)
            await page.wait_for_timeout(2000)

            print("\n【手順】")
            print("1. Googleログインボタンをクリック")
            print("2. Google認証を完了")
            print("3. 自動的にログイン完了を検知します")
            print()

            # ログイン完了を自動検知
            print("ログイン完了を監視中...\n")

            max_wait_time = 180
            check_interval = 3
            elapsed = 0
            login_successful = False

            while elapsed < max_wait_time:
                await page.wait_for_timeout(check_interval * 1000)
                elapsed += check_interval

                current_url = page.url

                if 'login' not in current_url and 'google.com' not in current_url:
                    try:
                        cookies = await context.cookies()
                        has_guest = any(c['name'] == 'current_guest' for c in cookies)
                        has_jsession = any(c['name'] == 'JSESSIONID' for c in cookies)

                        if has_jsession and not has_guest and '/v2/welcome' in current_url:
                            # 5秒待機して状態を確認
                            await page.wait_for_timeout(5000)

                            cookies_recheck = await context.cookies()
                            has_guest_recheck = any(c['name'] == 'current_guest' for c in cookies_recheck)

                            if not has_guest_recheck:
                                print("[OK] ログイン完了を検知しました！\n")
                                login_successful = True
                                break
                    except Exception:
                        pass

                elif elapsed % 15 == 0:
                    print(f"  [{elapsed}秒] 待機中...")

            if login_successful:
                print("Cookie を保存中...")
                # 追加の待機時間: すべてのCookieが設定されるのを待つ
                await page.wait_for_timeout(10000)

                cookies = await context.cookies()
                sellersprite_cookies = [
                    c for c in cookies
                    if 'sellersprite.com' in c.get('domain', '') and c.get('name') != 'current_guest'
                ]

                # Cookieファイルの親ディレクトリを作成
                COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)

                with open(COOKIE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(sellersprite_cookies, f, indent=2, ensure_ascii=False)

                print(f"[OK] Cookie 保存完了: {COOKIE_FILE} ({len(sellersprite_cookies)} 件)")
                print(f"[OK] Chromeプロファイル保存: {USER_DATA_DIR}")

                # スクリーンショット保存
                screenshot_path = COOKIE_FILE.parent / "login_success.png"
                await page.screenshot(path=str(screenshot_path), full_page=True)
                print(f"[OK] スクリーンショット: {screenshot_path}")

                return True
            else:
                print("\n[WARN] タイムアウト: ログイン完了を検知できませんでした")
                return False

        except Exception as e:
            print(f"\n[ERROR] エラー: {str(e)}")
            return False
        finally:
            await context.close()


async def auto_login():
    """
    Google認証情報を使用した自動ログイン
    環境変数からGOOGLE_EMAILとGOOGLE_PASSWORDを読み込む

    Returns:
        bool: ログイン成功時 True

    使用方法:
        .envファイルに以下を設定:
        GOOGLE_EMAIL=your_email@gmail.com
        GOOGLE_PASSWORD=your_password
    """
    print("=" * 60)
    print("自動ログイン（Google認証）")
    print("=" * 60)
    print()

    # 環境変数から認証情報を取得
    google_email = os.getenv('GOOGLE_EMAIL')
    google_password = os.getenv('GOOGLE_PASSWORD')

    if not google_email or not google_password:
        print("[ERROR] 環境変数 GOOGLE_EMAIL と GOOGLE_PASSWORD が設定されていません")
        print("\n.envファイルに以下を設定してください:")
        print("  GOOGLE_EMAIL=your_email@gmail.com")
        print("  GOOGLE_PASSWORD=your_password")
        return False

    print(f"Google Email: {google_email}")
    print()

    # Chromeプロファイルディレクトリを作成
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        # launch_persistent_context を使用してChromeプロファイルを永続化
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,
            viewport={"width": 1920, "height": 1080},
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-automation',
                '--disable-dev-shm-usage',
                '--no-sandbox',
            ],
            ignore_default_args=['--enable-automation'],
        )

        page = context.pages[0] if context.pages else await context.new_page()

        try:
            print("SellerSpriteログインページにアクセス中...")
            await page.goto("https://www.sellersprite.com/jp/w/user/login",
                           wait_until="domcontentloaded",
                           timeout=30000)
            await page.wait_for_timeout(3000)

            print("Googleログインボタンをクリック中...")

            # 複数の方法でGoogleログインボタンを探す
            login_clicked = False

            # 方法1: iframeのタイトルでフレームを特定し、最初のボタンをクリック
            try:
                print("  試行1: iframe内の最初のボタンをクリック...")
                google_login_frame = page.frame_locator('iframe[title*="Google"]')
                await google_login_frame.locator('button').first.click(timeout=10000)
                print("[OK] Googleログインボタンをクリックしました（方法1）")
                login_clicked = True
            except Exception as e1:
                print(f"  試行1失敗: {e1}")

                # 方法2: iframeのsrc属性でフレームを特定
                try:
                    print("  試行2: iframe src属性で特定...")
                    google_login_frame = page.frame_locator('iframe[src*="accounts.google.com"]')
                    await google_login_frame.locator('button').first.click(timeout=10000)
                    print("[OK] Googleログインボタンをクリックしました（方法2）")
                    login_clicked = True
                except Exception as e2:
                    print(f"  試行2失敗: {e2}")

                    # 方法3: divのrole="button"を試行
                    try:
                        print("  試行3: div[role=button]を試行...")
                        google_login_frame = page.frame_locator('iframe[title*="Google"]')
                        await google_login_frame.locator('div[role="button"]').first.click(timeout=10000)
                        print("[OK] Googleログインボタンをクリックしました（方法3）")
                        login_clicked = True
                    except Exception as e3:
                        print(f"  試行3失敗: {e3}")

                        # 方法4: 直接リンクを探す（フォールバック）
                        try:
                            print("  試行4: 直接リンクを探索...")
                            google_link = page.locator('a:has-text("Google")')
                            await google_link.click(timeout=5000)
                            print("[OK] Googleログインリンクをクリックしました（方法4）")
                            login_clicked = True
                        except Exception as e4:
                            print(f"  試行4失敗: {e4}")
                            print(f"[ERROR] すべての方法でGoogleログインボタンが見つかりませんでした")
                            return False

            if not login_clicked:
                print("[ERROR] Googleログインボタンをクリックできませんでした")
                return False

            # Googleログインページに遷移
            await page.wait_for_url(re.compile(r'accounts\.google\.com'), timeout=10000)
            print("[OK] Googleログインページに遷移しました")

            # メールアドレスを入力
            print("メールアドレスを入力中...")
            email_input = page.get_by_role('textbox', name=re.compile(r'メール|email', re.IGNORECASE))
            await email_input.fill(google_email)
            print("[OK] メールアドレス入力完了")

            # 「次へ」ボタンをクリック
            next_button = page.get_by_role('button', name=re.compile(r'次へ|Next', re.IGNORECASE))
            await next_button.click()
            print("[OK] 次へボタンをクリックしました")

            # パスワード入力画面を待機
            await page.wait_for_url(re.compile(r'challenge/pwd'), timeout=10000)
            print("[OK] パスワード入力画面に遷移しました")

            # パスワードを入力
            print("パスワードを入力中...")
            password_input = page.get_by_role('textbox', name=re.compile(r'パスワード|password', re.IGNORECASE)).or_(page.locator('input[type="password"]'))
            await password_input.fill(google_password)
            print("[OK] パスワード入力完了")

            # 「次へ」ボタンをクリック
            next_button = page.get_by_role('button', name=re.compile(r'次へ|Next', re.IGNORECASE))
            await next_button.click()
            print("[OK] 次へボタンをクリックしました")

            # 2段階認証の画面まで待機
            print("\n2段階認証の処理を待機中...")
            await page.wait_for_timeout(5000)

            current_url = page.url

            if 'challenge/dp' in current_url or 'challenge/az' in current_url:
                print("\n[INFO] 2段階認証の画面に到達しました")
                print("スマホでGmailアプリを開いて「はい」をタップして認証を完了してください")
                print("または、認証コードを入力してください")
                print("\n最大180秒待機します...")

                # 2段階認証完了を待機
                max_wait = 180
                check_interval = 5
                elapsed = 0

                while elapsed < max_wait:
                    await page.wait_for_timeout(check_interval * 1000)
                    elapsed += check_interval

                    current_url = page.url

                    # SellerSpriteに戻ったかチェック
                    if 'sellersprite.com' in current_url and 'login' not in current_url:
                        print("\n[OK] 2段階認証完了を検出しました！")
                        break

                    if elapsed % 15 == 0:
                        print(f"  [{elapsed}秒] 認証待機中...")

            # SellerSpriteへのリダイレクトを待機
            print("\nSellerSpriteへのリダイレクトを待機中...")
            max_wait_redirect = 60
            elapsed_redirect = 0

            while elapsed_redirect < max_wait_redirect:
                await page.wait_for_timeout(2000)
                elapsed_redirect += 2

                current_url = page.url

                if 'sellersprite.com' in current_url and 'login' not in current_url:
                    print("[OK] SellerSpriteにログイン完了しました")
                    break

                if elapsed_redirect % 10 == 0:
                    print(f"  [{elapsed_redirect}秒] リダイレクト待機中...")

            # ログイン完了確認
            if 'sellersprite.com' in page.url and 'login' not in page.url:
                print("\nCookie を保存中...")
                await page.wait_for_timeout(10000)

                cookies = await context.cookies()
                sellersprite_cookies = [
                    c for c in cookies
                    if 'sellersprite.com' in c.get('domain', '') and c.get('name') != 'current_guest'
                ]

                # Cookieファイルの親ディレクトリを作成
                COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)

                with open(COOKIE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(sellersprite_cookies, f, indent=2, ensure_ascii=False)

                print(f"[OK] Cookie 保存完了: {COOKIE_FILE} ({len(sellersprite_cookies)} 件)")
                print(f"[OK] Chromeプロファイル保存: {USER_DATA_DIR}")

                # スクリーンショット保存
                screenshot_path = COOKIE_FILE.parent / "auto_login_success.png"
                await page.screenshot(path=str(screenshot_path), full_page=True)
                print(f"[OK] スクリーンショット: {screenshot_path}")

                return True
            else:
                print("\n[WARN] ログイン完了を確認できませんでした")
                return False

        except Exception as e:
            print(f"\n[ERROR] エラー: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            await context.close()


async def direct_login():
    """
    メールアドレス/パスワードで直接ログイン
    環境変数からSELLERSPRITE_EMAILとSELLERSPRITE_PASSWORDを読み込む

    Returns:
        bool: ログイン成功時 True

    使用方法:
        .envファイルに以下を設定:
        SELLERSPRITE_EMAIL=your_email@example.com
        SELLERSPRITE_PASSWORD=your_password
    """
    print("=" * 60)
    print("直接ログイン（メールアドレス/パスワード）")
    print("=" * 60)
    print()

    # 環境変数から認証情報を取得
    email = os.getenv('SELLERSPRITE_EMAIL')
    password = os.getenv('SELLERSPRITE_PASSWORD')

    if not email or not password:
        print("[ERROR] 環境変数 SELLERSPRITE_EMAIL と SELLERSPRITE_PASSWORD が設定されていません")
        print("\n.envファイルに以下を設定してください:")
        print("  SELLERSPRITE_EMAIL=your_email@example.com")
        print("  SELLERSPRITE_PASSWORD=your_password")
        return False

    print(f"Email: {email}")
    print()

    # Chromeプロファイルディレクトリを作成
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        # launch_persistent_context を使用してChromeプロファイルを永続化
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,
            viewport={"width": 1920, "height": 1080},
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-automation',
                '--disable-dev-shm-usage',
                '--no-sandbox',
            ],
            ignore_default_args=['--enable-automation'],
        )

        page = context.pages[0] if context.pages else await context.new_page()

        try:
            # ログインページにアクセス
            print("ログインページにアクセス中...")
            await page.goto("https://www.sellersprite.com/jp/w/user/login",
                           wait_until="networkidle",
                           timeout=30000)
            print("[OK] ログインページ読み込み完了")

            # メールアドレス/パスワード認証
            print("\nメールアドレス/パスワードでログイン中...")

            # メールアドレス入力
            print("  メールアドレス入力中...")
            email_input = page.get_by_role('textbox', name=re.compile(r'メールアドレス|アカウント', re.IGNORECASE))
            await email_input.fill(email)
            await page.wait_for_timeout(1000)
            print("  [OK] メールアドレス入力完了")

            # パスワード入力
            print("  パスワード入力中...")
            password_input = page.get_by_role('textbox', name=re.compile(r'パスワード', re.IGNORECASE))
            await password_input.fill(password)
            await page.wait_for_timeout(1000)
            print("  [OK] パスワード入力完了")

            # ログインボタンをクリック
            print("  ログインボタンをクリック中...")
            login_button = page.get_by_role('button', name=re.compile(r'ログイン', re.IGNORECASE))
            await login_button.click()
            print("  [OK] ログインボタンをクリックしました")

            # ログイン完了を待機（welcomeページまたはdashboardページ）
            print("\nログイン完了を待機中...")
            try:
                await page.wait_for_url(re.compile(r'/(welcome|dashboard)'), timeout=30000)
                print("[OK] ログイン成功！")
            except Exception as e:
                print(f"[WARN] URL遷移の待機がタイムアウトしました: {e}")
                # URLチェックで確認
                current_url = page.url
                if 'login' not in current_url:
                    print("[OK] ログインページから離脱しました（ログイン成功の可能性大）")
                else:
                    print("[ERROR] まだログインページにいます")
                    return False

            # セッション初期化のため、product-researchページにアクセス
            print("\nセッション初期化のため商品リサーチページにアクセス中...")
            await page.goto("https://www.sellersprite.com/v3/product-research?market=JP",
                           wait_until="networkidle",
                           timeout=30000)
            print("[OK] 商品リサーチページにアクセスしました")

            # Cookie を保存
            print("\nCookie を保存中...")
            await page.wait_for_timeout(5000)  # Cookie設定の待機

            cookies = await context.cookies()
            sellersprite_cookies = [
                c for c in cookies
                if 'sellersprite.com' in c.get('domain', '') and c.get('name') != 'current_guest'
            ]

            # Cookieファイルの親ディレクトリを作成
            COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)

            with open(COOKIE_FILE, 'w', encoding='utf-8') as f:
                json.dump(sellersprite_cookies, f, indent=2, ensure_ascii=False)

            print(f"[OK] Cookie 保存完了: {COOKIE_FILE} ({len(sellersprite_cookies)} 件)")
            print(f"[OK] Chromeプロファイル保存: {USER_DATA_DIR}")

            # スクリーンショット保存
            screenshot_path = COOKIE_FILE.parent / "direct_login_success.png"
            await page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"[OK] スクリーンショット: {screenshot_path}")

            return True

        except Exception as e:
            print(f"\n[ERROR] エラー: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            await context.close()


async def get_authenticated_browser():
    """
    認証済みのブラウザコンテキストを取得
    Chromeプロファイルを使用してセッション情報を永続化
    Cookie が無効な場合は手動ログインを促す

    Returns:
        tuple: (context, page, playwright) または None
        注: launch_persistent_context使用のため、contextを返す（browserは存在しない）
    """
    print("=" * 60)
    print("SellerSprite 認証チェック")
    print("=" * 60)
    print()

    # Chromeプロファイルの存在チェック
    profile_exists = USER_DATA_DIR.exists() and any(USER_DATA_DIR.iterdir())

    # Cookie の有効期限チェック（参考情報として）
    cookie_status = check_cookie_expiry()

    print(f"Chromeプロファイル: {'存在' if profile_exists else '未作成'}")
    print(f"Cookie ステータス: {cookie_status['message']}")

    if cookie_status['expired_count'] > 0:
        print(f"  期限切れ: {cookie_status['expired_count']}/{cookie_status['total_count']} 件")

    if cookie_status['expires_soon']:
        print(f"  まもなく期限切れ:")
        for cookie in cookie_status['expires_soon']:
            print(f"    - {cookie['name']}: あと {cookie['hours_left']} 時間")

    print()

    # プロファイルもCookieも存在しない場合は手動ログイン
    if not profile_exists and (not cookie_status['exists'] or not cookie_status['valid']):
        print("[WARN] 認証情報がありません")
        print("\n手動ログインが必要です")

        response = input("今すぐログインしますか？ (y/n): ").strip().lower()

        if response == 'y':
            success = await manual_login()
            if not success:
                print("\n[ERROR] ログインに失敗しました")
                return None
        else:
            print("\nログインをキャンセルしました")
            return None
    else:
        if profile_exists:
            print("[OK] Chromeプロファイルが見つかりました")
        else:
            print("[INFO] Cookieを使用して認証します")

    # Chromeプロファイルディレクトリを作成（存在しない場合）
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

    # ブラウザを起動（launch_persistent_context使用）
    print("\nブラウザを起動中...")

    p = await async_playwright().start()
    context = await p.chromium.launch_persistent_context(
        user_data_dir=str(USER_DATA_DIR),
        headless=False,
        viewport={"width": 1920, "height": 1080},
        locale="ja-JP",
        timezone_id="Asia/Tokyo",
        args=[
            '--disable-blink-features=AutomationControlled',
            '--disable-automation',
            '--disable-dev-shm-usage',
            '--no-sandbox',
        ],
        ignore_default_args=['--enable-automation'],
    )

    # プロファイルが新規作成の場合、Cookieを読み込む（互換性のため）
    if not profile_exists and cookie_status['exists']:
        print("初回起動: Cookieを読み込み中...")
        try:
            with open(COOKIE_FILE, 'r', encoding='utf-8') as f:
                cookies = json.load(f)
            await context.add_cookies(cookies)
            print("[OK] Cookie読み込み完了")
        except Exception as e:
            print(f"[WARN] Cookie読み込みエラー: {e}")

    page = context.pages[0] if context.pages else await context.new_page()

    # ログイン状態を確認
    print("ログイン状態を確認中...")
    await page.goto("https://www.sellersprite.com/v2/welcome",
                   wait_until="domcontentloaded",
                   timeout=30000)
    await page.wait_for_timeout(3000)

    current_url = page.url

    if 'login' in current_url:
        print("\n[ERROR] ログインページにリダイレクトされました")
        print("セッションが期限切れの可能性があります")

        await context.close()
        await p.stop()

        # 環境変数が設定されている場合は自動的にdirect_loginを試行
        email = os.getenv('SELLERSPRITE_EMAIL')
        if email:
            print("\n環境変数が設定されているため、自動的に再ログインを試みます...")
            success = await direct_login()
            if success:
                print("\n再度ブラウザを起動します...")
                return await get_authenticated_browser()
            else:
                print("\n[ERROR] 自動ログインに失敗しました")
                return None

        # 環境変数がない場合は手動ログインを試行
        print("\n手動ログインを実行します...")
        success = await manual_login()

        if success:
            print("\n再度ブラウザを起動します...")
            return await get_authenticated_browser()
        else:
            return None

    # ゲストモードチェック
    current_cookies = await context.cookies()
    has_guest = any(c['name'] == 'current_guest' for c in current_cookies)

    if has_guest:
        print("\n[WARN] ゲストモードです")
        print("セッションが無効です")

        await context.close()
        await p.stop()

        # 環境変数が設定されている場合は自動的にdirect_loginを試行
        email = os.getenv('SELLERSPRITE_EMAIL')
        if email:
            print("\n環境変数が設定されているため、自動的に再ログインを試みます...")
            success = await direct_login()
            if success:
                print("\n再度ブラウザを起動します...")
                return await get_authenticated_browser()
            else:
                print("\n[ERROR] 自動ログインに失敗しました")
                return None

        # 環境変数がない場合は対話的に確認
        try:
            response = input("\n手動ログインを実行しますか？ (y/n): ").strip().lower()
            if response == 'y':
                success = await manual_login()
                if success:
                    return await get_authenticated_browser()
        except EOFError:
            print("\n[ERROR] 標準入力が利用できません")
            print("環境変数 SELLERSPRITE_EMAIL と SELLERSPRITE_PASSWORD を設定してください")

        return None

    print("[OK] ログイン成功！")
    print(f"現在のURL: {current_url}")
    print()

    # 注: launch_persistent_context使用のため、browserオブジェクトは存在しない
    # 互換性のため、contextをbrowserの位置に返す
    return (context, context, page, p)


async def example_usage():
    """
    使用例：認証済みブラウザを取得して作業を実行
    """
    result = await get_authenticated_browser()

    if result is None:
        print("認証に失敗しました")
        return

    # 注: launch_persistent_context使用のため、browserとcontextは同じ
    browser, context, page, p = result

    try:
        print("=" * 60)
        print("作業を実行中...")
        print("=" * 60)
        print()

        # ここで実際の作業を行う
        title = await page.title()
        print(f"ページタイトル: {title}")

        # 30秒間ブラウザを開いたまま
        print("\nブラウザを30秒間開いたままにします...")
        await page.wait_for_timeout(30000)

    except Exception as e:
        print(f"[ERROR] エラー: {e}")
    finally:
        await context.close()
        await p.stop()
        print("\nブラウザを閉じました")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == "check":
            # Cookie の状態を確認
            status = check_cookie_expiry()
            print("=" * 60)
            print("Cookie ステータス")
            print("=" * 60)
            print(f"存在: {status['exists']}")
            print(f"有効: {status['valid']}")
            print(f"メッセージ: {status['message']}")
            if status['expires_soon']:
                print("\nまもなく期限切れ:")
                for cookie in status['expires_soon']:
                    print(f"  - {cookie['name']}: あと {cookie['hours_left']} 時間")

        elif sys.argv[1] == "login":
            # 手動ログインのみ実行
            asyncio.run(manual_login())

        elif sys.argv[1] == "auto_login":
            # 自動ログイン実行（Google認証・環境変数使用）
            asyncio.run(auto_login())

        elif sys.argv[1] == "direct_login":
            # 直接ログイン実行（メールアドレス/パスワード・環境変数使用）
            asyncio.run(direct_login())

        else:
            print("使用方法:")
            print("  python auth_manager.py                  # 例を実行")
            print("  python auth_manager.py check            # Cookie の状態確認")
            print("  python auth_manager.py login            # 手動ログインのみ")
            print("  python auth_manager.py auto_login       # 自動ログイン（Google認証）")
            print("  python auth_manager.py direct_login     # 直接ログイン（メールアドレス/パスワード）")
    else:
        # デフォルト: 例を実行
        asyncio.run(example_usage())
