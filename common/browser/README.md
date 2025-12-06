# Playwrightブラウザオートメーション基盤

APIが提供されていないプラットフォームに対して、Playwrightによるブラウザ自動化で操作を実現します。

## 概要

このモジュールは、複数のECプラットフォームで共通利用できるブラウザオートメーション基盤を提供します。

**主な機能**:
- ✅ **Chromeプロファイル管理**: アカウント別にプロファイルを分離し、ログイン状態を永続化
- ✅ **セッション管理**: Cookie/セッション情報の自動保存・復元
- ✅ **マルチアカウント対応**: プラットフォーム/アカウント単位で独立した環境を提供

**対応プラットフォーム**:
- ✅ Amazon Business（実装完了）
- 🔜 メルカリ（計画中）
- 🔜 Yahoo!オークション（計画中）

## アーキテクチャ

```
ecauto/
├── common/                          # 共通ブラウザオートメーション基盤
│   └── browser/
│       ├── profile_manager.py       # ✅ Chromeプロファイル管理
│       ├── base_controller.py       # 🔜 汎用ブラウザコントローラー
│       └── session_manager.py       # 🔜 セッション管理
│
└── platforms/
    ├── amazon_business/             # ✅ Amazon Business（実装完了）
    │   ├── accounts/
    │   │   ├── account_config.json  # アカウント設定
    │   │   └── profiles/            # Chromeプロファイル（アカウント別）
    │   │       └── amazon_business_main/
    │   ├── browser/
    │   │   └── session.py           # セッション管理
    │   ├── tasks/
    │   │   └── address_cleanup.py   # 住所録クリーンアップ
    │   └── scripts/
    │       ├── login.py             # 初回ログイン
    │       ├── verify_session.py    # セッション確認
    │       └── cleanup_addresses.py # 住所録クリーンアップ実行
    │
    ├── mercari/                     # 🔜 メルカリ（計画中）
    │   ├── accounts/
    │   │   └── profiles/
    │   ├── browser/
    │   │   ├── auth_manager.py
    │   │   └── automation.py
    │   └── scripts/
    │
    └── yahoo_auction/               # 🔜 Yahoo!オークション（計画中）
        ├── accounts/
        │   └── profiles/
        ├── browser/
        │   ├── auth_manager.py
        │   └── automation.py
        └── scripts/
```

## 実装済みコンポーネント

### ProfileManager (`profile_manager.py`) ✅

プラットフォーム/アカウント単位でChromeプロファイルを管理します。

**主要メソッド**:

```python
from common.browser import ProfileManager

# プロファイルマネージャーを初期化
profile_manager = ProfileManager()

# プロファイルパスを取得
profile_path = profile_manager.get_profile_path(
    platform="amazon_business",
    account_id="amazon_business_main"
)
# → platforms/amazon_business/accounts/profiles/amazon_business_main/

# プロファイルを作成
profile_manager.create_profile("amazon_business", "amazon_business_main")

# プロファイルの存在確認
exists = profile_manager.profile_exists("amazon_business", "amazon_business_main")

# プラットフォームのプロファイル一覧を取得
profiles = profile_manager.list_profiles("amazon_business")
# → ["amazon_business_main"]

# プロファイル情報を取得
info = profile_manager.get_profile_info("amazon_business", "amazon_business_main")
# → {"platform": "amazon_business", "account_id": "...", "size_mb": 45.2, ...}
```

**プロファイルパス構造**:

```
platforms/{platform}/accounts/profiles/{account_id}/
├── Default/                  # Chromeプロファイルデータ
│   ├── Cookies              # Cookie情報
│   ├── Local Storage/       # ローカルストレージ
│   └── ...
└── cookies.json             # 明示的に保存したCookie（バックアップ）
```

### Amazon Business実装 ✅

**セッション管理** (`platforms/amazon_business/browser/session.py`):

```python
from platforms.amazon_business.browser import AmazonBusinessSession

# セッションマネージャーを初期化
session = AmazonBusinessSession(account_id="amazon_business_main")

# 認証済みコンテキストを取得（プロファイルから自動復元）
result = await session.get_authenticated_context(headless=False)

if result is None:
    # セッションが無効な場合は再ログインが必要
    print("再ログインが必要です")
else:
    playwright, context, page = result
    # ここでページ操作を実行
    await context.close()
    await playwright.stop()
```

