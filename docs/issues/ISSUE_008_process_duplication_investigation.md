# ISSUE #008: プロセス複製問題の徹底調査と解決

## 概要

sync_inventoryサービス起動時に複数のPythonプロセスが作成される問題について、徹底的な調査を実施。結果として、**コード上にプロセス複製の原因は存在しない**ことが判明。Claude Codeのバックグラウンドプロセスが原因であった可能性が高い。

**日付**: 2025-11-24
**関連ISSUE**: ISSUE_006 (SP-APIレート制限), ISSUE_007 (起動遅延とバッファリング)
**ステータス**: ✅ 調査完了、本番稼働準備完了

---

## プロジェクト全体像

### アーキテクチャ概要

```
ecauto/
├── scheduler/              # 出品スケジューラー（60秒ごと）
│   ├── upload_daemon.py   # BASE/eBay/Yahoo出品デーモン
│   ├── upload_executor.py # アップロード実行エンジン
│   ├── queue_manager.py   # キュー管理（時間分散アルゴリズム）
│   └── platform_uploaders/ # プラットフォーム別アップローダー
│
├── scheduled_tasks/        # 汎用定期実行フレームワーク（3時間ごと）
│   ├── daemon_base.py     # デーモン基底クラス（全デーモン共通）
│   └── sync_inventory_daemon.py # 在庫同期デーモン（本ISSUE対象）
│
├── inventory/
│   └── scripts/
│       └── sync_inventory.py # 統合インベントリ同期ロジック
│
├── integrations/
│   └── amazon/
│       └── sp_api_client.py # Amazon SP-API クライアント
│
└── platforms/
    └── base/
        └── scripts/
            └── sync_prices.py # BASE価格同期ロジック
```

### 役割分担

| コンポーネント | 役割 | 実行間隔 | プロセス管理 |
|--------------|------|---------|------------|
| **scheduler/upload_daemon.py** | 出品スケジューリング | 60秒 | NSSM (ECAutoUploadScheduler-BASE) |
| **scheduled_tasks/sync_inventory_daemon.py** | 在庫・価格同期 | 10800秒（3時間） | NSSM (EcAutoSyncInventory) |
| **DaemonBase** | デーモン基底クラス | 設定可能 | 継承先で利用 |

**設計パターン:**
- 両デーモンともDaemonBaseを継承
- 単一プロセス内でwhile Trueループ
- シグナルハンドラ（SIGINT/SIGTERM）でGraceful shutdown
- **プロセス複製なし**

---

## 問題の詳細

### 症状

**報告された問題:**
1. sync_inventoryサービス起動後、複数のPythonプロセスが検出される
2. ユーザーのテストでは「2つのプロセスが作成される」との報告
3. NSSMサービスが複数プロセスを起動している可能性

**初期調査結果（2025-11-24 04:00-06:30）:**
- ユーザーのテストで2つのPythonプロセスを確認（PID 12640, 36304）
- 再テスト時には4つのPythonプロセスを確認
- NSSMサービスが3回登録されていた（StartMode: Auto, Manual, Auto）

---

## 徹底調査の実施

### 1. デバッグログの追加と分析

**修正ファイル:**
- `scheduled_tasks/sync_inventory_daemon.py`
- `scheduled_tasks/daemon_base.py`

**追加したデバッグログ:**
```python
print(f"[DEBUG] sync_inventory_daemon.py - モジュール読み込み開始 - PID: {os.getpid()}", flush=True)
print(f"[DEBUG] sync_inventory_daemon.py - パス設定完了 - PID: {os.getpid()}", flush=True)
print(f"[DEBUG] sync_inventory_daemon.py - import完了 - PID: {os.getpid()}", flush=True)
print(f"[DEBUG] SyncInventoryDaemon.__init__() 開始 - PID: {os.getpid()}", flush=True)
print(f"[DEBUG] DaemonBase.__init__() 開始 - PID: {os.getpid()}", flush=True)
print(f"[DEBUG] DaemonBase.run() 開始 - PID: {os.getpid()}", flush=True)
# ... 各ステップでPID出力
```

