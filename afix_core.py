import hashlib
import json
from time import time
from ecdsa import SigningKey, SECP256k1, VerifyingKey


class Wallet:
    """کیف پول واقعی مبتنی بر کلید خصوصی و عمومی (دقیقاً مشابه ساختار بیت‌کوین)"""
    def __init__(self, existing_private_key_hex=None):
        if existing_private_key_hex:
            self.private_key = SigningKey.from_string(bytes.fromhex(existing_private_key_hex), curve=SECP256k1)
        else:
            self.private_key = SigningKey.generate(curve=SECP256k1)
        self.public_key = self.private_key.get_verifying_key()
        
    def get_address(self):
        """تولید آدرس اختصاصی شبکه از روی کلید عمومی (مشابه الگوریتم پابلیک کی به آدرس)"""
        pub_bytes = self.public_key.to_string()
        sha = hashlib.sha256(pub_bytes).digest()
        # استفاده از الگوریتم استاندارد هش برای ساخت آدرس با پیشوند اختصاصی AFIX
        return "AFIX_" + sha.hex()[:38]

    def get_private_key_hex(self):
        """دریافت کلید خصوصی (محرمانه) به صورت هکس"""
        return self.private_key.to_string().hex()

    def get_public_key_hex(self):
        """دریافت کلید عمومی برای تایید امضا"""
        return self.public_key.to_string().hex()

    def sign_transaction(self, transaction_data):
        """امضای دیجیتال تراکنش با استفاده از کلید خصوصی (امنیت سطح بیت‌کوین)"""
        data_str = json.dumps(transaction_data, sort_keys=True)
        signature = self.private_key.sign(data_str.encode())
        return signature.hex()


