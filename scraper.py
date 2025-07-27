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

# --- Configuration ---
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36'
]
WINDOW_SIZES = ["1920,1080", "1366,768", "1536,864"]
DB_NAME = 'products.db'

# --- 1. Database Functions ---
def setup_database():
    """Creates the database and tables if they don't exist."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Create a table for products
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            link TEXT,
            store TEXT
        )
    ''')
    # Create a table for price history
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
    """Inserts new products or updates the price if it's lower."""
    if not product_list:
        return
        
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    today = date.today().isoformat()
    updated_count = 0
    new_count = 0

    for product in product_list:
        cursor.execute("SELECT id FROM products WHERE name = ?", (product['name'],))
        result = cursor.fetchone()
        
        if result: # Product exists
            product_id = result[0]
            # Get the last known price
            cursor.execute("SELECT price FROM prices WHERE product_id = ? ORDER BY scrape_date DESC LIMIT 1", (product_id,))
            last_price_result = cursor.fetchone()
            last_price = last_price_result[0] if last_price_result else float('inf')

            # Only add a new price entry if the new price is lower
            if product['price'] > 0 and product['price'] < last_price:
                cursor.execute("INSERT INTO prices (product_id, price, stock_status, scrape_date) VALUES (?, ?, ?, ?)",
                               (product_id, product['price'], product['stock_status'], today))
                updated_count += 1
        else: # New product
            cursor.execute("INSERT INTO products (name, link, store) VALUES (?, ?, ?)",
                           (product['name'], product['link'], product['store']))
            product_id = cursor.lastrowid
            cursor.execute("INSERT INTO prices (product_id, price, stock_status, scrape_date) VALUES (?, ?, ?, ?)",
                           (product_id, product['price'], product['stock_status'], today))
            new_count += 1

    conn.commit()
    conn.close()
    print(f"✅ Database updated. New products: {new_count}, Prices updated: {updated_count}.")
    """Inserts or updates product data in the database."""
    if not product_list:
        return
        
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    today = date.today().isoformat()

    for product in product_list:
        # Check if product exists
        cursor.execute("SELECT id FROM products WHERE name = ?", (product['name'],))
        result = cursor.fetchone()
        
        if result:
            product_id = result[0]
        else:
            # Insert new product if it doesn't exist
            cursor.execute("INSERT INTO products (name, link, store) VALUES (?, ?, ?)",
                           (product['name'], product['link'], product['store']))
            product_id = cursor.lastrowid
        
        # Insert the new price entry for today
        cursor.execute("INSERT INTO prices (product_id, price, stock_status, scrape_date) VALUES (?, ?, ?, ?)",
                       (product_id, product['price'], product['stock_status'], today))

    conn.commit()
    conn.close()
    print(f"✅ Database updated with {len(product_list)} entries for {today}.")

# --- 2. Opportunity Analysis Function ---
def analyze_opportunities():
    """Analyzes the database to find buying opportunities and returns them as a list."""
    print("\n🔬 Analyzing price history for opportunities...")
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    query = """
    SELECT
        p.name,
        latest.price as current_price,
        MIN(h.price) as min_price,
        AVG(h.price) as avg_price
    FROM products p
    JOIN prices latest ON p.id = latest.product_id
    JOIN prices h ON p.id = h.product_id
    WHERE latest.scrape_date = (SELECT MAX(scrape_date) FROM prices WHERE product_id = p.id)
    GROUP BY p.id
    HAVING latest.price > 0
    """
    
    opportunities_list = []
    try:
        for row in cursor.execute(query):
            # Check for all-time low price
            if row['current_price'] <= row['min_price']:
                 opportunities_list.append(f"🔥 HOT DEAL! '{row['name']}' is at its all-time low price: {row['current_price']:.2f} Lei")
            # Check for price significantly below average
            elif row['current_price'] < row['avg_price'] * 0.85:
                 opportunities_list.append(f"💡 Good Deal! '{row['name']}' is 15%+ below its average price. Now: {row['current_price']:.2f} Lei (Avg: {row['avg_price']:.2f} Lei)")
    except sqlite3.OperationalError as e:
        print(f"Database query failed, likely empty: {e}")

    conn.close()
    
    if opportunities_list:
        print("--- Opportunity Report ---")
        for opp in opportunities_list:
            print(opp)
    else:
        print("No special deals found based on historical data today.")
        
    return opportunities_list

# --- 3. Scraper Function ---
def scrape_altex(product_name, exclusion_keywords):
    """
    Scrapes Altex.ro using a stealth browser to gather product data.
    """
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

# --- 4. Main Orchestrator for Flask ---
def run_scraper(product_to_search):
    """
    Main function that runs the scraper, updates the database, and returns the live results.
    """
    product_exclusion_keywords = [
        'folie', 'husă', 'carcasă', 'încărcător', 'cablu', 
        'suport', 'baterie externa', 'sticla', 'protectie', 'geam', 'securizat', 'rucsac', 'geanta'
    ]
    
    setup_database()
    altex_results = scrape_altex(product_to_search, product_exclusion_keywords)
    update_database(altex_results)
    
    return altex_results