import hashlib
import json
import os
import time
from flask import Flask, jsonify, request

app = Flask(__name__)

blockchain = [{
    "index": 0,
    "timestamp": time.time(),
    "transactions": [],
    "nonce": 0,
    "previous_hash": "0" * 64,
    "hash": "8f3a2b1c9d4e5f6a7b8c9d0e1f2a3b"
}]

DIFFICULTY = 3

@app.route('/', methods=['GET'])
def home():
    return jsonify({"status": "AFIX Node is online", "height": len(blockchain)}), 200

@app.route('/chain', methods=['GET'])
def get_chain():
    return jsonify({
        "chain": blockchain,
        "length": len(blockchain),
        "difficulty": DIFFICULTY
    }), 200

@app.route('/mine', methods=['POST'])
def mine_block():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid data format"}), 400
    
    miner_address = data.get("miner_address")
    block_index = data.get("block_index")
    nonce = data.get("nonce")
    block_hash = data.get("hash")
    
    if not all([miner_address, block_index, nonce, block_hash]):
        return jsonify({"error": "Missing parameters"}), 400
        
    previous_block = blockchain[-1]
    
    if block_index != previous_block["index"] + 1:
        return jsonify({"error": "Invalid block index"}), 400
        
    data_string = f"AFIX_{block_index}_{previous_block['hash']}_{nonce}_{miner_address}"
    calculated_hash = hashlib.sha256(data_string.encode()).hexdigest()
    
    if calculated_hash.startswith("0" * DIFFICULTY) and calculated_hash == block_hash:
        new_block = {
            "index": block_index,
            "timestamp": time.time(),
            "transactions": [{"to": miner_address, "reward": 50}],
            "nonce": nonce,
            "previous_hash": previous_block['hash'],
            "hash": block_hash
        }
        blockchain.append(new_block)
        return jsonify({"message": "Block added successfully!", "block": new_block}), 200
    
    return jsonify({"error": "Invalid block hash or difficulty mismatch"}), 400

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

