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
AFIX_PRICE_TOMAN = 300000

# خواندن امن آدرس ادمین از متغیرهای محیطی هاست (چیزی روی گیت‌هاب لو نمی‌رود)
GENESIS_ADDRESS = os.environ.get("GENESIS_ADDRESS", "AFIX_GMN_default")
GENESIS_INITIAL_BALANCE = 1100000.0

MAX_SUPPLY = 21000000.0
MINING_REWARD = 0.5
MAX_DAILY_EARN = 5.0
TRANSFER_FEE = 0.01

def calculate_dynamic_difficulty(total_circulating):
    base_difficulty = 4
    milestone_step = 1000000.0
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
            CREATE TABLE IF NOT EXISTS transactions (
                tx_id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender TEXT,
                recipient TEXT,
                amount REAL,
                fee REAL,
                timestamp REAL
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
    
    return jsonify({
        "node": "AFIX Mainnet Node",
        "status": "Online",
        "version": "5.1-SecureAdmin",
        "total_circulating_supply": total_supply
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

@app.route('/api/transfer', methods=['POST'])
def transfer_funds():
    data = request.json or {}
    sender = data.get('sender')
    recipient = data.get('recipient')
    try:
        amount = float(data.get('amount', 0))
    except ValueError:
        return jsonify({"error": "مقدار ارز نامعتبر است"}), 400

    if not sender or not recipient or amount <= 0:
        return jsonify({"error": "اطلاعات تراکنش ناقص است"}), 400

    if sender == recipient:
        return jsonify({"error": "نمی‌توانید به آدرس خودتان انتقال دهید"}), 400

    total_deduction = amount + TRANSFER_FEE

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("SELECT balance FROM wallets WHERE address = ?", (sender,))
    sender_row = cursor.fetchone()
    if not sender_row or sender_row[0] < total_deduction:
        conn.close()
        return jsonify({"error": f"موجودی کافی نیست. (به همراه {TRANSFER_FEE} واحد کارمزد شبکه)"}), 400

    cursor.execute("SELECT balance FROM wallets WHERE address = ?", (recipient,))
    recipient_row = cursor.fetchone()
    if not recipient_row:
        cursor.execute("INSERT INTO wallets (balance, address, daily_earned, last_mine_timestamp) VALUES (?, ?, ?, ?)", 
                       (0.0, recipient, 0.0, 0.0))

    cursor.execute("UPDATE wallets SET balance = balance - ? WHERE address = ?", (total_deduction, sender))
    cursor.execute("UPDATE wallets SET balance = balance + ? WHERE address = ?", (amount, recipient))
    
    cursor.execute("INSERT INTO transactions (sender, recipient, amount, fee, timestamp) VALUES (?, ?, ?, ?, ?)",
                   (sender, recipient, amount, TRANSFER_FEE, time.time()))
    
    conn.commit()
    conn.close()

    return jsonify({
        "status": "success",
        "message": "تراکنش با موفقیت انجام شد.",
        "fee_deducted": TRANSFER_FEE
    })

@app.route('/api/mine/challenge', methods=['GET'])
def get_mining_challenge():
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

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT SUM(balance) FROM wallets")
    total_supply = cursor.fetchone()[0] or 0.0

    dynamic_difficulty = calculate_dynamic_difficulty(total_supply)
    target_prefix = "0" * dynamic_difficulty

    if total_supply >= MAX_SUPPLY:
        conn.close()
        return jsonify({"error": "سقف کل عرضه توکن‌های AFIX کامل شده است!"}), 400

    block_string = f"{address}-{nonce}-{challenge_timestamp}".encode()
    block_hash = hashlib.sha256(block_string).hexdigest()

    if not block_hash.startswith(target_prefix):
        conn.close()
        return jsonify({"error": "اثبات کار نامعتبر است!"}), 400

    current_time = time.time()
    one_day_seconds = 24 * 60 * 60

    cursor.execute("SELECT balance, daily_earned, last_mine_timestamp FROM wallets WHERE address = ?", (address,))
    row = cursor.fetchone()

    if not row:
        cursor.execute("INSERT INTO wallets (balance, address, daily_earned, last_mine_timestamp) VALUES (?, ?, ?, ?)", 
                       (MINING_REWARD, address, MINING_REWARD, current_time))
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": "پاداش واریز شد", "balance": MINING_REWARD})

    balance, daily_earned, last_mine_timestamp = row

    if current_time - last_mine_timestamp >= one_day_seconds:
        daily_earned = 0.0
        last_mine_timestamp = current_time

    if daily_earned >= MAX_DAILY_EARN:
        conn.close()
        return jsonify({"error": "سقف استخراج روزانه تکمیل شده است."}), 400

    new_balance = balance + MINING_REWARD
    new_daily_earned = daily_earned + MINING_REWARD

    cursor.execute("UPDATE wallets SET balance = ?, daily_earned = ?, last_mine_timestamp = ? WHERE address = ?", 
                   (new_balance, new_daily_earned, last_mine_timestamp, address))
    conn.commit()
    conn.close()

    return jsonify({"status": "success", "message": "پاداش استخراج واریز شد", "balance": new_balance})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
