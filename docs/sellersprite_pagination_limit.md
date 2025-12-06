# SellerSprite ページネーション制限の調査結果

## 調査日
2025-11-23

## 問題の経緯

SellerSpriteからASINを大量に収集するスクリプト（`get_sellersprite_asins_2000.spec.ts`）において、ページ21以降にアクセスできない問題が発覚しました。

### 初期の状況

- スクリプトで`START_PAGE=31`を指定してASIN収集を試みたところ、ページが存在しないというエラーが発生
- playwright-mcpで手動確認したところ、フィルター結果は213,347件（約2,134ページ相当）が表示されていた
- URL parameter処理のバグ（文字列連結によるパラメータ重複）も発見され修正した

### 手動調査の結果

ユーザーが手動でSellerSpriteのページネーションを確認したところ、**ページャの上限が20ページ**であることが判明しました。

## SellerSpriteの仕様

### ページネーション制限

- **最大ページ数**: 20ページ
- **1ページあたりの最大表示数**: 100件
- **単一フィルター条件での最大取得可能件数**: 2000件

### 制限の詳細

1. フィルター結果が何十万件あっても、ページネーションでアクセスできるのは最初の20ページのみ
2. ページャには「次へ」ボタンがページ20まで表示されるが、それ以降は存在しない
3. URLで直接`page=21`にアクセスしようとしても、エラーまたはタイムアウトが発生する

### 制限の影響

- 3001番目以降のASINを取得することは、単一のフィルター条件では不可能
- より多くのASINを取得するには、以下のいずれかの方法が必要：
  1. フィルター条件を変更して複数回実行する
  2. 異なる価格帯や販売数の範囲で分割して収集する
  3. 市場（JP、US、UKなど）を変えて収集する

## 実装した修正

### 1. URL Parameter処理のバグ修正

**問題**: 文字列連結による`size`パラメータの重複

```typescript
// BEFORE (BROKEN):
const newUrl = currentUrl.includes('?')
  ? `${currentUrl}&size=100`  // これがsize=60&size=100になる
  : `${currentUrl}?size=100`;
```

**修正**: URLSearchParams APIを使用

```typescript
// AFTER (FIXED):
const urlObj = new URL(currentUrl);
if (urlObj.searchParams.get('size') !== '100') {
  urlObj.searchParams.set('size', '100');  // パラメータを正しく置換
  const newUrl = urlObj.toString();
  await page.goto(newUrl, { waitUntil: 'networkidle' });
}
```

### 2. MAX_PAGES制限の明示化

スクリプトに以下の定数を追加：

```typescript
const MAX_PAGES = 20;
const ITEMS_PER_PAGE = 100;
const MAX_ASINS = MAX_PAGES * ITEMS_PER_PAGE; // 2000件
```

### 3. 設定値の検証

```typescript
// START_PAGEの範囲チェック
if (startPage < 1 || startPage > MAX_PAGES) {
  throw new Error(`START_PAGE must be between 1 and ${MAX_PAGES} (SellerSprite pagination limit)`);
}

// 取得可能件数の計算と警告
const maxPossibleAsins = (MAX_PAGES - startPage + 1) * ITEMS_PER_PAGE;
if (asinCount > maxPossibleAsins) {
  console.log(`⚠️  WARNING: Requested ${asinCount} ASINs, but only ${maxPossibleAsins} ASINs are available from page ${startPage} to ${MAX_PAGES}`);
}
```

### 4. ループ内の制限チェック

```typescript
// ページ処理ループ内でMAX_PAGESをチェック
if (currentPage > MAX_PAGES) {
  console.log(`\n⚠️  Reached SellerSprite pagination limit (MAX_PAGES=${MAX_PAGES})`);
  break;
}

// 次ページ移動前のチェック
if (nextPage > MAX_PAGES) {
  console.log(`\n⚠️  Next page (${nextPage}) exceeds SellerSprite pagination limit`);
  break;
}
```

## テスト結果

### 成功したテスト

```bash
START_PAGE=1 ASIN_COUNT=2000
```

**結果**:
- ページ2から20まで収集（ページ1はデフォルトで60件表示のため）
- 合計1900件のASINを収集
- ファイル: `20251123_170337_asin_1900.txt`

**出力ログ**:
```
⚠️  WARNING: Requested 2000 ASINs, but only 1900 ASINs are available from page 2 to 20
⚠️  Will collect maximum available: 1900 ASINs
Configuration:
  Start Page: 2
  ASIN Count: 2000
  Max Available from page 2: 1900
```

### 失敗したテスト（制限前）

```bash
START_PAGE=31 ASIN_COUNT=2000
```

**結果**:
- ページ31が存在しないためエラー
- 適切なエラーメッセージが表示されるようになった

## 今後の対応

### 大量のASINを収集する方法

1. **価格帯で分割**
   ```bash
   # 2500-5000円
   START_PAGE=1 ASIN_COUNT=2000 PRICE_MIN=2500 PRICE_MAX=5000

   # 5000-10000円
   START_PAGE=1 ASIN_COUNT=2000 PRICE_MIN=5000 PRICE_MAX=10000
   ```

2. **販売数で分割**
   ```bash
   # 300-500件/月
   START_PAGE=1 ASIN_COUNT=2000 SALES_MIN=300 SALES_MAX=500

   # 500-1000件/月
   START_PAGE=1 ASIN_COUNT=2000 SALES_MIN=500 SALES_MAX=1000
   ```

3. **カテゴリで分割**
   - SellerSpriteのカテゴリフィルターを使用して、カテゴリごとに収集

## 参考資料

- スクリプト: `sourcing/sources/sellersprite/get_sellersprite_asins_2000.spec.ts`
- README: `sourcing/sources/sellersprite/README.md`
- 修正日: 2025-11-23

## 教訓

1. **外部サービスの制限を事前に確認する**: SellerSpriteのようなWebサービスには、ドキュメント化されていない制限が存在する可能性がある
2. **手動確認の重要性**: スクリプトが正しく動作しない場合、実際にWebページを手動で操作して制限を確認することが重要
3. **URL parameter処理**: 文字列連結ではなく、URLSearchParams APIなどの適切なAPIを使用すべき
4. **エラーハンドリングと警告**: ユーザーに分かりやすいエラーメッセージと警告を表示することで、問題の原因を素早く特定できる