**主な機能**:
- ✅ Chrome profileベースのセッション永続化
- ✅ 自動Cookie保存・復元
- ✅ ログイン状態の自動検出
- ✅ マルチタブ対応のログイン検知

**住所録クリーンアップ** (`platforms/amazon_business/tasks/address_cleanup.py`):

指定した名前以外の住所を自動削除する機能。設定ファイルで保護リストを管理できます。

## 使用例

### 1. 初回ログイン

```bash
# Amazon Businessに初回ログイン（Chromeプロファイルを作成）
python platforms/amazon_business/scripts/login.py
```

このスクリプトは以下を実行します:
1. Chromeプロファイルディレクトリを作成
2. ブラウザを起動（headless=False）
3. ログインページを開く
4. ユーザーの手動ログインを待機
5. ログイン完了を検知したらプロファイル・Cookieを自動保存

### 2. セッション確認

```bash
# 保存されたセッションが有効かチェック
python platforms/amazon_business/scripts/verify_session.py

# ヘッドレスモードで確認
python platforms/amazon_business/scripts/verify_session.py --headless
```

### 3. 自動化タスクの実行

```bash
# 住所録クリーンアップ（保護リストは config/address_cleanup.json で設定）
python platforms/amazon_business/scripts/cleanup_addresses.py

# ヘッドレスモードで実行
python platforms/amazon_business/scripts/cleanup_addresses.py --headless

# コマンドラインで除外名を指定
python platforms/amazon_business/scripts/cleanup_addresses.py \
  --exclude-names "住所1" "住所2" "住所3"
```

## 今後の実装予定

### Phase 1: 共通基盤の拡張 🔜

- [ ] **BaseController** (`base_controller.py`): 汎用ブラウザコントローラー
  - SellerSpriteのBrowserControllerを汎用化
  - 共通操作メソッド（goto, click, fill, screenshot等）

- [ ] **SessionManager** (`session_manager.py`): セッション管理の汎用化
  - Cookie/セッション情報の保存・復元
  - セッション有効性チェック

### Phase 2: メルカリ実装 🔜

メルカリは認証が厳しいため、Chromeプロファイル方式が最適です。

**実装予定**:
- [ ] `platforms/mercari/browser/auth_manager.py` - 認証管理
- [ ] `platforms/mercari/browser/automation.py` - 管理画面操作
- [ ] `platforms/mercari/scripts/login.py` - 初回ログイン
- [ ] 商品出品機能
- [ ] 価格更新機能
- [ ] 注文確認機能

**アカウント設定例**:
```json
{
  "accounts": [
    {
      "id": "mercari_account_1",
      "name": "メルカリアカウント1",
      "active": true,
      "profile_name": "mercari_account_1",
      "login_url": "https://jp.mercari.com/"
    }
  ]
}
```

### Phase 3: Yahoo!オークション実装 🔜

メルカリと同様のパターンで実装します。

## 設計原則

### 1. アカウント別プロファイル分離

各アカウントは独立したChromeプロファイルを持ちます:

```python
# メルカリアカウント1のプロファイル
mercari_profile_1 = profile_manager.get_profile_path("mercari", "mercari_account_1")
# → platforms/mercari/accounts/profiles/mercari_account_1/

# メルカリアカウント2のプロファイル
mercari_profile_2 = profile_manager.get_profile_path("mercari", "mercari_account_2")
# → platforms/mercari/accounts/profiles/mercari_account_2/

# ヤフオクアカウント1のプロファイル
yahoo_profile_1 = profile_manager.get_profile_path("yahoo_auction", "yahoo_account_1")
# → platforms/yahoo_auction/accounts/profiles/yahoo_account_1/
```

**メリット**:
- ✅ アカウント間の完全な分離
- ✅ 通常のGoogle Chromeと同じセッション管理
- ✅ 認証状態の永続化
- ✅ プラットフォーム別の独立性

