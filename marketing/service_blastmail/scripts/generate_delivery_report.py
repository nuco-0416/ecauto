#!/usr/bin/env python
"""
メルマガ配信レポート作成スクリプト（Blastmail + Google Analytics連携）

Blastmail APIから配信データを取得し、CSVレポートを生成する。
オプションでGoogle Analytics 4のデータ（PV、CV、売上等）を統合可能。

- アカウントごとに1CSVファイル
- 実行ごとに新規配信を追記
- 配信から3日以内のデータは更新（開封数等が変動するため）

使用例:
    # 全アカウントのレポートを生成
    venv/bin/python marketing/service_blastmail/scripts/generate_delivery_report.py --all-accounts

    # 特定アカウントのレポートを生成
    venv/bin/python marketing/service_blastmail/scripts/generate_delivery_report.py \
        --account blastmail_account_1

    # Google Analytics連携を有効にして生成
    venv/bin/python marketing/service_blastmail/scripts/generate_delivery_report.py \
        --account blastmail_account_1 --with-ga

    # ドライラン（実際の保存なし）
    venv/bin/python marketing/service_blastmail/scripts/generate_delivery_report.py \
        --account blastmail_account_1 --dry-run
"""

import argparse
import csv
import logging
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from marketing.service_blastmail.core.api_client import BlastmailAPIClient
from marketing.service_blastmail.accounts.manager import AccountManager

# 定数
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
UPDATE_DAYS = 3  # 配信からN日以内のデータは更新対象

# Google Analytics設定
GA_CREDENTIALS_PATH = Path(__file__).resolve().parent.parent.parent / "service_google_analytics" / "hadient-customers-562d9269b575.json"
GA_PROPERTY_ID = "442523274"

# Shopify設定
SHOPIFY_CONFIG_PATH = PROJECT_ROOT / "platforms" / "shopify" / "accounts" / "store1.json"

# CSVカラム定義（基本）
CSV_COLUMNS_BASE = [
    'message_id',        # メッセージID
    'delivery_date',     # 配信日 (YYYY-MM-DD)
    'delivery_time',     # 配信時間 (HH:MM:SS)
    'subject',           # メルマガタイトル
    'total',             # 配信数
    'success',           # 成功数
    'failure',           # エラー数
    'open_count',        # 開封数
    'error_rate',        # エラー率 (%)
    'open_rate',         # 開封率 (%)
    'destination_urls',  # 遷移先URL（複数の場合はセミコロン区切り）
    'updated_at',        # レコード更新日時
]

# Google Analytics用の追加カラム
CSV_COLUMNS_GA = [
    'ga_pageviews',      # GA: その日のPV数
    'ga_sessions',       # GA: その日のセッション数
    'ga_purchases',      # GA: その日の購入数
    'ga_revenue',        # GA: その日の売上
    'ga_mail_sessions',  # GA: メルマガ経由セッション数
]

# Shopify用の追加カラム
CSV_COLUMNS_SHOPIFY = [
    'shopify_orders',    # Shopify: その日の注文数
    'shopify_revenue',   # Shopify: その日の売上
    'shopify_products',  # Shopify: 販売商品名（セミコロン区切り）
]

# 動的にカラムを決定（GA連携の有無で変更）
CSV_COLUMNS = CSV_COLUMNS_BASE.copy()


def get_csv_columns(with_ga: bool = False, with_shopify: bool = False) -> List[str]:
    """連携オプションに応じたCSVカラムを返す"""
    columns = CSV_COLUMNS_BASE.copy()
    if with_ga:
        columns.extend(CSV_COLUMNS_GA)
    if with_shopify:
        columns.extend(CSV_COLUMNS_SHOPIFY)
    return columns


def setup_logging(debug: bool = False) -> logging.Logger:
    """ロギング設定"""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    return logging.getLogger(__name__)


