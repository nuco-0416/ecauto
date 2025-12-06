"""
SellerSprite カテゴリ別ASIN自動抽出スクリプト

カテゴリ軸でASINを自動抽出することで、既存データとの重複を最小化し、
新規ASINを効率的に取得する。

使用例:
    # 基本的な使用方法（目標10,000件の新規ASIN）
    python sourcing/scripts/auto_extract_by_categories.py \
      --target-new-asins 10000 \
      --sample-size 1000 \
      --asins-per-category 2000 \
      --sales-min 300 \
      --price-min 2500

    # カテゴリ数を制限して実行
    python sourcing/scripts/auto_extract_by_categories.py \
      --target-new-asins 5000 \
      --max-categories 10 \
      --output category_asins_20251126.txt

フロー:
    1. 初期サンプリング（500-1,000件）でカテゴリ情報を取得
    2. カテゴリごとの商品数をカウント
    3. 既存DBのカテゴリ分布と比較して未開拓カテゴリを特定
    4. 未開拓カテゴリを優先順位付け
    5. 各カテゴリで2,000件ずつ抽出（nodeIdPathsを使用）
    6. リアルタイムで重複チェック
    7. 目標件数に達するまで繰り返し
"""

import argparse
import asyncio
import sys
import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Set
from collections import Counter
from dotenv import load_dotenv

# ecautoプロジェクトのルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# .envファイルを読み込む
env_path = project_root / 'sourcing' / 'sources' / 'sellersprite' / '.env'
load_dotenv(dotenv_path=env_path)

# 共通モジュールからインポート（クリーンな実装を使用）
from sourcing.sources.sellersprite.utils.category_extractor import (
    build_product_research_url,
    extract_asins_with_categories,
    create_browser_session
)


