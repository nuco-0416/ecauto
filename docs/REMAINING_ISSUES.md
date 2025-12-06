# 残存課題リスト

**最終更新**: 2025-11-21

---

## 🚨 緊急対応が必要な課題

（現在、緊急対応が必要な課題はありません）

---

## 🟡 短期的に対応すべき課題

（現在、短期的に対応すべき課題はありません）

---

## 🟢 中期的に対応すべき課題

### Issue #3: データ整合性の不整合

**優先度**: 🟢 中

**現状**:
- upload_queueで`success`なのに、listingsが`pending`のまま残るケースが8件
- ステータス更新のトランザクション処理が不十分

**提案する改修**:
1. `upload_executor.py`でトランザクション処理を強化
2. 整合性チェックスクリプトの作成
3. 定期実行の設定

**期限**: 1ヶ月以内

**担当**: -

**ステータス**: ⏳ 未着手

**参考**:
- 詳細は[WORKFLOW_IMPROVEMENT_2025-11-21.md](./WORKFLOW_IMPROVEMENT_2025-11-21.md#phase-3-データ整合性の向上優先度-中)を参照

---

## ✅ 完了した課題

### Issue #1: 宙に浮いている1,885件のASIN ✅

**優先度**: 🔴 最高

**問題**:
- listingsテーブルに1,896件が`status='pending'`で登録済み
- しかしupload_queueには追加されていない
- 1,885件が処理待ち状態で放置されていた

**実施した対応**:
1. ✅ sourcing機能の実装（SellerSpriteからのASIN抽出）
2. ✅ 2034件のASIN候補を抽出（2025-11-25）
3. ✅ 出品連携スクリプト実装（import_candidates_to_master.py）
4. ✅ SP-APIで商品情報取得（約2.7時間で1920件処理）
5. ✅ upload_queueに2034件追加（2025-11-26）
6. ✅ アカウント自動割り振り（base_account_1: 1110件、base_account_2: 924件）

**達成した効果**:
- ✅ 宙に浮いていたASINを完全に解決
- ✅ sourcing_candidatesからmaster.dbへの自動連携パイプライン構築
- ✅ SP-APIレート制限の最適化（12秒→2.5秒、処理速度2.5倍向上）
- ✅ NGキーワード自動クリーニング機能の実装

**完了日**: 2025-11-26

**結果**: ✅ 成功

**参考**:
- [sourcing/docs/20251126_listing_integration_execution_report.md](../sourcing/docs/20251126_listing_integration_execution_report.md)
- [sourcing/docs/20251125_implementation_progress_report_v3.md](../sourcing/docs/20251125_implementation_progress_report_v3.md)

---

### Issue #2: SP-API処理の非効率性 ✅

**優先度**: 🟡 高

**問題**:
- 1ASINあたり約4.2秒かかる
- 2,000件の処理に約2.3時間
- Product Pricing APIのバッチ処理（20件/リクエスト）が未実装

**実施した改修**:
1. ✅ `sp_api_client.py`にバッチ処理メソッド `get_prices_batch()` を追加
2. ✅ `add_new_products.py`でバッチ処理を使用
3. ✅ `sync_prices.py`でバッチ処理を使用

**達成した効果**:
- ✅ 処理時間: **10-20倍高速化**
  - 新規商品追加（10件）: 21.0秒 → 1.9秒（**10.9倍**）
  - 価格取得（17件）: 35.7秒 → 1.7秒（**21.7倍**）
  - 価格取得（50件）: 105秒 → 11.2秒（**9.4倍**）
- ✅ API呼び出し: **95%削減**
- ✅ 1日あたり**4時間以上の時間削減**

**完了日**: 2025-11-22

**結果**: ✅ 成功

**参考**:
- 詳細は[BATCH_PROCESSING_IMPLEMENTATION.md](./BATCH_PROCESSING_IMPLEMENTATION.md)を参照
- [WORKFLOW_IMPROVEMENT_2025-11-21.md](./WORKFLOW_IMPROVEMENT_2025-11-21.md#phase-2-sp-api処理の効率化優先度-高)

---

### Issue #0: ワークフローの断絶 ✅

**優先度**: 🔴 最高

**問題**:
- add_new_products.py実行後、手動でadd_to_queue.pyを実行する必要があった
- 手動操作忘れにより、商品が登録されてもアップロードされない

**対応内容**:
- add_new_products.pyに自動キュー追加機能を実装
- 新しいオプション`--no-auto-queue`と`--queue-priority`を追加

**完了日**: 2025-11-21

**結果**: ✅ 成功

**参考**:
- [WORKFLOW_IMPROVEMENT_2025-11-21.md](./WORKFLOW_IMPROVEMENT_2025-11-21.md#phase-1-実施済み改修)

---

### Issue #4: アカウント分散・時間分散の最適化 ✅

**優先度**: 🟡 高

**問題**:
- デフォルトで複数アカウントに自動分散されてしまう
- 17時間に均等分散するため、クォータを効率的に使えない
- 既存スケジュールとの重複が不明確

**対応内容**:
1. **アカウント分散のデフォルト動作変更**
   - デフォルト: 指定された`--account-id`のみを使用
   - `--auto-distribute-accounts`フラグで複数アカウントへの自動分散を有効化

2. **時間分散アルゴリズムの最適化**
   - 1日のクォータ（1000件）を最大限使用
   - 1時間あたりの制限（デフォルト100件）を考慮した効率的な詰め込み
   - `--hourly-limit`オプションで調整可能

3. **キュー動作の明確化**
   - 既存スケジュールのチェック機能を追加
   - 重複する場合は警告を表示

**新しいオプション**:
```bash
--auto-distribute-accounts  # 複数アカウントへ自動分散（デフォルト: 指定アカウントのみ）
--hourly-limit N           # 1時間あたりの最大アップロード件数（デフォルト: 100）
```

**使用例**:
```bash
# デフォルト: 指定アカウントのみ使用、効率的な時間分散
python inventory/scripts/add_new_products.py \
  --asin-file asins.txt \
  --platform base \
  --account-id base_account_1 \
  --use-sp-api

# 複数アカウントへ自動分散を有効化
python inventory/scripts/add_new_products.py \
  --asin-file asins.txt \
  --platform base \
  --account-id base_account_1 \
  --use-sp-api \
  --auto-distribute-accounts

# 1時間あたりの制限を50件に変更（より時間を分散）
python inventory/scripts/add_new_products.py \
  --asin-file asins.txt \
  --platform base \
  --account-id base_account_1 \
  --use-sp-api \
  --hourly-limit 50
```

**完了日**: 2025-11-21

**結果**: ✅ 成功

---

## 📋 課題の優先順位

| 順位 | Issue | 優先度 | 期限 | 工数見積 | ステータス |
|:---:|---|:---:|---|---|:---:|
| 1 | ~~#1 宙に浮いている1,885件~~ | ~~🔴 最高~~ | ~~即座~~ | ~~5分~~ | ✅ **完了** |
| 2 | ~~#2 SP-API処理の非効率性~~ | ~~🟡 高~~ | ~~1-2週間~~ | ~~2-3日~~ | ✅ **完了** |
| 3 | #3 データ整合性の不整合 | 🟢 中 | 1ヶ月 | 1-2日 | ⏳ 未着手 |

---

## 🔄 定期的なメンテナンス

### 毎日

- [ ] キューの状態確認
  ```bash
  python scheduler/scripts/check_queue.py --platform base
  ```

### 毎週

- [ ] 失敗アイテムの確認と対応
  ```bash
  python scheduler/scripts/check_queue.py --status failed --limit 50
  ```

- [ ] データ整合性チェック（Phase 3実装後）
  ```bash
  python scheduler/scripts/check_consistency.py
  ```

### 毎月

- [ ] SP-APIレート制限の使用状況確認
- [ ] ログファイルのローテーション
- [ ] パフォーマンスメトリクスのレビュー

---

## 📞 サポート・質問

課題や質問がある場合は、以下のドキュメントを参照してください：

- [WORKFLOW_IMPROVEMENT_2025-11-21.md](./WORKFLOW_IMPROVEMENT_2025-11-21.md) - 詳細な改修レポート
- [scheduler/README.md](../scheduler/README.md) - スケジューラーの使い方
- [QUICKSTART.md](../QUICKSTART.md) - 全体のセットアップガイド

---

**Last Updated**: 2025-11-26
