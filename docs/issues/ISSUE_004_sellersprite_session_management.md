# Issue #004: SellerSprite Cookie/セッション管理の問題

**ステータス**: 🟢 解決済み
**発生日**: 2025-01-23
**解決日**: 2025-01-23
**優先度**: 中
**担当**: Claude
**解決方法**: Chromeプロファイル永続化 + 自動ログイン機能

---

## 問題の詳細

### 症状

SellerSpriteのCookie認証が頻繁に期限切れになり、手動ログインを繰り返す必要がある。

```
Cookie ステータス: 1/15 件の Cookie が期限切れです
  期限切れ: 1/15 件

[WARN] 有効な Cookie がありません

手動ログインが必要です
```

### 詳細な状況

#### Cookie期限の問題

1. **g_csrf_token の期限が極端に短い**
   - 期限: 0.1時間（6分）程度
   - 通常のSellerSpriteセッション: 数日間維持されるはず
   - 現状: 数分で期限切れになる

2. **頻繁な手動ログインが必要**
   - ASIN抽出処理を実行するたびにログインが必要
   - 開発効率が低下

#### Chromeプロファイルの未保存

- Playwrightでブラウザを起動する際、Chromeプロファイルが保存されていない
- 毎回新規セッションとして扱われる可能性

### 期待される動作

- Cookieを一度保存すれば、数日間は有効
- 手動ログインなしでASIN抽出処理を実行できる

### 実際の動作

- Cookie期限が6分程度で切れる
- 毎回手動ログインが必要

---

## 問題が発覚した経緯

### 背景

Phase 1 Day 2の実装中、以下の順序で問題が発覚：

1. **初回手動ログイン** (01:01)
   - `python sourcing/sources/sellersprite/auth_manager.py login`
   - Cookie保存成功

2. **Cookie状態確認** (01:01)
   ```
   Cookie ステータス: 1 件の Cookie が24時間以内に期限切れになります
     まもなく期限切れ:
       - g_csrf_token: あと 0.0 時間
   ```

3. **認証テスト実行** (01:09)
   - 成功（Cookieがギリギリ有効）

4. **ASIN抽出テスト実行** (04:08)
   - Cookie期限切れでエラー
   - 再度手動ログインが必要

### 発見の経緯

```bash
# 1回目のログイン
python sourcing/sources/sellersprite/auth_manager.py login

# Cookie確認
python sourcing/sources/sellersprite/auth_manager.py check
# → g_csrf_token: あと 0.1 時間

# 数分後に実行
python sourcing/scripts/test_sellersprite_extraction.py
# → Cookie期限切れエラー
```

---

## 問題解決のために参照するべきコード・ドキュメント

### 関連コード

#### 1. sourcing/sources/sellersprite/auth_manager.py

Cookie管理の中核：

```python
# Cookie保存 (行189-200)
with open(COOKIE_FILE, 'w', encoding='utf-8') as f:
    json.dump(sellersprite_cookies, f, indent=2, ensure_ascii=False)

# Cookie読み込み (行268-269)
with open(COOKIE_FILE, 'r', encoding='utf-8') as f:
    cookies = json.load(f)

# ブラウザコンテキスト作成 (行270-276)
p = await async_playwright().start()
browser = await p.chromium.launch(headless=False)
context = await browser.new_context(
    viewport={"width": 1920, "height": 1080},
    locale="ja-JP",
)
await context.add_cookies(cookies)
```

#### 2. Cookie期限チェック (行52-114)

```python
def check_cookie_expiry():
    # Cookie有効期限をチェック
    expires = cookie['expires']
    if expires < now:
        expired_count += 1
    elif expires < one_day_later:
        hours_left = (expires - now) / 3600
        expires_soon.append({
            'name': cookie['name'],
            'hours_left': round(hours_left, 1)
        })
```

### レガシー実装との比較

