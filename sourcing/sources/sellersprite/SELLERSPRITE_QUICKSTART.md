# SellerSprite クイックスタートガイド

## 問題の解決: コマンド実行時のパスエラー

### ❌ エラーが発生するコマンド

```bash
# sellersprite フォルダ内で実行すると、パスが二重になる
C:\Users\hiroo\Documents\GitHub\ecauto\sourcing\sources\sellersprite> python sourcing/sources/sellersprite/auth_manager.py auto_login
```

エラー:
```
can't open file '...\\sourcing\\sources\\sellersprite\\sourcing\\sources\\sellersprite\\auth_manager.py'
```

### ✅ 正しい実行方法

#### 方法1: sellersprite フォルダ内から実行（現在の場所から）

```bash
C:\Users\hiroo\Documents\GitHub\ecauto\sourcing\sources\sellersprite> python auth_manager.py auto_login
```

#### 方法2: プロジェクトルートに移動してから実行

```bash
cd C:\Users\hiroo\Documents\GitHub\ecauto
python sourcing\sources\sellersprite\auth_manager.py auto_login
```

#### 方法3: バッチファイルをダブルクリック（最も簡単）

プロジェクトルート (`C:\Users\hiroo\Documents\GitHub\ecauto`) に以下のバッチファイルを作成しました:

| ファイル名 | 機能 |
|-----------|------|
| `sellersprite_check.bat` | Cookie状態確認 |
| `sellersprite_manual_login.bat` | 手動ログイン |
| `sellersprite_auto_login.bat` | 自動ログイン（.env使用） |
| `sellersprite_extract_asins.bat` | ASIN抽出（10件） |

**使い方**: エクスプローラーでダブルクリックするだけ！

## 初回セットアップ手順

### ステップ1: Cookie状態を確認

```bash
# バッチファイルをダブルクリック
sellersprite_check.bat

# またはコマンドライン
cd C:\Users\hiroo\Documents\GitHub\ecauto
python sourcing\sources\sellersprite\auth_manager.py check
```

### ステップ2: ログイン

#### パターンA: 自動ログイン（.env設定済みの場合）

```bash
# バッチファイルをダブルクリック
sellersprite_auto_login.bat

# またはコマンドライン
cd C:\Users\hiroo\Documents\GitHub\ecauto
python sourcing\sources\sellersprite\auth_manager.py auto_login
```

#### パターンB: 手動ログイン

```bash
# バッチファイルをダブルクリック
sellersprite_manual_login.bat

# またはコマンドライン
cd C:\Users\hiroo\Documents\GitHub\ecauto
python sourcing\sources\sellersprite\auth_manager.py login
```

### ステップ3: ASIN抽出を実行

```bash
# バッチファイルをダブルクリック
sellersprite_extract_asins.bat

# またはコマンドライン
cd C:\Users\hiroo\Documents\GitHub\ecauto
python sourcing\scripts\extract_asins.py --pattern product_research --sales-min 300 --price-min 2500 --limit 10
```

## コマンドライン実行時の注意点

### 現在のディレクトリを確認

```bash
# Windowsの場合
cd

# 出力例
C:\Users\hiroo\Documents\GitHub\ecauto
```

### プロジェクトルートに移動

```bash
cd C:\Users\hiroo\Documents\GitHub\ecauto
```

### 文字化けが発生する場合

```bash
set PYTHONIOENCODING=utf-8
python sourcing\sources\sellersprite\auth_manager.py check
```

## トラブルシューティング

### Q1. パスが二重になるエラーが出る

**原因**: 現在のディレクトリが `sellersprite` フォルダ内にいる

**解決方法**:
```bash
# プロジェクトルートに移動
cd C:\Users\hiroo\Documents\GitHub\ecauto

# またはバッチファイルを使用（自動で正しいディレクトリに移動）
sellersprite_auto_login.bat
```

### Q2. Cookie期限切れエラー

```bash
# Cookie状態を確認
sellersprite_check.bat

# 期限切れの場合は再ログイン
sellersprite_auto_login.bat
```

### Q3. Chromeプロファイルが壊れた

```bash
# プロファイルディレクトリを削除
rmdir /s /q sourcing\data\chrome_profile

# 再ログイン
sellersprite_auto_login.bat
```

## 推奨: PowerShellエイリアスを設定（上級者向け）

PowerShellプロファイルに以下を追加すると、どこからでもコマンド実行可能:

```powershell
# プロファイルを開く
notepad $PROFILE

# 以下を追加
function ss-check {
    cd C:\Users\hiroo\Documents\GitHub\ecauto
    python sourcing\sources\sellersprite\auth_manager.py check
}

function ss-login {
    cd C:\Users\hiroo\Documents\GitHub\ecauto
    python sourcing\sources\sellersprite\auth_manager.py auto_login
}

function ss-extract {
    cd C:\Users\hiroo\Documents\GitHub\ecauto
    python sourcing\scripts\extract_asins.py --pattern product_research --sales-min 300 --price-min 2500 --limit 10
}
```

使用例:
```powershell
ss-check    # Cookie状態確認
ss-login    # 自動ログイン
ss-extract  # ASIN抽出
```

## まとめ

**最も簡単な方法**: バッチファイルをダブルクリック！

1. `sellersprite_auto_login.bat` - 初回ログイン
2. `sellersprite_extract_asins.bat` - ASIN抽出
3. `sellersprite_check.bat` - Cookie状態確認

これだけです！
