# app.py
from flask import Flask, render_template, request, redirect, url_for
import sqlite3
import os
from scraper import run_scraper

app = Flask(__name__)
app.secret_key = 'your_super_secret_key'
DB_NAME = 'products.db'

@app.route('/')
def index():
    """Main page: Displays all products from the database with their ALL-TIME LOWEST price."""
    products = []
    if os.path.exists(DB_NAME):
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # --- UPDATED QUERY ---
        # This query now finds the minimum price for each product and joins back
        # to get the other details from that specific historical entry.
        query = """
        SELECT
            p.name,
            p.link,
            p.store,
            pr.price,
            pr.stock_status
        FROM
            products p
        JOIN
            prices pr ON p.id = pr.product_id
        JOIN
            (SELECT product_id, MIN(price) as min_price
             FROM prices
             WHERE price > 0
             GROUP BY product_id) as min_prices ON pr.product_id = min_prices.product_id AND pr.price = min_prices.min_price
        GROUP BY
            p.id
        ORDER BY
            p.name ASC
        """
        products = cursor.execute(query).fetchall()
        conn.close()
        
    return render_template('index.html', products=products)

@app.route('/search', methods=['GET', 'POST'])
def search():
    """Handles both displaying the search form and processing it."""
    if request.method == 'POST':
        product_name = request.form['product_name']
        if product_name:
            run_scraper(product_name)
            return redirect(url_for('index'))
    return render_template('search.html')

if __name__ == '__main__':
    app.run(debug=True)