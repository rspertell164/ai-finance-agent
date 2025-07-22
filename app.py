from flask import Flask, render_template, request, redirect, url_for
import sqlite3
import datetime
import os
import openai

app = Flask(__name__)

DB_NAME = 'database.db'  # Updated for PostgreSQL compatibility with SQLite fallback
openai.api_key = os.getenv("OPENAI_API_KEY")

# === Database Setup (Optional SQLite Fallback) ===
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS investors (
        id INTEGER PRIMARY KEY,
        name TEXT,
        risk_tolerance TEXT,
        sector_preference TEXT,
        avg_investment_amount REAL,
        avg_hold_duration INTEGER
    )""")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS investments (
        id INTEGER PRIMARY KEY,
        investor_id INTEGER,
        stock_symbol TEXT,
        sector TEXT,
        amount REAL,
        buy_date TEXT,
        sell_date TEXT,
        FOREIGN KEY(investor_id) REFERENCES investors(id)
    )""")
    conn.commit()
    conn.close()

# === Core Logic ===
def update_profile_statistics(investor_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    SELECT sector, amount, buy_date, sell_date FROM investments WHERE investor_id=?
    """, (investor_id,))
    records = cursor.fetchall()

    if not records:
        return

    total_amount = 0
    sector_count = {}
    total_days_held = 0
    hold_count = 0

    for sector, amount, buy, sell in records:
        total_amount += amount
        sector_count[sector] = sector_count.get(sector, 0) + 1
        if sell:
            days_held = (datetime.datetime.strptime(sell, "%Y-%m-%d") -
                         datetime.datetime.strptime(buy, "%Y-%m-%d")).days
            total_days_held += days_held
            hold_count += 1

    avg_amount = total_amount / len(records)
    favorite_sector = max(sector_count.items(), key=lambda x: x[1])[0]
    avg_hold_duration = (total_days_held // hold_count) if hold_count > 0 else None

    cursor.execute("""
    UPDATE investors
    SET avg_investment_amount=?, sector_preference=?, avg_hold_duration=?
    WHERE id=?
    """, (avg_amount, favorite_sector, avg_hold_duration, investor_id))
    conn.commit()
    conn.close()

def generate_stock_recommendations(investor):
    try:
        prompt = f"""
        Based on the following investor profile, recommend 3 U.S. stocks with brief reasons:
        - Risk Tolerance: {investor[2]}
        - Preferred Sector: {investor[3] or 'None'}
        - Average Investment Amount: ${investor[4] or 'N/A'}
        - Average Holding Period: {investor[5] or 'N/A'} days
        Format: Stock Symbol - Reason
        """
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Error generating recommendations: {e}"

# === Routes ===
@app.route('/')
def index():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM investors')
    investors = cursor.fetchall()
    conn.close()
    return render_template('index.html', investors=investors)

@app.route('/add_investor', methods=['POST'])
def add_investor():
    name = request.form['name']
    risk = request.form['risk']
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO investors (name, risk_tolerance) VALUES (?, ?)', (name, risk))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/investor/<int:id>')
def investor_detail(id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM investors WHERE id=?', (id,))
    investor = cursor.fetchone()
    cursor.execute('SELECT * FROM investments WHERE investor_id=?', (id,))
    investments = cursor.fetchall()
    conn.close()

    recommendations = generate_stock_recommendations(investor)
    return render_template('investor_detail.html', investor=investor, investments=investments, recommendations=recommendations)

@app.route('/add_investment/<int:id>', methods=['POST'])
def add_investment(id):
    symbol = request.form['symbol']
    sector = request.form['sector']
    amount = float(request.form['amount'])
    buy_date = request.form['buy_date']
    sell_date = request.form['sell_date'] if request.form['sell_date'] else None

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO investments (investor_id, stock_symbol, sector, amount, buy_date, sell_date)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (id, symbol, sector, amount, buy_date, sell_date))
    conn.commit()
    conn.close()

    update_profile_statistics(id)
    return redirect(url_for('investor_detail', id=id))

if __name__ == '__main__':
    if not os.path.exists(DB_NAME):
        init_db()
    app.run(host='0.0.0.0', port=5000)