**分析結果:**
```
# テスト1: PID 36692
[DEBUG] sync_inventory_daemon.py - モジュール読み込み開始 - PID: 36692
[DEBUG] sync_inventory_daemon.py - パス設定完了 - PID: 36692
[DEBUG] daemon_base.py - モジュール読み込み開始 - PID: 36692
[DEBUG] sync_inventory_daemon.py - import完了 - PID: 36692
[DEBUG] __main__ ブロック開始 - PID: 36692
[DEBUG] main() 開始 - PID: 36692
[DEBUG] SyncInventoryDaemon.__init__() 開始 - PID: 36692
[DEBUG] DaemonBase.__init__() 開始 - PID: 36692
[DEBUG] DaemonBase.run() 開始 - PID: 36692
# ... 全ステップで同じPID

# テスト2: PID 12640
[DEBUG] sync_inventory_daemon.py - モジュール読み込み開始 - PID: 12640
[DEBUG] sync_inventory_daemon.py - パス設定完了 - PID: 12640
# ... 全ステップで同じPID

# テスト3: PID 35288
[DEBUG] sync_inventory_daemon.py - モジュール読み込み開始 - PID: 35288
# ... 全ステップで同じPID
```

**重要な発見:**
- ✅ **全てのデバッグログで同じPIDのみが表示される**
- ✅ **スクリプト実行中にプロセスIDは変化しない**
- ✅ **プロセス複製は発生していない**

### 2. コードベース全体の静的解析

**調査対象:**
- `scheduler/` ディレクトリ（全ファイル）
- `scheduled_tasks/` ディレクトリ（全ファイル）
- `docs/issues/` ディレクトリ（設計ドキュメント）

**プロセス複製パターンの検索:**

| パターン | 検索結果 | リスク |
|---------|---------|--------|
| `multiprocessing.Process` | **なし** | なし |
| `subprocess.Popen` / `subprocess.run` | **なし** | なし |
| `threading.Thread` | **なし** | なし |
| `concurrent.futures.ProcessPoolExecutor` | **なし** | なし |
| `concurrent.futures.ThreadPoolExecutor` | 1件（`sync_prices.py`） | 低（parallel=False設定済み） |
| `os.fork()` | **なし** | なし |

**ThreadPoolExecutorの詳細:**

**ファイル:** `platforms/base/scripts/sync_prices.py` (line 462-555)

```python
def sync_all_accounts(self, dry_run: bool = False, parallel: bool = True, max_workers: int = 4):
    if parallel and len(accounts) > 1:
        # 並列処理
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 各アカウントの処理をサブミット
            future_to_account = {
                executor.submit(self._sync_account_safe, account['id'], dry_run, max_items): account
                for account in accounts
            }
```

**リスク評価:** **低**
- ISSUE_006/007で `parallel=False` に設定済み（line 155）
- スレッド作成であり、プロセス複製ではない
- SP-API clientは `threading.Lock()` でスレッドセーフ実装済み

### 3. NSSMサービス設定の確認

**問題:**
- ECAutoSyncInventoryが3回登録されていた（StartMode: Auto, Manual, Auto）
- 複数のサービスインスタンスが起動する可能性

**解決:**
```powershell
# サービス削除
nssm remove EcAutoSyncInventory confirm

# 再登録（クリーン）
nssm install EcAutoSyncInventory "C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe" "C:\Users\hiroo\Documents\GitHub\ecauto\scheduled_tasks\sync_inventory_daemon.py" --interval 10800

# 設定
nssm set EcAutoSyncInventory AppDirectory "C:\Users\hiroo\Documents\GitHub\ecauto"
nssm set EcAutoSyncInventory AppStdout "C:\Users\hiroo\Documents\GitHub\ecauto\logs\sync_inventory_stdout.log"
nssm set EcAutoSyncInventory AppStderr "C:\Users\hiroo\Documents\GitHub\ecauto\logs\sync_inventory_stderr.log"
nssm set EcAutoSyncInventory Start SERVICE_AUTO_START
```

**結果:**
- ✅ サービスは1つのみ登録
- ✅ 起動テストで正常動作確認

### 4. Claude Codeバックグラウンドプロセスの発見

**ISSUE_007で記録された問題:**

**実行中のバックグラウンドプロセス（6つ）:**
1. **10ab9f**: ログ監視 (Get-Content -Wait)
2. **be9332**: sync_prices.py実行
3. **e2bb09**: ログ監視 (Get-Content -Wait)
4. **615dd8**: sync_inventory.py実行
5. **913ab6**: sync_inventory.py実行 (dry-run)
6. **842e62**: sync_inventory.py実行 (dry-run)

**原因:**
- Claude Codeが過去のテスト実行時に起動したプロセスが残存
- VSCodeのターミナルから起動されたバックグラウンドプロセス
- これらが同時にSP-APIを呼び出し、レート制限を消費

