# ISSUE20: multi_account_manager.py 起動後のハング問題

## 日時
- 発生日時: 2025-11-28
- 対応日時: 2025-11-28
- 対応者: Claude Code

## 問題の概要

`scheduler/multi_account_manager.py` が起動後すぐにハングし、デーモンプロセスが正常に動作しない問題が発生。

## 症状

- `multi_account_manager.py` を起動すると、デーモンプロセスは起動するが、画像アップロード処理後にハングする
- ログファイルで「画像アップロード: X件」の後、処理が進まない
- 新しいタスクサイクルが開始されない

## 調査過程

### 1. 初期調査

デバッグスクリプト (`debug_manager_hang.py`) を作成して以下を確認：
- モジュールインポート: 正常
- ロックチェック機能: 正常
- デーモンプロセス一覧取得: 正常
- Managerインスタンス化: 正常

### 2. プロセス状態確認

既存プロセスの確認：
- managerプロセス: PID 117712 (実行中)
- デーモンプロセス:
  - base_account_1: PID 160560
  - base_account_2: PID 36132

### 3. ログ分析

`logs/upload_scheduler_base_base_account_1.log` の最終行：
```
2025-11-28 14:24:10 [INFO] upload_scheduler_base_base_account_1: 画像アップロード: 6件
```

その後のデバッグログ（以下）が出力されていない：
- `[DEBUG] 画像アップロード処理完了後`
- `[DEBUG] if/else ブロック抜けた`
- `[DEBUG] キューステータス更新開始`
- `[DEBUG] キューステータス更新完了`
- `[DEBUG] _upload_single_item return前`

### 4. コード分析

**問題箇所の特定：**

1. `scheduler/multi_account_manager.py:385-386`
   ```python
   stdout=subprocess.PIPE,
   stderr=subprocess.PIPE,
   ```
   - 子プロセスのstdout/stderrをPIPEにリダイレクト
   - 親プロセスがパイプを読み取らない

2. `scheduler/platform_uploaders/base_uploader.py:164-171`
   ```python
   print(f"  [DEBUG] upload_images 開始: Item ID={platform_item_id}, 画像数={len(image_urls)}")
   print(f"  [DEBUG] 画像URL: {image_urls[:3]}...")
   ```
   - `print()` 文でデバッグ情報を出力

## 根本原因

**パイプバッファの詰まりによるデッドロック**

1. 親プロセス (`multi_account_manager.py`) が子プロセス (`upload_daemon_account.py`) のstdout/stderrをsubprocess.PIPEにリダイレクト
2. 子プロセス内の `base_uploader.py` が `print()` 文で標準出力に書き込み
3. 親プロセスがパイプを読み取らないため、パイプバッファ（通常64KB）が満杯になる
4. 子プロセスが `print()` で書き込もうとしてブロックされる（デッドロック）
5. 処理が先に進まず、ハング状態になる

## 修正内容

### 1. multi_account_manager.py の修正

**ファイル:** `scheduler/multi_account_manager.py`

**変更箇所1:** 子プロセス起動時のリダイレクト先を変更 (行387-388)

```python
# 修正前
stdout=subprocess.PIPE,
stderr=subprocess.PIPE,

# 修正後
stdout=subprocess.DEVNULL,
stderr=subprocess.DEVNULL,
```

**理由:**
- デーモンプロセスは既にログファイルに出力している
- stdout/stderrの出力は不要
- DEVNULLにリダイレクトすることでパイプバッファの問題を回避

**変更箇所2:** プロセス停止時の処理を修正 (行437-442)

```python
# 修正前
# 出力を読み取る
stdout, stderr = process.communicate()

print()
print("=" * 60)
print(f"[STOPPED] {key} が停止しました（終了コード: {returncode}）")
if stderr:
    print(f"エラー出力:\n{stderr[:500]}")
print("=" * 60)

# 修正後
# stdout/stderrはDEVNULLにリダイレクト済みのため読み取り不要
print()
print("=" * 60)
print(f"[STOPPED] {key} が停止しました（終了コード: {returncode}）")
print("ログファイルを確認してください: logs/upload_scheduler_{key}.log")
print("=" * 60)
```

**理由:**
- stdout/stderrはDEVNULLにリダイレクトされているため読み取り不要
- エラー情報はログファイルに記録されている

### 2. base_uploader.py の修正

**ファイル:** `scheduler/platform_uploaders/base_uploader.py`

**変更箇所:** print文をlogger文に変更 (行163-180)

