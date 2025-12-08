# ISSUE_031: sync_inventory_daemon のログがファイルに出力されない問題

## ステータス: RESOLVED

## 発生日時
2025-12-08

## 問題の概要
`sync_inventory_daemon` 実行時に、ターミナルに表示されるログの一部が `logs/sync_inventory.log` に記録されていなかった。

### 症状
以下のログがターミナルには表示されるが、ログファイルには記録されない：

1. **SP-APIバッチ処理のログ**
```
2025-12-08 19:44:42,203 - INFO - バッチ 224/810 完了: 所要時間 0.55秒, 成功 20件, 失敗 0件
2025-12-08 19:44:53,652 - INFO - バッチ 225/810: 20件のASINをリクエスト開始
```

2. **価格計算のログ**
```
2025-12-08 18:58:59,691 - INFO - 価格計算: Amazon=9,990円 → 販売=12,990円 (マークアップ=1.30, 戦略=simple_markup)
```

## 原因分析

### ロガー構成の問題
1. `sync_inventory_daemon` は `DaemonBase` を継承し、`setup_logger('sync_inventory')` でロガーを設定
2. SP-APIクライアント (`integrations/amazon/sp_api_client.py`) は `logging.getLogger(__name__)` を使用
3. 価格計算モジュール (`common/pricing/calculator.py`) は `logging.getLogger(self.__class__.__name__)` を使用

### 技術的原因
`shared/utils/logger.py` の `setup_logger` 関数で、ルートロガーへのファイルハンドラ設定に問題があった：

```python
# 修正前のコード
if not root_logger.handlers:
    root_logger.setLevel(level)
    root_logger.addHandler(file_handler)
```

この条件分岐では、他のライブラリ（`requests`, `urllib3`等）が先にルートロガーにハンドラを設定している場合、ファイルハンドラが追加されなかった。

## 解決策

### 修正ファイル
- `shared/utils/logger.py`

### 修正内容
ルートロガーへのファイルハンドラ設定を改善：

```python
# 修正後のコード
# ルートloggerに同じファイルへのハンドラがあるかチェック
log_file_str = str(log_file)
has_same_file_handler = False
for handler in root_logger.handlers:
    if isinstance(handler, (RotatingFileHandler, logging.FileHandler)):
        if hasattr(handler, 'baseFilename') and handler.baseFilename == log_file_str:
            has_same_file_handler = True
            break

# 同じファイルへのハンドラがなければ追加
if not has_same_file_handler:
    root_file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8'
    )
    root_file_handler.setLevel(level)
    root_file_handler.setFormatter(formatter)
    root_logger.addHandler(root_file_handler)

# コンソールハンドラも必要であれば追加（重複チェック）
if console_output:
    has_console_handler = any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        for h in root_logger.handlers
    )
    if not has_console_handler:
        root_console_handler = logging.StreamHandler(sys.stdout)
        root_console_handler.setLevel(level)
        root_console_handler.setFormatter(formatter)
        root_logger.addHandler(root_console_handler)
```

### 改善点
1. ルートロガーに既にハンドラがあっても、同じログファイルへのハンドラがなければ追加
2. ファイルハンドラの `baseFilename` 属性を使用して正確に重複チェック
3. コンソールハンドラも同様に重複チェックを実施

## 動作確認

テストスクリプトで以下のログが全てファイルに記録されることを確認：

```
2025-12-08 19:48:17 [INFO] test_logger: Main logger: テストメッセージ
2025-12-08 19:48:17 [INFO] other_module: Other module: テストメッセージ
2025-12-08 19:48:17 [INFO] integrations.amazon.sp_api_client: SP-API: バッチ 1/10 完了...
2025-12-08 19:48:17 [INFO] PricingCalculator: 価格計算: Amazon=9,990円 → 販売=12,990円...
```

## 影響範囲
- `sync_inventory_daemon` の全ログがファイルに記録されるようになる
- 他のデーモン（`upload_daemon` 等）でも同様の改善が適用される
- 既存の動作には影響なし（ログの重複出力は発生しない）

## バックアップ
- `shared/utils/logger.py.backup_20251208`

## 関連Issue
- ISSUE_011: stdout/stderr handling daemon hang（ルートロガー設定の初回対応）
