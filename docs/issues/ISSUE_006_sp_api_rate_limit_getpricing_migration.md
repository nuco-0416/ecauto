# Issue #006: SP-APIレート制限違反とgetPricing APIへの移行

**ステータス**: 🟢 完了（Phase 1のみ）
**発生日**: 2025-11-23
**完了日**: 2025-11-24
**優先度**: 🔴 最高（ビジネスクリティカル）
**担当**: Claude Code
**影響範囲**: 全商品（約10,000件）の価格・在庫同期処理

---

## 問題の詳細

### 症状

**現象:**
- 価格・在庫同期処理で**QuotaExceeded エラーが多発**
- バッチ処理の途中（約53%地点）でエラーが連続発生
- サービスが異常停止し、同期処理が完了しない

**エラー内容:**
```
エラー: バッチリクエスト失敗（バッチ 80/489）
- QuotaExceeded: You exceeded your quota for the requested resource.

エラー: バッチリクエスト失敗（バッチ 247/489）
エラー: バッチリクエスト失敗（バッチ 248/489）
エラー: バッチリクエスト失敗（バッチ 249/489）
...（連続発生）
```

**深刻な影響:**
- ⚠️ **価格情報の更新失敗**: 約半数の商品で価格が取得できない
- ⚠️ **サービスの停止**: デーモンプロセスが異常終了
- ⚠️ **処理時間の長大化**: 489バッチ × 10秒 = 約81分/回

### 具体例

**サービスステータス:**
```bash
$ nssm status EcAutoSyncInventory
SERVICE_STOPPED  # ← QuotaExceededエラーで停止
```

**ログ出力:**
```
[重要] SP-APIバッチで最新価格・在庫を取得中...
  対象商品数: 9,780件
  バッチサイズ: 20件/リクエスト
  予想リクエスト数: 489回

...（処理中）...

エラー: バッチリクエスト失敗（バッチ 247/489）- QuotaExceeded
エラー: バッチリクエスト失敗（バッチ 248/489）- QuotaExceeded
（以降、処理が完了せず停止）
```

---

## 問題が発覚した経緯

### タイムライン

1. **2025-11-23 20:24** - デーモン起動（実行間隔: 3時間）
2. **2025-11-23 20:24-21:16** - バッチ処理実行中
3. **バッチ80番目** - 最初のQuotaExceededエラー発生
4. **バッチ247-258番目** - QuotaExceededエラーが連続発生
5. **処理停止** - サービスが停止、ログ更新なし
6. **調査開始** - QuotaExceeded原因とAPI選択の問題を発見

### 発見の経緯

```bash
# サービスが停止している
$ nssm status EcAutoSyncInventory
SERVICE_STOPPED

# ログでQuotaExceededエラーを確認
$ tail -100 logs/sync_inventory_stdout.log | grep "QuotaExceeded"
エラー: バッチリクエスト失敗 - QuotaExceeded
（多数のエラー）

# レート制限の設定を確認
$ grep "min_interval" integrations/amazon/sp_api_client.py
default_interval = 2.5  # ← 公式レート（10秒）の1/4しか待っていない
```

---

## 問題解決のために参照したコード・ドキュメント

### 関連ファイル

#### 1. integrations/amazon/sp_api_client.py (行47-56, 434-590)

**問題のコード:**
```python
# レート制限管理（ISSUE #005対応）
# 公式レート: getItemOffersBatch = 0.1 req/sec (10秒/リクエスト)
# ※2023年7月10日以降、0.5 req/sec から 0.1 req/sec に変更
# 参考: https://developer-docs.amazon.com/sp-api/docs/product-pricing-api-rate-limits
# 注: バッチ処理の待機ロジック修正により、以前の2秒間隔でも問題なく動作
#     念のため余裕を持たせて2.5秒に設定
self.last_request_time = 0
default_interval = 2.5  # 以前の設定（2秒）+ 余裕0.5秒  ← 問題箇所
self.min_interval = float(os.getenv('SP_API_MIN_INTERVAL', default_interval))
```

