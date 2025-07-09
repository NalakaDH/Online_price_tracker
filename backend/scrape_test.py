import requests
from bs4 import BeautifulSoup
from flask_mysqldb import MySQL
from flask import Flask
import time
import random
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# Initialize Flask app
app = Flask(__name__)

# MySQL configuration
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'tracker_user'
app.config['MYSQL_PASSWORD'] = 'password'
app.config['MYSQL_DB'] = 'price_tracker'

mysql = MySQL(app)

# Sleep to ensure connection is ready
time.sleep(20)

# Create a session with proper configuration
def create_session():
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    })
    return session

session = create_session()

# Function to store data in MySQL
def store_product_data(product_name, new_price, old_price, product_image_url, company_name, product_url, category):
    try:
        with app.app_context():
            cursor = mysql.connection.cursor()
            cursor.execute(''' 
                INSERT INTO product_details (name, price, old_price, availability, images, company, ProductURL, category) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ''', (product_name, new_price, old_price, 'In Stock', product_image_url, company_name, product_url, category))
            mysql.connection.commit()
            cursor.close()

        print(f"Product scraped and stored successfully: {product_name}")
    except Exception as e:
        print(f"Error storing product details: {e}")

# Function to scrape individual product details from BigDeals
def scrape_bigdeals_product_details(product_url, category):
    try:
        response = session.get(product_url, verify=False, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract product name
        product_name_tag = soup.find('h1', class_='product-name')
        product_name = product_name_tag.text.strip() if product_name_tag else 'N/A'

        # Extract product price
        product_price_tag = soup.find('span', class_='sell-price')
        old_price_tag = soup.find('span', class_='m-price')
        new_price = product_price_tag.text.strip() if product_price_tag else '0.0'
        old_price = old_price_tag.text.strip() if old_price_tag else '0.0'

        # Clean and convert prices to float
        new_price = new_price.replace('Rs.', '').replace(',', '').strip() if new_price else '0.0'
        old_price = old_price.replace('Rs.', '').replace(',', '').strip() if old_price else '0.0'
        new_price = float(new_price)
        old_price = float(old_price)

        # Extract image URL
        image_tag = soup.find('a', class_='cloud-zoom defaultImage')
        product_image_url = image_tag['href'] if image_tag else 'N/A'

        if product_image_url.startswith('/'):
            product_image_url = 'https://bigdeals.lk' + product_image_url

        company_name = 'bigdeals.lk'
        store_product_data(product_name, new_price, old_price, product_image_url, company_name, product_url, category)

    except Exception as e:
        print(f"Error scraping product details from {product_url}: {e}")

# Function to scrape individual product details from Singhagiri
def scrape_singhagiri_product_details(product_url, category):
    try:
        response = session.get(product_url, verify=False, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract product name
        product_name_tag = soup.find('h1', class_='product-title')
        product_name = product_name_tag.text.strip() if product_name_tag else 'N/A'

        # Extract product price
        selling_price_tag = soup.find('div', class_='selling-price')
        product_price = '0.0'
        old_price = '0.0'
        
        if selling_price_tag:
            product_price_tag = selling_price_tag.find('span', class_='data')
            if product_price_tag:
                product_price = product_price_tag.text.strip()
        
        old_price_tag = soup.find('div', class_='strikeout')
        if old_price_tag:
            old_price = old_price_tag.text.strip()

        # Clean and convert prices to float
        product_price = product_price.replace('Rs.', '').replace('Rs', '').replace(',', '').replace('.', '').strip() if product_price else '0.0'
        old_price = old_price.replace('Rs', '').replace('Rs.', '').replace(',', '').replace('.', '').strip() if old_price else '0.0'
        product_price = float(product_price)
        old_price = float(old_price)

        # Extract image URL
        image_tag = soup.find('a', {'data-fancybox': 'gallery'})
        product_image_url = 'https://example.com/default-image.jpg'
        if image_tag:
            img_tag = image_tag.find('img')
            if img_tag:
                product_image_url = img_tag['src']

        if product_image_url.startswith('/'):
            product_image_url = 'https://d1ugx7ghroxfxae.cloudfront.net' + product_image_url

        company_name = 'singhagiri.lk'
        store_product_data(product_name, product_price, old_price, product_image_url, company_name, product_url, category)

        print(f"Product scraped and stored successfully: {product_name}")

    except Exception as e:
        print(f"Error scraping product details from {product_url}: {e}")

# Singer Product Scraping Function
def scrape_singer_product_details(product_url, category):
    try:
        response = session.get(product_url, verify=False, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract product name
        product_name_tag = soup.find('h5', class_='single-page-product-title')
        product_name = product_name_tag.text.strip() if product_name_tag else 'N/A'

        # Extract product price
        product_price_tag = soup.find('h4', class_='fw-bold mb-0 sing-pro-price')
        if not product_price_tag:
            product_price_tag = soup.find('h4', class_='text-primary fw-bold mb-0 productprice')
        old_price_tag = soup.find('span', class_='text-decoration-line-through text-muted fs-6')
        
        new_price = 0.0
        old_price = 0.0

        if product_price_tag:
            new_price_str = product_price_tag.find(text=True, recursive=False)
            if new_price_str:
                new_price_str = new_price_str.strip().replace('Rs.', '').replace(',', '').replace(' ', '')
                if new_price_str:
                    new_price = float(new_price_str)

        if old_price_tag:
            old_price_str = old_price_tag.text.strip().replace('Rs.', '').replace(',', '').replace(' ', '')
            if old_price_str:
                old_price = float(old_price_str)

        # Extract image URL
        image_tag = soup.find('a', {'data-fancybox': 'gallery'})
        product_image_url = 'N/A'
        if image_tag:
            img_tag = image_tag.find('img')
            if img_tag:
                product_image_url = img_tag['src']

        company_name = 'singersl.com'
        store_product_data(product_name, new_price, old_price, product_image_url, company_name, product_url, category)

    except Exception as e:
        print(f"Error scraping product details from {product_url}: {e}")

# Function to scrape product links from a single page
def scrape_listing_page(listing_url, category_name, site_type):
    try:
        time.sleep(random.uniform(1, 3))

        response = session.get(listing_url, verify=False, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Find all anchor tags with 'href' attribute
        product_links = soup.find_all('a', href=True)
        
        # Filter the links based on site type
        if site_type == 'bigdeals':
            valid_links = [link for link in product_links if f'/{category_name.lower()}/' in link['href']]
        elif site_type == 'singer' or site_type == 'singhagiri':
            valid_links = [link for link in product_links if '/product/' in link['href']]
        else:
            valid_links = []

        if not valid_links:
            print(f"No product links found on {listing_url}")
            return

        print(f"Found {len(valid_links)} product links.")

        # Loop through each product link and scrape its details
        for link in valid_links:
            product_url = link['href']
            
            # Build full URL
            if product_url.startswith('https://'):
                full_product_url = product_url
            else:
                if site_type == 'bigdeals':
                    full_product_url = 'https://bigdeals.lk' + product_url
                elif site_type == 'singer':
                    full_product_url = 'https://www.singersl.com' + product_url
                elif site_type == 'singhagiri':
                    full_product_url = 'https://singhagiri.lk' + product_url

            print(f"Scraping product: {full_product_url}")
            
            # Add delay between product scraping
            time.sleep(random.uniform(0.5, 1.5))
            
            if site_type == 'singer':
                scrape_singer_product_details(full_product_url, category_name)
            elif site_type == 'singhagiri':
                scrape_singhagiri_product_details(full_product_url, category_name)
            elif site_type == 'bigdeals':
                scrape_bigdeals_product_details(full_product_url, category_name)

    except requests.exceptions.SSLError as e:
        print(f"SSL Error scraping listing page: {e}")
        print("SSL verification has been disabled but error persists")
    except Exception as e:
        print(f"Error scraping listing page: {e}")

# Function to scrape multiple pages in a category
def scrape_listing_page_with_pagination(base_url, total_pages, category_name, site_type):
    for page_number in range(1, total_pages + 1):
        page_url = f"{base_url}?page={page_number}"
        print(f"Scraping page {page_number}: {page_url}")
        scrape_listing_page(page_url, category_name, site_type)

# Categories with URLs for all three sites
categories = {
    'bigdeals': {
        'tv': 'https://bigdeals.lk/tv',
        'laptops': 'https://bigdeals.lk/laptops',
        'mobile_phones': 'https://bigdeals.lk/mobile_phones'
    },
    'singer': {
        'tv': 'https://www.singersl.com/products/entertainment/television',
        'laptops': 'https://www.singersl.com/products/electronics/laptops-notebooks',
        'mobile_phones': 'https://www.singersl.com/products/electronics/mobile-phones'
    },
    'singhagiri': {
        'tv': 'https://singhagiri.lk/products/television',
        'laptops': 'https://singhagiri.lk/products/computers-accessories/laptop',
        'mobile_phones': 'https://singhagiri.lk/products/mobile-phones'
    }
}

# Loop through all categories for all sites
for site_type, categories_for_site in categories.items():
    for category_name, category_url in categories_for_site.items():
        print(f"Starting to scrape category: {category_name} from site: {site_type}")
        scrape_listing_page_with_pagination(category_url, total_pages=1, category_name=category_name, site_type=site_type)
