"""
AFIX Network - Standalone Mobile Miner Script
Created by Ariobarzan
"""

from afix_core import AfixMainnet, Wallet


def start_mining():
    print("==========================================")
    print("   AFIX Mobile Miner Node - Active        ")
    print("==========================================")

    # اتصال به شبکه اصلی
    network = AfixMainnet()

    user_name = input("Enter your miner wallet label: ")
    user_wallet = Wallet(user_name)

    print(f"\n[+] Wallet Created Successfully!")
    print(f"[+] Your Address: {user_wallet.address}")
    print("[+] Starting Proof of Work mining process...\n")

    # استخراج ۱ بلاک نمونه
    block, reward = network.mine_block(user_wallet.address)

    print("------------------------------------------")
    print(f"SUCCESS: Block #{block.index} Mined!")
    print(f"Block Hash: {block.hash}")
    print(f"Reward Received: {reward} AFIX")
    print("------------------------------------------")


if __name__ == "__main__":
    start_mining()
  
