"""
SellerSprite ASIN抽出スクリプト（優先度1：手動パラメータ）

使用例:
    # ランキング抽出
    python sourcing/scripts/extract_asins.py \
      --pattern ranking \
      --category "おもちゃ・ホビー" \
      --min-rank 1 \
      --max-rank 1000

    # 出力ファイル指定
    python sourcing/scripts/extract_asins.py \
      --pattern ranking \
      --category "おもちゃ・ホビー" \
      --min-rank 1 \
      --max-rank 1000 \
      --output data/asins_20250123.txt
"""

import argparse
import asyncio
import sys
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# ecautoプロジェクトのルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# .envファイルを読み込む
env_path = project_root / 'sourcing' / 'sources' / 'sellersprite' / '.env'
load_dotenv(dotenv_path=env_path)

from sourcing.sources.sellersprite.extractors.ranking_extractor import RankingExtractor
from sourcing.sources.sellersprite.extractors.product_research_extractor import ProductResearchExtractor


async def main():
    """メイン処理"""
    parser = argparse.ArgumentParser(
        description="SellerSprite ASIN抽出",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # ランキング抽出（基本）
  python sourcing/scripts/extract_asins.py \\
    --pattern ranking \\
    --category "おもちゃ・ホビー" \\
    --min-rank 1 \\
    --max-rank 1000

  # 商品リサーチ抽出（推奨）
  python sourcing/scripts/extract_asins.py \\
    --pattern product_research \\
    --sales-min 300 \\
    --price-min 2500 \\
    --limit 100

  # 出力ファイル指定
  python sourcing/scripts/extract_asins.py \\
    --pattern product_research \\
    --sales-min 300 \\
    --price-min 2500 \\
    --output data/asins_20250123.txt
        """
    )

    # 共通パラメータ
    parser.add_argument(
        "--pattern",
        required=True,
        choices=["ranking", "category", "seasonal", "product_research"],
        help="抽出パターン"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="出力ファイルパス（指定しない場合は標準出力）"
    )

    # ランキング抽出パラメータ
    parser.add_argument(
        "--category",
        type=str,
        help="カテゴリ名（例: おもちゃ・ホビー）"
    )
    parser.add_argument(
        "--min-rank",
        type=int,
        default=1,
        help="最小ランキング（デフォルト: 1）"
    )
    parser.add_argument(
        "--max-rank",
        type=int,
        default=100,
        help="最大ランキング（デフォルト: 100）"
    )
    parser.add_argument(
        "--marketplace",
        type=str,
        default="amazon.co.jp",
        help="マーケットプレイス（デフォルト: amazon.co.jp）"
    )

    # 商品リサーチパラメータ
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
        "--amz",
        action="store_true",
        default=True,
        help="Amazon販売のみ（デフォルト: True）"
    )
    parser.add_argument(
        "--fba",
        action="store_true",
        default=True,
        help="FBAのみ（デフォルト: True）"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="取得件数（デフォルト: 100, 最大: 100）"
    )
    parser.add_argument(
        "--market",
        type=str,
        default="JP",
        help="市場（デフォルト: JP、他: US, UK, DE等）"
    )
    parser.add_argument(
        "--keep-browser",
        action="store_true",
        default=False,
        help="ブラウザウィンドウを閉じずに開いたままにする（デバッグ用）"
    )

    args = parser.parse_args()

    # パラメータ準備
    parameters = {
        "category": args.category,
        "min_rank": args.min_rank,
        "max_rank": args.max_rank,
        "marketplace": args.marketplace,
        "keep_browser_open": args.keep_browser,
    }

    # 抽出器の選択
    print("=" * 60)
    print("SellerSprite ASIN抽出")
    print("=" * 60)
    print()

    extractor = None

    if args.pattern == "ranking":
        if not args.category:
            print("[ERROR] --category パラメータは必須です")
            sys.exit(1)

        print(f"抽出パターン: セールスランキング")
        print(f"カテゴリ: {args.category}")
        print(f"ランキング範囲: {args.min_rank} - {args.max_rank}")
        print()

        extractor = RankingExtractor(parameters)

    elif args.pattern == "category":
        print("[ERROR] category パターンは未実装です（Phase 1 Day 3-4で実装予定）")
        sys.exit(1)

    elif args.pattern == "seasonal":
        print("[ERROR] seasonal パターンは未実装です（Phase 1 Day 3-4で実装予定）")
        sys.exit(1)

    elif args.pattern == "product_research":
        print(f"抽出パターン: 商品リサーチ")
        print(f"市場: {args.market}")
        print(f"月間販売数 最小値: {args.sales_min}")
        print(f"価格 最小値: {args.price_min}")
        print(f"AMZ: {args.amz}")
        print(f"FBA: {args.fba}")
        print(f"取得件数: {args.limit}")
        print()

        extractor = ProductResearchExtractor({
            "sales_min": args.sales_min,
            "price_min": args.price_min,
            "amz": args.amz,
            "fba": args.fba,
            "limit": args.limit,
            "market": args.market,
            "keep_browser_open": args.keep_browser
        })

    # 抽出実行
    try:
        asins = await extractor.extract()

        print()
        print("=" * 60)
        print("抽出完了")
        print("=" * 60)
        print(f"抽出件数: {len(asins)}件")
        print()

        # 出力処理
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text("\n".join(asins), encoding="utf-8")
            print(f"出力ファイル: {output_path}")
            print(f"[OK] ファイル保存完了")
        else:
            print("抽出されたASIN:")
            if len(asins) <= 20:
                for asin in asins:
                    print(f"  {asin}")
            else:
                for asin in asins[:10]:
                    print(f"  {asin}")
                print(f"  ...")
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
