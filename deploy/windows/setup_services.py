"""
Windows服務自動セットアップスクリプト

config/platforms.jsonを読み込み、有効化されているプラットフォームの
Windowsサービスを自動的にインストールします。

使用方法:
    python setup_services.py [--install|--uninstall|--restart]

前提条件:
    - 管理者権限で実行
    - nssm.exeがこのディレクトリに配置されている
"""

import sys
import json
import subprocess
import shutil
from pathlib import Path
from typing import Dict, Any, List


class ServiceSetup:
    """Windows服務セットアップクラス"""

    def __init__(self):
        self.project_root = Path(__file__).resolve().parent.parent.parent
        self.deploy_dir = Path(__file__).resolve().parent
        self.python_exe = self.project_root / 'venv' / 'Scripts' / 'python.exe'
        self.daemon_script = self.project_root / 'scheduler' / 'upload_daemon.py'
        self.log_dir = self.project_root / 'logs'

        # NSSMパスを自動検出
        self.nssm_path = self._find_nssm()

        # platforms.jsonを読み込み
        platforms_config_path = self.project_root / 'config' / 'platforms.json'
        with open(platforms_config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)

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

        # 見つからない場合は local_nssm を返す（エラーは check_prerequisites で検出）
        return local_nssm

    def check_prerequisites(self) -> bool:
        """前提条件をチェック"""
        errors = []

        if not self.nssm_path.exists():
            errors.append(f"nssm.exeが見つかりません")
            errors.append("以下のいずれかの方法でインストールしてください:")
            errors.append("  1. システム全体: C:\\Windows\\System32\\nssm.exe に配置")
            errors.append("  2. プロジェクト内: deploy/windows/nssm.exe に配置")
            errors.append("  3. ダウンロード: https://nssm.cc/download")

        if not self.python_exe.exists():
            errors.append(f"Python実行ファイルが見つかりません: {self.python_exe}")

        if not self.daemon_script.exists():
            errors.append(f"デーモンスクリプトが見つかりません: {self.daemon_script}")

        if errors:
            print("❌ 前提条件エラー:")
            for error in errors:
                print(f"  - {error}")
            return False

        # ログディレクトリを作成
        self.log_dir.mkdir(exist_ok=True)

        print("✅ 前提条件チェック完了")
        print(f"   NSSM: {self.nssm_path}")
        print(f"   Python: {self.python_exe}")
        print(f"   Daemon: {self.daemon_script}")
        return True

    def get_enabled_platforms(self) -> List[tuple[str, Dict[str, Any]]]:
        """有効化されているプラットフォームを取得"""
        enabled = []
        for platform, config in self.config['platforms'].items():
            if config.get('enabled', False):
                enabled.append((platform, config))
        return enabled

    def install_service(self, platform: str, config: Dict[str, Any]) -> bool:
        """単一プラットフォームのサービスをインストール"""
        service_name = config['service_name']
        display_name = config['display_name']
        interval = config['interval_seconds']
        batch_size = config['batch_size']
        business_hours = config.get('business_hours', {})
        start_hour = business_hours.get('start', 6)
        end_hour = business_hours.get('end', 23)

        print(f"\n{'='*60}")
        print(f"サービスインストール: {service_name}")
        print(f"{'='*60}")

        # サービス引数を構築
        service_args = [
            str(self.daemon_script),
            '--platform', platform,
            '--interval', str(interval),
            '--batch-size', str(batch_size),
            '--start-hour', str(start_hour),
            '--end-hour', str(end_hour)
        ]

        # NSSMでサービスをインストール
        install_cmd = [
            str(self.nssm_path),
            'install',
            service_name,
            str(self.python_exe)
        ] + service_args

        try:
            result = subprocess.run(
                install_cmd,
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode != 0:
                # 既に存在する場合は警告のみ
                if 'already exists' in result.stderr.lower():
                    print(f"⚠️  サービス '{service_name}' は既に存在します")
                    return True
                else:
                    print(f"❌ インストール失敗: {result.stderr}")
                    return False

            print(f"✅ サービス '{service_name}' をインストールしました")

            # サービス設定
            self._configure_service(service_name, display_name, platform)

            return True

        except Exception as e:
            print(f"❌ エラー: {e}")
            return False

    def _configure_service(self, service_name: str, display_name: str, platform: str):
        """サービスの詳細設定"""
        settings = [
            # 作業ディレクトリ
            ('set', service_name, 'AppDirectory', str(self.project_root)),

            # 表示名
            ('set', service_name, 'DisplayName', display_name),

            # ログファイル
            ('set', service_name, 'AppStdout',
             str(self.log_dir / f'upload_scheduler_{platform}_service.log')),
            ('set', service_name, 'AppStderr',
             str(self.log_dir / f'upload_scheduler_{platform}_service_error.log')),

            # 自動起動（遅延）
            ('set', service_name, 'Start', 'SERVICE_DELAYED_AUTO_START'),

            # 失敗時の自動再起動
            ('set', service_name, 'AppExit', 'Default', 'Restart'),
            ('set', service_name, 'AppRestartDelay', '60000'),  # 60秒後に再起動
        ]

        print(f"  サービス設定を適用中...")
        for setting in settings:
            cmd = [str(self.nssm_path)] + list(setting)
            subprocess.run(cmd, capture_output=True, check=False)

        print(f"  ✅ サービス設定完了")

    def start_service(self, service_name: str) -> bool:
        """サービスを起動"""
        try:
            result = subprocess.run(
                [str(self.nssm_path), 'start', service_name],
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode == 0:
                print(f"  ✅ サービス '{service_name}' を起動しました")
                return True
            else:
                print(f"  ⚠️  サービス起動失敗: {result.stderr}")
                return False

        except Exception as e:
            print(f"  ❌ エラー: {e}")
            return False

    def stop_service(self, service_name: str) -> bool:
        """サービスを停止"""
        try:
            result = subprocess.run(
                [str(self.nssm_path), 'stop', service_name],
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode == 0:
                print(f"  ✅ サービス '{service_name}' を停止しました")
                return True
            else:
                # 既に停止している場合は警告のみ
                if 'not started' in result.stderr.lower() or 'stopped' in result.stderr.lower():
                    print(f"  ℹ️  サービス '{service_name}' は既に停止しています")
                    return True
                else:
                    print(f"  ⚠️  サービス停止失敗: {result.stderr}")
                    return False

        except Exception as e:
            print(f"  ❌ エラー: {e}")
            return False

    def uninstall_service(self, service_name: str) -> bool:
        """サービスをアンインストール"""
        try:
            # まず停止
            self.stop_service(service_name)

            # アンインストール
            result = subprocess.run(
                [str(self.nssm_path), 'remove', service_name, 'confirm'],
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode == 0:
                print(f"  ✅ サービス '{service_name}' をアンインストールしました")
                return True
            else:
                # 存在しない場合は警告のみ
                if 'not found' in result.stderr.lower():
                    print(f"  ℹ️  サービス '{service_name}' は存在しません")
                    return True
                else:
                    print(f"  ❌ アンインストール失敗: {result.stderr}")
                    return False

        except Exception as e:
            print(f"  ❌ エラー: {e}")
            return False

    def install_all(self):
        """全ての有効化されているプラットフォームのサービスをインストール"""
        if not self.check_prerequisites():
            return False

        enabled_platforms = self.get_enabled_platforms()

        if not enabled_platforms:
            print("\n⚠️  有効化されているプラットフォームがありません")
            print("config/platforms.json で 'enabled': true を設定してください")
            return False

        print(f"\n有効化されているプラットフォーム: {len(enabled_platforms)}個")
        for platform, _ in enabled_platforms:
            print(f"  - {platform}")

        success_count = 0
        for platform, config in enabled_platforms:
            if self.install_service(platform, config):
                success_count += 1

        print(f"\n{'='*60}")
        print(f"インストール完了: {success_count}/{len(enabled_platforms)} 成功")
        print(f"{'='*60}")

        # 起動確認
        print("\nサービスを起動しますか？ (y/n): ", end='')
        response = input().strip().lower()
        if response == 'y':
            for platform, config in enabled_platforms:
                service_name = config['service_name']
                self.start_service(service_name)

        return True

    def uninstall_all(self):
        """全ての有効化されているプラットフォームのサービスをアンインストール"""
        enabled_platforms = self.get_enabled_platforms()

        if not enabled_platforms:
            print("\n⚠️  有効化されているプラットフォームがありません")
            return False

        print(f"\n以下のサービスをアンインストールします:")
        for platform, config in enabled_platforms:
            print(f"  - {config['service_name']}")

        print("\n続行しますか？ (y/n): ", end='')
        response = input().strip().lower()
        if response != 'y':
            print("キャンセルしました")
            return False

        success_count = 0
        for platform, config in enabled_platforms:
            service_name = config['service_name']
            if self.uninstall_service(service_name):
                success_count += 1

        print(f"\n{'='*60}")
        print(f"アンインストール完了: {success_count}/{len(enabled_platforms)} 成功")
        print(f"{'='*60}")

        return True

    def restart_all(self):
        """全ての有効化されているプラットフォームのサービスを再起動"""
        enabled_platforms = self.get_enabled_platforms()

        if not enabled_platforms:
            print("\n⚠️  有効化されているプラットフォームがありません")
            return False

        print(f"\n以下のサービスを再起動します:")
        for platform, config in enabled_platforms:
            print(f"  - {config['service_name']}")

        success_count = 0
        for platform, config in enabled_platforms:
            service_name = config['service_name']
            print(f"\n{service_name} を再起動中...")
            if self.stop_service(service_name) and self.start_service(service_name):
                success_count += 1

        print(f"\n{'='*60}")
        print(f"再起動完了: {success_count}/{len(enabled_platforms)} 成功")
        print(f"{'='*60}")

        return True


def main():
    """メイン処理"""
    if len(sys.argv) < 2:
        print("使用方法:")
        print("  python setup_services.py --install     # サービスをインストール")
        print("  python setup_services.py --uninstall   # サービスをアンインストール")
        print("  python setup_services.py --restart     # サービスを再起動")
        sys.exit(1)

    setup = ServiceSetup()
    command = sys.argv[1]

    if command == '--install':
        setup.install_all()
    elif command == '--uninstall':
        setup.uninstall_all()
    elif command == '--restart':
        setup.restart_all()
    else:
        print(f"❌ 不明なコマンド: {command}")
        sys.exit(1)


if __name__ == '__main__':
    main()