**問題点:**
- コメントには「10秒/リクエスト」と正しく記載
- しかし実装は**2.5秒**（公式の1/4）
- 公式レート制限に違反 → QuotaExceeded

**使用中のAPI:**
```python
def get_prices_batch(self, asins: List[str], batch_size: int = 20):
    """
    getItemOffersBatch() を使用

    レート制限:
    - 0.1リクエスト/秒（10秒に1回）
    - バッチサイズ: 最大20件/リクエスト
    """
```

**取得データ:**
```python
# 詳細なオファー情報（重いデータ）
- 出品者全員のリスト
- 配送日（maximumHours, availabilityType）
- 送料（Shipping.Amount）
- Prime情報（PrimeInformation.IsPrime）
- FBA情報（IsFulfilledByAmazon）
- コンディション詳細（SubCondition）
```

#### 2. platforms/base/scripts/sync_prices.py (行272-349)

**実装内容:**
```python
# ISSUE #005対応: キャッシュをスキップして、常に全件をSP-APIバッチで取得
print(f"\n[重要] SP-APIバッチで最新価格・在庫を取得中...")
batch_count = (len(listings) + 19) // 20
# SP-APIレート: 0.1 req/sec (10秒/リクエスト) + 余裕2秒 = 12秒/リクエスト
estimated_seconds = batch_count * 12  # ← 期待値は12秒だが実際は2.5秒

batch_results = self.sp_api_client.get_prices_batch(asins, batch_size=20)
```

#### 3. 公式ドキュメント

**URL**: https://developer-docs.amazon.com/sp-api/docs/product-pricing-api-rate-limits

**レート制限（Product Pricing API v0）:**

| Operation | Rate | Burst | 実質速度 |
|-----------|------|-------|---------|
| **getItemOffersBatch** | 0.1 req/sec | 1 | 10秒に1回 |
| **getPricing** | 0.5 req/sec | 1 | 2秒に1回 |
| getCompetitivePricing | 0.5 req/sec | 1 | 2秒に1回 |
| getItemOffers | 0.5 req/sec | 1 | 2秒に1回 |

---

## 根本原因の分析

### 原因1: レート制限の実装ミス

**設計上の意図:**
- 公式レート: 0.1 req/sec（10秒に1回）
- 余裕を持って12秒間隔で実行

**実際の実装:**
- `min_interval = 2.5秒`
- 公式レートの**4倍速**でリクエスト
- Amazon側でクォータ超過を検知 → エラー

### 原因2: API選択の問題

**現在使用中:** `getItemOffersBatch`
- **取得データ**: 出品者全員の詳細情報（重い）
- **レート制限**: 0.1 req/sec（厳しい）
- **処理時間**: 489バッチ × 10秒 = **約81分**
- **必要性**: 詳細なフィルタリング（3日以内配送 AND 送料無料）のため

**実際の要件:**
- 価格と在庫状況のみ必要
- フィルタリング条件（3日以内配送 AND 送料無料）は**ビジネス要件として必須**
- しかしPrime商品のカート価格は高確率でこれらの条件を満たす

**適切なAPI:** `getPricing`
- **取得データ**: カート価格、最安値（軽い）
- **レート制限**: 0.5 req/sec（緩い）
- **処理時間**: 489バッチ × 2秒 = **約16分**（5倍高速）
- **制限**: 詳細なフィルタリング情報は取得不可

### 原因3: フィルタリング要件とAPI機能のミスマッチ

**ビジネス要件（必須）:**
- 3日以内配送
- 送料無料
- 新品のみ
- 招待制除外

**getItemOffersBatch の利点:**
- ✅ 全ての条件でフィルタリング可能
- ❌ レート制限が厳しい（10秒に1回）
- ❌ 処理時間が長い（81分）

**getPricing の特徴:**
- ❌ 詳細なフィルタリング情報が取得不可
- ✅ レート制限が緩い（2秒に1回）
- ✅ 処理時間が短い（16分）
- 📊 カート価格は統計的に条件を満たす可能性が高い

