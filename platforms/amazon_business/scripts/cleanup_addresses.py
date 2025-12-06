#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Amazon Business - 住所録クリーンアップ

指定した名前以外の住所を全て削除します。

設定ファイル:
    platforms/amazon_business/config/address_cleanup.json
    ここで保護したい住所名のリストを設定できます。

使用方法:
    # 設定ファイルの値を使用
    python platforms/amazon_business/scripts/cleanup_addresses.py

    # コマンドラインで除外名を指定（複数可）
    python platforms/amazon_business/scripts/cleanup_addresses.py --exclude-names "住所1" "住所2" "住所3"

    # ヘッドレスモードで実行
    python platforms/amazon_business/scripts/cleanup_addresses.py --headless
"""

import asyncio
import sys
import argparse
import json
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from platforms.amazon_business.browser import AmazonBusinessSession
from platforms.amazon_business.tasks import cleanup_addresses


def load_config():
    """設定ファイルを読み込む"""
    config_path = (
        Path(__file__).parent.parent / "config" / "address_cleanup.json"
    )

    if not config_path.exists():
        print(f"[WARN] 設定ファイルが見つかりません: {config_path}")
        print("デフォルト設定を使用します。")
        return {
            "address_cleanup": {
                "exclude_names": ["ハディエント公式"],
                "max_attempts": 100
            }
        }

    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


async def main():
    """メイン処理"""
    # 設定ファイルを読み込む
    config = load_config()
    config_cleanup = config.get("address_cleanup", {})

    # コマンドライン引数の解析
    parser = argparse.ArgumentParser(
        description="Amazon Business 住所録クリーンアップ"
    )
    parser.add_argument(
        "--exclude-names",
        nargs="+",
        help="削除しない住所の名前（複数指定可、スペース区切り）。指定しない場合は設定ファイルの値を使用"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="ヘッドレスモードで実行"
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        help=f"最大試行回数（デフォルト: 設定ファイル={config_cleanup.get('max_attempts', 100)}）"
    )
    args = parser.parse_args()

    # 設定の優先順位: コマンドライン引数 > 設定ファイル > デフォルト
    exclude_names = args.exclude_names or config_cleanup.get("exclude_names", ["ハディエント公式"])
    max_attempts = args.max_attempts or config_cleanup.get("max_attempts", 100)

    print()
    print("=" * 60)
    print("Amazon Business - 住所録クリーンアップ")
    print("=" * 60)
    print()
    print(f"除外名（保護する住所）: {exclude_names}")
    print(f"最大試行回数: {max_attempts}")
    print(f"ヘッドレス: {args.headless}")
    print()

    # セッションマネージャーを初期化
    session = AmazonBusinessSession(account_id="amazon_business_main")

    # 認証済みコンテキストを取得
    result = await session.get_authenticated_context(headless=args.headless)

    if result is None:
        print()
        print("=" * 60)
        print("[ERROR] セッションが無効です")
        print("=" * 60)
        print()
        print("再ログインが必要です:")
        print("  python platforms/amazon_business/scripts/login.py")
        print()
        return

    playwright, context, page = result

    try:
        print()
        print("=" * 60)
        print("住所録クリーンアップを開始します")
        print("=" * 60)
        print()

        # 住所クリーンアップタスクを実行
        result = await cleanup_addresses(
            page=page,
            exclude_names=exclude_names,
            max_attempts=max_attempts
        )

        print()
        print("=" * 60)
        if result["success"]:
            print("[SUCCESS] クリーンアップが完了しました")
        else:
            print("[FAILED] クリーンアップに失敗しました")
        print("=" * 60)
        print()
        print(f"削除件数: {result['deleted_count']} 件")
        print(f"メッセージ: {result['message']}")
        print()

        # ヘッドレスモードでない場合は、ブラウザを5秒間表示
        if not args.headless:
            print("ブラウザを5秒間表示します...")
            await asyncio.sleep(5)
            print()

    except Exception as e:
        print()
        print("=" * 60)
        print("[ERROR] エラーが発生しました")
        print("=" * 60)
        print()
        print(f"エラー: {e}")
        import traceback
        traceback.print_exc()
        print()

    finally:
        # クリーンアップ
        await context.close()
        await playwright.stop()


if __name__ == "__main__":
    asyncio.run(main())
