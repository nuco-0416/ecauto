"""
為替レート管理モジュール

yfinance APIを使用してリアルタイムで為替レートを取得します。
取得したレートは24時間キャッシュされます。

レガシープロジェクトから移植: ama-cari/ebay_pj/scripts/currency_manager.py
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional, Dict

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    logging.warning("yfinanceがインストールされていません。固定レートを使用します。")


class CurrencyManager:
    """為替レート管理クラス"""

    # デフォルト設定
    DEFAULT_CACHE_DURATION_SECONDS = 24 * 60 * 60  # 24時間
    DEFAULT_FALLBACK_RATE = 150.0  # フォールバックレート（1 USD = 150 JPY）

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        cache_duration_seconds: Optional[int] = None,
        fallback_rate: Optional[float] = None,
        use_cache: bool = True
    ):
        """
        初期化

        Args:
            cache_dir: キャッシュディレクトリ（Noneの場合はデフォルト）
            cache_duration_seconds: キャッシュ有効期間（秒）
            fallback_rate: フォールバックレート
            use_cache: キャッシュを使用するか
        """
        self.logger = logging.getLogger(self.__class__.__name__)

        # キャッシュディレクトリ
        if cache_dir is None:
            project_root = Path(__file__).resolve().parents[2]
            cache_dir = project_root / 'data' / 'currency_cache'

        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # 設定
        self.cache_duration_seconds = cache_duration_seconds or self.DEFAULT_CACHE_DURATION_SECONDS
        self.fallback_rate = fallback_rate or self.DEFAULT_FALLBACK_RATE
        self.use_cache = use_cache

    def get_usd_jpy_rate(self, force_refresh: bool = False) -> float:
        """
        USD/JPYの為替レートを取得

        Args:
            force_refresh: Trueの場合、キャッシュを無視して再取得

        Returns:
            為替レート（1 USD = X JPY）
        """
        # キャッシュファイルのパス
        cache_file = self.cache_dir / 'usd_jpy_rate.json'

        # キャッシュから取得
        if self.use_cache and not force_refresh:
            cached_rate = self._get_from_cache(cache_file)
            if cached_rate is not None:
                return cached_rate

        # APIから取得
        if YFINANCE_AVAILABLE:
            rate = self._fetch_from_api()
            if rate is not None:
                self._save_to_cache(cache_file, rate)
                return rate

        # フォールバックレートを使用
        self.logger.warning(
            f"為替レートの取得に失敗しました。固定レート {self.fallback_rate} を使用します。"
        )
        return self.fallback_rate

    def get_exchange_rate(
        self,
        from_currency: str,
        to_currency: str,
        force_refresh: bool = False
    ) -> float:
        """
        任意の通貨ペアの為替レートを取得

        Args:
            from_currency: 元の通貨（例: "JPY"）
            to_currency: 変換先の通貨（例: "USD"）
            force_refresh: Trueの場合、キャッシュを無視して再取得

        Returns:
            為替レート

        Raises:
            ValueError: サポートされていない通貨ペア
        """
        # 現在はJPY⇔USDのみ対応
        if from_currency == "JPY" and to_currency == "USD":
            usd_jpy_rate = self.get_usd_jpy_rate(force_refresh)
            return 1.0 / usd_jpy_rate

        elif from_currency == "USD" and to_currency == "JPY":
            return self.get_usd_jpy_rate(force_refresh)

        elif from_currency == to_currency:
            return 1.0

        else:
            raise ValueError(
                f"サポートされていない通貨ペア: {from_currency} → {to_currency}"
            )

    def convert(
        self,
        amount: float,
        from_currency: str,
        to_currency: str,
        force_refresh: bool = False
    ) -> float:
        """
        通貨換算

        Args:
            amount: 金額
            from_currency: 元の通貨
            to_currency: 変換先の通貨
            force_refresh: Trueの場合、キャッシュを無視して再取得

        Returns:
            換算後の金額
        """
        rate = self.get_exchange_rate(from_currency, to_currency, force_refresh)
        return amount * rate

    def _get_from_cache(self, cache_file: Path) -> Optional[float]:
        """
        キャッシュから為替レートを取得

        Args:
            cache_file: キャッシュファイルのパス

        Returns:
            為替レート（キャッシュがない、または期限切れの場合はNone）
        """
        if not cache_file.exists():
            return None

        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)

            last_updated = cache_data.get('timestamp', 0)
            current_time = time.time()

            # キャッシュが有効期限内か確認
            if current_time < last_updated + self.cache_duration_seconds:
                rate = cache_data.get('rate')
                self.logger.info(
                    f"キャッシュから為替レートを取得: 1 USD = {rate:.2f} JPY "
                    f"(有効期限まで残り {int((last_updated + self.cache_duration_seconds - current_time) / 3600)} 時間)"
                )
                return rate

        except (json.JSONDecodeError, KeyError) as e:
            self.logger.warning(f"キャッシュファイルが破損しています: {e}")

        return None

    def _fetch_from_api(self) -> Optional[float]:
        """
        yfinance APIから為替レートを取得

        Returns:
            為替レート（取得失敗時はNone）
        """
        self.logger.info("yfinance APIから最新の為替レートを取得中...")

        try:
            ticker = yf.Ticker("USDJPY=X")
            current_rate = ticker.info.get('regularMarketPrice')

            if current_rate is None:
                raise ValueError("yfinanceからレートが取得できませんでした。")

            self.logger.info(f"新しい為替レートを取得: 1 USD = {current_rate:.2f} JPY")
            return current_rate

        except Exception as e:
            self.logger.error(f"為替レートの取得に失敗: {e}")
            return None

    def _save_to_cache(self, cache_file: Path, rate: float) -> None:
        """
        為替レートをキャッシュに保存

        Args:
            cache_file: キャッシュファイルのパス
            rate: 為替レート
        """
        try:
            cache_data = {
                'rate': rate,
                'timestamp': time.time()
            }

            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2)

            self.logger.info(f"為替レートをキャッシュに保存しました")

        except Exception as e:
            self.logger.error(f"キャッシュの保存に失敗: {e}")

    def get_cache_info(self) -> Dict:
        """
        キャッシュ情報を取得（デバッグ用）

        Returns:
            キャッシュ情報の辞書
        """
        cache_file = self.cache_dir / 'usd_jpy_rate.json'

        if not cache_file.exists():
            return {
                'exists': False,
                'rate': None,
                'timestamp': None,
                'age_hours': None,
            }

        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)

            timestamp = cache_data.get('timestamp', 0)
            age_hours = (time.time() - timestamp) / 3600

            return {
                'exists': True,
                'rate': cache_data.get('rate'),
                'timestamp': timestamp,
                'age_hours': age_hours,
                'valid': age_hours < (self.cache_duration_seconds / 3600),
            }

        except Exception as e:
            self.logger.error(f"キャッシュ情報の取得に失敗: {e}")
            return {'exists': True, 'error': str(e)}


if __name__ == '__main__':
    # テスト実行
    import logging
    logging.basicConfig(level=logging.INFO)

    manager = CurrencyManager()

    # USD/JPY レート取得
    rate = manager.get_usd_jpy_rate()
    print(f"取得したレート: 1 USD = {rate:.2f} JPY")

    # 通貨換算テスト
    jpy_amount = 15000
    usd_amount = manager.convert(jpy_amount, "JPY", "USD")
    print(f"{jpy_amount:,} JPY = ${usd_amount:.2f} USD")

    # キャッシュ情報取得
    cache_info = manager.get_cache_info()
    print(f"キャッシュ情報: {cache_info}")
