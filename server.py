import os
import sqlite3
from flask import Flask, jsonify, request

app = Flask(__name__)

# نام دیتابیس محلی برای ذخیره کیف پول‌ها و تراکنش‌ها
DB_FILE = "afix_blockchain.db"

def init_db():
    """ساخت جدول پایگاه داده در صورت عدم وجود"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS wallets (
            address TEXT PRIMARY KEY,
            balance REAL NOT NULL
        )
    ''')
    # ساخت یک ولت پیش‌فرض با مقداری موجودی اولیه برای تست
    cursor.execute('''
        INSERT OR IGNORE INTO wallets (address, balance) 
        VALUES ('AFIX_GMN_f89637364a', 1000.0)
    ''')
    conn.commit()
    conn.close()

# اجرای تابع ساخت دیتابیس هنگام بالا آمدن سرور
init_db()

@app.route('/')
def home():
    return jsonify({
        "node": "AFIX Network",
        "status": "AFIX Node is online",
        "version": "1.1-transaction-core"
    })

@app.route('/balance', methods=['GET'])
def get_balance():
    """گرفتن موجودی کیف پول با ارسال آدرس در پارامتر"""
    address = request.args.get('address')
    if not address:
        return jsonify({"error": "Address is required"}), 400
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM wallets WHERE address = ?", (address,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return jsonify({"address": address, "balance": row[0]})
    else:
        # اگر ولت وجود نداشت با موجودی صفر ثبتش می‌کنیم
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO wallets (address, balance) VALUES (?, ?)", (address, 0.0))
        conn.commit()
        conn.close()
        return jsonify({"address": address, "balance": 0.0})

@app.route('/transfer', methods=['POST'])
def transfer():
    """انتقال توکن بین دو کیف پول"""
    data = request.json
    sender = data.get('sender')
    receiver = data.get('receiver')
    amount = data.get('amount')
    
    if not sender or not receiver or amount is None or amount <= 0:
        return jsonify({"error": "Invalid transaction parameters"}), 400
        
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # بررسی موجودی فرستنده
    cursor.execute("SELECT balance FROM wallets WHERE address = ?", (sender,))
    sender_row = cursor.fetchone()
    
    if not sender_row or sender_row[0] < amount:
        conn.close()
        return jsonify({"error": "Insufficient balance or sender not found"}), 400
        
    # بررسی یا ایجاد گیرنده
    cursor.execute("SELECT balance FROM wallets WHERE address = ?", (receiver,))
    receiver_row = cursor.fetchone()
    if not receiver_row:
        cursor.execute("INSERT INTO wallets (address, balance) VALUES (?, ?)", (receiver, 0.0))
    
    # کسر از فرستنده و افزودن به گیرنده
    cursor.execute("UPDATE wallets SET balance = balance - ? WHERE address = ?", (amount, sender))
    cursor.execute("UPDATE wallets SET balance = balance + ? WHERE address = ?", (amount, receiver))
    
    conn.commit()
    conn.close()
    
    return jsonify({
        "status": "success",
        "message": f"Successfully transferred {amount} AFIX from {sender} to {receiver}"
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