class Block:
    """بلاک‌های غیرقابل تغییر در زنجیره AFIX با ساختار هش‌محور"""

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
    """هسته خودگردان، ایمن و مبتنی بر اثبات کار (PoW) شبکه AFIX"""

    def __init__(self, creator_wallet_address, creator_email="ariobarzan@gmail.com"):
        self.chain = []
        self.pending_transactions = []

        # قوانین ثابت و ساختاری شبکه (مشابه مدل اقتصادی بیت‌کوین)
        self.MAX_SUPPLY = 21000000  # سقف کل ۲۱ میلیون توکن
        self.difficulty = 3         # سختی پایه استخراج
        self.initial_reward = 50    # پاداش اولیه بلاک
        self.halving_interval = 210000 # فاصله زمانی نصف شدن پاداش

        self.creator_email = creator_email
        self.creator_wallet_address = creator_wallet_address

        # صندوق قفل‌شده پشتیبان بازار (۱۰,۰۰۰,۰۰۰ AFIX)
        self.market_vault_address = "AFIX_LOCKED_VAULT_MARKET_RESERVE_10M"

        # ثبت توکن‌های اولیه در پیدایش شبکه
        self.total_minted = 1100000 + 10000000
        self.create_genesis_block()

    def create_genesis_block(self):
        genesis_transactions = [
            {
                "sender": "AFIX_SYSTEM",
                "recipient": self.creator_wallet_address,
                "amount": 1100000,
                "fee": 0,
                "note": f"Ariobarzan Personal Funds linked to Gmail: {self.creator_email}",
            },
            {
                "sender": "AFIX_SYSTEM",
                "recipient": self.market_vault_address,
                "amount": 10000000,
                "fee": 0,
                "note": "PERMANENTLY LOCKED: 10M Market Reserve Vault",
            },
        ]
        genesis_block = Block(0, genesis_transactions, "0")
        self.chain.append(genesis_block)

    def get_balance(self, address):
        """محاسبه دقیق موجودی از روی کل تاریخچه بلاک‌چین (احتساب مبلغ و کارمزد)"""
        balance = 0
        for block in self.chain:
            for tx in block.transactions:
                if tx["recipient"] == address:
                    balance += tx["amount"]
                if tx["sender"] == address:
                    total_deduction = tx["amount"] + tx.get("fee", 0)
                    balance -= total_deduction
        return balance

    def verify_signature(self, public_key_hex, signature_hex, transaction_data):
        """بررسی اعتبار امضای دیجیتال فرستنده با کلید عمومی"""
        try:
            public_key_bytes = bytes.fromhex(public_key_hex)
            sig_bytes = bytes.fromhex(signature_hex)
            vk = VerifyingKey.from_string(public_key_bytes, curve=SECP256k1)
            data_str = json.dumps(transaction_data, sort_keys=True)
            return vk.verify(sig_bytes, data_str.encode())
        except Exception:
            return False

    def add_transaction(self, sender, recipient, amount, signature=None, public_key_hex=None):
        # بررسی قفل بودن صندوق بازار
        if sender == self.market_vault_address:
            print("❌ خطای امنیتی: صندوق ۱۰ میلیونی پشتیبان بازار قفل است.")
            return False

        if amount <= 0:
            print("❌ خطای امنیتی: مقدار تراکنش باید بیشتر از صفر باشد.")
            return False

        fee = 0.0001
        total_cost = amount + fee

        sender_balance = self.get_balance(sender)
        if sender_balance < total_cost:
            print(f"❌ خطای امنیتی: موجودی کافی نیست. موجودی: {sender_balance} | نیاز: {total_cost}")
            return False

        transaction = {
            "sender": sender,
            "recipient": recipient,
            "amount": amount,
            "fee": fee,
            "timestamp": time(),
        }

        # اگر تراکنش سیستمی نباشد، امضای دیجیتال الزامی است
        if sender != "AFIX_SYSTEM":
            if not signature or not public_key_hex:
                print("❌ خطای امنیتی: تراکنش نیازمند امضای دیجیتال است.")
                return False
            if not self.verify_signature(public_key_hex, signature, transaction):
                print("❌ خطای امنیتی: امضای دیجیتال نامعتبر است.")
                return False

        self.pending_transactions.append(transaction)
        return True

    def mine_block(self, miner_address):
        if self.total_minted >= self.MAX_SUPPLY:
            reward = 0
        else:
            halvings = len(self.chain) // self.halving_interval
            reward = self.initial_reward / (2**halvings)
            reward = max(reward, 0.0001)
            if self.total_minted + reward > self.MAX_SUPPLY:
                reward = self.MAX_SUPPLY - self.total_minted

        block_transactions = list(self.pending_transactions)
        total_fees = sum(tx.get("fee", 0) for tx in block_transactions)
        final_miner_reward = reward + total_fees

        if final_miner_reward > 0:
            reward_tx = {
                "sender": "AFIX_NETWORK_REWARD",
                "recipient": miner_address,
                "amount": final_miner_reward,
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
        return new_block, final_miner_reward


# --- اجرای اصلی و ساخت کلیدها و آدرس اختصاصی شما ---
if __name__ == "__main__":
    # ۱. تولید کیف پول اصلی شما (با استاندارد رمزنگاری SECP256k1 دقیقاً مثل بیت‌کوین)
    my_wallet = Wallet()
    my_address = my_wallet.get_address()
    my_private_key = my_wallet.get_private_key_hex()

    MY_GMAIL = "ariobarzan@gmail.com"
    network = AfixMainnet(creator_wallet_address=my_address, creator_email=MY_GMAIL)

    print("==================================================")
    print("       AFIX Network Mainnet Core Node            ")
    print("       Creator: Ariobarzan                       ")
    print("==================================================")
    print(f"👤 نام مالک: آریوبرزن")
    print(f"📧 ایمیل احراز هویت: {network.creator_email}")
    print(f"📍 آدرس اختصاصی کیف پول: {my_address}")
    print(f"🔑 کلید خصوصی (محرمانه - SHA-256 / ECDSA): {my_private_key}")
    print(f"💰 موجودی فعال کیف پول: {network.get_balance(my_address):,} واحد AFIX")
    print(f"🔒 ذخیره قفل‌شده استراتژیک: {network.get_balance(network.market_vault_address):,} واحد AFIX")
    print(f"🌐 سقف عرضه کل شبکه: {network.MAX_SUPPLY:,} واحد AFIX")
    print("--------------------------------------------------")

    # تست امضای دیجیتال و تراکنش با کلید خصوصی شما
    test_recipient = "AFIX_TEST_RECEIVER_ADDRESS"
    tx_data = {
        "sender": my_address,
        "recipient": test_recipient,
        "amount": 10.0,
        "fee": 0.0001,
        "timestamp": time()
    }
    signature = my_wallet.sign_transaction(tx_data)
    print(f"✍️ نمونه امضای دیجیتال تراکنش شما: {signature[:32]}...")
