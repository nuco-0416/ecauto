# SellerSprite 認証・ASIN抽出システム

SellerSpriteからASINを自動抽出するシステムです。Chromeプロファイル永続化により、セッション情報を長期間保持します。

## 特徴

- **Chromeプロファイル永続化**: セッション情報を数日〜数週間保持
- **自動ログイン対応**: Google認証を自動化（オプション）
  - **NEW**: ボタンラベルに依存しない堅牢な検出方式
  - **NEW**: 4段階のフォールバック機構
- **手動ログイン対応**: 安全な手動ログイン方式
- **Cookie管理**: 期限チェック機能
- **ASIN抽出**: 商品リサーチ、ランキング等から抽出
- **セッション無効化検出**: ログイン状態を自動確認

## セットアップ

### 1. 初回ログイン

**方法A: 手動ログイン（推奨）**

```bash
python sourcing/sources/sellersprite/auth_manager.py login
```

ブラウザが開くので、Googleアカウントでログインしてください。

**方法B: 自動ログイン（環境変数使用）**

```bash
# .envファイルを作成
cd sourcing/sources/sellersprite/
cp .env.example .env

# .envファイルを編集してGoogle認証情報を設定
# GOOGLE_EMAIL=your_email@gmail.com
# GOOGLE_PASSWORD=your_password

# 自動ログイン実行
python sourcing/sources/sellersprite/auth_manager.py auto_login
```

### 2. Cookie状態の確認

```bash
python sourcing/sources/sellersprite/auth_manager.py check
```

出力例:
```
============================================================
Cookie ステータス
============================================================
存在: True
有効: True
総数: 15件
期限切れ: 0件
メッセージ: すべての Cookie が有効です
```

## 使用方法

### ASIN抽出（商品リサーチ）

```bash
python sourcing/scripts/extract_asins.py \
  --pattern product_research \
  --sales-min 300 \
  --price-min 2500 \
  --limit 100
```

**パラメータ:**
- `--sales-min`: 月間販売数の最小値（デフォルト: 300）
- `--price-min`: 価格の最小値（デフォルト: 2500）
- `--limit`: 取得件数（デフォルト: 100、最大: 100）
- `--market`: 市場（JP, US, UK, DE等、デフォルト: JP）
- `--keep-browser`: ブラウザを開いたまま（デバッグ用）

### ASIN抽出（ランキング）

```bash
python sourcing/scripts/extract_asins.py \
  --pattern ranking \
  --category "おもちゃ・ホビー" \
  --min-rank 1 \
  --max-rank 1000
```

### 出力ファイル指定

```bash
python sourcing/scripts/extract_asins.py \
  --pattern product_research \
  --sales-min 300 \
  --price-min 2500 \
  --output data/asins_20250123.txt
```

## コマンドリファレンス

### auth_manager.py

| コマンド | 説明 |
|---------|------|
| `python auth_manager.py check` | Cookie状態を確認 |
| `python auth_manager.py login` | 手動ログイン |
| `python auth_manager.py auto_login` | 自動ログイン（.env使用） |

### extract_asins.py

| パターン | 説明 |
|---------|------|
| `product_research` | 商品リサーチからASIN抽出 |
| `ranking` | ランキングからASIN抽出 |
| `category` | カテゴリからASIN抽出（未実装） |
| `seasonal` | 季節商品からASIN抽出（未実装） |

## トラブルシューティング

### Cookie期限切れエラー

```bash
# Cookie状態を確認
python sourcing/sources/sellersprite/auth_manager.py check

# 期限切れの場合は再ログイン
python sourcing/sources/sellersprite/auth_manager.py login
```

### セッション期限切れ

Chromeプロファイルが破損した場合、以下のディレクトリを削除して再ログイン:

```bash
# Windowsの場合
rmdir /s /q sourcing\data\chrome_profile

# 再ログイン
python sourcing/sources/sellersprite/auth_manager.py login
```

### 文字化け問題

Windows環境で文字化けが発生する場合、以下の環境変数を設定:

```bash
set PYTHONIOENCODING=utf-8
python sourcing/sources/sellersprite/auth_manager.py check
```

## ファイル構成

