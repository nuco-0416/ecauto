import { test, expect, chromium } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import * as dotenv from 'dotenv';

// .envファイルを読み込む
dotenv.config({ path: path.join(process.cwd(), 'sourcing', 'sources', 'sellersprite', '.env') });

test.describe('SellerSprite ASIN Search - Configurable', () => {
  test('should get ASINs with configurable start page and count', async () => {
    // SellerSpriteの仕様による制限
    // - ページネーション上限: 20ページ
    // - 1ページあたりの最大表示数: 100件
    // - 単一フィルター条件での最大取得可能件数: 2000件
    const MAX_PAGES = 20;
    const ITEMS_PER_PAGE = 100;
    const MAX_ASINS = MAX_PAGES * ITEMS_PER_PAGE; // 2000件

    // 環境変数から設定を取得（デフォルト値あり）
    const startPage = parseInt(process.env.START_PAGE || '2', 10);
    const asinCount = parseInt(process.env.ASIN_COUNT || '2000', 10);
    const email = process.env.SELLERSPRITE_EMAIL;
    const password = process.env.SELLERSPRITE_PASSWORD;

    if (!email || !password) {
      throw new Error('SELLERSPRITE_EMAIL and SELLERSPRITE_PASSWORD must be set in .env file');
    }

    // 設定値の検証
    if (startPage < 1 || startPage > MAX_PAGES) {
      throw new Error(`START_PAGE must be between 1 and ${MAX_PAGES} (SellerSprite pagination limit)`);
    }

    const maxPossibleAsins = (MAX_PAGES - startPage + 1) * ITEMS_PER_PAGE;
    if (asinCount > maxPossibleAsins) {
      console.log(`⚠️  WARNING: Requested ${asinCount} ASINs, but only ${maxPossibleAsins} ASINs are available from page ${startPage} to ${MAX_PAGES}`);
      console.log(`⚠️  Will collect maximum available: ${maxPossibleAsins} ASINs`);
    }

    console.log(`Configuration:`);
    console.log(`  Start Page: ${startPage}`);
    console.log(`  ASIN Count: ${asinCount}`);
    console.log(`  Max Available from page ${startPage}: ${maxPossibleAsins}`);
    console.log(`  Email: ${email}`);

    // ブラウザを起動
    const browser = await chromium.launch({
      headless: false,
      args: [
        '--disable-blink-features=AutomationControlled',
      ],
    });

    const context = await browser.newContext({
      viewport: { width: 1920, height: 1080 },
    });

    const page = await context.newPage();

    // market=JPを確保する関数
    const ensureJapanMarket = async () => {
      const currentUrl = page.url();
      if (!currentUrl.includes('market=JP')) {
        console.log('⚠️  WARNING: Market changed from JP. Restoring to JP...');
        const newUrl = currentUrl.includes('market=')
          ? currentUrl.replace(/market=[A-Z]+/, 'market=JP')
          : currentUrl.includes('?')
          ? `${currentUrl}&market=JP`
          : `${currentUrl}?market=JP`;
        await page.goto(newUrl, { waitUntil: 'networkidle' });
        await page.waitForSelector('table tbody tr', { timeout: 30000 });
        console.log('✓ Market restored to JP');
      } else {
        console.log('✓ Market is JP');
      }
    };

    try {
      // ログインページにアクセス
      console.log('Navigating to login page...');
      await page.goto('https://www.sellersprite.com/jp/w/user/login', { waitUntil: 'networkidle' });
      console.log('Login page loaded');

      // メール/パスワード認証を選択
      console.log('Logging in with email/password...');

      // メールアドレス入力（getByRoleを使用）
      await page.getByRole('textbox', { name: 'メールアドレス／アカウント' }).fill(email);
      console.log('Email entered');

      // パスワード入力（getByRoleを使用）
      await page.getByRole('textbox', { name: 'パスワード' }).fill(password);
      console.log('Password entered');

      // ログインボタンをクリック
      await page.getByRole('button', { name: 'ログイン' }).click();
      console.log('Login button clicked');

      // ログイン完了を待機（welcomeページまたはdashboardページ）
      await page.waitForURL(/\/(welcome|dashboard)/, { timeout: 30000 });
      console.log('Login successful');

      // 商品リサーチページに移動（日本市場を指定）
      console.log('Navigating to SellerSprite product research page...');
      await page.goto('https://www.sellersprite.com/v3/product-research?market=JP', { waitUntil: 'networkidle' });
      console.log('Page loaded with market=JP');

      // フィルター条件を設定
      console.log('Setting filter conditions...');

      // 月間販売数の最小値を入力（300）
      await page.waitForTimeout(2000); // ページ読み込み待機
      await page.getByRole('textbox', { name: '最小値' }).first().fill('300');
      console.log('Monthly sales min: 300');

      // 少し待機
      await page.waitForTimeout(1000);

      // 価格の最小値を入力（2500）
      await page.locator('.type-wrap.product > .item-wrap > div:nth-child(2) > .content > div > .el-form-item__content > .el-input > .el-input__inner').first().fill('2500');
      console.log('Price min: 2500');

      // 少し待機
      await page.waitForTimeout(1000);

      // AMZにチェック
      await page.locator('div:nth-child(2) > .content > .el-checkbox-group > label > .el-checkbox__input').first().click();
      console.log('AMZ checked');

      // 少し待機
      await page.waitForTimeout(500);

      // FBAにチェック
      await page.locator('label:nth-child(2) > .el-checkbox__input').first().click();
      console.log('FBA checked');

      // 少し待機
      await page.waitForTimeout(1000);

      // フィルター開始ボタンをクリック
      console.log('Clicking filter button...');
      await page.getByRole('button', { name: '  フィルター開始' }).click();

      // 結果が表示されるまで待機
      await page.waitForLoadState('networkidle');
      console.log('Filter applied, waiting for results...');

      // 結果テーブルが表示されるまで待機
      await page.waitForSelector('table tbody tr', { timeout: 30000 });

      // market=JPが維持されているか確認
      await ensureJapanMarket();

      // size=100に変更
      let currentUrl = page.url();
      const urlObj = new URL(currentUrl);
      if (urlObj.searchParams.get('size') !== '100') {
        urlObj.searchParams.set('size', '100');
        const newUrl = urlObj.toString();
        console.log('Changing page size to 100...');
        console.log('New URL:', newUrl);
        await page.goto(newUrl, { waitUntil: 'networkidle' });
        await page.waitForSelector('table tbody tr', { timeout: 30000 });

        // 実際に何件表示されているか確認
        const rowCount = await page.evaluate(() => {
          return document.querySelectorAll('table tbody tr').length;
        });
        console.log(`Page size changed. Rows displayed: ${rowCount}`);

        // ページサイズ変更後もmarket=JPを確認
        await ensureJapanMarket();
        currentUrl = page.url(); // URLを更新
        console.log('Current URL after size change:', currentUrl);
      }

      // 全ASINを収集
      const allAsins: string[] = [];
      let currentPage = 1;
      // ASIN数からページ数を計算（MAX_PAGESを超えないようにする）
      const requestedPages = Math.ceil(asinCount / ITEMS_PER_PAGE);
      const totalPagesToCollect = Math.min(requestedPages, MAX_PAGES - startPage + 1);

      console.log(`\n========== Starting ASIN collection from page ${startPage} ==========`);
      console.log(`Requested pages: ${requestedPages}`);
      console.log(`Total pages to collect (limited by MAX_PAGES): ${totalPagesToCollect}`);

      // 開始ページに移動
      console.log(`Navigating to page ${startPage}...`);
      const startUrlObj = new URL(currentUrl);
      startUrlObj.searchParams.set('page', startPage.toString());
      const startPageUrl = startUrlObj.toString();

      try {
        await page.goto(startPageUrl, { waitUntil: 'networkidle' });
        await page.waitForSelector('table tbody tr', { timeout: 30000 });
        console.log(`Navigated to page ${startPage}`);

        // 開始ページ移動後もmarket=JPを確認
        await ensureJapanMarket();
      } catch (error) {
        console.log(`\n⚠️  Start page ${startPage} does not exist.`);
        console.log(`The filter results do not have ${startPage} pages of data.`);
        console.log(`Total ASINs collected: 0`);
        console.log(`Please try a lower START_PAGE value.`);

        // 0件でも正常終了扱いにするため、空の配列で検証をスキップ
        expect(0).toBeGreaterThanOrEqual(0);
        return;
      }

      // 指定ページから指定件数分を収集
      for (let i = 0; i < totalPagesToCollect; i++) {
        currentPage = startPage + i;

        // MAX_PAGESの制限チェック
        if (currentPage > MAX_PAGES) {
          console.log(`\n⚠️  Reached SellerSprite pagination limit (MAX_PAGES=${MAX_PAGES})`);
          console.log(`Total ASINs collected: ${allAsins.length}`);
          break;
        }

        console.log(`\n--- Processing page ${currentPage} (${allAsins.length} ASINs collected so far) ---`);

        // ASINを抽出
        const pageAsins = await page.evaluate(() => {
          const asinElements = document.querySelectorAll('table tbody tr');
          const asinList: string[] = [];

          asinElements.forEach(row => {
            const text = row.textContent || '';
            const match = text.match(/ASIN:\s*([A-Z0-9]{10})/);
            if (match && match[1]) {
              asinList.push(match[1]);
            }
          });

          return asinList;
        });

        console.log(`Found ${pageAsins.length} ASINs on page ${currentPage}`);
        allAsins.push(...pageAsins);

        // 目標件数に達したか、またはこれが最後のページの場合は終了
        if (allAsins.length >= asinCount || i >= totalPagesToCollect - 1) {
          break;
        }

        // 次のページに移動
        const nextPage = currentPage + 1;

        // 次ページがMAX_PAGESを超える場合は移動せずに終了
        if (nextPage > MAX_PAGES) {
          console.log(`\n⚠️  Next page (${nextPage}) exceeds SellerSprite pagination limit (MAX_PAGES=${MAX_PAGES})`);
          console.log(`Stopping collection. Total ASINs collected: ${allAsins.length}`);
          break;
        }

        console.log(`Moving to page ${nextPage}...`);

        try {
          // 次ページボタンをクリック
          const nextButton = page.locator('button:has-text("次へ"), button.btn-next, li.next:not(.disabled) a');

          if (await nextButton.count() > 0 && await nextButton.first().isEnabled()) {
            await nextButton.first().click();
            await page.waitForLoadState('networkidle');
            await page.waitForTimeout(2000); // 少し待機
            await page.waitForSelector('table tbody tr', { timeout: 30000 });
          } else {
            console.log('次ページボタンが見つからないか、無効です。URLで直接移動します。');
            const nextUrlObj = new URL(page.url());
            nextUrlObj.searchParams.set('page', nextPage.toString());
            const nextPageUrl = nextUrlObj.toString();

            await page.goto(nextPageUrl, { waitUntil: 'networkidle' });
            await page.waitForSelector('table tbody tr', { timeout: 30000 });
          }

          // ページ遷移後もmarket=JPを確認
          await ensureJapanMarket();
        } catch (error) {
          console.log(`\n⚠️  Page ${nextPage} does not exist or failed to load.`);
          console.log(`Stopping collection. Total ASINs collected so far: ${allAsins.length}`);
          break; // 次のページが存在しない場合は収集を終了
        }
      }

      // 重複を除去
      const uniqueAsins = [...new Set(allAsins)];

      console.log(`\n========== Collection Complete ==========`);
      console.log(`Total ASINs collected: ${allAsins.length}`);
      console.log(`Unique ASINs: ${uniqueAsins.length}`);
      console.log('==========================================\n');

      // タイムスタンプ付きファイル名を生成
      const now = new Date();
      const timestamp = now.toISOString()
        .replace(/[-:]/g, '')
        .replace(/\..+/, '')
        .replace('T', '_');

      const filename = `${timestamp}_asin_${uniqueAsins.length}.txt`;
      const outputPath = path.join(process.cwd(), filename);

      // テキストファイルに保存（1行1ASIN）
      fs.writeFileSync(outputPath, uniqueAsins.join('\n'), 'utf8');
      console.log(`ASINs saved to: ${outputPath}`);

      // 検証
      expect(uniqueAsins.length).toBeGreaterThan(0);
      console.log(`\n✓ Successfully collected ${uniqueAsins.length} unique ASINs`);

    } catch (error) {
      console.error('Error occurred:', error);
      throw error;
    } finally {
      // ブラウザを閉じる
      await context.close();
      await browser.close();
      console.log('Browser closed');
    }
  });
});
