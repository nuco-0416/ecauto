# Issue #001: upload_queueとlistingsの整合性不整合【解決済み】

**ステータス**: ✅ 解決済み
**発生日**: 2025-11-22
**解決日**: 2025-11-22
**担当**: Claude Code

---

## 問題の詳細

### エラー内容

upload_daemon.py実行時に以下のエラーが発生：

```
2025-11-22 16:08:33 [ERROR] upload_scheduler_base: 例外発生: 出品情報が見つかりません: B09JSHR1J8, account=base_account_1
Traceback (most recent call last):
  File "C:\Users\hiroo\Documents\GitHub\ecauto\scheduler\upload_daemon.py", line 255, in _upload_single_item
    raise ValueError(f"出品情報が見つかりません: {asin}, account={account_id}")
ValueError: 出品情報が見つかりません: B09JSHR1J8, account=base_account_1
```

### 根本原因

1. `cleanup_invalid_listings.py` がlistingsテーブルからレコードを削除
2. しかし、対応する `upload_queue` のレコードは削除されていなかった
3. デーモンがキューから商品を取得 → listingsが見つからずエラー

### データ不整合の詳細

- **upload_queue**: 1,745件のレコード（pending + その他）
- **listings**: 削除により対応レコードが欠落
- **不整合レコード**: 99件

#### 不整合の内訳
- `base_account_1, failed`: 48件
- `base_account_1, pending`: 9件
- `base_account_1, success`: 10件
- `base_account_2, failed`: 25件
- `base_account_2, success`: 7件

---

## 問題が発覚した経緯

1. **通知処理を変更**（daemon_base.py, sync_inventory_daemon.py, upload_daemon.py）
2. **デーモンを再起動**
3. **エラーログを確認** → `ValueError: 出品情報が見つかりません`

### タイムライン

1. BASE API → ローカルDB マージ処理を実行（sync_from_base_api.py）
   - BASE APIから9,082件取得
   - ローカルDBに1,829件追加

2. 滞留商品をキューに追加（add_pending_to_queue.py）
   - base_account_1: 831件
   - base_account_2: 795件

3. **不要レコード削除を実行**（cleanup_invalid_listings.py）
   - listingsから削除（Amazon価格未取得など）
   - **upload_queueからは削除されず** ← 問題発生

4. デーモン実行時にエラー発生

---

## 解決方法

### ステップ1: 整合性回復スクリプトの作成

**作成ファイル**: [scheduler/scripts/fix_queue_listings_mismatch.py](../../scheduler/scripts/fix_queue_listings_mismatch.py)

#### 機能
- upload_queueから、対応するlistingsが存在しないレコードを削除
- 全プラットフォーム対象
- DRY RUNモードで影響範囲を事前確認
- 詳細なログを出力（`logs/queue_cleanup_YYYYMMDD_HHMMSS.log`）

#### 実行結果
```bash
# DRY RUN
./venv/Scripts/python.exe scheduler/scripts/fix_queue_listings_mismatch.py --dry-run

# 実行
./venv/Scripts/python.exe scheduler/scripts/fix_queue_listings_mismatch.py --yes
```

**削除件数**: 99件
**ログ**: `logs/queue_cleanup_20251122_172146.log`

### ステップ2: cleanup_invalid_listings.pyの改善

**修正ファイル**: [scheduler/scripts/cleanup_invalid_listings.py](../../scheduler/scripts/cleanup_invalid_listings.py)

#### 改善内容
1. listingsを削除する前に、対応する `upload_queue` も連鎖削除
2. 全プラットフォームを対象（platform指定なし）
3. 詳細なログ出力を追加（3フェーズに分割）
   - フェーズ1: upload_queue削除
   - フェーズ2: listings削除
   - フェーズ3: products削除（テストデータのみ）
4. スクリプトの目的を明確化（緊急時のメンテナンス用）

### ステップ3: 動作確認

