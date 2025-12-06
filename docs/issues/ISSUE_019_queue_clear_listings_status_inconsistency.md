# ISSUE_019: キュークリア時のlistingsテーブルステータス不整合問題

**日付**: 2025-11-28
**ステータス**: 🔴 未解決
**優先度**: 中
**カテゴリ**: データ整合性 / 仕様改善
**関連ファイル**:
- `inventory/core/master_db.py`
- `scheduler/queue_manager.py`
- `scheduler/scripts/add_to_queue.py`

---

## 📋 問題の概要

upload_queueテーブルのレコードをクリア（削除）した場合、listingsテーブルのステータスが不整合な状態になり、データ管理上の問題が発生する可能性がある。

### 現在の動作

**正常フロー**:
```
1. listings.status = 'pending' (初期状態)
2. upload_queueに追加
3. デーモンがアップロード実行
4. upload_queue.status = 'success'
5. → listings.status = 'listed' (自動更新)
```

**問題のあるフロー**:
```
1. listings.status = 'pending'
2. upload_queueに追加
3. 【ユーザーがキューをクリア】
4. → listings.status = 'pending' のまま残る
5. 再度キューに追加 → 重複登録の危険性
```

---

## 🔍 現在の実装

### upload_queue と listings の連携

**ファイル**: `inventory/core/master_db.py:776-792`

```python
# 成功時はlistingsテーブルも更新
if status == 'success' and queue_info and result_data:
    platform_item_id = result_data.get('platform_item_id')
    if platform_item_id:
        cursor.execute('''
            UPDATE listings
            SET status = 'listed',
                platform_item_id = ?,
                listed_at = ?
            WHERE asin = ? AND platform = ? AND account_id = ?
        ''', (
            platform_item_id,
            now,
            queue_info['asin'],
            queue_info['platform'],
            queue_info['account_id']
        ))
```

**重要な仕様**:
- キューのstatus='success'時**のみ**listingsテーブルを更新
- キューのstatus='failed'や削除時はlistingsテーブルは更新されない

---

## 🚨 具体的な問題シナリオ

### シナリオ1: 時間分散のためのキュー再登録

**ユースケース**:
- 現在のキューが即座に処理される設定（scheduled_time=過去）
- ユーザーが23時までの間で均等分散させたい
- キューをクリアして、`--distribute`オプション付きで再登録したい

**問題**:
1. キューをクリア → upload_queueから1,915件削除
2. listingsテーブルは変更なし（4,049件がpendingのまま）
3. 再度`add_to_queue.py --distribute`を実行
4. 同じ1,915件が再度キューに追加される可能性
5. 重複チェックが機能するが、scheduled_timeが異なるため重複として検出されない可能性

### シナリオ2: キャンセルしたアイテムの管理

**ユースケース**:
- 特定のアイテムをアップロードしたくない
- キューから手動で削除

**問題**:
1. upload_queueから削除
2. listings.status='pending'のまま残る
3. 後日、別のスクリプトで`status='pending'`を検索
4. 削除したはずのアイテムが再度キューに追加される

---

## 📊 現在の状況（2025-11-28時点）

```sql
-- 確認クエリ
SELECT
  'upload_queue (pending)' as type,
  COUNT(*) as count
FROM upload_queue
WHERE status='pending'
UNION ALL
SELECT
  'listings (pending)',
  COUNT(*)
FROM listings
WHERE status='pending' AND platform='base';
```

**結果**:
- upload_queue (pending): **1,915件**
- listings (pending): **4,049件**

**分析**:
- 4,049件のうち1,915件がキューに登録済み
- 残り2,134件はキューに未登録
- キューをクリアすると、1,915件がlistings.status='pending'のまま残る

---

## 💡 改善案

### 案1: キュー削除時のlistingsステータス同期（推奨）

**概要**: キューを削除する際に、listingsテーブルのステータスも適切に更新する

**実装**:
```python
def delete_from_queue(self, queue_id: int, update_listings: bool = True):
    """
    キューからアイテムを削除

    Args:
        queue_id: キューID
        update_listings: listingsテーブルも更新するか（デフォルト: True）
    """
    with self.get_connection() as conn:
        cursor = conn.cursor()

        # キュー情報を取得
        cursor.execute('''
            SELECT asin, platform, account_id, status
            FROM upload_queue
            WHERE id = ?
        ''', (queue_id,))
        queue_info = cursor.fetchone()

        # キューから削除
        cursor.execute('DELETE FROM upload_queue WHERE id = ?', (queue_id,))

        # listingsテーブルを更新
        if update_listings and queue_info and queue_info['status'] in ('pending', 'scheduled'):
            # pending/scheduledの場合、listingsのstatusは変更しない
            # または 'cancelled' などの新しいステータスを設定
            pass
```

