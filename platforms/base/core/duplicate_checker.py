"""
BASE本番環境との重複チェックモジュール

アップロード前にBASE API経由で既存商品をチェックし、重複を防止
"""

import sys
from pathlib import Path
from typing import List, Dict, Optional, Set
import time

# パスを追加
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))


class BaseDuplicateChecker:
    """
    BASE本番環境との重複チェッククラス

    機能:
    - BASE APIから既存商品一覧を取得
    - ASIN/SKUの重複をチェック
    - ローカルキャッシュで効率化
    """

    def __init__(self, account_id: str, cache_ttl_seconds: int = 300):
        """
        Args:
            account_id: アカウントID
            cache_ttl_seconds: キャッシュの有効期限（秒、デフォルト: 300秒=5分）
        """
        # 遅延インポート（循環インポート回避）
        from platforms.base.core.api_client import BaseAPIClient
        from platforms.base.accounts.manager import AccountManager

        self.account_id = account_id
        self.cache_ttl_seconds = cache_ttl_seconds

        # アカウント情報を取得
        account_manager = AccountManager()
        account = account_manager.get_account(account_id)

        if not account:
            raise ValueError(f"アカウントが見つかりません: {account_id}")

        self.client = BaseAPIClient(account['credentials'])

        # キャッシュ
        self._cache = {
            'items': [],
            'asins': set(),
            'skus': set(),
            'timestamp': 0
        }

    def _fetch_all_items(self) -> List[Dict]:
        """
        BASE APIから全商品を取得

        Returns:
            list: 商品情報のリスト
        """
        all_items = []
        limit = 100  # 1回のAPI呼び出しで取得する件数
        offset = 0

        print(f"[重複チェック] BASE本番環境から既存商品を取得中...")

        while True:
            try:
                response = self.client.list_items(limit=limit, offset=offset)

                items = response.get('items', [])
                if not items:
                    break

                all_items.extend(items)
                offset += limit

                print(f"  取得済み: {len(all_items)}件")

                # レート制限対策
                time.sleep(0.5)

            except Exception as e:
                print(f"  [WARNING] API呼び出しエラー: {e}")
                break

        print(f"[重複チェック] 合計 {len(all_items)}件の商品を取得しました")

        return all_items

    def _update_cache(self):
        """キャッシュを更新"""
        items = self._fetch_all_items()

        # ASINとSKUを抽出
        asins = set()
        skus = set()

        for item in items:
            # ASINを抽出（descriptionやdetailから）
            # BASE APIではASINが直接含まれていない場合があるため、
            # SKUやdescriptionから抽出する必要がある
            sku = item.get('identifier', item.get('code', ''))

            if sku:
                skus.add(sku)

                # SKUからASINを抽出（新形式: b-ASIN-timestamp）
                if '-' in sku:
                    parts = sku.split('-')
                    if len(parts) >= 2:
                        potential_asin = parts[1]
                        # ASINは通常B0で始まる10文字
                        if potential_asin.startswith('B') and len(potential_asin) == 10:
                            asins.add(potential_asin)

                # 旧形式からもASIN抽出を試みる（BASE-ASIN, base_account_ASIN など）
                if sku.startswith('BASE-') and len(sku) > 5:
                    potential_asin = sku[5:]
                    if potential_asin.startswith('B') and len(potential_asin) == 10:
                        asins.add(potential_asin)

                # base_*_ASIN形式
                if '_' in sku:
                    potential_asin = sku.split('_')[-1]
                    if potential_asin.startswith('B') and len(potential_asin) == 10:
                        asins.add(potential_asin)

        # キャッシュを更新
        self._cache = {
            'items': items,
            'asins': asins,
            'skus': skus,
            'timestamp': time.time()
        }

        print(f"[重複チェック] キャッシュ更新完了: {len(asins)}個のASIN, {len(skus)}個のSKU")

    def _is_cache_valid(self) -> bool:
        """キャッシュが有効か確認"""
        if not self._cache['items']:
            return False

        elapsed = time.time() - self._cache['timestamp']
        return elapsed < self.cache_ttl_seconds

    def _get_cache(self):
        """キャッシュを取得（必要に応じて更新）"""
        if not self._is_cache_valid():
            self._update_cache()

        return self._cache

    def check_asin(self, asin: str) -> Dict:
        """
        ASINの重複をチェック

        Args:
            asin: チェックするASIN

        Returns:
            dict: {
                'duplicate': bool,  # 重複しているか
                'message': str      # メッセージ
            }
        """
        cache = self._get_cache()

        if asin in cache['asins']:
            return {
                'duplicate': True,
                'message': f'ASIN {asin} は既にBASEに登録されています'
            }

        return {
            'duplicate': False,
            'message': f'ASIN {asin} は重複していません'
        }

    def check_sku(self, sku: str) -> Dict:
        """
        SKUの重複をチェック

        Args:
            sku: チェックするSKU

        Returns:
            dict: {
                'duplicate': bool,  # 重複しているか
                'message': str      # メッセージ
            }
        """
        cache = self._get_cache()

        if sku in cache['skus']:
            return {
                'duplicate': True,
                'message': f'SKU {sku} は既にBASEに登録されています'
            }

        return {
            'duplicate': False,
            'message': f'SKU {sku} は重複していません'
        }

    def check_batch(self, items: List[Dict]) -> Dict:
        """
        複数アイテムをまとめてチェック

        Args:
            items: チェックするアイテムのリスト
                   各アイテムは {'asin': str, 'sku': str} の形式

        Returns:
            dict: {
                'total': int,
                'duplicates': int,
                'safe': int,
                'duplicate_items': list  # 重複しているアイテムのリスト
            }
        """
        cache = self._get_cache()

        duplicate_items = []
        safe_items = []

        for item in items:
            asin = item.get('asin')
            sku = item.get('sku')

            is_duplicate = False
            reason = []

            if asin and asin in cache['asins']:
                is_duplicate = True
                reason.append(f'ASIN重複')

            if sku and sku in cache['skus']:
                is_duplicate = True
                reason.append(f'SKU重複')

            if is_duplicate:
                duplicate_items.append({
                    **item,
                    'reason': ', '.join(reason)
                })
            else:
                safe_items.append(item)

        return {
            'total': len(items),
            'duplicates': len(duplicate_items),
            'safe': len(safe_items),
            'duplicate_items': duplicate_items,
            'safe_items': safe_items
        }

    def refresh_cache(self):
        """キャッシュを強制的に更新"""
        self._update_cache()


