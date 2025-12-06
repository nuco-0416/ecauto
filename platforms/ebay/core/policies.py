# -*- coding: utf-8 -*-
"""
eBay ビジネスポリシー管理モジュール

レガシーシステムのPOLICY_IDsを統合管理・クラス化
"""

import json
from typing import Dict, Optional, Any
from pathlib import Path
import sys

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(project_root))


class PolicyManager:
    """
    eBayビジネスポリシー管理

    機能:
    - アカウント別デフォルトポリシーID管理
    - ポリシーIDバリデーション（API経由）
    - 設定ファイルの読み書き
    """

    def __init__(self, config_path: str = None):
        """
        Args:
            config_path: ポリシー設定ファイルのパス（Noneの場合はデフォルトパス）
        """
        if config_path is None:
            # デフォルトパス
            base_dir = Path(__file__).resolve().parent.parent
            config_path = base_dir / 'data' / 'policies' / 'default_policies.json'

        self.config_path = Path(config_path)
        self.policies = self._load_policies()

    def _load_policies(self) -> Dict[str, Any]:
        """
        ポリシー設定をロード

        Returns:
            dict: ポリシー設定
        """
        if not self.config_path.exists():
            print(f"警告: ポリシー設定ファイルが見つかりません: {self.config_path}")
            return {'accounts': {}}

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"エラー: ポリシー設定の読み込みに失敗しました: {e}")
            return {'accounts': {}}

    def get_default_policies(self, account_id: str) -> Optional[Dict[str, str]]:
        """
        アカウントのデフォルトポリシーID取得

        Args:
            account_id: アカウントID

        Returns:
            {
                'payment': str,
                'return': str,
                'fulfillment': str
            }
            or None: アカウントが見つからない場合
        """
        accounts = self.policies.get('accounts', {})
        return accounts.get(account_id)

    def set_default_policies(self, account_id: str, policies: Dict[str, str]) -> bool:
        """
        アカウントのデフォルトポリシーIDを設定

        Args:
            account_id: アカウントID
            policies: ポリシーID辞書 {'payment': str, 'return': str, 'fulfillment': str}

        Returns:
            bool: 成功時True
        """
        if 'accounts' not in self.policies:
            self.policies['accounts'] = {}

        self.policies['accounts'][account_id] = policies

        return self._save_policies()

    def _save_policies(self) -> bool:
        """
        ポリシー設定を保存

        Returns:
            bool: 成功時True
        """
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.policies, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"エラー: ポリシー設定の保存に失敗しました: {e}")
            return False

    def validate_policies(self, policy_ids: Dict[str, str]) -> Dict[str, bool]:
        """
        ポリシーIDの有効性確認（簡易バージョン）

        Args:
            policy_ids: ポリシーID辞書 {'payment': str, 'return': str, 'fulfillment': str}

        Returns:
            {
                'payment': True/False,
                'return': True/False,
                'fulfillment': True/False
            }

        Note:
            現在は簡易実装（IDの存在チェックのみ）
            将来的にはeBay APIで実際に検証
        """
        result = {}

        for policy_type in ['payment', 'return', 'fulfillment']:
            policy_id = policy_ids.get(policy_type)
            # 簡易検証: IDが存在し、数字のみで構成されているかチェック
            result[policy_type] = bool(policy_id and policy_id.isdigit())

        return result

    def validate_policies_api(self, policy_ids: Dict[str, str], api_client) -> Dict[str, bool]:
        """
        ポリシーIDの有効性確認（eBay API経由）

        Args:
            policy_ids: ポリシーID辞書
            api_client: EbayAPIClientインスタンス

        Returns:
            dict: 検証結果

        Note:
            現在は未実装（将来的にAccount API使用）
            TODO: GET /sell/account/v1/payment_policy/{payment_policy_id} 等を実装
        """
        # TODO: eBay Account APIでポリシーIDを検証
        # 現在は簡易バージョンにフォールバック
        return self.validate_policies(policy_ids)

    def list_accounts(self) -> list:
        """
        ポリシー設定済みアカウント一覧を取得

        Returns:
            list: アカウントIDのリスト
        """
        accounts = self.policies.get('accounts', {})
        return list(accounts.keys())

    def has_policies(self, account_id: str) -> bool:
        """
        アカウントにポリシー設定があるかチェック

        Args:
            account_id: アカウントID

        Returns:
            bool: ポリシー設定がある場合True
        """
        policies = self.get_default_policies(account_id)
        if not policies:
            return False

        # 全てのポリシーIDが設定されているかチェック
        required_keys = ['payment', 'return', 'fulfillment']
        return all(policies.get(key) for key in required_keys)

    def print_summary(self):
        """ポリシー設定のサマリーを表示"""
        print("\n" + "=" * 60)
        print("eBay ビジネスポリシー設定")
        print("=" * 60)

        accounts = self.policies.get('accounts', {})

        if not accounts:
            print("ポリシー設定済みアカウント: なし")
        else:
            print(f"ポリシー設定済みアカウント: {len(accounts)}件\n")

            for account_id, policies in accounts.items():
                print(f"[{account_id}]")
                print(f"  Payment Policy:     {policies.get('payment', 'なし')}")
                print(f"  Return Policy:      {policies.get('return', 'なし')}")
                print(f"  Fulfillment Policy: {policies.get('fulfillment', 'なし')}")
                print()

        print("=" * 60)


# テスト実行
def main():
    """テスト実行"""
    # Windows環境対応
    if sys.platform == 'win32':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    print("eBay ポリシーマネージャー - モジュールロードテスト")
    print("=" * 60)

    try:
        manager = PolicyManager()
        print("[OK] PolicyManager インスタンス作成成功")
        print(f"     設定ファイル: {manager.config_path}")

        # ポリシー設定サマリー表示
        manager.print_summary()

        # ポリシー取得テスト
        policies = manager.get_default_policies('ebay_account_1')
        if policies:
            print("[OK] ポリシー取得成功: ebay_account_1")
            print(f"     Payment: {policies.get('payment')}")
            print(f"     Return: {policies.get('return')}")
            print(f"     Fulfillment: {policies.get('fulfillment')}")

            # バリデーションテスト
            validation = manager.validate_policies(policies)
            print(f"[OK] ポリシーバリデーション: {validation}")
        else:
            print("[INFO] ebay_account_1 のポリシー設定がありません")

    except Exception as e:
        print(f"[ERROR] エラー: {e}")
        import traceback
        traceback.print_exc()

    print("=" * 60)
    print("[OK] モジュールのロードに成功しました")


if __name__ == '__main__':
    main()
