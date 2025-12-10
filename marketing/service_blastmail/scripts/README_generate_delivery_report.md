# メルマガ配信レポート作成スクリプト

`generate_delivery_report.py` - Blastmail APIから配信データを取得し、CSVレポートを生成するスクリプト

## 概要

- Blastmail APIから配信履歴・開封ログを取得
- **Google Analytics 4連携**（オプション）- 日付別のPV/セッション/購入数/売上を追加
- **Shopify連携**（オプション）- 日付別の注文数/売上/販売商品を追加
- アカウントごとにCSVファイルを生成
- 配信から3日以内のデータは自動更新（開封数等の変動に対応）

## 出力CSVカラム

### 基本カラム（Blastmailデータ）

| カラム | 説明 | 例 |
|--------|------|-----|
| message_id | メッセージID | 1101 |
| delivery_date | 配信日 | 2025-12-09 |
| delivery_time | 配信時間 | 19:35:00 |
| subject | メルマガタイトル | 【限定】特別キャンペーン |
| total | 配信数 | 90959 |
| success | 成功数 | 89986 |
| failure | エラー数 | 973 |
| open_count | 開封数（ユニーク） | 5952 |
| error_rate | エラー率（%） | 1.07 |
| open_rate | 開封率（%） | 6.61 |
| destination_urls | 遷移先URL（複数はセミコロン区切り） | https://example.com/ |
| updated_at | レコード更新日時 | 2025-12-10 00:28:02 |

### GA連携時の追加カラム（--with-ga オプション使用時）

| カラム | 説明 | 例 |
|--------|------|-----|
| ga_pageviews | 配信日のPV数 | 128 |
| ga_sessions | 配信日のセッション数 | 93 |
| ga_purchases | 配信日の購入数 | 1 |
| ga_revenue | 配信日の売上 | 3605.0 |
| ga_mail_sessions | メルマガ経由セッション数 | 1 |

### Shopify連携時の追加カラム（--with-shopify オプション使用時）

| カラム | 説明 | 例 |
|--------|------|-----|
| shopify_orders | 配信日の注文数 | 3 |
| shopify_revenue | 配信日の売上 | 15800.0 |
| shopify_products | 販売商品名（セミコロン区切り） | 商品A;商品B |

## 使用方法

### 基本コマンド

```bash
# プロジェクトルートから実行
cd /home/nuc_o/github/ecauto

# 特定アカウントのレポート生成
venv/bin/python marketing/service_blastmail/scripts/generate_delivery_report.py \
    --account blastmail_account_1

# 全アカウントのレポート生成
venv/bin/python marketing/service_blastmail/scripts/generate_delivery_report.py \
    --all-accounts

# Google Analytics連携を有効にして生成
venv/bin/python marketing/service_blastmail/scripts/generate_delivery_report.py \
    --account blastmail_account_1 --with-ga
```

### オプション一覧

#### アカウント選択

| オプション | 短縮形 | 説明 |
|------------|--------|------|
| `--account` | `-a` | アカウントID指定 |
| `--all-accounts` | | 全アクティブアカウントを処理 |
| `--list-accounts` | | 登録アカウント一覧を表示 |

#### 日付フィルタ

| オプション | 説明 | 形式 |
|------------|------|------|
| `--begin-date` | 取得開始日 | YYYY-MM-DD |
| `--end-date` | 取得終了日 | YYYY-MM-DD |

#### Google Analytics連携

| オプション | 説明 |
|------------|------|
| `--with-ga` | GA4連携を有効化（日付別PV/CV/売上を追加） |

#### Shopify連携

| オプション | 説明 |
|------------|------|
| `--with-shopify` | Shopify連携を有効化（日付別注文数/売上/商品を追加） |

#### 実行オプション

| オプション | 説明 |
|------------|------|
| `--dry-run` | ドライラン（保存せずに確認） |
| `--debug` | デバッグモード（詳細ログ出力） |

### 使用例

```bash
# アカウント一覧を確認
venv/bin/python marketing/service_blastmail/scripts/generate_delivery_report.py \
    --list-accounts

# 12月以降の配信のみ取得
venv/bin/python marketing/service_blastmail/scripts/generate_delivery_report.py \
    --account blastmail_account_1 \
    --begin-date 2025-12-01

# ドライランで確認してから実行
venv/bin/python marketing/service_blastmail/scripts/generate_delivery_report.py \
    --account blastmail_account_1 --dry-run

# デバッグモードで詳細ログを確認
venv/bin/python marketing/service_blastmail/scripts/generate_delivery_report.py \
    --account blastmail_account_1 --debug

# Shopify連携を有効にして生成
venv/bin/python marketing/service_blastmail/scripts/generate_delivery_report.py \
    --account blastmail_account_1 --with-shopify

# GA + Shopify両方の連携を有効にして生成
venv/bin/python marketing/service_blastmail/scripts/generate_delivery_report.py \
    --account blastmail_account_1 --with-ga --with-shopify
```

## 出力ファイル

### 保存先
```
/home/nuc_o/github/ecauto/marketing/service_blastmail/data/
```

### ファイル名規則
```
delivery_report_{account_id}.csv
```

例:
- `delivery_report_blastmail_account_1.csv`
- `delivery_report_blastmail_account_2.csv`

## 更新ロジック

| 配信からの経過日数 | 動作 |
|-------------------|------|
| 0〜3日 | データ更新（開封数等が変動するため） |
| 4日以上 | スキップ（データ固定） |

## 定期実行（推奨）

毎日1回実行することで、最新の配信データと開封状況を反映できます。

```bash
# cron例: 毎日午前6時に全アカウントのレポートを更新
0 6 * * * cd /home/nuc_o/github/ecauto && venv/bin/python marketing/service_blastmail/scripts/generate_delivery_report.py --all-accounts >> /var/log/blastmail_report.log 2>&1
```

## トラブルシューティング

### 認証エラーが発生する場合
```
config/account_config.json の認証情報を確認してください
```

### 開封数が0になる場合
- 配信直後は開封ログが空の場合があります
- 数時間〜1日後に再実行してください

### 日付フィルタでエラーが出る場合
- 日付フィルタなしで全件取得をお試しください
- Blastmail APIの日付形式制限による場合があります

## 関連ファイル

- 設定ファイル: `config/account_config.json`
- APIクライアント: `core/api_client.py`
- アカウント管理: `accounts/manager.py`
- GA4認証情報: `marketing/service_google_analytics/hadient-customers-*.json`
- Shopify設定: `platforms/shopify/accounts/store1.json`
