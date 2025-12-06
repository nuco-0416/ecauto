"""
SellerSprite ASIN抽出 基底クラス

すべての抽出パターンに共通する機能を提供。
"""

import json
import os
import re
import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from playwright.async_api import async_playwright
from ..browser_controller import BrowserController


class BaseExtractor(ABC):
    """
    ASIN抽出の基底クラス

    サブクラスで _extract_impl() を実装することで、
    具体的な抽出ロジックを定義できる。
    """

    def __init__(
        self,
        pattern_name: str,
        parameters: Dict[str, Any],
        db_path: Optional[Path] = None
    ):
        """
        Args:
            pattern_name: 抽出パターン名（'ranking', 'category', 'seasonal'）
            parameters: 抽出パラメータ（カテゴリ名、ランキング範囲等）
            db_path: sourcing.db のパス（Noneの場合はデフォルト）
        """
        self.pattern_name = pattern_name
        self.parameters = parameters
        self.log_id = None

        # ブラウザを開いたままにするオプション（デバッグ用）
        self.keep_browser_open = parameters.get("keep_browser_open", False)

        # データベースパス
        if db_path is None:
            base_dir = Path(__file__).parent.parent.parent.parent
            db_path = base_dir / 'data' / 'sourcing.db'

        self.db_path = db_path

    def log(self, message: str):
        """ログ出力"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")

    async def extract_with_page(self, page) -> List[str]:
        """
        既存のブラウザセッションを使用してASINを抽出（ログインスキップ）

        BulkExtractor等で複数回抽出する際に、ログインを1回だけにするために使用。

        Args:
            page: Playwrightのページオブジェクト（既にログイン済み）

        Returns:
            抽出されたASINリスト
        """
        # ログ記録開始
        self.log_id = self._start_log()
        self.log(f"抽出開始: {self.pattern_name}")
        self.log(f"パラメータ: {json.dumps(self.parameters, ensure_ascii=False)}")

        try:
            # BrowserControllerを初期化
            controller = BrowserController(page, verbose=True)

            # 具体的な抽出処理（サブクラスで実装）
            self.log(f"抽出処理を実行: {self.pattern_name}")
            asins = await self._extract_impl(controller)

            # 重複除去
            unique_asins = list(set(asins))
            self.log(f"抽出完了: {len(unique_asins)}件（重複除去前: {len(asins)}件）")

            # データベースに候補として保存
            self._save_candidates(unique_asins)

            # ログ記録完了
            self._complete_log(unique_asins)

            return unique_asins

        except Exception as e:
            self.log(f"[ERROR] 抽出失敗: {e}")
            self._fail_log(str(e))
            raise

    async def extract(self) -> List[str]:
        """
        ASINを抽出するメインメソッド（シングルセッション方式）

        TypeScript版と同様に、ログインからASIN抽出までを
        単一のブラウザセッション内で完結させます。

        Returns:
            抽出されたASINリスト
        """
        # ログ記録開始
        self.log_id = self._start_log()
        self.log(f"抽出開始: {self.pattern_name}")
        self.log(f"パラメータ: {json.dumps(self.parameters, ensure_ascii=False)}")

        # 環境変数から認証情報を取得
        email = os.getenv('SELLERSPRITE_EMAIL')
        password = os.getenv('SELLERSPRITE_PASSWORD')

        if not email or not password:
            error_msg = "環境変数 SELLERSPRITE_EMAIL と SELLERSPRITE_PASSWORD が設定されていません"
            self.log(f"[ERROR] {error_msg}")
            self._fail_log(error_msg)
            raise Exception(error_msg)

        try:
            async with async_playwright() as p:
                # ブラウザを起動（シングルセッション）
                self.log("ブラウザを起動中...")
                browser = await p.chromium.launch(
                    headless=False,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--disable-automation',
                        '--disable-dev-shm-usage',
                        '--no-sandbox',
                    ],
                )

                context = await browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    locale="ja-JP",
                    timezone_id="Asia/Tokyo",
                )

                page = await context.new_page()

                try:
                    # SellerSpriteにログイン
                    self.log("SellerSpriteにログイン中...")
                    await page.goto("https://www.sellersprite.com/jp/w/user/login",
                                   wait_until="networkidle",
                                   timeout=30000)

                    # メールアドレス入力
                    email_input = page.get_by_role('textbox', name=re.compile(r'メールアドレス|アカウント', re.IGNORECASE))
                    await email_input.fill(email)
                    await page.wait_for_timeout(1000)

                    # パスワード入力
                    password_input = page.get_by_role('textbox', name=re.compile(r'パスワード', re.IGNORECASE))
                    await password_input.fill(password)
                    await page.wait_for_timeout(1000)

                    # ログインボタンをクリック
                    login_button = page.get_by_role('button', name=re.compile(r'ログイン', re.IGNORECASE))
                    await login_button.click()

                    # ログイン完了を待機
                    try:
                        await page.wait_for_url(re.compile(r'/(welcome|dashboard)'), timeout=30000)
                        self.log("[OK] ログイン成功")
                    except Exception as e:
                        current_url = page.url
                        if 'login' not in current_url:
                            self.log("[OK] ログイン成功（URL遷移確認）")
                        else:
                            raise Exception(f"ログインに失敗しました: {e}")

                    # BrowserControllerを初期化
                    controller = BrowserController(page, verbose=True)

                    # 具体的な抽出処理（サブクラスで実装）
                    self.log(f"抽出処理を実行: {self.pattern_name}")
                    asins = await self._extract_impl(controller)

                    # 重複除去（文字列リストまたは辞書リストに対応）
                    if asins and isinstance(asins[0], dict):
                        # 辞書のリストの場合（カテゴリ情報付き）
                        seen_asins = {}
                        unique_asins = []
                        for item in asins:
                            asin = item.get('asin')
                            if asin and asin not in seen_asins:
                                seen_asins[asin] = True
                                unique_asins.append(item)
                        self.log(f"抽出完了: {len(unique_asins)}件（重複除去前: {len(asins)}件）")
                    else:
                        # 文字列のリストの場合（ASINのみ）
                        unique_asins = list(set(asins))
                        self.log(f"抽出完了: {len(unique_asins)}件（重複除去前: {len(asins)}件）")

                    # データベースに候補として保存
                    self._save_candidates(unique_asins)

                    # ログ記録完了
                    self._complete_log(unique_asins)

                    return unique_asins

                finally:
                    # keep_browser_openフラグがTrueの場合はブラウザを閉じない（デバッグ用）
                    if not self.keep_browser_open:
                        await context.close()
                        await browser.close()
                        self.log("ブラウザを閉じました")
                    else:
                        self.log("[OK] ブラウザウィンドウを開いたまま保持（デバッグモード）")

        except Exception as e:
            self.log(f"[ERROR] 抽出失敗: {e}")
            self._fail_log(str(e))
            raise

    @abstractmethod
    async def _extract_impl(self, controller: BrowserController) -> List[str]:
        """
        具体的な抽出ロジック（サブクラスで実装）

        Args:
            controller: BrowserControllerインスタンス

        Returns:
            ASINリスト
        """
        pass

    def _start_log(self) -> int:
        """
        抽出ログを開始

        Returns:
            int: ログID
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT INTO extraction_logs (
                    extraction_type,
                    parameters,
                    status,
                    started_at
                ) VALUES (?, ?, 'running', ?)
            ''', (
                self.pattern_name,
                json.dumps(self.parameters, ensure_ascii=False),
                datetime.now().isoformat()
            ))

            log_id = cursor.lastrowid
            conn.commit()

            self.log(f"抽出ログ開始: ID={log_id}")
            return log_id

        finally:
            conn.close()

    def _complete_log(self, asins: List[str]):
        """
        抽出ログを完了

        Args:
            asins: 抽出されたASINリスト
        """
        if self.log_id is None:
            return

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute('''
                UPDATE extraction_logs
                SET status = 'completed',
                    asins_found = ?,
                    completed_at = ?
                WHERE id = ?
            ''', (len(asins), datetime.now().isoformat(), self.log_id))

            conn.commit()
            self.log(f"抽出ログ完了: ID={self.log_id}")

        finally:
            conn.close()

    def _fail_log(self, error_message: str):
        """
        抽出ログを失敗として記録

        Args:
            error_message: エラーメッセージ
        """
        if self.log_id is None:
            return

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute('''
                UPDATE extraction_logs
                SET status = 'failed',
                    error_message = ?,
                    completed_at = ?
                WHERE id = ?
            ''', (error_message, datetime.now().isoformat(), self.log_id))

            conn.commit()
            self.log(f"抽出ログ失敗記録: ID={self.log_id}")

        finally:
            conn.close()

    def _save_candidates(self, asins):
        """
        抽出したASINを候補として保存

        Args:
            asins: ASINリスト（文字列のリストまたは辞書のリスト）
        """
        if not asins:
            return

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            saved_count = 0
            updated_count = 0

            for item in asins:
                # 辞書の場合はASINを取得、文字列の場合はそのまま使用
                if isinstance(item, dict):
                    asin = item.get('asin')
                else:
                    asin = item

                if not asin:
                    continue

                # 既存チェック
                cursor.execute('SELECT id FROM sourcing_candidates WHERE asin = ?', (asin,))
                existing = cursor.fetchone()

                if existing:
                    # 既存の場合は更新（最終発見日時を更新）
                    cursor.execute('''
                        UPDATE sourcing_candidates
                        SET discovered_at = ?
                        WHERE asin = ?
                    ''', (datetime.now().isoformat(), asin))
                    updated_count += 1
                else:
                    # 新規の場合は挿入
                    cursor.execute('''
                        INSERT INTO sourcing_candidates (
                            asin,
                            source,
                            status,
                            discovered_at
                        ) VALUES (?, 'sellersprite', 'candidate', ?)
                    ''', (asin, datetime.now().isoformat()))
                    saved_count += 1

            conn.commit()
            self.log(f"候補保存: 新規={saved_count}件, 更新={updated_count}件")

        except Exception as e:
            self.log(f"[WARN] 候補保存エラー: {e}")
            conn.rollback()

        finally:
            conn.close()

    def get_extraction_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        抽出履歴を取得

        Args:
            limit: 取得件数

        Returns:
            List[Dict]: 抽出履歴
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute('''
                SELECT *
                FROM extraction_logs
                WHERE extraction_type = ?
                ORDER BY started_at DESC
                LIMIT ?
            ''', (self.pattern_name, limit))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

        finally:
            conn.close()
