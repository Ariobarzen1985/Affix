import os
import hashlib
import time
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
AFIX_PRICE_TOMAN = 300000
GENESIS_ADDRESS = "AFIX_GMN_f89637364a"
GENESIS_INITIAL_BALANCE = 1100000.0

MINING_DIFFICULTY = 4
MINING_REWARD = 0.5
MAX_DAILY_EARN = 5.0  # سقف روزانه

def init_db():
    if sqlite3:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # جدول با فیلد ذخیره تایم‌استمپ آخرین استخراج
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS wallets (
                address TEXT PRIMARY KEY,
                balance REAL NOT NULL,
                daily_earned REAL DEFAULT 0.0,
                last_mine_timestamp REAL DEFAULT 0.0
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS p2p_orders (
                order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_address TEXT,
                amount_afix REAL,
                price_toman REAL,
                status TEXT
            )
        ''')
        
        cursor.execute("SELECT balance FROM wallets WHERE address = ?", (GENESIS_ADDRESS,))
        row = cursor.fetchone()
        if not row:
            cursor.execute("INSERT INTO wallets (balance, address, daily_earned, last_mine_timestamp) VALUES (?, ?, ?, ?)", 
                           (GENESIS_INITIAL_BALANCE, GENESIS_ADDRESS, 0.0, 0.0))
        
        conn.commit()
        conn.close()

init_db()

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "node": "AFIX Mainnet Node",
        "status": "Online",
        "version": "3.3-TimerPoW",
        "max_daily_earn": MAX_DAILY_EARN
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
        cursor.execute("INSERT INTO wallets (balance, address, daily_earned, last_mine_timestamp) VALUES (?, ?, ?, ?)", 
                       (0.0, address, 0.0, 0.0))
        conn.commit()
        balance = 0.0
    conn.close()

    return jsonify({
        "address": address,
        "balance": balance,
        "value_in_toman": balance * AFIX_PRICE_TOMAN
    })

@app.route('/api/mine/challenge', methods=['GET'])
def get_mining_challenge():
    return jsonify({
        "target_prefix": "0" * MINING_DIFFICULTY,
        "timestamp": time.time(),
        "reward": MINING_REWARD
    })

@app.route('/api/mine/submit', methods=['POST'])
def submit_mining_solution():
    data = request.json or {}
    address = data.get('address')
    nonce = data.get('nonce')
    challenge_timestamp = data.get('timestamp')

    if not address or nonce is None:
        return jsonify({"error": "اطلاعات ناقص است"}), 400

    # بررسی اثبات کار (PoW)
    block_string = f"{address}-{nonce}-{challenge_timestamp}".encode()
    block_hash = hashlib.sha256(block_string).hexdigest()

    target_prefix = "0" * MINING_DIFFICULTY
    if not block_hash.startswith(target_prefix):
        return jsonify({"error": "اثبات کار نامعتبر است!"}), 400

    current_time = time.time()
    one_day_seconds = 24 * 60 * 60  # ۲۴ ساعت به ثانیه

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT balance, daily_earned, last_mine_timestamp FROM wallets WHERE address = ?", (address,))
    row = cursor.fetchone()

    if not row:
        # ولت جدید
        cursor.execute("INSERT INTO wallets (balance, address, daily_earned, last_mine_timestamp) VALUES (?, ?, ?, ?)", 
                       (MINING_REWARD, address, MINING_REWARD, current_time))
        conn.commit()
        conn.close()
        return jsonify({
            "status": "success",
            "message": "معما حل شد و پاداش واریز گردید",
            "balance": MINING_REWARD
        })

    balance, daily_earned, last_mine_timestamp = row

    # بررسی اینکه آیا ۲۴ ساعت از اولین استخراجِ دوره گذشته است یا خیر
    if current_time - last_mine_timestamp >= one_day_seconds:
        # ۲۴ ساعت گذشته؛ چرخه ریست می‌شود
        daily_earned = 0.0
        last_mine_timestamp = current_time

    # بررسی سقف روزانه ۵ واحدی
    if daily_earned >= MAX_DAILY_EARN:
        remaining_time = int(one_day_seconds - (current_time - last_mine_timestamp))
        hours = remaining_time // 3600
        minutes = (remaining_time % 3600) // 60
        conn.close()
        return jsonify({
            "error": f"سقف استخراج روزانه تکمیل شده است. لطفاً {hours} ساعت و {minutes} دقیقه دیگر مجدداً تلاش کنید."
        }), 400

    # اعمال پاداش
    new_balance = balance + MINING_REWARD
    new_daily_earned = daily_earned + MINING_REWARD

    cursor.execute("UPDATE wallets SET balance = ?, daily_earned = ?, last_mine_timestamp = ? WHERE address = ?", 
                   (new_balance, new_daily_earned, last_mine_timestamp, address))
    conn.commit()
    conn.close()

    return jsonify({
        "status": "success",
        "message": "معما حل شد و پاداش استخراج واریز گردید",
        "balance": new_balance,
        "daily_earned": new_daily_earned
    })

# --- بازار P2P ---
@app.route('/api/p2p/create_order', methods=['POST'])
def create_p2p_order():
    data = request.json or {}
    seller_address = data.get('address')
    try:
        amount_afix = float(data.get('amount_afix', 0))
    except ValueError:
        return jsonify({"error": "مقدار نامعتبر است"}), 400

    if amount_afix <= 0 or not seller_address:
        return jsonify({"error": "اطلاعات ناقص است"}), 400

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM wallets WHERE address = ?", (seller_address,))
    row = cursor.fetchone()
    if not row or row[0] < amount_afix:
        conn.close()
        return jsonify({"error": "موجودی کافی نیست"}), 400

    cursor.execute("UPDATE wallets SET balance = balance - ? WHERE address = ?", (amount_afix, seller_address))
    cursor.execute("INSERT INTO p2p_orders (seller_address, amount_afix, price_toman, status) VALUES (?, ?, ?, ?)",
                   (seller_address, amount_afix, amount_afix * AFIX_PRICE_TOMAN, "active"))
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "message": "سفارش فروش ثبت شد"})

@app.route('/api/p2p/orders', methods=['GET'])
def get_p2p_orders():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT order_id, seller_address, amount_afix, price_toman FROM p2p_orders WHERE status = 'active'")
    rows = cursor.fetchall()
    conn.close()
    return jsonify({"orders": [{"order_id": r[0], "seller": r[1], "amount_afix": r[2], "price_toman": r[3]} for r in rows]})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
