"""
過去のレポートから履歴ファイルを生成するツール

過去の抽出レポート（Markdown）から、カテゴリごとの取得履歴を
JSON形式で生成します。

使用例:
    python sourcing/scripts/generate_history_from_reports.py \
      --reports category_report_20251128.md category_report_additional_20251128.md category_report_round3_20251128.md \
      --output category_history.json \
      --pages-extracted 10
"""

import argparse
import json
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict


def parse_report(report_path: Path) -> List[Dict]:
    """
    レポートファイルからカテゴリ情報を抽出

    Args:
        report_path: レポートファイルのパス

    Returns:
        [{"category": "...", "nodeIdPaths": "...", "count": 10}, ...]
    """
    with open(report_path, 'r', encoding='utf-8') as f:
        content = f.read()

    categories = []

    # カテゴリ一覧セクションを探す
    category_section_match = re.search(
        r'## 📂 処理カテゴリ一覧(.*?)(?=##|\Z)',
        content,
        re.DOTALL
    )

    if not category_section_match:
        print(f"[WARN] カテゴリ一覧が見つかりません: {report_path}")
        return categories

    category_section = category_section_match.group(1)

    # 各カテゴリを抽出
    # 例: 1. **ドラッグストア > 栄養補助食品 > ...**
    category_pattern = re.compile(
        r'\d+\.\s+\*\*(.*?)\*\*.*?nodeIdPaths:\s+`(.*?)`',
        re.DOTALL
    )

    for match in category_pattern.finditer(category_section):
        category_name = match.group(1).strip()
        node_id_paths = match.group(2).strip()

        # サンプル内商品数も抽出（オプション）
        count_match = re.search(
            r'サンプル内商品数:\s+(\d+)件',
            match.group(0)
        )
        count = int(count_match.group(1)) if count_match else 0

        categories.append({
            'category': category_name,
            'nodeIdPaths': node_id_paths,
            'count': count
        })

    return categories


def generate_history(
    report_paths: List[Path],
    pages_extracted: int
) -> Dict:
    """
    複数のレポートから履歴ファイルを生成

    Args:
        report_paths: レポートファイルのパスリスト
        pages_extracted: 取得済みページ数

    Returns:
        履歴データ（JSON形式）
    """
    history = {
        "categories": {},
        "metadata": {
            "total_asins": 0,
            "last_run": None,
            "generated_from_reports": [str(p) for p in report_paths],
            "generated_at": datetime.now().isoformat()
        }
    }

    # 各レポートを処理
    for report_path in report_paths:
        print(f"処理中: {report_path}")
        categories = parse_report(report_path)
        print(f"  → {len(categories)}カテゴリを抽出")

        for cat_info in categories:
            category_name = cat_info['category']

            # 既に存在する場合はスキップ（最初のレポートを優先）
            if category_name in history['categories']:
                continue

            history['categories'][category_name] = {
                'nodeIdPaths': cat_info['nodeIdPaths'],
                'pages_extracted': pages_extracted,
                'last_updated': datetime.now().isoformat(),
                'asins_count': 0,  # 実際のASIN数は不明なので0
                'sample_count': cat_info['count']
            }

    print(f"\n合計 {len(history['categories'])} カテゴリを履歴に追加")

    return history


def main():
    parser = argparse.ArgumentParser(
        description="過去のレポートから履歴ファイルを生成",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "--reports",
        nargs='+',
        required=True,
        help="レポートファイルのパス（複数指定可能）"
    )

    parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="出力先の履歴ファイルパス（JSON形式）"
    )

    parser.add_argument(
        "--pages-extracted",
        type=int,
        default=10,
        help="取得済みページ数（デフォルト: 10）"
    )

    args = parser.parse_args()

    # レポートファイルのパスを変換
    report_paths = [Path(r) for r in args.reports]

    # 存在確認
    for path in report_paths:
        if not path.exists():
            print(f"[ERROR] ファイルが見つかりません: {path}")
            return

    # 履歴を生成
    history = generate_history(report_paths, args.pages_extracted)

    # JSON形式で保存
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 履歴ファイルを生成しました: {output_path}")
    print(f"   カテゴリ数: {len(history['categories'])}件")
    print(f"   取得済みページ: {args.pages_extracted}ページ/カテゴリ")


if __name__ == "__main__":
    main()
