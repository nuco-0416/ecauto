# CHEATSHEET - 運用マニュアル

オペレーター用のクイックリファレンス。コピペで実行可能なコマンド集。

---

## 📋 目次

### A. 商品出品フロー
1. [事前確認](#1-事前確認)
2. [ASINの追加](#2-asinの追加)
3. [デーモン起動](#3-デーモン起動)
4. [監視・確認](#4-監視確認)
5. [停止・再起動](#5-停止再起動)

### B. 価格・在庫同期フロー
6. [定期実行デーモン（推奨）](#6-定期実行デーモン推奨)
7. [個別スクリプト実行](#7-個別スクリプト実行)
8. [同期ログの監視](#8-同期ログの監視)

### C. 共通
9. [トラブルシューティング](#9-トラブルシューティング)
10. [完全フロー例](#10-完全フロー例)
11. [チェックリスト](#11-チェックリスト)
12. [高速化Tips](#12-高速化tips)
13. [関連ドキュメント](#13-関連ドキュメント)

---

## 1. 事前確認

### 1.1 キューの統計情報確認（推奨）

```powershell
# upload_queueの全体統計 + アカウント別の内訳を確認
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' C:\Users\hiroo\Documents\GitHub\ecauto\scheduler\scripts\check_queue.py"
```

**表示内容:**
- **全体統計**: pending, uploading, success, failed の件数
- **アカウント別統計**: 各アカウントごとの内訳（pending, uploading, success, failed, 合計）

**venv activate済みの場合:**
```powershell
python scheduler\scripts\check_queue.py
```

### 1.2 特定ステータスの詳細確認

```powershell
# 失敗アイテムを20件表示
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' C:\Users\hiroo\Documents\GitHub\ecauto\scheduler\scripts\check_queue.py --status failed --limit 20"

# 処理中アイテムを確認
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' C:\Users\hiroo\Documents\GitHub\ecauto\scheduler\scripts\check_queue.py --status uploading --limit 10"

# venv activate済みの場合
python scheduler\scripts\check_queue.py --status failed --limit 20
```

**その他のオプション:**
- `--platform <プラットフォーム名>`: プラットフォームを指定（デフォルト: base）
- `--status <ステータス>`: pending/uploading/success/failed でフィルタ
- `--limit <件数>`: 表示件数（デフォルト: 10）
- `--show-due`: 予定時刻が到来したアイテムのみ表示

### 1.3 sourcing_candidatesの状態確認（推奨）

```powershell
# sourcing_candidatesの統計を確認
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' C:\Users\hiroo\Documents\GitHub\ecauto\sourcing\scripts\check_sourcing.py"
```

**表示内容:**
- 未登録ASIN（candidate）: master.dbに未連携のASIN件数
- 登録済みASIN（imported）: master.dbに連携済みのASIN件数
- 合計: sourcing_candidates内の全ASIN件数

**venv activate済みの場合:**
```powershell
python sourcing\scripts\check_sourcing.py
```

### 1.4 デーモンの実行状態確認

```powershell
# デーモンが起動しているか確認
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' C:\Users\hiroo\Documents\GitHub\ecauto\scheduler\multi_account_manager.py status"
```

---

## 2. ASINの追加

### 2.1 特定件数をアカウント別に追加

```powershell
# sourcing_candidatesからASINを追加（アカウント別件数指定）
# 例: account_1に500件、account_2に500件
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' C:\Users\hiroo\Documents\GitHub\ecauto\sourcing\scripts\import_candidates_to_master.py --account-limits base_account_1:500,base_account_2:500"
```

**処理時間の目安:**
- SP-API取得: 約0.7秒/件（Catalog API、ISSUE #023で7倍高速化）
- 500件 → 約10-15分（旧: 20-30分）
- 1000件 → 約20-30分（旧: 40-60分）
- ※既存ASIN（productsテーブルに存在）はSP-API呼び出しをスキップするため、さらに高速化される場合があります

**リアルタイム確認（別ターミナル）:**

```powershell
# データベースの変化を監視（30秒ごと）
while ($true) {
    Clear-Host
    Write-Host "=== upload_queue status ===" -ForegroundColor Cyan
    & 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' -c "import sqlite3; conn = sqlite3.connect('C:/Users/hiroo/Documents/GitHub/ecauto/inventory/data/master.db'); cursor = conn.cursor(); cursor.execute('SELECT status, COUNT(*) FROM upload_queue GROUP BY status'); [print(f'{row[0]}: {row[1]}') for row in cursor.fetchall()]; conn.close()"
    Write-Host "`nLast updated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    Start-Sleep -Seconds 30
}
```

### 2.2 全件追加（アカウント自動割り振り）

```powershell
# sourcing_candidatesから全ての未処理ASINを追加
# アカウントは1000件ずつ自動割り振り
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' C:\Users\hiroo\Documents\GitHub\ecauto\sourcing\scripts\import_candidates_to_master.py"
```

**📝 重要な仕様:**
- **アクティブアカウントのみが自動選択されます**
- `platforms/base/accounts/account_config.json` の `"active": true` のアカウントのみが対象
- 非アクティブなアカウント（`"active": false`）は自動的に除外されます
- 例: base_account_1 が非アクティブの場合、base_account_2 のみに割り振られます

### 2.3 Dry Run（確認のみ）

```powershell
# 実際の登録は行わず、動作確認のみ
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' C:\Users\hiroo\Documents\GitHub\ecauto\sourcing\scripts\import_candidates_to_master.py --limit 10 --dry-run"
```

### 2.4 キュー登録なし（商品情報収集のみ）

```powershell
# productsとlistingsのみ登録、upload_queueには追加しない
# 用途: 商品情報の事前収集、価格調査、段階的な処理など
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' C:\Users\hiroo\Documents\GitHub\ecauto\sourcing\scripts\import_candidates_to_master.py --account-limits base_account_1:500,base_account_2:500 --no-queue"
```

**処理内容:**
- ✅ productsテーブルに登録（商品情報・価格情報を取得）
- ✅ listingsテーブルに登録（SKU生成・売価計算）
- ❌ upload_queueには追加しない（出品キューに入らない）

**ユースケース:**
- 商品データベースの構築（出品は後で行う）
- Amazon価格情報の収集・分析
- テスト環境でのデータ準備

**後でキューに追加する場合:**
```powershell
# 滞留商品（pending状態のlistings）をキューに追加
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' C:\Users\hiroo\Documents\GitHub\ecauto\scheduler\scripts\add_pending_to_queue.py --yes"
```

### 2.5 ASIN情報収集のみ（productsテーブルのみ）

```powershell
# productsテーブルのみに登録（出品先プラットフォーム/アカウントは未決定）
# 用途: 商品情報の収集、後で出品先を決定する段階的な処理
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' C:\Users\hiroo\Documents\GitHub\ecauto\sourcing\scripts\import_candidates_to_master.py --limit 1000 --products-only"
```

**処理内容:**
- ✅ productsテーブルに登録（商品情報・価格情報を取得）
- ❌ listingsテーブルには登録しない（出品先未決定）
- ❌ upload_queueには追加しない

**ユースケース:**
- **多数の出品先プラットフォームへの展開**: BASE、eBay、Yahoo!オークション、メルカリなど
- 商品情報を先に収集し、後で出品先プラットフォーム/アカウントを選択
- 市場調査・価格分析（Amazon商品情報の収集のみ）
- 段階的な処理フロー: ASIN収集 → プラットフォーム選択 → 出品

**後でlistingsを追加する場合:**
```powershell
# 将来実装予定: productsからlistingsを作成するスクリプト
# python inventory\scripts\add_listings_from_products.py --platform base --account base_account_2
```

---

## 3. デーモン起動

### 3.1 マルチアカウントマネージャー起動（推奨）

```powershell
# 2つのアカウントで並列処理を開始
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' C:\Users\hiroo\Documents\GitHub\ecauto\scheduler\multi_account_manager.py start"
```

**起動確認:**

```powershell
# 起動後5秒待ってからステータス確認
Start-Sleep -Seconds 5
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' C:\Users\hiroo\Documents\GitHub\ecauto\scheduler\multi_account_manager.py status"
```

**期待される出力:**
```
[INFO] 2個のデーモンプロセスが実行中です
  [base_base_account_1] PID: XXXXX
  [base_base_account_2] PID: XXXXX
```

---

## 4. 監視・確認

### 4.1 ログのリアルタイム監視

**マルチログビューアー（推奨）:**

```powershell
# 両方のアカウントのログを同時監視（色分け表示）
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' C:\Users\hiroo\Documents\GitHub\ecauto\scheduler\view_multi_logs.py"
```

**個別ログ監視:**

```powershell
# account_1のログをリアルタイム表示
Get-Content C:\Users\hiroo\Documents\GitHub\ecauto\logs\upload_scheduler_base_base_account_1.log -Tail 50 -Wait

# account_2のログをリアルタイム表示
Get-Content C:\Users\hiroo\Documents\GitHub\ecauto\logs\upload_scheduler_base_base_account_2.log -Tail 50 -Wait
```

**最新50行のみ表示:**

```powershell
# account_1の最新ログ
Get-Content C:\Users\hiroo\Documents\GitHub\ecauto\logs\upload_scheduler_base_base_account_1.log -Tail 50

# account_2の最新ログ
Get-Content C:\Users\hiroo\Documents\GitHub\ecauto\logs\upload_scheduler_base_base_account_2.log -Tail 50
```

### 4.2 処理進捗の確認

**キューの統計情報（全体 + アカウント別）:**

```powershell
# キューの全体統計とアカウント別の内訳を確認
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' C:\Users\hiroo\Documents\GitHub\ecauto\scheduler\scripts\check_queue.py"

# venv activate済みの場合
python scheduler\scripts\check_queue.py
```

**表示内容:**
- プラットフォーム全体の統計（pending, uploading, success, failed, 合計）
- アカウント別の詳細統計（各ステータスの内訳）

### 4.3 失敗アイテムの確認

```powershell
# 失敗したアイテムを20件表示
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' C:\Users\hiroo\Documents\GitHub\ecauto\scheduler\scripts\check_queue.py --status failed --limit 20"

# venv activate済みの場合
python scheduler\scripts\check_queue.py --status failed --limit 20
```

### 4.4 処理速度の推定

**計算式:**
- レート制限: 2秒/件（BASE API制限）
- バッチサイズ: 10件（デフォルト）
- 実行間隔: 240秒（4分）

**推定処理時間:**
- 1000件 → 約55時間（単一アカウント）
- 1000件 × 2アカウント並列 → 約55時間（同時進行）

---

## 5. 停止・再起動

### 5.1 デーモン停止

```powershell
# 全デーモンプロセスを停止
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' C:\Users\hiroo\Documents\GitHub\ecauto\scheduler\multi_account_manager.py stop"
```

### 5.2 デーモン再起動

```powershell
# 全デーモンプロセスを再起動
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' C:\Users\hiroo\Documents\GitHub\ecauto\scheduler\multi_account_manager.py restart"
```

### 5.3 アカウント設定の確認・変更

**設定ファイルの場所:**
- `platforms\base\accounts\account_config.json` が**唯一の設定ファイル**です
- すべてのコンポーネント（Scheduler、価格・在庫同期等）がこのファイルを参照します

**アカウントの有効/無効を切り替え:**

```powershell
# エディタで設定ファイルを開く
notepad platforms\base\accounts\account_config.json

# "active": true → false に変更してアカウントを無効化
# "active": false → true に変更してアカウントを有効化
```

**設定例:**
```json
{
  "accounts": [
    {
      "id": "base_account_1",
      "name": "在庫BAZAAR",
      "active": false,  ← false で無効化
      ...
    },
    {
      "id": "base_account_2",
      "name": "バイヤー倉庫",
      "active": true,   ← true で有効化
      ...
    }
  ]
}
```

**重要: 設定変更後は必ずデーモンを再起動:**

```powershell
# 1. デーモンを停止
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' C:\Users\hiroo\Documents\GitHub\ecauto\scheduler\multi_account_manager.py stop"

# 2. デーモンを再起動（新しい設定が反映されます）
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' C:\Users\hiroo\Documents\GitHub\ecauto\scheduler\multi_account_manager.py start"

# 3. 設定が反映されたか確認
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' C:\Users\hiroo\Documents\GitHub\ecauto\scheduler\multi_account_manager.py status"
```

**同期デーモンも同様に再起動が必要:**

```powershell
# 同期デーモンを停止（Ctrl+Cで停止）
# 設定変更後、再度起動
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' scheduled_tasks\sync_inventory_daemon.py"
```

---

## 6. 定期実行デーモン（推奨）

**本番運用では定期実行デーモンの使用を強く推奨します。**

### 6.1 デーモン起動

```powershell
# デフォルト（3時間ごとに自動同期）
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' scheduled_tasks/sync_inventory_daemon.py"

# 1時間ごとに同期
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' scheduled_tasks/sync_inventory_daemon.py --interval 3600"

# Dry Runモード（テスト用）
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' scheduled_tasks/sync_inventory_daemon.py --dry-run"
```

**特徴:**
- ✅ **価格同期 + 在庫同期**の統合処理
- ✅ 定期自動実行（手動実行不要）
- ✅ ログ管理（`logs/sync_inventory.log`）
- ✅ SP-APIレート制限対策
- ✅ エラーハンドリング・リトライ機能

### 6.2 停止方法

```powershell
# Ctrl+C で停止
# または、タスクマネージャーでプロセスを終了
```

---

## 7. 個別スクリプト実行

**開発・テスト用。本番では定期実行デーモンを推奨。**

### 7.1 価格同期のみ実行

```powershell
# 全アカウントの価格を同期
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' platforms/base/scripts/sync_prices.py --markup-ratio 1.3" 2>&1 | Select-Object -Last 100

# 特定アカウントのみ同期
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' platforms/base/scripts/sync_prices.py --markup-ratio 1.3 --account base_account_1" 2>&1 | Select-Object -Last 100

# Dry Runモード
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' platforms/base/scripts/sync_prices.py --markup-ratio 1.3 --dry-run" 2>&1 | Select-Object -Last 100
```

**注意:**
- ⚠️ **価格同期のみ**（在庫同期は含まれない）
- ⚠️ ターミナル出力のみ（ログファイルなし）
- ⚠️ 手動実行が必要

---

## 8. 同期ログの監視

### 8.1 リアルタイム監視

```powershell
# 最新50行から表示してリアルタイム確認
Get-Content logs/sync_inventory.log -Tail 50 -Wait

# 最新20行から表示（推奨）
Get-Content logs/sync_inventory.log -Tail 20 -Wait
```

### 8.2 ログのフィルタリング

```powershell
# エラーのみ表示
Get-Content logs/sync_inventory.log -Wait | Select-String "ERROR"

# バッチ処理ログのみ表示
Get-Content logs/sync_inventory.log -Wait | Select-String "バッチ"

# 価格同期ログのみ表示
Get-Content logs/sync_inventory.log -Wait | Select-String "価格同期"

# 在庫同期ログのみ表示
Get-Content logs/sync_inventory.log -Wait | Select-String "在庫同期"
```

### 8.3 ログの内容

**主なログ項目:**
- 初期化ログ（各コンポーネントの起動状況）
- バッチ処理ログ（SP-APIリクエストの進捗）
- 価格同期ログ（更新件数、統計）
- 在庫同期ログ（非公開化・公開化の件数）
- エラーログ（QuotaExceeded、接続エラー等）

---

## 9. トラブルシューティング

### デーモンが起動しない

**原因確認:**

```powershell
# Pythonパスの確認
(Get-Command python).Path

# 仮想環境のPython確認
C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe --version
```

**ロックファイル削除:**

```powershell
# ロックファイルが残っている場合
Remove-Item C:\Users\hiroo\Documents\GitHub\ecauto\logs\multi_account_manager.lock -Force
```

### 処理が進まない

**pending件数の確認:**

```powershell
# 未処理件数とアカウント別内訳を確認
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' C:\Users\hiroo\Documents\GitHub\ecauto\scheduler\scripts\check_queue.py"

# venv activate済みの場合
python scheduler\scripts\check_queue.py
```

**ログでエラー確認:**

```powershell
# エラーのみ表示
Get-Content C:\Users\hiroo\Documents\GitHub\ecauto\logs\upload_scheduler_base_base_account_1.log | Select-String "ERROR"
```

### トークンエラー

**トークン更新:**

```powershell
# BASE APIトークンを手動更新
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' C:\Users\hiroo\Documents\GitHub\ecauto\platforms\base\scripts\refresh_tokens.py"
```

**トークン状態確認:**

```powershell
# トークンの有効期限確認
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' C:\Users\hiroo\Documents\GitHub\ecauto\platforms\base\scripts\check_token_status.py"
```

### 価格・在庫同期のエラー

**SP-APIレート制限エラー（QuotaExceeded）:**

```powershell
# ログでQuotaExceededエラーを確認
Get-Content logs/sync_inventory.log | Select-String "QuotaExceeded"

# 解決策: 実行間隔を長くする（3時間 → 6時間）
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' scheduled_tasks/sync_inventory_daemon.py --interval 21600"
```

**同期デーモンが停止する:**

```powershell
# エラーログを確認
Get-Content logs/sync_inventory.log -Tail 100 | Select-String "ERROR"

# プロセスが実行中か確認
Get-Process python | Where-Object {$_.CommandLine -like "*sync_inventory_daemon*"}
```

**価格が更新されない:**

```powershell
# ログで価格同期の統計を確認
Get-Content logs/sync_inventory.log | Select-String "価格同期完了"

# Dry Runで動作確認
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' scheduled_tasks/sync_inventory_daemon.py --dry-run"
```

---

## 10. 完全フロー例

### ケース1: sourcing ASINを1000件ずつ2アカウントに出品

```powershell
# 1. 事前確認
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' C:\Users\hiroo\Documents\GitHub\ecauto\scheduler\multi_account_manager.py status"

# 2. ASIN追加（1000件ずつ）
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' C:\Users\hiroo\Documents\GitHub\ecauto\sourcing\scripts\import_candidates_to_master.py --account-limits base_account_1:1000,base_account_2:1000"

# 3. デーモン起動
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' C:\Users\hiroo\Documents\GitHub\ecauto\scheduler\multi_account_manager.py start"

# 4. ログ監視
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' C:\Users\hiroo\Documents\GitHub\ecauto\scheduler\view_multi_logs.py"
```

### ケース2: 既存pendingアイテムの出品再開

```powershell
# 1. pending件数確認（アカウント別内訳も表示）
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' C:\Users\hiroo\Documents\GitHub\ecauto\scheduler\scripts\check_queue.py"

# 2. デーモン起動（追加処理なし）
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' C:\Users\hiroo\Documents\GitHub\ecauto\scheduler\multi_account_manager.py start"

# 3. 進捗確認
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' C:\Users\hiroo\Documents\GitHub\ecauto\scheduler\scripts\check_queue.py"
```

### ケース3: 価格・在庫の定期同期（本番運用）

```powershell
# 1. 定期実行デーモンを起動（3時間ごとに自動同期）
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' scheduled_tasks/sync_inventory_daemon.py"

# 2. ログをリアルタイム監視（別ターミナル）
Get-Content logs/sync_inventory.log -Tail 20 -Wait

# 3. エラー発生時の確認
Get-Content logs/sync_inventory.log | Select-String "ERROR"
```

### ケース4: 価格同期のみ手動実行（テスト）

```powershell
# 1. Dry Runで動作確認
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' platforms/base/scripts/sync_prices.py --markup-ratio 1.3 --dry-run" 2>&1 | Select-Object -Last 100

# 2. 問題なければ本番実行
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' platforms/base/scripts/sync_prices.py --markup-ratio 1.3" 2>&1 | Select-Object -Last 100
```

---

## 11. チェックリスト

### 出品前チェック

- [ ] デーモンが停止している
- [ ] sourcing_candidatesに未処理ASINがある（`candidate`状態）
- [ ] upload_queueのpending件数を確認
- [ ] トークンが有効期限内

### 出品中チェック

- [ ] デーモンプロセスが実行中（`status`コマンド）
- [ ] ログでエラーが発生していない
- [ ] pending件数が減少している
- [ ] success件数が増加している

### 出品後チェック

- [ ] pending件数が0になっている
- [ ] failed件数を確認・対応
- [ ] デーモンを停止（必要に応じて）

### 価格・在庫同期チェック

**起動前チェック:**
- [ ] 同期デーモンが停止している（または新規起動）
- [ ] ログディレクトリが存在する（`logs/`）
- [ ] SP-API認証情報が正しく設定されている

**同期中チェック:**
- [ ] デーモンプロセスが実行中
- [ ] ログでエラーが発生していない
- [ ] バッチ処理が正常に動作している
- [ ] 価格更新・在庫更新が記録されている

**同期後チェック:**
- [ ] エラー件数を確認・対応
- [ ] 統計情報を確認（処理件数、更新件数）
- [ ] 次回実行予定時刻が正しい

---

## 12. 高速化Tips

### 並列処理数の最大化

デフォルトでは2アカウントですが、`scheduler/config/accounts_config.py`でアカウントを追加すると、さらに並列化できます。

### バッチサイズの調整

`scheduler/config/accounts_config.py`で`batch_size`を増やすと、1回あたりの処理件数が増えます（デフォルト: 10件）。

```python
DAEMON_CONFIG = {
    'batch_size': 20,  # 10 → 20に変更で高速化
    'interval_seconds': 60,
}
```

**注意:** バッチサイズを大きくすると、エラー時のリトライコストも増えます。

---

## 13. 関連ドキュメント

### 商品出品関連
- [README.md](README.md) - プロジェクト全体の概要
- [QUICKSTART.md](QUICKSTART.md) - 初回セットアップガイド
- [scheduler/README.md](scheduler/README.md) - スケジューラー詳細
- [sourcing/sources/sellersprite/USAGE.md](sourcing/sources/sellersprite/USAGE.md) - SellerSprite使い方

### 価格・在庫同期関連
- [scheduled_tasks/README.md](scheduled_tasks/README.md) - 定期実行デーモン詳細ガイド
- [docs/高優先度機能_使い方ガイド.md](docs/高優先度機能_使い方ガイド.md) - 在庫切れ自動非公開・価格同期
- [docs/BATCH_PROCESSING_IMPLEMENTATION.md](docs/BATCH_PROCESSING_IMPLEMENTATION.md) - バッチ処理実装レポート

---

**最終更新: 2025-12-02**
