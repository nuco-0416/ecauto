# SellerSprite 認証とカテゴリ抽出 - 技術ドキュメント

**最終更新**: 2025-11-27
**対象**: AIエージェント、開発者

このドキュメントは、SellerSpriteの認証処理とカテゴリベースASIN抽出の実装詳細を説明します。

---

## 目次

1. [認証処理](#認証処理)
2. [URL構築方法](#url構築方法)
3. [カテゴリ名とnodeIdPathsの紐付け](#カテゴリ名とnodeidpathsの紐付け)
4. [再利用可能なコードサンプル](#再利用可能なコードサンプル)
5. [トラブルシューティング](#トラブルシューティング)

---

## 認証処理

### 1. 認証の仕組み

SellerSpriteでは、以下の3つの認証方法を実装しています：

#### **方法A: 既存の認証マネージャーを使用（未実装）**

```python
from sourcing.sources.sellersprite.auth_manager import get_authenticated_browser

# 認証済みブラウザを取得
browser, context, page = await get_authenticated_browser(headless=False)
```

**利点**:
- Cookie管理が自動化
- セッション有効性の自動チェック
- 認証情報の一元管理

#### **方法B: 手動ログイン（テスト用：現状はこれを使ってください）**

```python
import re
from playwright.async_api import async_playwright

async def login_to_sellersprite(page, email, password):
    """SellerSpriteに手動ログイン"""

    # ログインページに遷移
    await page.goto("https://www.sellersprite.com/jp/w/user/login",
                   wait_until="networkidle",
                   timeout=30000)

    # メールアドレス入力
    email_input = page.get_by_role('textbox',
                                   name=re.compile(r'メールアドレス|アカウント', re.IGNORECASE))
    await email_input.fill(email)
    await page.wait_for_timeout(1000)

    # パスワード入力
    password_input = page.get_by_role('textbox',
                                      name=re.compile(r'パスワード', re.IGNORECASE))
    await password_input.fill(password)
    await page.wait_for_timeout(1000)

    # ログインボタンをクリック
    login_button = page.get_by_role('button',
                                     name=re.compile(r'ログイン', re.IGNORECASE))
    await login_button.click()

    # ログイン完了を待機
    await page.wait_for_timeout(5000)

    # ログイン成功確認
    current_url = page.url
    if 'login' not in current_url:
        return True
    else:
        raise Exception(f"ログインに失敗しました。現在のURL: {current_url}")
```

**利用例**:
```python
async with async_playwright() as p:
    browser = await p.chromium.launch(headless=False)
    context = await browser.new_context(
        viewport={'width': 1920, 'height': 1080},
        locale="ja-JP",
        timezone_id="Asia/Tokyo"
    )
    page = await context.new_page()

    # ログイン
    await login_to_sellersprite(page, "your@email.com", "password")
```

#### **方法C: 環境変数を使用した認証**

```python
import os
from pathlib import Path

# 環境変数に認証情報を設定
os.environ['SELLERSPRITE_EMAIL'] = 'your@email.com'
os.environ['SELLERSPRITE_PASSWORD'] = 'your_password'

# または.envファイルから読み込み
from dotenv import load_dotenv
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)
```

**.env ファイル例**:
```env
SELLERSPRITE_EMAIL=your@email.com
SELLERSPRITE_PASSWORD=your_password
```

### 2. セッション管理

#### Cookie保存とリストア

```python
import json
from pathlib import Path

async def save_cookies(context, file_path):
    """Cookieを保存"""
    cookies = await context.cookies()
    Path(file_path).write_text(json.dumps(cookies, indent=2))

async def load_cookies(context, file_path):
    """Cookieをロード"""
    if Path(file_path).exists():
        cookies = json.loads(Path(file_path).read_text())
        await context.add_cookies(cookies)
        return True
    return False
```

#### セッション有効性確認

```python
async def check_session_valid(page):
    """セッションが有効かチェック"""
    current_url = page.url

    # ログインページにリダイレクトされていないか確認
    if 'login' in current_url:
        return False

    # ページコンテンツをチェック
    try:
        # ユーザーメニューなどの存在確認
        user_menu = await page.query_selector('.user-menu, .user-info')
        return user_menu is not None
    except:
        return False
```

---

## URL構築方法

### 1. 基本的なURL構築

SellerSpriteの商品リサーチURLは以下の構造を持ちます：

```
https://www.sellersprite.com/v3/product-research?[parameters]
```

### 2. URL構築関数

```python
from urllib.parse import urlencode

def build_product_research_url(
    node_id_paths="[]",
    sales_min=300,
    sales_max=None,
    price_min=2500,
    price_max=None,
    market="JP",
    page=1,
    size=100
):
    """
    SellerSprite 商品リサーチURLを構築

    Args:
        node_id_paths: カテゴリパス（JSON文字列）
            例: '["160384011:169976011:344024011:3457068051:3457072051"]'
        sales_min: 最小売上（月間販売数）
        sales_max: 最大売上（オプション）
        price_min: 最小価格（円）
        price_max: 最大価格（オプション）
        market: 市場（JP, US, UK, DE等）
        page: ページ番号
        size: 1ページあたりの件数（最大100）

    Returns:
        完全なURL文字列
    """
    # sellerTypesを構築（AMZ=Amazon販売、FBA=Fulfilled by Amazon）
    seller_types_str = '["AMZ","FBA"]'

    # ベースURL
    base_url = "https://www.sellersprite.com/v3/product-research"

    # 必須パラメータ
    params = {
        'market': market,
        'page': str(page),
        'size': str(size),
        'symbolFlag': 'true',
        'monthName': 'bsr_sales_nearly',  # 直近の売上データ
        'selectType': '2',
        'filterSub': 'false',
        'weightUnit': 'g',
        'order[field]': 'amz_unit',  # ソート基準
        'order[desc]': 'true',       # 降順
        'productTags': '[]',
        'nodeIdPaths': node_id_paths,
        'sellerTypes': seller_types_str,
        'eligibility': '[]',
        'pkgDimensionTypeList': '[]',
        'sellerNationList': '[]',
        'lowPrice': 'N',
        'video': ''
    }

    # フィルター条件を追加
    if sales_min is not None:
        params['minSales'] = str(sales_min)
    if sales_max is not None:
        params['maxSales'] = str(sales_max)
    if price_min is not None:
        params['minPrice'] = str(price_min)
    if price_max is not None:
        params['maxPrice'] = str(price_max)

    # URLエンコード（[]":は保護）
    query_string = urlencode(params, safe='[]":')

    return f"{base_url}?{query_string}"
```

### 3. 使用例

```python
# 基本的な使い方
url = build_product_research_url(
    sales_min=300,
    price_min=2500,
    market="JP"
)

# カテゴリ指定
url = build_product_research_url(
    node_id_paths='["160384011:169976011:344024011:3457068051:3457072051"]',
    sales_min=300,
    price_min=2500,
    market="JP"
)

# 売上・価格範囲指定
url = build_product_research_url(
    sales_min=300,
    sales_max=1000,
    price_min=2500,
    price_max=5000,
    market="JP"
)
```

---

## カテゴリ名とnodeIdPathsの紐付け

### 1. 紐付けの仕組み

**重要**: カテゴリ名とnodeIdPathsの事前定義マッピングテーブルは存在しません。SellerSpriteのページから動的に抽出します。

#### nodeIdPathsの構造

```
nodeIdPaths: ["カテゴリID1:カテゴリID2:カテゴリID3:カテゴリID4:カテゴリID5"]
```

**例**:
```json
{
  "category": "ドラッグストア > 栄養補助食品 > サプリメント・ビタミン > プロテイン > ホエイプロテイン",
  "nodeIdPaths": "160384011:169976011:344024011:3457068051:3457072051"
}
```

各IDはAmazonのカテゴリツリーのノードIDに対応します：
- `160384011`: ドラッグストア
- `169976011`: 栄養補助食品
- `344024011`: サプリメント・ビタミン
- `3457068051`: プロテイン
- `3457072051`: ホエイプロテイン

### 2. カテゴリ情報の抽出方法

#### ページから直接抽出

`ProductResearchExtractor` の `_extract_asins_with_categories` メソッドで実装されています。

**処理フロー**:

1. リスト表示に切り替え
2. 各商品行を展開（expand）
3. `.product-type` 要素内のカテゴリリンクを取得
4. リンクのURLパラメータから `nodeIdPaths` を抽出

**JavaScriptコード** (実際の抽出処理):

```javascript
// カテゴリリンク（class="type"）を全て取得
const categoryLinks = productType.querySelectorAll('a.type');

let categories = [];
let nodeIdPaths = '';

categoryLinks.forEach((link, linkIndex) => {
    // カテゴリ名を取得
    const categoryName = link.textContent.trim();
    if (categoryName) {
        categories.push(categoryName);
    }

    // 最後のリンクからnodeIdPathsを取得
    if (linkIndex === categoryLinks.length - 1 && link.href) {
        try {
            const url = new URL(link.href, window.location.origin);
            const nodeIdPathsParam = url.searchParams.get('nodeIdPaths');
            if (nodeIdPathsParam) {
                nodeIdPaths = nodeIdPathsParam;
            }
        } catch (e) {
            // URLパースエラーは無視
        }
    }
});

// 結果
const result = {
    category: categories.join(' > '),
    nodeIdPaths: nodeIdPaths
};
```

### 3. 人気カテゴリの分析と収集

#### スクリプトを使用した一括収集

```bash
# 上位500件からトップ10カテゴリを抽出
python sourcing/scripts/analyze_popular_categories.py \
  --sample-size 500 \
  --top-n 10 \
  --sales-min 300 \
  --price-min 2500 \
  --output popular_categories.json
```

**出力例** (`popular_categories.json`):

```json
[
  {
    "rank": 1,
    "category": "ドラッグストア > 栄養補助食品 > サプリメント・ビタミン > プロテイン > ホエイプロテイン",
    "count": 45,
    "percentage": 9.0,
    "nodeIdPaths": "160384011:169976011:344024011:3457068051:3457072051"
  },
  {
    "rank": 2,
    "category": "ホーム&キッチン > 家電 > キッチン家電",
    "count": 38,
    "percentage": 7.6,
    "nodeIdPaths": "2127209051:3828871:3828881"
  }
]
```

### 4. カテゴリを指定したASIN抽出

#### 既知のnodeIdPathsを使用

```python
from sourcing.sources.sellersprite.extractors.product_research_extractor import ProductResearchExtractor

# カテゴリを指定して抽出
extractor = ProductResearchExtractor({
    "node_id_paths": '["160384011:169976011:344024011:3457068051:3457072051"]',
    "sales_min": 300,
    "price_min": 2500,
    "limit": 100,
    "market": "JP"
})

asins = await extractor.extract()
```

#### カテゴリ情報付きで抽出

```python
# カテゴリ情報も含めて抽出
extractor = ProductResearchExtractor({
    "sales_min": 300,
    "price_min": 2500,
    "limit": 100,
    "market": "JP",
    "extract_category_info": True  # カテゴリ情報も抽出
})

# 戻り値は [{"asin": "...", "category": "...", "nodeIdPaths": "..."}, ...]
data = await extractor.extract()

for item in data:
    print(f"ASIN: {item['asin']}")
    print(f"Category: {item['category']}")
    print(f"NodeIdPaths: {item['nodeIdPaths']}")
```

---

## 再利用可能なコードサンプル

### サンプル1: 完全なASIN抽出フロー

```python
"""
SellerSprite ASIN抽出 - 完全なサンプル
"""
import asyncio
from sourcing.sources.sellersprite.extractors.product_research_extractor import ProductResearchExtractor

async def extract_asins_sample():
    """ASIN抽出のサンプル"""

    # Extractorを作成
    extractor = ProductResearchExtractor({
        "sales_min": 300,
        "price_min": 2500,
        "amz": True,
        "fba": True,
        "limit": 100,
        "market": "JP"
    })

    try:
        # ASIN抽出
        print("ASIN抽出中...")
        asins = await extractor.extract()

        print(f"抽出完了: {len(asins)}件")
        for i, asin in enumerate(asins[:10], 1):
            print(f"  {i}. {asin}")

        return asins

    except Exception as e:
        print(f"エラー: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(extract_asins_sample())
```

### サンプル2: カテゴリベース抽出

```python
"""
カテゴリを指定したASIN抽出
"""
import asyncio
import json
from pathlib import Path
from sourcing.sources.sellersprite.extractors.product_research_extractor import ProductResearchExtractor

async def extract_by_category(category_nodeIdPaths, output_file=None):
    """
    カテゴリを指定してASINを抽出

    Args:
        category_nodeIdPaths: カテゴリのnodeIdPaths
        output_file: 出力ファイルパス（オプション）
    """
    # nodeIdPathsを配列形式に変換
    if not category_nodeIdPaths.startswith('['):
        category_nodeIdPaths = f'["{category_nodeIdPaths}"]'

    extractor = ProductResearchExtractor({
        "node_id_paths": category_nodeIdPaths,
        "sales_min": 300,
        "price_min": 2500,
        "limit": 100,
        "market": "JP",
        "extract_category_info": True  # カテゴリ情報も抽出
    })

    print(f"カテゴリ: {category_nodeIdPaths}")
    print("抽出中...")

    data = await extractor.extract()

    print(f"抽出完了: {len(data)}件")

    # 結果を表示
    for item in data[:5]:
        print(f"  ASIN: {item['asin']}")
        print(f"  Category: {item['category']}")
        print()

    # ファイル出力
    if output_file:
        Path(output_file).write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )
        print(f"保存完了: {output_file}")

    return data

# 使用例
if __name__ == "__main__":
    # ホエイプロテインカテゴリから抽出
    asyncio.run(extract_by_category(
        "160384011:169976011:344024011:3457068051:3457072051",
        "whey_protein_asins.json"
    ))
```

### サンプル3: 人気カテゴリ自動発見

```python
"""
人気カテゴリを自動発見してASINを抽出
"""
import asyncio
from collections import Counter
from sourcing.sources.sellersprite.extractors.product_research_extractor import ProductResearchExtractor

async def discover_and_extract():
    """人気カテゴリを発見して抽出"""

    # Step 1: サンプルを取得してカテゴリを分析
    print("Step 1: 人気カテゴリを分析中...")
    extractor = ProductResearchExtractor({
        "sales_min": 300,
        "price_min": 2500,
        "limit": 500,
        "market": "JP",
        "extract_category_info": True
    })

    sample_data = await extractor.extract()

    # カテゴリごとに集計
    category_counts = Counter()
    category_to_nodeIdPaths = {}

    for item in sample_data:
        category = item.get('category', '')
        nodeIdPaths = item.get('nodeIdPaths', '')

        if category:
            category_counts[category] += 1
            if category not in category_to_nodeIdPaths and nodeIdPaths:
                category_to_nodeIdPaths[category] = nodeIdPaths

    # トップ3カテゴリ
    top_categories = category_counts.most_common(3)

    print(f"\nトップ3カテゴリ:")
    for i, (category, count) in enumerate(top_categories, 1):
        print(f"  {i}. {category} ({count}件)")

    # Step 2: 各カテゴリから詳細抽出
    print("\nStep 2: 各カテゴリから詳細抽出...")
    results = {}

    for category, count in top_categories:
        nodeIdPaths = category_to_nodeIdPaths.get(category)
        if not nodeIdPaths:
            continue

        print(f"\n抽出中: {category}")

        extractor = ProductResearchExtractor({
            "node_id_paths": f'["{nodeIdPaths}"]',
            "sales_min": 300,
            "price_min": 2500,
            "limit": 50,
            "market": "JP"
        })

        asins = await extractor.extract()
        results[category] = asins

        print(f"  → {len(asins)}件抽出")

    return results

if __name__ == "__main__":
    results = asyncio.run(discover_and_extract())

    print("\n最終結果:")
    for category, asins in results.items():
        print(f"{category}: {len(asins)}件")
```

### サンプル4: 直接URL方式（UI操作なし）

```python
"""
直接URLを構築してASINを抽出（UI操作なし）
"""
import asyncio
from urllib.parse import urlencode
from playwright.async_api import async_playwright

def build_url(node_id_paths="[]", sales_min=300, price_min=2500):
    """URLを構築"""
    base_url = "https://www.sellersprite.com/v3/product-research"

    params = {
        'market': 'JP',
        'page': '1',
        'size': '100',
        'symbolFlag': 'true',
        'monthName': 'bsr_sales_nearly',
        'selectType': '2',
        'filterSub': 'false',
        'weightUnit': 'g',
        'order[field]': 'amz_unit',
        'order[desc]': 'true',
        'productTags': '[]',
        'nodeIdPaths': node_id_paths,
        'sellerTypes': '["AMZ","FBA"]',
        'eligibility': '[]',
        'pkgDimensionTypeList': '[]',
        'sellerNationList': '[]',
        'lowPrice': 'N',
        'video': ''
    }

    if sales_min:
        params['minSales'] = str(sales_min)
    if price_min:
        params['minPrice'] = str(price_min)

    query_string = urlencode(params, safe='[]":')
    return f"{base_url}?{query_string}"

async def extract_asins_from_page(page):
    """ページからASINを抽出"""
    asins = await page.evaluate('''() => {
        const asinElements = document.querySelectorAll('table tbody tr');
        const asinList = [];

        asinElements.forEach(row => {
            const text = row.textContent || '';
            const match = text.match(/ASIN:\\s*([A-Z0-9]{10})/);
            if (match && match[1]) {
                asinList.push(match[1]);
            }
        });

        return [...new Set(asinList)];
    }''')

    return asins

async def main():
    """メイン処理"""
    # URLを構築
    url = build_url(
        node_id_paths='["160384011:169976011:344024011:3457068051:3457072051"]',
        sales_min=300,
        price_min=2500
    )

    print(f"URL: {url}\n")

    # ブラウザ起動
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            locale="ja-JP",
            timezone_id="Asia/Tokyo"
        )
        page = await context.new_page()

        # ログイン（省略 - 既存の認証マネージャーを使用）
        # ...

        # URLに直接アクセス
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)

        # ASIN抽出
        asins = await extract_asins_from_page(page)

        print(f"抽出件数: {len(asins)}件")
        for i, asin in enumerate(asins[:10], 1):
            print(f"  {i}. {asin}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
```

---

## トラブルシューティング

### 問題1: ログインに失敗する

**症状**:
```
[ERROR] ログインに失敗しました。現在のURL: https://www.sellersprite.com/jp/w/user/login
```

**原因と対処法**:

1. **認証情報が間違っている**
   - 環境変数 `SELLERSPRITE_EMAIL`, `SELLERSPRITE_PASSWORD` を確認
   - `.env` ファイルの内容を確認

2. **セレクタが変更されている**
   - SellerSpriteのUIが変更された可能性
   - ブラウザを起動して手動でセレクタを確認
   - 必要に応じてセレクタを更新

3. **CAPTCHA・二段階認証**
   - 手動でログインしてCookieを保存
   - 保存したCookieを読み込んで使用

### 問題2: nodeIdPathsが取得できない

**症状**:
```python
{"asin": "B00XXX", "category": "...", "nodeIdPaths": ""}
```

**原因と対処法**:

1. **リスト表示に切り替わっていない**
   ```python
   # リストボタンをクリック
   list_button = page.locator('button:has-text("リスト")').first
   await list_button.click()
   await page.wait_for_timeout(2000)
   ```

2. **行が展開されていない**
   ```javascript
   // 全ての行を展開
   const expandButtons = document.querySelectorAll('.el-table__expand-icon');
   expandButtons.forEach(button => {
       if (!button.classList.contains('el-table__expand-icon--expanded')) {
           button.click();
       }
   });
   ```

3. **待機時間が不足**
   ```python
   # DOM更新を十分に待機
   await page.wait_for_timeout(3000)
   ```

### 問題3: ASINが抽出されない

**症状**:
```
抽出されたASIN数: 0件
```

**原因と対処法**:

1. **テーブルがレンダリングされていない**
   ```python
   # テーブルの存在を確認
   table = await page.query_selector('table')
   if not table:
       print("テーブルが見つかりません")
       # スクリーンショットを撮影
       await page.screenshot(path="debug.png", full_page=True)
   ```

2. **フィルター条件が厳しすぎる**
   - `sales_min`, `price_min` の値を調整
   - カテゴリを広げる

3. **ページ遷移に失敗**
   ```python
   # ログイン状態を確認
   current_url = page.url
   if 'login' in current_url:
       raise Exception("セッションが無効です")
   ```

### 問題4: セッションが期限切れ

**症状**:
```
[ERROR] ログインページにリダイレクトされました
```

**対処法**:
```python
# Cookieを再取得
from sourcing.sources.sellersprite.auth_manager import get_authenticated_browser

# headless=Falseで起動して手動ログイン
browser, context, page = await get_authenticated_browser(headless=False)

# ログイン後、Cookieを保存
await save_cookies(context, "sourcing/data/sellersprite_cookies.json")
```

---

## 関連ファイル

| ファイルパス | 説明 |
|-------------|------|
| `sourcing/sources/sellersprite/auth_manager.py` | 認証マネージャー |
| `sourcing/sources/sellersprite/extractors/product_research_extractor.py` | 商品リサーチ抽出器 |
| `sourcing/scripts/extract_by_categories.py` | カテゴリ別抽出スクリプト |
| `sourcing/scripts/analyze_popular_categories.py` | 人気カテゴリ分析 |
| `test_direct_url_asin_extraction.py` | 直接URL方式テスト |

---

## まとめ

### 重要なポイント

1. **認証**: 既存の `get_authenticated_browser()` を使用するのが最も簡単
2. **URL構築**: `build_product_research_url()` 関数で完全なURLを構築
3. **カテゴリ**: nodeIdPathsは事前定義されておらず、ページから動的に抽出
4. **抽出**: `ProductResearchExtractor` を使えば認証からASIN抽出までワンストップ

### ベストプラクティス

- Cookie管理を適切に行い、頻繁なログインを避ける
- スクリーンショットを撮影してデバッグを容易にする
- タイムアウトとエラーハンドリングを適切に実装
- カテゴリ情報は一度取得したら `popular_categories.json` に保存して再利用

---

**ドキュメント管理**:
- バージョン: 1.0
- 最終更新: 2025-11-27
- メンテナ: ecauto開発チーム
