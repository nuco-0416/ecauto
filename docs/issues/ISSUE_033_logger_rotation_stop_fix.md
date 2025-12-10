# ISSUE_033: ログ出力停止問題の修正

## 概要

本番環境でログファイルへの出力が途中で停止する問題が発生。RotatingFileHandlerのローテーション時に、同一ファイルへの複数ハンドラによる競合が原因と特定。

## 発生日

2025-12-10

## ステータス

**解決済み（RESOLVED）**

## 問題の詳細

### 症状

- `upload_scheduler_base_base_account_3.log` へのログ出力が 2025-12-10 12:19:48 で停止
- ログファイルサイズは約10MB（10,485,781バイト）で停止
- DBへの書き込みは 23:00:13 まで正常に継続
- 処理自体は問題なく完了（615件success）

### 根本原因

`shared/utils/logger.py` の `setup_logger()` 関数で、同一ログファイルに対して2つの独立した `RotatingFileHandler` を追加していた：

1. **名前付きロガー用** (76行目)
2. **ルートロガー用** (117行目) - ISSUE #011対応で追加

これにより、ローテーション時に以下の競合が発生：
- 一方のハンドラがファイルをリネーム（例: `file.log` → `file.log.1`）
- もう一方のハンドラが存在しないファイル（元の `file.log`）に書き込もうとして失敗
- 結果としてログ出力が停止

### 問題のコード（修正前）

```python
# 名前付きロガーにファイルハンドラを追加
file_handler = RotatingFileHandler(log_file, maxBytes=max_bytes, ...)
logger.addHandler(file_handler)

# ルートロガーにも同じファイルへのハンドラを追加（ISSUE #011対応）
root_file_handler = RotatingFileHandler(log_file, maxBytes=max_bytes, ...)
root_logger.addHandler(root_file_handler)
```

## 解決策

### 1. FlushingRotatingFileHandler クラスの追加

emit後に必ずflush()を実行するカスタムハンドラを作成：

```python
class FlushingRotatingFileHandler(RotatingFileHandler):
    """
    emit後に必ずflushを行うRotatingFileHandler
    """
    def emit(self, record):
        super().emit(record)
        try:
            self.flush()
        except Exception:
            pass
```

### 2. ルートロガーへの重複ファイルハンドラ削除

同一ファイルへの複数ハンドラは競合の原因となるため、ルートロガーにはコンソールハンドラのみを追加するよう変更：

```python
# 修正後: ファイルハンドラは名前付きロガーのみに追加
# ルートロガーにはコンソールハンドラのみ追加
```

### 3. デフォルトファイルサイズ上限の縮小

より安全なローテーションのため、デフォルト値を変更：
- 変更前: `max_bytes = 10MB`
- 変更後: `max_bytes = 5MB`

## 変更ファイル

- `shared/utils/logger.py`

## 変更差分

| 項目 | 変更前 | 変更後 |
|------|--------|--------|
| ファイルハンドラ | `RotatingFileHandler` | `FlushingRotatingFileHandler` |
| max_bytes デフォルト | 10MB | 5MB |
| ルートロガーへのファイルハンドラ | 追加する | 追加しない |

## テスト結果

```
=== ハンドラ確認 ===
Handler: FlushingRotatingFileHandler
  - FlushingRotatingFileHandler確認: OK
  - maxBytes: 1024
  - backupCount: 3

=== ファイル確認 ===
test.log: 252 bytes
test.log.1: 1008 bytes
test.log.2: 1008 bytes
test.log.3: 1008 bytes

=== 最終行確認 ===
最終行: 2025-12-11 00:44:01 [INFO] test_logger: テストログメッセージ 49: xxxx...
総行数: 2

=== テスト完了 ===
```

ローテーションと即時フラッシュが正常に動作することを確認。

## 本番環境での検証事項

- [ ] 長時間（数時間〜1日）のログ出力で停止しないことを確認
- [ ] ローテーションサイズ（5MB）到達時の動作確認
- [ ] DBへの書き込みとログ出力の同期確認

## 関連ISSUE

- ISSUE #011: ルートロガーへのハンドラ設定対応（今回の問題の原因となった変更）

## コミット

- `9ebc138` - Fix log output stopping issue with RotatingFileHandler

## 備考

- `propagate=False` を設定しているため、名前付きロガーのログはルートロガーに伝播しない
- ルートロガーへのファイルハンドラ追加は、子ロガー（`__name__`使用）のファイル出力を意図したものだったが、同一ファイルへの複数ハンドラは避けるべき
- 子ロガーがファイル出力を必要とする場合は、各モジュールで明示的に `setup_logger()` を呼ぶ設計とする
