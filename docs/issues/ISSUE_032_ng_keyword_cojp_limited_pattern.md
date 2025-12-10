# ISSUE_032: 商品名に「【.co.jp 限定】」が残る問題

## 概要

商品登録時に「【Amazon.co.jp限定】」を削除するよう設定していたにもかかわらず、「【.co.jp限定】」や「【.co.jp 限定】」がBASEにアップロードされた商品名に残っている問題。

## 発生日

2025-12-11

## ステータス

**解決済み（RESOLVED）**

## 問題の詳細

### 症状

- BASEにアップロードされた商品タイトルに「【.co.jp限定】」「【.co.jp 限定】」が含まれている
- NGキーワードフィルターで「【Amazon.co.jp限定】」を削除するよう設定済みだったはず

### 根本原因

NGキーワードリストには以下が登録されていた：
- `【Amazon.co.jp限定】`
- `Amazon`

しかし、マッチング処理で「【Amazon.co.jp限定】」全体がマッチせず、「Amazon」のみが削除されていた。
その結果、「【.co.jp限定】」が残っていた。

**テストログ（修正前）:**
```
[元のタイトル]
【Amazon.co.jp限定】 素晴らしい商品

[NGキーワードフィルター] タイトルから削除: Amazon  ← 「Amazon」だけが削除
  変更前の長さ: 24 → 変更後の長さ: 18

[フィルター後のタイトル]
【.co.jp限定】 素晴らしい商品  ← 「【.co.jp限定】」が残る
```

## 解決策

### 1. NGキーワードリストの更新

`config/ng_keywords.json` に以下のパターンを追加：

```json
{
  "keywords": [
    "by Amazon",
    "【Amazon.co.jp限定】",
    "【Amazon.co.jp 限定】",
    "【.co.jp限定】",        // 追加
    "【.co.jp 限定】",       // 追加（スペースあり）
    "Amazon",
    "アマゾン",
    "プライム会員"
  ]
}
```

### 2. 既存データのクリーンアップスクリプト作成

#### マスターDBクリーンアップ
`shared/utils/ng_keywords_cleanup_master_db.py`

productsテーブル内のタイトル・説明文からNGキーワードを削除する。

```bash
# スキャンのみ（対象確認）
/home/nuc_o/github/ecauto/venv/bin/python shared/utils/ng_keywords_cleanup_master_db.py --scan-only

# dry-run（変更内容確認）
/home/nuc_o/github/ecauto/venv/bin/python shared/utils/ng_keywords_cleanup_master_db.py --dry-run

# 実行
/home/nuc_o/github/ecauto/venv/bin/python shared/utils/ng_keywords_cleanup_master_db.py --execute
```

#### BASE既存出品タイトル更新
`shared/utils/ng_keywords_cleanup_base_titles.py`

BASEに出品済みの商品タイトルを更新する。

```bash
# スキャンのみ
/home/nuc_o/github/ecauto/venv/bin/python shared/utils/ng_keywords_cleanup_base_titles.py --scan-only

# dry-run（全アカウント）
/home/nuc_o/github/ecauto/venv/bin/python shared/utils/ng_keywords_cleanup_base_titles.py --dry-run

# 特定アカウントのみ実行
/home/nuc_o/github/ecauto/venv/bin/python shared/utils/ng_keywords_cleanup_base_titles.py --execute --account base_account_1

# 全アカウント実行
/home/nuc_o/github/ecauto/venv/bin/python shared/utils/ng_keywords_cleanup_base_titles.py --execute
```

## パイプライン確認結果

NGキーワードフィルターの適用箇所を確認した結果、以下の2箇所で適切に適用されている：

| 処理箇所 | NGフィルター適用 | 該当ファイル |
|---------|-----------------|-------------|
| productsテーブル保存時 | ✅ | `inventory/core/master_db.py:218-232` |
| BASEアップロード時 | ✅ | `scheduler/platform_uploaders/base_uploader.py:262-264` |

今回の修正により、今後の新規登録商品は正しくフィルタリングされる。

## 影響範囲

### テスト結果（2025-12-11時点）

| 対象 | 検出件数 |
|-----|---------|
| マスターDB（productsテーブル） | 365件 |
| BASE出品 | 367件 |

**BASE出品のアカウント別内訳:**
- base_account_1: 249件
- base_account_2: 110件
- base_account_3: 8件

## 推奨実行順序

1. **まずマスターDBをクリーンアップ**（DBのソースデータを修正）
   ```bash
   /home/nuc_o/github/ecauto/venv/bin/python shared/utils/ng_keywords_cleanup_master_db.py --execute
   ```

2. **次にBASE出品を更新**（実際の出品タイトルを修正）
   ```bash
   /home/nuc_o/github/ecauto/venv/bin/python shared/utils/ng_keywords_cleanup_base_titles.py --execute
   ```

## 変更ファイル

- `config/ng_keywords.json` - NGキーワードパターン追加
- `shared/utils/ng_keywords_cleanup_master_db.py` - 新規作成
- `shared/utils/ng_keywords_cleanup_base_titles.py` - 新規作成

## 関連ファイル

- `common/ng_keyword_filter.py` - NGキーワードフィルター本体
- `inventory/core/master_db.py` - productsテーブル保存時のフィルター適用
- `scheduler/platform_uploaders/base_uploader.py` - BASEアップロード時のフィルター適用

## 備考

- NGキーワードは長い順にソートされてマッチングされるため、`【Amazon.co.jp限定】`は`Amazon`より先に処理される設計
- しかし実際には`【Amazon.co.jp限定】`全体がマッチせず`Amazon`のみが削除されるケースがあった
- 根本対策として、Amazonが削除された後の残骸パターン（`【.co.jp限定】`）も明示的にNGキーワードに追加した
