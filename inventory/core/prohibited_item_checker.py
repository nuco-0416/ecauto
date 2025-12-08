"""
禁止商品チェッカー

BASEの利用規約に基づいて商品が禁止商品に該当するかをチェック
"""
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple


class ProhibitedItemChecker:
    """
    禁止商品チェッカー

    商品情報（タイトル、説明文、カテゴリ、ブランド等）から
    BASE禁止商品に該当するかを判定し、リスクスコアを算出する
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Args:
            config_path: 設定ファイルのパス（デフォルト: config/prohibited_items.json）
        """
        if config_path is None:
            project_root = Path(__file__).resolve().parent.parent.parent
            config_path = project_root / 'config' / 'prohibited_items.json'

        self.config_path = Path(config_path)

        if not self.config_path.exists():
            raise FileNotFoundError(f"設定ファイルが見つかりません: {config_path}")

        with open(self.config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)

        self.categories = self.config.get('categories', {})
        self.keywords = self.config.get('keywords', {})
        self.brands = self.config.get('brands', {})
        self.asin_whitelist = self.keywords.get('asin_whitelist', [])
        self.risk_thresholds = self.config.get('risk_thresholds', {
            'auto_block': 80,
            'manual_review': 50,
            'auto_approve': 30
        })

    def check_product(self, product_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        商品情報をチェックしてリスクスコアを算出

        Args:
            product_info: 商品情報
                {
                    'asin': str,
                    'title_ja': str,
                    'title_en': str,
                    'description_ja': str,
                    'description_en': str,
                    'category': str,
                    'brand': str,
                    'images': list
                }

        Returns:
            dict: チェック結果
                {
                    'asin': str,
                    'risk_score': int (0-100),
                    'risk_level': str ('safe', 'review', 'block'),
                    'matched_keywords': list,
                    'matched_categories': list,
                    'is_whitelisted': bool,
                    'recommendation': str,
                    'details': dict
                }
        """
        asin = product_info.get('asin', 'UNKNOWN')
        title_ja = product_info.get('title_ja', '')
        title_en = product_info.get('title_en', '')
        description_ja = product_info.get('description_ja', '')
        description_en = product_info.get('description_en', '')
        category = product_info.get('category', '')
        brand = product_info.get('brand', '')

        # テキストを結合
        combined_text = f"{title_ja} {title_en} {description_ja} {description_en} {category} {brand}".lower()

        # 0. ASINホワイトリストチェック（最優先）
        if asin in self.asin_whitelist:
            return {
                'asin': asin,
                'risk_score': 0,
                'risk_level': 'safe',
                'matched_keywords': [],
                'matched_categories': [],
                'is_whitelisted': True,
                'recommendation': 'auto_approve',
                'details': {
                    'whitelist_reason': f'ASINホワイトリスト登録済み: {asin}'
                }
            }

        # 1. キーワードホワイトリストチェック
        is_whitelisted, whitelist_reason = self._check_whitelist(combined_text)

        if is_whitelisted:
            return {
                'asin': asin,
                'risk_score': 0,
                'risk_level': 'safe',
                'matched_keywords': [],
                'matched_categories': [],
                'is_whitelisted': True,
                'recommendation': 'auto_approve',
                'details': {
                    'whitelist_reason': whitelist_reason
                }
            }

        # 2. キーワードベースチェック
        keyword_score, matched_keywords = self._check_keywords(combined_text)

        # 3. カテゴリベースチェック
        category_score, matched_categories = self._check_categories(category)

        # 4. ブランドベースチェック
        brand_score, brand_reason = self._check_brand(brand)

        # 合計スコア
        total_score = min(100, keyword_score + category_score + brand_score)

        # リスクレベルの判定
        if total_score >= self.risk_thresholds['auto_block']:
            risk_level = 'block'
            recommendation = 'auto_block'
        elif total_score >= self.risk_thresholds['manual_review']:
            risk_level = 'review'
            recommendation = 'manual_review'
        else:
            risk_level = 'safe'
            recommendation = 'auto_approve'

        return {
            'asin': asin,
            'risk_score': total_score,
            'risk_level': risk_level,
            'matched_keywords': matched_keywords,
            'matched_categories': matched_categories,
            'is_whitelisted': False,
            'recommendation': recommendation,
            'details': {
                'keyword_score': keyword_score,
                'category_score': category_score,
                'brand_score': brand_score,
                'brand_reason': brand_reason
            }
        }

    def _check_whitelist(self, text: str) -> Tuple[bool, Optional[str]]:
        """
        ホワイトリストチェック

        Args:
            text: チェック対象のテキスト

        Returns:
            tuple: (is_whitelisted, reason)
        """
        whitelist = self.keywords.get('whitelist', {})

        for category, keywords in whitelist.items():
            for keyword in keywords:
                if keyword.lower() in text:
                    return True, f"ホワイトリスト該当: {category} - {keyword}"

        return False, None

    def _check_keywords(self, text: str) -> Tuple[int, List[Dict[str, Any]]]:
        """
        キーワードベースチェック

        Args:
            text: チェック対象のテキスト

        Returns:
            tuple: (score, matched_keywords)
        """
        total_score = 0
        matched = []

        # strict、moderate、lowの順にチェック
        for level in ['strict', 'moderate', 'low']:
            keyword_groups = self.keywords.get(level, {})

            for group_name, group_data in keyword_groups.items():
                keywords = group_data.get('keywords', [])
                weight = group_data.get('weight', 0)
                base_rule = group_data.get('base_rule', '')

                for keyword in keywords:
                    if keyword.lower() in text:
                        total_score += weight
                        matched.append({
                            'keyword': keyword,
                            'group': group_name,
                            'level': level,
                            'weight': weight,
                            'base_rule': base_rule
                        })
                        break  # 同じグループでは1つヒットすればOK

        return total_score, matched

    def _check_categories(self, category: str) -> Tuple[int, List[str]]:
        """
        カテゴリベースチェック

        Args:
            category: Amazonカテゴリ

        Returns:
            tuple: (score, matched_categories)
        """
        if not category:
            return 0, []

        score = 0
        matched = []

        # blockedカテゴリチェック（完全ブロック）
        for blocked_cat in self.categories.get('blocked', []):
            if blocked_cat.lower() in category.lower():
                score = 100  # 即座に100にして自動ブロック
                matched.append(f"blocked: {blocked_cat}")
                return score, matched  # 即座にリターン

        # high_riskカテゴリチェック
        for high_risk_cat in self.categories.get('high_risk', []):
            if high_risk_cat.lower() in category.lower():
                score += 30
                matched.append(f"high_risk: {high_risk_cat}")

        # medium_riskカテゴリチェック
        for medium_risk_cat in self.categories.get('medium_risk', []):
            if medium_risk_cat.lower() in category.lower():
                score += 20
                matched.append(f"medium_risk: {medium_risk_cat}")

        return score, matched

    def _check_brand(self, brand: str) -> Tuple[int, Optional[str]]:
        """
        ブランドベースチェック

        Args:
            brand: ブランド名

        Returns:
            tuple: (score, reason)
        """
        if not brand:
            return 0, None

        blacklist = self.brands.get('blacklist', [])

        for blacklisted_brand in blacklist:
            if blacklisted_brand.lower() in brand.lower():
                return 100, f"ブラックリストブランド: {blacklisted_brand}"

        return 0, None

    def check_asin_basic(self, asin: str, category: Optional[str] = None) -> int:
        """
        ASINの基本チェック（SP-API取得前）

        Args:
            asin: ASIN
            category: カテゴリ（オプション）

        Returns:
            int: リスクスコア
        """
        if not category:
            return 0

        category_score, _ = self._check_categories(category)

        return category_score

    def check_product_detailed(self, product_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        商品の詳細チェック（SP-API取得後）

        Args:
            product_info: 商品情報

        Returns:
            dict: チェック結果
        """
        return self.check_product(product_info)

    def get_recommendation_text(self, recommendation: str) -> str:
        """
        推奨アクションのテキストを取得

        Args:
            recommendation: 推奨アクション

        Returns:
            str: 説明文
        """
        texts = {
            'auto_block': '自動ブロック推奨: 禁止商品の可能性が高いため出品をブロックしてください',
            'manual_review': '手動レビュー推奨: 禁止商品の可能性があるため手動確認が必要です',
            'auto_approve': '自動承認: 問題なく出品可能です'
        }

        return texts.get(recommendation, '不明')
