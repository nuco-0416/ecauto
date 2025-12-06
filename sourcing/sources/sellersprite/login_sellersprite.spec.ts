import { test, expect } from '@playwright/test';
import * as dotenv from 'dotenv';

// 環境変数を読み込む
dotenv.config();

test('SellerSprite Google認証ログイン', async ({ page }) => {
  // 環境変数から認証情報を取得
  const googleEmail = process.env.GOOGLE_EMAIL;
  const googlePassword = process.env.GOOGLE_PASSWORD;

  if (!googleEmail || !googlePassword) {
    throw new Error('GOOGLE_EMAIL と GOOGLE_PASSWORD を .env ファイルに設定してください');
  }

  // SellerSpriteのログインページにアクセス
  await page.goto('https://www.sellersprite.com/jp/w/user/login');

  // Googleログインボタンを探してクリック
  const googleLoginButton = page.frameLocator('iframe[title="[Googleでログイン]ボタン"]')
    .getByRole('button', { name: 'Google でログイン。新しいタブで開きます' });
  await googleLoginButton.click();

  // Googleログインページに遷移
  await page.waitForURL(/accounts\.google\.com/);

  // メールアドレスを入力
  await page.getByRole('textbox', { name: 'メールアドレスまたは電話番号' }).fill(googleEmail);

  // 「次へ」ボタンをクリック
  await page.getByRole('button', { name: '次へ' }).click();

  // パスワード入力画面を待機
  await page.waitForURL(/challenge\/pwd/);

  // パスワードを入力
  await page.getByRole('textbox', { name: 'パスワードを入力' }).fill(googlePassword);

  // 「次へ」ボタンをクリック
  await page.getByRole('button', { name: '次へ' }).click();

  // 2段階認証の画面まで待機
  await page.waitForURL(/challenge\/dp/);

  console.log('2段階認証の画面に到達しました');
  console.log('スマホでGmailアプリを開いて「はい」をタップして認証を完了してください');

  // 2段階認証の画面が表示されていることを確認
  await expect(page.getByRole('heading', { name: '2 段階認証プロセス' })).toBeVisible();

  // ここでスマホでの認証を待つ（タイムアウトを長めに設定）
  // 実際の使用時は、手動で認証を完了させるか、適切な待機処理を追加してください
  await page.waitForTimeout(60000); // 60秒待機（必要に応じて調整）
});
