# マルチアカウント分離環境 実装記録

> **仕様書**: [multi-account-isolation-spec.md](./multi-account-isolation-spec.md)
> **レビュー版**: [multi-account-isolation-spec-reviewed.md](./multi-account-isolation-spec-reviewed.md)
> **実装日**: 2024-12-11
> **ステータス**: Phase 1-3 完了（基盤実装）

---

## 実装サマリー

| タスク | 内容 | ステータス |
|--------|------|-----------|
| Task 1 | プロキシ設定ファイル作成 | ✅ 完了 |
| Task 2 | プロキシ管理モジュール | ✅ 完了 |
| Task 3 | BASE API クライアント拡張 | ✅ 完了 |
| Task 4 | Yahoo Auction ディレクトリ構造 | ✅ 完了 |
| Task 5 | Yahoo セッション管理 | ✅ 完了 |
| Task 6 | Yahoo ログイン・検証スクリプト | ✅ 完了 |
| Task 7 | Docker構成 | ✅ 完了 |

---

## 1. 作成・更新ファイル一覧

### 1.1 プロキシ基盤

| ファイル | 状態 | 説明 |
|---------|------|------|
| `config/proxies.json` | 新規 | プロキシ設定（実運用用） |
| `config/proxies.json.example` | 新規 | プロキシ設定テンプレート |
| `common/proxy/__init__.py` | 新規 | モジュール初期化 |
| `common/proxy/proxy_manager.py` | 新規 | プロキシ管理クラス |
| `.env.example` | 更新 | プロキシ・Yahoo認証情報追加 |
| `.gitignore` | 更新 | Yahoo関連・プロキシ設定除外追加 |

### 1.2 BASE API 拡張

| ファイル | 状態 | 説明 |
|---------|------|------|
| `platforms/base/core/api_client.py` | 更新 | プロキシ対応追加 |
| `platforms/base/accounts/account_config.json.example` | 更新 | `proxy_id`フィールド追加 |

### 1.3 Yahoo Auction 実装

| ファイル | 状態 | 説明 |
|---------|------|------|
| `platforms/yahoo_auction/__init__.py` | 新規 | モジュール初期化 |
| `platforms/yahoo_auction/browser/__init__.py` | 新規 | ブラウザモジュール初期化 |
| `platforms/yahoo_auction/browser/session.py` | 新規 | Playwrightセッション管理 |
| `platforms/yahoo_auction/core/__init__.py` | 新規 | コアモジュール初期化 |
| `platforms/yahoo_auction/core/automation.py` | 新規 | 自動化ロジック（スケルトン） |
| `platforms/yahoo_auction/tasks/__init__.py` | 新規 | タスクモジュール初期化 |
| `platforms/yahoo_auction/scripts/__init__.py` | 新規 | スクリプトモジュール初期化 |
| `platforms/yahoo_auction/scripts/login.py` | 新規 | 初回ログインスクリプト |
| `platforms/yahoo_auction/scripts/verify_session.py` | 新規 | セッション確認スクリプト |
| `platforms/yahoo_auction/accounts/account_config.json.example` | 新規 | アカウント設定テンプレート |
| `platforms/yahoo_auction/accounts/profiles/.gitkeep` | 新規 | プロファイルディレクトリ保持 |

### 1.4 Docker 構成

| ファイル | 状態 | 説明 |
|---------|------|------|
| `deploy/docker/Dockerfile.yahoo` | 新規 | Yahoo用Dockerイメージ |
| `deploy/docker/docker-compose.yml` | 新規 | マルチアカウントコンテナ定義 |
| `deploy/docker/scripts/start_container.sh` | 新規 | コンテナ起動スクリプト |

### 1.5 設定ファイル更新

| ファイル | 状態 | 説明 |
|---------|------|------|
| `config/platforms.json` | 更新 | `yahoo_auction`設定追加 |

---

## 2. 実装詳細

### 2.1 ProxyManager クラス

**場所**: `common/proxy/proxy_manager.py`