```python
# 修正前
print(f"  [DEBUG] upload_images 開始: Item ID={platform_item_id}, 画像数={len(image_urls)}")
print(f"  [DEBUG] 画像URL: {image_urls[:3]}...")
result = self.client.add_images_bulk(platform_item_id, image_urls)
print(f"  [DEBUG] add_images_bulk 結果: {result}")

# 修正後
logger.debug(f"upload_images 開始: Item ID={platform_item_id}, 画像数={len(image_urls)}")
logger.debug(f"画像URL: {image_urls[:3]}...")
result = self.client.add_images_bulk(platform_item_id, image_urls)
logger.debug(f"add_images_bulk 結果: {result}")
```

**理由:**
- print文は標準出力に書き込まれ、パイプバッファの問題を引き起こす可能性がある
- logger文はログファイルに直接書き込まれる
- デーモンプロセスではloggerを使用するのが標準的な実装

## 修正手順

1. 既存プロセスの停止
   ```bash
   python scheduler/multi_account_manager.py stop
   ```

2. コードの修正
   - `scheduler/multi_account_manager.py` の修正
   - `scheduler/platform_uploaders/base_uploader.py` の修正

3. プロセスの再起動
   ```bash
   python scheduler/multi_account_manager.py start
   ```

## 修正結果

### 動作確認

**起動状態:**
- デーモンプロセス: 2つ正常起動
  - base_account_1: PID 61428
  - base_account_2: PID 70644

**ログ出力（修正後）:**
```
2025-11-28 14:36:03 [INFO] 画像アップロード: 9件
2025-11-28 14:36:03 [INFO] [DEBUG] 画像アップロード処理完了後  ← 以前は出力されなかった
2025-11-28 14:36:03 [INFO] [DEBUG] if/else ブロック抜けた
2025-11-28 14:36:03 [INFO] [DEBUG] キューステータス更新開始: queue_id=7761
2025-11-28 14:36:03 [INFO] [DEBUG] キューステータス更新完了: queue_id=7761
2025-11-28 14:36:03 [INFO] [DEBUG] _upload_single_item return前
2025-11-28 14:36:03 [INFO] バッチ完了: 成功=1, 失敗=0
2025-11-28 14:36:03 [INFO] --- タスク完了 (所要時間: 14.7秒) ---
2025-11-28 14:36:33 [INFO] --- タスク実行開始 2025-11-28 14:36:33 ---
```

### 確認事項

- ✅ 画像アップロード後も処理が継続
- ✅ キューステータスが正常に更新される
- ✅ 30秒間隔でタスクサイクルが実行される
- ✅ ハングせず正常に動作し続ける

## 技術的な教訓

### subprocess.PIPEの注意点

**問題:**
- `subprocess.Popen(stdout=subprocess.PIPE, stderr=subprocess.PIPE)` を使用した場合、親プロセスがパイプを読み取らないとバッファが満杯になる
- バッファサイズは通常64KB程度で、それを超えると子プロセスがブロックされる

**ベストプラクティス:**
1. **ログファイルに出力する場合**
   ```python
   stdout=subprocess.DEVNULL,
   stderr=subprocess.DEVNULL,
   ```

2. **出力を読み取る場合**
   ```python
   # 非ブロッキングで読み取る
   stdout, stderr = process.communicate()

   # または、別スレッドで読み取る
   import threading
   def read_output():
       for line in process.stdout:
           print(line)
   threading.Thread(target=read_output).start()
   ```

3. **ファイルにリダイレクトする場合**
   ```python
   with open('output.log', 'w') as f:
       process = subprocess.Popen(..., stdout=f, stderr=f)
   ```

### デバッグ出力の推奨方法

**避けるべき:**
```python
print(f"Debug: {value}")  # 標準出力に書き込まれる
```

**推奨:**
```python
logger.debug(f"Debug: {value}")  # ログファイルに書き込まれる
```

## 関連ファイル

- `scheduler/multi_account_manager.py` - マルチアカウントマネージャー
- `scheduler/upload_daemon_account.py` - アカウント別アップロードデーモン
- `scheduler/platform_uploaders/base_uploader.py` - BASE用アップローダー
- `platforms/base/core/api_client.py` - BASE APIクライアント

## 参考資料

- Python subprocess documentation: https://docs.python.org/3/library/subprocess.html
- Avoiding deadlocks with subprocess: https://docs.python.org/3/library/subprocess.html#subprocess.Popen.communicate

## ステータス

✅ **解決済み** (2025-11-28)

## 備考

- デバッグスクリプト (`debug_manager_hang.py`, `check_processes.py`) は調査完了後に削除済み
- 修正後、プロセスは正常に動作しており、問題は完全に解決
- 同様の問題が他のプロセスでも発生する可能性があるため、subprocess.PIPEの使用には注意が必要
