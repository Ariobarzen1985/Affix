import hashlib
import json
from time import time


class Wallet:
    """ساختار کیف‌پول اختصاصی شبکه AFIX"""

    def __init__(self, owner_name):
        self.owner = owner_name
        self.address = "AFIX_" + hashlib.sha256(
            f"{owner_name}_{time()}".encode()
        ).hexdigest()[:30]
        self.balance = 0


class Block:
    """بلاک‌های غیرقابل تغییر با قفل SHA-256"""

    def __init__(self, index, transactions, previous_hash, nonce=0):
        self.index = index
        self.timestamp = time()
        self.transactions = transactions
        self.previous_hash = previous_hash
        self.nonce = nonce
        self.hash = self.compute_hash()

    def compute_hash(self):
        block_string = json.dumps(
            {
                "network": "AFIX_MAINNET",
                "creator": "Ariobarzan",
                "index": self.index,
                "timestamp": self.timestamp,
                "transactions": self.transactions,
                "previous_hash": self.previous_hash,
                "nonce": self.nonce,
            },
            sort_keys=True,
        )
        return hashlib.sha256(block_string.encode()).hexdigest()


class AfixMainnet:
    """هسته خودگردان، ایمن و نهایی شبکه AFIX"""

    def __init__(self):
        self.chain = []
        self.pending_transactions = []

        # قوانین ثابت و دست‌نخوردنی شبکه
        self.MAX_SUPPLY = 21000000  # سقف ۲۱ میلیون
        self.difficulty = 3  # سختی پایه استخراج موبایل
        self.initial_reward = 5000  # پاداش اولیه
        self.halving_interval = 210000  # بازه زمانی هاوینگ

        # ۱. کیف‌پول شخصی آریوبرزن (۱,۱۰۰,۰۰۰ AFIX)
        self.ariobarzan_wallet = Wallet("Ariobarzan_Creator")
        self.ariobarzan_wallet.balance = 1100000

        # ۲. صندوق قفل‌شده پشتیبان بازار (۱۰,۰۰۰,۰۰۰ AFIX)
        self.market_vault_address = "AFIX_LOCKED_VAULT_MARKET_RESERVE_10M"

        # ثبت توکن‌های اولیه
        self.total_minted = 1100000 + 10000000
        self.create_genesis_block()

    def create_genesis_block(self):
        genesis_transactions = [
            {
                "sender": "AFIX_SYSTEM",
                "recipient": self.ariobarzan_wallet.address,
                "amount": 1100000,
                "note": "Ariobarzan Personal Creator Funds",
            },
            {
                "sender": "AFIX_SYSTEM",
                "recipient": self.market_vault_address,
                "amount": 10000000,
                "note": "PERMANENTLY LOCKED: 10M Market Reserve Vault",
            },
        ]
        genesis_block = Block(0, genesis_transactions, "0")
        self.chain.append(genesis_block)

    def calculate_current_reward(self):
        halvings = len(self.chain) // self.halving_interval
        reward = self.initial_reward / (2**halvings)
        return max(reward, 0.0001)

    def adjust_difficulty_dynamically(self):
        if len(self.chain) % 100 == 0 and len(self.chain) > 0:
            latest_block = self.chain[-1]
            old_block = self.chain[-100]
            time_difference = latest_block.timestamp - old_block.timestamp

            if time_difference < 1800:
                self.difficulty += 1
            elif time_difference > 7200 and self.difficulty > 3:
                self.difficulty -= 1

    def add_transaction(self, sender, recipient, amount):
        if sender == self.market_vault_address:
            print("❌ خطای امنیتی: صندوق ۱۰ میلیونی پشتیبان بازار قفل است.")
            return False

        if amount <= 0:
            return False

        transaction = {
            "sender": sender,
            "recipient": recipient,
            "amount": amount,
            "fee": 0.0001,
            "timestamp": time(),
        }
        self.pending_transactions.append(transaction)
        return True

    def mine_block(self, miner_address):
        # محاسبه پاداش دقیق این بلاک قبل از ثبت
        if self.total_minted >= self.MAX_SUPPLY:
            reward = 0
        else:
            reward = self.calculate_current_reward()
            if self.total_minted + reward > self.MAX_SUPPLY:
                reward = self.MAX_SUPPLY - self.total_minted

        block_transactions = list(self.pending_transactions)

        if reward > 0:
            reward_tx = {
                "sender": "AFIX_NETWORK_REWARD",
                "recipient": miner_address,
                "amount": reward,
                "fee": 0,
                "timestamp": time(),
            }
            block_transactions.append(reward_tx)

        new_block = Block(
            index=len(self.chain),
            transactions=block_transactions,
            previous_hash=self.chain[-1].hash,
        )

        target = "0" * self.difficulty
        while not new_block.compute_hash().startswith(target):
            new_block.nonce += 1

        new_block.hash = new_block.compute_hash()
        self.chain.append(new_block)

        self.total_minted += reward
        self.pending_transactions = []

        self.adjust_difficulty_dynamically()
        return new_block, reward


# --- اجرای تست عملیاتی ---
if __name__ == "__main__":
    network = AfixMainnet()

    print("==================================================")
    print("       AFIX Network Mainnet Core Node            ")
    print("       Creator: Ariobarzan                       ")
    print("==================================================")
    print(f"آدرس آریوبرزن: {network.ariobarzan_wallet.address}")
    print(f"موجودی آریوبرزن: {network.ariobarzan_wallet.balance:,} AFIX")
    print(f"ذخیره قفل‌شده بازار: ۱۰,۰۰۰,۰۰۰ AFIX")
    print(f"تولید اولیه: {network.total_minted:,} / ۲۱,۰۰۰,۰۰۰ AFIX")
    print("--------------------------------------------------")

    # تست استخراج بلاک
    miner = Wallet("Mobile_User_1")
    block, reward_given = network.mine_block(miner.address)

    print(f"✅ بلاک شماره {block.index} با موفقیت استخراج شد!")
    print(f"هش بلاک: {block.hash}")
    print(f"پاداش واریز شده به ماینر: {reward_given} AFIX")
