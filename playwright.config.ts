import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright設定ファイル
 * https://playwright.dev/docs/test-configuration
 */
export default defineConfig({
  testDir: './sourcing/sources/sellersprite',

  /* テストの並列実行を無効化（ログインスクリプトは順次実行） */
  fullyParallel: false,
  workers: 1,

  /* 失敗時のリトライ回数 */
  retries: 0,

  /* タイムアウト設定 */
  timeout: 300000, // 5分
  expect: {
    timeout: 10000, // 10秒
  },

  /* レポート設定 */
  reporter: [
    ['html'],
    ['list'],
  ],

  /* すべてのテストで共有される設定 */
  use: {
    /* ベースURL */
    baseURL: 'https://www.sellersprite.com',

    /* スクリーンショットとビデオの設定 */
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',

    /* トレース設定 */
    trace: 'on-first-retry',

    /* ブラウザの設定 */
    viewport: { width: 1920, height: 1080 },

    /* ナビゲーションタイムアウト */
    navigationTimeout: 30000,

    /* アクションタイムアウト */
    actionTimeout: 10000,
  },

  /* ブラウザプロジェクトの設定 */
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        launchOptions: {
          args: [
            '--disable-blink-features=AutomationControlled',
          ],
        },
      },
    },
  ],
});
