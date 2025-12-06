# ISSUE #007: サービス起動時の遅延とバッファリング問題の解決

## 概要

sync_inventoryサービス起動後、ログ出力が遅延する（7-8分）問題と、バックグラウンドプロセスがレート制限を消費する問題を解決。

**日付**: 2025-11-24
**関連ISSUE**: ISSUE_006 (SP-APIレート制限問題)

---

## 問題の詳細

### 問題1: ログ出力の7-8分遅延

**症状**:
```
04:01:15 - デーモン起動
04:01:17 - タスク実行開始
04:01:17 - 在庫同期を開始します
04:09:00 - 統合インベントリ同期を開始  ← 7分43秒の遅延
```

デーモン起動から「在庫同期を開始します」まで2秒だが、「統合インベントリ同期を開始」ログが7分以上遅れて表示される。

**原因**:
- Windowsでログファイルにリダイレクトする際、標準出力がバッファリングされる
- 大量のデータが溜まってから一気にフラッシュされるため、ログが遅延して表示される
- 実際には処理は即座に開始されているが、ログが見えないため遅延しているように見える

### 問題2: バックグラウンドプロセスによるレート制限消費

**症状**:
- Pythonプロセスを停止しても、数秒後に復活する
- サービス起動後にQuotaExceededエラーが発生
- 複数のPythonプロセスが同時実行されている

**原因**:
- Claude Codeが起動したバックグラウンドテストプロセス（6つ）が実行し続けている
- これらが同時にSP-APIを呼び出し、レート制限を消費している

---

## 解決策

### 解決策1: バッファリング無効化

#### 修正ファイル

**1. inventory/scripts/sync_inventory.py**

```python
# Before
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# After
# Windows環境でのUTF-8エンコーディング強制設定 + バッファリング無効化
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except AttributeError:
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
else:
    # UTF-8だがバッファリングを無効化
    try:
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except AttributeError:
        pass
```

**重要なprint文にflush=True追加**:
```python
# run_full_sync()メソッド内
print("\n" + "=" * 70, flush=True)
print("統合インベントリ同期を開始", flush=True)
print("=" * 70, flush=True)
print(f"プラットフォーム: {platform}", flush=True)
print(f"実行モード: {'DRY RUN（実際の更新なし）' if self.dry_run else '本番実行'}", flush=True)
print(f"開始時刻: {self.stats['start_time'].strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
print("=" * 70, flush=True)
print(flush=True)
```

**並列処理無効化の追加**:
```python
# run_price_only()メソッド内（line 161-162）
# ISSUE #006対応: SP-APIレート制限のため並列処理を無効化
price_stats = self.price_sync.sync_all_accounts(dry_run=self.dry_run, parallel=False)
```

**2. platforms/base/scripts/sync_prices.py**

同様のバッファリング無効化とflush=True追加を実施。

#### 修正結果

```
04:39:31 - デーモン起動
04:39:31 - タスク実行開始
04:39:31 - 統合インベントリ同期を開始  ← 即座に表示！
04:39:31 - 価格同期処理を開始
並列処理: 無効
順次処理モード
```

**✅ 成功**: ログが即座に出力されるようになった

---

### 解決策2: バックグラウンドプロセスの停止

#### 実行中のバックグラウンドプロセス（6つ）

1. **10ab9f**: ログ監視 (Get-Content -Wait)
2. **be9332**: sync_prices.py実行
3. **e2bb09**: ログ監視 (Get-Content -Wait)
4. **615dd8**: sync_inventory.py実行
5. **913ab6**: sync_inventory.py実行 (dry-run)
6. **842e62**: sync_inventory.py実行 (dry-run)

#### 停止手順

**ステップ1: NSSMサービスを停止**
```powershell
nssm stop EcAutoSyncInventory
```

**ステップ2: Pythonプロセスを全て停止**

管理者権限のPowerShellで実行：
```powershell
# 全てのPythonプロセスを確認
Get-Process python -ErrorAction SilentlyContinue

# 全て強制停止
Get-Process python | Stop-Process -Force
```

**ステップ3: VSCodeを再起動**

バックグラウンドプロセスがVSCodeのターミナルから起動されている場合、VSCodeを再起動することで完全に停止できる。

**ステップ4: プロセスが停止したことを確認**
```powershell
Get-Process python -ErrorAction SilentlyContinue
# 何も表示されなければ成功
```

**ステップ5: 10-15秒待機**

SP-APIのレート制限をクリアするため待機。

**ステップ6: サービスを起動**
```powershell
nssm start EcAutoSyncInventory
```

---

## 検証手順

サービス起動後、以下を確認：

### 1. ログの即座出力を確認

```powershell
Get-Content 'C:\Users\hiroo\Documents\GitHub\ecauto\logs\sync_inventory_stdout.log' -Tail 50
```

期待される結果：
- デーモン起動から処理開始まで1-2秒以内
- 「統合インベントリ同期を開始」が即座に表示される
- 「並列処理: 無効」と表示される