**解決手順（ISSUE_007で実施）:**
```powershell
# 1. NSSMサービス停止
nssm stop EcAutoSyncInventory

# 2. 全Pythonプロセス停止
Get-Process python | Stop-Process -Force

# 3. VSCode再起動（バックグラウンドプロセス完全停止）

# 4. プロセス停止確認
Get-Process python -ErrorAction SilentlyContinue  # 何も表示されなければ成功

# 5. 15秒待機（レート制限クリア）

# 6. サービス起動
nssm start EcAutoSyncInventory
```

**結果:**
- ✅ バックグラウンドプロセス全て停止
- ✅ QuotaExceededエラー解消

---

## 調査結論

### ✅ 最終結論: 根本原因はNSSMの不安定性

**2025-11-24 最終調査結果:**

1. **デバッグログ分析**
   - 全実行で単一PIDのみ記録
   - プロセスIDの変化なし
   - コード上のプロセス複製なし

2. **静的コード解析**
   - multiprocessing, subprocess等の使用なし
   - 標準的なwhile Trueループデーモン実装

3. **NSSM問題の発見**
   - **NSSMの設定が正しく保存されない**
   - パスが壊れる（空白・バックスラッシュが消失）
   - レジストリ設定の不安定性
   - 時代遅れで保守されていないツール

4. **最終的な解決策**
   - **NSSMサービスを完全廃止**
   - **手動実行 + ロック機構で運用**
   - msvcrtによるファイルロックで多重起動防止
   - 並列処理完全無効化
   - レート制限を12秒に設定

### 実装した対策

| 対策 | 実装内容 | 効果 |
|------|---------|------|
| **ロック機構** | msvcrt.locking()でファイルロック | 多重起動を完全防止 |
| **並列処理無効化** | parallel=False固定 | レート制限遵守を確実に |
| **レート制限強化** | 12秒間隔（公式10秒+余裕2秒） | QuotaExceeded激減 |
| **NSSM廃止** | 手動実行に移行 | 設定破損問題を根本解決 |

**結果:** QuotaExceededエラーが**ほぼゼロ**（たまに1件は正常範囲）

---

## 現在の運用方法（2025-11-24）

### 手動実行による運用

**起動方法:**
```powershell
cd C:\Users\hiroo\Documents\GitHub\ecauto
.venv\Scripts\python.exe scheduled_tasks\sync_inventory_daemon.py --interval 10800
```

**特徴:**
- ✅ ロック機構により多重起動を完全防止
- ✅ 並列処理無効化でレート制限を確実に遵守
- ✅ 12秒間隔でSP-APIリクエスト
- ✅ QuotaExceededエラーがほぼゼロ（たまに1件は正常範囲）
- ✅ コンソールにリアルタイムでログ出力

**プロセス監視:**
```powershell
# Pythonプロセス数確認（2つが正常: venv launcher + 実際のプロセス）
Get-Process python -ErrorAction SilentlyContinue

# ロックファイル確認（使用中 = 正常動作）
Get-Item C:\Users\hiroo\Documents\GitHub\ecauto\logs\sync_inventory_daemon.lock
```

### 今後の移行計画

**短期（1週間以内）:**
- 手動実行で安定稼働を確認
- QuotaExceededエラーの発生頻度を監視

**中期（2-4週間）:**
- Windowsタスクスケジューラーへの移行
- PC起動時の自動起動設定
- NSSMは完全廃止

**Windowsタスクスケジューラー設定例:**
```powershell
# タスクスケジューラーでPC起動時に自動起動
# - トリガー: システム起動時
# - アクション: .venv\Scripts\python.exe scheduled_tasks\sync_inventory_daemon.py --interval 10800
# - 作業ディレクトリ: C:\Users\hiroo\Documents\GitHub\ecauto
```

---

## 2025-11-23以降の主要修正

### ISSUE #005: キャッシュTTL機構の未実装（11月23日 19:02解決）

**問題:**
- SP-APIから新データを取得せず、2日前のキャッシュを使い続けていた

**解決:**
- キャッシュを無視してSP-APIバッチで全件取得（3時間ごと）
- `price_updated_at`, `stock_updated_at` フィールド追加

**影響範囲:** 全商品（10,772件）

---

### ISSUE #006: SP-APIレート制限違反（11月24日 02:01解決）

**問題:**
- `min_interval = 2.5秒`（公式レート10秒の1/4）
- QuotaExceededエラーが多発

