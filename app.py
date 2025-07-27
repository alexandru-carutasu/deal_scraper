# app.py
from flask import Flask, render_template, request, redirect, url_for
import sqlite3
import os
from scraper import run_scraper, categorize_products_ai, setup_database

app = Flask(__name__)
app.secret_key = 'your_super_secret_key' 
DB_NAME = 'products.db'

@app.route('/')
def index():
    """Main page: Displays all products, with optional category filtering."""
    if not os.path.exists(DB_NAME):
        setup_database()
        
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

  
    selected_category = request.args.get('category')
    
    categories = cursor.execute("SELECT DISTINCT category FROM products ORDER BY category").fetchall()


    query = """
    SELECT p.name, p.link, p.store, p.category, pr.price, pr.stock_status, pr.scrape_date
    FROM products p
    JOIN prices pr ON p.id = pr.product_id
    WHERE pr.scrape_date = (SELECT MAX(scrape_date) FROM prices WHERE product_id = p.id)
    """
    params = []
    if selected_category:
        query += " AND p.category = ?"
        params.append(selected_category)
    
    query += " ORDER BY p.name ASC"
    
    products = cursor.execute(query, params).fetchall()
    conn.close()
    
    return render_template('index.html', products=products, categories=categories, selected_category=selected_category)

@app.route('/search', methods=['GET', 'POST'])
def search():
    if request.method == 'POST':
        product_name = request.form['product_name']
        if product_name:
            live_results = run_scraper(product_name)
            if live_results:
                my_categories = ["Laptop", "Smartphone", "Mouse", "Keyboard", "Monitor", "Accessory", "Component"]
                product_names_to_categorize = [p['name'] for p in live_results]
                ai_categorized_list = categorize_products_ai(product_names_to_categorize, my_categories)
                
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                for item in ai_categorized_list:
                    cursor.execute("UPDATE products SET category = ? WHERE name = ?", (item['category'], item['name']))
                conn.commit()
                conn.close()
                print("✅ AI categories saved to database.")

            return redirect(url_for('index'))
            
    return render_template('search.html')

if __name__ == '__main__':
    app.run(debug=True)