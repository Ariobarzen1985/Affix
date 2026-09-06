import os
import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

sqlite3 = None
try:
    import sqlite3
except ImportError:
    pass

app = Flask(__name__)
CORS(app)

DB_FILE = "afix_blockchain.db"
MASTER_TON_WALLET = "UQAQbW_kDwLvTaqnZsM6U8aU46oVA7vEDMbChOwTC719Hv4N"
AFIX_PRICE_TOMAN = 300000  # قیمت هر واحد AFIX معادل ۳۰۰,۰۰۰ تومان
GENESIS_ADDRESS = "AFIX_GMN_f89637364a"
GENESIS_INITIAL_BALANCE = 1100000.0

def init_db():
    """راه‌اندازی اولیه پایگاه داده و مقداردهی ولت جنسیس"""
    if sqlite3:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # جدول کیف پول کاربران
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS wallets (
                address TEXT PRIMARY KEY,
                balance REAL NOT NULL,
                last_mine_time TEXT
            )
        ''')
        
        # جدول بازار خرید و فروش P2P
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS p2p_orders (
                order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_address TEXT,
                amount_afix REAL,
                price_toman REAL,
                status TEXT
            )
        ''')
        
        # تزریق خودکار موجودی جنسیس در صورت عدم وجود
        cursor.execute("SELECT balance FROM wallets WHERE address = ?", (GENESIS_ADDRESS,))
        row = cursor.fetchone()
        if not row:
            cursor.execute("INSERT INTO wallets (balance, address) VALUES (?, ?)", (GENESIS_INITIAL_BALANCE, GENESIS_ADDRESS))
        
        conn.commit()
        conn.close()

init_db()

def get_live_ton_price():
    """دریافت قیمت لحظه‌ای تون برای اطلاعات صرافی"""
    try:
        response = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd", timeout=5)
        data = response.json()
        ton_usd = data.get("the-open-network", {}).get("usd", 5.0)
        return ton_usd * 60000
    except Exception:
        return 300000

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "node": "AFIX Mainnet Node",
        "status": "Online",
        "version": "3.0-Standalone",
        "afix_price_toman": AFIX_PRICE_TOMAN
    })

@app.route('/api/exchange/info', methods=['GET'])
def exchange_info():
    return jsonify({
        "master_wallet": MASTER_TON_WALLET,
        "afix_price_toman": AFIX_PRICE_TOMAN,
        "ton_price_toman": get_live_ton_price(),
        "daily_mining_reward": 0.5
    })

@app.route('/api/balance', methods=['GET'])
def get_balance():
    """استعلام موجودی و ارزش تومانی هر آدرس"""
    address = request.args.get('address')
    if not address:
        return jsonify({"error": "Address required"}), 400

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM wallets WHERE address = ?", (address,))
    row = cursor.fetchone()
    
    if row:
        balance = row[0]
    else:
        # اگر آدرس جدید بود، به طور پیش‌فرض با صفر ثبت میشه
        cursor.execute("INSERT INTO wallets (balance, address) VALUES (?, ?)", (0.0, address))
        conn.commit()
        balance = 0.0
    conn.close()

    return jsonify({
        "address": address,
        "balance": balance,
        "value_in_toman": balance * AFIX_PRICE_TOMAN
    })

@app.route('/api/mine', methods=['POST'])
def mine_token():
    """سیستم استخراج توکن از طریق درخواست کلاینت پایتونی"""
    data = request.json or {}
    address = data.get('address')
    if not address:
        return jsonify({"error": "Address required"}), 400

    reward_amount = 0.5  # پاداش هر بار استخراج

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM wallets WHERE address = ?", (address,))
    row = cursor.fetchone()

    if not row:
        cursor.execute("INSERT INTO wallets (balance, address) VALUES (?, ?)", (reward_amount, address))
        new_balance = reward_amount
    else:
        new_balance = row[0] + reward_amount
        cursor.execute("UPDATE wallets SET balance = ? WHERE address = ?", (new_balance, address))
    
    conn.commit()
    conn.close()
    
    return jsonify({
        "status": "success",
        "message": "پاداش استخراج با موفقیت به حساب شما واریز شد",
        "balance": new_balance,
        "reward": reward_amount
    })

# --- بازار P2P ---

@app.route('/api/p2p/create_order', methods=['POST'])
def create_p2p_order():
    """ثبت سفارش فروش AFIX در بازار P2P"""
    data = request.json or {}
    seller_address = data.get('address')
    try:
        amount_afix = float(data.get('amount_afix', 0))
    except ValueError:
        return jsonify({"error": "مقدار نامعتبر است"}), 400

    if amount_afix <= 0 or not seller_address:
        return jsonify({"error": "اطلاعات ناقص یا نامعتبر است"}), 400

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("SELECT balance FROM wallets WHERE address = ?", (seller_address,))
    row = cursor.fetchone()
    if not row or row[0] < amount_afix:
        conn.close()
        return jsonify({"error": "موجودی کافی نیست"}), 400

    # کسر موقت از موجودی و ثبت سفارش
    cursor.execute("UPDATE wallets SET balance = balance - ? WHERE address = ?", (amount_afix, seller_address))
    cursor.execute("INSERT INTO p2p_orders (seller_address, amount_afix, price_toman, status) VALUES (?, ?, ?, ?)",
                   (seller_address, amount_afix, amount_afix * AFIX_PRICE_TOMAN, "active"))
    conn.commit()
    conn.close()

    return jsonify({"status": "success", "message": "سفارش فروش با موفقیت در بازار P2P ثبت شد"})

@app.route('/api/p2p/orders', methods=['GET'])
def get_p2p_orders():
    """دریافت لیست سفارشات فعال بازار"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT order_id, seller_address, amount_afix, price_toman FROM p2p_orders WHERE status = 'active'")
    rows = cursor.fetchall()
    conn.close()

    orders = []
    for r in rows:
        orders.append({
            "order_id": r[0],
            "seller": r[1],
            "amount_afix": r[2],
            "price_toman": r[3]
        })
    return jsonify({"orders": orders})

@app.route('/api/stats', methods=['GET'])
def public_stats():
    """آمار کلی شبکه"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*), SUM(balance) FROM wallets")
    user_count, total_supply = cursor.fetchone()
    conn.close()

    return jsonify({
        "status": "success",
        "total_users": user_count or 0,
        "total_circulating_balance": total_supply or 0,
        "master_wallet": MASTER_TON_WALLET
    })

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
