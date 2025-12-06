# AmazonScraperForEbay.py

# --- ▼▼▼ このブロックをファイルの先頭に追加 ▼▼▼ ---
import sys
import time
from pathlib import Path

# このスクリプト(amazonScraperForEbay.py)の場所からプロジェクトのルートディレクトリ(ama-cari)を特定
# .parent は一つ上の階層に移動することを意味します
# .../scripts -> .../ebay_pj -> .../ama-cari
project_root = Path(__file__).resolve().parent.parent.parent

# am_sp-api ディレクトリへのパスを構築
sp_api_dir = project_root / 'am_sp-api'

# Pythonがモジュールを探す場所のリストに、上記パスを追加
sys.path.append(str(sp_api_dir))
# --- ▲▲▲ 追加はここまで ▲▲▲ ---

import re
from sp_api.api import CatalogItems, Products
from sp_api.base import Marketplaces
from sp_api_credentials import credentials

class AmazonScraperForEbay:
    """
    Amazon SP-APIを利用して商品情報を取得し、eBay出品用にデータを整形するクラス。
    """
    def __init__(self):
        """
        初期化処理。eBay用なのでヤフオク関連の処理は不要。
        """
        pass

    def get_product_info(self, asin):
        """
        ASINを基にAmazonから商品情報を取得する。
        （images, summaries, attributesを含む）
        （QuotaExceededエラーのリトライロジックを追加)        
        """
        # --- ▼ リトライ設定 ▼ ---
        MAX_RETRIES = 3
        RETRY_DELAY_SECONDS = 5 # 待機時間 (秒)
        # --- ▲ リトライ設定 ▲ ---

        for attempt in range(MAX_RETRIES):
            try:
                catalog_client = CatalogItems(marketplace=Marketplaces.JP, credentials=credentials)
                # 取得するデータ項目を指定
                included_data = ['images', 'summaries', 'attributes', 'identifiers']
                result = catalog_client.get_catalog_item(asin, includedData=included_data)
                
                # 成功したら即座に結果を返す (ループ終了)
                return result.payload
            
            except Exception as e:
                error_message = str(e)
                
                # --- ▼ リトライ判定 ▼ ---
                # エラーメッセージに "QuotaExceeded" が含まれるかチェック
                if "QuotaExceeded" in error_message or "rate limit" in error_message.lower():
                    print(f"  -> 警告 (商品情報取得): ASIN={asin} でレート制限(QuotaExceeded)発生。({attempt + 1}/{MAX_RETRIES})")
                    
                    if attempt < MAX_RETRIES - 1:
                        # 最後のリトライでなければ待機
                        print(f"     ... {RETRY_DELAY_SECONDS}秒待機してリトライします。")
                        time.sleep(RETRY_DELAY_SECONDS)
                        continue # ループの次の試行へ
                    else:
                        # リトライ上限に達した場合
                        print(f"  -> ❌ リトライ上限({MAX_RETRIES}回)に達しました。")
                        break # ループを終了
                
                # --- ▼ その他のエラー (リトライしない) ▼ ---
                else:
                    print(f"エラー (商品情報取得): ASIN={asin}, {e}")
                    break # ループを終了 (リトライしない)
            # --- ▲ 例外処理終了 ▲ ---

        # ループが終了した場合 (リトライ失敗 or その他エラー)
        print(f"  -> 最終的に商品情報取得失敗: ASIN={asin}")
        return None

        # try:
        #     catalog_client = CatalogItems(marketplace=Marketplaces.JP, credentials=credentials)
        #     # 取得するデータ項目を指定
        #     included_data = ['images', 'summaries', 'attributes']
        #     result = catalog_client.get_catalog_item(asin, includedData=included_data)
        #     return result.payload
        # except Exception as e:
        #     print(f"エラー (商品情報取得): ASIN={asin}, {e}")
        #     return None

    def get_product_price(self, asin):
        """
        ASINを基にAmazonから価格情報を取得する。
        FBA発送の新品最安値を対象とする。
        (QuotaExceededエラーのリトライロジックを追加)
        """
        # --- ▼ リトライ設定 ▼ ---
        MAX_RETRIES = 3
        RETRY_DELAY_SECONDS = 5 # 待機時間 (秒)
        # --- ▲ リトライ設定 ▲ ---

        for attempt in range(MAX_RETRIES):
            try:
                products_client = Products(credentials=credentials, marketplace=Marketplaces.JP)
                response = products_client.get_item_offers(asin=asin, item_condition="New")
                offers = response.payload.get('Offers', [])

                if not offers:
                    # オファーがない(在庫切れ) -> 成功なのでリトライ不要
                    return {'price': None, 'in_stock': False}

                for offer in offers:
                    is_prime = offer.get('PrimeInformation', {}).get('IsPrime', False)
                    is_fulfilled_by_amazon = offer.get('IsFulfilledByAmazon', False)

                    shipping_time = offer.get('ShippingTime', {})
                    availability_type = shipping_time.get('availabilityType')

                    # Prime対象、FBA発送、かつ「NOW」(即時発送可)のオファーを優先
                    if is_prime and is_fulfilled_by_amazon and availability_type == "NOW":
                        price_amount = offer.get('ListingPrice', {}).get('Amount')
                        # 成功！リトライ不要
                        return {
                            'price': price_amount,
                            'in_stock': True
                        }
                
                # 条件に合うオファーが見つからなかった場合 (予約商品など)
                # -> 成功なのでリトライ不要
                return {'price': None, 'in_stock': False}
            
            except Exception as e:
                error_message = str(e)
                
                # --- ▼ リトライ判定 ▼ ---
                # エラーメッセージに "QuotaExceeded" が含まれるかチェック
                if "QuotaExceeded" in error_message or "rate limit" in error_message.lower():
                    print(f"  -> 警告 (価格情報取得): ASIN={asin} でレート制限(QuotaExceeded)発生。({attempt + 1}/{MAX_RETRIES})")
                    
                    if attempt < MAX_RETRIES - 1:
                        # 最後のリトライでなければ待機
                        print(f"     ... {RETRY_DELAY_SECONDS}秒待機してリトライします。")
                        time.sleep(RETRY_DELAY_SECONDS)
                        continue # ループの次の試行へ
                    else:
                        # リトライ上限に達した場合
                        print(f"  -> ❌ リトライ上限({MAX_RETRIES}回)に達しました。")
                        break # ループを終了
                
                # --- ▼ その他のエラー (リトライしない) ▼ ---
                else:
                    print(f"エラー (価格情報取得): ASIN={asin}, {e}")
                    break # ループを終了 (リトライしない)
            # --- ▲ 例外処理終了 ▲ ---

        # ループが終了した場合 (リトライ失敗 or その他エラー)
        print(f"  -> 最終的に価格情報取得失敗: ASIN={asin}")
        return {'price': None, 'in_stock': False}




        # try:
        #     products_client = Products(credentials=credentials, marketplace=Marketplaces.JP)
        #     response = products_client.get_item_offers(asin=asin, item_condition="New")
        #     offers = response.payload.get('Offers', [])

        #     if not offers:
        #         return {'price': None, 'in_stock': False}

        #     for offer in offers:
        #         is_prime = offer.get('PrimeInformation', {}).get('IsPrime', False)
        #         is_fulfilled_by_amazon = offer.get('IsFulfilledByAmazon', False)

        #         # --- ▼ 予約フィルター ▼ ---
        #         # ShippingTimeからavailabilityTypeを取得 (存在しない場合はNoneになる)
        #         shipping_time = offer.get('ShippingTime', {})
        #         availability_type = shipping_time.get('availabilityType')
        #         # --- ▲ 予約フィルター追加 ▲ ---

        #         # Prime対象かつFBA発送のオファーを優先
        #         if is_prime and is_fulfilled_by_amazon and availability_type == "NOW":
        #             price_amount = offer.get('ListingPrice', {}).get('Amount')
        #             return {
        #                 'price': price_amount,
        #                 'in_stock': True
        #             }
            
        #     # 条件に合うオファーが見つからなかった場合
        #     return {'price': None, 'in_stock': False}
        # except Exception as e:
        #     print(f"エラー (価格情報取得): ASIN={asin}, {e}")
        #     return {'price': None, 'in_stock': False}

    def format_description(self, asin, product_info):
        """
        取得した商品情報から、eBay向けに汎用的なHTML形式商品説明を生成する。
        ヤフオク用の定型文は削除し、商品の基本情報のみで構成。
        """
        summaries = product_info.get('summaries', [{}])[0]
        attributes = product_info.get('attributes', {})
        
        title = summaries.get('itemName', '')
        brand = summaries.get('brandName', '')
        
        # HTML商品説明の組み立て
        description = '<div>\n'
        
        # 管理用にASINを非表示で埋め込む
        description += f'<span style="display:none;">ASIN:{asin}</span>\n'
        
        # 商品タイトル
        description += f"<h2>{title}</h2>\n"
        
        # ブランド情報
        if brand:
            description += f"<p><b>Brand:</b> {brand}</p>\n"

        # 商品の箇条書き（特徴）
        bullet_points = attributes.get('bullet_point', [])
        if bullet_points:
            description += "<h3>Description</h3>\n"
            description += "<ul>\n"
            for point in bullet_points:
                # 'value'キーが存在するか確認
                point_text = point.get('value', '') if isinstance(point, dict) else str(point)
                description += f"<li>{point_text}</li>\n"
            description += "</ul>\n"


        # --- ここから追加 ---

        description += "<h3>Specifications</h3>\n"
        description += "<ul>\n"

        # ⚖️ 重量の取得 (am_get_product_info.pyのロジック)
        try:
            if 'item_weight' in attributes:
                weight_list = attributes['item_weight']
                if weight_list:
                    w = weight_list[0] # 最初の要素を取得
                    value = w.get('value', 'N/A')
                    unit = w.get('unit', '')
                    description += f"<li><b>Item Weight:</b> {value} {unit}</li>\n"
        except (KeyError, TypeError, IndexError):
            pass # エラーでも処理を続行

        # 📦 サイズの取得 (am_get_product_info.pyのロジック)
        try:
            if 'item_dimensions' in attributes:
                dims_list = attributes['item_dimensions']
                if dims_list:
                    d = dims_list[0] # 最初の要素を取得
                    height = d.get('height', {})
                    length = d.get('length', {})
                    width = d.get('width', {})

                    h_str = f"{height.get('value', '?')} {height.get('unit', '')}"
                    l_str = f"{length.get('value', '?')} {length.get('unit', '')}"
                    w_str = f"{width.get('value', '?')} {width.get('unit', '')}"

                    description += f"<li><b>Item Dimensions:</b> {l_str} (L) x {w_str} (W) x {h_str} (H)</li>\n"
        except (KeyError, TypeError, IndexError):
            pass # エラーでも処理を続行


        # 📝 商品説明文（箇条書きではない方）の取得
        try:
            # attributesの中から'product_description'キーを持つ最初の要素を取得
            prod_desc_data = next((attr for attr in attributes.get('product_description', []) if 'value' in attr), None)
            if prod_desc_data:
                product_text = prod_desc_data.get('value', '').replace('\n', '<br>')
                description += "<h3>Description</h3>\n"
                description += f"<p>{product_text}</p>\n"
        except (KeyError, TypeError, StopIteration):
            pass # データがない場合は何もしない

        # --- 追加ここまで ---


        
        description += "</div>"
        
        return description

    def get_image_urls(self, product_info):
        """
        商品情報から高解像度の画像URLを最大10件まで取得する。
        'MAIN', 'PT01', 'PT02'... の順に並び替える。
        """
        def sort_key_for_images(variant):
            # 画像を 'MAIN', 'PT01', 'PT02'... の順に並び替えるためのキーを返す
            if variant == 'MAIN':
                return '0'
            # PT01, PT02... などを正しくソートするために正規表現は使わず単純な置換で対応
            return variant.replace('PT', '1')

        image_urls = []
        images_payload = product_info.get('images', [])

        if images_payload and isinstance(images_payload, list):
            image_set = images_payload[0]
            image_list = image_set.get('images', [])

            # 各バリエーション（MAIN, PT01など）で最も解像度の高い画像を保持
            best_images = {}
            for img in image_list:
                variant = img.get('variant', 'UNKNOWN')
                height = img.get('height', 0)
                
                if variant not in best_images or height > best_images[variant].get('height', 0):
                    best_images[variant] = img
            
            # 画像を所定の順序 (MAIN, PT01, PT02...) に並び替え
            sorted_variants = sorted(best_images.keys(), key=sort_key_for_images)
            
            # 上位10件までのURLを取得
            image_urls = [best_images[variant]['link'] for variant in sorted_variants[:10]]

        return image_urls
    




    # (ファイルの一番下に追加)

