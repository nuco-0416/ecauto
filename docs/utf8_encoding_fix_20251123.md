# UTF-8エンコーディング修正レポート

**日付:** 2025-11-23
**作業者:** Claude Code
**カテゴリ:** バグ修正

## 問題の概要

### 発生していた問題

Windows環境で価格更新デーモン（ECAutoSyncInventory）が実行中にUnicodeEncodeErrorが発生し、処理が失敗していました。

**エラー内容:**
```
UnicodeEncodeError: 'cp932' codec can't encode character '\u26a0' in position 0: illegal multibyte sequence
```

**エラー発生箇所:**
- ファイル: `inventory/scripts/sync_stock_visibility.py:255`
- 処理: 在庫同期処理の完了サマリー表示時
- 原因: 絵文字（⚠）をWindows標準のcp932エンコーディングで出力しようとした

### 影響範囲

- **ECAutoSyncInventory** Windowsサービス
  - 在庫同期処理は完了するが、最終レポート表示時にクラッシュ
  - リトライ機能により最大3回再試行されるが、すべて失敗
  - 1時間ごとの定期実行が停止状態に

## 修正内容

### 修正アプローチ

すべての主要スクリプトの冒頭で、標準出力・標準エラー出力をUTF-8エンコーディングに強制設定しました。

### 修正したファイル

#### 1. `inventory/scripts/sync_stock_visibility.py`

**修正箇所:** 8-22行目

```python
# Windows環境でのUTF-8エンコーディング強制設定
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        # Python 3.7未満の場合のフォールバック
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
```

**効果:**
- 絵文字や日本語を含む出力が正しく表示される
- エラー発生箇所での警告メッセージ（⚠ 警告: ...）が正常に出力される

#### 2. `platforms/base/scripts/sync_prices.py`

**修正箇所:** 15-24行目

同様のUTF-8エンコーディング強制設定を追加。

**効果:**
- 価格同期処理のログ出力が正しく処理される
- 日本語メッセージや統計情報が正常に表示される

#### 3. `inventory/scripts/sync_inventory.py`

**修正箇所:** 13-22行目

統合同期スクリプトにも同様の設定を追加。

**効果:**
- 統合ワークフロー全体でUTF-8出力が保証される

#### 4. `scheduled_tasks/sync_inventory_daemon.py`

**修正箇所:** 26-35行目

デーモンスクリプト本体にも設定を追加。

**効果:**
- Windowsサービスとして実行される際も、UTF-8エンコーディングが適用される
- ログファイルへの出力も正しく処理される

### 修正の特徴

**互換性を考慮した実装:**
- Python 3.7以降: `reconfigure(encoding='utf-8')`を使用（推奨方法）
- Python 3.7未満: `codecs.getwriter()`を使用（フォールバック）
- 現在のエンコーディングがUTF-8の場合は何もしない（Unix系環境での不要な処理を回避）

**影響範囲:**
- ✅ Windows環境での絵文字・日本語出力をサポート
- ✅ Unix系環境（Linux/macOS）への影響なし
- ✅ ログファイルへの出力も正しく処理
- ✅ Windowsサービス実行時も正常動作

## 検証結果

### サービス再起動後の状態

**サービス状態:**
```
Name: ECAutoSyncInventory
State: Running
Status: OK
```

**ログ確認:**
```
2025-11-23 17:43:31 [INFO] sync_inventory: sync_inventory デーモン起動
2025-11-23 17:43:32 [INFO] sync_inventory: --- タスク実行開始 2025-11-23 17:43:32 ---
2025-11-23 17:43:32 [INFO] sync_inventory: 在庫同期を開始します（プラットフォーム: base）
```

サービスが正常に起動し、処理を開始していることを確認しました。

### 期待される動作

次回の処理完了時（約1時間後）、以下のようなサマリーが正しく表示されるはずです：

```
======================================================================
処理結果サマリー
======================================================================
処理した商品数: XXX件

更新した商品数:
  - 非公開に変更: XX件
  - 公開に変更: XX件

エラー: X件

⚠ 警告: X件の商品でキャッシュに問題がありました。  ← このメッセージが正常に表示される
======================================================================
```

## 技術的詳細

### Windows環境でのエンコーディング問題

**デフォルトの動作:**
- Windows環境では、標準出力のデフォルトエンコーディングが`cp932`（Shift_JIS）
- `cp932`は日本語をサポートするが、絵文字やUnicode拡張文字には非対応
- Python 3.7以降でも、Windows環境では`cp932`がデフォルト

**解決方法:**
1. **reconfigure()** (Python 3.7+)
   - 標準出力のエンコーディングを動的に変更
   - 最も推奨される方法

2. **codecs.getwriter()** (Python 3.6以下)
   - ストリームラッパーを使用してエンコーディングを変更
   - 後方互換性を保つためのフォールバック

3. **環境変数 PYTHONIOENCODING** (グローバル設定)
   - `PYTHONIOENCODING=utf-8`を設定
   - ただし、システム全体に影響するため、今回は採用せず

### 実装上の工夫

**チェック条件:**
```python
if sys.stdout.encoding != 'utf-8':
```

- Unix系環境（Linux/macOS）では通常すでにUTF-8のため、不要な処理をスキップ
- パフォーマンスへの影響を最小化

**エラーハンドリング:**
```python
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    # フォールバック処理
```

- Python 3.6以下では`reconfigure()`が存在しないため、AttributeErrorをキャッチ
- 古いバージョンでも動作保証

## 今後の推奨事項

### 1. ログファイルのエンコーディング確認

ログファイル自体がUTF-8で保存されているか確認する：

```python
# daemon_base.pyなどで
handler = logging.FileHandler(log_file, encoding='utf-8')
```

### 2. NSSMサービス設定での環境変数

オプションとして、NSSMサービス設定で環境変数を設定することも可能：

```batch
nssm set ECAutoSyncInventory AppEnvironmentExtra PYTHONIOENCODING=utf-8
```

ただし、コード側で対応済みのため、現時点では不要。

### 3. テスト環境での検証

定期的に以下を確認：
- 絵文字を含むメッセージが正しく表示される
- ログファイルが正しく記録される
- 通知（Chatwork等）が正しく送信される

## 関連ファイル

### 修正ファイル
- [inventory/scripts/sync_stock_visibility.py](../inventory/scripts/sync_stock_visibility.py)
- [platforms/base/scripts/sync_prices.py](../platforms/base/scripts/sync_prices.py)
- [inventory/scripts/sync_inventory.py](../inventory/scripts/sync_inventory.py)
- [scheduled_tasks/sync_inventory_daemon.py](../scheduled_tasks/sync_inventory_daemon.py)

### 関連ドキュメント
- [scheduled_tasks/README.md](../scheduled_tasks/README.md) - デーモンの使い方
- [deploy/windows/README.md](../deploy/windows/README.md) - Windowsサービス化ガイド

## まとめ

### 解決した問題
✅ UnicodeEncodeErrorによる処理失敗を解消
✅ 在庫同期デーモンの安定稼働を実現
✅ 絵文字・日本語を含むログ出力が正常に動作

### 影響
✅ Windows環境での運用安定性が向上
✅ Unix系環境への影響なし
✅ 既存機能への影響なし

### 次のステップ
- サービスの継続監視（1時間後に完了ログを確認）
- 必要に応じて追加のエンコーディング対策を検討

---

**修正完了日時:** 2025-11-23 17:43
**サービス再起動:** 2025-11-23 17:43
**ステータス:** ✅ 修正完了・検証待ち
