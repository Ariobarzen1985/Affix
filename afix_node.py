import os
from flask import Flask, jsonify, request
from afix_core import AfixMainnet, Wallet

app = Flask(__name__)

# راه‌اندازی شبکه AFIX با اتصال به هسته اصلی
CREATOR_GMAIL = "ariobarzan@gmail.com"
NETWORK_CREATOR_ADDRESS = "AFIX_ab773b6f7e43ac1e56bac9196b5b7f3950f2d"
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
    """مسیر استعلام موجودی واقعی هر آدرس از روی بلاک‌چین"""
    balance = blockchain.get_balance(address)
    return jsonify({
        "address": address,
        "balance": balance
    }), 200

@app.route('/transactions/new', methods=['POST'])
def new_transaction():
    values = request.get_json()
    if not values:
        return jsonify({"error": "داده‌ای ارسال نشده است"}), 400

    required = ['sender', 'recipient', 'amount']
    if not all(k in values for k in required):
        return jsonify({"error": "اطلاعات تراکنش ناقص است"}), 400

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
        return jsonify({"error": "تراکنش رد شد"}), 400

    return jsonify({"message": "تراکنش با موفقیت به صف انتظار اضافه شد"}), 201

@app.route('/mine', methods=['GET'])
def mine():
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