# --- テスト用の実行ブロック ---
# (Replace the entire test block at the bottom of the file with this)

if __name__ == '__main__':
    import pprint

    # Test ASIN that has been confirmed to work
    test_asin = "B07WXL5YPW"

    print(f"--- ASIN: {test_asin} のテストを開始します ---")

    scraper = AmazonScraperForEbay()

    print("\n[1] get_product_info をテスト中...")
    product_info = scraper.get_product_info(test_asin)

    if product_info:
        title = product_info.get('summaries', [{}])[0].get('itemName', '(Unknown Name)')
        print(f"  -> Success! Product Name: {title}")
    else:
        print("  -> Failed. Halting process.")
        exit()

    # --- ▼▼▼ This block has been modified ▼▼▼ ---
    print("\n[2] Testing retrieval of Package Dimensions and Weight...")
    try:
        attributes = product_info.get('attributes', {})
        data_found = False # Flag to check if any data was found

        # ① Check for 'item_package_dimensions'
        if 'item_package_dimensions' in attributes and attributes['item_package_dimensions']:
            if not data_found:
                print("  -> Success! Details:")
                data_found = True
            
            dims_data = attributes['item_package_dimensions'][0]
            length = dims_data.get('length', {})
            width = dims_data.get('width', {})
            height = dims_data.get('height', {})

            l_str = f"{length.get('value', '?')} {length.get('unit', '')}"
            w_str = f"{width.get('value', '?')} {width.get('unit', '')}"
            h_str = f"{height.get('value', '?')} {height.get('unit', '')}"

            print(f"    - Dimensions (L x W x H): {l_str} x {w_str} x {h_str}")

        # ② Check for 'item_weight'
        if 'item_weight' in attributes and attributes['item_weight']:
            if not data_found:
                print("  -> Success! Details:")
                data_found = True

            weight_data = attributes['item_weight'][0]
            value = weight_data.get('value', '?')
            unit = weight_data.get('unit', '')
            print(f"    - Weight: {value} {unit}")

        if not data_found:
            print("  -> Skipped. No package dimension or weight data found for this ASIN.")

    except Exception as e:
        print(f"  -> Error. An issue occurred while retrieving size/weight: {e}")
    # --- ▲▲▲ End of modified block ▲▲▲ ---


    print("\n[3] get_product_price をテスト中...")
    price_info = scraper.get_product_price(test_asin)
    if price_info and price_info.get('price'):
        print(f"  -> Success! Price: {price_info['price']}")
    else:
        print("  -> Failed. Price information not found.")

    print("\n[4] format_description をテスト中...")
    description = scraper.format_description(test_asin, product_info)
    print("  -> Success! Generated Description (Full):")
    print("-" * 20)
    print(description)
    print("-" * 20)

    print("\n[5] get_image_urls をテスト中...")
    image_urls = scraper.get_image_urls(product_info)
    if image_urls:
        print("  -> Success! Retrieved Image URLs:")
        for url in image_urls:
            print(f"    - {url}")
    else:
        print("  -> Failed. Image URLs not found.")

    print("\n--- Test Complete ---")