import requests
from bs4 import BeautifulSoup
import re
import time
import random
from urllib.parse import urlparse
from datetime import datetime

class CompetitorScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive'
        })
    
    def scrape_competitor_price(self, url, competitor_name):
        """Scrape price from competitor URL"""
        try:
            # Add delay to be respectful
            time.sleep(random.uniform(2, 5))
            
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Site-specific price extraction
            domain = urlparse(url).netloc.lower()
            
            if 'bigdeals.lk' in domain:
                return self._extract_bigdeals_price(soup)
            elif 'singersl.com' in domain:
                return self._extract_singer_price(soup)
            elif 'singhagiri.lk' in domain:
                return self._extract_singhagiri_price(soup)
            else:
                return self._extract_generic_price(soup)
                
        except Exception as e:
            print(f"Error scraping {url}: {e}")
            return None
    
    def _extract_bigdeals_price(self, soup):
        """Extract price from BigDeals"""
        try:
            price_tag = soup.find('span', class_='sell-price')
            old_price_tag = soup.find('span', class_='m-price')
            
            current_price = self._clean_price(price_tag.text if price_tag else '0')
            old_price = self._clean_price(old_price_tag.text if old_price_tag else '0')
            
            return {
                'price': current_price,
                'old_price': old_price if old_price > 0 else None,
                'availability': 'In Stock',
                'scraped_at': datetime.now()
            }
        except Exception as e:
            print(f"Error extracting BigDeals price: {e}")
            return None
    
    def _extract_singer_price(self, soup):
        """Extract price from Singer"""
        try:
            price_selectors = [
                'h4.fw-bold.mb-0.sing-pro-price',
                'h4.text-primary.fw-bold.mb-0.productprice',
                '.price'
            ]
            
            current_price = 0
            for selector in price_selectors:
                price_tag = soup.select_one(selector)
                if price_tag:
                    current_price = self._clean_price(price_tag.get_text())
                    break
            
            old_price_tag = soup.select_one('span.text-decoration-line-through')
            old_price = self._clean_price(old_price_tag.get_text() if old_price_tag else '0')
            
            return {
                'price': current_price,
                'old_price': old_price if old_price > 0 else None,
                'availability': 'In Stock',
                'scraped_at': datetime.now()
            }
        except Exception as e:
            print(f"Error extracting Singer price: {e}")
            return None
    
    def _extract_singhagiri_price(self, soup):
        """Extract price from Singhagiri"""
        try:
            selling_price_tag = soup.select_one('div.selling-price span.data')
            current_price = self._clean_price(selling_price_tag.get_text() if selling_price_tag else '0')
            
            old_price_tag = soup.select_one('div.strikeout')
            old_price = self._clean_price(old_price_tag.get_text() if old_price_tag else '0')
            
            return {
                'price': current_price,
                'old_price': old_price if old_price > 0 else None,
                'availability': 'In Stock',
                'scraped_at': datetime.now()
            }
        except Exception as e:
            print(f"Error extracting Singhagiri price: {e}")
            return None
    
    def _extract_generic_price(self, soup):
        """Generic price extraction for unknown sites"""
        try:
            price_selectors = [
                '.price', '.product-price', '.current-price',
                '[class*="price"]', '[data-price]',
                '.cost', '.amount', '.value'
            ]
            
            for selector in price_selectors:
                price_tag = soup.select_one(selector)
                if price_tag:
                    price_text = price_tag.get_text()
                    price = self._clean_price(price_text)
                    if price > 0:
                        return {
                            'price': price,
                            'old_price': None,
                            'availability': 'In Stock',
                            'scraped_at': datetime.now()
                        }
            
            return None
        except Exception as e:
            print(f"Error with generic price extraction: {e}")
            return None
    
    def _clean_price(self, price_text):
        """Clean and convert price text to float"""
        if not price_text:
            return 0.0
        
        # Remove currency symbols and formatting
        cleaned = re.sub(r'[^\d.]', '', str(price_text).replace(',', ''))
        
        try:
            return float(cleaned) if cleaned else 0.0
        except ValueError:
            return 0.0
