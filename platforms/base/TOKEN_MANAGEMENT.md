# BASE トークン管理ガイド

## 概要

BASE APIの認証トークンを自動管理する機能を提供します。

### 主な機能

- **OAuth 2.0 認証フロー**: 初回認証とトークン取得
- **自動トークン更新**: リフレッシュトークンを使った自動更新
- **トークン有効期限管理**: 期限切れの自動検知と更新
- **複数アカウント対応**: 各アカウントごとにトークンを個別管理

## トークンのライフサイクル

```
1. 初回認証
   └→ 認証URLでブラウザ認証
      └→ 認証コードを取得
         └→ トークン取得（access_token + refresh_token）

2. API呼び出し
   └→ トークン有効期限チェック
      ├→ [有効期限内] そのまま使用
      └→ [期限切れ間近/期限切れ] 自動更新
         └→ refresh_tokenで新トークン取得

3. 定期更新（推奨）
   └→ cronやタスクスケジューラで定期実行
      └→ 全アカウントのトークンを一括更新
```

## セットアップ

### 1. アカウント設定

`platforms/base/accounts/account_config.json` を作成:

```json
{
  "accounts": [
    {
      "id": "base_account_1",
      "name": "BASE本店",
      "description": "メインアカウント",
      "active": true,
      "daily_upload_limit": 1000,
      "rate_limit_per_hour": 50,
      "credentials": {
        "client_id": "YOUR_CLIENT_ID",
        "client_secret": "YOUR_CLIENT_SECRET",
        "redirect_uri": "http://localhost:8000/callback"
      }
    }
  ]
}
```

### 2. 初回認証

各アカウントで初回認証を実行:

```bash
python platforms/base/scripts/get_authorization_code.py
```

**手順:**

1. アカウント番号を選択
2. 表示された認証URLをブラウザで開く
3. BASE アカウントで認証
4. リダイレクト先URLから `code=` パラメータの値をコピー
5. スクリプトに認証コードを入力
6. トークンが自動取得・保存される

**保存先:** `platforms/base/accounts/tokens/{account_id}_token.json`

### 3. トークン状態確認

全アカウントのトークン状態を確認:

```bash
python platforms/base/scripts/check_token_status.py
```

**表示内容:**
- アカウントごとのトークン有無
- 有効期限（残り時間）
- 期限切れ警告
- 要対応アカウント一覧

## 使用方法

### 方法1: BaseAPIClient（自動更新あり）

```python
from accounts.manager import AccountManager
from core.api_client import BaseAPIClient

# AccountManager経由で自動更新機能を有効化
manager = AccountManager()

# APIクライアントを作成（自動更新機能ON）
client = BaseAPIClient(
    account_id='base_account_1',
    account_manager=manager
)

# API呼び出し時に自動的にトークンをチェック・更新
response = client.get_items(limit=10)
```

**メリット:**
- トークン有効期限を意識する必要なし
- 期限切れ時に自動更新
- スケジューラ・デーモンでの長時間実行に最適

### 方法2: BaseAPIClient（アクセストークン直接指定）

```python
from core.api_client import BaseAPIClient

# アクセストークンを直接指定（自動更新なし）
client = BaseAPIClient(access_token='YOUR_ACCESS_TOKEN')

# API呼び出し
response = client.get_items(limit=10)
```

**注意:** この方法では自動更新されません。短時間の処理のみ推奨。

### 方法3: 手動トークン管理

```python
from accounts.manager import AccountManager

manager = AccountManager()

# トークンを取得（自動更新付き）
token = manager.get_token_with_auto_refresh('base_account_1')
access_token = token['access_token']

# 手動でトークン更新が必要な場合
success = manager.refresh_token_if_needed('base_account_1', force=True)
```

## トークン自動更新

### 定期更新スクリプト

全アカウントのトークンを一括更新:

```bash
python platforms/base/scripts/refresh_tokens.py
```

**推奨設定:**
- 実行頻度: 1日1回（深夜など）
- 対象: アクティブなアカウントのみ
- 終了コード: 失敗時は1を返す（監視可能）

### Windows タスクスケジューラ設定例

```
タスク名: BASE Token Refresh
トリガー: 毎日 午前3時
操作: プログラムの開始
  プログラム: C:\path\to\python.exe
  引数: C:\Users\hiroo\Documents\GitHub\ecauto\platforms\base\scripts\refresh_tokens.py
  開始: C:\Users\hiroo\Documents\GitHub\ecauto
```

