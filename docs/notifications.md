# 通知機能 - セットアップガイド

デーモンの起動・停止、タスク失敗などの重要なイベントを通知で受け取ることができます。

## 対応通知方法

1. **Chatwork** (推奨 - 日本で広く使われるビジネスチャット)
2. **Discord Webhook**
3. **Slack Webhook**
4. **Email (SMTP)**
5. **Windows Event Log** (Windows環境のみ)

> **注意:** LINE Notifyは2025年3月31日にサービス終了予定です。

## クイックスタート - Chatwork

### 1. Chatwork APIトークンの取得

1. Chatworkにログイン: https://www.chatwork.com/
2. 右上のアイコン > 「サービス連携」をクリック
3. 「API Token」タブを選択
4. 「新しいトークンを発行」をクリック
5. **表示されたAPIトークンをコピー** （一度しか表示されません！）

### 2. ルームIDの確認

通知を送りたいチャットルームのURLを確認します：

```
例: https://www.chatwork.com/#!rid123456789
         ルームID ↑ この数字部分（123456789）がルームID
```

または：
1. Chatworkでルームを開く
2. URLバーの `#!rid` の後ろの数字をコピー

### 3. 設定ファイルの作成

```bash
# サンプルファイルをコピー
cd C:\Users\hiroo\Documents\GitHub\ecauto
copy config\notifications.json.example config\notifications.json
```

### 4. 設定ファイルの編集

`config\notifications.json` をテキストエディタで開き、以下を編集:

```json
{
  "enabled": true,  ← falseをtrueに変更
  "method": "chatwork",
  "chatwork": {
    "api_token": "取得したAPIトークンを貼り付け",
    "room_id": "ルームIDを貼り付け（例: 123456789）"
  },
  "events": {
    "daemon_start": true,      ← デーモン起動時に通知
    "daemon_stop": true,       ← デーモン停止時に通知
    "task_success": false,     ← 成功時は通知しない（頻繁すぎるため）
    "task_failure": true,      ← 失敗時に通知
    "retry_exhausted": true,   ← リトライ上限時に通知
    "service_restart": true    ← サービス再起動時に通知
  }
}
```

### 5. テスト実行

```bash
# テストデーモンで確認（10秒ごとに実行）
venv\Scripts\python.exe scheduled_tasks\test_daemon.py --interval 10
```

起動時と停止時（Ctrl+C）にChatworkに通知が届けば成功です！

## 通知イベントの詳細

### イベントタイプ

| イベント | 説明 | 推奨設定 | 重要度 |
|---------|------|---------|--------|
| `daemon_start` | デーモン起動時 | `true` | INFO |
| `daemon_stop` | デーモン停止時 | `true` | INFO |
| `task_success` | タスク成功時 | `false` | INFO |
| `task_failure` | タスク失敗時（初回） | `true` | WARNING |
| `retry_exhausted` | リトライ回数上限到達 | `true` | ERROR |
| `service_restart` | サービス再起動検出時 | `true` | WARNING |

### 推奨設定

**通常運用:**
```json
"events": {
  "daemon_start": true,
  "daemon_stop": true,
  "task_success": false,  ← 1時間ごとに通知が来ると煩わしいため
  "task_failure": true,
  "retry_exhausted": true,
  "service_restart": true
}
```

**デバッグ時:**
```json
"events": {
  "daemon_start": true,
  "daemon_stop": true,
  "task_success": true,  ← デバッグ時は有効にして動作確認
  "task_failure": true,
  "retry_exhausted": true,
  "service_restart": true
}
```

## その他の通知方法

### Discord Webhook

1. Discordサーバーの設定 > 連携サービス > ウェブフック
2. 「新しいウェブフック」をクリック
3. Webhook URLをコピー
4. 設定:
```json
{
  "enabled": true,
  "method": "discord",
  "discord": {
    "webhook_url": "https://discord.com/api/webhooks/YOUR_WEBHOOK_URL"
  }
}
```

### Slack Webhook

