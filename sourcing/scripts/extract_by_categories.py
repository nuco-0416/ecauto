"""
SellerSprite カテゴリ別ASIN抽出スクリプト

カテゴリフィルターを使用して、カテゴリごとにASINを抽出する。
2000件制限を回避するために、カテゴリを分割して抽出。

使用例:
    # 単一カテゴリで抽出
    python sourcing/scripts/extract_by_categories.py \
      --categories "Health & Household > Healthcare" \
      --sales-min 300 \
      --price-min 2500 \
      --limit 1000

    # 複数カテゴリで抽出
    python sourcing/scripts/extract_by_categories.py \
      --categories "Health & Household > Healthcare" "Beauty & Personal Care > Skin Care" \
      --sales-min 300 \
      --price-min 2500 \
      --limit 500
"""

import argparse
import asyncio
import sys
from pathlib import Path
from datetime import datetime
from typing import List
from dotenv import load_dotenv

# ecautoプロジェクトのルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# .envファイルを読み込む
env_path = project_root / 'sourcing' / 'sources' / 'sellersprite' / '.env'
load_dotenv(dotenv_path=env_path)

from sourcing.sources.sellersprite.extractors.product_research_extractor import ProductResearchExtractor


async def main():
    """メイン処理"""
    parser = argparse.ArgumentParser(
        description="SellerSprite カテゴリ別ASIN抽出",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # 単一カテゴリで抽出
  python sourcing/scripts/extract_by_categories.py \\
    --categories "Health & Household > Healthcare" \\
    --sales-min 300 \\
    --price-min 2500 \\
    --limit 1000

  # 複数カテゴリで抽出
  python sourcing/scripts/extract_by_categories.py \\
    --categories "Health & Household > Healthcare" "Beauty & Personal Care > Skin Care" \\
    --sales-min 300 \\
    --price-min 2500 \\
    --limit 500
        """
    )

    # カテゴリパラメータ
    parser.add_argument(
        "--categories",
        nargs='+',
        required=True,
        help='カテゴリパスのリスト（例: "Health & Household > Healthcare"）'
    )

    # フィルターパラメータ
    parser.add_argument(
        "--sales-min",
        type=int,
        default=300,
        help="月間販売数の最小値（デフォルト: 300）"
    )
    parser.add_argument(
        "--sales-max",
        type=int,
        help="月間販売数の最大値（オプション）"
    )
    parser.add_argument(
        "--price-min",
        type=int,
        default=2500,
        help="価格の最小値（デフォルト: 2500）"
    )
    parser.add_argument(
        "--price-max",
        type=int,
        help="価格の最大値（オプション）"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="取得件数（デフォルト: 1000、最大: 2000）"
    )
    parser.add_argument(
        "--market",
        type=str,
        default="JP",
        help="市場（デフォルト: JP、他: US, UK, DE等）"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="出力ファイルパス（指定しない場合は標準出力）"
    )
    parser.add_argument(
        "--with-categories",
        action="store_true",
        default=False,
        help="カテゴリ情報も含めて出力（JSON形式）"
    )

    args = parser.parse_args()

    print()
    print("=" * 60)
    print("SellerSprite カテゴリ別ASIN抽出")
    print("=" * 60)
    print(f"対象カテゴリ: {len(args.categories)}件")
    for i, cat in enumerate(args.categories):
        print(f"  {i + 1}. {cat}")
    print(f"販売数範囲: {args.sales_min} 以上", end="")
    if args.sales_max:
        print(f" {args.sales_max} 以下")
    else:
        print()
    print(f"価格範囲: {args.price_min} 以上", end="")
    if args.price_max:
        print(f" {args.price_max} 以下")
    else:
        print()
    print(f"取得件数: {args.limit}件")
    print()

    try:
        # ProductResearchExtractor実行
        extractor = ProductResearchExtractor({
            "categories": args.categories,
            "sales_min": args.sales_min,
            "sales_max": args.sales_max,
            "price_min": args.price_min,
            "price_max": args.price_max,
            "amz": True,
            "fba": True,
            "limit": args.limit,
            "market": args.market,
            "extract_category_info": args.with_categories  # カテゴリ情報抽出フラグ
        })

        # ASIN抽出（カテゴリ情報付きかどうかは内部で判定）
        print("ASIN抽出中...")
        asins = await extractor.extract()

        # 結果出力
        print()
        print("=" * 60)
        print("抽出完了")
        print("=" * 60)
        print(f"最終抽出件数: {len(asins)}件")
        print()

        # ファイル出力
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            if args.with_categories:
                # カテゴリ情報付きの場合はJSON形式
                import json
                output_path.write_text(json.dumps(asins, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"出力ファイル: {output_path}")
                print(f"[OK] ファイル保存完了（JSON形式）")
            else:
                # ASINのみの場合はテキスト形式
                output_path.write_text("\n".join(asins), encoding="utf-8")
                print(f"出力ファイル: {output_path}")
                print(f"[OK] ファイル保存完了")
        else:
            if args.with_categories:
                import json
                print(json.dumps(asins, ensure_ascii=False, indent=2))
            else:
                print("抽出されたASIN:")
                if len(asins) <= 20:
                    for asin in asins:
                        print(f"  {asin}")
                else:
                    for asin in asins[:10]:
                        print(f"  {asin}")
                    print(f"  ... 省略 ({len(asins) - 20}件) ...")
                    for asin in asins[-10:]:
                        print(f"  {asin}")

        print()
        print("[SUCCESS] 処理が正常に完了しました")

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
