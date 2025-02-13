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

    
    def get_products(self):
        """Retrieve products from Shopify API"""
        try:
            products = []
            params = {'limit': 250}
            page_count = 1

            while True:
                response = requests.get(self.base_url, headers=self.headers, params=params)
                logging.info(f"Fetching page {page_count}")

                if response.status_code == 200:
                    data = response.json()
                    current_products = data.get('products', [])
                    products.extend(current_products)
                    print(f"Retrieved {len(current_products)} products from page {page_count}")

                    link_header = response.headers.get('Link', '')
                    if 'rel="next"' not in link_header:
                        break

                    next_link = [l.split(';')[0].strip('<> ') for l in link_header.split(',') if 'rel="next"' in l]
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
    def process_products_to_dataframe(self, products):
        """Convert products to DataFrame with specific columns"""
        processed_data = []

        for product in products:
            for variant in product.get('variants', []):
                product_data = {
                    'product_id': product.get('id'),
                    'title': product.get('title'),
                    'variant_id': variant.get('id'),
                    'price': float(variant.get('price', 0)),
                    'sku': variant.get('sku'),
                    'inventory_quantity': variant.get('inventory_quantity'),
                    'created_at': product.get('created_at'),
                    'updated_at': product.get('updated_at'),
                    'status': product.get('status', 'active')
                }

                if product_data['price'] == 0:
                    self.update_product_variant(variant.get('id'), 0, 0)
                    product_data['inventory_quantity'] = 0
                    product_data['status'] = "draft"
                    logging.info(f"Set inventory to 0 and status to draft for variant {variant.get('id')} with zero price")

                processed_data.append(product_data)

        df = pd.DataFrame(processed_data)
        df['created_at'] = pd.to_datetime(df['created_at'], errors='coerce', utc=True)
        df['updated_at'] = pd.to_datetime(df['updated_at'], errors='coerce', utc=True)

        return df

    def safe_float(self, value, default=0):
        """Safely convert value to float, handling None, NaN, and string numbers with commas"""
        if pd.isna(value) or value == '':
            return default
        if isinstance(value, str):
            # Remove commas and spaces
            value = value.replace(',', '').strip()
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

def update_product_variant(self, variant_id, new_price, new_inventory):
    """Update price and inventory of a product variant on Shopify"""
    safe_price = self.safe_float(new_price)

    # Fetch variant details to get inventory_item_id
    variant_url = f"https://{self.store_name}.myshopify.com/admin/api/2024-01/variants/{variant_id}.json"
    response = requests.get(variant_url, headers=self.headers)
    if response.status_code != 200:
        logging.error(f"Failed to fetch variant details: {response.text}")
        return

    variant_data = response.json().get('variant', {})
    inventory_item_id = variant_data.get('inventory_item_id')

    # Fetch locations
    location_url = f"https://{self.store_name}.myshopify.com/admin/api/2024-01/locations.json"
    location_response = requests.get(location_url, headers=self.headers)
    if location_response.status_code != 200:
        logging.error(f"Failed to fetch locations: {location_response.text}")
        return

    locations = location_response.json().get('locations', [])
    if not locations:
        logging.error("No locations found for inventory updates.")
        return

    location_id = locations[0]['id']  # Use the first location

    # Update inventory
    self.update_inventory_level(inventory_item_id, location_id, new_inventory)

    # Update price separately
    update_url = f"https://{self.store_name}.myshopify.com/admin/api/2024-01/variants/{variant_id}.json"
    data = {"variant": {"id": variant_id, "price": safe_price}}
    price_response = requests.put(update_url, headers=self.headers, json=data)
    if price_response.status_code == 200:
        logging.info(f"Updated price for variant {variant_id} to {safe_price}")
    else:
        logging.error(f"Failed to update price: {price_response.text}")


    def create_product(self, title, sku, price, inventory, brand):
        """Create a new product in Shopify with the given brand."""
        # Convert and validate the values
        safe_price = self.safe_float(price)
        safe_inventory = int(self.safe_float(inventory))  # Convert to integer for inventory

        data = {
            "product": {
                "title": title,
                "status": "draft",
                #"vendor": brand.strip() if isinstance(brand, str) else brand,  # Clean up brand name
                "variants": [{
                    "sku": sku,
                    "price": safe_price,
                    "inventory_quantity": safe_inventory,
                    "inventory_management": "shopify",  # Enable inventory tracking
                    "inventory_policy": "deny",  # Prevent selling when out of stock
                    "requires_shipping": True
                    
                }]
            }
        }
        response = requests.post(self.base_url, headers=self.headers, json=data)
        if response.status_code == 201:
            logging.info(f"Created new product '{title}' with SKU {sku} and Brand '{brand}'")
            return response.json()
        else:
            logging.error(f"Failed to create product {title}: {response.text}")
            return None