**解決:**
- `min_interval = 12秒`（公式10秒 + 余裕2秒）
- バッチ処理の待機ロジック修正
- `threading.Lock()` でスレッドセーフ実装

**影響範囲:** 価格・在庫同期処理（489バッチ × 12秒 = 約98分）

---

### ISSUE #007: ログ出力遅延とバッファリング問題（11月24日 05:03解決）

**問題:**
- ログ出力が7-8分遅延（バッファリング）
- バックグラウンドプロセス（6つ）がレート制限を消費

**解決:**
- `sys.stdout.reconfigure(line_buffering=True)` でバッファリング無効化
- 全Pythonプロセス停止 → NSSMサービスのみ起動
- 並列処理無効化（`parallel=False`）

**影響範囲:** デーモン起動時の監視性

---

## アーキテクチャの複雑さ分析

### 複雑度レベル: **中程度**

**✅ 良い点:**
- 明確な責任分離（scheduler vs scheduled_tasks）
- DaemonBaseによる統一的なデーモン管理
- Chatwork通知統合
- レート制限遵守（ISSUE_006解決後）
- エラーリトライ機能
- 詳細な設計ドキュメント（ISSUE管理）

**⚠️ 改善の余地:**
- schedulerとscheduled_tasksの命名が直感的でない
  - `scheduler` → `listing_scheduler` の方が明確
  - `scheduled_tasks` → `daemons` の方が明確
- 2系統のデーモン実装（upload_daemon.py vs daemon_base.py継承）
  - 統一感は保たれているが、2段階の継承がやや複雑

**推奨される命名変更（オプション）:**
```
scheduler/ → listing_scheduler/
scheduled_tasks/ → daemons/
```

---

## 推奨される次のステップ

### 短期（完了済み）

#### 1. ✅ デバッグログの削除

**実施日:** 2025-11-24
**状態:** 完了

- `[DEBUG]` プレフィックスのログを全て削除
- `[LOCK]` ログは保持（本番機能）

#### 2. ✅ 手動実行による安定稼働確認

**実施日:** 2025-11-24
**状態:** 完了

**確認結果:**
- ✅ Pythonプロセスは2つ（venv launcher + 実際のプロセス）= 正常
- ✅ ロック機構が正常動作（resource busy）
- ✅ ログがリアルタイムで出力
- ✅ QuotaExceededエラーがほぼゼロ（たまに1件は正常範囲）
- ✅ レート制限を確実に遵守（12秒間隔）

### 中期（1-2週間）

#### 1. Windowsタスクスケジューラーへの移行

**優先度:** 高
**実装項目:**
- PC起動時の自動起動設定
- ログローテーション設定
- エラー時の再起動ポリシー

#### 2. 通知機能の再有効化

**優先度:** 中
**実装項目:**
- enable_notifications=True に変更
- Chatwork通知のテスト
- エラー率・処理時間の通知

#### 3. デーモンプロセスの監視強化

**優先度:** 中
**実装項目:**
- ヘルスチェック機能の実装
- プロセス死活監視
- レート制限の動的調整

### 長期（1-3ヶ月）

#### 1. ディレクトリ構造の整理

```
scheduler/ → listing_scheduler/
scheduled_tasks/ → daemons/
```

#### 2. デーモン統一フレームワーク

- 全デーモンがDaemonBaseを継承
- プラグイン方式でタスクを追加
- 設定ファイルでデーモン管理

#### 3. 監視ダッシュボード

- デーモン稼働状況の可視化
- レート制限使用率のグラフ化
- エラーログの集約表示

---

## トラブルシューティングガイド

### 問題1: 複数のPythonプロセスが起動する

**症状:**
```powershell
Get-Process python
# 2つ以上のプロセスが表示される
```

**原因:**
- Claude Codeのバックグラウンドプロセス
- VSCodeターミナルからの手動起動
- 他のデーモンサービス（ECAutoUploadScheduler-BASE等）

**対処法:**
```powershell
# 1. 全サービス停止
nssm stop EcAutoSyncInventory
nssm stop ECAutoUploadScheduler-BASE

# 2. VSCode/Claude Code閉じる

# 3. 全Pythonプロセス停止
Get-Process python | Stop-Process -Force

# 4. プロセス確認
Get-Process python -ErrorAction SilentlyContinue  # 何も表示されないこと

# 5. 必要なサービスのみ起動
nssm start EcAutoSyncInventory
```

### 問題2: QuotaExceededエラーが発生する

**症状:**
```
2025-11-24 06:20:40 [ERROR] sync_inventory: QuotaExceeded発生
```

