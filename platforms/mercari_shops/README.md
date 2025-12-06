# メルカリショップス プラットフォーム統合

メルカリショップスのブラウザ自動化による統合管理システムです。

## 概要

メルカリショップスはAPIが提供されていないため、Playwrightによるブラウザ自動化で操作を実現します。
Chromeプロファイルベースのセッション管理により、ログイン状態を永続化し、手動ログインの手間を最小限に抑えます。

## 主な機能

- ✅ **Chromeプロファイル管理**: ログイン状態を永続化
- ✅ **セッション自動復元**: Cookie/セッション情報の自動保存・復元
- ✅ **マルチタブ対応**: 複数タブでのログイン検知
- ✅ **ログイン状態の自動検出**: 管理画面URLやセレクタで判定

## ディレクトリ構造

```
platforms/mercari_shops/
├── accounts/
│   ├── account_config.json      # アカウント設定
│   └── profiles/                # Chromeプロファイル（ログイン後に自動作成）
│       └── mercari_shops_main/  # デフォルトアカウントのプロファイル
├── browser/
│   ├── __init__.py
│   └── session.py               # セッション管理クラス
├── scripts/
│   ├── __init__.py
│   ├── login.py                 # 初回ログインスクリプト
│   └── verify_session.py        # セッション確認スクリプト
├── tasks/
│   └── __init__.py              # 自動化タスク（将来実装予定）
└── README.md                    # このファイル
```

## セットアップ

### 1. 依存パッケージのインストール

```bash
# プロジェクトルートで実行
pip install -r requirements.txt
```

主要な依存パッケージ:
- `playwright` - ブラウザ自動化
- `asyncio` - 非同期処理

### 2. Playwrightブラウザのインストール

```bash
playwright install chromium
```

## 使用方法

### 初回ログイン（セッション作成）

初回のみ、手動ログインを行ってセッション情報を保存します。

```bash
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' platforms/mercari_shops/scripts/login.py"
```

**実行フロー:**

1. Chromeブラウザが自動的に起動します
2. メルカリショップスのログインページが開きます
3. 手動でログイン情報を入力:
   - メールアドレス/パスワード
   - 2段階認証（SMS認証コードなど）
4. ログイン完了を自動検知してセッションを保存
5. 次回以降は自動的にログイン状態が復元されます

**出力例:**

```
============================================================
メルカリショップス - 手動ログイン
============================================================

アカウントID: mercari_shops_main
アカウント名: メルカリショップス メインアカウント

ログインページにアクセス中: https://mercari-shops.com/signin/seller/owner

【手順】
1. メールアドレス/パスワードでログイン
2. 2段階認証（必要な場合）を完了
3. ログインが完了するまで待機します...

最大 300 秒間待機します

[DEBUG] 開いているタブ数: 1
[DEBUG] タブ 1 URL: https://mercari-shops.com/seller/shops/...
[OK] ログイン完了を検知しました！（タブ 1）

セッション情報を保存中...
[OK] プロファイル保存完了: ...
```

### セッション確認

保存されたセッションが有効かどうかを確認します。

```bash
# 通常モード（ブラウザが表示される）
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' platforms/mercari_shops/scripts/verify_session.py"

# ヘッドレスモード（バックグラウンド実行）
powershell -Command "& 'C:\Users\hiroo\Documents\GitHub\ecauto\venv\Scripts\python.exe' platforms/mercari_shops/scripts/verify_session.py --headless"
```

**出力例（成功時）:**

```
============================================================
メルカリショップス - セッション確認
============================================================

【プロファイル情報】
  プラットフォーム: mercari_shops
  アカウントID: mercari_shops_main
  プロファイルパス: C:\Users\...\mercari_shops_main
  存在: True
  サイズ: 45.2 MB

[OK] プロファイルが見つかりました

ログイン状態を確認中...
[OK] セッションが有効です

============================================================
[SUCCESS] セッションが有効です！
============================================================

現在のURL: https://mercari-shops.com/seller/shops/...
```

### セッション情報の保存場所

セッション情報は以下のディレクトリに保存されます:

```
platforms/mercari_shops/accounts/profiles/mercari_shops_main/
├── Default/                     # Chromeプロファイルデータ
│   ├── Cookies                  # Cookie情報
│   ├── Local Storage/           # ローカルストレージ
│   ├── Session Storage/         # セッションストレージ
│   └── ...                      # その他のブラウザデータ
└── cookies.json                 # 明示的に保存したCookie（バックアップ）
```