```
sourcing/sources/sellersprite/
├── auth_manager.py              # 認証管理
├── browser_controller.py        # ブラウザ操作
├── .env.example                 # 環境変数サンプル
├── .env                         # 環境変数（gitignore）
└── extractors/
    ├── base_extractor.py        # 抽出基底クラス
    ├── product_research_extractor.py  # 商品リサーチ抽出
    └── ranking_extractor.py     # ランキング抽出

sourcing/data/
├── sellersprite_cookies.json   # Cookie（gitignore）
├── chrome_profile/              # Chromeプロファイル（gitignore）
├── screenshots/                 # スクリーンショット（gitignore）
└── sourcing.db                  # データベース
```

## セキュリティ

- `.env` ファイルは `.gitignore` に追加済み
- Chromeプロファイルは `.gitignore` に追加済み
- Cookie情報は `.gitignore` に追加済み
- Google認証情報は安全に保管してください

## 技術詳細

### Chromeプロファイル永続化

`launch_persistent_context()` を使用してChromeプロファイルを永続化:

```python
context = await p.chromium.launch_persistent_context(
    user_data_dir=str(USER_DATA_DIR),
    headless=False,
    viewport={"width": 1920, "height": 1080},
    locale="ja-JP",
    timezone_id="Asia/Tokyo",
)
```

### Cookie管理

Cookie期限を自動チェックし、期限切れを検出:

```python
status = check_cookie_expiry()
# {'exists': True, 'valid': True, 'expired_count': 0, ...}
```

## 参考資料