---

## 解決方法

### 設計方針

**2段階のアプローチ:**

1. **短期対応（緊急）**: レート制限の修正
   - `min_interval = 2.5` → `12.0` に変更
   - QuotaExceededエラーを解消
   - 処理時間: 約81分（変わらず）

2. **中長期対応（推奨）**: getPricing APIへの移行
   - `getItemOffersBatch` → `getPricing` に変更
   - 処理時間: 約81分 → **約16分**（5倍高速）
   - レート制限違反のリスク低減
   - カート価格を基準とし、統計的にフィルタリング条件を満たすと判断

### Phase 1: レート制限の緊急修正（短期対応）

**目的**: QuotaExceededエラーを即座に解消

**修正ファイル:** `integrations/amazon/sp_api_client.py`

**修正内容:**
```python
# 修正前
default_interval = 2.5  # 以前の設定（2秒）+ 余裕0.5秒

# 修正後
default_interval = 12.0  # 公式レート10秒 + 余裕2秒
```

**影響範囲:**
- 処理時間: 約16分（現状の推定値） → 約81分
- QuotaExceededエラー: 解消
- サービス停止: 解消

**実装時間:** 5分

### Phase 2: getPricing APIへの移行（中長期対応）

**目的**: 処理速度を5倍向上、レート制限違反のリスク低減

**新規実装:** `integrations/amazon/sp_api_client.py`

**実装内容:**
```python
def get_pricing_batch(self, asins: List[str], batch_size: int = 20) -> Dict[str, Dict[str, Any]]:
    """
    複数商品の価格を取得（getPricing API使用）

    getItemOffersBatch との違い:
    - レート制限: 0.5 req/sec（5倍速い）
    - 取得データ: カート価格、最安値のみ（軽量）
    - 処理時間: 489バッチ × 2秒 = 約16分

    Args:
        asins: ASINのリスト
        batch_size: 1バッチあたりのASIN数（デフォルト: 20、最大: 20）

    Returns:
        dict: ASIN別の価格情報
            {
                'ASIN1': {'price': 1234, 'in_stock': True},
                'ASIN2': {'price': None, 'in_stock': False},
                ...
            }
    """
    if batch_size > 20:
        print(f"警告: バッチサイズが20を超えています。20に制限します。")
        batch_size = 20

    results = {}

    # ASINをバッチに分割
    batches = [asins[i:i + batch_size] for i in range(0, len(asins), batch_size)]

    products_client = Products(
        credentials=self.credentials,
        marketplace=self.marketplace
    )

    for batch_idx, batch_asins in enumerate(batches, 1):
        # レート制限待機（getPricing: 0.5 req/sec = 2秒/リクエスト）
        # 余裕を持って2.5秒
        self._wait_for_rate_limit()

        try:
            # getPricing APIを呼び出し
            response = products_client.get_pricing(
                asin_list=batch_asins,
                item_type='Asin',
                item_condition='New'
            )

            if hasattr(response, 'payload'):
                payload = response.payload

                for item in payload:
                    asin = item.get('ASIN')

                    if not asin:
                        continue

                    # Product pricing情報を取得
                    product = item.get('Product', {})
                    offers = product.get('Offers', [])

                    if offers:
                        # BuyBox価格を優先、なければ最安値
                        buybox_price = None
                        lowest_price = None

                        for offer in offers:
                            offer_type = offer.get('OfferType')
                            buying_price = offer.get('BuyingPrice', {})
                            listing_price = buying_price.get('ListingPrice', {})
                            amount = listing_price.get('Amount')

                            if offer_type == 'BuyBox' and amount is not None:
                                buybox_price = amount

                            if offer_type == 'Lowest' and amount is not None:
                                lowest_price = amount

                        # BuyBox価格を優先、なければ最安値
                        final_price = buybox_price if buybox_price else lowest_price

                        if final_price:
                            results[asin] = {
                                'price': final_price,
                                'in_stock': True
                            }
                        else:
                            results[asin] = {
                                'price': None,
                                'in_stock': False
                            }
                    else:
                        # オファーなし（在庫切れ）
                        results[asin] = {
                            'price': None,
                            'in_stock': False
                        }

        except Exception as e:
            print(f"  エラー: バッチリクエスト失敗（バッチ {batch_idx}/{len(batches)}）- {e}")
            # 失敗したバッチのASINにはNoneを設定
            for asin in batch_asins:
                if asin not in results:
                    results[asin] = None

    return results
```