**注意:** このディレクトリには認証情報が含まれるため、`.gitignore` で除外されています。

## アカウント設定

アカウント情報は `accounts/account_config.json` で管理します。

**デフォルト設定:**

```json
{
  "accounts": [
    {
      "id": "mercari_shops_main",
      "name": "メルカリショップス メインアカウント",
      "active": true,
      "profile_name": "mercari_shops_main",
      "login_url": "https://mercari-shops.com/signin/seller/owner"
    }
  ]
}
```

**複数アカウントを追加する場合:**

```json
{
  "accounts": [
    {
      "id": "mercari_shops_main",
      "name": "メルカリショップス メインアカウント",
      "active": true,
      "profile_name": "mercari_shops_main",
      "login_url": "https://mercari-shops.com/signin/seller/owner"
    },
    {
      "id": "mercari_shops_sub",
      "name": "メルカリショップス サブアカウント",
      "active": true,
      "profile_name": "mercari_shops_sub",
      "login_url": "https://mercari-shops.com/signin/seller/owner"
    }
  ]
}
```

各アカウントは独立したChromeプロファイルを持ち、セッション情報が分離されます。

## マルチアカウント管理

### アカウント管理の仕組み

メルカリショップスでは、複数のアカウントを完全に独立して管理できます。

**管理されるデータ：**
- Chromeプロファイル（Cookie、LocalStorage、SessionStorage）
- ショップID情報（`shop_info.json`）
- ログイン状態（セッション）

**データ保存場所：**
```
platforms/mercari_shops/accounts/
├── account_config.json           # 全アカウントの設定
└── profiles/
    ├── mercari_shops_main/       # アカウント1
    │   ├── shop_info.json        # ショップID: 259LKXPg8eJkPYu6oHrYsH
    │   ├── cookies.json          # Cookie（バックアップ）
    │   └── Default/              # Chromeプロファイル
    └── mercari_shops_KYAW/       # アカウント2
        ├── shop_info.json        # 別のショップID
        ├── cookies.json
        └── Default/
```

### 新しいアカウントの追加

**手順1: `account_config.json` にアカウントを追加**

```bash
notepad platforms\mercari_shops\accounts\account_config.json
```

```json
{
  "accounts": [
    {
      "id": "mercari_shops_main",
      "name": "メルカリショップス メインアカウント",
      "description": "メインショップ",
      "active": true,
      "daily_upload_limit": 1000,
      "rate_limit_per_hour": 50,
      "login_url": "https://mercari-shops.com/signin/seller/owner",
      "credentials": {}
    },
    {
      "id": "mercari_shops_sub",      // ← 新規追加
      "name": "メルカリショップス サブアカウント",
      "description": "サブショップ",
      "active": true,
      "daily_upload_limit": 1000,
      "rate_limit_per_hour": 50,
      "login_url": "https://mercari-shops.com/signin/seller/owner",
      "credentials": {}
    }
  ]
}
```

**手順2: `config/platforms.json` にアカウントIDを追加**

```bash
notepad config\platforms.json
```

```json
{
  "platforms": {
    "mercari_shops": {
      "enabled": false,
      "accounts": [
        "mercari_shops_main",
        "mercari_shops_sub"    // ← 追加
      ]
    }
  }
}
```

**手順3: 初回ログイン**

```bash
# 新しいアカウントでログイン
python platforms/mercari_shops/scripts/login.py --account mercari_shops_sub
```

**結果：**
- 新しいプロファイルディレクトリが自動作成される
- ショップIDが自動的に保存される
- 次回以降は管理画面URLに直接アクセスできる

### 既存アカウントのID変更

既存のアカウントIDを変更する場合、セッションを引き継ぐために以下の手順が必要です。

**手順1: プロファイルフォルダー名を変更**

```powershell
# 例：mercari_shops_main → mercari_shops_KYAW に変更
Rename-Item `
  -Path "platforms\mercari_shops\accounts\profiles\mercari_shops_main" `
  -NewName "mercari_shops_KYAW"
```

**手順2: `account_config.json` の `id` を変更**

