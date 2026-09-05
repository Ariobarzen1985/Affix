import hashlib
import json
from time import time


class Wallet:
    """ساختار کیف‌پول اختصاصی شبکه AFIX"""

    def __init__(self, owner_identifier):
        self.owner = owner_identifier
        # ساخت آدرس یکتا و غیرقابل حدس بر اساس شناسه و زمان
        unique_seed = f"{owner_identifier}_{time()}"
        self.address = "AFIX_" + hashlib.sha256(unique_seed.encode()).hexdigest()[:34]
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

    def __init__(self, creator_email="ariobarzan@gmail.com"):
        self.chain = []
        self.pending_transactions = []

        # قوانین ثابت و دست‌نخوردنی شبکه
        self.MAX_SUPPLY = 21000000  # سقف کل ۲۱ میلیون
        self.difficulty = 3  # سختی پایه استخراج
        self.initial_reward = 50  # پاداش اولیه تنظیم‌شده برای استخراج طی ۱۴۰ سال
        self.halving_interval = 210000  # هر ۲۱۰,۰۰۰ بلاک پاداش نصف می‌شود

        # ۱. کیف‌پول شخصی آریوبرزن با متصل کردن جیمیل
        self.creator_email = creator_email
        # تولید آدرس عمومی منحصربه‌فرد با هش کردن جیمیل آریوبرزن
        email_hash = hashlib.sha256(f"AFIX_GENESIS_{creator_email}".encode()).hexdigest()[:30]
        self.ariobarzan_wallet_address = f"AFIX_GMN_{email_hash}"

        # ۲. صندوق قفل‌شده پشتیبان بازار (۱۰,۰۰۰,۰۰۰ AFIX)
        self.market_vault_address = "AFIX_LOCKED_VAULT_MARKET_RESERVE_10M"

        # ثبت توکن‌های اولیه (۱.۱ میلیون آریوبرزن + ۱۰ میلیون صندوق)
        self.total_minted = 1100000 + 10000000
        self.create_genesis_block()

    def create_genesis_block(self):
        genesis_transactions = [
            {
                "sender": "AFIX_SYSTEM",
                "recipient": self.ariobarzan_wallet_address,
                "amount": 1100000,
                "note": f"Ariobarzan Personal Funds linked to Gmail: {self.creator_email}",
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

    def get_balance(self, address):
        """محاسبه دقیق موجودی واقعی یک آدرس از روی دفتر کل تراکنش‌ها"""
        balance = 0
        for block in self.chain:
            for tx in block.transactions:
                if tx["recipient"] == address:
                    balance += tx["amount"]
                if tx["sender"] == address:
                    balance -= tx["amount"]
        return balance

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
        # بررسی نفوذ ۱: صندوق ۱۰ میلیونی پشتیبان تحت هیچ شرایطی نباید خرج شود
        if sender == self.market_vault_address:
            print("❌ خطای امنیتی: صندوق ۱۰ میلیونی پشتیبان بازار قفل است.")
            return False

        if amount <= 0:
            print("❌ خطای امنیتی: مقدار تراکنش باید بیشتر از صفر باشد.")
            return False

        # بررسی نفوذ ۲: تایید موجودی فرستنده (جلوگیری از خرج کردن بیش از موجودی)
        sender_balance = self.get_balance(sender)
        if sender_balance < amount:
            print(f"❌ خطای امنیتی: موجودی کافی نیست. موجودی: {sender_balance} | درخواستی: {amount}")
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
        # محاسبه پاداش دقیق این بلاک قبل از ثبت و بررسی سقف عرضه
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
    # ثبت جیمیل شما برای اتصال به ۱.۱ میلیون توکن ژنزیس
    MY_GMAIL = "ariobarzan@gmail.com"
    network = AfixMainnet(creator_email=MY_GMAIL)

    print("==================================================")
    print("       AFIX Network Mainnet Core Node            ")
    print("       Creator: Ariobarzan                       ")
    print("==================================================")
    print(f"جیمیل ثبت‌شده مالک: {network.creator_email}")
    print(f"آدرس آریوبرزن (بر پایه جیمیل): {network.ariobarzan_wallet_address}")
    print(f"موجودی آریوبرزن: {network.get_balance(network.ariobarzan_wallet_address):,} AFIX")
    print(f"ذخیره قفل‌شده بازار: {network.get_balance(network.market_vault_address):,} AFIX")
    print(f"تولید اولیه: {network.total_minted:,} / {network.MAX_SUPPLY:,} AFIX")
    print("--------------------------------------------------")

    # تست استخراج بلاک
    miner = Wallet("Mobile_User_1")
    block, reward_given = network.mine_block(miner.address)

    print(f"✅ بلاک شماره {block.index} با موفقیت استخراج شد!")
    print(f"هش بلاک: {block.hash}")
    print(f"پاداش واریز شده به ماینر: {reward_given} AFIX")
