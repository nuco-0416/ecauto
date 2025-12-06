"""
SellerSprite 商品リサーチ抽出

商品リサーチ機能（Product Research）からASINを抽出する。
フィルター条件を指定して、条件に合致する商品を取得。

使用例:
    from sourcing.sources.sellersprite.extractors.product_research_extractor import ProductResearchExtractor

    extractor = ProductResearchExtractor({
        "sales_min": 300,
        "price_min": 2500,
        "amz": True,
        "fba": True,
        "limit": 100
    })

    asins = await extractor.extract()
"""

import asyncio
import re
from typing import List, Dict, Any

from .base_extractor import BaseExtractor
from ..browser_controller import BrowserController


class ProductResearchExtractor(BaseExtractor):
    """
    商品リサーチ機能からASIN抽出

    TypeScript実装（get_sellersprite_asins.spec.ts）をPythonに移植
    """

    def __init__(self, parameters: Dict[str, Any]):
        """
        Args:
            parameters: {
                "sales_min": int,     # 月間販売数の最小値（例: 300）
                "sales_max": int,     # 月間販売数の最大値（オプション）
                "price_min": int,     # 価格の最小値（例: 2500）
                "price_max": int,     # 価格の最大値（オプション）
                "amz": bool,          # Amazon販売のみ（デフォルト: True）
                "fba": bool,          # FBAのみ（デフォルト: True）
                "limit": int,         # 取得件数（デフォルト: 100）
                "market": str,        # 市場（デフォルト: "JP"、他: "US", "UK", "DE"等）
                "categories": List[str]  # カテゴリリスト（例: ["Health & Household > Healthcare"]）
            }
        """
        super().__init__("product_research", parameters)

        # パラメータのバリデーションとデフォルト値
        self.sales_min = parameters.get("sales_min", 300)
        self.sales_max = parameters.get("sales_max", None)  # 🆕 最大値（オプション）
        self.price_min = parameters.get("price_min", 2500)
        self.price_max = parameters.get("price_max", None)  # 🆕 最大値（オプション）
        self.amz = parameters.get("amz", True)
        self.fba = parameters.get("fba", True)
        self.limit = parameters.get("limit", 100)
        self.market = parameters.get("market", "JP")  # デフォルト: 日本市場
        self.node_id_paths = parameters.get("node_id_paths", "[]")  # nodeIdPaths（デフォルト: 空配列）
        self.extract_category_info = parameters.get("extract_category_info", False)  # カテゴリ情報も抽出するか

        # ページネーション対応: 最大2000件（20ページ）まで取得可能
        if self.limit > 2000:
            self.log("[WARN] limit は最大2000件です。2000件に調整されます。")
            self.limit = 2000

    async def _extract_impl(self, controller: BrowserController) -> List[str]:
        """
        商品リサーチからASINを抽出

        Args:
            controller: BrowserControllerインスタンス

        Returns:
            ASINリスト
        """
        asins = []

        try:
            # 完全なURLを構築（UI操作不要）
            self.log(f"商品リサーチページに遷移中（市場: {self.market}）...")

            product_research_url = self._build_complete_url()
            self.log(f"[URL] アクセス先: {product_research_url}")

            # ページ遷移
            page = controller.page
            success = await controller.goto(product_research_url, wait_until="domcontentloaded", timeout=30000)

            if not success:
                raise Exception("商品リサーチページへの遷移に失敗しました")

            self.log("[OK] ページ読み込み完了")

            # テーブルのレンダリングを待機
            await page.wait_for_timeout(5000)

            # 【デバッグ】ページの状態を確認
            page_state = await page.evaluate('''() => {
                return {
                    title: document.title,
                    buttonCount: document.querySelectorAll('button').length,
                    tableRowCount: document.querySelectorAll('table tbody tr').length,
                    filterButtons: Array.from(document.querySelectorAll('button')).filter(btn =>
                        btn.textContent.includes('フィルター') || btn.textContent.includes('実行')
                    ).map(btn => btn.textContent.trim()),
                    hasErrorDialog: document.querySelectorAll('.el-dialog__wrapper, .yun-message-box').length > 0
                };
            }''')
            self.log(f"[デバッグ] ページ状態: title='{page_state['title']}', buttons={page_state['buttonCount']}, tableRows={page_state['tableRowCount']}, hasError={page_state['hasErrorDialog']}")
            if page_state['filterButtons']:
                self.log(f"[デバッグ] フィルター関連ボタン: {page_state['filterButtons']}")

            # ページ読み込み直後にエラーポップアップをチェック
            popup_detected = await self._close_error_popup(controller)
            if popup_detected:
                self.log("[WARN] ページ読み込み直後にエラーが検出されました")
                # エラーが出た場合でも、処理を続行して可能な限りデータを取得

            # ログイン状態を確認
            current_url = page.url
            self.log(f"現在のURL: {current_url}")

            if 'login' in current_url:
                self.log("[ERROR] ログインページにリダイレクトされました")
                raise Exception("セッションが無効です。再ログインが必要です")

            # ASINを抽出（カテゴリ情報付きかどうかで分岐）
            if self.extract_category_info:
                self.log("ASINとカテゴリ情報を抽出中...")
                asins = await self._extract_asins_with_categories(controller)
            else:
                self.log("ASIN抽出中...")
                asins = await self._extract_asins(controller)

            # スクリーンショット保存
            await controller.screenshot(
                f"product_research_sales{self.sales_min}_price{self.price_min}.png"
            )

            self.log(f"[OK] {len(asins)}件のASINを抽出しました")

        except Exception as e:
            self.log(f"[ERROR] 抽出処理エラー: {e}")
            try:
                # ページが閉じられていない場合のみスクリーンショット
                if controller.page and not controller.page.is_closed():
                    await controller.screenshot("product_research_error.png")
            except Exception as screenshot_error:
                self.log(f"[WARN] スクリーンショット保存失敗: {screenshot_error}")
            raise

        return asins

    def _build_complete_url(self) -> str:
        """
        完全なURLを構築（すべてのフィルター条件を含む）

        Returns:
            str: 完全なURL
        """
        from urllib.parse import urlencode

        # sellerTypesを構築
        seller_types = []
        if self.amz:
            seller_types.append('"AMZ"')
        if self.fba:
            seller_types.append('"FBA"')
        seller_types_str = f'[{",".join(seller_types)}]' if seller_types else '[]'

        # ベースURL
        base_url = "https://www.sellersprite.com/v3/product-research"

        # 必須パラメータ
        params = {
            'market': self.market,
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
            'nodeIdPaths': self.node_id_paths,  # デフォルト: "[]"
            'sellerTypes': seller_types_str,
            'eligibility': '[]',
            'pkgDimensionTypeList': '[]',
            'sellerNationList': '[]',
            'lowPrice': 'N',
            'video': ''
        }

        # フィルター条件を追加
        if self.sales_min:
            params['minSales'] = str(self.sales_min)

        if self.price_min:
            params['minPrice'] = str(self.price_min)

        # URLを構築
        query_string = urlencode(params, safe='[]":')

        return f"{base_url}?{query_string}"

    async def _extract_asins(self, controller: BrowserController) -> List[str]:
        """
        テーブルからASINを抽出（ページネーション対応）

        Args:
            controller: BrowserControllerインスタンス

        Returns:
            ASINリスト
        """
        page = controller.page
        all_asins = []

        try:
            # 必要なページ数を計算（1ページ=100件）
            pages_needed = (self.limit + 99) // 100  # 切り上げ
            self.log(f"ページネーション: {pages_needed}ページから抽出予定")

            for page_num in range(1, pages_needed + 1):
                self.log(f"  ページ {page_num}/{pages_needed} を処理中...")

                # 現在のページからASINを抽出
                asins_on_page = await page.evaluate('''() => {
                    const asinElements = document.querySelectorAll('table tbody tr');
                    const asinList = [];

                    asinElements.forEach(row => {
                        const text = row.textContent || '';
                        const match = text.match(/ASIN:\\s*([A-Z0-9]{10})/);
                        if (match && match[1]) {
                            asinList.push(match[1]);
                        }
                    });

                    // 重複を除去
                    const uniqueAsins = [...new Set(asinList)];
                    return uniqueAsins;
                }''')

                self.log(f"    → {len(asins_on_page)}件抽出")
                all_asins.extend(asins_on_page)

                # 最後のページでない場合、次のページに移動
                if page_num < pages_needed:
                    try:
                        # エラーポップアップを検出・閉じる
                        popup_detected = await self._close_error_popup(controller)

                        if popup_detected:
                            # エラーポップアップが表示された場合、処理を中断
                            self.log(f"[WARN] エラーポップアップが表示されたため、{page_num}ページで終了します")
                            break

                        # 次のページボタンを探す（Element UI のページネーション）
                        # "次へ"ボタンまたはページ番号をクリック
                        next_button = page.locator('button.btn-next:not([disabled])')

                        # ボタンが存在するかチェック
                        button_count = await next_button.count()

                        if button_count > 0:
                            await next_button.click()
                            await page.wait_for_load_state("networkidle", timeout=30000)
                            await asyncio.sleep(1)  # 追加の待機
                            self.log(f"    次のページに移動しました")
                        else:
                            self.log(f"[WARN] 次のページボタンが見つかりません。{page_num}ページで終了します。")
                            break

                    except Exception as e:
                        self.log(f"[WARN] ページネーションエラー: {e}")

                        # エラー発生時も一度ポップアップをチェック
                        try:
                            await self._close_error_popup(controller)
                        except Exception:
                            pass

                        self.log(f"[WARN] {page_num}ページまでの結果を返します")
                        break

            # limit件数まで制限
            all_asins = all_asins[:self.limit]
            self.log(f"合計 {len(all_asins)}件のASINを抽出（目標: {self.limit}件）")

            return all_asins

        except Exception as e:
            self.log(f"[ERROR] ASIN抽出エラー: {e}")
            raise

    async def _close_error_popup(self, controller: BrowserController) -> bool:
        """
        エラーポップアップを検出して閉じる

        SellerSpriteのサイトでエラーポップアップが表示されている場合、
        その内容をログに出力して閉じる。

        Args:
            controller: BrowserControllerインスタンス

        Returns:
            bool: ポップアップが表示されていた場合True
        """
        page = controller.page

        try:
            # エラーポップアップを検出（複数のセレクタを試す）
            popup_selectors = [
                '.el-dialog__wrapper.yun-box',
                '.yun-message-box',
                '.el-message-box__wrapper'
            ]

            for selector in popup_selectors:
                popup = page.locator(selector)
                count = await popup.count()

                if count > 0:
                    # ポップアップの内容を取得
                    try:
                        popup_text = await popup.text_content()
                        if popup_text:
                            # 改行や余分な空白を削除
                            popup_text_clean = ' '.join(popup_text.split())
                            # 文字化けを避けるため、UTF-8エンコーディング
                            try:
                                self.log(f"[WARN] エラーポップアップ検出: {popup_text_clean[:300]}")
                            except Exception:
                                # ログ出力に失敗した場合、安全な文字列に変換
                                popup_text_safe = popup_text_clean[:300].encode('utf-8', errors='ignore').decode('utf-8')
                                self.log(f"[WARN] エラーポップアップ検出: {popup_text_safe}")
                        else:
                            self.log(f"[WARN] エラーポップアップ検出（内容は空）")
                    except Exception as e:
                        self.log(f"[WARN] エラーポップアップ検出（内容取得失敗: {e}）")

                    # 閉じるボタンをクリック（複数のパターンを試す）
                    close_button_selectors = [
                        f'{selector} button:has-text("確定")',
                        f'{selector} button:has-text("OK")',
                        f'{selector} button.el-button--primary',
                        f'{selector} button.el-message-box__headerbtn',
                        f'{selector} .el-icon-close'
                    ]

                    closed = False
                    for close_selector in close_button_selectors:
                        try:
                            close_button = page.locator(close_selector).first
                            close_count = await close_button.count()

                            if close_count > 0:
                                await close_button.click()
                                await page.wait_for_timeout(1000)
                                self.log("[OK] エラーポップアップを閉じました")
                                closed = True
                                break
                        except Exception:
                            continue

                    if not closed:
                        # 閉じるボタンが見つからない場合、ESCキーを試す
                        try:
                            await page.keyboard.press('Escape')
                            await page.wait_for_timeout(1000)
                            self.log("[OK] エラーポップアップを閉じました（ESCキー）")
                            closed = True
                        except Exception:
                            pass

                    return closed

            return False

        except Exception as e:
            self.log(f"[WARN] ポップアップ検出エラー: {e}")
            return False

    async def _switch_to_list_view(self, controller: BrowserController):
        """
        表示スタイルを「リスト」に切り替え

        カテゴリ情報を表示するには、リスト表示に切り替える必要がある。

        Args:
            controller: BrowserControllerインスタンス
        """
        page = controller.page

        try:
            self.log("表示スタイルを「リスト」に切り替え中...")

            # 【デバッグ】ページ上のボタンを列挙
            try:
                buttons_info = await page.evaluate('''() => {
                    const buttons = Array.from(document.querySelectorAll('button'));
                    return buttons.slice(0, 20).map((btn, index) => ({
                        index: index,
                        text: btn.textContent.trim(),
                        classes: btn.className,
                        type: btn.type,
                        disabled: btn.disabled
                    }));
                }''')
                self.log(f"    [デバッグ] ページ上のボタン（最初の20個）:")
                for btn_info in buttons_info[:10]:  # 最初の10個だけログ出力
                    try:
                        # 文字化けを避けるため、ASCII以外の文字を置き換え
                        text_safe = btn_info['text'][:30].encode('utf-8', errors='ignore').decode('utf-8')
                        class_safe = btn_info['classes'][:50].encode('utf-8', errors='ignore').decode('utf-8')
                        self.log(f"      [{btn_info['index']}] text='{text_safe}' class='{class_safe}' type={btn_info['type']} disabled={btn_info['disabled']}")
                    except Exception as e:
                        self.log(f"      [{btn_info['index']}] (ログ出力エラー: {e})")
            except Exception as e:
                self.log(f"    [デバッグ] ボタン列挙エラー: {e}")

            # より厳密なセレクタを使用（フィルター実行ボタンを避ける）
            list_button_selectors = [
                # 1. リスト表示ボタンのグループ内のボタン（最も安全）
                'div.el-button-group button:has-text("リスト")',
                # 2. クラス名で厳密に指定
                'button.el-button:has-text("リスト"):not(:has-text("フィルター")):not(:has-text("実行"))',
                # 3. 従来のセレクタ（フォールバック）
                'button:has-text("リスト")',
            ]

            clicked = False
            for i, selector in enumerate(list_button_selectors):
                try:
                    button = page.locator(selector).first
                    count = await button.count()

                    if count > 0:
                        # クリック前にボタンの情報を取得
                        button_text = await button.text_content()
                        button_class = await button.get_attribute('class')
                        self.log(f"    [デバッグ] セレクタ{i+1}でマッチ: text='{button_text.strip()}' class='{button_class}'")

                        # 「リスト」以外のテキストが含まれている場合はスキップ
                        if button_text.strip() != "リスト":
                            self.log(f"    [WARN] ボタンのテキストが「リスト」と完全一致しないためスキップ: '{button_text.strip()}'")
                            continue

                        await button.click()
                        await page.wait_for_timeout(2000)  # リスト表示への切り替えを待機
                        clicked = True
                        self.log("[OK] リスト表示に切り替えました")
                        break
                except Exception as e:
                    self.log(f"    [DEBUG] セレクタ{i+1}でエラー: {e}")
                    continue

            if not clicked:
                self.log("[WARN] リストボタンが見つかりませんでした。デフォルト表示のまま続行します。")

        except Exception as e:
            self.log(f"[WARN] リスト表示への切り替えエラー: {e}")
            # エラーでも処理続行

    async def _extract_asins_with_categories(self, controller: BrowserController) -> List[Dict[str, str]]:
        """
        テーブルからASINとカテゴリ情報を抽出（ページネーション対応）

        リスト表示に切り替えてから、各行の .product-type からカテゴリ情報を抽出する。

        Args:
            controller: BrowserControllerインスタンス

        Returns:
            [{"asin": "B00XXXXX", "category": "ドラッグストア > 栄養補助食品", "nodeIdPaths": "..."}, ...]
        """
        page = controller.page
        all_data = []

        try:
            # リスト表示に切り替え
            await self._switch_to_list_view(controller)

            # 必要なページ数を計算（1ページ=100件）
            pages_needed = (self.limit + 99) // 100  # 切り上げ
            self.log(f"ページネーション: {pages_needed}ページから抽出予定")

            for page_num in range(1, pages_needed + 1):
                self.log(f"  ページ {page_num}/{pages_needed} を処理中...")

                # 全ての行を展開
                self.log(f"    全ての行を展開中...")

                # 【デバッグ】展開ボタンの情報を取得
                expand_buttons_debug = await page.evaluate('''() => {
                    const expandButtons = document.querySelectorAll('td.el-table__expand-column .el-table__expand-icon');
                    const allButtons = document.querySelectorAll('button');

                    return {
                        expandButtonsCount: expandButtons.length,
                        allButtonsCount: allButtons.length,
                        expandButtonsInfo: Array.from(expandButtons).slice(0, 3).map((btn, idx) => ({
                            index: idx,
                            className: btn.className,
                            tagName: btn.tagName,
                            isExpanded: btn.classList.contains('el-table__expand-icon--expanded')
                        }))
                    };
                }''')
                self.log(f"    [デバッグ] 展開ボタン: {expand_buttons_debug['expandButtonsCount']}個見つかりました（全ボタン: {expand_buttons_debug['allButtonsCount']}個）")

                expand_result = await page.evaluate('''() => {
                    const expandButtons = document.querySelectorAll('td.el-table__expand-column .el-table__expand-icon');
                    let clickedCount = 0;

                    expandButtons.forEach(button => {
                        // 展開されていない場合のみクリック（expanded クラスがない場合）
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
                self.log(f"    → {expand_result['total']}個中{expand_result['clicked']}個の展開ボタンをクリック")

                # DOM更新を待機（展開アニメーション + コンテンツ読み込み）
                await page.wait_for_timeout(3000)

                # 展開状態を確認 + DOM構造を調査
                expanded_check = await page.evaluate('''() => {
                    const expandedButtons = document.querySelectorAll('td.el-table__expand-column .el-table__expand-icon--expanded');
                    const tableExpands = document.querySelectorAll('.table-expand');
                    const productTypes = document.querySelectorAll('.product-type');

                    // 最初の.product-type要素の親要素のパスを取得
                    let firstProductTypePath = null;
                    if (productTypes.length > 0) {
                        const first = productTypes[0];
                        const pathParts = [];
                        let current = first;

                        for (let i = 0; i < 5 && current; i++) {
                            const tag = current.tagName.toLowerCase();
                            const classes = current.className ? '.' + current.className.split(' ').join('.') : '';
                            pathParts.unshift(tag + classes);
                            current = current.parentElement;
                        }

                        firstProductTypePath = pathParts.join(' > ');
                    }

                    return {
                        expandedCount: expandedButtons.length,
                        tableExpandCount: tableExpands.length,
                        productTypeCount: productTypes.length,
                        firstProductTypePath: firstProductTypePath
                    };
                }''')
                self.log(f"    [展開確認] expanded={expanded_check['expandedCount']}, table-expand={expanded_check['tableExpandCount']}, product-type={expanded_check['productTypeCount']}")
                if expanded_check['firstProductTypePath']:
                    self.log(f"    [DOM構造] .product-typeのパス: {expanded_check['firstProductTypePath']}")

                # データ取得直前に表示モードを確認・修正
                self.log(f"    表示モードを確認中...")
                view_mode_check = await page.evaluate('''() => {
                    // 全てのボタンからテキストが「リスト」のものを探す
                    const buttons = Array.from(document.querySelectorAll('button'));
                    const listButton = buttons.find(btn => btn.textContent.trim() === 'リスト');
                    const isListView = listButton && listButton.classList.contains('is-active');

                    return {
                        isListView: isListView,
                        listButtonExists: !!listButton
                    };
                }''')

                if not view_mode_check['isListView']:
                    self.log(f"    [WARN] リスト表示になっていません。再度切り替えます...")
                    # リストボタンを再クリック
                    try:
                        list_button = page.locator('button:has-text("リスト")').first
                        await list_button.click()
                        await page.wait_for_timeout(2000)
                        self.log(f"    [OK] リスト表示に切り替えました")
                    except Exception as e:
                        self.log(f"    [ERROR] リスト表示への切り替えに失敗: {e}")
                else:
                    self.log(f"    [OK] リスト表示を確認")

                # テーブルの全行を走査してASINとカテゴリを抽出
                # 展開された詳細行（.table-expand）は通常行とは別の<tr>として挿入される
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

                            // データを追加（ASINとカテゴリ情報のペア）
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
                self.log(f"    → カテゴリ情報: {categories_found}件 / {len(data_on_page)}件")

                self.log(f"    → {len(data_on_page)}件抽出")
                all_data.extend(data_on_page)

                # 最後のページでない場合、次のページに移動
                if page_num < pages_needed:
                    try:
                        # エラーポップアップを検出・閉じる
                        popup_detected = await self._close_error_popup(controller)

                        if popup_detected:
                            # エラーポップアップが表示された場合、処理を中断
                            self.log(f"[WARN] エラーポップアップが表示されたため、{page_num}ページで終了します")
                            break

                        # 次のページボタンを探す
                        next_button = page.locator('button.btn-next:not([disabled])')
                        button_count = await next_button.count()

                        if button_count > 0:
                            await next_button.click()
                            await page.wait_for_load_state("networkidle", timeout=30000)
                            await asyncio.sleep(1)
                            self.log(f"    次のページに移動しました")
                        else:
                            self.log(f"[WARN] 次のページボタンが見つかりません。{page_num}ページで終了します。")
                            break

                    except Exception as e:
                        self.log(f"[WARN] ページネーションエラー: {e}")

                        # エラー発生時も一度ポップアップをチェック
                        try:
                            await self._close_error_popup(controller)
                        except Exception:
                            pass

                        self.log(f"[WARN] {page_num}ページまでの結果を返します")
                        break

            # limit件数まで制限
            all_data = all_data[:self.limit]
            self.log(f"合計 {len(all_data)}件のデータを抽出（目標: {self.limit}件）")

            return all_data

        except Exception as e:
            self.log(f"[ERROR] データ抽出エラー: {e}")
            raise


# サンプル使用例（直接実行用）
async def main():
    """
    サンプル実行
    """
    print("=" * 60)
    print("SellerSprite 商品リサーチ抽出 - サンプル実行")
    print("=" * 60)

    extractor = ProductResearchExtractor({
        "sales_min": 300,
        "price_min": 2500,
        "amz": True,
        "fba": True,
        "limit": 100
    })

    try:
        asins = await extractor.extract()

        print("\n抽出結果:")
        print(f"  抽出件数: {len(asins)}件")
        print("\nサンプルASIN:")
        for asin in asins[:10]:
            print(f"  - {asin}")

        if len(asins) > 10:
            print(f"  ... 他 {len(asins) - 10}件")

    except Exception as e:
        print(f"\n[ERROR] エラーが発生しました: {e}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