```json
{
  "accounts": [
    {
      "id": "mercari_shops_KYAW",  // ← 変更
      "name": "メルカリショップス メインアカウント",
      ...
    }
  ]
}
```

**手順3: `config/platforms.json` のアカウントリストを更新**

```json
{
  "platforms": {
    "mercari_shops": {
      "accounts": [
        "mercari_shops_KYAW"  // ← 変更
      ]
    }
  }
}
```

**手順4: 動作確認**

```bash
python platforms/mercari_shops/scripts/verify_session.py --account mercari_shops_KYAW
```

**結果：**
- 既存のセッションが引き継がれる
- 再ログイン不要
- ショップIDもそのまま使用できる

### 複数アカウントの切り替え

**ログイン：**
```bash
# アカウント1でログイン
python platforms/mercari_shops/scripts/login.py --account mercari_shops_main

# アカウント2でログイン
python platforms/mercari_shops/scripts/login.py --account mercari_shops_sub
```

**セッション確認：**
```bash
# アカウント1のセッション確認
python platforms/mercari_shops/scripts/verify_session.py --account mercari_shops_main

# アカウント2のセッション確認（ヘッドレス）
python platforms/mercari_shops/scripts/verify_session.py --account mercari_shops_sub --headless
```

**Pythonプログラムから：**
```python
from platforms.mercari_shops.browser import MercariShopsSession

# アカウント1を使用
session1 = MercariShopsSession(account_id="mercari_shops_main")

# アカウント2を使用
session2 = MercariShopsSession(account_id="mercari_shops_sub")
```

### ショップID情報の管理

**ショップID情報ファイル：** `platforms/mercari_shops/accounts/profiles/{account_id}/shop_info.json`

**内容：**
```json
{
  "shop_id": "259LKXPg8eJkPYu6oHrYsH",
  "dashboard_url": "https://mercari-shops.com/seller/shops/259LKXPg8eJkPYu6oHrYsH",
  "account_id": "mercari_shops_main",
  "updated_at": 1234567890.123
}
```

**自動保存タイミング：**
- 初回ログイン完了時
- ログイン後、管理画面URLが検出された時

**確認方法：**
```powershell
# PowerShellで確認
Get-Content platforms\mercari_shops\accounts\profiles\mercari_shops_main\shop_info.json | ConvertFrom-Json | Format-List
```

**出力例：**
```
shop_id       : 259LKXPg8eJkPYu6oHrYsH
dashboard_url : https://mercari-shops.com/seller/shops/259LKXPg8eJkPYu6oHrYsH
account_id    : mercari_shops_main
updated_at    : 1234567890.123
```

### マルチアカウント運用のベストプラクティス

1. **アカウントIDの命名規則**
   - プラットフォーム名を含める（例：`mercari_shops_xxx`）
   - 分かりやすく、ユニークな名前を付ける
   - 英数字とアンダースコアのみ使用

2. **設定ファイルの管理**
   - `account_config.json` と `config/platforms.json` を同期させる
   - アカウント追加時は両方のファイルを更新

3. **セッションの定期確認**
   - 定期的に `verify_session.py` でセッションが有効か確認
   - セッションが無効な場合は再ログイン

4. **プロファイルのバックアップ**
   - 重要なセッション情報は定期的にバックアップ
   - `profiles/` ディレクトリ全体をコピー

## プログラムからの利用

Pythonプログラムから直接セッション管理機能を利用できます。