**メリット**:
- データ整合性が保たれる
- 削除したアイテムを明確に追跡可能

**デメリット**:
- 新しいステータス（'cancelled'など）を定義する必要がある
- 既存のスクリプトの修正が必要

---

### 案2: キュー再登録時の重複チェック強化

**概要**: キューに追加する際、既存のpendingレコードをチェックして削除

**実装**:
```python
def add_to_queue(self, asin: str, platform: str, account_id: str, ...):
    """既存の pending/scheduled レコードをチェックして削除"""
    with self.get_connection() as conn:
        cursor = conn.cursor()

        # 既存の未処理レコードを削除
        cursor.execute('''
            DELETE FROM upload_queue
            WHERE asin = ? AND platform = ? AND account_id = ?
            AND status IN ('pending', 'scheduled')
        ''', (asin, platform, account_id))

        # 新しいレコードを追加
        cursor.execute('''INSERT INTO upload_queue ...''')
```

**メリット**:
- シンプルな実装
- 重複レコードを防止

**デメリット**:
- 意図せず既存のスケジュールを削除してしまう可能性
- 履歴追跡が困難

---

### 案3: listings.status に新しい状態を追加

**概要**: listingsテーブルに'queued'ステータスを追加

**状態遷移**:
```
pending → queued (キュー追加時)
queued → listed (アップロード成功時)
queued → pending (キュー削除時、または失敗時)
```

**実装**:
```python
# キュー追加時
def add_to_queue(self, asin: str, ...):
    # upload_queueに追加
    self.db.add_to_upload_queue(...)

    # listingsのstatusを'queued'に更新
    self.db.update_listing_status(
        asin=asin,
        platform=platform,
        account_id=account_id,
        status='queued'
    )

# キュー削除時
def delete_from_queue(self, queue_id: int):
    # listingsのstatusを'pending'に戻す
    self.db.update_listing_status(..., status='pending')

    # upload_queueから削除
    self.db.delete_from_upload_queue(queue_id)
```

**メリット**:
- 状態が明確に追跡可能
- データ整合性が保たれる
- 既存のステータス値（'pending', 'listed'）と互換性あり

**デメリット**:
- 既存のコードを広範囲に修正する必要がある
- listings.statusの定義を変更（現在: 'pending', 'queued', 'listed', 'sold', 'delisted'）

---

## 🎯 推奨アクション

### 短期対応（優先度: 中）

1. **ドキュメント整備**
   - キュー操作時の注意事項をREADMEに追加
   - 安全なキュー削除手順を記載

2. **スクリプト追加**
   - `scheduler/scripts/clear_queue_safely.py` を作成
   - listingsテーブルとの整合性を保ちながらキューをクリア

### 長期対応（優先度: 低）

1. **案3の実装**
   - listings.statusに'queued'を追加
   - キュー操作時に自動的にlistingsテーブルを更新
   - データ整合性を保証

2. **UIツール開発**
   - キューとlistingsの状態を可視化
   - 安全な操作をサポート

---

## 📝 関連情報

### 確認コマンド

```bash
# キューとlistingsの状態を確認
python -c "
import sqlite3
conn = sqlite3.connect('inventory/data/master.db')
cursor = conn.cursor()
cursor.execute('SELECT COUNT(*) FROM upload_queue WHERE status=\"pending\"')
print(f'Pending queue items: {cursor.fetchone()[0]}')
cursor.execute('SELECT COUNT(*) FROM listings WHERE status=\"pending\" AND platform=\"base\"')
print(f'Pending listings: {cursor.fetchone()[0]}')
conn.close()
"
```

### 関連ドキュメント

- [scheduler/README.md](../../scheduler/README.md) - スケジューラー使用ガイド
- [inventory/core/master_db.py](../../inventory/core/master_db.py) - データベース管理
- [ISSUE_001](ISSUE_001_queue_listings_mismatch_RESOLVED.md) - 類似の問題（解決済み）

---

## 🏷️ タグ

`data-integrity` `queue-management` `listings-status` `improvement` `medium-priority`
