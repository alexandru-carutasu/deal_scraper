import time
import csv
import random
import sqlite3
from datetime import date
import undetected_chromedriver as uc
from bs4 import BeautifulSoup
from urllib.parse import quote_plus
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from transformers import pipeline


USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
]
WINDOW_SIZES = ["1920,1080", "1366,768", "1536,864"]
DB_NAME = 'products.db'


def setup_database():
    """Creates the database and tables with the correct schema."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
  
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            link TEXT,
            store TEXT,
            category TEXT DEFAULT 'Uncategorized'
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS prices (
            product_id INTEGER,
            price REAL,
            stock_status TEXT,
            scrape_date DATE,
            FOREIGN KEY(product_id) REFERENCES products(id)
        )
    ''')
    conn.commit()
    conn.close()

def update_database(product_list):
    if not product_list:
        return
        
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    today = date.today().isoformat()

    for product in product_list:
        cursor.execute("SELECT id FROM products WHERE name = ?", (product['name'],))
        result = cursor.fetchone()
        
        if result:
            product_id = result[0]
        else:
            cursor.execute("INSERT INTO products (name, link, store) VALUES (?, ?, ?)",
                           (product['name'], product['link'], product['store']))
            product_id = cursor.lastrowid
        
        cursor.execute("INSERT INTO prices (product_id, price, stock_status, scrape_date) VALUES (?, ?, ?, ?)",
                       (product_id, product['price'], product['stock_status'], today))
    conn.commit()
    conn.close()
    print(f"✅ Database updated with {len(product_list)} entries for {today}.")


def categorize_products_ai(product_names, categories):
    """
    uses a zero-shot classification model to categorize products
    """
    print("Initializing AI classifier... (This may download a model on first run)")
    classifier = pipeline("zero-shot-classification", model="facebook/bart-large-mnli")
    
    print(f"Categorizing {len(product_names)} products...")
    results = classifier(product_names, candidate_labels=categories)
    
    categorized_results = []
    for res in results:
        categorized_results.append({
            'name': res['sequence'],
            'category': res['labels'][0]
        })
    return categorized_results


def scrape_altex(product_name, exclusion_keywords):

    all_products = []
    page_number = 1
    base_url = "https://altex.ro"
    formatted_product_name = quote_plus(product_name)
    search_keywords = product_name.lower().split()

    print(f"🔎 Initializing stealth browser for '{product_name}' on Altex.ro...")

    options = uc.ChromeOptions()
    options.add_argument(f'--user-agent={random.choice(USER_AGENTS)}')
    options.add_argument(f"--window-size={random.choice(WINDOW_SIZES)}")
    options.add_argument('--incognito')
    
    driver = uc.Chrome(options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    try:
        while True:
            if page_number == 1:
                current_url = f"{base_url}/cauta/?q={formatted_product_name}"
            else:
                current_url = f"{base_url}/cauta/filtru/p/{page_number}/?q={formatted_product_name}"

            print(f"Scraping page {page_number}: {current_url}")
            driver.get(current_url)
            
            try:
                WebDriverWait(driver, 20).until(
                    EC.visibility_of_element_located((By.CSS_SELECTOR, "li.Products-item"))
                )
            except Exception:
                print(f"No more products found on page {page_number}. Finished scraping Altex.")
                break

            soup = BeautifulSoup(driver.page_source, 'html.parser')
            product_containers = soup.select('li.Products-item')

            for container in product_containers:
                name_element = container.select_one('span.Product-name')
                price_element = container.select_one('span.Price-int')
                link_element = container.find('a', href=True)
                stock_element = container.select_one('div.Badge-stock')

                if name_element and price_element and link_element:
                    name = name_element.get_text(strip=True)
                    price_text = price_element.get_text(strip=True)
                    link = base_url + link_element['href']
                    stock_status = stock_element.get_text(strip=True) if stock_element else "N/A"
                    
                    name_lower = name.lower()
                    has_all_keywords = all(keyword in name_lower for keyword in search_keywords)
                    has_exclusion_keyword = any(ex_keyword.lower() in name_lower for ex_keyword in exclusion_keywords)

                    if has_all_keywords and not has_exclusion_keyword:
                        try:
                            price = float(price_text.replace('.', ''))
                        except (ValueError, AttributeError):
                            price = 0.0
                        
                        all_products.append({
                            'name': name, 'price': price, 'stock_status': stock_status,
                            'link': link, 'store': 'Altex'
                        })
            
            page_number += 1
            time.sleep(random.uniform(2.5, 5.5))
    finally:
        driver.quit()
        print("\nAltex browser closed.")
    
    return all_products


def run_scraper(product_to_search):
    """
    Main function that runs the scraper and updates the database.
    """
    product_exclusion_keywords = [
        'folie', 'husă', 'carcasă', 'încărcător', 'cablu', 
        'suport', 'baterie externa', 'sticla', 'protectie', 'geam', 'securizat', 'rucsac', 'geanta'
    ]
    
    setup_database()
    altex_results = scrape_altex(product_to_search, product_exclusion_keywords)
    update_database(altex_results)
    
    return altex_results