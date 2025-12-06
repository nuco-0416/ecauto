"""
BASE用アップローダー

既存のBASE API クライアントをラップして、
共通インターフェースに適合させる
"""

import sys
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

# パスを追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scheduler.platform_uploaders.uploader_interface import UploaderInterface
from common.pricing.calculator import PriceCalculator

# ロガー取得
logger = logging.getLogger(__name__)


class BaseUploader(UploaderInterface):
    """BASE専用アップローダー"""

    def __init__(self, account_id: str, account_manager=None):
        """
        Args:
            account_id: BASEアカウントID（例: 'base_account_1'）
            account_manager: AccountManagerインスタンス（オプション、指定しない場合は内部で作成）
        """
        # 循環インポートを回避するため、ここでインポート
        from platforms.base.core.api_client import BaseAPIClient
        from inventory.core.master_db import MasterDB
        from common.ng_keyword_filter import NGKeywordFilter

        self.account_id = account_id

        # account_managerが指定されていない場合のみ作成
        if account_manager is None:
            from platforms.base.accounts.manager import AccountManager
            self.account_manager = AccountManager()
        else:
            self.account_manager = account_manager

        self.client = BaseAPIClient(
            account_id=account_id,
            account_manager=self.account_manager
        )
        self.db = MasterDB()

        # NGキーワードフィルターを初期化
        project_root = Path(__file__).resolve().parent.parent.parent
        ng_keywords_file = project_root / 'config' / 'ng_keywords.json'
        self.ng_filter = NGKeywordFilter(str(ng_keywords_file))

        # 価格計算エンジンを初期化
        self.price_calculator = PriceCalculator()

    @property
    def platform_name(self) -> str:
        return 'base'

    def upload_item(self, item_data: Dict[str, Any]) -> Dict[str, Any]:
        """BASEにアイテムをアップロード"""
        try:
            asin = item_data.get('asin')
            if not asin:
                return {
                    'status': 'failed',
                    'platform_item_id': None,
                    'message': 'ASINが指定されていません'
                }

            # 商品情報を準備
            prepared_data = self._prepare_item_data(item_data)
            if not prepared_data:
                return {
                    'status': 'failed',
                    'platform_item_id': None,
                    'message': '商品情報の準備に失敗しました'
                }

            # BASE API でアイテムを作成
            result = self.client.create_item(prepared_data)
            item_id = result['item']['item_id']

            logger.info(f"商品登録成功: ASIN={asin}, Item ID={item_id}")

            return {
                'status': 'success',
                'platform_item_id': str(item_id),
                'message': 'アップロード成功'
            }

        except Exception as e:
            logger.error(f"アップロード失敗: {str(e)}")
            return {
                'status': 'failed',
                'platform_item_id': None,
                'message': str(e)
            }

    def check_duplicate(self, asin: str, sku: str) -> bool:
        """BASE重複チェック

        重複と判定するのは、実際にBASEに出品済みの商品のみ：
        - status='listed' （出品済み）
        - または platform_item_id IS NOT NULL（BASE登録済み）
        """
        try:
            # DBでチェック（listings テーブル）
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, status, platform_item_id
                    FROM listings
                    WHERE asin = ? AND platform = 'base' AND account_id = ?
                      AND (status = 'listed' OR platform_item_id IS NOT NULL)
                """, (asin, self.account_id))

                rows = cursor.fetchall()
                is_duplicate = len(rows) > 0

                # デバッグログ追加
                if is_duplicate:
                    for row in rows:
                        print(f"  [DEBUG] 重複検出: ASIN={asin}, listing_id={row['id']}, status={row['status']}, platform_item_id={row['platform_item_id']}")
                else:
                    print(f"  [DEBUG] 重複なし: ASIN={asin} (BASEに未出品)")

                return is_duplicate

        except Exception as e:
            # エラー時は重複なしとして扱う（安全側）
            print(f"  [DEBUG] 重複チェックエラー: ASIN={asin}, エラー={e}")
            return False

    def upload_images(
        self,
        platform_item_id: str,
        image_urls: List[str]
    ) -> Dict[str, Any]:
        """
        BASE画像アップロード

        商品登録後に画像URLを追加する

        Args:
            platform_item_id: BASE商品ID
            image_urls: 画像URLのリスト

        Returns:
            dict: アップロード結果
                - status: 'success' | 'failed'
                - uploaded_count: 成功件数
                - message: メッセージ
        """
        if not image_urls:
            return {
                'status': 'success',
                'uploaded_count': 0,
                'message': '画像URLが指定されていません'
            }

        try:
            # デバッグ: 画像アップロード情報を確認
            logger.debug(f"upload_images 開始: Item ID={platform_item_id}, 画像数={len(image_urls)}")
            logger.debug(f"画像URL: {image_urls[:3]}...")  # 最初の3件のみ表示

            # BASE API の add_images_bulk を使用
            result = self.client.add_images_bulk(platform_item_id, image_urls)

            # デバッグ: アップロード結果を確認
            logger.debug(f"add_images_bulk 結果: {result}")

            return {
                'status': 'success' if result['success_count'] > 0 else 'failed',
                'uploaded_count': result['success_count'],
                'message': f"{result['success_count']}/{result['total']}件の画像をアップロード"
            }

        except Exception as e:
            logger.error(f"upload_images エラー: {e}", exc_info=True)
            return {
                'status': 'failed',
                'uploaded_count': 0,
                'message': f'画像アップロードエラー: {str(e)}'
            }

    def validate_item(self, item_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """BASEアイテム検証"""
        # 必須フィールドチェック
        asin = item_data.get('asin')
        if not asin:
            return False, "ASINが指定されていません"

        # 商品情報を取得
        product = self.db.get_product(asin)
        if not product:
            return False, f"商品情報が見つかりません: {asin}"

        # タイトルチェック
        title = product.get('title_ja') or product.get('title_en')
        if not title:
            return False, "タイトルが取得できません"

        # 価格チェック
        price = item_data.get('price')
        if not price:
            # selling_priceがない場合はamazon_price_jpyから計算
            amazon_price = product.get('amazon_price_jpy')
            if not amazon_price or amazon_price <= 0:
                return False, "価格情報が不正です"

        return True, None

    def get_business_hours(self) -> tuple[int, int]:
        """BASE営業時間: 6AM-11PM"""
        return (6, 23)

    def get_rate_limit(self) -> float:
        """BASE API制限: 2秒"""
        return 2.0

    def _prepare_item_data(self, item_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        BASE API用のアイテムデータを準備

        Args:
            item_data: 入力アイテムデータ

        Returns:
            dict or None: BASE API用データ
        """
        asin = item_data.get('asin')

        # 商品情報を取得
        product = self.db.get_product(asin)
        if not product:
            logger.error(f"商品情報が見つかりません: {asin}")
            return None

        # 出品情報を取得（SKUを取得するため）
        listing = None
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM listings
                WHERE asin = ? AND platform = 'base' AND account_id = ?
                LIMIT 1
            """, (asin, self.account_id))
            row = cursor.fetchone()
            if row:
                listing = dict(row)

        # NGキーワードフィルターを適用
        title = product.get('title_ja') or product.get('title_en') or f'商品 {asin}'
        # description_jaがない場合はtitle_jaをフォールバックとして使用
        description = product.get('description_ja') or product.get('description_en') or title

        if self.ng_filter and self.ng_filter.ng_keywords:
            title = self.ng_filter.filter_title(title)
            description = self.ng_filter.filter_description(description)

        # 価格を取得
        price = item_data.get('price')
        if not price:
            amazon_price = product.get('amazon_price_jpy')
            if amazon_price:
                # 新しい価格計算モジュールを使用
                price = self.price_calculator.calculate_selling_price(amazon_price=amazon_price)
            else:
                logger.error("価格情報が取得できていません")
                return None

        # BASE API用データを構築
        prepared = {
            'title': title,
            'detail': description,
            'price': int(price),
            'stock': int(item_data.get('stock') or 1),
            'visible': 1  # 公開状態
        }

        # SKU（商品コード）を追加
        if listing and listing.get('sku'):
            prepared['identifier'] = listing['sku']
            logger.debug(f"商品コード設定: {listing['sku']}")

        return prepared
