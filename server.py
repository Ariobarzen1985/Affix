import os
import hashlib
import time
import hmac
import sqlite3
from functools import wraps
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

DB_FILE = "afix_blockchain.db"

# --- تنظیمات امنیتی ---
BOT_API_KEY = os.environ.get("BOT_API_KEY")
ADMIN_ADDRESS = os.environ.get("GENESIS_ADDRESS", "AFIX_GMN_default")

GENESIS_ADDRESS = ADMIN_ADDRESS
GENESIS_INITIAL_BALANCE = 1100000.0
MAX_SUPPLY = 21000000.0
MINING_REWARD = 0.5
MAX_DAILY_EARN = 5.0
TRANSFER_FEE = 0.01
TRADE_FEE_PERCENT = 0.002  # 0.2% کارمزد معامله برای هر طرف - می‌تونی صفر بذاری

DECIMALS = 6
FALLBACK_PRICE_TOMAN = 300000  # فقط وقتی هنوز هیچ معامله‌ای ثبت نشده، برای نمایش اولیه استفاده می‌شه


def round_amount(x):
    return round(float(x), DECIMALS)


def require_api_key(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not BOT_API_KEY:
            return jsonify({"error": "سرور به‌درستی پیکربندی نشده (BOT_API_KEY تنظیم نشده)."}), 500
        provided = request.headers.get("X-API-KEY", "")
        if not hmac.compare_digest(provided, BOT_API_KEY):
            return jsonify({"error": "دسترسی غیرمجاز. کلید API نامعتبر است."}), 401
        return f(*args, **kwargs)
    return wrapper


def require_admin(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        data = request.json or {}
        if data.get("admin_address") != ADMIN_ADDRESS:
            return jsonify({"error": "این عملیات فقط برای ادمین مجاز است."}), 403
        return f(*args, **kwargs)
    return wrapper


def get_db():
    conn = sqlite3.connect(DB_FILE, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS wallets (
            address TEXT PRIMARY KEY,
            balance REAL NOT NULL,          -- موجودی AFIX
            toman_balance REAL DEFAULT 0.0, -- موجودی تومانی داخلی (شارژ دستی توسط ادمین)
            daily_earned REAL DEFAULT 0.0,
            last_mine_timestamp REAL DEFAULT 0.0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            tx_id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender TEXT, recipient TEXT, amount REAL, fee REAL, timestamp REAL
        )
    ''')

    # --- مهاجرت (migration): اگر جدول wallets از نسخه‌ی قبلی از قبل وجود دارد و ستون
    # toman_balance را ندارد، اضافه‌اش می‌کنیم. این کار جلوی کرش سرور روی دیتابیس قدیمی را می‌گیرد
    # و موجودی AFIX فعلی همه (از جمله آدرس ادمین) دست‌نخورده باقی می‌ماند.
    cursor.execute("PRAGMA table_info(wallets)")
    existing_columns = [row[1] for row in cursor.fetchall()]
    if "toman_balance" not in existing_columns:
        cursor.execute("ALTER TABLE wallets ADD COLUMN toman_balance REAL DEFAULT 0.0")

    # سفارش‌های باز خرید/فروش
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            address TEXT NOT NULL,
            side TEXT NOT NULL,               -- 'buy' یا 'sell'
            price REAL NOT NULL,              -- قیمت هر واحد AFIX به تومان
            amount REAL NOT NULL,             -- مقدار کل سفارش (AFIX)
            remaining REAL NOT NULL,          -- مقدار باقیمانده هنوز تطبیق‌نشده
            status TEXT NOT NULL DEFAULT 'open',  -- open / filled / cancelled
            created_at REAL NOT NULL
        )
    ''')
    # تاریخچه معاملات انجام‌شده (منبع قیمت واقعی بازار)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
            buy_order_id INTEGER,
            sell_order_id INTEGER,
            buyer TEXT, seller TEXT,
            price REAL, amount REAL,
            timestamp REAL
        )
    ''')
    cursor.execute("SELECT balance FROM wallets WHERE address = ?", (GENESIS_ADDRESS,))
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO wallets (balance, address, toman_balance, daily_earned, last_mine_timestamp) VALUES (?, ?, ?, ?, ?)",
            (GENESIS_INITIAL_BALANCE, GENESIS_ADDRESS, 0.0, 0.0, 0.0)
        )
    conn.commit()
    conn.close()


init_db()


def ensure_wallet(cursor, address):
    cursor.execute("SELECT address FROM wallets WHERE address = ?", (address,))
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO wallets (balance, address, toman_balance, daily_earned, last_mine_timestamp) VALUES (?, ?, ?, ?, ?)",
            (0.0, address, 0.0, 0.0, 0.0)
        )


def calculate_dynamic_difficulty(total_circulating):
    base_difficulty = 4
    milestone_step = 1000000.0
    return base_difficulty + int(total_circulating // milestone_step)


@app.route('/', methods=['GET'])
def home():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT SUM(balance) FROM wallets")
    total_supply = cursor.fetchone()[0] or 0.0
    conn.close()
    return jsonify({"node": "AFIX Mainnet Node", "status": "Online", "version": "7.0-Market",
                     "total_circulating_supply": total_supply})


@app.route('/api/balance', methods=['GET'])
def get_balance():
    address = request.args.get('address')
    if not address:
        return jsonify({"error": "Address required"}), 400
    conn = get_db()
    cursor = conn.cursor()
    ensure_wallet(cursor, address)
    conn.commit()
    cursor.execute("SELECT balance, toman_balance FROM wallets WHERE address = ?", (address,))
    balance, toman_balance = cursor.fetchone()
    conn.close()
    current_price = get_current_price()
    return jsonify({
        "address": address,
        "balance": balance,
        "toman_balance": toman_balance,
        "value_in_toman": balance * current_price,
        "current_price_toman": current_price
    })


@app.route('/api/transfer', methods=['POST'])
@require_api_key
def transfer_funds():
    data = request.json or {}
    sender = data.get('sender')
    recipient = data.get('recipient')
    try:
        amount = round_amount(data.get('amount', 0))
    except (ValueError, TypeError):
        return jsonify({"error": "مقدار ارز نامعتبر است"}), 400
    if not sender or not recipient or amount <= 0:
        return jsonify({"error": "اطلاعات تراکنش ناقص است"}), 400
    if sender == recipient:
        return jsonify({"error": "نمی‌توانید به آدرس خودتان انتقال دهید"}), 400

    total_deduction = round_amount(amount + TRANSFER_FEE)
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN IMMEDIATE")
        ensure_wallet(cursor, sender)
        ensure_wallet(cursor, recipient)
        cursor.execute("SELECT balance FROM wallets WHERE address = ?", (sender,))
        sender_balance = cursor.fetchone()[0]
        if sender_balance < total_deduction:
            conn.rollback(); conn.close()
            return jsonify({"error": f"موجودی کافی نیست. (به همراه {TRANSFER_FEE} واحد کارمزد شبکه)"}), 400
        cursor.execute("UPDATE wallets SET balance = balance - ? WHERE address = ?", (total_deduction, sender))
        cursor.execute("UPDATE wallets SET balance = balance + ? WHERE address = ?", (amount, recipient))
        cursor.execute(
            "INSERT INTO transactions (sender, recipient, amount, fee, timestamp) VALUES (?, ?, ?, ?, ?)",
            (sender, recipient, amount, TRANSFER_FEE, time.time())
        )
        conn.commit()
    except Exception as e:
        conn.rollback(); conn.close()
        return jsonify({"error": f"خطای داخلی سرور: {e}"}), 500
    conn.close()
    return jsonify({"status": "success", "message": "تراکنش با موفقیت انجام شد.", "fee_deducted": TRANSFER_FEE})


@app.route('/api/mine/challenge', methods=['GET'])
def get_mining_challenge():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT SUM(balance) FROM wallets")
    total_supply = cursor.fetchone()[0] or 0.0
    conn.close()
    dynamic_difficulty = calculate_dynamic_difficulty(total_supply)
    return jsonify({"target_prefix": "0" * dynamic_difficulty, "difficulty_level": dynamic_difficulty,
                     "timestamp": time.time(), "reward": MINING_REWARD})


@app.route('/api/mine/submit', methods=['POST'])
@require_api_key
def submit_mining_solution():
    data = request.json or {}
    address = data.get('address')
    nonce = data.get('nonce')
    challenge_timestamp = data.get('timestamp')
    if not address or nonce is None or challenge_timestamp is None:
        return jsonify({"error": "اطلاعات ناقص است"}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT SUM(balance) FROM wallets")
    total_supply = cursor.fetchone()[0] or 0.0
    dynamic_difficulty = calculate_dynamic_difficulty(total_supply)
    target_prefix = "0" * dynamic_difficulty

    if total_supply >= MAX_SUPPLY:
        conn.close()
        return jsonify({"error": "سقف کل عرضه توکن‌های AFIX کامل شده است!"}), 400
    if time.time() - float(challenge_timestamp) > 300:
        conn.close()
        return jsonify({"error": "این چالش استخراج منقضی شده. دوباره تلاش کنید."}), 400

    block_hash = hashlib.sha256(f"{address}-{nonce}-{challenge_timestamp}".encode()).hexdigest()
    if not block_hash.startswith(target_prefix):
        conn.close()
        return jsonify({"error": "اثبات کار نامعتبر است!"}), 400

    current_time = time.time()
    one_day_seconds = 24 * 60 * 60
    try:
        cursor.execute("BEGIN IMMEDIATE")
        ensure_wallet(cursor, address)
        cursor.execute("SELECT balance, daily_earned, last_mine_timestamp FROM wallets WHERE address = ?", (address,))
        balance, daily_earned, last_mine_timestamp = cursor.fetchone()

        if current_time - last_mine_timestamp >= one_day_seconds:
            daily_earned = 0.0
        if daily_earned >= MAX_DAILY_EARN:
            conn.rollback(); conn.close()
            return jsonify({"error": "سقف استخراج روزانه تکمیل شده است."}), 400

        new_balance = round_amount(balance + MINING_REWARD)
        new_daily_earned = round_amount(daily_earned + MINING_REWARD)
        cursor.execute(
            "UPDATE wallets SET balance = ?, daily_earned = ?, last_mine_timestamp = ? WHERE address = ?",
            (new_balance, new_daily_earned, current_time, address)
        )
        conn.commit()
    except Exception as e:
        conn.rollback(); conn.close()
        return jsonify({"error": f"خطای داخلی سرور: {e}"}), 500
    conn.close()
    return jsonify({"status": "success", "message": "پاداش استخراج واریز شد", "balance": new_balance})


# ==================== بازار: شارژ موجودی تومانی (فقط ادمین، بعد از تایید دستی واریز کارت‌به‌کارت) ====================
@app.route('/api/wallet/toman/credit', methods=['POST'])
@require_api_key
@require_admin
def credit_toman():
    data = request.json or {}
    address = data.get('address')
    try:
        amount = round_amount(data.get('amount', 0))
    except (ValueError, TypeError):
        return jsonify({"error": "مقدار نامعتبر است"}), 400
    if not address or amount <= 0:
        return jsonify({"error": "اطلاعات ناقص است"}), 400
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("BEGIN IMMEDIATE")
    ensure_wallet(cursor, address)
    cursor.execute("UPDATE wallets SET toman_balance = toman_balance + ? WHERE address = ?", (amount, address))
    conn.commit()
    cursor.execute("SELECT toman_balance FROM wallets WHERE address = ?", (address,))
    new_balance = cursor.fetchone()[0]
    conn.close()
    return jsonify({"status": "success", "toman_balance": new_balance})


def get_current_price():
    """آخرین قیمت معامله‌شده؛ اگر معامله‌ای نبوده، میانگین بهترین سفارش خرید/فروش باز؛ در نبود هر دو، قیمت پیش‌فرض."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT price FROM trades ORDER BY trade_id DESC LIMIT 1")
    row = cursor.fetchone()
    if row:
        conn.close()
        return row[0]
    cursor.execute("SELECT MAX(price) FROM orders WHERE side='buy' AND status='open'")
    best_bid = cursor.fetchone()[0]
    cursor.execute("SELECT MIN(price) FROM orders WHERE side='sell' AND status='open'")
    best_ask = cursor.fetchone()[0]
    conn.close()
    if best_bid and best_ask:
        return (best_bid + best_ask) / 2
    return best_bid or best_ask or FALLBACK_PRICE_TOMAN


@app.route('/api/market/price', methods=['GET'])
def market_price():
    return jsonify({"price_toman": get_current_price()})


@app.route('/api/market/orderbook', methods=['GET'])
def orderbook():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT price, remaining FROM orders WHERE side='buy' AND status='open' ORDER BY price DESC, created_at ASC LIMIT 20"
    )
    bids = [{"price": r[0], "amount": r[1]} for r in cursor.fetchall()]
    cursor.execute(
        "SELECT price, remaining FROM orders WHERE side='sell' AND status='open' ORDER BY price ASC, created_at ASC LIMIT 20"
    )
    asks = [{"price": r[0], "amount": r[1]} for r in cursor.fetchall()]
    conn.close()
    return jsonify({"bids": bids, "asks": asks, "current_price": get_current_price()})


@app.route('/api/market/my_orders', methods=['GET'])
def my_orders():
    address = request.args.get('address')
    if not address:
        return jsonify({"error": "Address required"}), 400
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT order_id, side, price, amount, remaining, status, created_at FROM orders "
        "WHERE address = ? ORDER BY created_at DESC LIMIT 50", (address,)
    )
    rows = cursor.fetchall()
    conn.close()
    orders_list = [{
        "order_id": r[0], "side": r[1], "price": r[2], "amount": r[3],
        "remaining": r[4], "status": r[5], "created_at": r[6]
    } for r in rows]
    return jsonify({"orders": orders_list})


def _match_order(cursor, new_order_id, address, side, price, remaining):
    """تطبیق یک سفارش تازه با سفارش‌های مخالف موجود در دفتر سفارش. فرض: قبلاً موجودی/تومان لاک شده."""
    trades_done = []
    opposite_side = 'sell' if side == 'buy' else 'buy'
    order_by = "ASC" if side == 'buy' else "DESC"  # خریدار با ارزون‌ترین فروشنده match می‌شه و برعکس

    while remaining > 0:
        cursor.execute(
            f"SELECT order_id, address, price, remaining FROM orders "
            f"WHERE side=? AND status='open' AND order_id != ? "
            f"ORDER BY price {order_by}, created_at ASC LIMIT 1",
            (opposite_side, new_order_id)
        )
        match = cursor.fetchone()
        if not match:
            break
        match_id, match_address, match_price, match_remaining = match

        price_ok = (price >= match_price) if side == 'buy' else (price <= match_price)
        if not price_ok:
            break

        trade_amount = min(remaining, match_remaining)
        trade_price = match_price  # قیمت سفارش قدیمی‌تر (maker) ملاک معامله است

        buyer = address if side == 'buy' else match_address
        seller = match_address if side == 'buy' else address

        toman_value = round_amount(trade_amount * trade_price)
        fee_buyer = round_amount(toman_value * TRADE_FEE_PERCENT)
        fee_seller = round_amount(trade_amount * TRADE_FEE_PERCENT)

        # تحویل AFIX به خریدار (منهای کارمزد ناچیز)
        cursor.execute("UPDATE wallets SET balance = balance + ? WHERE address = ?",
                        (round_amount(trade_amount - fee_seller), buyer))
        # تحویل تومان به فروشنده (منهای کارمزد)
        cursor.execute("UPDATE wallets SET toman_balance = toman_balance + ? WHERE address = ?",
                        (round_amount(toman_value - fee_buyer), seller))

        cursor.execute(
            "INSERT INTO trades (buy_order_id, sell_order_id, buyer, seller, price, amount, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (new_order_id if side == 'buy' else match_id,
             match_id if side == 'buy' else new_order_id,
             buyer, seller, trade_price, trade_amount, time.time())
        )

        new_match_remaining = round_amount(match_remaining - trade_amount)
        match_status = 'filled' if new_match_remaining <= 0 else 'open'
        cursor.execute("UPDATE orders SET remaining = ?, status = ? WHERE order_id = ?",
                        (new_match_remaining, match_status, match_id))

        remaining = round_amount(remaining - trade_amount)
        trades_done.append({"price": trade_price, "amount": trade_amount})

    return remaining, trades_done


@app.route('/api/market/order', methods=['POST'])
@require_api_key
def place_order():
    data = request.json or {}
    address = data.get('address')
    side = data.get('side')
    try:
        price = round_amount(data.get('price', 0))
        amount = round_amount(data.get('amount', 0))
    except (ValueError, TypeError):
        return jsonify({"error": "مقدار یا قیمت نامعتبر است"}), 400

    if not address or side not in ('buy', 'sell') or price <= 0 or amount <= 0:
        return jsonify({"error": "اطلاعات سفارش ناقص یا نامعتبر است"}), 400

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN IMMEDIATE")
        ensure_wallet(cursor, address)
        cursor.execute("SELECT balance, toman_balance FROM wallets WHERE address = ?", (address,))
        afix_balance, toman_balance = cursor.fetchone()

        if side == 'sell':
            if afix_balance < amount:
                conn.rollback(); conn.close()
                return jsonify({"error": "موجودی AFIX کافی نیست."}), 400
            # قفل کردن فوری موجودی فروشنده (کسر از حساب تا زمان تطبیق یا لغو)
            cursor.execute("UPDATE wallets SET balance = balance - ? WHERE address = ?", (amount, address))
        else:  # buy
            required_toman = round_amount(price * amount)
            if toman_balance < required_toman:
                conn.rollback(); conn.close()
                return jsonify({"error": "موجودی تومانی کافی نیست."}), 400
            cursor.execute("UPDATE wallets SET toman_balance = toman_balance - ? WHERE address = ?",
                            (required_toman, address))

        cursor.execute(
            "INSERT INTO orders (address, side, price, amount, remaining, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, 'open', ?)",
            (address, side, price, amount, amount, time.time())
        )
        new_order_id = cursor.lastrowid

        remaining_after, trades_done = _match_order(cursor, new_order_id, address, side, price, amount)

        # اگر سفارش خرید بخشی تطبیق نشد و مانده، مازاد تومان قفل‌شده (که بابت قیمت پیشنهادی محاسبه شده) نگه داشته می‌شود
        # تا وقتی سفارش باقی‌مانده match یا لغو شود.
        final_status = 'filled' if remaining_after <= 0 else 'open'
        cursor.execute("UPDATE orders SET remaining = ?, status = ? WHERE order_id = ?",
                        (remaining_after, final_status, new_order_id))

        conn.commit()
    except Exception as e:
        conn.rollback(); conn.close()
        return jsonify({"error": f"خطای داخلی سرور: {e}"}), 500
    conn.close()

    return jsonify({
        "status": "success", "order_id": new_order_id, "filled_trades": trades_done,
        "remaining": remaining_after, "order_status": final_status
    })


@app.route('/api/market/cancel_order', methods=['POST'])
@require_api_key
def cancel_order():
    data = request.json or {}
    address = data.get('address')
    order_id = data.get('order_id')
    if not address or order_id is None:
        return jsonify({"error": "اطلاعات ناقص است"}), 400

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN IMMEDIATE")
        cursor.execute("SELECT address, side, price, remaining, status FROM orders WHERE order_id = ?", (order_id,))
        row = cursor.fetchone()
        if not row:
            conn.rollback(); conn.close()
            return jsonify({"error": "سفارش یافت نشد."}), 404
        order_address, side, price, remaining, status = row
        if order_address != address:
            conn.rollback(); conn.close()
            return jsonify({"error": "این سفارش متعلق به شما نیست."}), 403
        if status != 'open':
            conn.rollback(); conn.close()
            return jsonify({"error": "این سفارش قابل لغو نیست (قبلاً بسته یا کامل شده)."}), 400

        # بازگرداندن مقدار قفل‌شده باقیمانده
        if side == 'sell':
            cursor.execute("UPDATE wallets SET balance = balance + ? WHERE address = ?", (remaining, address))
        else:
            refund_toman = round_amount(remaining * price)
            cursor.execute("UPDATE wallets SET toman_balance = toman_balance + ? WHERE address = ?",
                            (refund_toman, address))

        cursor.execute("UPDATE orders SET status = 'cancelled' WHERE order_id = ?", (order_id,))
        conn.commit()
    except Exception as e:
        conn.rollback(); conn.close()
        return jsonify({"error": f"خطای داخلی سرور: {e}"}), 500
    conn.close()
    return jsonify({"status": "success", "message": "سفارش لغو شد."})


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
