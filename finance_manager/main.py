import pandas as pd
import glob
import os
import datetime
import warnings

# 警告を無視
warnings.simplefilter('ignore')

# ==========================================
# 1. 設定・マッピング定義
# ==========================================

SEGMENT_MAP = {
    'hadient': '1_D2C_Hadient',
    'shopify_bcp': '2_List_Supple',
    'base_papalifee': '3_List_Men',
    'base_sanyodo': '3_List_Men',
    'base_montyhole': '5_EC_Drop',
    'mercarishops': '5_EC_Drop',
    'ebay': '5_EC_Drop',
}

OUTPUT_DIR = './03_output'
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ==========================================
# 2. 読み込み・処理ロジック
# ==========================================

def load_csv_safe(filepath):
    """エンコーディングを自動判別して読み込む"""
    filename = os.path.basename(filepath).lower()

    # eBayファイルの場合は特別処理（最初の11行をスキップ）
    if 'ebay' in filename:
        encodings = ['utf-8-sig', 'utf-8', 'cp932']
        for enc in encodings:
            try:
                df = pd.read_csv(filepath, encoding=enc, skiprows=11, encoding_errors='strict')
                return df
            except UnicodeDecodeError:
                continue
            except Exception:
                continue
        # 最後の手段
        return pd.read_csv(filepath, encoding='utf-8-sig', skiprows=11, encoding_errors='ignore')

    # その他のファイル
    # Mercariファイルの場合はshift_jisを優先
    if 'mercari' in filename:
        encodings = ['shift_jis', 'utf-8-sig', 'utf-8', 'cp932']
    else:
        encodings = ['utf-8-sig', 'utf-8', 'cp932']

    for enc in encodings:
        try:
            df = pd.read_csv(filepath, encoding=enc, encoding_errors='strict')
            return df
        except UnicodeDecodeError:
            continue
        except Exception:
            continue
    # 最後の手段（エラー無視して読む）
    return pd.read_csv(filepath, encoding='cp932', encoding_errors='ignore')

def process_hadient_shopify(df, filename):
    """D2C / Shopify / Subsc用"""
    if 'キャンセル日' in df.columns:
        df = df[df['キャンセル日'].isna()]

    # カラム名のゆらぎ吸収
    key_col = '注文番号' if '注文番号' in df.columns else 'Name'
    # Shopifyは 'Total', Subscは '総合計(税込み)'
    total_col = None
    if '综合計(税込み)' in df.columns: total_col = '综合計(税込み)' # 文字化け対策
    elif '総合計(税込み)' in df.columns: total_col = '総合計(税込み)'
    elif 'Total' in df.columns: total_col = 'Total'

    if not total_col or key_col not in df.columns:
        raise ValueError(f"必須カラム不足: {key_col}, {total_col}")

    df_unique = df.drop_duplicates(subset=[key_col])

    # 日付カラムの特定
    date_col = df.columns[0] # 1列目と仮定
    for col in ['注文日', 'Created at', 'date', 'Date']:
        if col in df.columns:
            date_col = col
            break

    return pd.DataFrame({
        'date': pd.to_datetime(df_unique[date_col], errors='coerce'),
        'sales': df_unique[total_col],
        'cost': 0,
        'description': df_unique[key_col].astype(str)
    })

def process_base(df, filename):
    """BASE用"""
    df_result = df.copy()
    df_result['date'] = pd.to_datetime(df['注文日時'], errors='coerce')

    return pd.DataFrame({
        'date': df_result['date'],
        'sales': df['価格'] * df['数量'], # 行ごとの売上
        'cost': 0,
        'description': df['注文ID'].astype(str)
    })

def process_mercari(df, filename):
    """Mercari Shops用"""
    import re

    def parse_japanese_date(date_str):
        """日本語日付フォーマット '2025年11月1日 07:55' をパース"""
        try:
            match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日\s*(\d{1,2}):(\d{1,2})', str(date_str))
            if match:
                y, m, d, h, mi = match.groups()
                return pd.Timestamp(f'{y}-{m.zfill(2)}-{d.zfill(2)} {h.zfill(2)}:{mi.zfill(2)}')
            # 日本語形式でなければ通常のパースを試す
            return pd.to_datetime(date_str, errors='coerce')
        except:
            return pd.NaT

    df_result = df.copy()
    df_result['date'] = df['purchase_date'].apply(parse_japanese_date)

    return pd.DataFrame({
        'date': df_result['date'],
        'sales': (df['product_price'] * df['quantity']),
        'cost': 0,
        'description': df['order_id'].astype(str)
    })

def process_amazon(df, filename):
    """Amazon用"""
    # 日本語ヘッダー対応
    date_col = '日付' if '日付' in df.columns else 'date/time'
    sales_col = '商品価格合計' if '商品価格合計' in df.columns else 'product sales'
    fee_col = 'Amazon手数料' if 'Amazon手数料' in df.columns else 'selling fees'
    order_col = '注文番号' if '注文番号' in df.columns else 'order id'

    df_result = df.copy()
    df_result['date'] = pd.to_datetime(df[date_col], errors='coerce')

    return pd.DataFrame({
        'date': df_result['date'],
        'sales': df[sales_col].fillna(0),
        'variable_cost': df[fee_col].fillna(0) * -1, # 手数料
        'description': df[order_col].astype(str)
    })

