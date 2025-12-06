"""
アップロード実行スクリプト（ワンショット）

キュー内のアイテムを一括でアップロード
"""

import sys
from pathlib import Path

# パスを追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scheduler.upload_executor import UploadExecutor


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='キュー内のアイテムをアップロード実行'
    )
    parser.add_argument(
        '--platform',
        type=str,
        default='base',
        help='プラットフォーム名（デフォルト: base）'
    )
    parser.add_argument(
        '--account-id',
        type=str,
        default=None,
        help='アカウントID（--forceと併用時に特定アカウントのみ処理）'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=10,
        help='一度に処理するアイテム数（デフォルト: 10）'
    )
    parser.add_argument(
        '--rate-limit',
        type=float,
        default=2.0,
        help='API呼び出し間隔（秒、デフォルト: 2.0）'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='scheduled_timeを無視して強制実行（営業時間外でもテスト実行可能）'
    )

    args = parser.parse_args()

    print("=" * 60)
    print("アップロード実行")
    if args.force:
        print("（強制実行モード）")
    print("=" * 60)

    # UploadExecutorを初期化
    executor = UploadExecutor(
        rate_limit_seconds=args.rate_limit,
        max_retries=3
    )

    # アップロード実行
    print(f"\nプラットフォーム: {args.platform}")
    if args.account_id:
        print(f"アカウント: {args.account_id}")
    print(f"バッチサイズ: {args.batch_size}")
    print(f"レート制限: {args.rate_limit}秒")
    if args.force:
        print("モード: 強制実行（scheduled_time無視）")
    print()

    # 強制実行モードかどうかで処理を分岐
    if args.force:
        result = executor.process_pending_items(
            platform=args.platform,
            account_id=args.account_id,
            batch_size=args.batch_size
        )
    else:
        result = executor.process_due_items(
            platform=args.platform,
            batch_size=args.batch_size
        )

    # 結果を表示
    print("\n" + "=" * 60)
    print("実行結果")
    print("=" * 60)
    print(f"成功: {result.get('success', 0)}件")
    print(f"失敗: {result.get('failed', 0)}件")
    print(f"合計処理: {result.get('processed', 0)}件")
    print("=" * 60)


if __name__ == '__main__':
    main()
