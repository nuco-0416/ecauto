# -*- coding: utf-8 -*-
"""
eBay Inventory API統合クライアント

レガシーシステムのlisting.pyとinventory.pyを統合・改良
"""

import requests
import json
import logging
from typing import Dict, Optional, List, Any
from pathlib import Path
import sys

# ロガー設定
logger = logging.getLogger(__name__)

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(project_root))

from platforms.ebay.core.auth import EbayTokenManager


class EbayAPIClient:
    """
    eBay Inventory API統合クライアント

    機能:
    - Inventory Item操作（作成/更新/取得/削除）
    - Offer操作（作成/公開/取得/削除）
    - Location操作（Merchant Location作成）
    - 価格・在庫更新
    """

    # マーケットプレイス定義
    MARKETPLACE_US = "EBAY_US"
    MARKETPLACE_UK = "EBAY_GB"
    MARKETPLACE_AU = "EBAY_AU"

    def __init__(self, account_id: str, credentials: Dict[str, str], environment: str = 'production'):
        """
        Args:
            account_id: アカウントID
            credentials: 認証情報 {'app_id', 'cert_id', 'redirect_uri'}
            environment: 'sandbox' or 'production'
        """
        self.account_id = account_id
        self.environment = environment
        self.is_sandbox = (environment == 'sandbox')

        # トークンマネージャー初期化
        self.token_manager = EbayTokenManager(
            account_id=account_id,
            credentials=credentials,
            environment=environment
        )

        # API URL設定
        if self.is_sandbox:
            self.base_url = "https://api.sandbox.ebay.com"
        else:
            self.base_url = "https://api.ebay.com"

    def _get_headers(self) -> Dict[str, str]:
        """
        API リクエストヘッダー取得

        Returns:
            dict: リクエストヘッダー
        """
        access_token = self.token_manager.get_valid_token()
        if not access_token:
            raise Exception("有効なアクセストークンが取得できません")

        return {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Content-Language": "en-US",
            "X-EBAY-C-MARKETPLACE-ID": self.MARKETPLACE_US
        }

    # =========================================================================
    # Inventory Item 操作
    # =========================================================================

    def create_or_update_inventory_item(self, sku: str, item_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Inventory Item作成/更新

        Args:
            sku: 商品SKU
            item_data: 商品データ
                {
                    'product': {
                        'title': str,
                        'description': str,
                        'imageUrls': [str],
                        'aspects': {'Brand': [str], ...}
                    },
                    'condition': 'NEW' | 'USED',
                    'availability': {
                        'shipToLocationAvailability': {'quantity': int}
                    },
                    'packageWeightAndSize': {...}
                }

        Returns:
            {'success': bool, 'sku': str, 'error': dict}
        """
        url = f"{self.base_url}/sell/inventory/v1/inventory_item/{sku}"

        try:
            response = requests.put(url, headers=self._get_headers(), json=item_data)

            if response.status_code in [200, 201, 204]:
                return {'success': True, 'sku': sku}
            else:
                error_data = response.json() if response.text else {}
                return {'success': False, 'sku': sku, 'error': error_data, 'status_code': response.status_code}

        except requests.exceptions.RequestException as e:
            return {'success': False, 'sku': sku, 'error': str(e)}

    def get_inventory_item(self, sku: str) -> Optional[Dict[str, Any]]:
        """
        Inventory Item取得

        Args:
            sku: 商品SKU

        Returns:
            dict or None: Inventory Itemデータ
        """
        url = f"{self.base_url}/sell/inventory/v1/inventory_item/{sku}"

        try:
            response = requests.get(url, headers=self._get_headers())

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                logger.debug(f"[eBay/{self.account_id}] Inventory Item not found: sku={sku}")
                return None
            else:
                # エラー詳細をログに出力
                error_detail = ""
                try:
                    error_json = response.json()
                    error_detail = json.dumps(error_json, ensure_ascii=False)
                except:
                    error_detail = response.text[:500] if response.text else "No response body"
                logger.error(f"[eBay/{self.account_id}] get_inventory_item failed: sku={sku}, status={response.status_code}, error={error_detail}")
                return None

        except requests.exceptions.RequestException as e:
            logger.error(f"[eBay/{self.account_id}] get_inventory_item exception: sku={sku}, error={e}")
            return None

    def delete_inventory_item(self, sku: str) -> bool:
        """
        Inventory Item削除

        Args:
            sku: 商品SKU

        Returns:
            bool: 成功時True
        """
        url = f"{self.base_url}/sell/inventory/v1/inventory_item/{sku}"

        try:
            response = requests.delete(url, headers=self._get_headers())
            return response.status_code in [200, 204]

        except requests.exceptions.RequestException:
            return False

    def get_all_inventory_items(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """
        全Inventory Itemsを取得（ページネーション対応）

        Args:
            limit: 1ページあたりの取得件数（最大100）
            offset: オフセット（取得開始位置）

        Returns:
            list: Inventory Itemsのリスト
                [
                    {
                        'sku': str,
                        'availability': {
                            'shipToLocationAvailability': {
                                'quantity': int
                            }
                        },
                        'product': {...},
                        ...
                    },
                    ...
                ]
        """
        url = f"{self.base_url}/sell/inventory/v1/inventory_item"

        params = {
            'limit': min(limit, 100),  # 最大100
            'offset': offset
        }

        try:
            response = requests.get(url, headers=self._get_headers(), params=params)

            if response.status_code == 200:
                data = response.json()
                return data.get('inventoryItems', [])
            else:
                return []

        except requests.exceptions.RequestException:
            return []

    def get_all_inventory_items_paginated(self, max_items: int = None) -> List[Dict[str, Any]]:
        """
        全Inventory Itemsを取得（自動ページネーション）

        Args:
            max_items: 最大取得件数（Noneの場合は全件取得）

        Returns:
            list: Inventory Itemsのリスト
        """
        all_items = []
        offset = 0
        limit = 100

        while True:
            items = self.get_all_inventory_items(limit=limit, offset=offset)

            if not items:
                break

            all_items.extend(items)

            # 最大件数チェック
            if max_items and len(all_items) >= max_items:
                all_items = all_items[:max_items]
                break

            # 次のページがない場合は終了
            if len(items) < limit:
                break

            offset += limit

        return all_items

    # =========================================================================
    # Offer 操作
    # =========================================================================

    def create_offer(self, sku: str, price: float, category_id: str,
                    policies: Dict[str, str], quantity: int = 1,
                    merchant_location_key: str = 'JP_LOCATION') -> Optional[str]:
        """
        Offer作成

        Args:
            sku: 商品SKU
            price: 販売価格（USD）
            category_id: eBayカテゴリID
            policies: ポリシーID {'payment': str, 'return': str, 'fulfillment': str}
            quantity: 在庫数
            merchant_location_key: 発送元ロケーションキー

        Returns:
            str or None: Offer ID（失敗時はNone）
        """
        url = f"{self.base_url}/sell/inventory/v1/offer"

        offer_data = {
            "sku": sku,
            "marketplaceId": self.MARKETPLACE_US,
            "format": "FIXED_PRICE",
            "availableQuantity": quantity,
            "categoryId": category_id,
            "merchantLocationKey": merchant_location_key,
            "listingPolicies": {
                "paymentPolicyId": policies['payment'],
                "returnPolicyId": policies['return'],
                "fulfillmentPolicyId": policies['fulfillment']
            },
            "pricingSummary": {
                "price": {
                    "value": str(round(price, 2)),
                    "currency": "USD"
                }
            },
            "listingDuration": "GTC"  # Good Till Cancelled
        }

        try:
            response = requests.post(url, headers=self._get_headers(), json=offer_data)

            if response.status_code in [200, 201]:
                offer = response.json()
                return offer.get('offerId')
            else:
                return None

        except requests.exceptions.RequestException:
            return None

    def publish_offer(self, offer_id: str) -> Optional[str]:
        """
        Offer公開（リスティング作成）

        Args:
            offer_id: Offer ID

        Returns:
            str or None: Listing ID（失敗時はNone）
        """
        url = f"{self.base_url}/sell/inventory/v1/offer/{offer_id}/publish"

        try:
            response = requests.post(url, headers=self._get_headers())

            if response.status_code in [200, 201]:
                result = response.json()
                return result.get('listingId')
            else:
                return None

        except requests.exceptions.RequestException:
            return None

    def get_all_offers(self, limit: int = 200) -> List[Dict[str, Any]]:
        """
        全Offer一覧取得（レガシーシステムと同じ実装）

        Args:
            limit: 1回のリクエストで取得する最大件数（デフォルト: 200、eBay API最大値）

        Returns:
            list: 全Offerリスト
        """
        url = f"{self.base_url}/sell/inventory/v1/offer"
        params = {'limit': limit}

        try:
            print(f"[DEBUG] Request URL: {url}")
            print(f"[DEBUG] Request Params: {params}")

            response = requests.get(url, headers=self._get_headers(), params=params)

            print(f"[DEBUG] Actual Request URL: {response.url}")
            print(f"[DEBUG] API Response Status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                offers = data.get('offers', [])
                total = data.get('total', 0)

                print(f"[DEBUG] Offers retrieved: {len(offers)}, Total: {total}")

                return offers
            else:
                print(f"[DEBUG] API Error Response: {response.text[:500]}")
                return []

        except requests.exceptions.RequestException as e:
            print(f"[DEBUG] Request Exception: {e}")
            return []

    def get_offers_by_sku(self, sku: str) -> List[Dict[str, Any]]:
        """
        SKUに紐づくOffer一覧取得

        Args:
            sku: 商品SKU

        Returns:
            list: Offerリスト
        """
        url = f"{self.base_url}/sell/inventory/v1/offer"
        params = {'sku': sku, 'limit': 10}

        try:
            response = requests.get(url, headers=self._get_headers(), params=params)

            if response.status_code == 200:
                data = response.json()
                return data.get('offers', [])
            else:
                return []

        except requests.exceptions.RequestException:
            return []

    def get_offer(self, offer_id: str) -> Optional[Dict[str, Any]]:
        """
        Offer詳細取得

        Args:
            offer_id: Offer ID

        Returns:
            dict or None: Offer詳細
        """
        url = f"{self.base_url}/sell/inventory/v1/offer/{offer_id}"

        try:
            response = requests.get(url, headers=self._get_headers())

            if response.status_code == 200:
                return response.json()
            else:
                return None

        except requests.exceptions.RequestException:
            return None

    def delete_offer(self, offer_id: str) -> bool:
        """
        Offer削除

        Args:
            offer_id: Offer ID

        Returns:
            bool: 成功時True
        """
        url = f"{self.base_url}/sell/inventory/v1/offer/{offer_id}"

        try:
            response = requests.delete(url, headers=self._get_headers())
            return response.status_code in [200, 204]

        except requests.exceptions.RequestException:
            return False

    def relist_offer(self, offer_id: str, sku: str, merchant_location_key: str = 'JP_LOCATION') -> Optional[str]:
        """
        UNPUBLISHED状態のOfferを再公開（relist）

        販売済み等でUNPUBLISHED状態になったOfferを再公開します。
        merchantLocationKeyが設定されていない場合は、Offerを更新してから再公開します。

        Args:
            offer_id: Offer ID
            sku: 商品SKU
            merchant_location_key: 発送元ロケーションキー（デフォルト: JP_LOCATION）

        Returns:
            str or None: 新しいListing ID（失敗時はNone）
        """
        # 既存Offer取得
        offer = self.get_offer(offer_id)
        if not offer:
            print(f"  [ERROR] relist_offer: Offer取得失敗 offer_id={offer_id}")
            return None

        # Offerのステータスを確認
        offer_status = offer.get('status', '')
        if offer_status != 'UNPUBLISHED':
            print(f"  [WARN] relist_offer: OfferはUNPUBLISHED状態ではありません (status={offer_status})")
            # 既にPUBLISHEDの場合はlisting IDを返す
            if offer_status == 'PUBLISHED':
                return offer.get('listing', {}).get('listingId')
            return None

        # merchantLocationKeyが設定されていない場合は更新
        if not offer.get('merchantLocationKey'):
            print(f"  [INFO] relist_offer: merchantLocationKeyが未設定、更新します")

            # Offerを更新
            offer['merchantLocationKey'] = merchant_location_key

            # 読み取り専用フィールドを削除
            fields_to_remove = ['availableQuantity', 'offerId', 'listing', 'status']
            update_offer = {k: v for k, v in offer.items() if k not in fields_to_remove}

            url = f"{self.base_url}/sell/inventory/v1/offer/{offer_id}"

            try:
                response = requests.put(url, headers=self._get_headers(), json=update_offer)

                if response.status_code not in [200, 204]:
                    print(f"  [ERROR] relist_offer: Offer更新失敗 status={response.status_code}")
                    try:
                        error_data = response.json()
                        print(f"  [ERROR] レスポンス: {error_data}")
                    except:
                        print(f"  [ERROR] レスポンステキスト: {response.text[:500]}")
                    return None

                print(f"  [INFO] relist_offer: Offer更新成功 (merchantLocationKey={merchant_location_key})")

            except requests.exceptions.RequestException as e:
                print(f"  [ERROR] relist_offer: Offer更新エラー: {e}")
                return None

        # Offer再公開
        listing_id = self.publish_offer(offer_id)
        return listing_id

    # =========================================================================
    # 価格・在庫更新
    # =========================================================================

    def update_offer_price(self, offer_id: str, new_price: float) -> bool:
        """
        Offer価格更新

        Args:
            offer_id: Offer ID
            new_price: 新しい価格（USD）

        Returns:
            bool: 成功時True
        """
        url = f"{self.base_url}/sell/inventory/v1/offer/{offer_id}"

        # 既存Offer取得
        offer = self.get_offer(offer_id)
        if not offer:
            print(f"  [ERROR] Offer取得失敗: offer_id={offer_id}")
            return False

        # Offerの詳細情報を取得
        offer_quantity = offer.get('availableQuantity', 0)
        offer_status = offer.get('status', 'unknown')
        sku = offer.get('sku', 'unknown')

        # 重要: Inventory Itemの数量が0の場合、価格更新が拒否される
        # eBay APIの制約により、PUBLISHED状態のOfferの価格を更新するには、
        # Inventory Itemの数量が1以上である必要がある
        # 最適化: PUBLISHED状態かつOffer数量が0の場合のみInventory Itemを取得
        if offer_status == 'PUBLISHED' and offer_quantity == 0:
            inventory_item = self.get_inventory_item(sku)
            if inventory_item:
                availability = inventory_item.get('availability', {})
                ship_to_location = availability.get('shipToLocationAvailability', {})
                quantity = ship_to_location.get('quantity', 0)

                if quantity == 0:
                    print(f"  [INFO] Inventory Item数量が0のため、1に更新してから価格を更新します")
                    success = self.update_inventory_quantity(sku, 1)
                    if success:
                        logger.info(f"[eBay/{self.account_id}] Inventory Item数量を1に更新しました: sku={sku}")
                    else:
                        logger.error(f"[eBay/{self.account_id}] Inventory Item数量の更新に失敗しました: sku={sku}")
                        return False

        # 価格のみ更新
        offer['pricingSummary']['price']['value'] = str(round(new_price, 2))

        # IMPORTANT: PUTリクエストから読み取り専用フィールドを削除
        # availableQuantity, offerId, listing, statusは更新時に含めてはいけない
        # これらを含めるとeBay APIがエラー25004を返す
        fields_to_remove = ['availableQuantity', 'offerId', 'listing', 'status']
        for field in fields_to_remove:
            offer.pop(field, None)

        # デバッグ: PUTリクエストボディを出力
        logger.debug(f"[eBay/{self.account_id}] PUT request body keys: {list(offer.keys())}")
        logger.debug(f"[eBay/{self.account_id}] pricingSummary={offer.get('pricingSummary')}")

        try:
            response = requests.put(url, headers=self._get_headers(), json=offer)

            if response.status_code in [200, 204]:
                return True
            else:
                # エラー詳細をログ出力
                error_detail = ""
                try:
                    error_data = response.json()
                    error_detail = json.dumps(error_data, ensure_ascii=False)
                except:
                    error_detail = response.text[:500] if response.text else "No response body"
                logger.error(f"[eBay/{self.account_id}] update_offer_price failed: offer_id={offer_id}, status={response.status_code}, error={error_detail}")
                return False

        except requests.exceptions.RequestException as e:
            logger.error(f"[eBay/{self.account_id}] update_offer_price exception: offer_id={offer_id}, error={e}")
            return False

    def update_inventory_quantity(self, sku: str, quantity: int) -> bool:
        """
        在庫数更新

        Args:
            sku: 商品SKU
            quantity: 在庫数

        Returns:
            bool: 成功時True
        """
        # 既存Inventory Item取得
        item = self.get_inventory_item(sku)
        if not item:
            logger.error(f"[eBay/{self.account_id}] update_inventory_quantity failed: sku={sku} - Inventory Item not found")
            return False

        # 在庫数のみ更新
        item['availability']['shipToLocationAvailability']['quantity'] = quantity

        result = self.create_or_update_inventory_item(sku, item)
        if not result.get('success', False):
            # エラー詳細をログに出力
            error_info = result.get('error', 'Unknown error')
            status_code = result.get('status_code', 'N/A')
            logger.error(f"[eBay/{self.account_id}] update_inventory_quantity failed: sku={sku}, quantity={quantity}, status={status_code}, error={error_info}")
            return False
        return True

    # =========================================================================
    # Location 操作
    # =========================================================================

    def create_location(self, location_key: str = 'JP_LOCATION',
                       name: str = 'Japan Warehouse') -> bool:
        """
        Merchant Location作成

        Args:
            location_key: ロケーションキー
            name: ロケーション名

        Returns:
            bool: 成功時True
        """
        url = f"{self.base_url}/sell/inventory/v1/location/{location_key}"

        location_data = {
            "location": {
                "address": {
                    "addressLine1": "Tokyo",
                    "city": "Tokyo",
                    "stateOrProvince": "Tokyo",
                    "postalCode": "155-0031",
                    "country": "JP"
                }
            },
            "locationInstructions": "Items ship from Japan",
            "name": name,
            "merchantLocationStatus": "ENABLED",
            "locationTypes": ["WAREHOUSE"]
        }

        try:
            # PUTメソッドでロケーション作成/更新
            response = requests.put(url, headers=self._get_headers(), json=location_data)
            return response.status_code in [200, 201, 204]

        except requests.exceptions.RequestException:
            return False

    # =========================================================================
    # ヘルパーメソッド
    # =========================================================================

    def build_inventory_item_data(self, product_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        master.dbの商品データからInventory Item用データを構築

        Args:
            product_data: 商品データ（master.db products + SP-API情報）
                {
                    'title_en': str,
                    'description_en': str,
                    'images': [str],
                    'brand': str,
                    'category': str,
                    ...
                }

        Returns:
            dict: eBay Inventory Item用データ
        """
        # 画像URL（最大12枚）
        images = product_data.get('images', [])
        if isinstance(images, str):
            try:
                images = json.loads(images)
            except:
                images = []

        # タイトル（80文字制限）
        title = product_data.get('title_en', '')[:80]

        # 説明文
        description = product_data.get('description_en', '') or title

        # Aspects（Item Specifics）
        aspects = {
            "Brand": [product_data.get('brand', 'Unbranded')],
            "Condition": ["New"],
            "Country/Region of Manufacture": ["Japan"],
        }

        # カテゴリがあれば追加
        if product_data.get('category'):
            aspects["Category"] = [product_data['category']]

        item_data = {
            "product": {
                "title": title,
                "description": description,
                "imageUrls": images[:12],  # 最大12枚
                "aspects": aspects
            },
            "condition": "NEW",
            "conditionDescription": "Brand new, sealed",
            "availability": {
                "shipToLocationAvailability": {
                    "quantity": 1
                }
            },
            "packageWeightAndSize": {
                "dimensions": {
                    "height": 10,
                    "length": 20,
                    "width": 15,
                    "unit": "CENTIMETER"
                },
                "weight": {
                    "value": 500,
                    "unit": "GRAM"
                }
            }
        }

        return item_data


# テスト実行
def main():
    """テスト実行"""
    # Windows環境対応
    if sys.platform == 'win32':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    print("eBay APIクライアント - モジュールロードテスト")
    print("=" * 60)

    # ダミー認証情報でインスタンス作成
    credentials = {
        'app_id': 'test_app_id',
        'cert_id': 'test_cert_id',
        'redirect_uri': 'https://localhost:8000/callback'
    }

    try:
        client = EbayAPIClient(
            account_id='test_account',
            credentials=credentials,
            environment='sandbox'
        )
        print("[OK] EbayAPIClient インスタンス作成成功")
        print(f"     環境: {client.environment}")
        print(f"     Base URL: {client.base_url}")

    except Exception as e:
        print(f"[ERROR] エラー: {e}")
        import traceback
        traceback.print_exc()

    print("=" * 60)
    print("[OK] モジュールのロードに成功しました")


if __name__ == '__main__':
    main()
