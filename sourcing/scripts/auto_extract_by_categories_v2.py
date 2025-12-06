"""
SellerSprite カテゴリ別ASIN自動抽出スクリプト v2（履歴管理機能付き）

v1からの改善点:
- カテゴリごとのページ取得履歴を管理
- 前回の続きから抽出を再開可能
- ページ深さを20ページまで拡張可能（v1は10ページまで）
- 履歴ファイル（JSON）で進捗を永続化

使用例:
    # 初回実行（履歴ファイルを作成）
    python sourcing/scripts/auto_extract_by_categories_v2.py \
      --target-new-asins 3000 \
      --pages-per-category 10 \
      --history-file category_history.json

    # 前回の続きから実行（11ページ目から20ページ目まで）
    python sourcing/scripts/auto_extract_by_categories_v2.py \
      --target-new-asins 3000 \
      --resume \
      --history-file category_history.json \
      --pages-per-category 20

履歴ファイル形式:
    {
      "categories": {
        "カテゴリ名": {
          "nodeIdPaths": "[\"...\"]",
          "pages_extracted": 10,
          "last_updated": "2025-11-28T01:33:59",
          "asins_count": 458
        }
      },
      "metadata": {
        "total_asins": 3375,
        "last_run": "2025-11-28T01:54:58"
      }
    }
"""

import argparse
import asyncio
import sys
import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Set, Optional
from collections import Counter
from dotenv import load_dotenv

# ecautoプロジェクトのルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# .envファイルを読み込む
env_path = project_root / 'sourcing' / 'sources' / 'sellersprite' / '.env'
load_dotenv(dotenv_path=env_path)

# 共通モジュールからインポート
from sourcing.sources.sellersprite.utils.category_extractor import (
    build_product_research_url,
    create_browser_session
)


class CategoryHistoryManager:
    """カテゴリ履歴管理クラス"""

    def __init__(self, history_file: Path):
        self.history_file = history_file
        self.history = self._load_history()

    def _load_history(self) -> Dict:
        """履歴ファイルを読み込む"""
        if self.history_file.exists():
            with open(self.history_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            return {
                "categories": {},
                "metadata": {
                    "total_asins": 0,
                    "last_run": None
                }
            }

    def save_history(self):
        """履歴ファイルに保存"""
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.history_file, 'w', encoding='utf-8') as f:
            json.dump(self.history, f, ensure_ascii=False, indent=2)

    def get_category_info(self, category_name: str) -> Optional[Dict]:
        """カテゴリ情報を取得"""
        return self.history['categories'].get(category_name)

    def update_category(
        self,
        category_name: str,
        node_id_paths: str,
        pages_extracted: int,
        asins_count: int
    ):
        """カテゴリ情報を更新"""
        if category_name not in self.history['categories']:
            self.history['categories'][category_name] = {}

        self.history['categories'][category_name].update({
            'nodeIdPaths': node_id_paths,
            'pages_extracted': pages_extracted,
            'last_updated': datetime.now().isoformat(),
            'asins_count': asins_count
        })

    def update_metadata(self, total_asins: int):
        """メタデータを更新"""
        self.history['metadata']['total_asins'] = total_asins
        self.history['metadata']['last_run'] = datetime.now().isoformat()

    def get_categories_to_process(self, max_pages: int) -> List[tuple]:
        """
        処理すべきカテゴリリストを取得

        Args:
            max_pages: 最大ページ数

        Returns:
            [(category_name, category_info, start_page), ...]
        """
        categories_to_process = []

        for cat_name, cat_info in self.history['categories'].items():
            pages_extracted = cat_info.get('pages_extracted', 0)

            # まだ max_pages まで到達していないカテゴリを対象
            if pages_extracted < max_pages:
                start_page = pages_extracted + 1
                categories_to_process.append((cat_name, cat_info, start_page))

        return categories_to_process


