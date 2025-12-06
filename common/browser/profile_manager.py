"""
Chrome Profile Manager

プラットフォーム/アカウント単位でChromeプロファイルを管理します。
Playwrightの launch_persistent_context を使用してプロファイルを永続化します。
"""

from pathlib import Path
from typing import Optional
import json


class ProfileManager:
    """
    Chromeプロファイルマネージャー

    各プラットフォームのアカウント別にChromeプロファイルを管理し、
    セッション情報を永続化します。

    プロファイルパス例:
        - platforms/amazon_business/accounts/profiles/amazon_business_main/
        - platforms/mercari/accounts/profiles/mercari_account_1/
        - platforms/yahoo_auction/accounts/profiles/yahoo_account_1/
    """

    def __init__(self, base_dir: Optional[Path] = None):
        """
        Args:
            base_dir: プロジェクトのルートディレクトリ（Noneの場合は自動検出）
        """
        if base_dir is None:
            # このファイルから3階層上がルートディレクトリ（ecauto/）
            base_dir = Path(__file__).parent.parent.parent

        self.base_dir = Path(base_dir)
        self.platforms_dir = self.base_dir / "platforms"

    def get_profile_path(self, platform: str, account_id: str) -> Path:
        """
        指定したプラットフォーム/アカウントのプロファイルパスを取得

        Args:
            platform: プラットフォーム名（例: "amazon_business", "mercari"）
            account_id: アカウントID（例: "amazon_business_main", "mercari_account_1"）

        Returns:
            Path: プロファイルディレクトリのパス
        """
        profile_path = self.platforms_dir / platform / "accounts" / "profiles" / account_id
        return profile_path

    def create_profile(self, platform: str, account_id: str) -> Path:
        """
        プロファイルディレクトリを作成

        Args:
            platform: プラットフォーム名
            account_id: アカウントID

        Returns:
            Path: 作成したプロファイルディレクトリのパス
        """
        profile_path = self.get_profile_path(platform, account_id)
        profile_path.mkdir(parents=True, exist_ok=True)
        return profile_path

    def profile_exists(self, platform: str, account_id: str) -> bool:
        """
        プロファイルが存在するかチェック

        Args:
            platform: プラットフォーム名
            account_id: アカウントID

        Returns:
            bool: プロファイルが存在する場合 True
        """
        profile_path = self.get_profile_path(platform, account_id)
        return profile_path.exists() and any(profile_path.iterdir())

    def list_profiles(self, platform: str) -> list[str]:
        """
        指定したプラットフォームのプロファイル一覧を取得

        Args:
            platform: プラットフォーム名

        Returns:
            list[str]: アカウントIDのリスト
        """
        profiles_dir = self.platforms_dir / platform / "accounts" / "profiles"

        if not profiles_dir.exists():
            return []

        return [
            profile.name
            for profile in profiles_dir.iterdir()
            if profile.is_dir()
        ]

    def get_profile_info(self, platform: str, account_id: str) -> dict:
        """
        プロファイル情報を取得

        Args:
            platform: プラットフォーム名
            account_id: アカウントID

        Returns:
            dict: プロファイル情報
        """
        profile_path = self.get_profile_path(platform, account_id)

        info = {
            "platform": platform,
            "account_id": account_id,
            "profile_path": str(profile_path),
            "exists": self.profile_exists(platform, account_id),
            "size_mb": 0
        }

        # プロファイルサイズを計算
        if info["exists"]:
            total_size = sum(
                f.stat().st_size
                for f in profile_path.rglob("*")
                if f.is_file()
            )
            info["size_mb"] = round(total_size / (1024 * 1024), 2)

        return info

    def delete_profile(self, platform: str, account_id: str) -> bool:
        """
        プロファイルを削除

        Args:
            platform: プラットフォーム名
            account_id: アカウントID

        Returns:
            bool: 削除成功時 True
        """
        profile_path = self.get_profile_path(platform, account_id)

        if not profile_path.exists():
            return False

        import shutil
        shutil.rmtree(profile_path)
        return True
