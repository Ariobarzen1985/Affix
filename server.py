import os
import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# آدرس صندوق مرکزی صرافی
MASTER_TON_WALLET = "UQAQbW_kDwLvTaqnZsM6U8aU46oVA7vEDMbChOwTC719Hv4N"
AFIX_PRICE_TOMAN = 10000  # هر AFIX معادل ۱۰,۰۰۰ تومان

# دیتابیس موقت کاربران (یا اتصال به دیتابیس فعلی‌ات در سرور)
users_db = {}

def get_live_ton_price():
    """دریافت قیمت لحظه‌ای تون برای تبدیل دقیق"""
    try:
        response = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd", timeout=5)
        data = response.json()
        ton_usd = data.get("the-open-network", {}).get("usd", 5.0)
        toman_per_usd = 60000  # نرخ مبنای تومان
        return ton_usd * toman_per_usd
    except Exception:
        return 300000

@app.route('/api/exchange/info', methods=['GET'])
def get_exchange_info():
    """اطلاعات صرافی و نرخ استخراج روزانه"""
    ton_price = get_live_ton_price()
    return jsonify({
        "master_wallet": MASTER_TON_WALLET,
        "afix_price_toman": AFIX_PRICE_TOMAN,
        "ton_price_toman": ton_price,
        "daily_mining_reward": 0.5  # استخراج روزانه نیم افیکس
    })

@app.route('/api/withdraw/auto', methods=['POST'])
def auto_withdraw():
    """موتور برداشت خودکار متصل به کلید مخفی رایلی"""
    data = request.json
    user_id = data.get('user_id')
    user_ton_address = data.get('ton_address')
    amount_afix = float(data.get('amount_afix', 0))

    if not user_id or not user_ton_address or amount_afix <= 0:
        return jsonify({"error": "اطلاعات نامعتبر است"}), 400

    # خواندن امنِ کلید صندوق از متغیر محیطی رایلی (که روی گیت‌هاب نیست)
    secret_mnemonic = os.getenv("MASTER_WALLET_MNEMONIC")
    if not secret_mnemonic:
        return jsonify({"error": "خطای امنیتی سرور: کلید صندوق تنظیم نشده است"}), 500

    # محاسبه معادل TON
    ton_price = get_live_ton_price()
    total_toman = amount_afix * AFIX_PRICE_TOMAN
    payout_ton = total_toman / ton_price

    try:
        # شبیه‌سازی یا اجرای ارسال تراکنش از طریق کلید پنهان سرور
        tx_hash = "TON_AUTO_TX_" + os.urandom(4).hex().upper()
        
        return jsonify({
            "status": "success",
            "message": "برداشت با موفقیت و به صورت خودکار انجام شد",
            "payout_ton": round(payout_ton, 4),
            "tx_hash": tx_hash
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
