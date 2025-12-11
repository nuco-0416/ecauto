# ng_keyword_filter.py

import re
import unicodedata
from pathlib import Path


class NGKeywordFilter:
    """NGキーワードをテキストから削除するフィルタークラス"""

    def __init__(self, ng_keywords_file):
        """
        Args:
            ng_keywords_file (str): NGキーワードファイルのパス
        """
        self.ng_keywords = self._load_ng_keywords(ng_keywords_file)
        self.ng_patterns = self._compile_patterns()

    def _load_ng_keywords(self, filename):
        """NGキーワードファイルを読み込む（JSON/TXT両対応）"""
        keywords = []
        try:
            # ファイル拡張子で形式を判定
            if filename.endswith('.json'):
                # JSON形式
                import json
                with open(filename, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    keywords = config.get('keywords', [])
                print(f"[NGキーワードフィルター] {len(keywords)}件のNGキーワードを読み込みました (JSON)")
            else:
                # テキスト形式（従来の形式）
                with open(filename, 'r', encoding='utf-8') as f:
                    for line in f:
                        keyword = line.strip()
                        if keyword:  # 空行をスキップ
                            keywords.append(keyword)
                print(f"[NGキーワードフィルター] {len(keywords)}件のNGキーワードを読み込みました (TXT)")
        except FileNotFoundError:
            print(f"警告: NGキーワードファイル '{filename}' が見つかりません。フィルターは無効です。")
        except Exception as e:
            print(f"エラー: NGキーワードファイルの読み込み中にエラーが発生しました: {e}")
        return keywords

    def _normalize_text(self, text):
        """
        テキストを正規化（全角→半角、大文字→小文字）

        Args:
            text (str): 正規化するテキスト

        Returns:
            str: 正規化されたテキスト
        """
        # Unicode正規化（NFKC: 互換文字を統一）
        # 全角英数字→半角、全角記号→半角など
        normalized = unicodedata.normalize('NFKC', text)
        # 小文字に統一
        normalized = normalized.lower()
        return normalized

    def _compile_patterns(self):
        """
        NGキーワードから正規表現パターンをコンパイル
        大文字小文字・全角半角を区別しないパターンを生成

        NOTE: キーワードを長い順にソートすることで、
        「【Amazon.co.jp限定】」が「Amazon」より先に削除されるようにする
        """
        patterns = []

        # キーワードを長さの降順でソート（長いキーワードを優先）
        sorted_keywords = sorted(self.ng_keywords, key=len, reverse=True)

        for keyword in sorted_keywords:
            # キーワードを正規化
            normalized_keyword = self._normalize_text(keyword)
            # 正規表現の特殊文字をエスケープ
            escaped_keyword = re.escape(normalized_keyword)
            # パターンとして保存（元のキーワードもログ用に保持）
            patterns.append({
                'original': keyword,
                'normalized': normalized_keyword,
                'escaped': escaped_keyword
            })
        return patterns

    def remove_ng_keywords(self, text, field_name="テキスト"):
        """
        テキストからNGキーワードを削除

        Args:
            text (str): 処理対象のテキスト
            field_name (str): フィールド名（ログ表示用）

        Returns:
            str: NGキーワードが削除されたテキスト
        """
        if not text or not self.ng_patterns:
            return text

        original_text = text
        normalized_text = self._normalize_text(text)
        removed_keywords = []

        # 各NGキーワードをチェック
        for pattern_info in self.ng_patterns:
            normalized_keyword = pattern_info['normalized']

            # 正規化されたテキスト内でキーワードを検索
            if normalized_keyword in normalized_text:
                # 元のテキストから対応する部分を削除
                # 大文字小文字・全角半角を無視して削除するため、
                # 正規化前後の位置を追跡して削除する必要がある
                text = self._remove_case_insensitive(text, pattern_info)
                normalized_text = self._normalize_text(text)
                removed_keywords.append(pattern_info['original'])

        # 削除後の処理: 連続スペースを1つに正規化
        text = self._normalize_spaces(text)

        # ログ出力
        if removed_keywords:
            print(f"[NGキーワードフィルター] {field_name}から削除: {', '.join(removed_keywords)}")
            if len(original_text) != len(text):
                print(f"  変更前の長さ: {len(original_text)} → 変更後の長さ: {len(text)}")

        return text

    def _remove_case_insensitive(self, text, pattern_info):
        """
        大文字小文字・全角半角を区別せずにキーワードを削除

        Args:
            text (str): 処理対象のテキスト
            pattern_info (dict): パターン情報

        Returns:
            str: キーワードが削除されたテキスト
        """
        # 1文字ずつ正規化しながらマッチング・削除を行う
        result = []
        i = 0
        normalized_keyword = pattern_info['normalized']
        keyword_len = len(normalized_keyword)

        while i < len(text):
            # 現在位置から先のテキストを正規化してマッチをチェック
            match_found = False
            accumulated_normalized = ""

            # キーワード長分の文字を正規化しながら収集
            for j in range(i, min(i + keyword_len * 2, len(text))):  # 全角考慮で2倍
                accumulated_normalized += self._normalize_text(text[j])

                # マッチしたら元のテキストの該当部分をスキップ
                if accumulated_normalized == normalized_keyword:
                    i = j + 1  # マッチ部分をスキップ
                    match_found = True
                    break

                # マッチの可能性がなくなったら中断
                if len(accumulated_normalized) >= keyword_len and not normalized_keyword.startswith(accumulated_normalized):
                    break

            # マッチしなかった場合は現在の文字を結果に追加
            if not match_found:
                result.append(text[i])
                i += 1

        return ''.join(result)

    def _normalize_spaces(self, text):
        """
        連続するスペース（全角・半角）を1つの半角スペースに正規化
        また、先頭・末尾のスペースを削除
        ※改行は保持する

        Args:
            text (str): 処理対象のテキスト

        Returns:
            str: スペースが正規化されたテキスト
        """
        # 全角スペースを半角スペースに変換
        text = text.replace('\u3000', ' ')
        # 連続する空白文字（改行以外）を1つの半角スペースに置換
        # \s+ ではなく [ \t]+ を使用して改行を保持
        text = re.sub(r'[ \t]+', ' ', text)
        # 各行の先頭・末尾のスペースを削除（改行は保持）
        lines = text.split('\n')
        lines = [line.strip() for line in lines]
        text = '\n'.join(lines)
        return text

    def _cleanup_residue(self, text):
        """
        NGキーワード削除後の残骸をクリーンアップ

        対応するケース:
        - 空の【】[]()を削除
        - 【】[]内が1-2文字の意味のない残骸（「品」「の」など）の場合は削除
        - 「■ の」のような助詞だけが残ったパターンを修正

        Args:
            text (str): 処理対象のテキスト

        Returns:
            str: クリーンアップされたテキスト
        """
        if not text:
            return text

        # 空の括弧を削除: 【】 [] () （）
        text = re.sub(r'【\s*】', '', text)
        text = re.sub(r'\[\s*\]', '', text)
        text = re.sub(r'\(\s*\)', '', text)
        text = re.sub(r'（\s*）', '', text)

        # 括弧内が1-2文字の意味のない残骸を削除
        # 「品」「の」「を」「が」「は」「に」「で」「と」「も」「や」などの助詞・接尾辞のみの場合
        residue_pattern = r'[品の を が は に で と も や へ]'
        text = re.sub(r'【\s*' + residue_pattern + r'{1,2}\s*】', '', text)
        text = re.sub(r'\[\s*' + residue_pattern + r'{1,2}\s*\]', '', text)

        # 「■ の」「■ を」のような、記号の後に助詞だけが残ったパターンを修正
        text = re.sub(r'(■\s*)[のをがはにでともや]\s+', r'\1', text)

        # 連続スペースを再度正規化
        text = re.sub(r'[ \t]+', ' ', text)
        text = text.strip()

        return text

    def _remove_emojis(self, text):
        """
        テキストから絵文字を除去

        Args:
            text (str): 処理対象のテキスト

        Returns:
            str: 絵文字が除去されたテキスト
        """
        if not text:
            return text

        # 絵文字のUnicode範囲を定義（日本語を含まない安全な範囲のみ）
        # 参考: https://en.wikipedia.org/wiki/Unicode_block
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # Emoticons (顔文字)
            "\U0001F300-\U0001F5FF"  # Miscellaneous Symbols and Pictographs
            "\U0001F680-\U0001F6FF"  # Transport and Map Symbols
            "\U0001F700-\U0001F77F"  # Alchemical Symbols
            "\U0001F780-\U0001F7FF"  # Geometric Shapes Extended
            "\U0001F800-\U0001F8FF"  # Supplemental Arrows-C
            "\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs
            "\U0001FA00-\U0001FA6F"  # Chess Symbols
            "\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
            "\U00002600-\U000026FF"  # Miscellaneous Symbols (天気記号等)
            "\U00002700-\U000027BF"  # Dingbats
            "\U00002B00-\U00002BFF"  # Miscellaneous Symbols and Arrows (⭐等)
            "]+",
            flags=re.UNICODE
        )

        return emoji_pattern.sub('', text)

    def filter_title(self, title):
        """
        タイトルからNGキーワードと絵文字を削除

        Args:
            title (str): 商品タイトル

        Returns:
            str: フィルター済みタイトル
        """
        # NGキーワードを削除
        filtered = self.remove_ng_keywords(title, field_name="タイトル")
        # 絵文字を削除
        filtered = self._remove_emojis(filtered)
        # スペースを正規化
        filtered = self._normalize_spaces(filtered)
        # 残骸をクリーンアップ
        filtered = self._cleanup_residue(filtered)
        return filtered

    def filter_description(self, description):
        """
        商品説明からNGキーワードと絵文字を削除

        Args:
            description (str): 商品説明（HTML含む）

        Returns:
            str: フィルター済み商品説明
        """
        # NGキーワードを削除
        filtered = self.remove_ng_keywords(description, field_name="商品説明")
        # 絵文字を削除
        filtered = self._remove_emojis(filtered)
        # スペースを正規化
        filtered = self._normalize_spaces(filtered)
        # 残骸をクリーンアップ
        filtered = self._cleanup_residue(filtered)
        return filtered

    def clean_product_data(self, product_data, asin=None):
        """
        商品データ全体をクリーニング（TextCleanerとの互換性のため）

        Args:
            product_data (dict): 商品データ（title_ja, title_en, description_ja, description_enなどを含む）
            asin (str): 商品ASIN（ログ用、オプション）

        Returns:
            tuple: (クリーンな商品データ, 削除が発生したか)
        """
        if not product_data:
            return product_data, False

        cleaned_data = product_data.copy()
        any_removed = False

        # クリーニング対象フィールド
        text_fields = {
            'title_ja': 'タイトル(日本語)',
            'title_en': 'タイトル(英語)',
            'title': 'タイトル',
            'description_ja': '商品説明(日本語)',
            'description_en': '商品説明(英語)',
            'description': '商品説明',
            'detail': '詳細'
        }

        for field, field_name in text_fields.items():
            if field in cleaned_data and cleaned_data[field]:
                original = cleaned_data[field]
                # フィルター適用
                if 'title' in field.lower():
                    filtered = self.filter_title(original)
                else:
                    filtered = self.filter_description(original)

                cleaned_data[field] = filtered
                if original != filtered:
                    any_removed = True

        return cleaned_data, any_removed


