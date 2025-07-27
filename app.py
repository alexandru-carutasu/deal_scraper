# app.py
from flask import Flask, render_template, request, redirect, url_for
import sqlite3
import os
from scraper import run_scraper, setup_database

app = Flask(__name__)
app.secret_key = 'your_super_secret_key'
DB_NAME = 'products.db'

@app.route('/')
def index():
    if not os.path.exists(DB_NAME):
        setup_database()
        
    products = []
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    query = """
    SELECT p.name, p.link, p.store, p.category, pr.price, pr.stock_status, pr.scrape_date
    FROM products p
    JOIN prices pr ON p.id = pr.product_id
    WHERE pr.scrape_date = (SELECT MAX(scrape_date) FROM prices WHERE product_id = p.id)
    ORDER BY p.name ASC
    """
    products = cursor.execute(query).fetchall()
    conn.close()
    
    return render_template('index.html', products=products)

@app.route('/search', methods=['GET', 'POST'])
def search():
    """Handles the search form and runs the full scraper and AI pipeline."""
    if request.method == 'POST':
        product_name = request.form['product_name']
        if product_name:
            run_scraper(product_name)
            return redirect(url_for('index'))
    return render_template('search.html')

if __name__ == '__main__':
    app.run(debug=True)