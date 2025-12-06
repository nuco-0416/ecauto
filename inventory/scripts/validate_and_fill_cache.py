"""
キャッシュ検証・差分補完スクリプト

更新対象ASINのキャッシュを検証し、欠損データのみSP-APIで補完する
本番環境（数万件規模）を想定した効率的な実装
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
import time
from typing import List, Dict, Any, Set

# パスを追加
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from inventory.core.master_db import MasterDB
from inventory.core.cache_manager import AmazonProductCache
from integrations.amazon.config import SP_API_CREDENTIALS
from integrations.amazon.sp_api_client import AmazonSPAPIClient


class CacheValidator:
    """
    キャッシュ検証・補完クラス
    """

    # TTL設定（秒）
    TTL_BASIC_INFO = 7 * 24 * 3600      # 基本情報: 7日
    TTL_PRICE = 24 * 3600                # 価格: 24時間
    TTL_STOCK = 3600                     # 在庫: 1時間

    def __init__(self, dry_run: bool = False):
        """
        初期化

        Args:
            dry_run: Trueの場合、SP-API呼び出しを行わない
        """
        self.master_db = MasterDB()
        self.cache = AmazonProductCache()
        self.dry_run = dry_run

        # SP-APIクライアント
        if all(SP_API_CREDENTIALS.values()):
            self.sp_api_client = AmazonSPAPIClient(SP_API_CREDENTIALS)
            self.sp_api_available = True
        else:
            print("[WARN] SP-API認証情報が不足しています")
            self.sp_api_client = None
            self.sp_api_available = False

        # 統計情報
        self.stats = {
            'total_asins': 0,
            'cache_ok': 0,
            'cache_missing': 0,
            'price_expired': 0,
            'stock_expired': 0,
            'need_update': 0,
            'sp_api_success': 0,
            'sp_api_failed': 0,
            'errors': []
        }

    def is_expired(self, timestamp_str: str, ttl_seconds: int) -> bool:
        """
        タイムスタンプが期限切れかチェック

        Args:
            timestamp_str: ISO形式のタイムスタンプ
            ttl_seconds: 有効期限（秒）

        Returns:
            bool: 期限切れの場合True
        """
        if not timestamp_str:
            return True

        try:
            timestamp = datetime.fromisoformat(timestamp_str)
            age = (datetime.now() - timestamp).total_seconds()
            return age > ttl_seconds
        except:
            return True

    def validate_cache(self, asin: str) -> Dict[str, Any]:
        """
        1つのASINのキャッシュを検証

        Args:
            asin: 商品ASIN

        Returns:
            dict: 検証結果
                - needs_update: bool
                - missing_data: list (欠損しているデータ種別)
        """
        result = {
            'asin': asin,
            'needs_update': False,
            'missing_data': [],
            'reason': []
        }

        # キャッシュを取得
        cache_data = self.cache.get_product(asin)

        if not cache_data:
            result['needs_update'] = True
            result['missing_data'].append('all')
            result['reason'].append('キャッシュなし')
            return result

        # 価格情報のチェック
        if not cache_data.get('price_jpy'):
            result['needs_update'] = True
            result['missing_data'].append('price')
            result['reason'].append('価格情報なし')
        elif self.is_expired(cache_data.get('price_updated_at', ''), self.TTL_PRICE):
            result['needs_update'] = True
            result['missing_data'].append('price')
            result['reason'].append('価格期限切れ')

        # 在庫情報のチェック
        if cache_data.get('in_stock') is None:
            result['needs_update'] = True
            result['missing_data'].append('stock')
            result['reason'].append('在庫情報なし')
        elif self.is_expired(cache_data.get('stock_updated_at', ''), self.TTL_STOCK):
            result['needs_update'] = True
            result['missing_data'].append('stock')
            result['reason'].append('在庫期限切れ')

        return result

    def validate_all(self, platform: str = 'base') -> List[str]:
        """
        全ASINのキャッシュを検証

        Args:
            platform: プラットフォーム名

        Returns:
            list: 更新が必要なASINリスト
        """
        print("\n" + "=" * 70)
        print("キャッシュ検証を開始")
        print("=" * 70)
        print(f"プラットフォーム: {platform}")
        print(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()

        # 更新対象ASINを取得（出品済みのもののみ）
        listings = self.master_db.get_listings_by_account(
            platform=platform,
            account_id=None,  # 全アカウント
            status='listed'
        )

        # プラットフォーム指定がない場合は全出品を取得
        if not listings:
            with self.master_db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT DISTINCT asin FROM listings
                    WHERE platform = ? AND status = 'listed'
                ''', (platform,))
                listings = [{'asin': row[0]} for row in cursor.fetchall()]

        asins = list(set([l['asin'] for l in listings]))
        self.stats['total_asins'] = len(asins)

        print(f"対象ASIN数: {len(asins)}件")
        print()

        need_update_asins = []
        missing_asins = []
        price_expired_asins = []
        stock_expired_asins = []

        # 各ASINを検証
        for i, asin in enumerate(asins, 1):
            result = self.validate_cache(asin)

            if result['needs_update']:
                need_update_asins.append(asin)

                if 'all' in result['missing_data']:
                    missing_asins.append(asin)
                if 'price' in result['missing_data']:
                    price_expired_asins.append(asin)
                if 'stock' in result['missing_data']:
                    stock_expired_asins.append(asin)

            # 進捗表示（100件ごと）
            if i % 100 == 0:
                print(f"[{i}/{len(asins)}] 検証中... ({i/len(asins)*100:.1f}%)")

        # 統計を更新
        self.stats['cache_ok'] = len(asins) - len(need_update_asins)
        self.stats['cache_missing'] = len(missing_asins)
        self.stats['price_expired'] = len(price_expired_asins)
        self.stats['stock_expired'] = len(stock_expired_asins)
        self.stats['need_update'] = len(need_update_asins)

        # 結果表示
        print()
        print("=" * 70)
        print("検証結果サマリー")
        print("=" * 70)
        print(f"全ASIN数: {self.stats['total_asins']}件")
        print(f"  - キャッシュOK: {self.stats['cache_ok']}件")
        print(f"  - キャッシュなし: {self.stats['cache_missing']}件")
        print(f"  - 価格期限切れ: {self.stats['price_expired']}件")
        print(f"  - 在庫期限切れ: {self.stats['stock_expired']}件")
        print()
        print(f"更新が必要: {self.stats['need_update']}件")
        print("=" * 70)
        print()

        return need_update_asins

    def fill_missing_cache(self, asins: List[str]) -> Dict[str, Any]:
        """
        欠損キャッシュをSP-APIで補完

        Args:
            asins: 更新が必要なASINリスト

        Returns:
            dict: 補完結果
        """
        if not asins:
            print("更新が必要なASINはありません。")
            return self.stats

        if not self.sp_api_available:
            print("[ERROR] SP-APIクライアントが利用できません")
            print("キャッシュの補完をスキップします")
            return self.stats

        if self.dry_run:
            print(f"[DRY RUN] {len(asins)}件のASINをSP-APIで取得する予定です")
            return self.stats

        print()
        print("=" * 70)
        print("キャッシュ補完を開始")
        print("=" * 70)
        print(f"対象ASIN数: {len(asins)}件")
        print(f"推定所要時間: {len(asins) * 2.1 / 60:.1f}分")
        print()

        for i, asin in enumerate(asins, 1):
            try:
                # SP-APIで商品情報を取得
                product_data = self.sp_api_client.get_product_price(asin)

                if product_data:
                    # キャッシュに保存
                    now = datetime.now().isoformat()
                    product_data['price_updated_at'] = now
                    product_data['stock_updated_at'] = now

                    self.cache.set_product(asin, product_data)

                    # Master DBも更新
                    self.master_db.update_amazon_info(
                        asin=asin,
                        price_jpy=product_data.get('price_jpy', 0),
                        in_stock=product_data.get('in_stock', False)
                    )

                    self.stats['sp_api_success'] += 1

                    # 進捗表示（10件ごと）
                    if i % 10 == 0:
                        print(f"[{i}/{len(asins)}] {asin} - 成功 ({i/len(asins)*100:.1f}%)")

                else:
                    print(f"[{i}/{len(asins)}] {asin} - データなし")
                    self.stats['sp_api_failed'] += 1

            except Exception as e:
                error_msg = f"{asin}: {str(e)}"
                print(f"[{i}/{len(asins)}] {asin} - エラー: {e}")
                self.stats['sp_api_failed'] += 1
                self.stats['errors'].append(error_msg)

            # レート制限（2.1秒待機）
            if i < len(asins):
                time.sleep(2.1)

        print()
        print("=" * 70)
        print("補完結果サマリー")
        print("=" * 70)
        print(f"SP-API呼び出し: {len(asins)}件")
        print(f"  - 成功: {self.stats['sp_api_success']}件")
        print(f"  - 失敗: {self.stats['sp_api_failed']}件")

        if self.stats['errors']:
            print()
            print("エラー詳細（最大10件）:")
            for error in self.stats['errors'][:10]:
                print(f"  - {error}")

        print("=" * 70)
        print()

        return self.stats

    def run(self, platform: str = 'base') -> Dict[str, Any]:
        """
        検証・補完を実行

        Args:
            platform: プラットフォーム名

        Returns:
            dict: 実行結果
        """
        # Step 1: キャッシュ検証
        need_update_asins = self.validate_all(platform)

        # Step 2: 差分補完
        if need_update_asins:
            self.fill_missing_cache(need_update_asins)
        else:
            print("全てのキャッシュが最新です。補完は不要です。")

        print(f"終了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()

        return self.stats


def main():
    """メイン処理"""
    import argparse

    parser = argparse.ArgumentParser(
        description='キャッシュ検証・差分補完スクリプト'
    )
    parser.add_argument(
        '--platform',
        default='base',
        help='プラットフォーム名（デフォルト: base）'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='DRY RUNモード（SP-API呼び出しなし）'
    )

    args = parser.parse_args()

    # 検証・補完実行
    validator = CacheValidator(dry_run=args.dry_run)
    stats = validator.run(platform=args.platform)

    # 終了コード
    if stats['sp_api_failed'] > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
