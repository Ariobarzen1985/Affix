import os
import hashlib
import json
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

# درجه سختی شبکه (تعداد صفرهای ابتدای هش - برای تست روی 4 تنظیم شده تا معقول باشد)
MINING_DIFFICULTY = 4 
MINING_REWARD = 0.5

def init_db():
    if sqlite3:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS wallets (
                address TEXT PRIMARY KEY,
                balance REAL NOT NULL,
                last_mine_time TEXT
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
            cursor.execute("INSERT INTO wallets (balance, address) VALUES (?, ?)", (GENESIS_INITIAL_BALANCE, GENESIS_ADDRESS))
        conn.commit()
        conn.close()

init_db()

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "node": "AFIX Mainnet Node",
        "status": "Online",
        "consensus": "Proof of Work (PoW)",
        "difficulty": MINING_DIFFICULTY
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

    return jsonify({
        "address": address,
        "balance": balance,
        "value_in_toman": balance * AFIX_PRICE_TOMAN
    })

@app.route('/api/mine/challenge', methods=['GET'])
def get_mining_challenge():
    """ارسال چالش جدید (شامل آخرین هش و هدف سختی) برای ماینر"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(order_id) FROM p2p_orders") # به عنوان نمونه‌ای از داده پویا
    conn.close()
    
    challenge_data = {
        "target_prefix": "0" * MINING_DIFFICULTY,
        "timestamp": time.time(),
        "reward": MINING_REWARD
    }
    return jsonify(challenge_data)

@app.route('/api/mine/submit', methods=['POST'])
def submit_mining_solution():
    """بررسی اثبات کار (Proof of Work) فرستاده شده توسط ماینر"""
    data = request.json or {}
    address = data.get('address')
    nonce = data.get('nonce')
    challenge_timestamp = data.get('timestamp')

    if not address or nonce is None:
        return jsonify({"error": "اطلاعات ناقص است"}), 400

    # اعتبارسنجی هش تولید شده توسط ماینر
    block_string = f"{address}-{nonce}-{challenge_timestamp}".encode()
    block_hash = hashlib.sha256(block_string).hexdigest()

    target_prefix = "0" * MINING_DIFFICULTY
    if not block_hash.startswith(target_prefix):
        return jsonify({"error": "اثبات کار نامعتبر است! هش با سختی شبکه مطابقت ندارد."}), 400

    # اگر معما حل شده باشد، پاداش واریز می‌شود
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM wallets WHERE address = ?", (address,))
    row = cursor.fetchone()

    if not row:
        cursor.execute("INSERT INTO wallets (balance, address) VALUES (?, ?)", (MINING_REWARD, address))
        new_balance = MINING_REWARD
    else:
        new_balance = row[0] + MINING_REWARD
        cursor.execute("UPDATE wallets SET balance = ? WHERE address = ?", (new_balance, address))
    
    conn.commit()
    conn.close()

    return jsonify({
        "status": "success",
        "message": "بلاک با موفقیت استخراج شد و پاداش واریز گردید!",
        "hash": block_hash,
        "balance": new_balance
    })

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