### 2. 設定ファイルによる管理

アカウント情報は各プラットフォームの `account_config.json` で管理します:

```
platforms/{platform}/accounts/account_config.json
```

**共通フィールド**:
- `id`: アカウントID（一意）
- `name`: アカウント名（表示用）
- `active`: 有効/無効フラグ
- `profile_name`: プロファイル名（通常はidと同じ）
- `login_url`: ログインページURL

### 3. 既存プロジェクトとの統合

ブラウザ自動化は既存の在庫管理DBと連携します:

```python
from inventory.core.database import MasterDatabase
from platforms.mercari.browser import MercariAuthManager, MercariAutomation

async def sync_mercari_listings():
    """メルカリ出品をmaster.dbと同期"""
    db = MasterDatabase()
    auth = MercariAuthManager()

    # 認証済みコンテキスト取得
    result = await auth.get_authenticated_context("mercari_account_1")
    if not result:
        print("認証失敗")
        return

    context, page, playwright = result

    try:
        # メルカリから出品一覧を取得
        automation = MercariAutomation(page)
        listings = await automation.get_all_listings()

        # master.dbに反映
        for listing in listings:
            db.update_listing(
                platform="mercari",
                account_id="mercari_account_1",
                platform_item_id=listing["id"],
                status=listing["status"],
                price=listing["price"]
            )
    finally:
        await context.close()
        await playwright.stop()
```

## 開発ガイドライン

### 新しいプラットフォームを追加する場合

1. **ディレクトリ構造を作成**:
   ```
   platforms/{platform}/
   ├── accounts/
   │   ├── account_config.json
   │   └── profiles/
   ├── browser/
   │   ├── __init__.py
   │   ├── auth_manager.py
   │   └── automation.py
   ├── scripts/
   │   └── login.py
   └── tasks/
   ```

2. **アカウント設定ファイルを作成**:
   ```json
   {
     "accounts": [
       {
         "id": "platform_account_1",
         "name": "アカウント1",
         "active": true,
         "profile_name": "platform_account_1",
         "login_url": "https://example.com/"
       }
     ]
   }
   ```

3. **認証マネージャーを実装**:
   - `get_authenticated_context()`: 認証済みコンテキストを取得
   - `manual_login()`: 手動ログイン実行
   - `check_login_status()`: ログイン状態確認

4. **オートメーションを実装**:
   - プラットフォーム固有の操作メソッドを実装
   - 既存のAmazon Business実装を参考にする

5. **スクリプトを実装**:
   - `login.py`: 初回ログイン
   - `verify_session.py`: セッション確認
   - その他必要なタスク

### ベストプラクティス

1. **エラーハンドリング**:
   - ネットワークエラー、タイムアウトを適切に処理
   - ログイン失敗時の再試行ロジック

2. **セッション管理**:
   - プロファイルとCookieの両方を保存（冗長性）
   - セッション有効期限のチェック

3. **ログ出力**:
   - デバッグ用の詳細なログを出力
   - 処理の進捗状況を表示

4. **設定の外部化**:
   - ハードコーディングを避ける
   - 設定ファイルで柔軟に管理

## 参考資料

- [Amazon Business実装ドキュメント](../../platforms/amazon_business/README.md)
- [Playwright公式ドキュメント](https://playwright.dev/python/)
- [プロジェクトルートREADME](../../README.md)

## トラブルシューティング

### セッションが復元されない

1. プロファイルディレクトリが存在するか確認:
   ```python
   profile_manager.profile_exists("platform", "account_id")
   ```

2. Cookie ファイルが存在するか確認:
   ```
   platforms/{platform}/accounts/profiles/{account_id}/cookies.json
   ```

3. 手動で再ログイン:
   ```bash
   python platforms/{platform}/scripts/login.py
   ```

### ログイン状態の検出が失敗する

- セレクタが変更されている可能性があります
- `check_login_status()` メソッドのセレクタを確認・更新してください

### プロファイルが肥大化する

- 定期的にプロファイルをクリーンアップ:
   ```python
   profile_manager.delete_profile("platform", "account_id")
   # 再ログイン
   ```
