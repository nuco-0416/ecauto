"""
BASE出品の妥当性検証モジュール

商品がBASE側に存在するか検証し、存在しない場合は自動的にdelistedステータスに変更する
"""

import logging
import json
from typing import Dict, Any, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class ListingValidator:
    """
    BASE出品の妥当性検証クラス

    機能:
    - BASE API側での商品存在確認
    - 自動delisted処理（複数段階の検証）
    - 復元可能な安全な実装
    """

    def __init__(self, base_client, master_db):
        """
        Args:
            base_client: BaseAPIClientインスタンス
            master_db: MasterDBインスタンス
        """
        self.base_client = base_client
        self.master_db = master_db
        self._item_cache = None  # BASE商品リストのキャッシュ

    def verify_item_exists(
        self,
        platform_item_id: str,
        listing: Dict[str, Any],
        use_cache: bool = True
    ) -> Tuple[bool, Optional[str]]:
        """
        BASE側で商品が存在するか検証（高速版：個別API呼び出し）

        Args:
            platform_item_id: BASE商品ID
            listing: リスティング情報（ASIN、SKUを含む）
            use_cache: キャッシュを使用するか（デフォルト: True）

        Returns:
            tuple: (存在するか, エラーメッセージ)
                - (True, None): 存在する
                - (False, "reason"): 存在しない（理由）
        """
        import requests

        try:
            # 個別APIで存在確認（直接API呼び出し）
            logger.info(f"  [検証] item_id={platform_item_id} の存在確認中...")

            # BASE APIに直接リクエスト
            url = f"{self.base_client.BASE_URL}/items/detail"
            params = {'item_id': str(platform_item_id)}

            # GETリクエスト用のヘッダー（Content-Typeを除外）
            headers = {'Authorization': self.base_client.headers['Authorization']}

            try:
                response = requests.get(
                    url,
                    headers=headers,
                    params=params,
                    timeout=30
                )
                response.raise_for_status()

                # 成功：商品が存在する
                item = response.json()
                if item:
                    logger.info(f"  [検証] ✓ item_id={platform_item_id} は存在します")
                    return True, None

            except requests.exceptions.HTTPError as e:
                # HTTPエラーの詳細を確認
                if e.response is None:
                    logger.error(f"  [検証] HTTPError (response is None): {e}")
                    return True, f"api_error:no_response"

                status_code = e.response.status_code
                logger.warning(f"  [検証] HTTPError発生: status_code={status_code}")

                if status_code == 404:
                    # 404エラー = 商品が存在しない
                    logger.warning(f"  [検証] item_id={platform_item_id} は存在しません（404）")
                    return False, "item_not_found_in_base"

                elif status_code == 400:
                    # 400エラー：エラー詳細を確認
                    try:
                        error_json = e.response.json()
                        error_type = error_json.get('error')
                        logger.warning(f"  [検証] 400エラーレスポンス: {json.dumps(error_json, ensure_ascii=False)}")

                        # bad_item_id または no_item_id = 商品が存在しない
                        if error_type in ('bad_item_id', 'no_item_id'):
                            logger.warning(f"  [検証] item_id={platform_item_id} は存在しません（{error_type}）")
                            return False, error_type
                        else:
                            # その他の400エラー
                            logger.error(f"  [検証] その他の400エラー: {error_type}")
                            return True, f"api_error:400_{error_type}"
                    except Exception as ex:
                        logger.error(f"  [検証] エラーレスポンスのパースに失敗: {ex}")
                        return True, f"api_error:400_parse_error"

                else:
                    # その他のHTTPエラー
                    logger.error(f"  [検証] APIエラー: status_code={status_code}")
                    return True, f"api_error:{status_code}"

            # 存在しない（レスポンスがNone）
            return False, "item_not_found_in_base"

        except Exception as e:
            logger.error(f"  [検証] エラー: {e}", exc_info=True)
            # 検証エラーの場合は、安全のため「存在する」と判定
            return True, f"verification_error:{str(e)}"

    def _fetch_all_items(self) -> Dict[str, Any]:
        """
        BASE APIから全商品を取得してキャッシュ

        Returns:
            dict: {
                'item_map': {item_id: item},
                'identifier_map': {identifier: item}
            }
        """
        items = self.base_client.get_all_items()

        item_map = {str(item['item_id']): item for item in items}
        identifier_map = {}

        for item in items:
            identifier = item.get('identifier', '').strip()
            if identifier:
                identifier_map[identifier] = item

        logger.info(f"  [検証] BASE商品: {len(item_map)}件取得")

        return {
            'item_map': item_map,
            'identifier_map': identifier_map
        }

    def auto_delist_listing(
        self,
        listing_id: int,
        reason: str,
        error_details: Optional[Dict[str, Any]] = None,
        dry_run: bool = False
    ) -> bool:
        """
        出品を自動的にdelistedステータスに変更

        Args:
            listing_id: リスティングID
            reason: 理由（"bad_item_id"など）
            error_details: エラー詳細
            dry_run: DRY RUNモード

        Returns:
            bool: 成功時True
        """
        try:
            # 自動delisted記録を作成
            auto_delisted_info = {
                'auto_delisted': True,
                'reason': reason,
                'timestamp': datetime.now().isoformat(),
                'error_details': error_details or {}
            }

            # ログ出力
            logger.warning(f"  [自動delisted] Listing {listing_id} を非アクティブ化します")
            logger.warning(f"    理由: {reason}")
            logger.warning(f"    詳細: {json.dumps(error_details, ensure_ascii=False)}")

            if dry_run:
                logger.warning(f"    [DRY RUN] 実際の変更はスキップ")
                return True

            # データベースを更新
            # ISSUE: ListingsテーブルにJSON型のカラムがない場合は、
            # 別途metadata列を追加するか、ログのみで対応
            with self.master_db.get_connection() as conn:
                # statusをdelistedに変更
                conn.execute("""
                    UPDATE Listings
                    SET status = 'delisted',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (listing_id,))

            logger.warning(f"    ✓ Listing {listing_id} を delisted に変更しました")

            # 統計情報を記録（別途ログファイルに保存）
            self._log_auto_delisted(listing_id, auto_delisted_info)

            return True

        except Exception as e:
            logger.error(f"  [自動delisted] エラー: {e}", exc_info=True)
            return False

    def _log_auto_delisted(self, listing_id: int, info: Dict[str, Any]):
        """
        自動delisted情報をログファイルに記録

        Args:
            listing_id: リスティングID
            info: 自動delisted情報
        """
        from pathlib import Path

        # ログディレクトリ
        log_dir = Path(__file__).resolve().parent.parent.parent.parent / 'logs'
        log_dir.mkdir(exist_ok=True)

        # auto_delisted.logに追記
        log_file = log_dir / 'auto_delisted.log'

        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                log_entry = {
                    'listing_id': listing_id,
                    **info
                }
                f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
        except Exception as e:
            logger.error(f"  [自動delisted] ログ記録エラー: {e}")

    def update_item_id(self, listing_id: int, new_item_id: str, dry_run: bool = False) -> bool:
        """
        item_idを更新

        Args:
            listing_id: リスティングID
            new_item_id: 新しいitem_id
            dry_run: DRY RUNモード

        Returns:
            bool: 成功時True
        """
        try:
            logger.warning(f"  [item_id更新] Listing {listing_id} のitem_idを更新します")
            logger.warning(f"    新しいitem_id: {new_item_id}")

            if dry_run:
                logger.warning(f"    [DRY RUN] 実際の変更はスキップ")
                return True

            self.master_db.update_listing(
                listing_id=listing_id,
                platform_item_id=new_item_id
            )

            logger.warning(f"    ✓ item_idを更新しました")
            return True

        except Exception as e:
            logger.error(f"  [item_id更新] エラー: {e}", exc_info=True)
            return False