**修正ファイル:** `platforms/base/scripts/sync_prices.py`

**修正内容:**
```python
# 修正前
batch_results = self.sp_api_client.get_prices_batch(asins, batch_size=20)

# 修正後
batch_results = self.sp_api_client.get_pricing_batch(asins, batch_size=20)
```

**レート制限設定の調整:**
```python
# getPricing 用のレート制限
# 公式: 0.5 req/sec (2秒に1回)
# 実装: 余裕を持って 2.5秒に設定
default_interval_get_pricing = 2.5
```

**注意事項:**
- getPricing APIでは詳細なフィルタリング（3日以内配送、送料無料）の情報が取得できない
- これらの条件は**ビジネス要件として必須**
- ただし、カート価格は統計的に高確率でPrime商品（＝送料無料、迅速配送）である
- 代替戦略: カート価格を基準とし、フィルタリング条件を満たすと判断

### Phase 3: フィルタリング戦略の見直し

**問題点:**
- getPricing APIでは配送日、送料の情報が取得できない
- フィルタリング条件（3日以内配送 AND 送料無料）が適用できない

**採用する戦略: getPricingのみ + 統計的アプローチ**

1. **getPricing で価格取得**（全商品）
   - カート価格（BuyBox価格）を優先取得
   - カート価格がなければ最安値を取得

2. **統計的にフィルタリング条件を推定**
   - **前提**: カート価格 = 高確率で「Prime、FBA、送料無料」
   - Amazonのカート獲得アルゴリズムは、Prime/FBA/送料無料を優遇
   - 過去データから条件適合率を算出（検証フェーズで実施）

3. **精度検証**
   - サンプリング調査で一致率を確認
   - 一致率95%以上であれば採用

**推奨理由:**
- カート価格は高確率でPrime、FBA、送料無料を満たす
- 処理速度が5倍向上（81分 → 16分）
- レート制限違反のリスクが大幅に低減

---

## 実装計画

### タイムライン

| Phase | 作業内容 | 所要時間 | 優先度 |
|-------|---------|---------|-------|
| 1 | レート制限の緊急修正 | 30分 | 🔴 緊急 |
| 2 | getPricing API実装 | 3時間 | 🟡 推奨 |
| 3 | フィルタリング戦略の検証 | 2時間 | 🟡 推奨 |
| 4 | テスト実行（dry-run） | 1時間 | 必須 |
| 5 | 本番デプロイ | 30分 | 必須 |
| **合計** | **7時間** | |

### Phase別詳細

#### Phase 1: レート制限の緊急修正（最優先）

**目的:** QuotaExceededエラーを即座に解消

**作業内容:**
1. `integrations/amazon/sp_api_client.py` の修正
   ```python
   # 行54: default_interval の変更
   default_interval = 12.0  # 公式レート10秒 + 余裕2秒
   ```

2. サービス再起動
   ```bash
   nssm stop EcAutoSyncInventory
   nssm start EcAutoSyncInventory
   ```

3. ログ監視（最初の20分間）
   ```bash
   tail -f logs/sync_inventory_stdout.log | grep "QuotaExceeded\|完了"
   ```

**成功基準:**
- QuotaExceededエラーが発生しない
- バッチ処理が完了する（489/489）

**所要時間:** 30分

#### Phase 2: getPricing API実装

**作業内容:**

1. **get_pricing_batch メソッドの実装**
   - ファイル: `integrations/amazon/sp_api_client.py`
   - 場所: get_prices_batch メソッドの後に追加