**主要機能**:
- `config/proxies.json` からプロキシ設定を読み込み
- `${ENV_VAR}` 形式の環境変数を展開
- requests用: `get_proxy(proxy_id)` → `{'http': url, 'https': url}`
- Playwright用: `get_proxy_for_playwright(proxy_id)` → `{'server': ..., 'username': ..., 'password': ...}`
- 接続検証: `verify_proxy(proxy_id)` → `bool`

**使用例**:
```python
from common.proxy import ProxyManager

pm = ProxyManager()
print(pm.list_proxies())  # ['proxy_01', 'proxy_02']

# requests用
proxies = pm.get_proxy('proxy_01')
response = requests.get(url, proxies=proxies)

# Playwright用
proxy_config = pm.get_proxy_for_playwright('proxy_01')
# {'server': 'http://host:port', 'username': 'user', 'password': 'pass'}
```

### 2.2 BaseAPIClient プロキシ対応

**場所**: `platforms/base/core/api_client.py`

**変更点**:
1. コンストラクタに `proxy_id` パラメータ追加
2. `account_config.json` の `proxy_id` を自動読み取り
3. 共通 `_request()` メソッドでプロキシ適用

**後方互換性**:
- `proxy_id` 未設定時はプロキシなしで動作
- 既存コードの変更不要

**使用例**:
```python
# 従来通り（プロキシなし）
client = BaseAPIClient(access_token="xxx")

# プロキシ明示指定
client = BaseAPIClient(access_token="xxx", proxy_id="proxy_01")

# AccountManager経由（account_config.jsonのproxy_idを自動使用）
client = BaseAPIClient(account_id="base_account_1", account_manager=manager)
```

### 2.3 YahooAuctionSession クラス

**場所**: `platforms/yahoo_auction/browser/session.py`

**主要機能**:
- Playwright `launch_persistent_context` によるセッション永続化
- プロキシ経由接続（ProxyManager連携）
- WebRTC無効化（ローカルIP漏洩防止）
- タイムゾーン: Asia/Tokyo、ロケール: ja-JP 固定

**使用例**:
```python
from platforms.yahoo_auction.browser.session import YahooAuctionSession

# コンテキストマネージャ
with YahooAuctionSession(account_id="yahoo_01", proxy_id="proxy_01") as page:
    page.goto("https://auctions.yahoo.co.jp/")

# 明示的開始/終了
session = YahooAuctionSession(account_id="yahoo_01", headless=False)
page = session.start()
try:
    if session.is_logged_in():
        print("ログイン済み")
finally:
    session.stop()
```

### 2.4 Docker構成

**Dockerfile.yahoo**:
- ベース: `mcr.microsoft.com/playwright/python:v1.40.0-jammy`
- 日本語フォント: fonts-ipafont-gothic, fonts-noto-cjk
- タイムゾーン: Asia/Tokyo
- Playwrightブラウザ: Chromium

**docker-compose.yml**:
- サービス: `yahoo_01`, `yahoo_02`
- ボリューム: プロファイルディレクトリをマウント
- 環境変数: `PROXY_URL`, `YAHOO_JAPAN_ID`, `HEADLESS`

---

## 3. 使用方法

### 3.1 初期設定

```bash
# 1. プロキシ設定
cp config/proxies.json.example config/proxies.json
# config/proxies.json を編集（プロキシURLを設定）

# 2. 環境変数設定
# .env にプロキシ認証情報を追加
PROXY_01_USER=your_user
PROXY_01_PASS=your_pass

# 3. Yahooアカウント設定
cp platforms/yahoo_auction/accounts/account_config.json.example \
   platforms/yahoo_auction/accounts/account_config.json
# account_config.json を編集
```

### 3.2 プロキシ接続確認

```bash
# プロキシ一覧表示
venv/bin/python -c "from common.proxy import ProxyManager; ProxyManager().print_summary()"

# 接続検証（実際のプロキシが設定されている場合）
venv/bin/python common/proxy/proxy_manager.py proxy_01
```

