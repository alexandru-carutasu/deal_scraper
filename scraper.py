import time
import random
import sqlite3
import undetected_chromedriver as uc
from datetime import date
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
    """Creates the database and tables if they don't exist."""
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
    """Inserts or updates product data and categories in the database."""
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
            
            cursor.execute("UPDATE products SET category = ? WHERE id = ?", (product.get('category', 'Uncategorized'), product_id))
        else:
            cursor.execute("INSERT INTO products (name, link, store, category) VALUES (?, ?, ?, ?)",
                           (product['name'], product['link'], product['store'], product.get('category', 'Uncategorized')))
            product_id = cursor.lastrowid
        
        cursor.execute("INSERT INTO prices (product_id, price, stock_status, scrape_date) VALUES (?, ?, ?, ?)",
                       (product_id, product['price'], product['stock_status'], today))
    conn.commit()
    conn.close()
    print(f"✅ Database updated with {len(product_list)} entries for {today}.")


def classify_product_type_ai(product_names):
    """Uses AI to classify products as 'Main Product' or 'Accessory'."""
    if not product_names:
        return {}
    print("🤖 AI Step 1: Classifying product types...")
    classifier = pipeline("zero-shot-classification", model="facebook/bart-large-mnli")
    categories = ["Main Product", "Accessory"]
    results = classifier(product_names, candidate_labels=categories)
    
    classified_results = {}
    for res in results:
        classified_results[res['sequence']] = res['labels'][0]
    return classified_results

def categorize_products_ai(product_names, categories):
    """Uses AI to assign specific categories like 'Laptop', 'Smartphone'."""
    if not product_names:
        return {}
    print("🤖 AI Step 2: Assigning specific categories...")
    classifier = pipeline("zero-shot-classification", model="facebook/bart-large-mnli")
    results = classifier(product_names, candidate_labels=categories)
    
    categorized_results = {}
    for res in results:
        categorized_results[res['sequence']] = res['labels'][0]
    return categorized_results


def scrape_altex(product_name):
    all_products = []
    page_number = 1
    base_url = "https://altex.ro"
    formatted_product_name = quote_plus(product_name)

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
    """runs the full scrape and two-step AI classification process."""
    setup_database()
  
    altex_results = scrape_altex(product_to_search)
    
    if altex_results:
        product_names = [p['name'] for p in altex_results]
        
       
        classified_types = classify_product_type_ai(product_names)
        main_products = [p for p in altex_results if classified_types.get(p['name']) == 'Main Product']
        
        
        if main_products:
            main_product_names = [p['name'] for p in main_products]
            my_categories = ["Laptop", "Smartphone", "Mouse", "Keyboard", "Monitor", "Component", "Gaming Console"]
            final_categories = categorize_products_ai(main_product_names, my_categories)
            
          
            for product in main_products:
                product['category'] = final_categories.get(product['name'], 'Uncategorized')
        
        print(f"Found {len(main_products)} main products. Updating database.")
        update_database(main_products)
        return main_products
    
    return []