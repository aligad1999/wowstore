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
    page_icon="🔄"
)

# Set up logging
logging.basicConfig(
    filename='shopify_product_sync.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class ShopifyProductSync:
    # [Previous class implementation remains the same until the main() function]
    def __init__(self, store_name, access_token):
        self.store_name = store_name
        self.access_token = access_token
        self.base_url = f"https://{store_name}.myshopify.com/admin/api/2024-01/products.json"
        self.headers = {
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": access_token
        }
        self.location_id = self.get_location_id()

    # [Include all other methods from your original class implementation]
    # [They remain unchanged]

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
            required_columns = ['اسم البحث', 'المخزون الفعلي', 'Sales Price', 'اسم المنتج', 'Brand']
            
            if all(column in external_df.columns for column in required_columns):
                st.markdown("""
                📂 File uploaded and validated successfully!  
                Loading…
                """)
                
                # Clean up the data
                external_df['المخزون الفعلي'] = external_df['المخزون الفعلي'].apply(sync.safe_float)
                external_df['Sales Price'] = external_df['Sales Price'].apply(sync.safe_float)
                external_df['Brand'] = external_df['Brand'].fillna('').astype(str).str.strip()
                external_df['اسم البحث'] = external_df['اسم البحث'].astype(str).str.strip().str.replace(" ", "")
                
                # Get existing products
                df = sync.get_products()
                
                df['sku'] = df['sku'].astype(str).str.strip().str.replace(" ", "")
                # Perform merge
                merged_df = df.merge(external_df, left_on='sku', right_on='اسم البحث', how='inner')
                
                # Find unmatched SKUs (new products)
                unmatched_skus = external_df[~external_df['اسم البحث'].isin(df['sku'])]
                
                # Show preview of updates
                st.write(f"✅ Found {len(merged_df)} products to update:")
                st.dataframe(merged_df[["title", "sku", "Sales Price", "المخزون الفعلي"]])
                
                st.write(f"📌 Found {len(unmatched_skus)} new products to create:")
                st.dataframe(unmatched_skus[['اسم المنتج', 'اسم البحث', 'Sales Price', 'المخزون الفعلي', 'Brand']])
                
                # Calculate total operations
                total_operations = len(merged_df) + len(unmatched_skus)
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # Update existing products
                for index, row in merged_df.iterrows():
                    # Ensure progress stays within [0, 1]
                    progress = min((index + 1) / total_operations, 1.0)
                    progress_bar.progress(progress)
                    status_text.text(f"Updating existing product {index + 1} of {len(merged_df)}: {row['title']}")
                    
                    success = sync.update_product_variant(
                        row['variant_id'],
                        row['Sales Price'],
                        row['المخزون الفعلي']
                    )
                    
                    if not success:
                        logging.warning(f"Failed to update {row['sku']}. Check the logs for details.")
                    
                    time.sleep(0.5)  # Respect API rate limits
                
                # Create new products
                start_progress = len(merged_df) / total_operations
                for index, row in unmatched_skus.iterrows():
                    # Calculate progress for new products portion
                    current_progress = start_progress + (index + 1) / total_operations
                    # Ensure progress stays within [0, 1]
                    progress = min(current_progress, 1.0)
                    progress_bar.progress(progress)
                    status_text.text(f"Creating new product {index + 1} of {len(unmatched_skus)}: {row['اسم المنتج']}")
                    
                    result = sync.create_product(
                        title=row['اسم المنتج'],
                        sku=row['اسم البحث'],
                        price=row['Sales Price'],
                        inventory=row['المخزون الفعلي'],
                        brand=row['Brand']
                    )
                    
                    if not result:
                        st.warning(f"Failed to create product {row['اسم البحث']}. Check the logs for details.")
                    
                    time.sleep(0.5)  # Respect API rate limits
                
                # Ensure final progress is exactly 1.0
                progress_bar.progress(1.0)
                st.success(f"✅ Process completed! Updated {len(merged_df)} products and created {len(unmatched_skus)} new products.")
                
            else:
                st.error(f"File must contain the following columns: {required_columns}")
                
    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
        logging.error(f"Main function error: {str(e)}")

if __name__ == "__main__":
    main()
