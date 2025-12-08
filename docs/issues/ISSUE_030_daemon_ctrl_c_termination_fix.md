# ISSUE #030: sync_inventory_daemon Ctrl+C終了問題の修正

## ステータス: RESOLVED

## 発生日: 2025-12-08

## 問題の概要

`sync_inventory_daemon.py` がCtrl+C（SIGINT）を受信しても適切に終了しない問題。
特に以下のタイミングで終了しなかった:
- SP-APIバッチ処理のレート制限待機中（12秒間隔）
- タスク間インターバル待機中（3時間）
- Phase 1処理中のMaster DB保存ループ

## 根本原因

### 1. シグナルハンドラの上書き問題
`sync_stock_visibility.py` と `sync_prices.py` が `__init__` メソッド内で独自のシグナルハンドラを登録していたため、`daemon_base.py` のシグナルハンドラが上書きされていた。

### 2. `_interruptible_sleep` の長いタイムアウト
`daemon_base.py` の `_interruptible_sleep` が `Event.wait(timeout=total_seconds)` を1回だけ呼び出していたため、シグナル受信時に即座に応答できなかった。

### 3. execute_task内のシャットダウンチェック不足
`sync_inventory_daemon.py` の `execute_task` メソッド内で、Phase 1処理後やMaster DB保存ループ内にシャットダウンチェックがなかった。

## 修正内容

### 1. daemon_base.py

**シグナルハンドラの簡素化** (行108-130):
- `logger.info()` の代わりに `sys.stderr.write()` を使用（スレッドセーフ）
- シグナルハンドラ内では最小限の処理のみ実行

```python
def _signal_handler(self, signum, frame):
    self.shutdown_requested = True
    self._shutdown_event.set()
    try:
        sys.stderr.write(f"\n[SIGNAL] シグナル {signum} を受信しました。シャットダウン開始...\n")
        sys.stderr.flush()
    except:
        pass
```

**`_interruptible_sleep` の改善** (行132-167):
- 1秒間隔の短いポーリングに変更
- シグナル受信時に最大1秒以内に応答

```python
def _interruptible_sleep(self, total_seconds: float) -> bool:
    POLL_INTERVAL = 1.0
    elapsed = 0.0
    while elapsed < total_seconds:
        if self.shutdown_requested:
            return False
        remaining = total_seconds - elapsed
        wait_time = min(POLL_INTERVAL, remaining)
        interrupted = self._shutdown_event.wait(timeout=wait_time)
        if interrupted:
            return False
        elapsed += wait_time
    return True
```

### 2. sync_stock_visibility.py

**シグナルハンドラ登録のオプション化** (行53-65):
- `register_signal_handler` パラメータを追加（デフォルト: False）
- daemon経由で実行される場合はシグナルハンドラを登録しない

```python
def __init__(self, register_signal_handler: bool = False):
    if register_signal_handler:
        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)
```

### 3. sync_prices.py

**同様のシグナルハンドラ登録のオプション化** (行83-85):
- `register_signal_handler` パラメータを追加

### 4. sync_inventory_daemon.py

**Phase 1後のシャットダウンチェック** (行226-229):
```python
if self.shutdown_requested:
    self.logger.info("シャットダウン要求を検出（Phase 2をスキップ）")
    return False
```

**SP-API処理後のシャットダウンチェック** (行429-432):
```python
if self.shutdown_requested:
    self.logger.info("シャットダウン要求を検出（Phase 1中断 - SP-API処理後）")
    return
```

**Master DB保存ループ内のシャットダウンチェック** (行440-443):
```python
if self.shutdown_requested:
    self.logger.info(f"シャットダウン要求を検出（Master DB保存中断 - {success_count}件保存済み）")
    break
```

### 5. sp_api_client.py

**`_interruptible_sleep` の実装** (行107-128):
- `shutdown_event` (threading.Event) を使用した割り込み可能な待機
- シャットダウン要求時に即座に中断

## デバッグ出力のクリーンアップ

修正中に追加したデバッグ出力をすべて削除:

| ファイル | 削除したデバッグ出力 |
|---------|---------------------|
| daemon_base.py | `[DEBUG]` プリント文（8箇所） |
| sp_api_client.py | `[DEBUG_SLEEP]`, `[RATE_LIMIT_DEBUG]`（7箇所） |
| sync_inventory_daemon.py | `[LOCK]` プリント文（9箇所） |
| sync_prices.py | `[DEBUG]` ログ（17箇所） |
| sync_inventory.py | `[DEBUG]` ログ（9箇所） |

## 変更ファイル一覧

| ファイル | 変更内容 |
|---------|---------|
| `scheduled_tasks/daemon_base.py` | シグナルハンドラ簡素化、`_interruptible_sleep`改善、デバッグ出力削除 |
| `scheduled_tasks/sync_inventory_daemon.py` | シャットダウンチェック追加（3箇所）、デバッグ出力削除 |
| `inventory/scripts/sync_stock_visibility.py` | `register_signal_handler`パラメータ追加 |
| `platforms/base/scripts/sync_prices.py` | `register_signal_handler`パラメータ追加、デバッグ出力削除 |
| `inventory/scripts/sync_inventory.py` | デバッグ出力削除 |
| `integrations/amazon/sp_api_client.py` | デバッグ出力削除 |

## テスト結果

### テストシナリオ
1. デーモン起動
2. SP-APIバッチ処理中（レート制限待機中）にCtrl+C送信
3. 終了確認

### 期待される動作
```
[SIGNAL] シグナル 2 を受信しました。シャットダウン開始...
シャットダウン要求を検出（SP-API待機中断）: event.is_set()=True
シャットダウン要求により、バッチ処理を中断しました
シャットダウン要求を検出（Phase 1中断 - SP-API処理後）
シャットダウン要求を検出（Phase 2をスキップ）
デーモンをシャットダウンしています...
sync_inventory デーモンを停止しました
```

### 結果
- シグナル受信後、約1秒以内にシャットダウン処理開始
- 正常に終了することを確認

## 関連Issue

- ISSUE #028: sync_inventory_daemon SP-API重複呼び出し問題
- ISSUE #029: キャッシュシステム削除とワークフロー改善

## 備考

- スタンドアロンで `sync_prices.py` や `sync_stock_visibility.py` を実行する場合は、`main()` 関数内で `register_signal_handler=True` を指定しているため、従来通りCtrl+Cで終了可能
- daemon経由で実行される場合は、`daemon_base.py` のシグナルハンドラが有効になり、全体の終了を制御