def main():
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.image("logo.png", width=200)
        
    st.title("🔄 Wow Store Product Sync Tool!")

    store_name = st.secrets["store_name"]
    access_token = st.secrets["access_token"]

    sync = ShopifyProductSync(store_name, access_token)
    st.write("Sync and update product prices and inventory on Shopify with a simple Excel upload. Automatically update existing products and create new ones as drafts if missing. Track progress in real time! 🚀")
             
    uploaded_file = st.file_uploader("Upload your Excel file", type=["xlsx"])
    if uploaded_file is not None:
        external_df = pd.read_excel(uploaded_file)
        required_columns = ['اسم البحث', 'الإجمالي المتاح', 'Sales Price', 'اسم المنتج', 'Brand']
        
        if all(column in external_df.columns for column in required_columns):
            st.markdown("""
            📂 File uploaded and validated successfully!  
            Loading…
            """)
            
            # Clean up the data
            external_df['الإجمالي المتاح'] = external_df['الإجمالي المتاح'].apply(sync.safe_float)
            external_df['Sales Price'] = external_df['Sales Price'].apply(sync.safe_float)
            external_df['Brand'] = external_df['Brand'].fillna('').astype(str).str.strip()
            
            df = sync.get_products()

            # Perform merge
            merged_df = df.merge(external_df, left_on='sku', right_on='اسم البحث', how='inner')
            columns_to_keep = ["variant_id", "updated_at", "title", "Brand", "اسم البحث", "الإجمالي المتاح", "Sales Price"]
            show_merged_df = merged_df[columns_to_keep]
            
            st.write(f"✅ {len(merged_df)} Updated products based on Excel data.")
            st.dataframe(show_merged_df)

            # Find unmatched SKUs
            unmatched_skus = external_df[~external_df["اسم البحث"].isin(df["sku"])]
            unmatched_skus["status"] = "draft"
            st.write(f"📌 {len(unmatched_skus)} new products will be created.")
            st.dataframe(unmatched_skus)

            progress_bar = st.progress(0)
            total_updates = len(merged_df) + len(unmatched_skus)

            # Update existing products
            for i, (_, row) in enumerate(merged_df.iterrows()):
                sync.update_product_variant(row['variant_id'], row['Sales Price'], row['الإجمالي المتاح'])
                progress_bar.progress((i + 1) / total_updates)
                time.sleep(0.1)

            # Create new products
            for i, (_, row) in enumerate(unmatched_skus.iterrows(), start=len(merged_df)):
                sync.create_product(row["اسم المنتج"], row["اسم البحث"], row["Sales Price"], row["الإجمالي المتاح"], row["Brand"])
                progress_bar.progress((i + 1) / total_updates)
                time.sleep(0.1)

            st.success(f"✅ Updated {len(merged_df)} products and created {len(unmatched_skus)} new products.")
        else:
            st.error(f"File must contain the following columns: {required_columns}")

if __name__ == "__main__":
    main()