1. デーモンが正常実行中であることを確認
2. 整合性回復後、エラーが発生しないことを確認
3. テスト用ASINでアップロード処理が正常に開始されることを確認

---

## 問題解決のために参照したコード・ドキュメント

### 主要ファイル

1. **scheduler/upload_daemon.py** (行252-255)
   - エラー発生箇所
   - `get_listings_by_asin()` でlistingsを取得

2. **inventory/core/master_db.py** (行300-319)
   - `get_listings_by_asin()` の実装

3. **scheduler/scripts/add_pending_to_queue.py** (行149-166)
   - キュー追加時のフィルタリング条件
   - `selling_price IS NOT NULL` のチェック

4. **scheduler/scripts/cleanup_invalid_listings.py**
   - 不要レコード削除処理
   - 元々upload_queueの削除がなかった

### データベーススキーマ

- **upload_queue**: キュー管理
  - `id`, `asin`, `platform`, `account_id`, `scheduled_time`, `status`

- **listings**: 出品情報
  - `id`, `asin`, `platform`, `account_id`, `sku`, `selling_price`, `status`

### ドキュメント

- [README.md](../../README.md) - 2025-11-22の作業履歴
- [QUICKSTART.md](../../QUICKSTART.md) - BASE API同期の手順

---

## 検証結果

### テスト1: scheduled_timeを変更して即座に処理

```bash
./venv/Scripts/python.exe reschedule_for_test.py --yes
```

**結果**:
- ✅ listingsが正常に取得された
- ✅ 「出品情報が見つかりません」エラーは発生しなかった
- ✅ アップロード処理が正常に開始された

### ログ証跡

**整合性回復前**:
```
2025-11-22 16:08:33 [ERROR] upload_scheduler_base: 例外発生: 出品情報が見つかりません: B09JSHR1J8, account=base_account_1
```

**整合性回復後**:
```
2025-11-22 17:33:45 [INFO] upload_scheduler_base: アップロード開始: ASIN=B09KTYVX7Z, Account=base_account_2
```

---

## 今後の対応・推奨事項

### 1. 運用上の注意

- `cleanup_invalid_listings.py` は定期実行不要
- 緊急時のメンテナンス用として使用
- 実行前に必ずバックアップを取得

### 2. データ整合性の原則

システム設計の原則として以下を徹底：

1. **上位の情報が存在しない限り下位のものが存在してはならない**
   - products → listings → upload_queue の階層構造

2. **キューに追加する時点で厳密にバリデーション**
   - 不正なデータを後から修正するのではなく、追加時点で排除

3. **削除時は関連データも連鎖削除**
   - listingsを削除 → upload_queueも削除
   - 外部キー制約的な整合性を保つ

### 3. 防御的実装（将来対応、優先度低）

upload_daemon.pyでlistingsが見つからない場合のエラーハンドリング：
- エラーログを記録してスキップ
- ただし、根本原因を修正した後に実装すべき

---

## 関連Issue

- **Issue #002**: 重複判定処理の問題（新規、未解決）

---

## セッション用プロンプト

次回同様の問題が発生した場合、以下のプロンプトで問題解決を開始：

```
upload_queueとlistingsの整合性に問題があります。

症状:
- upload_daemon.py実行時に「ValueError: 出品情報が見つかりません」エラーが発生
- upload_queueにレコードは存在するが、対応するlistingsが見つからない

確認すべき点:
1. upload_queueとlistingsの対応関係
2. cleanup_invalid_listings.pyなどのメンテナンススクリプトの実行履歴
3. 不整合レコードの件数と内訳

参照ドキュメント:
- docs/issues/ISSUE_001_queue_listings_mismatch_RESOLVED.md
- scheduler/scripts/fix_queue_listings_mismatch.py

対応手順:
1. fix_queue_listings_mismatch.py で不整合を確認（--dry-run）
2. バックアップ取得
3. fix_queue_listings_mismatch.py で整合性回復（--yes）
4. デーモン再起動して動作確認
```
