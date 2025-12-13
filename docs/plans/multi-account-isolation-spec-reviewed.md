# マルチアカウント分離環境 実装仕様書（既存環境適合版）

> **元仕様書**: [multi-account-isolation-spec.md](./multi-account-isolation-spec.md)
> **作成日**: 2024-12-11
> **ステータス**: レビュー済み・実装待ち

## 1. 概要

### 1.1 目的
BASE および Yahoo!オークション（ヤフオク）の複数アカウント運用において、各アカウントの接続元を完全に分離し、プラットフォーム側からの関連付けを防止する。

### 1.2 対象プラットフォーム
| プラットフォーム | 通信方式 | 分離方式 |
|-----------------|---------|---------|
| BASE | API通信 | プロキシ切り替えのみ |
| ヤフオク | Playwright（ブラウザ自動化） | Docker + プロキシ |

### 1.3 設計方針
- **既存構造への統合**: 新規ディレクトリ作成を最小限に抑え、既存の `platforms/`, `common/`, `config/` 構造を活用
- **後方互換性**: 既存のアカウント管理・ブラウザプロファイル管理を拡張する形で実装
- **段階的導入**: プロキシなしでも動作し、プロキシ設定追加で分離機能が有効になる設計

---

## 2. システム構成

### 2.1 全体アーキテクチャ

```
┌─────────────────────────────────────────────────────────────────────┐
│  Host Machine (ローカルPC / 将来的にGCE)                              │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │  ecauto/ (既存プロジェクト)                                      │ │
│  │                                                               │ │
│  │  ┌─────────────────────────────────┐                         │ │
│  │  │  BASE API Runner                 │                         │ │
│  │  │  ・platforms/base/core/api_client.py (拡張)                │ │
│  │  │  ・アカウントごとにプロキシ切り替え                           │ │
│  │  │  ・Docker分離不要                                          │ │
│  │  └─────────────────────────────────┘                         │ │
│  │                                                               │ │
│  │  ┌─────────────────────────────────┐                         │ │
│  │  │  Yahoo Auction (Docker外で開発)   │                         │ │
│  │  │  ・platforms/yahoo_auction/ (新規)                         │ │
│  │  │  ・common/browser/profile_manager.py (既存活用)             │ │
│  │  └─────────────────────────────────┘                         │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐                        │
│  │ yahoo_01  │ │ yahoo_02  │ │ yahoo_03  │  ... (本番運用時)       │
│  │ Container │ │ Container │ │ Container │                        │
│  │ Playwright│ │ Playwright│ │ Playwright│                        │
│  │ Proxy A   │ │ Proxy B   │ │ Proxy C   │                        │
│  └───────────┘ └───────────┘ └───────────┘                        │
│        ↓             ↓             ↓                               │
│   住宅Proxy A   住宅Proxy B   住宅Proxy C                           │
│   (日本IP)      (日本IP)      (日本IP)                              │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 ディレクトリ構成（既存構造への統合）

```
ecauto/                                    # 既存プロジェクトルート
├── .env                                   # 環境変数（プロキシ認証情報追加）
├── .env.example                           # テンプレート更新
│
├── config/                                # グローバル設定（既存）
│   ├── proxies.json                       # 【新規】プロキシ一覧
│   ├── platforms.json                     # 【更新】yahoo設定追加
│   ├── pricing_strategy.yaml              # 既存
│   └── ...
│
├── common/                                # 共通ライブラリ（既存）
│   ├── browser/                           # 既存
│   │   ├── profile_manager.py             # 既存（Yahoo対応拡張）
│   │   └── README.md
│   └── proxy/                             # 【新規】プロキシ管理
│       ├── __init__.py
│       ├── proxy_manager.py               # プロキシ取得・検証
│       └── proxy_rotator.py               # アカウント-プロキシマッピング
│
├── platforms/                             # プラットフォーム別実装（既存）
│   ├── base/                              # 既存
│   │   ├── accounts/
│   │   │   ├── account_config.json        # 【更新】proxy_id追加
│   │   │   ├── account_config.json.example
│   │   │   └── tokens/
│   │   ├── core/
│   │   │   ├── api_client.py              # 【更新】プロキシ対応追加
│   │   │   └── ...
│   │   └── scripts/
│   │
│   ├── yahoo_auction/                     # 【新規】ヤフオク実装
│   │   ├── __init__.py
│   │   ├── accounts/
│   │   │   ├── account_config.json        # アカウント設定
│   │   │   ├── account_config.json.example
│   │   │   └── profiles/                  # Playwrightプロファイル
│   │   │       ├── yahoo_01/
│   │   │       ├── yahoo_02/
│   │   │       └── ...
│   │   ├── browser/
│   │   │   ├── __init__.py
│   │   │   └── session.py                 # Playwright セッション管理
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   └── automation.py              # ヤフオク自動化ロジック
│   │   ├── tasks/
│   │   │   ├── __init__.py
│   │   │   └── listing.py                 # 出品タスク
│   │   └── scripts/
│   │       ├── __init__.py
│   │       ├── login.py                   # 初回ログイン
│   │       └── verify_session.py          # セッション確認
│   │
│   ├── amazon_business/                   # 既存
│   ├── mercari_shops/                     # 既存
│   └── ebay/                              # 既存
│
├── deploy/                                # デプロイ関連（既存）
│   ├── windows/                           # 既存
│   └── docker/                            # 【新規】Docker関連
│       ├── docker-compose.yml             # ヤフオク用コンテナ定義
│       ├── docker-compose.override.yml    # ローカル開発用オーバーライド
│       ├── Dockerfile.yahoo               # ヤフオク用イメージ
│       └── scripts/
│           ├── start_container.sh         # 特定コンテナ起動
│           └── start_all.sh               # 全コンテナ起動
│
└── docs/
    └── plans/
        ├── multi-account-isolation-spec.md           # 元仕様
        └── multi-account-isolation-spec-reviewed.md  # 本ドキュメント
