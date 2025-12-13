"""
価格同期スクリプト

キャッシュベースでAmazon価格を取得し、BASE出品の価格を自動同期する
SP-APIを節約するため、キャッシュが古い場合のみSP-APIを呼び出す
"""

import sys
import logging
import signal
from pathlib import Path
from datetime import datetime
import time
from typing import Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

# ロガーの設定
logger = logging.getLogger(__name__)

# グローバルシャットダウンフラグ
_shutdown_requested = False

def _signal_handler(signum, frame):
    """シグナルハンドラ（Ctrl+C対応）"""
    global _shutdown_requested
    signal_name = signal.Signals(signum).name
    logger.info(f"シグナル {signal_name} ({signum}) を受信しました")
    _shutdown_requested = True

# Windows環境でのUTF-8エンコーディング強制設定 + バッファリング無効化
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except AttributeError:
        # Python 3.7未満の場合のフォールバック
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
else:
    # UTF-8だがバッファリングを無効化
    try:
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except AttributeError:
        pass

# パスを追加
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from inventory.core.master_db import MasterDB
from platforms.base.accounts.manager import AccountManager
from platforms.base.core.api_client import BaseAPIClient
from platforms.base.core.listing_validator import ListingValidator
from integrations.amazon.sp_api_client import AmazonSPAPIClient
from integrations.amazon.config import SP_API_CREDENTIALS
from common.pricing.calculator import PriceCalculator
import os
import requests