class GoogleAnalyticsClient:
    """
    Google Analytics 4 データ取得クライアント

    日付別のPV、セッション、購入数、売上などを取得する
    """

    def __init__(self, credentials_path: Path, property_id: str):
        """
        Args:
            credentials_path: サービスアカウントキーのパス
            property_id: GA4プロパティID
        """
        import os
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = str(credentials_path)

        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        self.client = BetaAnalyticsDataClient()
        self.property_id = property_id
        self._cache: Dict[str, Dict[str, Any]] = {}

    def fetch_daily_metrics(self, start_date: str, end_date: str) -> Dict[str, Dict[str, Any]]:
        """
        日付別のメトリクスを取得

        Args:
            start_date: 開始日（YYYY-MM-DD または "30daysAgo"）
            end_date: 終了日（YYYY-MM-DD または "today"）

        Returns:
            dict: 日付をキーとしたメトリクス辞書
                {
                    "2025-12-09": {
                        "pageviews": 127,
                        "sessions": 93,
                        "purchases": 1,
                        "revenue": 3605.0
                    },
                    ...
                }
        """
        from google.analytics.data_v1beta.types import (
            DateRange, Dimension, Metric, RunReportRequest
        )

        logger = logging.getLogger(__name__)
        results = {}

        # 基本メトリクス取得
        logger.debug(f"GA4: 日付別メトリクスを取得中 ({start_date} 〜 {end_date})")
        request = RunReportRequest(
            property=f"properties/{self.property_id}",
            dimensions=[Dimension(name="date")],
            metrics=[
                Metric(name="screenPageViews"),
                Metric(name="sessions"),
                Metric(name="ecommercePurchases"),
                Metric(name="purchaseRevenue"),
            ],
            date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
        )

        try:
            response = self.client.run_report(request)
            for row in response.rows:
                date_raw = row.dimension_values[0].value
                date_key = f"{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:8]}"
                results[date_key] = {
                    'pageviews': int(row.metric_values[0].value),
                    'sessions': int(row.metric_values[1].value),
                    'purchases': int(row.metric_values[2].value),
                    'revenue': float(row.metric_values[3].value),
                    'mail_sessions': 0,  # 後で更新
                }
        except Exception as e:
            logger.warning(f"GA4 基本メトリクス取得エラー: {e}")

        # メルマガ経由セッション数を取得
        logger.debug("GA4: メルマガ経由セッションを取得中")
        try:
            request_mail = RunReportRequest(
                property=f"properties/{self.property_id}",
                dimensions=[Dimension(name="date")],
                metrics=[Metric(name="sessions")],
                date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
                dimension_filter={
                    "and_group": {
                        "expressions": [
                            {
                                "filter": {
                                    "field_name": "sessionSource",
                                    "string_filter": {"value": "mailmagazine"}
                                }
                            }
                        ]
                    }
                },
            )
            response_mail = self.client.run_report(request_mail)
            for row in response_mail.rows:
                date_raw = row.dimension_values[0].value
                date_key = f"{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:8]}"
                if date_key in results:
                    results[date_key]['mail_sessions'] = int(row.metric_values[0].value)
        except Exception as e:
            logger.warning(f"GA4 メルマガセッション取得エラー: {e}")

        self._cache = results
        logger.info(f"GA4: {len(results)} 日分のデータを取得")
        return results

    def get_metrics_for_date(self, date: str) -> Dict[str, Any]:
        """
        特定日のメトリクスを取得（キャッシュから）

        Args:
            date: 日付（YYYY-MM-DD）

        Returns:
            dict: メトリクス辞書（データがない場合はデフォルト値）
        """
        return self._cache.get(date, {
            'pageviews': 0,
            'sessions': 0,
            'purchases': 0,
            'revenue': 0.0,
            'mail_sessions': 0,
        })