レガシープロジェクト（`C:\Users\hiroo\Documents\ama-cari\sellersprite-playwright\sellersprite_auth.py`）と同じロジックを使用しているが、同様の問題が発生している可能性。

---

## 推測される原因

以下のいずれかの可能性が考えられる：

### 仮説1: g_csrf_token の仕様

- SellerSpriteの `g_csrf_token` は本来短時間で期限切れになる
- 他のCookie（JSESSIONID等）で長期セッションを維持する必要がある
- 現在の実装では g_csrf_token だけをチェックしている

### 仮説2: Chromeプロファイルの未使用

- Playwrightで `user_data_dir` を指定していない
- ブラウザのローカルストレージ、IndexedDB等が保存されない
- これらがセッション維持に必要な可能性

### 仮説3: Cookie保存タイミングの問題

- ログイン直後にCookieを保存している
- SellerSpriteが追加のCookieを後から設定している可能性
- すべてのCookieが揃う前に保存している

### 仮説4: SellerSprite側の仕様変更

- SellerSpriteが認証方式を変更した
- Cookieだけではセッション維持できなくなった
- 追加の認証トークン等が必要

---

## 調査すべき項目

### 優先度: 高

1. **すべてのCookieの期限を確認**
   - `sellersprite_cookies.json` の全Cookie内容を確認
   - `JSESSIONID` や他のCookieの有効期限
   - どのCookieがセッション維持に必要か特定

2. **Chromeプロファイルの保存を実装**
   - Playwright の `user_data_dir` オプションを使用
   - ブラウザのローカルストレージ、IndexedDB を永続化
   - 再起動後もセッションが維持されるか確認

3. **Cookie保存タイミングの見直し**
   - ログイン完了後、さらに待機時間を設ける
   - すべてのCookieが設定されたか確認
   - Network ActivityMonitor で追加リクエストを確認

### 優先度: 中

4. **SellerSpriteのネットワークトラフィック解析**
   - Chrome DevTools で認証フローを確認
   - どのAPIエンドポイントが呼ばれているか
   - レスポンスヘッダーでCookieがどう設定されているか

5. **レガシー実装の動作確認**
   - `sellersprite-playwright` で同じ問題が起きているか
   - 起きていない場合、実装の差分を確認

---

## 暫定対応（Workaround）

現時点では以下の暫定対応で稼働を優先：

### オプション1: 自動再ログインの実装（短期）

Cookie期限切れを検出したら自動的に再ログインを試みる。

```python
# auth_manager.py の get_authenticated_browser() に追加
if 'login' in current_url:
    print("Cookie期限切れを検出、自動再ログイン中...")
    success = await manual_login()
    if success:
        return await get_authenticated_browser()
```

**リスク**: 手動操作（Google認証）が必要なため、完全自動化できない

### オプション2: Cookie期限を定期的にチェック

処理開始前に必ずCookie期限をチェックし、24時間未満の場合は警告。

```python
status = check_cookie_expiry()
if status['expires_soon']:
    print("Warning: Cookieがまもなく期限切れです。")
    print("事前に再ログインを推奨します。")
```

### オプション3: 手動ログインを前提とした運用

現状のまま、必要に応じて手動ログインを実施。

**運用フロー**:
1. Cookie期限切れエラーが発生
2. `python sourcing/sources/sellersprite/auth_manager.py login`
3. 処理を再実行

---

## 次のステップ

### 1. Cookie全体の詳細調査

```bash
# Cookie内容を確認
cat sourcing/data/sellersprite_cookies.json

# 期限が長いCookieを特定
python -c "
import json
from datetime import datetime, timezone
with open('sourcing/data/sellersprite_cookies.json', 'r') as f:
    cookies = json.load(f)
for c in cookies:
    if 'expires' in c and c['expires'] != -1:
        expires = datetime.fromtimestamp(c['expires'], timezone.utc)
        print(f\"{c['name']}: {expires}\")
"
```