```

---

## 3. 設定ファイル仕様

### 3.1 プロキシ設定: `config/proxies.json`

```json
{
  "proxies": [
    {
      "id": "proxy_01",
      "url": "http://${PROXY_01_USER}:${PROXY_01_PASS}@proxy1.example.com:8080",
      "region": "JP",
      "type": "residential",
      "description": "住宅プロキシ1（日本）"
    },
    {
      "id": "proxy_02",
      "url": "http://${PROXY_02_USER}:${PROXY_02_PASS}@proxy2.example.com:8080",
      "region": "JP",
      "type": "residential",
      "description": "住宅プロキシ2（日本）"
    }
  ],
  "_comment": {
    "id": "一意のプロキシID（アカウント設定で参照）",
    "url": "プロキシURL（環境変数展開対応）",
    "region": "接続元リージョン",
    "type": "residential（住宅）/ datacenter（データセンター）"
  }
}
```

### 3.2 BASEアカウント設定: `platforms/base/accounts/account_config.json`

**既存スキーマへの追加フィールド:**

```json
{
  "accounts": [
    {
      "id": "base_account_1",
      "name": "在庫BAZAAR",
      "description": "メインアカウント",
      "active": true,
      "daily_upload_limit": 1000,
      "rate_limit_per_hour": 50,
      "proxy_id": "proxy_01",
      "credentials": {
        "client_id": "YOUR_CLIENT_ID_1",
        "client_secret": "YOUR_CLIENT_SECRET_1",
        "redirect_uri": "http://localhost:8000/callback"
      }
    },
    {
      "id": "base_account_2",
      "name": "バイヤー倉庫",
      "description": "サブアカウント",
      "active": true,
      "daily_upload_limit": 1000,
      "rate_limit_per_hour": 50,
      "proxy_id": "proxy_02",
      "credentials": {
        "client_id": "YOUR_CLIENT_ID_2",
        "client_secret": "YOUR_CLIENT_SECRET_2",
        "redirect_uri": "http://localhost:8000/callback"
      }
    }
  ]
}
```

**変更点:**
- `proxy_id` フィールド追加（オプション、未設定時はプロキシなしで動作）

### 3.3 Yahooアカウント設定: `platforms/yahoo_auction/accounts/account_config.json`

```json
{
  "accounts": [
    {
      "id": "yahoo_01",
      "name": "ヤフオクアカウント1",
      "description": "メインアカウント",
      "active": true,
      "proxy_id": "proxy_01",
      "yahoo_japan_id": "${YAHOO_01_ID}",
      "daily_listing_limit": 100,
      "profile_path": "platforms/yahoo_auction/accounts/profiles/yahoo_01"
    },
    {
      "id": "yahoo_02",
      "name": "ヤフオクアカウント2",
      "description": "サブアカウント",
      "active": true,
      "proxy_id": "proxy_02",
      "yahoo_japan_id": "${YAHOO_02_ID}",
      "daily_listing_limit": 100,
      "profile_path": "platforms/yahoo_auction/accounts/profiles/yahoo_02"
    }
  ],
  "_comment": {
    "proxy_id": "config/proxies.json のプロキシIDを参照",
    "yahoo_japan_id": "Yahoo! JAPAN ID（環境変数参照可）",
    "profile_path": "Playwrightプロファイルのパス"
  }
}
```

### 3.4 環境変数: `.env` への追加

```bash
# =====================================
# 既存の設定（変更なし）
# =====================================
# Amazon SP-API
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
SP_API_REFRESH_TOKEN=your_refresh_token

