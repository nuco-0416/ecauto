"""
SellerSprite 人気カテゴリ分析スクリプト（スタンドアロン版）

ランキング上位商品のカテゴリを分析して、人気カテゴリとnodeIdPathsを特定する。
共通モジュール（category_extractor）を使用したクリーンな実装。

使用例:
    # 上位50件からトップ5カテゴリを分析
    python sourcing/scripts/analyze_popular_categories.py \
      --sample-size 50 \
      --top-n 5 \
      --sales-min 300 \
      --price-min 2500
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import List, Dict
from collections import Counter
import json

# プロジェクトルート
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 共通モジュールからインポート
from sourcing.sources.sellersprite.utils.category_extractor import (
    log,
    build_product_research_url,
    extract_asins_with_categories,
    create_browser_session
)


async def main():
    """メイン処理"""
    parser = argparse.ArgumentParser(
        description="SellerSprite 人気カテゴリ分析（スタンドアロン版）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # 上位50件からトップ5カテゴリを分析
  python sourcing/scripts/analyze_popular_categories.py \\
    --sample-size 50 \\
    --top-n 5 \\
    --sales-min 300 \\
    --price-min 2500
        """
    )

    # サンプリングパラメータ
    parser.add_argument(
        "--sample-size",
        type=int,
        default=500,
        help="分析するサンプル数（デフォルト: 500、最大: 2000）"
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=10,
        help="上位N件のカテゴリを抽出（デフォルト: 10）"
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
    parser.add_argument(
        "--output",
        type=str,
        default=str(project_root / "sourcing" / "sources" / "sellersprite" / "popular_categories.json"),
        help="出力ファイルパス（JSON形式）"
    )

    args = parser.parse_args()

    print()
    print("=" * 60)
    print("SellerSprite 人気カテゴリ分析（スタンドアロン版）")
    print("=" * 60)
    print(f"サンプルサイズ: {args.sample_size}件")
    print(f"販売数範囲: {args.sales_min} 以上")
    print(f"価格範囲: {args.price_min} 以上")
    print(f"トップ {args.top_n} カテゴリを抽出")
    print()

    try:
        # ブラウザセッションを作成（ログイン済み）
        async with create_browser_session(headless=False) as (browser, page):
            # 商品リサーチページに遷移（URLパラメータでフィルター条件を指定）
            log(f"商品リサーチページに遷移中（市場: {args.market}）...")
            product_research_url = build_product_research_url(
                market=args.market,
                sales_min=args.sales_min,
                price_min=args.price_min,
                amz=True,
                fba=True
            )
            log(f"[URL] {product_research_url[:150]}...")

            await page.goto(product_research_url, wait_until="domcontentloaded", timeout=30000)
            log("[OK] ページ読み込み完了")

            # テーブルのレンダリングを待機
            await page.wait_for_timeout(5000)

            # ログイン状態を確認
            current_url = page.url
            if 'login' in current_url:
                log("[ERROR] ログインページにリダイレクトされました")
                raise Exception("セッションが無効です。再ログインが必要です")

            # カテゴリ情報付きでASINを抽出
            log("ASINとカテゴリ情報を抽出中...")
            data = await extract_asins_with_categories(
                page,
                args.sample_size
            )

            print()
            print("=" * 60)
            print("カテゴリ分析中")
            print("=" * 60)
            print(f"抽出データ: {len(data)}件")
            print()

            # デバッグ: 最初の3件のデータを確認
            print("【デバッグ】最初の3件のデータ:")
            for i, item in enumerate(data[:3]):
                print(f"  {i + 1}. ASIN: {item.get('asin', 'N/A')}")
                print(f"     Category: '{item.get('category', 'N/A')}'")
                print(f"     NodeIdPaths: '{item.get('nodeIdPaths', 'N/A')}'")
                print()

            # カテゴリごとに集計
            category_counts = Counter()
            category_to_node_id = {}

            for item in data:
                category = item.get('category', '')
                node_id_paths = item.get('nodeIdPaths', '')

                if category:
                    category_counts[category] += 1

                    # nodeIdPathsを記録（最初に見つかったものを使用）
                    if category not in category_to_node_id and node_id_paths:
                        category_to_node_id[category] = node_id_paths

            # トップNカテゴリを抽出
            top_categories = category_counts.most_common(args.top_n)

            print(f"【トップ {args.top_n} 人気カテゴリ】")
            print()

            results = []
            for i, (category, count) in enumerate(top_categories):
                node_id_paths = category_to_node_id.get(category, '')
                percentage = (count / len(data)) * 100

                print(f"{i + 1}. {category}")
                print(f"   商品数: {count}件 ({percentage:.1f}%)")
                print(f"   nodeIdPaths: {node_id_paths}")
                print()

                results.append({
                    "rank": i + 1,
                    "category": category,
                    "count": count,
                    "percentage": round(percentage, 1),
                    "nodeIdPaths": node_id_paths
                })

            # 結果を出力
            if args.output:
                output_path = Path(args.output)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(
                    json.dumps(results, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
                print(f"[OK] 結果を保存しました: {output_path}")

            print()
            print("[SUCCESS] 分析完了")

    except KeyboardInterrupt:
        print("\n\n[WARN] ユーザーによって中断されました")
        sys.exit(130)

    except Exception as e:
        print()
        print("=" * 60)
        print("[ERROR] エラーが発生しました")
        print("=" * 60)
        print(f"エラー内容: {e}")
        print()
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
