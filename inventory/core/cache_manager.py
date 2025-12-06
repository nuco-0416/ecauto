"""
Amazon Product Cache Manager

Amazon SP-APIから取得した商品情報をローカルにキャッシュして
APIレート制限を回避する
"""

import json
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List


class AmazonProductCache:
    """
    Amazon商品情報のキャッシュ管理クラス

    各ASINごとにJSONファイルとしてキャッシュし、
    有効期限を管理する
    """

    def __init__(self, cache_dir: str = None, cache_ttl: int = 86400):
        """
        Args:
            cache_dir: キャッシュディレクトリ（デフォルト: inventory/data/cache/amazon_products）
            cache_ttl: キャッシュ有効期限（秒）デフォルト: 24時間
        """
        if cache_dir is None:
            base_dir = Path(__file__).resolve().parent.parent
            cache_dir = base_dir / 'data' / 'cache' / 'amazon_products'

        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.cache_ttl = cache_ttl
        self.metadata_file = self.cache_dir.parent / 'metadata.json'

        # メタデータ初期化
        self._load_metadata()

    def _load_metadata(self):
        """メタデータをロード"""
        if self.metadata_file.exists():
            with open(self.metadata_file, 'r', encoding='utf-8') as f:
                self.metadata = json.load(f)
        else:
            self.metadata = {
                'total_cached': 0,
                'last_bulk_update': None,
                'cache_hits': 0,
                'cache_misses': 0
            }
            self._save_metadata()

    def _save_metadata(self):
        """メタデータを保存"""
        with open(self.metadata_file, 'w', encoding='utf-8') as f:
            json.dump(self.metadata, f, ensure_ascii=False, indent=2)

    def get_product(self, asin: str) -> Optional[Dict[str, Any]]:
        """
        キャッシュから商品情報を取得

        Args:
            asin: Amazon ASIN

        Returns:
            dict or None: 商品情報、期限切れまたは存在しない場合はNone
        """
        cache_file = self.cache_dir / f'{asin}.json'

        if not cache_file.exists():
            self.metadata['cache_misses'] += 1
            self._save_metadata()
            return None

        # キャッシュの有効期限チェック
        mtime = cache_file.stat().st_mtime
        age = time.time() - mtime

        if age > self.cache_ttl:
            # 期限切れ
            self.metadata['cache_misses'] += 1
            self._save_metadata()
            return None

        # キャッシュヒット
        with open(cache_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self.metadata['cache_hits'] += 1
        self._save_metadata()

        return data

    def set_product(self, asin: str, data: Dict[str, Any],
                    update_types: List[str] = None) -> bool:
        """
        商品情報をキャッシュに保存（部分更新対応）

        Args:
            asin: Amazon ASIN
            data: 商品情報の辞書
            update_types: 更新タイプのリスト ['price', 'stock', 'basic_info', 'all']
                         Noneまたは['all']の場合は全データを更新

        Returns:
            bool: 成功時True
        """
        if update_types is None:
            update_types = ['all']

        cache_file = self.cache_dir / f'{asin}.json'
        now = datetime.now().isoformat()

        # 部分更新の場合は既存データを読み込み
        existing_data = {}
        if 'all' not in update_types and cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
            except Exception as e:
                print(f"Warning: Failed to read existing cache for {asin}: {e}")
                # 読み込み失敗時は新規作成として扱う
                existing_data = {}

        # データをマージ（新しいデータで上書き）
        merged_data = {**existing_data, **data}

        # 更新日時を設定
        if 'price' in update_types or 'all' in update_types:
            merged_data['price_updated_at'] = now
        if 'stock' in update_types or 'all' in update_types:
            merged_data['stock_updated_at'] = now
        if 'basic_info' in update_types or 'all' in update_types:
            merged_data['basic_info_updated_at'] = now

        # 全体の保存時刻は常に更新
        merged_data['cached_at'] = now

        try:
            # ファイルが新規作成かどうかを先に確認
            is_new_file = not cache_file.exists()

            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(merged_data, f, ensure_ascii=False, indent=2)

            # メタデータ更新（新規作成時のみ）
            if is_new_file:
                self.metadata['total_cached'] += 1
                self._save_metadata()

            return True

        except Exception as e:
            print(f"Error caching {asin}: {e}")
            return False

    def delete_product(self, asin: str) -> bool:
        """
        キャッシュから商品情報を削除

        Args:
            asin: Amazon ASIN

        Returns:
            bool: 成功時True
        """
        cache_file = self.cache_dir / f'{asin}.json'

        if cache_file.exists():
            cache_file.unlink()
            self.metadata['total_cached'] -= 1
            self._save_metadata()
            return True

        return False

    def bulk_update(self, asin_list: List[str], sp_api_client,
                   batch_size: int = 50, sleep_time: float = 1.5) -> Dict[str, Any]:
        """
        ASINリストを一括でキャッシュ更新

        Args:
            asin_list: 更新するASINのリスト
            sp_api_client: Amazon SP-APIクライアント（get_product_price メソッドを持つ）
            batch_size: バッチサイズ（進捗表示用）
            sleep_time: API呼び出し間隔（秒）SP-APIレート制限対策

        Returns:
            dict: 実行結果のサマリー
        """
        total = len(asin_list)
        success_count = 0
        error_count = 0
        errors = []

        print(f"=== Amazon商品情報キャッシュ更新開始 ===")
        print(f"対象: {total}件")
        print(f"API呼び出し間隔: {sleep_time}秒")
        print()

        for i, asin in enumerate(asin_list, 1):
            try:
                # SP-APIで商品情報取得
                product_data = sp_api_client.get_product_price(asin)

                if product_data:
                    # キャッシュに保存
                    self.set_product(asin, product_data)
                    success_count += 1

                    if i % batch_size == 0:
                        print(f"[{i}/{total}] {asin} - 成功 (進捗: {i/total*100:.1f}%)")
                else:
                    error_count += 1
                    errors.append({'asin': asin, 'error': 'No data returned'})
                    print(f"[{i}/{total}] {asin} - データなし")

            except Exception as e:
                error_count += 1
                error_msg = str(e)
                errors.append({'asin': asin, 'error': error_msg})
                print(f"[{i}/{total}] {asin} - エラー: {error_msg}")

            # SP-APIレート制限対策
            if i < total:
                time.sleep(sleep_time)

        # メタデータ更新
        self.metadata['last_bulk_update'] = datetime.now().isoformat()
        self._save_metadata()

        summary = {
            'total': total,
            'success': success_count,
            'error': error_count,
            'errors': errors
        }

        print()
        print("=== キャッシュ更新完了 ===")
        print(f"成功: {success_count}件")
        print(f"失敗: {error_count}件")
        print(f"成功率: {success_count/total*100:.1f}%")

        return summary

    def cleanup_expired(self) -> int:
        """
        期限切れキャッシュを削除

        Returns:
            int: 削除したファイル数
        """
        deleted_count = 0
        current_time = time.time()

        for cache_file in self.cache_dir.glob('*.json'):
            mtime = cache_file.stat().st_mtime
            age = current_time - mtime

            if age > self.cache_ttl:
                cache_file.unlink()
                deleted_count += 1

        if deleted_count > 0:
            self.metadata['total_cached'] -= deleted_count
            self._save_metadata()
            print(f"期限切れキャッシュを {deleted_count}件 削除しました")

        return deleted_count

    def get_stats(self) -> Dict[str, Any]:
        """
        キャッシュの統計情報を取得

        Returns:
            dict: 統計情報
        """
        total_files = len(list(self.cache_dir.glob('*.json')))

        # ヒット率計算
        total_requests = self.metadata['cache_hits'] + self.metadata['cache_misses']
        hit_rate = (self.metadata['cache_hits'] / total_requests * 100) if total_requests > 0 else 0

        return {
            'total_cached': total_files,
            'cache_hits': self.metadata['cache_hits'],
            'cache_misses': self.metadata['cache_misses'],
            'hit_rate': f"{hit_rate:.1f}%",
            'last_bulk_update': self.metadata.get('last_bulk_update'),
            'cache_ttl_hours': self.cache_ttl / 3600
        }

    def list_cached_asins(self) -> List[str]:
        """
        キャッシュされているASIN一覧を取得

        Returns:
            list: ASINのリスト
        """
        return [f.stem for f in self.cache_dir.glob('*.json')]

    def get_cache_age(self, asin: str) -> Optional[int]:
        """
        キャッシュの経過時間（秒）を取得

        Args:
            asin: Amazon ASIN

        Returns:
            int or None: 経過時間（秒）、存在しない場合はNone
        """
        cache_file = self.cache_dir / f'{asin}.json'

        if not cache_file.exists():
            return None

        mtime = cache_file.stat().st_mtime
        return int(time.time() - mtime)