async def extract_asins_with_categories_paginated(
    page,
    limit: int,
    start_page: int = 1
) -> List[Dict[str, str]]:
    """
    ページング対応のASIN抽出（開始ページ指定可能）

    Args:
        page: Playwrightページオブジェクト
        limit: 取得件数
        start_page: 開始ページ（1-20）

    Returns:
        [{"asin": "B00XXXXX", "category": "...", "nodeIdPaths": "..."}, ...]
    """
    from sourcing.sources.sellersprite.utils.category_extractor import log

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
        except Exception as e:
            log(f"[WARN] リスト表示への切り替えエラー: {e}")

        # 必要なページ数を計算
        pages_needed = (limit + 99) // 100
        end_page = min(start_page + pages_needed - 1, 20)  # 最大20ページまで

        log(f"ページネーション: {start_page}ページ目から{end_page}ページ目まで抽出予定")

        # 開始ページまで移動（start_page > 1の場合）
        if start_page > 1:
            log(f"  開始ページ {start_page} まで移動中...")
            for _ in range(start_page - 1):
                try:
                    next_button = page.locator('button.btn-next:not([disabled])')
                    button_count = await next_button.count()

                    if button_count > 0:
                        await next_button.click()
                        await page.wait_for_load_state("networkidle", timeout=30000)
                        await asyncio.sleep(1)
                    else:
                        log(f"[WARN] 次のページボタンが見つかりません")
                        return all_data
                except Exception as e:
                    log(f"[ERROR] ページ移動エラー: {e}")
                    return all_data

            log(f"  → {start_page}ページ目に到達")

        # データ抽出ループ
        for page_num in range(start_page, end_page + 1):
            log(f"  ページ {page_num}/20 を処理中...")

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

            # テーブルの全行を走査してASINとカテゴリを抽出
            data_on_page = await page.evaluate('''() => {
                const data = [];
                const rows = Array.from(document.querySelectorAll('table tbody tr'));

                let currentAsin = null;

                rows.forEach((row, index) => {
                    const rowText = row.textContent || '';
                    const asinMatch = rowText.match(/ASIN:\\s*([A-Z0-9]{10})/);

                    if (asinMatch) {
                        currentAsin = asinMatch[1];
                    }

                    const tableExpand = row.querySelector('.table-expand');
                    if (tableExpand && currentAsin) {
                        let categories = [];
                        let nodeIdPaths = '';

                        const productType = tableExpand.querySelector('.product-type');
                        if (productType) {
                            const categoryLinks = productType.querySelectorAll('a.type');

                            categoryLinks.forEach((link, linkIndex) => {
                                const categoryName = link.textContent.trim();
                                if (categoryName) {
                                    categories.push(categoryName);
                                }

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

                        data.push({
                            asin: currentAsin,
                            category: categories.join(' > '),
                            nodeIdPaths: nodeIdPaths
                        });

                        currentAsin = null;
                    }
                });

                return data;
            }''')

            categories_found = sum(1 for item in data_on_page if item.get('category'))
            log(f"    → カテゴリ情報: {categories_found}件 / {len(data_on_page)}件")
            log(f"    → {len(data_on_page)}件抽出")
            all_data.extend(data_on_page)

            # 最後のページでない場合、次のページに移動
            if page_num < end_page:
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

        # limit件数まで制限
        all_data = all_data[:limit]
        log(f"合計 {len(all_data)}件のデータを抽出（目標: {limit}件）")

        return all_data

    except Exception as e:
        log(f"[ERROR] データ抽出エラー: {e}")
        raise


