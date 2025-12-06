"""
SellerSprite 大量ASIN抽出スクリプト（セグメント分割方式）

2000件制限を回避して、3000件/日の目標を達成するためのスクリプト。
価格帯や販売数範囲を複数のセグメントに分割して抽出し、重複を除去する。

使用例:
    # 3つの価格帯で各1000件、合計3000件を取得
    python sourcing/scripts/extract_asins_bulk.py \
      --strategy segment \
      --segments "2500-5000,5000-10000,10000-20000" \
      --sales-min 300 \
      --count-per-segment 1000

    # 販売数で分割
    python sourcing/scripts/extract_asins_bulk.py \
      --strategy segment \
      --segment-type sales \
      --segments "300-500,500-1000,1000-5000" \
      --price-min 2500 \
      --count-per-segment 1000
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Tuple
from dotenv import load_dotenv

# ecautoプロジェクトのルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# .envファイルを読み込む
env_path = project_root / 'sourcing' / 'sources' / 'sellersprite' / '.env'
load_dotenv(dotenv_path=env_path)

from sourcing.sources.sellersprite.extractors.product_research_extractor import ProductResearchExtractor


class BulkExtractor:
    """
    セグメント分割による大量ASIN抽出クラス
    """

    def __init__(
        self,
        segments: List[Tuple[int, int]],
        segment_type: str,
        sales_min: int,
        sales_max: int,
        price_min: int,
        price_max: int,
        count_per_segment: int,
        market: str = "JP",
        keep_browser: bool = False
    ):
        """
        Args:
            segments: セグメントのリスト [(min1, max1), (min2, max2), ...]
            segment_type: セグメントの種類（"price" or "sales"）
            sales_min: 販売数の最小値（segment_type="price"の場合）
            sales_max: 販売数の最大値（segment_type="price"の場合、オプション）
            price_min: 価格の最小値（segment_type="sales"の場合）
            price_max: 価格の最大値（segment_type="sales"の場合、オプション）
            count_per_segment: 各セグメントでの取得件数
            market: 市場（デフォルト: JP）
            keep_browser: ブラウザを開いたままにするか
        """
        self.segments = segments
        self.segment_type = segment_type
        self.sales_min = sales_min
        self.sales_max = sales_max
        self.price_min = price_min
        self.price_max = price_max
        self.count_per_segment = count_per_segment
        self.market = market
        self.keep_browser = keep_browser

    async def extract(self) -> List[str]:
        """
        全セグメントからASINを抽出
        1回のログインで全セグメントを処理し、ログインループを回避

        Returns:
            重複除去済みASINリスト
        """
        all_asins = []
        total_segments = len(self.segments)

        print()
        print("=" * 60)
        print("セグメント分割抽出 開始")
        print("=" * 60)
        print(f"総セグメント数: {total_segments}")
        print(f"各セグメント取得件数: {self.count_per_segment}件")
        print(f"目標合計件数: {total_segments * self.count_per_segment}件")
        print()

        # 環境変数から認証情報を取得
        email = os.getenv('SELLERSPRITE_EMAIL')
        password = os.getenv('SELLERSPRITE_PASSWORD')

        if not email or not password:
            raise Exception("環境変数 SELLERSPRITE_EMAIL と SELLERSPRITE_PASSWORD が設定されていません")

        # Playwrightを使用してブラウザを起動（1回のみ）
        from playwright.async_api import async_playwright
        import re

        async with async_playwright() as p:
            # ブラウザを起動
            print("ブラウザを起動中...")
            browser = await p.chromium.launch(
                headless=False,
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

            try:
                # SellerSpriteにログイン（1回のみ）
                print("SellerSpriteにログイン中...")
                await page.goto("https://www.sellersprite.com/jp/w/user/login",
                               wait_until="networkidle",
                               timeout=30000)

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
                    print("[OK] ログイン成功")
                except Exception as e:
                    current_url = page.url
                    if 'login' not in current_url:
                        print("[OK] ログイン成功（URL遷移確認）")
                    else:
                        raise Exception(f"ログインに失敗しました: {e}")

                print()
                print("=" * 60)
                print("各セグメントの処理を開始")
                print("=" * 60)

                # 各セグメントを処理（同じブラウザセッションを使用）
                for i, (seg_min, seg_max) in enumerate(self.segments):
                    segment_num = i + 1
                    print()
                    print("-" * 60)
                    print(f"[セグメント {segment_num}/{total_segments}]")

                    # パラメータを構築
                    if self.segment_type == "price":
                        # 価格セグメント
                        params = {
                            "sales_min": self.sales_min,
                            "sales_max": self.sales_max,
                            "price_min": seg_min,
                            "price_max": seg_max,
                            "amz": True,
                            "fba": True,
                            "limit": self.count_per_segment,
                            "market": self.market,
                            "keep_browser_open": self.keep_browser
                        }
                        print(f"  価格範囲: {seg_min} - {seg_max}")
                        print(f"  販売数範囲: {self.sales_min} 以上", end="")
                        if self.sales_max:
                            print(f" {self.sales_max} 以下")
                        else:
                            print()

                    else:
                        # 販売数セグメント
                        params = {
                            "sales_min": seg_min,
                            "sales_max": seg_max,
                            "price_min": self.price_min,
                            "price_max": self.price_max,
                            "amz": True,
                            "fba": True,
                            "limit": self.count_per_segment,
                            "market": self.market,
                            "keep_browser_open": self.keep_browser
                        }
                        print(f"  販売数範囲: {seg_min} - {seg_max}")
                        print(f"  価格範囲: {self.price_min} 以上", end="")
                        if self.price_max:
                            print(f" {self.price_max} 以下")
                        else:
                            print()

                    print(f"  取得目標: {self.count_per_segment}件")
                    print()

                    try:
                        # ProductResearchExtractorを作成し、既存のpageで実行
                        extractor = ProductResearchExtractor(params)
                        asins = await extractor.extract_with_page(page)

                        print()
                        print(f"  [OK] {len(asins)}件のASINを抽出")
                        all_asins.extend(asins)

                    except Exception as e:
                        print()
                        print(f"  [ERROR] エラーが発生しました: {e}")
                        print(f"  このセグメントをスキップして続行します")
                        import traceback
                        traceback.print_exc()

            finally:
                # ブラウザを閉じる（keep_browser_openフラグを考慮）
                if not self.keep_browser:
                    await context.close()
                    await browser.close()
                    print()
                    print("ブラウザを閉じました")

        # 重複除去
        print()
        print("=" * 60)
        print("重複除去処理")
        print("=" * 60)
        print(f"抽出総数: {len(all_asins)}件")

        unique_asins = list(dict.fromkeys(all_asins))  # 順序を保持しつつ重複除去
        duplicates = len(all_asins) - len(unique_asins)

        print(f"重複除去: {duplicates}件")
        print(f"ユニーク: {len(unique_asins)}件")
        print()

        return unique_asins


def parse_segments(segments_str: str) -> List[Tuple[int, int]]:
    """
    セグメント文字列を解析

    Args:
        segments_str: "2500-5000,5000-10000,10000-20000" 形式の文字列

    Returns:
        [(2500, 5000), (5000, 10000), (10000, 20000)]
    """
    segments = []
    for seg in segments_str.split(","):
        seg = seg.strip()
        if "-" in seg:
            min_val, max_val = seg.split("-")
            segments.append((int(min_val), int(max_val)))
        else:
            raise ValueError(f"不正なセグメント形式: {seg}")

    return segments


async def main():
    """メイン処理"""
    parser = argparse.ArgumentParser(
        description="SellerSprite 大量ASIN抽出（セグメント分割方式）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # 3つの価格帯で各1000件、合計3000件を取得
  python sourcing/scripts/extract_asins_bulk.py \\
    --strategy segment \\
    --segments "2500-5000,5000-10000,10000-20000" \\
    --sales-min 300 \\
    --count-per-segment 1000

  # 販売数で分割
  python sourcing/scripts/extract_asins_bulk.py \\
    --strategy segment \\
    --segment-type sales \\
    --segments "300-500,500-1000,1000-5000" \\
    --price-min 2500 \\
    --count-per-segment 1000
        """
    )

    # 共通パラメータ
    parser.add_argument(
        "--strategy",
        required=True,
        choices=["segment"],
        help="抽出戦略（現在はsegmentのみ）"
    )
    parser.add_argument(
        "--segments",
        required=True,
        type=str,
        help="セグメント定義（例: 2500-5000,5000-10000,10000-20000）"
    )
    parser.add_argument(
        "--segment-type",
        type=str,
        default="price",
        choices=["price", "sales"],
        help="セグメントの種類（price: 価格で分割、sales: 販売数で分割）"
    )
    parser.add_argument(
        "--count-per-segment",
        type=int,
        default=1000,
        help="各セグメントでの取得件数（デフォルト: 1000）"
    )

    # 価格セグメント用パラメータ
    parser.add_argument(
        "--sales-min",
        type=int,
        default=300,
        help="月間販売数の最小値（segment-type=priceの場合、デフォルト: 300）"
    )
    parser.add_argument(
        "--sales-max",
        type=int,
        help="月間販売数の最大値（オプション）"
    )

    # 販売数セグメント用パラメータ
    parser.add_argument(
        "--price-min",
        type=int,
        default=2500,
        help="価格の最小値（segment-type=salesの場合、デフォルト: 2500）"
    )
    parser.add_argument(
        "--price-max",
        type=int,
        help="価格の最大値（オプション）"
    )

    # その他のパラメータ
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
        "--keep-browser",
        action="store_true",
        default=False,
        help="ブラウザウィンドウを閉じずに開いたままにする（デバッグ用）"
    )

    args = parser.parse_args()

    # セグメント解析
    try:
        segments = parse_segments(args.segments)
    except ValueError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    # BulkExtractor実行
    try:
        extractor = BulkExtractor(
            segments=segments,
            segment_type=args.segment_type,
            sales_min=args.sales_min,
            sales_max=args.sales_max,
            price_min=args.price_min,
            price_max=args.price_max,
            count_per_segment=args.count_per_segment,
            market=args.market,
            keep_browser=args.keep_browser
        )

        unique_asins = await extractor.extract()

        # 結果出力
        print()
        print("=" * 60)
        print("抽出完了")
        print("=" * 60)
        print(f"最終抽出件数: {len(unique_asins)}件")
        print()

        # ファイル出力
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text("\n".join(unique_asins), encoding="utf-8")
            print(f"出力ファイル: {output_path}")
            print(f"[OK] ファイル保存完了")
        else:
            print("抽出されたASIN:")
            if len(unique_asins) <= 20:
                for asin in unique_asins:
                    print(f"  {asin}")
            else:
                for asin in unique_asins[:10]:
                    print(f"  {asin}")
                print(f"  ... 省略 ({len(unique_asins) - 20}件) ...")
                for asin in unique_asins[-10:]:
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
