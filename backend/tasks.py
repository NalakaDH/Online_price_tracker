from celery import Celery
from backend.app import app, scrape_listing_page_with_pagination  # Import your Flask app and scraping function
import os

# Set up Celery with Redis as the broker
celery = Celery(
    'tasks',
    broker=os.getenv('REDIS_URL', 'redis://localhost:6379/0')  # Using Redis as the message broker
)

celery.conf.update(app.config)

@celery.task
def fetch_and_store_price_data():
    """
    Periodic task to scrape products from competitors and update the database
    """
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

    # Loop through categories and scrape data for each site
    for site_type, categories_for_site in categories.items():
        for category_name, category_url in categories_for_site.items():
            print(f"Starting to scrape category: {category_name} from site: {site_type}")
            scrape_listing_page_with_pagination(category_url, total_pages=1, category_name=category_name, site_type=site_type)

# Schedule the task to run periodically (every 30 minutes)
from celery.schedules import crontab

celery.conf.beat_schedule = {
    'scrape-price-data': {
        'task': 'tasks.fetch_and_store_price_data',
        'schedule': crontab(minute='*/30'),  # Run every 30 minutes (you can adjust this)
    },
}