class CategoryBasedExtractor:
    """カテゴリベースのASIN抽出クラス"""

    def __init__(self, args):
        """
        Args:
            args: コマンドライン引数
        """
        self.args = args
        self.db_path = project_root / 'sourcing' / 'data' / 'sourcing.db'

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
        self.log("カテゴリベースASIN自動抽出を開始")
        self.log("=" * 60)
        self.log(f"目標新規ASIN数: {self.args.target_new_asins}件")
        self.log(f"初期サンプルサイズ: {self.args.sample_size}件")
        self.log(f"カテゴリあたりの取得数: {self.args.asins_per_category}件")
        self.log(f"販売数範囲: {self.args.sales_min} 以上")
        self.log(f"価格範囲: {self.args.price_min} 以上")
        self.log("")

        try:
            # ブラウザセッションを1回だけ作成（全ての処理で再利用）
            async with create_browser_session(headless=False) as (browser, page):
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
                    self.log("[INFO] 全カテゴリから抽出を試みます")
                    prioritized_categories = list(category_stats.items())[:self.args.max_categories]

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
                    self.log(f"  サンプル内商品数: {category_info['count']}件")
                    self.log(f"  nodeIdPaths: {category_info['nodeIdPaths']}")

                    # カテゴリ別抽出
                    new_asins = await self._extract_by_category(
                        page,
                        category_name,
                        category_info['nodeIdPaths'],
                        all_new_asins
                    )

                    all_new_asins.update(new_asins)
                    self.stats['categories_processed'] += 1

                    self.log(f"  → 累計新規ASIN: {len(all_new_asins)}件 / {self.args.target_new_asins}件")

                # ステップ6: 結果保存
                self.log("")
                self.log("【ステップ6】結果を保存中...")
                await self._save_results(all_new_asins, prioritized_categories)

                # 完了レポート
                self.log("")
                self.log("=" * 60)
                self.log("抽出完了")
                self.log("=" * 60)
                self.log(f"新規ASIN数: {len(all_new_asins)}件")
                self.log(f"処理カテゴリ数: {self.stats['categories_processed']}件")
                self.log(f"総抽出ASIN数: {self.stats['total_extracted']}件")
                self.log(f"重複ASIN数: {self.stats['duplicate_asins']}件")
                if self.stats['total_extracted'] > 0:
                    self.log(f"新規率: {len(all_new_asins) / self.stats['total_extracted'] * 100:.1f}%")

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

    async def _initial_sampling(self, page) -> List[Dict]:
        """
        初期サンプリング: カテゴリ情報付きでASINを取得

        共通モジュール（category_extractor）のクリーンな実装を使用

        Args:
            page: Playwrightページオブジェクト

        Returns:
            [{"asin": "B00XXX", "category": "Home & Kitchen", "nodeIdPaths": "[...]"}, ...]
        """
        self.log(f"  サンプルサイズ: {self.args.sample_size}件")

        # URLを構築
        url = build_product_research_url(
            market=self.args.market,
            sales_min=self.args.sales_min,
            price_min=self.args.price_min,
            amz=True,
            fba=True
        )

        # ページに遷移
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(5000)

        # データ抽出（クリーンな実装を使用）
        data = await extract_asins_with_categories(page, self.args.sample_size)

        self.log(f"  → {len(data)}件のデータを取得")

        # デバッグ: カテゴリ情報が取得できているか確認
        categories_found = sum(1 for item in data if item.get('category'))
        self.log(f"  → カテゴリ情報あり: {categories_found}件 / {len(data)}件")

        return data

    def _analyze_categories(self, data: List[Dict]) -> Dict[str, Dict]:
        """
        カテゴリごとの統計情報を分析

        Args:
            data: [{"asin": "B00XXX", "category": "...", "nodeIdPaths": "..."}, ...]

        Returns:
            {
                "Home & Kitchen": {"count": 50, "nodeIdPaths": "[...]"},
                "Beauty": {"count": 30, "nodeIdPaths": "[...]"},
                ...
            }
        """
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

        # カウント順にソート
        sorted_stats = dict(
            sorted(category_stats.items(), key=lambda x: x[1]['count'], reverse=True)
        )

        self.log(f"  発見されたカテゴリ数: {len(sorted_stats)}件")
        self.log(f"  トップ5カテゴリ:")
        for i, (category, info) in enumerate(list(sorted_stats.items())[:5]):
            self.log(f"    {i+1}. {category}: {info['count']}件")

        return sorted_stats

    def _get_existing_categories(self) -> Dict[str, int]:
        """
        既存DBのカテゴリ分布を取得

        Returns:
            {"Home & Kitchen": 1200, "Beauty": 800, ...}
        """
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
            if existing_categories:
                top_existing = list(existing_categories.items())[:3]
                self.log(f"  既存トップ3カテゴリ:")
                for category, count in top_existing:
                    self.log(f"    - {category}: {count}件")

            return existing_categories

        finally:
            conn.close()

    def _identify_unexplored_categories(
        self,
        category_stats: Dict[str, Dict],
        existing_categories: Dict[str, int]
    ) -> Set[str]:
        """
        未開拓カテゴリを特定

        Args:
            category_stats: サンプルから得られたカテゴリ統計
            existing_categories: 既存DBのカテゴリ分布

        Returns:
            未開拓カテゴリのセット
        """
        unexplored = set()

        for category in category_stats.keys():
            if category not in existing_categories:
                unexplored.add(category)

        self.log(f"  未開拓カテゴリ数: {len(unexplored)}件")

        if unexplored:
            self.log(f"  未開拓カテゴリ例:")
            for i, category in enumerate(list(unexplored)[:5]):
                self.log(f"    - {category}")

        return unexplored

    def _prioritize_categories(
        self,
        category_stats: Dict[str, Dict],
        unexplored_categories: Set[str]
    ) -> List[tuple]:
        """
        カテゴリを優先順位付け

        優先順位:
        1. 未開拓カテゴリ（商品数が多い順）
        2. 既存カテゴリ（商品数が多い順）

        Args:
            category_stats: カテゴリ統計
            unexplored_categories: 未開拓カテゴリセット

        Returns:
            [(category_name, category_info), ...]
        """
        # 未開拓カテゴリを優先
        unexplored_list = [
            (cat, info) for cat, info in category_stats.items()
            if cat in unexplored_categories
        ]

        # 既存カテゴリ
        explored_list = [
            (cat, info) for cat, info in category_stats.items()
            if cat not in unexplored_categories
        ]

        # 結合（未開拓 → 既存の順）
        prioritized = unexplored_list + explored_list

        # max_categories まで制限
        prioritized = prioritized[:self.args.max_categories]

        self.log(f"  優先順位付け完了: {len(prioritized)}カテゴリを処理対象に")
        self.log(f"  内訳: 未開拓={len(unexplored_list[:self.args.max_categories])}件, "
                 f"既存={len(prioritized) - len(unexplored_list[:self.args.max_categories])}件")

        return prioritized

    async def _extract_by_category(
        self,
        page,
        category_name: str,
        node_id_paths: str,
        already_found_asins: Set[str]
    ) -> Set[str]:
        """
        特定カテゴリからASINを抽出

        共通モジュール（category_extractor）のクリーンな実装を使用

        Args:
            page: Playwrightページオブジェクト
            category_name: カテゴリ名
            node_id_paths: nodeIdPaths（例: '["3760911:11060451"]'）
            already_found_asins: 既に見つかっているASINセット（今回の実行で）

        Returns:
            新規ASINのセット
        """
        if not node_id_paths:
            self.log(f"  [WARN] nodeIdPathsが空のためスキップ")
            return set()

        try:
            # URLを構築（nodeIdPathsでフィルター）
            url = build_product_research_url(
                market=self.args.market,
                sales_min=self.args.sales_min,
                price_min=self.args.price_min,
                amz=True,
                fba=True,
                node_id_paths=node_id_paths
            )

            # ページに遷移
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(5000)

            # データ抽出（カテゴリ情報は不要なので高速）
            data = await extract_asins_with_categories(page, self.args.asins_per_category)

            # ASINのみ抽出
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

            return new_asins

        except Exception as e:
            self.log(f"  [ERROR] カテゴリ抽出エラー: {e}")
            return set()

    def _get_existing_asins(self) -> Set[str]:
        """
        既存DBのASINセットを取得

        Returns:
            既存ASINのセット
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute('SELECT asin FROM sourcing_candidates')
            rows = cursor.fetchall()
            return {row[0] for row in rows}

        finally:
            conn.close()

    async def _save_results(self, new_asins: Set[str], categories: List[tuple]):
        """
        結果を保存

        Args:
            new_asins: 新規ASINセット
            categories: 処理したカテゴリリスト
        """
        # ASINをファイルに保存
        if self.args.output:
            output_path = Path(self.args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with output_path.open('w', encoding='utf-8') as f:
                for asin in sorted(new_asins):
                    f.write(f"{asin}\n")

            self.log(f"  ASINファイル保存: {output_path}")
            self.log(f"  保存件数: {len(new_asins)}件")

        # レポート生成
        if self.args.report:
            await self._generate_report(new_asins, categories)

    async def _generate_report(self, new_asins: Set[str], categories: List[tuple]):
        """
        レポートを生成

        Args:
            new_asins: 新規ASINセット
            categories: 処理したカテゴリリスト
        """
        report_path = Path(self.args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)

        with report_path.open('w', encoding='utf-8') as f:
            f.write(f"# カテゴリベースASIN自動抽出レポート\n\n")
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
            for i, (category, info) in enumerate(categories[:self.stats['categories_processed']]):
                f.write(f"{i+1}. **{category}**\n")
                f.write(f"   - サンプル内商品数: {info['count']}件\n")
                f.write(f"   - nodeIdPaths: `{info['nodeIdPaths']}`\n")
                f.write(f"\n")

            f.write(f"## ⚙️ 実行パラメータ\n\n")
            f.write(f"```\n")
            f.write(f"目標新規ASIN数: {self.args.target_new_asins}件\n")
            f.write(f"初期サンプルサイズ: {self.args.sample_size}件\n")
            f.write(f"カテゴリあたりの取得数: {self.args.asins_per_category}件\n")
            f.write(f"最大カテゴリ数: {self.args.max_categories}件\n")
            f.write(f"販売数範囲: {self.args.sales_min} 以上\n")
            f.write(f"価格範囲: {self.args.price_min} 以上\n")
            f.write(f"市場: {self.args.market}\n")
            f.write(f"```\n")

        self.log(f"  レポート保存: {report_path}")


async def main():
    """メイン処理"""
    parser = argparse.ArgumentParser(
        description="SellerSprite カテゴリベースASIN自動抽出",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # 基本的な使用方法（目標10,000件の新規ASIN）
  python sourcing/scripts/auto_extract_by_categories.py \\
    --target-new-asins 10000 \\
    --sample-size 1000 \\
    --asins-per-category 2000 \\
    --sales-min 300 \\
    --price-min 2500

  # カテゴリ数を制限して実行
  python sourcing/scripts/auto_extract_by_categories.py \\
    --target-new-asins 5000 \\
    --max-categories 10 \\
    --output category_asins.txt \\
    --report category_report.md
        """
    )

    # 目標パラメータ
    parser.add_argument(
        "--target-new-asins",
        type=int,
        default=10000,
        help="目標新規ASIN数（デフォルト: 10000）"
    )

    # サンプリングパラメータ
    parser.add_argument(
        "--sample-size",
        type=int,
        default=1000,
        help="初期サンプルサイズ（デフォルト: 1000、最大: 2000）"
    )
    parser.add_argument(
        "--asins-per-category",
        type=int,
        default=2000,
        help="各カテゴリの取得数（デフォルト: 2000、最大: 2000）"
    )
    parser.add_argument(
        "--max-categories",
        type=int,
        default=20,
        help="最大カテゴリ数（デフォルト: 20）"
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
        help="出力ファイルパス（ASIN一覧、指定しない場合は保存しない）"
    )
    parser.add_argument(
        "--report",
        type=str,
        help="レポートファイルパス（Markdown形式、指定しない場合は保存しない）"
    )

    args = parser.parse_args()

    # 実行
    extractor = CategoryBasedExtractor(args)
    await extractor.run()


if __name__ == "__main__":
    asyncio.run(main())