def process_ebay(df, filename):
    """eBay用 (Transaction Report)"""
    # Transaction type: 'Order', 'Refund', 'Shipping label' etc.
    # Amount description: 'Price', 'Tax', 'Ad Fee'

    # 日付パース
    if 'Transaction creation date' in df.columns:
        date_col = 'Transaction creation date'
    elif 'Transaction date' in df.columns:
        date_col = 'Transaction date'
    else:
        date_col = df.columns[0] # 先頭と仮定

    df_result = df.copy()
    df_result['date'] = pd.to_datetime(df[date_col], errors='coerce')

    # Net amountを使用（Payout currency建て）
    val_col = 'Net amount' if 'Net amount' in df.columns else 'Amount'

    # Order numberがない場合の対応
    order_col = 'Order number' if 'Order number' in df.columns else 'Transaction ID'

    # Type列の確認
    type_col = 'Type' if 'Type' in df.columns else 'Transaction type' if 'Transaction type' in df.columns else None

    if type_col:
        # 売上のみ抽出 (Type=Order)
        return pd.DataFrame({
            'date': df_result['date'],
            'sales': df.apply(lambda x: x[val_col] if str(x[type_col]).strip() == 'Order' else 0, axis=1),
            'variable_cost': df.apply(lambda x: x[val_col] if str(x[type_col]).strip() != 'Order' else 0, axis=1),
            'description': df[order_col].astype(str)
        })
    else:
        # Type列がない場合はすべて売上として扱う
        return pd.DataFrame({
            'date': df_result['date'],
            'sales': df[val_col].fillna(0),
            'cost': 0,
            'description': df[order_col].astype(str)
        })

# ==========================================
# 3. メイン処理
# ==========================================

def main():
    all_data = []
    files = glob.glob('./01_raw_data/**/*.csv', recursive=True)
    error_files = []
    
    print(f"発見したファイル数: {len(files)}")
    
    for filepath in files:
        filename = os.path.basename(filepath)
        # 隠しファイルなどはスキップ
        if filename.startswith('.'): continue
        
        try:
            df = load_csv_safe(filepath)
            
            # セグメント判定
            segment = 'Unknown'
            for key, val in SEGMENT_MAP.items():
                if key in filename.lower():
                    segment = val
                    break
            
            # --- 処理分岐 (順序重要) ---
            processed_df = pd.DataFrame()
            
            # 1. Amazon (hadientが含まれていてもAmazonルールで読むため先頭に)
            if 'amazon' in filename.lower():
                processed_df = process_amazon(df, filename)
                
            # 2. eBay
            elif 'ebay' in filename.lower():
                processed_df = process_ebay(df, filename)
            
            # 3. Mercari
            elif 'mercari' in filename.lower():
                processed_df = process_mercari(df, filename)

            # 4. BASE
            elif 'base' in filename.lower():
                processed_df = process_base(df, filename)

            # 5. D2C / Shopify (最後に判定)
            elif 'hadient' in filename.lower() or 'shopify' in filename.lower():
                processed_df = process_hadient_shopify(df, filename)
            
            else:
                print(f"Skip (対象外): {filename}")
                continue

            # 共通処理
            if processed_df.empty:
                print(f"Warning: {filename} からデータが取れませんでした")
                continue
                
            processed_df['segment'] = segment
            processed_df['source_file'] = filename
            all_data.append(processed_df)
            print(f"OK: {filename} ({len(processed_df)} rows)")
            
        except Exception as e:
            print(f"Error: {filename} -> {e}")
            error_files.append((filename, str(e)))

    # --- 集計と出力 ---
    if not all_data:
        print("データがありません")
        return

    master_df = pd.concat(all_data, ignore_index=True)

    # date列を明示的にdatetime型に変換
    master_df['date'] = pd.to_datetime(master_df['date'], errors='coerce')

    # NaT（欠損日付）を除外
    master_df = master_df[master_df['date'].notna()]

    master_df['month'] = master_df['date'].dt.strftime('%Y-%m')
    
    # ピボットテーブル (売上)
    pivot_sales = master_df.pivot_table(
        index='month', columns='segment', values='sales', aggfunc='sum'
    ).fillna(0)
    
    # 出力
    today_str = datetime.date.today().strftime('%Y%m%d')
    output_path = os.path.join(OUTPUT_DIR, f'monthly_report_{today_str}.xlsx')
    
    with pd.ExcelWriter(output_path) as writer:
        pivot_sales.to_excel(writer, sheet_name='Sales_Summary')
        master_df.to_excel(writer, sheet_name='Raw_Data', index=False)
        
        # エラーログも別シートに出す
        if error_files:
            pd.DataFrame(error_files, columns=['File', 'Error']).to_excel(writer, sheet_name='Errors')
            
    print(f"\n完了！レポートを出力しました: {output_path}")
    if error_files:
        print("\n⚠️ 読み込みエラーが発生したファイルがあります。Excelの'Errors'シートを確認してください。")

if __name__ == "__main__":
    main()