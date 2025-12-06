"""
マルチアカウント・マルチプラットフォームアップロード構成

platforms/base/accounts/account_config.json から動的に読み込み、
activeフラグを尊重します

【改修履歴】
- 2025-12-01: 動的読み込み実装（account_config.json を信頼できる唯一の情報源とする）
"""

import json
from pathlib import Path
import sys

# プロジェクトルート
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _load_active_accounts_from_json():
    """
    platforms/base/accounts/account_config.json から
    アクティブなアカウントのみを読み込む

    Returns:
        dict: {'base': ['account_id', ...], 'ebay': [...], ...}
    """
    accounts = {'base': []}

    try:
        config_path = PROJECT_ROOT / 'platforms' / 'base' / 'accounts' / 'account_config.json'

        if not config_path.exists():
            print(f"警告: account_config.json が見つかりません: {config_path}", file=sys.stderr)
            raise FileNotFoundError(f"account_config.json not found: {config_path}")

        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

            for account in config.get('accounts', []):
                account_id = account.get('id')
                is_active = account.get('active', False)

                # activeフラグがTrueのものだけ追加
                if is_active and account_id:
                    accounts['base'].append(account_id)

        print(f"[INFO] アクティブなBASEアカウント: {accounts['base']}", file=sys.stderr)

    except Exception as e:
        print(f"警告: account_config.json の読み込みに失敗しました: {e}", file=sys.stderr)
        print("フォールバック: デフォルトのアカウントリストを使用します", file=sys.stderr)

        # フォールバック（既存の動作を維持）
        accounts['base'] = [
            'base_account_1',
            'base_account_2',
        ]

    # 将来の拡張用プレースホルダー
    # accounts['ebay'] = []
    # accounts['yahoo'] = []

    return accounts


# アカウント構成（動的に読み込み）
# 注意: この変数はモジュールロード時に一度だけ評価されます
# 設定ファイルを変更した場合は、デーモンプロセスの再起動が必要です
UPLOAD_ACCOUNTS = _load_active_accounts_from_json()

# デーモン設定（全アカウント共通）
DAEMON_CONFIG = {
    'interval_seconds': 60,  # チェック間隔（秒）- 高速化のため240→60に変更
    'batch_size': 20,  # 1回の処理件数 - 高速化のため1→20に変更
    'business_hours_start': 0,  # 営業開始時刻（時）- 0時から
    'business_hours_end': 24,  # 営業終了時刻（時）- 24時まで（24時間稼働）
}

# アカウント別の個別設定（オプション）
# 特定のアカウントで設定を上書きしたい場合に使用
ACCOUNT_SPECIFIC_CONFIG = {
    # 例: account_1は処理速度を上げる
    # 'base_account_1': {
    #     'batch_size': 15,
    # },
    # 例: account_2は営業時間を制限
    # 'base_account_2': {
    #     'business_hours_start': 9,
    #     'business_hours_end': 18,
    # },
}


def get_all_accounts():
    """
    すべてのプラットフォーム・アカウントの組み合わせを取得

    Returns:
        list: [(platform, account_id), ...] のリスト
    """
    accounts = []
    for platform, account_ids in UPLOAD_ACCOUNTS.items():
        for account_id in account_ids:
            accounts.append((platform, account_id))
    return accounts


def get_daemon_config(account_id: str = None):
    """
    デーモン設定を取得（アカウント別設定を考慮）

    Args:
        account_id: アカウントID（Noneの場合は共通設定を返す）

    Returns:
        dict: デーモン設定
    """
    config = DAEMON_CONFIG.copy()

    # アカウント別設定があれば上書き
    if account_id and account_id in ACCOUNT_SPECIFIC_CONFIG:
        config.update(ACCOUNT_SPECIFIC_CONFIG[account_id])

    return config


def get_accounts_by_platform(platform: str):
    """
    指定プラットフォームのアカウントリストを取得

    Args:
        platform: プラットフォーム名

    Returns:
        list: アカウントIDのリスト
    """
    return UPLOAD_ACCOUNTS.get(platform, [])
