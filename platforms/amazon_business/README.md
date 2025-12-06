# Amazon Business - ブラウザオートメーション

Amazonビジネスでの仕入れ購入オートメーション機能です。

## 特徴

- ✅ **Chromeプロファイル永続化**: ログイン状態を確実に保存・復元
- ✅ **セッション管理**: 手動ログイン後、次回以降は自動的にログイン状態を維持
- ✅ **シンプルな実装**: Playwrightの `launch_persistent_context` を使用した確実な実装
- ✅ **2段階認証対応**: 手動ログイン時に2段階認証を完了できます

## ディレクトリ構造

```
platforms/amazon_business/
├── accounts/
│   ├── account_config.json      # アカウント設定
│   └── profiles/                # Chromeプロファイル（自動生成）
│       └── amazon_business_main/
├── browser/
│   ├── __init__.py
│   └── session.py               # セッション管理
├── scripts/
│   ├── __init__.py
│   ├── login.py                 # 初回ログイン
│   └── verify_session.py        # セッション確認
└── README.md
```

## セットアップ

### 1. 初回ログイン

初めて使用する場合、手動でログインしてセッション情報を保存します。

```bash
# プロジェクトルートから実行
cd C:\Users\hiroo\Documents\GitHub\ecauto

# 仮想環境を有効化（必要な場合）
.\venv\Scripts\activate

# 初回ログインスクリプトを実行
python platforms/amazon_business/scripts/login.py
```

**実行手順:**

1. スクリプトを実行するとブラウザが自動的に開きます
2. Amazonビジネスのログインページが表示されます
3. 手動でログイン（メールアドレス/パスワード + 2段階認証）
4. ログインが完了すると自動的に検知されます
5. セッション情報がChromeプロファイルに保存されます

**注意:**
- ログイン完了の検知には最大5分かかります
- 2段階認証は通常通り完了してください（スマホ確認、認証コード入力など）

### 2. セッション確認

保存されたセッション情報が有効か確認します。

```bash
# セッション確認（ブラウザを表示）
python platforms/amazon_business/scripts/verify_session.py

# ヘッドレスモードで確認
python platforms/amazon_business/scripts/verify_session.py --headless
```

**期待される結果:**

```
============================================================
Amazon Business - セッション確認
============================================================

【プロファイル情報】
  プラットフォーム: amazon_business
  アカウントID: amazon_business_main
  プロファイルパス: C:\Users\hiroo\Documents\GitHub\ecauto\platforms\amazon_business\accounts\profiles\amazon_business_main
  存在: True
  サイズ: 45.23 MB

プロファイルパス: ...
プロファイル存在: True

ログイン状態を確認中...
[OK] ログイン済みです
[OK] セッションが有効です

============================================================
[SUCCESS] セッションが有効です！
============================================================

現在のURL: https://business.amazon.co.jp/
ページタイトル: Amazon Business - ホーム
...
```

### 3. セッションが無効な場合

セッションが期限切れの場合、再ログインが必要です。

```bash
# 再ログイン
python platforms/amazon_business/scripts/login.py
```

## プログラムからの使用例

他のPythonスクリプトから使用する場合の例です。

```python
import asyncio
from platforms.amazon_business.browser import AmazonBusinessSession


async def example():
    """使用例"""
    # セッションマネージャーを初期化
    session = AmazonBusinessSession(account_id="amazon_business_main")

    # 認証済みコンテキストを取得
    result = await session.get_authenticated_context(headless=False)

    if result is None:
        print("セッションが無効です。再ログインしてください。")
        return

    playwright, context, page = result

    try:
        # ここで実際の処理を行う
        print(f"現在のURL: {page.url}")

        # 例: 商品検索
        await page.goto("https://business.amazon.co.jp/search?k=ノートパソコン")
        await page.wait_for_load_state("domcontentloaded")

        # ページタイトルを取得
        title = await page.title()
        print(f"ページタイトル: {title}")

        # 他の操作...

    finally:
        # クリーンアップ
        await context.close()
        await playwright.stop()


if __name__ == "__main__":
    asyncio.run(example())
```

## トラブルシューティング

### プロファイルが見つかりません

**症状:**
```
[INFO] プロファイルが見つかりません
初回ログインが必要です
```

**解決策:**
初回ログインを実行してください。

```bash
python platforms/amazon_business/scripts/login.py
```

### セッションが無効です

**症状:**
```
[WARN] セッションが無効です
再ログインが必要です
```

**原因:**
- Cookieの有効期限が切れた
- Amazonがセキュリティ上の理由でセッションを無効化した

**解決策:**
再ログインを実行してください。

```bash
python platforms/amazon_business/scripts/login.py
```

### ログイン完了を検知できない

**症状:**
```
[WARN] タイムアウト: 300秒経過しました
```

**原因:**
- ログインに時間がかかりすぎている
- 2段階認証が完了していない

**解決策:**
1. 2段階認証を確実に完了してください
2. ログイン後、ダッシュボードが表示されるまで待ってください
3. それでも検知されない場合は、もう一度実行してください

### Playwrightが見つかりません

**症状:**
```
ModuleNotFoundError: No module named 'playwright'
```

**解決策:**
Playwrightをインストールしてください。

```bash
# Playwrightをインストール
pip install playwright

# Playwrightブラウザをインストール
playwright install chromium
```

## 仕様

### セッション管理の仕組み

1. **Chromeプロファイル永続化**
   - Playwrightの `launch_persistent_context` を使用
   - プロファイルディレクトリ: `platforms/amazon_business/accounts/profiles/amazon_business_main/`
   - Cookie、LocalStorage、セッション情報がすべて保存されます

2. **ログイン状態の確認**
   - Amazonビジネスのダッシュボードにアクセス
   - ログインページにリダイレクトされないかチェック
   - ナビゲーションバーにアカウント名が表示されているかチェック

3. **自動復元**
   - 次回起動時、保存されたプロファイルから自動的にセッション情報を復元
   - ログイン操作は不要

### 設定ファイル

`accounts/account_config.json`:

```json
{
  "accounts": [
    {
      "id": "amazon_business_main",
      "name": "Amazonビジネスメインアカウント",
      "active": true,
      "profile_name": "amazon_business_main",
      "login_url": "https://www.amazon.co.jp/",
      "description": "仕入れ購入用メインアカウント"
    }
  ]
}
```

## 次のステップ

セッション管理が確実に動作することを確認したら、以下の機能を実装できます：

1. **商品検索・購入オートメーション**
2. **注文履歴の取得**
3. **カート操作**
4. **価格監視**

---

**作成日**: 2025-12-02
**最終更新**: 2025-12-02
