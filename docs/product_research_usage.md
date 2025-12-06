# SellerSprite 商品リサーチ ASIN抽出 - 使用方法

最終更新: 2025-01-23

## 概要

SellerSpriteの商品リサーチ機能を使用して、フィルター条件に合致するASINを自動抽出します。

TypeScript実装（`get_sellersprite_asins.spec.ts`）をPythonに移植し、ecautoプロジェクトに統合しました。

---

## 基本的な使用方法

### デフォルト設定で実行

```bash
cd C:\Users\hiroo\Documents\GitHub\ecauto
.\venv\Scripts\activate

python sourcing\scripts\extract_asins.py \
  --pattern product_research
```

**デフォルト条件:**
- 月間販売数 最小値: 300
- 価格 最小値: 2500円
- AMZ（Amazon販売）: 有効
- FBA（Fulfilled by Amazon）: 有効
- 取得件数: 100件

---

### カスタム条件で実行

```bash
python sourcing\scripts\extract_asins.py \
  --pattern product_research \
  --sales-min 500 \
  --price-min 3000 \
  --limit 50
```

---

### 出力ファイル指定

```bash
python sourcing\scripts\extract_asins.py \
  --pattern product_research \
  --sales-min 300 \
  --price-min 2500 \
  --output data\asins_20250123.txt
```

---

## パラメータ一覧

| パラメータ | 説明 | デフォルト値 | 必須 |
|-----------|------|-------------|------|
| `--pattern` | 抽出パターン（`product_research` を指定） | - | ✅ |
| `--sales-min` | 月間販売数の最小値 | 300 | - |
| `--price-min` | 価格の最小値（円） | 2500 | - |
| `--amz` | Amazon販売のみ | True | - |
| `--fba` | FBAのみ | True | - |
| `--limit` | 取得件数（最大100） | 100 | - |
| `--output` | 出力ファイルパス | - | - |

---

## 実装の仕組み

### 処理フロー

1. **Cookie認証**
   - `sourcing/data/sellersprite_cookies.json` から認証情報を読み込み
   - 手動ログイン不要で自動ログイン

2. **商品リサーチページに遷移**
   - URL: `https://www.sellersprite.com/v3/product-research`

3. **フィルター条件を設定**
   - 月間販売数の最小値を入力
   - 価格の最小値を入力
   - AMZ、FBAにチェック

4. **フィルター実行**
   - 「フィルター開始」ボタンをクリック

5. **ページサイズを100件に変更**
   - URLパラメータに `size=100` を追加

6. **ASINを抽出**
   - テーブルの各行から `ASIN: [10文字の英数字]` パターンで抽出
   - 重複除去

7. **データベースに保存**
   - `sourcing_candidates` テーブルに候補として保存
   - `extraction_logs` テーブルにログ記録

---

## 実装ファイル

| ファイル | 説明 |
|---------|------|
| `get_sellersprite_asins.spec.ts` | TypeScript実装（Playwright） |
| `sourcing/sources/sellersprite/extractors/product_research_extractor.py` | Python実装 |
| `sourcing/scripts/extract_asins.py` | メイン実行スクリプト |

---

## データベースへの保存

抽出されたASINは自動的に以下のテーブルに保存されます：

### sourcing_candidates テーブル

```sql
SELECT * FROM sourcing_candidates
WHERE source = 'sellersprite'
ORDER BY discovered_at DESC;
```

### extraction_logs テーブル

```sql
SELECT * FROM extraction_logs
WHERE extraction_type = 'product_research'
ORDER BY started_at DESC;
```

---

## トラブルシューティング

### Cookie期限切れエラー

**エラーメッセージ:**
```
有効な Cookie がありません
```

**対処法:**
```bash
# 手動ログインでCookieを更新
python sourcing\sources\sellersprite\auth_manager.py login
```

### ASINが0件

**原因:**
- フィルター条件が厳しすぎる
- ページの読み込みが完了していない

**対処法:**
- `--sales-min`, `--price-min` の値を調整
- スクリーンショットを確認（`sourcing/data/screenshots/`）

---

## 応用例

### 高利益商品を狙う

```bash
python sourcing\scripts\extract_asins.py \
  --pattern product_research \
  --sales-min 500 \
  --price-min 5000 \
  --limit 100
```

### 低価格帯で回転率重視

```bash
python sourcing\scripts\extract_asins.py \
  --pattern product_research \
  --sales-min 1000 \
  --price-min 1000 \
  --limit 100
```

---

## 次のステップ

### Phase 2: LLMによるパラメータ自動生成

プロンプトで抽出条件を指定：

```bash
python sourcing\scripts\extract_asins_smart.py \
  --prompt "直近で販売数が急増している2500円以上のおもちゃを100件抽出"
```

→ LLMが自動的に `--sales-min 500 --price-min 2500` などのパラメータを生成

---

## 参考

- [実装計画](sourcing_plan.md)
- [Phase 1 Day 2 完了レポート](phase1_day2_complete.md)
- [SellerSprite公式ドキュメント](https://www.sellersprite.com/)