class PriceSync:
    """
    価格同期クラス
    """

    # 価格計算設定
    DEFAULT_MARKUP_RATIO = 1.3  # デフォルト掛け率: 1.3倍
    MIN_PRICE_DIFF = 100  # 価格差がこの金額以上の場合のみ更新（円）

    def __init__(self, markup_ratio: float = None, register_signal_handler: bool = False):
        """
        初期化

        Args:
            markup_ratio: 掛け率（デフォルト: 1.3）
            register_signal_handler: シグナルハンドラを登録するか（スタンドアロン実行時のみTrue）
                                      daemon経由で実行される場合はFalse（daemon_base.pyが管理）
        """
        # スタンドアロン実行時のみシグナルハンドラを登録
        # daemon経由の場合はdaemon_base.pyのシグナルハンドラが管理
        if register_signal_handler:
            signal.signal(signal.SIGINT, _signal_handler)
            signal.signal(signal.SIGTERM, _signal_handler)

        self.master_db = MasterDB()
        self.account_manager = AccountManager()

        # SP-APIクライアント（キャッシュミス時のみ使用）
        try:
            # 統一された認証情報管理を使用
            if all(SP_API_CREDENTIALS.values()):
                self.sp_api_client = AmazonSPAPIClient(SP_API_CREDENTIALS)
                self.sp_api_available = True
            else:
                logger.warning("SP-API認証情報が不足しています")
                logger.warning("キャッシュが存在する商品のみ処理します")
                self.sp_api_client = None
                self.sp_api_available = False
        except Exception as e:
            logger.error(f"SP-APIクライアント初期化失敗: {e}", exc_info=True)
            logger.warning("キャッシュが存在する商品のみ処理します")
            self.sp_api_client = None
            self.sp_api_available = False

        self.markup_ratio = markup_ratio if markup_ratio else self.DEFAULT_MARKUP_RATIO

        # 価格計算エンジンを初期化
        self.price_calculator = PriceCalculator()

        # 統計情報
        self.stats = {
            'total_listings': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'sp_api_calls': 0,
            'sp_api_errors': 0,
            'cache_fallback': 0,
            'price_updated': 0,
            'no_update_needed': 0,
            'errors': 0,
            'errors_detail': [],
            # 変動検知用の統計（ISSUE #005対応）
            'price_changes': [],  # {'asin': str, 'old': int, 'new': int, 'diff': int}
            'stock_changes': [],  # {'asin': str, 'old': bool, 'new': bool}
            # ISSUE #022対応: 価格取得失敗の詳細分類
            'price_fetch_success': 0,  # 成功
            'price_fetch_api_error': 0,  # APIエラー
            'price_fetch_out_of_stock': 0,  # 在庫切れ
            'price_fetch_filtered_out': 0,  # フィルタリング条件不一致
            'price_fetch_fallback_success': 0,  # フォールバック成功
            'price_fetch_fallback_failed': 0,  # フォールバック失敗
            # 自動delisted処理の統計
            'auto_delisted_count': 0,  # 自動delisted件数
        }

    def calculate_selling_price(self, amazon_price_jpy: int) -> int:
        """
        販売価格を計算

        Args:
            amazon_price_jpy: Amazon価格（円）

        Returns:
            int: 販売価格（円）
        """
        # 新しい価格計算モジュールを使用
        # markup_ratioがコマンドラインオプションで指定されている場合はオーバーライド
        return self.price_calculator.calculate_selling_price(
            amazon_price=amazon_price_jpy,
            override_markup_ratio=self.markup_ratio if self.markup_ratio != self.DEFAULT_MARKUP_RATIO else None
        )

    def get_amazon_price(
        self,
        asin: str,
        use_cache: bool = True,
        allow_sp_api: bool = True,
        update_stats: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Amazon価格情報を取得（Master DB優先）

        Args:
            asin: 商品ASIN
            use_cache: 互換性のため残しているが、Master DBから取得
            allow_sp_api: Master DBにない場合にSP-API呼び出しを許可するか（デフォルト: True）
            update_stats: 統計情報を更新するか（デフォルト: True）

        Returns:
            dict or None: 価格情報 {'price_jpy': int, 'in_stock': bool}
        """
        db_product = None

        # Master DBから取得
        if use_cache:
            try:
                db_product = self.master_db.get_product(asin)

                # priceフィールドが存在するかチェック
                if db_product and db_product.get('amazon_price_jpy') is not None:
                    if update_stats:
                        self.stats['cache_hits'] += 1
                    return {
                        'price_jpy': int(db_product.get('amazon_price_jpy', 0)),
                        'in_stock': db_product.get('amazon_in_stock', False)
                    }
            except Exception as e:
                logger.error(f"    [WARN] Master DB読み込みエラー: {asin} - {e}")
                db_product = None

        # Master DBにデータがない、または欠損している
        if update_stats:
            self.stats['cache_misses'] += 1

        # SP-APIが利用可能で、かつ呼び出しが許可されている場合のみ呼び出し
        if allow_sp_api and self.sp_api_available and self.sp_api_client:
            try:
                logger.info(f"    [SP-API] Master DBミス: {asin} - SP-APIで取得中...")
                product_data = self.sp_api_client.get_product_price(asin)

                if product_data is not None:
                    # 正常に取得できた（在庫あり、または在庫切れの正常レスポンス）
                    self.stats['sp_api_calls'] += 1

                    # マスタDBに保存
                    price_jpy = product_data.get('price')
                    in_stock = product_data.get('in_stock', False)

                    if price_jpy is not None:
                        self.master_db.update_amazon_info(
                            asin=asin,
                            price_jpy=int(price_jpy),
                            in_stock=in_stock
                        )

                    return {
                        'price_jpy': int(price_jpy) if price_jpy else None,
                        'in_stock': in_stock
                    }
                else:
                    # SP-API エラー（None が返された）
                    self.stats['sp_api_errors'] += 1
                    logger.error(f"    [エラー] SP-API取得エラー: {asin}")

                    # フォールバック: 既存のMaster DBを使用
                    if db_product is not None:
                        logger.info(f"    [フォールバック] 既存のMaster DBデータを使用: {asin}")
                        self.stats['cache_fallback'] += 1

                        # in_stock フィールドをチェック
                        price = db_product.get('amazon_price_jpy')
                        in_stock = db_product.get('amazon_in_stock')

                        if price is not None and in_stock is not None:
                            return {
                                'price_jpy': int(price),
                                'in_stock': in_stock
                            }
                        else:
                            logger.info(f"    [WARN] Master DBの在庫情報が不完全: {asin}")
                    else:
                        logger.error(f"    [エラー] フォールバック失敗（Master DBデータなし）: {asin}")

                time.sleep(2.1)  # SP-APIレート制限

            except Exception as e:
                logger.error(f"    [ERROR] SP-API呼び出し例外: {asin} - {e}")
                self.stats['sp_api_errors'] += 1

                # フォールバック: 既存のMaster DBデータを使用
                if db_product is not None:
                    logger.info(f"    [フォールバック] 既存のMaster DBデータを使用: {asin}")
                    self.stats['cache_fallback'] += 1

                    price = db_product.get('amazon_price_jpy')
                    in_stock = db_product.get('amazon_in_stock')

                    if price is not None and in_stock is not None:
                        return {
                            'price_jpy': int(price),
                            'in_stock': in_stock
                        }

                return None

        return None

    def sync_account_prices(self, account_id: str, dry_run: bool = False, max_items: int = None, skip_cache_update: bool = False):
        """
        1アカウントの価格を同期（バッチ処理対応）

        Args:
            account_id: アカウントID
            dry_run: Trueの場合、実際の更新は行わない
            max_items: テスト用：処理する最大商品数（省略時は全件）
            skip_cache_update: Trueの場合、SP-API処理をスキップして既存キャッシュを使用（テスト用）
        """
        account = self.account_manager.get_account(account_id)
        if not account:
            logger.error(f"アカウント {account_id} が見つかりません")
            self.stats['errors'] += 1
            return self.stats

        logger.info("")
        logger.info("┌" + "─" * 68 + "┐")
        logger.info(f"│ 【BASE価格同期】アカウント: {account['name']} ({account_id})" + " " * (68 - len(f" 【BASE価格同期】アカウント: {account['name']} ({account_id})") - 2) + "│")
        logger.info("└" + "─" * 68 + "┘")

        # 出品一覧を取得（出品済みのみ）
        listings = self.master_db.get_listings_by_account(
            platform='base',
            account_id=account_id,
            status='listed'
        )

        # テスト用：商品数を制限
        if max_items and len(listings) > max_items:
            logger.info(f"出品数: {len(listings)}件 → {max_items}件に制限（テストモード）")
            listings = listings[:max_items]
        else:
            logger.info(f"出品数: {len(listings)}件")

        if not listings:
            logger.info("  → 出品なし、スキップ")
            return self.stats

        # BASE APIクライアント作成
        try:
            base_client = BaseAPIClient(
                account_id=account_id,
                account_manager=self.account_manager
            )
        except Exception as e:
            logger.error(f"BASE APIクライアントの初期化に失敗: {e}")
            self.stats['errors'] += 1
            return self.stats

        asins = [listing['asin'] for listing in listings]
        price_map = {}  # ASIN -> 価格情報のマップ

        if skip_cache_update:
            # 既存Master DBから価格情報を取得（SP-API処理をスキップ）
            logger.info(f"\n[重要] SP-API処理をスキップ - Master DBから価格情報を取得中...")
            logger.info(f"  対象商品数: {len(listings)}件")

            for asin in asins:
                product = self.master_db.get_product(asin)
                if product and product.get('amazon_price_jpy'):
                    price_map[asin] = {
                        'price_jpy': product['amazon_price_jpy'],
                        'in_stock': product.get('amazon_in_stock', False)
                    }
                    self.stats['cache_hits'] += 1
                else:
                    logger.debug(f"  [WARN] Master DBに価格情報なし: {asin}")

            logger.info(f"  完了: {len(price_map)}件の価格情報を取得（Master DB）")

        if not skip_cache_update:
            # ISSUE #005 & #006対応: キャッシュをスキップして、常に全件をSP-APIバッチで取得
            # ISSUE #006: レート制限を適切に設定（QuotaExceeded対策）
            logger.info(f"\n[重要] SP-APIバッチで最新価格・在庫を取得中...")
            logger.info(f"  対象商品数: {len(listings)}件")
            logger.info(f"  バッチサイズ: 20件/リクエスト")
            batch_count = (len(listings) + 19) // 20
            logger.info(f"  予想リクエスト数: {batch_count}回")
            # SP-APIレート: getItemOffersBatch = 0.1 req/sec (10秒/リクエスト) + 余裕2秒 = 12秒/リクエスト
            estimated_seconds = batch_count * 12
            logger.info(f"  予想処理時間: {estimated_seconds:.0f}秒 ({estimated_seconds/60:.1f}分)")
            logger.info(f"  使用API: getItemOffersBatch（安定版）")

            if not self.sp_api_available:
                logger.error("SP-APIクライアントが利用できません")
                self.stats['errors'] += 1
                return self.stats

            batch_start = time.time()
            try:
                # ISSUE #006: get_prices_batch を使用（既存の安定版API）
                batch_results = self.sp_api_client.get_prices_batch(asins, batch_size=20)
                batch_elapsed = time.time() - batch_start

                logger.info(f"  完了: {len(batch_results)}件の価格情報を取得（{batch_elapsed:.1f}秒）")
                self.stats['sp_api_calls'] = len(batch_results)

                # QuotaExceededエラーの発生回数を記録
                if hasattr(self.sp_api_client, 'quota_exceeded_count'):
                    quota_exceeded_count = self.sp_api_client.quota_exceeded_count
                    if quota_exceeded_count > 0:
                        logger.error(f"  [警告] QuotaExceededエラー: {quota_exceeded_count}回発生")
                        self.stats['quota_exceeded_count'] = quota_exceeded_count

                # 結果を処理（変動検知含む）
                for asin, price_info in batch_results.items():
                    # ISSUE #022対応: statusによる詳細な分類
                    status = price_info.get('status', 'unknown') if price_info else 'unknown'

                    if status == 'success':
                        # 成功
                        self.stats['price_fetch_success'] += 1

                        # 旧データを取得（変動検知用）
                        old_product = self.master_db.get_product(asin)
                        old_price = old_product.get('amazon_price_jpy') if old_product else None
                        old_stock = old_product.get('amazon_in_stock') if old_product else None

                        new_price = int(price_info['price'])
                        new_stock = price_info.get('in_stock', False)

                        # SP-API → Master DB（価格・在庫情報を更新）
                        self.master_db.update_amazon_info(
                            asin=asin,
                            price_jpy=new_price,
                            in_stock=new_stock
                        )

                        # price_mapに追加（後続の処理で使用）
                        price_map[asin] = {
                            'price_jpy': new_price,
                            'in_stock': new_stock
                        }

                        # 価格変動検知
                        if old_price and abs(new_price - old_price) >= 100:
                            self.stats['price_changes'].append({
                                'asin': asin,
                                'old': old_price,
                                'new': new_price,
                                'diff': new_price - old_price
                            })
                            logger.info(f"  [価格変動] {asin}: {old_price:,}円 → {new_price:,}円 ({new_price - old_price:+,}円)")

                        # 在庫変動検知
                        if old_stock is not None and old_stock != new_stock:
                            self.stats['stock_changes'].append({
                                'asin': asin,
                                'old': old_stock,
                                'new': new_stock
                            })
                            old_status = '在庫あり' if old_stock else '在庫切れ'
                            new_status = '在庫あり' if new_stock else '在庫切れ'
                            logger.info(f"  [在庫変動] {asin}: {old_status} → {new_status}")

                    elif status == 'api_error':
                        # APIエラー → フォールバック処理
                        self.stats['price_fetch_api_error'] += 1
                        error_msg = price_info.get('error_message', 'Unknown')
                        logger.warning(f"  [API_ERROR] {asin} - {error_msg}")

                        # Master DBからフォールバック
                        product = self.master_db.get_product(asin)
                        if product and product.get('amazon_price_jpy'):
                            fallback_price = product['amazon_price_jpy']
                            fallback_stock = product.get('amazon_in_stock', False)
                            logger.info(f"    → Master DBからフォールバック: {fallback_price:,}円")

                            # フォールバック成功
                            self.stats['price_fetch_fallback_success'] += 1
                            price_map[asin] = {
                                'price_jpy': fallback_price,
                                'in_stock': fallback_stock
                            }
                        else:
                            # フォールバック失敗
                            self.stats['price_fetch_fallback_failed'] += 1
                            logger.error(f"    → フォールバック失敗: Master DBにデータなし")

                    elif status == 'out_of_stock':
                        # 在庫切れ
                        self.stats['price_fetch_out_of_stock'] += 1
                        reason = price_info.get('failure_reason', 'unknown')
                        logger.debug(f"  [OUT_OF_STOCK] {asin} - {reason}")
                        # price_mapには追加しない（在庫同期で非公開化される）

                    elif status == 'filtered_out':
                        # フィルタリング条件不一致
                        self.stats['price_fetch_filtered_out'] += 1
                        logger.debug(f"  [FILTERED] {asin} - 条件を満たすオファーなし")
                        # price_mapには追加しない（取引対象外）

                    else:
                        # 不明なステータス
                        logger.warning(f"  [UNKNOWN] {asin} - status={status}")
                        self.stats['errors'] += 1

                # 比較情報を表示
                individual_estimated = len(asins) * 2.1
                if batch_elapsed > 0:
                    speedup = individual_estimated / batch_elapsed
                    logger.info(f"  効率化: 個別取得想定{individual_estimated:.1f}秒 → 実際{batch_elapsed:.1f}秒（{speedup:.1f}倍高速）")

            except Exception as e:
                logger.error(f"  エラー: バッチ価格取得失敗 - {e}")
                self.stats['sp_api_errors'] += 1
                self.stats['errors'] += 1
                return self.stats

        # ステップ3: 各出品の価格を更新
        logger.info(f"\nステップ3: 価格を更新中...")
        for listing in listings:
            # シャットダウン要求チェック
            global _shutdown_requested
            if _shutdown_requested:
                logger.info("シャットダウン要求を検出しました（出品ループ中断）")
                break

            asin = listing['asin']
            amazon_info = price_map.get(asin)

            if amazon_info:
                self._sync_listing_price_with_info(listing, base_client, amazon_info, dry_run)
                time.sleep(0.1)  # BASE APIのレート制限対策（5000req/h = 0.72秒/req、安全マージン含む）
            else:
                # price_mapにない = 在庫切れ/フィルタリング不一致/APIエラーでフォールバック失敗
                # 詳細は既にログに出力されているため、ここではカウントのみ
                self.stats['total_listings'] += 1
                logger.debug(f"  [SKIP] {asin} - 価格更新対象外（詳細は上記ログ参照）")

        return self.stats

    def _sync_listing_price_with_info(self, listing: dict, base_client: BaseAPIClient, amazon_info: dict, dry_run: bool):
        """
        1つの出品の価格を同期（価格情報を引数で受け取る）

        Args:
            listing: 出品情報
            base_client: BASE APIクライアント
            amazon_info: Amazon価格情報
            dry_run: Trueの場合、実際の更新は行わない
        """
        asin = listing['asin']
        listing_id = listing['id']
        platform_item_id = listing['platform_item_id']
        current_price = listing['selling_price']

        self.stats['total_listings'] += 1

        if not amazon_info or not amazon_info.get('price_jpy'):
            logger.info(f"  [SKIP] {asin} - 価格情報が取得できません")
            return

        amazon_price = amazon_info['price_jpy']

        # 販売価格を計算
        new_price = self.calculate_selling_price(amazon_price)

        # 価格差をチェック
        price_diff = abs(new_price - current_price)

        if price_diff < self.MIN_PRICE_DIFF:
            # 変更不要
            self.stats['no_update_needed'] += 1
            return

        # 変更が必要
        logger.info(f"  [UPDATE] {asin} | {current_price:,}円 -> {new_price:,}円 (差額: {price_diff:,}円)")
        logger.info(f"    Amazon価格: {amazon_price:,}円")

        if dry_run:
            logger.info(f"    → DRY RUN: 実際の更新はスキップ")
            self.stats['price_updated'] += 1
            return

        # BASE APIで更新
        try:
            base_client.update_item(
                item_id=platform_item_id,
                updates={'price': new_price}
            )

            # マスタDBも更新
            self.master_db.update_listing(
                listing_id=listing_id,
                selling_price=new_price
            )

            logger.info(f"    → 更新成功")
            self.stats['price_updated'] += 1

        except requests.exceptions.HTTPError as e:
            # HTTPエラーの詳細を解析
            status_code = e.response.status_code if e.response else None
            error_detail = {'asin': asin, 'listing_id': listing_id, 'status_code': status_code}

            # レスポンスボディを解析
            error_json = None
            if e.response:
                try:
                    error_json = e.response.json()
                    error_detail['error'] = error_json.get('error')
                    error_detail['error_description'] = error_json.get('error_description')
                except:
                    error_detail['error'] = str(e)

            # bad_item_idエラーの場合、自動delisted処理を実行
            if status_code == 400 and error_json and error_json.get('error') == 'bad_item_id':
                logger.error(f"    → BASE APIエラー: bad_item_id (商品が存在しません)")

                # 環境変数で無効化していない限り、自動delisted処理を実行（デフォルト: 有効）
                auto_delist_enabled = os.getenv('AUTO_DELIST_INVALID_ITEMS', 'true').lower() == 'true'

                if auto_delist_enabled:
                    self._handle_bad_item_id(listing, base_client, error_detail, dry_run)
                else:
                    logger.warning(f"    → 自動delisted処理は無効化されています（AUTO_DELIST_INVALID_ITEMS=false）")
                    self.stats['errors'] += 1
                    self.stats['errors_detail'].append(error_detail)
            else:
                # その他のHTTPエラー
                logger.error(f"    → 更新エラー: HTTP {status_code} - {error_detail.get('error', str(e))}")
                self.stats['errors'] += 1
                self.stats['errors_detail'].append(error_detail)

        except Exception as e:
            logger.error(f"    → 更新エラー: {e}")
            self.stats['errors'] += 1
            self.stats['errors_detail'].append({
                'asin': asin,
                'listing_id': listing_id,
                'error': str(e)
            })

    def _handle_bad_item_id(
        self,
        listing: dict,
        base_client: BaseAPIClient,
        error_detail: dict,
        dry_run: bool
    ):
        """
        bad_item_idエラーのハンドリング

        Args:
            listing: リスティング情報
            base_client: BASE APIクライアント
            error_detail: エラー詳細
            dry_run: DRY RUNモード
        """
        listing_id = listing['id']
        platform_item_id = listing['platform_item_id']

        logger.info(f"    [検証開始] 商品の存在確認を行います...")

        # ListingValidatorを使用して検証
        validator = ListingValidator(base_client, self.master_db)

        exists, reason = validator.verify_item_exists(
            platform_item_id=platform_item_id,
            listing=listing,
            use_cache=True
        )

        if not exists:
            # 商品が存在しない場合
            logger.error(f"    [確認] 商品がBASE側に存在しないことを確認しました")
            logger.error(f"    [自動delisted] Listing {listing_id} を非アクティブ化します")

            # auto_delisted処理
            if validator.auto_delist_listing(
                listing_id=listing_id,
                reason='bad_item_id',
                error_details=error_detail,
                dry_run=dry_run
            ):
                self.stats['auto_delisted_count'] += 1
                logger.info(f"    → 自動delisted成功")
            else:
                logger.error(f"    → 自動delisted失敗")
                self.stats['errors'] += 1
                self.stats['errors_detail'].append(error_detail)
        else:
            # 存在する、または検証エラー
            if reason:
                logger.error(f"    [検証エラー] 商品の存在確認に失敗しました: {reason}")
            else:
                logger.info(f"    [確認] 商品は存在します（一時的なエラーの可能性）")
            self.stats['errors'] += 1
            self.stats['errors_detail'].append(error_detail)

    def sync_all_accounts(self, dry_run: bool = False, parallel: bool = True, max_workers: int = 4, max_items: int = None, skip_cache_update: bool = False):
        """
        全アカウントの価格を同期（並列処理対応）

        Args:
            dry_run: Trueの場合、実際の更新は行わない
            parallel: 並列処理を有効にするか（デフォルト: True）
            max_workers: 並列処理の最大ワーカー数（デフォルト: 4）
            max_items: テスト用：処理する最大商品数（省略時は全件）
            skip_cache_update: Trueの場合、SP-API処理をスキップして既存キャッシュを使用（テスト用）
        """
        logger.info("\n" + "=" * 70)
        logger.info("価格同期処理を開始")
        logger.info("=" * 70)
        logger.info(f"掛け率: {self.markup_ratio}")
        logger.info(f"最小価格差: {self.MIN_PRICE_DIFF:,}円")
        logger.info(f"実行モード: {'DRY RUN（実際の更新なし）' if dry_run else '本番実行'}")
        logger.info(f"並列処理: {'有効' if parallel else '無効'} ({max_workers}ワーカー)" if parallel else "並列処理: 無効")
        logger.info(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # アクティブなアカウント取得
        accounts = self.account_manager.get_active_accounts()
        if not accounts:
            logger.error("エラー: アクティブなアカウントが見つかりません")
            return self.stats

        logger.info(f"アクティブアカウント数: {len(accounts)}件\n")

        if parallel and len(accounts) > 1:
            # 並列処理
            logger.info(f"並列処理モード: {min(len(accounts), max_workers)}アカウントを同時処理\n")

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 各アカウントの処理をサブミット
                future_to_account = {
                    executor.submit(self._sync_account_safe, account['id'], dry_run, max_items, skip_cache_update): account
                    for account in accounts
                }

                # 完了したものから処理
                for future in as_completed(future_to_account):
                    account = future_to_account[future]
                    account_id = account['id']

                    try:
                        future.result()
                        logger.info(f"[完了] アカウント {account_id} の処理完了\n")
                    except Exception as e:
                        logger.error(f"[エラー] アカウント {account_id} の処理中にエラー: {e}\n")
                        self.stats['errors'] += 1
                        self.stats['errors_detail'].append({
                            'account_id': account_id,
                            'error': str(e)
                        })
        else:
            # 順次処理（並列処理無効、または1アカウントのみ）
            if len(accounts) == 1:
                logger.info("アカウント数が1件のため、順次処理モード\n")
            else:
                logger.info("順次処理モード\n")

            for account in accounts:
                # シャットダウン要求チェック
                global _shutdown_requested
                if _shutdown_requested:
                    logger.info("シャットダウン要求を検出しました（アカウントループ中断）")
                    break

                account_id = account['id']

                try:
                    self.sync_account_prices(account_id, dry_run, max_items, skip_cache_update)
                except Exception as e:
                    logger.error(f"エラー: アカウント {account_id} の処理中にエラー: {e}")
                    self.stats['errors'] += 1
                    self.stats['errors_detail'].append({
                        'account_id': account_id,
                        'error': str(e)
                    })

        # 統計表示
        self._print_summary()

        return self.stats

    def _sync_account_safe(self, account_id: str, dry_run: bool, max_items: int = None, skip_cache_update: bool = False):
        """
        アカウントの価格同期（並列処理用のラッパー）

        Args:
            account_id: アカウントID
            dry_run: Trueの場合、実際の更新は行わない
            max_items: テスト用：処理する最大商品数（省略時は全件）
        """
        try:
            self.sync_account_prices(account_id, dry_run, max_items, skip_cache_update)
        except Exception as e:
            # エラーを再スローして、呼び出し元でキャッチできるようにする
            raise

    def _print_summary(self):
        """統計情報を表示"""
        logger.info("\n" + "=" * 70)
        logger.info("処理結果サマリー")
        logger.info("=" * 70)
        logger.info(f"処理した出品数: {self.stats['total_listings']}件")
        print()
        logger.info(f"Master DB参照:")
        logger.info(f"  - DBヒット: {self.stats['cache_hits']}件")
        logger.info(f"  - DBミス: {self.stats['cache_misses']}件")
        if self.stats['cache_hits'] + self.stats['cache_misses'] > 0:
            hit_rate = self.stats['cache_hits'] / (self.stats['cache_hits'] + self.stats['cache_misses']) * 100
            logger.info(f"  - ヒット率: {hit_rate:.1f}%")
        logger.info(f"  - SP-API呼び出し: {self.stats['sp_api_calls']}件")
        print()
        logger.error(f"SP-API エラー処理:")
        logger.error(f"  - SP-APIエラー発生: {self.stats['sp_api_errors']}件")
        logger.info(f"  - Master DBフォールバック成功: {self.stats['cache_fallback']}件")
        if self.stats['sp_api_errors'] > 0:
            fallback_rate = (self.stats['cache_fallback'] / self.stats['sp_api_errors']) * 100
            logger.info(f"  - フォールバック成功率: {fallback_rate:.1f}%")

        # QuotaExceededエラーの統計（ISSUE #006対応）
        if self.stats.get('quota_exceeded_count', 0) > 0:
            logger.error(f"  - QuotaExceededエラー: {self.stats['quota_exceeded_count']}件 ⚠️")
            logger.info(f"    → レート制限に違反している可能性があります")
            logger.info(f"    → 詳細はログを確認してください")
        print()
        logger.info(f"価格更新:")
        logger.info(f"  - 更新した商品: {self.stats['price_updated']}件")
        logger.info(f"  - 更新不要: {self.stats['no_update_needed']}件")
        print()

        # ISSUE #022対応: 価格取得の詳細分類
        logger.info(f"価格取得の詳細（ISSUE #022）:")
        logger.info(f"  - 成功: {self.stats['price_fetch_success']}件")
        logger.info(f"  - 在庫切れ: {self.stats['price_fetch_out_of_stock']}件")
        logger.info(f"  - フィルタリング不一致: {self.stats['price_fetch_filtered_out']}件")
        logger.info(f"  - APIエラー: {self.stats['price_fetch_api_error']}件")
        if self.stats['price_fetch_api_error'] > 0:
            logger.info(f"    - フォールバック成功: {self.stats['price_fetch_fallback_success']}件")
            logger.info(f"    - フォールバック失敗: {self.stats['price_fetch_fallback_failed']}件")
            if self.stats['price_fetch_api_error'] > 0:
                fallback_rate = (self.stats['price_fetch_fallback_success'] / self.stats['price_fetch_api_error']) * 100
                logger.info(f"    - フォールバック成功率: {fallback_rate:.1f}%")
        print()

        # ISSUE #005対応: 価格・在庫変動検知の統計
        logger.info(f"変動検知（ISSUE #005）:")
        logger.info(f"  - 価格変動検出: {len(self.stats['price_changes'])}件")
        if self.stats['price_changes']:
            logger.info(f"    変動詳細（最大10件）:")
            for change in self.stats['price_changes'][:10]:
                diff_sign = "+" if change['diff'] > 0 else ""
                logger.info(f"      {change['asin']}: {change['old']:,}円 → {change['new']:,}円 ({diff_sign}{change['diff']:,}円)")

        logger.info(f"  - 在庫状態変動検出: {len(self.stats['stock_changes'])}件")
        if self.stats['stock_changes']:
            logger.info(f"    変動詳細（最大10件）:")
            for change in self.stats['stock_changes'][:10]:
                old_status = "在庫あり" if change['old'] else "在庫なし"
                new_status = "在庫あり" if change['new'] else "在庫なし"
                logger.info(f"      {change['asin']}: {old_status} → {new_status}")
        print()

        # 自動delisted処理の統計
        if self.stats['auto_delisted_count'] > 0:
            logger.info(f"自動delisted処理:")
            logger.info(f"  - 自動delisted: {self.stats['auto_delisted_count']}件")
            logger.warning(f"    → 詳細: logs/auto_delisted.log を確認してください")
            print()

        logger.error(f"エラー: {self.stats['errors']}件")

        if self.stats['errors_detail']:
            logger.error("\nエラー詳細:")
            for error in self.stats['errors_detail'][:10]:  # 最大10件表示
                logger.error(f"  - {error}")

        # 重要な警告を表示
        if self.stats['sp_api_errors'] > 0:
            unrecovered = self.stats['sp_api_errors'] - self.stats['cache_fallback']
            if unrecovered > 0:
                print()
                logger.error(f"⚠ 警告: {unrecovered}件の商品でSP-APIエラーが発生し、Master DBデータも利用できませんでした。")

        logger.info("=" * 70)
        logger.info(f"終了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()


def main():
    """メイン処理"""
    import argparse

    # ログ設定（INFO以上を表示）
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    parser = argparse.ArgumentParser(
        description='キャッシュベースでBASE出品の価格を自動同期'
    )
    parser.add_argument(
        '--markup-ratio',
        type=float,
        default=1.3,
        help='掛け率（デフォルト: 1.3）'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='DRY RUNモード（実際の更新は行わない）'
    )
    parser.add_argument(
        '--account',
        help='特定のアカウントIDのみ処理（省略時は全アカウント）'
    )
    parser.add_argument(
        '--parallel',
        action='store_true',
        default=True,
        help='並列処理を有効にする（デフォルト: 有効）'
    )
    parser.add_argument(
        '--no-parallel',
        dest='parallel',
        action='store_false',
        help='並列処理を無効にする（逐次処理）'
    )
    parser.add_argument(
        '--max-workers',
        type=int,
        default=4,
        help='並列処理の最大ワーカー数（デフォルト: 4）'
    )
    parser.add_argument(
        '--max-items',
        type=int,
        default=None,
        help='テスト用：処理する最大商品数（省略時は全件）'
    )

    args = parser.parse_args()

    # 価格同期処理実行（スタンドアロン実行時はシグナルハンドラを登録）
    sync = PriceSync(markup_ratio=args.markup_ratio, register_signal_handler=True)

    if args.account:
        # 特定アカウントのみ
        stats = sync.sync_account_prices(
            account_id=args.account,
            dry_run=args.dry_run,
            max_items=args.max_items
        )
        sync._print_summary()
    else:
        # 全アカウント
        stats = sync.sync_all_accounts(
            dry_run=args.dry_run,
            parallel=args.parallel,
            max_workers=args.max_workers,
            max_items=args.max_items
        )

    # 終了コード
    if stats['errors'] > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
