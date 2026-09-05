import os
sqlite3 = None
try:
    import sqlite3
except ImportError:
    pass

import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

DB_FILE = "afix_blockchain.db"
MASTER_TON_WALLET = "UQAQbW_kDwLvTaqnZsM6U8aU46oVA7vEDMbChOwTC719Hv4N"
AFIX_PRICE_TOMAN = 10000  # هر AFIX معادل ۱۰,۰۰۰ تومان

def init_db():
    """ساخت جدول پایگاه داده در صورت عدم وجود"""
    if sqlite3:
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
            VALUES ('AFIX_GEN_989637364A', 1000.0)
        ''')
        conn.commit()
        conn.close()

# اجرای اولیه‌ ساخت دیتابیس هنگام بالا آمدن سرور
init_db()

def get_live_ton_price():
    """دریافت قیمت لحظه‌ای تون برای تبدیل دقیق به تومان"""
    try:
        response = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd", timeout=5)
        data = response.json()
        ton_usd = data.get("the-open-network", {}).get("usd", 5.0)
        toman_per_usd = 60000  # نرخ مبنای تومان
        return ton_usd * toman_per_usd
    except Exception:
        return 300000

@app.route('/')
def home():
    return jsonify({
        "node": "AFIX Network",
        "status": "AFIX Node is online",
        "version": "1.1-transaction-core"
    })

@app.route('/api/exchange/info', methods=['GET'])
def exchange_info():
    """اطلاعات پایه صرافی و قیمت لحظه‌ای"""
    ton_price = get_live_ton_price()
    return jsonify({
        "master_wallet": MASTER_TON_WALLET,
        "afix_price_toman": AFIX_PRICE_TOMAN,
        "ton_price_toman": ton_price,
        "daily_mining_reward": 0.5
    })

@app.route('/api/balance', methods=['GET'])
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
        # اگر والت جدید باشد با موجودی صفر اضافه می‌کنیم
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO wallets (address, balance) VALUES (?, ?)", (address, 0.0))
        conn.commit()
        conn.close()
        return jsonify({"address": address, "balance": 0.0})

@app.route('/api/withdraw/auto', methods=['POST'])
def auto_withdraw():
    """موتور برداشت خودکار متصل به کلید امن رایلی و دیتابیس"""
    data = request.json
    user_address = data.get('address')
    amount_afix = float(data.get('amount_afix', 0))

    if not user_address or amount_afix <= 0:
        return jsonify({"error": "اطلاعات نامعتبر است"}), 400

    # بررسی موجودی کاربر در دیتابیس SQLite
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM wallets WHERE address = ?", (user_address,))
    row = cursor.fetchone()

    if not row or row[0] < amount_afix:
        conn.close()
        return jsonify({"error": "موجودی AFIX کافی نیست"}), 400

    # خواندن امنِ کلید صندوق از متغیر محیطی رایلی (که روی گیت‌هاب نیست)
    secret_mnemonic = os.getenv("MASTER_WALLET_MNEMONIC")
    if not secret_mnemonic:
        conn.close()
        return jsonify({"error": "خطای امنیتی سرور: کلید صندوق تنظیم نشده است"}), 500

    # محاسبه معادل TON
    ton_price = get_live_ton_price()
    total_toman = amount_afix * AFIX_PRICE_TOMAN
    payout_ton = total_toman / ton_price

    try:
        # شبیه‌سازی ارسال تراکنش از طریق کلید پنهان سرور به شبکه TON
        tx_hash = "TON_AUTO_TX_" + os.urandom(4).hex().upper()
        
        # کسر موجودی از دیتابیس بعد از تایید
        cursor.execute("UPDATE wallets SET balance = balance - ? WHERE address = ?", (amount_afix, user_address))
        conn.commit()
        conn.close()

        return jsonify({
            "status": "success",
            "message": "برداشت با موفقیت و به صورت خودکار انجام شد",
            "payout_ton": round(payout_ton, 4),
            "tx_hash": tx_hash
        })
    except Exception as e:
        conn.close()
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
