"""
Amazon SP-API Client

Amazon Selling Partner APIのラッパークライアント
既存システムから移植
"""

import os
import time
import json
import logging
import requests
import threading
from typing import List, Dict, Any, Optional
from sp_api.api import CatalogItems, Products
from sp_api.base import Marketplaces

# ロガー設定（ISSUE #011対応）
logger = logging.getLogger(__name__)

# 通知機能（オプショナル）
try:
    from shared.utils.notifier import Notifier
    NOTIFIER_AVAILABLE = True
except ImportError:
    NOTIFIER_AVAILABLE = False


class AmazonSPAPIClient:
    """
    Amazon SP-API クライアント

    機能:
    - 商品情報取得（Catalog API）
    - 価格情報取得（Products API - get_item_offers）
    - 在庫情報取得

    注意:
    - Products API (get_item_offers) を使用することで、すべての商品の価格が取得可能
    - Prime + FBA発送 + 即時発送可能 (availabilityType=NOW) の商品をフィルタリング
    """

    def __init__(self, credentials: Dict[str, str], shutdown_event=None):
        """
        Args:
            credentials: SP-API認証情報
                - refresh_token: リフレッシュトークン
                - lwa_app_id: LWA App ID
                - lwa_client_secret: LWA Client Secret
            shutdown_event: threading.Event - シャットダウン通知用のイベント（デーモンから渡される）
                イベントがセットされた場合、処理を中断する
                threading.Event.wait() はシグナルで即座に中断可能
        """
        import os

        self.credentials = credentials
        self.marketplace = Marketplaces.JP
        self.shutdown_event = shutdown_event

        # アクセストークン管理
        self.access_token = None
        self.token_expires_at = 0

        # レート制限管理（ISSUE #005 & #006対応）
        # 公式レート: getItemOffersBatch = 0.1 req/sec (10秒/リクエスト)
        # ※2023年7月10日以降、0.5 req/sec から 0.1 req/sec に変更
        # 参考: https://developer-docs.amazon.com/sp-api/docs/product-pricing-api-rate-limits
        # ISSUE #006: QuotaExceeded発生のため、公式レート + 余裕2秒に修正
        # 初回リクエスト時に即座に送信されないよう、Noneで初期化
        self.last_request_time = None

        # レート制限設定
        # Catalog API（個別処理）: 0.7秒/リクエスト（ISSUE #023最適化）
        # 公式レート: 2 req/sec (0.5秒間隔)
        # 実測結果: 0.5秒でも6,494件/6,495件成功（QuotaExceededエラーは出るがデータ更新は成功）
        # 安全マージンを考慮して0.7秒を推奨（0.5秒の1.4倍）
        self.min_interval_catalog = float(os.getenv('SP_API_CATALOG_INTERVAL', 0.7))

        # Pricing API - getItemOffersBatch（バッチ処理）: 12秒/リクエスト（ISSUE #006対応）
        default_interval_item_offers = 12.0  # 公式レート10秒 + 余裕2秒
        self.min_interval_batch = float(os.getenv('SP_API_BATCH_INTERVAL', default_interval_item_offers))

        # デフォルトはバッチ処理の間隔を使用（後方互換性）
        self.min_interval = self.min_interval_batch

        # 通知機能の初期化（オプショナル）
        self.notifier = None
        if NOTIFIER_AVAILABLE:
            try:
                self.notifier = Notifier()
            except Exception:
                # 通知機能の初期化に失敗してもエラーにしない
                pass

        # QuotaExceededエラーの発生状況を追跡（重複通知を防ぐ）
        self.quota_exceeded_notified = False
        self.quota_exceeded_count = 0  # QuotaExceededエラーの発生回数

        # スレッドセーフなレート制限のためのロック
        self._rate_limit_lock = threading.Lock()

    def _interruptible_sleep(self, total_seconds: float) -> bool:
        """
        割り込み可能なsleep（デーモン用）

        threading.Event.wait() を使用することで、シグナルで即座に中断可能。
        Event.wait(timeout) はタイムアウトまで待機し、イベントがセットされた場合は即座に返る。

        Args:
            total_seconds: 待機時間（秒）

        Returns:
            bool: 正常に待機完了した場合True、シャットダウン要求で中断された場合False
        """
        # shutdown_eventが設定されていない場合は通常のsleep
        if self.shutdown_event is None:
            time.sleep(total_seconds)
            return True

        # Event.wait() はシグナルで即座に中断可能
        # タイムアウトまで待機し、イベントがセットされたらTrueを返す
        # タイムアウトしたらFalseを返す
        interrupted = self.shutdown_event.wait(timeout=total_seconds)

        if interrupted:
            logger.info(f"シャットダウン要求を検出（SP-API待機中断）: event.is_set()={self.shutdown_event.is_set()}")
            return False

        return True

    def _wait_for_rate_limit(self, interval: float = None) -> bool:
        """
        レート制限のための待機（スレッドセーフ、割り込み可能）

        Args:
            interval: 待機間隔（秒）。Noneの場合はself.min_intervalを使用

        Returns:
            bool: 正常に待機完了した場合True、シャットダウン要求で中断された場合False
        """
        if interval is None:
            interval = self.min_interval

        # ロックの中で待機時間を計算
        wait_time = None
        with self._rate_limit_lock:
            current_time = time.time()

            # 初回リクエストの場合はlast_request_timeがNone
            if self.last_request_time is None:
                self.last_request_time = current_time
                return True

            time_since_last_request = current_time - self.last_request_time

            if time_since_last_request < interval:
                wait_time = interval - time_since_last_request

        # ロックの外で待機（シグナル処理を妨げない）
        if wait_time is not None and wait_time > 0:
            if not self._interruptible_sleep(wait_time):
                # シャットダウン要求で中断された場合
                return False

        # 待機完了後、ロックを再取得してlast_request_timeを更新
        with self._rate_limit_lock:
            self.last_request_time = time.time()
            return True

    def _notify_quota_exceeded(self, asin: str, error_message: str):
        """
        QuotaExceededエラー発生時に通知を送信

        Args:
            asin: エラーが発生したASIN
            error_message: エラーメッセージ
        """
        if not self.notifier or not self.notifier.is_enabled('quota_exceeded'):
            return

        title = 'SP-API QuotaExceeded エラー発生'
        message = (
            f'Amazon SP-APIでQuotaExceededエラーが発生しました。\n\n'
            f'【エラー情報】\n'
            f'ASIN: {asin}\n'
            f'エラー: {error_message}\n\n'
            f'【対応状況】\n'
            f'- レート制限: {self.min_interval}秒/リクエスト\n'
            f'- 自動リトライ: 実行中\n\n'
            f'【推奨アクション】\n'
            f'- ログを確認してエラーが継続していないか確認してください\n'
            f'- エラーが継続する場合は、レート制限設定を見直してください\n'
            f'- 詳細: docs/issues/ISSUE_006_sp_api_rate_limit_getpricing_migration.md'
        )

        try:
            self.notifier.notify(
                event_type='quota_exceeded',
                title=title,
                message=message,
                level='WARNING'
            )
        except Exception as e:
            # 通知失敗してもエラーにしない
            print(f"  -> 通知送信に失敗: {e}")

    def _deduplicate_images(self, image_urls: list) -> list:
        """
        同一画像の異なるサイズを除外（最大サイズのみ保持）

        Amazon画像URLのパターン:
        - https://m.media-amazon.com/images/I/81abc123._AC_SL1500_.jpg (large)
        - https://m.media-amazon.com/images/I/81abc123._AC_SL1000_.jpg (medium)
        - https://m.media-amazon.com/images/I/81abc123._AC_SL500_.jpg (small)

        Args:
            image_urls: 画像URLのリスト

        Returns:
            list: 重複排除された画像URLリスト（最大サイズのみ）
        """
        import re
        from collections import defaultdict

        if not image_urls:
            return []

        # 画像の基本IDとサイズを抽出
        image_groups = defaultdict(list)

        for url in image_urls:
            # Amazon画像URLから画像IDを抽出
            # パターン: /images/I/{IMAGE_ID}.{SIZE_INFO}.jpg
            match = re.search(r'/images/I/([^.]+)', url)
            if match:
                image_id = match.group(1)

                # サイズ情報を抽出（SL1500, SL1000, AC_UL1500_など）
                size_match = re.search(r'_(?:AC_)?(?:SL|UL|SR)(\d+)', url)
                if size_match:
                    size = int(size_match.group(1))
                else:
                    # サイズ情報がない場合はデフォルト値
                    size = 0

                image_groups[image_id].append((url, size))
            else:
                # パターンに一致しない場合はそのまま保持
                image_groups[url].append((url, 0))

        # 各グループから最大サイズの画像のみを選択
        deduplicated = []
        for image_id, url_list in image_groups.items():
            # サイズでソートして最大のものを選択
            url_list.sort(key=lambda x: x[1], reverse=True)
            deduplicated.append(url_list[0][0])

        return deduplicated

    def _get_access_token(self) -> str:
        """LWAアクセストークンを取得"""
        current_time = time.time()

        # 既存トークンが有効な場合は再利用
        if self.access_token and current_time < self.token_expires_at:
            return self.access_token

        url = "https://api.amazon.com/auth/o2/token"
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": self.credentials["refresh_token"],
            "client_id": self.credentials["lwa_app_id"],
            "client_secret": self.credentials["lwa_client_secret"]
        }

        response = requests.post(url, data=payload)

        if response.status_code == 200:
            token_data = response.json()
            self.access_token = token_data["access_token"]
            # 有効期限を少し短めに設定（安全マージン）
            self.token_expires_at = current_time + 3500
            return self.access_token
        else:
            raise Exception(f"アクセストークン取得失敗: {response.status_code} - {response.text}")

    def get_product_info(self, asin: str) -> Optional[Dict[str, Any]]:
        """
        商品情報を取得（Catalog API）

        Args:
            asin: 商品ASIN

        Returns:
            dict: 商品情報
                - asin: ASIN
                - title_ja: 商品名
                - description_ja: 商品説明
                - brand: ブランド
                - category: カテゴリ
                - images: 画像URLリスト
                - bullet_points: 箇条書き説明リスト
                - attributes: その他属性
        """
        try:
            # レート制限待機（Catalog API: 2.5秒/リクエスト）
            self._wait_for_rate_limit(self.min_interval_catalog)

            catalog_client = CatalogItems(
                marketplace=self.marketplace,
                credentials=self.credentials
            )

            result = catalog_client.get_catalog_item(
                asin,
                includedData=['attributes', 'summaries', 'images', 'salesRanks']
            )

            item_data = result() if callable(result) else result

            # データを整形して返す
            product_info = {
                'asin': asin,
                'title_ja': None,
                'title_en': None,
                'description_ja': None,
                'brand': None,
                'category': None,
                'images': [],
                'bullet_points': [],
                'attributes': {}
            }

            # 基本情報（summaries）
            summaries = item_data.get('summaries', [])
            if summaries:
                summary = summaries[0]
                product_info['title_ja'] = summary.get('itemName')
                product_info['brand'] = summary.get('brandName')

            # 属性情報
            attributes = item_data.get('attributes', {})
            product_info['attributes'] = attributes

            # 箇条書き説明
            bullet_points = attributes.get('bullet_point', [])
            for point in bullet_points:
                if isinstance(point, dict):
                    text = point.get('value', '')
                else:
                    text = str(point)
                if text:
                    product_info['bullet_points'].append(text)

            # 商品説明（箇条書きをプレーンテキスト形式で整形）
            if product_info['bullet_points']:
                # 箇条書きを改行と記号で整形して読みやすくする
                text_description = ''
                for point in product_info['bullet_points']:
                    # 長い文章は句点で改行を入れて読みやすくする
                    formatted_point = point.replace('。 ', '。\n')
                    formatted_point = formatted_point.replace('。', '。\n')
                    # 末尾の改行を削除して、箇条書き記号を追加
                    formatted_point = formatted_point.rstrip('\n')
                    text_description += f'■ {formatted_point}\n\n'
                # 末尾の余分な改行を削除
                product_info['description_ja'] = text_description.rstrip('\n')
            else:
                # bullet_pointsがない場合はタイトルを説明文として使用
                if product_info['title_ja']:
                    product_info['description_ja'] = product_info['title_ja']

            # カテゴリ情報（salesRanksから階層パスを構築）
            sales_ranks = item_data.get('salesRanks', [])
            if sales_ranks:
                # 日本市場のsalesRanksを取得
                for sales_rank in sales_ranks:
                    if sales_rank.get('marketplaceId') == 'A1VC38T7YXB528':  # JP
                        ranks = sales_rank.get('ranks', [])
                        if ranks:
                            # ranks配列のtitleを " > " で結合してカテゴリパスを作成
                            # 例: "DIY・工具・ガーデン > ガーデン噴霧器"
                            category_path = ' > '.join([rank.get('title', '') for rank in ranks if rank.get('title')])
                            if category_path:
                                product_info['category'] = category_path
                        break

            # salesRanksでカテゴリが取得できなかった場合、browseNodeInfoから取得（フォールバック）
            if not product_info['category']:
                browse_node_info = item_data.get('browseNodeInfo', {})
                browse_nodes = browse_node_info.get('browseNodes', [])

                if browse_nodes:
                    # 最初のbrowseNodeを使用
                    browse_node = browse_nodes[0]
                    category_names = []

                    # 祖先（ancestor）から階層を構築（ルート → リーフの順）
                    ancestors = browse_node.get('ancestor', [])
                    for ancestor in ancestors:
                        display_name = ancestor.get('displayName')
                        if display_name:
                            category_names.append(display_name)

                    # 現在のノードのdisplayNameを追加（最も具体的なカテゴリ）
                    display_name = browse_node.get('displayName')
                    if display_name:
                        category_names.append(display_name)

                    # " > " で結合してカテゴリパスを作成
                    if category_names:
                        product_info['category'] = ' > '.join(category_names)

            # 画像URL（variant別に最大サイズのみを選択）
            images = item_data.get('images', [])
            for marketplace_images in images:
                if marketplace_images.get('marketplaceId') == 'A1VC38T7YXB528':  # JP
                    image_list = marketplace_images.get('images', [])

                    # variant別にグルーピングして最大サイズを選択
                    from collections import defaultdict
                    variants = defaultdict(list)

                    for img in image_list:
                        variant = img.get('variant', 'UNKNOWN')
                        variants[variant].append(img)

                    # variantを順序付け（MAIN, PT01, PT02, ...）
                    def sort_variant_key(v):
                        if v == 'MAIN':
                            return '0'
                        return v.replace('PT', '1')

                    # 各variantから最大サイズ（height x width）の画像を選択
                    for variant in sorted(variants.keys(), key=sort_variant_key):
                        variant_images = variants[variant]
                        # heightでソートして最大のものを選択
                        max_image = max(variant_images, key=lambda x: x.get('height', 0) * x.get('width', 0))
                        link = max_image.get('link')
                        if link:
                            product_info['images'].append(link)
                    break

            return product_info

        except Exception as e:
            print(f"エラー: ASIN {asin} の商品情報取得失敗 - {e}")
            return None

    def get_product_price(self, asin: str, max_retries: int = 3) -> Optional[Dict[str, Any]]:
        """
        価格情報を取得（Products API - get_item_offers）

        必須条件:
        - 到着日が3日以内
        - 送料無料

        優先取得条件（スコアリング）:
        1. 即時発送
        2. 到着までの期限が短い順（値がない場合は招待制の可能性があるため除外）
        3. Prime商品
        4. FBA発送

        複数ある場合: スコアが高い順、同スコアなら安い順に取得

        除外条件（将来のTODO）:
        - 評価母数が40件以上 + 良い評価が60％以下

        Args:
            asin: 商品ASIN
            max_retries: 最大リトライ回数（デフォルト3回）

        Returns:
            dict or None: 価格情報。APIエラー時はNoneを返す（在庫切れとエラーを区別）
                {
                    'price': 1234,  # 価格（整数、円）
                    'in_stock': True,  # 在庫あり
                    'is_prime': True,  # Prime対象
                    'is_fba': True,  # FBA発送
                    'is_buybox_winner': True,  # カート獲得商品
                }
        """
        retry_delay = 5  # リトライ待機時間（秒）
        last_error = None

        for attempt in range(max_retries):
            try:
                # レート制限待機（個別処理: 2.5秒/リクエスト）
                self._wait_for_rate_limit(self.min_interval_catalog)

                products_client = Products(
                    credentials=self.credentials,
                    marketplace=self.marketplace
                )

                response = products_client.get_item_offers(
                    asin=asin,
                    item_condition="New"
                )

                offers = response.payload.get('Offers', [])

                if not offers:
                    # オファーがない（在庫切れ） - これは正常なレスポンス
                    return {'price': None, 'in_stock': False}

                # 候補となるオファーをフィルタリング＆スコアリング
                candidates = []

                for offer in offers:
                    # 基本情報を取得
                    sub_condition = offer.get('SubCondition', '').lower()
                    if sub_condition != 'new':
                        continue  # 新品のみ

                    shipping_info = offer.get('Shipping', {})
                    is_free_shipping = (shipping_info.get('Amount', 0) == 0)

                    shipping_time = offer.get('ShippingTime', {})
                    availability_type = shipping_time.get('availabilityType')
                    max_hours = shipping_time.get('maximumHours', 999)

                    # 招待制商品を除外（max_hoursが設定されていない＝999のまま）
                    if max_hours == 999:
                        continue

                    # 必須条件チェック: 3日以内配送 AND 送料無料
                    if max_hours > 72:
                        continue
                    if not is_free_shipping:
                        continue

                    # 優先条件の取得
                    is_prime = offer.get('PrimeInformation', {}).get('IsPrime', False)
                    is_fba = offer.get('IsFulfilledByAmazon', False)
                    is_immediate = (availability_type == 'NOW')
                    is_buybox_winner = offer.get('IsBuyBoxWinner', False)
                    price = offer.get('ListingPrice', {}).get('Amount')

                    if price is None:
                        continue

                    # スコアリング
                    score = 0
                    if is_immediate:
                        score += 1000  # 即時発送は最優先
                    score += (72 - max_hours)  # 到着が早いほど高スコア（最大72点）
                    if is_prime:
                        score += 100
                    if is_fba:
                        score += 50

                    candidates.append({
                        'price': price,
                        'score': score,
                        'is_prime': is_prime,
                        'is_fba': is_fba,
                        'is_immediate': is_immediate,
                        'is_buybox_winner': is_buybox_winner,
                        'max_hours': max_hours
                    })

                if not candidates:
                    # 条件に合うオファーが見つからなかった - これも正常なレスポンス
                    return {'price': None, 'in_stock': False}

                # スコアが高い順、同じスコアなら価格が安い順にソート
                candidates.sort(key=lambda x: (-x['score'], x['price']))

                # 最適な商品を選択
                best = candidates[0]

                return {
                    'price': best['price'],
                    'in_stock': True,
                    'is_prime': best['is_prime'],
                    'is_fba': best['is_fba'],
                    'is_buybox_winner': best['is_buybox_winner'],
                    'currency': 'JPY'
                }

            except Exception as e:
                error_message = str(e)
                last_error = error_message

                # レート制限エラーの判定
                if "QuotaExceeded" in error_message or "rate limit" in error_message.lower():
                    print(f"  -> 警告 (価格情報取得): ASIN={asin} でレート制限(QuotaExceeded)発生。({attempt + 1}/{max_retries})")

                    # カウンターを増やす
                    self.quota_exceeded_count += 1

                    # 初回のみ通知を送信（重複通知を防ぐ）
                    if not self.quota_exceeded_notified and self.notifier:
                        self._notify_quota_exceeded(asin, error_message)
                        self.quota_exceeded_notified = True

                    if attempt < max_retries - 1:
                        # 最後のリトライでなければ待機
                        print(f"     ... {retry_delay}秒待機してリトライします。")
                        if not self._interruptible_sleep(retry_delay):
                            # シャットダウン要求で中断された場合
                            logger.info(f"シャットダウン要求により、リトライを中断しました（ASIN={asin}）")
                            return None
                        continue
                    else:
                        # リトライ上限に達した
                        print(f"  -> [重要] リトライ上限({max_retries}回)に達しました。ASIN={asin}")
                        print(f"  -> エラー詳細: {error_message}")
                        break
                else:
                    # その他のエラー（即座にリトライせず、1回だけリトライ）
                    print(f"  -> エラー (価格情報取得): ASIN={asin}, {e} ({attempt + 1}/{max_retries})")

                    if attempt < max_retries - 1:
                        # 最後のリトライでなければ待機してリトライ
                        print(f"     ... {retry_delay}秒待機してリトライします。")
                        if not self._interruptible_sleep(retry_delay):
                            # シャットダウン要求で中断された場合
                            logger.info(f"シャットダウン要求により、リトライを中断しました（ASIN={asin}）")
                            return None
                        continue
                    else:
                        print(f"  -> [重要] リトライ上限({max_retries}回)に達しました。ASIN={asin}")
                        break

        # リトライ失敗 - APIエラーとして None を返す（在庫切れとは区別）
        print(f"  -> [エラー通知] ASIN={asin} のSP-API取得に失敗しました。前回のキャッシュを保持します。")
        print(f"     最終エラー: {last_error}")
        return None

    def get_prices_batch(self, asins: List[str], batch_size: int = 20) -> Dict[str, Dict[str, Any]]:
        """
        複数商品の価格を取得（バッチAPI使用）

        get_item_offers_batch() を使用して、効率的に複数ASINの価格情報を取得します。

        レート制限（ISSUE #005対応）:
        - 0.1リクエスト/秒（10秒に1回、2023年7月10日以降）
        - 実装では余裕を持って12秒/リクエスト
        - バッチサイズ: 最大20件/リクエスト
        - 参考: https://developer-docs.amazon.com/sp-api/docs/product-pricing-api-rate-limits

        Args:
            asins: ASINのリスト
            batch_size: 1バッチあたりのASIN数（デフォルト: 20、最大: 20）

        Returns:
            dict: ASIN別の価格情報
                {
                    'ASIN1': {'price': 1234, 'in_stock': True, 'is_prime': True, ...},
                    'ASIN2': {'price': None, 'in_stock': False},
                    ...
                }
        """
        if batch_size > 20:
            print(f"警告: バッチサイズが20を超えています。20に制限します。")
            batch_size = 20

        results = {}

        # ASINをバッチに分割
        batches = [asins[i:i + batch_size] for i in range(0, len(asins), batch_size)]

        products_client = Products(
            credentials=self.credentials,
            marketplace=self.marketplace
        )

        for batch_idx, batch_asins in enumerate(batches, 1):
            # レート制限待機（全てのバッチで実行 - ISSUE #005 & #006対応）
            # 前回のリクエストから12秒以上経過していることを保証
            if not self._wait_for_rate_limit():
                # シャットダウン要求で中断された場合
                logger.info(f"シャットダウン要求により、バッチ処理を中断しました（{batch_idx-1}/{len(batches)}完了）")
                break

            # ISSUE #011対応: バッチリクエスト開始ログ
            batch_start_time = time.time()
            logger.info(f"バッチ {batch_idx}/{len(batches)}: {len(batch_asins)}件のASINをリクエスト開始")

            # バッチリクエストを作成
            requests = []
            for asin in batch_asins:
                request = {
                    "uri": f"/products/pricing/v0/items/{asin}/offers",
                    "method": "GET",
                    "MarketplaceId": self.marketplace.marketplace_id,
                    "ItemCondition": "New"
                }
                requests.append(request)

            try:
                # バッチリクエストを実行
                response = products_client.get_item_offers_batch(requests_=requests)

                # ISSUE #011対応: バッチ内の成功/失敗をカウント
                batch_success_count = 0
                batch_failure_count = 0

                if hasattr(response, 'payload'):
                    payload = response.payload

                    if isinstance(payload, dict) and 'responses' in payload:
                        responses = payload['responses']

                        for item_response in responses:
                            # ステータスコードを確認
                            status = item_response.get('status', {})
                            status_code = status.get('statusCode', 0)

                            # ASINをrequestフィールドから取得
                            request_info = item_response.get('request', {})
                            asin = request_info.get('Asin')

                            if not asin:
                                continue

                            if status_code == 200:
                                # ISSUE #011対応: 成功カウント
                                batch_success_count += 1

                                # 成功レスポンス
                                body = item_response.get('body', {})
                                payload_data = body.get('payload', {})

                                if payload_data:
                                    offers = payload_data.get('Offers', [])

                                    # デバッグ用: 特定ASINの詳細ログ（環境変数で制御）
                                    # 使用方法: SET DEBUG_ASIN=B0006PKIQA として実行
                                    debug_asin = os.getenv('DEBUG_ASIN', '')
                                    is_debug = (asin == debug_asin) if debug_asin else False
                                    if is_debug:
                                        print(f"\n=== デバッグ: ASIN {asin} ===")
                                        print(f"オファー件数: {len(offers)}件")

                                    if offers:
                                        # 価格情報を抽出（既存のロジックと同様）
                                        best_offer = None
                                        best_score = -1

                                        for offer_idx, offer in enumerate(offers, 1):
                                            if is_debug:
                                                print(f"\n--- オファー #{offer_idx} ---")
                                            # フィルタリング条件
                                            sub_condition = offer.get('SubCondition', '').lower()

                                            if is_debug:
                                                print(f"  SubCondition: {sub_condition}")

                                            if sub_condition != 'new':
                                                if is_debug:
                                                    print(f"  [NG] 新品ではない -> スキップ")
                                                continue

                                            shipping_info = offer.get('Shipping', {})
                                            shipping_amount = shipping_info.get('Amount', 0)
                                            is_free_shipping = (shipping_amount == 0)

                                            shipping_time = offer.get('ShippingTime', {})
                                            max_hours = shipping_time.get('maximumHours', 999)
                                            availability_type = shipping_time.get('availabilityType', 'N/A')

                                            if is_debug:
                                                print(f"  送料: {shipping_amount}円 (無料: {is_free_shipping})")
                                                print(f"  配送時間: {max_hours}時間 (タイプ: {availability_type})")

                                            # 招待制商品を除外
                                            if max_hours == 999:
                                                if is_debug:
                                                    print(f"  [NG] 招待制商品 (maximumHours=999) -> スキップ")
                                                continue

                                            # 必須条件: 3日以内配送 AND 送料無料
                                            if max_hours > 72 or not is_free_shipping:
                                                if is_debug:
                                                    if max_hours > 72:
                                                        print(f"  [NG] 3日以内配送ではない (maximumHours={max_hours} > 72) -> スキップ")
                                                    if not is_free_shipping:
                                                        print(f"  [NG] 送料無料ではない (送料={shipping_amount}円) -> スキップ")
                                                continue

                                            # スコアリング
                                            is_immediate = (shipping_time.get('availabilityType') == 'NOW')
                                            is_prime = offer.get('PrimeInformation', {}).get('IsPrime', False)
                                            is_fba = offer.get('IsFulfilledByAmazon', False)
                                            price = offer.get('ListingPrice', {}).get('Amount')

                                            score = 0
                                            if is_immediate:
                                                score += 1000
                                            score += (72 - max_hours)
                                            if is_prime:
                                                score += 100
                                            if is_fba:
                                                score += 50

                                            if is_debug:
                                                print(f"  Prime: {is_prime}, FBA: {is_fba}")
                                                print(f"  価格: {price}円")
                                                print(f"  スコア: {score}")

                                            if score > best_score:
                                                best_score = score
                                                best_offer = {
                                                    'price': price,
                                                    'is_prime': is_prime,
                                                    'is_fba': is_fba,
                                                    'in_stock': True,
                                                    'currency': 'JPY'
                                                }
                                                if is_debug:
                                                    print(f"  [OK] このオファーを採用 (現在のベストスコア: {best_score})")

                                        if is_debug:
                                            print(f"\n--- 最終結果 ---")
                                            if best_offer:
                                                print(f"[OK] 採用されたオファー: 価格={best_offer['price']}円, スコア={best_score}")
                                            else:
                                                print(f"[NG] 条件を満たすオファーが見つかりませんでした")

                                        if best_offer:
                                            # 成功
                                            best_offer['status'] = 'success'
                                            results[asin] = best_offer
                                        else:
                                            # フィルタリング条件を満たすオファーがない
                                            results[asin] = {
                                                'price': None,
                                                'in_stock': False,
                                                'status': 'filtered_out',
                                                'failure_reason': 'no_offers_matching_criteria'
                                            }
                                    else:
                                        # オファーなし（在庫切れ）
                                        if is_debug:
                                            print(f"\n[NG] オファーが存在しません（在庫切れの可能性）")
                                        results[asin] = {
                                            'price': None,
                                            'in_stock': False,
                                            'status': 'out_of_stock',
                                            'failure_reason': 'no_offers'
                                        }
                                else:
                                    # payloadが空
                                    if is_debug:
                                        print(f"\n[NG] payloadが空です")
                                    results[asin] = {
                                        'price': None,
                                        'in_stock': False,
                                        'status': 'out_of_stock',
                                        'failure_reason': 'empty_payload'
                                    }
                            else:
                                # ISSUE #011対応: 失敗カウント
                                batch_failure_count += 1

                                # エラーレスポンス（400など）
                                error_message = status.get('reasonPhrase', 'Unknown')
                                print(f"  警告: {asin} のステータスコード {status_code}: {error_message}")

                                # APIエラーの詳細を記録
                                results[asin] = {
                                    'price': None,
                                    'in_stock': False,
                                    'status': 'api_error',
                                    'failure_reason': 'sp_api_error',
                                    'error_code': status_code,
                                    'error_message': error_message
                                }

                # ISSUE #011対応: バッチ処理成功時のログ（所要時間と統計）
                batch_elapsed = time.time() - batch_start_time
                logger.info(f"バッチ {batch_idx}/{len(batches)} 完了: "
                           f"所要時間 {batch_elapsed:.2f}秒, "
                           f"成功 {batch_success_count}件, 失敗 {batch_failure_count}件")

            except Exception as e:
                error_message = str(e)
                print(f"  エラー: バッチリクエスト失敗（バッチ {batch_idx}/{len(batches)}）- {error_message}")

                # QuotaExceededエラーの検出と通知
                if "QuotaExceeded" in error_message or "rate limit" in error_message.lower():
                    print(f"  -> [警告] QuotaExceededエラーを検出しました")
                    # カウンターを増やす
                    self.quota_exceeded_count += 1

                    # 初回のみ通知を送信（重複通知を防ぐ）
                    if not self.quota_exceeded_notified and self.notifier:
                        batch_asin_sample = batch_asins[0] if batch_asins else 'N/A'
                        self._notify_quota_exceeded(batch_asin_sample, error_message)
                        self.quota_exceeded_notified = True

                # 失敗したバッチのASINには詳細エラー情報を設定
                for asin in batch_asins:
                    if asin not in results:
                        # バッチ全体のエラーとして記録
                        results[asin] = {
                            'price': None,
                            'in_stock': False,
                            'status': 'api_error',
                            'failure_reason': 'batch_request_failed',
                            'error_message': error_message
                        }

        return results

    def get_pricing_batch(self, asins: List[str], batch_size: int = 20) -> Dict[str, Dict[str, Any]]:
        """
        複数商品の価格を取得（getPricing API使用）- ISSUE #006対応

        【注意】現在は使用していません（将来の拡張用）
        理由: get_product_pricing_for_asins APIがオファー情報を返さないため、
              既存のget_item_offers_batch APIを使用しています。

        getItemOffersBatch との違い（期待値）:
        - レート制限: 0.5 req/sec（5倍速い）
        - 取得データ: カート価格、最安値、FBA情報、送料情報
        - 処理時間: 489バッチ × 2.5秒 = 約20分（getItemOffersBatchの81分から大幅短縮）

        フィルタリング条件:
        - 新品のみ（ItemCondition='New'で指定）
        - 送料無料（Shipping.Amount == 0）
        - FBA（IsFulfilledByAmazon == True）で3日以内配送と判断

        Args:
            asins: ASINのリスト
            batch_size: 1バッチあたりのASIN数（デフォルト: 20、最大: 20）

        Returns:
            dict: ASIN別の価格情報
                {
                    'ASIN1': {'price': 1234, 'in_stock': True, 'is_prime': True, 'is_fba': True, ...},
                    'ASIN2': {'price': None, 'in_stock': False},
                    ...
                }
        """
        if batch_size > 20:
            print(f"警告: バッチサイズが20を超えています。20に制限します。")
            batch_size = 20

        results = {}

        # ASINをバッチに分割
        batches = [asins[i:i + batch_size] for i in range(0, len(asins), batch_size)]

        products_client = Products(
            credentials=self.credentials,
            marketplace=self.marketplace
        )

        # レート制限を一時的にgetPricing用に変更
        original_min_interval = self.min_interval
        self.min_interval = self.min_interval_get_pricing

        try:
            for batch_idx, batch_asins in enumerate(batches, 1):
                # レート制限待機（getPricing: 0.5 req/sec = 2秒/リクエスト + 余裕0.5秒）
                self._wait_for_rate_limit()

                try:
                    # getPricing APIを呼び出し（正しいメソッド名: get_product_pricing_for_asins）
                    response = products_client.get_product_pricing_for_asins(
                        asin_list=batch_asins,
                        item_condition='New'
                    )

                    if hasattr(response, 'payload'):
                        payload = response.payload

                        for item in payload:
                            asin = item.get('ASIN')

                            if not asin:
                                continue

                            # Product pricing情報を取得
                            product = item.get('Product', {})
                            offers = product.get('Offers', [])

                            if offers:
                                # BuyBox価格を優先、なければ最安値
                                buybox_offer = None
                                lowest_offer = None

                                for offer in offers:
                                    offer_type = offer.get('OfferType')

                                    # BuyBox価格
                                    if offer_type == 'BuyBox':
                                        buybox_offer = offer

                                    # 最安値
                                    if offer_type == 'Lowest':
                                        lowest_offer = offer

                                # BuyBox価格を優先
                                selected_offer = buybox_offer if buybox_offer else lowest_offer

                                if selected_offer:
                                    # フィルタリング条件を適用
                                    buying_price = selected_offer.get('BuyingPrice', {})
                                    listing_price = buying_price.get('ListingPrice', {})
                                    shipping = buying_price.get('Shipping', {})

                                    price_amount = listing_price.get('Amount')
                                    shipping_amount = shipping.get('Amount', 0)
                                    is_fba = selected_offer.get('IsFulfilledByAmazon', False)

                                    # フィルタリング: 送料無料 AND FBA（3日以内配送と判断）
                                    if shipping_amount == 0 and is_fba:
                                        results[asin] = {
                                            'price': price_amount,
                                            'is_prime': True,  # FBA商品は基本的にPrime対象
                                            'is_fba': is_fba,
                                            'in_stock': True,
                                            'currency': 'JPY'
                                        }
                                    else:
                                        # フィルタリング条件を満たさない
                                        results[asin] = {'price': None, 'in_stock': False}
                                else:
                                    # オファーが見つからない
                                    results[asin] = {'price': None, 'in_stock': False}
                            else:
                                # オファーなし（在庫切れ）
                                results[asin] = {'price': None, 'in_stock': False}

                except Exception as e:
                    print(f"  エラー: バッチリクエスト失敗（バッチ {batch_idx}/{len(batches)}）- {e}")
                    # 失敗したバッチのASINにはNoneを設定
                    for asin in batch_asins:
                        if asin not in results:
                            results[asin] = None

        finally:
            # レート制限を元に戻す
            self.min_interval = original_min_interval

        return results

    def get_product_with_price(self, asin: str) -> Optional[Dict[str, Any]]:
        """
        商品情報と価格情報を統合して取得

        Args:
            asin: 商品ASIN

        Returns:
            dict: 統合された商品情報
        """
        # 商品情報を取得
        product_info = self.get_product_info(asin)
        if not product_info:
            return None

        # 価格情報を取得（Products API使用）
        price_data = self.get_product_price(asin)

        # 統合
        product_info.update({
            'amazon_price_jpy': price_data.get('price'),
            'amazon_in_stock': price_data.get('in_stock', False),
            'is_prime': price_data.get('is_prime', False),
            'is_fba': price_data.get('is_fba', False),
            'currency': price_data.get('currency', 'JPY')
        })

        return product_info

    def get_products_batch(self, asins: List[str], enable_detailed_logging: bool = False) -> Dict[str, Dict[str, Any]]:
        """
        複数商品の情報を一括取得（詳細ログ付き）

        注意: Products APIはバッチ処理に対応していないため、
        商品情報と価格情報を個別に取得します。

        Args:
            asins: ASINのリスト
            enable_detailed_logging: 詳細ログを有効にするか（デフォルト: False）

        Returns:
            dict: ASIN別の商品情報
        """
        results = {}

        # 統計情報の初期化
        stats = {
            'total': len(asins),
            'success': 0,           # 商品情報+価格情報の両方取得成功
            'partial_success': 0,   # 商品情報のみ取得成功（価格失敗）
            'failed': 0,            # 商品情報取得失敗
            'errors': {
                'QuotaExceeded': 0,
                'NOT_FOUND': 0,
                'Other': 0
            }
        }

        if enable_detailed_logging:
            print(f"\n[BATCH_START] 処理開始: {len(asins)}件")

        # 商品情報と価格情報を個別に取得
        for i, asin in enumerate(asins, 1):
            try:
                # 商品情報取得
                product_info = self.get_product_info(asin)

                if product_info:
                    # 価格情報を追加
                    try:
                        price_data = self.get_product_price(asin)
                        if price_data:
                            product_info.update({
                                'amazon_price_jpy': price_data.get('price'),
                                'amazon_in_stock': price_data.get('in_stock', False),
                                'is_prime': price_data.get('is_prime', False),
                                'is_fba': price_data.get('is_fba', False)
                            })
                            stats['success'] += 1
                            if enable_detailed_logging:
                                print(f"  [{i}/{len(asins)}] ✅ {asin}: 商品情報+価格情報 取得成功")
                        else:
                            # 価格情報取得失敗
                            product_info.update({
                                'amazon_price_jpy': None,
                                'amazon_in_stock': False,
                                'is_prime': False,
                                'is_fba': False
                            })
                            stats['partial_success'] += 1
                            if enable_detailed_logging:
                                print(f"  [{i}/{len(asins)}] ⚠️  {asin}: 商品情報のみ取得（価格情報失敗）")
                    except Exception as price_error:
                        # 価格エラーハンドリング
                        error_str = str(price_error)
                        if 'QuotaExceeded' in error_str:
                            stats['errors']['QuotaExceeded'] += 1
                            error_type = "QuotaExceeded"
                        else:
                            stats['errors']['Other'] += 1
                            error_type = "Other"

                        product_info.update({
                            'amazon_price_jpy': None,
                            'amazon_in_stock': False,
                            'is_prime': False,
                            'is_fba': False
                        })
                        stats['partial_success'] += 1
                        if enable_detailed_logging:
                            print(f"  [{i}/{len(asins)}] ⚠️  {asin}: 商品情報のみ取得（価格エラー: {error_type}）")

                    results[asin] = product_info
                else:
                    # 商品情報取得失敗
                    stats['failed'] += 1
                    if enable_detailed_logging:
                        print(f"  [{i}/{len(asins)}] ❌ {asin}: 商品情報取得失敗")

            except Exception as e:
                # 商品情報取得エラー
                error_str = str(e)

                if 'QuotaExceeded' in error_str:
                    stats['errors']['QuotaExceeded'] += 1
                    error_type = "QuotaExceeded"
                elif 'NOT_FOUND' in error_str:
                    stats['errors']['NOT_FOUND'] += 1
                    error_type = "NOT_FOUND"
                else:
                    stats['errors']['Other'] += 1
                    error_type = "Other"

                stats['failed'] += 1
                if enable_detailed_logging:
                    print(f"  [{i}/{len(asins)}] ❌ {asin}: エラー ({error_type})")

        # 統計情報を出力
        if enable_detailed_logging:
            print(f"\n[BATCH_COMPLETE] 処理完了")
            print(f"  総数: {stats['total']}件")
            print(f"  完全成功: {stats['success']}件（商品情報+価格情報）")
            print(f"  部分成功: {stats['partial_success']}件（商品情報のみ）")
            print(f"  失敗: {stats['failed']}件")
            print(f"  成功率: {(stats['success'] + stats['partial_success']) / stats['total'] * 100:.1f}%")
            if any(stats['errors'].values()):
                print(f"  エラー内訳:")
                if stats['errors']['QuotaExceeded'] > 0:
                    print(f"    - QuotaExceeded: {stats['errors']['QuotaExceeded']}件")
                if stats['errors']['NOT_FOUND'] > 0:
                    print(f"    - NOT_FOUND: {stats['errors']['NOT_FOUND']}件")
                if stats['errors']['Other'] > 0:
                    print(f"    - その他: {stats['errors']['Other']}件")

        return results