# BASE API
BASE_CLIENT_ID=your_client_id
BASE_CLIENT_SECRET=your_client_secret

# =====================================
# 【追加】プロキシ認証情報
# =====================================
PROXY_01_USER=proxy_user_1
PROXY_01_PASS=proxy_pass_1
PROXY_02_USER=proxy_user_2
PROXY_02_PASS=proxy_pass_2

# =====================================
# 【追加】Yahoo! JAPAN認証情報
# =====================================
YAHOO_01_ID=yahoo_user_1
YAHOO_02_ID=yahoo_user_2
```

---

## 4. コンポーネント実装仕様

### 4.1 プロキシマネージャー: `common/proxy/proxy_manager.py`

```python
"""
Proxy Manager

プロキシ設定の読み込みと管理を行う共通モジュール
"""

import os
import json
import re
from pathlib import Path
from typing import Dict, Any, Optional
import requests


class ProxyManager:
    """
    プロキシ管理クラス

    config/proxies.json からプロキシ設定を読み込み、
    環境変数を展開して使用可能な形式で提供する。
    """

    def __init__(self, config_path: str = None):
        """
        Args:
            config_path: プロキシ設定ファイルのパス（Noneの場合はデフォルト）
        """
        if config_path is None:
            # プロジェクトルートからの相対パス
            base_dir = Path(__file__).parent.parent.parent
            config_path = base_dir / "config" / "proxies.json"

        self.config_path = Path(config_path)
        self.proxies = self._load_config()

    def _load_config(self) -> Dict[str, Dict[str, Any]]:
        """プロキシ設定をロード"""
        if not self.config_path.exists():
            return {}

        with open(self.config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        # id をキーとした辞書に変換
        return {p['id']: p for p in config.get('proxies', [])}

    def _expand_env_vars(self, url: str) -> str:
        """URL内の環境変数を展開"""
        pattern = r'\$\{([^}]+)\}'

        def replace(match):
            var_name = match.group(1)
            return os.environ.get(var_name, '')

        return re.sub(pattern, replace, url)

    def get_proxy(self, proxy_id: str) -> Optional[Dict[str, str]]:
        """
        指定したIDのプロキシ設定を取得

        Args:
            proxy_id: プロキシID

        Returns:
            dict: requests用のproxies辞書 {'http': url, 'https': url}
                  存在しない場合はNone
        """
        if proxy_id not in self.proxies:
            return None

        proxy = self.proxies[proxy_id]
        url = self._expand_env_vars(proxy['url'])

        return {
            'http': url,
            'https': url
        }

    def get_proxy_for_playwright(self, proxy_id: str) -> Optional[Dict[str, str]]:
        """
        Playwright用のプロキシ設定を取得

        Args:
            proxy_id: プロキシID

        Returns:
            dict: Playwright用のproxy設定 {'server': url}
        """
        if proxy_id not in self.proxies:
            return None

        proxy = self.proxies[proxy_id]
        url = self._expand_env_vars(proxy['url'])

        return {'server': url}

    def verify_proxy(self, proxy_id: str, timeout: int = 10) -> bool:
        """
        プロキシの接続を検証

        Args:
            proxy_id: プロキシID
            timeout: タイムアウト秒数

        Returns:
            bool: 接続成功時True
        """
        proxies = self.get_proxy(proxy_id)
        if not proxies:
            return False

        try:
            # IPアドレス確認サービスに接続
            response = requests.get(
                'https://api.ipify.org?format=json',
                proxies=proxies,
                timeout=timeout
            )
            return response.ok
        except Exception:
            return False

    def list_proxies(self) -> list:
        """全プロキシIDのリストを取得"""
        return list(self.proxies.keys())
```

### 4.2 BASE APIクライアント拡張: `platforms/base/core/api_client.py`

**既存クラスへの変更点:**

```python
# 追加インポート
import sys
from pathlib import Path

# common/proxy を参照可能にする
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
from common.proxy.proxy_manager import ProxyManager


class BaseAPIClient:
    """
    BASE APIクライアントクラス（自動トークン更新 + プロキシ対応）
    """

    BASE_URL = "https://api.thebase.in/1"

    def __init__(
        self,
        access_token: str = None,
        account_id: str = None,
        account_manager: Optional['AccountManager'] = None,
        proxy_id: str = None  # 【追加】プロキシID
    ):
        """
        Args:
            access_token: BASE APIのアクセストークン（直接指定の場合）
            account_id: アカウントID（AccountManager経由の場合）
            account_manager: AccountManagerインスタンス
            proxy_id: プロキシID（config/proxies.jsonのID）
        """
        self.account_id = account_id
        self.account_manager = account_manager
        self.access_token = access_token

        # 【追加】プロキシ設定
        self.proxies = None
        if proxy_id:
            proxy_manager = ProxyManager()
            self.proxies = proxy_manager.get_proxy(proxy_id)
        elif account_id and account_manager:
            # アカウント設定からproxy_idを取得
            account = account_manager.get_account(account_id)
            if account and account.get('proxy_id'):
                proxy_manager = ProxyManager()
                self.proxies = proxy_manager.get_proxy(account['proxy_id'])

        # 以下、既存のトークン取得処理...
        if account_id and account_manager:
            token_data = account_manager.get_token_with_auto_refresh(account_id)
            if token_data:
                self.access_token = token_data['access_token']
            else:
                raise ValueError(f"アカウント {account_id} の有効なトークンを取得できませんでした")

        if not self.access_token:
            raise ValueError("access_token または (account_id + account_manager) が必要です")

        self.headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        """
        【追加】共通リクエストメソッド（プロキシ対応）
        """
        # プロキシ設定を追加
        if self.proxies:
            kwargs['proxies'] = self.proxies

        kwargs.setdefault('timeout', 30)

        return requests.request(method, url, **kwargs)

    def create_item(self, item_data: Dict[str, Any]) -> Dict[str, Any]:
        """商品を作成（プロキシ対応版）"""
        self._refresh_token_if_needed()

        url = f"{self.BASE_URL}/items/add"
        response = self._request('POST', url, headers=self.headers, data=item_data)

        if not response.ok:
            # エラーハンドリング...
            response.raise_for_status()

        return response.json()

    # 他のメソッドも同様に self._request() を使用するよう変更
```

### 4.3 Yahooセッション管理: `platforms/yahoo_auction/browser/session.py`

```python
"""
Yahoo Auction Session Manager

Playwrightを使用したYahoo!オークションのセッション管理
"""

import os
import sys
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
from common.proxy.proxy_manager import ProxyManager
from common.browser.profile_manager import ProfileManager


class YahooAuctionSession:
    """
    Yahoo!オークション セッション管理クラス

    - プロキシ経由での接続
    - Playwrightプロファイルの永続化
    - WebRTC無効化などのフィンガープリント対策
    """

    PLATFORM = "yahoo_auction"

    def __init__(
        self,
        account_id: str,
        proxy_id: Optional[str] = None,
        headless: bool = True
    ):
        """
        Args:
            account_id: アカウントID（例: "yahoo_01"）
            proxy_id: プロキシID（Noneの場合はプロキシなし）
            headless: ヘッドレスモード
        """
        self.account_id = account_id
        self.proxy_id = proxy_id
        self.headless = headless

        # マネージャー初期化
        self.profile_manager = ProfileManager()
        self.proxy_manager = ProxyManager() if proxy_id else None

        # Playwright関連
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    @property
    def profile_path(self) -> Path:
        """プロファイルパスを取得"""
        return self.profile_manager.get_profile_path(self.PLATFORM, self.account_id)

    def _get_browser_args(self) -> list:
        """ブラウザ起動引数を取得"""
        return [
            "--disable-webrtc",
            "--disable-features=WebRtcHideLocalIpsWithMdns",
            "--disable-blink-features=AutomationControlled",
        ]

    def _get_proxy_config(self) -> Optional[dict]:
        """プロキシ設定を取得"""
        if not self.proxy_id or not self.proxy_manager:
            return None
        return self.proxy_manager.get_proxy_for_playwright(self.proxy_id)

    def start(self) -> Page:
        """
        ブラウザセッションを開始

        Returns:
            Page: Playwrightページオブジェクト
        """
        # プロファイルディレクトリを作成
        self.profile_manager.create_profile(self.PLATFORM, self.account_id)

        self._playwright = sync_playwright().start()

        # 起動オプション
        launch_options = {
            "headless": self.headless,
            "args": self._get_browser_args(),
        }

        # プロキシ設定
        proxy_config = self._get_proxy_config()
        if proxy_config:
            launch_options["proxy"] = proxy_config

        # persistent_contextでプロファイルを永続化
        self._context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_path),
            **launch_options,
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            viewport={"width": 1280, "height": 720},
        )

        # 既存のページがあれば使用、なければ新規作成
        if self._context.pages:
            self._page = self._context.pages[0]
        else:
            self._page = self._context.new_page()

        return self._page

    def stop(self):
        """ブラウザセッションを終了"""
        if self._context:
            self._context.close()
            self._context = None

        if self._playwright:
            self._playwright.stop()
            self._playwright = None

        self._page = None

    def __enter__(self) -> Page:
        return self.start()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    def is_logged_in(self) -> bool:
        """ログイン状態を確認"""
        if not self._page:
            return False

        try:
            # Yahoo!オークションのマイページにアクセス
            self._page.goto("https://auctions.yahoo.co.jp/user/jp/show/mystatus")

            # ログインページにリダイレクトされたかチェック
            if "login.yahoo.co.jp" in self._page.url:
                return False

            return True
        except Exception:
            return False
