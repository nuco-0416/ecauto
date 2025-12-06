# SellerSprite ログイン自動化スクリプト

このディレクトリには、SellerSpriteへのGoogle認証ログインを自動化する2つのスクリプトが含まれています。

## スクリプトの種類

### 1. `login_sellersprite.spec.ts`
**初回ログイン用（プロファイルなし）**

初めてログインする際や、Chromeプロファイルを使用しない場合に使用します。

**処理フロー：**
1. SellerSpriteのログインページにアクセス
2. 「Google でログイン」ボタンをクリック
3. Googleメールアドレスを入力
4. Googleパスワードを入力
5. 2段階認証画面まで進む（手動でスマホ認証が必要）

**使用方法：**
```bash
npx playwright test login_sellersprite.spec.ts
```

### 2. `login_sellersprite_with_profile.spec.ts`
**Chromeプロファイル使用版**

Chromeプロファイル（`C:\Users\hiroo\Documents\GitHub\ecauto\sourcing\data\chrome_profile`）が保存されている場合に使用します。プロファイルにログイン情報が保持されているため、ログインが簡略化されます。

**処理フロー：**
1. Chromeプロファイルを読み込んでブラウザを起動
2. SellerSpriteのログインページにアクセス
3. 「〈ユーザー名〉でログイン」ボタンをクリック
4. Googleアカウント選択画面でアカウントを選択
5. （必要に応じて）パスワード入力や2段階認証を処理

**使用方法：**
```bash
npx playwright test login_sellersprite_with_profile.spec.ts
```

## 環境設定

### 1. 環境変数の設定

プロジェクトルートの `.env` ファイルに以下を設定してください：

```env
GOOGLE_EMAIL=hiroo.oguchi@gmail.com
GOOGLE_PASSWORD=RXkjxcabZ3gMl5BHywCDjBN
```

### 2. 依存関係のインストール

```bash
npm install
npx playwright install chromium
```

## 注意事項

### 2段階認証について
両方のスクリプトとも、2段階認証が有効な場合は手動でスマホでの認証が必要です。スクリプトは2段階認証画面まで自動で進み、スマホでの認証を待機します。

### プロファイルの保存
初回ログイン後、プロファイルを保存するには以下のようにブラウザを起動してログインします：

```bash
# Chromeをプロファイル保存モードで起動
chromium --user-data-dir="C:\Users\hiroo\Documents\GitHub\ecauto\sourcing\data\chrome_profile" https://www.sellersprite.com/jp/w/user/login
```

手動でログインを完了させた後、ブラウザを閉じるとプロファイルが保存されます。

### トラブルシューティング

#### 「login error!」が表示される
- Google同意画面で「許可」ボタンのクリックが必要な場合があります
- 2段階認証がタイムアウトした可能性があります
- プロファイルのクッキーやセッションが期限切れの可能性があります

#### プロファイル付きスクリプトでエラーが発生する
- プロファイルディレクトリが存在するか確認してください
- プロファイルが破損している場合は、削除して再作成してください

```bash
# プロファイルディレクトリを削除
rmdir /s "C:\Users\hiroo\Documents\GitHub\ecauto\sourcing\data\chrome_profile"

# 初回ログインスクリプトを実行
npx playwright test login_sellersprite.spec.ts
```

## スクリプトのカスタマイズ

### タイムアウト時間の調整

2段階認証の待機時間を変更したい場合：

```typescript
// 60秒から180秒（3分）に変更
await page.waitForTimeout(180000);
```

### ログ出力の追加

デバッグ情報を追加したい場合：

```typescript
console.log('現在のURL:', page.url());
console.log('ページタイトル:', await page.title());
```

## セキュリティに関する注意

- `.env` ファイルは `.gitignore` に追加してください
- 認証情報を含むスクリプトは公開リポジトリにコミットしないでください
- プロファイルディレクトリもバージョン管理から除外してください
