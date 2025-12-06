"""
Upload Queue Manager

出品キューの管理を行うモジュール
"""

import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import random

# パスを追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from inventory.core.master_db import MasterDB
from platforms.base.accounts.manager import AccountManager


class UploadQueueManager:
    """
    出品キューマネージャー

    機能:
    - アイテムをキューに追加
    - アカウント自動割り当て
    - 時間スロット自動計算
    - 優先度管理
    """

    # ステータス定義
    STATUS_PENDING = 'pending'
    STATUS_SCHEDULED = 'scheduled'
    STATUS_UPLOADING = 'uploading'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_CANCELLED = 'cancelled'

    # 優先度定義
    PRIORITY_LOW = 1
    PRIORITY_NORMAL = 5
    PRIORITY_HIGH = 10
    PRIORITY_URGENT = 20

    def __init__(self, db_path: str = None):
        """
        Args:
            db_path: マスタDBのパス（デフォルトは標準パス）
        """
        self.db = MasterDB(db_path)
        self.account_manager = AccountManager()

    def add_to_queue(
        self,
        asin: str,
        platform: str,
        account_id: str = None,
        priority: int = PRIORITY_NORMAL,
        scheduled_at: datetime = None,
        metadata: Dict[str, Any] = None
    ) -> bool:
        """
        アイテムをキューに追加

        Args:
            asin: 商品ASIN
            platform: プラットフォーム名
            account_id: アカウントID（Noneの場合は自動割り当て）
            priority: 優先度（1-20）
            scheduled_at: アップロード予定時刻（Noneの場合は自動計算）
            metadata: メタデータ（JSON）

        Returns:
            bool: 成功時True
        """
        # アカウントの自動割り当て
        if not account_id:
            account_id = self._assign_account(platform)
            if not account_id:
                print(f"エラー: 利用可能なアカウントがありません（{platform}）")
                return False

        # scheduled_atが未指定の場合は現在時刻に設定（後でスケジューラが再計算）
        if not scheduled_at:
            scheduled_at = datetime.now()

        # キューに追加
        return self.db.add_to_upload_queue(
            asin=asin,
            platform=platform,
            account_id=account_id,
            priority=priority,
            scheduled_at=scheduled_at,
            metadata=metadata
        )

    def add_batch_to_queue(
        self,
        asins: List[str],
        platform: str,
        account_id: str = None,
        priority: int = PRIORITY_NORMAL,
        distribute_time: bool = True,
        auto_distribute_accounts: bool = False,
        start_time: datetime = None,
        hourly_limit: int = 100
    ) -> Dict[str, Any]:
        """
        複数アイテムを一括でキューに追加

        Args:
            asins: ASINのリスト
            platform: プラットフォーム名
            account_id: アカウントID（指定した場合はこのアカウントのみ使用）
            priority: 優先度
            distribute_time: 時間分散を行うか
            auto_distribute_accounts: 複数アカウントへ自動分散（account_idが指定されている場合は無視）
            start_time: 開始時刻（デフォルトは翌日6時）
            hourly_limit: 1時間あたりの最大アップロード件数（デフォルト: 100）

        Returns:
            dict: 実行結果
                - success: 成功件数
                - failed: 失敗件数
                - account_distribution: アカウント別件数
        """
        success_count = 0
        failed_count = 0
        account_distribution = {}

        # 開始時刻の設定（デフォルトは翌日6時）
        if not start_time:
            start_time = self._get_next_upload_start_time()

        # 既存のスケジュールをチェック（警告のため）
        existing_schedules = self._check_existing_schedules(
            platform=platform,
            start_time=start_time,
            account_id=account_id
        )

        if existing_schedules > 0:
            print(f"\n警告: 指定された時間帯に既に{existing_schedules}件のスケジュールがあります")
            print(f"  既存スケジュールと新規スケジュールが重複する可能性があります")
            print(f"  時間分散により自動調整されますが、1時間あたりの制限を超える可能性があります\n")

        # 時間スロットを計算
        if distribute_time:
            time_slots = self._calculate_time_slots(
                len(asins),
                start_time,
                hourly_limit=hourly_limit
            )
        else:
            time_slots = [start_time] * len(asins)

        # アカウントを割り当て
        if account_id:
            # 指定されたアカウントIDのみを使用
            account_assignments = [account_id] * len(asins)
        elif auto_distribute_accounts:
            # 複数アカウントへ自動分散
            account_assignments = self._assign_accounts_batch(platform, len(asins))
        else:
            # デフォルト: 最初のアクティブアカウントを使用
            account_assignments = self._assign_accounts_batch(platform, len(asins), single_account=True)

        # 各ASINをキューに追加
        for i, asin in enumerate(asins):
            assigned_account_id = account_assignments[i] if i < len(account_assignments) else None
            if not assigned_account_id:
                print(f"警告: ASIN {asin} のアカウント割り当てに失敗しました")
                failed_count += 1
                continue

            scheduled_at = time_slots[i]

            if self.add_to_queue(
                asin=asin,
                platform=platform,
                account_id=assigned_account_id,
                priority=priority,
                scheduled_at=scheduled_at
            ):
                success_count += 1
                account_distribution[assigned_account_id] = account_distribution.get(assigned_account_id, 0) + 1
            else:
                failed_count += 1

        return {
            'success': success_count,
            'failed': failed_count,
            'account_distribution': account_distribution,
            'start_time': start_time.isoformat(),
            'end_time': time_slots[-1].isoformat() if time_slots else None
        }

    def _assign_account(self, platform: str) -> Optional[str]:
        """
        単一アイテム用にアカウントを割り当て

        Args:
            platform: プラットフォーム名

        Returns:
            str or None: アカウントID
        """
        if platform != 'base':
            print(f"警告: プラットフォーム {platform} は未対応です")
            return None

        # アクティブなアカウントを取得
        active_accounts = self.account_manager.get_active_accounts()
        if not active_accounts:
            return None

        # 今日の各アカウントの使用状況を確認
        today = datetime.now().date()
        account_usage = {}

        for account in active_accounts:
            account_id = account['id']
            daily_limit = account.get('daily_upload_limit', 1000)

            # 今日のアップロード件数を取得
            uploaded_today = self.db.get_upload_count_by_account_and_date(
                account_id=account_id,
                date=today
            )

            remaining = daily_limit - uploaded_today
            account_usage[account_id] = {
                'limit': daily_limit,
                'used': uploaded_today,
                'remaining': remaining
            }

        # 空きがあるアカウントから選択（残り枠が多い順）
        available_accounts = [
            (acc_id, info['remaining'])
            for acc_id, info in account_usage.items()
            if info['remaining'] > 0
        ]

        if not available_accounts:
            return None

        # 残り枠が最も多いアカウントを選択
        available_accounts.sort(key=lambda x: x[1], reverse=True)
        return available_accounts[0][0]

    def _assign_accounts_batch(
        self,
        platform: str,
        count: int,
        single_account: bool = False
    ) -> List[str]:
        """
        バッチアイテム用にアカウントを割り当て

        Args:
            platform: プラットフォーム名
            count: アイテム数
            single_account: 単一アカウントのみを使用（デフォルト: False）

        Returns:
            list: アカウントIDのリスト
        """
        if platform != 'base':
            print(f"警告: プラットフォーム {platform} は未対応です")
            return []

        active_accounts = self.account_manager.get_active_accounts()
        if not active_accounts:
            return []

        # 今日の各アカウントの使用状況を確認
        today = datetime.now().date()

        if single_account:
            # 単一アカウントのみを使用（残り枠が最も多いアカウント）
            best_account_id = None
            max_remaining = 0

            for account in active_accounts:
                account_id = account['id']
                daily_limit = account.get('daily_upload_limit', 1000)

                uploaded_today = self.db.get_upload_count_by_account_and_date(
                    account_id=account_id,
                    date=today
                )

                remaining = daily_limit - uploaded_today

                if remaining > max_remaining:
                    max_remaining = remaining
                    best_account_id = account_id

            if not best_account_id:
                print(f"警告: 利用可能なアカウントがありません")
                return []

            if max_remaining < count:
                print(f"警告: 日次上限に対してアイテム数が多すぎます（必要: {count}、利用可能: {max_remaining}）")
                # 可能な範囲で割り当て
                return [best_account_id] * max_remaining

            return [best_account_id] * count

        else:
            # 複数アカウントへ自動分散
            account_pool = []

            for account in active_accounts:
                account_id = account['id']
                daily_limit = account.get('daily_upload_limit', 1000)

                uploaded_today = self.db.get_upload_count_by_account_and_date(
                    account_id=account_id,
                    date=today
                )

                remaining = daily_limit - uploaded_today

                # 空きがある場合、残り枠分だけプールに追加
                if remaining > 0:
                    account_pool.extend([account_id] * remaining)

            # プールが不足している場合は警告
            if len(account_pool) < count:
                print(f"警告: 日次上限に対してアイテム数が多すぎます（必要: {count}、利用可能: {len(account_pool)}）")
                # 不足分は利用可能な範囲で割り当て
                count = len(account_pool)

            # ランダムに割り当て（均等分散）
            random.shuffle(account_pool)
            return account_pool[:count]

    def _check_existing_schedules(
        self,
        platform: str,
        start_time: datetime,
        account_id: str = None
    ) -> int:
        """
        指定された時間帯に既存のスケジュールが何件あるかをチェック

        Args:
            platform: プラットフォーム名
            start_time: 開始時刻
            account_id: アカウントID（Noneの場合は全アカウント）

        Returns:
            int: 既存スケジュール件数
        """
        # 営業時間の終了時刻（start_timeから17時間後）
        end_time = start_time + timedelta(hours=17)

        # 既存のスケジュールを取得（scheduled または pending）
        existing_items = self.db.get_upload_queue(
            platform=platform,
            account_id=account_id,
            limit=10000  # 大きめの制限
        )

        # 指定時間帯内のアイテムをカウント
        count = 0
        for item in existing_items:
            scheduled_time = item.get('scheduled_time')
            if scheduled_time:
                if isinstance(scheduled_time, str):
                    scheduled_time = datetime.fromisoformat(scheduled_time)

                if start_time <= scheduled_time <= end_time:
                    count += 1

        return count

    def _get_next_upload_start_time(self) -> datetime:
        """
        次のアップロード開始時刻を取得（翌日6時）

        Returns:
            datetime: 開始時刻
        """
        now = datetime.now()
        next_day = now + timedelta(days=1)
        start_time = next_day.replace(hour=6, minute=0, second=0, microsecond=0)
        return start_time

    def _calculate_time_slots(
        self,
        count: int,
        start_time: datetime = None,
        hourly_limit: int = 100
    ) -> List[datetime]:
        """
        時間スロットを計算（1時間あたりの制限を考慮した効率的な分散）

        Args:
            count: アイテム数
            start_time: 開始時刻（デフォルトは翌日6時）
            hourly_limit: 1時間あたりの最大アップロード件数（デフォルト: 100）

        Returns:
            list: scheduled_at のリスト
        """
        if not start_time:
            start_time = self._get_next_upload_start_time()

        if count == 0:
            return []

        if count == 1:
            return [start_time]

        # 営業時間: 6AM-11PM = 17時間
        total_hours = 17

        # 必要な時間を計算（1時間あたりhourly_limit件まで）
        required_hours = (count + hourly_limit - 1) // hourly_limit  # 切り上げ

        # 17時間を超える場合は警告
        if required_hours > total_hours:
            print(f"警告: アイテム数が多すぎます（{count}件）。営業時間内に収まらない可能性があります")
            required_hours = total_hours

        # 1時間を均等に分割してアイテムを配置
        time_slots = []
        items_per_hour = min(hourly_limit, (count + required_hours - 1) // required_hours)

        for i in range(count):
            # どの時間帯に属するか
            hour_index = i // items_per_hour
            # その時間帯内での位置
            position_in_hour = i % items_per_hour

            # 時間帯内で均等に分散（1時間=60分）
            if items_per_hour > 1:
                interval_minutes = 60.0 / items_per_hour
                offset_minutes = int(hour_index * 60 + position_in_hour * interval_minutes)
            else:
                offset_minutes = hour_index * 60

            slot_time = start_time + timedelta(minutes=offset_minutes)
            time_slots.append(slot_time)

        return time_slots

    def get_pending_items(
        self,
        limit: int = 100,
        platform: str = None,
        account_id: str = None
    ) -> List[Dict[str, Any]]:
        """
        ペンディング中のアイテムを取得

        Args:
            limit: 取得件数
            platform: プラットフォーム名（フィルタ）
            account_id: アカウントID（フィルタ）

        Returns:
            list: キューアイテムのリスト
        """
        return self.db.get_upload_queue(
            status=self.STATUS_PENDING,
            limit=limit,
            platform=platform,
            account_id=account_id
        )

    def get_scheduled_items_due(
        self,
        limit: int = 100,
        platform: str = None,
        account_id: str = None
    ) -> List[Dict[str, Any]]:
        """
        scheduled_at が現在時刻を過ぎたアイテムを取得

        Args:
            limit: 取得件数
            platform: プラットフォーム名（フィルタ、オプション）
            account_id: アカウントID（フィルタ、オプション）

        Returns:
            list: キューアイテムのリスト
        """
        return self.db.get_upload_queue_due(limit=limit, platform=platform, account_id=account_id)

    def get_pending_items(
        self,
        limit: int = 100,
        platform: str = None,
        account_id: str = None
    ) -> List[Dict[str, Any]]:
        """
        scheduled_timeに関係なく、pending状態のアイテムを取得（強制実行用）

        Args:
            limit: 取得件数
            platform: プラットフォーム名（フィルタ）
            account_id: アカウントID（フィルタ、オプション）

        Returns:
            list: キューアイテムのリスト
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # クエリ構築
            query = """
                SELECT *
                FROM upload_queue
                WHERE status = 'pending'
            """
            params = []

            if platform:
                query += " AND platform = ?"
                params.append(platform)

            if account_id:
                query += " AND account_id = ?"
                params.append(account_id)

            query += " ORDER BY priority DESC, scheduled_time ASC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            # 辞書形式に変換
            items = []
            for row in rows:
                items.append(dict(row))

            return items

    def update_queue_status(
        self,
        queue_id: int,
        status: str,
        result_data: Dict[str, Any] = None,
        error_message: str = None
    ) -> bool:
        """
        キューアイテムのステータスを更新

        Args:
            queue_id: キューID
            status: 新しいステータス
            result_data: 結果データ（JSON）
            error_message: エラーメッセージ

        Returns:
            bool: 成功時True
        """
        return self.db.update_upload_queue_status(
            queue_id=queue_id,
            status=status,
            result_data=result_data,
            error_message=error_message
        )

    def get_queue_statistics(self, platform: str = None, account_id: str = None) -> Dict[str, Any]:
        """
        キューの統計情報を取得

        Args:
            platform: プラットフォーム名（フィルタ、オプション）
            account_id: アカウントID（フィルタ、オプション）

        Returns:
            dict: 統計情報
        """
        stats = {
            'pending': 0,
            'scheduled': 0,
            'uploading': 0,
            'success': 0,
            'failed': 0,
            'total': 0
        }

        for status in [self.STATUS_PENDING, self.STATUS_SCHEDULED,
                       self.STATUS_UPLOADING, self.STATUS_SUCCESS, self.STATUS_FAILED]:
            items = self.db.get_upload_queue(status=status, platform=platform, account_id=account_id, limit=10000)
            count = len(items)
            stats[status] = count
            stats['total'] += count

        return stats
