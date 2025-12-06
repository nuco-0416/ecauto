"""
マルチプラットフォーム対応アップロードデーモン

プラットフォームごとに独立したサービスとして起動
DaemonBaseを継承し、通知機能・エラーリトライ・ログローテーションを統合
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
import time

# パスを追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scheduled_tasks.daemon_base import DaemonBase
from scheduler.platform_uploaders.uploader_factory import UploaderFactory
from scheduler.queue_manager import UploadQueueManager
from inventory.core.master_db import MasterDB


class UploadSchedulerDaemon(DaemonBase):
    """
    マルチプラットフォーム対応アップロードスケジューラー

    特徴:
    - プラットフォーム別に独立して起動可能（BASE、eBay、Yahoo!等）
    - DaemonBase継承による堅牢性
    - Chatwork通知統合
    - エラーリトライ機能
    - 構造化ログ
    - 営業時間管理
    """

    def __init__(
        self,
        platform: str,
        interval_seconds: int = 60,
        batch_size: int = 10,
        business_hours_start: int = 6,
        business_hours_end: int = 23
    ):
        """
        Args:
            platform: プラットフォーム名（'base', 'ebay', 'yahoo'）
            interval_seconds: チェック間隔（秒）
            batch_size: 1回の処理件数
            business_hours_start: 営業開始時刻（時）
            business_hours_end: 営業終了時刻（時）
        """
        # プラットフォーム対応チェック
        supported = UploaderFactory.get_supported_platforms()
        if platform not in supported:
            raise ValueError(
                f"未対応のプラットフォーム: {platform}\n"
                f"対応プラットフォーム: {supported}"
            )

        # DaemonBase初期化
        super().__init__(
            name=f'upload_scheduler_{platform}',  # プラットフォーム別ログ
            interval_seconds=interval_seconds,
            max_retries=3,
            retry_delay_seconds=60,
            enable_notifications=True
        )

        self.platform = platform
        self.batch_size = batch_size
        self.business_hours_start = business_hours_start
        self.business_hours_end = business_hours_end

        self.queue_manager = UploadQueueManager()
        self.db = MasterDB()

        # AccountManagerを作成（UploaderFactory用）
        from platforms.base.accounts.manager import AccountManager
        self.account_manager = AccountManager()

        self.logger.info(f"プラットフォーム: {platform}")
        self.logger.info(f"営業時間: {business_hours_start}:00 - {business_hours_end}:00")
        self.logger.info(f"バッチサイズ: {batch_size}")

    def _is_business_hours(self) -> bool:
        """営業時間内かチェック"""
        now = datetime.now()
        current_hour = now.hour
        return self.business_hours_start <= current_hour < self.business_hours_end

    def execute_task(self) -> bool:
        """
        定期実行タスク（DaemonBaseから継承）

        Returns:
            bool: 成功時True、失敗時False
        """
        try:
            # 営業時間外はスキップ
            if not self._is_business_hours():
                self.logger.debug(
                    f"営業時間外のためスキップ（営業時間: "
                    f"{self.business_hours_start}:00-{self.business_hours_end}:00）"
                )
                return True

            # キュー統計を取得
            stats = self.queue_manager.get_queue_statistics(
                platform=self.platform
            )

            pending_count = stats.get('pending', 0)

            if pending_count == 0:
                self.logger.debug("処理対象のアイテムがありません")
                return True

            self.logger.info(
                f"処理開始: pending={pending_count}, "
                f"success={stats.get('success', 0)}, "
                f"failed={stats.get('failed', 0)}"
            )

            # バッチ処理
            success_count = 0
            failed_count = 0
            processed_count = 0

            # 実行可能なアイテムを取得
            items = self.queue_manager.get_scheduled_items_due(
                limit=self.batch_size,
                platform=self.platform
            )

            for item in items:
                try:
                    result = self._upload_single_item(item)
                    processed_count += 1

                    if result['status'] == 'success':
                        success_count += 1
                    else:
                        failed_count += 1

                except Exception as e:
                    failed_count += 1
                    processed_count += 1
                    self.logger.error(
                        f"アイテムアップロード失敗: "
                        f"ASIN={item.get('asin')}, "
                        f"Error={e}",
                        exc_info=True
                    )

            self.logger.info(
                f"バッチ完了: 成功={success_count}, 失敗={failed_count}"
            )

            # 完了レポートを送信（処理した件数が0より大きい場合）
            if processed_count > 0:
                self._send_completion_notification(
                    processed_count=processed_count,
                    success_count=success_count,
                    failed_count=failed_count,
                    remaining_count=pending_count - processed_count
                )

            # 失敗率が高い場合は警告通知
            if failed_count > 0 and failed_count > success_count:
                if self.notifier:
                    self.notifier.notify(
                        event_type='task_failure',
                        title=f"⚠️ {self.platform.upper()} アップロード失敗率が高い",
                        message=(
                            f"成功: {success_count}件\n"
                            f"失敗: {failed_count}件\n\n"
                            f"ログを確認してください"
                        ),
                        level="WARNING"
                    )

            return True

        except Exception as e:
            self.logger.error(f"タスク実行エラー: {e}", exc_info=True)
            return False

    def _send_completion_notification(
        self,
        processed_count: int,
        success_count: int,
        failed_count: int,
        remaining_count: int
    ):
        """
        完了通知を送信

        Args:
            processed_count: 処理件数
            success_count: 成功件数
            failed_count: 失敗件数
            remaining_count: 残り件数
        """
        report_stats = {
            '処理件数': processed_count,
            '登録成功': success_count,
            '登録失敗': failed_count,
            '残り件数': remaining_count,
        }

        # 完了レポートを送信
        self.send_completion_report(
            task_name=f'{self.platform.upper()} 商品出品',
            stats=report_stats
        )

    def _upload_single_item(self, queue_item: Dict[str, Any]) -> Dict[str, Any]:
        """
        単一アイテムをアップロード

        Args:
            queue_item: キューアイテム

        Returns:
            dict: {'status': 'success'|'failed', 'message': str}
        """
        queue_id = queue_item['id']
        asin = queue_item['asin']
        account_id = queue_item['account_id']

        self.logger.info(
            f"アップロード開始: ASIN={asin}, Account={account_id}"
        )

        # ステータスを「処理中」に更新
        self.queue_manager.update_queue_status(queue_id, 'uploading')

        try:
            # プラットフォーム別アップローダーを取得
            uploader = UploaderFactory.create(
                platform=self.platform,
                account_id=account_id,
                account_manager=self.account_manager
            )

            # 商品情報を取得
            product = self.db.get_product(asin)
            if not product:
                raise ValueError(f"商品情報が見つかりません: {asin}")

            # 出品情報を取得（ASINとアカウントIDから探す）
            listings = self.db.get_listings_by_asin(asin)
            listing = next((l for l in listings if l['account_id'] == account_id and l['platform'] == self.platform), None)
            if not listing:
                raise ValueError(f"出品情報が見つかりません: {asin}, account={account_id}")

            # 画像URLをパース（JSON文字列の場合）
            import json
            images = product.get('images', [])
            if isinstance(images, str):
                try:
                    images = json.loads(images)
                except (json.JSONDecodeError, TypeError):
                    images = []

            # アイテムデータを準備
            item_data = {
                'asin': asin,
                'sku': listing.get('sku', ''),
                'title': product.get('title_ja') or product.get('title_en'),
                'description': product.get('description_ja') or product.get('description_en'),
                'price': listing.get('selling_price'),
                'stock': listing.get('in_stock_quantity', 1),
                'images': images,
                'account_id': account_id
            }

            # バリデーション
            is_valid, error_msg = uploader.validate_item(item_data)
            if not is_valid:
                raise ValueError(f"バリデーションエラー: {error_msg}")

            # 重複チェック
            if uploader.check_duplicate(asin, item_data['sku']):
                self.logger.warning(f"重複検出: {asin} - スキップします")
                self.queue_manager.update_queue_status(
                    queue_id=queue_id,
                    status='failed',
                    error_message='重複商品'
                )
                return {'status': 'failed', 'message': '重複商品'}

            # アップロード実行
            result = uploader.upload_item(item_data)

            if result['status'] == 'success':
                platform_item_id = result.get('platform_item_id')
                self.logger.info(f"アップロード成功: Item ID={platform_item_id}")

                # 画像アップロード
                if item_data.get('images'):
                    img_result = uploader.upload_images(
                        platform_item_id,
                        item_data['images']
                    )
                    self.logger.info(
                        f"画像アップロード: {img_result.get('uploaded_count', 0)}件"
                    )

                # ステータスを「成功」に更新
                self.queue_manager.update_queue_status(
                    queue_id=queue_id,
                    status='success',
                    result_data={'platform_item_id': platform_item_id}
                )

                return {'status': 'success', 'message': '成功'}

            else:
                # アップロード失敗
                error_message = result.get('message', '不明なエラー')
                self.logger.error(f"アップロード失敗: {error_message}")

                self.queue_manager.update_queue_status(
                    queue_id=queue_id,
                    status='failed',
                    error_message=error_message
                )

                return {'status': 'failed', 'message': error_message}

        except Exception as e:
            error_message = str(e)
            self.logger.error(f"例外発生: {error_message}", exc_info=True)

            self.queue_manager.update_queue_status(
                queue_id=queue_id,
                status='failed',
                error_message=error_message
            )

            return {'status': 'failed', 'message': error_message}


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description='マルチプラットフォーム対応アップロードスケジューラー'
    )
    parser.add_argument(
        '--platform',
        required=True,
        choices=UploaderFactory.get_supported_platforms(),
        help='プラットフォーム名'
    )
    parser.add_argument(
        '--interval',
        type=int,
        default=60,
        help='チェック間隔（秒）'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=10,
        help='1回の処理件数'
    )
    parser.add_argument(
        '--start-hour',
        type=int,
        default=6,
        help='営業開始時刻（時）'
    )
    parser.add_argument(
        '--end-hour',
        type=int,
        default=23,
        help='営業終了時刻（時）'
    )

    args = parser.parse_args()

    daemon = UploadSchedulerDaemon(
        platform=args.platform,
        interval_seconds=args.interval,
        batch_size=args.batch_size,
        business_hours_start=args.start_hour,
        business_hours_end=args.end_hour
    )

    daemon.run()
