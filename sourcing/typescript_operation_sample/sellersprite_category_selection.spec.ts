import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

test.describe('SellerSprite Category Selection', () => {
  test('should login and select Healthcare category', async ({ page, context }) => {
    // Cookieファイルのパスを設定
    const cookiePath = path.join(__dirname, '..', 'data', 'sellersprite_cookies.json');

    // Cookieを読み込み
    console.log('Loading cookies from:', cookiePath);
    const cookiesString = fs.readFileSync(cookiePath, 'utf8');
    const cookies = JSON.parse(cookiesString);

    // コンテキストにCookieを追加
    await context.addCookies(cookies);
    console.log('Cookies loaded successfully');

    // SellerSprite商品リサーチページにアクセス（日本市場を指定）
    console.log('Navigating to SellerSprite product research page...');
    await page.goto('https://www.sellersprite.com/v3/product-research?market=JP');

    // ページが読み込まれるまで待機
    await page.waitForLoadState('networkidle');
    console.log('Page loaded with market=JP');

    // カテゴリー選択ボタンをクリック
    console.log('Opening category selection modal...');
    const categorySelector = '#app > div.layout > div.layout-container > div > div.filter-wrap.jp-filter-wrap > div:nth-child(5) > div.type-wrap > div > div.item-wrap > div > div > div > span';
    await page.click(categorySelector);

    // モーダルが開くのを待機
    await page.waitForTimeout(2000);
    console.log('Category modal opened');

    // Health & Householdカテゴリーを展開
    console.log('Expanding Health & Household category...');
    await page.click('text=Health & Household');

    // ツリーが展開されるのを待機
    await page.waitForTimeout(2000);
    console.log('Health & Household expanded');

    // Healthcareサブカテゴリーのチェックボックスを選択
    console.log('Selecting Healthcare subcategory...');
    await page.click('.el-tree-node:has-text("Healthcare") .el-checkbox');

    // 選択が反映されるのを少し待機
    await page.waitForTimeout(1000);
    console.log('Healthcare selected');

    // 確定ボタンをクリック
    console.log('Confirming category selection...');
    await page.click('button:has-text("確定")');

    // フィルターが適用されるのを待機
    await page.waitForTimeout(3000);
    console.log('Category filter applied');

    // スクリーンショットを保存（オプション）
    const timestamp = new Date().toISOString().replace(/:/g, '-').split('.')[0];
    const screenshotPath = path.join(__dirname, '..', 'data', `category_selected_${timestamp}.png`);
    await page.screenshot({ path: screenshotPath, fullPage: true });
    console.log(`Screenshot saved to: ${screenshotPath}`);

    // テストの検証（オプション）
    // カテゴリーが選択されたことを確認する処理を追加できます
  });
});