class CategoryBasedExtractorV2:
    """カテゴリベースのASIN抽出クラス v2（履歴管理機能付き）"""

    def __init__(self, args):
        self.args = args
        self.db_path = project_root / 'sourcing' / 'data' / 'sourcing.db'
        self.history_manager = CategoryHistoryManager(Path(args.history_file))

        # 統計情報
        self.stats = {
            'total_extracted': 0,
            'new_asins': 0,
            'duplicate_asins': 0,
            'categories_processed': 0,
        }

    def log(self, message: str):
        """ログ出力"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")

    async def run(self):
        """メイン処理"""
        self.log("=" * 60)
        self.log("カテゴリベースASIN自動抽出 v2（履歴管理機能付き）")
        self.log("=" * 60)
        self.log(f"目標新規ASIN数: {self.args.target_new_asins}件")
        self.log(f"カテゴリあたりのページ数: {self.args.pages_per_category}ページ")
        self.log(f"再開モード: {'ON' if self.args.resume else 'OFF'}")
        self.log(f"履歴ファイル: {self.args.history_file}")
        self.log("")

        try:
            async with create_browser_session(headless=False) as (browser, page):
                if self.args.resume:
                    # 再開モード: 履歴から続きを処理
                    await self._resume_extraction(page)
                else:
                    # 通常モード: 新規に抽出
                    await self._normal_extraction(page)

                # 完了レポート
                self.log("")
                self.log("=" * 60)
                self.log("抽出完了")
                self.log("=" * 60)
                self.log(f"新規ASIN数: {self.stats['new_asins']}件")
                self.log(f"処理カテゴリ数: {self.stats['categories_processed']}件")
                self.log(f"総抽出ASIN数: {self.stats['total_extracted']}件")
                self.log(f"重複ASIN数: {self.stats['duplicate_asins']}件")
                if self.stats['total_extracted'] > 0:
                    self.log(f"新規率: {self.stats['new_asins'] / self.stats['total_extracted'] * 100:.1f}%")

        except KeyboardInterrupt:
            self.log("")
            self.log("[WARN] ユーザーによって中断されました")
            sys.exit(130)

        except Exception as e:
            self.log("")
            self.log("[ERROR] エラーが発生しました")
            self.log(f"エラー内容: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

    async def _resume_extraction(self, page):
        """再開モード: 履歴から続きを処理"""
        self.log("【再開モード】履歴ファイルから処理を再開します")

        categories_to_process = self.history_manager.get_categories_to_process(
            self.args.pages_per_category
        )

        if not categories_to_process:
            self.log("[WARN] 処理すべきカテゴリが見つかりません")
            self.log("[INFO] 全カテゴリが指定ページ数まで処理済みです")
            return

        self.log(f"  処理対象カテゴリ数: {len(categories_to_process)}件")

        all_new_asins = set()

        for i, (category_name, category_info, start_page) in enumerate(categories_to_process):
            if len(all_new_asins) >= self.args.target_new_asins:
                self.log(f"[OK] 目標達成: {len(all_new_asins)}件の新規ASIN")
                break

            self.log("")
            self.log(f"[カテゴリ {i+1}/{len(categories_to_process)}]")
            self.log(f"  カテゴリ: {category_name}")
            self.log(f"  nodeIdPaths: {category_info['nodeIdPaths']}")
            self.log(f"  取得済みページ: {category_info.get('pages_extracted', 0)}ページ")
            self.log(f"  開始ページ: {start_page}ページ")

            # カテゴリ別抽出
            new_asins = await self._extract_by_category_paginated(
                page,
                category_name,
                category_info['nodeIdPaths'],
                start_page,
                all_new_asins
            )

            all_new_asins.update(new_asins)
            self.stats['categories_processed'] += 1

            self.log(f"  → 累計新規ASIN: {len(all_new_asins)}件 / {self.args.target_new_asins}件")

        # 結果保存
        await self._save_results(all_new_asins, categories_to_process)

    async def _normal_extraction(self, page):
        """通常モード: 新規に抽出"""
        self.log("【通常モード】新規にカテゴリを探索して抽出します")

        # ステップ1: 初期サンプリング
        self.log("【ステップ1】初期サンプリングを開始...")
        sample_data = await self._initial_sampling(page)

        if not sample_data:
            self.log("[ERROR] サンプリングでデータが取得できませんでした")
            return

        # ステップ2: カテゴリ統計
        self.log("")
        self.log("【ステップ2】カテゴリ統計を分析中...")
        category_stats = self._analyze_categories(sample_data)

        if not category_stats:
            self.log("[ERROR] カテゴリ情報が取得できませんでした")
            return

        # ステップ3: 既存DBと比較
        self.log("")
        self.log("【ステップ3】既存DBのカテゴリ分布を確認中...")
        existing_categories = self._get_existing_categories()
        unexplored_categories = self._identify_unexplored_categories(
            category_stats, existing_categories
        )

        # ステップ4: 優先順位付け
        self.log("")
        self.log("【ステップ4】カテゴリを優先順位付け中...")
        prioritized_categories = self._prioritize_categories(
            category_stats, unexplored_categories
        )

        if not prioritized_categories:
            self.log("[WARN] 優先すべきカテゴリが見つかりませんでした")
            return

        # ステップ5: カテゴリ別抽出ループ
        self.log("")
        self.log("【ステップ5】カテゴリ別抽出を開始...")
        all_new_asins = set()

        for i, (category_name, category_info) in enumerate(prioritized_categories):
            if len(all_new_asins) >= self.args.target_new_asins:
                self.log(f"[OK] 目標達成: {len(all_new_asins)}件の新規ASIN")
                break

            self.log("")
            self.log(f"[カテゴリ {i+1}/{len(prioritized_categories)}]")
            self.log(f"  カテゴリ: {category_name}")
            self.log(f"  nodeIdPaths: {category_info['nodeIdPaths']}")

            # カテゴリ別抽出（1ページ目から）
            new_asins = await self._extract_by_category_paginated(
                page,
                category_name,
                category_info['nodeIdPaths'],
                start_page=1,
                already_found_asins=all_new_asins
            )

            all_new_asins.update(new_asins)
            self.stats['categories_processed'] += 1

            self.log(f"  → 累計新規ASIN: {len(all_new_asins)}件 / {self.args.target_new_asins}件")

        # 結果保存
        await self._save_results(all_new_asins, prioritized_categories)

    async def _initial_sampling(self, page) -> List[Dict]:
        """初期サンプリング"""
        self.log(f"  サンプルサイズ: {self.args.sample_size}件")

        if self.args.use_intermediate_categories:
            self.log(f"  中間カテゴリ抽出モード: ON（全階層を抽出）")
        else:
            self.log(f"  中間カテゴリ抽出モード: OFF（最深カテゴリのみ）")

        url = build_product_research_url(
            market=self.args.market,
            sales_min=self.args.sales_min,
            price_min=self.args.price_min,
            amz=True,
            fba=True
        )

        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(5000)

        # データ抽出（フラグに応じて関数を選択）
        if self.args.use_intermediate_categories:
            from sourcing.sources.sellersprite.utils.category_extractor_v2 import extract_asins_with_all_category_levels
            data = await extract_asins_with_all_category_levels(page, self.args.sample_size)

            # v2のデータは複数エントリ（ASIN×カテゴリレベル）を返すため、統計を計算
            unique_asins = len(set(item['asin'] for item in data))
            self.log(f"  → {len(data)}件のカテゴリエントリを取得（ユニークASIN: {unique_asins}件）")
        else:
            from sourcing.sources.sellersprite.utils.category_extractor import extract_asins_with_categories
            data = await extract_asins_with_categories(page, self.args.sample_size)

            self.log(f"  → {len(data)}件のデータを取得")

            categories_found = sum(1 for item in data if item.get('category'))
            self.log(f"  → カテゴリ情報あり: {categories_found}件 / {len(data)}件")

        return data

    def _analyze_categories(self, data: List[Dict]) -> Dict[str, Dict]:
        """カテゴリごとの統計情報を分析"""
        category_stats = {}

        for item in data:
            category = item.get('category', '').strip()
            node_id_paths = item.get('nodeIdPaths', '').strip()

            if not category:
                continue

            if category not in category_stats:
                category_stats[category] = {
                    'count': 0,
                    'nodeIdPaths': node_id_paths
                }

            category_stats[category]['count'] += 1

        sorted_stats = dict(
            sorted(category_stats.items(), key=lambda x: x[1]['count'], reverse=True)
        )

        self.log(f"  発見されたカテゴリ数: {len(sorted_stats)}件")
        self.log(f"  トップ5カテゴリ:")
        for i, (category, info) in enumerate(list(sorted_stats.items())[:5]):
            self.log(f"    {i+1}. {category}: {info['count']}件")

        return sorted_stats

    def _get_existing_categories(self) -> Dict[str, int]:
        """既存DBのカテゴリ分布を取得"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute('''
                SELECT category, COUNT(*) as count
                FROM sourcing_candidates
                WHERE category IS NOT NULL AND category != ''
                GROUP BY category
                ORDER BY count DESC
            ''')

            rows = cursor.fetchall()
            existing_categories = {row[0]: row[1] for row in rows}

            self.log(f"  既存DB内のカテゴリ数: {len(existing_categories)}件")

            return existing_categories

        finally:
            conn.close()

    def _identify_unexplored_categories(
        self,
        category_stats: Dict[str, Dict],
        existing_categories: Dict[str, int]
    ) -> Set[str]:
        """未開拓カテゴリを特定"""
        unexplored = set()

        for category in category_stats.keys():
            if category not in existing_categories:
                unexplored.add(category)

        self.log(f"  未開拓カテゴリ数: {len(unexplored)}件")

        return unexplored

    def _prioritize_categories(
        self,
        category_stats: Dict[str, Dict],
        unexplored_categories: Set[str]
    ) -> List[tuple]:
        """カテゴリを優先順位付け"""
        unexplored_list = [
            (cat, info) for cat, info in category_stats.items()
            if cat in unexplored_categories
        ]

        explored_list = [
            (cat, info) for cat, info in category_stats.items()
            if cat not in unexplored_categories
        ]

        prioritized = unexplored_list + explored_list
        prioritized = prioritized[:self.args.max_categories]

        self.log(f"  優先順位付け完了: {len(prioritized)}カテゴリを処理対象に")

        return prioritized

    async def _extract_by_category_paginated(
        self,
        page,
        category_name: str,
        node_id_paths: str,
        start_page: int,
        already_found_asins: Set[str]
    ) -> Set[str]:
        """特定カテゴリからASINを抽出（ページ指定可能）"""
        if not node_id_paths:
            self.log(f"  [WARN] nodeIdPathsが空のためスキップ")
            return set()

        try:
            url = build_product_research_url(
                market=self.args.market,
                sales_min=self.args.sales_min,
                price_min=self.args.price_min,
                amz=True,
                fba=True,
                node_id_paths=node_id_paths
            )

            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(5000)

            # ページ数を計算
            items_per_page = 100
            pages_to_extract = self.args.pages_per_category - (start_page - 1)
            limit = min(pages_to_extract * items_per_page, 2000)  # 最大2000件

            # データ抽出
            data = await extract_asins_with_categories_paginated(page, limit, start_page)

            asins = {item['asin'] for item in data if item.get('asin')}
            self.stats['total_extracted'] += len(asins)

            # 既存DBのASINを取得
            existing_asins = self._get_existing_asins()

            # 重複チェック
            new_asins = asins - existing_asins - already_found_asins

            duplicate_count = len(asins) - len(new_asins)
            self.stats['duplicate_asins'] += duplicate_count
            self.stats['new_asins'] += len(new_asins)

            self.log(f"  取得: {len(asins)}件")
            self.log(f"  新規: {len(new_asins)}件 ({len(new_asins)/max(len(asins), 1)*100:.1f}%)")
            self.log(f"  重複: {duplicate_count}件")

            # 履歴を更新
            self.history_manager.update_category(
                category_name,
                node_id_paths,
                start_page + pages_to_extract - 1,
                len(new_asins)
            )
            self.history_manager.save_history()

            return new_asins

        except Exception as e:
            self.log(f"  [ERROR] カテゴリ抽出エラー: {e}")
            return set()

    def _get_existing_asins(self) -> Set[str]:
        """既存DBのASINセットを取得"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute('SELECT asin FROM sourcing_candidates')
            rows = cursor.fetchall()
            return {row[0] for row in rows}

        finally:
            conn.close()

    async def _save_results(self, new_asins: Set[str], categories: List[tuple]):
        """結果を保存"""
        if self.args.output:
            output_path = Path(self.args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with output_path.open('w', encoding='utf-8') as f:
                for asin in sorted(new_asins):
                    f.write(f"{asin}\n")

            self.log(f"  ASINファイル保存: {output_path}")
            self.log(f"  保存件数: {len(new_asins)}件")

        if self.args.report:
            await self._generate_report(new_asins, categories)

        # 履歴メタデータ更新
        self.history_manager.update_metadata(len(new_asins))
        self.history_manager.save_history()
        self.log(f"  履歴ファイル更新: {self.args.history_file}")

    async def _generate_report(self, new_asins: Set[str], categories: List[tuple]):
        """レポートを生成"""
        report_path = Path(self.args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)

        with report_path.open('w', encoding='utf-8') as f:
            f.write(f"# カテゴリベースASIN自動抽出レポート v2\n\n")
            f.write(f"**実行日時**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            f.write(f"## 📊 抽出結果サマリー\n\n")
            f.write(f"| 指標 | 値 |\n")
            f.write(f"|------|------|\n")
            f.write(f"| 新規ASIN数 | {len(new_asins)}件 |\n")
            f.write(f"| 総抽出ASIN数 | {self.stats['total_extracted']}件 |\n")
            f.write(f"| 重複ASIN数 | {self.stats['duplicate_asins']}件 |\n")
            if self.stats['total_extracted'] > 0:
                f.write(f"| 新規率 | {len(new_asins) / self.stats['total_extracted'] * 100:.1f}% |\n")
            f.write(f"| 処理カテゴリ数 | {self.stats['categories_processed']}件 |\n")
            f.write(f"\n")

            f.write(f"## 📂 処理カテゴリ一覧\n\n")
            for i, item in enumerate(categories[:self.stats['categories_processed']]):
                if len(item) == 3:  # 再開モード
                    category, info, start_page = item
                    f.write(f"{i+1}. **{category}**\n")
                    f.write(f"   - nodeIdPaths: `{info['nodeIdPaths']}`\n")
                    f.write(f"   - 開始ページ: {start_page}ページ\n")
                else:  # 通常モード
                    category, info = item
                    f.write(f"{i+1}. **{category}**\n")
                    f.write(f"   - サンプル内商品数: {info['count']}件\n")
                    f.write(f"   - nodeIdPaths: `{info['nodeIdPaths']}`\n")
                f.write(f"\n")

            f.write(f"## ⚙️ 実行パラメータ\n\n")
            f.write(f"```\n")
            f.write(f"目標新規ASIN数: {self.args.target_new_asins}件\n")
            f.write(f"カテゴリあたりのページ数: {self.args.pages_per_category}ページ\n")
            f.write(f"再開モード: {'ON' if self.args.resume else 'OFF'}\n")
            f.write(f"履歴ファイル: {self.args.history_file}\n")
            f.write(f"販売数範囲: {self.args.sales_min} 以上\n")
            f.write(f"価格範囲: {self.args.price_min} 以上\n")
            f.write(f"市場: {self.args.market}\n")
            f.write(f"```\n")

        self.log(f"  レポート保存: {report_path}")


async def main():
    """メイン処理"""
    parser = argparse.ArgumentParser(
        description="SellerSprite カテゴリベースASIN自動抽出 v2（履歴管理機能付き）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # 初回実行（履歴ファイルを作成）
  python sourcing/scripts/auto_extract_by_categories_v2.py \\
    --target-new-asins 3000 \\
    --pages-per-category 10 \\
    --history-file category_history.json \\
    --output asins_batch1.txt \\
    --report report_batch1.md

  # 前回の続きから実行（11ページ目から20ページ目まで）
  python sourcing/scripts/auto_extract_by_categories_v2.py \\
    --target-new-asins 3000 \\
    --resume \\
    --history-file category_history.json \\
    --pages-per-category 20 \\
    --output asins_batch2.txt \\
    --report report_batch2.md
        """
    )

    # 目標パラメータ
    parser.add_argument(
        "--target-new-asins",
        type=int,
        default=3000,
        help="目標新規ASIN数（デフォルト: 3000）"
    )

    # ページングパラメータ
    parser.add_argument(
        "--pages-per-category",
        type=int,
        default=10,
        help="各カテゴリの最大ページ数（1-20、デフォルト: 10）"
    )

    # 履歴管理パラメータ
    parser.add_argument(
        "--resume",
        action="store_true",
        help="前回の続きから実行（履歴ファイルから再開）"
    )
    parser.add_argument(
        "--history-file",
        type=str,
        required=True,
        help="履歴ファイルのパス（JSON形式）"
    )

    # サンプリングパラメータ（通常モードのみ）
    parser.add_argument(
        "--sample-size",
        type=int,
        default=1000,
        help="初期サンプルサイズ（デフォルト: 1000、最大: 2000）"
    )
    parser.add_argument(
        "--max-categories",
        type=int,
        default=30,
        help="最大カテゴリ数（デフォルト: 30）"
    )

    # フィルターパラメータ
    parser.add_argument(
        "--sales-min",
        type=int,
        default=300,
        help="月間販売数の最小値（デフォルト: 300）"
    )
    parser.add_argument(
        "--price-min",
        type=int,
        default=2500,
        help="価格の最小値（デフォルト: 2500）"
    )
    parser.add_argument(
        "--market",
        type=str,
        default="JP",
        help="市場（デフォルト: JP）"
    )

    # 出力パラメータ
    parser.add_argument(
        "--output",
        type=str,
        help="出力ファイルパス（ASIN一覧）"
    )
    parser.add_argument(
        "--report",
        type=str,
        help="レポートファイルパス（Markdown形式）"
    )

    # 中間カテゴリ機能（実験的）
    parser.add_argument(
        "--use-intermediate-categories",
        action="store_true",
        help="中間カテゴリも抽出対象に含める（例：「A > B > C > D」から全階層を抽出）"
    )

    args = parser.parse_args()

    # 実行
    extractor = CategoryBasedExtractorV2(args)
    await extractor.run()


if __name__ == "__main__":
    asyncio.run(main())
