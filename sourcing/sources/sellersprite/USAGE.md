# SellerSprite 認証システム - 使い方クイックガイド

## 🆕 推奨: 直接ログイン（メールアドレス/パスワード）

**最も簡単で安定した認証方法です！**

### セットアップ手順

1. `.env.example`を`.env`にコピー
   ```bash
   cd sourcing/sources/sellersprite
   copy .env.example .env
   ```

2. `.env`ファイルを編集して認証情報を設定
   ```env
   SELLERSPRITE_EMAIL=your_email@example.com
   SELLERSPRITE_PASSWORD=your_password
   ```

3. 直接ログインを実行
   ```bash
   # プロジェクトルートから実行
   cd C:\Users\hiroo\Documents\GitHub\ecauto
   python sourcing/sources/sellersprite/auth_manager.py direct_login
   ```

### メリット
- ✅ Google認証より簡単
- ✅ 2段階認証の手間がない
- ✅ 安定して動作
- ✅ TypeScript版と同じ実装

---

## 重要: コマンド実行時のディレクトリ

コマンドを実行する際は、**現在のディレクトリ**に注意してください。

### パターン1: プロジェクトルート (`ecauto` フォルダ) から実行

```bash
# 現在位置の確認
C:\Users\hiroo\Documents\GitHub\ecauto> pwd
# → C:\Users\hiroo\Documents\GitHub\ecauto

# Cookie状態確認
python sourcing/sources/sellersprite/auth_manager.py check

# 直接ログイン（推奨）
python sourcing/sources/sellersprite/auth_manager.py direct_login

# 手動ログイン
python sourcing/sources/sellersprite/auth_manager.py login

# 自動ログイン（Google認証）
python sourcing/sources/sellersprite/auth_manager.py auto_login

# ASIN抽出
python sourcing/scripts/extract_asins.py --pattern product_research --sales-min 300 --price-min 2500 --limit 10
```

### パターン2: `sellersprite` フォルダ内から実行

```bash
# 現在位置の確認
C:\Users\hiroo\Documents\GitHub\ecauto\sourcing\sources\sellersprite> pwd
# → C:\Users\hiroo\Documents\GitHub\ecauto\sourcing\sources\sellersprite

# Cookie状態確認
python auth_manager.py check

# 直接ログイン（推奨）
python auth_manager.py direct_login

# 手動ログイン
python auth_manager.py login

# 自動ログイン（Google認証）
python auth_manager.py auto_login

# ASIN抽出（プロジェクトルートに戻る必要あり）
cd ../../../
python sourcing/scripts/extract_asins.py --pattern product_research --sales-min 300 --price-min 2500 --limit 10
```

### パターン3: 絶対パスで実行（どこからでもOK）

```bash
# Cookie状態確認
python C:\Users\hiroo\Documents\GitHub\ecauto\sourcing\sources\sellersprite\auth_manager.py check

# 直接ログイン（推奨）
python C:\Users\hiroo\Documents\GitHub\ecauto\sourcing\sources\sellersprite\auth_manager.py direct_login

# 手動ログイン
python C:\Users\hiroo\Documents\GitHub\ecauto\sourcing\sources\sellersprite\auth_manager.py login

# 自動ログイン（Google認証）
python C:\Users\hiroo\Documents\GitHub\ecauto\sourcing\sources\sellersprite\auth_manager.py auto_login

# ASIN抽出
python C:\Users\hiroo\Documents\GitHub\ecauto\sourcing\scripts\extract_asins.py --pattern product_research --sales-min 300 --price-min 2500 --limit 10
```

## エラーが発生した場合

### エラー: パスが重複している

```
can't open file '...\\sourcing\\sources\\sellersprite\\sourcing\\sources\\sellersprite\\auth_manager.py'
```

**原因**: `sellersprite` フォルダ内にいるのに、相対パスで `sourcing/sources/sellersprite/...` を指定している

**解決方法**:
1. プロジェクトルートに移動する
   ```bash
   cd C:\Users\hiroo\Documents\GitHub\ecauto
   python sourcing/sources/sellersprite/auth_manager.py auto_login
   ```

2. または、現在のディレクトリから相対パスで指定
   ```bash
   # sellersprite フォルダ内にいる場合
   python auth_manager.py auto_login
   ```

### エラー: 文字化け

**解決方法**:
```bash
set PYTHONIOENCODING=utf-8
python auth_manager.py check
```

## 推奨: プロジェクトルートから実行

**最も安全で分かりやすい方法**は、常にプロジェクトルートから実行することです:

```bash
# プロジェクトルートに移動
cd C:\Users\hiroo\Documents\GitHub\ecauto

# 以降、すべてのコマンドをここから実行

# 直接ログイン（推奨）
python sourcing/sources/sellersprite/auth_manager.py direct_login

# または自動ログイン（Google認証）
python sourcing/sources/sellersprite/auth_manager.py auto_login

# ASIN抽出
python sourcing/scripts/extract_asins.py --pattern product_research --sales-min 300 --price-min 2500 --limit 10
```

## クイックリファレンス

| 実行したい処理 | コマンド（プロジェクトルートから） |
|---------------|-----------------------------------|
| Cookie状態確認 | `python sourcing/sources/sellersprite/auth_manager.py check` |
| 手動ログイン | `python sourcing/sources/sellersprite/auth_manager.py login` |
| **直接ログイン（推奨）** | `python sourcing/sources/sellersprite/auth_manager.py direct_login` |
| 自動ログイン（Google認証） | `python sourcing/sources/sellersprite/auth_manager.py auto_login` |
| ASIN抽出 | `python sourcing/scripts/extract_asins.py --pattern product_research --sales-min 300 --price-min 2500 --limit 10` |

## ヘルプ表示

```bash
# auth_manager.py のヘルプ
python sourcing/sources/sellersprite/auth_manager.py --help

# extract_asins.py のヘルプ
python sourcing/scripts/extract_asins.py --help
```
