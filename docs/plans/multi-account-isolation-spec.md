# マルチアカウント分離環境 技術仕様書

## 1. 概要

### 1.1 目的
BASE および Yahoo!オークション（ヤフオク）の複数アカウント運用において、各アカウントの接続元を完全に分離し、プラットフォーム側からの関連付けを防止する。

### 1.2 対象プラットフォーム
| プラットフォーム | 通信方式 | 分離方式 |
|-----------------|---------|---------|
| BASE | API通信 | プロキシ切り替えのみ |
| ヤフオク | Playwright（ブラウザ自動化） | Docker + プロキシ |

### 1.3 スケール目標
- Phase 1: 10アカウント（ローカルPC）
- Phase 2: 数十アカウント（GCP移行検討）

---

## 2. システム構成

### 2.1 全体アーキテクチャ

```
┌─────────────────────────────────────────────────────────────┐
│  Host Machine (ローカルPC / 将来的にGCE)                      │
│                                                             │
│  ┌─────────────────────────────────────┐                   │
│  │  BASE API Runner                     │                   │
│  │  ・単一Pythonプロセス                  │                   │
│  │  ・アカウントごとにプロキシ切り替え       │                   │
│  │  ・Docker分離不要                     │                   │
│  └─────────────────────────────────────┘                   │
│                                                             │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐                │
│  │ yahoo_01  │ │ yahoo_02  │ │ yahoo_03  │  ...           │
│  │ Container │ │ Container │ │ Container │                │
│  │ Playwright│ │ Playwright│ │ Playwright│                │
│  │ Proxy A   │ │ Proxy B   │ │ Proxy C   │                │
│  │ Profile A │ │ Profile B │ │ Profile C │                │
│  └───────────┘ └───────────┘ └───────────┘                │
│        ↓             ↓             ↓                       │
│   住宅Proxy A   住宅Proxy B   住宅Proxy C                   │
│   (日本IP)      (日本IP)      (日本IP)                      │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 ディレクトリ構成

```
multi-account-system/
├── docker-compose.yml          # ヤフオク用コンテナ定義
├── Dockerfile.yahoo            # ヤフオク用Dockerイメージ
├── .env                        # 環境変数（プロキシ認証情報等）
├── .env.example                # 環境変数テンプレート
│
├── config/
│   ├── accounts.yml            # アカウント設定（ID、プロキシ割当）
│   └── proxies.yml             # プロキシ一覧
│
├── base_api/
│   ├── __init__.py
│   ├── client.py               # BASE API クライアント（プロキシ対応）
│   └── account_manager.py      # アカウント切り替えロジック
│
├── yahoo/
│   ├── __init__.py
│   ├── browser.py              # Playwright ブラウザ管理
│   ├── automation.py           # ヤフオク自動化ロジック
│   └── entrypoint.py           # コンテナ起動スクリプト
│
├── shared/
│   ├── __init__.py
│   ├── proxy_manager.py        # プロキシ管理共通モジュール
│   └── config_loader.py        # 設定読み込み
│
├── data/
│   └── yahoo_profiles/         # Playwrightプロファイル永続化
│       ├── yahoo_01/
│       ├── yahoo_02/
│       └── ...
│
└── scripts/
    ├── start_yahoo_container.sh    # 特定コンテナ起動
    ├── start_all.sh                # 全コンテナ起動
    └── setup_profiles.sh           # 初期プロファイル作成
```

---

## 3. コンポーネント詳細

### 3.1 BASE API クライアント

#### 要件
- Docker分離不要（API通信のためフィンガープリント検知なし）
- リクエストごとにアカウントに紐づくプロキシを使用
- 認証トークンはアカウント別に管理

#### 設計
```python
# 呼び出しイメージ
client = BaseApiClient(account_id="base_01")
client.create_product(product_data)  # 自動的に対応プロキシ経由
```

#### プロキシ設定方式
- `requests` ライブラリの `proxies` パラメータで切り替え
- アカウントIDとプロキシのマッピングは `config/accounts.yml` で管理

---

### 3.2 ヤフオク用 Docker コンテナ

#### 要件
- コンテナ単位で完全分離（IP、フィンガープリント、セッション）
- Playwrightブラウザプロファイルを永続化（再ログイン回避）
- 各コンテナに固定の住宅プロキシを割り当て
- MACアドレスはDockerが自動的に分離

#### Dockerfile 要件
- ベースイメージ: `mcr.microsoft.com/playwright/python:v1.40.0-jammy` 等
- Python 3.11+
- Playwright + Chromium
- 日本語フォント（IPAフォント等）
- タイムゾーン: Asia/Tokyo

#### docker-compose.yml 要件
- サービス名: `yahoo_01`, `yahoo_02`, ... （アカウントIDと一致）
- 環境変数でプロキシ情報を注入
- プロファイルディレクトリをボリュームマウント
- ネットワーク: 各コンテナは独立（bridge mode）

#### コンテナ起動パターン
```bash
# 特定アカウントのコンテナのみ起動
docker compose up yahoo_01

