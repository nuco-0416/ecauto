# ISSUE_034: BASE API レート制限エラー対応

## 概要

BASE APIの1時間あたり呼び出し上限（5000回）に達した際のエラーハンドリングとログ出力を改善。

## 発生状況

### エラー内容
```json
{
  "error": "hour_api_limit",
  "error_description": "1時間のAPIの利用回数を超えました。時間が経ってから再度アクセスしてください。"
}
```

### 原因分析

| 項目 | 内容 |
|------|------|
| BASE API制限 | 5000回/時間（アクセストークンごと） |
| 商品登録間隔 | 2秒（理論値1800回/時間） |
| 画像追加間隔 | 0.1秒（理論値最大36000回/時間） |

**実際のAPI消費**:
- 商品1件 = 1（商品登録）+ 最大20（画像追加）= 最大21 API calls
- 画像が多い商品を連続処理すると、短時間で上限に到達

**注意**: レート制限はアクセストークン（アカウント）ごとに独立。複数アカウント並列処理では累積しない。

## 問題点（修正前）

1. **APIエラー詳細がログに残らない**
   - `api_client.py`でエラー詳細を構築していたが、ログに出力せずに例外を投げていた
   - `hour_api_limit`などの詳細が失われていた

2. **レート制限エラーに対する特別な処理がない**
   - バッチ処理が継続され、全アイテムが失敗する可能性
   - リセット時刻が不明

## 修正内容

### 1. api_client.py - APIエラー詳細のログ出力

**対象メソッド**: `create_item`, `update_item`, `add_image_from_url`

```python
# エラー時に詳細なメッセージを取得してログ出力
if not response.ok:
    error_detail = f"Status: {response.status_code}"
    error_type = None
    error_description = None

    try:
        error_json = response.json()
        error_type = error_json.get('error')
        error_description = error_json.get('error_description')
        error_detail += f", Response: {error_json}"
    except:
        error_detail += f", Text: {response.text[:200]}"

    # レート制限エラーの場合は特別に警告ログを出力
    if error_type == 'hour_api_limit':
        logger.warning(
            f"[RATE_LIMIT] APIレート制限に到達しました: {error_description}"
        )
        logger.warning(
            f"[RATE_LIMIT] Account: {self.account_id}, "
            f"1時間後に自動リセットされます"
        )

    # 全てのAPIエラーをログに記録
    logger.error(
        f"商品登録エラー: {error_detail}, "
        f"Account: {self.account_id}"
    )

    # HTTPError例外を投げる（エラー詳細を含める）
    from requests.exceptions import HTTPError
    error_msg = f"{error_type}: {error_description}" if error_type else error_detail
    raise HTTPError(error_msg, response=response)
```

### 2. base_uploader.py - エラータイプの伝播

```python
except Exception as e:
    error_message = str(e)
    error_type = 'unknown_error'

    # レート制限エラーを検知
    if 'hour_api_limit' in error_message:
        error_type = 'rate_limit'
        logger.warning(f"[RATE_LIMIT] 商品登録失敗 (ASIN={item_data.get('asin')}): {error_message}")
    else:
        logger.error(f"アップロード失敗 (ASIN={item_data.get('asin')}): {error_message}")

    return {
        'status': 'failed',
        'platform_item_id': None,
        'message': error_message,
        'error_type': error_type  # 追加
    }
```

### 3. upload_daemon_account.py - レート制限検知と処理中断

```python
# バッチ処理
success_count = 0
failed_count = 0
processed_count = 0
rate_limit_hit = False  # レート制限フラグ
rate_limit_detected_at = None  # レート制限検出時刻

for item in items:
    # レート制限に達した場合、残りの処理を中断
    if rate_limit_hit:
        self.logger.warning(
            f"[RATE_LIMIT] バッチ処理を中断: "
            f"残り{len(items) - processed_count}件は次回処理"
        )
        break

    try:
        result = self._upload_single_item(item)
        processed_count += 1

        if result['status'] == 'success':
            success_count += 1
        else:
            failed_count += 1
            # レート制限エラーを検知
            if result.get('error_type') == 'rate_limit':
                rate_limit_hit = True
                rate_limit_detected_at = datetime.now()
                reset_time = rate_limit_detected_at + timedelta(hours=1)
                self.logger.warning(
                    f"[RATE_LIMIT] {rate_limit_detected_at.strftime('%Y-%m-%d %H:%M:%S')}JST "
                    f"APIレート制限到達を検知"
                )
                self.logger.warning(
                    f"[RATE_LIMIT] Account: {self.account_id}, "
                    f"リセット予定: {reset_time.strftime('%Y-%m-%d %H:%M:%S')}JST"
                )
```

### 4. Chatwork通知の強化

```python
# レート制限到達時は特別な警告通知
if rate_limit_hit and rate_limit_detected_at:
    reset_time = rate_limit_detected_at + timedelta(hours=1)
    if self.notifier:
        self.notifier.notify(
            event_type='task_failure',
            title=f"[RATE_LIMIT] {self.platform.upper()} / {self.account_id} APIレート制限到達",
            message=(
                f"BASE APIの1時間あたり呼び出し上限（5000回）に達しました。\n\n"
                f"検出時刻: {rate_limit_detected_at.strftime('%Y-%m-%d %H:%M:%S')}JST\n"
                f"リセット予定: {reset_time.strftime('%Y-%m-%d %H:%M:%S')}JST\n\n"
                f"処理済み: {processed_count}件（成功: {success_count}, 失敗: {failed_count}）\n"
                f"残り: {pending_count - processed_count}件"
            ),
            level="WARNING"
        )
```

## 修正後のログ出力例

```
[RATE_LIMIT] 2025-12-13 16:33:00JST APIレート制限到達を検知
[RATE_LIMIT] Account: base_account_3, リセット予定: 2025-12-13 17:33:00JST
[RATE_LIMIT] バッチ処理を中断: 残り8件は次回処理
```

## 修正ファイル一覧

| ファイル | 修正内容 |
|----------|----------|
| `platforms/base/core/api_client.py` | APIエラー詳細のログ出力、HTTPError例外にエラー詳細を含める |
| `scheduler/platform_uploaders/base_uploader.py` | `error_type`を戻り値に追加、レート制限エラーの検知 |
| `scheduler/upload_daemon_account.py` | レート制限検知時のバッチ中断、検出時刻とリセット予定時刻の表示、Chatwork通知強化 |

## 今後の対策（推奨）

1. **画像アップロード間隔の調整検討**
   - 現在: 0.1秒
   - 推奨: 0.5秒程度に変更すると、画像枚数が多い場合のレート超過リスクを軽減

2. **失敗アイテムのリトライ**
   - `failed`ステータスのアイテムを`pending`に戻すスクリプトを活用
   - レート制限解除後（1時間後）に再処理

## ステータス

- **作成日**: 2025-12-13
- **ステータス**: RESOLVED
- **対応者**: Claude
