# app.py
import streamlit as st
import requests
import pandas as pd
import time
import logging
from datetime import datetime
import os

# Set page config
st.set_page_config(
    page_title="Wow Store Product Sync Tool",
    page_icon="🔄",
    layout="wide"
)

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
        self.location_id = self.get_location_id()

    def get_location_id(self):
        """Get the first location ID from the store"""
        url = f"https://{self.store_name}.myshopify.com/admin/api/2024-01/locations.json"
        response = requests.get(url, headers=self.headers)
        
        if response.status_code == 200:
            locations = response.json().get('locations', [])
            if locations:
                location_id = locations[0]['id']
                logging.info(f"Retrieved location ID: {location_id}")
                return location_id
        
        logging.error("Failed to get location ID")
        return None

    def set_inventory_level(self, inventory_item_id, new_quantity):
        """Set inventory level directly using the inventory levels set endpoint"""
        if not self.location_id:
            logging.error("No location ID available")
            return False

        set_url = f"https://{self.store_name}.myshopify.com/admin/api/2024-01/inventory_levels/set.json"
        
        data = {
            "location_id": self.location_id,
            "inventory_item_id": inventory_item_id,
            "available": int(new_quantity)
        }
        
        try:
            response = requests.post(set_url, headers=self.headers, json=data)
            if response.status_code == 200:
                logging.info(f"Successfully set inventory for item {inventory_item_id} to {new_quantity}")
                return True
            else:
                logging.error(f"Failed to set inventory: Status {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            logging.error(f"Error setting inventory: {str(e)}")
            return False

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
                    'inventory_item_id': variant.get('inventory_item_id'),
                    'created_at': product.get('created_at'),
                    'updated_at': product.get('updated_at'),
                    'status': product.get('status', 'active')
                }
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
            value = value.replace(',', '').strip()
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    def update_product_variant(self, variant_id, new_price, new_inventory):
        """Update price and inventory of a product variant on Shopify"""
        try:
            # First, get the variant details to get the inventory_item_id
            variant_url = f"https://{self.store_name}.myshopify.com/admin/api/2024-01/variants/{variant_id}.json"
            variant_response = requests.get(variant_url, headers=self.headers)
            
            if variant_response.status_code != 200:
                logging.error(f"Failed to get variant details for {variant_id}")
                return False

            variant_data = variant_response.json()['variant']
            inventory_item_id = variant_data['inventory_item_id']

            # Update price
            update_url = f"https://{self.store_name}.myshopify.com/admin/api/2024-01/variants/{variant_id}.json"
            price_data = {
                "variant": {
                    "id": variant_id,
                    "price": self.safe_float(new_price)
                }
            }
            
            price_response = requests.put(update_url, headers=self.headers, json=price_data)
            if price_response.status_code != 200:
                logging.error(f"Failed to update price for variant {variant_id}")
                return False

            # Update inventory separately
            inventory_success = self.set_inventory_level(inventory_item_id, new_inventory)
            
            if inventory_success:
                logging.info(f"Successfully updated variant {variant_id} price and inventory")
                return True
            else:
                logging.error(f"Failed to update inventory for variant {variant_id}")
                return False

        except Exception as e:
            logging.error(f"Error in update_product_variant: {str(e)}")
            return False

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

     def create_product(self, title, sku, price, inventory, brand):
            """Create a new product in Shopify with the given brand."""
            # Convert and validate the values
            safe_price = self.safe_float(price)
            safe_inventory = int(self.safe_float(inventory))  # Convert to integer for inventory
    
            data = {
                "product": {
                    "title": title,
                    "status": "draft",
                    "vendor": brand.strip() if isinstance(brand, str) else brand,  # Clean up brand name
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

    try:
        sync = ShopifyProductSync(store_name, access_token)
        if not sync.location_id:
            st.error("Failed to get store location ID. Please check your store settings.")
            return
            
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
                
                # Get existing products
                df = sync.get_products()

                # Perform merge
                merged_df = df.merge(external_df, left_on='sku', right_on='اسم البحث', how='inner')
                
                # Find unmatched SKUs (new products)
                unmatched_skus = external_df[~external_df['اسم البحث'].isin(df['sku'])]
                
                # Show preview of updates
                st.write(f"✅ Found {len(merged_df)} products to update:")
                st.dataframe(merged_df[["title", "sku", "Sales Price", "الإجمالي المتاح"]])
                
                st.write(f"📌 Found {len(unmatched_skus)} new products to create:")
                st.dataframe(unmatched_skus[['اسم المنتج', 'اسم البحث', 'Sales Price', 'الإجمالي المتاح', 'Brand']])

                # Calculate total operations
                total_operations = len(merged_df) + len(unmatched_skus)
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # Update existing products
                for index, row in merged_df.iterrows():
                    progress = (index + 1) / total_operations
                    progress_bar.progress(progress)
                    status_text.text(f"Updating existing product {index + 1} of {len(merged_df)}: {row['title']}")
                    
                    success = sync.update_product_variant(
                        row['variant_id'],
                        row['Sales Price'],
                        row['الإجمالي المتاح']
                    )
                    
                    if not success:
                        st.warning(f"Failed to update {row['title']}. Check the logs for details.")
                    
                    time.sleep(0.5)  # Respect API rate limits

                # Create new products
                for index, row in unmatched_skus.iterrows():
                    current_index = len(merged_df) + index + 1
                    progress = current_index / total_operations
                    progress_bar.progress(progress)
                    status_text.text(f"Creating new product {index + 1} of {len(unmatched_skus)}: {row['اسم المنتج']}")
                    
                    result = sync.create_product(
                        title=row['اسم المنتج'],
                        sku=row['اسم البحث'],
                        price=row['Sales Price'],
                        inventory=row['الإجمالي المتاح'],
                        brand=row['Brand']
                    )
                    
                    if not result:
                        st.warning(f"Failed to create product {row['اسم المنتج']}. Check the logs for details.")
                    
                    time.sleep(0.5)  # Respect API rate limits

                st.success(f"✅ Process completed! Updated {len(merged_df)} products and created {len(unmatched_skus)} new products.")
                
            else:
                st.error(f"File must contain the following columns: {required_columns}")
                
    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
        logging.error(f"Main function error: {str(e)}")

if __name__ == "__main__":
    main()
