#!/usr/bin/env python
"""
Blastmail 配信履歴取得スクリプト（マルチアカウント対応・自動認証）

Blastmail APIを使用して配信履歴を取得し、表示またはファイル出力する
トークンは認証情報から自動取得され、期限切れ時も自動更新される

使用例:
    # アカウント一覧を表示
    venv/bin/python marketing/service_blastmail/scripts/get_delivery_history.py --list-accounts

    # 特定アカウントの最新10件を表示
    venv/bin/python marketing/service_blastmail/scripts/get_delivery_history.py \
        --account blastmail_account_1 --limit 10

    # 全アカウントの配信履歴を取得
    venv/bin/python marketing/service_blastmail/scripts/get_delivery_history.py --all-accounts

    # 日付範囲を指定して取得
    venv/bin/python marketing/service_blastmail/scripts/get_delivery_history.py \
        --account blastmail_account_1 \
        --begin-date 2025-12-01 --end-date 2025-12-09

    # JSON形式でファイル出力
    venv/bin/python marketing/service_blastmail/scripts/get_delivery_history.py \
        --account blastmail_account_1 \
        --output data/history.json --format json
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from marketing.service_blastmail.core.api_client import BlastmailAPIClient
from marketing.service_blastmail.accounts.manager import AccountManager


def setup_logging(debug: bool = False) -> logging.Logger:
    """ロギング設定"""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    return logging.getLogger(__name__)


def format_history_item(item: dict, account_name: str = None) -> str:
    """配信履歴アイテムを整形して表示用文字列に変換"""
    lines = [f"{'=' * 60}"]
    if account_name:
        lines.append(f"アカウント: {account_name}")
    lines.extend([
        f"メッセージID: {item.get('messageID', 'N/A')}",
        f"件名: {item.get('subject', 'N/A')}",
        f"配信日時: {item.get('date', 'N/A')}",
        f"配信状態: {item.get('status', 'N/A')}",
        f"宛先グループ: {item.get('group', 'N/A')}",
        f"宛先数: {item.get('total', 'N/A')}",
        f"成功数: {item.get('success', 'N/A')}",
        f"失敗数: {item.get('failure', 'N/A')}",
    ])
    return '\n'.join(lines)


def get_clients(
    account_manager: AccountManager,
    account_id: Optional[str] = None,
    all_accounts: bool = False,
    logger: logging.Logger = None
) -> List[BlastmailAPIClient]:
    """
    指定条件に基づいてAPIクライアントを取得

    Args:
        account_manager: AccountManagerインスタンス
        account_id: 特定アカウントID（指定時はそのアカウントのみ）
        all_accounts: True時は全アクティブアカウント
        logger: ロガー

    Returns:
        list: BlastmailAPIClientのリスト
    """
    clients = []

    if all_accounts:
        # 全アクティブアカウント
        clients = account_manager.create_all_clients(active_only=True)
        if not clients and logger:
            logger.error("有効なアカウントが見つかりません")

    elif account_id:
        # 特定アカウント
        try:
            client = account_manager.create_client(account_id)
            clients.append(client)
        except ValueError as e:
            if logger:
                logger.error(str(e))

    else:
        # アカウント指定なし: 最初のアクティブアカウントを使用
        active_accounts = account_manager.get_active_accounts()
        if active_accounts:
            try:
                client = account_manager.create_client(active_accounts[0]['id'])
                clients.append(client)
                if logger:
                    logger.info(f"アカウント '{active_accounts[0]['id']}' を使用")
            except ValueError as e:
                if logger:
                    logger.error(str(e))

    return clients


def main():
    parser = argparse.ArgumentParser(
        description='Blastmail 配信履歴取得（マルチアカウント対応・自動認証）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  %(prog)s --list-accounts                      # アカウント一覧を表示
  %(prog)s --account blastmail_account_1 -n 10  # 特定アカウントの最新10件
  %(prog)s --all-accounts                       # 全アカウントの履歴を取得
  %(prog)s --begin-date 2025-12-01              # 12/1以降の履歴を取得
        """
    )

    # アカウント選択オプション
    account_group = parser.add_argument_group('アカウント選択')
    account_group.add_argument(
        '--account', '-a',
        type=str,
        help='アカウントID（例: blastmail_account_1）'
    )
    account_group.add_argument(
        '--all-accounts',
        action='store_true',
        help='全アクティブアカウントの履歴を取得'
    )
    account_group.add_argument(
        '--list-accounts',
        action='store_true',
        help='登録アカウント一覧を表示'
    )

    # 取得オプション
    parser.add_argument(
        '--limit', '-n',
        type=int,
        default=25,
        help='取得件数制限（デフォルト: 25）'
    )
    parser.add_argument(
        '--offset',
        type=int,
        default=0,
        help='取得開始位置（デフォルト: 0）'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='全件取得（ページネーション自動処理）'
    )

    # フィルタオプション
    parser.add_argument(
        '--begin-date',
        type=str,
        help='配信開始日時（YYYY-MM-DD または YYYY-MM-DDTHH:MM:SS）'
    )
    parser.add_argument(
        '--end-date',
        type=str,
        help='配信終了日時（YYYY-MM-DD または YYYY-MM-DDTHH:MM:SS）'
    )
    parser.add_argument(
        '--message-id',
        type=str,
        help='特定のメッセージIDを指定'
    )

    # 詳細取得オプション
    parser.add_argument(
        '--detail',
        action='store_true',
        help='メッセージ詳細を取得（--message-idと併用）'
    )
    parser.add_argument(
        '--export-success',
        action='store_true',
        help='成功アドレスをCSVエクスポート（--message-idと併用）'
    )
    parser.add_argument(
        '--export-failure',
        action='store_true',
        help='失敗アドレスをCSVエクスポート（--message-idと併用）'
    )
    parser.add_argument(
        '--export-open-log',
        action='store_true',
        help='開封ログをCSVエクスポート（--message-idと併用）'
    )

    # 出力オプション
    parser.add_argument(
        '--output', '-o',
        type=str,
        help='出力ファイルパス（指定しない場合は標準出力）'
    )
    parser.add_argument(
        '--format', '-f',
        type=str,
        choices=['text', 'json'],
        default='text',
        help='出力形式（デフォルト: text）'
    )

    # その他オプション
    parser.add_argument(
        '--debug',
        action='store_true',
        help='デバッグモード'
    )

    args = parser.parse_args()
    logger = setup_logging(args.debug)

    try:
        # AccountManager初期化
        account_manager = AccountManager()

        # アカウント一覧表示
        if args.list_accounts:
            account_manager.list_accounts()
            return 0

        # 日付パース
        begin_date = None
        end_date = None
        if args.begin_date:
            try:
                begin_date = datetime.fromisoformat(args.begin_date)
            except ValueError:
                begin_date = datetime.strptime(args.begin_date, '%Y-%m-%d')
        if args.end_date:
            try:
                end_date = datetime.fromisoformat(args.end_date)
            except ValueError:
                end_date = datetime.strptime(args.end_date, '%Y-%m-%d')

        # クライアント取得（自動認証）
        clients = get_clients(
            account_manager,
            account_id=args.account,
            all_accounts=args.all_accounts,
            logger=logger
        )

        if not clients:
            logger.error(
                "APIクライアントを初期化できませんでした。\n"
                "以下を確認してください:\n"
                "1. config/account_config.json にアカウント情報を設定\n"
                "2. 認証情報（username, password, api_key）が正しいこと"
            )
            return 1

        # 結果収集
        all_results = []

        for client in clients:
            account_label = client.account_name or client.account_id or "default"
            logger.info(f"アカウント '{account_label}' の配信履歴を取得中...")

            result = None

            try:
                # 特定メッセージIDの処理
                if args.message_id:
                    if args.detail:
                        result = client.get_message_detail(args.message_id)
                    elif args.export_success:
                        result = client.export_delivery_addresses(args.message_id, status=0)
                    elif args.export_failure:
                        result = client.export_delivery_addresses(args.message_id, status=1)
                    elif args.export_open_log:
                        result = client.export_open_log(args.message_id)
                    else:
                        result = client.get_message_detail(args.message_id)
                else:
                    # 配信履歴検索
                    if args.all:
                        items = client.get_all_delivery_history(
                            begin_date=begin_date,
                            end_date=end_date
                        )
                        result = {'items': items, 'total': len(items)}
                    else:
                        result = client.search_delivery_history(
                            offset=args.offset,
                            limit=args.limit,
                            begin_date=begin_date,
                            end_date=end_date
                        )

                if result:
                    all_results.append({
                        'account_id': client.account_id,
                        'account_name': account_label,
                        'data': result
                    })

            except Exception as e:
                logger.error(f"アカウント '{account_label}' でエラー: {e}")
                if args.debug:
                    raise

        # 結果出力
        if not all_results:
            logger.warning("取得結果がありません")
            return 1

        # CSV形式の場合はそのまま出力
        if isinstance(all_results[0]['data'], str):
            output_text = all_results[0]['data']
        elif args.format == 'json':
            if len(all_results) == 1:
                output_data = all_results[0]['data']
            else:
                output_data = all_results
            output_text = json.dumps(output_data, ensure_ascii=False, indent=2)
        else:
            # テキスト形式
            lines = []
            for result in all_results:
                account_name = result['account_name']
                data = result['data']
                # APIレスポンスは 'message' キーを使用
                items = data.get('message', data.get('items', []))

                if len(all_results) > 1:
                    lines.append(f"\n{'#' * 60}")
                    lines.append(f"# アカウント: {account_name}")
                    lines.append(f"{'#' * 60}")

                if not items:
                    lines.append("配信履歴が見つかりませんでした")
                else:
                    lines.append(f"配信履歴: {len(items)} 件\n")
                    for item in items:
                        lines.append(format_history_item(item, account_name if len(all_results) > 1 else None))
                        lines.append("")  # 空行を追加

            output_text = '\n'.join(lines)

        # ファイル出力または標準出力
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(output_text)
            logger.info(f"出力完了: {output_path}")
        else:
            print(output_text)

        return 0

    except ValueError as e:
        logger.error(str(e))
        return 1
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}", exc_info=args.debug)
        return 1


if __name__ == '__main__':
    sys.exit(main())
