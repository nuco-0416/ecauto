# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
eBay出品状態同期スクリプト（CSVベース）

eBay Seller Hubからエクスポートしたactive listings reportを使用して
ローカルDBと同期する
"""

import sys
import logging
import csv
from pathlib import Path
from typing import Dict, Any

# Windows環境対応
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(project_root))

from inventory.core.master_db import MasterDB

# ロガー設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class EbayListingSyncFromCSV:
    """
    eBay出品状態同期クラス（CSVベース）
    """

    def __init__(self):
        """初期化"""
        logger.info("eBay出品状態同期処理（CSV）を初期化中...")

        self.master_db = MasterDB()

        # 統計情報
        self.stats = {
            'total_listings': 0,
            'updated': 0,
            'new': 0,
            'errors': 0,
        }

    def sync_from_csv(self, csv_path: str, account_id: str = 'ebay_account_1'):
        """
        CSVファイルから出品情報を同期

        Args:
            csv_path: eBay active listings report CSVファイルのパス
            account_id: eBayアカウントID
        """
        logger.info("")
        logger.info("┌" + "─" * 68 + "┐")
        logger.info(f"│ 【eBay出品同期（CSV）】ファイル: {Path(csv_path).name[:40]}" + " " * (68 - len(f" 【eBay出品同期（CSV）】ファイル: {Path(csv_path).name[:40]}") - 2) + "│")
        logger.info("└" + "─" * 68 + "┘")

        csv_file = Path(csv_path)
        if not csv_file.exists():
            logger.error(f"CSVファイルが見つかりません: {csv_path}")
            return

        # CSVを読み込んで同期
        logger.info(f"CSVファイルを読み込み中: {csv_file}")

        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)

                for row in reader:
                    self._sync_listing_from_csv_row(row, account_id)
                    self.stats['total_listings'] += 1

        except Exception as e:
            logger.error(f"CSVファイル読み込みエラー: {e}")
            self.stats['errors'] += 1

        # 統計表示
        self._print_summary()

    def _sync_listing_from_csv_row(self, row: Dict[str, str], account_id: str):
        """
        CSV行から1つの出品を同期

        Args:
            row: CSV行データ
            account_id: アカウントID
        """
        try:
            # CSV列名（eBay active listings reportの形式）
            item_number = row.get('Item number', '').strip()
            sku = row.get('Custom label (SKU)', '').strip()
            title = row.get('Title', '').strip()
            price_str = row.get('Current price', '').strip()
            quantity_str = row.get('Available quantity', '').strip()

            if not item_number:
                logger.warning(f"  [SKIP] Item numberが空です")
                return

            # 価格をfloatに変換
            try:
                price = float(price_str) if price_str else 0.0
            except ValueError:
                price = 0.0

            # 数量をintに変換
            try:
                quantity = int(quantity_str) if quantity_str else 0
            except ValueError:
                quantity = 0

            # ステータス判定（数量が0なら在庫切れ、それ以外は出品中）
            status = 'listed' if quantity > 0 else 'out_of_stock'

            # SKUからASINを抽出（SKU形式: s-{asin}-{timestamp}）
            asin = None
            if sku and sku.startswith('s-'):
                parts = sku.split('-')
                if len(parts) >= 2:
                    asin = parts[1]

            if not asin:
                # SKUがない場合、titleやitem_numberから推測するか、スキップ
                logger.warning(f"  [SKIP] SKUからASINを抽出できません: item={item_number}, sku={sku}")
                return

            # DBに既存レコードがあるかチェック
            with self.master_db.get_connection() as conn:
                cursor = conn.execute("""
                    SELECT id FROM listings
                    WHERE platform = 'ebay' AND account_id = ?
                    AND (sku = ? OR (asin = ? AND sku IS NULL))
                """, (account_id, sku if sku else None, asin))

                existing = cursor.fetchone()

                if existing:
                    # 更新
                    listing_id = existing[0]

                    conn.execute("""
                        UPDATE listings
                        SET status = ?,
                            selling_price = ?,
                            sku = ?,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (status, price, sku, listing_id))

                    # eBayメタデータも更新
                    if sku:
                        conn.execute("""
                            INSERT OR REPLACE INTO ebay_metadata (
                                sku, ebay_listing_id, updated_at
                            ) VALUES (?, ?, CURRENT_TIMESTAMP)
                        """, (sku, item_number))

                    logger.info(f"  [UPDATE] {sku or asin} -> {status} (${price})")
                    self.stats['updated'] += 1
                else:
                    # 新規作成
                    if not sku:
                        logger.warning(f"  [SKIP] 新規作成にはSKUが必要です: item={item_number}, asin={asin}")
                        return

                    conn.execute("""
                        INSERT INTO listings (
                            asin, sku, platform, account_id, status, selling_price
                        ) VALUES (?, ?, 'ebay', ?, ?, ?)
                    """, (asin, sku, account_id, status, price))

                    # eBayメタデータも作成
                    conn.execute("""
                        INSERT OR REPLACE INTO ebay_metadata (
                            sku, ebay_listing_id
                        ) VALUES (?, ?)
                    """, (sku, item_number))

                    logger.info(f"  [NEW] {sku} -> {status} (${price})")
                    self.stats['new'] += 1

        except Exception as e:
            logger.error(f"  [ERROR] レコード同期エラー: {e}")
            self.stats['errors'] += 1

    def _print_summary(self):
        """統計情報を表示"""
        logger.info("\n" + "=" * 70)
        logger.info("処理結果サマリー")
        logger.info("=" * 70)
        logger.info(f"処理した出品数: {self.stats['total_listings']}件")
        logger.info(f"  - 更新: {self.stats['updated']}件")
        logger.info(f"  - 新規: {self.stats['new']}件")
        logger.info(f"エラー: {self.stats['errors']}件")
        logger.info("=" * 70)
        logger.info("")


def main():
    """メイン処理"""
    import argparse

    parser = argparse.ArgumentParser(
        description='eBay出品状態をCSVからローカルDBと同期'
    )
    parser.add_argument(
        'csv_file',
        help='eBay active listings report CSVファイルのパス'
    )
    parser.add_argument(
        '--account',
        default='ebay_account_1',
        help='アカウントID（デフォルト: ebay_account_1）'
    )

    args = parser.parse_args()

    # 同期処理実行
    sync = EbayListingSyncFromCSV()
    sync.sync_from_csv(args.csv_file, args.account)

    # 終了コード
    if sync.stats['errors'] > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