class ShopifyClient:
    """
    Shopify API データ取得クライアント

    日付別の注文数、売上、販売商品を取得する
    """

    def __init__(self, config_path: Path):
        """
        Args:
            config_path: Shopify設定JSONファイルのパス
        """
        import json
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        self.shop_domain = config['myshopify_domain']
        self.access_token = config['access_token']
        self.shop_name = config.get('name', '')
        self._cache: Dict[str, Dict[str, Any]] = {}

    def fetch_daily_orders(self, days: int = 90) -> Dict[str, Dict[str, Any]]:
        """
        日付別の注文データを取得

        Args:
            days: 取得する日数

        Returns:
            dict: 日付をキーとした注文データ辞書
        """
        import requests
        from datetime import timedelta

        logger = logging.getLogger(__name__)
        results = {}

        since_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%dT00:00:00+09:00')

        headers = {
            "X-Shopify-Access-Token": self.access_token,
            "Content-Type": "application/json"
        }

        orders_url = f"https://{self.shop_domain}/admin/api/2024-01/orders.json"
        params = {
            "created_at_min": since_date,
            "status": "any",
            "limit": 250
        }

        logger.debug(f"Shopify: 注文データを取得中 (過去{days}日)")

        try:
            response = requests.get(orders_url, headers=headers, params=params, timeout=60)
            if response.status_code != 200:
                logger.warning(f"Shopify API エラー: {response.status_code}")
                return results

            orders = response.json().get('orders', [])

            for order in orders:
                # 返金済み注文は除外
                if order.get('financial_status') == 'refunded':
                    continue

                created_at = order['created_at'][:10]  # YYYY-MM-DD

                if created_at not in results:
                    results[created_at] = {
                        'orders': 0,
                        'revenue': 0.0,
                        'products': []
                    }

                results[created_at]['orders'] += 1
                results[created_at]['revenue'] += float(order.get('total_price', 0))

                # 商品情報
                for item in order.get('line_items', []):
                    product_name = item.get('title', '')[:30]
                    if product_name and product_name not in results[created_at]['products']:
                        results[created_at]['products'].append(product_name)

            logger.info(f"Shopify: {len(results)} 日分のデータを取得 (注文 {len(orders)} 件)")

        except Exception as e:
            logger.warning(f"Shopify データ取得エラー: {e}")

        self._cache = results
        return results

    def get_orders_for_date(self, date: str) -> Dict[str, Any]:
        """
        特定日の注文データを取得（キャッシュから）

        Args:
            date: 日付（YYYY-MM-DD）

        Returns:
            dict: 注文データ辞書（データがない場合はデフォルト値）
        """
        return self._cache.get(date, {
            'orders': 0,
            'revenue': 0.0,
            'products': [],
        })


def extract_urls_from_content(text_part: str, html_part: str) -> List[str]:
    """
    メール本文からURLを抽出

    Args:
        text_part: テキストパート
        html_part: HTMLパート

    Returns:
        list: 抽出されたURLリスト（重複排除済み）
    """
    urls = set()

    # URLパターン（http/https）
    url_pattern = r'https?://[^\s<>"\')\]]+[^\s<>"\')\].,;!?]'

    # テキストパートから抽出
    if text_part:
        found = re.findall(url_pattern, text_part)
        urls.update(found)

    # HTMLパートから抽出（href属性）
    if html_part:
        href_pattern = r'href=["\']?(https?://[^"\'\s>]+)'
        found = re.findall(href_pattern, html_part, re.IGNORECASE)
        urls.update(found)

    # フィルタリング: 画像やスタイルシートなどを除外
    filtered_urls = []
    exclude_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.css', '.js', '.ico', '.svg'}
    exclude_domains = {'blastmail.jp', 'bme.jp'}  # Blastmail関連のURLを除外

    for url in urls:
        try:
            parsed = urlparse(url)
            path_lower = parsed.path.lower()
            domain = parsed.netloc.lower()

            # 除外条件チェック
            if any(path_lower.endswith(ext) for ext in exclude_extensions):
                continue
            if any(excl in domain for excl in exclude_domains):
                continue

            filtered_urls.append(url)
        except Exception:
            continue

    return sorted(filtered_urls)


def count_opens_from_log(open_log_csv: str) -> int:
    """
    開封ログCSVから開封数をカウント

    Blastmail開封ログCSV形式:
    "送信/受信","エラーカウント","開封日","名前","E-Mail"

    Args:
        open_log_csv: 開封ログのCSV文字列（Shift-JISエンコード済み）

    Returns:
        int: 開封数（ユニーク開封者数）
    """
    if not open_log_csv or open_log_csv.strip() == '':
        return 0

    lines = open_log_csv.strip().split('\n')
    # ヘッダー行を除いた行数
    if len(lines) <= 1:
        return 0

    # CSVパース（ヘッダー行あり想定）
    try:
        reader = csv.reader(lines)
        header = next(reader, None)
        if not header:
            return 0

        # メールアドレスは最後の列（インデックス4: E-Mail）
        email_col_idx = len(header) - 1 if len(header) > 0 else 4
        email_addresses = set()

        for row in reader:
            if row and len(row) > email_col_idx:
                email = row[email_col_idx].strip()
                if email and '@' in email:
                    email_addresses.add(email.lower())

        return len(email_addresses)
    except Exception:
        # パースエラー時は行数ベースでカウント（ヘッダー除く）
        return len(lines) - 1