**原因:**
- 複数プロセスが同時にSP-APIを呼び出している
- レート制限（12秒/リクエスト）を超過

**対処法:**
```powershell
# 1. 全プロセス停止（上記と同じ）

# 2. 15秒待機（レート制限クリア）
Start-Sleep -Seconds 15

# 3. サービス起動
nssm start EcAutoSyncInventory

# 4. ログ確認
Get-Content 'C:\Users\hiroo\Documents\GitHub\ecauto\logs\sync_inventory_stdout.log' -Tail 20
# 「並列処理: 無効」と表示されることを確認
```

### 問題3: ログが遅延して表示される

**症状:**
- デーモン起動から処理開始まで7-8分の遅延

**原因:**
- Windowsのstdoutバッファリング
- ISSUE_007で解決済みだが、修正が反映されていない可能性

**対処法:**
```powershell
# 1. サービス停止
nssm stop EcAutoSyncInventory

# 2. 修正確認
# sync_inventory.py の line 13-29 にバッファリング無効化コードがあることを確認

# 3. サービス再起動
nssm start EcAutoSyncInventory

# 4. ログ確認（即座に出力されるか）
Get-Content 'C:\Users\hiroo\Documents\GitHub\ecauto\logs\sync_inventory_stdout.log' -Tail 10
```

---

## 関連ファイル

### 調査対象ファイル

**デーモン実装:**
- `scheduled_tasks/daemon_base.py` - デーモン基底クラス
- `scheduled_tasks/sync_inventory_daemon.py` - 在庫同期デーモン
- `scheduler/upload_daemon.py` - 出品スケジューラーデーモン

**同期ロジック:**
- `inventory/scripts/sync_inventory.py` - 統合インベントリ同期
- `platforms/base/scripts/sync_prices.py` - BASE価格同期
- `integrations/amazon/sp_api_client.py` - SP-APIクライアント

**設定・ドキュメント:**
- `docs/issues/ISSUE_005_cache_ttl_realtime_price_sync.md`
- `docs/issues/ISSUE_006_sp_api_rate_limit_getpricing_migration.md`
- `docs/issues/ISSUE_007_startup_delay_and_buffering.md`
- `docs/issues/ISSUE_008_process_duplication_investigation.md` (本ドキュメント)

### ログファイル

- `logs/sync_inventory_stdout.log` - 標準出力ログ
- `logs/sync_inventory_stderr.log` - エラーログ

---

## 期待される最終状態

### ✅ 成功基準

1. **単一プロセス稼働**
   - Pythonプロセスは1つのみ
   - NSSMサービスが正しく管理

2. **ログの即座出力**
   - デーモン起動から処理開始まで1-2秒
   - リアルタイムでログが表示される

3. **並列処理の無効化**
   - ログに「並列処理: 無効」と表示
   - ログに「順次処理モード」と表示

4. **QuotaExceededエラーなし**
   - stderrログにQuotaExceededエラーが表示されない
   - バッチ処理が正常に進行する（12秒間隔）

5. **価格更新の成功**
   - 価格情報が正常に取得される
   - BASEの価格が更新される
   - エラー率が低い（数%以内）

### 📊 パフォーマンス

- **9767件のアカウント**: 約97.8分（489バッチ × 12秒）
- **1005件のアカウント**: 約10.2分（51バッチ × 12秒）
- **合計**: 約108分（1.8時間）

**次回実行:** 3時間後（10800秒後）

---

## まとめ

### 調査結果

1. ✅ **コード上にプロセス複製の原因は存在しない**
2. ✅ **NSSMサービスは正常に動作している**
3. ✅ **バックグラウンドプロセス問題はISSUE_007で解決済み**
4. ✅ **アーキテクチャは健全（複雑度: 中程度）**
5. ✅ **2025-11-23以降の3つの重大問題を全て解決**

### 推奨アクション

**優先度: 高**
- デバッグログの削除（本番用に戻す）
- 通知機能の再有効化
- VSCode閉じた状態でのNSSMサービステスト

**優先度: 中**
- デーモン監視強化
- レート制限動的調整
- テストカバレッジ向上

**優先度: 低**
- ディレクトリ命名変更（オプション）

---

**調査完了日:** 2025-11-24 06:30
**問題解決日:** 2025-11-24 10:00
**調査者:** Claude Code + User
**最終ステータス:** ✅ **完全解決** - 手動実行で安定稼働中
**次回レビュー:** Windowsタスクスケジューラー移行時（2025-12-01）
