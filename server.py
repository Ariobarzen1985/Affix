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
AFIX_PRICE_TOMAN = 10000  # هر AFIX معادل ۱۰,۰۰۰ تومان

# آیدی تلگرامی ادمین کل (برای دسترسی به پنل مدیریت)
ADMIN_TELEGRAM_IDS = ["YOUR_ADMIN_TELEGRAM_ID_HERE"] # آیدی عددی تلگرام خودت را اینجا بگذار

def init_db():
    """ساخت جداول پایگاه داده در صورت عدم وجود"""
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
        conn.commit()
        conn.close()

init_db()

def get_live_ton_price():
    """دریافت قیمت لحظه‌ای تون"""
    try:
        response = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd", timeout=5)
        data = response.json()
        ton_usd = data.get("the-open-network", {}).get("usd", 5.0)
        return ton_usd * 60000
    except Exception:
        return 300000

@app.route('/')
def home():
    return jsonify({"node": "AFIX Network", "status": "Online", "version": "2.0-P2P"})

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
        cursor.execute("INSERT INTO wallets (balance, address) VALUES (?, ?)", (0.0, address))
        conn.commit()
        balance = 0.0
    conn.close()
    return jsonify({"address": address, "balance": balance})

@app.route('/api/mine', methods=['POST'])
def mine_token():
    """بخش استخراج روزانه نیم افیکس"""
    data = request.json
    address = data.get('address')
    if not address:
        return jsonify({"error": "Address required"}), 400

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM wallets WHERE address = ?", (address,))
    row = cursor.fetchone()

    if not row:
        cursor.execute("INSERT INTO wallets (balance, address) VALUES (?, ?)", (0.5, address))
        new_balance = 0.5
    else:
        new_balance = row[0] + 0.5
        cursor.execute("UPDATE wallets SET balance = ? WHERE address = ?", (new_balance, address))
    
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "message": "پاداش استخراج واریز شد", "balance": new_balance})

# --- بخش بازار P2P (خرید و فروش مستقیم) ---

@app.route('/api/p2p/create_order', methods=['POST'])
def create_p2p_order():
    """کاربر یک سفارش فروش ثبت می‌کند تا دیگران بخرند"""
    data = request.json
    seller_address = data.get('address')
    amount_afix = float(data.get('amount_afix', 0))

    if amount_afix <= 0:
        return jsonify({"error": "مقدار نامعتبر است"}), 400

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # بررسی موجودی فروشنده
    cursor.execute("SELECT balance FROM wallets WHERE address = ?", (seller_address,))
    row = cursor.fetchone()
    if not row or row[0] < amount_afix:
        conn.close()
        return jsonify({"error": "موجودی کافی نیست"}), 400

    # کسر موقت از موجودی فروشنده و ثبت در بازار P2P
    cursor.execute("UPDATE wallets SET balance = balance - ? WHERE address = ?", (amount_afix, seller_address))
    cursor.execute("INSERT INTO p2p_orders (seller_address, amount_afix, price_toman, status) VALUES (?, ?, ?, ?)",
                   (seller_address, amount_afix, amount_afix * AFIX_PRICE_TOMAN, "active"))
    conn.commit()
    conn.close()

    return jsonify({"status": "success", "message": "سفارش فروش با موفقیت در بازار ثبت شد"})

@app.route('/api/p2p/orders', methods=['GET'])
def get_p2p_orders():
    """نمایش لیست سفارشات فعال برای خرید"""
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

# --- پنل ادمین ---

@app.route('/api/admin/stats', methods=['GET'])
def admin_stats():
    """پنل مدیریت اختصاصی ادمین"""
    admin_id = request.args.get('admin_id')
    # امنیت: بررسی اینکه درخواست‌کننده واقعاً ادمین باشد
    if admin_id not in ADMIN_TELEGRAM_IDS:
        return jsonify({"error": "دسترسی غیرمجاز! شما ادمین نیستید."}), 403

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
