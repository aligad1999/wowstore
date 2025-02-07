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

class ShopifyProductSync:
    def __init__(self, store_name, access_token):
        self.store_name = store_name
        self.access_token = access_token
        self.base_url = f"https://{store_name}.myshopify.com/admin/api/2024-01/products.json"
        self.headers = {
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": access_token
        }

    def extract_nested_value(self, data, path):
        """Extract nested dictionary values using dot notation path"""
        try:
            for key in path.split('.'):
                data = data.get(key, {})
            return data if data != {} else None
        except:
            return None

    def process_products_to_dataframe(self, products):
        """Convert products to DataFrame with specific columns"""
        processed_data = []

        for product in products:
            for variant in product.get('variants', []):
                product_data = {
                    'product_id': product.get('id'),
                    'title': product.get('title'),
                    'variant_id': variant.get('id'),
                    'variant_title': variant.get('title'),
                    'price': variant.get('price'),
                    'sku': variant.get('sku'),
                    'inventory_quantity': variant.get('inventory_quantity'),
                    'created_at': product.get('created_at'),
                    'updated_at': product.get('updated_at'),
                    'retrieved_at': datetime.utcnow()
                }
                
                # Check if price is zero and update inventory quantity to 0
                if float(variant.get('price', 0)) == 0:
                    self.update_product_variant(variant.get('id'), 0, 0)
                    product_data['inventory_quantity'] = 0
                    logging.info(f"Set inventory to 0 for variant {variant.get('id')} with zero price")

                processed_data.append(product_data)

        df = pd.DataFrame(processed_data)
        df['price'] = pd.to_numeric(df['price'], errors='coerce')
        df['inventory_quantity'] = pd.to_numeric(df['inventory_quantity'], errors='coerce')
        df['created_at'] = pd.to_datetime(df['created_at'], errors='coerce', utc=True)
        df['updated_at'] = pd.to_datetime(df['updated_at'], errors='coerce', utc=True)
        df['retrieved_at'] = pd.to_datetime(df['retrieved_at'], errors='coerce', utc=True)

        return df

    def update_product_variant(self, variant_id, new_price, new_inventory):
        """Update the price and inventory of a product variant on Shopify"""
        update_url = f"https://{self.store_name}.myshopify.com/admin/api/2024-01/variants/{variant_id}.json"
        data = {
            "variant": {
                "id": variant_id,
                "price": new_price,
                "inventory_quantity": new_inventory
            }
        }
        response = requests.put(update_url, headers=self.headers, json=data)
        if response.status_code == 200:
            logging.info(f"Updated variant {variant_id} with price {new_price} and inventory {new_inventory}")
        else:
            logging.error(f"Failed to update variant {variant_id}: {response.text}")

    def get_products(self):
        """Retrieve products from Shopify API"""
        try:
            products = []
            params = {'limit': 250}
            page_count = 1

            while True:
                response = requests.get(
                    self.base_url,
                    headers=self.headers,
                    params=params
                )

                logging.info(f"Fetching page {page_count}")

                if response.status_code == 200:
                    data = response.json()
                    current_products = data.get('products', [])
                    products.extend(current_products)
                    print(f"Retrieved {len(current_products)} products from page {page_count}")

                    link_header = response.headers.get('Link', '')
                    if 'rel="next"' not in link_header:
                        break

                    next_link = [l.split(';')[0].strip('<> ') for l in link_header.split(',') 
                               if 'rel="next"' in l]
                    if not next_link:
                        break

                    try:
                        params = dict(param.split('=') for param in next_link[0].split('?')[1].split('&'))
                    except Exception as e:
                        logging.error(f"Error parsing next page parameters: {str(e)}")
                        break

                    time.sleep(0.5)
                    page_count += 1

                elif response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 10))
                    time.sleep(retry_after)
                    continue
                else:
                    logging.error(f"API request failed with status code: {response.status_code}")
                    response.raise_for_status()

            print(f"Successfully retrieved {len(products)} products")
            return self.process_products_to_dataframe(products)
        
        except Exception as e:
            logging.error(f"Error retrieving products: {str(e)}")
            raise

def main():
    # Custom CSS to center the logo
    st.markdown(
        """
        <style>
        .logo-container {
            display: flex;
            justify-content: center;
            align-items: center;
            margin-bottom: 20px;
        }
        .logo-img {
            max-width: 400px;
        }
        </style>
        """,
        unsafe_allow_html=True
    )
    
    # Add the logo
    st.markdown(
        """
        <div class="logo-container">
            <img src="https://via.placeholder.com/200" class="logo-img" alt="Logo">
        </div>
        """,
        unsafe_allow_html=True
    )
    
    # Set the title of the app
    st.title("Shopify Product Sync")
    
    # Rest of your app code
    st.write("Welcome to the Shopify Product Sync app!")


    # Use Streamlit secrets for sensitive information
    store_name = st.secrets["store_name"]
    access_token = st.secrets["access_token"]

    sync = ShopifyProductSync(store_name, access_token)
    st.write("Initialized Shopify product sync...")

    uploaded_file = st.file_uploader("Upload your Excel file", type=["xlsx"])
    if uploaded_file is not None:
        external_df = pd.read_excel(uploaded_file)
        required_columns = ['اسم البحث', 'الإجمالي المتاح', 'Sales Price']
        if all(column in external_df.columns for column in required_columns):
            st.write("📂 File uploaded and validated successfully!")
            df = sync.get_products()
            st.write(f"Retrieved {len(df)} product variants.")

            merged_df = df.merge(external_df, left_on='sku', right_on='اسم البحث', how='inner')
            st.write("Merged Data:")
            st.dataframe(merged_df)

            progress_bar = st.progress(0)
            total_updates = len(merged_df)
            for i, (_, row) in enumerate(merged_df.iterrows()):
                sync.update_product_variant(row['variant_id'], row['Sales Price'], row['الإجمالي المتاح'])
                progress_bar.progress((i + 1) / total_updates)
                time.sleep(0.1)  # Simulate delay for progress bar

            st.write(f"✅ Updated {total_updates} products based on Excel data.")
        else:
            st.error(f"File must contain the following columns: {required_columns}")

if __name__ == "__main__":
    main()