# 全コンテナ起動
docker compose up

# 特定コンテナでインタラクティブ操作（デバッグ用）
docker compose run --rm yahoo_01 bash
```

---

### 3.3 Playwright ブラウザ管理

#### 要件
- ヘッドレスモード（本番）/ ヘッド有りモード（デバッグ）切り替え可能
- プロキシはコンテナの環境変数から取得
- ブラウザプロファイル（Cookie、LocalStorage）を永続化
- WebRTC無効化（ローカルIP漏洩防止）
- フィンガープリント対策（playwright-stealth または同等の対策）

#### プロファイル永続化
```
data/yahoo_profiles/yahoo_01/  → コンテナ内 /app/profile にマウント
```

#### 起動オプション（必須）
```python
browser.launch(
    proxy={"server": os.environ["PROXY_URL"]},
    args=[
        "--disable-webrtc",
        "--disable-features=WebRtcHideLocalIpsWithMdns",
    ]
)
context.new_context(
    storage_state="profile/state.json",  # セッション復元
    locale="ja-JP",
    timezone_id="Asia/Tokyo",
)
```

---

### 3.4 設定ファイル

#### config/accounts.yml
```yaml
base:
  - id: base_01
    proxy_id: proxy_01
    access_token: ${BASE_01_TOKEN}  # 環境変数参照
  - id: base_02
    proxy_id: proxy_02
    access_token: ${BASE_02_TOKEN}

yahoo:
  - id: yahoo_01
    proxy_id: proxy_01
    yahoo_japan_id: ${YAHOO_01_ID}
  - id: yahoo_02
    proxy_id: proxy_02
    yahoo_japan_id: ${YAHOO_02_ID}
```

#### config/proxies.yml
```yaml
proxies:
  - id: proxy_01
    url: http://${PROXY_01_USER}:${PROXY_01_PASS}@proxy1.example.com:port
    region: JP
  - id: proxy_02
    url: http://${PROXY_02_USER}:${PROXY_02_PASS}@proxy2.example.com:port
    region: JP
```

#### .env.example
```bash
# Proxy credentials
PROXY_01_USER=user1
PROXY_01_PASS=pass1
PROXY_02_USER=user2
PROXY_02_PASS=pass2

# BASE tokens
BASE_01_TOKEN=xxxxxxxx
BASE_02_TOKEN=xxxxxxxx

# Yahoo credentials (if needed)
YAHOO_01_ID=yahoo_user_1
YAHOO_02_ID=yahoo_user_2
```

---

## 4. 分離要素チェックリスト

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

## 5. 運用考慮事項

### 5.1 ヤフオク特有の注意
- **同一IPからの複数アカウントログイン厳禁**
- アカウント作成時と運用時のIPは一致させる
- ログイン時間、操作間隔にランダム性を持たせる
- 出品数、取引パターンを自然に分散

### 5.2 プロキシ障害時
- プロキシ接続失敗時は該当アカウントの処理をスキップ
- フォールバックで別IPに接続しない（アカウント紐付けリスク）

### 5.3 手動確認時の運用
- デバッグ時は該当コンテナにattachして操作
- または `HEADLESS=false` でブラウザ表示
- ホストのChromeは使用しない（プロキシ設定ミスリスク）

---

## 6. 将来拡張

### 6.1 GCP移行時
- GCE (e2-medium以上) に Docker 環境を構築
- ローカルと同一の docker-compose.yml を使用
- プロファイルデータは GCS または永続ディスクに保存

### 6.2 スケール時（20アカウント以上）
- docker-compose.yml の動的生成スクリプト
- コンテナオーケストレーション検討（Docker Swarm / Kubernetes）