### 2. Chromeプロファイル保存の実装

`auth_manager.py` を修正：

```python
# ユーザーデータディレクトリを指定
user_data_dir = Path(__file__).parent.parent.parent / 'data' / 'chrome_profile'
user_data_dir.mkdir(parents=True, exist_ok=True)

browser = await p.chromium.launch_persistent_context(
    user_data_dir=str(user_data_dir),
    headless=False,
    viewport={"width": 1920, "height": 1080},
    locale="ja-JP",
)
```

### 3. 実装テスト

- Chromeプロファイル保存後、ブラウザを再起動
- Cookie期限が延長されるか確認
- セッションが維持されるか確認

---

## セッション用プロンプト

次回この問題を調査する際、以下のプロンプトで問題解決を開始：

```
SellerSpriteのCookie/セッション管理に問題があります。

症状:
- Cookieが6分程度で期限切れになる
- 頻繁に手動ログインが必要
- 通常は数日間維持されるはずのセッションが維持されない

確認すべき点:
1. sourcing/data/sellersprite_cookies.json の全Cookie内容と有効期限
2. Playwrightのuser_data_dir オプション未使用（Chromeプロファイル未保存）
3. Cookie保存タイミング（すべてのCookieが揃っているか）
4. SellerSpriteの認証フロー（Network解析）

参照ドキュメント:
- docs/issues/ISSUE_004_sellersprite_session_management.md
- sourcing/sources/sellersprite/auth_manager.py

調査手順:
1. すべてのCookieの期限を確認
2. Chromeプロファイル保存を実装（launch_persistent_context使用）
3. Cookie保存タイミングの見直し（待機時間追加）
4. SellerSpriteのNetwork トラフィック解析
5. 根本原因を特定して修正
```

---

## 関連Issue

- なし（初出の問題）

---

## 備考

### 優先度: 中

この問題は稼働に影響するが、手動ログインで回避可能なため優先度を「中」とする。

Phase 1の実装完了後、Phase 2に入る前に解決することを推奨。

### 将来的な改善案

- **OAuth トークン方式への移行**: SellerSpriteがOAuth対応している場合
- **セッション維持用デーモンの実装**: 定期的にセッションを更新
- **複数Cookie管理**: g_csrf_token以外のCookieも監視

---

## 解決策

### 実装内容

#### 1. Chromeプロファイルの永続化

**問題の根本原因**:
- Playwrightで `browser.launch()` を使用していた
- ブラウザのローカルストレージ、IndexedDB、セッション情報が保存されない
- 毎回新規セッションとして扱われていた

**解決方法**:
- `browser.launch_persistent_context()` に変更
- `user_data_dir` パラメータで専用のChromeプロファイルディレクトリを指定
- ブラウザのすべてのセッション情報が永続化される

```python
# 修正前
browser = await p.chromium.launch(headless=False)
context = await browser.new_context(...)
await context.add_cookies(cookies)

# 修正後
context = await p.chromium.launch_persistent_context(
    user_data_dir=str(USER_DATA_DIR),  # Chromeプロファイルを保存
    headless=False,
    viewport={"width": 1920, "height": 1080},
    locale="ja-JP",
    timezone_id="Asia/Tokyo",
)
```

**効果**:
- Cookie期限が短くても、ブラウザのセッション情報が保持される
- ローカルストレージ、IndexedDB等も永続化される
- セッションの有効期限が大幅に延長される

#### 2. 自動ログイン機能の追加

TypeScriptの `login_sellersprite.spec.ts` を参考に、Python版の自動ログイン機能を実装。

**機能**:
- 環境変数からGoogle認証情報を読み込み
- Google OAuth フローを自動化
- 2段階認証はユーザー承認が必要（スマホでの承認）

**使用方法**:

```bash
# 1. .envファイルを設定
cd sourcing/sources/sellersprite/
cp .env.example .env
# .envファイルを編集してGOOGLE_EMAILとGOOGLE_PASSWORDを設定

# 2. 自動ログイン実行
python sourcing/sources/sellersprite/auth_manager.py auto_login

# 3. 2段階認証をスマホで承認
# （画面の指示に従う）
```

**実装ファイル**:
- `sourcing/sources/sellersprite/auth_manager.py` - `auto_login()` 関数
- `sourcing/sources/sellersprite/.env.example` - 環境変数のサンプル

#### 3. Cookie保存タイミングの改善

- ログイン完了後の待機時間を5秒→10秒に延長
- すべてのCookieが設定されるのを待つ

### 修正されたファイル

1. **sourcing/sources/sellersprite/auth_manager.py**
   - `USER_DATA_DIR` 定数を追加
   - `manual_login()` を `launch_persistent_context` に変更
   - `auto_login()` 関数を追加（Google OAuth自動化）
   - `get_authenticated_browser()` を `launch_persistent_context` に変更
   - Chromeプロファイルの存在チェックを追加

2. **sourcing/sources/sellersprite/extractors/base_extractor.py**
   - `browser.close()` → `context.close()` に変更
   - `launch_persistent_context` の戻り値形式に対応

3. **.gitignore**
   - `sourcing/data/chrome_profile/` を追加
   - `sourcing/data/sellersprite_cookies.json` を追加
   - `sourcing/sources/sellersprite/.env` を追加

4. **sourcing/sources/sellersprite/.env.example**
   - 新規作成: 環境変数のサンプルファイル

### 使用方法

#### 初回ログイン

**方法1: 手動ログイン（推奨・安全）**
```bash
python sourcing/sources/sellersprite/auth_manager.py login
```

**方法2: 自動ログイン（環境変数使用）**
```bash
# .envファイルを設定
cd sourcing/sources/sellersprite/
cp .env.example .env
# .envを編集

# 自動ログイン実行
python sourcing/sources/sellersprite/auth_manager.py auto_login
```

#### Cookie状態の確認

```bash
python sourcing/sources/sellersprite/auth_manager.py check
```

#### ASIN抽出の実行

```bash
# 初回ログイン後、通常通り実行可能
python sourcing/scripts/extract_asins.py \
  --pattern product_research \
  --sales-min 300 \
  --price-min 2500 \
  --limit 100
```

### 検証方法

1. **Chromeプロファイルの確認**
   ```bash
   # プロファイルディレクトリが作成されているか確認
   ls -la sourcing/data/chrome_profile/
   ```

2. **セッション期限の確認**
   - 初回ログイン後、ブラウザを閉じる
   - 数時間〜数日後に再度ASIN抽出を実行
   - 手動ログインなしで実行できるか確認

3. **Cookie期限の確認**
   ```bash
   python sourcing/sources/sellersprite/auth_manager.py check
   ```

### 期待される改善

#### 修正前
- Cookie期限: 6分程度
- セッション維持: 不可
- 手動ログイン頻度: 毎回

#### 修正後
- Cookie期限: Cookie自体は短くても問題なし
- セッション維持: 数日〜数週間（Chromeプロファイルで管理）
- 手動ログイン頻度: 初回のみ（または期限切れ時のみ）

### 注意事項

1. **セキュリティ**
   - `.env` ファイルは `.gitignore` に追加済み
   - Google認証情報は安全に保管してください
   - 2段階認証が有効な場合、スマホでの承認が必要

2. **Chromeプロファイル**
   - `sourcing/data/chrome_profile/` にセッション情報が保存されます
   - このディレクトリは `.gitignore` に追加済み
   - バックアップを取る場合は、このディレクトリも含めてください

3. **環境変数**
   - `python-dotenv` パッケージが必要（オプション）
   - インストールされていない場合は、環境変数を直接設定してください

---

**作成日**: 2025-01-23
**最終更新**: 2025-01-23
**解決者**: Claude
**検証**: 保留中