2. **レート制限設定の分離**
   ```python
   def __init__(self, credentials: Dict[str, str]):
       # getItemOffersBatch 用
       self.min_interval_item_offers = 12.0  # 10秒 + 余裕2秒

       # getPricing 用
       self.min_interval_get_pricing = 2.5  # 2秒 + 余裕0.5秒

       # デフォルトはgetPricingの間隔を使用
       self.min_interval = self.min_interval_get_pricing
   ```

3. **sync_prices.py の修正**
   ```python
   # 行292: API呼び出しを変更
   batch_results = self.sp_api_client.get_pricing_batch(asins, batch_size=20)
   ```

4. **エラーハンドリングの改善**
   - getPricing APIのレスポンス構造に対応
   - データ欠損時のフォールバック処理

**テスト:**
```bash
# DRY RUN
python platforms/base/scripts/sync_prices.py --dry-run --account-id base_account_1
```

**所要時間:** 3時間

#### Phase 3: フィルタリング戦略の検証

**作業内容:**

1. **サンプリング調査スクリプトの作成**
   ```python
   # scripts/validate_pricing_api.py

   def compare_apis(asin_list):
       """
       getPricing と getItemOffersBatch の結果を比較

       検証項目:
       1. 価格の一致率
       2. カート価格が条件を満たす確率
       3. データ欠損率
       """
       # getPricing で取得
       pricing_results = client.get_pricing_batch(asin_list)

       # getItemOffersBatch で取得（フィルタリングあり）
       offers_results = client.get_prices_batch(asin_list)

       # 比較分析
       match_rate = calculate_match_rate(pricing_results, offers_results)

       return {
           'match_rate': match_rate,
           'pricing_coverage': len(pricing_results) / len(asin_list),
           'offers_coverage': len(offers_results) / len(asin_list)
       }
   ```

2. **検証実行**
   - サンプル数: 500件（ランダム抽出）
   - 比較項目: 価格一致率、データカバレッジ

3. **結果分析**
   - 一致率が95%以上 → getPricing 採用
   - 一致率が80-95% → 条件付き採用（監視強化）
   - 一致率が80%未満 → 現行API継続

**所要時間:** 2時間

#### Phase 4: テスト実行

**dry-runテスト:**
```bash
# 1アカウントでテスト
python platforms/base/scripts/sync_prices.py \
  --dry-run \
  --account-id base_account_1 \
  --max-items 100
```

**確認事項:**
- [ ] QuotaExceededエラーが発生しない
- [ ] 処理時間が想定内（100件 → 約1分）
- [ ] 価格データが正しく取得できている
- [ ] キャッシュが正しく更新されている
- [ ] Productsテーブルが更新されている

**所要時間:** 1時間

#### Phase 5: 本番デプロイ

**手順:**
1. サービス停止
   ```bash
   nssm stop EcAutoSyncInventory
   ```

2. コード更新（git pull または手動コピー）

3. サービス起動
   ```bash
   nssm start EcAutoSyncInventory
   ```

4. ログ監視（最初の1サイクル = 約16分）
   ```bash
   tail -f logs/sync_inventory_stdout.log
   ```

5. 動作確認
   - キャッシュファイルの更新確認
   - Productsテーブルの更新確認
   - Chatwork通知の受信確認

**所要時間:** 30分

---

## 期待される効果

### Phase 1（レート制限修正）の効果

**修正前:**
```
┌─────────────────────────────────────────┐
│ getItemOffersBatch使用                  │
│ - レート制限: 2.5秒/リクエスト（違反）  │
│ - QuotaExceeded: 多発                   │
│ - 処理完了率: 約53%                     │
│ - サービス停止: あり                    │
└─────────────────────────────────────────┘
```

**修正後:**
```
┌─────────────────────────────────────────┐
│ getItemOffersBatch使用                  │
│ - レート制限: 12秒/リクエスト（準拠）   │
│ - QuotaExceeded: なし                   │
│ - 処理完了率: 100%                      │
│ - 処理時間: 約81分                      │
│ - サービス停止: なし                    │
└─────────────────────────────────────────┘
```

