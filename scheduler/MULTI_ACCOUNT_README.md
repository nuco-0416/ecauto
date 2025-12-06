# マルチアカウント並列アップロード

> **📢 重要なお知らせ**
>
> **このドキュメントは [scheduler/README.md](README.md) に統合されました。**
>
> 最新の情報は [scheduler/README.md](README.md) を参照してください。
>
> このファイルは後方互換性のために残されていますが、今後は更新されません。

---

## 概要

複数のアカウント・プラットフォームで並列アップロードを実行するシステムです。

### 特徴

- ✅ **アカウント別並列処理**: 各アカウントが独立したプロセスで動作
- ✅ **プラットフォーム別並列処理**: BASE、eBay、Yahoo!等を同時処理可能
- ✅ **自動再起動**: プロセスが停止した場合、自動的に再起動
- ✅ **後方互換性**: 既存の `upload_daemon.py` と併用可能
- ✅ **個別ログ**: アカウント別にログファイルを出力
- ✅ **設定ファイル管理**: `accounts_config.py` で簡単に構成変更

---

## アーキテクチャ

```
multi_account_manager.py (親プロセス)
├── upload_daemon_account.py --platform base --account base_account_1
├── upload_daemon_account.py --platform base --account base_account_2
├── upload_daemon_account.py --platform ebay --account ebay_account_1
└── upload_daemon_account.py --platform yahoo --account yahoo_account_1
```

各プロセスは独立して動作し、キューから自分のアカウントのアイテムのみを処理します。

---

## セットアップ

### 1. アカウント構成の設定

`scheduler/config/accounts_config.py` を編集：

```python
UPLOAD_ACCOUNTS = {
    'base': [
        'base_account_1',
        'base_account_2',
    ],
    'ebay': [
        'ebay_account_1',
    ],
}
```

### 2. デーモン設定の調整（オプション）

```python
DAEMON_CONFIG = {
    'interval_seconds': 60,  # チェック間隔（秒）
    'batch_size': 10,  # 1回の処理件数
    'business_hours_start': 6,  # 営業開始時刻（時）
    'business_hours_end': 23,  # 営業終了時刻（時）
}
```

---

## 使い方

### 基本的な起動

```bash
# プロジェクトルートで実行
cd C:\Users\hiroo\Documents\GitHub\ecauto

# マルチアカウントマネージャーを起動
python scheduler/multi_account_manager.py
```

### 起動時の出力例

```
============================================================
マルチアカウントアップロードマネージャー
============================================================

起動するプロセス数: 2

[START] base_base_account_1 (PID: 12345)
[START] base_base_account_2 (PID: 12346)

============================================================
✓ 2個のプロセスを起動しました
============================================================

起動中のプロセス:

  [Running] base_base_account_1
    PID: 12345
    稼働時間: 0:00:05
    再起動回数: 0
    設定: batch_size=10, interval=60s

  [Running] base_base_account_2
    PID: 12346
    稼働時間: 0:00:05
    再起動回数: 0
    設定: batch_size=10, interval=60s

============================================================
プロセス監視を開始します
チェック間隔: 60秒
停止するには Ctrl+C を押してください
============================================================
```

### 停止方法

**Ctrl + C** を押すと、すべてのプロセスが Graceful Shutdown されます。

```
シグナル 2 を受信しました。プロセスを停止します...

============================================================
すべてのプロセスを停止しています...
============================================================

[STOP] base_base_account_1 (PID: 12345) を停止します...
  ✓ 停止しました
[STOP] base_base_account_2 (PID: 12346) を停止します...
  ✓ 停止しました

============================================================
すべてのプロセスを停止しました
お疲れ様でした
============================================================
```

---

## 単一アカウントでの起動（テスト用）

マネージャーを使わず、単一アカウントのみを起動することもできます：

```bash
# base_account_1のみ起動
python scheduler/upload_daemon_account.py --platform base --account base_account_1

# オプション指定
python scheduler/upload_daemon_account.py \
  --platform base \
  --account base_account_1 \
  --batch-size 15 \
  --interval 30
```

---

## ログファイル

アカウント別にログファイルが生成されます：

```
logs/
├── upload_scheduler_base_base_account_1.log
├── upload_scheduler_base_base_account_2.log
└── upload_scheduler_base.log  # 既存の従来版デーモン
```

---

## 既存デーモンとの併用

既存の `upload_daemon.py` と併用可能です：

### 従来版（単一プロセス、順次処理）

```bash
python scheduler/upload_daemon.py --platform base --batch-size 10
```

### 並列版（複数プロセス、アカウント別並列処理）

```bash
python scheduler/multi_account_manager.py
```

**注意**: 同じプラットフォームで両方を同時に起動すると、重複処理が発生する可能性があります。どちらか一方を選択してください。

---

## トラブルシューティング

### プロセスが起動しない

**原因**: Pythonのパスが正しくない

**解決策**: `multi_account_manager.py` でPythonの実行パスを確認

```python
python_exe = sys.executable  # 現在のPythonインタープリタを使用
```

### プロセスが自動再起動を繰り返す

**原因**: デーモン内でエラーが発生している

**解決策**: アカウント別ログファイルを確認

```bash
tail -f logs/upload_scheduler_base_base_account_1.log
```

### キューが処理されない

**原因**: アカウント構成が正しくない

**解決策**: `accounts_config.py` でアカウントIDが正しいか確認

```python
UPLOAD_ACCOUNTS = {
    'base': [
        'base_account_1',  # <- これがDBのaccount_idと一致するか確認
        'base_account_2',
    ],
}
```

---

## パフォーマンス

### 従来版（順次処理）

```
account_1: 113件 → 約2時間
account_2: 286件 → 約5時間
合計: 約7時間
```

### 並列版（2プロセス）

```
account_1: 113件 → 約2時間 }
account_2: 286件 → 約5時間 } 並列実行
合計: 約5時間（最も遅いプロセスの時間）
```

**約2時間の短縮！**

---

## 今後の拡張

### プラットフォーム追加

`accounts_config.py` に追加するだけ：

```python
UPLOAD_ACCOUNTS = {
    'base': ['base_account_1', 'base_account_2'],
    'ebay': ['ebay_account_1'],  # ← 追加
    'yahoo': ['yahoo_account_1'],  # ← 追加
}
```

### アカウント別設定

特定のアカウントで設定を変更：

```python
ACCOUNT_SPECIFIC_CONFIG = {
    'base_account_1': {
        'batch_size': 15,  # account_1は高速処理
        'interval_seconds': 30,
    },
    'base_account_2': {
        'business_hours_start': 9,  # account_2は営業時間制限
        'business_hours_end': 18,
    },
}
```

---

## まとめ

- 既存の `upload_daemon.py` は**そのまま残る**（後方互換性）
- 並列処理が必要な場合は `multi_account_manager.py` を使用
- 設定は `accounts_config.py` で一元管理
- アカウント別ログで詳細な監視が可能

お疲れ様でした！🎉
