"""
Amazon 住所録クリーンアップタスク

指定した名前以外の住所をすべて削除する処理
"""

import asyncio
from playwright.async_api import Page, TimeoutError as PlaywrightTimeout


async def cleanup_addresses(
    page: Page,
    exclude_names: list = None,
    address_page_url: str = "https://www.amazon.co.jp/a/addresses",
    max_attempts: int = 100
) -> dict:
    """
    Amazonの住所録ページで、指定した名前以外の住所をすべて削除する

    Args:
        page: Playwrightページオブジェクト
        exclude_names: 削除しない住所の名前リスト（これらの名前の住所は残す）
        address_page_url: 住所録ページのURL
        max_attempts: 最大試行回数（無限ループ防止）

    Returns:
        dict: {
            "success": bool,
            "deleted_count": int,
            "message": str
        }
    """
    # デフォルト値の設定
    if exclude_names is None:
        exclude_names = ["ハディエント公式"]

    print(f"[Task: cleanup_addresses] 実行中...")
    print(f"  -> 除外名: {exclude_names}")
    print(f"  -> ターゲットURL: {address_page_url}")

    deleted_count = 0

    try:
        # まず現在のURLを確認
        current_url = page.url
        print(f"  -> 現在のURL: {current_url}")

        # ブランクページまたはログインページにいる場合、まずトップページにアクセス
        if not current_url or current_url == "about:blank" or "signin" in current_url.lower():
            print("  -> トップページにアクセスしてセッションを確立します...")
            await page.goto("https://www.amazon.co.jp/", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            print(f"  -> トップページアクセス完了: {page.url}")

        # 住所録ページにアクセス
        print(f"  -> 住所録ページにアクセス: {address_page_url}")
        await page.goto(address_page_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

        # アクセス後のURLを確認（ログインページにリダイレクトされていないか）
        final_url = page.url
        print(f"  -> アクセス後のURL: {final_url}")
        if "signin" in final_url.lower():
            return {
                "success": False,
                "deleted_count": 0,
                "message": "ログインページにリダイレクトされました。セッションが無効です。"
            }

        attempt = 0

        # 削除ループ
        while attempt < max_attempts:
            attempt += 1

            # 住所カードを取得
            try:
                await page.wait_for_selector(
                    "div.normal-desktop-address-tile",
                    timeout=10000
                )
                cards = await page.query_selector_all("div.normal-desktop-address-tile")
            except PlaywrightTimeout:
                print("  -> 住所カードが見つかりません。")
                break

            if not cards:
                print("  -> 住所カードがありません。")
                break

            # 削除対象を探す
            delete_target_index = None
            target_name = ""

            for idx, card in enumerate(cards):
                try:
                    name_element = await card.query_selector("h5.id-addr-ux-search-text")
                    if name_element:
                        name = (await name_element.text_content()).strip()

                        if name not in exclude_names:
                            delete_target_index = idx
                            target_name = name
                            break
                except Exception as e:
                    print(f"  -> カード {idx} の処理中にエラー: {e}")
                    continue

            # 削除対象が見つからなければ終了
            if delete_target_index is None:
                print(f"除外リスト {exclude_names} 以外の住所はすべて削除されました。")
                break

            print(f"  -> 削除対象を発見: {target_name} (index: {delete_target_index})")

            # 削除前のカード数を記録
            initial_card_count = len(cards)

            # 削除リンクを取得
            try:
                delete_links = await page.query_selector_all("a[id^='ya-myab-address-delete-btn-']")

                if delete_target_index >= len(delete_links):
                    print(f"  -> エラー: 削除リンクが見つかりません（インデックス不一致）")
                    return {
                        "success": False,
                        "deleted_count": deleted_count,
                        "message": "削除リンクのインデックスが一致しません"
                    }

                delete_link = delete_links[delete_target_index]
                delete_link_id = await delete_link.get_attribute('id')
                print(f"  -> 削除リンクをクリックします (ID: {delete_link_id})")

                # IDから番号を抽出
                link_number = delete_link_id.split('-')[-1]

                # JavaScriptでクリック
                await page.evaluate("(element) => element.click()", delete_link)

            except Exception as e:
                print(f"  -> エラー: 削除リンクのクリックに失敗: {e}")
                return {
                    "success": False,
                    "deleted_count": deleted_count,
                    "message": f"削除リンクのクリックに失敗: {str(e)}"
                }

            # 確認モーダルの「はい」ボタンをクリック
            try:
                # モーダルが表示されるまで待つ
                await asyncio.sleep(2)

                # 確認ボタンのセレクタリスト
                confirm_selectors = [
                    f"#deleteAddressModal-{link_number}-submit-btn input.a-button-input",
                    "form[action='/a/addresses/delete'] input[type='submit']",
                    "span.a-button-primary input.a-button-input[type='submit']",
                    "div.a-modal-content input.a-button-input[type='submit']",
                    "div.a-popover-content input.a-button-input[type='submit']",
                ]

                confirm_button = None
                for selector in confirm_selectors:
                    try:
                        elements = await page.query_selector_all(selector)
                        # 表示されている要素を探す
                        for elem in elements:
                            if await elem.is_visible() and await elem.is_enabled():
                                confirm_button = elem
                                print(f"  -> 確認ボタン(input)が見つかりました: {selector}")
                                break
                        if confirm_button:
                            break
                    except:
                        continue

                if confirm_button:
                    print(f"  -> 確認モーダルの「はい」ボタン(input)をクリックします。")

                    try:
                        await confirm_button.click()
                    except:
                        # クリックが失敗したらJavaScriptで実行
                        await page.evaluate("(element) => element.click()", confirm_button)

                    # ページのリロードを待つ
                    await asyncio.sleep(3)

                    # 削除が成功したか確認（カード数が減っているか）
                    try:
                        new_cards = await page.query_selector_all("div.normal-desktop-address-tile")
                        if len(new_cards) < initial_card_count:
                            deleted_count += 1
                            print(f"  -> 「{target_name}」を削除しました。(合計 {deleted_count} 件)")
                        else:
                            print(f"  -> 警告: 削除が実行されなかった可能性があります（カード数が変わっていません）")
                            # フォームを直接submit
                            forms = await page.query_selector_all("form[action='/a/addresses/delete']")
                            if forms:
                                for form in forms:
                                    if await form.is_visible():
                                        print(f"    デバッグ: フォームを直接submitします")
                                        await page.evaluate("(form) => form.submit()", form)
                                        await asyncio.sleep(3)
                                        break
                    except:
                        deleted_count += 1
                        print(f"  -> 「{target_name}」を削除しました。(合計 {deleted_count} 件)")

                    # DOM安定待ち
                    await asyncio.sleep(2)
                else:
                    print("  -> エラー: 確認ボタン(input要素)が見つかりません")

                    # 最後の手段：表示されているフォームを直接submit
                    forms = await page.query_selector_all("form[action='/a/addresses/delete']")
                    form_found = False
                    for form in forms:
                        if await form.is_visible():
                            print("  -> フォームを直接submitします")
                            await page.evaluate("(form) => form.submit()", form)
                            form_found = True
                            await asyncio.sleep(3)
                            deleted_count += 1
                            print(f"  -> 「{target_name}」を削除しました。(合計 {deleted_count} 件)")
                            break

                    if not form_found:
                        return {
                            "success": False,
                            "deleted_count": deleted_count,
                            "message": "削除確認ボタンが見つかりません"
                        }

            except PlaywrightTimeout:
                print("  -> エラー: 削除確認ポップアップが見つかりませんでした。")
                return {
                    "success": False,
                    "deleted_count": deleted_count,
                    "message": "削除確認ポップアップが見つかりません"
                }
            except Exception as e:
                print(f"  -> エラー: 確認処理中にエラー: {e}")
                return {
                    "success": False,
                    "deleted_count": deleted_count,
                    "message": f"確認処理中にエラー: {str(e)}"
                }

        # 最大試行回数に達した場合
        if attempt >= max_attempts:
            return {
                "success": False,
                "deleted_count": deleted_count,
                "message": f"最大試行回数に達しました。合計 {deleted_count} 件の住所を削除しました。"
            }

        return {
            "success": True,
            "deleted_count": deleted_count,
            "message": f"合計 {deleted_count} 件の住所を削除しました。"
        }

    except Exception as e:
        print(f"[ERROR] 予期せぬエラー: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "deleted_count": deleted_count,
            "message": f"予期せぬエラー: {str(e)}"
        }
