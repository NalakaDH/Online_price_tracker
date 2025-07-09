import os
import sys
import time
import random
from datetime import datetime
import mysql.connector
from competitor_scraper import CompetitorScraper

def get_database_connection():
    """Get database connection"""
    return mysql.connector.connect(
        host=os.getenv('MYSQL_HOST', 'localhost'),
        user=os.getenv('MYSQL_USER', 'tracker_user'),
        password=os.getenv('MYSQL_PASSWORD', 'password'),
        database=os.getenv('MYSQL_DB', 'price_tracker')
    )

def update_all_competitor_prices():
    """Update prices for all active competitor products"""
    try:
        # Initialize scraper
        scraper = CompetitorScraper()
        
        # Get database connection
        conn = get_database_connection()
        cursor = conn.cursor()
        
        # Get all active competitor products
        cursor.execute('''
            SELECT cp.id, cp.competitor_url, c.name as competitor_name, 
                   p.name as product_name
            FROM competitor_products cp
            JOIN competitors c ON cp.competitor_id = c.id
            JOIN product_details p ON cp.product_id = p.id
            WHERE cp.is_active = TRUE AND c.status = 'active'
        ''')
        
        competitor_products = cursor.fetchall()
        
        updated_count = 0
        error_count = 0
        
        print(f"Starting price update for {len(competitor_products)} competitor products...")
        
        for cp_id, url, competitor_name, product_name in competitor_products:
            try:
                print(f"Scraping {competitor_name} - {product_name}")
                
                # Scrape price data
                price_data = scraper.scrape_competitor_price(url, competitor_name)
                
                if price_data:
                    # Insert price history
                    cursor.execute('''
                        INSERT INTO competitor_price_history 
                        (competitor_product_id, price, old_price, availability, scraped_at)
                        VALUES (%s, %s, %s, %s, %s)
                    ''', (
                        cp_id,
                        price_data['price'],
                        price_data['old_price'],
                        price_data['availability'],
                        price_data['scraped_at']
                    ))
                    
                    updated_count += 1
                    print(f"✓ Updated: Rs. {price_data['price']}")
                else:
                    error_count += 1
                    print(f"✗ Failed to scrape")
                
                # Rate limiting
                time.sleep(random.uniform(3, 7))
                
            except Exception as e:
                error_count += 1
                print(f"✗ Error: {str(e)}")
                continue
        
        # Update competitor last_scraped timestamps
        cursor.execute('''
            UPDATE competitors c
            JOIN competitor_products cp ON c.id = cp.competitor_id
            SET c.last_scraped = NOW()
            WHERE cp.is_active = TRUE AND c.status = 'active'
        ''')
        
        # Commit all changes
        conn.commit()
        cursor.close()
        conn.close()
        
        # Print summary
        print(f"\n{'='*50}")
        print(f"Price Update Summary:")
        print(f"Successfully updated: {updated_count}")
        print(f"Errors: {error_count}")
        print(f"Total processed: {len(competitor_products)}")
        print(f"Success rate: {(updated_count/len(competitor_products)*100):.1f}%")
        print(f"{'='*50}")
        
    except Exception as e:
        print(f"Critical error in price update: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    update_all_competitor_prices()