### Phase 2（getPricing移行）の効果

**移行前（Phase 1完了後）:**
```
┌─────────────────────────────────────────┐
│ getItemOffersBatch使用                  │
│ - レート制限: 0.1 req/sec               │
│ - 処理時間: 約81分/回                   │
│ - 取得データ: 詳細（重い）              │
│ - QuotaExceeded: なし                   │
└─────────────────────────────────────────┘
```

**移行後:**
```
┌─────────────────────────────────────────┐
│ getPricing使用                          │
│ - レート制限: 0.5 req/sec（5倍緩い）    │
│ - 処理時間: 約16分/回（5倍速い）        │
│ - 取得データ: 価格のみ（軽い）          │
│ - QuotaExceeded: リスク大幅減           │
│ - フィルタリング: 統計的アプローチ      │
└─────────────────────────────────────────┘
```

### ビジネスインパクト

| 指標 | Phase 1完了後 | Phase 2完了後 | 改善率 |
|------|--------------|--------------|--------|
| 処理時間 | 81分 | 16分 | 🟢 80%短縮 |
| QuotaExceeded | なし | なし | ✅ 解消 |
| サービス停止 | なし | なし | ✅ 解消 |
| レート制限余裕 | 12秒（公式10秒） | 2.5秒（公式2秒） | 🟢 より安全 |
| API呼び出しコスト | 489回/81分 | 489回/16分 | ➖ 同じ |
| データ更新頻度 | 3時間ごと | 3時間ごと | ➖ 同じ |

---

## リスクと対策

### リスク1: getPricingで詳細情報が取得できない

**懸念:**
- 配送日、送料の情報が取得不可
- フィルタリング条件（3日以内配送 AND 送料無料）が適用不可

**対策:**
- ✅ カート価格は高確率で条件を満たす（統計的アプローチ）
- ✅ サンプリング調査で精度を検証（Phase 3）
- ✅ 一致率95%以上を採用基準とする

**根拠:**
- Amazonのカート獲得アルゴリズムは、Prime/FBA/送料無料を優遇
- カート価格 = 高確率で「Prime、FBA、送料無料、迅速配送」

### リスク2: API移行後の価格データの精度低下

**懸念:**
- getPricingの価格 ≠ フィルタリング後の価格
- ビジネス判断に影響する可能性

**対策:**
- ✅ Phase 3で精度検証（500件サンプル）
- ✅ 一致率95%以上を採用基準とする
- ✅ 一致率が低い場合は現行API継続

### リスク3: レート制限変更によるAPI仕様変更

**懸念:**
- Amazon側でレート制限が変更される可能性
- 将来的にQuotaExceededが再発

**対策:**
- ✅ 環境変数でレート制限を設定可能にする
  ```python
  self.min_interval = float(os.getenv('SP_API_MIN_INTERVAL', default_interval))
  ```
- ✅ ログで実際のレート制限を監視
- ✅ QuotaExceeded発生時は自動的にバックオフ

### リスク4: 処理時間延長による影響（Phase 1のみ）

**懸念:**
- 81分/回 → 3時間サイクルに対して余裕が少ない
- 処理遅延のリスク

**対策:**
- ✅ Phase 2（getPricing移行）で16分に短縮
- ✅ 営業時間外は処理スキップ（オプション）

---

## テスト計画

### テストケース

#### TC-1: レート制限修正の検証

**前提条件:**
- `min_interval = 12.0` に修正済み

**操作:**
1. サービス起動
2. 100件のバッチ処理を実行（dry-run）

**期待結果:**
- ✅ QuotaExceededエラーが発生しない
- ✅ 100件 × 12秒 = 約20分で完了
- ✅ 全100件の価格が取得できる

#### TC-2: getPricing APIの動作確認

**前提条件:**
- `get_pricing_batch` メソッド実装済み

**操作:**
1. テストスクリプトで20件のASINを取得
   ```python
   results = client.get_pricing_batch(['B0006L0120', ...])
   ```