```

---

## 5. Docker構成（本番運用時）

### 5.1 Dockerfile: `deploy/docker/Dockerfile.yahoo`

```dockerfile
# Yahoo!オークション自動化用Dockerイメージ
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# タイムゾーン設定
ENV TZ=Asia/Tokyo
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 日本語フォントインストール
RUN apt-get update && apt-get install -y \
    fonts-ipafont-gothic \
    fonts-ipafont-mincho \
    && rm -rf /var/lib/apt/lists/*

# 作業ディレクトリ
WORKDIR /app

# 依存関係インストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwrightブラウザインストール
RUN playwright install chromium

# アプリケーションコードコピー
COPY . .

# プロファイルディレクトリ
VOLUME ["/app/profiles"]

# エントリーポイント
ENTRYPOINT ["python", "-m", "platforms.yahoo_auction.scripts.entrypoint"]
```

### 5.2 docker-compose.yml: `deploy/docker/docker-compose.yml`

```yaml
version: '3.8'

services:
  yahoo_01:
    build:
      context: ../..
      dockerfile: deploy/docker/Dockerfile.yahoo
    container_name: ecauto-yahoo-01
    environment:
      - ACCOUNT_ID=yahoo_01
      - PROXY_URL=${PROXY_01_URL}
      - YAHOO_JAPAN_ID=${YAHOO_01_ID}
      - HEADLESS=true
    volumes:
      - ../../platforms/yahoo_auction/accounts/profiles/yahoo_01:/app/profiles
    networks:
      - yahoo_net_01
    restart: unless-stopped

  yahoo_02:
    build:
      context: ../..
      dockerfile: deploy/docker/Dockerfile.yahoo
    container_name: ecauto-yahoo-02
    environment:
      - ACCOUNT_ID=yahoo_02
      - PROXY_URL=${PROXY_02_URL}
      - YAHOO_JAPAN_ID=${YAHOO_02_ID}
      - HEADLESS=true
    volumes:
      - ../../platforms/yahoo_auction/accounts/profiles/yahoo_02:/app/profiles
    networks:
      - yahoo_net_02
    restart: unless-stopped

networks:
  yahoo_net_01:
    driver: bridge
  yahoo_net_02:
    driver: bridge
```

---

## 6. 実装フェーズ

### Phase 1: プロキシ基盤（1-2日）
1. `config/proxies.json` 作成
2. `common/proxy/proxy_manager.py` 実装
3. プロキシ接続検証スクリプト作成

### Phase 2: BASE API プロキシ対応（1日）
1. `platforms/base/accounts/account_config.json` に `proxy_id` 追加
2. `platforms/base/core/api_client.py` にプロキシ対応追加
3. 既存スクリプトの動作確認

### Phase 3: Yahoo基本実装（2-3日）
1. `platforms/yahoo_auction/` ディレクトリ構造作成
2. `browser/session.py` 実装（プロキシ + プロファイル永続化）
3. `scripts/login.py`, `scripts/verify_session.py` 実装
4. ローカル環境での動作確認

### Phase 4: Docker化（2-3日）
1. `deploy/docker/Dockerfile.yahoo` 作成
2. `deploy/docker/docker-compose.yml` 作成
3. コンテナビルド・起動テスト
4. プロファイル永続化の確認

### Phase 5: Yahoo自動化ロジック（継続）
1. 出品機能実装
2. 在庫管理連携
3. master.db との統合

---

## 7. 分離要素チェックリスト

| 要素 | BASE API | ヤフオク（Docker） | 対策 |
|------|----------|------------------|------|
| IPアドレス | ✅ | ✅ | 住宅プロキシ（アカウント固定） |
| MACアドレス | N/A | ✅ | Dockerが自動分離 |
| ブラウザフィンガープリント | N/A | ✅ | コンテナ分離 + stealth |
| Cookie/Session | N/A | ✅ | プロファイル分離 |
| WebRTC (Local IP) | N/A | ✅ | 起動オプションで無効化 |
| User-Agent | N/A | ✅ | デフォルト or ランダム化 |
| タイムゾーン | N/A | ✅ | Asia/Tokyo 固定 |
| 言語設定 | N/A | ✅ | ja-JP 固定 |

---

## 8. 運用注意事項

### 8.1 プロキシ障害時の動作
- プロキシ接続失敗時は該当アカウントの処理をスキップ
- **フォールバックで別IPに接続しない**（アカウント紐付けリスク）
- エラーログを記録し、手動確認を促す

### 8.2 同一IPからの複数アカウントログイン厳禁
- Yahoo!オークションは特に厳格
- 各コンテナは専用プロキシを経由
- ホストPCのブラウザからのログインは禁止

### 8.3 手動確認時の運用
- デバッグ時は `headless=False` でブラウザ表示
- または該当コンテナにattachして操作
- ホストのChromeは使用しない

---

## 9. 関連ドキュメント

- [元仕様書](./multi-account-isolation-spec.md)
- [BASEアカウント管理](../../platforms/base/README.md)
- [ブラウザ自動化基盤](../../common/browser/README.md)
- [Amazon Business実装例](../../platforms/amazon_business/README.md)
