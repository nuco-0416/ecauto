# SellerSprite カテゴリー選択自動化スクリプト

このディレクトリには、SellerSpriteの商品リサーチページでカテゴリーを自動選択するPlaywright + TypeScriptスクリプトが含まれています。

## ファイル構成

- `sellersprite_category_selection.spec.ts` - メインスクリプト

## 前提条件

1. Node.jsとnpmがインストールされていること
2. Playwrightがインストールされていること
3. SellerSpriteのログインCookieが保存されていること（`sourcing/data/sellersprite_cookies.json`）

## セットアップ

プロジェクトルートで以下のコマンドを実行してください：

```bash
npm install
npx playwright install
```

## 実行方法

プロジェクトルートから以下のコマンドを実行します：

```bash
npx playwright test sourcing/typescript_operation_sample/sellersprite_category_selection.spec.ts
```

ヘッドレスモードを無効にして実行する場合：

```bash
npx playwright test sourcing/typescript_operation_sample/sellersprite_category_selection.spec.ts --headed
```

## スクリプトの動作内容

1. 保存されたCookieを読み込み
2. SellerSprite商品リサーチページ（日本市場）にアクセス
3. カテゴリー選択モーダルを開く
4. 「Health & Household」カテゴリーを展開
5. 「Healthcare」サブカテゴリーを選択
6. 「確定」ボタンをクリックしてフィルターを適用
7. スクリーンショットを保存

## カスタマイズ

異なるカテゴリーを選択したい場合は、スクリプト内の以下の部分を変更してください：

```typescript
// カテゴリー名を変更
await page.click('text=Health & Household');

// サブカテゴリー名を変更
await page.click('.el-tree-node:has-text("Healthcare") .el-checkbox');
```

## 注意事項

- スクリプト実行前に、有効なSellerSpriteのログインCookieが必要です
- Cookieの有効期限が切れている場合は、再度ログインしてCookieを更新してください
- 待機時間（`waitForTimeout`）は環境に応じて調整が必要な場合があります

## トラブルシューティング

### Cookieが見つからない

```bash
Error: ENOENT: no such file or directory, open '.../sellersprite_cookies.json'
```

→ `sourcing/data/sellersprite_cookies.json` が存在することを確認してください

### タイムアウトエラー

→ `waitForTimeout` の時間を増やすか、`waitForLoadState` や `waitForSelector` を使用して要素の読み込みを待機してください

### カテゴリーが選択されない

→ SellerSpriteのUIが変更されている可能性があります。セレクターを確認・更新してください
