"""
Amazon SP-API Configuration

.envファイルからSP-API認証情報を読み込み
"""

import os
from pathlib import Path
from typing import Dict
from dotenv import load_dotenv


def load_sp_api_credentials() -> Dict[str, str]:
    """
    .envファイルからSP-API認証情報を読み込み

    Returns:
        dict: SP-API認証情報
            - refresh_token
            - lwa_app_id
            - lwa_client_secret
    """
    # プロジェクトルートの.envファイルを読み込み
    project_root = Path(__file__).resolve().parent.parent.parent
    env_path = project_root / '.env'

    if not env_path.exists():
        print("[ERROR] .envファイルが見つかりません")
        print(f"  期待されるパス: {env_path}")
        print("  .env.exampleを参考に.envファイルを作成してください")
        return {
            "refresh_token": "",
            "lwa_app_id": "",
            "lwa_client_secret": ""
        }

    # .envファイルを読み込み
    load_dotenv(env_path)

    # .envの変数名をチェック（2パターン対応）
    # 優先: REFRESH_TOKEN, LWA_APP_ID, LWA_CLIENT_SECRET（現在の.env形式）
    # 代替: SP_API_REFRESH_TOKEN, SP_API_LWA_APP_ID, SP_API_LWA_CLIENT_SECRET
    refresh_token = (
        os.getenv('REFRESH_TOKEN') or
        os.getenv('SP_API_REFRESH_TOKEN')
    )
    lwa_app_id = (
        os.getenv('LWA_APP_ID') or
        os.getenv('SP_API_LWA_APP_ID')
    )
    lwa_client_secret = (
        os.getenv('LWA_CLIENT_SECRET') or
        os.getenv('SP_API_LWA_CLIENT_SECRET')
    )

    # 認証情報の検証
    if not all([refresh_token, lwa_app_id, lwa_client_secret]):
        print("[ERROR] .envファイルに必要な認証情報が不足しています")
        print("  必要な変数:")
        print("    - REFRESH_TOKEN (または SP_API_REFRESH_TOKEN)")
        print("    - LWA_APP_ID (または SP_API_LWA_APP_ID)")
        print("    - LWA_CLIENT_SECRET (または SP_API_LWA_CLIENT_SECRET)")

        # 欠けている変数を表示
        if not refresh_token:
            print("  ✗ REFRESH_TOKEN が設定されていません")
        if not lwa_app_id:
            print("  ✗ LWA_APP_ID が設定されていません")
        if not lwa_client_secret:
            print("  ✗ LWA_CLIENT_SECRET が設定されていません")

        return {
            "refresh_token": "",
            "lwa_app_id": "",
            "lwa_client_secret": ""
        }

    print("[INFO] SP-API認証情報: .envファイルから読み込み成功")

    return {
        "refresh_token": refresh_token,
        "lwa_app_id": lwa_app_id,
        "lwa_client_secret": lwa_client_secret
    }


# グローバル変数として読み込み
SP_API_CREDENTIALS = load_sp_api_credentials()
