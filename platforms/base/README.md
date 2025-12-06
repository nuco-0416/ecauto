# BASE プラットフォーム管理

BASE ECの複数アカウント管理とAPI操作

## ディレクトリ構成

```
platforms/base/
├── accounts/                      # アカウント管理
│   ├── manager.py                # アカウントマネージャー
│   ├── account_config.json       # アカウント設定（要作成）
│   ├── account_config.json.example  # 設定テンプレート
│   └── tokens/                   # トークンファイル（自動作成）
│       ├── base_account_1_token.json
│       ├── base_account_2_token.json
│       └── ...
│
├── core/                         # APIクライアント
│   ├── api_client.py            # BASE APIクライアント
│   └── auth.py                  # 認証ヘルパー（Phase 3で実装）
│
└── scripts/                      # 管理スクリプト
    ├── test_accounts.py         # アカウント管理テスト
    └── setup_account.py         # セットアップスクリプト
```

## セットアップ

### 1. アカウント設定ファイルの作成

`account_config.json.example` をコピーして `account_config.json` を作成：

```bash
cd platforms/base/accounts
cp account_config.json.example account_config.json
```

`account_config.json` を編集して、アカウント情報を設定：

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

### 2. トークンの設定

#### 方法A: 既存トークンからコピー

既存の `C:\Users\hiroo\Documents\ama-cari\base\base_token.json` がある場合：

```bash
python platforms/base/scripts/setup_account.py
```

#### 方法B: 手動でトークンファイルを作成

`platforms/base/accounts/tokens/base_account_1_token.json` を作成：

```json
{
  "access_token": "your_access_token_here",
  "refresh_token": "your_refresh_token_here",
  "token_type": "Bearer",
  "expires_in": 3600
}
```

### 3. 動作確認

```bash
python platforms/base/scripts/test_accounts.py
```

成功すると以下のような出力が表示されます：

```
============================================================
BASE アカウント一覧
============================================================
アクティブ: 1件 / 全体: 3件

[Active] [Token OK] base_account_1
  名前: BASE本店
  説明: メインアカウント

[Active] [No Token] base_account_2
  名前: BASE別館
  説明: サブアカウント1

...
```

## 使用方法

### アカウントマネージャーの使用

```python
from platforms.base.accounts.manager import AccountManager

# アカウントマネージャーを初期化
manager = AccountManager()

# アクティブなアカウント一覧を取得
active_accounts = manager.get_active_accounts()

# トークンを取得
token = manager.get_token('base_account_1')

# アカウント情報を取得
info = manager.get_account_info('base_account_1')
```

### BASE APIクライアントの使用

```python
from platforms.base.accounts.manager import AccountManager
from platforms.base.core.api_client import BaseAPIClient

# アカウントマネージャーを初期化
manager = AccountManager()

# トークンを取得
token_data = manager.get_token('base_account_1')
access_token = token_data['access_token']

# APIクライアントを初期化
client = BaseAPIClient(access_token)

# 商品を作成
result = client.create_item({
    'title': '商品名',
    'price': 5000,
    'stock': 10,
    'detail': '商品説明',
    'visible': 1
})

item_id = result['item']['item_id']
print(f"商品ID: {item_id}")

# 商品を更新
client.update_item(item_id, {
    'price': 4500,
    'stock': 8
})

# 商品一覧を取得
items = client.get_all_items(max_items=100)
```

## トラブルシューティング

### アカウント設定ファイルが見つからない

```
警告: アカウント設定ファイルが見つかりません
```

→ `platforms/base/accounts/account_config.json` を作成してください

### トークンが無効

```
[No Token] base_account_1
```

→ `setup_account.py` を実行してトークンを設定してください

## 次のステップ

Phase 3でスケジューラーと統合し、複数アカウントでの自動出品を実現します。