### 2. QuotaExceededエラーが発生しないことを確認

```powershell
Get-Content 'C:\Users\hiroo\Documents\GitHub\ecauto\logs\sync_inventory_stderr.log' -Tail 50
```

期待される結果：
- QuotaExceededエラーが表示されない
- バッチ処理が正常に進行する（12秒間隔）

### 3. 価格更新が正常に行われることを確認

stdoutログで以下のようなメッセージを確認：
```
[UPDATE] B0899W5G17 | 2,130円 -> 2,830円 (差額 700円)
  Amazon価格: 2,177円
  → 更新成功
```

---

## トラブルシューティング

### Pythonプロセスが復活する場合

**原因**: VSCodeのターミナルまたは他のアプリケーションがPythonプロセスを起動している

**対処法**:
1. VSCodeを完全に閉じる
2. タスクマネージャーを開く（Ctrl+Shift+Esc）
3. 「詳細」タブで python.exe を検索
4. 全てのpython.exeプロセスを右クリック → 「タスクの終了」
5. 再度確認して、プロセスが残っていないことを確認
6. NSSMサービスのみを起動

### QuotaExceededエラーが発生する場合

**原因1**: 他のPythonプロセスが同時にSP-APIを呼び出している

**対処法**:
- 上記の手順でPythonプロセスを全て停止
- 15秒待機してからサービスを起動

**原因2**: 並列処理が有効になっている

**対処法**:
- ログで「並列処理: 無効」と表示されているか確認
- 表示されていない場合は、修正が反映されていない
- サービスを再起動して修正を反映

### ログが遅延して表示される場合

**原因**: バッファリング修正が反映されていない

**対処法**:
1. サービスを停止
2. 修正内容を確認（line_buffering=True、flush=True）
3. サービスを再起動
4. ログを確認

---

## 関連ファイル

### 修正済みファイル

- `inventory/scripts/sync_inventory.py` (line 13-29, 82-89, 161-162)
- `platforms/base/scripts/sync_prices.py` (line 15-31, 472-480)
- `integrations/amazon/sp_api_client.py` (ISSUE_006で修正済み)

### ログファイル

- `logs/sync_inventory_stdout.log` - 標準出力ログ
- `logs/sync_inventory_stderr.log` - エラーログ

---

## 期待される最終状態

### ✅ 成功基準

1. **ログの即座出力**
   - デーモン起動から処理開始まで1-2秒
   - リアルタイムでログが表示される

2. **並列処理の無効化**
   - ログに「並列処理: 無効」と表示
   - ログに「順次処理モード」と表示

3. **QuotaExceededエラーなし**
   - stderrログにQuotaExceededエラーが表示されない
   - バッチ処理が正常に進行する

4. **価格更新の成功**
   - 価格情報が正常に取得される
   - BASEの価格が更新される
   - エラー率が低い（数%以内）

### 📊 パフォーマンス

- **9767件のアカウント**: 約97.8分（489バッチ × 12秒）
- **1005件のアカウント**: 約10.2分（51バッチ × 12秒）
- **合計**: 約108分（1.8時間）

---

## 今後の改善案

### 1. レート制限の最適化

現在: 12秒/リクエスト（10秒公式 + 2秒バッファ）

検討事項:
- 実際のレート制限違反が発生しないか監視
- 安定稼働後、11秒に短縮を検討（処理時間10%短縮）

### 2. バッチサイズの最適化

現在: 20件/バッチ（SP-API制限）

検討事項:
- エラー率とバッチサイズの関係を分析
- 必要に応じてバッチサイズを調整

### 3. エラーハンドリングの改善

- QuotaExceededエラー発生時の自動リトライ
- エラー発生時のSlack/ChatWork通知
- エラーログの詳細化

---

## 参考情報

### SP-API レート制限

**getItemOffersBatch**:
- レート: 0.1 req/sec（10秒/リクエスト）
- バーストトークン: なし
- 最大バッチサイズ: 20件

### 関連ドキュメント

- [ISSUE_006: SP-APIレート制限対策](./ISSUE_006_sp_api_rate_limit_getpricing_migration.md)
- [ISSUE_005: キャッシュ無効化とSP-API優先](./ISSUE_005_cache_skip_for_real_time_pricing.md)

---

## 最終確認チェックリスト

VSCode再起動後、以下を順番に実行：

- [ ] 管理者権限PowerShellでPythonプロセス確認 (`Get-Process python -ErrorAction SilentlyContinue`)
- [ ] Pythonプロセスが全て停止していることを確認
- [ ] NSSMサービス起動 (`nssm start EcAutoSyncInventory`)
- [ ] stdoutログ確認（即座にログが出力されるか）
- [ ] stderrログ確認（QuotaExceededエラーがないか）
- [ ] 30秒後、最初のバッチが成功しているか確認
- [ ] 3-5分後、継続的にバッチ処理が進行しているか確認
- [ ] 価格更新が正常に行われているか確認

全てのチェックが完了したら、**ISSUE #007は完全に解決**です。