**期待結果:**
- ✅ 20件全てのデータが取得できる
- ✅ レスポンス構造が正しい
- ✅ 価格、在庫状況が含まれる

#### TC-3: API比較検証（精度確認）

**前提条件:**
- 500件のASINリスト準備

**操作:**
1. getPricing で取得
2. getItemOffersBatch で取得（フィルタリングあり）
3. 結果を比較

**期待結果:**
- ✅ 価格一致率: 95%以上
- ✅ データカバレッジ（getPricing）: 90%以上
- ✅ データカバレッジ（getItemOffersBatch）: 70%以上

#### TC-4: エンドツーエンドテスト

**前提条件:**
- getPricing API実装完了
- sync_prices.py 修正完了

**操作:**
1. dry-runで全件実行
   ```bash
   python platforms/base/scripts/sync_prices.py --dry-run
   ```

**期待結果:**
- ✅ 処理時間: 約16分
- ✅ QuotaExceededエラー: なし
- ✅ キャッシュ更新: 全件
- ✅ Productsテーブル更新: 全件
- ✅ 価格変動検知: 正常
- ✅ Chatwork通知: 正常

---

## 関連Issue

- **ISSUE #005**: キャッシュTTL機構の未実装による価格・在庫更新の停止
  - 関連: ISSUE #005でバッチ処理を実装したが、レート制限が正しく設定されていなかった

---

## セッション用プロンプト

次回この問題または類似問題が発生した場合、以下のプロンプトで問題解決を再開：

```
SP-API QuotaExceededエラーが発生しています。

症状:
- バッチ処理でQuotaExceededエラーが多発
- サービスが停止している
- 価格データが取得できない

確認すべき点:
1. レート制限の設定（integrations/amazon/sp_api_client.py）
2. 使用中のAPI（getItemOffersBatch vs getPricing）
3. サービスステータス（nssm status EcAutoSyncInventory）
4. ログファイル（logs/sync_inventory_stdout.log）

参照ドキュメント:
- docs/issues/ISSUE_006_sp_api_rate_limit_getpricing_migration.md
- https://developer-docs.amazon.com/sp-api/docs/product-pricing-api-rate-limits

対応手順:
1. レート制限の確認（公式: getItemOffersBatch = 10秒、getPricing = 2秒）
2. 緊急対応: min_interval を修正（2.5秒 → 12秒）
3. 推奨対応: getPricing APIへの移行（処理時間5倍短縮）
4. テスト実行（dry-run）
5. 本番デプロイ
```

---

## 実装結果（2025-11-24）

### セッション作業サマリー

**実装範囲**: Phase 1のみ完了（レート制限の修正）

**目標変更の経緯**:
- 当初はPhase 1〜3の完全実装を計画
- Phase 2（getPricing API移行）の実装中に問題を発見
- SP-API Python SDKの`get_product_pricing_for_asins`メソッドがオファー情報を返さないことが判明
- ユーザーと協議の結果、Phase 1のみを実装し、既存の`getItemOffersBatch`を維持する方針に変更

### 実装内容

#### 修正ファイル

1. **integrations/amazon/sp_api_client.py**
   - レート制限: `2.5秒 → 12.0秒` に変更
   - 公式レート（10秒）+ 余裕2秒 = 12秒/リクエスト
   - コメント更新: ISSUE #006対応を明記

2. **platforms/base/scripts/sync_prices.py**
   - 予想処理時間の計算を12秒ベースに修正
   - 表示メッセージ更新: 使用API「getItemOffersBatch（安定版）」

#### テスト結果

✅ **60件（3バッチ）テスト**: QuotaExceededエラー 0件
✅ **100件（5バッチ）テスト**: QuotaExceededエラー 0件
✅ **最終確認テスト**: QuotaExceededエラー 0件

**待機時間の実測値**:
- バッチ2〜5: 平均10.5〜11.2秒待機（設定値12秒に対して適切）

#### 処理時間

