# ISSUE #035: BASE get_item APIエンドポイント形式の修正

**作成日**: 2025-12-13
**優先度**: 🔴 高
**ステータス**: ✅ 解決済み
**関連**: 在庫同期スクリプト (`sync_stock_visibility.py`)

---

## 📋 概要

在庫同期スクリプト実行時に大量の「在庫復活エラー」が発生。
`get_item`メソッドがBASE APIの仕様に反したリクエスト形式を使用していたことが原因。

**エラーメッセージ**:
```
2025-12-13 16:32:20,021 - ERROR - [STOCK] B0FJS24NC1 - 在庫復活エラー: 400 Client Error: Bad Request for url: https://api.thebase.in/1/items/detail?item_id=127634915
```

---

## 🔍 根本原因

### 問題のコード

**ファイル**: `platforms/base/core/api_client.py`
**メソッド**: `get_item` (行315-337)

```python
# 修正前（誤り）
def get_item(self, item_id: str) -> Dict[str, Any]:
    url = f"{self.BASE_URL}/items/detail"
    params = {'item_id': item_id}
    response = self._request('GET', url, params=params)
    response.raise_for_status()
    return response.json()
```

**問題点**:
- `GET /items/detail?item_id=xxx` としてクエリパラメータで渡している
- BASE API公式仕様では `item_id` はURLパスに含める必要がある

### BASE API公式仕様

**エンドポイント**: `GET /1/items/detail/:item_id`

参照: https://docs.thebase.in/api/items/detail

---

## 🛠️ 実施した修正

**ファイル**: `platforms/base/core/api_client.py`
**メソッド**: `get_item` (行315-337)

```python
# 修正後（正しい形式）
def get_item(self, item_id: str) -> Dict[str, Any]:
    """
    商品情報を取得

    Args:
        item_id: BASE商品ID

    Returns:
        dict: API応答データ

    Raises:
        requests.exceptions.HTTPError: API呼び出しエラー
    """
    # トークン自動更新チェック
    self._refresh_token_if_needed()

    # 公式API仕様: GET /1/items/detail/:item_id
    url = f"{self.BASE_URL}/items/detail/{item_id}"

    response = self._request('GET', url)
    response.raise_for_status()

    return response.json()
```

### 変更内容

| 項目 | 修正前 | 修正後 |
|------|--------|--------|
| URL形式 | `/items/detail?item_id=xxx` | `/items/detail/{item_id}` |
| パラメータ渡し方 | クエリパラメータ (`params`) | URLパスに含める |

---

## ✅ 検証結果

### テスト実行

**アカウント**: `base_account_3`

```
商品一覧を取得中...
テスト対象 item_id: 127063772

get_item(127063772) を実行中...
成功! 取得した商品情報:
  - title: JVCケンウッド Victor HA-A30T2-V ワイヤレスイヤホン...
  - price: 10530
  - stock: 1
  - visible: 1
```

**結果**: ✅ 正常に商品情報を取得できることを確認

---

## 📊 影響範囲

### このメソッドを呼び出している箇所

1. **`inventory/scripts/sync_stock_visibility.py`**
   - `_restore_stock_if_needed` メソッド（行270付近）
   - 在庫復活処理で商品情報を取得する際に使用

### 修正による影響

- ✅ 在庫同期スクリプトの「在庫復活エラー」が解消
- ✅ 他のエンドポイントには影響なし（POST形式のものはbodyで`item_id`を渡す仕様で正しい）

---

## 📝 補足情報

### 他のBASE APIエンドポイントとの違い

| エンドポイント | メソッド | item_idの渡し方 | 備考 |
|---------------|----------|-----------------|------|
| `/items/detail/:item_id` | GET | URLパス | 今回修正 |
| `/items/edit` | POST | body | 現状で正しい |
| `/items/delete` | POST | body | 現状で正しい |
| `/items/add_image` | POST | body | 現状で正しい |

`get_item`のみがGETメソッドでURLパス形式を使用する仕様となっている。

---

## ✅ ステータス

**解決日**: 2025-12-13
**ステータス**: ✅ 完全解決

**動作確認**:
- ✅ `get_item` APIが正常に動作することを確認
- ✅ 400 Bad Request エラーが解消

**残課題**: なし