# グローバルインスタンス（使いやすさのため）
_filter_instance = None


def get_ng_keyword_filter():
    """
    NGKeywordFilterのグローバルインスタンスを取得

    Returns:
        NGKeywordFilter: シングルトンインスタンス
    """
    global _filter_instance
    if _filter_instance is None:
        # デフォルトでng_keywords.jsonを使用
        import os
        config_path = os.path.join(os.path.dirname(__file__), "..", "config", "ng_keywords.json")
        _filter_instance = NGKeywordFilter(config_path)
    return _filter_instance


def clean_product_data(product_data, asin=None):
    """
    商品データ全体をクリーニング（便利関数、TextCleanerとの互換性のため）

    Args:
        product_data (dict): 商品データ
        asin (str): 商品ASIN（ログ用）

    Returns:
        tuple: (クリーンな商品データ, 削除が発生したか)
    """
    filter_instance = get_ng_keyword_filter()
    return filter_instance.clean_product_data(product_data, asin)


# テスト用コード
if __name__ == "__main__":
    # テスト実行例
    import os

    # NGキーワードファイルのパス（JSON優先）
    ng_file = os.path.join(os.path.dirname(__file__), "..", "config", "ng_keywords.json")

    # フィルター初期化
    filter = NGKeywordFilter(ng_file)

    # テストデータ
    test_title = "【Amazon.co.jp限定】 素晴らしい商品"
    test_description = """
    <div>
    <h2>【amazon.co.jp限定】高品質商品</h2>
    <p>これはAMAZON限定の素晴らしい商品です。</p>
    <p>【　Ａｍａｚｏｎ．ｃｏ．ｊｐ限定　】特典付き</p>
    </div>
    """

    print("=" * 60)
    print("テスト実行")
    print("=" * 60)

    print("\n[元のタイトル]")
    print(test_title)
    filtered_title = filter.filter_title(test_title)
    print("[フィルター後のタイトル]")
    print(filtered_title)

    print("\n[元の説明]")
    print(test_description)
    filtered_description = filter.filter_description(test_description)
    print("[フィルター後の説明]")
    print(filtered_description)
