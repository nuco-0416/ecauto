# Blastmail サービス統合

Blastmail APIを使用したメルマガ配信管理・履歴取得機能を提供します。
**マルチアカウント対応**で複数のBlastmailアカウントを一元管理できます。

## 主な機能

- 認証情報（username, password, api_key）からの**自動トークン取得**
- トークン期限切れ時の**自動再認証**（1時間ごと）
- **マルチアカウント対応**（3アカウント等を同時管理）
- 配信履歴の検索・全件取得
- メッセージ詳細の取得
- 成功/失敗アドレスのCSVエクスポート
- 開封ログのCSVエクスポート

## ディレクトリ構造

```
marketing/service_blastmail/
├── accounts/
│   ├── __init__.py
│   └── manager.py               # アカウント管理・自動認証
├── core/
│   ├── __init__.py
│   ├── api_client.py            # Blastmail APIクライアント
│   └── (BlastmailAuthenticator) # トークン自動取得・更新
├── scripts/
│   ├── __init__.py
│   └── get_delivery_history.py  # 配信履歴取得スクリプト
├── config/
│   └── account_config.json.example  # マルチアカウント設定サンプル
├── data/                        # 出力データ保存用
└── README.md
```

## セットアップ

### 認証情報の設定

```bash
cd marketing/service_blastmail/config
cp account_config.json.example account_config.json
```

`account_config.json` を編集して各アカウントの認証情報を設定：

```json
{
    "accounts": [
        {
            "id": "blastmail_account_1",
            "name": "メインアカウント",
            "active": true,
            "credentials": {
                "username": "YOUR_BLASTMAIL_ID_1",
                "password": "YOUR_API_PASSWORD_1",
                "api_key": "YOUR_API_KEY_1"
            }
        },
        {
            "id": "blastmail_account_2",
            "name": "サブアカウント",
            "active": true,
            "credentials": {
                "username": "YOUR_BLASTMAIL_ID_2",
                "password": "YOUR_API_PASSWORD_2",
                "api_key": "YOUR_API_KEY_2"
            }
        },
        {
            "id": "blastmail_account_3",
            "name": "予備アカウント",
            "active": true,
            "credentials": {
                "username": "YOUR_BLASTMAIL_ID_3",
                "password": "YOUR_API_PASSWORD_3",
                "api_key": "YOUR_API_KEY_3"
            }
        }
    ]
}
```

**認証情報の取得方法**:
- `username`: ブラストメールID（ログイン時に使用するID）
- `password`: APIパスワード（Blastmail管理画面で設定）
- `api_key`: API利用キー（Blastmail管理画面で取得）

## 使用方法

### アカウント管理

```bash
# 登録アカウント一覧を表示
venv/bin/python marketing/service_blastmail/scripts/get_delivery_history.py --list-accounts
```

### 配信履歴の取得

```bash
# 特定アカウントの最新10件を取得（自動認証）
venv/bin/python marketing/service_blastmail/scripts/get_delivery_history.py \
    --account blastmail_account_1 --limit 10

# 全アカウントの配信履歴を取得
venv/bin/python marketing/service_blastmail/scripts/get_delivery_history.py --all-accounts

# 日付範囲を指定して取得
venv/bin/python marketing/service_blastmail/scripts/get_delivery_history.py \
    --account blastmail_account_1 \
    --begin-date 2025-12-01 \
    --end-date 2025-12-09

# 全件取得（ページネーション自動処理）
venv/bin/python marketing/service_blastmail/scripts/get_delivery_history.py \
    --account blastmail_account_1 --all

# JSON形式でファイル出力
venv/bin/python marketing/service_blastmail/scripts/get_delivery_history.py \
    --account blastmail_account_1 \
    --output data/history.json \
    --format json
```

### 特定メッセージの詳細取得

```bash
# メッセージ詳細を取得
venv/bin/python marketing/service_blastmail/scripts/get_delivery_history.py \
    --account blastmail_account_1 \
    --message-id 12345 --detail

# 成功アドレスをCSVエクスポート
venv/bin/python marketing/service_blastmail/scripts/get_delivery_history.py \
    --account blastmail_account_1 \
    --message-id 12345 --export-success

# 失敗アドレスをCSVエクスポート
venv/bin/python marketing/service_blastmail/scripts/get_delivery_history.py \
    --account blastmail_account_1 \
    --message-id 12345 --export-failure

# 開封ログをCSVエクスポート
venv/bin/python marketing/service_blastmail/scripts/get_delivery_history.py \
    --account blastmail_account_1 \
    --message-id 12345 --export-open-log
```

## APIクライアントの直接使用

```python
from marketing.service_blastmail.core import BlastmailAPIClient
from marketing.service_blastmail.accounts import AccountManager

# 方法1: AccountManager経由（推奨）
# 認証情報から自動でトークンを取得し、期限切れ時も自動更新
account_manager = AccountManager()
client = account_manager.create_client('blastmail_account_1')

history = client.search_delivery_history(limit=10)
for item in history.get('items', []):
    print(f"{item['subject']} - {item['deliveryDate']}")

# 方法2: 認証情報から直接作成
client = BlastmailAPIClient.from_credentials(
    username='your_blastmail_id',
    password='your_api_password',
    api_key='your_api_key'
)

# 配信履歴検索
history = client.search_delivery_history(limit=10)

# 全配信履歴取得
all_history = client.get_all_delivery_history()

# メッセージ詳細取得
detail = client.get_message_detail(message_id='12345')

# 成功アドレスエクスポート（CSV）
csv_data = client.export_delivery_addresses(message_id='12345', status=0)

# 開封ログエクスポート（CSV）
open_log = client.export_open_log(message_id='12345')
```

## 認証フロー

```
1. スクリプト実行
       ↓
2. AccountManager が認証情報を読み込み
       ↓
3. BlastmailAuthenticator が /authenticate/login にPOST
   (username, password, api_key を送信)
       ↓
4. アクセストークンを取得（有効期限: 約1時間）
       ↓
5. API呼び出し実行
       ↓
6. トークン期限切れ時は自動で再認証
```

## CLIオプション一覧

### アカウント選択

| オプション | 短縮形 | 説明 |
|------------|--------|------|
| `--account` | `-a` | アカウントID指定 |
| `--all-accounts` | | 全アクティブアカウント |
| `--list-accounts` | | アカウント一覧表示 |

### 取得オプション

| オプション | 短縮形 | 説明 |
|------------|--------|------|
| `--limit` | `-n` | 取得件数制限（デフォルト: 25） |
| `--offset` | | 取得開始位置（デフォルト: 0） |
| `--all` | | 全件取得 |
| `--begin-date` | | 配信開始日時フィルタ |
| `--end-date` | | 配信終了日時フィルタ |
| `--message-id` | | 特定メッセージID指定 |
| `--detail` | | メッセージ詳細取得 |
| `--export-success` | | 成功アドレスCSVエクスポート |
| `--export-failure` | | 失敗アドレスCSVエクスポート |
| `--export-open-log` | | 開封ログCSVエクスポート |

### 出力オプション

| オプション | 短縮形 | 説明 |
|------------|--------|------|
| `--output` | `-o` | 出力ファイルパス |
| `--format` | `-f` | 出力形式（text/json） |
| `--debug` | | デバッグモード |

## API リファレンス

- [Blastmail API ドキュメント - ログイン](https://blastmail.jp/api/login_https.html)
- [Blastmail API ドキュメント - 配信履歴](https://blastmail.jp/api/recent_https.html)
