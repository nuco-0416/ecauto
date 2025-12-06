"""
Windows服務ヘルスチェック監視スクリプト

全てのアップロードデーモンサービスを監視し、問題があれば自動修復とChatwork通知を行います。

使用方法:
    python health_check.py [--daily-report]

前提条件:
    - nssm.exeがこのディレクトリに配置されている
    - config/notifications.jsonが設定済み
"""

import sys
import json
import subprocess
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional


# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from shared.utils.notifier import Notifier


class ServiceHealthCheck:
    """サービスヘルスチェッククラス"""

    def __init__(self):
        self.project_root = Path(__file__).resolve().parent.parent.parent
        self.deploy_dir = Path(__file__).resolve().parent
        self.log_dir = self.project_root / 'logs'

        # NSSMパスを自動検出
        self.nssm_path = self._find_nssm()

        # platforms.jsonを読み込み
        platforms_config_path = self.project_root / 'config' / 'platforms.json'
        with open(platforms_config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)

        # Notifierを初期化
        self.notifier = Notifier()

    def _find_nssm(self) -> Path:
        """NSSMの実行ファイルを自動検出"""
        # 1. システムPATHから検索（C:\Windows\System32など）
        nssm_in_path = shutil.which('nssm')
        if nssm_in_path:
            return Path(nssm_in_path)

        # 2. deploy/windows/nssm.exeを検索
        local_nssm = self.deploy_dir / 'nssm.exe'
        if local_nssm.exists():
            return local_nssm

        # 3. C:\Windows\System32\nssm.exeを直接検索
        system32_nssm = Path(r'C:\Windows\System32\nssm.exe')
        if system32_nssm.exists():
            return system32_nssm

        # 見つからない場合は local_nssm を返す
        return local_nssm

    def get_enabled_platforms(self) -> List[tuple[str, Dict[str, Any]]]:
        """有効化されているプラットフォームを取得"""
        enabled = []
        for platform, config in self.config['platforms'].items():
            if config.get('enabled', False):
                enabled.append((platform, config))
        return enabled

    def check_service_status(self, service_name: str) -> Optional[str]:
        """
        サービスのステータスをチェック

        Returns:
            'running', 'stopped', 'paused', None (存在しない)
        """
        try:
            result = subprocess.run(
                [str(self.nssm_path), 'status', service_name],
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode == 0:
                status = result.stdout.strip().lower()
                return status
            else:
                return None

        except Exception as e:
            print(f"❌ ステータスチェックエラー ({service_name}): {e}")
            return None

    def start_service(self, service_name: str) -> bool:
        """サービスを起動"""
        try:
            result = subprocess.run(
                [str(self.nssm_path), 'start', service_name],
                capture_output=True,
                text=True,
                check=False
            )

            return result.returncode == 0

        except Exception as e:
            print(f"❌ サービス起動エラー ({service_name}): {e}")
            return False

    def check_log_freshness(
        self,
        platform: str,
        max_age_minutes: int = 10
    ) -> tuple[bool, Optional[str]]:
        """
        ログファイルの鮮度をチェック

        Args:
            platform: プラットフォーム名
            max_age_minutes: 許容する最大経過時間（分）

        Returns:
            (is_fresh, message)
        """
        log_file = self.log_dir / f'upload_scheduler_{platform}_service.log'

        if not log_file.exists():
            return False, f"ログファイルが存在しません: {log_file}"

        try:
            # ログファイルの最終更新時刻を取得
            last_modified = datetime.fromtimestamp(log_file.stat().st_mtime)
            age = datetime.now() - last_modified
            age_minutes = age.total_seconds() / 60

            if age_minutes > max_age_minutes:
                return False, f"ログが{age_minutes:.1f}分間更新されていません（許容: {max_age_minutes}分）"

            return True, None

        except Exception as e:
            return False, f"ログファイルチェックエラー: {e}"

    def check_single_service(
        self,
        platform: str,
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        単一サービスをチェック

        Returns:
            {
                'platform': str,
                'service_name': str,
                'status': str,
                'healthy': bool,
                'issues': List[str],
                'actions_taken': List[str]
            }
        """
        service_name = config['service_name']
        result = {
            'platform': platform,
            'service_name': service_name,
            'status': 'unknown',
            'healthy': True,
            'issues': [],
            'actions_taken': []
        }

        # ステータスチェック
        status = self.check_service_status(service_name)
        result['status'] = status or 'not_found'

        if status is None:
            result['healthy'] = False
            result['issues'].append(f"サービスが見つかりません")
            return result

        if status != 'service_running':
            result['healthy'] = False
            result['issues'].append(f"サービスが停止しています (status: {status})")

            # 自動再起動を試みる
            print(f"⚠️  サービス '{service_name}' が停止しています。再起動を試みます...")
            if self.start_service(service_name):
                result['actions_taken'].append("サービスを再起動しました")
                print(f"✅ サービス '{service_name}' を再起動しました")
            else:
                result['actions_taken'].append("サービスの再起動に失敗しました")
                print(f"❌ サービス '{service_name}' の再起動に失敗しました")

        # ログの鮮度チェック（サービスが動作している場合のみ）
        if status == 'service_running':
            is_fresh, message = self.check_log_freshness(
                platform,
                max_age_minutes=config['interval_seconds'] // 60 + 5  # インターバル + 5分
            )

            if not is_fresh:
                result['healthy'] = False
                result['issues'].append(message)

        return result

    def check_all_services(self) -> List[Dict[str, Any]]:
        """全てのサービスをチェック"""
        enabled_platforms = self.get_enabled_platforms()
        results = []

        print(f"{'='*60}")
        print(f"サービスヘルスチェック - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")

        for platform, config in enabled_platforms:
            print(f"チェック中: {platform}...")
            result = self.check_single_service(platform, config)
            results.append(result)

            if result['healthy']:
                print(f"  ✅ 正常")
            else:
                print(f"  ⚠️  問題検出:")
                for issue in result['issues']:
                    print(f"    - {issue}")
                if result['actions_taken']:
                    print(f"  📝 実施した対応:")
                    for action in result['actions_taken']:
                        print(f"    - {action}")

            print()

        return results

    def send_alert(self, results: List[Dict[str, Any]]):
        """問題があればChatwork通知を送信"""
        unhealthy = [r for r in results if not r['healthy']]

        if not unhealthy:
            return

        # 通知メッセージを構築
        title = "⚠️ アップロードデーモン ヘルスチェック警告"
        message_parts = [
            f"[info][title]{title}[/title]",
            f"{len(unhealthy)}個のサービスで問題が検出されました。\n"
        ]

        for result in unhealthy:
            message_parts.append(f"[hr]")
            message_parts.append(f"プラットフォーム: {result['platform']}")
            message_parts.append(f"サービス名: {result['service_name']}")
            message_parts.append(f"ステータス: {result['status']}\n")

            if result['issues']:
                message_parts.append("問題:")
                for issue in result['issues']:
                    message_parts.append(f"  • {issue}")
                message_parts.append("")

            if result['actions_taken']:
                message_parts.append("実施した対応:")
                for action in result['actions_taken']:
                    message_parts.append(f"  • {action}")
                message_parts.append("")

        message_parts.append(f"[hr]")
        message_parts.append(f"確認時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        message_parts.append("[/info]")

        message = "\n".join(message_parts)

        # Chatwork通知を送信
        try:
            self.notifier.send(title, message)
            print(f"📤 Chatwork通知を送信しました")
        except Exception as e:
            print(f"❌ Chatwork通知送信エラー: {e}")

    def generate_daily_report(self) -> str:
        """日次レポートを生成"""
        enabled_platforms = self.get_enabled_platforms()
        results = self.check_all_services()

        healthy_count = sum(1 for r in results if r['healthy'])
        unhealthy_count = len(results) - healthy_count

        # レポートを構築
        report_parts = [
            "[info][title]📊 アップロードデーモン 日次レポート[/title]",
            f"日付: {datetime.now().strftime('%Y年%m月%d日')}\n",
            f"[hr]",
            f"📈 サービス稼働状況",
            f"  • 正常: {healthy_count}個",
            f"  • 異常: {unhealthy_count}個",
            f"  • 合計: {len(results)}個\n",
        ]

        if results:
            report_parts.append(f"[hr]")
            report_parts.append(f"📋 各サービスの状態\n")

            for result in results:
                status_icon = "✅" if result['healthy'] else "⚠️"
                report_parts.append(
                    f"{status_icon} {result['platform']}: {result['status']}"
                )

        report_parts.append(f"\n[hr]")
        report_parts.append(f"生成時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_parts.append("[/info]")

        return "\n".join(report_parts)

    def send_daily_report(self):
        """日次レポートを送信"""
        report = self.generate_daily_report()

        try:
            self.notifier.send("日次レポート", report)
            print(f"📤 日次レポートを送信しました")
        except Exception as e:
            print(f"❌ 日次レポート送信エラー: {e}")


def main():
    """メイン処理"""
    health_check = ServiceHealthCheck()

    # コマンドライン引数をチェック
    daily_report = '--daily-report' in sys.argv

    if daily_report:
        # 日次レポート送信
        print("📊 日次レポートを生成中...\n")
        health_check.send_daily_report()
    else:
        # 通常のヘルスチェック
        results = health_check.check_all_services()

        # 問題があれば通知
        health_check.send_alert(results)

        # サマリー表示
        print(f"{'='*60}")
        print(f"ヘルスチェック完了")
        print(f"{'='*60}")
        healthy_count = sum(1 for r in results if r['healthy'])
        print(f"正常: {healthy_count}/{len(results)}")
        print()


if __name__ == '__main__':
    main()