| 項目 | 修正前 | 修正後 |
|------|--------|--------|
| レート制限 | 2.5秒/バッチ | 12秒/バッチ |
| QuotaExceeded | 多発 | 0件 |
| 全商品処理時間（489バッチ） | エラーで完了せず | 約98分（489 × 12秒） |

### Phase 2実装の試行と問題点

#### 実装を試みたこと

1. **get_pricing_batchメソッドの実装**
   - `get_product_pricing_for_asins` APIを使用
   - フィルタリング条件（新品、送料無料、FBA）を実装
   - `integrations/amazon/sp_api_client.py`に追加（現在は未使用）

2. **レスポンス調査**
   - デバッグ出力でレスポンス構造を確認
   - `Product.Identifiers`のみ含まれ、価格情報（Offers、CompetitivePricing、OfferListings）が一切含まれていないことを発見

#### 判明した問題

**SP-API Python SDKの制約**:
```json
{
  "status": "Success",
  "ASIN": "B0CGWPYCBQ",
  "Product": {
    "Identifiers": {
      "MarketplaceASIN": {
        "MarketplaceId": "A1VC38T7YXB528",
        "ASIN": "B0CGWPYCBQ"
      }
    }
  }
}
```

- `get_product_pricing_for_asins`: 価格情報なし（Identifiersのみ）
- `get_competitive_pricing_for_asins`: 自分で出品している商品のみ取得可能（使用不可）

**結論**: 現状のSP-API Python SDKでは、ドキュメントで説明されていた「カート価格（CompetitivePricing）」と「最安値一覧（OfferListings）」を取得できるAPIメソッドが見つからなかった。

### 将来への対応可能性

#### オプション1: SP-API直接呼び出し

SP-API Python SDKを経由せず、HTTPリクエストで直接APIを呼び出す方法を検討：

**メリット**:
- SDKの制約を受けない
- 公式ドキュメント通りのレスポンスが取得できる可能性

**デメリット**:
- 認証処理を自前で実装する必要がある
- SDKのエラーハンドリング機能が使えない

**実装イメージ**:
```python
import requests

def get_pricing_direct(asins: List[str]):
    """SP-APIに直接HTTPリクエストを送信"""
    headers = {
        'x-amz-access-token': self.access_token,
        'Content-Type': 'application/json'
    }

    url = f"https://sellingpartnerapi-fe.amazon.com/products/pricing/v0/price"
    params = {
        'MarketplaceId': self.marketplace.marketplace_id,
        'Asins': ','.join(asins),
        'ItemType': 'Asin',
        'ItemCondition': 'New'
    }

    response = requests.get(url, headers=headers, params=params)
    # レスポンス処理...
```

#### オプション2: SP-API Python SDKの更新待ち

- SDKのバージョンアップで改善される可能性を待つ
- GitHubで報告・Issue作成を検討

#### オプション3: 別のAPIエンドポイントの調査

SP-API Product Pricing API v0の他のエンドポイントを調査：
- `get_listing_offers`
- `get_featured_offer_expected_price_batch`

#### オプション4: 現状維持（推奨）

**理由**:
- QuotaExceededエラーは解消済み
- 処理は安定して動作
- 処理時間（約98分）は許容範囲内
- フィルタリング条件（送料無料、FBA）も正しく適用されている

**今後のアクション**:
1. 本番環境で数日間の動作確認
2. QuotaExceededが再発しないことを確認
3. 問題なければ現状維持

### 残存する課題

なし（Phase 1で目標達成）

### 次回の改善提案

getPricing APIへの移行は、以下の条件が整った場合に再検討：
1. SP-API Python SDKの更新で価格情報が取得可能になる
2. 直接HTTP呼び出しでの実装が必要と判断される
3. 処理時間の大幅短縮が求められる

---

**作成日**: 2025-11-23
**最終更新**: 2025-11-24
**作成者**: Claude Code
**ステータス**: 🟢 完了（Phase 1のみ）
**優先度**: 🔴 最高（ビジネスクリティカル）
