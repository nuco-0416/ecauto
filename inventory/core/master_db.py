"""
Master Database Manager

全プラットフォームの商品・出品情報を管理するSQLiteデータベース
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

# NGキーワードクリーニング機能をインポート
try:
    from common.ng_keyword_filter import clean_product_data
    NG_KEYWORD_AVAILABLE = True
except ImportError:
    NG_KEYWORD_AVAILABLE = False
    print("[WARN] NGキーワードクリーニング機能が利用できません")


class MasterDB:
    """
    SQLiteベースのマスタデータベース管理クラス
    """

    def __init__(self, db_path: str = None):
        """
        Args:
            db_path: データベースファイルのパス（デフォルト: inventory/data/master.db）
        """
        if db_path is None:
            # デフォルトパス
            base_dir = Path(__file__).resolve().parent.parent
            db_path = base_dir / 'data' / 'master.db'

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # 初期化時にテーブルを作成
        self._init_tables()

    @contextmanager
    def get_connection(self):
        """データベース接続のコンテキストマネージャー"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # 列名でアクセス可能に
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def _init_tables(self):
        """テーブルの初期化"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # products テーブル（商品マスタ）
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS products (
                    asin TEXT PRIMARY KEY,
                    title_ja TEXT,
                    title_en TEXT,
                    description_ja TEXT,
                    description_en TEXT,
                    category TEXT,
                    brand TEXT,
                    images TEXT,              -- JSON形式
                    amazon_price_jpy INTEGER,
                    amazon_in_stock BOOLEAN,
                    last_fetched_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # listings テーブル（出品情報）
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS listings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asin TEXT,
                    platform TEXT,            -- 'base', 'ebay', 'yahoo', 'mercari'
                    account_id TEXT,          -- 'base_account_1', 'ebay_main', etc.
                    platform_item_id TEXT,    -- BASE item_id, eBay listing_id等
                    sku TEXT UNIQUE,
                    selling_price REAL,
                    currency TEXT DEFAULT 'JPY',
                    in_stock_quantity INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'pending',  -- 'pending', 'queued', 'listed', 'sold', 'delisted'
                    visibility TEXT DEFAULT 'public',  -- 'public', 'hidden'
                    listed_at TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (asin) REFERENCES products(asin)
                )
            ''')

            # インデックス作成
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_listings_asin
                ON listings(asin)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_listings_platform_account
                ON listings(platform, account_id)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_listings_status
                ON listings(status)
            ''')

            # UNIQUE制約: 同じASINは1つのplatformの同じアカウント内で1つのみ出品可能
            # Issue #013: account_idを追加してaccount別の出品を可能にする
            cursor.execute('''
                CREATE UNIQUE INDEX IF NOT EXISTS idx_listings_asin_platform_account_unique
                ON listings(asin, platform, account_id)
            ''')

            # upload_queue テーブル（出品キュー）
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS upload_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asin TEXT,
                    platform TEXT,
                    account_id TEXT,
                    scheduled_time TIMESTAMP,
                    priority INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'pending',  -- 'pending', 'processing', 'completed', 'failed'
                    retry_count INTEGER DEFAULT 0,
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed_at TIMESTAMP,
                    FOREIGN KEY (asin) REFERENCES products(asin)
                )
            ''')

            # インデックス作成
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_queue_scheduled
                ON upload_queue(platform, account_id, scheduled_time, status)
            ''')

            # UNIQUE制約: 同じASINは1つのplatformの同じアカウント内で1つのみキューに追加可能
            # Issue #014: UNIQUE制約を追加して重複レコードを防止
            cursor.execute('''
                CREATE UNIQUE INDEX IF NOT EXISTS idx_queue_asin_platform_account_unique
                ON upload_queue(asin, platform, account_id)
            ''')

            # account_configs テーブル（アカウント設定）
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS account_configs (
                    id TEXT PRIMARY KEY,      -- 'base_account_1'
                    platform TEXT,
                    name TEXT,
                    category_filter TEXT,     -- JSON形式
                    daily_upload_limit INTEGER DEFAULT 1000,
                    rate_limit_per_hour INTEGER DEFAULT 50,
                    active BOOLEAN DEFAULT 1,
                    credentials TEXT,         -- JSON形式（暗号化推奨）
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # ebay_listing_metadata テーブル（eBay固有のリスティングメタデータ）
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS ebay_listing_metadata (
                    sku TEXT PRIMARY KEY,
                    listing_id TEXT,
                    offer_id TEXT,
                    category_id TEXT,
                    policy_payment_id TEXT,
                    policy_return_id TEXT,
                    policy_fulfillment_id TEXT,
                    item_specifics TEXT,      -- JSON形式
                    merchant_location_key TEXT DEFAULT 'JP_LOCATION',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (sku) REFERENCES listings(sku)
                )
            ''')

    # ==================== Products（商品マスタ）====================

    def add_product(self, asin: str, title_ja: str = None, title_en: str = None,
                   description_ja: str = None, description_en: str = None,
                   category: str = None, brand: str = None, images: List[str] = None,
                   amazon_price_jpy: int = None, amazon_in_stock: bool = None) -> bool:
        """
        商品を追加（既存の場合は更新）
        NGキーワードを自動的にクリーニングします

        IMPORTANT: NULLの場合は既存値を保持します（ISSUE #23対策）

        Returns:
            bool: 成功時True
        """
        # 既存レコードを確認
        existing = self.get_product(asin)

        # NULLの場合は既存値を使用（既存レコードがある場合のみ）
        if existing:
            title_ja = title_ja if title_ja is not None else existing.get('title_ja')
            title_en = title_en if title_en is not None else existing.get('title_en')
            description_ja = description_ja if description_ja is not None else existing.get('description_ja')
            description_en = description_en if description_en is not None else existing.get('description_en')
            category = category if category is not None else existing.get('category')
            brand = brand if brand is not None else existing.get('brand')
            images = images if images is not None else existing.get('images')
            amazon_price_jpy = amazon_price_jpy if amazon_price_jpy is not None else existing.get('amazon_price_jpy')
            amazon_in_stock = amazon_in_stock if amazon_in_stock is not None else existing.get('amazon_in_stock')

        # NGキーワードクリーニング（テキストフィールドのみ）
        if NG_KEYWORD_AVAILABLE:
            product_data = {
                'title_ja': title_ja,
                'title_en': title_en,
                'description_ja': description_ja,
                'description_en': description_en
            }
            cleaned_data, removed = clean_product_data(product_data, asin)

            if removed:
                title_ja = cleaned_data.get('title_ja')
                title_en = cleaned_data.get('title_en')
                description_ja = cleaned_data.get('description_ja')
                description_en = cleaned_data.get('description_en')

        with self.get_connection() as conn:
            cursor = conn.cursor()

            images_json = json.dumps(images) if images else None
            now = datetime.now().isoformat()

            cursor.execute('''
                INSERT OR REPLACE INTO products
                (asin, title_ja, title_en, description_ja, description_en,
                 category, brand, images, amazon_price_jpy, amazon_in_stock,
                 last_fetched_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (asin, title_ja, title_en, description_ja, description_en,
                  category, brand, images_json, amazon_price_jpy, amazon_in_stock,
                  now, now))

            return True

    def get_product(self, asin: str) -> Optional[Dict[str, Any]]:
        """
        ASINで商品情報を取得

        Returns:
            dict or None: 商品情報の辞書
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM products WHERE asin = ?', (asin,))
            row = cursor.fetchone()

            if row:
                product = dict(row)
                # JSON文字列をパース
                if product.get('images'):
                    product['images'] = json.loads(product['images'])
                return product
            return None

    def update_amazon_info(self, asin: str, price_jpy: int, in_stock: bool) -> bool:
        """
        Amazon価格・在庫情報を更新
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()

            cursor.execute('''
                UPDATE products
                SET amazon_price_jpy = ?,
                    amazon_in_stock = ?,
                    last_fetched_at = ?,
                    updated_at = ?
                WHERE asin = ?
            ''', (price_jpy, in_stock, now, now, asin))

            return cursor.rowcount > 0

    # ==================== Listings（出品情報）====================

    def add_listing(self, asin: str, platform: str, account_id: str,
                   platform_item_id: str = None, sku: str = None,
                   selling_price: float = None, currency: str = 'JPY',
                   in_stock_quantity: int = 0, status: str = 'pending',
                   visibility: str = 'public') -> Optional[int]:
        """
        出品情報を追加

        Returns:
            int or None: 追加された listing ID
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()

            cursor.execute('''
                INSERT INTO listings
                (asin, platform, account_id, platform_item_id, sku,
                 selling_price, currency, in_stock_quantity, status, visibility,
                 listed_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (asin, platform, account_id, platform_item_id, sku,
                  selling_price, currency, in_stock_quantity, status, visibility,
                  now, now))

            return cursor.lastrowid

    def get_listings_by_account(self, platform: str, account_id: str,
                               status: str = None) -> List[Dict[str, Any]]:
        """
        アカウント別に出品一覧を取得
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            if status:
                cursor.execute('''
                    SELECT * FROM listings
                    WHERE platform = ? AND account_id = ? AND status = ?
                    ORDER BY updated_at DESC
                ''', (platform, account_id, status))
            else:
                cursor.execute('''
                    SELECT * FROM listings
                    WHERE platform = ? AND account_id = ?
                    ORDER BY updated_at DESC
                ''', (platform, account_id))

            return [dict(row) for row in cursor.fetchall()]

    def get_listings_by_asin(self, asin: str) -> List[Dict[str, Any]]:
        """
        ASINで出品情報を取得（複数プラットフォームの可能性あり）

        Args:
            asin: 商品ASIN

        Returns:
            list: 出品情報のリスト
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('''
                SELECT * FROM listings
                WHERE asin = ?
                ORDER BY updated_at DESC
            ''', (asin,))

            return [dict(row) for row in cursor.fetchall()]

    def get_listing_by_sku(self, sku: str) -> Optional[Dict[str, Any]]:
        """
        SKUで出品情報を取得

        Returns:
            dict or None: 出品情報の辞書
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM listings WHERE sku = ?', (sku,))
            row = cursor.fetchone()

            if row:
                return dict(row)
            return None

    def upsert_listing(self, asin: str, platform: str, account_id: str,
                      platform_item_id: str = None, sku: str = None,
                      selling_price: float = None, currency: str = 'JPY',
                      in_stock_quantity: int = 0, status: str = 'pending',
                      visibility: str = 'public') -> Optional[int]:
        """
        出品情報を追加または更新（UPSERT）
        SKUが既に存在する場合は更新、存在しない場合は追加

        Returns:
            int or None: listing ID
        """
        # 既存の出品をSKUで検索
        if sku:
            existing = self.get_listing_by_sku(sku)
            if existing:
                # 既存の出品を更新
                self.update_listing(
                    existing['id'],
                    asin=asin,
                    platform=platform,
                    account_id=account_id,
                    platform_item_id=platform_item_id,
                    selling_price=selling_price,
                    currency=currency,
                    in_stock_quantity=in_stock_quantity,
                    status=status,
                    visibility=visibility
                )
                return existing['id']

        # 新規追加
        return self.add_listing(
            asin=asin,
            platform=platform,
            account_id=account_id,
            platform_item_id=platform_item_id,
            sku=sku,
            selling_price=selling_price,
            currency=currency,
            in_stock_quantity=in_stock_quantity,
            status=status,
            visibility=visibility
        )

    def update_listing(self, listing_id: int, **kwargs) -> bool:
        """
        出品情報を更新

        Args:
            listing_id: Listing ID
            **kwargs: 更新するフィールド（selling_price, status, visibility等）
        """
        if not kwargs:
            return False

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 更新フィールドを構築
            fields = ', '.join([f'{k} = ?' for k in kwargs.keys()])
            values = list(kwargs.values())
            values.append(datetime.now().isoformat())  # updated_at
            values.append(listing_id)

            cursor.execute(f'''
                UPDATE listings
                SET {fields}, updated_at = ?
                WHERE id = ?
            ''', values)

            return cursor.rowcount > 0

    # ==================== Upload Queue（出品キュー）====================

    def add_to_queue(self, asin: str, platform: str, account_id: str,
                    scheduled_time: str, priority: int = 0) -> Optional[int]:
        """
        出品キューに追加

        Args:
            scheduled_time: ISO形式の日時文字列

        Returns:
            int or None: 追加されたキューID
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO upload_queue
                (asin, platform, account_id, scheduled_time, priority, status)
                VALUES (?, ?, ?, ?, ?, 'pending')
            ''', (asin, platform, account_id, scheduled_time, priority))

            return cursor.lastrowid

    def add_to_upload_queue(self, asin: str, platform: str, account_id: str,
                           priority: int, scheduled_at: datetime,
                           metadata: Dict[str, Any] = None) -> bool:
        """
        出品キューに追加（新インターフェース）

        Args:
            asin: 商品ASIN
            platform: プラットフォーム名
            account_id: アカウントID
            priority: 優先度
            scheduled_at: アップロード予定時刻（datetime）
            metadata: メタデータ（JSON）

        Returns:
            bool: 成功時True（既に出品済みの場合はFalse）
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 既に出品済み（listings.status='listed'）の商品をチェック
            cursor.execute('''
                SELECT status, platform_item_id
                FROM listings
                WHERE asin = ? AND platform = ? AND account_id = ?
            ''', (asin, platform, account_id))

            existing_listing = cursor.fetchone()

            if existing_listing and existing_listing['status'] == 'listed':
                # 既に出品済みの場合はスキップ
                print(f"  [SKIP] {asin}: 既に出品済み (platform_item_id: {existing_listing['platform_item_id']})")
                return False

            # metadataはupload_queueテーブルにないので無視
            scheduled_at_str = scheduled_at.isoformat()

            cursor.execute('''
                INSERT INTO upload_queue
                (asin, platform, account_id, scheduled_time, priority, status)
                VALUES (?, ?, ?, ?, ?, 'pending')
            ''', (asin, platform, account_id, scheduled_at_str, priority))

            return True

    def get_due_uploads(self, platform: str, account_id: str,
                       limit: int = 100) -> List[Dict[str, Any]]:
        """
        実行すべき出品を取得

        Args:
            limit: 取得件数上限
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()

            cursor.execute('''
                SELECT * FROM upload_queue
                WHERE platform = ?
                  AND account_id = ?
                  AND status = 'pending'
                  AND scheduled_time <= ?
                ORDER BY scheduled_time ASC, priority DESC
                LIMIT ?
            ''', (platform, account_id, now, limit))

            return [dict(row) for row in cursor.fetchall()]

    def update_queue_status(self, queue_id: int, status: str,
                           error_message: str = None) -> bool:
        """
        キューのステータスを更新
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()

            if status in ('completed', 'failed'):
                cursor.execute('''
                    UPDATE upload_queue
                    SET status = ?,
                        error_message = ?,
                        processed_at = ?
                    WHERE id = ?
                ''', (status, error_message, now, queue_id))
            else:
                cursor.execute('''
                    UPDATE upload_queue
                    SET status = ?
                    WHERE id = ?
                ''', (status, queue_id))

            return cursor.rowcount > 0

    # ==================== Account Configs（アカウント設定）====================

    def add_account_config(self, account_id: str, platform: str, name: str,
                          category_filter: Dict = None,
                          daily_upload_limit: int = 1000,
                          rate_limit_per_hour: int = 50,
                          active: bool = True,
                          credentials: Dict = None) -> bool:
        """
        アカウント設定を追加
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            category_filter_json = json.dumps(category_filter) if category_filter else None
            credentials_json = json.dumps(credentials) if credentials else None

            cursor.execute('''
                INSERT OR REPLACE INTO account_configs
                (id, platform, name, category_filter, daily_upload_limit,
                 rate_limit_per_hour, active, credentials, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (account_id, platform, name, category_filter_json,
                  daily_upload_limit, rate_limit_per_hour, active,
                  credentials_json, datetime.now().isoformat()))

            return True

    def get_active_accounts(self, platform: str) -> List[Dict[str, Any]]:
        """
        アクティブなアカウント一覧を取得
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('''
                SELECT * FROM account_configs
                WHERE platform = ? AND active = 1
                ORDER BY id
            ''', (platform,))

            accounts = []
            for row in cursor.fetchall():
                account = dict(row)
                # JSON文字列をパース
                if account.get('category_filter'):
                    account['category_filter'] = json.loads(account['category_filter'])
                if account.get('credentials'):
                    account['credentials'] = json.loads(account['credentials'])
                accounts.append(account)

            return accounts

    def get_upload_count_by_account_and_date(self, account_id: str, date) -> int:
        """
        特定の日付における特定アカウントのアップロード件数を取得

        Args:
            account_id: アカウントID
            date: 日付（datetime.date オブジェクト）

        Returns:
            int: アップロード件数
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # scheduled_time が指定日付のものをカウント
            date_str = date.strftime('%Y-%m-%d')
            start_datetime = f"{date_str} 00:00:00"
            end_datetime = f"{date_str} 23:59:59"

            cursor.execute('''
                SELECT COUNT(*) as count
                FROM upload_queue
                WHERE account_id = ?
                AND scheduled_time BETWEEN ? AND ?
            ''', (account_id, start_datetime, end_datetime))

            row = cursor.fetchone()
            return row['count'] if row else 0

    def get_upload_queue(
        self,
        status: str = None,
        platform: str = None,
        account_id: str = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        アップロードキューを取得（フィルタ付き）

        Args:
            status: ステータスフィルタ
            platform: プラットフォームフィルタ
            account_id: アカウントIDフィルタ
            limit: 取得件数

        Returns:
            list: キューアイテムのリスト
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            query = 'SELECT * FROM upload_queue WHERE 1=1'
            params = []

            if status:
                query += ' AND status = ?'
                params.append(status)

            if platform:
                query += ' AND platform = ?'
                params.append(platform)

            if account_id:
                query += ' AND account_id = ?'
                params.append(account_id)

            query += ' ORDER BY priority DESC, scheduled_time ASC LIMIT ?'
            params.append(limit)

            cursor.execute(query, params)

            items = []
            for row in cursor.fetchall():
                item = dict(row)
                # JSON文字列をパース
                if item.get('metadata'):
                    item['metadata'] = json.loads(item['metadata'])
                if item.get('result_data'):
                    item['result_data'] = json.loads(item['result_data'])
                items.append(item)

            return items

    def get_upload_queue_due(
        self,
        limit: int = 100,
        platform: str = None,
        account_id: str = None
    ) -> List[Dict[str, Any]]:
        """
        scheduled_at が現在時刻を過ぎたアイテムを取得

        Args:
            limit: 取得件数
            platform: プラットフォームフィルタ（オプション）
            account_id: アカウントIDフィルタ（オプション）

        Returns:
            list: キューアイテムのリスト
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # SQLiteのdatetime関数を使って正規化して比較（ローカル時間）
            query = '''
                SELECT * FROM upload_queue
                WHERE status = 'pending'
                AND datetime(scheduled_time) <= datetime('now', 'localtime')
            '''
            params = []

            if platform:
                query += ' AND platform = ?'
                params.append(platform)

            if account_id:
                query += ' AND account_id = ?'
                params.append(account_id)

            query += ' ORDER BY priority DESC, scheduled_time ASC LIMIT ?'
            params.append(limit)

            cursor.execute(query, params)

            items = []
            for row in cursor.fetchall():
                item = dict(row)
                if item.get('metadata'):
                    item['metadata'] = json.loads(item['metadata'])
                if item.get('result_data'):
                    item['result_data'] = json.loads(item['result_data'])
                items.append(item)

            return items

    def update_upload_queue_status(
        self,
        queue_id: int,
        status: str,
        result_data: Dict[str, Any] = None,
        error_message: str = None
    ) -> bool:
        """
        アップロードキューのステータスを更新

        成功時はlistingsテーブルも更新する

        Args:
            queue_id: キューID
            status: 新しいステータス
            result_data: 結果データ（JSON）
                - platform_item_id: プラットフォーム側の商品ID
            error_message: エラーメッセージ

        Returns:
            bool: 成功時True
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()

            # キュー情報を取得（listingsテーブル更新用）
            cursor.execute('''
                SELECT asin, platform, account_id
                FROM upload_queue
                WHERE id = ?
            ''', (queue_id,))
            queue_info = cursor.fetchone()

            # upload_queueテーブルを更新
            if status in ('success', 'failed', 'completed'):
                cursor.execute('''
                    UPDATE upload_queue
                    SET status = ?,
                        error_message = ?,
                        processed_at = ?
                    WHERE id = ?
                ''', (status, error_message, now, queue_id))
            else:
                cursor.execute('''
                    UPDATE upload_queue
                    SET status = ?,
                        error_message = ?
                    WHERE id = ?
                ''', (status, error_message, queue_id))

            # 成功時はlistingsテーブルも更新
            if status == 'success' and queue_info and result_data:
                platform_item_id = result_data.get('platform_item_id')
                if platform_item_id:
                    cursor.execute('''
                        UPDATE listings
                        SET status = 'listed',
                            platform_item_id = ?,
                            listed_at = ?
                        WHERE asin = ? AND platform = ? AND account_id = ?
                    ''', (
                        platform_item_id,
                        now,
                        queue_info['asin'],
                        queue_info['platform'],
                        queue_info['account_id']
                    ))

            return cursor.rowcount > 0

    # ==================== eBay Metadata ====================

    def save_ebay_metadata(self, sku: str, metadata: Dict[str, Any]) -> bool:
        """
        eBay出品メタデータを保存

        Args:
            sku: 商品SKU
            metadata: eBayメタデータ
                {
                    'listing_id': str,
                    'offer_id': str,
                    'category_id': str,
                    'policy_payment_id': str,
                    'policy_return_id': str,
                    'policy_fulfillment_id': str,
                    'item_specifics': dict (optional),
                    'merchant_location_key': str (optional)
                }

        Returns:
            bool: 成功時True
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()

            # item_specificsをJSON文字列に変換
            item_specifics_json = None
            if metadata.get('item_specifics'):
                item_specifics_json = json.dumps(metadata['item_specifics'])

            cursor.execute('''
                INSERT INTO ebay_listing_metadata (
                    sku,
                    listing_id,
                    offer_id,
                    category_id,
                    policy_payment_id,
                    policy_return_id,
                    policy_fulfillment_id,
                    item_specifics,
                    merchant_location_key,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(sku) DO UPDATE SET
                    listing_id = excluded.listing_id,
                    offer_id = excluded.offer_id,
                    category_id = excluded.category_id,
                    policy_payment_id = excluded.policy_payment_id,
                    policy_return_id = excluded.policy_return_id,
                    policy_fulfillment_id = excluded.policy_fulfillment_id,
                    item_specifics = excluded.item_specifics,
                    merchant_location_key = excluded.merchant_location_key,
                    updated_at = excluded.updated_at
            ''', (
                sku,
                metadata.get('listing_id'),
                metadata.get('offer_id'),
                metadata.get('category_id'),
                metadata.get('policy_payment_id'),
                metadata.get('policy_return_id'),
                metadata.get('policy_fulfillment_id'),
                item_specifics_json,
                metadata.get('merchant_location_key', 'JP_LOCATION'),
                now,
                now
            ))

            return cursor.rowcount > 0

    def get_ebay_metadata(self, sku: str) -> Optional[Dict[str, Any]]:
        """
        eBay出品メタデータを取得

        Args:
            sku: 商品SKU

        Returns:
            dict or None: eBayメタデータ
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT *
                FROM ebay_listing_metadata
                WHERE sku = ?
            ''', (sku,))

            row = cursor.fetchone()
            if not row:
                return None

            metadata = dict(row)

            # item_specificsをパース
            if metadata.get('item_specifics'):
                try:
                    metadata['item_specifics'] = json.loads(metadata['item_specifics'])
                except:
                    metadata['item_specifics'] = None

            return metadata

    # ==================== Price History ====================

    def add_price_history_record(
        self,
        asin: str,
        platform: str,
        account_id: str,
        old_price: float,
        new_price: float,
        amazon_price_jpy: int,
        markup_ratio: float,
        strategy_used: str,
        change_reason: str = None
    ) -> bool:
        """
        価格変更履歴を記録

        Args:
            asin: 商品ASIN
            platform: プラットフォーム名
            account_id: アカウントID
            old_price: 変更前の価格
            new_price: 変更後の価格
            amazon_price_jpy: Amazon価格（円）
            markup_ratio: 適用されたマークアップ率
            strategy_used: 使用された価格戦略名
            change_reason: 変更理由

        Returns:
            bool: 成功時True
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO price_history (
                    asin,
                    platform,
                    account_id,
                    old_price,
                    new_price,
                    amazon_price_jpy,
                    markup_ratio,
                    strategy_used,
                    change_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                asin,
                platform,
                account_id,
                old_price,
                new_price,
                amazon_price_jpy,
                markup_ratio,
                strategy_used,
                change_reason
            ))

            return cursor.rowcount > 0

    def get_price_history(
        self,
        asin: str = None,
        platform: str = None,
        account_id: str = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        価格変更履歴を取得

        Args:
            asin: 商品ASIN（フィルター、省略時は全商品）
            platform: プラットフォーム名（フィルター）
            account_id: アカウントID（フィルター）
            limit: 取得件数上限

        Returns:
            List[dict]: 価格変更履歴のリスト
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            query = 'SELECT * FROM price_history WHERE 1=1'
            params = []

            if asin:
                query += ' AND asin = ?'
                params.append(asin)

            if platform:
                query += ' AND platform = ?'
                params.append(platform)

            if account_id:
                query += ' AND account_id = ?'
                params.append(account_id)

            query += ' ORDER BY changed_at DESC LIMIT ?'
            params.append(limit)

            cursor.execute(query, params)

            return [dict(row) for row in cursor.fetchall()]
