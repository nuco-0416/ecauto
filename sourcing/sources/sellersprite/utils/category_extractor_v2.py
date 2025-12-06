"""
SellerSprite カテゴリ抽出ユーティリティ v2

v1との違い：
- 中間カテゴリも含めて全階層のカテゴリを抽出
- 各カテゴリレベルのnodeIdPathsも取得

例：
「ドラッグストア > 日用品 > 洗濯・仕上げ剤 > 液体洗剤」の場合
v1: 「液体洗剤」のnodeIdPathsのみ
v2: 全階層のnodeIdPathsを抽出
    - ドラッグストア
    - ドラッグストア > 日用品
    - ドラッグストア > 日用品 > 洗濯・仕上げ剤
    - ドラッグストア > 日用品 > 洗濯・仕上げ剤 > 液体洗剤
"""

import asyncio
from pathlib import Path
from datetime import datetime
from typing import List, Dict
from playwright.async_api import Page


def log(message: str):
    """ログ出力"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")


async def extract_asins_with_all_category_levels(
    page: Page,
    limit: int
) -> List[Dict[str, str]]:
    """
    テーブルからASINと全階層のカテゴリ情報を抽出

    各ASINから、全てのカテゴリレベル（中間カテゴリを含む）のnodeIdPathsを抽出する。

    Args:
        page: Playwrightページオブジェクト
        limit: 取得件数

    Returns:
        [{"asin": "B00XXXXX", "category": "...", "nodeIdPaths": "...", "category_level": N}, ...]
        各ASINから複数のカテゴリレベルが生成される
    """
    all_data = []

    try:
        # リスト表示に切り替え
        log("表示スタイルを「リスト」に切り替え中...")

        try:
            list_button = page.locator('div.el-button-group button').filter(has_text="リスト").first
            button_count = await list_button.count()

            if button_count > 0:
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

            # テーブルの全行を走査して全階層のカテゴリ情報を抽出
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
                        const productType = tableExpand.querySelector('.product-type');
                        if (productType) {
                            const categoryLinks = productType.querySelectorAll('a.type');

                            // 各カテゴリリンクからnodeIdPathsを抽出
                            const categoriesData = [];

                            categoryLinks.forEach((link, linkIndex) => {
                                const categoryName = link.textContent.trim();
                                if (!categoryName) return;

                                // このレベルまでのカテゴリパスを構築
                                const categoryPath = Array.from(categoryLinks)
                                    .slice(0, linkIndex + 1)
                                    .map(l => l.textContent.trim())
                                    .filter(c => c)
                                    .join(' > ');

                                // nodeIdPathsを取得
                                let nodeIdPaths = '';
                                if (link.href) {
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

                                if (nodeIdPaths) {
                                    categoriesData.push({
                                        category: categoryPath,
                                        nodeIdPaths: nodeIdPaths,
                                        level: linkIndex + 1,
                                        total_levels: categoryLinks.length
                                    });
                                }
                            });

                            // 各カテゴリレベルをデータに追加
                            categoriesData.forEach(catData => {
                                data.push({
                                    asin: currentAsin,
                                    category: catData.category,
                                    nodeIdPaths: catData.nodeIdPaths,
                                    category_level: catData.level,
                                    total_category_levels: catData.total_levels
                                });
                            });
                        }

                        currentAsin = null;
                    }
                });

                return data;
            }''')

            # カテゴリ情報取得状況を出力
            asins_found = len(set(item['asin'] for item in data_on_page))
            categories_found = len(data_on_page)
            log(f"    → ASIN: {asins_found}件, カテゴリエントリ: {categories_found}件")
            log(f"    → {categories_found}件抽出（中間カテゴリ含む）")
            all_data.extend(data_on_page)

            # 最後のページでない場合、次のページに移動
            if page_num < pages_needed:
                try:
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

        # ユニークASIN数を計算
        unique_asins = len(set(item['asin'] for item in all_data))
        log(f"合計 {len(all_data)}件のカテゴリエントリを抽出（ユニークASIN: {unique_asins}件）")

        return all_data

    except Exception as e:
        log(f"[ERROR] データ抽出エラー: {e}")
        raise
