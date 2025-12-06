# SellerSprite システム更新履歴

## 2025-01-23 - v2.0 アップデート

### 修正内容

#### 1. Googleログインボタン検出の改善 ✅

**問題**:
- 初回ログイン時: ボタンラベルが「Googleでログイン」
- 2回目以降（Chromeプロファイル保存後）: ボタンラベルが「<ユーザー名>でログイン」に変更
- ラベルに依存した検出方法のため、2回目以降エラーになる

**修正内容**:

複数の方法で段階的にボタンを検出するフォールバック機構を実装:

1. **方法1**: iframe内の最初のボタンをクリック（最も堅牢）
   ```python
   google_login_frame = page.frame_locator('iframe[title*="Google"]')
   await google_login_frame.locator('button').first.click()
   ```

2. **方法2**: iframeのsrc属性で特定
   ```python
   google_login_frame = page.frame_locator('iframe[src*="accounts.google.com"]')
   await google_login_frame.locator('button').first.click()
   ```

3. **方法3**: div[role="button"]を試行
   ```python
   await google_login_frame.locator('div[role="button"]').first.click()
   ```

4. **方法4**: 直接リンクを探す（フォールバック）
   ```python
   google_link = page.locator('a:has-text("Google")')
   await google_link.click()
   ```

**影響範囲**:
- `sourcing/sources/sellersprite/auth_manager.py` - `auto_login()` 関数

#### 2. セッション無効化検出の強化 ✅

**問題**:
- ログイン後、商品リサーチページでログインページにリダイレクトされる
- エラーメッセージが不明確

**修正内容**:

商品リサーチページ遷移後、ログイン状態を確認:

```python
# ログイン状態を確認
page = controller.page
await page.wait_for_timeout(3000)
current_url = page.url

if 'login' in current_url:
    raise Exception("セッションが無効です。再ログインが必要です")
```

エラー時のスクリーンショット保存を安全に処理:

```python
try:
    if controller.page and not controller.page.is_closed():
        await controller.screenshot("product_research_error.png")
except Exception as screenshot_error:
    self.log(f"[WARN] スクリーンショット保存失敗: {screenshot_error}")
```

**影響範囲**:
- `sourcing/sources/sellersprite/extractors/product_research_extractor.py`

#### 3. 自動化検出回避の強化 ✅

**問題**:
- SellerSpriteが自動化ツールを検出してログアウト

**修正内容**:

Chromiumの起動オプションを追加:

```python
args=[
    '--disable-blink-features=AutomationControlled',
    '--disable-automation',
    '--disable-dev-shm-usage',
    '--no-sandbox',
],
ignore_default_args=['--enable-automation'],
```

**影響範囲**:
- `sourcing/sources/sellersprite/auth_manager.py` - すべてのブラウザ起動箇所

#### 4. バッチファイルの文字化け修正 ✅

**問題**:
- Windowsコマンドプロンプトで日本語が文字化け

**修正内容**:

`PYTHONIOENCODING=utf-8` を設定:

```batch
@echo off
cd /d C:\Users\hiroo\Documents\GitHub\ecauto
set PYTHONIOENCODING=utf-8
venv\Scripts\python.exe sourcing\scripts\extract_asins.py --pattern product_research ...
```

**影響範囲**:
- `sellersprite_extract_asins.bat`
- `sellersprite_check.bat`
- `sellersprite_auto_login.bat`
- `sellersprite_manual_login.bat`

### 新規ファイル

1. **sellersprite_reset.bat** - セッションリセットツール
   - Chromeプロファイルと古いCookieを削除

2. **SELLERSPRITE_TROUBLESHOOTING.md** - トラブルシューティングガイド
   - よくある問題と解決方法

3. **SELLERSPRITE_QUICKSTART.md** - クイックスタートガイド
   - 初回セットアップ手順

4. **test_google_login_button.py** - Googleログインボタン検出テスト
   - ボタン検出状況を確認

### 使用方法

#### Googleログインボタン検出テスト

```bash
set PYTHONIOENCODING=utf-8
python test_google_login_button.py
```

実行すると:
1. SellerSpriteログインページにアクセス
2. iframeを探索
3. 各種方法でボタンを検出
4. 結果を表示

#### セッションリセット

問題が発生した場合:

```bash
# 1. セッションリセット
sellersprite_reset.bat

# 2. 再ログイン
sellersprite_auto_login.bat

# 3. ASIN抽出
sellersprite_extract_asins.bat
```

### 技術詳細

#### Googleログインボタン検出の仕組み

SellerSpriteのログインページには、Googleの「ワンタップログイン」iframeが埋め込まれています:

```html
<iframe
  title="[Googleでログイン]ボタン"
  src="https://accounts.google.com/gsi/button?...">
  <button>Googleでログイン</button>  <!-- 初回 -->
  <button><ユーザー名>でログイン</button>  <!-- 2回目以降 -->
</iframe>
```

**課題**:
- ボタンのラベルが動的に変化
- iframeの内部構造はGoogleが管理

**解決策**:
- ラベルに依存せず、iframe内の**最初のボタン**を取得
- iframeの特定方法を複数用意（title属性、src属性）
- フォールバック機構で確実に検出

#### フォールバック機構の利点

1. **堅牢性**: 複数の検出方法を試行
2. **互換性**: Googleの仕様変更に対応
3. **デバッグ性**: どの方法で成功/失敗したか明確

### 今後の改善予定

1. **ヘッドレスモード対応**
   - 現在はheadless=Falseのみ
   - バックグラウンド実行のためヘッドレスモード対応

2. **リトライ機構**
   - ボタンクリック失敗時の自動リトライ
   - ログイン失敗時の再試行

3. **ログ出力の改善**
   - 構造化ログ（JSON形式）
   - ログレベルの設定

## テスト済み環境

- **OS**: Windows 11
- **Python**: 3.13
- **Playwright**: 最新版
- **ブラウザ**: Chromium（Playwright管理）

## 互換性

### 破壊的変更

なし。既存のコードはそのまま動作します。

### 非推奨機能

なし。

### 推奨される移行手順

既存のChromeプロファイルが古い場合、リセットを推奨:

```bash
sellersprite_reset.bat
sellersprite_auto_login.bat
```

## バグ報告

問題が発生した場合は、以下の情報を添えて報告してください:

1. エラーメッセージ全文
2. 実行したコマンド
3. `sellersprite_check.bat` の出力
4. `test_google_login_button.py` の出力

## 参考資料

- [クイックスタートガイド](SELLERSPRITE_QUICKSTART.md)
- [トラブルシューティング](SELLERSPRITE_TROUBLESHOOTING.md)
- [Issue #004: セッション管理](docs/issues/ISSUE_004_sellersprite_session_management.md)