### Linux/Mac cron設定例

```cron
# 毎日午前3時にトークン更新
0 3 * * * cd /path/to/ecauto && python platforms/base/scripts/refresh_tokens.py
```

## トークンファイル形式

`platforms/base/accounts/tokens/base_account_1_token.json`:

```json
{
  "access_token": "ACCESS_TOKEN_STRING",
  "refresh_token": "REFRESH_TOKEN_STRING",
  "token_type": "Bearer",
  "expires_in": 3600,
  "obtained_at": "2025-11-19T10:30:00",
  "expires_at": "2025-11-19T11:30:00"
}
```

**フィールド説明:**
- `access_token`: API呼び出しに使用
- `refresh_token`: トークン更新に使用
- `expires_in`: 有効期限（秒）
- `obtained_at`: 取得日時（ISO形式）
- `expires_at`: 期限切れ日時（ISO形式）

## トラブルシューティング

### トークンが期限切れエラー

**症状:** API呼び出し時に401エラー

**対処:**
```bash
# トークン状態確認
python platforms/base/scripts/check_token_status.py

# トークン更新
python platforms/base/scripts/refresh_tokens.py
```

### リフレッシュトークンが無効

**症状:** トークン更新時に400エラー

**原因:**
- リフレッシュトークンの期限切れ
- BASE側でアプリ認証が取り消された

**対処:**
```bash
# 再認証が必要
python platforms/base/scripts/get_authorization_code.py
```

### トークンファイルが見つからない

**対処:**
```bash
# 初回認証を実行
python platforms/base/scripts/get_authorization_code.py
```

### 複数アカウントで一部のトークンのみ期限切れ

**対処:**
```bash
# 全アカウント一括更新
python platforms/base/scripts/refresh_tokens.py
```

## セキュリティ考慮事項

### トークンファイルの保護

- `platforms/base/accounts/tokens/` ディレクトリのアクセス権限を制限
- トークンファイルをGitにコミットしない（`.gitignore`に追加済み）
- 本番環境では環境変数や秘密管理サービスの使用を推奨

### トークンのローテーション

- 定期的にリフレッシュトークンで更新することを推奨
- 長期間使用しないアカウントは再認証を検討

### アクセス権限の最小化

- BASE API スコープは必要最小限に設定
- 現在の設定: `read_items write_items`

## テスト

自動トークン更新機能のテスト:

```bash
python platforms/base/scripts/test_auto_refresh.py
```

**テスト内容:**
1. AccountManager初期化
2. トークン有効期限確認
3. BaseAPIClient作成（自動更新ON）
4. API呼び出し（get_items）
5. トークン状態確認

## API リファレンス

### BaseOAuthClient

```python
from core.auth import BaseOAuthClient

oauth = BaseOAuthClient(
    client_id='YOUR_CLIENT_ID',
    client_secret='YOUR_CLIENT_SECRET',
    redirect_uri='http://localhost:8000/callback'
)

# 認証URL生成
auth_url = oauth.get_authorization_url()

# 認証コードからトークン取得
token = oauth.get_access_token_from_code(code='AUTH_CODE')

# トークン更新
new_token = oauth.refresh_access_token(refresh_token='REFRESH_TOKEN')

# トークン有効期限チェック
is_expired = BaseOAuthClient.is_token_expired(token_data)

# トークン情報取得
info = BaseOAuthClient.get_token_info(token_data)
```

### AccountManager（トークン管理機能）

```python
from accounts.manager import AccountManager

manager = AccountManager()

# トークン取得（自動更新付き）
token = manager.get_token_with_auto_refresh('base_account_1')

# トークン更新（必要時のみ）
success = manager.refresh_token_if_needed('base_account_1')

# トークン強制更新
success = manager.refresh_token_if_needed('base_account_1', force=True)

# 全アカウント一括更新
results = manager.refresh_all_tokens(active_only=True)

# トークン有効性チェック
is_valid = manager.has_valid_token('base_account_1')
```

## 次のステップ

Phase 2.5完了後、Phase 3に進みます:

- **Phase 3**: Upload Queue & Scheduler
  - 時間帯分散アップロード
  - アカウント振り分けロジック
  - レート制限管理
  - リトライ処理

トークン管理が完全自動化されたため、スケジューラによる長時間・定期実行が可能になります。