# 使用例
if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description='BASE重複チェックテスト'
    )
    parser.add_argument(
        '--account-id',
        type=str,
        default='base_account_2',
        help='アカウントID'
    )
    parser.add_argument(
        '--asin',
        type=str,
        help='チェックするASIN'
    )

    args = parser.parse_args()

    checker = BaseDuplicateChecker(args.account_id)

    if args.asin:
        result = checker.check_asin(args.asin)
        print(f"\nASIN {args.asin} のチェック結果:")
        print(f"  重複: {result['duplicate']}")
        print(f"  メッセージ: {result['message']}")
    else:
        # テストデータでバッチチェック
        test_items = [
            {'asin': 'B0FFN1RB6J', 'sku': 'b-B0FFN1RB6J-20251120230102'},
            {'asin': 'B01N9B03QR', 'sku': 'b-B01N9B03QR-20251120230102'},
        ]

        result = checker.check_batch(test_items)
        print(f"\nバッチチェック結果:")
        print(f"  合計: {result['total']}件")
        print(f"  重複: {result['duplicates']}件")
        print(f"  安全: {result['safe']}件")

        if result['duplicate_items']:
            print(f"\n重複アイテム:")
            for item in result['duplicate_items']:
                print(f"    ASIN: {item['asin']}, 理由: {item['reason']}")