1. Slack App設定: https://api.slack.com/messaging/webhooks
2. Incoming Webhookを有効化
3. Webhook URLを取得
4. 設定:
```json
{
  "enabled": true,
  "method": "slack",
  "slack": {
    "webhook_url": "https://hooks.slack.com/services/YOUR_WEBHOOK_URL"
  }
}
```

### Email (SMTP)

Gmail推奨（アプリパスワード使用）:

1. Googleアカウント > セキュリティ > 2段階認証を有効化
2. アプリパスワードを生成: https://support.google.com/accounts/answer/185833
3. 設定:
```json
{
  "enabled": true,
  "method": "email",
  "email": {
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "from_email": "your-email@gmail.com",
    "to_email": "your-email@gmail.com",
    "password": "your-app-password"
  }
}
```

## Chatwork 通知のカスタマイズ

### To指定（メンション）

特定のユーザーにメンションしたい場合は、Chatwork APIのTo記法を使用できます：

```python
# shared/utils/notifier.pyを編集
full_message = f"[To:{account_id}] {emoji_data['icon']} {emoji_data['text']}{title}\n{message}\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
```

アカウントIDの確認方法：
1. Chatworkでユーザープロフィールを開く
2. URLの `?aid=` 以降の数字がアカウントID

### Info/Code記法

Chatworkのメッセージ記法を活用できます：

```
[info]
ここに情報を記載
[/info]

[code]
ここにコードを記載
[/code]
```

詳細: https://help.chatwork.com/hc/ja/articles/360000296622

## トラブルシューティング

### 通知が届かない

1. **設定ファイルを確認**
   ```bash
   type config\notifications.json
   ```
   - `enabled: true` になっているか？
   - `api_token` と `room_id` が正しいか？

2. **ログを確認**
   ```bash
   type logs\sync_inventory.log | findstr "通知"
   ```
   - 「通知機能が有効です」と表示されているか？
   - エラーメッセージがないか？

3. **手動テスト**
   ```python
   # Python REPLで確認
   from shared.utils.notifier import Notifier
   n = Notifier()
   n.notify('test', 'テスト', 'これはテスト通知です', 'INFO')
   ```

### Chatworkエラー

**エラー: `401 Unauthorized`**
- APIトークンが間違っています
- トークンを再発行してください

**エラー: `404 Not Found`**
- ルームIDが間違っています
- ルームIDを確認してください

**エラー: `403 Forbidden`**
- 該当ルームへのアクセス権限がありません
- 自分が参加しているルームのIDを指定してください

### 通知が多すぎる

`task_success` を `false` に設定:
```json
"events": {
  "task_success": false
}
```

## Chatwork API制限

Chatwork APIには以下の制限があります：

- **無料プラン:** 100リクエスト/日
- **ビジネスプラン:** 300リクエスト/日
- **エンタープライズプラン:** 1000リクエスト/日

通常運用（`task_success: false`）の場合：
- デーモン起動/停止: 2回/日
- エラー通知: 必要時のみ
- 合計: 10回未満/日（十分余裕あり）

## セキュリティ注意事項

1. **`notifications.json` を.gitignoreに追加**
   ```
   config/notifications.json
   ```

2. **APIトークンは絶対に公開しない**
   - GitHubにpushしない
   - スクリーンショットに含めない

3. **トークンが漏洩した場合**
   - すぐにChatworkで削除
   - 新しいトークンを発行

## 参考リンク

- [Chatwork API ドキュメント](https://developer.chatwork.com/docs)
- [Chatwork APIトークン管理](https://www.chatwork.com/service/packages/chatwork/subpackages/api/apply_Beta_acount.php)
- [Discord Webhooks](https://support.discord.com/hc/ja/articles/228383668)
- [Slack Incoming Webhooks](https://api.slack.com/messaging/webhooks)
- [Gmail アプリパスワード](https://support.google.com/accounts/answer/185833)

## LINE Notifyからの移行

LINE Notifyは2025年3月31日にサービス終了します。Chatworkへの移行をお勧めします：

1. Chatwork APIトークンとルームIDを取得
2. `config/notifications.json` の `method` を `"chatwork"` に変更
3. Chatwork設定を追加
4. サービスを再起動

移行後もLINE Notify設定は残しておけるため、2025年3月まで並行運用も可能です。
