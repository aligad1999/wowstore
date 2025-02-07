import streamlit as st
import requests
import pandas as pd
import time
import logging
from datetime import datetime

# Set up logging
logging.basicConfig(
    filename='shopify_product_sync.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Set page configuration
st.set_page_config(page_title="Wow Store Product Sync", page_icon="🛍", layout="centered")

# Centered logo
st.markdown(
    """
    <style>
        .centered {
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .title-text {
            text-align: center;
            font-size: 26px;
            font-weight: bold;
            color: #333;
        }
        .uploaded-file {
            border: 2px dashed #4CAF50;
            padding: 10px;
            border-radius: 10px;
            text-align: center;
            background-color: #f9f9f9;
        }
    </style>
    <div class="centered">
        <img src="logo.png" width="400">
    </div>
    <p class="title-text">Wow Store Product Sync</p>
    """,
    unsafe_allow_html=True
)

class ShopifyProductSync:
    def __init__(self, store_name, access_token):
        self.store_name = store_name
        self.access_token = access_token
        self.base_url = f"https://{store_name}.myshopify.com/admin/api/2024-01/products.json"
        self.headers = {
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": access_token
        }

    def get_products(self):
        try:
            products = []
            params = {'limit': 250}
            while True:
                response = requests.get(self.base_url, headers=self.headers, params=params)
                if response.status_code == 200:
                    data = response.json()
                    products.extend(data.get('products', []))
                    break
                else:
                    logging.error(f"API request failed: {response.status_code}")
                    break
            return pd.DataFrame(products)
        except Exception as e:
            logging.error(f"Error retrieving products: {str(e)}")
            return pd.DataFrame()

    def update_product_variant(self, variant_id, new_price, new_inventory):
        update_url = f"https://{self.store_name}.myshopify.com/admin/api/2024-01/variants/{variant_id}.json"
        data = {"variant": {"id": variant_id, "price": new_price, "inventory_quantity": new_inventory}}
        response = requests.put(update_url, headers=self.headers, json=data)
        return response.status_code == 200

# Main function
def main():
    store_name = st.secrets["store_name"]
    access_token = st.secrets["access_token"]
    sync = ShopifyProductSync(store_name, access_token)

    st.subheader("📂 Upload Your Excel File")
    uploaded_file = st.file_uploader("Upload an Excel file containing product updates", type=["xlsx"], help="Ensure the file includes 'اسم البحث', 'الإجمالي المتاح', 'Sales Price' columns.")

    if uploaded_file is not None:
        external_df = pd.read_excel(uploaded_file)
        required_columns = ['اسم البحث', 'الإجمالي المتاح', 'Sales Price']
        if all(column in external_df.columns for column in required_columns):
            st.success("File uploaded successfully!")
            df = sync.get_products()
            merged_df = df.merge(external_df, left_on='sku', right_on='اسم البحث', how='inner')

            if not merged_df.empty:
                st.write("✅ Merged Data Preview:")
                st.dataframe(merged_df)
                progress_bar = st.progress(0)
                total_updates = len(merged_df)
                for i, (_, row) in enumerate(merged_df.iterrows()):
                    sync.update_product_variant(row['variant_id'], row['Sales Price'], row['الإجمالي المتاح'])
                    progress_bar.progress((i + 1) / total_updates)
                    time.sleep(0.1)
                st.success(f"Successfully updated {total_updates} products!")
            else:
                st.warning("No matching SKUs found in Shopify.")
        else:
            st.error(f"Missing required columns: {required_columns}")

if __name__ == "__main__":
    main()
