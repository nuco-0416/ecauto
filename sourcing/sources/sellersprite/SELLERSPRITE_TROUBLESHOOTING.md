# SellerSprite トラブルシューティングガイド

## 問題: ログイン後に商品リサーチページでログインページにリダイレクトされる

### 症状

```
[06:43:24] 商品リサーチページに遷移中（市場: JP）...
[06:43:27] [OK] ページ読み込み完了
[06:43:27] [ERROR] ログインページにリダイレクトされました
[06:43:27] セッションが無効です。
```

### 原因

1. **Chromeプロファイルが破損している**
   - 古いセッション情報が残っている
   - SellerSpriteのセキュリティ更新でセッション形式が変更された

2. **Cookieが古い**
   - 保存されたCookieが期限切れまたは無効

3. **SellerSpriteの自動化検出**
   - 自動化ツールとして検出されログアウトされる

### 解決方法

#### ステップ1: セッションをリセット

```bash
# バッチファイルをダブルクリック
sellersprite_reset.bat
```

または手動で:

```bash
# Chromeプロファイル削除
rmdir /s /q sourcing\data\chrome_profile

# Cookie削除
del /q sourcing\data\sellersprite_cookies.json
```

#### ステップ2: 再ログイン

```bash
# 自動ログイン
sellersprite_auto_login.bat

# または手動ログイン
sellersprite_manual_login.bat
```

#### ステップ3: ASIN抽出を再実行

```bash
sellersprite_extract_asins.bat
```

## 問題: "Target page, context or browser has been closed" エラー

### 症状

```
[ERROR] フィルター設定エラー: Target page, context or browser has been closed
```

### 原因

- ページが途中で閉じられた
- ブラウザが強制終了された
- SellerSpriteが自動的にログアウトした

### 解決方法

**完全リセットして再試行:**

```bash
# 1. セッションリセット
sellersprite_reset.bat

# 2. 再ログイン
sellersprite_auto_login.bat

# 3. ASIN抽出
sellersprite_extract_asins.bat
```

## 問題: Cookie期限切れ

### 症状

```
Cookie ステータス: 1/15 件の Cookie が期限切れです
```

### 解決方法

**短期的Cookie期限は問題なし:**

`g_csrf_token` というCookieは数分で期限切れになりますが、**Chromeプロファイルがあれば問題ありません**。

ただし、ログインに失敗する場合は再ログイン:

```bash
sellersprite_auto_login.bat
```

## 問題: 文字化け

### 症状

```
'��以上' is not recognized as an internal or external command
```

### 原因

バッチファイルのエンコーディング問題

### 解決方法

**すでに修正済み** - 最新のバッチファイルを使用してください:
- `sellersprite_extract_asins.bat`
- `sellersprite_auto_login.bat`
- `sellersprite_manual_login.bat`
- `sellersprite_check.bat`

## 完全トラブルシューティング手順

### すべてをリセットして再セットアップ

```bash
# ステップ1: セッション完全リセット
sellersprite_reset.bat

# ステップ2: Pythonの依存関係確認
venv\Scripts\python.exe -m pip install --upgrade playwright
venv\Scripts\python.exe -m playwright install chromium

# ステップ3: 環境変数確認（自動ログイン使用時）
# sourcing\sources\sellersprite\.env を確認
# GOOGLE_EMAIL=your_email@gmail.com
# GOOGLE_PASSWORD=your_password

# ステップ4: 再ログイン
sellersprite_auto_login.bat

# ステップ5: Cookie状態確認
sellersprite_check.bat

# ステップ6: ASIN抽出テスト
sellersprite_extract_asins.bat
```

## よくある質問

### Q1. 毎回ログインが必要ですか？

いいえ。Chromeプロファイルが正常に保存されていれば、**数日〜数週間はログイン不要**です。

### Q2. Chromeプロファイルはどこに保存されていますか？

```
C:\Users\hiroo\Documents\GitHub\ecauto\sourcing\data\chrome_profile\
```

### Q3. エラーが解決しない場合は？

1. **完全リセット**: `sellersprite_reset.bat`
2. **仮想環境を再作成**:
   ```bash
   rmdir /s /q venv
   python -m venv venv
   venv\Scripts\pip install -r requirements.txt
   venv\Scripts\playwright install chromium
   ```
3. **再ログイン**: `sellersprite_auto_login.bat`

### Q4. ログが正常に見えるのにエラーになる

SellerSpriteの仕様変更やセキュリティ強化の可能性があります。以下を試してください:

1. **ブラウザを手動で開いてログイン**してみる
2. **Chromeプロファイルをリセット**
3. **手動ログイン**で時間をかけてログイン

### Q5. 自動化検出を回避するには？

既に以下の設定を追加済みです:

```python
args=[
    '--disable-blink-features=AutomationControlled',
    '--disable-automation',
    '--disable-dev-shm-usage',
    '--no-sandbox',
],
ignore_default_args=['--enable-automation'],
```

それでも検出される場合:
- **手動ログイン**を使用
- **待機時間を長くする** (`--keep-browser`オプションで確認)

## デバッグモード

エラー箇所を確認したい場合、`--keep-browser`オプションでブラウザを開いたままにできます:

```bash
cd C:\Users\hiroo\Documents\GitHub\ecauto
python sourcing\scripts\extract_asins.py --pattern product_research --sales-min 300 --price-min 2500 --limit 10 --keep-browser
```

ブラウザが開いたまま残るので、エラーの原因を目視で確認できます。

## サポート

問題が解決しない場合は、以下の情報を添えて報告してください:

1. エラーメッセージ全文
2. 実行したコマンド
3. `sellersprite_check.bat` の出力
4. Chromeプロファイルの存在確認: `dir sourcing\data\chrome_profile`

## 参考資料

- [クイックスタートガイド](SELLERSPRITE_QUICKSTART.md)
- [使用方法詳細](sourcing/sources/sellersprite/USAGE.md)
- [Issue #004: セッション管理](docs/issues/ISSUE_004_sellersprite_session_management.md)
