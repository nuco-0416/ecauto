"""
SellerSprite カテゴリ抽出ユーティリティ

商品リサーチページからASINとカテゴリ情報を抽出する共通機能を提供。
analyze_popular_categories.py のクリーンな実装を再利用可能にしたモジュール。

使用例:
    from sourcing.sources.sellersprite.utils.category_extractor import (
        create_browser_session,
        build_product_research_url,
        extract_asins_with_categories
    )

    async with create_browser_session() as (browser, page):
        url = build_product_research_url(
            market="JP",
            sales_min=300,
            price_min=2500
        )

        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(5000)

        data = await extract_asins_with_categories(page, limit=100)
"""

import os
import re
import asyncio
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlencode
from contextlib import asynccontextmanager
from playwright.async_api import async_playwright, Browser, Page
from dotenv import load_dotenv

# プロジェクトルート
project_root = Path(__file__).parent.parent.parent.parent.parent

# .envファイルを読み込む
env_path = project_root / 'sourcing' / 'sources' / 'sellersprite' / '.env'
load_dotenv(dotenv_path=env_path)


def log(message: str):
    """ログ出力"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")


def build_product_research_url(
    market: str,
    sales_min: int,
    price_min: int,
    amz: bool = True,
    fba: bool = True,
    node_id_paths: str = "[]"
) -> str:
    """
    商品リサーチページの完全なURLを構築（フィルター条件付き）

    UI操作は一切せず、URLパラメータで全てのフィルター条件を指定する。
    これにより、フィルター実行ボタンのクリックなどの不要な操作を回避。

    Args:
        market: 市場（JP, US, UK等）
        sales_min: 月間販売数の最小値
        price_min: 価格の最小値
        amz: Amazon販売のみ
        fba: FBAのみ
        node_id_paths: カテゴリのnodeIdPaths

    Returns:
        完全なURL
    """
    # sellerTypesを構築
    seller_types = []
    if amz:
        seller_types.append('"AMZ"')
    if fba:
        seller_types.append('"FBA"')
    seller_types_str = f'[{",".join(seller_types)}]' if seller_types else '[]'

    # ベースURL
    base_url = "https://www.sellersprite.com/v3/product-research"

    # 必須パラメータ
    params = {
        'market': market,
        'page': '1',
        'size': '100',
        'symbolFlag': 'true',
        'monthName': 'bsr_sales_nearly',
        'selectType': '2',
        'filterSub': 'false',
        'weightUnit': 'g',
        'order[field]': 'amz_unit',
        'order[desc]': 'true',
        'productTags': '[]',
        'nodeIdPaths': node_id_paths,
        'sellerTypes': seller_types_str,
        'eligibility': '[]',
        'pkgDimensionTypeList': '[]',
        'sellerNationList': '[]',
        'lowPrice': 'N',
        'video': ''
    }

    # フィルター条件を追加
    if sales_min:
        params['minSales'] = str(sales_min)

    if price_min:
        params['minPrice'] = str(price_min)

    # URLを構築
    query_string = urlencode(params, safe='[]":')

    return f"{base_url}?{query_string}"


async def extract_asins_with_categories(
    page: Page,
    limit: int
) -> List[Dict[str, str]]:
    """
    テーブルからASINとカテゴリ情報を抽出

    リスト表示に切り替えて、各行の詳細を展開してカテゴリ情報を取得。
    フィルター実行などのUI操作は一切行わない。

    Args:
        page: Playwrightページオブジェクト
        limit: 取得件数

    Returns:
        [{"asin": "B00XXXXX", "category": "...", "nodeIdPaths": "..."}, ...]
    """
    all_data = []

    try:
        # リスト表示に切り替え
        log("表示スタイルを「リスト」に切り替え中...")

        # リストボタンを探してクリック
        # 注意: フィルター実行ボタンを避けるため、厳密なセレクタを使用
        try:
            # el-button-group内の「リスト」ボタンのみを対象にする（最も安全）
            list_button = page.locator('div.el-button-group button').filter(has_text="リスト").first
            button_count = await list_button.count()

            if button_count > 0:
                # ボタンのテキストを確認（完全一致チェック）
                button_text = await list_button.text_content()
                if button_text and button_text.strip() == "リスト":
                    await list_button.click()
                    await page.wait_for_timeout(2000)
                    log("[OK] リスト表示に切り替えました")
                else:
                    log(f"[WARN] ボタンのテキストが「リスト」と完全一致しません: '{button_text}'")
            else:
                log("[WARN] リストボタンが見つかりませんでした。デフォルト表示のまま続行します。")
        except Exception as e:
            log(f"[WARN] リスト表示への切り替えエラー: {e}")

        # 必要なページ数を計算（1ページ=100件）
        pages_needed = (limit + 99) // 100
        log(f"ページネーション: {pages_needed}ページから抽出予定")

        for page_num in range(1, pages_needed + 1):
            log(f"  ページ {page_num}/{pages_needed} を処理中...")

            # 全ての行を展開
            log(f"    全ての行を展開中...")
            expand_result = await page.evaluate('''() => {
                const expandButtons = document.querySelectorAll('td.el-table__expand-column .el-table__expand-icon');
                let clickedCount = 0;

                expandButtons.forEach(button => {
                    // 展開されていない場合のみクリック
                    if (!button.classList.contains('el-table__expand-icon--expanded')) {
                        button.click();
                        clickedCount++;
                    }
                });

                return {
                    total: expandButtons.length,
                    clicked: clickedCount
                };
            }''')
            log(f"    → {expand_result['total']}個中{expand_result['clicked']}個の展開ボタンをクリック")

            # DOM更新を待機
            await page.wait_for_timeout(3000)

            # テーブルの全行を走査してASINとカテゴリを抽出
            data_on_page = await page.evaluate('''() => {
                const data = [];
                const rows = Array.from(document.querySelectorAll('table tbody tr'));

                let currentAsin = null;

                rows.forEach((row, index) => {
                    // 通常の行からASINを抽出
                    const rowText = row.textContent || '';
                    const asinMatch = rowText.match(/ASIN:\\s*([A-Z0-9]{10})/);

                    if (asinMatch) {
                        currentAsin = asinMatch[1];
                    }

                    // 展開された詳細行からカテゴリ情報を抽出
                    const tableExpand = row.querySelector('.table-expand');
                    if (tableExpand && currentAsin) {
                        let categories = [];
                        let nodeIdPaths = '';

                        // .product-type 要素からカテゴリ階層を抽出
                        const productType = tableExpand.querySelector('.product-type');
                        if (productType) {
                            // カテゴリリンク（class="type"）を全て取得
                            const categoryLinks = productType.querySelectorAll('a.type');

                            categoryLinks.forEach((link, linkIndex) => {
                                const categoryName = link.textContent.trim();
                                if (categoryName) {
                                    categories.push(categoryName);
                                }

                                // 最後のリンクからnodeIdPathsを取得
                                if (linkIndex === categoryLinks.length - 1 && link.href) {
                                    try {
                                        const url = new URL(link.href, window.location.origin);
                                        const nodeIdPathsParam = url.searchParams.get('nodeIdPaths');
                                        if (nodeIdPathsParam) {
                                            nodeIdPaths = nodeIdPathsParam;
                                        }
                                    } catch (e) {
                                        // URLパースエラーは無視
                                    }
                                }
                            });
                        }

                        // データを追加
                        data.push({
                            asin: currentAsin,
                            category: categories.join(' > '),
                            nodeIdPaths: nodeIdPaths
                        });

                        // 次のASINのためにリセット
                        currentAsin = null;
                    }
                });

                return data;
            }''')

            # カテゴリ情報取得状況を出力
            categories_found = sum(1 for item in data_on_page if item.get('category'))
            log(f"    → カテゴリ情報: {categories_found}件 / {len(data_on_page)}件")
            log(f"    → {len(data_on_page)}件抽出")
            all_data.extend(data_on_page)

            # 最後のページでない場合、次のページに移動
            if page_num < pages_needed:
                try:
                    # 次のページボタンを探す
                    next_button = page.locator('button.btn-next:not([disabled])')
                    button_count = await next_button.count()

                    if button_count > 0:
                        await next_button.click()
                        await page.wait_for_load_state("networkidle", timeout=30000)
                        await asyncio.sleep(1)
                        log(f"    次のページに移動しました")
                    else:
                        log(f"[WARN] 次のページボタンが見つかりません。{page_num}ページで終了します。")
                        break

                except Exception as e:
                    log(f"[WARN] ページネーションエラー: {e}")
                    log(f"[WARN] {page_num}ページまでの結果を返します")
                    break

        # limit件数まで制限
        all_data = all_data[:limit]
        log(f"合計 {len(all_data)}件のデータを抽出（目標: {limit}件）")

        return all_data

    except Exception as e:
        log(f"[ERROR] データ抽出エラー: {e}")
        raise


@asynccontextmanager
async def create_browser_session(
    email: Optional[str] = None,
    password: Optional[str] = None,
    headless: bool = False
):
    """
    SellerSpriteのブラウザセッションを作成（ログイン済み）

    環境変数から認証情報を取得し、SellerSpriteにログインした状態のブラウザセッションを返す。

    Args:
        email: SellerSpriteのメールアドレス（省略時は環境変数から取得）
        password: SellerSpriteのパスワード（省略時は環境変数から取得）
        headless: ヘッドレスモードで起動するか

    Yields:
        (browser, page): ログイン済みのブラウザとページ

    使用例:
        async with create_browser_session() as (browser, page):
            await page.goto('https://...')
            # 処理
    """
    # 環境変数から認証情報を取得
    email = email or os.getenv('SELLERSPRITE_EMAIL')
    password = password or os.getenv('SELLERSPRITE_PASSWORD')

    if not email or not password:
        raise ValueError("環境変数 SELLERSPRITE_EMAIL と SELLERSPRITE_PASSWORD が設定されていません")

    browser = None
    try:
        async with async_playwright() as p:
            # ブラウザを起動
            log("ブラウザを起動中...")
            browser = await p.chromium.launch(
                headless=headless,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-automation',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                ],
            )

            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                locale="ja-JP",
                timezone_id="Asia/Tokyo",
            )

            page = await context.new_page()

            # SellerSpriteにログイン
            log("SellerSpriteにログイン中...")
            await page.goto(
                "https://www.sellersprite.com/jp/w/user/login",
                wait_until="networkidle",
                timeout=30000
            )

            # メールアドレス入力
            email_input = page.get_by_role('textbox', name=re.compile(r'メールアドレス|アカウント', re.IGNORECASE))
            await email_input.fill(email)
            await page.wait_for_timeout(1000)

            # パスワード入力
            password_input = page.get_by_role('textbox', name=re.compile(r'パスワード', re.IGNORECASE))
            await password_input.fill(password)
            await page.wait_for_timeout(1000)

            # ログインボタンをクリック
            login_button = page.get_by_role('button', name=re.compile(r'ログイン', re.IGNORECASE))
            await login_button.click()

            # ログイン完了を待機
            try:
                await page.wait_for_url(re.compile(r'/(welcome|dashboard)'), timeout=30000)
                log("[OK] ログイン成功")
            except Exception as e:
                current_url = page.url
                if 'login' not in current_url:
                    log("[OK] ログイン成功（URL遷移確認）")
                else:
                    raise Exception(f"ログインに失敗しました: {e}")

            # セッションを提供
            yield browser, page

    finally:
        # クリーンアップ
        if browser:
            await browser.close()
            log("ブラウザを閉じました")