- [Issue #004: セッション管理問題](../../../docs/issues/ISSUE_004_sellersprite_session_management.md)
- [Playwright ドキュメント](https://playwright.dev/python/)

## 更新履歴

### v2.0 (2025-01-23)

- **Googleログインボタン検出の改善**: ボタンラベルに依存しない検出方式
- **4段階フォールバック機構**: 複数の方法でボタンを確実に検出
- **セッション無効化検出**: 商品リサーチページでのログイン状態確認
- **自動化検出回避の強化**: Chromiumオプションの追加
- **バッチファイルの文字化け修正**: UTF-8エンコーディング設定
- **セッションリセットツール**: `sellersprite_reset.bat` 追加
- **トラブルシューティングガイド**: 詳細なドキュメント追加

詳細は [SELLERSPRITE_UPDATES.md](../../../SELLERSPRITE_UPDATES.md) を参照。

### v1.0 (2025-01-23)

- 初回リリース
- Chromeプロファイル永続化
- 自動ログイン機能（基本版）
- 手動ログイン機能
- Cookie管理
- ASIN抽出（商品リサーチ、ランキング）

## テスト

### Googleログインボタン検出テスト

ボタンが正しく検出できるか確認:

```bash
set PYTHONIOENCODING=utf-8
python test_google_login_button.py
```

### 総合テスト

すべての機能が正常か確認:

```bash
set PYTHONIOENCODING=utf-8
python test_complete.py
```

## トラブルシューティング

問題が発生した場合は、[SELLERSPRITE_TROUBLESHOOTING.md](../../../SELLERSPRITE_TROUBLESHOOTING.md) を参照してください。

よくある問題:
- ログインページにリダイレクトされる → `sellersprite_reset.bat` でセッションリセット
- Googleログインボタンが見つからない → 自動的に複数の方法で検出を試行
- Cookie期限切れ → `g_csrf_token`は短時間で期限切れになりますが問題ありません

## ライセンス

プロジェクトのライセンスに従います。

---

# TypeScript/Playwright版 - ASIN一括収集スクリプト

## 概要

`get_sellersprite_asins_2000.spec.ts`は、SellerSpriteの商品リサーチページから大量のASINを自動収集するPlaywright（TypeScript）スクリプトです。

## SellerSpriteの仕様による制限

**重要**: SellerSpriteには以下のページネーション制限があります：

- **最大ページ数**: 20ページ
- **1ページあたりの表示数**: 100件（設定可能だが、スクリプトでは100件に固定）
- **単一フィルター条件での最大取得可能件数**: 2000件

フィルター結果が何十万件あっても、実際にページネーションでアクセスできるのは最初の20ページ（2000件）のみです。

## セットアップ

### 1. 認証情報の設定

`.env`ファイルをこのディレクトリに作成し、SellerSpriteの認証情報を設定します：

```env
SELLERSPRITE_EMAIL=your-email@example.com
SELLERSPRITE_PASSWORD=your-password
START_PAGE=2
ASIN_COUNT=2000
```

### 2. 環境変数の説明

| 変数名 | 説明 | デフォルト値 | 制限 |
|--------|------|-------------|------|
| `SELLERSPRITE_EMAIL` | SellerSpriteのログインメールアドレス | - | 必須 |
| `SELLERSPRITE_PASSWORD` | SellerSpriteのログインパスワード | - | 必須 |
| `START_PAGE` | ASIN収集を開始するページ番号 | 2 | 1-20 |
| `ASIN_COUNT` | 収集するASIN数 | 2000 | 最大2000（制限による） |

## 使用方法

### 基本的な実行

```bash
# .envファイルに設定された値で実行
npx playwright test sourcing/sources/sellersprite/get_sellersprite_asins_2000.spec.ts
```

### 環境変数を上書きして実行（Windows PowerShell）

```powershell
# ページ1から1900件取得（ページ1は60件表示のため実際は2-20で1900件）
$env:START_PAGE="1"; $env:ASIN_COUNT="2000"; npx playwright test sourcing/sources/sellersprite/get_sellersprite_asins_2000.spec.ts

# ページ2から500件取得
$env:START_PAGE="2"; $env:ASIN_COUNT="500"; npx playwright test sourcing/sources/sellersprite/get_sellersprite_asins_2000.spec.ts
```

### 環境変数を上書きして実行（Linux/Mac）

```bash
# ページ1から1900件取得
START_PAGE=1 ASIN_COUNT=2000 npx playwright test sourcing/sources/sellersprite/get_sellersprite_asins_2000.spec.ts

# ページ2から500件取得
START_PAGE=2 ASIN_COUNT=500 npx playwright test sourcing/sources/sellersprite/get_sellersprite_asins_2000.spec.ts
```

## フィルター条件

スクリプトは以下のフィルター条件で商品を検索します：

- **市場**: 日本（JP）
- **月間販売数**: 300以上
- **価格**: 2500円以上
- **セラータイプ**: AMZ（Amazon直販）、FBA

これらの条件は、スクリプト内の88-115行目で設定されています。条件を変更したい場合は、該当箇所を編集してください。

## 出力

スクリプトは、収集したASINをタイムスタンプ付きのテキストファイルに保存します：

```
YYYYMMDD_HHMMSS_asin_[件数].txt
```

例：
- `20251123_170337_asin_1900.txt` - 1900件のASINを含むファイル

ファイルは1行に1ASINの形式で保存されます。

## 制限事項と注意点

### ページネーション制限

- ページ21以降にはアクセスできません
- START_PAGE=1, ASIN_COUNT=2000を指定しても、実際にはページ2-20（1900件）しか取得できません（ページ1はデフォルトで60件表示のため）
- より多くのASINを取得するには、フィルター条件を変更して複数回実行する必要があります

### 市場パラメータの維持

スクリプトは、ページ遷移時に市場パラメータ（market=JP）が変更されないように`ensureJapanMarket()`関数で監視しています。

### エラーハンドリング

- 指定されたページが存在しない場合、収集を停止し、それまでに取得したASINを保存します
- MAX_PAGESを超えるページを指定した場合、エラーメッセージを表示します

## トラブルシューティング（TypeScript版）

### "Page XX does not exist" エラー

指定したSTART_PAGEが存在しない、またはMAX_PAGES（20）を超えている場合に発生します。START_PAGEを1-20の範囲に設定してください。

### "Market changed from JP" 警告

ページ遷移時に市場パラメータがJPから変更された場合、自動的にJPに戻されます。この警告が頻繁に表示される場合は、SellerSpriteの仕様変更の可能性があります。

### 認証エラー

`.env`ファイルの`SELLERSPRITE_EMAIL`と`SELLERSPRITE_PASSWORD`が正しく設定されているか確認してください。

## 更新履歴（TypeScript版）

### 2025-11-23

- MAX_PAGES制限（20ページ）を明示的に追加
- URL parameter処理をURLSearchParams APIに変更してバグ修正
- 市場パラメータ維持機能を追加
- ページ数制限チェックを追加
- 設定値の検証機能を追加
- 最大取得可能件数の警告表示を追加