def parse_delivery_datetime(date_str: str) -> tuple:
    """
    配信日時文字列をパースして日付と時間に分割

    Args:
        date_str: 日時文字列（様々な形式に対応）
            - 20251209T19:35:00 (Blastmail形式)
            - 2025-12-09T19:35:00 (ISO 8601)
            - 2025-12-09 19:35:00

    Returns:
        tuple: (date_str, time_str) 形式の文字列タプル
    """
    if not date_str:
        return '', ''

    try:
        # Blastmail形式: 20251209T19:35:00
        if len(date_str) >= 15 and 'T' in date_str and '-' not in date_str[:8]:
            # 日付部分: 20251209 -> 2025-12-09
            date_part = date_str[:8]
            time_part = date_str[9:] if len(date_str) > 9 else ''

            year = date_part[:4]
            month = date_part[4:6]
            day = date_part[6:8]
            formatted_date = f"{year}-{month}-{day}"

            return formatted_date, time_part

        # 標準的な形式に対応
        for fmt in ['%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y/%m/%d %H:%M:%S']:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.strftime('%Y-%m-%d'), dt.strftime('%H:%M:%S')
            except ValueError:
                continue

        # パースできない場合はそのまま返す
        return date_str, ''
    except Exception:
        return date_str, ''


def load_existing_report(csv_path: Path) -> Dict[str, Dict[str, Any]]:
    """
    既存のCSVレポートを読み込み

    Args:
        csv_path: CSVファイルパス

    Returns:
        dict: message_idをキーとしたデータ辞書
    """
    data = {}
    if not csv_path.exists():
        return data

    try:
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                message_id = row.get('message_id')
                if message_id:
                    data[message_id] = row
    except Exception as e:
        logging.warning(f"既存レポートの読み込みに失敗: {e}")

    return data


def save_report(
    csv_path: Path,
    data: Dict[str, Dict[str, Any]],
    dry_run: bool = False,
    columns: Optional[List[str]] = None
):
    """
    レポートをCSVに保存

    Args:
        csv_path: 保存先パス
        data: 保存データ（message_idをキーとした辞書）
        dry_run: Trueの場合は保存しない
        columns: CSVカラムリスト（省略時はCSV_COLUMNS_BASE）
    """
    if dry_run:
        logging.info(f"[DRY RUN] 保存スキップ: {csv_path}")
        return

    if columns is None:
        columns = CSV_COLUMNS_BASE

    # ディレクトリ作成
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    # 配信日時でソート
    sorted_data = sorted(
        data.values(),
        key=lambda x: (x.get('delivery_date', ''), x.get('delivery_time', '')),
        reverse=True  # 新しい順
    )

    with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(sorted_data)

    logging.info(f"レポート保存完了: {csv_path} ({len(sorted_data)} 件)")


