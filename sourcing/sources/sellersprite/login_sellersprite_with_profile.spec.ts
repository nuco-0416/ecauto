import { test, expect, chromium } from '@playwright/test';
import * as dotenv from 'dotenv';
import * as path from 'path';

// 環境変数を読み込む
dotenv.config();

test('SellerSprite Google認証ログイン（プロファイル使用）', async () => {
  // Chromeプロファイルのパス
  const profilePath = path.join(process.cwd(), 'sourcing', 'data', 'chrome_profile');

  // プロファイルを使用してブラウザを起動
  const browser = await chromium.launchPersistentContext(profilePath, {
    headless: false, // プロファイル使用時はheadless: falseが推奨
    args: [
      '--disable-blink-features=AutomationControlled',
    ],
  });

  const page = await browser.newPage();

  try {
    // SellerSpriteのログインページにアクセス
    await page.goto('https://www.sellersprite.com/jp/w/user/login', { waitUntil: 'networkidle' });

    // プロファイルが保持されている場合、ボタンの表示が変わる
    // 「Hiroo でログイン」のようなボタンを探す
    const profileLoginButton = page.frameLocator('iframe[title="[Googleでログイン]ボタン"]')
      .locator('button:has-text("でログイン")');

    // ボタンが見つかるまで待機
    await profileLoginButton.waitFor({ timeout: 5000 }).catch(() => {
      console.log('プロファイル付きログインボタンが見つかりませんでした');
    });

    // ボタンをクリック
    await profileLoginButton.click();

    // Googleアカウント選択画面に遷移
    await page.waitForURL(/accounts\.google\.com/, { timeout: 10000 });

    // アカウント選択画面でアカウントを選択
    // 「Hiroo Oguchi hiroo.oguchi@gmail.com」のようなリンクを探す
    const accountLink = page.locator('a:has-text("hiroo.oguchi@gmail.com")');

    await accountLink.waitFor({ timeout: 10000 }).catch(async () => {
      console.log('アカウント選択リンクが見つかりませんでした。パスワード入力が必要な可能性があります。');

      // パスワード入力が必要な場合の処理
      const googlePassword = process.env.GOOGLE_PASSWORD;
      if (!googlePassword) {
        throw new Error('GOOGLE_PASSWORD を .env ファイルに設定してください');
      }

      // パスワード入力フィールドを探す
      const passwordField = page.getByRole('textbox', { name: 'パスワードを入力' });
      if (await passwordField.isVisible({ timeout: 5000 }).catch(() => false)) {
        await passwordField.fill(googlePassword);
        await page.getByRole('button', { name: '次へ' }).click();
      }
    });

    // アカウントリンクが見つかった場合はクリック
    if (await accountLink.isVisible({ timeout: 5000 }).catch(() => false)) {
      await accountLink.click();
    }

    // Google同意画面が表示される場合がある
    // 「続行」「許可」などのボタンを探す
    const continueButton = page.locator('button:has-text("続行"), button:has-text("許可"), button:has-text("同意")');
    if (await continueButton.isVisible({ timeout: 5000 }).catch(() => false)) {
      console.log('Google同意画面が表示されました。同意ボタンをクリックします。');
      await continueButton.first().click();
    }

    // 2段階認証が必要な場合
    const twoFactorHeading = page.getByRole('heading', { name: '2 段階認証プロセス' });
    if (await twoFactorHeading.isVisible({ timeout: 5000 }).catch(() => false)) {
      console.log('2段階認証の画面に到達しました');
      console.log('スマホでGmailアプリを開いて「はい」をタップして認証を完了してください');

      // スマホでの認証を待つ（最大3分）
      await page.waitForURL(/www\.sellersprite\.com/, { timeout: 180000 }).catch(() => {
        console.log('2段階認証がタイムアウトしました');
      });
    }

    // SellerSpriteにログインできたか確認
    await page.waitForURL(/www\.sellersprite\.com/, { timeout: 30000 });

    // ログインエラーが表示されていないか確認
    const loginError = page.locator('text=login error!');
    if (await loginError.isVisible({ timeout: 2000 }).catch(() => false)) {
      console.error('ログインエラーが発生しました');
      throw new Error('SellerSpriteへのログインに失敗しました');
    }

    console.log('SellerSpriteへのログインに成功しました！');

    // ログイン後のページを少し待機
    await page.waitForTimeout(5000);

  } catch (error) {
    console.error('エラーが発生しました:', error);
    throw error;
  } finally {
    // ブラウザを閉じる
    await browser.close();
  }
});