```python
import asyncio
from platforms.mercari_shops.browser import MercariShopsSession

async def main():
    # セッションマネージャーを初期化
    session = MercariShopsSession(account_id="mercari_shops_main")

    # 認証済みコンテキストを取得
    result = await session.get_authenticated_context(headless=False)

    if result is None:
        print("セッションが無効です。再ログインが必要です。")
        # 手動ログインを実行
        success = await session.manual_login()
        if not success:
            print("ログインに失敗しました")
            return

        # 再度コンテキストを取得
        result = await session.get_authenticated_context(headless=False)

    playwright, context, page = result

    try:
        # ここでページ操作を実行
        print(f"現在のURL: {page.url}")

        # 例: 商品一覧ページに移動
        await page.goto("https://mercari-shops.com/seller/products")
        await page.wait_for_load_state("domcontentloaded")

        # ページ操作...

    finally:
        # クリーンアップ
        await context.close()
        await playwright.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

## トラブルシューティング

### セッションが復元されない

**症状:** `verify_session.py` で「セッションが無効です」と表示される

**原因と対処法:**

1. **プロファイルが存在しない**
   - 初回ログインが未実行の可能性があります
   - 対処法: `login.py` を実行してセッションを作成

2. **セッションの有効期限切れ**
   - メルカリショップスのセッションが期限切れになっている可能性があります
   - 対処法: `login.py` を再実行してログインし直す

3. **プロファイルが破損している**
   - プロファイルディレクトリが破損している可能性があります
   - 対処法: プロファイルを削除して再作成
     ```bash
     # プロファイルディレクトリを削除
     Remove-Item -Recurse -Force "platforms\mercari_shops\accounts\profiles\mercari_shops_main"

     # 再ログイン
     python platforms/mercari_shops/scripts/login.py
     ```

### ログイン状態の検出が失敗する

**症状:** ログインは成功しているのに「ログイン未完了」と表示される

**原因:** メルカリショップスの画面構造が変更され、セレクタが無効になっている可能性があります。

**対処法:**

1. playwright-mcpを使用して現在のページ構造を確認
2. `browser/session.py` の `check_login_status()` メソッドのセレクタを更新
3. 該当箇所: [session.py:161-174](browser/session.py#L161-L174)

```python
# ログイン状態を確認するためのセレクタ
login_indicators = [
    "a[href*='/settings']",      # 設定リンク
    "a[href*='/dashboard']",      # ダッシュボードリンク
    "button[aria-label*='メニュー']",  # メニューボタン
    "nav a[href*='/shop']",       # ショップナビゲーション
    "[data-testid*='header']",    # ヘッダー要素
]
```

### ブラウザが起動しない

**症状:** スクリプト実行時にブラウザが起動しない

**原因と対処法:**

1. **Playwrightブラウザが未インストール**
   ```bash
   playwright install chromium
   ```

2. **パーミッションエラー**
   - プロファイルディレクトリへの書き込み権限を確認
   - 必要に応じて管理者権限でコマンドプロンプトを起動

## 今後の実装予定

### Phase 1: 商品管理機能
- [ ] 商品一覧の取得
- [ ] 商品詳細情報の取得
- [ ] 商品情報の更新（価格、在庫など）

### Phase 2: 出品機能
- [ ] 新規商品の出品
- [ ] 画像アップロード
- [ ] カテゴリ選択

### Phase 3: 在庫・価格同期
- [ ] master.db との在庫同期
- [ ] 価格自動更新
- [ ] 在庫切れ商品の自動非公開

### Phase 4: 注文管理
- [ ] 新規注文の取得
- [ ] 注文ステータスの更新
- [ ] 発送通知

## 関連ドキュメント

- [プロジェクトルートREADME](../../README.md) - プロジェクト全体の概要
- [共通ブラウザ基盤](../../common/browser/README.md) - Playwrightブラウザオートメーション基盤
- [Amazon Business実装](../amazon_business/README.md) - 参考実装

## 技術仕様

### セッション管理の仕組み

1. **Chromeプロファイルの永続化**
   - Playwrightの `launch_persistent_context` を使用
   - 通常のGoogle Chromeと同じ形式でプロファイルを保存
   - Cookie、LocalStorage、SessionStorageなどが自動的に保存される

2. **ログイン状態の検出**
   - URLパターンマッチング: `/seller/`, `/dashboard`, `/settings` など
   - DOM要素の存在確認: 設定リンク、メニューボタンなど
   - マルチタブ対応: 全てのタブでログイン状態をチェック

3. **自動Cookie保存**
   - ログイン完了時に明示的にCookieをバックアップ
   - `cookies.json` として保存（冗長性のため）

### セキュリティ考慮事項

- **プロファイルディレクトリのセキュリティ**
  - 認証情報を含むため、適切なファイル権限で保護
  - `.gitignore` で除外し、バージョン管理から除外

- **自動化検知の回避**
  - `--disable-blink-features=AutomationControlled` を使用
  - 通常のユーザー操作と同等のブラウザ挙動

## ライセンス

Private

## サポート

問題が発生した場合は、以下の情報を添えて報告してください:

1. エラーメッセージの全文
2. 実行したコマンド
3. 実行環境（OS、Pythonバージョンなど）
4. ログ出力（可能な範囲で）
