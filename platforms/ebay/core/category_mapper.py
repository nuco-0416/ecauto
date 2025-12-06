# -*- coding: utf-8 -*-
"""
eBay カテゴリ自動推薦モジュール

レガシーシステムのget_ebay_category_id()を改良・クラス化
"""

import requests
import json
from typing import Dict, Optional, List, Any
from pathlib import Path
import sys
import hashlib

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(project_root))

from platforms.ebay.core.auth import EbayAuthClient


class CategoryMapper:
    """
    eBayカテゴリ自動推薦

    機能:
    - Taxonomy APIでカテゴリ推薦
    - カテゴリ別必須Item Specifics取得
    - カテゴリ推薦結果のキャッシュ
    """

    # デフォルトフォールバックカテゴリ
    FALLBACK_CATEGORIES = {
        'toys': '16427',  # Action Figures
        'collectibles': '13658',  # Anime & Manga Collectibles
        'default': '16427'  # デフォルト: Action Figures
    }

    def __init__(self, credentials: Dict[str, str], environment: str = 'production'):
        """
        Args:
            credentials: 認証情報 {'app_id', 'cert_id', 'redirect_uri'}
            environment: 'sandbox' or 'production'
        """
        self.environment = environment
        self.is_sandbox = (environment == 'sandbox')

        # OAuth クライアント初期化（Application Token用）
        self.auth_client = EbayAuthClient(
            app_id=credentials['app_id'],
            cert_id=credentials['cert_id'],
            redirect_uri=credentials['redirect_uri'],
            environment=environment
        )

        # API URL設定
        if self.is_sandbox:
            self.base_url = "https://api.sandbox.ebay.com"
        else:
            self.base_url = "https://api.ebay.com"

        # キャッシュディレクトリ
        self.cache_dir = Path(__file__).parent.parent / 'data' / 'category_cache'
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_recommended_category(self, title: str, description: str = None,
                                use_cache: bool = True) -> Optional[Dict[str, Any]]:
        """
        Taxonomy APIでカテゴリ推薦

        Args:
            title: 商品タイトル
            description: 商品説明（オプション）
            use_cache: キャッシュを使用するか

        Returns:
            {
                'category_id': str,
                'category_name': str,
                'confidence': float,
                'source': 'api' | 'cache' | 'fallback'
            }
        """
        # クエリ文字列
        query = f"{title} {description}" if description else title

        # キャッシュチェック
        if use_cache:
            cached = self._get_cached_category(query)
            if cached:
                cached['source'] = 'cache'
                return cached

        # Taxonomy API呼び出し
        app_token_data = self.auth_client.get_application_token()
        if not app_token_data:
            # Application Token取得失敗時はフォールバック
            return self._get_fallback_category()

        app_token = app_token_data['access_token']

        url = f"{self.base_url}/commerce/taxonomy/v1/category_tree/0/get_category_suggestions"
        headers = {
            "Authorization": f"Bearer {app_token}",
            "Content-Type": "application/json"
        }
        params = {"q": title[:300]}  # タイトルのみ使用（最大300文字）

        try:
            response = requests.get(url, headers=headers, params=params)

            if response.status_code == 200:
                data = response.json()
                suggestions = data.get('categorySuggestions', [])

                if suggestions:
                    suggestion = suggestions[0]
                    category_info = suggestion['category']

                    result = {
                        'category_id': category_info['categoryId'],
                        'category_name': category_info.get('categoryName', 'Unknown'),
                        'confidence': 1.0,  # eBay APIは信頼度を返さないため固定値
                        'source': 'api'
                    }

                    # キャッシュに保存
                    self._save_cache(query, result)

                    return result

            # API呼び出し失敗またはカテゴリなし
            return self._get_fallback_category()

        except requests.exceptions.RequestException:
            # ネットワークエラー等
            return self._get_fallback_category()

    def get_category_specifics(self, category_id: str) -> List[Dict[str, Any]]:
        """
        カテゴリ別必須Item Specifics取得

        Args:
            category_id: eBayカテゴリID

        Returns:
            [
                {
                    'name': 'Brand',
                    'required': True,
                    'values': ['Sony', 'Canon', ...]
                },
                ...
            ]

        Note:
            現在は簡易実装（API未実装）
            将来的にはGetCategorySpecifics APIを使用
        """
        # TODO: GetCategorySpecifics API実装
        # 現在は基本的なItem Specificsのみ返す
        return [
            {
                'name': 'Brand',
                'required': True,
                'values': []
            },
            {
                'name': 'Condition',
                'required': True,
                'values': ['New', 'Used', 'New other (see details)']
            },
            {
                'name': 'Country/Region of Manufacture',
                'required': False,
                'values': ['Japan', 'China', 'United States']
            }
        ]

    # =========================================================================
    # キャッシュ管理
    # =========================================================================

    def _get_cache_key(self, query: str) -> str:
        """
        クエリ文字列からキャッシュキー生成

        Args:
            query: 検索クエリ

        Returns:
            str: ハッシュ化されたキャッシュキー
        """
        return hashlib.md5(query.lower().encode()).hexdigest()

    def _get_cached_category(self, query: str) -> Optional[Dict[str, Any]]:
        """
        キャッシュからカテゴリ取得

        Args:
            query: 検索クエリ

        Returns:
            dict or None: キャッシュされたカテゴリ情報
        """
        cache_key = self._get_cache_key(query)
        cache_file = self.cache_dir / f'{cache_key}.json'

        if not cache_file.exists():
            return None

        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return None

    def _save_cache(self, query: str, category_info: Dict[str, Any]):
        """
        カテゴリ情報をキャッシュに保存

        Args:
            query: 検索クエリ
            category_info: カテゴリ情報
        """
        cache_key = self._get_cache_key(query)
        cache_file = self.cache_dir / f'{cache_key}.json'

        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(category_info, f, ensure_ascii=False, indent=2)
        except:
            pass  # キャッシュ保存失敗は無視

    def _get_fallback_category(self) -> Dict[str, Any]:
        """
        フォールバックカテゴリ取得

        Returns:
            dict: デフォルトカテゴリ情報
        """
        return {
            'category_id': self.FALLBACK_CATEGORIES['default'],
            'category_name': 'Action Figures',
            'confidence': 0.5,
            'source': 'fallback'
        }

    # =========================================================================
    # ユーティリティ
    # =========================================================================

    def clear_cache(self):
        """キャッシュをクリア"""
        import shutil
        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)
            self.cache_dir.mkdir(parents=True, exist_ok=True)


# テスト実行
def main():
    """テスト実行"""
    # Windows環境対応
    if sys.platform == 'win32':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    print("eBay カテゴリマッパー - モジュールロードテスト")
    print("=" * 60)

    # ダミー認証情報でインスタンス作成
    credentials = {
        'app_id': 'test_app_id',
        'cert_id': 'test_cert_id',
        'redirect_uri': 'https://localhost:8000/callback'
    }

    try:
        mapper = CategoryMapper(
            credentials=credentials,
            environment='sandbox'
        )
        print("[OK] CategoryMapper インスタンス作成成功")
        print(f"     環境: {mapper.environment}")
        print(f"     キャッシュディレクトリ: {mapper.cache_dir}")

        # フォールバックカテゴリ取得テスト
        fallback = mapper._get_fallback_category()
        print(f"[OK] フォールバックカテゴリ: {fallback['category_name']} (ID: {fallback['category_id']})")

    except Exception as e:
        print(f"[ERROR] エラー: {e}")
        import traceback
        traceback.print_exc()

    print("=" * 60)
    print("[OK] モジュールのロードに成功しました")


if __name__ == '__main__':
    main()