def generate_report_for_account(
    client: BlastmailAPIClient,
    account_id: str,
    begin_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    dry_run: bool = False,
    logger: logging.Logger = None,
    ga_client: Optional['GoogleAnalyticsClient'] = None,
    shopify_client: Optional['ShopifyClient'] = None
) -> Dict[str, Any]:
    """
    単一アカウントのレポートを生成

    Args:
        client: BlastmailAPIClient
        account_id: アカウントID
        begin_date: 取得開始日
        end_date: 取得終了日
        dry_run: ドライランモード
        logger: ロガー
        ga_client: GoogleAnalyticsClient（GA連携時）
        shopify_client: ShopifyClient（Shopify連携時）

    Returns:
        dict: 処理結果の統計情報
    """
    logger = logger or logging.getLogger(__name__)
    stats = {'new': 0, 'updated': 0, 'skipped': 0, 'errors': 0}
    with_ga = ga_client is not None
    with_shopify = shopify_client is not None

    # 出力ファイルパス
    csv_path = DATA_DIR / f"delivery_report_{account_id}.csv"

    # 既存データ読み込み
    existing_data = load_existing_report(csv_path)
    logger.info(f"既存レコード数: {len(existing_data)}")

    # 更新対象の日付閾値（N日前）
    update_threshold = datetime.now() - timedelta(days=UPDATE_DAYS)

    # 配信履歴を取得
    logger.info("配信履歴を取得中...")
    history_items = client.get_all_delivery_history(
        begin_date=begin_date,
        end_date=end_date
    )
    logger.info(f"取得した配信履歴: {len(history_items)} 件")

    # 各配信のデータを処理
    for item in history_items:
        message_id = str(item.get('messageID', ''))
        if not message_id:
            continue

        # 配信日時パース
        date_str = item.get('date', '')
        delivery_date, delivery_time = parse_delivery_datetime(date_str)

        # 更新判定
        is_existing = message_id in existing_data
        should_update = False

        if is_existing:
            # 既存レコード: N日以内なら更新
            try:
                item_date = datetime.strptime(delivery_date, '%Y-%m-%d')
                if item_date >= update_threshold:
                    should_update = True
                    logger.debug(f"更新対象: {message_id} (配信日: {delivery_date})")
                else:
                    stats['skipped'] += 1
                    continue
            except ValueError:
                stats['skipped'] += 1
                continue
        else:
            should_update = True  # 新規は常に追加

        try:
            # メッセージ詳細を取得（遷移先URL抽出用）
            detail = client.get_message_detail(message_id)
            text_part = detail.get('textPart', '')
            html_part = detail.get('htmlPart', '')
            urls = extract_urls_from_content(text_part, html_part)

            # 開封ログを取得
            open_log = client.export_open_log(message_id)
            open_count = count_opens_from_log(open_log)

            # 数値データ
            total = int(item.get('total', 0))
            success = int(item.get('success', 0))
            failure = int(item.get('failure', 0))

            # 計算項目
            error_rate = round((failure / total * 100), 2) if total > 0 else 0
            open_rate = round((open_count / success * 100), 2) if success > 0 else 0

            # レコード作成
            record = {
                'message_id': message_id,
                'delivery_date': delivery_date,
                'delivery_time': delivery_time,
                'subject': item.get('subject', ''),
                'total': total,
                'success': success,
                'failure': failure,
                'open_count': open_count,
                'error_rate': error_rate,
                'open_rate': open_rate,
                'destination_urls': ';'.join(urls),
                'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            }

            # GA4データを追加（有効時）
            if with_ga and ga_client:
                ga_metrics = ga_client.get_metrics_for_date(delivery_date)
                record['ga_pageviews'] = ga_metrics['pageviews']
                record['ga_sessions'] = ga_metrics['sessions']
                record['ga_purchases'] = ga_metrics['purchases']
                record['ga_revenue'] = round(ga_metrics['revenue'], 2)
                record['ga_mail_sessions'] = ga_metrics['mail_sessions']

            # Shopifyデータを追加（有効時）
            if with_shopify and shopify_client:
                shopify_data = shopify_client.get_orders_for_date(delivery_date)
                record['shopify_orders'] = shopify_data['orders']
                record['shopify_revenue'] = round(shopify_data['revenue'], 2)
                record['shopify_products'] = ';'.join(shopify_data['products'])

            existing_data[message_id] = record

            if is_existing:
                stats['updated'] += 1
                logger.debug(f"更新: {message_id} - {item.get('subject', '')[:30]}")
            else:
                stats['new'] += 1
                logger.debug(f"新規: {message_id} - {item.get('subject', '')[:30]}")

        except Exception as e:
            stats['errors'] += 1
            logger.warning(f"メッセージ {message_id} の処理でエラー: {e}")

    # 保存（GA連携有無でカラムを切り替え）
    columns = get_csv_columns(with_ga=with_ga, with_shopify=with_shopify)
    save_report(csv_path, existing_data, dry_run=dry_run, columns=columns)

    return stats


def main():
    parser = argparse.ArgumentParser(
        description='メルマガ配信レポート作成（Blastmail + Google Analytics連携）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  %(prog)s --all-accounts                    # 全アカウントのレポート生成
  %(prog)s --account blastmail_account_1     # 特定アカウント
  %(prog)s --account blastmail_account_1 --with-ga  # GA連携有効
  %(prog)s --dry-run                         # 保存せずに確認
        """
    )

    # アカウント選択
    account_group = parser.add_argument_group('アカウント選択')
    account_group.add_argument(
        '--account', '-a',
        type=str,
        help='アカウントID（例: blastmail_account_1）'
    )
    account_group.add_argument(
        '--all-accounts',
        action='store_true',
        help='全アクティブアカウントを処理'
    )
    account_group.add_argument(
        '--list-accounts',
        action='store_true',
        help='登録アカウント一覧を表示'
    )

    # 日付フィルタ
    parser.add_argument(
        '--begin-date',
        type=str,
        help='取得開始日（YYYY-MM-DD）'
    )
    parser.add_argument(
        '--end-date',
        type=str,
        help='取得終了日（YYYY-MM-DD）'
    )

    # Google Analytics連携
    parser.add_argument(
        '--with-ga',
        action='store_true',
        help='Google Analytics連携を有効化（日付別PV/CV/売上を追加）'
    )

    # Shopify連携
    parser.add_argument(
        '--with-shopify',
        action='store_true',
        help='Shopify連携を有効化（日付別注文数/売上/商品を追加）'
    )

    # 実行オプション
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='ドライラン（保存しない）'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='デバッグモード'
    )

    args = parser.parse_args()
    logger = setup_logging(args.debug)

    try:
        # AccountManager初期化
        account_manager = AccountManager()

        # アカウント一覧表示
        if args.list_accounts:
            account_manager.list_accounts()
            return 0

        # 日付パース
        begin_date = None
        end_date = None
        if args.begin_date:
            begin_date = datetime.strptime(args.begin_date, '%Y-%m-%d')
        if args.end_date:
            end_date = datetime.strptime(args.end_date, '%Y-%m-%d')

        # 処理対象アカウント決定
        if args.all_accounts:
            accounts = account_manager.get_active_accounts()
        elif args.account:
            accounts = [{'id': args.account}]
        else:
            # デフォルト: 最初のアクティブアカウント
            active = account_manager.get_active_accounts()
            if active:
                accounts = [active[0]]
            else:
                logger.error("有効なアカウントが見つかりません")
                return 1

        if not accounts:
            logger.error("処理対象のアカウントがありません")
            return 1

        # Google Analytics クライアント初期化（オプション）
        ga_client = None
        if args.with_ga:
            if GA_CREDENTIALS_PATH.exists():
                logger.info("Google Analytics連携を初期化中...")
                try:
                    ga_client = GoogleAnalyticsClient(GA_CREDENTIALS_PATH, GA_PROPERTY_ID)
                    # 90日分のデータを事前取得してキャッシュ
                    ga_client.fetch_daily_metrics("90daysAgo", "today")
                except Exception as e:
                    logger.warning(f"GA4初期化エラー（GA連携なしで続行）: {e}")
                    ga_client = None
            else:
                logger.warning(f"GA認証ファイルが見つかりません: {GA_CREDENTIALS_PATH}")
                logger.warning("GA連携なしで続行します")

        # Shopify クライアント初期化（オプション）
        shopify_client = None
        if args.with_shopify:
            if SHOPIFY_CONFIG_PATH.exists():
                logger.info("Shopify連携を初期化中...")
                try:
                    shopify_client = ShopifyClient(SHOPIFY_CONFIG_PATH)
                    # 90日分の注文データを事前取得してキャッシュ
                    shopify_client.fetch_daily_orders(days=90)
                except Exception as e:
                    logger.warning(f"Shopify初期化エラー（Shopify連携なしで続行）: {e}")
                    shopify_client = None
            else:
                logger.warning(f"Shopify設定ファイルが見つかりません: {SHOPIFY_CONFIG_PATH}")
                logger.warning("Shopify連携なしで続行します")

        # 各アカウントを処理
        total_stats = {'new': 0, 'updated': 0, 'skipped': 0, 'errors': 0}

        for account in accounts:
            account_id = account['id']
            logger.info(f"\n{'='*60}")
            logger.info(f"アカウント: {account_id}")
            if ga_client:
                logger.info("Google Analytics連携: 有効")
            if shopify_client:
                logger.info("Shopify連携: 有効")
            logger.info(f"{'='*60}")

            try:
                client = account_manager.create_client(account_id)
                stats = generate_report_for_account(
                    client=client,
                    account_id=account_id,
                    begin_date=begin_date,
                    end_date=end_date,
                    dry_run=args.dry_run,
                    logger=logger,
                    ga_client=ga_client,
                    shopify_client=shopify_client
                )

                # 統計表示
                logger.info(f"処理結果: 新規={stats['new']}, 更新={stats['updated']}, "
                           f"スキップ={stats['skipped']}, エラー={stats['errors']}")

                for key in total_stats:
                    total_stats[key] += stats[key]

            except Exception as e:
                logger.error(f"アカウント {account_id} の処理でエラー: {e}")
                if args.debug:
                    raise

        # 全体統計
        if len(accounts) > 1:
            logger.info(f"\n{'='*60}")
            logger.info("全体統計")
            logger.info(f"{'='*60}")
            logger.info(f"新規: {total_stats['new']}, 更新: {total_stats['updated']}, "
                       f"スキップ: {total_stats['skipped']}, エラー: {total_stats['errors']}")

        return 0

    except Exception as e:
        logger.error(f"エラーが発生しました: {e}", exc_info=args.debug)
        return 1


if __name__ == '__main__':
    sys.exit(main())