### 3.3 Yahoo ログイン

```bash
# 初回ログイン（ブラウザ表示）
venv/bin/python -m platforms.yahoo_auction.scripts.login --account-id yahoo_01

# プロキシ指定
venv/bin/python -m platforms.yahoo_auction.scripts.login \
  --account-id yahoo_01 \
  --proxy-id proxy_01

# セッション確認
venv/bin/python -m platforms.yahoo_auction.scripts.verify_session --account-id yahoo_01
```

### 3.4 Docker起動

```bash
cd deploy/docker

# 単一コンテナ起動
./scripts/start_container.sh yahoo_01

# イメージ再ビルド
./scripts/start_container.sh yahoo_01 --build

# 全コンテナ起動
./scripts/start_container.sh --all

# ログ確認
./scripts/start_container.sh --logs yahoo_01

# 停止
./scripts/start_container.sh --stop yahoo_01
```

---

## 4. 設定ファイル形式

### 4.1 config/proxies.json

```json
{
  "proxies": [
    {
      "id": "proxy_01",
      "url": "http://${PROXY_01_USER}:${PROXY_01_PASS}@proxy1.example.com:8080",
      "region": "JP",
      "type": "residential",
      "description": "住宅プロキシ1（日本）"
    }
  ]
}
```

### 4.2 platforms/base/accounts/account_config.json

```json
{
  "accounts": [
    {
      "id": "base_account_1",
      "name": "BASE本店",
      "active": true,
      "proxy_id": "proxy_01",
      "credentials": { ... }
    }
  ]
}
```

### 4.3 platforms/yahoo_auction/accounts/account_config.json

```json
{
  "accounts": [
    {
      "id": "yahoo_01",
      "name": "ヤフオクアカウント1",
      "active": true,
      "proxy_id": "proxy_01",
      "yahoo_japan_id": "${YAHOO_01_ID}",
      "daily_listing_limit": 100,
      "profile_path": "platforms/yahoo_auction/accounts/profiles/yahoo_01"
    }
  ]
}
```

---

## 5. 残作業・今後の実装

### 5.1 Phase 4: Yahoo自動化ロジック（未実装）

| 機能 | ファイル | ステータス |
|------|---------|-----------|
| 出品機能 | `core/automation.py` | スケルトンのみ |
| 在庫管理 | `tasks/inventory.py` | 未作成 |
| 価格更新 | `tasks/pricing.py` | 未作成 |
| master.db連携 | - | 未実装 |

### 5.2 Phase 5: 本番運用準備

- [ ] 実際のプロキシサービス契約・設定
- [ ] Yahoo各アカウントの初回ログイン実施
- [ ] Docker本番環境構築（GCE等）
- [ ] 監視・アラート設定

### 5.3 将来的な拡張

- [ ] メルカリ対応（同様のDocker分離）
- [ ] スケール時のdocker-compose動的生成
- [ ] Kubernetes移行検討

---

## 6. 分離要素チェックリスト

| 要素 | BASE API | Yahoo Auction | 実装状況 |
|------|----------|---------------|----------|
| IPアドレス | ✅ プロキシ | ✅ プロキシ | 完了 |
| MACアドレス | N/A | ✅ Docker分離 | 完了 |
| ブラウザFP | N/A | ✅ プロファイル分離 | 完了 |
| Cookie/Session | N/A | ✅ 永続化 | 完了 |
| WebRTC | N/A | ✅ 無効化 | 完了 |
| タイムゾーン | N/A | ✅ Asia/Tokyo | 完了 |
| 言語設定 | N/A | ✅ ja-JP | 完了 |

---

## 7. 関連ドキュメント

- [元仕様書](./multi-account-isolation-spec.md)
- [レビュー版仕様書](./multi-account-isolation-spec-reviewed.md)
- [BASEアカウント管理](../../platforms/base/README.md)
- [ブラウザ自動化基盤](../../common/browser/README.md)
