import os
from flask import Flask, jsonify, request
from afix_core import AfixMainnet, Wallet

app = Flask(__name__)

# راه‌اندازی شبکه AFIX با اتصال مستقیم به آدرس و جیمیل اختصاصی شما
# (اینجا از آدرس ثابت شما یا ولت سیستمی برای نود استفاده می‌شود)
CREATOR_GMAIL = "ariobarzan@gmail.com"
# برای جلوگیری از تغییر ولت با هر بار ریستارت سرور، یک آدرس پایه تعریف می‌کنیم
NETWORK_CREATOR_ADDRESS = "AFIX_GMN_ariobarzan_main_node"
blockchain = AfixMainnet(creator_wallet_address=NETWORK_CREATOR_ADDRESS, creator_email=CREATOR_GMAIL)

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "status": "AFIX Mainnet Node is online",
        "creator": "Ariobarzan",
        "chain_height": len(blockchain.chain),
        "total_minted": blockchain.total_minted,
        "max_supply": blockchain.MAX_SUPPLY
    }), 200

@app.route('/chain', methods=['GET'])
def get_chain():
    """دریافت کل تاریخچه بلاک‌چین واقعی AFIX"""
    chain_data = []
    for block in blockchain.chain:
        block_data = {
            "index": block.index,
            "timestamp": block.timestamp,
            "transactions": block.transactions,
            "previous_hash": block.previous_hash,
            "nonce": block.nonce,
            "hash": block.hash
        }
        chain_data.append(block_data)
    
    return jsonify({
        "length": len(chain_data),
        "chain": chain_data,
        "difficulty": blockchain.difficulty
    }), 200

@app.route('/balance/<address>', methods=['GET'])
def check_balance(address):
    """بررسی موجودی واقعی هر آدرس از روی دفتر کل شبکه"""
    balance = blockchain.get_balance(address)
    return jsonify({
        "address": address,
        "balance": balance
    }), 200

@app.route('/transactions/new', methods=['POST'])
def new_transaction():
    """ثبت تراکنش جدید با رعایت قوانین امنیتی و ضدتقلب"""
    values = request.get_json()
    if not values:
        return jsonify({"error": "داده‌ای ارسال نشده است"}), 400

    required = ['sender', 'recipient', 'amount']
    if not all(k in values for k in required):
        return jsonify({"error": "اطلاعات تراکنش ناقص است"}), 400

    # دریافت امضا و کلید عمومی (اگر تراکنش غیرسیستمی باشد)
    signature = values.get('signature')
    public_key_hex = values.get('public_key_hex')

    success = blockchain.add_transaction(
        sender=values['sender'],
        recipient=values['recipient'],
        amount=values['amount'],
        signature=signature,
        public_key_hex=public_key_hex
    )

    if not success:
        return jsonify({"error": "تراکنش رد شد (خطای موجودی، صندوق قفل‌شده یا نامعتبر بودن امضا)"}), 400

    return jsonify({"message": "تراکنش با موفقیت به صف انتظار اضافه شد"}), 201

@app.route('/mine', methods=['GET'])
def mine():
    """استخراج بلاک جدید و واریز پاداش به ماینر"""
    # پاداش استخراج به آدرس پیش‌فرض سازنده نود واریز می‌شود
    miner_address = NETWORK_CREATOR_ADDRESS
    
    new_block, reward = blockchain.mine_block(miner_address)
    
    response = {
        "message": "بلاک جدید با موفقیت استخراج شد!",
        "index": new_block.index,
        "transactions": new_block.transactions,
        "nonce": new_block.nonce,
        "previous_hash": new_block.previous_hash,
        "hash": new_block.hash,
        "reward_given": reward,
        "total_minted": blockchain.total_minted
    }
    return jsonify(response), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
