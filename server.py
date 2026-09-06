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

MAX_SUPPLY = 21000000.0  # کل سقف عرضه توکن
MINING_REWARD = 0.5
MAX_DAILY_EARN = 5.0  # سقف روزانه هر کاربر

def calculate_dynamic_difficulty(total_circulating):
    """
    محاسبه خودکار سختی شبکه بر اساس توکن‌های استخراج شده:
    به ازای هر ۱,۰۰۰,۰۰۰ واحد استخراج شده، سختی یک واحد اضافه می‌شود.
    پایه سختی از ۴ شروع می‌شود.
    """
    base_difficulty = 4
    milestone_step = 1000000.0  # هر یک میلیون واحد
    extra_difficulty = int(total_circulating // milestone_step)
    return base_difficulty + extra_difficulty

def init_db():
    if sqlite3:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
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
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT SUM(balance) FROM wallets")
    total_supply = cursor.fetchone()[0] or 0.0
    conn.close()
    
    current_diff = calculate_dynamic_difficulty(total_supply)
    
    return jsonify({
        "node": "AFIX Mainnet Node",
        "status": "Online",
        "version": "4.0-HalvingDifficulty",
        "total_circulating_supply": total_supply,
        "max_supply": MAX_SUPPLY,
        "current_mining_difficulty": current_diff
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
    """ارسال چالش با سختی کاملاً پویا بر اساس کل توکن‌های استخراج‌شده در شبکه"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT SUM(balance) FROM wallets")
    total_supply = cursor.fetchone()[0] or 0.0
    conn.close()

    dynamic_difficulty = calculate_dynamic_difficulty(total_supply)

    return jsonify({
        "target_prefix": "0" * dynamic_difficulty,
        "difficulty_level": dynamic_difficulty,
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

    # محاسبه مجدد سختی لحظه‌ای برای بررسی صحت اثبات کار کاربر
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT SUM(balance) FROM wallets")
    total_supply = cursor.fetchone()[0] or 0.0

    dynamic_difficulty = calculate_dynamic_difficulty(total_supply)
    target_prefix = "0" * dynamic_difficulty

    # بررسی سقف کل عرضه (بیت‌کوین استایل: بیش از ۲۱ میلیون قابل استخراج نیست)
    if total_supply >= MAX_SUPPLY:
        conn.close()
        return jsonify({"error": "سقف کل عرضه توکن‌های AFIX (۲۱ میلیون) کامل شده است. استخراج به پایان رسید!"}), 400

    # بررسی اثبات کار با سختیِ روز
    block_string = f"{address}-{nonce}-{challenge_timestamp}".encode()
    block_hash = hashlib.sha256(block_string).hexdigest()

    if not block_hash.startswith(target_prefix):
        conn.close()
        return jsonify({"error": f"اثبات کار نامعتبر است! سختی فعلی شبکه روی سطح {dynamic_difficulty} است."}), 400

    current_time = time.time()
    one_day_seconds = 24 * 60 * 60

    cursor.execute("SELECT balance, daily_earned, last_mine_timestamp FROM wallets WHERE address = ?", (address,))
    row = cursor.fetchone()

    if not row:
        cursor.execute("INSERT INTO wallets (balance, address, daily_earned, last_mine_timestamp) VALUES (?, ?, ?, ?)", 
                       (MINING_REWARD, address, MINING_REWARD, current_time))
        conn.commit()
        conn.close()
        return jsonify({
            "status": "success",
            "message": "معما حل شد و پاداش واریز گردید",
            "balance": MINING_REWARD,
            "network_difficulty": dynamic_difficulty
        })

    balance, daily_earned, last_mine_timestamp = row

    if current_time - last_mine_timestamp >= one_day_seconds:
        daily_earned = 0.0
        last_mine_timestamp = current_time

    if daily_earned >= MAX_DAILY_EARN:
        remaining_time = int(one_day_seconds - (current_time - last_mine_timestamp))
        hours = remaining_time // 3600
        minutes = (remaining_time % 3600) // 60
        conn.close()
        return jsonify({
            "error": f"سقف استخراج روزانه تکمیل شده است. لطفاً {hours} ساعت و {minutes} دقیقه دیگر تلاش کنید."
        }), 400

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
        "network_difficulty": dynamic_difficulty
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
